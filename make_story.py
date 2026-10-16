#!/usr/bin/env python3
"""Render a "WHAT IF ...?" science short (1080x1920).

Format mirrors the narrated what-if explainers: a title card, a stylised
scene (city/park or a globe seen from space), a HUD across the top (tag,
label, big animated number, sub line on the left; a second readout on the
right), centred captions with *highlighted* words, and an end card.

Everything is drawn procedurally: no footage needed. Sound is synthesised
(pad, city ambience, wind, rumble, impacts). Drop a recorded narration in
`voiceover` (and/or a track in `music`) and it is mixed on top; the timed
script is written next to the video so the VO can be recorded to it.

Usage:  python3 make_story.py story_earth_stops.json
        python3 make_story.py story_earth_stops.json --still 21.5   # one PNG
        python3 make_story.py story_earth_stops.json --draft        # fast encode
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import wave
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "fonts")
W, H = 1080, 1920
SR = 44100

WHITE = (255, 255, 255)
ORANGE = (255, 138, 31)
GREY = (190, 196, 206)

HUD_X = 64
HUD_TOP = 200
CAPTION_CY = 1290
CAPTION_MAX_W = 920


# ---------------------------------------------------------------- helpers

def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def ease_out(u):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 3


def param(fx, key, u, default=0.0):
    """fx[key] is a constant or [start, end] eased across the beat."""
    v = fx.get(key, default)
    if isinstance(v, (list, tuple)):
        return v[0] + (v[1] - v[0]) * smooth(u)
    return v


@lru_cache(maxsize=None)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def rich(text, base=WHITE, accent=ORANGE):
    """'plain *highlight*. plain' -> words, each a tuple of (text, colour) runs."""
    words, hot = [], False
    for raw in text.split(" "):
        runs = []
        for k, part in enumerate(raw.split("*")):
            if k:
                hot = not hot
            if part:
                runs.append((part, accent if hot else base))
        if runs:
            words.append(tuple(runs))
    return words


@lru_cache(maxsize=2048)
def render_runs(runs, fname, size, tracking=0, shadow=6, shadow_alpha=170):
    """Render [(text, rgb), ...] on one line. Returns (img, pad): the visible
    glyph box starts at (pad, pad), so paste at (x - pad, y_top - pad)."""
    f = font(fname, size)
    full = "".join(t for t, _ in runs)
    _, top, _, bottom = f.getbbox(full or " ")

    def adv(s):
        return f.getlength(s) if not tracking else sum(f.getlength(c) for c in s) + tracking * len(s)

    width = sum(adv(t) for t, _ in runs) - (tracking if tracking else 0)
    pad = shadow * 3 + 4
    img = Image.new("RGBA", (int(width) + 2 * pad + 2, bottom - top + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for text, col in runs:
        if tracking:
            for c in text:
                d.text((x, pad - top), c, font=f, fill=col + (255,))
                x += f.getlength(c) + tracking
        else:
            d.text((x, pad - top), text, font=f, fill=col + (255,))
            x += f.getlength(text)
    if shadow:
        a = img.getchannel("A").filter(ImageFilter.GaussianBlur(shadow))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.putalpha(a.point(lambda v: min(255, v * shadow_alpha // 120)))
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(sh, (0, 3))
        out.alpha_composite(img)
        img = out
    return img, pad


def text_w(img_pad):
    img, pad = img_pad
    return img.width - 2 * pad


def text_h(img_pad):
    img, pad = img_pad
    return img.height - 2 * pad


def paste(canvas, img_pad, x, y, alpha=1.0):
    img, pad = img_pad
    if alpha <= 0:
        return
    if alpha < 1:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(img, (int(x - pad), int(y - pad)))


def fmt_value(v, t):
    """String, or {"from","to","decimals","delay","dur"} counted over the beat."""
    if not isinstance(v, dict):
        return str(v)
    d = v.get("decimals", 0)
    u = ease_out((t - v.get("delay", 0.0)) / v.get("dur", 1.2))
    x = v["from"] + (v["to"] - v["from"]) * u
    return f"{x:,.{d}f}"


# ---------------------------------------------------------------- noise

def _hash3(ix, iy, iz, seed):
    h = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 144665) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def value_noise3(p, seed):
    """Smooth value noise at points p (N,3)."""
    i = np.floor(p).astype(np.int64)
    f = p - i
    f = f * f * (3 - 2 * f)
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = _hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
                wx = f[:, 0] if dx else 1 - f[:, 0]
                wy = f[:, 1] if dy else 1 - f[:, 1]
                wz = f[:, 2] if dz else 1 - f[:, 2]
                out = out + h * wx * wy * wz
    return out


def fbm3(p, seed, octaves=6, gain=0.5):
    total, amp, norm = 0, 1.0, 0
    for o in range(octaves):
        total = total + amp * value_noise3(p * (2 ** o), seed + o * 17)
        norm += amp
        amp *= gain
    return total / norm


# ---------------------------------------------------------------- city scene

class City:
    HORIZON = 1060

    def __init__(self, seed=7):
        rng = np.random.default_rng(seed)
        hz = self.HORIZON

        # sky
        y = np.linspace(0, 1, hz + 40)[:, None]
        top, bot = np.array([62, 104, 168]), np.array([184, 206, 228])
        sky = (top + (bot - top) * y ** 0.8)[:, None, :] * np.ones((1, W, 1))
        self.sky = Image.fromarray(sky.astype(np.uint8), "RGB")
        dust_top, dust_bot = np.array([96, 70, 52]), np.array([196, 150, 102])
        dsky = (dust_top + (dust_bot - dust_top) * y ** 0.8)[:, None, :] * np.ones((1, W, 1))
        self.dust_sky = Image.fromarray(dsky.astype(np.uint8), "RGB")

        # soft clouds on a wide strip so they can drift
        self.clouds = Image.new("RGBA", (W * 2, 700), (0, 0, 0, 0))
        d = ImageDraw.Draw(self.clouds)
        for _ in range(26):
            cx, cy = rng.uniform(0, W * 2), rng.uniform(80, 560)
            for _ in range(6):
                rx, ry = rng.uniform(60, 190), rng.uniform(18, 45)
                ox, oy = rng.uniform(-150, 150), rng.uniform(-25, 25)
                d.ellipse([cx + ox - rx, cy + oy - ry, cx + ox + rx, cy + oy + ry],
                          fill=(255, 255, 255, int(rng.uniform(40, 90))))
        self.clouds = self.clouds.filter(ImageFilter.GaussianBlur(22))

        # skyline layers (wider than the frame for pan / lean)
        self.layers = [self._skyline(rng, (128, 146, 178), 160, 520, 0.35),
                       self._skyline(rng, (78, 92, 122), 110, 400, 0.6)]
        self.trees = self._trees(rng)

        # ground
        gh = H - hz
        g = np.linspace(0, 1, gh)[:, None]
        g_top, g_bot = np.array([104, 160, 66]), np.array([44, 112, 34])
        ground = (g_top + (g_bot - g_top) * g)[:, None, :] * np.ones((1, W, 1))
        self.ground = Image.fromarray(ground.astype(np.uint8), "RGB")
        gd = ImageDraw.Draw(self.ground)
        for _ in range(14000):
            yy = rng.uniform(0, 1) ** 1.6 * gh
            k = yy / gh
            xx = rng.uniform(-20, W + 20)
            ln = 4 + 70 * k ** 2 * rng.uniform(0.6, 1.4)
            lean = rng.uniform(-0.35, 0.35) * ln
            shade = rng.uniform(-30, 30)
            col = tuple(int(max(0, min(255, c + shade))) for c in (70 + 40 * (1 - k), 140, 48))
            gd.line([(xx, yy), (xx + lean, yy - ln)], fill=col, width=max(1, int(1 + 5 * k ** 2)))
        for _ in range(160):  # flowers
            yy = rng.uniform(0.25, 1) * gh
            k = yy / gh
            r = 1.5 + 6 * k ** 2
            xx = rng.uniform(0, W)
            col = [(255, 255, 255), (250, 214, 70), (200, 150, 255)][rng.integers(3)]
            gd.ellipse([xx - r, yy - r, xx + r, yy + r], fill=col)
        dirt = Image.new("RGB", self.ground.size, (120, 88, 58))
        self.dirt = Image.blend(self.ground, dirt, 0.72)

        # people in the park
        n = 70
        self.people = dict(
            x=rng.uniform(-40, W + 40, n), y=hz + 18 + rng.uniform(0, 1, n) ** 1.5 * 170,
            walk=rng.uniform(-14, 14, n), ph=rng.uniform(0, 6.28, n),
            vx=rng.uniform(1600, 4200, n), vy=rng.uniform(-700, -150, n),
            delay=rng.uniform(0, 0.35, n),
            col=[tuple(int(c) for c in rng.integers(40, 255, 3)) for _ in range(n)])

        # debris & wind streaks (looping particles)
        nd = 260
        self.debris = dict(x=rng.uniform(0, W + 600, nd), y=rng.uniform(250, H - 150, nd),
                           v=rng.uniform(1400, 4200, nd), ln=rng.uniform(18, 140, nd),
                           w=rng.integers(2, 9, nd),
                           col=[[(120, 88, 58), (70, 120, 40), (150, 150, 150), (90, 70, 50)][i % 4]
                                for i in range(nd)])
        ns = 150
        self.bubbles = Bubbles()
        self.wind = dict(x=rng.uniform(0, W + 1200, ns), y=rng.uniform(80, H - 80, ns),
                         v=rng.uniform(2800, 6500, ns), ln=rng.uniform(150, 560, ns),
                         a=rng.integers(30, 95, ns))

    def _skyline(self, rng, col, hmin, hmax, density):
        hz = self.HORIZON
        img = Image.new("RGBA", (W + 800, hz + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 0
        while x < img.width:
            bw = rng.uniform(50, 130)
            bh = rng.uniform(hmin, hmax) * (1.4 if rng.random() < 0.12 else 1)
            shade = rng.uniform(-14, 14)
            c = tuple(int(max(0, min(255, v + shade))) for v in col)
            top = hz + 10 - bh
            d.rectangle([x, top, x + bw, hz + 40], fill=c + (255,))
            if rng.random() < 0.35:  # setback crown
                inset = bw * rng.uniform(0.15, 0.3)
                d.rectangle([x + inset, top - bh * 0.12, x + bw - inset, top], fill=c + (255,))
            if rng.random() < 0.2:  # antenna
                d.line([(x + bw / 2, top - bh * 0.12), (x + bw / 2, top - bh * 0.3)], fill=c + (255,), width=3)
            win = tuple(int(min(255, v + 26)) for v in c)
            for wy in np.arange(top + 12, hz, 16):
                for wx in np.arange(x + 7, x + bw - 8, 12):
                    if rng.random() < 0.6:
                        d.rectangle([wx, wy, wx + 5, wy + 7], fill=win + (255,))
            x += bw + rng.uniform(-10, 30) * (1 - density)
        return img

    def _trees(self, rng):
        hz = self.HORIZON
        img = Image.new("RGBA", (W + 800, hz + 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for _ in range(140):
            x, r = rng.uniform(0, img.width), rng.uniform(18, 42)
            y = hz + rng.uniform(-6, 14)
            g = int(rng.uniform(95, 150))
            d.ellipse([x - r, y - 2 * r, x + r, y], fill=(40, g, 46, 255))
            d.ellipse([x - r * 0.6, y - 2 * r, x + r * 0.3, y - r * 1.2], fill=(70, g + 30, 60, 255))
        d.rectangle([0, hz + 6, img.width, hz + 60], fill=(118, 96, 70, 255))  # path
        return img

    def _layer(self, img, shift, lean, sway=0.0):
        """Crop a W-wide window at `shift`, sheared so the top moves right by `lean`."""
        hz = self.HORIZON
        s = lean * 0.9  # shear per pixel of height
        return img.transform((W, img.height), Image.AFFINE,
                             (1, s, 400 - shift + sway - s * hz, 0, 1, 0), resample=Image.BILINEAR)

    def render(self, gt, fx, u, t, launch_t, idx):
        hz = self.HORIZON
        dust = param(fx, "dust", u)
        lean = param(fx, "lean", u)
        scorch = param(fx, "scorch", u)
        cam = gt * 6

        sky = self.sky if dust <= 0 else Image.blend(self.sky, self.dust_sky, min(1, dust))
        frame = Image.new("RGBA", (W, H))
        frame.paste(sky, (0, 0))
        cs = int((gt * 12 + (lean * 4000)) % W)
        frame.alpha_composite(self.clouds.crop((cs, 0, cs + W, 700)))

        for img, depth in zip(self.layers, (0.25, 0.5)):
            frame.alpha_composite(self._layer(img, cam * depth, lean * depth * 1.6), (0, 0))
            if depth < 0.4:
                frame.alpha_composite(self._haze(dust))
        frame.alpha_composite(self._layer(self.trees, cam * 0.8, lean * 0.4), (0, 0))

        ground = self.ground if scorch <= 0 else Image.blend(self.ground, self.dirt, min(1, scorch))
        frame.paste(ground, (0, hz + 40), None)
        frame.paste(ground.crop((0, 0, W, 40)), (0, hz), None)
        frame.alpha_composite(self._layer(self.trees, cam * 0.8, lean * 0.4).crop((0, hz, W, hz + 60)), (0, hz))

        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        p = self.people
        for i in range(len(p["x"])):
            k = (p["y"][i] - hz) / 190
            sc = 0.6 + 1.6 * k
            x, y = p["x"][i] + p["walk"][i] * gt - cam * 0.9, p["y"][i]
            bob = abs(math.sin(gt * 6 + p["ph"][i])) * 2 * sc
            streak = 0
            if launch_t is not None and gt >= launch_t + p["delay"][i]:
                dt = gt - launch_t - p["delay"][i]
                x += p["vx"][i] * dt
                y += p["vy"][i] * dt + 900 * dt * dt
                streak = p["vx"][i] * 0.05
                if x > W + 200:
                    continue
            bw, bh, hr = 5 * sc, 13 * sc, 3.2 * sc
            c = p["col"][i]
            if streak:
                d.line([(x - streak, y - bh / 2), (x, y - bh / 2)], fill=c + (110,), width=int(bw * 1.6))
            d.rectangle([x - bw / 2, y - bh - bob, x + bw / 2, y - bob], fill=c + (255,))
            d.ellipse([x - hr, y - bh - 2 * hr - bob, x + hr, y - bh - bob], fill=(232, 190, 150, 255))

        nd = int(param(fx, "debris", u) * len(self.debris["x"]))
        q = self.debris
        for i in range(nd):
            x = (q["x"][i] + q["v"][i] * gt) % (W + 600) - 300
            y = q["y"][i] + math.sin(gt * 3 + i) * 20
            d.line([(x - q["ln"][i], y), (x, y)], fill=q["col"][i] + (200,), width=int(q["w"][i]))
        ns = int(param(fx, "wind", u) * len(self.wind["x"]))
        q = self.wind
        for i in range(ns):
            x = (q["x"][i] + q["v"][i] * gt) % (W + 1200) - 600
            d.line([(x - q["ln"][i], q["y"][i]), (x, q["y"][i])], fill=(255, 245, 230, int(q["a"][i])), width=2)
        frame.alpha_composite(ov)

        if dust > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (150, 108, 70, int(110 * min(1, dust)))))

        warm = param(fx, "warm", u)
        if warm > 0:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 160, 80, int(90 * min(1, warm)))))

        if fx.get("thoughts"):
            self.bubbles.draw(frame, gt, param(fx, "thoughts", u), fx.get("mood", "busy"))
        return frame

    @lru_cache(maxsize=64)
    def _haze(self, dust):
        hz = self.HORIZON
        a = np.clip((np.arange(hz + 40) - (hz - 520)) / 520, 0, 1) ** 1.5 * 150
        col = np.array([196, 210, 228]) * (1 - min(1, dust)) + np.array([190, 146, 100]) * min(1, dust)
        arr = np.zeros((hz + 40, W, 4), np.uint8)
        arr[..., :3] = col.astype(np.uint8)
        arr[..., 3] = a[:, None].astype(np.uint8)
        return Image.fromarray(arr, "RGBA")


THOUGHTS = {
    "busy": ["did I lock the door?", "pizza tonight?", "I'm so late", "nice shoes", "what's my password?",
             "is he looking at me?", "should've stayed in bed", "I love this song", "3 more hours...",
             "don't trip", "rent is due", "call mom back", "what was her name?", "cute dog!",
             "I'm starving", "am I being weird?", "need coffee", "did I say that out loud?",
             "where did I park?", "ugh, Mondays", "text him back", "is it going to rain?"],
    "kind": ["they seem nice", "love that jacket", "they're funny", "I should say hi", "great smile",
             "wish we talked more", "they're so cool", "good vibes", "they look kind", "I like them"],
}


@lru_cache(maxsize=256)
def bubble_img(text):
    f = font("Poppins-SemiBold.ttf", 30)
    tw = int(f.getlength(text))
    bw, bh, pad = tw + 48, 64, 24
    img = Image.new("RGBA", (bw + 2 * pad, bh + 60 + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for layer, col, off in ((sh, (0, 0, 0, 90), 4), (img, (255, 255, 255, 240), 0)):
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle([pad, pad + off, pad + bw, pad + bh + off], 30, fill=col)
        d.ellipse([pad + 26, pad + bh + 8 + off, pad + 44, pad + bh + 26 + off], fill=col)
        d.ellipse([pad + 14, pad + bh + 34 + off, pad + 24, pad + bh + 44 + off], fill=col)
    out = sh.filter(ImageFilter.GaussianBlur(6))
    out.alpha_composite(img)
    ImageDraw.Draw(out).text((pad + 24, pad + 13), text, font=f, fill=(30, 30, 40, 255))
    return out


class Bubbles:
    """Thought bubbles popping in and out above the crowd."""
    SLOTS, PERIOD = 22, 2.6

    def draw(self, frame, gt, amount, mood):
        pool = THOUGHTS[mood]
        n = int(round(amount * self.SLOTS))
        for k in range(n):
            ph = gt / self.PERIOD + k / self.SLOTS * 3.7
            cyc, u = int(ph), ph - int(ph)
            h = (k * 7919 + cyc * 104729) % 100003
            img = bubble_img(pool[h % len(pool)])
            x = 40 + (h * 37 % 1000) / 1000 * (W - 80 - img.width)
            y = 560 + (h * 61 % 1000) / 1000 * 560
            life = u * self.PERIOD
            a = min(1, life / 0.18) * (1 - smooth((life - (self.PERIOD - 0.35)) / 0.35))
            if a <= 0:
                continue
            sc = 0.6 + 0.4 * ease_out(life / 0.25)
            im = img.resize((int(img.width * sc), int(img.height * sc)), Image.BILINEAR)
            if a < 1:
                im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
            frame.alpha_composite(im, (int(x + img.width * (1 - sc) / 2), int(y + img.height * (1 - sc))))


# ---------------------------------------------------------------- neuron scene

class Neurons:
    """A slowly turning 3D web of neurons with signal pulses (drawn at half res)."""

    def __init__(self, seed=5, n=260):
        rng = np.random.default_rng(seed)
        p = rng.standard_normal((n, 3))
        p /= np.linalg.norm(p, axis=1)[:, None]
        self.p = p * rng.uniform(0.25, 1, (n, 1)) ** 0.5
        d = np.linalg.norm(self.p[:, None] - self.p[None], axis=-1)
        self.edges = sorted({tuple(sorted((i, j))) for i in range(n) for j in np.argsort(d[i])[1:4]})
        m = len(self.edges)
        self.pulse = dict(e=rng.integers(0, m, 600), off=rng.uniform(0, 1, 600), v=rng.uniform(0.6, 1.6, 600))
        self.size = rng.uniform(1.5, 4, n)
        y = np.linspace(0, 1, H // 2)[:, None]
        bg = (np.array([10, 6, 28]) + np.array([16, 10, 40]) * y)[:, None, :] * np.ones((1, W // 2, 1))
        self.bg = Image.fromarray(bg.astype(np.uint8), "RGB")

    def render(self, gt, fx, u, t, idx):
        w, h = W // 2, H // 2
        yaw = gt * 0.12 + math.radians(param(fx, "yaw", u, 0))
        zoom = param(fx, "zoom", u, 1.0)
        act = param(fx, "activity", u, 0.4)
        heat = param(fx, "heat", u)  # 0 calm blue/violet -> 1 overload red
        cy_ = param(fx, "cy", u, 1040) / 2
        c, s = math.cos(yaw), math.sin(yaw)
        x = self.p[:, 0] * c + self.p[:, 2] * s
        z = -self.p[:, 0] * s + self.p[:, 2] * c + 2.6
        y = self.p[:, 1]
        f = 820 * zoom / 2
        sx, sy = w / 2 + f * x / z, cy_ - f * y / z
        depth = np.clip((3.6 - z) / 2, 0.15, 1)

        base = np.array([120, 110, 255]) * (1 - heat) + np.array([255, 70, 60]) * heat
        hot = np.array([150, 230, 255]) * (1 - heat) + np.array([255, 210, 120]) * heat
        lines = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(lines)
        for i, j in self.edges:
            a = int(70 * (depth[i] + depth[j]) / 2)
            d.line([(sx[i], sy[i]), (sx[j], sy[j])], fill=tuple(int(v) for v in base) + (a,), width=1)
        for i in range(len(sx)):
            r = self.size[i] * depth[i] * zoom
            d.ellipse([sx[i] - r, sy[i] - r, sx[i] + r, sy[i] + r],
                      fill=tuple(int(v) for v in base * 0.6 + 100) + (int(200 * depth[i]),))
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        q = self.pulse
        npulse = int(act * len(q["e"]))
        for k in range(npulse):
            i, j = self.edges[q["e"][k]]
            v = (q["off"][k] + gt * q["v"][k] * (1 + 1.5 * heat)) % 1
            px, py = sx[i] + (sx[j] - sx[i]) * v, sy[i] + (sy[j] - sy[i]) * v
            r = 2.5 * zoom
            g.ellipse([px - r, py - r, px + r, py + r], fill=tuple(int(c_) for c_ in hot) + (255,))
        frame = self.bg.convert("RGBA")
        frame.alpha_composite(lines)
        frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4)))
        frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(1.2)))
        flick = param(fx, "flicker", u)
        if flick > 0:
            a = np.random.default_rng(idx).uniform(0, 1) ** 3 * flick
            frame.alpha_composite(Image.new("RGBA", (w, h), (255, 60, 50, int(120 * a))))
        return frame.resize((W, H), Image.BILINEAR)


# ---------------------------------------------------------------- globe scene

class Globe:
    TW, TH = 1024, 512

    def __init__(self, seed=3):
        lat = (0.5 - (np.arange(self.TH) + 0.5) / self.TH) * np.pi
        lon = ((np.arange(self.TW) + 0.5) / self.TW) * 2 * np.pi - np.pi
        lo, la = np.meshgrid(lon, lat)
        pts = np.stack([np.cos(la) * np.sin(lo), np.sin(la), np.cos(la) * np.cos(lo)], -1).reshape(-1, 3)
        e = fbm3(pts * 1.7 + 11.3, seed, octaves=7).reshape(self.TH, self.TW)
        e = (e - np.quantile(e, 0.70)) / (e.max() - e.min()) * 2.6  # ~30% land
        self.elev = e.astype(np.float32)
        c = fbm3(pts * 3.2 + 4.1, seed + 99, octaves=5).reshape(self.TH, self.TW)
        self.cloud = np.clip((c - 0.52) * 4.5, 0, 0.9).astype(np.float32)
        self.sin2 = (np.sin(lat) ** 2)[:, None].astype(np.float32)
        self.abslat = np.abs(np.degrees(lat))[:, None].astype(np.float32)
        self._tex = {}

        rng = np.random.default_rng(seed)
        y = np.linspace(0, 1, H)[:, None]
        bg = (np.array([6, 8, 20]) + np.array([10, 14, 34]) * y)[:, None, :] * np.ones((1, W, 1))
        n = 700
        xs, ys = rng.integers(0, W, n), rng.integers(0, H, n)
        bg[ys, xs] = np.clip(rng.uniform(90, 255, (n, 1)), 0, 255)
        self.bg = Image.fromarray(bg.astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(0.6))
        self.bg_arr = np.asarray(self.bg).astype(np.float32)

    def texture(self, drain):
        key = round(drain, 3)
        if key in self._tex:
            return self._tex[key]
        sea = drain * (1.9 * self.sin2 - 1.05)  # without the spin, water piles up at the poles
        d = self.elev - sea
        land = d > 0
        k = np.clip(d / 1.1, 0, 1)[..., None]
        low, high = np.array([86, 158, 74]), np.array([164, 146, 98])
        col = low + (high - low) * k
        seabed = (self.elev <= 0) & land  # old ocean floor, now dry
        col = np.where(seabed[..., None], np.array([196, 172, 120]) - 30 * k, col)
        ice = (self.abslat > 72) & land
        col = np.where(ice[..., None], np.array([236, 242, 248]), col)
        depth = np.clip(-d / 1.0, 0, 1)[..., None]
        water = np.array([78, 172, 226]) + (np.array([30, 84, 170]) - np.array([78, 172, 226])) * depth ** 0.6
        col = np.where(land[..., None], col, water).astype(np.float32)
        if len(self._tex) > 400:
            self._tex.clear()
        self._tex[key] = col
        return col

    def render(self, gt, fx, u):
        R = param(fx, "radius", u, 520)
        cx, cy = W / 2, param(fx, "cy", u, 1180)
        yaw = math.radians(param(fx, "yaw", u, 0))
        tilt = math.radians(param(fx, "tilt", u, 18))
        saz = math.radians(param(fx, "sun_az", u, -40))
        sel = math.radians(param(fx, "sun_el", u, 25))
        tex = self.texture(param(fx, "drain", u))

        out = self.bg_arr.copy()
        x0, x1 = max(0, int(cx - R * 1.08)), min(W, int(cx + R * 1.08) + 1)
        y0, y1 = max(0, int(cy - R * 1.08)), min(H, int(cy + R * 1.08) + 1)
        ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        nx, ny = (xs - cx) / R, (cy - ys) / R
        r2 = nx * nx + ny * ny
        inside = r2 <= 1
        nz = np.sqrt(np.clip(1 - r2, 0, 1))

        # view -> world: tilt about x, then yaw about y
        wy = ny * math.cos(tilt) + nz * math.sin(tilt)
        wz = -ny * math.sin(tilt) + nz * math.cos(tilt)
        wx = nx
        lon = np.arctan2(wx, wz) + yaw
        lat = np.arcsin(np.clip(wy, -1, 1))
        ti = np.clip(((0.5 - lat / np.pi) * self.TH).astype(np.int32), 0, self.TH - 1)
        tj = (((lon / (2 * np.pi) + 0.5) % 1.0) * self.TW).astype(np.int32) % self.TW
        col = tex[ti, tj]
        cj = (tj + int(gt * 6)) % self.TW
        cl = self.cloud[ti, cj][..., None]
        col = col * (1 - cl) + 250 * cl

        sun = np.array([math.sin(saz) * math.cos(sel), math.sin(sel), math.cos(saz) * math.cos(sel)])
        diff = np.clip(nx * sun[0] + ny * sun[1] + nz * sun[2], 0, 1)
        light = 0.08 + 0.92 * diff ** 0.75
        spec = np.clip(diff, 0, 1) ** 30 * 60
        col = col * light[..., None] + spec[..., None] * (1 - cl)
        col = col * (0.8 + 0.2 * nz)[..., None]

        region = out[y0:y1, x0:x1]
        region[inside] = col[inside]
        # atmosphere rim
        r = np.sqrt(r2)
        rim = np.clip(1 - (r - 1) / 0.07, 0, 1) * (r > 1)
        rim_in = np.clip((r - 0.86) / 0.14, 0, 1) * inside
        lit = 0.25 + 0.75 * np.clip(nx * sun[0] + ny * sun[1] + 0.3, 0, 1)
        glow = (rim ** 2 * 0.9 + rim_in ** 3 * 0.45) * lit
        region += glow[..., None] * (np.array([110, 170, 255]) - region) * (glow[..., None] > 0)
        out[y0:y1, x0:x1] = region
        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        dim = param(fx, "dim", u)
        if dim > 0:
            img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * dim))))
        return img


# ---------------------------------------------------------------- overlays

def hud_layer(hud, right, t):
    layer = Image.new("RGBA", (W, 620), (0, 0, 0, 0))
    if hud:
        y = HUD_TOP
        tag = render_runs(((hud["tag"].upper(), WHITE),), "Poppins-SemiBold.ttf", 28, 3, 4)
        d = ImageDraw.Draw(layer)
        d.ellipse([HUD_X, y + 5, HUD_X + 13, y + 18], fill=ORANGE + (255,))
        paste(layer, tag, HUD_X + 26, y)
        y += 46
        lab = render_runs(((hud["label"].upper(), WHITE),), "Poppins-SemiBold.ttf", 27, 2, 4)
        paste(layer, lab, HUD_X, y)
        y += text_h(lab) + 14
        val = render_runs(((fmt_value(hud["value"], t), WHITE),), "Anton-Regular.ttf", 96, 0, 6)
        paste(layer, val, HUD_X, y)
        if hud.get("unit"):
            un = render_runs(((hud["unit"], WHITE),), "Poppins-Bold.ttf", 38, 1, 5)
            paste(layer, un, HUD_X + text_w(val) + 12, y + text_h(val) - text_h(un))
        y += text_h(val) + 18
        if hud.get("sub"):
            sub = render_runs(((hud["sub"].upper(), WHITE),), "Poppins-SemiBold.ttf", 25, 2, 4)
            paste(layer, sub, HUD_X, y)
    if right:
        xr, y = W - HUD_X, HUD_TOP
        lab = render_runs(((right["label"].upper(), WHITE),), "Poppins-SemiBold.ttf", 27, 2, 4)
        paste(layer, lab, xr - text_w(lab), y)
        y += text_h(lab) + 14
        val = render_runs(((fmt_value(right["value"], t), WHITE),), "Anton-Regular.ttf", 72, 0, 6)
        un = render_runs(((right.get("unit") or " ", WHITE),), "Poppins-Bold.ttf", 30, 1, 5)
        uw = text_w(un) + 10 if right.get("unit") else 0
        paste(layer, val, xr - uw - text_w(val), y)
        if uw:
            paste(layer, un, xr - text_w(un), y + text_h(val) - text_h(un))
        y += text_h(val) + 16
        if right.get("sub"):
            sub = render_runs(((right["sub"].upper(), WHITE),), "Poppins-SemiBold.ttf", 23, 2, 4)
            paste(layer, sub, xr - text_w(sub), y)
    return layer


def wrap(words, fname, size, max_w):
    """Greedy word wrap; returns one tuple of merged (text, colour) runs per line."""
    f = font(fname, size)
    lines, cur = [], []
    for w in words:
        trial = " ".join("".join(t for t, _ in x) for x in cur + [w])
        if cur and f.getlength(trial) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    out = []
    for line in lines:
        runs = []
        for i, word in enumerate(line):
            for j, (txt, c) in enumerate(word):
                if j == len(word) - 1 and i < len(line) - 1:
                    txt += " "
                if runs and runs[-1][1] == c:
                    runs[-1] = (runs[-1][0] + txt, c)
                else:
                    runs.append((txt, c))
        out.append(tuple(runs))
    return out


@lru_cache(maxsize=128)
def caption_lines(text, size=60):
    return [render_runs(r, "Poppins-Bold.ttf", size, 0, 7, 220)
            for r in wrap(rich(text), "Poppins-Bold.ttf", size, CAPTION_MAX_W)]


def draw_caption(canvas, text, cy, alpha, dy=0, size=60, pitch=78):
    lines = caption_lines(text, size)
    y = cy - pitch * len(lines) / 2 + dy
    for ln in lines:
        paste(canvas, ln, W / 2 - text_w(ln) / 2, y, alpha)
        y += pitch


@lru_cache(maxsize=8)
def title_lines(lines, scale=1.0):
    out = []
    for line in lines:
        runs = tuple((w, c) for w, c in wrap(rich(line), "Anton-Regular.ttf", 110, 2000)[0])
        size = int((150 if any(c == ORANGE for _, c in runs) else 104) * scale)
        while font("Anton-Regular.ttf", size).getlength("".join(t for t, _ in runs)) > (W - 140) * scale:
            size -= 2
        out.append(render_runs(runs, "Anton-Regular.ttf", size, 2, 8, 200))
    return out


def draw_title(canvas, lines, cy, t, alpha=1.0, scale=1.0):
    imgs = title_lines(tuple(lines), scale)
    gap = int(26 * scale)
    total = sum(text_h(i) for i in imgs) + gap * (len(imgs) - 1)
    y = cy - total / 2
    for k, im in enumerate(imgs):
        u = ease_out((t - 0.12 * k) / 0.45)
        paste(canvas, im, W / 2 - text_w(im) / 2, y + 30 * (1 - u), alpha * u)
        y += text_h(im) + gap


@lru_cache(maxsize=1)
def title_shade():
    a = np.zeros((H, 1), np.float32)
    yy = np.arange(H)[:, None]
    a = np.clip(1 - np.abs(yy - 820) / 620, 0, 1) ** 1.2 * 200
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# ---------------------------------------------------------------- audio

def fft_band(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-6
    g = np.ones_like(f)
    if hi:
        g /= 1 + (f / hi) ** 4
    if lo:
        g *= (f / lo) ** 4 / (1 + (f / lo) ** 4)
    return np.fft.irfft(X * g, len(x))


def decode(path, n):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)[:n]
    return np.pad(a, (0, n - len(a)))


def build_audio(cfg, beats, starts, total, path):
    n = int(total * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(n)

    # per-beat envelopes sampled at 50 Hz, then interpolated
    kt = np.arange(0, total, 0.02)
    env = {k: np.zeros(len(kt)) for k in ("wind", "shake", "amb", "space", "buzz")}
    for j, tt in enumerate(kt):
        i = min(len(beats) - 1, int(np.searchsorted(starts, tt, "right") - 1))
        b, u = beats[i], (tt - starts[i]) / beats[i]["dur"]
        fx = b.get("fx", {})
        env["wind"][j] = param(fx, "wind", u)
        env["shake"][j] = min(1, param(fx, "shake", u) / 30)
        env["amb"][j] = 1.0 if b["scene"] == "city" and not (set(fx) - {"thoughts", "mood", "warm"}) else 0
        env["buzz"][j] = param(fx, "thoughts", u) if b["scene"] == "city" else param(fx, "heat", u)
        env["space"][j] = 1.0 if b["scene"] != "city" else 0
    sm = lambda a: np.convolve(a, np.ones(15) / 15, "same")
    E = {k: np.interp(t, kt, sm(v)) for k, v in env.items()}

    # pad: slow minor chord, swelling
    pad = sum(np.sin(2 * np.pi * f * t + p) * a for f, p, a in
              ((55, 0, 0.5), (110, 1, 0.35), (130.8, 2, 0.25), (164.8, 3, 0.25), (220, 4, 0.12)))
    pad *= 0.55 + 0.45 * np.sin(2 * np.pi * t / 7.0) ** 2
    pad = fft_band(pad, hi=900) * 0.10 * (0.8 + 0.6 * E["space"])

    amb = fft_band(noise, lo=300, hi=2500) * 0.035 * E["amb"]
    birds = np.zeros(n)
    for k in range(int(total * 1.2)):
        s = rng.uniform(0, total)
        if E["amb"][min(n - 1, int(s * SR))] < 0.5:
            continue
        L = int(0.09 * SR)
        i0 = int(s * SR)
        tt = np.arange(min(L, n - i0)) / SR
        f0 = rng.uniform(2600, 4200)
        birds[i0:i0 + len(tt)] += np.sin(2 * np.pi * (f0 * tt + 9000 * tt ** 2)) * np.sin(np.pi * tt / 0.09) * 0.03
    wind = fft_band(noise, lo=150, hi=1400) * 0.16 * E["wind"] * (0.8 + 0.2 * np.sin(2 * np.pi * t * 0.7))
    rumble = fft_band(rng.standard_normal(n), hi=90) * 0.9 * E["shake"]

    booms = np.zeros(n)
    for i, b in enumerate(beats):
        if b.get("fx", {}).get("flash") or b.get("fx", {}).get("launch"):
            i0 = int(starts[i] * SR)
            L = min(int(3.0 * SR), n - i0)
            tt = np.arange(L) / SR
            sweep = np.sin(2 * np.pi * (70 * tt - 12 * tt ** 2)) * np.exp(-tt / 0.7)
            hit = fft_band(rng.standard_normal(L), hi=400) * np.exp(-tt / 0.25) * 2.5
            booms[i0:i0 + L] += (sweep * 0.8 + hit) * (1.0 if b["fx"].get("flash") else 0.5)
        if i > 0 and b["scene"] != beats[i - 1]["scene"]:  # whoosh into a new scene
            i0 = int(max(0, starts[i] - 0.6) * SR)
            L = min(int(1.0 * SR), n - i0)
            tt = np.arange(L) / SR
            booms[i0:i0 + L] += fft_band(rng.standard_normal(L), lo=300, hi=3000) * np.sin(np.pi * tt / 1.0) ** 2 * 0.25

    # crowd murmur: many detuned formant-ish voices, louder with more thoughts
    murmur = sum(fft_band(rng.standard_normal(n), lo=f * 0.8, hi=f * 1.25) *
                 (0.5 + 0.5 * np.sin(2 * np.pi * t * rng.uniform(2, 5) + rng.uniform(0, 6))) ** 2
                 for f in (350, 520, 800, 1200, 1700))
    murmur = murmur * 0.12 * E["buzz"] ** 1.5

    mix = pad + amb + birds + wind + rumble + booms + murmur
    fade = np.clip((total - t) / 1.5, 0, 1) * np.clip(t / 0.4, 0, 1)
    mix *= fade
    mix /= max(1e-6, np.abs(mix).max()) / 0.85

    if cfg.get("music") and os.path.exists(os.path.join(ROOT, cfg["music"])):
        mix = mix * 0.6 + decode(os.path.join(ROOT, cfg["music"]), n) * cfg.get("music_gain", 0.35) * fade
    if cfg.get("voiceover") and os.path.exists(os.path.join(ROOT, cfg["voiceover"])):
        mix = mix * 0.35 + decode(os.path.join(ROOT, cfg["voiceover"]), n)
    mix /= max(1.0, np.abs(mix).max() / 0.95)

    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.repeat(pcm, 2).tobytes())


# ---------------------------------------------------------------- main

class Story:
    def __init__(self, cfg):
        self.cfg = cfg
        self.beats = cfg["beats"]
        self.starts = np.concatenate([[0], np.cumsum([b["dur"] for b in self.beats])])
        self.total = float(self.starts[-1])
        self.city = City()
        bgs = {b.get("fx", {}).get("bg", "globe") if b["scene"] == "end" else b["scene"] for b in self.beats}
        self.globe = Globe() if "globe" in bgs else None
        self.neurons = Neurons() if "neurons" in bgs else None
        self.launch_t = next((self.starts[i] + b["fx"].get("launch_at", 0)
                              for i, b in enumerate(self.beats) if b.get("fx", {}).get("launch")), None)

    def beat(self, gt):
        i = min(len(self.beats) - 1, int(np.searchsorted(self.starts, gt, "right") - 1))
        return i, gt - self.starts[i]

    def frame(self, gt, idx):
        i, t = self.beat(gt)
        b = self.beats[i]
        fx, dur = b.get("fx", {}), b["dur"]
        u = t / dur
        prev = self.beats[i - 1] if i else None
        nxt = self.beats[i + 1] if i + 1 < len(self.beats) else None

        scene = fx.get("bg", "globe") if b["scene"] == "end" else b["scene"]
        if scene == "city":
            img = self.city.render(gt, fx, u, t, self.launch_t, idx)
        elif scene == "neurons":
            img = self.neurons.render(gt, fx, u, t, idx)
            dim = param(fx, "dim", u)
            if dim > 0:
                img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * dim))))
        else:
            img = self.globe.render(gt, fx, u)

        if fx.get("flash"):
            a = math.exp(-t / 0.18)
            if a > 0.01:
                img.alpha_composite(Image.new("RGBA", (W, H), (255, 250, 235, int(255 * a))))
        shake = param(fx, "shake", u)
        if shake > 0:
            rng = np.random.default_rng(idx)
            ox, oy = rng.uniform(-shake, shake, 2)
            sc = 1 + 2.4 * shake / W
            img = img.transform((W, H), Image.AFFINE,
                                (1 / sc, 0, (W - W / sc) / 2 + ox, 0, 1 / sc, (H - H / sc) / 2 + oy),
                                resample=Image.BILINEAR)

        # scene cut: quick dip from black
        if prev and prev["scene"] != b["scene"] and t < 0.35:
            img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - t / 0.35)))))

        if b.get("title"):
            fade = 1 - smooth((t - (dur - 0.45)) / 0.45)
            sh = title_shade()
            if fade < 1:
                sh = sh.copy()
                sh.putalpha(sh.getchannel("A").point(lambda v: int(v * fade)))
            img.alpha_composite(sh)
            draw_title(img, self.cfg["title"], 820, t, fade)

        if b["scene"] == "end":
            img.alpha_composite(title_shade())
            draw_title(img, self.cfg["title"], 640, t, 1.0, 0.72)
            if self.cfg.get("disclaimer"):
                dis = render_runs(((self.cfg["disclaimer"].upper(), GREY),), "Poppins-SemiBold.ttf", 22, 3, 3)
                paste(img, dis, W / 2 - text_w(dis) / 2, 920, ease_out((t - 0.5) / 0.5))
            if b.get("caption"):
                a = ease_out((t - 0.9) / 0.4)
                draw_caption(img, b["caption"], 1060, a, 16 * (1 - a))
            hnd = render_runs(((self.cfg["handle"].upper(), WHITE),), "Poppins-Bold.ttf", 34, 2, 5)
            a = ease_out((t - 1.3) / 0.4)
            paste(img, hnd, W / 2 - text_w(hnd) / 2, 1180, a)
            return img

        # HUD: fades/slides in when its tag changes
        hud, right = b.get("hud"), b.get("right")
        if hud or right:
            same_prev = prev and (prev.get("hud") or {}).get("tag") == (hud or {}).get("tag")
            same_next = nxt and (nxt.get("hud") or {}).get("tag") == (hud or {}).get("tag") \
                and nxt["scene"] == b["scene"]
            a_in = 1.0 if same_prev and prev["scene"] == b["scene"] else ease_out(t / 0.35)
            a_out = 1.0 if same_next else 1 - smooth((t - (dur - 0.25)) / 0.25)
            a = a_in * a_out
            layer = hud_layer(hud, right, t)
            if a < 1:
                layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
            img.alpha_composite(layer, (int(-24 * (1 - a_in)), 0))

        if b.get("caption"):
            a_in = ease_out(t / 0.22)
            a_out = 1 - smooth((t - (dur - 0.18)) / 0.18)
            draw_caption(img, b["caption"], CAPTION_CY, a_in * a_out, 18 * (1 - a_in))

        if self.cfg.get("handle") and not b.get("title"):
            hnd = render_runs(((self.cfg["handle"].upper(), WHITE),), "Poppins-SemiBold.ttf", 24, 2, 4)
            paste(img, hnd, W / 2 - text_w(hnd) / 2, 1500, 0.55)
        return img


def write_script(story, path):
    with open(path, "w") as f:
        f.write(f"{' '.join(story.cfg['title']).replace('*', '')}\n\n")
        for b, s in zip(story.beats, story.starts):
            if b.get("caption"):
                f.write(f"[{int(s // 60)}:{s % 60:05.2f}]  {b['caption'].replace('*', '')}\n")


def main():
    args = sys.argv[1:]
    cfg_path = next((a for a in args if a.endswith(".json")), os.path.join(ROOT, "story_earth_stops.json"))
    with open(cfg_path) as f:
        cfg = json.load(f)
    story = Story(cfg)
    fps = cfg.get("fps", 30)
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)

    if "--still" in args:
        gt = float(args[args.index("--still") + 1])
        p = os.path.splitext(out)[0] + f"_{gt:05.2f}.png"
        story.frame(gt, int(gt * fps)).convert("RGB").save(p)
        print("Still ->", p)
        return

    write_script(story, os.path.splitext(out)[0] + "_script.txt")
    tmp = tempfile.mkdtemp(prefix="story_")
    wav = os.path.join(tmp, "audio.wav")
    print(f"Synthesising audio ({story.total:.1f} s)…")
    build_audio(cfg, story.beats, story.starts[:-1], story.total, wav)

    print("Rendering frames…")
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-i", wav, "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "ultrafast" if "--draft" in args else "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out],
        stdin=subprocess.PIPE)
    n = int(round(story.total * fps))
    for idx in range(n):
        enc.stdin.write(story.frame(idx / fps, idx).convert("RGB").tobytes())
        if idx % (fps * 5) == 0:
            print(f"  {idx / fps:5.1f}s / {story.total:.1f}s", flush=True)
    enc.stdin.close()
    if enc.wait():
        sys.exit("encode failed")
    os.remove(wav)
    os.rmdir(tmp)
    print("Done ->", out)


if __name__ == "__main__":
    main()
