"""Adds the caption bar, the "3 hours later..." card and a synthesized
soundtrack to the rendered frames, then encodes the final 1080x1920 MP4.

    python3 compose.py frames/ output/hide_and_seek.mp4
"""

import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "fonts")
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

W, H, BAR = 1080, 1920, 260         # scene area is 1080x1400 between two black bars
FPS, END, CARD = 30, 960, (810, 840)
CAPTION = ["POV: Playing Hide and Seek", "With Friends"]
BUBBLES = [12, 46, 80, 128, 240, 302, 340, 462, 552, 655, 714, 744, 888]
MUSIC = [(0, 450), (630, 810)]      # cut the music for the "bro." / "HOW??" beat
SR = 44100


# ---------------------------------------------------------------- picture
def caption_layer():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, BAR), fill=(0, 0, 0, 255))
    d.rectangle((0, BAR + 1400, W, H), fill=(0, 0, 0, 255))
    font = ImageFont.truetype(os.path.join(FONTS, "Poppins-ExtraBold.ttf"), 54)
    skull = None
    if os.path.exists(EMOJI_FONT):
        ef = ImageFont.truetype(EMOJI_FONT, 109)
        skull = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
        ImageDraw.Draw(skull).text((70, 70), "\U0001F480", font=ef, embedded_color=True, anchor="mm")
        skull = skull.crop(skull.getbbox()).resize((52, 52), Image.LANCZOS)
    for i, line in enumerate(CAPTION):
        y = 150 + i * 68
        tw = d.textlength(line, font=font)
        extra = 64 if (skull and i == len(CAPTION) - 1) else 0
        x = (W - tw - extra) / 2
        d.text((x, y), line, font=font, fill="white", anchor="lm")
        if extra:
            img.alpha_composite(skull, (int(x + tw + 12), y - 27))
    return img


def card():
    img = Image.new("RGB", (W, 1400), (0, 0, 0))
    font = ImageFont.truetype(os.path.join(FONTS, "LilitaOne-Regular.ttf"), 120)
    ImageDraw.Draw(img).text((W / 2, 700), "3 hours later...", font=font, fill=(255, 214, 40),
                             anchor="mm", stroke_width=6, stroke_fill=(120, 60, 0))
    return img


# ---------------------------------------------------------------- sound
def t_(sec):
    return np.arange(int(sec * SR)) / SR


def env(n, attack=0.005, decay=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / attack) * np.exp(-t / decay)


def pluck(freq, sec, decay=0.25):
    t = t_(sec)
    tone = sum(np.sin(2 * np.pi * freq * k * t) / k ** 1.4 for k in range(1, 6))
    return tone * env(len(t), 0.004, decay)


def music(sec):
    bpm = 120
    beat = 60 / bpm
    out = np.zeros(int(sec * SR) + SR)
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]   # C G Am F
    mel = [72, 76, 79, 76, 74, 79, 74, 71, 72, 76, 72, 69, 69, 72, 77, 76]
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    n_beats = int(sec / beat)
    for b in range(n_beats):
        start = int(b * beat * SR)
        ch = chords[(b // 4) % 4]
        bass = pluck(hz(ch[0] - 24), beat * 0.95, 0.35) * 0.55
        out[start:start + len(bass)] += bass
        if b % 2 == 1:
            for m in ch:
                s = pluck(hz(m), beat, 0.18) * 0.12
                out[start:start + len(s)] += s
        for half in (0, 1):
            note = mel[(b * 2 + half) % 16]
            if (b * 2 + half) % 16 in (7, 15):
                continue
            s = pluck(hz(note), beat / 2, 0.12) * 0.22
            p = start + int(half * beat / 2 * SR)
            out[p:p + len(s)] += s
        hat = np.random.default_rng(b).standard_normal(int(0.03 * SR)) * env(int(0.03 * SR), 0.001, 0.01)
        p = start + int(beat / 2 * SR)
        out[p:p + len(hat)] += hat * 0.05
    return out[:int(sec * SR)]


def pop():
    t = t_(0.08)
    f = 700 + 1400 * t / t[-1]
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.002, 0.03) * 0.35


def noise_burst(sec, cutoff, decay, rng):
    n = int(sec * SR)
    x = rng.standard_normal(n)
    k = max(1, int(SR / cutoff))
    x = np.convolve(x, np.ones(k) / k, mode="same")      # crude low-pass
    return x * env(n, 0.03, decay)


def rustle(rng):
    x = noise_burst(0.5, 3000, 0.2, rng)
    t = t_(0.5)
    return x * (0.6 + 0.4 * np.sin(2 * np.pi * 18 * t)) * 0.8


def boom():
    t = t_(1.6)
    f = 70 * np.exp(-t * 1.5) + 38
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.003, 0.6)
    return np.tanh(x * 2.5) * 0.7


def zoom():
    t = t_(0.3)
    f = 250 + 1100 * (t / t[-1]) ** 2
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.minimum(1, (0.3 - t) * 20) * 0.25


def crickets(sec, rng):
    out = np.zeros(int(sec * SR))
    for freq, offset, gap in ((4600, 0.2, 0.85), (4100, 0.55, 1.1)):
        p = offset
        while p < sec - 0.2:
            for k in range(3):
                t = t_(0.022)
                c = np.sin(2 * np.pi * freq * t) * np.sin(np.pi * t / t[-1])
                i = int((p + k * 0.045) * SR)
                out[i:i + len(c)] += c * 0.07
            p += gap + rng.uniform(-0.1, 0.1)
    return out


def soundtrack(path):
    rng = np.random.default_rng(1)
    total = np.zeros(int(END / FPS * SR) + SR)

    def put(frame, clip):
        i = int(frame / FPS * SR)
        total[i:i + len(clip)] += clip[:len(total) - i]

    for f0, f1 in MUSIC:
        m = music((f1 - f0) / FPS)
        fade = int(0.15 * SR)
        m[-fade:] *= np.linspace(1, 0, fade)
        put(f0, m * 0.55)
    for f in BUBBLES:
        put(f, pop())
    for f in (10, 762):
        put(f, noise_burst(0.6, 1200, 0.25, rng) * 0.5)
    for f in (55, 214, 282, 634, 856):
        put(f, rustle(rng))
    put(462, boom())
    put(548, zoom())
    put(CARD[1], crickets((END - CARD[1]) / FPS, rng))

    total = total[:int(END / FPS * SR)]
    total = np.clip(total / max(1e-6, np.abs(total).max()) * 0.9, -1, 1)
    pcm = (total * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- encode
def main():
    frames_dir, out = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wav = os.path.splitext(out)[0] + ".wav"
    soundtrack(wav)

    overlay = caption_layer()
    card_img = card()
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
         out],
        stdin=subprocess.PIPE)
    last = None
    for f in range(END):
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        if CARD[0] <= f < CARD[1]:
            scene = card_img
        else:
            path = os.path.join(frames_dir, f"{f:04d}.png")
            scene = Image.open(path).convert("RGB").resize((W, 1400), Image.LANCZOS) \
                if os.path.exists(path) else last
            last = scene
        if scene is not None:
            canvas.paste(scene, (0, BAR))
        canvas.alpha_composite(overlay)
        ff.stdin.write(canvas.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    os.remove(wav)
    print("wrote", out)


if __name__ == "__main__":
    main()
