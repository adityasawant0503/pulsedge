"""Temporary: which economic-calendar sources answer GitHub's runners."""
import json, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
P = [
 ("tradingview", "https://economic-calendar.tradingview.com/events?from=2026-11-26T00:00:00.000Z&to=2027-01-31T00:00:00.000Z&countries=US,IN,EU,GB,JP,CN", {"Origin": "https://in.tradingview.com", "Referer": "https://in.tradingview.com/"}),
 ("forexfactory week", "https://nfs.faireconomy.media/ff_calendar_thisweek.json", {}),
 ("forexfactory next", "https://nfs.faireconomy.media/ff_calendar_nextweek.json", {}),
]
for name, url, h in P:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **h})
        b = urllib.request.urlopen(req, timeout=20).read()
        j = json.loads(b)
        rows = j.get("result", j) if isinstance(j, dict) else j
        print(f"== {name}: {len(b)} bytes, {len(rows)} rows")
        hi = [r for r in rows if r.get("importance") == 1 or r.get("impact") == "High"]
        print("  high:", len(hi), "keys:", list(rows[0].keys()) if rows else None)
        for r in (hi or rows)[:40]:
            print("  ", r.get("date"), r.get("country"), r.get("importance", r.get("impact")), "|", r.get("title"), "|", r.get("period", ""), r.get("forecast", ""))
        ins = [r for r in rows if r.get("country") == "IN"]
        print("  india rows:", len(ins)); [print("   IN", r.get("date"), r.get("importance"), r.get("title")) for r in ins[:25]]
    except Exception as e:
        print(f"== {name}: {type(e).__name__} {str(e)[:200]}")
