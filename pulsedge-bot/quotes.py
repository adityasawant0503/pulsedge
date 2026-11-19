#!/usr/bin/env python3
"""Live NSE prices at the moment an alert goes out.

    python pulsedge-bot/quotes.py RELIANCE TCS M&M          # print what the source returns

quotes(symbols) -> {symbol: {"px": last price, "prev": previous close, "move": % since that close, "at": ISO time}}
for the symbols it could price. Used by news_pipeline.add_quotes() for every item that names a stock while NSE is
open, so each alert records how far the stock had already moved when it went out (shown as "already +6.2% today")
and the track record can measure what happened after the alert, not just after the news.

Source: Yahoo Finance's public chart endpoint (no key; NSE's own quote API refuses GitHub's runners). A symbol it
can't price is left out; nothing here ever stops a run.
"""
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
TIMEOUT = 8


def quote(symbol):
    path = "/v8/finance/chart/" + urllib.parse.quote(symbol + ".NS") + "?range=1d&interval=1m&includePrePost=false"
    for host in HOSTS:
        try:
            req = urllib.request.Request("https://" + host + path, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                meta = json.loads(r.read())["chart"]["result"][0]["meta"]
            px, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose") or meta.get("previousClose")
            if not px or not prev:
                return None
            at = datetime.fromtimestamp(meta.get("regularMarketTime") or 0, IST)
            return {"px": round(float(px), 2), "prev": round(float(prev), 2),
                    "move": round((float(px) / float(prev) - 1) * 100, 2), "at": at.isoformat(timespec="seconds")}
        except Exception:
            continue
    return None


def quotes(symbols, workers=6):
    symbols = sorted({s for s in symbols if s})
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = dict(zip(symbols, ex.map(quote, symbols)))
    return {s: q for s, q in got.items() if q}


def market_open(t=None):
    t = t or datetime.now(IST)
    return t.weekday() < 5 and (9, 15) <= (t.hour, t.minute) < (15, 30)


if __name__ == "__main__" and sys.argv[1:2] == ["--probe"]:
    pass
elif __name__ == "__main__":
    syms = sys.argv[1:] or ["RELIANCE", "TCS", "M&M", "HDFCBANK"]
    got = quotes(syms)
    for s in syms:
        print(f"{s:12} {json.dumps(got.get(s)) if s in got else 'no price'}")
    print(f"{len(got)} of {len(syms)} priced")


def probe(symbols=("RELIANCE", "M&M")):
    """Which free price sources answer from this machine (run from the branch workflow when choosing one)."""
    import urllib.error
    def hit(label, url, data=None, headers=None):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read().decode("utf-8", "replace")
            print(f"{label:22} HTTP 200  {body[:240]!r}")
        except urllib.error.HTTPError as e:
            print(f"{label:22} HTTP {e.code}  {e.read()[:160]!r}")
        except Exception as e:
            print(f"{label:22} {type(e).__name__}: {str(e)[:120]}")
    s = symbols[0]
    hit("yahoo chart", f"https://query1.finance.yahoo.com/v8/finance/chart/{s}.NS?range=1d&interval=1m")
    hit("google finance", f"https://www.google.com/finance/quote/{s}:NSE")
    body = json.dumps({"symbols": {"tickers": [f"NSE:{x}" for x in symbols]}, "columns": ["close", "change", "update_mode"]}).encode()
    hit("tradingview scanner", "https://scanner.tradingview.com/india/scan", body, {"Content-Type": "application/json"})
    hit("nse quote api", f"https://www.nseindia.com/api/quote-equity?symbol={s}", None, {"Accept": "application/json", "Referer": "https://www.nseindia.com/"})


if __name__ == "__main__" and sys.argv[1:2] == ["--probe"]:
    probe()
