# Tighten the "not 2021" voiceover, then time every caption word.
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
 [("The",3),("Nifty",5),("just",4),("had",3),("its",3),("best",4),("week",4),("since",5),("2021.",14)],
 [("But",3),("this",4),("is",2),("NOT",4),("2021.",14)],
 [("Back",4),("then,",4),("the",3),("RBI's",9),("rate",4),("was",3),("at",2),("a",1),("record",6),("low.",4)],
 [("Now,",4)],
 [("most",4),("economists",10),("expect",6),("a",1),("hike.",4)],
 [("US",4),("10-year",9),("bonds",5),("paid",4),("just",4),("over",4),("1%.",9)],
 [("Now?",4)],
 [("Over",4),("5%.",8)],
 [("Inflation",9),("was",3),("4.6%.",16)],
 [("Now,",4)],
 [("6.1%.",12)],
 [("And",3),("the",3),("foreign",6),("money",5),("behind",5),("this",4),("rally?",6)],
 [("Only",4),("about",4),("a",1),("quarter",6),("of",2),("this",4),("year's",5),("selling",6),("has",3),("come",4),("back.",4)],
 [("Prices,",7),("rates,",6),("and",3),("rain",4),("decide",6),("what's",5),("next.",5)],
 [("Full",4),("breakdown",9),("in",2),("our",3),("latest",6),("post.",5)],
 [("Follow",6),("PulsEdge.",9)],
]
bounds = [0.0] + [v for g in gaps for v in g] + [total]
chunks = [(bounds[2 * i], bounds[2 * i + 1]) for i in range(len(gaps) + 1)]
assert len(chunks) == len(CH), (len(chunks), len(CH))
chunks[0] = (0.05, chunks[0][1])
# pauses kept (1-based gap index): a beat after "not 2021", after "Now?", before the catch and before "Prices"
KEEP = {2: 0.42, 7: 0.24, 11: 0.3, 13: 0.34}
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
cues = {"hook": 0.0, "notyet": L(1) - 0.1, "board": L(2) - 0.1, "now1": L(3), "n1": L(4), "r2": L(5), "n2": L(7), "r3": L(8), "n3": L(10),
        "catch": L(11) - 0.1, "fill": L(12), "next": L(13) - 0.1, "w1": first(13, "Prices,"), "w2": first(13, "rates,"), "w3": first(13, "rain"),
        "cta": L(14) - 0.1, "follow": L(15)}
json.dump({"cues": {k: round(v, 3) for k, v in cues.items()}, "words": words, "lines": lines, "audio": round(dur, 3), "end": round(dur + 1.3, 2)}, open(tout, "w"), indent=0)
print(json.dumps({"orig": round(total, 2), "new": round(dur, 2), "end": round(dur + 1.3, 2), "cues": {k: round(v, 2) for k, v in cues.items()}}))
