#!/usr/bin/env python3
"""Build pulsedge/data/premarket.json (the terminal's pre-market panel) from free quotes.

  python pulsedge-bot/premarket.py            # write premarket.json
  python pulsedge-bot/premarket.py --dry-run  # print it instead

Quotes come from TradingView's public screener first (it is also the only free source of GIFT Nifty), then CNBC's
public quote service and Yahoo Finance's chart endpoint for anything it misses (all unofficial, personal use; swap for a
licensed feed before charging for access). Stocks in focus come from today's feed.json.
Any quote that can't be fetched is left out rather than guessed.

Outside NSE hours the first checklist item is GIFT Nifty's opening indication: GIFT Nifty (NSE IX, traded from 06:30 IST
and overnight) against Nifty futures' last close on NSE. Comparing it with the Nifty 50 index instead would add the
futures premium and overstate the gap. The terminal shows the same prices live (it reads TradingView from the
visitor's browser); this file is the 15-minute snapshot.
"""
import argparse
import collections
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import quotes as tv  # noqa: E402  (TradingView's screener)
import live_market as lm  # noqa: E402  (NSE's live indices, VIX and option chain; per-figure quality)
DATA = os.path.join(HERE, "..", "pulsedge", "data")
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

QUOTES = {
    "nifty": "^NSEI", "banknifty": "^NSEBANK", "vix": "^INDIAVIX",
    "dow": "^DJI", "spx": "^GSPC", "nasdaq": "^IXIC", "nqf": "NQ=F", "esf": "ES=F",
    "nikkei": "^N225", "hangseng": "^HSI", "kospi": "^KS11",
    "dxy": "DX-Y.NYB", "usdinr": "INR=X", "brent": "BZ=F", "wti": "CL=F", "gold": "GC=F", "us10y": "^TNX",
}


# The same instruments on TradingView, plus GIFT Nifty and Nifty futures for the opening indication.
TV = {
    "gift": "NSEIX:NIFTY1!", "niftyfut": "NSE:NIFTY1!",
    "nifty": "NSE:NIFTY", "banknifty": "NSE:BANKNIFTY", "vix": "NSE:INDIAVIX",
    "dow": "DJ:DJI", "spx": "SP:SPX", "nasdaq": "NASDAQ:IXIC", "nqf": "CME_MINI:NQ1!", "esf": "CME_MINI:ES1!",
    "nikkei": "TVC:NI225", "hangseng": "TVC:HSI", "kospi": "TVC:KOSPI",
    "dxy": "TVC:DXY", "usdinr": "FX_IDC:USDINR", "brent": "ICEEUR:BRN1!", "wti": "NYMEX:CL1!", "gold": "TVC:GOLD", "us10y": "TVC:US10Y",
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# Same instruments on CNBC (a tuple lists candidate symbols, first that parses wins); anything missing or unparseable falls back to Yahoo.
CNBC = {
    "nifty": ".NSEI", "banknifty": ".NSEBANK", "vix": (".NIFVIX", ".INVIXN", ".INDIAVIX", "INDIAVIX"),
    "dow": ".DJI", "spx": ".SPX", "nasdaq": ".IXIC", "nqf": "@ND.1", "esf": "@SP.1",
    "nikkei": ".N225", "hangseng": ".HSI", "kospi": ".KS11",
    "dxy": ".DXY", "usdinr": "INR=", "brent": "@LCO.1", "wti": "@CL.1", "gold": "@GC.1", "us10y": "US10Y",
}


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def cnbc_quotes():
    url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols="
           + urllib.parse.quote("|".join(x for v in CNBC.values() for x in (v if isinstance(v, tuple) else (v,)))) + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.load(r)["FormattedQuoteResult"]["FormattedQuote"]
    by_sym = {row.get("symbol"): row for row in rows}
    out = {}
    for k, syms in CNBC.items():
        for sym in syms if isinstance(syms, tuple) else (syms,):
            row = by_sym.get(sym) or {}
            price, chg = num(row.get("last")), num(row.get("change_pct"))
            # change_pct is the last session's move; previous_day_closing rolls over to the latest close
            # once a session ends, which would make every closed market read 0.00%.
            if price and chg is not None and chg > -100:
                out[k] = {"price": price, "prev": price / (1 + chg / 100), "chg": chg}
                break
            prev = num(row.get("previous_day_closing"))
            if price and prev:
                out[k] = {"price": price, "prev": prev, "chg": (price / prev - 1) * 100}
                break
    return out


def tv_quotes():
    rows = tv.scan(TV.values())
    out = {}
    for k, t in TV.items():
        try:
            price, chg = float(rows[t][0]), float(rows[t][1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if price and chg > -100:
            out[k] = {"price": price, "prev": price / (1 + chg / 100), "chg": chg, "delay": tv.delay_of(rows[t][2])}
    return out


def opening_word(gp):
    """GIFT Nifty's gap against Nifty futures, in words."""
    if abs(gp) < 0.15:
        return "flat start indicated"
    if abs(gp) < 0.5:
        return "slightly higher start indicated" if gp > 0 else "slightly lower start indicated"
    return "gap-up start indicated" if gp > 0 else "gap-down start indicated"


_SESSION = {}


def session():
    # Yahoo rate-limits cookieless requests (HTTP 429), so pick up its consent cookie and crumb once.
    if "opener" not in _SESSION:
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        op.addheaders = [("User-Agent", UA), ("Accept", "*/*")]
        try:
            op.open("https://fc.yahoo.com", timeout=8).read()
        except Exception:
            pass  # fc.yahoo.com answers 404 but still sets the cookie
        try:
            _SESSION["crumb"] = op.open("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=8).read().decode().strip()
        except Exception as e:
            log(f"  crumb: none ({type(e).__name__}: {e})")
            _SESSION["crumb"] = ""
        _SESSION["opener"] = op
    return _SESSION["opener"], _SESSION["crumb"]


def quote(sym):
    op, crumb = session()
    path = "/v8/finance/chart/" + urllib.parse.quote(sym) + "?range=5d&interval=1d" + ("&crumb=" + urllib.parse.quote(crumb) if crumb else "")
    err = None
    for host in ("https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com"):
        try:
            with op.open(host + path, timeout=8) as r:
                res = json.load(r)["chart"]["result"][0]
            break
        except urllib.error.HTTPError as e:
            err = e
            time.sleep(1)
    else:
        raise err
    meta = res["meta"]
    price = meta.get("regularMarketPrice")
    closes = [c for c in (res.get("indicators", {}).get("quote", [{}])[0].get("close") or []) if c is not None]
    prev = meta.get("chartPreviousClose") if len(closes) < 2 else closes[-2]
    if price is None or not prev:
        raise ValueError("no price")
    return {"price": float(price), "prev": float(prev), "chg": (float(price) / float(prev) - 1) * 100}


def fmt(v, d=2):
    return f"{v:,.{d}f}"


def pct(v):
    return f"{v:+.2f}%"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--writer", default="premarket", help="who is writing: the 15-minute run, or the fast lane's frequent ticks (\"live\")")
    ap.add_argument("--if-stale", type=int, default=0, metavar="SECONDS",
                    help="do nothing if the fast lane's ticks wrote premarket.json within this many seconds")
    args = ap.parse_args(argv)
    dry = args.dry_run
    if args.if_stale and not dry:
        try:
            with open(os.path.join(DATA, "premarket.json"), encoding="utf-8") as fh:
                cur = json.load(fh)
            age = (NOW - datetime.fromisoformat(cur["updated"])).total_seconds()
            if cur.get("writer") == "live" and age < args.if_stale:
                log(f"premarket.json was written {age:.0f} s ago by the fast lane's ticks; leaving it")
                return
        except (OSError, ValueError, KeyError):
            pass

    q = {}
    try:
        q = tv_quotes()
        log(f"  TradingView: {len(q)}/{len(TV)}")
    except Exception as e:
        log(f"  TradingView: failed ({type(e).__name__}: {e})")
    if any(k not in q for k in CNBC):
        try:
            got = cnbc_quotes()
            for k, v in got.items():
                q.setdefault(k, v)
            log(f"  CNBC: {len(got)}/{len(CNBC)}")
        except Exception as e:
            log(f"  CNBC: failed ({type(e).__name__}: {e})")
    misses = 0
    for k, sym in QUOTES.items():
        if k in q:
            continue
        if misses >= 3:
            log(f"  {sym}: skipped (Yahoo keeps failing)")
            continue
        try:
            q[k] = quote(sym)
            misses = 0
            time.sleep(0.3)
        except Exception as e:
            misses += 1
            log(f"  {sym}: skipped ({type(e).__name__}: {e})")
    log(f"quotes: {len(q)} of {len(set(TV) | set(QUOTES))}")
    # NSE's own live data replaces TradingView's 15-minute-late Nifty, Bank Nifty and India VIX
    live = {}
    try:
        live = lm.build()
        log("live: " + lm.summary(live))
    except Exception as e:  # noqa: BLE001
        log(f"  live market data failed ({type(e).__name__}: {e})")
    ins = live.get("instruments", {})
    for k in ("nifty", "banknifty", "vix"):
        i = ins.get(k)
        if i and i.get("src") == "NSE" and i.get("prev") and i.get("chg_pct") is not None:
            q[k] = {"price": i["v"], "prev": i["prev"], "chg": i["chg_pct"], "delay": 0, "src": "NSE"}
    if len(q) < 5:
        log("too few quotes; leaving premarket.json unchanged")
        return

    checklist, up, down = [], 0, 0

    def rank(quality):
        return 0 if quality == "realtime" else 1 if quality == "final" else 10 + int(quality[8:-1]) if str(quality).startswith("delayed_") else 99

    def qlabel(quality):
        return {"realtime": "live", "final": "final close", "scheduled": "scheduled"}.get(quality) or (
            quality.replace("delayed_", "delayed ").replace("m", " min") if str(quality).startswith("delayed_") else "age unknown")

    def stamp(keys, quality=None, src=None):
        """Where a checklist item's numbers came from, whether they are real time, and as of when."""
        have = [ins[k] for k in keys if k in ins]
        qual = quality or (max((i.get("quality", "unknown") for i in have), key=rank) if have else "unknown")
        srcs = src or " + ".join(dict.fromkeys(i.get("src", "") for i in have if i.get("src"))) or "other"
        ats = [i["as_of"] for i in have if i.get("as_of")]
        return {"quality": qual, "src": srcs, "as_of": min(ats) if ats else live.get("as_of")}

    def add(title, dir_, value, detail, keys=(), quality=None, src=None, count=True, as_of=None, show_time=True):
        nonlocal up, down
        if count:
            up += dir_ == "up"
            down += dir_ == "down"
        st = stamp(keys, quality, src)
        if as_of:
            st["as_of"] = as_of
        try:
            when = datetime.fromisoformat(st["as_of"])
            at = (f"session of {when:%d %b}" if len(st["as_of"]) == 10 else
                  f"as of {when:%H:%M} IST" if when.date() == NOW.date() else f"as of {when:%d %b %H:%M} IST") if show_time else ""
        except (TypeError, ValueError):
            at = ""
        detail = list(detail) + [f"{st['src']} · {qlabel(st['quality'])}" + (f" · {at}" if at else "")]
        checklist.append({"title": title, "dir": dir_, "value": value, "detail": detail, **st})

    # US cash indices are final from their close (about 02:00 IST) until the next open (about 19:30 IST)
    us_closed = (NOW.weekday() < 5 and 3 <= NOW.hour < 19) or NOW.weekday() in (5, 6)

    def tone(ch, inverse=False, band=0.25):
        if ch is None or abs(ch) < band:
            return "flat"
        good = ch > 0 if not inverse else ch < 0
        return "up" if good else "down"

    in_hours = NOW.weekday() < 5 and (9, 15) <= (NOW.hour, NOW.minute) < (15, 30)
    opening = None
    if not in_hours and "gift" in q and "niftyfut" in q:
        g, f = q["gift"]["price"], q["niftyfut"]["price"]
        gap, gp = g - f, (g / f - 1) * 100
        opening = opening_word(gp)
        det = []
        if "nifty" in q:
            n = q["nifty"]
            det += [f"Nifty 50 last close {fmt(n['price'])} ({pct(n['chg'])})",
                    f"Implied open near {fmt(n['price'] * (1 + gp / 100), 0)}"]
        det.append(f"Against Nifty futures' last close {fmt(f, 1)}")
        add("GIFT Nifty - opening indication", tone(gp, band=0.15),
            f"{fmt(g, 1)} · {gap:+,.0f} pts ({gp:+.2f}%) · {opening}", det, keys=("gift",),
            src="TradingView (GIFT Nifty) against NSE's last close")
    elif "nifty" in q:
        n = q["nifty"]
        det = [f"Previous close {fmt(n['prev'])}"]
        if "gift" in q:
            det.append(f"GIFT Nifty {fmt(q['gift']['price'], 1)} ({pct(q['gift']['chg'])})")
        ni = ins.get("nifty") or {}
        title = ("Nifty 50 live" if ni.get("quality") == "realtime" else "Nifty 50 now (15 min delayed)") if in_hours else "Nifty 50 last close"
        if in_hours and ni.get("high"):
            det.append(f"Today: open {fmt(ni['open'], 1)} · high {fmt(ni['high'], 1)} · low {fmt(ni['low'], 1)}")
        add(title, tone(n["chg"]), f"{fmt(n['price'])} ({pct(n['chg'])})", det, keys=("nifty",))
    us = [k for k in ("dow", "spx", "nasdaq") if k in q]
    if us:
        higher = sum(q[k]["chg"] > 0 for k in us)
        avg = sum(q[k]["chg"] for k in us) / len(us)
        label = "Higher" if higher == len(us) else "Lower" if higher == 0 else f"Mixed — {higher}/{len(us)} higher"
        names = {"dow": "Dow", "spx": "S&P", "nasdaq": "Nasdaq"}
        det = [f"{names[k]} {fmt(q[k]['price'])} {pct(q[k]['chg'])}" for k in us]
        if "nqf" in q:
            det.append(f"Nasdaq futures now {pct(q['nqf']['chg'])}")
        add("US close - Dow/S&P/Nasdaq direction", tone(avg), label, det, keys=("spx", "ndx", "dji", "nq"),
            quality="final" if us_closed else "delayed_10m", show_time=not us_closed,
            src="TradingView (US futures 10 min delayed)")
    asia = [k for k in ("nikkei", "hangseng") if k in q]
    if asia:
        avg = sum(q[k]["chg"] for k in asia) / len(asia)
        names = {"nikkei": "Nikkei", "hangseng": "Hang Seng"}
        mixed = len(asia) == 2 and (q["nikkei"]["chg"] > 0) != (q["hangseng"]["chg"] > 0)
        add("Asian markets live - Nikkei, Hang Seng", "flat" if mixed else tone(avg),
            "Asia mixed" if mixed else ("Asia higher" if avg > 0 else "Asia lower"),
            [f"{names[k]} {fmt(q[k]['price'])} {pct(q[k]['chg'])}" for k in asia], keys=("nikkei", "hangseng"))
    if "dxy" in q or "usdinr" in q:
        fx = [q[k]["chg"] for k in ("dxy", "usdinr") if k in q]
        worst = max(fx)
        det = []
        if "dxy" in q:
            det.append(f"DXY {fmt(q['dxy']['price'])} {pct(q['dxy']['chg'])}")
        if "usdinr" in q:
            det.append(f"USD/INR {fmt(q['usdinr']['price'], 3)} {pct(q['usdinr']['chg'])}")
        add("DXY + USDINR move", tone(worst, inverse=True, band=0.3),
            "Rupee under pressure" if worst >= 0.3 else "No major currency pressure", det, keys=("dxy", "usdinr"))
    if "brent" in q:
        b = q["brent"]
        add("Brent crude level", tone(b["chg"], inverse=True, band=1.0), f"${fmt(b['price'])} {pct(b['chg'])}",
            ["Rising crude hurts India (OMCs, paints, aviation); helps upstream"] if b["chg"] > 1 else [], keys=("brent",))
    if "vix" in q:
        v = q["vix"]
        level = "elevated" if v["price"] >= 18 else "normal" if v["price"] >= 11 else "low"
        vi = ins.get("vix") or {}
        vdet = [f"Previous close {fmt(v['prev'])}"] + ([f"Day range {fmt(vi['low'])}–{fmt(vi['high'])}"] if vi.get("high") and vi.get("low") else [])
        add("India VIX", tone(v["chg"], inverse=True, band=5), f"{fmt(v['price'])} ({pct(v['chg'])}) — {level}", vdet, keys=("vix",))

    # ---- extra context for the day trader: not part of the sentiment score (count=False) ----
    k0 = lambda v: f"{v:,.0f}"  # noqa: E731
    today = NOW.strftime("%Y-%m-%d")
    lv_all, opt_all = live.get("levels", {}), live.get("options", {})
    mkt = live.get("market") or {}
    implied = q["nifty"]["price"] * (1 + gp / 100) if opening and "nifty" in q else None

    def zone(x, lv):
        pv = lv["pivots"]
        ladder = [("S3", pv["s3"]), ("S2", pv["s2"]), ("S1", pv["s1"]), ("Pivot", pv["p"]), ("R1", pv["r1"]), ("R2", pv["r2"]), ("R3", pv["r3"])]
        below = [(n, v) for n, v in ladder if v <= x]
        above = [(n, v) for n, v in ladder if v > x]
        if not below:
            return f"below S3 ({k0(pv['s3'])})"
        if not above:
            return f"above R3 ({k0(pv['r3'])})"
        return f"between {below[-1][0]} {k0(below[-1][1])} and {above[0][0]} {k0(above[0][1])}"

    lv = lv_all.get("nifty")
    if lv:
        pv, cp, pr = lv["pivots"], lv["cpr"], lv["prev"]
        det = [f"Previous session ({pr['date']}): high {fmt(pr['high'], 1)} · low {fmt(pr['low'], 1)} · close {fmt(pr['close'], 1)}",
               f"Resistance R1 {k0(pv['r1'])} · R2 {k0(pv['r2'])} · R3 {k0(pv['r3'])}",
               f"Support S1 {k0(pv['s1'])} · S2 {k0(pv['s2'])} · S3 {k0(pv['s3'])}",
               f"Central pivot range {k0(cp['bottom'])}–{k0(cp['top'])} ({cp['width_pct']:.2f}% wide, {cp['read']})"]
        if lv.get("avg_range_5d"):
            det.append(f"Last session's range {k0(lv['prev_range'])} pts against a 5-day average of {k0(lv['avg_range_5d'])}")
        value = f"Pivot {k0(pv['p'])} · CPR {cp['read'].split(':')[0]}"
        if implied:
            side = "above" if implied > cp["top"] else "below" if implied < cp["bottom"] else "inside"
            det.insert(0, f"GIFT-implied open {k0(implied)} is {side} the CPR, {zone(implied, lv)}")
            value += f" · open {side} CPR"
        b = lv_all.get("banknifty")
        if b:
            det.append(f"Bank Nifty: pivot {k0(b['pivots']['p'])} · R1 {k0(b['pivots']['r1'])} · S1 {k0(b['pivots']['s1'])} · CPR {k0(b['cpr']['bottom'])}–{k0(b['cpr']['top'])}")
        add("Key levels - Nifty pivots and CPR", "flat", value, det, quality="final", src="NSE daily index history (previous session)",
            as_of=pr["date"], count=False)

    def chain_quality(o):
        try:
            age = (NOW - datetime.fromisoformat(o["as_of"])).total_seconds()
        except (TypeError, ValueError, KeyError):
            return "unknown"
        return "realtime" if mkt.get("open") and o.get("session") == "today" and age <= 300 else "final" if not mkt.get("open") else "stale"

    o = opt_all.get("nifty")
    if o:
        value = f"PCR {o['pcr_oi']:.2f} · max pain {k0(o['max_pain'])} · walls {k0(o['put_wall'])} / {k0(o['call_wall'])}" if o.get("pcr_oi") and o.get("max_pain") and o.get("put_wall") and o.get("call_wall") else "Option chain loaded"
        det = [f"Nifty options expiring {o['expiry']}" + (" (today)" if o["expiry"] == today else "") + f" · at-the-money strike {k0(o['atm'])}"
               + ("" if o.get("session") == "today" else " · figures are from the previous session")]
        if o.get("pcr_read"):
            det.append(f"Put/call ratio by open interest {o['pcr_oi']:.2f} ({o['pcr_read']})" + (f"; by volume {o['pcr_volume']:.2f}" if o.get("pcr_volume") else ""))
        if o.get("straddle"):
            det.append(f"At-the-money straddle ₹{o['straddle']:,.0f} — the market is pricing about ±{o['implied_move_pct']:.2f}% (±{k0(o['straddle'])} pts) to expiry"
                       + (f" · IV {o['atm_iv']:.1f}%" if o.get("atm_iv") else ""))
        det.append(f"Put wall (biggest put open interest below spot) {k0(o['put_wall'])} · call wall (biggest call open interest above) {k0(o['call_wall'])}")
        if o.get("top_call_oi"):
            det.append("Heaviest call strikes " + ", ".join(k0(x["strike"]) for x in o["top_call_oi"]) + " · heaviest put strikes " + ", ".join(k0(x["strike"]) for x in o.get("top_put_oi", [])))
        oc = o.get("oi_change") or {}
        if oc and (oc.get("calls") or oc.get("puts")):
            det.append(f"Open interest added today: calls {oc['calls']:+,} · puts {oc['puts']:+,}")
        bo = opt_all.get("banknifty")
        if bo and bo.get("pcr_oi"):
            det.append(f"Bank Nifty ({bo['expiry']}): PCR {bo['pcr_oi']:.2f} · max pain {k0(bo['max_pain'])} · walls {k0(bo['put_wall'])} / {k0(bo['call_wall'])}"
                       + (f" · straddle ₹{bo['straddle']:,.0f} (±{bo['implied_move_pct']:.2f}%)" if bo.get("straddle") else ""))
        add("Options positioning - Nifty", "flat", value, det, quality=chain_quality(o), src="NSE option chain", as_of=o.get("as_of"), count=False)

    br, ni = live.get("breadth") or {}, ins.get("nifty") or {}
    if br.get("advances") is not None and br.get("declines") is not None:
        a, d = br["advances"], br["declines"]
        ratio = a / d if d else None
        det = [f"Whole market: {k0(a)} advancing · {k0(d)} declining" + (f" · {k0(br['unchanged'])} unchanged" if br.get("unchanged") is not None else "")]
        if ni.get("advances") is not None:
            det.append(f"Nifty 50: {k0(ni['advances'])} up · {k0(ni['declines'])} down")
        secs = live.get("sectors") or []
        if len(secs) >= 4:
            det.append("Leading sectors " + ", ".join(f"{x['name']} {x['chg_pct']:+.2f}%" for x in secs[:3]))
            det.append("Lagging sectors " + ", ".join(f"{x['name']} {x['chg_pct']:+.2f}%" for x in secs[-3:][::-1]))
        for k, nm in (("midcap100", "Midcap 100"), ("smallcap100", "Smallcap 100")):
            if ins.get(k, {}).get("chg_pct") is not None:
                det.append(f"{nm} {ins[k]['chg_pct']:+.2f}%")
        flows = {}
        try:
            with open(os.path.join(DATA, "flows.json"), encoding="utf-8") as fh:
                flows = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
        cash = flows.get("cash") or {}
        if cash.get("fii"):
            money = lambda v: f"{'+' if v >= 0 else '−'}₹{abs(v):,.0f} cr"  # noqa: E731
            fl = f"FII net {money(cash['fii']['net'])}" + (f" · DII net {money(cash['dii']['net'])}" if cash.get("dii") else "")
            det.append(f"Last session ({cash.get('date')}): {fl}")
        fn = flows.get("fno") or {}
        if fn.get("fii_long_pct") is not None:
            det.append(f"FII index futures: {fn['fii_long_pct']:.1f}% long (was {fn['prev_long_pct']:.1f}% on {fn.get('prev_date')})" if fn.get("prev_long_pct") is not None
                       else f"FII index futures: {fn['fii_long_pct']:.1f}% long")
        add("Market breadth and flows", "up" if ratio and ratio >= 1.5 else "down" if ratio is not None and ratio <= 0.67 else "flat",
            f"{k0(a)} up · {k0(d)} down" + (f" · A/D {ratio:.2f}" if ratio else ""), det,
            quality=ni.get("quality") or "final", src="NSE (breadth, sectors); NSE/NSDL end-of-day flows", as_of=live.get("as_of"), count=False)

    cal = []
    try:
        with open(os.path.join(DATA, "events.json"), encoding="utf-8") as fh:
            cal = [x for x in json.load(fh).get("events", []) if x.get("d") == today]
    except (OSError, json.JSONDecodeError):
        pass
    big = [x for x in cal if x.get("k") in ("rbi", "fed", "budget", "expiry", "india", "world")]
    big.sort(key=lambda x: (x.get("tm") or "99:99"))
    comp = collections.Counter(x["k"] for x in cal if x.get("k") in ("results", "board", "ex"))
    exp_today = [f"Nifty weekly expiry today ({(o or {}).get('expiry')})"] if o and o.get("expiry") == today else []
    def names(kind, n=6):
        got = list(dict.fromkeys(x["s"] for x in cal if x.get("k") == kind and x.get("s")))
        return ", ".join(got[:n]) + (f" and {len(got) - n} more" if len(got) > n else "")
    if big or comp or exp_today:
        det = exp_today + [(f"{x['tm']} IST  " if x.get("tm") else "") + x["t"] for x in big]
        if comp.get("results"):
            det.append(f"{comp['results']} result announcement(s): {names('results')}")
        if comp.get("board"):
            det.append(f"{comp['board']} board meeting(s): {names('board')}")
        if comp.get("ex"):
            det.append(f"{comp['ex']} stock(s) go ex-date: {names('ex')}")
        head = [x["t"] for x in big][:2] + exp_today[:1]
        add("Today's calendar", "flat", " · ".join(head) if head else f"{sum(comp.values())} company event(s)", det,
            quality="scheduled", src="PulsEdge calendar (NSE announcements and official dates)", as_of=today, count=False)

    score = up - down
    sentiment = ("Bullish" if score >= 3 else "Mildly bullish" if score >= 1 else
                 "Bearish" if score <= -3 else "Mildly bearish" if score <= -1 else "Neutral")

    cues = []
    if opening:
        g = q["gift"]["price"] - q["niftyfut"]["price"]
        cues.append(f"GIFT Nifty: {opening} ({g:+,.0f} pts)")
    if "brent" in q and abs(q["brent"]["chg"]) >= 1:
        cues.append(f"Brent {'up' if q['brent']['chg'] > 0 else 'down'} {abs(q['brent']['chg']):.2f}%"
                    + (" — pressure on OMCs, paints and aviation" if q["brent"]["chg"] > 0 else " — relief for OMCs and paints"))
    if "nasdaq" in q:
        c = q["nasdaq"]["chg"]
        cues.append(("NASDAQ closed flat" if abs(c) < 0.01 else f"NASDAQ closed {abs(c):.2f}% {'higher' if c > 0 else 'lower'}") + ("; IT may open soft" if c < -0.3 else "; supportive for IT" if c > 0.3 else ""))
    if asia:
        cues.append(", ".join(f"{ {'nikkei': 'Nikkei', 'hangseng': 'Hang Seng'}[k]} {'up' if q[k]['chg'] > 0 else 'down'}" for k in asia))

    feed = {}
    try:
        with open(os.path.join(DATA, "feed.json"), encoding="utf-8") as fh:
            feed = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    today = NOW.strftime("%Y-%m-%d")
    picks = sorted((x for x in feed.get("items", []) if x.get("time", "")[:10] == today and x.get("tickers") and x.get("call") != "ignore"),
                   key=lambda x: -(x.get("impact") or 0))[:3]
    focus = [{"symbol": x["tickers"][0]["symbol"], "note": x["headline"][:70]} for x in picks]
    triggers = [f"{len([x for x in feed.get('items', []) if x.get('time', '')[:10] == today and x.get('call') != 'ignore'])} filings and headlines worth a look so far today"] if feed else []
    if "vix" in q and q["vix"]["chg"] >= 3:
        triggers.append(f"India VIX up {q['vix']['chg']:.1f}% — expect wider ranges")

    risks = []
    if "brent" in q and q["brent"]["chg"] > 1:
        risks.append("A further crude spike would hit OMCs and widen the INR move")
    if "nasdaq" in q and q["nasdaq"]["chg"] < -1:
        risks.append("Weak US tech could weigh on Indian IT at the open")
    if "vix" in q and q["vix"]["price"] >= 18:
        risks.append("Elevated VIX — gaps and reversals are more likely")

    also_keys = [("BANK NIFTY", "banknifty", 1), ("S&P FUT", "esf", 0), ("NASDAQ FUT", "nqf", 0), ("KOSPI", "kospi", 0),
                 ("WTI", "wti", 2), ("GOLD", "gold", 0), ("US 10Y", "us10y", 2)]
    out = {
        "date": today,
        "updated": NOW.isoformat(timespec="seconds"),
        "writer": args.writer,
        "data_as_of": live.get("as_of"),
        "market": live.get("market") or {},
        "sentiment": sentiment,
        "breadth": {"up": up, "down": down},
        "checklist": checklist,
        "summary": f"{sentiment} setup. " + ("; ".join(cues[:2]) if cues else "No strong moves overnight") + ".",
        "global_cues": cues,
        "india_triggers": triggers,
        "focus": focus,
        "sector_tags": ([{"label": "Upstream oil", "tone": "positive"}, {"label": "OMCs", "tone": "negative"}] if "brent" in q and q["brent"]["chg"] > 1 else [])
                       + ([{"label": "IT", "tone": "watch"}] if "nasdaq" in q and abs(q["nasdaq"]["chg"]) > 0.3 else []),
        "key_risk": risks[0] if risks else "",
        "also": [{"name": n, "value": fmt(q[k]["price"], d), "change": round(q[k]["chg"], 2)} for n, k, d in also_keys if k in q],
        "source": "NSE live indices, VIX, breadth and option chain; TradingView (GIFT Nifty, Asia, FX and gold in real time; US futures and crude 10 min delayed); CNBC / Yahoo as backups. Each checklist item says which, and whether it is live",
        "data": {"instruments": {k: {f: i.get(f) for f in ("v", "chg_pct", "prev", "open", "high", "low", "quality", "src", "as_of")}
                                 for k, i in ins.items() if k in ("nifty", "banknifty", "vix", "gift", "niftyfut", "usdinr", "dxy", "brent", "es", "nq", "us30cfd", "nikkei", "hangseng")},
                 "levels": lv_all, "options": opt_all, "live_file": "data/live.json"},
    }
    if dry:
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return
    if live.get("instruments"):
        try:
            lm.write(live)
        except OSError as e:
            log(f"  live.json not written: {e}")
    with open(os.path.join(DATA, "premarket.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    log(f"wrote premarket.json: {sentiment}, {len(checklist)} checklist items")


if __name__ == "__main__":
    main()
