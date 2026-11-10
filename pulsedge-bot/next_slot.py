#!/usr/bin/env python3
"""When should the PulsEdge news run happen next?

GitHub's own cron is often hours late for this repository, so every run of the news workflow on master
books the following one itself: it waits for the next slot below and then starts the workflow again.

Slots, Monday to Friday, India time:
  08:15 to 16:00, every 15 minutes   kind "tick"     collect, classify, deploy, post new Act signals
  19:20                              kind "evening"  the same, plus the evening summary and the daily reel

Prints "<unix time> <kind>" for the next slot, or nothing when the next slot is more than MAX_WAIT away
(a job can't wait longer than that; a later cron run picks the day up again).
"""
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
MAX_WAIT = timedelta(hours=5, minutes=40)
LEAD = timedelta(seconds=20)  # a slot closer than this is covered by the run that is asking


def slots(day):
    """The day's slots as (time, kind), in order."""
    if day.weekday() >= 5:
        return []
    at = lambda h, m: day.replace(hour=h, minute=m, second=0, microsecond=0)
    out, t = [], at(8, 15)
    while t <= at(16, 0):
        out.append((t, "tick"))
        t += timedelta(minutes=15)
    out.append((at(19, 20), "evening"))
    return out


def next_slot(now):
    for ahead in (0, 1):
        for t, kind in slots(now + timedelta(days=ahead)):
            if t > now + LEAD:
                return (t, kind) if t - now <= MAX_WAIT else None
    return None


if __name__ == "__main__":
    now = datetime.fromtimestamp(int(sys.argv[1]), IST) if len(sys.argv) > 1 else datetime.now(IST)
    hit = next_slot(now)
    if hit:
        print(int(hit[0].timestamp()), hit[1])
