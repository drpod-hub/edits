#!/usr/bin/env python3
"""Vertical (1080x1920) viral cut of "VINICIN REAGE LULA REELEITO".

Layout: hook title on top, the stream (CNN + facecam) in the middle, a zoomed
facecam panel below it, and word-by-word captions on the seam. Silences are
jump-cut out, screams get a punch-in zoom + shake + white flash + bass hit,
section changes get a whoosh.

Usage:  python3 make_corte.py SOURCE.mp4 [OUT.mp4]
"""
import math
import os
import random
import re
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
SR = 48000
ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "..", "fonts")
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

YELLOW = (255, 230, 0)
WHITE = (255, 255, 255)
GREEN = (60, 235, 90)

# Layout
MAIN_Y = 452                      # stream panel (1080x608)
MAIN_H = 608
FACE_Y = MAIN_Y + MAIN_H + 26     # zoomed facecam panel
FACE_SRC = (164, 88, 256, 144)    # facecam box in the 256x144 source
FACE_H = int(W * (FACE_SRC[3] - FACE_SRC[1]) / (FACE_SRC[2] - FACE_SRC[0]))
CAP_Y = FACE_Y + 40               # caption centre line
RADIUS = 30

# --------------------------------------------------------------------------
# Edit decision list. s/e are source seconds. `text` is spread over the
# piece's voiced audio; `words` pins words to source times instead.
# fx: punch (zoom-in hit), shake, flash, boom (bass hit), whoosh (on entry)
# --------------------------------------------------------------------------
PIECES = [
    # HOOK: breaking news drops and he loses it
    dict(s=284.00, e=288.80, words=[("AAAAAAHHH!!", 284.60)],
         fx={"flash", "boom", "shake", "punch"}, emoji=("😂", 284.9)),

    # "minutos antes..." the rant
    dict(s=46.45, e=49.60, text="Eu nem sou petista, mano. Mas só de ver o Neymar...",
         fx={"whoosh"}, label="MINUTOS ANTES..."),
    dict(s=49.79, e=55.45, text="Esses moleque de direita que me segue, esses lerdão chorando... eu não sou petista, mano!"),
    dict(s=55.74, e=61.45, text="Eu sou de Nova Iguaçu, mano! Eu não sei nem que porra é essa, mano! Eu só quero ver o Neymar chorando, mano!"),
    dict(s=63.80, e=66.95, text="Eu não sou petista não, mano! Eu sou da favela, mano!", fx={"punch"}),
    dict(s=67.04, e=73.66, text="Eu quero ver vocês chorando! Eu não quero ganhar! Eu quero ver vocês perder, seus filha das putas! Eu não quero ganhar não!",
         emoji=("😭", 68.0)),
    dict(s=73.76, e=75.37, text="EU QUERO VER VOCÊS PERDER!", fx={"punch", "shake"}),
    dict(s=77.68, e=81.70, text="Tocando a bola errado! Se lesionando! Se fudendo! Pro hospital!",
         emoji=("🤣", 79.2)),
    dict(s=86.04, e=89.06, text="Vão mamar muito ainda, 4 anos mamando!", fx={"punch"}),
    dict(s=89.56, e=92.40, text="QUATRO ANOS MAMANDO!", fx={"shake"}),

    # the dare
    dict(s=159.19, e=162.31, text="Se tu falar Bolsonaro, tu vai meter o pé! A porra já vai estancar!",
         fx={"whoosh"}),
    dict(s=162.96, e=164.19, text="Fala Bolsonaro pra tu ver!"),
    dict(s=164.40, e=166.88, text="Fala Bolsonaro, fala pra tu ver, fala Bolsonaro!", fx={"punch"}),
    dict(s=168.37, e=169.54, text="Vai, fala aí, Bolsonaro!"),
    dict(s=172.60, e=173.98, text="Fala pra tu ver!", fx={"punch"}),
    dict(s=175.09, e=175.81, text="É Lula?"),
    dict(s=176.12, e=177.90, words=[("AÊÊÊÊÊÊ!!", 176.15)],
         fx={"flash", "boom", "shake", "punch"}, emoji=("🔥", 176.3)),

    # payoff: Lula is announced
    dict(s=487.00, e=491.40, words=[("LUIZ", 487.05), ("INÁCIO", 487.25), ("LULA...", 487.60),
                                    ("É LULA!!", 488.32), ("AAAAAAAAH!!", 489.10)],
         fx={"whoosh", "shake"}, flash_at=488.6, boom_at=488.6),
    dict(s=503.45, e=507.60, words=[("DEU", 503.48), ("NÓS,", 503.72), ("DEU", 504.0), ("NÓS,", 504.2),
                                    ("PORRA!", 504.58), ("VAMOS", 506.2), ("GANHAR,", 506.45), ("CARALHO!", 506.95)],
         fx={"punch", "shake"}, emoji=("🔥", 506.5)),
]

TITLE = [("QUANDO O ", WHITE), ("LULA", GREEN), (" GANHOU", WHITE)]
TITLE2 = [("O VINICIN FICOU ASSIM", YELLOW)]
CREDIT = "Cortes do Vinicin OFICIAL"

CENSOR = {"porra": "P*RRA", "putas": "P*TAS", "fudendo": "F*DENDO", "caralho": "C*RALHO"}


# --------------------------------------------------------------------------
def font(weight, size):
    return ImageFont.truetype(os.path.join(FONTS, f"Poppins-{weight}.ttf"), size)


def run(cmd, **kw):
    r = subprocess.run(cmd, stderr=subprocess.PIPE, **kw)
    if r.returncode:
        sys.exit("command failed: " + " ".join(cmd) + "\n" + r.stderr.decode()[-2000:])
    return r


def emoji_img(ch, size):
    f = ImageFont.truetype(EMOJI_FONT, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)


def stroke_text(runs, fnt, stroke=8, shadow=10):
    """[(text, rgb)] on one line with black outline + soft shadow."""
    pad = stroke + shadow * 2
    widths = [fnt.getlength(t) for t, _ in runs]
    asc, desc = fnt.getmetrics()
    img = Image.new("RGBA", (int(sum(widths)) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    x = pad
    for (t, _), w in zip(runs, widths):
        md.text((x, pad), t, font=fnt, fill=255, stroke_width=stroke, stroke_fill=255)
        x += w
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(mask.filter(ImageFilter.GaussianBlur(shadow)).point(lambda v: int(v * 0.8)))
    img.alpha_composite(sh, (0, 5))
    d = ImageDraw.Draw(img)
    x = pad
    for (t, col), w in zip(runs, widths):
        d.text((x, pad), t, font=fnt, fill=col, stroke_width=stroke, stroke_fill=(0, 0, 0))
        x += w
    return img


def round_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def ease_out(p):
    return 1 - (1 - p) ** 3


# --------------------------------------------------------------------------
# Timing: word alignment over voiced audio, output timeline
# --------------------------------------------------------------------------
def syllables(w):
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõà]+", w.lower()))) + 0.3


def align(piece, mono):
    """Return [(word, src_time)] for a piece."""
    if "words" in piece:
        return piece["words"]
    words = piece["text"].split()
    s, e = piece["s"], piece["e"]
    hop = 0.01
    seg = mono[int(s * SR):int(e * SR)]
    n = len(seg) // int(hop * SR)
    rms = np.array([np.sqrt((seg[i * int(hop * SR):(i + 1) * int(hop * SR)] ** 2).mean()) for i in range(n)])
    voiced = rms > 0.25 * np.percentile(rms, 90)
    cum = np.concatenate([[0], np.cumsum(voiced)])
    total = cum[-1]
    weights = np.array([syllables(w) for w in words])
    starts = np.concatenate([[0], np.cumsum(weights)[:-1]]) / weights.sum() * total
    out = []
    for w, v in zip(words, starts):
        idx = int(np.searchsorted(cum, v + 0.5))
        out.append((w, s + max(0, idx - 1) * hop))
    return out


def build_timeline(mono):
    t = 0.0
    for p in PIECES:
        p["frames"] = int(round((p["e"] - p["s"]) * FPS))
        p["t0"] = t
        p["dur"] = p["frames"] / FPS
        t += p["dur"]
        p["fx"] = p.get("fx", set())
    words = []
    for p in PIECES:
        for w, st in align(p, mono):
            words.append((w, p["t0"] + st - p["s"], p))
    return t, words


def caption_chunks(words, total):
    chunks, cur = [], []
    for i, (w, t, p) in enumerate(words):
        cur.append((w, t))
        nxt = words[i + 1] if i + 1 < len(words) else None
        chars = sum(len(x) for x, _ in cur)
        brk = (nxt is None or len(cur) >= 3 or chars >= 13 or w[-1] in ".!?,"
               or nxt[2] is not p or (nxt[1] - t) > 0.9)
        if brk:
            chunks.append(cur)
            cur = []
    out = []
    for i, c in enumerate(chunks):
        end = chunks[i + 1][0][1] if i + 1 < len(chunks) else total
        end = min(end, c[-1][1] + 1.2)
        out.append((c[0][1], end, c))
    return out


def clean(w):
    base = re.sub(r"[^\wÀ-ÿ*]", "", w.lower())
    up = w.upper()
    if base in CENSOR:
        up = up.replace(base.upper(), CENSOR[base])
    return up


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------
def synth_boom(dur=0.9):
    t = np.arange(int(dur * SR)) / SR
    f = 40 + 90 * np.exp(-t * 9)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t * 4.5)
    x += 0.25 * np.random.default_rng(1).standard_normal(len(t)) * np.exp(-t * 40)
    return np.tanh(1.6 * x) * 0.9


def synth_whoosh(dur=0.45):
    n = int(dur * SR)
    noise = np.random.default_rng(2).standard_normal(n)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    spec *= np.exp(-((np.log(freqs + 1) - np.log(1800)) ** 2) / 1.2)
    x = np.fft.irfft(spec, n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    x = x * env
    return x / np.abs(x).max() * 0.55


def build_audio(src, total, tmp):
    wav = os.path.join(tmp, "src.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "2", "-ar", str(SR), wav])
    a, _ = sf.read(wav, dtype="float32")
    out = np.zeros((int(math.ceil(total * SR)) + SR, 2), dtype=np.float32)
    fade = int(0.008 * SR)
    for p in PIECES:
        seg = a[int(p["s"] * SR):int(p["s"] * SR) + int(p["dur"] * SR)].copy()
        seg[:fade] *= np.linspace(0, 1, fade)[:, None]
        seg[-fade:] *= np.linspace(1, 0, fade)[:, None]
        i = int(p["t0"] * SR)
        out[i:i + len(seg)] += seg
    peak = np.abs(out).max() or 1
    out *= 0.85 / peak
    boom, whoosh = synth_boom(), synth_whoosh()

    def add(sfx, t, gain):
        i = max(0, int(t * SR))
        j = min(len(out), i + len(sfx))
        out[i:j] += (sfx[:j - i] * gain)[:, None]

    for p in PIECES:
        if "boom" in p["fx"]:
            add(boom, p["t0"], 0.55)
        if "boom_at" in p:
            add(boom, p["t0"] + p["boom_at"] - p["s"], 0.55)
        if "whoosh" in p["fx"]:
            add(whoosh, p["t0"] - 0.22, 0.45)
    out = out[:int(total * SR)]
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    path = os.path.join(tmp, "mix.wav")
    sf.write(path, out, SR)
    return path


# --------------------------------------------------------------------------
# Video
# --------------------------------------------------------------------------
def piece_frames(src, p):
    r = run(["ffmpeg", "-v", "error", "-ss", f"{p['s']:.3f}", "-i", src, "-t", f"{p['dur'] + 0.2:.3f}",
             "-vf", f"fps={FPS},scale=256:144", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
    buf = np.frombuffer(r.stdout, np.uint8)
    n = len(buf) // (256 * 144 * 3)
    frames = buf[:n * 256 * 144 * 3].reshape(n, 144, 256, 3)
    out = [frames[min(i, n - 1)] for i in range(p["frames"])]
    return out


class Renderer:
    def __init__(self, total, chunks):
        self.total = total
        self.chunks = chunks
        self.main_mask = round_mask((W - 40, MAIN_H - 22), RADIUS)
        self.face_mask = round_mask((W - 40, FACE_H), RADIUS)
        self.cap_font = font("ExtraBold", 92)
        self.emojis = {}
        self.cap_cache = {}

        # static top layer: title + credit
        top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        t1 = stroke_text(TITLE, font("ExtraBold", 74), stroke=7)
        top.alpha_composite(t1, ((W - t1.width) // 2, 198))
        t2 = stroke_text(TITLE2, font("ExtraBold", 66), stroke=7)
        e = emoji_img("😂", 78)
        x = (W - t2.width - e.width) // 2
        top.alpha_composite(t2, (x, 292))
        top.alpha_composite(e, (x + t2.width - 4, 316))
        cr = stroke_text([(CREDIT, (220, 220, 220))], font("SemiBold", 34), stroke=3, shadow=6)
        top.alpha_composite(cr, ((W - cr.width) // 2, FACE_Y + FACE_H + 40))
        self.top = top

    def emoji(self, ch):
        if ch not in self.emojis:
            self.emojis[ch] = emoji_img(ch, 190)
        return self.emojis[ch]

    def caption(self, chunk, active):
        key = (id(chunk), active)
        if key not in self.cap_cache:
            runs = []
            for i, (w, _) in enumerate(chunk):
                runs.append(((" " if i else "") + clean(w), YELLOW if i == active else WHITE))
            f = self.cap_font
            while sum(f.getlength(t) for t, _ in runs) > W - 90 and f.size > 50:
                f = font("ExtraBold", f.size - 4)
            self.cap_cache[key] = stroke_text(runs, f, stroke=9, shadow=12)
        return self.cap_cache[key]

    def frame(self, src, p, k, t):
        lt = k / FPS                      # time inside piece
        st = p["s"] + lt                  # source time
        im = Image.fromarray(src)

        # punch zoom + shake
        zoom = 1.0 + (0.06 if PIECES.index(p) % 2 else 0.0)   # alternate framing per cut
        if "punch" in p["fx"]:
            zoom += 0.16 * (1 - ease_out(min(1, lt / 0.35)))
        dx = dy = 0
        shake = 0.0
        if "shake" in p["fx"]:
            shake = 16 * max(0.25, 1 - lt / max(p["dur"], 0.01))
        if "flash_at" in p and st >= p["flash_at"]:
            shake = max(shake, 22 * max(0, 1 - (st - p["flash_at"]) / 1.5))
        if shake:
            rnd = random.Random(int(t * FPS))
            dx, dy = rnd.uniform(-shake, shake), rnd.uniform(-shake, shake)

        # background: blurred, darkened stream
        bg = im.crop((88, 0, 168, 144)).resize((135, 240), Image.BILINEAR)
        bg = bg.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR)
        bg = Image.eval(bg, lambda v: int(v * 0.38)).convert("RGBA")

        # main stream panel
        mw, mh = W - 40, MAIN_H - 22
        main = im.resize((mw, mh), Image.BICUBIC).filter(ImageFilter.UnsharpMask(2, 70, 2))
        bg.paste(main, (20 + int(dx * 0.5), MAIN_Y + 11 + int(dy * 0.5)), self.main_mask)

        # zoomed facecam panel
        x0, y0, x1, y1 = FACE_SRC
        cw, ch = (x1 - x0) / zoom, (y1 - y0) / zoom
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.06 * (zoom - 1) * 4
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        face = im.resize((256 * 4, 144 * 4), Image.BICUBIC)
        face = face.crop(tuple(int(v * 4) for v in box)).resize((W - 40, FACE_H), Image.BICUBIC)
        face = face.filter(ImageFilter.UnsharpMask(3, 60, 2))
        bg.paste(face, (20 + int(dx), FACE_Y + int(dy)), self.face_mask)
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([20 + int(dx), FACE_Y + int(dy), W - 21 + int(dx), FACE_Y + FACE_H + int(dy)],
                            RADIUS, outline=(255, 255, 255), width=5)

        bg.alpha_composite(self.top)

        # section label
        if "label" in p and lt < 1.6:
            a = min(1, lt / 0.15, (1.6 - lt) / 0.25)
            lab = stroke_text([(p["label"], YELLOW)], font("ExtraBold", 70), stroke=7)
            pill = Image.new("RGBA", (lab.width + 20, lab.height), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([20, 18, pill.width - 20, pill.height - 18], 30, fill=(0, 0, 0, 170))
            pill.alpha_composite(lab, (10, 0))
            pill.putalpha(pill.getchannel("A").point(lambda v: int(v * a)))
            bg.alpha_composite(pill, ((W - pill.width) // 2, MAIN_Y + MAIN_H // 2 - pill.height // 2))

        # emoji pop
        if "emoji" in p:
            ch, et = p["emoji"]
            el = st - et
            if 0 <= el < 1.4:
                e = self.emoji(ch)
                sc = (0.4 + 0.75 * ease_out(min(1, el / 0.25))) * (1 + 0.05 * math.sin(el * 12))
                e2 = e.resize((int(e.width * sc), int(e.height * sc)), Image.BICUBIC).rotate(
                    -12 + 8 * math.sin(el * 6), Image.BICUBIC, expand=True)
                if el > 1.1:
                    e2.putalpha(e2.getchannel("A").point(lambda v: int(v * (1.4 - el) / 0.3)))
                bg.alpha_composite(e2, (W - e2.width - 40, FACE_Y + FACE_H - e2.height - 30))

        # captions
        for c0, c1, chunk in self.chunks:
            if c0 <= t < c1:
                active = max(i for i, (_, wt) in enumerate(chunk) if wt <= t + 1e-6) if chunk[0][1] <= t else 0
                cap = self.caption(chunk, active)
                pop = 1 + 0.22 * (1 - ease_out(min(1, (t - c0) / 0.12)))
                if pop != 1:
                    cap = cap.resize((int(cap.width * pop), int(cap.height * pop)), Image.BICUBIC)
                bg.alpha_composite(cap, ((W - cap.width) // 2, CAP_Y - cap.height // 2))
                break

        # flash
        fl = None
        if "flash" in p["fx"] and lt < 0.2:
            fl = 1 - lt / 0.2
        if "flash_at" in p and 0 <= st - p["flash_at"] < 0.2:
            fl = 1 - (st - p["flash_at"]) / 0.2
        if fl:
            bg = Image.blend(bg, Image.new("RGBA", (W, H), (255, 255, 255, 255)), 0.85 * fl)

        # progress bar
        d = ImageDraw.Draw(bg)
        d.rectangle([0, H - 14, W, H], fill=(0, 0, 0, 255))
        d.rectangle([0, H - 14, int(W * t / self.total), H], fill=YELLOW)
        return bg.convert("RGB")


# --------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "..", "output", "vinicin_lula_corte.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="corte_") as tmp:
        mono_path = os.path.join(tmp, "mono.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", str(SR), mono_path])
        mono, _ = sf.read(mono_path, dtype="float32")

        total, words = build_timeline(mono)
        chunks = caption_chunks(words, total)
        print(f"{len(PIECES)} cuts, {total:.1f}s, {len(chunks)} caption chunks")

        print("Mixing audio…")
        mix = build_audio(src, total, tmp)

        print("Rendering video…")
        r = Renderer(total, chunks)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-i", mix,
             "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        n = 0
        for p in PIECES:
            for k, fr in enumerate(piece_frames(src, p)):
                enc.stdin.write(r.frame(fr, p, k, p["t0"] + k / FPS).tobytes())
                n += 1
            print(f"  {p['t0'] + p['dur']:5.1f}s / {total:.1f}s")
        enc.stdin.close()
        if enc.wait():
            sys.exit("encode failed")
    print("Done ->", out)


if __name__ == "__main__":
    main()
