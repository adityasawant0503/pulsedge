#!/usr/bin/env python3
"""Test the Act checks on every past Act alert (pulsedge-bot/eval/act_alerts.json).

    python pulsedge-bot/eval_act.py            # the rules only (no network)
    python pulsedge-bot/eval_act.py --review   # the rules, then the second AI check (needs the AI keys)

For each alert it re-runs news_pipeline.temper() and, with --review, review_act(), then compares what each set of
alerts did next: how often the stock moved the way the alert said by the next close, and the average move in the
alert's direction, overall and against the average Nifty 500 stock. Run it on every change to the checks.

The sample is small (dozens of alerts), so a difference of 10 points in the hit rate can be chance; look at the
direction of the change and at which alerts were dropped, not only at the totals.
"""
import argparse
import copy
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import news_pipeline as news  # noqa: E402


def moves(alerts, key):
    return [m[key] for a in alerts for m in a["moves"].values() if m.get(key) is not None]


def line(label, alerts):
    s1, x1, s5 = moves(alerts, "s1"), moves(alerts, "x1"), moves(alerts, "s5")
    if not s1:
        return f"{label:34} {len(alerts):3} alerts, no next-day prices yet"
    p = sum(v > 0 for v in s1) / len(s1)
    ci = 1.96 * math.sqrt(p * (1 - p) / len(s1)) * 100
    five = f"  5 days {st.mean(s5):+.2f}% (n={len(s5)})" if s5 else ""
    return (f"{label:34} {len(alerts):3} alerts  next day: {round(p * 100):3}% right (±{ci:.0f})  "
            f"avg {st.mean(s1):+.2f}%  vs market {st.mean(x1):+.2f}  (n={len(s1)}){five}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="also run the second AI check")
    a = ap.parse_args()

    doc = json.load(open(os.path.join(HERE, "eval", "act_alerts.json"), encoding="utf-8"))
    alerts = doc["alerts"]
    print(f"Past Act alerts: {len(alerts)}, prices to {doc.get('prices_to')}")
    print(line("as posted", alerts))

    after = [news.temper(copy.deepcopy(x)) for x in alerts]
    ruled = [x for x in after if x["call"] in ("buy", "sell")]
    dropped = [x for x in after if x["call"] not in ("buy", "sell")]
    print(line("after the rules", ruled))
    print(line("  dropped by the rules", dropped))
    for x in dropped:
        print(f"    - {x['checked']}: {x['headline'][:90]}")

    if a.review:
        reviewed = copy.deepcopy(ruled)
        news.AI_TIMEOUT = 30
        cands = sorted(news.ai_candidates(), key=lambda c: 0 if "groq.com" in c[0] else 1)   # as in the fast lane
        for i in range(0, len(reviewed), 15):                 # small batches, like a busy hour
            news.review_act(reviewed[i:i + 15], cands)
        kept = [x for x in reviewed if x["call"] in ("buy", "sell")]
        gone = [x for x in reviewed if x["call"] not in ("buy", "sell")]
        print(line("after rules and second check", kept))
        print(line("  dropped by the second check", gone))
        for x in gone:
            print(f"    - {x.get('checked', '')[:60]}: {x['headline'][:80]}")
        for side in ("buy", "sell"):
            print(line(f"  {side} alerts kept", [x for x in kept if x["call"] == side]))


if __name__ == "__main__":
    main()
