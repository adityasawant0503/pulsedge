#!/usr/bin/env python3
"""PulsEdge fast lane: the quickest sources, checked about once a minute instead of every 15 minutes.

Sources marked "fast": true in sources.json (today: RedBox Global India's Telegram channel) are read every
--every seconds. Each new post is sorted at once, with the same AI models and keyword rules as news_pipeline.py,
and added to pulsedge/data/fast.json, which the terminal reads every minute. With --publish (GitHub Actions)
every change is committed to master and the site redeployed, so a post reaches the terminal two to three
minutes after it appears. The 15-minute news run then folds these items into feed.json as they are.

    python pulsedge-bot/fast_lane.py --dry-run                     # one check: show what is new, write nothing
    python pulsedge-bot/fast_lane.py --loop --publish --until 16:00 --minutes 345

In --loop mode it runs on NSE trading days from --start to --until IST, for at most --minutes, then prints
more=1 to $GITHUB_OUTPUT when the window is still open, so the workflow can hand over to a fresh run.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

import news_pipeline as news

FAST = os.path.join(news.DATA, "fast.json")
REPO_ROOT = os.path.normpath(os.path.join(news.HERE, ".."))
KEEP = timedelta(hours=24)     # how long items stay in fast.json; the news run has long since taken them by then
MAX_ITEMS = 80
FRESH = timedelta(hours=6)     # older posts (a first check of the day) are left to the news run


def log(*a):
    print(datetime.now(news.IST).strftime("%H:%M:%S"), *a, flush=True)


def now():
    return datetime.now(news.IST)


def fast_sources():
    path = os.environ.get("PULSEDGE_SOURCES") or os.path.join(news.HERE, "sources.json")
    return [s for s in news.load_json(path, {}).get("sources", []) if s.get("fast") and s.get("enabled") is not False]


def trading_day(t):
    hol = set(news.load_json(os.path.join(news.DATA, "calendar.json"), {}).get("holidays", []))
    return t.weekday() < 5 and t.strftime("%Y-%m-%d") not in hol


def collect(sources):
    """news_pipeline.collect without its per-source log lines, which would fill the log once a minute."""
    out = []
    for src in sources:
        try:
            got = {"bse": news.fetch_bse, "telegram": news.fetch_telegram}.get(src["kind"], news.fetch_rss)(src)
        except Exception as e:
            log(f"{src['name']}: skipped ({type(e).__name__}: {str(e)[:120]})")
            continue
        for g in got:
            g["source"], g["section_hint"] = src["name"], src.get("section", "news")
        out += got
    return out


class Sorter:
    """The AI models in news_pipeline's order. One that fails is left alone for a while: an hour when it is gone
    or out of its daily quota, as long as the provider asks when it is over a per-minute limit, two minutes otherwise."""

    def __init__(self):
        self.claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self.cands = [] if self.claude else news.ai_candidates()
        self.rest = {}

    def describe(self):
        return "Claude" if self.claude else f"{len(self.cands)} free models" if self.cands else "keyword rules"

    def __call__(self, batch, universe):
        if self.claude:
            try:
                return news.classify_claude(batch, universe), "claude"
            except Exception as e:
                log(f"  Claude failed ({type(e).__name__}: {str(e)[:120]})")
        for i, cand in enumerate(self.cands):
            if self.rest.get(i, 0) > time.time():
                continue
            try:
                return news.classify_compat(batch, universe, *cand), cand[2]
            except Exception as e:
                msg = str(e)
                log(f"  {cand[2]}: {news.brief(msg)}")
                if re.match(r"HTTP (400|401|403|404)", msg) or (msg.startswith("HTTP 429") and news.DAILY.search(msg)):
                    self.rest[i] = time.time() + 3600
                elif msg.startswith("HTTP 429"):
                    self.rest[i] = time.time() + news.retry_after(msg, 60)
                else:
                    self.rest[i] = time.time() + 120
        return None, "rules"


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def sync():
    """The latest master, so a post the news run has just taken is not sorted twice."""
    if git("fetch", "-q", "origin", "master").returncode == 0:
        git("reset", "-q", "--hard", "origin/master")


def publish(n):
    git("add", os.path.relpath(FAST, REPO_ROOT))
    if git("commit", "-q", "-m", f"PulsEdge fast lane: {n} new post{'s' if n != 1 else ''}").returncode != 0:
        return
    for attempt in range(4):
        if git("push", "-q", "origin", "HEAD:master").returncode == 0:
            break
        git("pull", "--rebase", "-q", "origin", "master")   # the news run pushed meanwhile; it never touches fast.json
        time.sleep(1 + attempt * 2)
    else:
        log("  push failed four times; these posts are picked up again on the next check")
        return
    # a push made with the workflow's own token starts no other workflow, so the site deploy is asked for directly
    r = subprocess.run(["gh", "workflow", "run", "pulsedge-pages.yml", "--ref", "master"], capture_output=True, text=True)
    log("  pushed; site deploy " + ("started" if r.returncode == 0 else f"not started ({r.stderr.strip()[:120]})"))


def check(sources, sorter, universe, known, dry, publishing):
    """One look at the fast sources. Returns how many new posts were added."""
    raw = collect(sources)

    def new_posts():
        fast = news.load_json(FAST, {"items": []})
        have = {x.get("id") for x in fast.get("items", [])}
        seen, t0, out, keys = news.load_json(news.STATE, {}), now(), [], set()
        for it in raw:
            k = news.key_of(it["headline"])
            t = it["time"] or t0
            if k in have or k in seen or k in keys or t0 - t > FRESH:
                continue
            keys.add(k)
            out.append(dict(it, key=k, time=t))
        return fast, out

    fast, new = new_posts()
    if new and publishing:
        sync()
        fast, new = new_posts()
    if not new:
        return 0
    new = sorted(new, key=lambda x: x["time"], reverse=True)[:20]
    res, by = sorter(new, universe)
    if res is None:
        res = news.classify_rules(new, universe)
    picked = now()
    items = []
    for n, it in enumerate(new):
        x = news.to_item(it, res.get(n) or news.classify_rules([it], universe)[0], known)
        lag = (picked - it["time"]).total_seconds()
        if 0 <= lag < 3600:
            x["latency"] = round(lag, 1)      # seconds from the post to PulsEdge's verdict, shown on the card
        x["lane"] = "fast"
        items.append(x)
        log(f"  {x['call'].upper():6} {x['impact']:3}  {int(lag):>5}s after posting  ({by})  {x['headline'][:90]}")

    cutoff = picked - KEEP
    old = [x for x in fast.get("items", []) if news.parse_time(x.get("time", "")) and news.parse_time(x["time"]) > cutoff]
    out = {
        "note": "Posts from the fastest sources, sorted within about a minute of appearing (pulsedge-bot/fast_lane.py). "
                "The terminal shows them until the 15-minute news run adds them to feed.json.",
        "updated": picked.isoformat(timespec="seconds"),
        "items": sorted(items + old, key=lambda x: x["time"], reverse=True)[:MAX_ITEMS],
    }
    if dry:
        log(f"dry run: {len(items)} new, nothing written")
        return len(items)
    with open(FAST, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    if publishing:
        publish(len(items))
    return len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show what is new; write nothing")
    ap.add_argument("--loop", action="store_true", help="keep checking until --until or --minutes")
    ap.add_argument("--publish", action="store_true", help="commit, push and redeploy the site after each change")
    ap.add_argument("--every", type=int, default=int(os.environ.get("PULSEDGE_FAST_EVERY") or 60), help="seconds between checks")
    ap.add_argument("--start", default="07:00", help="IST time the window opens (HH:MM)")
    ap.add_argument("--until", default="16:00", help="IST time the window closes (HH:MM)")
    ap.add_argument("--minutes", type=float, default=345, help="longest this run may keep checking")
    a = ap.parse_args()

    sources = fast_sources()
    if not sources:
        log('no source has "fast": true in sources.json; nothing to do')
        return
    universe = news.load_universe()
    known = {s["symbol"] for s in universe}
    sorter = Sorter()
    every = max(20, a.every)
    log(f"fast lane: {', '.join(s['name'] for s in sources)}; sorting with {sorter.describe()}"
        + (f"; every {every} s, {a.start}–{a.until} IST" if a.loop else ""))
    if not a.loop:
        n = check(sources, sorter, universe, known, a.dry_run, a.publish and not a.dry_run)
        log(f"{n} new")
        return

    end, checks, added, more = time.time() + a.minutes * 60, 0, 0, False
    while True:
        t = now()
        if not trading_day(t):
            log("NSE is closed today; stopping")
            break
        if t.strftime("%H:%M") >= a.until:
            log(f"{a.until} IST: window closed")
            break
        if time.time() >= end:
            more = True
            log("time limit for this run reached; handing over to the next run")
            break
        if t.strftime("%H:%M") < a.start:
            h, m = map(int, a.start.split(":"))
            wait = (t.replace(hour=h, minute=m, second=0, microsecond=0) - t).total_seconds()
            if time.time() + wait >= end:
                log(f"opens at {a.start} IST, after this run's time limit; stopping")
                break
            log(f"waiting {wait / 60:.0f} min for {a.start} IST")
            time.sleep(wait)
            continue
        began = time.time()
        try:
            added += check(sources, sorter, universe, known, a.dry_run, a.publish and not a.dry_run)
        except Exception as e:                       # one bad check never stops the lane
            log(f"check failed ({type(e).__name__}: {str(e)[:160]})")
        checks += 1
        if checks % 30 == 0:
            log(f"{checks} checks, {added} new posts so far")
        time.sleep(max(5.0, every - (time.time() - began)))
    log(f"done: {checks} checks, {added} new posts")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"more={1 if more else 0}\n")


if __name__ == "__main__":
    sys.exit(main())
