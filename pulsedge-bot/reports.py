#!/usr/bin/env python3
"""PulsEdge AI reports: a short plain-English report for each stock with flagged news, and one for the day.

The terminal's search shows them: type a company and its brief opens with the AI report; type "today" for the
day's. Reports are written by an AI model (Groq's Llama first, Google's Gemini as a fallback) from PulsEdge's
own data only: the flagged headlines about the stock, big-investor deals and how its sector moved. They explain;
they never say buy, sell or hold.

A stock's report is rewritten only when its flagged headlines change, and at most MAX_PER_RUN per run, so the
free tiers' limits hold. A report that fails the advice check is dropped, never published.

  python reports.py            # update pulsedge/data/reports.json
  python reports.py --dry-run  # write the day's report and two stock reports to the log; change nothing

Needs GROQ_API_KEY and/or AI_API_KEY (a Gemini key). Without either it leaves reports.json as it is.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "pulsedge", "data")
OUT = os.path.join(DATA, "reports.json")
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)

MAX_PER_RUN = 8                  # stock reports written per run (each is one request)
TODAY_EVERY = timedelta(minutes=45)
GAP = 5                          # seconds between requests, to stay under per-minute token limits
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_LIST = "https://api.groq.com/openai/v1/models"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# Groq's catalogue changes, so its models are picked from what it offers today: chat models only (no guard,
# speech or embedding models), Llama first as asked, larger before smaller
GROQ_SKIP = re.compile(r"guard|whisper|tts|playai|orpheus|embed|distil|compound|vision|audio|transcri", re.I)
GROQ_RANK = [r"llama-4.*maverick", r"llama-3\.3-70b", r"llama.*70b", r"llama-4.*scout", r"llama", r"qwen",
             r"gpt-oss-120b", r"kimi", r"gpt-oss", r"."]      # Qwen before gpt-oss: gpt-oss sometimes fails JSON mode
GEMINI_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest"]
NIFTY50_CSV = ["https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
               "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
               "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# the stock's sector (universe.json) -> the NSE sector index that follows it (flows.json labels); same as the terminal
SECTOR_INDEX = {"Financial Services": "Financials", "Healthcare": "Healthcare", "Automobile and Auto Components": "Auto",
                "Fast Moving Consumer Goods": "FMCG", "Information Technology": "IT", "Metals & Mining": "Metals",
                "Oil Gas & Consumable Fuels": "Oil & Gas", "Power": "Energy", "Consumer Durables": "Consumer durables",
                "Realty": "Realty", "Media Entertainment & Publication": "Media"}
# a report that reads as advice is not published
ADVICE = re.compile(r"\b(you|investors?|readers?|traders?|one)\s+(should|must|could consider|may want to|might want to|"
                    r"would do well to|are advised to)\s+(buy|sell|hold|accumulate|exit|book|add|avoid|short)\b|"
                    r"\b(target price|price target|stop[- ]?loss|multibagger|guaranteed)\b|"
                    r"\b(strong )?(buy|sell|hold) (rating|call|signal|recommendation)\b|"
                    r"\b(good|great|right) time to (buy|sell|invest)\b", re.I)

GUIDE = """You write short reports for PulsEdge, an educational service that explains Indian stock market news to
people who are new to investing. Rules:
- Use only the facts given to you. If something isn't in them, leave it out.
- Everyday English, short sentences. If you must use a market term, explain it in a few words.
- Never tell the reader to buy, sell or hold. No price targets, no predictions of the share price, no promises.
- Do not repeat brokers' or headlines' ratings, price targets or buy/sell calls, even when a headline contains them.
- When something could go either way, say so, and give both sides.
- Write as PulsEdge ("PulsEdge flagged..."), not as "I".
Reply with JSON only."""

STOCK_ASK = """Write a report on {name} ({symbol}) from the facts below. JSON fields:
"summary": 2 or 3 sentences: what is happening with the company right now.
"why": 1 or 2 sentences: why this matters to someone who owns its shares.
"upside": 1 sentence: what could turn out well, or "" if nothing in the facts points that way.
"downside": 1 sentence: what could go wrong, or "" if nothing in the facts points that way.
"watch": a list of 2 or 3 short things worth looking out for next.
"about": 1 sentence on what the company does, only if you are certain of it; otherwise "".

Facts:
{facts}"""

TODAY_ASK = """Write a short report on the Indian stock market for {day} from the facts below. JSON fields:
"summary": 3 or 4 sentences: what mattered today, in plain words.
"themes": a list of up to 3 short lines, each one theme that ran through the news.
"watch": a list of 2 or 3 short things worth looking out for next.

Facts:
{facts}"""


def log(*a):
    print(*a, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def http(url, key=None, body=None, timeout=45, accept="application/json"):
    headers = {"Accept": accept, "User-Agent": UA}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:400].decode("utf-8", "replace")
        m = re.search(r'"message"\W{1,6}(.{0,160})', detail)
        raise RuntimeError(f"HTTP {e.code} {m.group(1) if m else detail[:160]}".replace("\\n", " "))


# ---------------------------------------------------------------- models

def groq_models(key):
    """Groq's chat models, best first, from its live catalogue."""
    have = [m["id"] for m in json.loads(http(GROQ_LIST, key, timeout=20)).get("data", []) if m.get("active", True)]
    chat = [m for m in have if not GROQ_SKIP.search(m)]
    pick = lambda m: next(i for i, pat in enumerate(GROQ_RANK) if re.search(pat, m, re.I))
    small = lambda m: bool(re.search(r"(?<![0-9])(1|2|3|7|8|9|11)b(?![0-9a-z])", m, re.I))    # small models last
    ranked = sorted(chat, key=lambda m: (small(m), pick(m), m))
    log(f"Groq offers: {', '.join(sorted(have))}")
    return ranked


def candidates():
    """Models to try, best first, as (label, url, key, model)."""
    out = []
    gk = os.environ.get("GROQ_API_KEY")
    if gk:
        try:
            names = [os.environ["GROQ_MODEL"]] if os.environ.get("GROQ_MODEL") else groq_models(gk)[:3]
            log(f"Groq: using {', '.join(names) or 'none'}")
        except Exception as e:
            names = [os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile"]
            log(f"Groq model list unavailable ({e}); trying {names[0]}")
        out += [("groq", GROQ_URL, gk, m) for m in names]
    ak = os.environ.get("AI_API_KEY")
    if ak:
        url = os.environ.get("AI_BASE_URL") or GEMINI_URL
        out += [("gemini", url, ak, m) for m in GEMINI_MODELS]
    return out


class Writer:
    def __init__(self, cands):
        self.cands, self.dead, self.rest, self.calls, self.last = cands, set(), {}, 0, 0.0

    def ask(self, prompt, max_tokens=700):
        """One JSON answer from the first model that gives one, or None."""
        for i, (label, url, key, model) in enumerate(self.cands):
            if i in self.dead or self.rest.get(i, 0) > self.calls:
                continue
            wait = GAP - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            body = {"model": model, "temperature": 0.3, "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": GUIDE}, {"role": "user", "content": prompt}]}
            if label == "gemini":
                body["reasoning_effort"] = "low"
            try:
                raw = json.loads(http(url, key, body))
                text = raw["choices"][0]["message"]["content"] or ""
                text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text)
                out = json.loads(text[text.find("{"):text.rfind("}") + 1])
                self.calls += 1
                return out, model
            except Exception as e:
                msg = str(e)
                log(f"  {model}: {msg[:140]}")
                if re.match(r"HTTP (400|401|403|404)", msg):
                    self.dead.add(i)
                else:                                   # over a limit, busy or slow: skip it for a few requests
                    self.rest[i] = self.calls + (3 if msg.startswith("HTTP 429") else 1)
        self.calls += 1
        return None, None


# ---------------------------------------------------------------- facts from PulsEdge's own data

def verdict(x):
    c = str(x.get("call", "")).lower()
    return "act" if c in ("buy", "sell") else c if c in ("watch", "ignore") else "watch"


def clean_head(h):
    return str(h or "").split(" |SUBJECT")[0].strip()


def item_line(x):
    t = str(x.get("time", ""))[:16].replace("T", " ")
    bits = [f"- {t} IST, {verdict(x).upper()}: {clean_head(x.get('headline'))}"]
    if x.get("plain"):
        bits.append(f"  In plain words: {x['plain']}")
    why = x.get("why") or (x.get("reason") or [""])[0]
    if why:
        bits.append(f"  Why PulsEdge flagged it: {why}")
    if x.get("risks"):
        bits.append(f"  Risk noted: {x['risks'][0]}")
    if x.get("source"):
        bits.append(f"  Source: {x['source']}")
    return "\n".join(bits)


def pct(v):
    return f"{v:+.1f}%"


def nifty50(prev, dry):
    """The Nifty 50 symbols, refreshed weekly from NSE."""
    if prev and prev.get("symbols") and prev.get("updated", "") > (NOW - timedelta(days=6)).strftime("%Y-%m-%d"):
        return prev
    for url in NIFTY50_CSV:
        try:
            rows = list(csv.DictReader(io.StringIO(http(url, accept="text/csv,*/*", timeout=25).decode("utf-8-sig"))))
            syms = sorted(r["Symbol"].strip().upper() for r in rows if r.get("Symbol"))
            if len(syms) >= 45:
                log(f"Nifty 50 list: {len(syms)} stocks")
                return {"updated": NOW.strftime("%Y-%m-%d"), "symbols": syms}
        except Exception as e:
            log(f"Nifty 50 list: {url.split('/')[2]} failed ({e})")
    return prev or {"updated": "", "symbols": []}


def stock_facts(st, items, flows, n50):
    lines = [f"Company: {st['name']} (NSE: {st['symbol']}), sector: {st.get('sector') or 'not given'}.",
             "It is one of India's 50 largest listed companies (in the Nifty 50 index)." if st["symbol"] in n50
             else "It is in the Nifty 500, the index of India's 500 largest listed companies.",
             "", "Headlines PulsEdge flagged about it in the last few days (newest first):"]
    lines += [item_line(x) for x in items[:8]]
    deals = [d for d in (flows.get("deals") or []) if d.get("symbol") == st["symbol"]][:4]
    if deals:
        lines += ["", "Big-investor trades disclosed by NSE:"]
        lines += [f"- {d['date']}: {d['client']} {'bought' if d['side'] == 'buy' else 'sold'} shares worth "
                  f"Rs {d['value_cr']:,.0f} crore in a {d['kind']} deal" for d in deals]
    idx = SECTOR_INDEX.get(st.get("sector", ""))
    mv = next((s for s in flows.get("sectors") or [] if s.get("label") == idx), None)
    if mv and mv.get("d1") is not None:
        lines += ["", f"Its sector index ({idx}) moved {pct(mv['d1'])} in the last session"
                  + (f" and {pct(mv['d5'])} over five sessions." if mv.get("d5") is not None else ".")]
    return "\n".join(lines)


def today_facts(day, items, flows):
    lines = [f"The most important headlines PulsEdge flagged on {day}:"] + [item_line(x) for x in items[:12]]
    secs = [s for s in flows.get("sectors") or [] if not s.get("broad") and s.get("d1") is not None]
    if secs:
        secs.sort(key=lambda s: s["d1"])
        lines += ["", "Sector indices in the last session: strongest "
                  + ", ".join(f"{s['label']} {pct(s['d1'])}" for s in secs[-3:][::-1])
                  + "; weakest " + ", ".join(f"{s['label']} {pct(s['d1'])}" for s in secs[:3]) + "."]
    f = flows.get("fno") or {}
    if f.get("fii_long_pct") is not None:
        lines.append(f"Foreign funds' index-futures positions were {f['fii_long_pct']:.0f}% long"
                     + (f" (previous session {f['prev_long_pct']:.0f}%)." if f.get("prev_long_pct") is not None else "."))
    return "\n".join(lines)


def tidy(v, n=320):
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    return v[:n].rsplit(" ", 1)[0] + "…" if len(v) > n else v


def tidy_list(v, k=3, n=140):
    return [tidy(x, n) for x in (v if isinstance(v, list) else [v] if v else []) if str(x).strip()][:k]


def is_advice(rep):
    return bool(ADVICE.search(json.dumps(rep, ensure_ascii=False)))


def basis(items):
    return hashlib.sha1("|".join(sorted(x["id"] for x in items)).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    feed = load_json(os.path.join(DATA, "feed.json"), {})
    flows = load_json(os.path.join(DATA, "flows.json"), {}) or {}
    uni = {s["symbol"]: s for s in (load_json(os.path.join(DATA, "universe.json"), {}) or {}).get("stocks", [])}
    old = load_json(OUT, {}) or {}
    items = [x for x in feed.get("items", []) if x.get("headline") and x.get("id")]
    if not items:
        log("feed.json has no items; nothing to report on")
        return
    cands = candidates()
    if not cands:
        log("No AI key (GROQ_API_KEY or AI_API_KEY); reports.json left as it is")
        return
    w = Writer(cands)
    n50 = nifty50(old.get("nifty50"), a.dry_run)
    n50set = set(n50.get("symbols") or [])
    rank = lambda x: (verdict(x) == "act", x.get("impact") or 0, x.get("time", ""))

    # ---- the day's report
    # the latest day with flagged news (a weekend run would otherwise pick a day of routine filings)
    day = max((str(x.get("time", ""))[:10] for x in items if verdict(x) != "ignore"), default="")
    top = sorted((x for x in items if str(x.get("time", ""))[:10] == day and verdict(x) != "ignore"), key=rank, reverse=True)
    today, prev = old.get("today"), old.get("today") or {}
    if top:
        b = basis(top[:12])
        stale = prev.get("date") != day or (prev.get("basis") != b and NOW - datetime.fromisoformat(prev.get("updated", "2000-01-01T00:00:00+05:30")) >= TODAY_EVERY)
        if a.dry_run or stale:
            rep, model = w.ask(TODAY_ASK.format(day=datetime.fromisoformat(day).strftime("%A %d %B %Y"), facts=today_facts(day, top, flows)), 600)
            if rep:
                rep = {"summary": tidy(rep.get("summary"), 700), "themes": tidy_list(rep.get("themes")), "watch": tidy_list(rep.get("watch"))}
                if is_advice(rep):
                    log("  day's report read as advice; not published")
                elif rep["summary"]:
                    today = dict(rep, date=day, basis=b, updated=NOW.isoformat(timespec="minutes"), model=model, items=len(top))
                    log(f"day's report ({model}): {rep['summary'][:200]}")
                    if a.dry_run:
                        log(json.dumps(today, indent=1, ensure_ascii=False))

    # ---- stock reports, for stocks with flagged news
    by = {}
    for x in items:
        if verdict(x) == "ignore":
            continue
        for t in x.get("tickers") or []:
            s = str(t.get("symbol", "")).upper()
            if s in uni:
                by.setdefault(s, []).append(x)
    # a report is worth writing when there is something to explain: an Act item, an important Watch item,
    # several flagged items, or a big-investor trade
    dealt = {d.get("symbol") for d in flows.get("deals") or []}
    by = {s: v for s, v in by.items() if any(verdict(x) == "act" for x in v) or max(x.get("impact") or 0 for x in v) >= 45
          or len(v) >= 2 or s in dealt}
    order = sorted(by, key=lambda s: (any(verdict(x) == "act" for x in by[s]), max(x.get("impact") or 0 for x in by[s]),
                                      len(by[s]), max(x.get("time", "") for x in by[s])), reverse=True)
    stocks, todo = {}, []
    for s in order:
        lst = sorted(by[s], key=lambda x: x.get("time", ""), reverse=True)
        b = basis(lst)
        prev = (old.get("stocks") or {}).get(s)
        if prev:
            stocks[s] = prev                      # kept until a new one is written
        if a.dry_run or not prev or prev.get("basis") != b:
            todo.append((s, lst, b))
    limit = 2 if a.dry_run else MAX_PER_RUN
    done = 0
    for s, lst, b in todo:
        if done >= limit:
            break
        st = uni[s]
        rep, model = w.ask(STOCK_ASK.format(name=st["name"], symbol=s, facts=stock_facts(st, lst, flows, n50set)))
        done += 1
        if not rep:
            if all(i in w.dead for i in range(len(cands))):
                break
            continue
        rep = {"summary": tidy(rep.get("summary"), 520), "why": tidy(rep.get("why")), "upside": tidy(rep.get("upside")),
               "downside": tidy(rep.get("downside")), "watch": tidy_list(rep.get("watch")), "about": tidy(rep.get("about"), 220)}
        if not rep["summary"]:
            continue
        if is_advice(rep):
            log(f"  {s}: report read as advice; not published")
            continue
        stocks[s] = dict(rep, basis=b, items=len(lst), updated=NOW.isoformat(timespec="minutes"), model=model)
        log(f"{s} ({model}): {rep['summary'][:160]}")
        if a.dry_run:
            log(json.dumps(stocks[s], indent=1, ensure_ascii=False))

    if a.dry_run:
        log(f"dry run: {len(todo)} stocks would get a new report ({len(order)} with flagged news); nothing written")
        return
    out = {"note": "AI-written plain-English reports from PulsEdge's own feed, shown in the terminal's search. "
                   "Educational information, not investment advice.",
           "updated": NOW.isoformat(timespec="minutes"), "nifty50": n50, "today": today,
           "stocks": {s: stocks[s] for s in order if s in stocks}}
    same = lambda d: {k: v for k, v in d.items() if k != "updated"}
    if old and same(out) == same(old):
        log("reports unchanged")
        return
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    log(f"reports.json: {len(out['stocks'])} stock reports ({done} attempted this run, {len(todo) - done} waiting), "
        f"day's report {'present' if today else 'missing'}")


if __name__ == "__main__":
    sys.exit(main())
