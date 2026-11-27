"""Temporary: NSE option chain (new endpoints), index history, and the timestamps on NSE's live index data."""
import http.cookiejar, json, urllib.request, urllib.parse
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def nse(path, ref="https://www.nseindia.com/option-chain"):
    req = urllib.request.Request("https://www.nseindia.com/api/" + path, headers={"User-Agent": UA, "Accept": "*/*", "Referer": ref, "Accept-Language": "en-US,en;q=0.9"})
    return json.loads(op.open(req, timeout=25).read())
for u in ("https://www.nseindia.com/", "https://www.nseindia.com/option-chain"):
    try: op.open(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=15).read()
    except Exception as e: print("warm", u, type(e).__name__, e)
def show(name, f):
    try:
        v = f(); print(f"== {name}: OK"); print("  ", json.dumps(v)[:1500] if not isinstance(v, str) else v)
    except Exception as e: print(f"== {name}: {type(e).__name__} {str(e)[:120]}")
show("allIndices timestamp + keys", lambda: {k: v for k, v in nse("allIndices").items() if k != "data"} | {"n": len(nse("allIndices")["data"]),
     "first": nse("allIndices")["data"][0], "names": [d["index"] for d in nse("allIndices")["data"]][:60]})
show("india vix row", lambda: [d for d in nse("allIndices")["data"] if "VIX" in d["index"]])
show("marketStatus", lambda: nse("marketStatus"))
show("contract info", lambda: nse("option-chain-contract-info?symbol=NIFTY"))
def oc():
    info = nse("option-chain-contract-info?symbol=NIFTY"); exp = info["expiryDates"][0]
    j = nse("option-chain-v3?type=Indices&symbol=NIFTY&expiry=" + urllib.parse.quote(exp))
    recs = j.get("records", j); data = recs.get("data", [])
    return {"expiry": exp, "keys": list(j.keys()), "rec_keys": list(recs.keys()), "n": len(data), "underlying": recs.get("underlyingValue"),
            "ts": recs.get("timestamp"), "sample": data[len(data)//2] if data else None, "filtered_keys": list((j.get("filtered") or {}).keys())}
show("option chain v3 NIFTY", oc)
show("indicesHistory NIFTY 50", lambda: nse("historical/indicesHistory?indexType=" + urllib.parse.quote("NIFTY 50") + "&from=20-Nov-2026&to=27-Nov-2026", "https://www.nseindia.com/reports-indices-historical-index-data"))
show("indicesHistory v2", lambda: nse("historicalOR/indicesHistory?indexType=" + urllib.parse.quote("NIFTY 50") + "&from=20-11-2026&to=27-11-2026", "https://www.nseindia.com/reports-indices-historical-index-data"))
show("fiidii (flows.py style referer)", lambda: nse("fiidiiTradeReact", "https://www.nseindia.com/reports/fii-dii"))
show("fii derivatives stats", lambda: nse("fiidiiTradeReact"))
show("equity-stockIndices NIFTY 50", lambda: [ (d["symbol"], d["lastPrice"], d["pChange"]) for d in nse("equity-stockIndices?index=" + urllib.parse.quote("NIFTY 50"))["data"]][:5])
show("top F&O gainers/losers", lambda: list(nse("live-analysis-variations?index=gainers").keys()))
# rerun
