#!/usr/bin/env python3
"""Write trailer/build/Night Drive Kit.zip: a small synthesized drum kit laid out like a
downloaded sample pack (Kicks/, Snares/, Hats/, 808s/...), used for the kit-import scene."""
import io
import math
import os
import random
import struct
import wave
import zipfile

SR = 22050
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "Night Drive Kit.zip")


def wav(samples):
    b = io.BytesIO()
    f = wave.open(b, "wb")
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
    f.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 26000)))) for s in samples))
    f.close()
    return b.getvalue()


def kick():
    ph, out = 0, []
    for i in range(int(SR * .5)):
        t = i / SR
        ph += 2 * math.pi * (45 + 110 * math.exp(-t * 30)) / SR
        out.append(math.sin(ph) * math.exp(-t * 7))
    return out


def noise(d, k): return [random.uniform(-1, 1) * math.exp(-i / SR * k) for i in range(int(SR * d))]
def tone(f, d, k): return [math.sin(2 * math.pi * f * i / SR) * math.exp(-i / SR * k) for i in range(int(SR * d))]


def mix(a, b, gb=1):
    n = max(len(a), len(b))
    return [(a[i] if i < len(a) else 0) + gb * (b[i] if i < len(b) else 0) for i in range(n)]


KIT = {
    "Kicks/Kick Dusty.wav": kick(), "Snares/Snare Tape.wav": mix(noise(.3, 14), tone(190, .2, 25), .6),
    "Claps/Clap Room.wav": noise(.35, 12), "Rims/Rim Click.wav": tone(1700, .06, 80),
    "Hats/Closed Hat 01.wav": noise(.08, 60), "Hats/Open Hat 02.wav": noise(.45, 7),
    "Percs/Shaker Soft.wav": noise(.15, 30), "Percs/Cowbell Lo.wav": mix(tone(540, .4, 9), tone(800, .4, 9)),
    "Toms/Tom Low.wav": tone(95, .6, 6), "Toms/Tom Hi.wav": tone(170, .5, 7),
    "808s/808 Glide.wav": tone(55, 1.2, 2), "FX/Vox Chop.wav": tone(330, .4, 6),
    "Percs/Conga Slap.wav": tone(260, .3, 14), "Kicks/Kick Punch.wav": kick(),
}

if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with zipfile.ZipFile(OUT, "w") as z:
        for name, s in KIT.items():
            z.writestr("Night Drive Kit/" + name, wav(s))
    print(OUT)
