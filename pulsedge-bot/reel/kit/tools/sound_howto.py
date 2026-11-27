# Light beat + UI sounds for one guide episode, ducked under the voice, mixed to -14 LUFS.
# usage: python3 -I tools/sound_howto.py timing-ep<N>.json vo.wav audio/ep<N>-mix.wav
import json, subprocess, sys
import numpy as np
tj, vo_path, out = sys.argv[1:4]
T = json.load(open(tj)); C = T["cues"]; END = T["end"]; EP = T["ep"]; SR = 48000
N = int(END * SR); rng = np.random.default_rng(20 + EP)
vo = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", vo_path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout, dtype=np.float32)
vo = np.pad(vo, (0, max(0, N - len(vo))))[:N].astype(np.float64)
def band(x, lo, hi):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); X[(f < lo) | (f > hi)] = 0; return np.fft.irfft(X, len(x))
def add(buf, sig, t0, g=1.0):
    i = int(t0 * SR)
    if i < 0: sig, i = sig[-i:], 0
    j = min(N, i + len(sig)); buf[i:j] += g * sig[:j - i]
tt = lambda d: np.arange(int(d * SR)) / SR
music, sfx = np.zeros(N), np.zeros(N)
BEAT = 60 / 112
def kick():
    t = tt(0.35); ph = 2 * np.pi * (48 * t + 100 * 0.03 * (1 - np.exp(-t / 0.03))); return np.sin(ph) * np.exp(-t / 0.18)
def hat():
    t = tt(0.05); return band(rng.standard_normal(len(t)), 7000, 15000) * np.exp(-t / 0.015)
K, H = kick(), hat()
for b in range(int(END / BEAT) + 1):
    t0 = b * BEAT
    if t0 >= END - 0.8: continue
    if b % 2 == 0: add(music, K, t0, 0.7)
    add(music, H, t0 + BEAT / 2, 0.16)
t = np.arange(N) / SR
chords = [[261.63, 329.63, 392.0], [220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 246.94, 293.66]]   # C Am F G
bar = 4 * BEAT; idx = (t // bar).astype(int) % 4
pad = np.zeros(N)
for ci, ch in enumerate(chords):
    m = idx == ci
    for f in ch: pad[m] += np.sin(2 * np.pi * f * t[m])
pad *= 0.045 * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * t))
music += pad
music *= np.clip((END - t) / 1.0, 0, 1) * np.clip(t / 0.3, 0, 1)
def whoosh(d=0.35):
    tq = tt(d); return band(rng.standard_normal(len(tq)), 400, 6000) * np.sin(np.pi * tq / d) ** 2
def click():
    tq = tt(0.05); return band(rng.standard_normal(len(tq)), 1500, 8000) * np.exp(-tq / 0.006) + 0.6 * np.sin(2 * np.pi * 1800 * tq) * np.exp(-tq / 0.01)
def blip(f=1320):
    tq = tt(0.12); return np.sin(2 * np.pi * f * tq) * np.exp(-tq / 0.03)
def chime():
    tq = tt(1.2); return sum(np.sin(2 * np.pi * f * tq) * np.exp(-tq / 0.5) for f in (523.25, 659.25, 783.99)) / 3
EV = {1: (["tap1", "tap2", "top"], ["tap1", "tap2"], ["cta", "mkt", "left", "five", "card"]),
      2: (["act", "story", "tabs", "money", "pm"], [], ["label", "act", "watch", "ignore", "plain", "why", "check", "panel"]),
      3: (["brief", "mine", "ask", "answer"], ["pick", "tapadd", "tapfab", "chip"], ["search", "add", "mine"]),
      4: (["open", "own", "money", "stuck", "answer"], ["tapideas", "tapask"], ["nifty", "us", "asia", "fx", "brent", "vix", "mine"]),
      5: (["open", "money", "own", "stuck", "answer"], ["tapideas", "tapask"], ["panel", "deal", "mine"])}[EP]
for k in EV[0]: add(sfx, whoosh(), C[k] + (0.15 if k.startswith("tap") else -0.15), 0.25)
for k in EV[1]: add(sfx, click(), C[k], 0.5)
for k in EV[2]: add(sfx, blip(1320 if EP != 2 else 1100), C[k], 0.14)
add(sfx, chime(), C["end"], 0.22)
w = int(0.03 * SR); e = np.sqrt(np.convolve(vo ** 2, np.ones(w) / w, "same"))
speak = np.clip(e / 0.02, 0, 1); k = int(0.15 * SR); speak = np.convolve(speak, np.ones(k) / k, "same")
duck = 1 - 0.6 * np.clip(speak, 0, 1)
mix = vo + 0.28 * music * duck + 0.35 * sfx
mix /= max(1e-9, np.abs(mix).max()) / 0.9
raw = out.replace(".wav", "-raw.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-", raw], input=mix.astype(np.float64).tobytes(), check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", out], check=True)
print("ok ep", EP, round(len(mix) / SR, 2), "s")
