#!/usr/bin/env python3
"""Render an illustrated "music lore" explainer short (1080x1920).

Style follows the flat-illustration fact shorts: one illustrated scene that the
camera pushes around, a big swirling hero effect, word-by-word captions with
the spoken word boxed in red, a pop-in notes card, a red dashed "reveal" trace,
a moving watermark and a dimmed logo/handle outro.

Usage:  python3 make_explainer.py [explainer_funky_drummer.json]

The voiceover is generated offline with Kokoro TTS (model files are fetched
into models/kokoro/ on first run), or set "voice_file" to your own recording:
captions are then spread over it in proportion to the script.
The drum loop, bass and sound effects are synthesised, so there is nothing
else to supply.
"""
import hashlib
import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
import skia

W, H = 1080, 1920
ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "fonts")
MODEL_DIR = os.path.join(ROOT, "models", "kokoro")
MODEL_URLS = {
    "kokoro.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
    "voices.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}

SR = 44100              # mix sample rate
BPM = 96
STEP = 60 / BPM / 4     # one 16th note
OUTRO = 2.8             # seconds of logo/handle card after the last line
LEAD_IN = 0.35

# Palette
CREAM = "#efe5d3"
CREAM_DOT = "#e2d3b9"
FLOOR_TOP = "#d2a96f"
FLOOR_BOT = "#b4834c"
NAVY = "#25287a"
NAVY_DK = "#171a55"
INK = "#1b1b24"
RED = "#e8473a"
SKIN = "#8a5a3b"
SKIN_DK = "#6e4429"
GOLD = "#e2b13c"
CHROME = "#c9ccd3"
SHELL = "#c8372d"
WHITE = "#ffffff"


# --------------------------------------------------------------------------
# small helpers

def col(h, a=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return skia.ColorSetARGB(int(max(0, min(1, a)) * 255), r, g, b)


def paint(c, a=1.0, stroke=0.0, cap=skia.Paint.kRound_Cap, effect=None, shader=None):
    p = skia.Paint(AntiAlias=True, Color=col(c, a))
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        p.setStrokeCap(cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    if effect is not None:
        p.setPathEffect(effect)
    if shader is not None:
        p.setShader(shader)
    return p


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def back_out(t, s=1.9):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def window(t, t0, t1, fin=0.25, fout=0.25):
    """0..1 visibility: fades in after t0, out before t1."""
    if t < t0 or t > t1:
        return 0.0
    return min(smooth((t - t0) / fin) if fin else 1.0, smooth((t1 - t) / fout) if fout else 1.0)


def hash01(*xs):
    h = hashlib.md5(repr(xs).encode()).digest()
    return int.from_bytes(h[:4], "little") / 2 ** 32


_tf = {}


def font(weight, size):
    if weight not in _tf:
        _tf[weight] = skia.Typeface.MakeFromFile(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"))
    return skia.Font(_tf[weight], size)


def text_w(f, s):
    return f.measureText(s)


def draw_text(c, s, x, y, f, fill, a=1.0, outline=None, ow=0.0, align="left"):
    w = text_w(f, s)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    if outline:
        c.drawString(s, x, y, f, paint(outline, a, stroke=ow))
    c.drawString(s, x, y, f, paint(fill, a))
    return w


def catmull(points, n=24):
    """Dense polyline through control points (Catmull-Rom)."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (np.array(p, float) for p in pts[i - 1:i + 3])
        for j in range(n):
            t = j / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(np.array(points[-1], float))
    return np.array(out)


def resample(poly, step):
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    ss = np.arange(0, s[-1], step)
    x = np.interp(ss, s, poly[:, 0])
    y = np.interp(ss, s, poly[:, 1])
    return np.stack([x, y], 1), s[-1]


def path_of(pts):
    p = skia.Path()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    return p


def trimmed(path, a, b):
    m = skia.PathMeasure(path, False)
    L = m.getLength()
    out = skia.Path()
    m.getSegment(L * clamp(a), L * clamp(b), out, True)
    return out


# --------------------------------------------------------------------------
# timeline (voiceover -> line times -> word times)

def ensure_models():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for name, url in MODEL_URLS.items():
        dst = os.path.join(MODEL_DIR, name)
        if not os.path.exists(dst):
            print(f"downloading {name} ...")
            subprocess.run(["curl", "-sSL", "--fail", "-o", dst + ".part", url], check=True)
            os.replace(dst + ".part", dst)


def read_wav_mono(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def trim_silence(a, thr=0.012, pad=0.03):
    idx = np.nonzero(np.abs(a) > thr)[0]
    if len(idx) == 0:
        return a
    p = int(pad * SR)
    return a[max(0, idx[0] - p):idx[-1] + p]


def tts_lines(cfg, cache_dir):
    """One trimmed audio array per script line (cached by text+voice)."""
    os.makedirs(cache_dir, exist_ok=True)
    kokoro = None
    out = []
    for line in cfg["lines"]:
        key = hashlib.md5(f'{cfg["voice"]}|{cfg["voice_speed"]}|{line["text"]}'.encode()).hexdigest()[:12]
        path = os.path.join(cache_dir, key + ".wav")
        if not os.path.exists(path):
            if kokoro is None:
                ensure_models()
                from kokoro_onnx import Kokoro
                kokoro = Kokoro(os.path.join(MODEL_DIR, "kokoro.onnx"), os.path.join(MODEL_DIR, "voices.bin"))
            print(f"tts: {line['text']}")
            samples, sr = kokoro.create(line["text"], voice=cfg["voice"], speed=cfg["voice_speed"], lang="en-us")
            pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm.tobytes())
        out.append(trim_silence(read_wav_mono(path)))
    return out


def syllables(word):
    w = "".join(ch for ch in word.lower() if ch.isalnum())
    if w.isdigit():
        return 2.0 * len(w) / 2 + 1
    groups, prev = 0, False
    for ch in w:
        v = ch in "aeiouy"
        if v and not prev:
            groups += 1
        prev = v
    if w.endswith("e") and groups > 1:
        groups -= 1
    return max(1, groups) + 0.6


def build_timeline(cfg, cache_dir):
    lines = cfg["lines"]
    if cfg.get("voice_file"):
        # Own recording: spread the lines over it in proportion to their syllables.
        voice = read_wav_mono(os.path.join(ROOT, cfg["voice_file"]))
        weights = [sum(syllables(w) for w in l["text"].split()) + 2.0 for l in lines]
        span = len(voice) / SR
        t = 0.0
        for l, wgt in zip(lines, weights):
            d = span * wgt / sum(weights)
            l["start"], l["end"] = t, t + d - 0.15
            t += d
        total = span + OUTRO
    else:
        clips = tts_lines(cfg, cache_dir)
        t = LEAD_IN
        placed = []
        for l, a in zip(lines, clips):
            d = len(a) / SR
            l["start"], l["end"] = t, t + d
            placed.append((t, a))
            gap = 0.30 if l["text"].rstrip()[-1] in ".!?" else 0.10
            t += d + gap
        total = lines[-1]["end"] + OUTRO
        voice = np.zeros(int(total * SR) + SR, np.float32)
        for t0, a in placed:
            i = int(t0 * SR)
            voice[i:i + len(a)] += a

    # word timings and caption chunks
    chunks = []
    for l in lines:
        words = l["text"].split()
        wts = [syllables(w) + (0.8 if w[-1] in ",.!?" else 0) for w in words]
        d = l["end"] - l["start"]
        acc, times = 0.0, []
        for w, wt in zip(words, wts):
            times.append((w, l["start"] + d * acc / sum(wts), l["start"] + d * (acc + wt) / sum(wts)))
            acc += wt
        cur = []
        for i, item in enumerate(times):
            cur.append(item)
            chars = sum(len(x[0]) + 1 for x in cur)
            nxt = times[i + 1][0] if i + 1 < len(times) else ""
            if (len(cur) >= 3 or item[0][-1] in ",.!?" or chars + len(nxt) > 20 or not nxt):
                chunks.append(cur)
                cur = []
    for i, ch in enumerate(chunks):
        nxt = chunks[i + 1][0][1] if i + 1 < len(chunks) else ch[-1][2] + 0.4
        ch_end = min(nxt, ch[-1][2] + 0.45)
        chunks[i] = {"words": ch, "start": ch[0][1], "end": ch_end}
    return voice, total, chunks


# --------------------------------------------------------------------------
# music + sfx (synthesised, all original)

def synth_kick(n):
    t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 32)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 9) * 0.95


def synth_snare(n, rng):
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - np.concatenate([[0], noise[:-1]]) * 0.6
    return (noise * np.exp(-t * 22) * 0.35 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.5)


def synth_hat(n, rng, open_=False):
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    hp = noise - np.concatenate([[0], noise[:-1]])
    return hp * np.exp(-t * (14 if open_ else 70)) * 0.16


def synth_bass(n, freq):
    t = np.arange(n) / SR
    env = np.minimum(1, t * 200) * np.exp(-t * 3.5)
    return (np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)) * env * 0.42


def synth_stab(n, freqs):
    t = np.arange(n) / SR
    env = np.minimum(1, t * 300) * np.exp(-t * 11)
    s = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) for f in freqs)
    return s * env * 0.07


KICKS = {0: 1.0, 6: 0.8, 10: 0.9}
SNARES = {4: 1.0, 12: 1.0, 7: 0.25, 9: 0.3, 15: 0.22}
HATS = {i: (0.75 if i % 4 == 0 else 0.5) for i in range(0, 16, 2)}
BASS = {0: 82.4, 6: 98.0, 10: 110.0, 11: 123.5}   # E2 G2 A2 B2
STABS = {2: (329.6, 392.0, 493.9), 10: (293.7, 370.0, 440.0)}


def music_sections(T, total):
    """(start, end, parts) where parts is a set of 'drums', 'bass', 'stab'."""
    return [
        (0.0, T["dropout"] + 0.9, {"drums", "bass", "stab"}),
        (T["dropout"] + 0.9, T["sampled"], {"drums"}),                      # the break
        (T["sampled"], T["royalty"], {"drums", "bass", "stab"}),
        (T["everywhere"], total - 1.2, {"drums", "bass", "stab"}),
    ]


def drum_events(T, total):
    """List of (time, kind, velocity) for every drum hit; drives audio + animation."""
    ev = []
    for s0, s1, parts in music_sections(T, total):
        if "drums" not in parts:
            continue
        k0 = math.ceil(s0 / STEP)
        k = k0
        while k * STEP < s1:
            step = k % 16
            t = k * STEP
            if step in KICKS:
                ev.append((t, "kick", KICKS[step]))
            if step in SNARES:
                ev.append((t, "snare", SNARES[step]))
            if step in HATS:
                ev.append((t, "hat", HATS[step]))
            k += 1
    return ev


def build_music(T, total, events):
    rng = np.random.default_rng(7)
    n = int(total * SR) + SR
    mus = np.zeros(n, np.float32)
    kick, snare = synth_kick(int(0.4 * SR)), synth_snare(int(0.25 * SR), rng)
    hat = synth_hat(int(0.06 * SR), rng)

    def add(buf, t, s, g):
        i = int(t * SR)
        j = min(len(buf), i + len(s))
        if i < len(buf):
            buf[i:j] += (s[:j - i] * g).astype(np.float32)

    for t, kind, v in events:
        add(mus, t, {"kick": kick, "snare": snare, "hat": hat}[kind], v)
    for s0, s1, parts in music_sections(T, total):
        k = math.ceil(s0 / STEP)
        while k * STEP < s1:
            step, bar = k % 16, k // 16
            if "bass" in parts and step in BASS:
                add(mus, k * STEP, synth_bass(int(STEP * 3 * SR), BASS[step]), 1.0)
            if "stab" in parts and step in STABS and bar % 2 == 0:
                add(mus, k * STEP, synth_stab(int(0.5 * SR), STABS[step]), 1.0)
            k += 1
    # vinyl crackle bed
    crack = (rng.random(n) > 0.9993).astype(np.float32) * rng.standard_normal(n).astype(np.float32) * 0.25
    mus += crack
    # fade at the very end
    f = int(1.2 * SR)
    end = int((total - 0.2) * SR)
    mus[end - f:end] *= np.linspace(1, 0, f, dtype=np.float32)
    mus[end:] = 0
    return mus


def build_sfx(T, total, cfg):
    rng = np.random.default_rng(11)
    n = int(total * SR) + SR
    sfx = np.zeros(n, np.float32)

    def add(t, s, g=1.0):
        i = int(t * SR)
        j = min(n, i + len(s))
        sfx[i:j] += (s[:j - i] * g).astype(np.float32)

    def whoosh(d=0.45):
        m = int(d * SR)
        x = np.arange(m) / m
        noise = rng.standard_normal(m)
        # crude moving low-pass: blend of smoothed noise with rising cutoff
        k = 1 + (1 - x) * 40
        out = np.zeros(m)
        acc = 0.0
        for i in range(m):
            acc += (noise[i] - acc) / k[i]
            out[i] = acc
        return out * np.sin(np.pi * x) ** 2 * 1.4

    def pop(f0=700, f1=1400, d=0.09):
        m = int(d * SR)
        t = np.arange(m) / SR
        f = np.linspace(f0, f1, m)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * 0.35

    def glitch(d=0.35):
        m = int(d * SR)
        s = rng.standard_normal(m) * 0.25
        s = np.round(s * 4) / 4
        gate = (np.sin(np.arange(m) / SR * 2 * np.pi * 23) > 0).astype(float)
        return s * gate

    def thud():
        m = int(0.6 * SR)
        t = np.arange(m) / SR
        return np.sin(2 * np.pi * (55 + 40 * np.exp(-t * 20)) * t) * np.exp(-t * 6) * 0.8

    w = whoosh()
    for key in ("older", "dropout", "sampled", "royalty", "everywhere"):
        add(T[key] - 0.2, w, 0.5)
    add(T["older"], glitch(), 0.5)
    add(T["notes"], pop(), 1.0)
    add(T["names"], pop(500, 1100), 1.0)
    add(T["names"] + 0.7, pop(500, 1100), 1.0)
    add(T["royalty2"] + 0.25, thud(), 0.9)
    add(T["end"] + 0.05, whoosh(0.6), 0.6)
    return sfx


def write_wav(path, a):
    a = np.clip(a, -1, 1)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((a * 32767).astype(np.int16).tobytes())


# --------------------------------------------------------------------------
# drawing: world

BG_X0, BG_Y0, BG_W, BG_H = -900, -400, 3300, 3100   # world area covered by the backdrop


def make_background():
    """Backdrop in world coordinates: halftone wall + stage floor at y=1380."""
    surf = skia.Surface(BG_W, BG_H)
    c = surf.getCanvas()
    c.translate(-BG_X0, -BG_Y0)
    c.clear(col(CREAM))
    floor_y = 1380
    for y in range(BG_Y0, floor_y, 22):
        for x in range(BG_X0, BG_X0 + BG_W, 22):
            ox = 11 if (y // 22) % 2 else 0
            d = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(x * 0.004 + y * 0.003)) * clamp((floor_y - y) / 900)
            c.drawCircle(x + ox, y, 1.2 + 3.4 * d * d, paint(CREAM_DOT, 0.9))
    sh = skia.GradientShader.MakeLinear([(0, floor_y), (0, floor_y + 900)], [col(FLOOR_TOP), col(FLOOR_BOT)])
    c.drawRect(skia.Rect.MakeLTRB(BG_X0, floor_y, BG_X0 + BG_W, BG_Y0 + BG_H), paint(FLOOR_TOP, shader=sh))
    vp = (W / 2, 900)
    for i in range(-30, 31):
        xb = W / 2 + i * 150
        c.drawLine(lerp(vp[0], xb, (floor_y - vp[1]) / (H - vp[1])), floor_y,
                   lerp(vp[0], xb, (BG_Y0 + BG_H - vp[1]) / (H - vp[1])), BG_Y0 + BG_H,
                   paint("#9c6d3c", 0.35, stroke=2.5))
    y, gap = floor_y + 14, 16
    while y < BG_Y0 + BG_H:
        c.drawLine(BG_X0, y, BG_X0 + BG_W, y, paint("#9c6d3c", 0.25, stroke=2))
        gap *= 1.35
        y += gap
    c.drawLine(BG_X0, floor_y, BG_X0 + BG_W, floor_y, paint("#8e6236", 0.6, stroke=4))
    for cx in (540, 1520):
        sp = skia.GradientShader.MakeRadial((cx, 0), 460, [col("#fff3d6", 0.6), col("#fff3d6", 0)])
        c.save()
        c.translate(0, 1430)
        c.scale(1, 0.3)
        c.drawCircle(cx, 0, 460, paint(WHITE, shader=sp))
        c.restore()
    return surf.makeImageSnapshot()


_HITS = {"events": []}


def set_events(events):
    _HITS.clear()
    _HITS["events"] = events


def hit_arrays(kinds):
    key = tuple(sorted(kinds))
    if key not in _HITS:
        sel = [e for e in _HITS["events"] if e[1] in kinds]
        _HITS[key] = (np.array([e[0] for e in sel]), np.array([e[2] for e in sel]))
    return _HITS[key]


def drum_state(t, kinds):
    """Stick height 0 (on the drum) .. 1 (raised) for a limb playing `kinds` hits."""
    times, vels = hit_arrays(kinds)
    if len(times) == 0:
        return 0.25
    i = int(np.searchsorted(times, t))
    prev = times[i - 1] if i > 0 else None
    nxt = times[i] if i < len(times) else None
    if prev is None or nxt is None or nxt - prev > 1.0:
        far = min(abs(t - x) for x in (prev, nxt) if x is not None)
        return 0.25 * smooth(far * 3)
    ph = (t - prev) / (nxt - prev)
    return math.sin(math.pi * ph) ** 0.8 * (0.45 + 0.55 * vels[i])


def last_hit(t, kinds):
    times, vels = hit_arrays(kinds)
    i = int(np.searchsorted(times, t, "right")) - 1
    if i < 0:
        return 99.0, 0.0
    return t - times[i], vels[i]


def hit_env(t, kinds, decay=10.0):
    dt, v = last_hit(t, kinds)
    return v * math.exp(-dt * decay)


def ik(s, tgt, a, b, bend):
    s, tgt = np.array(s, float), np.array(tgt, float)
    d = np.linalg.norm(tgt - s)
    d = clamp(d, abs(a - b) + 1, a + b - 1)
    base = math.atan2(tgt[1] - s[1], tgt[0] - s[0])
    ang = math.acos(clamp((a * a + d * d - b * b) / (2 * a * d), -1, 1))
    return s + a * np.array([math.cos(base + bend * ang), math.sin(base + bend * ang)])


# ---- shape helpers (flat cel-shaded look)

def p_rrect(l, t, r, b, rad):
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(l, t, r, b), rad, rad))
    return p


def p_oval(l, t, r, b):
    p = skia.Path()
    p.addOval(skia.Rect.MakeLTRB(l, t, r, b))
    return p


def p_circle(x, y, r):
    p = skia.Path()
    p.addCircle(x, y, r)
    return p


def p_poly(pts):
    p = path_of(pts)
    p.close()
    return p


def p_blob(pts, n=8):
    """Closed smooth shape through control points."""
    ring = list(pts) + list(pts[:3])
    dense = catmull(ring, n)
    return p_poly([tuple(q) for q in dense[n:-2 * n]])


def shaded(c, path, base, dark, off=(-11, -8), hi=None, hi_off=(5, 4)):
    """Fill with a dark rim on the lower-right and an optional light rim upper-left."""
    c.drawPath(path, paint(dark))
    c.save()
    c.clipPath(path, skia.ClipOp.kIntersect, True)
    c.translate(*off)
    if hi:
        c.drawPath(path, paint(hi))
        c.translate(*hi_off)
    c.drawPath(path, paint(base))
    c.restore()


def limb(c, a, b, w, base, dark):
    c.drawLine(a[0], a[1], b[0], b[1], paint(dark, stroke=w))
    c.drawLine(a[0] - w * 0.13, a[1] - w * 0.1, b[0] - w * 0.13, b[1] - w * 0.1, paint(base, stroke=w * 0.66))


def halftone(c, path, color, a=1.0, step=11, r=2.2):
    b = path.getBounds()
    c.save()
    c.clipPath(path, skia.ClipOp.kIntersect, True)
    p = paint(color, a)
    y, row = b.top(), 0
    while y < b.bottom():
        x = b.left() + (step / 2 if row % 2 else 0)
        while x < b.right():
            c.drawCircle(x, y, r, p)
            x += step
        y += step
        row += 1
    c.restore()


def draw_cymbal(c, x, y, rx, tilt, wob=0.0, glint=0.0):
    c.save()
    c.translate(x, y)
    c.rotate(tilt + wob)
    body = p_oval(-rx, -rx * 0.17, rx, rx * 0.17)
    shaded(c, body, GOLD, "#a87818", off=(0, -5), hi="#fbe39a", hi_off=(0, 3))
    for k in (0.72, 0.45):
        c.drawOval(skia.Rect.MakeLTRB(-rx * k, -rx * 0.17 * k, rx * k, rx * 0.17 * k), paint("#b8861f", 0.45, stroke=2))
    c.drawOval(skia.Rect.MakeLTRB(-rx * 0.2, -rx * 0.12, rx * 0.2, rx * 0.04), paint("#c9952a"))
    c.drawCircle(0, -rx * 0.05, 5, paint("#6e4f12"))
    if glint > 0.02:
        gx, gy, s = -rx * 0.45, -rx * 0.04, 26 * glint
        p = paint(WHITE, glint, stroke=4)
        c.drawLine(gx - s, gy, gx + s, gy, p)
        c.drawLine(gx, gy - s, gx, gy + s, p)
    c.restore()


def draw_drum_shell(c, cx, top, w, h, body=SHELL, squash=0.0):
    c.save()
    c.translate(cx, top + h)
    c.scale(1 + 0.04 * squash, 1 - 0.08 * squash)
    c.translate(-cx, -(top + h))
    r = skia.Rect.MakeLTRB(cx - w / 2, top, cx + w / 2, top + h)
    c.drawRect(r, paint(body))
    sh = skia.GradientShader.MakeLinear([(cx - w / 2, 0), (cx + w / 2, 0)],
                                        [col(WHITE, 0.3), col(WHITE, 0), col(INK, 0.3)], [0, 0.3, 1])
    c.drawRect(r, paint(WHITE, shader=sh))
    for k in range(5):
        lx = cx - w / 2 + w * (0.12 + 0.19 * k)
        c.drawRoundRect(skia.Rect.MakeLTRB(lx - 4, top + h * 0.3, lx + 4, top + h * 0.7), 3, 3, paint(CHROME))
    for yy in (top + 4, top + h - 4):
        c.drawLine(cx - w / 2, yy, cx + w / 2, yy, paint(CHROME, stroke=7, cap=skia.Paint.kButt_Cap))
    head = skia.Rect.MakeLTRB(cx - w / 2, top - w * 0.12, cx + w / 2, top + w * 0.12)
    c.drawOval(head, paint("#f6f1e8"))
    c.drawOval(skia.Rect.MakeLTRB(cx - w / 2 + 6, top - w * 0.12 + 6, cx + w / 2, top + w * 0.12),
               paint("#e3dccd"))
    c.drawOval(skia.Rect.MakeLTRB(cx - w / 2 + 6, top - w * 0.12 + 3, cx + w / 2 - 10, top + w * 0.12 - 4),
               paint("#f6f1e8"))
    c.drawOval(head, paint(CHROME, stroke=5))
    c.restore()


# ---- the drummer

SNARE_HIT = (395, 1120)
HAT_HIT = (690, 1066)


def arm_pose(shoulder, drum, h, bend, stick_dir):
    hand = np.array([drum[0] + stick_dir * 70, drum[1] - 50 - 90 * h])
    el = ik(shoulder, hand, 118, 112, bend)
    ang = math.atan2(drum[1] - hand[1], drum[0] - hand[0])
    d = np.array([math.cos(ang), math.sin(ang)])
    return np.array(shoulder, float), el, hand, hand + 150 * d, hand - 22 * d


def drummer_pose(t, playing):
    hat_h = drum_state(t, ("hat",)) if playing else 0.05
    sn_h = drum_state(t, ("snare",)) if playing else 0.05
    bob = 9 * hit_env(t, ("kick", "snare"), 8) if playing else 0.0
    sway = 5 * math.sin(2 * math.pi * t * BPM / 60 / 2) if playing else 0.0
    sy = 985 + bob * 0.6
    return {
        "bob": bob, "sway": sway, "hat_h": hat_h,
        "left": arm_pose((488 + sway * 0.4, sy), SNARE_HIT, sn_h, -1, 1),
        "right": arm_pose((636 + sway * 0.4, sy), HAT_HIT, hat_h, 1, -1),
    }


def draw_head(c, t, cx, hy, mood):
    c.save()
    if mood == "sad":
        c.translate(0, 14)
        c.rotate(-9, cx, hy + 60)
    elif mood == "bliss":
        c.rotate(4 * math.sin(t * 9), cx, hy + 60)
    afro = p_circle(cx + 12, hy - 34, 94)
    shaded(c, afro, INK, "#0b0b10", off=(-10, -8), hi="#34343f", hi_off=(5, 4))
    halftone(c, afro, "#3b3b4a", 0.9, step=12, r=2.4)
    shaded(c, p_oval(cx + 36, hy - 14, cx + 64, hy + 24), SKIN, SKIN_DK, off=(-4, -3))
    face = p_blob([(cx - 50, hy - 40), (cx - 4, hy - 64), (cx + 50, hy - 40), (cx + 54, hy + 20),
                   (cx + 20, hy + 62), (cx - 26, hy + 64), (cx - 52, hy + 30)])
    shaded(c, face, SKIN, SKIN_DK, off=(-9, -6), hi="#a5724f", hi_off=(4, 3))
    c.drawPath(p_poly([(cx - 52, hy - 30), (cx - 60, hy - 72), (cx, hy - 104), (cx + 84, hy - 64),
                       (cx + 62, hy - 16), (cx + 36, hy - 44), (cx - 10, hy - 46)]), paint(INK))
    c.drawRoundRect(skia.Rect.MakeLTRB(cx + 26, hy - 34, cx + 36, hy + 6), 5, 5, paint(INK))
    # eye
    blink = 0.12 if (t % 3.3) < 0.11 else 1.0
    ex, ey = cx - 22, hy - 6
    if mood == "bliss":
        c.drawArc(skia.Rect.MakeLTRB(ex - 13, ey - 8, ex + 13, ey + 10), 200, 140, False, paint(INK, stroke=5))
    else:
        c.drawOval(skia.Rect.MakeLTRB(ex - 13, ey - 8 * blink, ex + 11, ey + 8 * blink), paint("#fbf6ec"))
        if blink > 0.5:
            look = -3 if mood != "sad" else -1
            c.drawCircle(ex - 3 + look, ey + (3 if mood == "sad" else 0), 6, paint(INK))
        c.drawLine(ex - 14, ey - 8 * blink, ex + 12, ey - 8 * blink, paint(INK, stroke=4))
    # brow
    if mood == "sad":
        c.drawLine(ex - 16, ey - 14, ex + 12, ey - 26, paint(INK, stroke=6))
    elif mood == "bliss":
        c.drawArc(skia.Rect.MakeLTRB(ex - 16, ey - 34, ex + 14, ey - 14), 200, 130, False, paint(INK, stroke=6))
    else:
        c.drawLine(ex - 16, ey - 22, ex + 14, ey - 18, paint(INK, stroke=6))
    # nose, moustache, mouth
    c.drawPath(p_poly([(cx - 44, hy - 4), (cx - 60, hy + 20), (cx - 40, hy + 22)]), paint(SKIN_DK))
    c.drawPath(p_blob([(cx - 54, hy + 34), (cx - 32, hy + 27), (cx - 10, hy + 33), (cx - 14, hy + 41),
                       (cx - 34, hy + 37)], 6), paint(INK))
    if mood == "bliss":
        c.drawArc(skia.Rect.MakeLTRB(cx - 46, hy + 36, cx - 16, hy + 56), 20, 140, False, paint(INK, stroke=4))
    elif mood == "sad":
        c.drawArc(skia.Rect.MakeLTRB(cx - 44, hy + 46, cx - 18, hy + 62), 200, 140, False, paint(INK, stroke=4))
    else:
        c.drawLine(cx - 42, hy + 49, cx - 22, hy + 48, paint(SKIN_DK, stroke=4))
    c.restore()


def draw_arm(c, arm, ghost=0.0):
    s, e, h, tip, tail = arm
    if ghost:
        p = paint("#aab4f0", ghost, stroke=34)
        c.drawLine(e[0], e[1], h[0], h[1], p)
        c.drawLine(tail[0], tail[1], tip[0], tip[1], paint("#f3dfae", ghost, stroke=11))
        return
    limb(c, s, e, 52, NAVY, NAVY_DK)
    c.drawLine(s[0] - 14, s[1] + 4, e[0] - 14, e[1] - 2, paint(WHITE, 0.55, stroke=3))
    limb(c, e, h, 38, SKIN, SKIN_DK)
    c.drawRoundRect(skia.Rect.MakeLTRB(e[0] + (h[0] - e[0]) * 0.72 - 20, e[1] + (h[1] - e[1]) * 0.72 - 9,
                                       e[0] + (h[0] - e[0]) * 0.72 + 20, e[1] + (h[1] - e[1]) * 0.72 + 9),
                    5, 5, paint(GOLD))
    c.drawLine(tail[0], tail[1], tip[0], tip[1], paint("#b88f4f", stroke=13))
    c.drawLine(tail[0] - 2, tail[1] - 3, tip[0] - 2, tip[1] - 3, paint("#f3dfae", stroke=5))
    c.drawCircle(tip[0], tip[1], 7, paint("#f3dfae"))
    shaded(c, p_circle(h[0], h[1], 23), SKIN, SKIN_DK, off=(-5, -4))


def draw_drummer(c, t, playing, mood, trail=0):
    pose = drummer_pose(t, playing)
    bob, sway = pose["bob"], pose["sway"]

    # cymbals behind the kit, wobbling after hits
    st = paint("#55565e", stroke=7)
    for x, top in ((300, 930), (815, 980)):
        c.drawLine(x, top, x, 1380, st)
        c.drawLine(x - 42, 1380, x, 1330, st)
        c.drawLine(x + 42, 1380, x, 1330, st)
    dtk, vk = last_hit(t, ("kick",))
    crash = 10 * math.exp(-dtk * 5) * math.sin(dtk * 26) if (playing and vk >= 1.0) else 0
    draw_cymbal(c, 300, 925, 108, -14, wob=crash, glint=math.exp(-dtk * 6) if (playing and vk >= 1.0) else 0)
    draw_cymbal(c, 815, 975, 118, 10, wob=1.5 * math.sin(t * 3))

    # legs (knees peek out either side of the bass drum)
    pants, pants_dk = "#ece2cc", "#c7b796"
    kick_e = hit_env(t, ("kick",), 14) if playing else 0
    limb(c, (515, 1180), (432, 1245), 56, pants, pants_dk)
    limb(c, (432, 1245), (420, 1360), 46, pants, pants_dk)
    limb(c, (605, 1180), (684, 1245), 56, pants, pants_dk)
    limb(c, (684, 1245), (640, 1355), 46, pants, pants_dk)
    c.drawRoundRect(skia.Rect.MakeLTRB(384, 1356, 446, 1384), 12, 12, paint(INK))
    c.save()
    c.rotate(-10 * (1 - kick_e), 650, 1380)
    c.drawRoundRect(skia.Rect.MakeLTRB(588, 1356, 656, 1384), 12, 12, paint(INK))
    c.restore()

    # torso
    c.save()
    c.rotate(sway * 0.35, 560, 1200)
    oy = bob * 0.6
    neck = p_rrect(538, 915 + bob, 586, 975 + bob, 12)
    shaded(c, neck, SKIN_DK, "#55341f", off=(-6, 0))
    torso = p_blob([(470, 990 + oy), (520, 952 + oy), (604, 952 + oy), (652, 990 + oy), (664, 1120),
                    (650, 1205), (474, 1205), (458, 1120)])
    shaded(c, torso, NAVY, NAVY_DK, off=(-16, -10), hi="#3a40ad", hi_off=(7, 5))
    c.drawPath(p_poly([(526, 954 + oy), (562, 1020 + oy), (598, 954 + oy)]), paint("#f1e7d2"))
    c.drawPath(path_of([(530, 960 + oy), (562, 1030 + oy), (594, 960 + oy)]), paint(WHITE, 0.9, stroke=5))
    c.drawPath(path_of([(488, 1000 + oy), (478, 1080), (482, 1180)]), paint(WHITE, 0.55, stroke=4))
    draw_head(c, t, 560, 870 + bob, mood)
    c.restore()

    # bass drum
    shaded(c, p_circle(540, 1250, 130), SHELL, "#8e231c", off=(-8, -8), hi="#e2554a", hi_off=(4, 4))
    hg = skia.GradientShader.MakeRadial((515, 1225), 140, [col("#fbf7f0"), col("#e6ddcc")])
    c.drawCircle(540, 1250, 112, paint(WHITE, shader=hg))
    for k in range(10):
        a = math.radians(k * 36 + 18)
        c.save()
        c.translate(540 + 121 * math.cos(a), 1250 + 121 * math.sin(a))
        c.rotate(math.degrees(a))
        c.drawRoundRect(skia.Rect.MakeLTRB(-9, -5, 9, 5), 3, 3, paint(CHROME))
        c.restore()
    c.drawCircle(540, 1250, 120, paint(CHROME, stroke=7))
    c.drawCircle(540, 1250, 54, paint(SHELL))
    c.drawCircle(540, 1250, 46, paint("#f4efe6", stroke=3))
    draw_text(c, "1970", 540, 1262, font("ExtraBold", 32), "#f4efe6", align="center")
    if kick_e > 0.02:
        c.drawCircle(540, 1250, 112, paint(WHITE, 0.35 * kick_e))
        c.drawCircle(540, 1250, 130 + 50 * (1 - kick_e), paint(WHITE, 0.6 * kick_e, stroke=5))
    beater = 1250 + 60 - 22 * (1 - kick_e)
    c.drawLine(570, 1378, 575, beater + 30, paint("#55565e", stroke=6))
    c.drawCircle(575, beater + 30, 9, paint(INK))

    # rack tom, floor tom
    draw_drum_shell(c, 540, 1068, 124, 58)
    c.drawLine(712, 1290, 712, 1380, st)
    c.drawLine(812, 1290, 812, 1380, st)
    draw_drum_shell(c, 762, 1200, 134, 95)

    # snare on its stand
    dts, vs = last_hit(t, ("snare",))
    c.drawLine(395, 1180, 395, 1380, st)
    c.drawLine(395, 1330, 350, 1380, st)
    c.drawLine(395, 1330, 440, 1380, st)
    draw_drum_shell(c, 395, 1138, 164, 46, body="#d9dbe0",
                    squash=(math.exp(-dts * 25) * vs if playing else 0))

    # hi-hat
    dth, _ = last_hit(t, ("hat",))
    hw = 6 * math.exp(-dth * 7) * math.sin(dth * 38) if playing else 0
    c.drawLine(700, 1080, 700, 1380, st)
    c.drawLine(700, 1330, 660, 1380, st)
    c.drawLine(700, 1330, 740, 1380, st)
    open_ = 3 + 5 * pose["hat_h"]
    draw_cymbal(c, 700, 1080 + open_, 80, 4)
    draw_cymbal(c, 700, 1074 - open_, 80, 4 + hw)

    # arms: afterimages, smear, then the real arms
    for k in range(trail, 0, -1):
        pk = drummer_pose(t - k * 0.035, playing)
        a = 0.28 * (1 - k / (trail + 1))
        draw_arm(c, pk["left"], ghost=a)
        draw_arm(c, pk["right"], ghost=a)
    if playing:
        prev = drummer_pose(t - 0.045, playing)
        for side in ("left", "right"):
            _, _, h0, t0, _ = prev[side]
            _, _, h1, t1, _ = pose[side]
            if np.linalg.norm(t1 - t0) > 12:
                c.drawPath(p_poly([tuple(h0), tuple(t0), tuple(t1), tuple(h1)]), paint(WHITE, 0.4))
    draw_arm(c, pose["left"])
    draw_arm(c, pose["right"])

    # impact ring + sparks on accented snare hits
    if playing and dts < 0.25 and vs > 0.5:
        p = dts / 0.25
        rx = 70 + 120 * ease_out(p)
        c.drawOval(skia.Rect.MakeLTRB(395 - rx, 1128 - rx * 0.24, 395 + rx, 1128 + rx * 0.24),
                   paint(WHITE, 0.8 * (1 - p), stroke=6))
        for k in range(7):
            a = math.radians(-160 + k * 23)
            r0, r1 = 50 + 110 * ease_out(p), 80 + 140 * ease_out(p)
            c.drawLine(395 + math.cos(a) * r0, 1110 + math.sin(a) * r0 * 0.8,
                       395 + math.cos(a) * r1, 1110 + math.sin(a) * r1 * 0.8,
                       paint("#fff3c8", 1 - p, stroke=6))


def draw_meter(c, t, rise, alarm):
    """Royalty gauge: a test-tube on a post with a '$0' tag (like a rain gauge)."""
    if rise <= 0:
        return
    c.save()
    c.translate(0, (1 - ease_out(rise)) * 520)
    x = 930
    c.drawRect(skia.Rect.MakeLTRB(x - 9, 1150, x + 9, 1420), paint("#7a5130"))
    tube = skia.Rect.MakeLTRB(x - 26, 960, x + 26, 1170)
    c.drawRoundRect(tube, 20, 20, paint("#f7f4ee", 0.95))
    c.drawRoundRect(tube, 20, 20, paint("#9da2ad", stroke=4))
    for i in range(9):
        yy = 990 + i * 20
        c.drawLine(x - 26, yy, x - (6 if i % 2 else -2), yy, paint("#9da2ad", stroke=3))
    c.drawRoundRect(skia.Rect.MakeLTRB(x - 34, 940, x + 34, 966), 6, 6, paint(RED))
    f = font("ExtraBold", 13)
    c.save()
    c.translate(x + 14, 1150)
    c.rotate(-90)
    draw_text(c, "ROYALTIES", 0, 0, f, "#9da2ad")
    c.restore()
    flash = 0.5 + 0.5 * math.sin(t * 14) if alarm else 1.0
    tag = skia.Rect.MakeLTRB(x + 34, 1040, x + 120, 1090)
    c.drawRoundRect(tag, 10, 10, paint(RED if flash > 0.4 else "#ff7a6b"))
    draw_text(c, "$0", x + 77, 1078, font("ExtraBold", 38), WHITE, align="center")
    c.restore()


def squash_in(t, t_in, dur=0.5):
    """(sx, sy) for a springy pop-in from the feet."""
    k = clamp((t - t_in) / dur)
    if k >= 1:
        return 1.0, 1.0
    sy = max(0.001, back_out(k, 2.6))
    return 1 + 0.35 * (1 - k) * math.sin(k * math.pi), sy


def draw_band(c, t, T, E):
    """Bandleader (cape + mic) on the right, bassist on the left."""
    a = window(t, T["band"] - 0.05, E["dropout"] + 1.3, 0.05, 0.3)
    if a <= 0:
        return
    drop = T["dropout"]
    leave = smooth((t - drop - 0.6) / 0.9)
    hop = -150 * math.sin(math.pi * clamp((t - drop - 0.6) / 0.9))
    singing = t < drop + 0.3
    beat = 2 * math.pi * t * BPM / 60
    c.saveLayerAlpha(None, int(255 * a))

    # bandleader
    bx = 900
    sx, sy = squash_in(t, T["band"] + 0.05)
    c.save()
    c.translate(560 * leave, hop)
    c.translate(bx, 1380)
    c.scale(sx, sy)
    c.translate(-bx, -1380)
    sway = 7 * math.sin(beat / 2) if singing else 0
    limb(c, (bx - 20, 1170), (bx - 34 + sway * 0.4, 1372), 32, "#26262e", INK)
    limb(c, (bx + 20, 1170), (bx + 34, 1372), 32, "#26262e", INK)
    c.drawRoundRect(skia.Rect.MakeLTRB(bx - 66 + sway * 0.4, 1360, bx - 10, 1384), 10, 10, paint(INK))
    c.drawRoundRect(skia.Rect.MakeLTRB(bx + 8, 1360, bx + 70, 1384), 10, 10, paint(INK))
    cape = p_blob([(bx - 70, 960), (bx + 70, 960), (bx + 128 + sway, 1330), (bx + 10, 1350), (bx - 116 + sway, 1330)])
    shaded(c, cape, "#c21d33", "#7e0f1e", off=(-14, -6), hi="#e8475a")
    for k in range(14):
        tw = 0.5 + 0.5 * math.sin(t * 6 + k * 1.7)
        c.drawCircle(bx - 80 + 160 * hash01("sp", k) + sway * hash01("sq", k),
                     1000 + 320 * hash01("sy", k), 3 + 3 * tw, paint("#ffd977", 0.4 + 0.6 * tw))
    shirt = p_rrect(bx - 52, 950, bx + 52, 1190, 30)
    shaded(c, shirt, "#f4efe6", "#cfc6b4", off=(-10, -6))
    c.drawLine(bx, 962, bx, 1190, paint(INK, stroke=4))
    hx = bx + sway * 0.3
    shaded(c, p_oval(hx - 44, 832, hx + 40, 944), "#7b4a2e", "#5c3520", off=(-7, -5), hi="#946043")
    hair = p_blob([(hx - 52, 874), (hx - 44, 804), (hx + 4, 774), (hx + 58, 800), (hx + 50, 870), (hx + 10, 834),
                   (hx - 30, 846)])
    shaded(c, hair, INK, "#0b0b10", off=(-6, -6), hi="#34343f")
    halftone(c, hair, "#3b3b4a", 0.8, step=11, r=2.0)
    c.drawCircle(hx - 24, 884, 5, paint(INK))
    c.drawLine(hx - 36, 868, hx - 12, 870, paint(INK, stroke=5))
    mouth = (0.3 + 0.7 * abs(math.sin(t * 8.5))) if singing else (0.9 if t < drop + 0.9 else 0.2)
    c.drawOval(skia.Rect.MakeLTRB(hx - 36, 912 - 2, hx - 18, 912 + 14 * mouth), paint("#3a1610"))
    # mic stand + mic
    c.drawLine(bx - 120, 950, bx - 120, 1380, paint("#55565e", stroke=6))
    c.drawLine(bx - 150, 1380, bx - 90, 1380, paint("#55565e", stroke=6))
    c.drawLine(bx - 120, 950, bx - 62, 908, paint("#55565e", stroke=6))
    c.drawRoundRect(skia.Rect.MakeLTRB(bx - 76, 884, bx - 46, 926), 12, 12, paint(INK))
    halftone(c, p_rrect(bx - 76, 884, bx - 46, 904, 12), "#666666", 1, step=6, r=1.5)
    # mic arm
    limb(c, (bx - 30, 990), (bx - 66, 1060), 30, "#f4efe6", "#cfc6b4")
    limb(c, (bx - 66, 1060), (bx - 60, 935), 25, "#7b4a2e", "#5c3520")
    # free arm: swings on the beat, then points at the drummer ("give the drummer some")
    point = smooth((t - drop - 0.05) / 0.3) * (1 - leave)
    elbow = (lerp(bx + 70, bx - 110, point), lerp(1060 + 20 * math.sin(beat), 975, point))
    hand = (lerp(bx + 60, bx - 220, point), lerp(960 + 30 * math.sin(beat), 935, point))
    limb(c, (bx + 36, 990), elbow, 30, "#f4efe6", "#cfc6b4")
    limb(c, elbow, hand, 25, "#7b4a2e", "#5c3520")
    c.drawCircle(hand[0], hand[1], 15, paint("#7b4a2e"))
    if point > 0.5:
        c.drawLine(hand[0] - 4, hand[1], hand[0] - 34, hand[1] - 2, paint("#7b4a2e", stroke=9))
    c.restore()

    # bassist
    gx = 140
    sx, sy = squash_in(t, T["band"] + 0.2)
    nod = 10 * hit_env(t, ("kick",), 7) if singing else 0
    c.save()
    c.translate(-560 * leave, hop)
    c.translate(gx, 1380)
    c.scale(sx, sy)
    c.translate(-gx, -1380)
    limb(c, (gx - 18, 1170), (gx - 30, 1372), 30, "#2c3e50", "#1b2733")
    limb(c, (gx + 18, 1170), (gx + 30, 1372), 30, "#2c3e50", "#1b2733")
    c.drawRoundRect(skia.Rect.MakeLTRB(gx - 62, 1360, gx - 8, 1384), 10, 10, paint(INK))
    c.drawRoundRect(skia.Rect.MakeLTRB(gx + 6, 1360, gx + 64, 1384), 10, 10, paint(INK))
    shaded(c, p_rrect(gx - 52, 960, gx + 52, 1190, 30), "#2f8a74", "#1f5e4f", off=(-10, -6), hi="#45a88f")
    c.drawRect(skia.Rect.MakeLTRB(gx - 9, 925, gx + 13, 965), paint(SKIN_DK))
    c.save()
    c.rotate(nod * 0.6, gx, 950)
    afro = p_circle(gx + 6, 872, 60)
    shaded(c, afro, INK, "#0b0b10", off=(-6, -5), hi="#34343f")
    halftone(c, afro, "#3b3b4a", 0.8, step=11, r=2.0)
    shaded(c, p_oval(gx - 32, 868, gx + 44, 962), SKIN_DK, "#55341f", off=(-6, -4))
    c.drawCircle(gx + 22, 904, 5, paint(INK))
    c.drawLine(gx + 12, 930, gx + 30, 930, paint("#3a1610", stroke=4))
    c.restore()
    c.save()
    c.translate(gx, 1100)
    c.rotate(-32)
    shaded(c, p_blob([(-70, -30), (-20, -46), (40, -40), (66, 0), (40, 42), (-20, 46), (-70, 30)]),
           "#e0822e", "#a85a18", off=(-6, -5), hi="#f2a35a")
    c.drawCircle(-6, 0, 12, paint(INK))
    c.drawRect(skia.Rect.MakeLTRB(50, -9, 270, 9), paint("#5a3a1e"))
    for k in range(6):
        c.drawLine(80 + k * 30, -9, 80 + k * 30, 9, paint("#c9ccd3", stroke=2))
    c.drawRoundRect(skia.Rect.MakeLTRB(262, -15, 302, 15), 5, 5, paint(INK))
    c.restore()
    strum = 14 * math.sin(beat * 2) if singing else 0
    limb(c, (gx + 30, 990), (gx + 30, 1080), 26, "#2f8a74", "#1f5e4f")
    limb(c, (gx + 30, 1080), (gx - 4 + strum, 1110), 22, SKIN_DK, "#55341f")
    c.restore()
    c.restore()


def draw_producer(c, t, T, E):
    """Producer at a table with a pad sampler, around world x=1520."""
    a = window(t, T["sampled"], T["royalty"] + 0.3, 0.05, 0.5)
    if a <= 0:
        return
    px = 1520
    sx, sy = squash_in(t, T["sampled"] + 0.1)
    tap = drum_state(t, ("snare", "kick"))
    nod = 9 * hit_env(t, ("kick", "snare"), 7)
    c.saveLayerAlpha(None, int(255 * a))
    c.save()
    c.translate(px, 1380)
    c.scale(sx, sy)
    c.translate(-px, -1380)
    # chair
    c.drawRoundRect(skia.Rect.MakeLTRB(px + 40, 1000, px + 96, 1230), 20, 20, paint("#3b3b46"))
    c.drawLine(px + 70, 1230, px + 70, 1380, paint("#55565e", stroke=8))
    # body + head
    body = p_blob([(px - 80, 1000), (px - 20, 955), (px + 60, 965), (px + 86, 1060), (px + 80, 1190), (px - 78, 1190)])
    shaded(c, body, "#2f8a8a", "#1d5d5d", off=(-12, -8), hi="#46a7a7")
    c.drawPath(path_of([(px - 40, 980), (px - 30, 1040)]), paint(WHITE, 0.8, stroke=4))
    c.save()
    c.rotate(nod, px, 950)
    shaded(c, p_oval(px - 50, 810, px + 46, 935), "#c98f62", "#a06c44", off=(-7, -5), hi="#dba67b")
    cap = p_blob([(px - 56, 842), (px - 44, 790), (px + 20, 778), (px + 58, 812), (px + 54, 846)])
    shaded(c, cap, "#e04f3f", "#a8352a", off=(-5, -5), hi="#f07a6b")
    c.drawRoundRect(skia.Rect.MakeLTRB(px - 118, 830, px - 30, 846), 7, 7, paint("#c43f31"))
    c.drawArc(skia.Rect.MakeLTRB(px - 64, 796, px + 64, 936), 195, 150, False, paint(INK, stroke=11))
    shaded(c, p_rrect(px + 30, 852, px + 68, 910, 14), "#2b2b33", INK, off=(-4, -3))
    blink = 0.15 if (t % 2.9) < 0.1 else 1
    c.drawOval(skia.Rect.MakeLTRB(px - 34, 870 - 6 * blink, px - 18, 870 + 6 * blink), paint(INK))
    c.drawLine(px - 40, 902, px - 22, 900, paint("#7a4a2e", stroke=4))
    c.restore()
    # table + sampler
    shaded(c, p_rrect(px - 230, 1178, px + 230, 1208, 6), "#7a4e2c", "#563620", off=(0, -5))
    c.drawLine(px - 196, 1206, px - 196, 1380, paint("#563620", stroke=16))
    c.drawLine(px + 196, 1206, px + 196, 1380, paint("#563620", stroke=16))
    shaded(c, p_rrect(px - 180, 1100, px + 70, 1182, 12), "#9a9ca4", "#6e7078", off=(-6, -6), hi="#c4c6cc")
    c.drawRoundRect(skia.Rect.MakeLTRB(px - 168, 1114, px - 76, 1140), 4, 4, paint("#35603a"))
    lvl = 0.3 + 0.7 * tap
    c.drawRect(skia.Rect.MakeLTRB(px - 162, 1120, px - 162 + 80 * lvl, 1134), paint("#8ee36a"))
    lit = int(t / STEP) % 8
    for i in range(4):
        for j in range(2):
            on = (i + 4 * j == lit) and tap > 0.3
            r = skia.Rect.MakeLTRB(px - 62 + i * 30, 1112 + j * 30, px - 38 + i * 30, 1136 + j * 30)
            c.drawRoundRect(r, 4, 4, paint(RED if on else "#d5d7dd"))
            if on:
                c.drawRoundRect(r.makeOutset(5, 5), 7, 7, paint(RED, 0.35))
    # arm tapping pads
    hand = (px - 22, 1104 - 34 * tap)
    limb(c, (px - 40, 1000), (px - 112, 1086), 40, "#2f8a8a", "#1d5d5d")
    limb(c, (px - 112, 1086), hand, 30, "#c98f62", "#a06c44")
    shaded(c, p_circle(hand[0], hand[1], 18), "#c98f62", "#a06c44", off=(-4, -3))
    c.restore()
    c.restore()


# ---- the hero "sound wave" curl

WAVE_CTRL = [(395, 1110), (250, 1040), (150, 860), (150, 600), (300, 380), (520, 320),
             (720, 420), (760, 600), (660, 720), (520, 690), (480, 570), (560, 520), (610, 570)]
WAVE_PTS, WAVE_LEN = resample(catmull(WAVE_CTRL), 6.0)
_tang = np.gradient(WAVE_PTS, axis=0)
_tang /= np.linalg.norm(_tang, axis=1, keepdims=True) + 1e-9
WAVE_NRM = np.stack([-_tang[:, 1], _tang[:, 0]], 1)
WAVE_S = np.linspace(0, 1, len(WAVE_PTS))
WAVE_W = 30 + 180 * np.sin(np.pi * np.clip(WAVE_S * 1.15, 0, 1)) ** 1.3 * (1 - 0.72 * WAVE_S)
WAVE_EDGES = [path_of([tuple(p) for p in WAVE_PTS + WAVE_NRM * (WAVE_W * f)[:, None]]) for f in (-0.5, 0.5)]
WAVE_BANDS = [(-0.5, 0.5, "#14318f"), (-0.36, 0.5, "#2152c4"), (-0.12, 0.45, "#3a80e3"),
              (0.14, 0.4, "#78bdfc"), (0.28, 0.34, "#e9f5ff")]


def ribbon(pts, nrm, w, f0, f1):
    a = pts + nrm * (w * f0)[:, None]
    b = pts + nrm * (w * f1)[:, None]
    return p_poly([tuple(p) for p in np.concatenate([a, b[::-1]])])


def draw_note(c, x, y, s, color, a, rot):
    c.save()
    c.translate(x, y)
    c.rotate(rot)
    c.save()
    c.rotate(-20)
    c.drawOval(skia.Rect.MakeLTRB(-s * 0.55, -s * 0.36, s * 0.55, s * 0.36), paint(color, a))
    c.restore()
    c.drawLine(s * 0.46, -s * 0.1, s * 0.46, -s * 2.1, paint(color, a, stroke=s * 0.17))
    c.drawPath(path_of([(s * 0.46, -s * 2.1), (s * 1.1, -s * 1.6), (s * 0.95, -s * 1.0)]),
               paint(color, a, stroke=s * 0.17))
    c.restore()


def draw_wave(c, t, grow, fade, tl):
    """Layered-ribbon water curl whose edge ripples like a sound wave."""
    n = len(WAVE_PTS)
    upto = int(n * clamp(grow))
    if upto < 6 or fade <= 0:
        return
    idx = np.arange(upto)
    s = WAVE_S[:upto]
    w = WAVE_W[:upto] * (1 + 0.11 * np.sin(s * 60 - t * 10) + 0.05 * np.sin(s * 150 - t * 19))
    w = w * np.clip((upto - idx) / 22, 0.2, 1)
    pts, nrm = WAVE_PTS[:upto], WAVE_NRM[:upto]
    c.saveLayerAlpha(None, int(255 * fade))
    c.drawPath(ribbon(pts + np.array([14, 12]), nrm, w, -0.5, 0.5), paint("#6b5232", 0.16))
    for f0, f1, cc in WAVE_BANDS:
        c.drawPath(ribbon(pts, nrm, w, f0, f1), paint(cc))
    for f, dash, sp, al, sw in ((0.02, [60, 90], 420, 0.45, 5), (-0.25, [30, 120], 300, 0.35, 4),
                                (0.36, [18, 50], 520, 0.85, 3)):
        line = pts + nrm * (w * f)[:, None]
        eff = skia.DashPathEffect.Make(dash, -t * sp)
        c.drawPath(path_of([tuple(p) for p in line]), paint(WHITE, al, stroke=sw, effect=eff))
    # foam at the crest
    head = pts[-1]
    for k in range(10):
        r = 7 + 16 * hash01("fo", k)
        ang = hash01("fa", k) * 2 * math.pi
        d = 10 + 30 * hash01("fd", k) + 4 * math.sin(t * 7 + k)
        c.drawCircle(head[0] + math.cos(ang) * d, head[1] + math.sin(ang) * d, r, paint(WHITE, 0.92))
    # droplets thrown off the edge
    for i in range(48):
        tb = i * 0.085 + 0.05 * hash01("db", i)
        age = tl - tb
        if not (0 < age < 0.9):
            continue
        j = int(hash01("di", i) * (upto - 1))
        side = 1 if hash01("ds", i) > 0.35 else -1
        p0 = pts[j] + nrm[j] * w[j] * 0.5 * side
        v = nrm[j] * side * (180 + 260 * hash01("dv", i)) + np.array([0, -120])
        pos = p0 + v * age + np.array([0, 450 * age * age])
        vel = v + np.array([0, 900 * age])
        r = (4 + 9 * hash01("dr", i)) * (1 - age / 0.9)
        cc = WHITE if i % 3 else "#7cc0ff"
        c.drawLine(pos[0], pos[1], pos[0] - vel[0] * 0.03, pos[1] - vel[1] * 0.03, paint(cc, 0.45, stroke=r * 1.1))
        c.drawCircle(pos[0], pos[1], r, paint(cc, 0.95))
    # music notes drifting up out of the wave
    for i in range(8):
        tb = i * 0.4 + 0.3 * hash01("nb", i)
        age = tl - tb
        if not (0 < age < 2.2):
            continue
        j = int((0.15 + 0.7 * hash01("nj", i)) * (upto - 1))
        x = pts[j][0] + 40 * math.sin(age * 3 + i)
        y = pts[j][1] - 150 * age
        draw_note(c, x, y, 22 + 10 * hash01("ns", i), NAVY if i % 2 else "#2152c4",
                  window(age, 0, 2.2, 0.3, 0.6), 15 * math.sin(age * 4 + i))
    c.restore()


def draw_dashed_curl(c, t, a, draw_on=1.0, w=6):
    if a <= 0 or draw_on <= 0:
        return
    eff = skia.DashPathEffect.Make([24, 15], -t * 40)
    for edge in WAVE_EDGES:
        c.drawPath(trimmed(edge, 0, draw_on), paint(RED, a, stroke=w, effect=eff))


def draw_waveform_strip(c, t, a, hl, cx=540, y=560, w=760):
    """Horizontal track overview with the 20s break highlighted."""
    if a <= 0:
        return
    c.saveLayerAlpha(None, int(255 * a))
    r = skia.Rect.MakeLTRB(cx - w / 2, y - 70, cx + w / 2, y + 70)
    c.drawRoundRect(r, 22, 22, paint("#fbf6ec"))
    c.drawRoundRect(r, 22, 22, paint(NAVY, stroke=4))
    bars = 90
    x0 = cx - w / 2 + 24
    step = (w - 48) / bars
    b0, b1 = 70, 82
    for i in range(bars):
        amp = 0.25 + 0.75 * abs(math.sin(i * 0.7) * math.sin(i * 0.13 + 2)) * (0.6 + 0.4 * hash01("wf", i))
        inbreak = b0 <= i < b1
        if inbreak:
            amp = 0.55 + 0.45 * abs(math.sin(i * 1.9))
        h = 52 * amp
        c.drawLine(x0 + i * step, y - h, x0 + i * step, y + h,
                   paint(RED if inbreak and hl > 0 else "#7d83b5", stroke=step * 0.6))
    if hl > 0:
        bx0, bx1 = x0 + b0 * step - 8, x0 + b1 * step
        eff = skia.DashPathEffect.Make([12, 8], -t * 30)
        c.drawRoundRect(skia.Rect.MakeLTRB(bx0, y - 82, bx1, y + 82), 12, 12,
                        paint(RED, hl, stroke=5, effect=eff))
        f = font("ExtraBold", 28)
        lbl = skia.Rect.MakeLTRB((bx0 + bx1) / 2 - 56, y - 130, (bx0 + bx1) / 2 + 56, y - 90)
        c.drawRoundRect(lbl, 10, 10, paint(RED, hl))
        draw_text(c, "0:20", (bx0 + bx1) / 2, y - 99, f, WHITE, a=hl, align="center")
    f = font("Bold", 24)
    draw_text(c, "FUNKY DRUMMER  ·  1970", cx - w / 2 + 24, y + 108, f, NAVY)
    c.restore()


# --------------------------------------------------------------------------
# drawing: screen-space UI

def draw_record(c, x, y, r, rot, label, alpha=1.0):
    c.save()
    c.translate(x, y)
    c.rotate(rot)
    c.drawCircle(4, 8, r, paint(INK, 0.25 * alpha))
    c.drawCircle(0, 0, r, paint("#141418", alpha))
    for k in range(6):
        c.drawCircle(0, 0, r * (0.5 + k * 0.08), paint("#2a2a33", alpha, stroke=2))
    c.drawArc(skia.Rect.MakeLTRB(-r * 0.9, -r * 0.9, r * 0.9, r * 0.9), -60, 35, False,
              paint(WHITE, 0.22 * alpha, stroke=r * 0.18, cap=skia.Paint.kButt_Cap))
    c.drawArc(skia.Rect.MakeLTRB(-r * 0.9, -r * 0.9, r * 0.9, r * 0.9), 120, 35, False,
              paint(WHITE, 0.12 * alpha, stroke=r * 0.18, cap=skia.Paint.kButt_Cap))
    c.drawCircle(0, 0, r * 0.36, paint(label, alpha))
    c.drawCircle(0, -r * 0.18, r * 0.05, paint(WHITE, 0.6 * alpha))
    c.drawCircle(0, 0, r * 0.045, paint(CREAM, alpha))
    c.restore()


def draw_notes_card(c, t, t_in, t_out, line2_t):
    a = window(t, t_in, t_out, 0.01, 0.3)
    if a <= 0:
        return
    k = back_out((t - t_in) / 0.45)
    c.save()
    c.translate(70, 190)
    c.rotate(-2.5 + (1 - k) * -8)
    c.scale(0.6 + 0.4 * k, 0.6 + 0.4 * k)
    c.saveLayerAlpha(None, int(255 * a))
    r = skia.Rect.MakeLTRB(0, 0, 610, 300)
    c.drawRect(skia.Rect.MakeLTRB(8, 12, 618, 312), paint(INK, 0.18))
    c.drawRect(r, paint("#fbf8f1"))
    for i in range(6):
        c.drawLine(28, 110 + i * 34, 582, 110 + i * 34, paint("#d9d3c6", stroke=2))
    draw_text(c, "1970  ·  LINER NOTES", 28, 50, font("ExtraBold", 24), NAVY)
    c.drawLine(28, 66, 582, 66, paint(RED, stroke=3))
    draw_text(c, "Funky Drummer.", 28, 140, font("ExtraBold", 54), NAVY_DK)
    draw_text(c, "James Brown", 28, 190, font("SemiBold", 30), "#5b5e78")
    if t >= line2_t:
        k2 = back_out((t - line2_t) / 0.4)
        c.save()
        c.translate(28, 250)
        c.scale(k2, k2)
        draw_text(c, "Drums: Clyde Stubblefield", 0, 0, font("ExtraBold", 34), RED)
        c.restore()
    c.restore()
    c.restore()


def draw_glitch_title(c, t, t0, t1, l1, l2):
    a = window(t, t0, t1, 0.05, 0.2)
    if a <= 0:
        return
    c.drawRect(skia.Rect.MakeWH(W, H), paint(CREAM, 0.55 * a))
    f = font("ExtraBold", 142)
    fr = int(t * 30) // 2
    lines = [(l1, NAVY_DK, 470), (l2, RED, 630)]
    for band in range(14):
        y0 = 330 + band * 26
        dx = (hash01("g", band, fr) - 0.5) * 70 * (1 if hash01("on", band, fr) > 0.6 else 0.1)
        c.save()
        c.clipRect(skia.Rect.MakeLTRB(0, y0, W, y0 + 26))
        for txt, color, y in lines:
            draw_text(c, txt, 60 + dx + 6, y, f, "#3fd0ff", a=0.5 * a)
            draw_text(c, txt, 60 + dx - 6, y, f, "#ff3f6c", a=0.5 * a)
            draw_text(c, txt, 60 + dx, y, f, color, a=a)
        c.restore()
    for k in range(9):
        yy = 300 + hash01("ln", k, fr) * 900
        c.drawLine(0, yy, W, yy, paint(NAVY, 0.5 * a, stroke=2))


def draw_ig_glyph(c, x, y, s, color_or_shader, a=1.0):
    if isinstance(color_or_shader, str):
        p = paint(color_or_shader, a, stroke=s * 0.11)
        pf = paint(color_or_shader, a)
    else:
        p = paint(WHITE, a, stroke=s * 0.11, shader=color_or_shader)
        pf = paint(WHITE, a, shader=color_or_shader)
    c.drawRoundRect(skia.Rect.MakeLTRB(x - s / 2, y - s / 2, x + s / 2, y + s / 2), s * 0.28, s * 0.28, p)
    c.drawCircle(x, y, s * 0.22, p)
    c.drawCircle(x + s * 0.26, y - s * 0.26, s * 0.055, pf)


def draw_watermark(c, t, handle, slot):
    pos = [(W - 200, 250), (130, 1640)][slot]
    draw_ig_glyph(c, pos[0], pos[1] - 40, 34, WHITE, 0.75)
    draw_text(c, handle.upper(), pos[0], pos[1], font("Bold", 22), WHITE, a=0.85,
              outline=INK, ow=4, align="center")


def draw_captions(c, t, chunks):
    for ch in chunks:
        if not (ch["start"] <= t < ch["end"]):
            continue
        f = font("ExtraBold", 70)
        space = 20
        widths = [text_w(f, w) for w, _, _ in ch["words"]]
        total = sum(widths) + space * (len(widths) - 1)
        pop = back_out((t - ch["start"]) / 0.22, 2.4)
        c.save()
        cy = 1520
        c.translate(W / 2, cy)
        c.scale(0.75 + 0.25 * pop, 0.75 + 0.25 * pop)
        x = -total / 2
        for (w, w0, w1), ww in zip(ch["words"], widths):
            active = w0 <= t < max(w1, w0 + 0.12) or (t >= w1 and (w, w0, w1) == ch["words"][-1])
            if active:
                k = back_out((t - w0) / 0.16, 3)
                pad = 12
                rr = skia.Rect.MakeLTRB(x - pad, -58, x + ww + pad, 22)
                c.save()
                c.translate(x + ww / 2, -18)
                c.scale(0.85 + 0.15 * k, 0.85 + 0.15 * k)
                c.translate(-(x + ww / 2), 18)
                c.drawRoundRect(rr, 14, 14, paint(RED))
                c.restore()
                draw_text(c, w, x, 0, f, WHITE, outline="#7a1d16", ow=6)
            else:
                draw_text(c, w, x, 0, f, WHITE, outline=INK, ow=12)
            x += ww + space
        c.restore()


def draw_outro(c, t, t0, cfg):
    a = smooth((t - t0) / 0.5)
    if a <= 0:
        return
    c.drawRect(skia.Rect.MakeWH(W, H), paint("#0d0d10", 0.68 * a))
    brand = cfg.get("brand", "")
    acc = cfg.get("brand_accent_index", -1)
    f = font("ExtraBold", 112)
    widths = [text_w(f, ch) for ch in brand]
    x = W / 2 - sum(widths) / 2
    for i, (ch, w) in enumerate(zip(brand, widths)):
        k = back_out((t - t0 - 0.06 * i) / 0.35)
        if k <= 0:
            x += w
            continue
        c.save()
        c.translate(x + w / 2, 300)
        c.rotate((hash01("b", i) - 0.5) * 14)
        c.scale(k, k)
        color = RED if i == acc else "#f4efe6"
        draw_text(c, ch, 0, 0, f, color, outline=INK, ow=8, align="center")
        c.restore()
        x += w
    k = back_out((t - t0 - 0.2) / 0.4)
    c.save()
    c.translate(W / 2, 880)
    c.scale(k, k)
    grad_on = smooth((t - t0 - 1.1) / 0.4)
    draw_ig_glyph(c, 0, 0, 150, WHITE, a * (1 - grad_on))
    if grad_on > 0:
        sh = skia.GradientShader.MakeLinear([(-75, 75), (75, -75)],
                                            [col("#feda75"), col("#fa7e1e"), col("#d62976"), col("#962fbf"),
                                             col("#4f5bd5")])
        draw_ig_glyph(c, 0, 0, 150, sh, a * grad_on)
    c.restore()
    draw_text(c, cfg["handle"].upper(), W / 2, 1020, font("Bold", 44), WHITE, a=a * smooth((t - t0 - 0.4) / 0.3),
              align="center")


# --------------------------------------------------------------------------
# scene direction

def camera_keys(T, total):
    # (time, transition seconds, zoom, cx, cy) - cx/cy is the world point at screen centre
    return [
        (0.0, 0.0, 1.06, 520, 900),
        (T["older"] + 0.6, 0.6, 0.86, 560, 1000),          # widen for the band
        (T["solo"] - 0.05, 0.5, 1.55, 540, 1060),         # push in on the solo
        (T["twenty"], 0.5, 1.0, 540, 960),
        (T["sampled"] + 0.1, 0.8, 0.62, 1000, 1010),      # reveal the producer
        (T["names"] - 0.2, 0.5, 0.62, 1000, 1010),
        (T["royalty"], 0.7, 1.0, 600, 960),
        (T["royalty2"], 0.5, 2.0, 930, 1060),            # zoom on the $0 tag
        (T["everywhere"], 0.6, 1.0, 520, 900),
        (T["almost"] + 0.6, 1.6, 1.12, 520, 920),
    ]


def camera_at(keys, t):
    z, cx, cy = keys[0][2:]
    for kt, kd, kz, kx, ky in keys[1:]:
        if t < kt:
            break
        p = smooth((t - kt) / kd) if kd else 1
        z, cx, cy = lerp(z, kz, p), lerp(cx, kx, p), lerp(cy, ky, p)
    z *= 1 + 0.012 * math.sin(t * 0.7)
    return z, cx, cy


def render(cfg_path):
    with open(cfg_path) as fh:
        cfg = json.load(fh)
    fps = cfg.get("fps", 30)
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    work = os.path.join(ROOT, "output", "work")
    os.makedirs(work, exist_ok=True)

    voice, total, chunks = build_timeline(cfg, os.path.join(ROOT, "output", "tts"))
    T = {l["id"]: l["start"] for l in cfg["lines"]}
    T["end"] = cfg["lines"][-1]["end"]
    E = {l["id"]: l["end"] for l in cfg["lines"]}
    events = drum_events(T, total)
    set_events(events)
    print(f"duration {total:.2f}s, {len(chunks)} caption chunks")
    print("  ".join(f"{k}={v:.2f}" for k, v in T.items()))

    # audio
    music = build_music(T, total, events)
    sfx = build_sfx(T, total, cfg)
    n = int(total * SR)
    voice = np.pad(voice, (0, max(0, n - len(voice))))[:n]
    music, sfx = music[:n], sfx[:n]
    # duck the music under the voice
    env = np.convolve((np.abs(voice) > 0.01).astype(np.float32), np.ones(int(0.25 * SR)) / (0.25 * SR), "same")
    duck = 0.55 - 0.33 * np.clip(env * 3, 0, 1)
    mix = voice * 1.0 + music * duck + sfx * 0.6
    wav = os.path.join(work, "mix.wav")
    write_wav(wav, mix / max(1.0, np.abs(mix).max() / 0.95))

    bg = make_background()
    keys = camera_keys(T, total)
    frames = int(total * fps)

    stills = [float(x) for x in os.environ.get("STILLS", "").split(",") if x]
    enc = None if stills else subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-i", wav,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-shortest", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)

    surf = skia.Surface(W, H)
    shadow = skia.Paint(ImageFilter=skia.ImageFilters.DropShadow(14, 11, 0, 0, col("#6b5232", 0.2)))
    sections = music_sections(T, total)

    def is_playing(tt):
        return any(s0 <= tt < s1 and "drums" in parts for s0, s1, parts in sections)

    def mood_at(tt):
        if T["solo"] <= tt < T["twenty"] + 0.3:
            return "bliss"
        if T["royalty"] + 0.3 <= tt < T["everywhere"]:
            return "sad"
        return "focus"

    def cam(tt):
        z, cx, cy = camera_at(keys, tt)
        if is_playing(tt):
            z *= 1 + 0.012 * hit_env(tt, ("kick",), 12)
        return z, cx, cy

    def draw_world(c, t, z, cx, cy):
        playing = is_playing(t)
        c.save()
        c.translate(W / 2, H / 2)
        c.scale(z, z)
        c.translate(-cx, -cy)
        c.drawImage(bg, BG_X0, BG_Y0)
        # spotlight cone + dust in the light
        cone = skia.GradientShader.MakeLinear([(0, -300), (0, 1420)], [col("#fff8e6", 0.0), col("#fff8e6", 0.32)])
        c.drawPath(p_poly([(430, -300), (650, -300), (930, 1420), (150, 1420)]), paint(WHITE, shader=cone))
        for k in range(36):
            mx, my, ms = hash01("mx", k), hash01("my", k), hash01("ms", k)
            x = 200 + 680 * mx + 18 * math.sin(t * 0.7 + k)
            y = 1380 - ((my * 1500 + t * 22 * (0.5 + ms)) % 1500)
            c.drawCircle(x, y, 1.5 + 2.5 * ms, paint("#fffaf0", 0.35 + 0.4 * ms))

        hero1 = t < T["older"] + 0.1
        hero_a = window(t, 0, T["older"] + 0.1, 0, 0.3) + window(t, T["everywhere"] - 0.1, total, 0.3, 0.01)
        tl = t if hero1 else t - (T["everywhere"] - 0.1)
        hero_grow = ease_out(tl / 1.4)
        hero_fade = 1 - smooth((t - T["almost"] - 0.3) / 0.9) if t > T["everywhere"] else 1
        draw_wave(c, t, hero_grow * min(1, hero_a), hero_fade * min(1, hero_a), tl)
        draw_dashed_curl(c, t, window(t, T["almost"], total, 0.3, 0.01), smooth((t - T["almost"]) / 1.2))

        c.saveLayer(None, shadow)
        draw_band(c, t, T, E)
        meter_rise = smooth((t - T["royalty"] - 0.2) / 0.6) * (1 - smooth((t - E["almost"]) / 0.6))
        meter_rise = max(meter_rise, window(t, 0, T["band"], 0, 0.4))
        draw_meter(c, t, meter_rise, T["royalty2"] + 0.2 < t < E["royalty2"] + 0.5)
        ghost = smooth((t - T["almost"] - 0.2) / 1.0)
        if ghost > 0:
            c.saveLayerAlpha(None, int(255 * (1 - 0.72 * ghost)))
        solo = T["solo"] <= t < T["twenty"]
        draw_drummer(c, t, playing, mood_at(t), trail=4 if solo else 0)
        if ghost > 0:
            c.restore()
        draw_producer(c, t, T, E)
        c.restore()

        strip_a = window(t, T["twenty"] - 0.05, T["era"] + 0.3, 0.3, 0.4)
        draw_waveform_strip(c, t, strip_a, smooth((t - T["twenty"] - 0.2) / 0.3), cx=540, y=560)
        # dashed cable from the highlighted break to the sampler
        cable = smooth((t - T["sampled"] - 0.5) / 0.9) * window(t, T["sampled"], T["era"] + 0.3, 0.2, 0.4)
        if cable > 0:
            cab = path_of([tuple(p) for p in catmull([(830, 490), (1150, 380), (1450, 700), (1440, 1100)], 30)])
            eff = skia.DashPathEffect.Make([22, 14], -t * 60)
            c.drawPath(trimmed(cab, 0, cable), paint(RED, stroke=7, effect=eff))
            m = skia.PathMeasure(cab, False)
            pos, _ = m.getPosTan(m.getLength() * ((t * 0.8) % 1) * cable)
            if pos is not None:
                c.drawCircle(pos.x(), pos.y(), 12, paint(RED))
                c.drawCircle(pos.x(), pos.y(), 22, paint(RED, 0.25))
        # loop arrow over the sampler
        loop_a = window(t, T["looped"], T["royalty"], 0.3, 0.4)
        if loop_a > 0:
            c.save()
            c.translate(1450, 960)
            c.scale(back_out((t - T["looped"]) / 0.4), back_out((t - T["looped"]) / 0.4))
            c.rotate(t * 220)
            c.drawArc(skia.Rect.MakeLTRB(-90, -90, 90, 90), 20, 300, False, paint(RED, loop_a, stroke=14))
            c.drawPath(p_poly([(84, -48), (60, 20), (118, 4)]), paint(RED, loop_a))
            c.restore()
        # speed lines during the solo
        solo_a = window(t, T["solo"], T["twenty"], 0.2, 0.3)
        if solo_a > 0:
            for k in range(12):
                ang = math.radians(195 + k * 14 + 6 * math.sin(t * 3 + k))
                r0 = 250 + 40 * ((t * 3 + hash01("sl", k)) % 1)
                ln = 40 + 60 * hash01("sll", k)
                c.drawLine(560 + math.cos(ang) * r0, 1040 + math.sin(ang) * r0,
                           560 + math.cos(ang) * (r0 + ln), 1040 + math.sin(ang) * (r0 + ln),
                           paint(NAVY, 0.55 * solo_a, stroke=5))
        c.restore()

    for fi, t in enumerate(stills or [i / fps for i in range(frames)]):
        c = surf.getCanvas()
        c.clear(col(CREAM))
        z, cx, cy = cam(t)
        z0, cx0, cy0 = cam(t - 1 / fps)
        moving = math.hypot(cx - cx0, cy - cy0) * z > 14 or abs(z / z0 - 1) > 0.015
        # camera motion blur: average a few sub-frame camera positions on fast moves
        subs = 4 if moving else 1
        for j in range(subs):
            ts = t - (subs - 1 - j) / subs / fps
            if j:
                c.saveLayerAlpha(None, int(255 / (j + 1)))
            draw_world(c, t, *cam(ts))
            if j:
                c.restore()


        # ---- screen-space overlays
        draw_glitch_title(c, t, T["older"], T["band"] + 0.1, "OLDER THAN", "HIP-HOP.")
        draw_notes_card(c, t, T["notes"], T["solo"] + 0.6, T["dropout"] + 0.6)

        # flying records for the names and the count
        rec_a = window(t, T["era"] + 0.2, T["royalty"] + 0.2, 0.2, 0.4)
        if rec_a > 0:
            for k in range(26):
                t0 = T["thousand"] + 0.05 * k
                if t < t0:
                    continue
                pr = ease_out((t - t0) / 0.6)
                x = lerp(W / 2, 110 + 860 * hash01("rx", k), pr)
                y = lerp(1210, 230 + 830 * hash01("ry", k), pr)
                draw_record(c, x, y, 66, t * 200 + k * 30, ["#e8473a", "#f6d36b", "#59a8ff", "#8ee36a"][k % 4],
                            rec_a * 0.9)
            items = [("Fight the Power", "Public Enemy · 1989", "#e8473a", T["names"]),
                     ("Mama Said Knock You Out", "LL Cool J · 1990", "#f6d36b", T["names"] + 0.75)]
            for i, (song, by, lc, t0) in enumerate(items):
                if t < t0:
                    continue
                k = back_out((t - t0) / 0.5)
                y = 520 + i * 330
                x = lerp(W + 200, 250, k) - 1500 * smooth((t - T["thousand"] + 0.1) / 0.5)
                draw_record(c, x, y, 130, t * 160, lc, rec_a)
                draw_text(c, song, x + 165, y - 6, font("ExtraBold", 40), NAVY_DK, a=rec_a, outline="#fbf6ec", ow=8)
                draw_text(c, by, x + 165, y + 42, font("SemiBold", 30), "#5b5e78", a=rec_a, outline="#fbf6ec", ow=6)
            cnt_a = smooth((t - T["thousand"]) / 0.3) * rec_a
            if cnt_a > 0:
                val = int(1000 * ease_out((t - T["thousand"]) / 1.1))
                s = f"{val:,}" + ("+" if val >= 1000 else "")
                c.drawRoundRect(skia.Rect.MakeLTRB(W / 2 - 250, 1130, W / 2 + 250, 1290), 30, 30, paint(RED, cnt_a))
                draw_text(c, s, W / 2, 1238, font("ExtraBold", 110), WHITE, a=cnt_a, align="center")

        slot = int(t // 7) % 2 if t < T["end"] else 0
        if t < T["end"] + 0.3:
            draw_watermark(c, t, cfg["handle"], slot)
        draw_captions(c, t, chunks)
        draw_outro(c, t, T["end"] + 0.25, cfg)

        if stills:
            surf.makeImageSnapshot().save(os.path.join(work, f"still_{t:05.2f}.png"))
            continue
        frame = surf.makeImageSnapshot().toarray()
        enc.stdin.write(frame.tobytes())
        if fi % 150 == 0:
            print(f"frame {fi}/{frames}")
    if stills:
        print("stills written to", work)
        return
    enc.stdin.close()
    enc.wait()
    if enc.returncode:
        sys.exit("ffmpeg failed")
    print("wrote", out)


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "explainer_funky_drummer.json"))
