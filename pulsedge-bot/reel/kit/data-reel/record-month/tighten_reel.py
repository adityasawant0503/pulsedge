# Tighten the "not 2021" voiceover, then time every caption word.
# usage: python3 -I tools/tighten_reel.py in.mp3 audio/vo-tight.wav timing.json  (edit CH and the cues for a new script)
import json, re, subprocess, sys
import numpy as np
src, out, tout = sys.argv[1:4]
SR, TEMPO, LEAD_IN = 44100, 1.12, 0.15
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
x = np.frombuffer(pcm, dtype=np.float32)
log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "silencedetect=noise=-38dB:d=0.15", "-f", "null", "-"], capture_output=True, text=True).stderr
gaps = [(float(a), float(b)) for a, b in zip(re.findall(r"silence_start: ([\d.]+)", log), re.findall(r"silence_end: ([\d.]+)", log))]
total = len(x) / SR
if gaps and gaps[-1][1] > total - 0.1:          # trailing silence: trim it, it is not a pause between lines
    total = gaps[-1][0] + 0.06; x = x[:int(total * SR)]; gaps = gaps[:-1]
# speech chunks between the pauses, each with its caption tokens: (shown text, spoken weight)
CH = [
 [("Foreign",7),("investors",9),("just",4),("bought",6),("₹1.38",14),("lakh",4),("crore",5),("of",2),("Indian",6),("shares",6),("this",4),("month.",5)],
 [("A",1),("record.",6)],
 [("In",2),("the",3),("first",5),("two",3),("weeks,",5),("half",4),("of",2),("it",2),("went",4),("into",4),("one",3),("sector:",6)],
 [("banks",5),("and",3),("finance.",7)],
 [("₹43,000",16),("crore.",5)],
 [("Telecom,",7),("IT",4),("and",3),("consumer",8),("stocks",6),("got",3),("money",5),("too.",3)],
 [("Capital",7),("goods?",5)],
 [("That's",5),("what",4),("they",4),("sold",4),("most.",4)],
 [("Want",4),("to",2),("catch",5),("moves",5),("like",4),("this",4),("early?",5)],
 [("Here's",5),("a",1),("2-minute",8),("routine.",7)],
]
bounds = [0.0] + [v for g in gaps for v in g] + [total]
chunks = [(bounds[2 * i], bounds[2 * i + 1]) for i in range(len(gaps) + 1)]
assert len(chunks) == len(CH), (len(chunks), len(CH))
chunks[0] = (0.05, chunks[0][1])
# pauses kept (1-based gap index): a beat after "not 2021", after "Now?", before the catch and before "Prices"
KEEP = {1: 0.2, 2: 0.2, 6: 0.3, 8: 0.36}
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
cues = {"hook": 0.0, "rec": L(1), "half": L(2) - 0.1, "one": first(2, "one"), "bank": L(3), "n43": L(4), "bars": L(5) - 0.1,
        "b2": first(5, "Telecom,"), "b3": first(5, "IT"), "b4": first(5, "consumer"), "cg": L(6), "sold": first(7, "sold"), "next": L(8) - 0.1, "routine": L(9)}
json.dump({"cues": {k: round(v, 3) for k, v in cues.items()}, "words": words, "lines": lines, "audio": round(dur, 3), "end": round(dur + 0.35, 2)}, open(tout, "w"), indent=0)
print(json.dumps({"orig": round(total, 2), "new": round(dur, 2), "end": round(dur + 0.35, 2), "cues": {k: round(v, 2) for k, v in cues.items()}}))
