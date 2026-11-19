#!/usr/bin/env python3
"""Track how PulsEdge calls did: pulsedge/data/track.json for the "How our calls did" page.

  python pulsedge-bot/track_record.py            # update track.json
  python pulsedge-bot/track_record.py --dry-run  # print the summary instead

Every Watch/Act/Buy/Sell call that names a stock is recorded the first time it is seen in
feed.json (the feed only keeps three days, so this runs on every pipeline run). Prices are
NSE's official end-of-day closes from the daily bhavcopy on nsearchives.nseindia.com.

  entry = the first NSE close after the news reached readers (its feed time + 15 minutes): the earliest
          price someone who read the alert could have traded at with end-of-day data
  1D / 5D = close of the 1st / 5th session after that
  news day = the move from the last close before the news to the entry close (already gone by the entry)
  alert price = the live price recorded when the alert went out (quotes.py), when NSE was open; "after alert"
          is the move from it to the entry close

Until 20 Nov 2026 the entry was the close before the news, which counted the news-day move as if it could be
traded and made the calls look far better than anyone could have done (61% vs about 40% on the same calls).

paper_book() keeps the paper-trading log (data/paper.json): rules fixed on 20 Nov 2026, trades from then on.

A call counts towards the hit rate only when the AI gave the stock a direction (up/down).
Keyword-rule calls have no real direction, so they show the price move but are never scored.
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "pulsedge", "data")
STATE = os.path.join(HERE, "state")
CLOSES = os.path.join(STATE, "closes.json")
TRACK = os.path.join(DATA, "track.json")
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

KEEP_SESSIONS = 30     # closes kept per symbol: enough for 5D on calls up to ~5 weeks old
KEEP_DAYS = 120        # calls kept on the page
LOOKBACK_DAYS = 14     # how far back to fill missing bhavcopies
TRACKED_CALLS = {"watch", "act", "buy", "sell"}
CLOSE_TIME = (15, 30)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":") if path == CLOSES else None,
                  indent=None if path == CLOSES else 1)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def bhavcopy(d):
    """{symbol: close} for EQ/BE/BZ series on date d, or None if NSE has no file (holiday / not out yet)."""
    rows = None
    try:
        raw = get(f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv")
        rows = [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(raw.decode("utf-8", "replace")))]
        sym_k, ser_k, cls_k = "SYMBOL", "SERIES", "CLOSE_PRICE"
    except urllib.error.HTTPError as e:
        if e.code not in (403, 404):
            raise
    if rows is None:  # newer UDiFF format
        try:
            raw = get(f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            raise
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            text = z.read(z.namelist()[0]).decode("utf-8", "replace")
        rows = [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
        sym_k, ser_k, cls_k = "TckrSymb", "SctySrs", "ClsPric"
    out = {}
    for r in rows:
        if r.get(ser_k) in ("EQ", "BE", "BZ"):
            try:
                out[r[sym_k]] = float(r[cls_k])
            except (KeyError, ValueError):
                pass
    return out or None


def same_as_previous(sessions, key, px):
    """True when px repeats the closes of the session before key for every stock: NSE serves a file on some holidays
    (Dussehra and 10 Nov 2026 were stored as sessions this way, which made every move across them read 0%)."""
    before = [k for k in sorted(sessions) if k < key]
    if not before:
        return False
    prev = sessions[before[-1]]
    common = [x for x in px if x in prev]
    return len(common) > 50 and all(px[x] == prev[x] for x in common)


def drop_holiday_sessions(closes):
    """Removes stored sessions that are calendar holidays or repeat the previous session; returns them."""
    sessions, holidays = closes.setdefault("sessions", {}), set(closes.setdefault("holidays", []))
    cal = set(load(os.path.join(DATA, "calendar.json"), {}).get("holidays", []))
    gone = [k for k in sorted(sessions) if k in cal or same_as_previous(sessions, k, sessions[k])]
    for k in gone:
        del sessions[k]
        holidays.add(k)
    closes["holidays"] = sorted(holidays)
    return gone


def refresh_closes(closes, wanted):
    """Fill in missing sessions from the last LOOKBACK_DAYS. closes = {"sessions": {date: {sym: px}}, "holidays": [...]}."""
    gone = drop_holiday_sessions(closes)
    if gone:
        log(f"  dropped holiday sessions stored as trading days: {', '.join(gone)}")
    sessions, holidays = closes.setdefault("sessions", {}), set(closes.setdefault("holidays", []))
    holidays |= set(load(os.path.join(DATA, "calendar.json"), {}).get("holidays", []))
    today = NOW.date()
    published = NOW.hour * 60 + NOW.minute >= 19 * 60  # bhavcopy is usually out by ~18:30 IST
    added = 0
    for back in range(LOOKBACK_DAYS, -1, -1):
        d = today - timedelta(days=back)
        key = d.isoformat()
        if d.weekday() >= 5 or key in sessions or key in holidays:
            continue
        if d == today and not published:
            continue
        try:
            px = bhavcopy(d)
        except Exception as e:
            log(f"  bhavcopy {key}: failed ({type(e).__name__}: {e})")
            continue
        if px is None:
            if d < today:
                holidays.add(key)  # no file for a past weekday: market holiday
            log(f"  bhavcopy {key}: none")
            continue
        kept = {s: p for s, p in px.items() if s in wanted}
        if same_as_previous(sessions, key, kept):
            holidays.add(key)
            log(f"  bhavcopy {key}: repeats the previous session; a holiday")
            continue
        sessions[key] = kept
        added += 1
        log(f"  bhavcopy {key}: {len(px)} stocks, kept {len(sessions[key])}")
    for k in sorted(sessions)[:-KEEP_SESSIONS]:
        del sessions[k]
    cutoff = (today - timedelta(days=LOOKBACK_DAYS + 7)).isoformat()
    closes["holidays"] = sorted(h for h in holidays if h >= cutoff)
    return added


def ai_classified(item):
    if item.get("kind") == "deal":                 # reported trades (flows.py), not predictions
        return False
    return not any("Keyword rules" in r for r in item.get("reason") or [])


def add_calls(track, feed):
    have = {(c["id"], c["symbol"]) for c in track["calls"]}
    new = 0
    for it in feed.get("items", []):
        if (it.get("call") or "").lower() not in TRACKED_CALLS or not it.get("tickers") or not it.get("time"):
            continue
        for t in it["tickers"][:2]:
            sym = t["symbol"] if isinstance(t, dict) else str(t)
            if (it["id"], sym) in have:
                continue
            d = (t.get("direction") if isinstance(t, dict) else None) or it.get("direction")
            scored = ai_classified(it) and d in ("up", "down")
            q = (it.get("quotes") or {}).get(sym) or {}
            track["calls"].append({
                "id": it["id"], "symbol": sym, "time": it["time"], "call": it["call"].lower(),
                "dir": d if scored else None, "scored": scored, "source": it.get("source", ""),
                "headline": (it.get("headline") or "")[:160], "url": it.get("url", ""),
                **({"alert_px": q["px"], "alert_move": q["move"], "alert_at": q["at"], "alert_delay": q.get("delay", 0)}
                   if q.get("px") else {}),
            })
            have.add((it["id"], sym))
            new += 1
    return new


READ_DELAY = timedelta(minutes=15)     # the news run's cadence: by then the item is in the terminal


def closed_by(t, days):
    """Index of the last session whose close (15:30 IST) had happened by time t."""
    idx = None
    for i, d in enumerate(days):
        if datetime.fromisoformat(d).replace(hour=CLOSE_TIME[0], minute=CLOSE_TIME[1], tzinfo=IST) <= t:
            idx = i
        else:
            break
    return idx


def entry_session(t, days):
    """Index of the first session that closed after the news reached readers (t + READ_DELAY)."""
    i = closed_by(t + READ_DELAY, days)
    j = 0 if i is None else i + 1
    return j if j < len(days) else None


def score(track, closes):
    sessions = closes.get("sessions", {})
    days = sorted(sessions)
    for c in track["calls"]:
        for k in ("entry_date", "entry", "r1", "r5", "hit1", "hit5", "news_day", "after_alert"):   # recomputed each run
            c.pop(k, None)
        t = datetime.fromisoformat(c["time"])
        i = entry_session(t, days)
        if i is None:
            continue  # prices not in yet, or news older than our price history
        c["entry_date"] = days[i]
        entry = sessions[days[i]].get(c["symbol"])
        if not entry:
            continue
        c["entry"] = entry
        p = closed_by(t, days)
        before = sessions[days[p]].get(c["symbol"]) if p is not None and p < i else None
        if before:
            c["news_day"] = round((entry / before - 1) * 100, 2)
        if c.get("alert_px"):
            c["after_alert"] = round((entry / c["alert_px"] - 1) * 100, 2)
        for n, k in ((1, "r1"), (5, "r5")):
            if i + n < len(days):
                px = sessions[days[i + n]].get(c["symbol"])
                if px:
                    c[k] = round((px / entry - 1) * 100, 2)
                    if c["scored"]:
                        c["hit" + str(n)] = (c[k] > 0) == (c["dir"] == "up") and c[k] != 0


def summarise(calls):
    def rate(n):
        done = [c for c in calls if c["scored"] and f"hit{n}" in c]
        hits = sum(c[f"hit{n}"] for c in done)
        signed = [c[f"r{n}"] * (1 if c["dir"] == "up" else -1) for c in done]
        return {"scored": len(done), "hits": hits,
                "hit_rate": round(hits / len(done) * 100) if done else None,
                "avg_return": round(sum(signed) / len(signed), 2) if signed else None}

    moved = [abs(c["r1"]) for c in calls if "r1" in c]
    sign = lambda c: 1 if c["dir"] == "up" else -1                    # noqa: E731
    news_day = [sign(c) * c["news_day"] for c in calls if c["scored"] and c.get("news_day") is not None]
    after = [sign(c) * c["after_alert"] for c in calls if c["scored"] and c.get("after_alert") is not None]
    return {
        "calls": len(calls),
        "scored_calls": sum(c["scored"] for c in calls),
        "d1": rate(1), "d5": rate(5),
        "avg_abs_move_1d": round(sum(moved) / len(moved), 2) if moved else None,
        # how much of the move had already happened by the entry: on the news day, and from the alert to that close
        "news_day_move": round(sum(news_day) / len(news_day), 2) if news_day else None,
        "after_alert_move": {"n": len(after), "avg": round(sum(after) / len(after), 2)} if after else None,
        "since": min((c["time"][:10] for c in calls), default=None),
    }


# ---------------------------------------------------------------- paper trading
# Rules written down before any of these trades happened (20 Nov 2026), from a test on 9-19 Nov that found nothing
# proven. Only trades entered from PAPER_START count. Same honest entry as the track record, 0.3% round-trip costs.
PAPER = os.path.join(DATA, "paper.json")
PAPER_START = "2026-11-20"
COST = 0.30
STRATEGIES = [
    {"id": "buy-the-fall", "name": "Buy the fall", "hold": 1,
     "rule": "PulsEdge flags bad news on a stock (an AI call pointing down) and the stock has already fallen 3% or more "
             "from the close before the news to the first close after it reached readers: buy at that close, sell at "
             "the next close.",
     "earlier": "9-19 Nov replay: 24 trades, 58% won, +0.42% a trade after costs (8 of them on 18 Nov; not proven)",
     "pick": lambda c: c["scored"] and c["dir"] == "down" and c.get("news_day") is not None and c["news_day"] <= -3,
     "side": lambda c: 1},
    {"id": "short-sell-alerts", "name": "Act on Sell alerts", "hold": 1,
     "rule": "Every Sell (Act) alert: short at the first close after it reached readers, buy back at the next close. "
             "In practice this needs futures or an intraday short; for a holder it means selling.",
     "earlier": "9-19 Nov replay: 25 trades, 48% won, -0.06% a trade after costs (Sell alerts beat Buy alerts, but not costs)",
     "pick": lambda c: c["call"] == "sell" and c["scored"],
     "side": lambda c: -1},
    {"id": "fade-jumps", "name": "Fade the jump", "hold": 5,
     "rule": "PulsEdge flags good news (an AI call pointing up) and the stock has already risen 3% or more by the "
             "first close after the news reached readers: short at that close, buy back five sessions later.",
     "earlier": "9-19 Nov replay: 28 trades, 75% won, +1.11% a trade after costs, 12 of them on 11 Nov (not proven)",
     "pick": lambda c: c["scored"] and c["dir"] == "up" and c.get("news_day") is not None and c["news_day"] >= 3,
     "side": lambda c: -1},
    {"id": "follow-act", "name": "Follow every Act alert (baseline)", "hold": 1,
     "rule": "Every Act alert in the alert's direction: buy if it points up, short if down, at the first close "
             "after it reached readers; exit at the next close. The yardstick the others must beat.",
     "earlier": "9-19 Nov replay: 70 trades, 39% won, -0.18% a trade after costs",
     "pick": lambda c: c["call"] in ("buy", "sell") and c["scored"],
     "side": lambda c: 1 if c["dir"] == "up" else -1},
]


def paper_book(calls, closes):
    sessions = closes.get("sessions", {})
    days = sorted(sessions)
    out = []
    for st in STRATEGIES:
        trades, seen = [], set()
        for c in sorted(calls, key=lambda c: c["time"]):
            if not c.get("entry") or c.get("entry_date", "") < PAPER_START or not st["pick"](c):
                continue
            key = (c["symbol"], c["entry_date"])
            if key in seen:                                   # one trade per stock per entry day
                continue
            seen.add(key)
            side, i = st["side"](c), days.index(c["entry_date"]) if c["entry_date"] in days else None
            t = {"date": c["entry_date"], "symbol": c["symbol"], "side": "long" if side > 0 else "short",
                 "entry": c["entry"], "headline": c["headline"][:120], "url": c.get("url", "")}
            j = None if i is None else i + st["hold"]
            px = sessions[days[j]].get(c["symbol"]) if j is not None and j < len(days) else None
            if px:
                t.update(exit_date=days[j], exit=px, net=round(side * (px / c["entry"] - 1) * 100 - COST, 2))
            trades.append(t)
        done = [t["net"] for t in trades if "net" in t]
        summary = {"closed": len(done), "open": len(trades) - len(done),
                   "win_rate": round(100 * sum(v > 0 for v in done) / len(done)) if done else None,
                   "avg_net": round(sum(done) / len(done), 2) if done else None,
                   "total_net": round(sum(done), 2) if done else None}
        out.append({k: st[k] for k in ("id", "name", "rule", "hold", "earlier")} | {"summary": summary,
                    "trades": sorted(trades, key=lambda t: t["date"], reverse=True)[:80]})
    return {"updated": NOW.isoformat(timespec="seconds"), "start": PAPER_START, "cost": COST,
            "note": "Paper trades only: no money is placed. Rules fixed on 20 Nov 2026 and never changed afterwards; "
                    "entry is the first NSE close after the news reached readers, exit the close 'hold' sessions "
                    "later, net of 0.3% round-trip costs. Educational; not investment advice.",
            "strategies": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    dry = ap.parse_args().dry_run

    feed = load(os.path.join(DATA, "feed.json"), {})
    universe = load(os.path.join(DATA, "universe.json"), {})
    track = load(TRACK, {"calls": []})
    closes = load(CLOSES, {})

    new = add_calls(track, feed)
    cutoff = (NOW - timedelta(days=KEEP_DAYS)).isoformat()
    track["calls"] = [c for c in track["calls"] if c["time"] >= cutoff]
    wanted = {s.get("symbol") for s in universe.get("stocks", []) if isinstance(s, dict)} | {c["symbol"] for c in track["calls"]}
    added = refresh_closes(closes, wanted)
    score(track, closes)
    track["calls"].sort(key=lambda c: c["time"], reverse=True)
    out = {
        "updated": NOW.isoformat(timespec="seconds"),
        "summary": summarise(track["calls"]),
        "method": "Entry is the first NSE close after the news reached readers (15 minutes after it came out); 1D and "
                  "5D are the closes 1 and 5 sessions later. Only AI calls with an up/down direction count towards the "
                  "hit rate.",
        "source": "NSE end-of-day bhavcopy",
        "calls": track["calls"],
    }
    paper = paper_book(track["calls"], closes)
    log(f"track: {new} new calls, {added} new sessions, {len(closes.get('sessions', {}))} sessions stored")
    log("summary: " + json.dumps(out["summary"]))
    log("paper: " + "; ".join(f"{s['id']} {json.dumps(s['summary'])}" for s in paper["strategies"]))
    if dry:
        return
    save(CLOSES, closes)
    save(TRACK, out)
    save(PAPER, paper)


if __name__ == "__main__":
    main()
