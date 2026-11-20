#!/usr/bin/env python3
"""Temporary probe (branch only): which live price sources a visitor's browser could call from the site."""
import json
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ORIGIN = "https://adityasawant0503.github.io"


def hit(label, url, data=None, headers=None, method=None):
    h = {"User-Agent": UA, "Origin": ORIGIN, **(headers or {})}
    try:
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            hdr = {k: v for k, v in r.headers.items() if k.lower().startswith("access-control")}
            print(f"{label:28} HTTP {r.status} cors={hdr}")
            return body
    except urllib.error.HTTPError as e:
        hdr = {k: v for k, v in e.headers.items() if k.lower().startswith("access-control")}
        print(f"{label:28} HTTP {e.code} cors={hdr} {e.read()[:160]!r}")
    except Exception as e:
        print(f"{label:28} {type(e).__name__}: {str(e)[:120]}")
    return None


TICKERS = ["NSE:NIFTY", "NSE:BANKNIFTY", "NSE:INDIAVIX", "NSEIX:NIFTY1!", "SGX:IN1!", "NSE:NIFTY1!",
           "TVC:DJI", "SP:SPX", "NASDAQ:IXIC", "CME_MINI:NQ1!", "CME_MINI:ES1!", "CBOT_MINI:YM1!",
           "TVC:NI225", "TVC:HSI", "TVC:KOSPI", "TVC:DXY", "FX_IDC:USDINR", "TVC:UKOIL", "TVC:USOIL",
           "TVC:GOLD", "TVC:US10Y", "NSE:RELIANCE", "BSE:SENSEX"]
cols = ["close", "change", "update_mode", "description", "type"]

for scan, ctype in (("global", "application/json"), ("global", "text/plain;charset=UTF-8")):
    body = hit(f"tv {scan} {ctype[:10]}", f"https://scanner.tradingview.com/{scan}/scan",
               json.dumps({"symbols": {"tickers": TICKERS}, "columns": cols}).encode(), {"Content-Type": ctype})
    if body:
        rows = {r["s"]: r["d"] for r in json.loads(body).get("data", [])}
        for t in TICKERS:
            print(f"    {t:18} {rows.get(t, 'MISSING')}")
        break
hit("tv preflight OPTIONS", "https://scanner.tradingview.com/global/scan", None,
    {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}, "OPTIONS")

hit("cnbc json", "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=.NSEI&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")
b = hit("cnbc jsonp", "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=.NSEI|@ND.1&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=jsonp&callback=pe")
print("    ", (b or "")[:300])
hit("yahoo chart", "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?range=1d&interval=1m")
b = hit("bse announcements", "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=&strScrip=&strSearch=P&strToDate=&strType=C&subcategory=-1",
        None, {"Referer": "https://www.bseindia.com/", "Accept": "application/json"})
print("    ", (b or "")[:300])
b = hit("nse announcements", "https://www.nseindia.com/api/corporate-announcements?index=equities",
        None, {"Referer": "https://www.nseindia.com/", "Accept": "application/json"})
