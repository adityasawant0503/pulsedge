import json, sys, numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
M = sys.argv[1]; out = sys.argv[2]; voice = sys.argv[3]; speed = float(sys.argv[4])
k = Kokoro(M + "/kokoro-v1.0.onnx", M + "/voices-v1.0.bin")
LINES = [
 ["A fifty-five thousand rupee AC", "just wiped over a thousand crore off Voltas.", "In one morning."],
 ["It started the evening before.", "Three fifty-nine p.m.", "The market had closed,", "and a small filing came in."],
 ["The company that repairs your AC...", "now sells its own."],
 ["The real twist?", "A five-year warranty.", "Free gas refills.", "And AC brands earn from service too."],
 ["Next morning.", "Nine fifteen.", "Voltas, down three percent.", "Blue Star, down two.", "Havells, down too."],
 ["If you read that filing last evening...", "this was no surprise.", "So... which company is next?"],
]
SR = None; parts = []; timing = []; pos = 0.08; GIN, GOUT = 0.12, 0.26
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
