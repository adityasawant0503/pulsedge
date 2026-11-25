#!/usr/bin/env python3
"""Upcoming events for the news calendar (work in progress: probe of the sources reachable from GitHub's runners)."""
import http.cookiejar
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PROBES = [
    ("nse rss board", "https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml", "https://www.nseindia.com/"),
    ("nse rss actions", "https://nsearchives.nseindia.com/content/RSS/Corporate_action.xml", "https://www.nseindia.com/"),
    ("nse rss results", "https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml", "https://www.nseindia.com/"),
    ("nse api events", "https://www.nseindia.com/api/event-calendar?index=equities", "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar"),
    ("nse api actions", "https://www.nseindia.com/api/corporates-corporateActions?index=equities", "https://www.nseindia.com/companies-listing/corporate-filings-actions"),
    ("bse forthcoming results", "https://api.bseindia.com/BseIndiaAPI/api/Corpforthresults/w", "https://www.bseindia.com/"),
    ("bse corp actions", "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w?Fdate=20261125&TDate=20261231&Purposecode=&strSearch=S&ddlindustrys=&ddlcategorys=E&segment=0", "https://www.bseindia.com/"),
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
            print(b[:1800].decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            print(f"== {name}: {type(e).__name__} {str(e)[:150]}")


if __name__ == "__main__":
    if sys.argv[1:] == ["probe"]:
        probe()
