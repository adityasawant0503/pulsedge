#!/usr/bin/env python3
"""Upcoming events for the news calendar (pulsedge/calendar.html): results dates, board meetings and ex-dates for the
Nifty 500, plus the dates that move the whole market (RBI policy, the US Fed, the Union Budget, F&O expiry).

  python pulsedge-bot/events.py update [--dry-run] [--force]     # from the news run; asks NSE at most every 3 hours

Writes pulsedge/data/events.json. Sources:
- NSE's board-meeting calendar and corporate actions (www.nseindia.com/api/event-calendar, corporate-board-meetings,
  corporates-corporateActions). They answer GitHub's runners (NSE's home page doesn't).
- NSE's RSS feeds for board meetings and corporate actions (nsearchives), matched to the Nifty 500 by company name,
  for anything the API calls missed.
- FIXED below: RBI and Fed dates from their published schedules, checked by hand. Update them when the schedules
  change (the Fed's dates are tentative until the meeting before), and add each new year's in December.
Events already found are kept until the month before last, so a failed call never empties the calendar.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "pulsedge", "data"))
OUT = os.path.join(DATA, "events.json")
IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
EVERY_HOURS = 3
AHEAD_DAYS = 120

# Checked against the sources on 25 Nov 2026.
# RBI: MPC meetings for 2026-27 (RBI press release, "Monetary Policy Committee meetings: schedule"); the decision is
#      announced on the last day, usually at 10:00 IST.
# Fed: FOMC calendar as revised on 12 Nov 2026 (federalreserve.gov/monetarypolicy/fomccalendars.htm). The decision is
#      at 2:00 pm in Washington: 23:30 IST while the US is on summer time (14 Mar - 7 Nov 2027), 00:30 IST the next day
#      otherwise. The 26-27 Oct 2027 meeting is strategy only, with no decision.
FIXED = [
    ("2026-12-04", "rbi", "RBI policy decision", "The Monetary Policy Committee meets 2-4 Dec; the decision is usually announced at 10:00 IST."),
    ("2027-02-05", "rbi", "RBI policy decision", "The Monetary Policy Committee meets 3-5 Feb; the decision is usually announced at 10:00 IST."),
    ("2026-12-10", "fed", "US Fed rate decision", "Announced at 00:30 IST (2:00 pm on 9 Dec in Washington). Indian markets react in the session that day."),
    ("2027-01-28", "fed", "US Fed rate decision", "Announced at 00:30 IST (2:00 pm on 27 Jan in Washington). Indian markets react in the session that day."),
    ("2027-03-17", "fed", "US Fed rate decision", "Announced at 23:30 IST, after Indian markets close. They react the next session."),
    ("2027-04-28", "fed", "US Fed rate decision", "Announced at 23:30 IST, after Indian markets close. They react the next session."),
    ("2027-06-09", "fed", "US Fed rate decision", "Announced at 23:30 IST, after Indian markets close. They react the next session."),
    ("2027-07-28", "fed", "US Fed rate decision", "Announced at 23:30 IST, after Indian markets close. They react the next session."),
    ("2027-09-15", "fed", "US Fed rate decision", "Announced at 23:30 IST, after Indian markets close. They react the next session."),
    ("2027-11-18", "fed", "US Fed rate decision", "Announced at 00:30 IST (2:00 pm on 17 Nov in Washington). Indian markets react in the session that day."),
    ("2027-02-01", "budget", "Union Budget 2027-28 (expected)", "Usually presented on 1 February; the government confirms the date in January."),
]

# NSE is closed on these every year (Republic Day, Independence Day, Gandhi Jayanti, Christmas), so expiry dates for
# a year whose holiday list isn't in calendar.json yet still avoid them
ALWAYS_CLOSED = {"01-26", "08-15", "10-02", "12-25"}
# The world's dates that move Indian markets, from TradingView's public economic calendar (it answers GitHub's
# runners; unofficial, like the prices we take from TradingView). Each entry: country, title as TradingView writes it,
# our key, the tag on the calendar, the name, priority (1 shows everywhere, 2 only in the World view), the unit of its
# numbers, and why it matters for India, in our own words. The Fed and the RBI come from FIXED above.
TV_ECON = "https://economic-calendar.tradingview.com/events"
ECON = [
    ("US", r"^Inflation Rate YoY$", "us-cpi", "US CPI", "US inflation (CPI)", 1, "%",
     "Hotter US inflation can keep US rates high for longer, which tends to pull foreign money out of Indian stocks and weaken the rupee."),
    ("US", r"^Non Farm Payrolls$", "us-jobs", "US JOBS", "US jobs report", 1, "k",
     "Strong US hiring can mean higher US rates for longer; weak hiring the opposite. It moves the dollar, US bond yields and foreign flows into India."),
    ("US", r"^Core PCE Price Index YoY$", "us-pce", "US PCE", "US core PCE inflation (the Fed's preferred measure)", 2, "%",
     "The inflation measure the Fed watches most closely; a surprise changes expectations for US rates."),
    ("US", r"^GDP Growth Rate QoQ", "us-gdp", "US GDP", "US GDP growth", 2, "%",
     "How fast the US economy is growing; it matters for Indian IT, which earns much of its revenue there."),
    ("US", r"^Retail Sales MoM$", "us-retail", "US RETAIL", "US retail sales", 2, "%",
     "US consumer spending; a guide to the US economy and to demand for Indian exports and IT services."),
    ("US", r"^ISM Manufacturing PMI$", "us-ism", "US ISM", "US factory activity (ISM)", 2, "",
     "Above 50 means US factories are growing. It moves US yields and global risk appetite."),
    ("US", r"^FOMC Minutes$", "fomc-min", "FOMC", "Minutes of the last Fed meeting (FOMC)", 2, None,
     "The detail behind the Fed's last decision; markets read it for hints on the next rate move."),
    ("US", r"Fed Chair .*Speech|Powell Speech|Fed Chair .*Testimony", "fed-chair", "FED CHAIR", "The US Fed chair speaks", 2, None,
     "Markets listen for hints on US rates, which drive the dollar and foreign flows into India."),
    ("EU", r"^ECB Interest Rate Decision$", "ecb", "ECB", "European Central Bank rate decision", 1, "%",
     "Europe's rate decision moves global bond yields and currencies, and with them foreign money flows."),
    ("GB", r"^(BoE )?Interest Rate( Decision)?$", "boe", "BOE", "Bank of England rate decision", 2, "%",
     "The UK's rate decision; it moves the pound and global bond yields."),
    ("JP", r"^(BoJ )?Interest Rate( Decision)?$", "boj", "BOJ", "Bank of Japan rate decision", 1, "%",
     "Japanese rates drive the yen \"carry trade\"; a surprise can pull money out of emerging markets including India."),
    ("CN", r"^NBS Manufacturing PMI$", "cn-pmi", "CHINA PMI", "China factory activity (PMI)", 2, "",
     "China's demand drives metal and commodity prices, which move Indian metal stocks."),
    ("CN", r"^GDP Growth Rate YoY$", "cn-gdp", "CHINA GDP", "China GDP growth", 1, "%",
     "China's growth drives global demand for metals and commodities, which moves Indian metal and energy stocks."),
    ("CN", r"^Loan Prime Rate 1Y$", "cn-lpr", "CHINA RATE", "China lending rate (PBoC)", 2, "%",
     "China's benchmark lending rate; a cut signals support for its economy and metal demand."),
    ("IN", r"^Inflation Rate YoY$", "in-cpi", "INDIA CPI", "India inflation (CPI)", 1, "%",
     "India's inflation shapes the RBI's next rate decision, which moves banks, NBFCs and rate-sensitive stocks."),
    ("IN", r"^GDP Growth Rate YoY$", "in-gdp", "INDIA GDP", "India GDP growth", 1, "%",
     "How fast India's economy grew last quarter; it sets the tone for the whole market."),
    ("IN", r"^WPI Inflation YoY$", "in-wpi", "INDIA WPI", "India wholesale inflation (WPI)", 2, "%",
     "Price pressure at the factory gate; it feeds into companies' costs and margins."),
    ("IN", r"^Industrial Production YoY$", "in-iip", "INDIA IIP", "India industrial output (IIP)", 2, "%",
     "How fast India's factories, mines and power plants are growing."),
    ("IN", r"^Balance of Trade$", "in-trade", "INDIA TRADE", "India trade balance", 2, None,
     "The gap between imports and exports; a wider deficit can weigh on the rupee."),
    ("IN", r"^HSBC Manufacturing PMI Final$", "in-pmi", "INDIA PMI", "India factory activity (PMI)", 2, "",
     "Above 50 means India's factories are growing."),
]
NSE_API = "https://www.nseindia.com/api/"
RSS_BOARD = "https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml"
RSS_ACTIONS = "https://nsearchives.nseindia.com/content/RSS/Corporate_action.xml"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def get(url, referer="https://www.nseindia.com/"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/xml, */*",
                                               "Referer": referer, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def day(s):
    """'05-Dec-2026' (or '05-Dec-2026 14:03:38') -> '2026-12-05'."""
    try:
        return datetime.strptime(str(s).strip()[:11], "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def nice(d):
    x = date.fromisoformat(d)
    return f"{x.day} {x:%b}"


def rupees(s):
    s = re.sub(r"\b(?:Rs|Re)\.?\s*(?=\d)", "₹", s, flags=re.I)
    s = re.sub(r"\s*/-", "", s)
    s = re.sub(r"\s*per\s+share", " a share", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" -|")


def sentence(s):
    s = s.strip()
    return s[:1].upper() + s[1:].lower() if s else s


# ---------- stocks ----------

def board_event(sym, d, purpose, desc):
    purpose, desc = str(purpose or "").strip(), re.sub(r"\s+", " ", str(desc or "")).strip()
    if re.search(r"financial\s+results?", purpose + " " + desc, re.I):
        k, t = "results", "Results (board meeting)"
        if re.search(r"dividend", purpose, re.I):
            t = "Results and dividend (board meeting)"
    else:
        p = re.sub(r"\bboard\s+meeting(\s+intimation)?\b", "", purpose, flags=re.I).strip(" ,/-|")
        k, t = "board", ("Board meeting: " + sentence(p.replace("/", ", "))) if p else "Board meeting"
    return {"d": d, "k": k, "s": sym, "t": t, "x": desc[:200]}


def action_event(sym, ex, subject, rec=None):
    subject = rupees(str(subject or ""))
    t = "Ex-date: " + sentence(subject)
    x = f"Shares bought on or after this date don't qualify; record date {nice(rec)}." if rec and re.search(r"dividend|bonus|rights|split", subject, re.I) else (
        f"Record date {nice(rec)}." if rec else "")
    return {"d": ex, "k": "ex", "s": sym, "t": t[:120], "x": x}


def from_api(universe):
    """NSE's calendar: (events, how each call went)."""
    today = datetime.now(IST).date()
    rng = f"index=equities&from_date={today - timedelta(days=7):%d-%m-%Y}&to_date={today + timedelta(days=AHEAD_DAYS):%d-%m-%Y}"
    out, status = [], {}
    calls = [
        ("event-calendar", "event-calendar?" + rng, "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"),
        ("board-meetings", "corporate-board-meetings?" + rng, "https://www.nseindia.com/companies-listing/corporate-filings-board-meetings"),
        ("actions", "corporates-corporateActions?" + rng, "https://www.nseindia.com/companies-listing/corporate-filings-actions"),
    ]
    for name, path, ref in calls:
        try:
            j = json.loads(get(NSE_API + path, ref))
            rows = j if isinstance(j, list) else (j.get("data") or [])
        except Exception as e:  # noqa: BLE001 - the RSS feeds and the kept events cover a failed call
            status[name] = f"failed: {type(e).__name__} {str(e)[:80]}"
            continue
        n = 0
        for r in rows:
            if name == "actions":
                sym, d = r.get("symbol"), day(r.get("exDate"))
                if sym in universe and d and r.get("series") in ("EQ", "BE", None):
                    out.append(action_event(sym, d, r.get("subject"), day(r.get("recDate"))))
                    n += 1
            else:
                sym = r.get("symbol") or r.get("bm_symbol")
                d = day(r.get("date") or r.get("bm_date"))
                if sym in universe and d:
                    out.append(board_event(sym, d, r.get("purpose") or r.get("bm_purpose"), r.get("bm_desc")))
                    n += 1
        status[name] = f"{len(rows)} rows, {n} for the Nifty 500"
    return out, status


def norm(name):
    s = html.unescape(str(name or "")).lower().replace("&", " and ")
    s = re.sub(r"\b(limited|ltd)\b\.?", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def rss_items(xml):
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        it = m.group(1)
        f = {k: html.unescape(re.sub(r"\s+", " ", (re.search(rf"<{k}>(.*?)</{k}>", it, re.S) or [None, ""])[1]).strip())
             for k in ("title", "description")}
        yield f["title"], f["description"]


def from_rss(names):
    """The RSS feeds name companies, not symbols: matched to the Nifty 500 by name."""
    out, status = [], {}
    for name, url in (("rss-board", RSS_BOARD), ("rss-actions", RSS_ACTIONS)):
        try:
            xml = get(url).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            status[name] = f"failed: {type(e).__name__} {str(e)[:80]}"
            continue
        n = rows = 0
        for title, desc in rss_items(xml):
            rows += 1
            if name == "rss-board":
                sym, m = names.get(norm(title)), re.search(r"Meeting Date:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", desc)
                if sym and m and day(m.group(1)):
                    text = desc.split("|")[0].strip()
                    out.append(board_event(sym, day(m.group(1)), text if len(text) < 60 else "", text))
                    n += 1
            else:
                m = re.match(r"(.*?)\s*-\s*Ex-Date:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", title)
                p = re.search(r"PURPOSE:\s*([^|]+)", desc)
                s = re.search(r"SERIES:\s*([A-Z]+)", desc)
                rec = re.search(r"RECORD DATE:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", desc)
                sym = names.get(norm(m.group(1))) if m else None
                if sym and p and day(m.group(2)) and (not s or s.group(1) in ("EQ", "BE")):
                    out.append(action_event(sym, day(m.group(2)), p.group(1), day(rec.group(1)) if rec else None))
                    n += 1
        status[name] = f"{rows} items, {n} for the Nifty 500"
    return out, status


# ---------- the whole market ----------

def expiries(today, holidays):
    """NSE's monthly F&O contracts expire on the month's last Tuesday, or the trading day before if that's a holiday."""
    out = []
    y, m = today.year, today.month
    for _ in range(5):
        last = date(y, m, monthrange(y, m)[1])
        d = last - timedelta(days=(last.weekday() - 1) % 7)
        while d.weekday() > 4 or d.isoformat() in holidays or d.strftime("%m-%d") in ALWAYS_CLOSED:
            d -= timedelta(days=1)
        known = str(y) in {h[:4] for h in holidays}
        out.append((d.isoformat(), "expiry", "Monthly F&O expiry",
                    "NSE's monthly Nifty and stock futures and options expire (the last Tuesday, or the trading day before "
                    "when it's a holiday)." + ("" if known else " Check NSE's holiday list for this year.")))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def num(v, unit):
    if not isinstance(v, (int, float)):
        return None
    t = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    return t + ("%" if unit == "%" else "K" if unit == "k" else "")


def from_econ(today):
    """Curated world and India economic dates (ECON) from TradingView's calendar: (events, status)."""
    a = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    b = today + timedelta(days=75)
    url = (f"{TV_ECON}?from={a.isoformat()}T00:00:00.000Z&to={b.isoformat()}T00:00:00.000Z&countries=" +
           ",".join(sorted({c for c, *_ in ECON})))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                   "Origin": "https://in.tradingview.com", "Referer": "https://in.tradingview.com/"})
        with urllib.request.urlopen(req, timeout=25) as r:
            rows = (json.loads(r.read()) or {}).get("result") or []
    except Exception as e:  # noqa: BLE001 - the dates found earlier are kept
        return None, f"failed: {type(e).__name__} {str(e)[:80]}"
    out = {}
    for r in rows:
        cc, title = r.get("country"), str(r.get("title") or "").strip()
        rule = next((x for x in ECON if x[0] == cc and re.search(x[1], title)), None)
        if not rule or not r.get("date"):
            continue
        _, _, key, tag, name, prio, unit, why = rule
        try:
            at = datetime.fromisoformat(str(r["date"]).replace("Z", "+00:00")).astimezone(IST)
        except ValueError:
            continue
        d = at.date().isoformat()
        if (d, key) in out:
            continue
        period = str(r.get("period") or "").strip()
        # "Nov. 2026" -> "Nov 2026", "Q3 2026" stays; a plain date (rate decisions) adds nothing
        per = period.replace(".", "") if re.match(r"^([A-Z][a-z]{2}\.? \d{4}|Q\d \d{4})$", period) else ""
        bits = []
        act, fc, prev = (num(r.get(k), unit) if unit is not None else None for k in ("actual", "forecast", "previous"))
        if act:
            bits.append(f"Came in at {act}" + (f" (forecast {fc})" if fc else "") + (f", previous {prev}" if prev else "") + ".")
        elif fc:
            bits.append(f"Forecast {fc}" + (f", previous {prev}" if prev else "") + ".")
        elif prev:
            bits.append(f"Previous {prev}.")
        out[(d, key)] = {"d": d, "k": "india" if cc == "IN" else "world", "g": key, "tg": tag, "cc": cc, "p": prio,
                         "t": name + (f" ({per})" if per else ""), "tm": at.strftime("%H:%M"), "x": (" ".join(bits) + " " + why).strip()}
    return list(out.values()), f"{len(rows)} rows, {len(out)} kept"


def market(today, holidays):
    return [{"d": d, "k": k, "t": t, "x": x} for d, k, t, x in FIXED + expiries(today, holidays)]


# ---------- the file ----------

def update(dry=False, force=False):
    now = datetime.now(IST)
    old = load(OUT, {})
    try:
        last = datetime.fromisoformat(old.get("fetched") or "")
    except (TypeError, ValueError):
        last = None
    due = force or not last or now - last >= timedelta(hours=EVERY_HOURS)
    uni = load(os.path.join(DATA, "universe.json"), {}).get("stocks", [])
    universe = {s["symbol"]: s.get("name", s["symbol"]) for s in uni}
    by_name = {norm(n): s for s, n in universe.items()}
    holidays = set(load(os.path.join(DATA, "calendar.json"), {}).get("holidays", []))
    today = now.date()
    keep_from = (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()   # the start of last month

    stocks, status, econ = [], dict(old.get("sources") or {}), None
    if due:
        a, s1 = from_api(universe)
        r, s2 = from_rss(by_name)
        econ, s3 = from_econ(today)
        stocks, status = a + r, {**s1, **s2, "economic-calendar": s3}
        for k, v in status.items():
            log(f"  {k}: {v}")
    # one event per stock, day and family (a board meeting, an ex-date); the API's wording wins over the RSS feed's,
    # and anything found earlier stays unless NSE now has it under another wording
    fam = lambda e: "ex" if e["k"] == "ex" else "bm"  # noqa: E731
    merged = {}
    for e in stocks + [e for e in old.get("events", []) if e.get("s")]:
        key = (e["d"], e["s"], fam(e))
        if key not in merged and keep_from <= e["d"] <= (today + timedelta(days=AHEAD_DAYS)).isoformat():
            merged[key] = e
    # economic dates: this run's, or the ones found earlier when the calendar couldn't be read (or wasn't asked)
    if econ is None:
        econ = [e for e in old.get("events", []) if e.get("k") in ("world", "india")]
    fixed = market(today, holidays)
    # the Fed and the RBI come from FIXED; their dates in the feed would repeat them
    econ = [e for e in econ if keep_from <= e["d"] <= (today + timedelta(days=AHEAD_DAYS)).isoformat()]
    evs = sorted(list(merged.values()) + econ + [e for e in fixed if e["d"] >= keep_from],
                 key=lambda e: (e["d"], e.get("s") or "", e["k"]))
    out = {"events": evs, "names": {s: universe[s] for s in sorted({e["s"] for e in evs if e.get("s")}) if s in universe},
           "sources": status,
           "note": ("Upcoming events for calendar.html (pulsedge-bot/events.py). d date (IST), k results|board|ex|rbi|fed|"
                    "budget|expiry|world|india, s NSE symbol, t title, x detail; world and India economic dates also have "
                    "g key, tg tag, cc country, p priority (1 everywhere, 2 World view only), tm time IST.")}
    # a run where every source failed asks again next time
    ok = due and any(not str(v).startswith("failed") for v in status.values())
    out["fetched"] = now.isoformat(timespec="minutes") if ok else old.get("fetched")
    same = {k: v for k, v in old.items() if k not in ("updated", "fetched")} == {k: v for k, v in out.items() if k != "fetched"}
    stock_n = sum(1 for e in evs if e.get("s"))
    log(f"  events: {stock_n} for stocks, {len(evs) - stock_n} market-wide{'' if due else ' (NSE asked less than 3 hours ago)'}"
        f"{' (no change)' if same else ''}{' [dry run]' if dry else ''}")
    if same and not due:
        return out
    out["updated"] = now.isoformat(timespec="minutes") if not same else old.get("updated")
    if not dry:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["update"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ask NSE now, however recently it was asked")
    a = ap.parse_args()
    update(a.dry_run, a.force)


if __name__ == "__main__":
    main()
