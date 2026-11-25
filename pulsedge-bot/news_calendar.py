#!/usr/bin/env python3
"""The PulsEdge news calendar (pulsedge/calendar.html): each day's news worth a look, with the NSE closes the page needs
to show how every stock moved on the day of its news and since.

  python pulsedge-bot/news_calendar.py update [--dry-run]                      # every news run: adds feed.json's new items
  python pulsedge-bot/news_calendar.py backfill --month 2026-11 [--ref origin/master] [--dry-run]   # a month from git history

Writes pulsedge/data/newscal/<YYYY-MM>.json and index.json:
- items: Act and Watch news (tips pieces, brokers' views, round-ups and live blogs left out, as in the monthly report),
  one copy of each story a day, trimmed to what the page shows.
- sessions, px, nifty: closes from the last session before the month to its last session, for the stocks in the month's
  news. closes.json keeps about 30 sessions, so the month file keeps its own copy and a finished month stays complete.
- index.json: the months there are, and every stock's latest close for "since the news".
Holdings never reach us: the page matches them against these files in the visitor's browser.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import monthly_report as mr  # noqa: E402  (news filters, history reader, headline clean-up)

OUT = os.path.join(mr.DATA, "newscal")
CLOSES = os.path.join(HERE, "state", "closes.json")
MAX_TICKERS = 6
# stand-in summaries the pipeline writes when the AI is off: they say nothing about the story, so the page shows none
FILLER = re.compile(r"^(?:Keyword rules\b|It names a listed company or a kind of event)", re.I)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def ist_time(t):
    """'YYYY-MM-DDTHH:MM' in IST, or None."""
    try:
        d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=mr.IST)
    return d.astimezone(mr.IST).strftime("%Y-%m-%dT%H:%M")


def row(x):
    """The fields the page shows, from a feed item (or a track.json call)."""
    t = ist_time(x.get("time"))
    if not t or not x.get("id") or not x.get("headline"):
        return None
    syms = []
    for tk in x.get("tickers") or []:
        s = tk.get("symbol") if isinstance(tk, dict) else None
        if s and s not in syms:
            syms.append(s)
    why = x.get("why") or x.get("plain") or ((x.get("reason") or [""])[0] if isinstance(x.get("reason"), list) else "")
    d = str(x.get("direction") or (x.get("tickers") or [{}])[0].get("direction") or "").lower()
    why = str(why or "").strip()
    r = {"i": str(x["id"]), "t": t, "h": mr.clean_head(x["headline"])[:200], "w": "" if FILLER.search(why) else why[:240],
         "v": "a" if x.get("call") in ("buy", "sell") else "w", "s": syms[:MAX_TICKERS],
         "c": str(x.get("section") or "news"), "src": str(x.get("source") or "")[:48], "u": str(x.get("url") or "")[:300]}
    if d in ("up", "down", "mixed"):
        r["d"] = d
    if isinstance(x.get("impact"), (int, float)):
        r["m"] = int(x["impact"])
    return r


def same(a, b):
    """The same story twice on one day: about the same stocks, with a headline that says the same thing."""
    return a["t"][:10] == b["t"][:10] and set(a["s"]) == set(b["s"]) and mr.same_story(a["h"], b["h"])


def wanted(x):
    return x.get("call") != "ignore" and not mr.noise(x)


# ---------- the month file ----------

def path(month):
    return os.path.join(OUT, f"{month}.json")


def load_month(month):
    m = mr.load(path(month), None)
    return m if isinstance(m, dict) and m.get("month") == month else {"month": month, "items": [], "sessions": [], "nifty": [], "px": {}}


def add_items(m, xs):
    """Adds new stories; returns how many. A story already there (by id, or the same story that day) keeps the first copy:
    the time it first came out is the one "since the news" counts from."""
    # the filters apply to stories already kept too, so a rule added later tidies past months on their next run
    m["items"] = [r for r in m["items"] if not mr.noise({"headline": r["h"]})]
    for r in m["items"]:
        if FILLER.search(r.get("w", "")):
            r["w"] = ""
    have = {r["i"] for r in m["items"]}
    by_day = {}
    for r in m["items"]:
        by_day.setdefault(r["t"][:10], []).append(r)
    n = 0
    for x in sorted(xs, key=lambda x: str(x.get("time", ""))):
        if not wanted(x):
            continue
        r = row(x)
        if not r or r["t"][:7] != m["month"] or r["i"] in have:
            continue
        day = by_day.setdefault(r["t"][:10], [])
        if any(same(r, y) for y in day):
            continue
        m["items"].append(r)
        day.append(r)
        have.add(r["i"])
        n += 1
    m["items"].sort(key=lambda r: (r["t"], r["i"]))
    return n


def add_prices(m, closes, flows):
    """sessions: the last NSE session before the month, then the month's sessions; px[sym] and nifty line up with them.
    Closes already in the file are kept when closes.json no longer has them."""
    start, end = mr.month_bounds(m["month"])
    s0, s1 = start.isoformat(), end.isoformat()
    old = {d: {} for d in m.get("sessions") or []}
    for sym, xs in (m.get("px") or {}).items():
        for d, p in zip(m.get("sessions") or [], xs):
            if p is not None:
                old[d][sym] = p
    old_n = dict(zip(m.get("sessions") or [], m.get("nifty") or []))
    days = sorted(set(old) | {d for d in closes if d <= s1})
    before = [d for d in days if d < s0]
    sessions = before[-1:] + [d for d in days if s0 <= d <= s1]
    syms = sorted({s for r in m["items"] for s in r["s"]})
    ih = flows.get("index_history") or {}
    m["sessions"] = sessions
    m["px"] = {}
    for s in syms:
        xs = []
        for d in sessions:
            p = (closes.get(d) or {}).get(s)
            xs.append(round(float(p), 2) if isinstance(p, (int, float)) and p > 0 else old.get(d, {}).get(s))
        if any(p is not None for p in xs):
            m["px"][s] = xs
    m["nifty"] = [((ih.get(d) or {}).get("Nifty 50") or [None])[0] or old_n.get(d) for d in sessions]


def finish(m, names):
    m["names"] = {s: names.get(s, s) for s in sorted({s for r in m["items"] for s in r["s"]})}
    m["note"] = ("PulsEdge news calendar (pulsedge-bot/news_calendar.py). items: i id, t IST time, h headline, w why it "
                 "matters, v a=Act w=Watch, d direction, m impact 0-100, s NSE symbols, c section, src, u link. px[sym] and "
                 "nifty are closes on the sessions listed.")
    return m


def body(m):
    return json.dumps({k: v for k, v in m.items() if k != "updated"}, ensure_ascii=False, sort_keys=True)


def save(m, before, dry):
    if body(m) == before:
        return False
    m["updated"] = datetime.now(mr.IST).isoformat(timespec="minutes")
    if dry:
        return True
    os.makedirs(OUT, exist_ok=True)
    with open(path(m["month"]), "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, separators=(",", ":"))
    return True


def save_index(closes, dry):
    months = sorted(f[:7] for f in os.listdir(OUT) if len(f) == 12 and f.endswith(".json")) if os.path.isdir(OUT) else []
    last = max(closes) if closes else None
    idx = {"months": months, "last": {"date": last, "px": {s: round(float(p), 2) for s, p in sorted((closes.get(last) or {}).items())
                                                           if isinstance(p, (int, float)) and p > 0}},
           "note": "Months in the news calendar, and each stock's latest NSE close (for \"since the news\")."}
    old = mr.load(os.path.join(OUT, "index.json"), {})
    if {k: v for k, v in old.items() if k != "updated"} == idx:
        return
    idx["updated"] = datetime.now(mr.IST).isoformat(timespec="minutes")
    if not dry:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(idx, fh, ensure_ascii=False, separators=(",", ":"))


def context():
    closes = mr.load(CLOSES, {}).get("sessions", {})
    flows = mr.load(os.path.join(mr.DATA, "flows.json"), {})
    names = {s["symbol"]: s.get("name", s["symbol"]) for s in mr.load(os.path.join(mr.DATA, "universe.json"), {}).get("stocks", [])}
    return closes, flows, names


def build(month, xs, dry):
    closes, flows, names = context()
    m = load_month(month)
    before = body(m) if os.path.exists(path(month)) else ""
    n = add_items(m, xs)
    add_prices(m, closes, flows)
    finish(m, names)
    changed = save(m, before, dry)
    log(f"  {month}: {n} new stories, {len(m['items'])} in all, {len(m['px'])} stocks with closes on {len(m['sessions'])} sessions"
        f"{'' if changed else ' (no change)'}{' [dry run]' if dry else ''}")
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["update", "backfill"])
    ap.add_argument("--month", help="YYYY-MM (backfill)")
    ap.add_argument("--ref", default="HEAD", help="branch whose feed.json history a backfill reads")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "backfill":
        if not a.month:
            ap.error("backfill needs --month")
        start, end = mr.month_bounds(a.month)
        build(a.month, mr.collect(start, end, a.ref), a.dry_run)
    else:
        feed = mr.load(os.path.join(mr.DATA, "feed.json"), {}).get("items", [])
        months = {str(ist_time(x.get("time")) or "")[:7] for x in feed} - {""}
        months.add(datetime.now(mr.IST).strftime("%Y-%m"))      # the month's closes, even on a day without news
        for month in sorted(months):
            if month >= "2026-11":                                # the news history starts in November 2026
                build(month, feed, a.dry_run)
    save_index(context()[0], a.dry_run)


if __name__ == "__main__":
    main()
