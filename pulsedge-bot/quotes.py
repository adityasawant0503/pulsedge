#!/usr/bin/env python3
"""NSE prices at the moment an alert goes out.

    python pulsedge-bot/quotes.py RELIANCE TCS M&M          # print what the source returns
    python pulsedge-bot/quotes.py --probe                   # which free sources answer from this machine

quotes(symbols) -> {symbol: {"px": price, "prev": previous close, "move": % since that close, "at": ISO time,
"delay": seconds the price lags}} for the symbols it could price. news_pipeline.add_quotes() calls it for every item
that names a stock while NSE is open, so each alert records how far the stock had already moved when it went out
(the terminal and Telegram show "already +6.2% today") and the track record can look at what happened after it.

Source: TradingView's public screener (one request for many symbols). From GitHub's runners it is the only free
source that answers: Yahoo returns 429, NSE's own API 403, Google only as a page to scrape (checked 19 Nov 2026 with
--probe). Its NSE prices are 15 minutes delayed, so "already moved" is the move up to about 15 minutes before the
alert, and the price is not the exact one at the alert. A real-time price needs a broker's API (a key as a
repository secret). It is an unofficial endpoint: fine for this, but a paid product should take prices from a
licensed source. A symbol it can't price is left out; nothing here ever stops a run.
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SCAN = "https://scanner.tradingview.com/india/scan"
TIMEOUT = 8


def quotes(symbols):
    symbols = sorted({str(s).upper() for s in symbols if s})
    out, now = {}, datetime.now(IST).isoformat(timespec="seconds")
    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i + 100]
        body = json.dumps({"symbols": {"tickers": [f"NSE:{s}" for s in chunk]},
                           "columns": ["close", "change", "update_mode"]}).encode()
        try:
            req = urllib.request.Request(SCAN, data=body, headers={"User-Agent": UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rows = json.loads(r.read()).get("data") or []
        except Exception:
            continue
        for row in rows:
            try:
                sym, (px, chg, mode) = row["s"].split(":", 1)[1], row["d"][:3]
                if not px or chg is None:
                    continue
                delay = int(str(mode).rsplit("_", 1)[1]) if "delayed" in str(mode) else 0
                out[sym] = {"px": round(float(px), 2), "prev": round(float(px) / (1 + float(chg) / 100), 2),
                            "move": round(float(chg), 2), "at": now, "delay": delay}
            except (KeyError, ValueError, TypeError, IndexError):
                continue
    return out


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
