#!/usr/bin/env python3
"""Live Indian market data for the pre-market checklist and for the day trader: every figure carries where it came from,
when, and whether it is real time or delayed.

  python pulsedge-bot/live_market.py            # print the live view
  python pulsedge-bot/live_market.py --write    # write pulsedge/data/live.json

Sources (all free and unofficial; fine for a personal tool, replace with a licensed feed before charging for access):
- NSE's own site (www.nseindia.com/api), which answers GitHub's runners and is live to the minute:
    allIndices      Nifty 50, Bank Nifty, Fin Nifty, Midcap Select, India VIX and every sector index: last, open, high,
                    low, previous close, advances and declines (also market-wide), stamped "27-Nov-2026 13:47"
    marketStatus    whether the capital market is open
    option-chain-v3 open interest, change in OI, volume, IV and prices for every strike (Nifty and Bank Nifty)
    historicalOR    daily index OHLC, for the previous session's levels and pivots
- TradingView's public screener: GIFT Nifty (real time), Asia, FX, gold and bond yields (real time), and the
  instruments NSE doesn't give (US indices and futures 10 minutes late, crude 10 minutes late, Nifty futures 15).
Quality of each figure: "realtime", "delayed_10m" / "delayed_15m", or "final" (the market is closed and this is the
last session's close). A figure that couldn't be fetched is left out and named under "errors", never guessed.
"""
import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA = os.path.normpath(os.path.join(HERE, "..", "pulsedge", "data"))
LIVE = os.path.join(DATA, "live.json")
IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SCHEMA = 1
LIVE_WINDOW_S = 300     # NSE stamps its figures to the minute and they reach its API one to three minutes later: still its live feed

# NSE index names we keep
NSE_INDICES = {"nifty": "NIFTY 50", "banknifty": "NIFTY BANK", "finnifty": "NIFTY FINANCIAL SERVICES",
               "midcpnifty": "NIFTY MIDCAP SELECT", "next50": "NIFTY NEXT 50", "vix": "INDIA VIX",
               "midcap100": "NIFTY MIDCAP 100", "smallcap100": "NIFTY SMALLCAP 100"}
SECTOR_KEY = "SECTORAL"
# TradingView: key -> (ticker, label). update_mode on the row says real time or delayed.
TV_SET = {
    "gift": ("NSEIX:NIFTY1!", "GIFT Nifty (futures)"), "niftyfut": ("NSE:NIFTY1!", "Nifty futures (NSE)"),
    "spx": ("SP:SPX", "S&P 500"), "ndx": ("NASDAQ:NDX", "Nasdaq-100"), "dji": ("DJ:DJI", "Dow Jones"),
    "es": ("CME_MINI:ES1!", "S&P 500 futures"), "nq": ("CME_MINI:NQ1!", "Nasdaq futures"), "ym": ("CBOT_MINI:YM1!", "Dow futures"),
    "us30cfd": ("OANDA:US30USD", "Dow (real-time CFD)"),
    "nikkei": ("TVC:NI225", "Nikkei 225"), "hangseng": ("TVC:HSI", "Hang Seng"), "kospi": ("TVC:KOSPI", "KOSPI"),
    "usdinr": ("FX_IDC:USDINR", "USD/INR"), "dxy": ("TVC:DXY", "Dollar index"), "usdjpy": ("FX:USDJPY", "USD/JPY"),
    "brent": ("ICEEUR:BRN1!", "Brent crude"), "wti": ("NYMEX:CL1!", "WTI crude"),
    "gold": ("TVC:GOLD", "Gold"), "silver": ("TVC:SILVER", "Silver"),
    "us10y": ("TVC:US10Y", "US 10Y yield"), "in10y": ("TVC:IN10Y", "India 10Y yield"),
    # the same Indian instruments from TradingView, used only if NSE can't be reached (15 minutes late)
    "nifty_tv": ("NSE:NIFTY", "Nifty 50"), "banknifty_tv": ("NSE:BANKNIFTY", "Bank Nifty"), "vix_tv": ("NSE:INDIAVIX", "India VIX"),
}

_cache = {}          # in-memory, for the fast lane's long loop: {name: (time, value)}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def now_ist():
    return datetime.now(IST)


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def parse_ts(s):
    """'27-Nov-2026 13:47' or '27-Nov-2026 13:47:31' (NSE, India time) -> aware datetime, or None."""
    s = str(s or "").strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST)
        except ValueError:
            pass
    return None


def fnum(v):
    try:
        x = float(str(v).replace(",", ""))
        return x if x == x else None
    except (TypeError, ValueError):
        return None


# ---------- NSE ----------

class NSE:
    """A cookie-keeping session. NSE's home page answers 403 to cloud runners but its API still answers once the
    request looks like a browser's, so the warm-up is allowed to fail."""

    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.warm = False

    def _warm(self):
        for u in ("https://www.nseindia.com/", "https://www.nseindia.com/option-chain"):
            try:
                self.op.open(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=12).read()
            except Exception:  # noqa: BLE001 - expected: 403 on the home page
                pass
        self.warm = True

    def get(self, path, referer="https://www.nseindia.com/option-chain"):
        if not self.warm:
            self._warm()
        last = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request("https://www.nseindia.com/api/" + path, headers={
                    "User-Agent": UA, "Accept": "*/*", "Referer": referer, "Accept-Language": "en-US,en;q=0.9"})
                with self.op.open(req, timeout=20) as r:
                    return json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.5)
                self.warm = False if attempt == 1 else self.warm
                if attempt == 1:
                    self._warm()
        raise last


def market_status(nse):
    j = nse.get("marketStatus")
    cap = next((m for m in j.get("marketState", []) if m.get("market") == "Capital Market"), {})
    status = str(cap.get("marketStatus") or "")
    return {"status": status or None, "open": status.lower() == "open", "message": cap.get("marketStatusMessage"),
            "as_of": iso(parse_ts(cap.get("tradeDate")))}


def sector_name(index):
    """'NIFTY PSU BANK' -> 'PSU Bank', 'NIFTY IT' -> 'IT', 'NIFTY OIL & GAS' -> 'Oil & Gas'."""
    keep = {"IT", "FMCG", "PSU", "MNC", "CPSE", "PSE", "&", "EV", "ESG"}
    return " ".join(w if w in keep else w.capitalize() for w in index.replace("NIFTY ", "", 1).split())


def indices(nse):
    """NSE's allIndices -> ({key: row}, sectors, market breadth, as_of)."""
    j = nse.get("allIndices")
    rows = {d.get("index"): d for d in j.get("data", []) if isinstance(d, dict)}
    out = {}
    for k, name in NSE_INDICES.items():
        d = rows.get(name)
        if d and fnum(d.get("last")) is not None:
            out[k] = {"v": fnum(d["last"]), "chg": fnum(d.get("variation")), "chg_pct": fnum(d.get("percentChange")),
                      "prev": fnum(d.get("previousClose")), "open": fnum(d.get("open")), "high": fnum(d.get("high")),
                      "low": fnum(d.get("low")), "year_high": fnum(d.get("yearHigh")), "year_low": fnum(d.get("yearLow")),
                      "pe": fnum(d.get("pe")), "advances": fnum(d.get("advances")), "declines": fnum(d.get("declines")),
                      "label": name}
    sectors = sorted(({"name": sector_name(d["index"]), "chg_pct": fnum(d.get("percentChange")), "v": fnum(d.get("last"))}
                      for d in rows.values() if SECTOR_KEY in str(d.get("key", "")) and fnum(d.get("percentChange")) is not None),
                     key=lambda s: -s["chg_pct"])
    breadth = {"advances": fnum(j.get("advances")), "declines": fnum(j.get("declines")), "unchanged": fnum(j.get("unchanged"))}
    return out, sectors, breadth, parse_ts(j.get("timestamp"))


def history(nse, index_name, days=14):
    """Daily OHLC from NSE: [{d, o, h, l, c}] oldest first."""
    end = now_ist().date()
    start = end - timedelta(days=days)
    q = urllib.parse.urlencode({"indexType": index_name, "from": start.strftime("%d-%m-%Y"), "to": end.strftime("%d-%m-%Y")}, quote_via=urllib.parse.quote)
    j = nse.get("historicalOR/indicesHistory?" + q, "https://www.nseindia.com/reports-indices-historical-index-data")
    out = []
    for r in j.get("data", []):
        try:
            d = datetime.strptime(str(r["EOD_TIMESTAMP"]).title(), "%d-%b-%Y").date().isoformat()
        except (KeyError, ValueError):
            continue
        o, h, lo, c = (fnum(r.get(k)) for k in ("EOD_OPEN_INDEX_VAL", "EOD_HIGH_INDEX_VAL", "EOD_LOW_INDEX_VAL", "EOD_CLOSE_INDEX_VAL"))
        if None not in (o, h, lo, c):
            out.append({"d": d, "o": o, "h": h, "l": lo, "c": c})
    return sorted(out, key=lambda r: r["d"])


def levels(rows, today):
    """The previous session's range and the classic pivots and central pivot range that follow from it."""
    prev = [r for r in rows if r["d"] < today]
    if not prev:
        return None
    p = prev[-1]
    h, lo, c = p["h"], p["l"], p["c"]
    pv = (h + lo + c) / 3
    bc = (h + lo) / 2
    tc = 2 * pv - bc
    lo_c, hi_c = min(bc, tc), max(bc, tc)
    rng = [r["h"] - r["l"] for r in prev[-5:]]
    return {"prev": {"date": p["d"], "open": p["o"], "high": h, "low": lo, "close": c},
            "pivots": {"p": round(pv, 2), "r1": round(2 * pv - lo, 2), "r2": round(pv + (h - lo), 2), "r3": round(h + 2 * (pv - lo), 2),
                       "s1": round(2 * pv - h, 2), "s2": round(pv - (h - lo), 2), "s3": round(lo - 2 * (h - pv), 2)},
            "cpr": {"top": round(hi_c, 2), "bottom": round(lo_c, 2), "width_pct": round((hi_c - lo_c) / pv * 100, 3),
                    "read": "narrow: a trending day is more likely" if (hi_c - lo_c) / pv * 100 < 0.15 else
                            "wide: a range-bound day is more likely" if (hi_c - lo_c) / pv * 100 > 0.4 else "normal"},
            "avg_range_5d": round(sum(rng) / len(rng), 2) if rng else None,
            "prev_range": round(h - lo, 2)}


# ---------- options ----------

def max_pain(strikes):
    """The strike where option buyers collectively lose most: minimises the payout of all open interest."""
    best, best_pay = None, None
    for k in strikes:
        pay = sum(ce * max(k - s, 0) + pe * max(s - k, 0) for s, (ce, pe) in strikes.items())
        if best_pay is None or pay < best_pay:
            best, best_pay = k, pay
    return best


def option_metrics(chain, today):
    """From NSE's option-chain-v3 reply: PCR, max pain, the call and put walls (largest open interest), the at-the-money
    straddle and IV, and where open interest was added today."""
    rec = chain.get("records", chain)
    data = rec.get("data", [])
    spot = fnum(rec.get("underlyingValue"))
    if not data or not spot:
        return None
    oi, vol, strikes, rows = {"ce": 0.0, "pe": 0.0}, {"ce": 0.0, "pe": 0.0}, {}, []
    chg = {"ce": 0.0, "pe": 0.0}
    for d in data:
        k = fnum(d.get("strikePrice"))
        if k is None:
            continue
        ce, pe = d.get("CE") or {}, d.get("PE") or {}
        ce_oi, pe_oi = fnum(ce.get("openInterest")) or 0.0, fnum(pe.get("openInterest")) or 0.0
        strikes[k] = (ce_oi, pe_oi)
        oi["ce"] += ce_oi
        oi["pe"] += pe_oi
        vol["ce"] += fnum(ce.get("totalTradedVolume")) or 0.0
        vol["pe"] += fnum(pe.get("totalTradedVolume")) or 0.0
        chg["ce"] += fnum(ce.get("changeinOpenInterest")) or 0.0
        chg["pe"] += fnum(pe.get("changeinOpenInterest")) or 0.0
        rows.append((k, ce, pe))
    if not strikes or not oi["ce"]:
        return None
    atm = min(strikes, key=lambda k: abs(k - spot))
    a = next(((ce, pe) for k, ce, pe in rows if k == atm), ({}, {}))
    c_ltp, p_ltp = fnum(a[0].get("lastPrice")), fnum(a[1].get("lastPrice"))
    ivs = [x for x in (fnum(a[0].get("impliedVolatility")), fnum(a[1].get("impliedVolatility"))) if x]
    above = {k: v[0] for k, v in strikes.items() if k >= spot and v[0]}
    below = {k: v[1] for k, v in strikes.items() if k <= spot and v[1]}
    call_wall = max(above, key=above.get) if above else None
    put_wall = max(below, key=below.get) if below else None
    top = lambda m, n=3: [{"strike": int(k), "oi": int(v)} for k, v in sorted(m.items(), key=lambda x: -x[1])[:n]]  # noqa: E731
    straddle = round(c_ltp + p_ltp, 2) if c_ltp and p_ltp else None
    pcr = oi["pe"] / oi["ce"] if oi["ce"] else None
    ts = parse_ts(rec.get("timestamp"))
    return {"spot": spot, "atm": int(atm), "pcr_oi": round(pcr, 3) if pcr else None,
            "pcr_volume": round(vol["pe"] / vol["ce"], 3) if vol["ce"] else None,
            "pcr_read": None if pcr is None else ("put-heavy: support is being built (bullish lean)" if pcr >= 1.2 else
                                                 "call-heavy: resistance is being built (bearish lean)" if pcr <= 0.7 else "balanced"),
            "max_pain": int(max_pain(strikes)) if strikes else None,
            "call_wall": int(call_wall) if call_wall else None, "put_wall": int(put_wall) if put_wall else None,
            "top_call_oi": top(above), "top_put_oi": top(below),
            "oi_total": {"calls": int(oi["ce"]), "puts": int(oi["pe"])}, "oi_change": {"calls": int(chg["ce"]), "puts": int(chg["pe"])},
            "straddle": straddle, "implied_move_pct": round(straddle / spot * 100, 2) if straddle else None,
            "atm_iv": round(sum(ivs) / len(ivs), 2) if ivs else None,
            "as_of": iso(ts), "session": "today" if ts and ts.date().isoformat() == today else "previous"}


def options(nse, symbol, today):
    info = nse.get(f"option-chain-contract-info?symbol={symbol}")
    exps = [e for e in info.get("expiryDates", []) if datetime.strptime(e, "%d-%b-%Y").date().isoformat() >= today]
    if not exps:
        return None
    chain = nse.get("option-chain-v3?type=Indices&symbol=%s&expiry=%s" % (symbol, urllib.parse.quote(exps[0])))
    m = option_metrics(chain, today)
    if m:
        m["expiry"] = datetime.strptime(exps[0], "%d-%b-%Y").date().isoformat()
        m["next_expiries"] = [datetime.strptime(e, "%d-%b-%Y").date().isoformat() for e in exps[1:3]]
    return m


# ---------- TradingView ----------

def tv_quality(mode):
    mode = str(mode or "")
    if mode == "streaming":
        return "realtime"
    import re
    m = re.search(r"delayed_streaming_(\d+)", mode)
    return f"delayed_{int(m.group(1)) // 60}m" if m else "unknown"


def tradingview(now):
    import quotes as tv
    rows = tv.scan([t for t, _ in TV_SET.values()], columns=("close", "change", "update_mode", "open", "high", "low"))
    out = {}
    for k, (ticker, label) in TV_SET.items():
        r = rows.get(ticker)
        if not r or not isinstance(r[0], (int, float)) or not r[0]:
            continue
        out[k] = {"v": r[0], "chg_pct": round(r[1], 3) if isinstance(r[1], (int, float)) else None, "open": r[3], "high": r[4], "low": r[5],
                  "quality": tv_quality(r[2]), "src": "TradingView", "as_of": iso(now), "label": label}
    return out


# ---------- the whole picture ----------

_shared = {}


def shared_nse():
    """One cookie-keeping NSE session for the whole process, so the fast lane's long loop doesn't warm up on every tick."""
    if "nse" not in _shared:
        _shared["nse"] = NSE()
    return _shared["nse"]


def cached(name, ttl, fn):
    """Fetch at most every ttl seconds within one process (the fast lane keeps running for hours)."""
    t, v = _cache.get(name, (0, None))
    if time.time() - t < ttl and v is not None:
        return v
    v = fn()
    _cache[name] = (time.time(), v)
    return v


def build(now=None, nse=None, option_ttl=180):
    """The live view. Anything that fails is named under "errors" and left out."""
    now = now or now_ist()
    today = now.date().isoformat()
    nse = nse or shared_nse()
    errors, out = [], {"schema": SCHEMA, "as_of": iso(now), "instruments": {}, "market": {}, "breadth": {}, "sectors": [], "levels": {}, "options": {}}

    status = None
    try:
        status = market_status(nse)
        out["market"] = status
    except Exception as e:  # noqa: BLE001
        errors.append(f"marketStatus: {type(e).__name__} {str(e)[:80]}")
    is_open = bool(status and status["open"])

    nse_rows = {}
    try:
        nse_rows, sectors, breadth, ts = indices(nse)
        out["sectors"], out["breadth"] = sectors, breadth
        for k, r in nse_rows.items():
            age = int((now - ts).total_seconds()) if ts else None
            q = "realtime" if is_open and (age is None or age <= LIVE_WINDOW_S) else ("final" if not is_open else "stale")
            out["instruments"][k] = {**r, "quality": q, "src": "NSE", "as_of": iso(ts), "age_s": age}
    except Exception as e:  # noqa: BLE001
        errors.append(f"allIndices: {type(e).__name__} {str(e)[:80]}")

    try:
        tvr = tradingview(now)
        for k, r in tvr.items():
            if not k.endswith("_tv"):
                out["instruments"].setdefault(k, r)
        if not nse_rows:                                          # NSE down: fall back to TradingView's 15-minute-late copy
            for k, tk in (("nifty", "nifty_tv"), ("banknifty", "banknifty_tv"), ("vix", "vix_tv")):
                if tk in tvr:
                    out["instruments"][k] = tvr[tk]
    except Exception as e:  # noqa: BLE001
        errors.append(f"TradingView: {type(e).__name__} {str(e)[:80]}")

    for key, name in (("nifty", "NIFTY 50"), ("banknifty", "NIFTY BANK")):
        try:
            rows = cached(f"hist:{key}:{today}", 6 * 3600, lambda n=name: history(nse, n))
            lv = levels(rows, today)
            if lv:
                out["levels"][key] = lv
        except Exception as e:  # noqa: BLE001
            errors.append(f"history {name}: {type(e).__name__} {str(e)[:80]}")

    ttl = option_ttl if is_open else 900                         # the chain barely moves while the market is shut
    for key, sym in (("nifty", "NIFTY"), ("banknifty", "BANKNIFTY")):
        try:
            m = cached(f"opt:{key}", ttl, lambda s=sym: options(nse, s, today))
            if m:
                out["options"][key] = m
        except Exception as e:  # noqa: BLE001
            errors.append(f"options {sym}: {type(e).__name__} {str(e)[:80]}")
    out["errors"] = errors
    return out


def write(live):
    tmp = LIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(live, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, LIVE)


def summary(live):
    ins = live.get("instruments", {})
    bits = []
    for k in ("nifty", "banknifty", "vix", "gift"):
        i = ins.get(k)
        if i:
            bits.append(f"{k} {i['v']:,.2f} ({i.get('chg_pct')}%) {i.get('quality')}/{i.get('src')}")
    o = (live.get("options") or {}).get("nifty")
    if o:
        bits.append(f"nifty options {o['expiry']}: PCR {o['pcr_oi']}, max pain {o['max_pain']}, walls {o['put_wall']}/{o['call_wall']}, straddle {o['straddle']}")
    lv = (live.get("levels") or {}).get("nifty")
    if lv:
        bits.append(f"nifty levels from {lv['prev']['date']}: P {lv['pivots']['p']} R1 {lv['pivots']['r1']} S1 {lv['pivots']['s1']}")
    return "; ".join(bits) + (f" | errors: {live['errors']}" if live.get("errors") else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    live = build()
    log(summary(live))
    if a.write:
        write(live)
    else:
        print(json.dumps(live, indent=1)[:6000])


if __name__ == "__main__":
    main()
