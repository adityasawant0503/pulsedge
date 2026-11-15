#!/usr/bin/env python3
"""Add the AI voice-over to the intro video.

    python pulsedge-bot/intro/voice.py --model kokoro-v1.0.onnx --voices voices-v1.0.bin

Reads narration.json, speaks each line with Kokoro (an open-weight text-to-speech model, Apache-2.0, free for
commercial use) through kokoro-onnx, places every line at its start time, speeding a line up slightly when it would
run past its scene, then mixes the track (loudness-normalised) into pulsedge/assets/intro.mp4 and intro.webm.
The picture is copied, not re-encoded. Runs in GitHub Actions (.github/workflows/pulsedge-intro-voice.yml).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "..", "pulsedge", "assets")
MAX_SPEED = 1.25  # faster than this starts to sound rushed


def say(tts, text, voice, speed):
    samples, rate = tts.create(text, voice=voice, speed=speed, lang="en-us")
    return np.asarray(samples, dtype=np.float32), rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--voices", required=True)
    ap.add_argument("--script", default=os.path.join(HERE, "narration.json"))
    ap.add_argument("--duration", type=float, default=54.0)
    ap.add_argument("--wav", default=os.path.join(tempfile.gettempdir(), "intro-voice.wav"))
    a = ap.parse_args()

    script = json.load(open(a.script, encoding="utf-8"))
    tts = Kokoro(a.model, a.voices)
    voice, base = script.get("voice", "af_heart"), float(script.get("speed", 1.0))
    if voice not in tts.get_voices():
        sys.exit(f"voice {voice} not available; try one of: {', '.join(tts.get_voices())}")

    rate, track, report = None, None, []
    for line in script["lines"]:
        room = line["by"] - line["at"]
        speed = base
        audio, rate = say(tts, line["text"], voice, speed)
        if len(audio) / rate > room:
            speed = min(MAX_SPEED, base * (len(audio) / rate) / room * 1.03)
            audio, rate = say(tts, line["text"], voice, speed)
        if track is None:
            track = np.zeros(int(a.duration * rate), dtype=np.float32)
        start = int(line["at"] * rate)
        end = min(len(track), start + len(audio))
        track[start:end] += audio[: end - start]
        took = len(audio) / rate
        report.append(f'{line["at"]:5.1f}s  {took:4.1f}s of {room:4.1f}s  x{speed:.2f}  {"OVERRUNS " if took > room else ""}{line["text"]}')

    print("\n".join(report))
    if any("OVERRUNS" in r for r in report):
        print("warning: some lines still run past their scene; shorten them in narration.json", file=sys.stderr)

    peak = float(np.max(np.abs(track))) or 1.0
    pcm = (np.clip(track / peak * 0.89, -1, 1) * 32767).astype(np.int16)
    with wave.open(a.wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())

    # speech loudness for web video: about -16 LUFS, peaks under -1.5 dBTP; stereo so every player centres it
    af = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,pan=stereo|c0=c0|c1=c0"
    for name, codec in (("intro.mp4", ["-c:a", "aac", "-b:a", "128k"]), ("intro.webm", ["-c:a", "libopus", "-b:a", "96k"])):
        src = os.path.join(ASSETS, name)
        tmp = src + ".tmp" + os.path.splitext(name)[1]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", a.wav, "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-af", af, *codec, "-shortest", "-movflags", "+faststart", tmp], check=True)
        os.replace(tmp, src)
        print("voiced", name)


if __name__ == "__main__":
    main()
