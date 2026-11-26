# Tighten one guide episode's voiceover, time every caption word, and name the visual cues.
# usage: python3 -I tools/tighten_howto.py <ep 1|2|3> in.mp3 out.wav timing-ep<N>.json  (edit CH and the cues for a new script)
import json, re, subprocess, sys
import numpy as np
ep, src, out, tout = int(sys.argv[1]), *sys.argv[2:5]
SR, TEMPO, LEAD_IN = 44100, 1.06, 0.2
CH = {1: [
 [("New",3),("to",2),("PulsEdge?",9)],
 [("Here's",5),("how",3),("to",2),("start.",5)],
 [("Tap",3),("the",2),("link",4),("in",2),("our",3),("bio,",3),("then",4),("start",5),("free",4),("trial.",5)],
 [("Type",4),("your",4),("email,",5),("and",3),("tap",3),("start.",5)],
 [("That's",5),("it:",3)],
 [("five",4),("trading",6),("sessions,",8)],
 [("no",2),("card.",4)],
 [("Up",2),("top,",4),("see",3),("if",2),("the",2),("market's",7),("open,",4),("and",3),("how",3),("many",4),("sessions",7),("you",2),("have",3),("left.",4)]],
 2: [
 [("Here's",5),("how",3),("to",2),("read",4),("the",2),("feed.",4)],
 [("Every",5),("headline",7),("gets",4),("a",1),("label.",5)],
 [("ACT:",4)], [("worth",4),("reading",6),("now.",3)],
 [("WATCH:",5)], [("keep",4),("an",2),("eye",2),("on",2),("it.",2)],
 [("IGNORE:",6)], [("safe",4),("to",2),("skip.",5)],
 [("Each",3),("story",5),("comes",4),("in",2),("plain",5),("English,",7),("with",3),("why",3),("it",2),("matters,",7),("and",3),("what",3),("to",2),("check",5),("next.",4)],
 [("Use",3),("the",2),("tabs",4),("to",2),("jump",4),("to",2),("big",3),("money",5),("trades,",6),("filings,",7),("or",2),("global",6),("news.",4)],
 [("And",3),("before",5),("the",2),("open,",4)],
 [("check",5),("the",2),("pre-market",10),("panel.",6)]],
 3: [
 [("Make",4),("PulsEdge",9),("yours.",5)],
 [("Search",6),("any",3),("company",7),("you",2),("own,",3),("for",3),("a",1),("one-page",8),("brief",5),("in",2),("plain",5),("English.",7)],
 [("Tap",3),("add",3),("to",2),("My",2),("stocks,",6),("and",3),("that",4),("tab",3),("shows",5),("only",4),("your",4),("stocks'",7),("news.",4)],
 [("Stuck",5),("on",2),("a",1),("word",4),("or",2),("a",1),("story?",6)],
 [("Tap",3),("Ask",3),("PulsEdge.",9)],
 [("It",2),("explains",8),("the",2),("news.",4)],
 [("The",2),("decision",7),("stays",5),("yours.",5)]],
 4: [
 [("Here's",5),("a",1),("2-minute",8),("market",6),("routine",7),("with",4),("PulsEdge.",8)],
 [("Before",6),("9:15,",10)],
 [("open",4),("the",3),("pre-market",10),("panel:",5)],
 [("Nifty,",5)], [("the",3),("US",3),("close,",5)], [("Asia,",4)], [("the",3),("rupee,",5)], [("crude",5),("and",3),("VIX,",4)],
 [("in",2),("one",3),("checklist.",9)],
 [("Once",4),("the",3),("market",6),("opens,",5)],
 [("tap",3)], [("Act",3),("now,",3)],
 [("for",3),("only",4),("the",3),("headlines",9),("worth",5),("reading",6),("now.",3)],
 [("Own",3),("a",1),("stock?",5)],
 [("My",2),("stocks",6),("shows",5),("just",4),("your",4),("companies'",9),("news.",4)],
 [("Big",3),("money",5),("shows",5),("the",3),("large",5),("trades.",6)],
 [("Confused",8),("by",2),("a",1),("headline?",8)],
 [("Tap",3),("Ask",3),("on",2),("that",4),("card,",4),("and",3),("get",3),("it",2),("in",2),("plain",5),("words.",5)],
 [("Two",3),("minutes,",7),("and",3),("you're",5),("caught",6),("up.",2)],
 [("Follow",6),("PulsEdge.",8)]]}[ep]
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
x = np.frombuffer(pcm, dtype=np.float32)
log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "silencedetect=noise=-38dB:d=0.15", "-f", "null", "-"], capture_output=True, text=True).stderr
gaps = [(float(a), float(b)) for a, b in zip(re.findall(r"silence_start: ([\d.]+)", log), re.findall(r"silence_end: ([\d.]+)", log))]
total = len(x) / SR
if gaps and gaps[-1][1] > total - 0.1:
    total = gaps[-1][0] + 0.06; x = x[:int(total * SR)]; gaps = gaps[:-1]
bounds = [0.0] + [v for g in gaps for v in g] + [total]
chunks = [(bounds[2 * i], bounds[2 * i + 1]) for i in range(len(gaps) + 1)]
assert len(chunks) == len(CH), (len(chunks), len(CH))
chunks[0] = (0.04, chunks[0][1])
pieces, segs, pos, cur = [], [], 0.0, 0.0
for i, (a, b) in enumerate(gaps):
    keep = min(0.26 if (b - a) >= 0.33 else 0.16, b - a)
    ca, cb = a + keep / 2, b - keep / 2
    segs.append((cur, ca, pos)); pieces.append(x[int(cur * SR):int(ca * SR)]); pos += ca - cur; cur = cb
segs.append((cur, total, pos)); pieces.append(x[int(cur * SR):]); pos += total - cur
def remap(t):
    for a, b, n in segs:
        if t <= b: return LEAD_IN + (n + max(0.0, t - a)) / TEMPO
    return LEAD_IN + pos / TEMPO
words, lines = [], []
for ci, ((a, b), toks) in enumerate(zip(chunks, CH)):
    a2, b2 = remap(a), remap(b)
    w = [k + 1.5 for _, k in toks]; tot = sum(w); acc = 0.0
    for (txt, _), wi in zip(toks, w):
        words.append({"w": txt, "t": round(a2 + (b2 - a2) * acc / tot, 3), "e": round(a2 + (b2 - a2) * (acc + wi) / tot, 3), "c": ci}); acc += wi
    lines.append({"a": round(a2, 3), "b": round(b2, 3)})
raw = out.replace(".wav", "-raw.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", raw], input=np.concatenate(pieces).tobytes(), check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", f"atempo={TEMPO},loudnorm=I=-14:TP=-1.5:LRA=11,adelay={int(LEAD_IN*1000)}|{int(LEAD_IN*1000)}", "-ar", "48000", "-ac", "1", out], check=True)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], capture_output=True, text=True).stdout)
L = lambda i: lines[i]["a"]
W = lambda ci, w: next(x["t"] for x in words if x["c"] == ci and x["w"] == w)
last = lines[-1]["b"]
if ep == 1:
    cues = {"hook": 0.0, "cta": L(2), "tap1": W(2, "start"), "type": L(3), "tap2": W(3, "start."), "five": L(5), "card": L(6), "top": L(7),
            "mkt": W(7, "market's"), "left": W(7, "sessions"), "end": last + 0.35}
elif ep == 2:
    cues = {"hook": 0.0, "label": L(1), "act": L(2), "watch": L(4), "ignore": L(6), "story": L(8) - 0.1, "plain": W(8, "plain"), "why": W(8, "why"),
            "check": W(8, "check"), "tabs": L(9) - 0.05, "money": W(9, "big"), "pm": L(10) - 0.05, "panel": W(11, "pre-market"), "end": last + 0.35}
elif ep == 4:
    cues = {"hook": 0.0, "pm": L(1), "panel": W(2, "pre-market"), "nifty": L(3), "us": L(4), "asia": L(5), "fx": L(6), "brent": W(7, "crude"), "vix": W(7, "VIX,"),
            "check": L(8), "open": L(9), "tapideas": L(10), "ideas": L(11) - 0.05, "own": L(13) - 0.05, "mine": W(14, "My"), "money": L(15) - 0.05,
            "stuck": L(16) - 0.05, "tapask": W(17, "Ask"), "answer": W(17, "get"), "end": L(18) - 0.1}
else:
    cues = {"hook": 0.0, "search": L(1), "pick": W(1, "one-page") - 0.3, "brief": W(1, "one-page"), "add": L(2), "tapadd": W(2, "add"), "mine": W(2, "tab"),
            "ask": L(3), "tapfab": W(4, "Ask"), "chip": W(4, "PulsEdge.") + 0.35, "answer": L(5) - 0.05, "end": L(6) - 0.1}
end = round(max(dur, last) + (2.4 if ep < 3 else 2.0 if ep == 3 else 1.0), 2)
json.dump({"ep": ep, "cues": {k: round(v, 3) for k, v in cues.items()}, "words": words, "lines": lines, "audio": round(dur, 3), "end": end}, open(tout, "w"), indent=0)
print(json.dumps({"ep": ep, "orig": round(total, 2), "new": round(dur, 2), "end": end, "cues": {k: round(v, 2) for k, v in cues.items()}}))
