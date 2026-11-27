# Beat + sound effects for the "not 2021" reel, ducked under the voice, mixed to -14 LUFS.
# usage: python3 -I tools/sound_reel.py timing.json audio/vo-tight.wav audio/mix.wav
import json, subprocess, sys
import numpy as np
tj, vo_path, out = sys.argv[1:4]
T = json.load(open(tj)); C = T["cues"]; END = T["end"]; SR = 48000
N = int(END * SR); rng = np.random.default_rng(11)
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
BEAT = 0.5; turn = C["cg"]; drop_a = turn - 0.9; lift = C["next"]
def kick():
    t = tt(0.4); ph = 2 * np.pi * (45 * t + 110 * 0.03 * (1 - np.exp(-t / 0.03))); return np.sin(ph) * np.exp(-t / 0.22)
def hat():
    t = tt(0.06); return band(rng.standard_normal(len(t)), 7000, 16000) * np.exp(-t / 0.018)
def clap():
    t = tt(0.25); env = sum(np.exp(-np.clip(t - o, 0, None) / 0.012) * (t >= o) for o in (0, 0.012, 0.024)) + 0.6 * np.exp(-t / 0.09)
    return band(rng.standard_normal(len(t)), 900, 3500) * env
K, H, CL = kick(), hat(), clap()
for b in range(int(END / BEAT) + 1):
    t0 = b * BEAT
    if drop_a <= t0 < turn or t0 >= END - 1.0: continue          # drums drop out for the build, and at the very end
    add(music, K, t0, 0.9); add(music, H, t0 + BEAT / 2, 0.22)
    if b % 2 == 1: add(music, CL, t0, 0.35)
# pad: C major for the rally, A minor from "this is not 2021", back to C major for the call to action
t = np.arange(N) / SR
major, minor = [261.63, 329.63, 392.0], [220.0, 261.63, 329.63]
inmin = (t >= turn) & (t < lift)
pad = np.zeros(N)
for f in major: pad += np.where(~inmin, np.sin(2 * np.pi * f * t), 0)
for f in minor: pad += np.where(inmin, np.sin(2 * np.pi * f * t), 0)
pad *= 0.05 * (0.75 + 0.25 * np.sin(2 * np.pi * 0.5 * t))
root = np.where(inmin, 55.0, 65.41)
pump = 1 - 0.8 * np.exp(-((t % BEAT) / 0.12))
sub = 0.32 * np.sin(2 * np.pi * root * t) * pump * ~((t >= drop_a) & (t < turn))
music += pad + sub
music *= np.clip((END - t) / 1.2, 0, 1) * np.clip(t / 0.05, 0, 1)
def impact(d=1.4, g=1.0):
    t = tt(d); return g * (np.sin(2 * np.pi * (40 * t + 60 * 0.05 * (1 - np.exp(-t / 0.05)))) * np.exp(-t / 0.45) + 0.5 * band(rng.standard_normal(len(t)), 40, 2500) * np.exp(-t / 0.12))
def riser(d=0.9):
    t = tt(d); r = t / d; ph = 2 * np.pi * np.cumsum(300 * (5 ** r)) / SR
    return (0.35 * np.sin(ph) + 0.6 * band(rng.standard_normal(len(t)), 1500, 9000)) * r ** 2
def whoosh(d=0.4):
    t = tt(d); return band(rng.standard_normal(len(t)), 300, 5000) * np.sin(np.pi * t / d) ** 2
def blip(f=1320):
    t = tt(0.12); return np.sin(2 * np.pi * f * t) * np.exp(-t / 0.03)
add(sfx, impact(1.2, 0.8), 0.0)
add(sfx, riser(), turn - 0.9, 0.55)
add(sfx, impact(1.6, 1.0), turn)
for k in ["half", "bars", "next"]: add(sfx, whoosh(), C[k] - 0.2, 0.32)
for k in ["rec", "n43"]: add(sfx, impact(0.5, 0.45), C[k]); add(sfx, blip(880), C[k], 0.18)
for k in ["b2", "b3", "b4", "routine"]: add(sfx, blip(), C[k], 0.18)
w = int(0.03 * SR); e = np.sqrt(np.convolve(vo ** 2, np.ones(w) / w, "same"))
speak = np.clip(e / 0.02, 0, 1); k = int(0.15 * SR); speak = np.convolve(speak, np.ones(k) / k, "same")
duck = 1 - 0.65 * np.clip(speak, 0, 1)
mix = vo + 0.30 * music * duck + 0.35 * sfx
mix /= max(1e-9, np.abs(mix).max()) / 0.9
raw = out.replace(".wav", "-raw.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-", raw], input=mix.astype(np.float64).tobytes(), check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", out], check=True)
print("ok", round(len(mix) / SR, 2), "s")
