import json, sys, numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
M = sys.argv[1]; out = sys.argv[2]; voice = sys.argv[3]; speed = float(sys.argv[4])
k = Kokoro(M + "/kokoro-v1.0.onnx", M + "/voices-v1.0.bin")
LINES = [
 ["Voltas lost over a thousand crore in one morning.", "The reason was public seventeen hours earlier."],
 ["Three fifty-nine p.m.", "Market closed.", "One page went up on the exchange."],
 ["Most people never opened it.", "Urban Company,", "the app that repairs your AC,", "would now sell its own."],
 ["The price wasn't the threat.", "The warranty was.", "Five years. Free gas refills."],
 ["Next morning.", "Voltas, down three percent.", "Blue Star, two.", "Havells, too."],
 ["Every big move leaves a page like this.", "Most people never read it."],
]
SR = None; parts = []; timing = []; pos = 0.1; GIN, GOUT = 0.16, 0.34
def trim(x, sr, thr=0.012):
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx): return x
    a = max(0, idx[0] - int(0.02 * sr)); b = min(len(x), idx[-1] + int(0.06 * sr)); return x[a:b]
for li, line in enumerate(LINES):
    chunks = []; start = pos
    for pi, ph in enumerate(line):
        a, sr = k.create(ph, voice=voice, speed=speed, lang="en-us"); SR = sr
        a = trim(np.asarray(a, dtype=np.float32), sr)
        chunks.append(round(pos, 3)); parts.append((pos, a)); pos += len(a) / sr
        if pi < len(line) - 1: pos += GIN
    timing.append({"start": round(start, 3), "end": round(pos, 3), "chunks": chunks}); pos += GOUT
total = pos
y = np.zeros(int((total + 0.1) * SR), dtype=np.float32)
for p, a in parts:
    i = int(p * SR); y[i:i + len(a)] += a
sf.write(out, y, SR)
json.dump({"lines": timing, "audio": round(total, 3), "end": round(total + 1.3, 2)}, open(out.replace(".wav", "-timing.json"), "w"), indent=1)
for tl in timing: print(tl)
print("total", round(total, 2))
