#!/usr/bin/env python3
"""Upcoming events for the news calendar (work in progress: probe of the sources reachable from GitHub's runners)."""
import http.cookiejar
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PROBES = [
    ("nse api events range", "https://www.nseindia.com/api/event-calendar?index=equities&from_date=25-11-2026&to_date=31-01-2027", "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"),
    ("nse api actions range", "https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=25-11-2026&to_date=31-01-2027", "https://www.nseindia.com/companies-listing/corporate-filings-actions"),
    ("nse api board range", "https://www.nseindia.com/api/corporate-board-meetings?index=equities&from_date=25-11-2026&to_date=31-01-2027", "https://www.nseindia.com/companies-listing/corporate-filings-board-meetings"),
    ("nse api events plain", "https://www.nseindia.com/api/event-calendar?index=equities", "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"),
]


def probe():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        op.open(urllib.request.Request("https://www.nseindia.com/", headers={"User-Agent": UA}), timeout=15).read()
    except Exception as e:  # noqa: BLE001
        print("nse home:", type(e).__name__, e)
    for name, url, ref in PROBES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": ref, "Origin": ref.rstrip("/").split("/companies")[0],
                                                       "Accept-Language": "en-US,en;q=0.9"})
            with op.open(req, timeout=20) as r:
                b = r.read()
            print(f"== {name}: HTTP 200, {len(b)} bytes")
            try:
                import json
                j = json.loads(b)
                rows = j if isinstance(j, list) else j.get("data", j)
                print("rows:", len(rows), "keys:", list(rows[0].keys()) if rows else None)
                ds = sorted({str(r.get("date") or r.get("exDate") or r.get("bm_date") or "")[-8:] for r in rows})
                print("dates:", ds[:3], "...", ds[-3:], "| sample:", json.dumps(rows[:2])[:700])
            except Exception as e:  # noqa: BLE001
                print("not json:", e, b[:400])
        except Exception as e:  # noqa: BLE001
            print(f"== {name}: {type(e).__name__} {str(e)[:150]}")


if __name__ == "__main__":
    if sys.argv[1:] == ["probe"]:
        probe()
