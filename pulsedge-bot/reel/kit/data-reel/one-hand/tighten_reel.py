# Tighten the data-reel voiceover, then time every caption word.
# usage: python3 -I tools/tighten_reel.py in.mp3 audio/vo-tight.wav timing.json  (edit CH and the cues for a new script)
import json, re, subprocess, sys
import numpy as np
src, out, tout = sys.argv[1:4]
SR, TEMPO, LEAD_IN = 44100, 1.12, 0.15
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
x = np.frombuffer(pcm, dtype=np.float32)
log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "silencedetect=noise=-38dB:d=0.18", "-f", "null", "-"], capture_output=True, text=True).stderr
gaps = [(float(a), float(b)) for a, b in zip(re.findall(r"silence_start: ([\d.]+)", log), re.findall(r"silence_end: ([\d.]+)", log))]
total = len(x) / SR
if gaps and gaps[-1][1] > total - 0.1:          # trailing silence: trim it, it is not a pause between lines
    total = gaps[-1][0] + 0.06; x = x[:int(total * SR)]; gaps = gaps[:-1]
# speech chunks between the pauses, each with its caption tokens: (shown text, spoken weight)
CH = [
 [("Foreign",7),("investors",9),("just",4),("bought",6),("₹58,000",20),("crore",5),("of",2),("Indian",6),("shares.",6)],
 [("In",2),("7",5),("trading",7),("sessions.",8)],
 [("7",5),("sessions.",8)],
 [("Net",3),("buying",6),("in",2),("every",5),("single",6),("one.",3)],
 [("But",3),("here's",5),("the",3),("twist.",5)],
 [("Look",4),("at",2),("their",5),("index",5),("futures.",7)],
 [("On",2),("12",7),("November,",8),("37%",16),("of",2),("their",5),("bets",4),("were",4),("long.",4)],
 [("By",2),("the",3),("23rd,",12)],
 [("just",4),("20%.",8)],
 [("Buying",6),("shares",6),("with",4),("one",3),("hand.",4)],
 [("Hedging",7),("with",4),("the",3),("other.",5)],
 [("They",4),("want",4),("India.",6)],
 [("They're",6),("just",4),("insuring",8),("against",7),("a",1),("fall",4),("while",5),("Wall",4),("Street's",8),("AI",4),("selloff",7),("plays",5),("out.",3)],
 [("Next",4),("tests:",5)],
 [("GDP",6),("on",2),("the",3),("30th,",9),("the",3),("RBI",6),("on",2),("Dec",8),("4,",6)],
 [("the",3),("Fed",3),("on",2),("the",3),("9th.",6)],
 [("We",2),("track",5),("this",4),("every",5),("day.",3)],
 [("Follow",6),("PulsEdge.",9)],
]
bounds = [0.0] + [v for g in gaps for v in g] + [total]
chunks = [(bounds[2 * i], bounds[2 * i + 1]) for i in range(len(gaps) + 1)]
assert len(chunks) == len(CH), (len(chunks), len(CH))
chunks[0] = (0.05, chunks[0][1])
# pauses kept (1-based gap index): a beat before the twist, after "just 20%" and before "Next tests"
KEEP = {4: 0.36, 9: 0.75, 13: 0.3}
pieces, segs, pos, cur = [], [], 0.0, 0.0
for i, (a, b) in enumerate(gaps):
    keep = KEEP.get(i + 1, 0.22 if (b - a) >= 0.3 else 0.13)
    keep = min(keep, b - a)
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
        words.append({"w": txt, "t": round(a2 + (b2 - a2) * acc / tot, 3), "e": round(a2 + (b2 - a2) * (acc + wi) / tot, 3), "c": ci})
        acc += wi
    lines.append({"a": round(a2, 3), "b": round(b2, 3)})
raw = out.replace(".wav", "-raw.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", raw], input=np.concatenate(pieces).tobytes(), check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", f"atempo={TEMPO},loudnorm=I=-14:TP=-1.5:LRA=11,adelay={int(LEAD_IN*1000)}|{int(LEAD_IN*1000)}", "-ar", "48000", "-ac", "1", out], check=True)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out], capture_output=True, text=True).stdout)
L = lambda i: lines[i]["a"]
first = lambda ci, w: next(x["t"] for x in words if x["c"] == ci and x["w"] == w)
cues = {"hook": 0.0, "streak": L(2) - 0.1, "ticks": L(3), "twist": L(4) - 0.1, "fut": L(5) - 0.1, "n1": first(6, "37%"), "n2": L(8),
        "hands": L(9) + 0.3, "h2": L(10), "why": L(11) - 0.1, "ws": first(12, "Wall"), "next": L(13) - 0.1, "d1": first(14, "GDP"),
        "d2": first(14, "RBI"), "d3": first(15, "Fed"), "cta": L(16) - 0.1, "follow": L(17)}
json.dump({"cues": {k: round(v, 3) for k, v in cues.items()}, "words": words, "lines": lines, "audio": round(dur, 3), "end": round(dur + 1.3, 2)}, open(tout, "w"), indent=0)
print(json.dumps({"orig": round(total, 2), "new": round(dur, 2), "end": round(dur + 1.3, 2), "cues": {k: round(v, 2) for k, v in cues.items()}}))
