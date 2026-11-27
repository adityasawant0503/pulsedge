"""Temporary: more real-time candidates, OHLC columns, and NSE's own index and option-chain endpoints."""
import http.cookiejar, json, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def scan(url, tickers, cols):
    body = json.dumps({"symbols": {"tickers": tickers}, "columns": cols}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Content-Type": "text/plain"})
    return {r["s"]: r["d"] for r in json.loads(urllib.request.urlopen(req, timeout=20).read()).get("data", [])}

C = ["close", "change", "update_mode", "description"]
G = "https://scanner.tradingview.com/global/scan"
print("== US / crude candidates (global scanner)")
T = ["TVC:SPX", "TVC:NDX", "TVC:DJI", "SP:SPX", "NASDAQ:NDX", "DJ:DJI", "FOREXCOM:SPXUSD", "FOREXCOM:DJI", "FOREXCOM:NSXUSD",
     "CAPITALCOM:US500", "CAPITALCOM:US100", "ICMARKETS:SP500", "VANTAGE:SP500", "FXCM:SPX500", "FXCM:NAS100", "EIGHTCAP:SP500", "BLACKBULL:SP500",
     "PEPPERSTONE:SP500", "PEPPERSTONE:NAS100", "OANDA:SPX500USD", "OANDA:NAS100USD", "FTMO:US500", "SKILLING:SPX500", "GLOBALPRIME:SP500", "AMP:ES1!",
     "TVC:UKOIL", "TVC:USOIL", "FXOPEN:BRENT", "PEPPERSTONE:XBRUSD", "PEPPERSTONE:XTIUSD", "OANDA:WTICOUSD", "OANDA:BCOUSD", "ICEEUR:BRN1!", "NYMEX:CL1!",
     "SKILLING:UKOIL", "FOREXCOM:UKOIL", "FOREXCOM:USOIL", "CAPITALCOM:OIL_CRUDE", "VANTAGE:UKOIL", "FXCM:UKOilSpot", "TVC:SILVER", "COMEX:GC1!"]
try:
    got = scan(G, T, C)
    for t in T:
        d = got.get(t); print(f"  {t:26s}", "MISSING" if not d else f"{d[2]!s:22s} {d[0]!s:>10} {d[1]:>7.2f}  {d[3]}")
except Exception as e: print("  failed", e)

print("== other scanner markets for the same names")
for market in ("cfd", "forex", "futures", "america", "india"):
    try:
        got = scan(f"https://scanner.tradingview.com/{market}/scan", ["TVC:SPX", "TVC:NDX", "TVC:UKOIL", "TVC:USOIL", "NSE:NIFTY", "NSE:BANKNIFTY", "SP:SPX", "NASDAQ:NDX"], C)
        print(" ", market, {k: v[2] for k, v in got.items()})
    except Exception as e: print(" ", market, "failed", str(e)[:80])

print("== OHLC and time columns for Nifty, Bank Nifty and GIFT Nifty")
try:
    cols = ["open", "high", "low", "close", "change", "update_mode", "time", "change_abs", "volume", "Pivot.M.Classic.Middle", "Perf.1M", "ATR"]
    got = scan(G, ["NSE:NIFTY", "NSE:BANKNIFTY", "NSEIX:NIFTY1!", "NSE:INDIAVIX"], cols)
    for k, v in got.items(): print(" ", k, dict(zip(cols, v)))
except Exception as e: print("  failed", e)

print("== NSE endpoints from this runner")
jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def nse(path, ref="https://www.nseindia.com/"):
    req = urllib.request.Request("https://www.nseindia.com/api/" + path, headers={"User-Agent": UA, "Accept": "*/*", "Referer": ref, "Accept-Language": "en-US,en;q=0.9"})
    return op.open(req, timeout=20).read()
try: op.open(urllib.request.Request("https://www.nseindia.com/", headers={"User-Agent": UA}), timeout=15).read()
except Exception as e: print("  home:", type(e).__name__, e)
for name, path in [("marketStatus", "marketStatus"), ("allIndices", "allIndices"), ("option-chain NIFTY", "option-chain-indices?symbol=NIFTY"),
                   ("option-chain BANKNIFTY", "option-chain-indices?symbol=BANKNIFTY"), ("quote-derivative NIFTY", "quote-derivative?symbol=NIFTY"),
                   ("NIFTY 50 stocks", "equity-stockIndices?index=NIFTY%2050"), ("fiidii", "fiidiiTradeReact"), ("oi-spurts", "live-analysis-oi-spurts-underlyings"),
                   ("index-names", "equity-master"), ("pre-open", "market-data-pre-open?key=NIFTY")]:
    try:
        b = nse(path); j = json.loads(b)
        s = json.dumps(j)[:420]
        print(f"  {name}: 200, {len(b)} bytes | {s}")
    except Exception as e: print(f"  {name}: {type(e).__name__} {str(e)[:100]}")
