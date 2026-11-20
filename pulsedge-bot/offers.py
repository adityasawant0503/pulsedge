#!/usr/bin/env python3
"""Prices and discount codes for the website (index.html pricing, pay.html checkout).

  python pulsedge-bot/offers.py list
  python pulsedge-bot/offers.py add YOUTUBE10 --pct 10 [--plans complete_m,complete_y] [--until 2027-03-31] [--label "YouTube"]
  python pulsedge-bot/offers.py remove YOUTUBE10
  python pulsedge-bot/offers.py founding 12      # Founding 100 seats taken so far (the site shows how many are left)
  python pulsedge-bot/offers.py add ASHA10 --pct 10 --label "Partner Asha"   # a partner's code (sell.html)
  python pulsedge-bot/offers.py qr               # UPI QR codes for every price the site can show (needs: pip install segno)
  python pulsedge-bot/offers.py check            # prices, codes, QR files and the pages' built-in prices agree

Prices live in pulsedge/data/prices.json; codes in pulsedge/data/offers.json, stored only as SHA-256 hashes of
"pulsedge:" + CODE, so the public repository doesn't reveal them. The pages hash what a visitor types and look it up.
Keep your own list of codes and who has each one.

Honest pricing (India's dark-pattern guidelines, 2023): a struck-through "list" price must be a price you will really
charge after launch_until, and the Founding 100 count must be the real number of seats sold. Update both here.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "..", "pulsedge")
PRICES = os.path.join(SITE, "data", "prices.json")
OFFERS = os.path.join(SITE, "data", "offers.json")
QR_DIR = os.path.join(SITE, "assets", "pay")
VPA, PAYEE = "8073708940@ybl", "Aditya Sawant"


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def norm(code):
    return re.sub(r"\s+", "", str(code)).upper()


def code_hash(code):
    return hashlib.sha256(("pulsedge:" + norm(code)).encode()).hexdigest()


def discounted(price, pct):
    return int(round(price * (1 - pct / 100)))


def amounts(prices, offers):
    """Every amount a visitor can be asked to pay: each plan's price, and each code's price on the plans it covers."""
    out = set()
    for key, p in prices["plans"].items():
        out.add(p["price"])
        for o in offers.get("offers", []):
            if not o.get("plans") or key in o["plans"]:
                out.add(discounted(p["price"], o["pct"]))
        m = prices["plans"].get(key[:-2] + "_m") if key.endswith("_y") else None
        if m:                                       # month-to-year credit: the yearly price less the month paid
            out.add(p["price"] - m["price"])
    return sorted(out)


def upi_uri(amount):
    return f"upi://pay?pa={VPA}&pn={PAYEE.replace(' ', '%20')}&am={amount}.00&cu=INR&tn=PulsEdge"


def cmd_qr(prices, offers):
    import segno
    os.makedirs(QR_DIR, exist_ok=True)
    want = {f"upi-{a}.svg": a for a in amounts(prices, offers)}
    for name, a in want.items():
        segno.make(upi_uri(a), error="m").save(os.path.join(QR_DIR, name), scale=8, border=2, dark="#0b0b10", light="#ffffff")
    for name in os.listdir(QR_DIR):          # QR codes for prices no longer offered
        if name.startswith("upi-") and name.endswith(".svg") and name not in want:
            os.remove(os.path.join(QR_DIR, name))
    print(f"{len(want)} QR codes in {os.path.relpath(QR_DIR)}: " + ", ".join(f"₹{a:,}" for a in want.values()))


def cmd_check(prices, offers):
    bad = []
    for a in amounts(prices, offers):
        if not os.path.exists(os.path.join(QR_DIR, f"upi-{a}.svg")):
            bad.append(f"no QR code for ₹{a:,} (run: offers.py qr)")
    for key, p in prices["plans"].items():
        if p.get("list") and p["list"] <= p["price"]:
            bad.append(f"{key}: list price ₹{p['list']} isn't above the price ₹{p['price']}")
    f = prices.get("founding", {})
    if not 0 <= f.get("taken", 0) <= f.get("seats", 0):
        bad.append("founding: taken must be between 0 and seats")
    # the pages carry the same prices as a fallback for when prices.json can't load
    for page in ("index.html", "pay.html"):
        html = open(os.path.join(SITE, page), encoding="utf-8").read()
        m = re.search(r"var PRICES_FALLBACK=(\{.*?\});//end", html, re.S)
        if not m:
            bad.append(f"{page}: no PRICES_FALLBACK")
            continue
        fb = json.loads(m.group(1))
        for key, p in prices["plans"].items():
            q = fb.get("plans", {}).get(key)
            if not q or q.get("price") != p["price"] or q.get("list") != p.get("list"):
                bad.append(f"{page}: fallback price for {key} differs from prices.json")
    biz = open(os.path.join(SITE, "business.html"), encoding="utf-8").read()
    for key, pk in prices.get("business", {}).get("packages", {}).items():
        if pk.get("price") and f"₹{pk['price']:,}" not in biz:
            bad.append(f"business.html doesn't show {pk['name']} at ₹{pk['price']:,}")
    # the partner page's commission table and calculator: 20% of the price after the customer's 10% off
    sell = open(os.path.join(SITE, "sell.html"), encoding="utf-8").read()
    pl = prices["plans"]
    earn = {k: round(round(pl[k]["price"] * 0.9) * 0.2) for k in ("complete_y", "pro_y", "alerts_y")}
    want = [f"₹{round(pl[k]['price'] * 0.9):,}" for k in earn] + [f"₹{v:,}" for v in earn.values()] + [f"₹{round(pl['founding']['price'] * 0.2):,}"]
    want.append(f"EARN={{c:{earn['complete_y']},p:{earn['pro_y']},a:{earn['alerts_y']}}}")
    for w in want:
        if w not in sell:
            bad.append(f"sell.html doesn't show {w} (commission figures out of date)")
    today = date.today().isoformat()
    for o in offers.get("offers", []):
        if o.get("until") and o["until"] < today:
            print(f"note: code '{o.get('label')}' ended {o['until']}")
    if bad:
        print("\n".join("problem: " + b for b in bad))
        sys.exit(1)
    print("prices, codes and QR codes agree")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "add", "remove", "founding", "qr", "check"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--pct", type=float, help="add: percent off")
    ap.add_argument("--plans", default="", help="add: comma-separated plan keys (default: every plan but founding)")
    ap.add_argument("--until", default="", help="add: last day the code works, YYYY-MM-DD")
    ap.add_argument("--label", default="", help="add: shown to the visitor, e.g. 'YouTube viewers'")
    a = ap.parse_args()
    prices = load(PRICES, None)
    if not prices:
        sys.exit(f"can't read {PRICES}")
    offers = load(OFFERS, {"note": "Discount codes, stored as SHA-256 hashes. Manage with pulsedge-bot/offers.py.", "offers": []})

    if a.cmd == "list":
        for o in offers["offers"]:
            print(f"{o['label']:28} {o['pct']:g}% off  plans: {','.join(o.get('plans') or ['all'])}  until: {o.get('until') or 'no end'}")
        f = prices["founding"]
        print(f"Founding 100: {f['taken']} of {f['seats']} taken")
        return
    if a.cmd == "add":
        if not a.arg or not a.pct or not 0 < a.pct < 100:
            sys.exit("usage: offers.py add CODE --pct 10 [--plans ...] [--until YYYY-MM-DD] [--label ...]")
        plans = [p for p in a.plans.split(",") if p] or [k for k in prices["plans"] if k != "founding"]
        unknown = [p for p in plans if p not in prices["plans"]]
        if unknown:
            sys.exit(f"unknown plans: {', '.join(unknown)} (plans: {', '.join(prices['plans'])})")
        h = code_hash(a.arg)
        offers["offers"] = [o for o in offers["offers"] if o["h"] != h] + [
            {"h": h, "pct": a.pct, "plans": plans, "until": a.until, "label": a.label or f"{a.pct:g}% off"}]
        save(OFFERS, offers)
        print(f"added {norm(a.arg)}: {a.pct:g}% off {', '.join(plans)}" + (f" until {a.until}" if a.until else ""))
        print("now run: python pulsedge-bot/offers.py qr")
        return
    if a.cmd == "remove":
        h = code_hash(a.arg or "")
        n = len(offers["offers"])
        offers["offers"] = [o for o in offers["offers"] if o["h"] != h]
        save(OFFERS, offers)
        print("removed" if len(offers["offers"]) < n else "no such code")
        return
    if a.cmd == "founding":
        prices["founding"]["taken"] = int(a.arg or 0)
        save(PRICES, prices)
        print(f"Founding 100: {prices['founding']['taken']} of {prices['founding']['seats']} taken")
        return
    if a.cmd == "qr":
        cmd_qr(prices, offers)
        return
    cmd_check(prices, offers)


if __name__ == "__main__":
    main()
