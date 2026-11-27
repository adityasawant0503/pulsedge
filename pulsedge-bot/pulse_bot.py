#!/usr/bin/env python3
"""PulsEdge Telegram bot: renders PULSE signal cards and posts them to the channel.

Reads the same feed the terminal reads (pulsedge/data/feed.json, falling back to
feed.sample.json), so whatever shows in the terminal is what goes to Telegram.

  python pulse_bot.py render [--event ID] [--out DIR]   # write card PNGs, no network
  python pulse_bot.py post   [--event ID] [--dry-run]   # post new Act signals to Telegram
  python pulse_bot.py news   [--dry-run]                # post the most market-moving global and India news
  python pulse_bot.py digest [--dry-run] [--any-hour]   # post the day's evening summary (once a day)
  python pulse_bot.py brief  [--dry-run] [--any-hour]   # post the morning pre-market brief (once a day)
  python pulse_bot.py teaser [--dry-run]                # premium mode: a few delayed Act alerts for the free channel

Posting needs TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID (defaults to @pulsedgein).
Events already posted are recorded in posted.json so nothing is sent twice.

PulsEdge Premium: with the repository variable TELEGRAM_PRO_CHAT_ID set (a private channel's id, -100...; the bot must
be one of its admins), every Act card and market-moving story goes to that channel the moment it is found, here and
in the fast lane. The public channel becomes the free tier: the morning brief, up to FREE_PER_DAY Act cards a day,
each posted FREE_DELAY after members got it and saying when they did, and the evening summary with a line on what
members got that day. Without the variable everything goes to the public channel, as before.

Market-moving news: Watch items in the global or macro (economy and policy) sections with impact of at
least NEWS_MIN: the headline, why it matters and the sectors to watch, with the source credited and linked. At most
NEWS_PER_RUN per message and NEWS_PER_DAY a day; live-blog updates, stale items and repeats of a story
already posted that day are left out.

The channel stays quiet from 22:00 to 07:00 IST: signals found overnight are posted by the first run
after 07:00. The evening summary only goes out on an NSE trading day, and after 18:00 IST unless
--any-hour is given. Both rules exist because a scheduled run can arrive hours late.
"""
import argparse
import html
import io
import json
import os
import re
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "pulsedge", "data")
POSTED = os.path.join(HERE, "posted.json")
# what the fast lane (fast_lane.py) posted itself, the moment it sorted a RedBox or Walter Bloomberg post;
# read here so the 15-minute run never posts those again (each lane writes only its own file)
FAST_POSTED = os.path.join(HERE, "state", "fast_posted.json")
IST = timezone(timedelta(hours=5, minutes=30))
# premium mode: when each Act card went to the alert channel (each lane writes its own file), and what the free
# channel has had
POSTED_AT = os.path.join(HERE, "state", "posted_at.json")
FAST_POSTED_AT = os.path.join(HERE, "state", "fast_posted_at.json")
FREE_POSTED = os.path.join(HERE, "state", "free_posted.json")
FREE_PER_DAY = int(os.environ.get("PULSEDGE_FREE_PER_DAY") or 3)
FREE_DELAY = timedelta(minutes=int(os.environ.get("PULSEDGE_FREE_DELAY_MIN") or 30))

# card palette, matches terminal.html (PULSE design)
BG, PANEL, LINE = (11, 11, 16), (18, 18, 25), (38, 37, 50)
FG, MUTE, DIM = (236, 235, 243), (142, 138, 158), (95, 92, 109)
PUR, PUR_L, PUR_BOX, PUR_EDGE = (139, 92, 246), (167, 139, 250), (26, 22, 48), (76, 61, 143)
GREEN, GREEN_L, RED, RED_L, AMBER, AMBER_L = (34, 197, 94), (74, 222, 128), (239, 68, 68), (248, 113, 113), (245, 158, 11), (251, 191, 36)
CALL_EDGE = {"buy": GREEN, "sell": RED, "watch": AMBER, "ignore": DIM}
CALL_BADGE = {"buy": ((20, 83, 45), GREEN_L), "sell": ((127, 29, 29), RED_L), "watch": ((120, 53, 15), AMBER_L), "ignore": ((63, 63, 70), MUTE)}
ARROW = {"up": "▲", "down": "▼", "mixed": "◆"}
HZ = {"intraday": "Intraday", "swing": "Swing", "positional": "Positional"}


def font(size, bold=False):
    name = "JetBrainsMono-Bold.ttf" if bold else "JetBrainsMono-Regular.ttf"
    return ImageFont.truetype(os.path.join(HERE, "fonts", name), size)


# ---------- data ----------

def load_feed():
    for name in ("feed.json", "feed.sample.json"):
        path = os.path.join(DATA, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh), name
    sys.exit("No feed file found in pulsedge/data/")


def as_list(v):
    return [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])


def normalize(item):
    """Accepts the terminal's signal format and the older verdict/impacts format."""
    raw = item.get("tickers") or item.get("impacts") or []
    tickers = []
    for m in raw:
        if isinstance(m, str):
            tickers.append({"symbol": m.upper(), "direction": "up"})
        elif isinstance(m, dict) and m.get("symbol"):
            tickers.append({"symbol": str(m["symbol"]).upper(), "direction": "down" if m.get("direction") == "down" else "up"})
    dirs = {t["direction"] for t in tickers}
    direction = item.get("direction") if item.get("direction") in ARROW else ("mixed" if len(dirs) > 1 else (dirs.pop() if dirs else "mixed"))
    call = str(item.get("call", "")).lower()
    if call not in CALL_EDGE:
        v = str(item.get("verdict", "")).lower()
        call = ("sell" if direction == "down" else "buy") if v == "act" else ("ignore" if v == "ignore" else "watch")
    try:
        t = datetime.fromisoformat(str(item.get("time", "")).replace("Z", "+00:00")).astimezone(IST)
    except ValueError:
        t = None
    def score(k):
        v = item.get(k)
        return max(0, min(100, v)) if isinstance(v, (int, float)) else None
    return {
        "id": str(item.get("id") or item.get("headline", "")[:60]),
        "headline": str(item.get("headline", "")),
        "source": str(item.get("source", "")),
        "call": call,
        "horizon": str(item.get("horizon", "")).lower(),
        "direction": direction,
        "tickers": tickers,
        "sectors": as_list(item.get("sectors") or item.get("affected")),
        "impact": score("impact"),
        "confidence": score("confidence"),
        "category": str(item.get("category") or item.get("theme") or ""),
        "action": str(item.get("action", "")),
        "reason": as_list(item.get("reason")),
        "url": item.get("url") if str(item.get("url", "")).startswith(("http://", "https://")) else "",
        "time": t,
        "section": str(item.get("section", "")),
        "plain": str(item.get("plain") or ""),
        "why": str(item.get("why") or ""),
        "original": str(item.get("original") or ""),
        "quotes": item.get("quotes") if isinstance(item.get("quotes"), dict) else {},
    }


def public_chat():
    return os.environ.get("TELEGRAM_CHAT_ID") or "@pulsedgein"


def pro_chat():
    return os.environ.get("TELEGRAM_PRO_CHAT_ID", "").strip()


def alert_chat():
    """Where alerts go the moment they are found: the premium channel when there is one."""
    return pro_chat() or public_chat()


def premium_url():
    return os.environ.get("PULSEDGE_PREMIUM_URL") or SITE + "index.html#pricing"


def read_times(path):
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def write_times(path, times, now):
    """Keep four days of {id: ISO time} (enough for any free-channel delay and the evening count)."""
    keep = {k: v for k, v in times.items() if parse_iso(v) and now - parse_iso(v) < timedelta(days=4)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=1, sort_keys=True)


def parse_iso(v):
    try:
        t = datetime.fromisoformat(str(v))
        return t if t.tzinfo else t.replace(tzinfo=IST)
    except ValueError:
        return None


def alert_times():
    """{id: when it went to the alert channel}, from both lanes."""
    return {k: t for k, t in ((k, parse_iso(v)) for k, v in {**read_times(FAST_POSTED_AT), **read_times(POSTED_AT)}.items()) if t}


def postable(ev):
    return ev["call"] in ("buy", "sell")


def read_list(path):
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


# ---------- market-moving news ----------
NEWS_MIN = 45            # impact a global or macro story needs: about 2-10 a day qualify
NEWS_PER_RUN = 3
NEWS_PER_DAY = 8
NEWS_MAX_AGE = timedelta(hours=12)
LIVE_BLOG = re.compile(r"\blive\b[: ]|live updates|live blog|highlights", re.I)
SECTION_LABEL = {"global": "🌍 Global", "macro": "📊 Economy &amp; policy"}


COMMON = set("the and for are was were has had not but its which could about their this that with have will been "
             "from into over more than what when they them some also after before because while would should being "
             "make made says said year years today company companies market markets stock stocks share shares news "
             "india indian investors investor money growth economy going gone good".split())


def stems(text):
    return {w[:4] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in COMMON}


def consistent(ev):
    """The AI's plain-English line shares a word with the headline. Now and then a model answers for the wrong
    item of a batch (a dollar story summed up as an oil story); such an item never goes to the public channel.
    Items sorted by keyword rules alone (no plain line) don't either: their scores are rough."""
    return bool(ev["plain"]) and bool(stems(ev["plain"]) & stems(ev["headline"] + " " + ev["original"]))


def newsworthy(ev, now):
    return (ev["call"] == "watch" and ev["section"] in SECTION_LABEL and (ev["impact"] or 0) >= NEWS_MIN
            and ev["time"] is not None and now - ev["time"] <= NEWS_MAX_AGE and not LIVE_BLOG.search(ev["headline"])
            and consistent(ev))


def words(text):
    return {w for w in re.findall(r"[a-z0-9$%.]+", text.lower()) if len(w) > 3}


def same_story(a, b):
    """Two headlines about the same event: most of the shorter one's words appear in the other."""
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def pick_news(events, posted, now):
    """Today's best new stories, most important first, skipping repeats of a story already posted today."""
    day = now.strftime("%Y-%m-%d")
    done_ids = {p.split(":", 2)[2] for p in posted if p.startswith(f"news:{day}:")}
    left = NEWS_PER_DAY - len(done_ids)
    if left <= 0:
        return []
    done = [e["headline"] for e in events if e["id"] in done_ids]
    out = []
    for ev in sorted((e for e in events if newsworthy(e, now) and e["id"] not in done_ids),
                     key=lambda e: (-(e["impact"] or 0), -(e["time"].timestamp()))):
        if any(same_story(ev["headline"], h) for h in done + [x["headline"] for x in out]):
            continue
        out.append(ev)
        if len(out) >= min(NEWS_PER_RUN, left):
            break
    return out


def news_text(evs, now):
    lines = [f"📰 <b>Market-moving news</b> · {now:%H:%M} IST"]
    for ev in evs:
        lines += ["", f"<b>{SECTION_LABEL[ev['section']]}</b>"]
        lines.append(f"<b>{html.escape(ev['headline'])}</b>")
        why = ev["why"] or (ev["reason"][0] if ev["reason"] else "")
        if why:
            lines.append(f"Why it matters: {html.escape(why)}")
        if ev["sectors"]:
            lines.append("Sectors to watch: " + html.escape(", ".join(ev["sectors"][:3])))
        if ev["source"]:
            src = html.escape(ev["source"])
            lines.append(f'Source: <a href="{html.escape(ev["url"], quote=True)}">{src}</a>' if ev["url"] else f"Source: {src}")
    lines += ["", f'<a href="{SITE}terminal.html">Open the PULSE terminal</a> · '
                  "<i>Educational information only. Not investment advice.</i>"]
    text = "\n".join(lines)
    return text if len(text) <= 4000 else text[:3990].rsplit("\n", 1)[0] + "\n…"


def quiet_hours(now):
    return now.hour >= 22 or now.hour < 7


def trading_day(day):
    """True when NSE trades on this date (a weekday that isn't in data/calendar.json's holidays)."""
    try:
        with open(os.path.join(DATA, "calendar.json"), encoding="utf-8") as fh:
            holidays = set(json.load(fh).get("holidays", []))
    except (OSError, ValueError):
        holidays = set()
    return day.weekday() < 5 and day.isoformat() not in holidays


# ---------- card image ----------

def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def flow(draw, items, fnt, x0, width, gap=12):
    """Lay out chips left to right, wrapping; returns [(x, row, text, style)] and row count."""
    out, x, row = [], x0, 0
    for text, style in items:
        w = draw.textlength(text, font=fnt) + 28
        if x + w > x0 + width and x > x0:
            x, row = x0, row + 1
        out.append((x, row, text, style, w))
        x += w + gap
    return out, (row + 1 if items else 0)


def render(ev):
    W, M, P = 1080, 36, 44          # canvas width, outer margin, card padding
    X0, inner = M + P + 8, W - 2 * M - 2 * P - 8
    f_meta, f_meta_b = font(28), font(28, True)
    f_head, f_chip, f_body, f_small = font(44, True), font(28, True), font(30), font(24)
    d0 = ImageDraw.Draw(Image.new("RGB", (W, 10)))

    head = wrap(d0, ev["headline"], f_head, inner)
    chips = [((("▼ " if t["direction"] == "down" else "") + t["symbol"]), "down" if t["direction"] == "down" else "tk") for t in ev["tickers"]]
    chips += [(s, "sec") for s in ev["sectors"]]
    chip_pos, chip_rows = flow(d0, chips, f_chip, X0, inner)
    action = wrap(d0, "→ " + ev["action"], f_body, inner - 40) if ev["action"] else []
    reason = wrap(d0, ev["reason"][0], f_body, inner) if ev["reason"] else []

    H = M + P + 50 + 18 + len(head) * 58 + 16 + chip_rows * 58 + (60 if ev["impact"] is not None or ev["confidence"] is not None else 0)
    H += (len(action) * 42 + 40 + 18) if action else 0
    H += (len(reason) * 42 + 20) if reason else 0
    H += 70 + P + M
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((M, M, W - M, H - M), radius=24, fill=PANEL, outline=LINE, width=2)
    d.rounded_rectangle((M, M, M + 10, H - M), radius=5, fill=CALL_EDGE[ev["call"]])

    # header: time · source · CALL · horizon · direction
    y, x = M + P, X0
    if ev["time"]:
        ts = ev["time"].strftime("%H:%M:%S")
        d.text((x, y), ts, font=f_meta, fill=MUTE)
        x += d.textlength(ts, font=f_meta) + 22
    if ev["source"]:
        w = d.textlength(ev["source"], font=f_meta) + 22
        d.rounded_rectangle((x, y - 4, x + w, y + 38), radius=6, fill=(26, 22, 48), outline=PUR_EDGE, width=2)
        d.text((x + 11, y), ev["source"], font=f_meta, fill=PUR_L)
        x += w + 18
    bg, fg = CALL_BADGE[ev["call"]]
    label = "ACT" if ev["call"] in ("buy", "sell") else ev["call"].upper()   # never BUY/SELL in public posts
    w = d.textlength(label, font=f_meta_b) + 22
    d.rounded_rectangle((x, y - 4, x + w, y + 38), radius=6, fill=bg)
    d.text((x + 11, y), label, font=f_meta_b, fill=fg)
    x += w + 18
    tail = " · ".join(filter(None, [HZ.get(ev["horizon"], ev["horizon"].title()), ARROW[ev["direction"]] + " " + ev["direction"].upper()]))
    dir_col = GREEN_L if ev["direction"] == "up" else RED_L if ev["direction"] == "down" else MUTE
    if x + d.textlength(tail, font=f_meta) <= W - M - P:
        d.text((x, y), tail, font=f_meta, fill=dir_col)
    y += 50 + 18

    for line in head:
        d.text((X0, y), line, font=f_head, fill=FG)
        y += 58
    y += 16

    for cx, row, text, style, w in chip_pos:
        cy = y + row * 58
        if style == "sec":
            for dx in range(int(cx), int(cx + w), 12):   # dashed outline
                d.line((dx, cy, min(dx + 6, cx + w), cy), fill=LINE, width=2)
                d.line((dx, cy + 44, min(dx + 6, cx + w), cy + 44), fill=LINE, width=2)
            d.line((cx, cy, cx, cy + 44), fill=LINE, width=2)
            d.line((cx + w, cy, cx + w, cy + 44), fill=LINE, width=2)
            d.text((cx + 14, cy + 6), text, font=font(28), fill=MUTE)
        else:
            edge, col, fill = (RED, RED_L, (45, 20, 24)) if style == "down" else (PUR_EDGE, PUR_L, (26, 22, 48))
            d.rounded_rectangle((cx, cy, cx + w, cy + 44), radius=6, fill=fill, outline=edge, width=2)
            d.text((cx + 14, cy + 6), text, font=f_chip, fill=col)
    y += chip_rows * 58

    if ev["impact"] is not None or ev["confidence"] is not None:
        x = X0
        for name, v in (("Impact", ev["impact"]), ("Conf", ev["confidence"])):
            if v is None:
                continue
            d.text((x, y + 4), name, font=f_meta, fill=MUTE)
            x += d.textlength(name + " ", font=f_meta)
            d.text((x, y + 4), str(round(v)), font=f_meta_b, fill=FG)
            x += d.textlength(str(round(v)) + " ", font=f_meta_b)
            d.rounded_rectangle((x, y + 18, x + 120, y + 28), radius=5, fill=(42, 41, 53))
            d.rounded_rectangle((x, y + 18, x + max(10, int(120 * v / 100)), y + 28), radius=5, fill=PUR)
            x += 150
        if ev["category"] and x + d.textlength(ev["category"], font=f_meta) <= W - M - P:
            d.text((x, y + 4), ev["category"], font=f_meta, fill=MUTE)
        y += 60

    if action:
        box_h = len(action) * 42 + 40
        d.rounded_rectangle((X0, y, W - M - P, y + box_h), radius=14, fill=PUR_BOX, outline=PUR_EDGE, width=2)
        yy = y + 20
        for line in action:
            d.text((X0 + 20, yy), line, font=f_body, fill=FG)
            yy += 42
        y += box_h + 18

    for line in reason:
        d.text((X0, y), line, font=f_body, fill=MUTE)
        y += 42

    y = H - M - P - 30
    d.ellipse((X0, y + 8, X0 + 16, y + 24), fill=PUR)
    d.text((X0 + 28, y), "PULSE", font=font(26, True), fill=FG)
    note = "Not investment advice · t.me/pulsedgein"
    d.text((W - M - P - d.textlength(note, font=f_small), y + 3), note, font=f_small, fill=DIM)
    return img


# ---------- Telegram ----------

def caption(ev, extra=None):
    head = "<b>ACT · worth reading now</b>" if ev["call"] in ("buy", "sell") else f"<b>{ev['call'].upper()}</b>"
    if ev["horizon"]:
        head += f" · {HZ.get(ev['horizon'], ev['horizon'].title())}"
    if ev["source"]:
        head += f" · {html.escape(ev['source'])}"
    lines = [head, f"<b>{html.escape(ev['headline'])}</b>", ""]
    if ev["tickers"]:
        lines.append("  ".join(f"{ARROW[t['direction']]} <b>{html.escape(t['symbol'])}</b>" for t in ev["tickers"]))
    meters = [f"{k} {round(v)}" for k, v in (("Impact", ev["impact"]), ("Conf", ev["confidence"])) if v is not None]
    if meters:
        lines.append(" · ".join(meters))
    moved = [f"{t['symbol']} {q['move']:+.1f}%" for t in ev["tickers"] for q in [ev["quotes"].get(t["symbol"])]
             if q and isinstance(q.get("move"), (int, float))]
    if moved:
        late = any(abs(ev["quotes"][t["symbol"]]["move"]) >= 3 for t in ev["tickers"] if t["symbol"] in ev["quotes"])
        lines.append("Already moved today: " + ", ".join(moved) + (" · much of the move may be done" if late else "")
                     + " <i>(15-min delayed)</i>")
    if ev["reason"]:
        lines += ["", f"Why: {html.escape(ev['reason'][0])}"]
    if ev["url"]:
        lines += ["", f'<a href="{html.escape(ev["url"], quote=True)}">Source</a>']
    if extra:
        lines += [""] + extra
    lines += ["", "<i>Educational information only, not investment advice. AI can be wrong: check the source.</i>"]
    text = "\n".join(lines)
    if len(text) <= 1024:
        return text
    if extra:                                        # keep the members line; shorten the rest
        tail = "\n\n" + "\n".join(extra) + "\n\n<i>Educational information only, not investment advice.</i>"
        return text[:1020 - len(tail)].rsplit("\n", 1)[0] + "\n…" + tail
    return text[:1000].rsplit("\n", 1)[0] + "\n…"


def send_photo(token, chat_id, png, text):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", chat_id), ("caption", text), ("parse_mode", "HTML")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="pulse.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + png + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", "Telegram rejected the post"))


def send_message(token, chat_id, text):
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(body.get("description", "Telegram rejected the message"))


SITE = "https://adityasawant0503.github.io/pulsedge/"


def digest_text(feed):
    """The evening summary: what was read, what mattered, sectors, FIIs and big money."""
    dg = feed.get("digest") or {}
    day = dg.get("date") or datetime.now(IST).strftime("%Y-%m-%d")
    flows = {}
    try:
        with open(os.path.join(DATA, "flows.json"), encoding="utf-8") as fh:
            flows = json.load(fh)
    except (OSError, ValueError):
        pass
    label = datetime.strptime(day, "%Y-%m-%d").strftime("%a %-d %b")
    worth, act, ign = (dg.get("watch") or 0) + (dg.get("act") or 0), dg.get("act") or 0, dg.get("ignored") or 0
    lines = [f"<b>PulsEdge · {label}</b>",
             f"{worth + ign:,} headlines read · {worth:,} worth a look" + (f" · {act} to act on" if act else "")]
    today = [x for x in feed.get("items", []) if str(x.get("time", ""))[:10] == day and x.get("call") != "ignore"
             and x.get("kind") != "deal" and x.get("section") != "global"]
    today.sort(key=lambda x: -(x.get("impact") or 0))
    if today:
        lines += ["", "<b>Worth reading</b>"]
        for x in today[:3]:
            tk = ", ".join(t["symbol"] for t in (x.get("tickers") or [])[:2] if t.get("symbol"))
            h = str(x.get("headline", ""))
            lines.append(f"• {html.escape((tk + ': ') if tk else '')}{html.escape(h[:110] + ('…' if len(h) > 110 else ''))}")
    secs = [s for s in flows.get("sectors") or [] if not s.get("broad")]
    if secs:
        pick = secs[:2] + secs[-2:] if len(secs) > 4 else secs
        lines += ["", "<b>Sectors</b> " + " · ".join(f"{s['label']} {s['d1']:+.1f}%" for s in pick)]
    f = flows.get("fno") or {}
    if f.get("fii_long_pct") is not None:
        ch = f.get("prev_long_pct")
        lines.append(f"<b>FIIs</b> {f['fii_long_pct']}% long in index futures"
                     + (f" ({f['fii_long_pct'] - ch:+.1f} pts)" if ch is not None else ""))
    big = (flows.get("by_stock") or [])[:2]
    if big and flows.get("deals_date") == day:
        parts = []
        for b in big:
            for k, who in (("foreign_cr", "foreign funds"), ("domestic_cr", "domestic institutions")):
                v = b.get(k) or 0
                if v:
                    parts.append(f"{b['symbol']}: {who} {'bought' if v > 0 else 'sold'} ₹{abs(v):,.0f} cr")
        lines.append("<b>Big money</b> " + " · ".join(parts[:3]))
    glob = [x for x in feed.get("items", []) if str(x.get("time", ""))[:10] == day and x.get("section") == "global"
            and x.get("call") != "ignore" and not LIVE_BLOG.search(str(x.get("headline", "")))]
    glob.sort(key=lambda x: -(x.get("impact") or 0))
    if glob:
        lines += ["", "<b>Around the world</b>"]
        for x in glob[:2]:
            h = str(x.get("headline", ""))
            lines.append(f"• {html.escape(h[:110] + ('…' if len(h) > 110 else ''))}")
    lines += ["", f'<a href="{SITE}terminal.html">Open the PULSE terminal</a>',
              "<i>Educational information only. Not investment advice.</i>"]
    return day, "\n".join(lines)


def post_fast(items, dry=False):
    """Called by fast_lane.py with the items it has just sorted: posts their Act cards and any market-moving news
    at once, instead of waiting for the next 15-minute run. Returns the entries to record in FAST_POSTED."""
    now = datetime.now(IST)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = alert_chat()
    if quiet_hours(now) or not (token or dry):
        return []
    seen = read_list(POSTED) + read_list(FAST_POSTED)
    events = [normalize(x) for x in items if x.get("headline")]
    done = []
    for ev in sorted((e for e in events if postable(e) and e["id"] not in seen),
                     key=lambda e: e["time"] or datetime.min.replace(tzinfo=IST)):
        if dry:
            print(f"--- would post card {ev['id']} to {chat}\n{caption(ev)}\n")
            continue
        try:
            send_photo(token, chat, png_bytes(render(ev)), caption(ev))
            done.append(ev["id"])
        except Exception as e:                       # one failed post never stops the lane
            print(f"card {ev['id']} not posted ({type(e).__name__}: {str(e)[:120]})")
    picks = pick_news(events, seen + done, now)
    if picks:
        text = news_text(picks, now)
        if dry:
            print(f"--- would post news\n{text}\n")
        else:
            try:
                send_message(token, chat, text)
                done += [f"news:{now:%Y-%m-%d}:{e['id']}" for e in picks]
            except Exception as e:
                print(f"news not posted ({type(e).__name__}: {str(e)[:120]})")
    return done


# ---------- morning brief, free-channel previews ----------

def brief_text(pm, now):
    """The morning pre-market brief from premarket.json: GIFT Nifty's opening indication first, then the checklist."""
    if not pm or pm.get("date") != now.strftime("%Y-%m-%d"):
        return None
    # the levels, options, breadth and calendar items are for the terminal and the day trader, not the public brief
    cl = [c for c in pm.get("checklist") or [] if isinstance(c, dict) and c.get("title") and c.get("group") not in ("trade", "today")]
    if not cl:
        return None
    br = pm.get("breadth") or {}
    lines = [f"☀️ <b>PulsEdge pre-market · {now:%a} {now.day} {now:%b}</b>"]
    gift = next((c for c in cl if str(c["title"]).startswith("GIFT Nifty")), None)
    if gift:
        lines.append(f"<b>GIFT Nifty:</b> {html.escape(str(gift.get('value', '')))}")
    lines.append(f"<b>Setup:</b> {html.escape(str(pm.get('sentiment') or 'Neutral'))} "
                 f"({br.get('up', 0)}▲ {br.get('down', 0)}▼)")
    lines.append("")
    for c in cl:
        if c is gift:
            continue
        t = re.sub(r"\s+-\s+.*$", "", re.sub(r"\s*\(.*?\)\s*", " ", str(c["title"]))).strip()
        lines.append(f"{ARROW.get(c.get('dir'), '●')} {html.escape(t)}: {html.escape(str(c.get('value', '')))}")
    if pm.get("key_risk"):
        lines += ["", f"<b>Key risk:</b> {html.escape(str(pm['key_risk']))}"]
    focus = [str(f.get("symbol")) for f in pm.get("focus") or [] if isinstance(f, dict) and f.get("symbol")]
    if focus:
        lines.append("<b>Stocks in focus:</b> " + html.escape(", ".join(focus[:4])))
    lines.append("")
    yt = os.environ.get("PULSEDGE_YOUTUBE_URL", "").strip()
    if yt:
        lines.append(f'📺 <a href="{html.escape(yt, quote=True)}">Watch PulsEdge Live</a> from 8:45')
    lines.append(f'<a href="{SITE}terminal.html">Open the PULSE terminal</a> · live GIFT Nifty and global prices')
    lines.append("<i>Educational information only. Not investment advice.</i>")
    return "\n".join(lines)


def teaser_picks(events, now):
    """Premium mode: Act cards members got at least FREE_DELAY ago (today, within 4 hours), not yet in the free
    channel, best first; one a run so the day's few spread out, and none once FREE_PER_DAY is reached."""
    day = now.strftime("%Y-%m-%d")
    free = read_list(FREE_POSTED)
    if sum(p.startswith(f"free:{day}:") for p in free) >= FREE_PER_DAY:
        return []
    had = {p.split(":", 2)[2] for p in free if p.startswith("free:")}
    times = alert_times()
    out = []
    for ev in events:
        t = times.get(ev["id"])
        if (t and ev["id"] not in had and postable(ev) and consistent(ev) and t.strftime("%Y-%m-%d") == day
                and FREE_DELAY <= now - t <= timedelta(hours=4)):
            out.append((ev, t))
    out.sort(key=lambda p: (-(p[0]["impact"] or 0), p[1]))
    return out[:1]


def members_line(t, now):
    mins = max(1, round((now - t).total_seconds() / 60))
    ago = f"{mins} min earlier" if mins < 120 else f"{mins // 60} h {mins % 60} min earlier"
    return [f"🔒 <b>PulsEdge Premium members got this at {t:%H:%M}</b>, {ago}.",
            f'<a href="{html.escape(premium_url(), quote=True)}">Get every alert the moment it is found</a>']


def members_today(now):
    day = now.strftime("%Y-%m-%d")
    got = sorted(t for t in alert_times().values() if t.strftime("%Y-%m-%d") == day)
    return len(got), (got[0] if got else None)


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "post", "news", "digest", "brief", "teaser"])
    ap.add_argument("--event", help="only this event id")
    ap.add_argument("--out", default=os.path.join(HERE, "out"), help="render: output folder")
    ap.add_argument("--dry-run", action="store_true", help="post: show what would be sent")
    ap.add_argument("--any-hour", action="store_true", help="digest/brief: post it outside its usual hours")
    a = ap.parse_args()

    feed, source = load_feed()
    if a.cmd == "digest":
        day, text = digest_text(feed)
        posted = json.load(open(POSTED)) if os.path.exists(POSTED) else []
        if a.dry_run:
            print(text)
            return
        if source != "feed.json":
            print("Only sample data is present; no summary posted.")
            return
        if f"digest:{day}" in posted:
            print(f"Summary for {day} already posted.")
            return
        now = datetime.now(IST)
        if not trading_day(now.date()):
            print("NSE is closed today; no evening summary.")
            return
        if now.hour < 18 and not a.any_hour:
            print("Before 18:00 IST: too early for the evening summary.")
            return
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            print("TELEGRAM_BOT_TOKEN isn't set; skipping.")
            return
        send_message(token, alert_chat(), text)
        if pro_chat():
            n, first = members_today(now)
            free = text
            if n:
                free = text.replace("\n<i>Educational", f"\n🔒 PulsEdge Premium members got {n} alert{'s' if n != 1 else ''} "
                                    f"today, the first at {first:%H:%M}. <a href=\"{html.escape(premium_url(), quote=True)}\">Join</a>"
                                    "\n<i>Educational", 1)
            try:
                send_message(token, public_chat(), free)
            except Exception as e:
                print(f"free channel summary not posted ({type(e).__name__}: {str(e)[:120]})")
        posted.append(f"digest:{day}")
        with open(POSTED, "w") as fh:
            json.dump(posted[-2000:], fh, indent=1)
        print("posted summary for", day)
        return
    if a.cmd == "brief":
        now = datetime.now(IST)
        posted = read_list(POSTED)
        pm = None
        try:
            with open(os.path.join(DATA, "premarket.json"), encoding="utf-8") as fh:
                pm = json.load(fh)
        except (OSError, ValueError):
            pass
        text = brief_text(pm, now)
        if a.dry_run:
            print(text or "No pre-market data for today.")
            return
        if not text:
            print("No pre-market data for today; no brief.")
            return
        if f"brief:{now:%Y-%m-%d}" in posted:
            print("Today's brief already posted.")
            return
        if not trading_day(now.date()):
            print("NSE is closed today; no brief.")
            return
        upd = parse_iso(pm.get("updated"))
        if not a.any_hour and (not (8 * 60 + 15 <= now.hour * 60 + now.minute < 9 * 60 + 20)
                               or not upd or now - upd > timedelta(minutes=40)):
            print("The brief goes out between 08:15 and 09:20 IST, from pre-market data under 40 minutes old.")
            return
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            print("TELEGRAM_BOT_TOKEN isn't set; skipping.")
            return
        for chat in [public_chat()] + ([pro_chat()] if pro_chat() else []):
            try:
                send_message(token, chat, text)
            except Exception as e:
                print(f"brief not posted to {chat} ({type(e).__name__}: {str(e)[:120]})")
        posted.append(f"brief:{now:%Y-%m-%d}")
        with open(POSTED, "w") as fh:
            json.dump(posted[-2000:], fh, indent=1)
        print("posted the morning brief")
        return

    events = [normalize(x) for x in feed.get("items", []) if x.get("headline")]
    if a.cmd == "teaser":
        now = datetime.now(IST)
        if not pro_chat():
            print("No premium channel (TELEGRAM_PRO_CHAT_ID); the public channel already gets every alert.")
            return
        picks = teaser_picks(events, now)
        if not picks:
            print("No preview for the free channel this run.")
            return
        ev, t = picks[0]
        text = caption(ev, members_line(t, now))
        if a.dry_run:
            print(f"--- would post {ev['id']} to {public_chat()}\n{text}\n")
            return
        if quiet_hours(now) or source != "feed.json":
            print("Quiet hours or sample data; no preview.")
            return
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            print("TELEGRAM_BOT_TOKEN isn't set; skipping.")
            return
        send_photo(token, public_chat(), png_bytes(render(ev)), text)
        free = read_list(FREE_POSTED) + [f"free:{now:%Y-%m-%d}:{ev['id']}"]
        os.makedirs(os.path.dirname(FREE_POSTED), exist_ok=True)
        with open(FREE_POSTED, "w", encoding="utf-8") as fh:
            json.dump(free[-500:], fh, indent=1)
        print("posted a preview to the free channel:", ev["id"])
        return

    if a.event:
        events = [e for e in events if e["id"] == a.event]
        if not events:
            sys.exit(f"No event with id {a.event} in {source}")

    if a.cmd == "news":
        now = datetime.now(IST)
        posted = read_list(POSTED)
        picks = pick_news(events, posted + read_list(FAST_POSTED), now)
        if not picks:
            print("No new market-moving news.")
            return
        text = news_text(picks, now)
        if a.dry_run:
            print(text)
            return
        if source != "feed.json":
            print("Only sample data is present; no news posted.")
            return
        if quiet_hours(now):
            print("Quiet hours (22:00 to 07:00 IST): news waits for the first run after 07:00.")
            return
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            print("TELEGRAM_BOT_TOKEN isn't set; skipping.")
            return
        send_message(token, alert_chat(), text)
        posted += [f"news:{now:%Y-%m-%d}:{e['id']}" for e in picks]
        with open(POSTED, "w") as fh:
            json.dump(posted[-2000:], fh, indent=1)
        print("posted news:", ", ".join(e["id"] for e in picks))
        return

    if a.cmd == "render":
        os.makedirs(a.out, exist_ok=True)
        for ev in events:
            path = os.path.join(a.out, f"{ev['id']}.png")
            render(ev).save(path, optimize=True)
            print("wrote", path)
        return

    if source != "feed.json" and not a.event and not a.dry_run:
        print("Only sample data is present (feed.sample.json); not posting it to the channel.")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = alert_chat()
    if not token and not a.dry_run:
        print("TELEGRAM_BOT_TOKEN isn't set; skipping. Add it as a repository secret to turn posting on.")
        return
    if quiet_hours(datetime.now(IST)) and not a.event and not a.dry_run:
        print("Quiet hours (22:00 to 07:00 IST): new signals wait for the first run after 07:00.")
        return
    posted = read_list(POSTED)
    sent = set(posted) | set(read_list(FAST_POSTED))
    todo = [e for e in events if (a.event or postable(e)) and e["id"] not in sent]
    todo.sort(key=lambda e: e["time"] or datetime.min.replace(tzinfo=IST))
    if not todo:
        print("Nothing new to post.")
        return
    times = read_times(POSTED_AT)
    for ev in todo:
        if a.dry_run:
            print(f"--- would post {ev['id']} to {chat}\n{caption(ev)}\n")
            continue
        send_photo(token, chat, png_bytes(render(ev)), caption(ev))
        posted.append(ev["id"])
        times[ev["id"]] = datetime.now(IST).isoformat(timespec="seconds")
        print("posted", ev["id"])
    if not a.dry_run:
        with open(POSTED, "w") as fh:
            json.dump(posted[-2000:], fh, indent=1)
        write_times(POSTED_AT, times, datetime.now(IST))


if __name__ == "__main__":
    main()
