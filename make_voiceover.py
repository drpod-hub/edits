#!/usr/bin/env python3
"""Generate an AI narration for a make_story.py config with Kokoro TTS.

Each beat's caption (or its "vo" text, when the written caption doesn't read
well aloud, e.g. "1,270 km/h") is spoken starting at that beat. A line that
would overrun its beat is sped up (up to MAX_SPEED); the title beat speaks the
title. The result is written to the config's "voiceover" path, which
make_story.py mixes in (use --remux to swap it into an existing render fast).

Setup (once):
    pip install kokoro-onnx soundfile
    # model files from https://github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0)
    #   kokoro-v1.0.onnx, voices-v1.0.bin  -> put them in models/ (or set KOKORO_DIR)

Usage:  python3 make_voiceover.py story_earth_stops.json [--voice am_michael] [--speed 1.1]
"""
import json
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("KOKORO_DIR", os.path.join(ROOT, "models"))
LEAD = 0.15        # seconds after a beat starts before its line begins
TAIL = 0.25        # keep this much silence before the next beat
MAX_SPEED = 1.45


def spoken(beat, cfg):
    if "vo" in beat:
        return beat["vo"]
    if beat.get("title"):
        t = " ".join(cfg["title"]).replace("*", "").lower()  # all-caps can get spelled out
        return t[0].upper() + t[1:]
    return (beat.get("caption") or "").replace("*", "")


def main():
    args = sys.argv[1:]
    cfg_path = next(a for a in args if a.endswith(".json"))
    voice = args[args.index("--voice") + 1] if "--voice" in args else None
    speed = float(args[args.index("--speed") + 1]) if "--speed" in args else None
    with open(cfg_path) as f:
        cfg = json.load(f)
    voice = voice or cfg.get("vo_voice", "am_michael")
    speed = speed or cfg.get("vo_speed", 1.1)

    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"), os.path.join(MODEL_DIR, "voices-v1.0.bin"))

    beats = cfg["beats"]
    starts = np.concatenate([[0], np.cumsum([b["dur"] for b in beats])])
    sr = 24000
    track = np.zeros(int(starts[-1] * sr) + sr, np.float32)
    for i, b in enumerate(beats):
        text = spoken(b, cfg)
        if not text:
            continue
        room = b["dur"] - LEAD - TAIL
        s = speed
        audio, sr = k.create(text, voice=voice, speed=s, lang="en-us")
        if len(audio) / sr > room:  # re-speak faster rather than time-stretch
            s = min(MAX_SPEED, s * (len(audio) / sr) / room)
            audio, sr = k.create(text, voice=voice, speed=s, lang="en-us")
        took = len(audio) / sr
        flag = "  ** overruns beat, lengthen dur or shorten line" if took > b["dur"] - LEAD else ""
        print(f"[{starts[i]:5.1f}s] {took:4.1f}s/{b['dur']:.1f}s x{s:.2f}  {text}{flag}")
        i0 = int((starts[i] + LEAD) * sr)
        seg = audio[: len(track) - i0]
        track[i0:i0 + len(seg)] += seg

    track /= max(1e-6, np.abs(track).max()) / 0.9
    out = os.path.join(ROOT, cfg["voiceover"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pcm = (track * 32767).astype(np.int16).tobytes()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
                    "-af", "acompressor=threshold=-18dB:ratio=3:attack=5:release=120,"
                           "equalizer=f=180:t=q:w=1:g=2,equalizer=f=3500:t=q:w=1:g=2",
                    "-b:a", "192k", out], input=pcm, check=True)
    print("Voiceover ->", out)


if __name__ == "__main__":
    main()
