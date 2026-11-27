"""Temporary: which TradingView symbols are real time (update_mode) for the pre-market checklist."""
import json, urllib.request
T = ["NSEIX:NIFTY1!", "NSE:NIFTY", "NSE:NIFTY1!", "NSE:BANKNIFTY", "NSE:INDIAVIX",
     "CME_MINI:ES1!", "CME_MINI:NQ1!", "CBOT_MINI:YM1!", "OANDA:SPX500USD", "OANDA:NAS100USD", "OANDA:US30USD",
     "CAPITALCOM:US500", "CAPITALCOM:US100", "PEPPERSTONE:US500", "FOREXCOM:SPXUSD", "FOREXCOM:NSXUSD",
     "TVC:NI225", "OANDA:JP225USD", "TVC:HSI", "OANDA:HK33HKD", "TVC:KOSPI", "KRX:KOSPI", "CAPITALCOM:HK50",
     "FX_IDC:USDINR", "FX:USDJPY", "OANDA:USDJPY", "TVC:DXY", "CAPITALCOM:DXY",
     "ICEEUR:BRN1!", "TVC:UKOIL", "OANDA:BCOUSD", "NYMEX:CL1!", "TVC:USOIL", "CAPITALCOM:OIL_BRENT",
     "TVC:GOLD", "OANDA:XAUUSD", "TVC:US10Y", "TVC:IN10Y", "CAPITALCOM:IN50", "PEPPERSTONE:IND50", "OANDA:IN50USD"]
body = json.dumps({"symbols": {"tickers": T}, "columns": ["close", "change", "update_mode", "description"]}).encode()
req = urllib.request.Request("https://scanner.tradingview.com/global/scan", data=body, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "text/plain"})
j = json.loads(urllib.request.urlopen(req, timeout=20).read())
got = {r["s"]: r["d"] for r in j.get("data", [])}
for t in T:
    d = got.get(t)
    print(f"{t:24s}", "MISSING" if not d else f"{d[2]!s:24s} {d[0]!s:>12} {d[1]!s:>8}  {d[3]}")
