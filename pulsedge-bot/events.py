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
        k, t = "board", "Board meeting: " + (sentence(purpose.replace("/", ", ")) or "other matters")
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

    stocks, status = [], dict(old.get("sources") or {})
    if due:
        a, s1 = from_api(universe)
        r, s2 = from_rss(by_name)
        stocks, status = a + r, {**s1, **s2}
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
    evs = sorted(list(merged.values()) + [e for e in market(today, holidays) if e["d"] >= keep_from],
                 key=lambda e: (e["d"], e.get("s") or "", e["k"]))
    out = {"events": evs, "names": {s: universe[s] for s in sorted({e["s"] for e in evs if e.get("s")}) if s in universe},
           "sources": status,
           "note": ("Upcoming events for calendar.html (pulsedge-bot/events.py). d date (IST), k results|board|ex|rbi|fed|"
                    "budget|expiry, s NSE symbol, t title, x detail.")}
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
