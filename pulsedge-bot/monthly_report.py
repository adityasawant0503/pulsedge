#!/usr/bin/env python3
"""The PulsEdge monthly report: the month in review for everyone, and what each member's browser needs to build the
section on their own holdings (pulsedge/report.html).

  python pulsedge-bot/monthly_report.py draft [--month 2026-11] [--no-ai] [--dry-run] [--if-needed]
  python pulsedge-bot/monthly_report.py publish --month 2026-11 [--announce]

draft writes pulsedge/data/monthly/<month>.json with status "draft": only the owner sees it in report.html. Read it
there, ask for changes, then publish: members see it, and with --announce the Telegram channels are told.

Where the month comes from:
- News: feed.json keeps three days, so the draft reads the last copy of each day from the git history (the news run
  commits it about every 15 minutes; pass --ref to read another branch), the working copy, and track.json's verdicts
  on named stocks.
- Prices: NSE closes in pulsedge-bot/state/closes.json (the whole Nifty 500), from the last close before the month to
  the last close in it.
- Flows and indices: pulsedge/data/flows.json (FII cash by day, FII index-futures positioning, sector indices).
Holdings never reach us: report.html matches them in the member's browser against this file.

What an AI writes here is news and context, never a recommendation: the prompts forbid advice, and any summary that
still reads like advice (buy, sell, target, stop-loss...) is listed under "flags" for the owner to check.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.normpath(os.path.join(HERE, ".."))
DATA = os.path.join(REPO, "pulsedge", "data")
OUT = os.path.join(DATA, "monthly")
IST = timezone(timedelta(hours=5, minutes=30))
FEED_PATH = "pulsedge/data/feed.json"
# advice-shaped phrases (a descriptive "sell a new drug" is fine; "should buy", "buy rating", "target price" are not)
ADVICE = re.compile(r"\b(?:(?:should|consider|time to|good time to|worth|better to|must)\s+(?:buy|sell|accumulate|exit|hold|invest|avoid|book)\w*"
                    r"|(?:buy|sell|accumulate|hold|outperform|underperform)\s+(?:rating|call|recommendation)"
                    r"|target price|price target|stop[- ]?loss|recommend\w*|multibagger|upside potential|downside risk of)\b", re.I)
# tip-style pieces from other sites ("stock to buy", "target price", "buying opportunity") stay out of the report,
# with the pipeline's own rules for brokers' views, round-ups of several stocks and live blogs
TIPS = re.compile(r"\b(?:stocks? to (?:buy|sell|watch)|to buy now|buying opportunity|target price|price target|stop[- ]?loss|"
                  r"multibagger|should you (?:buy|sell)|technical charts? suggests?|key levels)\b", re.I)
SECTION = {"global": "global", "macro": "policy"}           # everything else with a stock or Indian news is "india"
MAX_ITEMS_PER_STOCK = 5


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def month_bounds(m):
    y, mo = map(int, m.split("-"))
    return date(y, mo, 1), date(y, mo, monthrange(y, mo)[1])


def last_month(today=None):
    today = today or datetime.now(IST).date()
    first = today.replace(day=1)
    return (first - timedelta(days=1)).strftime("%Y-%m")


def in_month(t, start, end):
    return bool(t) and start.isoformat() <= str(t)[:10] <= end.isoformat()


# ---------- the month's news ----------

def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)


def feed_snapshots(start, end, ref):
    """The last committed feed.json of each day from three days before the month to its end."""
    since = (start - timedelta(days=3)).isoformat()
    until = (end + timedelta(days=1)).isoformat()
    r = git("log", ref, f"--since={since}", f"--until={until}T23:59:59+05:30", "--format=%H %cI", "--", FEED_PATH)
    if r.returncode:
        log(f"  git history unavailable ({r.stderr.strip()[:120]}); using the working copy only")
        return []
    last = {}
    for line in r.stdout.split("\n"):
        if line.strip():
            h, when = line.split(" ", 1)
            day = datetime.fromisoformat(when).astimezone(IST).date().isoformat()
            last.setdefault(day, h)                       # git log is newest first: the first seen is the day's last
    out = []
    for day, h in sorted(last.items()):
        s = git("show", f"{h}:{FEED_PATH}")
        if s.returncode == 0:
            try:
                out.append(json.loads(s.stdout))
            except ValueError:
                pass
    log(f"  {len(out)} daily copies of feed.json from the git history")
    return out


def collect(start, end, ref):
    items = {}
    for feed in feed_snapshots(start, end, ref) + [load(os.path.join(DATA, "feed.json"), {})]:
        for x in feed.get("items", []):
            if x.get("id") and x.get("headline") and in_month(x.get("time"), start, end) and x.get("call") != "ignore":
                items[x["id"]] = x                         # later copies win
    for c in load(os.path.join(DATA, "track.json"), {}).get("calls", []):
        if c.get("id") and c["id"] not in items and in_month(c.get("time"), start, end) and c.get("call") != "ignore":
            items[c["id"]] = {"id": c["id"], "time": c["time"], "headline": c.get("headline", ""), "source": c.get("source", ""),
                              "url": c.get("url", ""), "call": c.get("call"), "section": "news",
                              "tickers": [{"symbol": c["symbol"], "direction": c.get("dir")}], "impact": None}
    log(f"  {len(items)} news items worth a look in {start:%B %Y}")
    return list(items.values())


def noise(x):
    import news_pipeline as news
    h = str(x.get("headline", ""))
    return bool(TIPS.search(h) or news.BROKER.search(h) or news.LIVE_BLOG.search(h) or news.ROUNDUP.search(h))


def score(x):
    return (2 if x.get("call") in ("buy", "sell") else 1) * 100 + (x.get("impact") or 30)


def words(t):
    return {w for w in re.findall(r"[a-z0-9]+", str(t).lower()) if len(w) > 3}


def same_story(a, b):
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def clean_head(h):
    h = str(h or "").split(" |SUBJECT")[0]
    m = re.match(r"^(.+?):\s+(.+)$", h)
    if m:
        co, rest = m.group(1), m.group(2)
        rest = re.sub(r"^" + re.escape(co) + r"\s+(has\s+)?(informed the Exchange|submitted to the Exchange)\s*(about|regarding|,)?\s*", "", rest, flags=re.I)
        if rest:
            h = co + ": " + rest[0].upper() + rest[1:]
    return h[:220]


def story(x):
    why = x.get("why") or x.get("plain") or ((x.get("reason") or [""])[0] if isinstance(x.get("reason"), list) else "")
    return {"date": str(x.get("time", ""))[:10], "headline": clean_head(x.get("headline")), "source": x.get("source", ""),
            "url": x.get("url", ""), "why": str(why or "")[:240], "act": x.get("call") in ("buy", "sell"),
            "tickers": [t["symbol"] for t in (x.get("tickers") or []) if t.get("symbol")][:4]}


def top_stories(items, section, n):
    pool = sorted((x for x in items if SECTION.get(x.get("section"), "india") == section), key=lambda x: (-score(x), x.get("time", "")))
    out = []
    for x in pool:
        if any(same_story(x["headline"], y["headline"]) for y in out):
            continue
        out.append(x)
        if len(out) >= n:
            break
    return [story(x) for x in sorted(out, key=lambda x: x.get("time", ""))]


# ---------- prices, indices, flows ----------

def span(dates, start, end):
    """The last date before the month (or the first in it) and the last date in it."""
    before = [d for d in dates if d < start.isoformat()]
    inside = [d for d in dates if start.isoformat() <= d <= end.isoformat()]
    if not inside:
        return None, None
    return (before[-1] if before else inside[0]), inside[-1]


def price_moves(start, end):
    closes = load(os.path.join(HERE, "state", "closes.json"), {}).get("sessions", {})
    a, b = span(sorted(closes), start, end)
    if not a:
        return {}, None, None
    moves = {}
    for sym, px in closes[b].items():
        p0 = closes[a].get(sym)
        if p0 and px:
            moves[sym] = [round(p0, 2), round(px, 2), round((px / p0 - 1) * 100, 2)]
    return moves, a, b


def index_moves(flows, start, end):
    ih = flows.get("index_history") or {}
    a, b = span(sorted(ih), start, end)
    if not a:
        return []
    out = []
    for label, v in ih[b].items():
        p0 = (ih[a].get(label) or [None])[0]
        if p0 and v and v[0]:
            out.append({"label": label, "start": p0, "end": v[0], "chg": round((v[0] / p0 - 1) * 100, 2)})
    return out


def flow_summary(flows, start, end):
    cash = [x for x in flows.get("cash_history") or [] if in_month(x.get("date"), start, end)]
    fii = [x["fii"] for x in cash if isinstance(x.get("fii"), (int, float))]
    dii = [x["dii"] for x in cash if isinstance(x.get("dii"), (int, float))]
    fno = {d: v for d, v in (flows.get("fno_history") or {}).items() if in_month(d, start, end)}
    out = {"days": len(fii), "fii_net_cr": round(sum(fii), 1) if fii else None, "dii_net_cr": round(sum(dii), 1) if dii else None,
           "source": (cash[-1].get("src") if cash else None)}
    if fno:
        ks = sorted(fno)
        out["fii_futures_long_pct"] = {"start": fno[ks[0]], "end": fno[ks[-1]]}
    return out


# ---------- AI ----------

SYSTEM = ("You write PulsEdge's monthly market review for Indian retail investors, in plain English a 55-year-old "
          "investor follows easily. Report what happened and why it mattered, from the facts given. Never recommend "
          "buying, selling, holding or avoiding anything; no price targets, stop-losses, forecasts or predictions; no "
          "'should'. Don't invent numbers or events that aren't in the facts. Answer with a JSON object only.")


SPENT = set()        # models whose daily quota ran out during this run: not asked again


def ask(cands, user, max_tokens=2500):
    """The first model that answers. A per-minute limit is waited out and retried once; a daily one is skipped from
    then on, so the run doesn't eat the quota the live alerts need."""
    import time
    import news_pipeline as news
    news.AI_TIMEOUT = 60
    for url, key, model in cands:
        if model in SPENT:
            continue
        for attempt in (1, 2):
            try:
                return news.ask_json(url, key, model, SYSTEM, user, max_tokens), model
            except Exception as e:
                msg = str(e)
                log(f"    {model}: {type(e).__name__}: {msg[:110]}")
                if "429" in msg and news.DAILY.search(msg):
                    SPENT.add(model)
                elif "429" in msg and attempt == 1:
                    time.sleep(news.retry_after(msg, 20))
                    continue
                break
    return None, None


def write_overview(cands, rep):
    facts = {"month": rep["title"], "indices": rep["markets"], "sectors": rep["sectors"], "flows": rep["flows"],
             "india": [{k: s[k] for k in ("date", "headline", "why")} for s in rep["india"]],
             "global": [{k: s[k] for k in ("date", "headline", "why")} for s in rep["global"]],
             "policy": [{k: s[k] for k in ("date", "headline", "why")} for s in rep["policy"]]}
    user = ("Facts for the month (JSON):\n" + json.dumps(facts, ensure_ascii=False)[:14000] +
            "\n\nReturn {\"headline\": one sentence that sums up the month, \"india\": 3-4 sentences on Indian markets and "
            "companies, \"global\": 2-3 sentences on global news that mattered for India, \"flows\": 1-2 sentences on "
            "foreign investor flows (say plainly if data covers only some days), \"sectors\": 1-2 sentences on the "
            "best and worst sectors}.")
    out, model = ask(cands, user, 1500)
    if not out:
        return None
    keep = {k: str(out.get(k, "")).strip() for k in ("headline", "india", "global", "flows", "sectors") if out.get(k)}
    keep["model"] = model
    return keep


def write_stock_notes(cands, stocks):
    notes = {}
    syms = sorted(stocks, key=lambda s: -stocks[s]["weight"])
    for i in range(0, len(syms), 25):
        batch = {s: {"name": stocks[s]["name"], "month_change_pct": stocks[s]["chg"],
                     "news": [f"{it['date']}: {it['headline']}" + (f" ({it['why']})" if it["why"] else "") for it in stocks[s]["items"]]}
                 for s in syms[i:i + 25]}
        user = ("For each stock below, write 1-2 sentences for an investor who holds it: what happened this month and why "
                "it matters, using only these facts. Mention the month's price change only if given. Return a JSON "
                "object mapping each symbol to its text.\n\n" + json.dumps(batch, ensure_ascii=False))
        out, _ = ask(cands, user, 3000)
        for s, t in (out or {}).items():
            if s in batch and isinstance(t, str) and t.strip():
                notes[s] = t.strip()[:400]
        log(f"  stock notes: {len(notes)} of {min(len(syms), i + 25)}")
        if i + 25 < len(syms):
            import time
            time.sleep(6)                                 # spread the batches over minutes: free tiers limit tokens a minute
    return notes


# ---------- the report ----------

def build(month, ref, use_ai):
    start, end = month_bounds(month)
    title = start.strftime("%B %Y")
    items = collect(start, end, ref)
    n0 = len(items)
    items = [x for x in items if not noise(x)]
    log(f"  {n0 - len(items)} tips pieces, brokers' views, round-ups and live blogs left out")
    flows = load(os.path.join(DATA, "flows.json"), {})
    names = {s["symbol"]: s.get("name", s["symbol"]) for s in load(os.path.join(DATA, "universe.json"), {}).get("stocks", [])}
    moves, p0, p1 = price_moves(start, end)
    idx = index_moves(flows, start, end)
    broad = {"Nifty 50", "Midcap 100", "Smallcap 100"}

    stocks = {}
    for x in sorted(items, key=lambda x: (-score(x), x.get("time", ""))):
        for t in x.get("tickers") or []:
            s = t.get("symbol")
            if not s:
                continue
            st = stocks.setdefault(s, {"name": names.get(s, s), "chg": (moves.get(s) or [None, None, None])[2], "weight": 0, "act": 0, "top": 0, "items": []})
            st["weight"] += score(x)
            st["act"] += x.get("call") in ("buy", "sell")
            st["top"] = max(st["top"], x.get("impact") or 0)
            if len(st["items"]) < MAX_ITEMS_PER_STOCK and not any(same_story(x["headline"], y["headline"]) for y in st["items"]):
                st["items"].append(story(x))
    for st in stocks.values():
        st["items"].sort(key=lambda i: i["date"])
        # major: an Act verdict, or news the classifier rated high impact (65+ of 100)
        st["level"] = "major" if st["act"] or st["top"] >= 65 else "some"

    rep = {"month": month, "title": title, "status": "draft",
           "generated": datetime.now(IST).isoformat(timespec="minutes"),
           "period": {"news_from": min((str(x["time"])[:10] for x in items), default=None),
                      "news_to": max((str(x["time"])[:10] for x in items), default=None),
                      "prices_from": p0, "prices_to": p1, "items": len(items)},
           "markets": [i for i in idx if i["label"] in broad], "sectors": sorted((i for i in idx if i["label"] not in broad), key=lambda i: -i["chg"]),
           "flows": flow_summary(flows, start, end),
           "india": top_stories(items, "india", 10), "global": top_stories(items, "global", 6), "policy": top_stories(items, "policy", 5)}

    overview, notes = None, {}
    if use_ai:
        import news_pipeline as news
        cands = news.ai_candidates()
        if cands:
            overview = write_overview(cands, rep)
            notes = write_stock_notes(cands, stocks)
        else:
            log("  no AI keys: writing without summaries")
    if not overview:
        top = (rep["india"] + rep["global"])[:3]
        overview = {"headline": f"{title}: {len(items)} news items worth a look across {len(stocks)} stocks.",
                    "india": " ".join(f"{s['headline']}." for s in rep["india"][:3]),
                    "global": " ".join(f"{s['headline']}." for s in rep["global"][:2]), "flows": "", "sectors": "", "model": None}
    rep["overview"] = overview
    for s, st in stocks.items():
        fallback = next((i["why"] for i in st["items"] if i["why"]), st["items"][0]["headline"] if st["items"] else "")
        st["note"] = notes.get(s) or fallback
        st["note_by"] = "ai" if s in notes else "headline"
        del st["weight"], st["top"]
    rep["stocks"] = stocks
    rep["notes_by_ai"] = sum(1 for st in stocks.values() if st["note_by"] == "ai")
    rep["moves"] = moves                                  # {symbol: [close before the month, last close in it, % change]}
    rep["flags"] = [{"where": f"stocks.{s}", "text": st["note"]} for s, st in stocks.items() if ADVICE.search(st["note"])]
    rep["flags"] += [{"where": f"overview.{k}", "text": v} for k, v in overview.items() if k != "model" and isinstance(v, str) and ADVICE.search(v)]
    return rep


def save(rep):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{rep['month']}.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, separators=(",", ":"))
    idx = load(os.path.join(OUT, "index.json"), {"reports": []})
    idx["reports"] = sorted([r for r in idx["reports"] if r["month"] != rep["month"]] +
                            [{"month": rep["month"], "title": rep["title"], "status": rep["status"], "published": rep.get("published")}],
                            key=lambda r: r["month"], reverse=True)
    idx["note"] = "Monthly reports (pulsedge-bot/monthly_report.py). Drafts are shown only to the owner."
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=1)


SITE = "https://adityasawant0503.github.io/pulsedge/"


def announce(rep):
    """Tell the channels: members (the private channel, or the public one without it) and a teaser in the public one."""
    import html
    import pulse_bot as pb
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        log("TELEGRAM_BOT_TOKEN isn't set; not announced")
        return
    link = f"{SITE}report.html?m={rep['month']}"
    head = html.escape(rep["overview"].get("headline", ""))
    members = (f"📊 <b>Your PulsEdge report for {rep['title']} is ready</b>\n\n{head}\n\n"
               f"Open it on the phone or computer where you added your stocks to see what the month meant for your holdings:\n"
               f'<a href="{link}">{link}</a>\n\n<i>News and information only. Not investment advice.</i>')
    pb.send_message(token, pb.alert_chat(), members)
    if pb.pro_chat():
        teaser = (f"📊 <b>{rep['title']} in review</b>\n\n{head}\n\nRead the month in review: <a href=\"{link}\">{link}</a>\n"
                  f"Members also get a section on their own holdings.\n\n<i>News and information only. Not investment advice.</i>")
        pb.send_message(token, pb.public_chat(), teaser)
    log("announced on Telegram")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["draft", "publish"])
    ap.add_argument("--month", default="", help="YYYY-MM (default: last month)")
    ap.add_argument("--ref", default="origin/master", help="git ref whose history holds feed.json")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="draft: print a summary, write nothing")
    ap.add_argument("--if-needed", action="store_true",
                    help="draft: skip when the report is published, or was written after the month ended (a preview "
                         "written during the month is replaced)")
    ap.add_argument("--announce", action="store_true", help="publish: post to Telegram")
    a = ap.parse_args()
    month = a.month or last_month()
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        sys.exit("--month must look like 2026-11")

    if a.cmd == "draft":
        old = load(os.path.join(OUT, f"{month}.json"), {})
        if a.if_needed and old and (old.get("status") == "published" or str(old.get("generated", ""))[:10] > month_bounds(month)[1].isoformat()):
            print(f"{month}: a full report exists already; nothing to do")
            return
        if git("rev-parse", "--verify", "-q", a.ref).returncode:
            a.ref = "HEAD"
        rep = build(month, a.ref, not a.no_ai)
        log(f"{rep['title']}: {rep['period']['items']} items, {len(rep['stocks'])} stocks with news, "
            f"{sum(1 for s in rep['stocks'].values() if s['level'] == 'major')} with major news, {len(rep['moves'])} price moves, "
            f"{len(rep['flags'])} summaries flagged for review; overview by {rep['overview'].get('model') or 'headlines'}")
        if a.dry_run:
            print(json.dumps({k: rep[k] for k in ("title", "period", "overview", "markets", "flows", "flags")}, ensure_ascii=False, indent=1)[:4000])
            return
        if old.get("status") == "published":
            sys.exit(f"{month} is already published; not overwriting it")
        save(rep)
        log(f"wrote pulsedge/data/monthly/{month}.json (draft)")
        return

    path = os.path.join(OUT, f"{month}.json")
    rep = load(path, None)
    if not rep:
        sys.exit(f"no draft for {month}: run draft first")
    rep["status"] = "published"
    rep["published"] = datetime.now(IST).isoformat(timespec="minutes")
    save(rep)
    log(f"published {month}")
    if a.announce:
        announce(rep)


if __name__ == "__main__":
    main()
