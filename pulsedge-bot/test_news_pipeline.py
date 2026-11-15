#!/usr/bin/env python3
"""Checks for the parts of news_pipeline.py that decide what the public sees: which stock a headline is about, and
that no item reads as a recommendation. Needs no network and no data files.

  python pulsedge-bot/test_news_pipeline.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from news_pipeline import DEAL_SOURCE, PLAIN_ACTION, PLAIN_CHECK, heal_item, match_tickers, soften  # noqa: E402

UNIVERSE = [{"symbol": s, "name": n} for s, n in [
    ("SOLARINDS", "Solar Industries India Ltd."), ("OIL", "Oil India Ltd."), ("BANKINDIA", "Bank of India"),
    ("SBIN", "State Bank of India"), ("BSE", "BSE Ltd."), ("MCX", "Multi Commodity Exchange of India Ltd."),
    ("RELIANCE", "Reliance Industries Ltd."), ("RPOWER", "Reliance Power Ltd."), ("ENGINERSIN", "Engineers India Ltd."),
    ("SUPREMEIND", "Supreme Industries Ltd."), ("TRIDENT", "Trident Ltd."), ("ECLERX", "eClerx Services Ltd."),
    ("NUVAMA", "Nuvama Wealth Management Ltd."), ("IDBI", "IDBI Bank Ltd."), ("IDEA", "Vodafone Idea Ltd."),
    ("PAYTM", "One 97 Communications Ltd."), ("TCS", "Tata Consultancy Services Ltd."), ("SUZLON", "Suzlon Energy Ltd."),
    ("GODREJIND", "Godrej Industries Ltd."), ("GODREJPROP", "Godrej Properties Ltd."),
    ("POWERGRID", "Power Grid Corporation of India Ltd."), ("MARUTI", "Maruti Suzuki India Ltd."), ("MEESHO", "Meesho Ltd."),
    ("ACE", "Action Construction Equipment Ltd."), ("IGL", "Indraprastha Gas Ltd."),
]]

# headline -> the stocks it is about
NAMES = [
    # a word inside another company's name, or an everyday word, is not the company
    ("Vikram Solar Limited: Vikram Solar Limited has informed the Exchange regarding a press release", []),
    ("Solar stocks surge as tenders pick up", []),
    ("Solar Industries wins a defence order", ["SOLARINDS"]),
    ("Crude-sensitive stocks fall as oil trades at $95; shares of oil marketing companies fell", []),
    ("Oil prices rise 2% on supply worries", []),
    ("Oil India Ltd reports higher output", ["OIL"]),
    ("OIL Q2 profit rises 12%", ["OIL"]),
    ("Winsol Engineers Limited has submitted to the Exchange the financial results", []),
    ("Supreme Infrastructure India Limited has informed the Exchange regarding a press release", []),
    ("Supreme Court to hear the telecom dues case", []),
    ("Supreme Industries Q2 profit rises", ["SUPREMEIND"]),
    ("Trident Limited: Trident Limited has informed the Exchange about Credit Rating", ["TRIDENT"]),
    ("Fintech firms want a recurring revenue stream, replacing reliance on discretionary incentives", []),
    ("That is a good idea, say analysts", []),
    ("India's power grid failure hits three states", []),
    # the longest name wins, and bodies that are not listed are not the bank inside their name
    ("The Reserve Bank of India is expected to raise interest rates", []),
    ("State Bank of India raises deposit rates", ["SBIN"]),
    ("Bank of India Q2 profit jumps 20%", ["BANKINDIA"]),
    ("Godrej Properties buys 31-acre land in Indore", ["GODREJPROP"]),
    # one word followed by another company-like word belongs to that other company
    ("Reliance Power wins a 500 MW bid", ["RPOWER"]),
    ("Reliance Infrastructure shares fall 5%", []),
    ("IDBI Capital said that CDSL has witnessed a decisive breakout", []),
    ("IGL Spirits Limited has informed the Exchange about Change in Directors", []),
    ("IDBI Bank Q2 net profit rises", ["IDBI"]),
    ("Nuvama Wealth shares rose as much as 6.6%", ["NUVAMA"]),
    ("Suzlon Energy shares gain; Suzlon bags a 300 MW order", ["SUZLON"]),
    ("Order inflows are expected to support growth momentum for ACE Construction", ["ACE"]),
    # an exchange is the company only when the text is about the company
    ("Auto ancillary shares zoom up to 17% on BSE as Sensex gains", []),
    ("MCX gold rebounds from 1-year low", []),
    ("BSE shares hit a record high after Q2 results", ["BSE"]),
    ("BSE Limited has informed the Exchange about a board meeting", ["BSE"]),
    ("Multi Commodity Exchange posts record volumes", ["MCX"]),
    # the everyday ways news names a company still work
    ("Reliance Q2 profit beats estimates", ["RELIANCE"]),
    ("Paytm shares cross Rs 1,955 after five years", ["PAYTM"]),
    ("TCS wins a $1 billion deal", ["TCS"]),
    ("Maruti sales jump; Maruti Suzuki raises prices", ["MARUTI"]),
    ("Vodafone Idea shares decline 3.5% on wider loss", ["IDEA"]),
    ("eClerx Services Limited has informed the Exchange regarding a press release", ["ECLERX"]),
    ("Power Grid wins two transmission projects", ["POWERGRID"]),
    # in the order the text names them
    ("Stocks to watch: Meesho, TCS and Bank of India", ["MEESHO", "TCS", "BANKINDIA"]),
]

# lines that read as advice, and what they become
ADVICE_LINES = [
    "Accumulate on dips supported by brokerage confidence.",
    "Watch for pullbacks to key moving averages before entering swing trades.",
    "Watch for support near recent swing lows before considering entry.",
    "Watch for support levels to hold before considering any bottom-fishing.",
    "Watch broader market support levels before entering new trades.",
    "Watch for sustained institutional buying volumes in highlighted multibaggers.",
    "Keep a stop-loss below the day's low.",
    "A good time to buy, say analysts.",
]
# lines that describe or point to something to read, and must be left alone
FINE_LINES = [
    "Watch for follow-through in the stock if volume picks up.",
    "Watch for buying volume near support levels if momentum continues.",
    "Track institutional buying momentum in large-cap index heavyweights.",
    "Check the quarterly net profit and revenue growth figures.",
    "See why before acting: check recent results and news. One deal isn't a trend.",
    "Read the source before acting",
    "Check the company's entry into EV batteries.",
]


def test_names():
    for text, want in NAMES:
        got = match_tickers(text, UNIVERSE)
        assert got == want, f"{text!r}: got {got}, want {want}"


def test_limit():
    text = "Stocks to watch: Meesho, TCS and Bank of India"
    assert match_tickers(text, UNIVERSE, limit=2) == ["MEESHO", "TCS"]
    assert len(match_tickers(text, UNIVERSE, limit=0)) == 3


def test_advice_is_replaced():
    for line in ADVICE_LINES:
        item = {"action": line, "check": "Check the order book.", "reason": [], "risks": []}
        assert soften(item), line
        assert item["action"] == "Check the order book.", f"{line!r} -> {item['action']!r}"
        item = {"action": line, "check": line}
        soften(item)
        assert item["check"] == PLAIN_CHECK and item["action"] == PLAIN_CHECK, line
        item = {"action": line, "check": ""}
        soften(item)
        assert item["action"] == PLAIN_ACTION, line


def test_news_wording_is_kept():
    for line in FINE_LINES:
        item = {"action": line, "check": line, "plain": line, "why": line, "reason": [line], "risks": [line]}
        assert not soften(item), f"{line!r} was changed: {item}"
    # a company's own plans, and how the market behaves, are news
    item = {"plain": "The board passed a resolution to consider buying back its own shares.",
            "why": "Good news can bring profit booking, but upgraded estimates hint at long-term strength.",
            "reason": ["The company will consider selling its cement unit."], "risks": ["Profit booking near multi-year highs."]}
    assert not soften(item), item


def test_broker_calls_are_dropped():
    item = {"action": "Check the results.", "check": "", "why": "Brokers raised the target price to Rs 500.",
            "reason": ["ICICI Securities maintains a Buy rating with a 28% upside potential.", "Order book at a record."],
            "risks": ["Target price cuts by some brokerages indicate valuation caution."]}
    assert soften(item)
    assert item["reason"] == ["Order book at a record."] and item["risks"] == [] and item["why"] == ""
    assert item["action"] == "Check the results."


def test_heal_item():
    def stored(headline, symbols, **extra):
        return dict({"headline": headline, "original": headline, "source": "NSE Announcements", "action": "Read the source before acting",
                     "tickers": [{"symbol": s, "direction": "up"} for s in symbols]}, **extra)
    x = stored("Vikram Solar Limited: Vikram Solar Limited has informed the Exchange regarding a press release", ["SOLARINDS"])
    assert heal_item(x, UNIVERSE) and x["tickers"] == []
    x = stored("Crude-sensitive stocks fall as oil trades at $95; Paytm down over 2%", ["OIL", "PAYTM"])
    assert heal_item(x, UNIVERSE) and [t["symbol"] for t in x["tickers"]] == ["PAYTM"]
    # a tag the text does not explain was not made by the old name match, and is left alone
    x = stored("IT major wins a $1 billion deal", ["TCS"])
    assert not heal_item(x, UNIVERSE) and [t["symbol"] for t in x["tickers"]] == ["TCS"]
    # a deal's stock comes from the deal
    x = stored("A big investor sold about Rs 1,885 crore of solar shares in a single trade", ["SOLARINDS"], source=DEAL_SOURCE)
    assert not heal_item(x, UNIVERSE) and len(x["tickers"]) == 1
    x = stored("Reliance Q2 profit beats estimates", ["RELIANCE"], action="Accumulate on dips supported by brokerage confidence.")
    assert heal_item(x, UNIVERSE) and x["action"] == PLAIN_ACTION and [t["symbol"] for t in x["tickers"]] == ["RELIANCE"]
    assert not heal_item(x, UNIVERSE)          # a second pass changes nothing


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"{len(tests)} tests passed")
