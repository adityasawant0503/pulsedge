#!/usr/bin/env python3
"""Temporary probe (branch only): can a visitor's browser read TradingView's screener, and which symbols work."""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IST = timezone(timedelta(hours=5, minutes=30))


def post(url, body, origin, ctype="text/plain;charset=UTF-8"):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"User-Agent": UA, "Origin": origin, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.headers.get("Access-Control-Allow-Origin"), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Access-Control-Allow-Origin"), e.read()[:200]
    except Exception as e:
        return type(e).__name__, None, str(e)[:200]


one = {"symbols": {"tickers": ["NSEIX:NIFTY1!"]}, "columns": ["close", "change", "update_mode"]}
for origin in ("https://adityasawant0503.github.io", "https://pulsedge.pages.dev", "http://localhost:8777", "https://example.com"):
    st, acao, body = post("https://scanner.tradingview.com/global/scan", one, origin)
    print(f"text/plain from {origin:38} HTTP {st} ACAO={acao} data={str(body)[:120]}")

cols = ["close", "change", "update_mode", "description", "change_abs"]
for scan, tickers in (
    ("global", ["DJ:DJI", "TVC:DJI", "NYMEX:CL1!", "ICEEUR:BRN1!", "NYMEX:BZ1!", "OANDA:BCOUSD", "OANDA:WTICOUSD",
                "TVC:UKOIL", "TVC:USOIL", "MCX:CRUDEOIL1!", "COMEX:GC1!", "OANDA:XAUUSD", "NSE:CNXIT", "NSE:CNXPHARMA",
                "NSE:NIFTY_MID_SELECT", "NSE:CNXMIDCAP", "NSE:CNXSMALLCAP", "NSE:CNXAUTO", "NSE:CNXFMCG", "NSE:CNXMETAL",
                "TVC:SHCOMP", "TVC:STI", "XETR:DAX", "TVC:UKX", "TVC:VIX", "BITSTAMP:BTCUSD", "NSE:M&M", "NSE:BAJAJ_AUTO"]),
    ("cfd", ["TVC:UKOIL", "TVC:USOIL", "TVC:DJI", "TVC:GOLD"]),
):
    st, acao, body = post(f"https://scanner.tradingview.com/{scan}/scan", {"symbols": {"tickers": tickers}, "columns": cols},
                          "https://adityasawant0503.github.io")
    rows = {r["s"]: r["d"] for r in body.get("data", [])} if isinstance(body, dict) else {}
    print(f"{scan} scan HTTP {st} ACAO={acao}")
    for t in tickers:
        print(f"    {t:22} {rows.get(t, 'MISSING')}")

# How fresh is NSE's announcements RSS (what the news run reads)?
try:
    req = urllib.request.Request("https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",
                                 headers={"User-Agent": UA, "Referer": "https://www.nseindia.com/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        xml = r.read().decode("utf-8", "replace")
    dates = [parsedate_to_datetime(d.strip()) for d in re.findall(r"<pubDate>(.*?)</pubDate>", xml)]
    now = datetime.now(IST)
    print(f"NSE RSS: {len(dates)} items; newest {[str(now - d)[:7] for d in sorted(dates, reverse=True)[:5]]} ago; "
          f"last hour: {sum(now - d < timedelta(hours=1) for d in dates)}")
except Exception as e:
    print("NSE RSS:", type(e).__name__, e)
