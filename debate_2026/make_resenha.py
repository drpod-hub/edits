#!/usr/bin/env python3
"""Vertical (1080x1920) "resenha" cut of BBC News Brasil's recap of the first
2026 presidential debate (Band) — the one Lula and Flávio Bolsonaro skipped.

Square speaker crop in the middle, speaker-coloured word-by-word captions,
nickname lower-thirds, "ENQUANTO ISSO..." labels, freeze-frame punchlines
with a record scratch, crickets over the empty podium, a zen filter for
Cury and a red "pistola" vignette for Renan.

Usage:  python3 make_resenha.py SOURCE.mp4 [OUT.mp4]
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
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 48000
SW, SH = 426, 240                       # source frame size
ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "..", "fonts")
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

WHITE, YELLOW, BLACK = (255, 255, 255), (255, 226, 0), (0, 0, 0)
SPEAKERS = {   # caption highlight colour, panel border colour
    "reporter": YELLOW,
    "renan": (255, 140, 0),
    "cury": (120, 235, 160),
    "caiado": (80, 200, 255),
    "lula": (255, 80, 80),
    "flavio": (255, 214, 40),
}

PANEL_Y, PANEL = 330, W                 # square video panel
CAP_Y = PANEL_Y + PANEL + 120           # caption centre line
RADIUS = 34

# --------------------------------------------------------------------------
# Edit decision list (source seconds). vs = take video from another time,
# cw/cx = crop width/centre in the 426x240 source (cw 240 = square, 426 = full
# width letterboxed), hold = freeze-frame punchline after the piece.
# --------------------------------------------------------------------------
PIECES = [
    dict(s=315.40, e=320.62, spk="renan", cx=255,
         text="O Flávio é fraco, o Flávio não é inteligente, o Flávio tem gravíssimos déficits cognitivos",
         fx={"punch", "rage"}, sfx=[("boom", 317.0)],
         hold=1.1, hold_text="VAMOS DO COMEÇO", hold_emoji="⏪"),

    dict(s=0.25, e=6.05, vs=93.0, spk="reporter", cw=426,
         text="O primeiro debate entre os candidatos à presidência foi o mais esvaziado desde 1989.",
         label=("DEBATE PRESIDENCIAL 2026", "🎤"), fx={"whoosh"}),
    dict(s=360.0, e=361.9, mute=True, cx=165, cw=300, label=("CADÊ OS FAVORITOS?", "🦗"),
         sfx=[("crickets", 360.0)], fx={"slowzoom"}),

    dict(s=56.10, e=59.46, spk="lula", cx=290, cw=300,
         text="Tem gente que acha que pode ser candidato por causa da internet.",
         label=("ENQUANTO ISSO...", "📺"), tag=("LULA", "dando entrevista na Record"), fx={"whoosh"}),
    dict(s=68.15, e=74.85, spk="flavio", cx=213,
         text="O meu adversário é quem está no poder. E está destruindo o Brasil. E você sabe muito bem de quem eu estou falando.",
         tag=("FLÁVIO BOLSONARO", "mandou um vídeo"), fx={"whoosh"},
         hold=0.8, hold_text="SABEMOS?", hold_emoji="🤔"),

    dict(s=92.54, e=95.27, spk="renan", cx=240,
         text="Esses dois criminosos, esses dois criminosos... não vieram ao debate!",
         tag=("RENAN SANTOS", "modo pistola ativado"), fx={"rage", "punch", "whoosh"}),
    dict(s=101.21, e=104.87, spk="renan", cx=235,
         text="Botando seus cachorros pra ficarem discutindo. Mas eles próprios são covardes!",
         fx={"rage"}, emoji=("🐕", 101.6)),
    dict(s=289.94, e=294.85, spk="renan", cx=213, cw=340,
         text="Dois fracassados, dois medrosos... Lula e Flávio Bolsonaro.",
         label=("ELE LEVOU FRALDA", "🍼"), fx={"whoosh"}, emoji=("👶", 293.3), sfx=[("pop", 293.3)]),

    dict(s=254.95, e=256.50, spk="cury", cw=426, text="Nós estamos numa democracia.",
         label=("ENQUANTO ISSO, O CURY", "🧘"), tag=("AUGUSTO CURY", "modo terapeuta"),
         fx={"zen", "whoosh"}, sfx=[("bell", 254.95)]),
    dict(s=256.80, e=260.75, spk="cury", cx=247, text="E a democracia, a beleza dela... está na divergência.",
         fx={"zen"}),
    dict(s=265.10, e=267.70, spk="cury", cw=426, text="Mas você não pode criticar a pessoa.",
         fx={"zen"}, emoji=("😌", 265.6)),

    dict(s=578.96, e=586.45, spk="caiado", cx=185,
         text="O Lula tá doido pra criar esse impasse. Então ele está provocando o Trump toda hora, tá certo? Falando da dentadura do Trump.",
         tag=("RONALDO CAIADO", "correspondente internacional"), fx={"whoosh"},
         zoom_at=585.3, emoji=("🦷", 585.4), sfx=[("boom", 585.3)],
         hold=0.9, hold_text="ASSUNTO SÉRIO", hold_emoji="🦷"),

    dict(s=646.99, e=653.90, spk="renan", cx=150,
         text="Não acredite nesses políticos que estão dizendo pra você que você vai trabalhar menos e ganhar mais. Num país que até as Casas Bahia quebraram!",
         label=("E A ESCALA 6x1?", "💼"), fx={"whoosh"}, emoji=("💀", 652.9), sfx=[("pop", 652.9)]),
    dict(s=654.95, e=655.85, spk="renan", cx=170, text="Todo mundo quebrando!", fx={"punch"}),
    dict(s=659.70, e=660.62, spk="renan", cx=170, text="DESESPERADOR.", fx={"punch", "rage"},
         sfx=[("boom", 659.75)]),

    dict(s=725.31, e=728.17, spk="reporter", cx=145,
         text="Afirmam que o debate não teve um vencedor claro.",
         label=("E QUEM GANHOU?", "🏆"), fx={"whoosh"},
         hold=1.4, hold_text="NINGUÉM", hold_emoji="💀"),
]

TITLE1 = [("RESUMO DO DEBATE", WHITE)]
TITLE2 = [("SEM LULA E SEM FLÁVIO", YELLOW)]
CREDIT = "Imagens: BBC News Brasil / Band"


# --------------------------------------------------------------------------
def font(weight, size):
    return ImageFont.truetype(os.path.join(FONTS, f"Poppins-{weight}.ttf"), size)


def run(cmd, **kw):
    r = subprocess.run(cmd, stderr=subprocess.PIPE, **kw)
    if r.returncode:
        sys.exit("command failed: " + " ".join(cmd) + "\n" + r.stderr.decode()[-2000:])
    return r


_emoji_cache = {}


def emoji_img(ch, size):
    key = (ch, size)
    if key not in _emoji_cache:
        f = ImageFont.truetype(EMOJI_FONT, 109)
        im = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
        im = im.crop(im.getbbox())
        _emoji_cache[key] = im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)
    return _emoji_cache[key]


def stroke_text(runs, fnt, stroke=8, shadow=10):
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
        d.text((x, pad), t, font=fnt, fill=col, stroke_width=stroke, stroke_fill=BLACK)
        x += w
    return img


def with_emoji(img, ch, size, gap=-8):
    e = emoji_img(ch, size)
    out = Image.new("RGBA", (img.width + e.width + gap, max(img.height, e.height)), (0, 0, 0, 0))
    out.alpha_composite(img, (0, (out.height - img.height) // 2))
    out.alpha_composite(e, (img.width + gap, (out.height - e.height) // 2))
    return out


def round_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def ease_out(p):
    return 1 - (1 - p) ** 3


def fade_alpha(img, a):
    if a >= 1:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return img


# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------
def syllables(w):
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõà]+", w.lower()))) + 0.3


def align(p, mono):
    if "text" not in p:
        return []
    words = p["text"].split()
    s, e = p["s"], p["e"]
    hop = int(0.01 * SR)
    seg = mono[int(s * SR):int(e * SR)]
    n = len(seg) // hop
    rms = np.sqrt((seg[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
    voiced = rms > 0.25 * np.percentile(rms, 90)
    cum = np.concatenate([[0], np.cumsum(voiced)])
    wts = np.array([syllables(w) for w in words])
    starts = np.concatenate([[0], np.cumsum(wts)[:-1]]) / wts.sum() * cum[-1]
    return [(w, s + max(0, int(np.searchsorted(cum, v + 0.5)) - 1) * 0.01) for w, v in zip(words, starts)]


def build_timeline(mono):
    t = 0.0
    for p in PIECES:
        p.setdefault("fx", set())
        p.setdefault("cw", 240)
        p.setdefault("cx", SW / 2)
        p["frames"] = int(round((p["e"] - p["s"]) * FPS))
        p["hold_frames"] = int(round(p.get("hold", 0) * FPS))
        p["t0"] = t
        p["dur"] = p["frames"] / FPS
        t += (p["frames"] + p["hold_frames"]) / FPS
    words = []
    for p in PIECES:
        for w, st in align(p, mono):
            words.append((w, p["t0"] + st - p["s"], p))
    return t, words


def caption_chunks(words):
    chunks, cur = [], []
    for i, (w, t, p) in enumerate(words):
        cur.append((w, t))
        nxt = words[i + 1] if i + 1 < len(words) else None
        chars = sum(len(x) for x, _ in cur)
        if (nxt is None or len(cur) >= 3 or chars >= 14 or w[-1] in ".!?,"
                or nxt[2] is not p or nxt[1] - t > 0.9):
            chunks.append((cur, p))
            cur = []
    out = []
    for i, (c, p) in enumerate(chunks):
        end = p["t0"] + p["dur"]
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][0][0][1])
        out.append((c[0][1], min(end, c[-1][1] + 1.3), c, p))
    return out


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------
RNG = np.random.default_rng(7)


def sfx_boom(d=0.9):
    t = np.arange(int(d * SR)) / SR
    f = 40 + 90 * np.exp(-t * 9)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5)
    x += 0.25 * RNG.standard_normal(len(t)) * np.exp(-t * 40)
    return np.tanh(1.6 * x) * 0.9


def bandpass(x, lo, hi):
    spec = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    spec[(fr < lo) | (fr > hi)] = 0
    return np.fft.irfft(spec, len(x))


def sfx_whoosh(d=0.45):
    n = int(d * SR)
    x = bandpass(RNG.standard_normal(n), 500, 5000) * np.sin(np.linspace(0, np.pi, n)) ** 2
    return x / np.abs(x).max() * 0.5


def sfx_scratch(d=0.42):
    t = np.arange(int(d * SR)) / SR
    # vinyl dragged back and forth: pitch follows a fast triangle-ish wobble
    speed = np.abs(np.sin(2 * np.pi * 5.5 * t)) * np.exp(-t * 2)
    ph = np.cumsum(220 + 1800 * speed) / SR
    x = 0.6 * np.sign(np.sin(2 * np.pi * ph)) * speed
    x += 0.6 * bandpass(RNG.standard_normal(len(t)), 800, 6000) * speed
    x = bandpass(x, 150, 7000)
    return x / np.abs(x).max() * 0.7


def sfx_crickets(d=1.9):
    t = np.arange(int(d * SR)) / SR
    carrier = np.sin(2 * np.pi * 4700 * t)
    pulse = (np.sin(2 * np.pi * 28 * t) > 0.2).astype(float)
    gate = ((t % 0.55) < 0.22).astype(float)
    x = carrier * pulse * gate
    x = np.convolve(x, np.ones(48) / 48, mode="same")
    return x / np.abs(x).max() * 0.35


def sfx_bell(d=1.8):
    t = np.arange(int(d * SR)) / SR
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * k)
            for f, a, k in ((880, 1, 2.2), (1760, 0.45, 3.5), (2640, 0.25, 5), (1320, 0.3, 3)))
    return x / np.abs(x).max() * 0.4


def sfx_pop(d=0.12):
    t = np.arange(int(d * SR)) / SR
    x = np.sin(2 * np.pi * np.cumsum(900 * np.exp(-t * 30) + 180) / SR) * np.exp(-t * 35)
    return x * 0.6


SFX = {"boom": (sfx_boom, 0.5), "whoosh": (sfx_whoosh, 0.45), "scratch": (sfx_scratch, 0.55),
       "crickets": (sfx_crickets, 0.9), "bell": (sfx_bell, 0.6), "pop": (sfx_pop, 0.6)}


def build_audio(src, total, tmp):
    wav = os.path.join(tmp, "src.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "2", "-ar", str(SR), wav])
    a, _ = sf.read(wav, dtype="float32")
    out = np.zeros((int(math.ceil(total * SR)) + SR * 2, 2), dtype=np.float32)
    fade = int(0.01 * SR)
    for p in PIECES:
        if p.get("mute"):
            continue
        seg = a[int(p["s"] * SR):int(p["s"] * SR) + int(p["dur"] * SR)].copy()
        seg[:fade] *= np.linspace(0, 1, fade)[:, None]
        seg[-fade:] *= np.linspace(1, 0, fade)[:, None]
        i = int(p["t0"] * SR)
        out[i:i + len(seg)] += seg
    out *= 0.8 / (np.abs(out).max() or 1)
    cache = {}

    def add(name, t):
        if name not in cache:
            cache[name] = SFX[name][0]()
        x, g = cache[name], SFX[name][1]
        i = max(0, int(t * SR))
        j = min(len(out), i + len(x))
        out[i:j] += (x[:j - i] * g)[:, None]

    for p in PIECES:
        if "whoosh" in p["fx"]:
            add("whoosh", p["t0"] - 0.25)
        for name, st in p.get("sfx", []):
            add(name, p["t0"] + st - p["s"])
        if p["hold_frames"]:
            th = p["t0"] + p["dur"]
            add("scratch", th)
            if p.get("hold_emoji") == "💀":
                add("boom", th + 0.15)
    out = out[:int(total * SR)]
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    path = os.path.join(tmp, "mix.wav")
    sf.write(path, out, SR)
    return path


# --------------------------------------------------------------------------
# Video
# --------------------------------------------------------------------------
def piece_frames(src, p):
    vs = p.get("vs", p["s"])
    r = run(["ffmpeg", "-v", "error", "-ss", f"{vs:.3f}", "-i", src, "-t", f"{p['dur'] + 0.3:.3f}",
             "-vf", f"fps={FPS},scale={SW}:{SH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
    buf = np.frombuffer(r.stdout, np.uint8)
    n = len(buf) // (SW * SH * 3)
    frames = buf[:n * SW * SH * 3].reshape(n, SH, SW, 3)
    return [frames[min(i, n - 1)] for i in range(p["frames"])]


class Renderer:
    def __init__(self, total, chunks):
        self.total, self.chunks = total, chunks
        self.cap_cache, self.misc = {}, {}
        top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        t1 = stroke_text(TITLE1, font("ExtraBold", 70), stroke=7)
        top.alpha_composite(t1, ((W - t1.width) // 2, 112))
        t2 = with_emoji(stroke_text(TITLE2, font("ExtraBold", 70), stroke=7), "💀", 80, gap=0)
        top.alpha_composite(t2, ((W - t2.width) // 2, 196))
        cr = stroke_text([(CREDIT, (200, 200, 200))], font("SemiBold", 30), stroke=3, shadow=6)
        top.alpha_composite(cr, ((W - cr.width) // 2, H - 150))
        self.top = top
        self.vignette = self._vignette()

    def _vignette(self):
        y, x = np.mgrid[0:PANEL, 0:PANEL]
        r = np.sqrt(((x - PANEL / 2) / (PANEL / 2)) ** 2 + ((y - PANEL / 2) / (PANEL / 2)) ** 2)
        return np.clip((r - 0.55) / 0.6, 0, 1)

    def tinted(self, key, rgb, alpha):
        k = (key, int(alpha * 40))
        if k not in self.misc:
            a = (self.vignette * alpha * 255).astype(np.uint8)
            im = Image.new("RGBA", (PANEL, PANEL), rgb + (0,))
            im.putalpha(Image.fromarray(a))
            self.misc[k] = im
        return self.misc[k]

    def caption(self, chunk, active, spk):
        key = (id(chunk), active)
        if key not in self.cap_cache:
            col = SPEAKERS.get(spk, YELLOW)
            runs = [((" " if i else "") + w.upper(), col if i == active else WHITE)
                    for i, (w, _) in enumerate(chunk)]
            f = font("ExtraBold", 88)
            while sum(f.getlength(t) for t, _ in runs) > W - 90 and f.size > 50:
                f = font("ExtraBold", f.size - 4)
            self.cap_cache[key] = stroke_text(runs, f, stroke=9, shadow=12)
        return self.cap_cache[key]

    def label(self, text, ch):
        k = ("label", text)
        if k not in self.misc:
            lab = with_emoji(stroke_text([(text, YELLOW)], font("ExtraBold", 62), stroke=6), ch, 72)
            pill = Image.new("RGBA", (lab.width + 30, lab.height + 10), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([18, 22, pill.width - 18, pill.height - 22], 34,
                                                   fill=(0, 0, 0, 200))
            pill.alpha_composite(lab, (15, 5))
            self.misc[k] = pill
        return self.misc[k]

    def tag(self, name, sub, spk):
        k = ("tag", name)
        if k not in self.misc:
            col = SPEAKERS[spk]
            fn, fs = font("ExtraBold", 50), font("Bold", 36)
            w = int(max(fn.getlength(name), fs.getlength(sub))) + 60
            im = Image.new("RGBA", (w + 14, 150), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle([14, 0, w + 13, 78], 16, fill=col + (255,))
            d.rectangle([0, 0, 13, 78], fill=WHITE)
            d.text((40, 39), name, font=fn, fill=BLACK, anchor="lm")
            d.rounded_rectangle([14, 84, int(fs.getlength(sub)) + 54, 140], 14, fill=(15, 15, 15, 235))
            d.text((34, 112), sub, font=fs, fill=WHITE, anchor="lm")
            self.misc[k] = im
        return self.misc[k]

    def hold_text(self, text, ch):
        k = ("hold", text)
        if k not in self.misc:
            f = font("ExtraBold", 104)
            while f.getlength(text) > W - 260 and f.size > 60:
                f = font("ExtraBold", f.size - 4)
            self.misc[k] = with_emoji(stroke_text([(text, WHITE)], f, stroke=11), ch, int(f.size * 1.15))
        return self.misc[k]

    def panel_image(self, src, p, zoom):
        im = Image.fromarray(src)
        cw = p["cw"] / zoom
        ch = cw if p["cw"] <= SH else SH / zoom   # square crop, or full-height letterbox
        cx = min(max(p["cx"], cw / 2), SW - cw / 2)
        cy = SH / 2
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        out_h = int(PANEL * ch / cw)
        big = im.resize((SW * 3, SH * 3), Image.BICUBIC)
        crop = big.crop(tuple(int(v * 3) for v in box)).resize((PANEL, out_h), Image.BICUBIC)
        return crop.filter(ImageFilter.UnsharpMask(2, 60, 2))

    def frame(self, src, p, k, t, held=None):
        """held = seconds into the freeze-frame, or None."""
        lt = k / FPS
        st = p["s"] + lt
        im = Image.fromarray(src)

        zoom = 1.0
        if "punch" in p["fx"]:
            zoom += 0.18 * (1 - ease_out(min(1, lt / 0.35)))
        if "slowzoom" in p["fx"]:
            zoom += 0.12 * lt / max(p["dur"], 0.1)
        if "zoom_at" in p and st >= p["zoom_at"]:
            zoom += 0.35 * ease_out(min(1, (st - p["zoom_at"]) / 0.25))
        if held is not None:
            zoom *= 1 + 0.22 * ease_out(min(1, held / 0.5))
        shake = 0
        if "punch" in p["fx"] and lt < 0.4:
            shake = 14 * (1 - lt / 0.4)
        if held is not None and held < 0.3:
            shake = 18 * (1 - held / 0.3)
        dx = dy = 0
        if shake:
            rnd = random.Random(int(t * FPS))
            dx, dy = rnd.uniform(-shake, shake), rnd.uniform(-shake, shake)

        # background
        bg = im.crop((133, 0, 293, 240)).resize((90, 160), Image.BILINEAR)
        bg = bg.filter(ImageFilter.GaussianBlur(4)).resize((W, H), Image.BILINEAR)
        bg = Image.eval(bg, lambda v: int(v * 0.35)).convert("RGBA")

        # video panel
        vid = self.panel_image(src, p, zoom)
        if held is not None:
            vid = ImageEnhance.Color(vid).enhance(max(0.15, 1 - held * 2.5))
        panel = Image.new("RGBA", (PANEL, PANEL), (0, 0, 0, 0))
        panel.paste(vid, (0, (PANEL - vid.height) // 2))
        if "zen" in p["fx"]:
            panel.alpha_composite(self.tinted("zen", (190, 150, 255), 0.75))
        if "rage" in p["fx"]:
            pulse = 0.55 + 0.25 * math.sin(lt * 2 * math.pi * 2)
            panel.alpha_composite(self.tinted("rage", (255, 0, 0), pulse))
        px, py = int(dx), PANEL_Y + int(dy)
        vy0 = (PANEL - vid.height) // 2
        mask = Image.new("L", (PANEL, PANEL), 0)
        mask.paste(round_mask((PANEL - 40, vid.height), RADIUS), (20, vy0))
        bg.paste(panel, (px, py), mask)
        col = SPEAKERS.get(p.get("spk"), WHITE) if held is None else WHITE
        ImageDraw.Draw(bg).rounded_rectangle([px + 20, py + vy0, px + PANEL - 21, py + vy0 + vid.height - 1],
                                             RADIUS, outline=col, width=6)
        bg.alpha_composite(self.top)

        # zen floating monk
        if "zen" in p["fx"]:
            e = emoji_img("🧘", 130)
            bg.alpha_composite(e, (W - 190, int(PANEL_Y + vy0 + 40 + 14 * math.sin(t * 3))))

        # label (first 1.7 s of the piece)
        if "label" in p and held is None and lt < 1.7:
            a = min(1, lt / 0.12, (1.7 - lt) / 0.25)
            lab = self.label(*p["label"])
            sc = 1 + 0.25 * (1 - ease_out(min(1, lt / 0.18)))
            if sc != 1:
                lab = lab.resize((int(lab.width * sc), int(lab.height * sc)), Image.BICUBIC)
            bg.alpha_composite(fade_alpha(lab, a), ((W - lab.width) // 2, PANEL_Y + vy0 + 24))

        # nickname lower-third, slides in from the left
        if "tag" in p and held is None:
            tg = self.tag(*p["tag"], p["spk"])
            x = int(-tg.width + (tg.width + 40) * ease_out(min(1, max(0, lt - 0.2) / 0.3)))
            if lt > p["dur"] - 0.25:
                x -= int((tg.width + 40) * (lt - (p["dur"] - 0.25)) / 0.25)
            bg.alpha_composite(tg, (x, PANEL_Y + vy0 + vid.height - 190))

        # emoji pop
        if "emoji" in p and held is None:
            ch, et = p["emoji"]
            el = st - et
            if 0 <= el < 1.5:
                e = emoji_img(ch, 200)
                sc = (0.4 + 0.75 * ease_out(min(1, el / 0.22))) * (1 + 0.05 * math.sin(el * 12))
                e2 = e.resize((int(e.width * sc), int(e.height * sc)), Image.BICUBIC).rotate(
                    10 * math.sin(el * 7), Image.BICUBIC, expand=True)
                if el > 1.2:
                    e2 = fade_alpha(e2, (1.5 - el) / 0.3)
                bg.alpha_composite(e2, (W - e2.width - 50, PANEL_Y + vy0 + vid.height - e2.height - 40))

        # freeze-frame punchline
        if held is not None:
            ht = self.hold_text(p["hold_text"], p["hold_emoji"])
            sc = 0.5 + 0.5 * ease_out(min(1, held / 0.18)) + 0.03 * math.sin(held * 14)
            h2 = ht.resize((int(ht.width * sc), int(ht.height * sc)), Image.BICUBIC).rotate(-4, Image.BICUBIC, expand=True)
            bg.alpha_composite(h2, ((W - h2.width) // 2, PANEL_Y + PANEL // 2 - h2.height // 2))

        # captions
        if held is None:
            for c0, c1, chunk, cp in self.chunks:
                if c0 <= t < c1:
                    active = max([i for i, (_, wt) in enumerate(chunk) if wt <= t + 1e-6] or [0])
                    cap = self.caption(chunk, active, cp.get("spk"))
                    pop = 1 + 0.2 * (1 - ease_out(min(1, (t - c0) / 0.12)))
                    if pop != 1:
                        cap = cap.resize((int(cap.width * pop), int(cap.height * pop)), Image.BICUBIC)
                    bg.alpha_composite(cap, ((W - cap.width) // 2, CAP_Y - cap.height // 2))
                    break

        # white flash entering a freeze
        if held is not None and held < 0.12:
            bg = Image.blend(bg, Image.new("RGBA", (W, H), WHITE + (255,)), 0.7 * (1 - held / 0.12))

        d = ImageDraw.Draw(bg)
        d.rectangle([0, H - 14, W, H], fill=BLACK)
        d.rectangle([0, H - 14, int(W * t / self.total), H], fill=YELLOW)
        return bg.convert("RGB")


# --------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "..", "output", "debate_2026_resenha.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="resenha_") as tmp:
        mono_path = os.path.join(tmp, "mono.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", str(SR), mono_path])
        mono, _ = sf.read(mono_path, dtype="float32")
        total, words = build_timeline(mono)
        chunks = caption_chunks(words)
        print(f"{len(PIECES)} cuts, {total:.1f}s")
        mix = build_audio(src, total, tmp)
        r = Renderer(total, chunks)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-i", mix, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        for p in PIECES:
            frames = piece_frames(src, p)
            for k, fr in enumerate(frames):
                enc.stdin.write(r.frame(fr, p, k, p["t0"] + k / FPS).tobytes())
            last = len(frames) - 1
            for h in range(p["hold_frames"]):
                t = p["t0"] + p["dur"] + h / FPS
                enc.stdin.write(r.frame(frames[last], p, last, t, held=h / FPS).tobytes())
            print(f"  {p['t0'] + p['dur'] + p['hold_frames'] / FPS:5.1f}s / {total:.1f}s")
        enc.stdin.close()
        if enc.wait():
            sys.exit("encode failed")
    print("Done ->", out)


if __name__ == "__main__":
    main()
