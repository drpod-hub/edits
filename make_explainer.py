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


def drum_state(events, t, kind, lift=1.0):
    """Stick height 0 (on the drum) .. 1 (raised) for a limb playing `kind` hits."""
    hits = [e for e in events if e[1] in kind]
    if not hits:
        return 0.35
    times = [e[0] for e in hits]
    i = np.searchsorted(times, t)
    prev = times[i - 1] if i > 0 else None
    nxt = times[i] if i < len(times) else None
    if prev is None or nxt is None:
        # resting before the first / after the last hit: ease to a low hover
        far = min(abs(t - (prev if prev is not None else nxt)), 1.0)
        return 0.25 * smooth(far * 3)
    span = nxt - prev
    if span > 1.0:
        return 0.25 * smooth(min(t - prev, nxt - t) * 3)
    ph = (t - prev) / span
    v = hits[i][2]
    return math.sin(math.pi * ph) ** 0.8 * (0.45 + 0.55 * v) * lift


def ik(s, tgt, a, b, bend):
    s, tgt = np.array(s, float), np.array(tgt, float)
    d = np.linalg.norm(tgt - s)
    d = clamp(d, abs(a - b) + 1, a + b - 1)
    base = math.atan2(tgt[1] - s[1], tgt[0] - s[0])
    ang = math.acos(clamp((a * a + d * d - b * b) / (2 * a * d), -1, 1))
    e = s + a * np.array([math.cos(base + bend * ang), math.sin(base + bend * ang)])
    return e


def draw_cymbal(c, x, y, rx, tilt, wob=0.0):
    c.save()
    c.translate(x, y)
    c.rotate(tilt + wob)
    c.drawOval(skia.Rect.MakeLTRB(-rx, -rx * 0.18, rx, rx * 0.18), paint(GOLD))
    c.drawOval(skia.Rect.MakeLTRB(-rx, -rx * 0.18, rx, rx * 0.18), paint("#a57a1c", stroke=3))
    c.drawOval(skia.Rect.MakeLTRB(-rx * 0.55, -rx * 0.09, rx * 0.25, rx * 0.04), paint("#fbe39a", 0.7))
    c.drawCircle(0, -2, 6, paint("#a57a1c"))
    c.restore()


def draw_drum_shell(c, cx, top, w, h, body=SHELL):
    r = skia.Rect.MakeLTRB(cx - w / 2, top, cx + w / 2, top + h)
    c.drawRect(r, paint(body))
    sh = skia.GradientShader.MakeLinear([(cx - w / 2, 0), (cx + w / 2, 0)],
                                        [col(WHITE, 0.25), col(WHITE, 0), col(INK, 0.25)], [0, 0.35, 1])
    c.drawRect(r, paint(WHITE, shader=sh))
    for yy in (top + 4, top + h - 4):
        c.drawLine(cx - w / 2, yy, cx + w / 2, yy, paint(CHROME, stroke=7, cap=skia.Paint.kButt_Cap))
    c.drawOval(skia.Rect.MakeLTRB(cx - w / 2, top - w * 0.12, cx + w / 2, top + w * 0.12), paint("#f4efe6"))
    c.drawOval(skia.Rect.MakeLTRB(cx - w / 2, top - w * 0.12, cx + w / 2, top + w * 0.12), paint(CHROME, stroke=5))


def draw_drummer(c, t, ev, playing, bob):
    """Drummer behind a kit; kit centred around x=540, floor at y=1380."""
    hat_h = drum_state(ev, t, ("hat",)) if playing else 0.0
    sn_h = drum_state(ev, t, ("snare",)) if playing else 0.0
    kick_h = drum_state(ev, t, ("kick",)) if playing else 0.0

    # stands behind the kit
    st = paint("#55565e", stroke=6)
    c.drawLine(300, 930, 300, 1380, st)
    c.drawLine(300, 1380, 260, 1380, st)
    c.drawLine(300, 1380, 340, 1380, st)
    c.drawLine(815, 980, 815, 1380, st)
    draw_cymbal(c, 300, 925, 105, -14, wob=2.5 * math.sin(t * 9) * (1 if playing else 0))
    draw_cymbal(c, 815, 975, 115, 10)

    # body
    hy = 870 + bob
    c.drawRoundRect(skia.Rect.MakeLTRB(462, 950 + bob * 0.6, 660, 1200), 60, 60, paint(NAVY))
    c.drawPath(path_of([(520, 950 + bob * 0.6), (562, 1010 + bob * 0.6), (604, 950 + bob * 0.6)]),
               paint("#f1e7d2"))
    c.drawRect(skia.Rect.MakeLTRB(540, 925 + bob, 584, 965 + bob), paint(SKIN_DK))
    # afro + head (three-quarter view facing left)
    c.drawCircle(572, hy - 34, 92, paint(INK))
    c.drawOval(skia.Rect.MakeLTRB(510, hy - 62, 616, hy + 62), paint(SKIN))
    c.drawOval(skia.Rect.MakeLTRB(596, hy - 14, 622, hy + 22), paint(SKIN_DK))
    c.drawPath(path_of([(512, hy - 30), (500, hy - 66), (560, hy - 92), (640, hy - 60), (620, hy - 20),
                        (590, hy - 44), (540, hy - 40)]), paint(INK))
    c.drawRect(skia.Rect.MakeLTRB(588, hy - 30, 604, hy + 18), paint(INK))  # sideburn
    c.drawCircle(530, hy - 8, 5.5, paint(INK))
    c.drawLine(518, hy - 24, 542, hy - 26, paint(INK, stroke=5))
    c.drawPath(path_of([(512, hy - 2), (502, hy + 18), (514, hy + 20)]), paint(SKIN_DK, stroke=4))
    c.drawPath(path_of([(514, hy + 33), (532, hy + 30), (548, hy + 34)]), paint(INK, stroke=6))  # moustache
    c.drawLine(524, hy + 45, 540, hy + 46, paint(SKIN_DK, stroke=4))

    # bass drum + pedal
    c.drawCircle(540, 1250, 128, paint(SHELL))
    c.drawCircle(540, 1250, 112, paint("#f4efe6"))
    c.drawCircle(540, 1250, 120, paint(CHROME, stroke=8))
    c.drawCircle(540, 1250, 52, paint(SHELL))
    f = font("ExtraBold", 34)
    draw_text(c, "1970", 540, 1262, f, "#f4efe6", align="center")
    beater = 1250 + 60 - 18 * (1 - kick_h)
    c.drawLine(560, 1380, 572, beater + 30, paint("#55565e", stroke=6))
    c.drawRoundRect(skia.Rect.MakeLTRB(548, 1360, 600, 1384), 8, 8, paint(INK))
    # rack tom
    draw_drum_shell(c, 540, 1068, 120, 56)
    # floor tom
    c.drawLine(712, 1290, 712, 1380, st)
    c.drawLine(812, 1290, 812, 1380, st)
    draw_drum_shell(c, 762, 1200, 130, 95)
    # snare on its stand
    c.drawLine(395, 1180, 395, 1380, st)
    c.drawLine(395, 1380, 350, 1380, st)
    c.drawLine(395, 1380, 440, 1380, st)
    draw_drum_shell(c, 395, 1138, 160, 46, body="#d9dbe0")
    # hi-hat (right side)
    c.drawLine(700, 1080, 700, 1380, st)
    open_ = 4 + 6 * hat_h
    draw_cymbal(c, 700, 1080 + open_, 78, 4)
    draw_cymbal(c, 700, 1074 - open_, 78, 4)

    # arms + sticks (in front of the kit)
    def arm(shoulder, drum, h, bend, stick_dir):
        hand = (drum[0] + stick_dir * 70, drum[1] - 50 - 90 * h)
        el = ik(shoulder, hand, 118, 112, bend)
        c.drawLine(shoulder[0], shoulder[1], el[0], el[1], paint(NAVY, stroke=50))
        c.drawLine(el[0], el[1], hand[0], hand[1], paint(SKIN, stroke=36))
        ang = math.atan2(drum[1] - hand[1], drum[0] - hand[0])
        tip = (hand[0] + 150 * math.cos(ang), hand[1] + 150 * math.sin(ang))
        c.drawLine(hand[0] - 20 * math.cos(ang), hand[1] - 20 * math.sin(ang), tip[0], tip[1],
                   paint("#e9cf98", stroke=11))
        c.drawCircle(hand[0], hand[1], 21, paint(SKIN))
        c.drawCircle(hand[0], hand[1], 21, paint(SKIN_DK, stroke=3))
        return tip

    arm((488, 985 + bob * 0.6), (395, 1120), sn_h, -1, 1)
    arm((636, 985 + bob * 0.6), (690, 1066), hat_h, 1, -1)
    return sn_h, hat_h


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


def draw_band(c, t, a, slide):
    """Bandleader (cape + mic) on the right, bassist on the left."""
    if a <= 0:
        return
    c.saveLayerAlpha(None, int(255 * a))
    # bandleader
    c.save()
    c.translate(slide, 0)
    sway = 6 * math.sin(t * 2 * math.pi * BPM / 60 / 2)
    bx = 900
    c.drawLine(bx - 20, 1170, bx - 30, 1380, paint(INK, stroke=30))
    c.drawLine(bx + 20, 1170, bx + 32, 1380, paint(INK, stroke=30))
    c.drawPath(path_of([(bx - 70, 960), (bx + 70, 960), (bx + 120 + sway, 1330), (bx - 110 + sway, 1330)]),
               paint("#b0182c"))
    c.drawRoundRect(skia.Rect.MakeLTRB(bx - 52, 950, bx + 52, 1190), 30, 30, paint("#f4efe6"))
    c.drawLine(bx, 960, bx, 1190, paint(INK, stroke=4))
    c.drawOval(skia.Rect.MakeLTRB(bx - 44 + sway * 0.3, 830, bx + 40 + sway * 0.3, 940), paint(SKIN))
    c.drawPath(path_of([(bx - 50 + sway * 0.3, 870), (bx - 40, 800), (bx + 10, 780), (bx + 54, 810),
                        (bx + 40 + sway * 0.3, 860), (bx + 10, 832), (bx - 30, 842)]), paint(INK))
    c.drawCircle(bx - 26 + sway * 0.3, 884, 5, paint(INK))
    # mic stand + arm to mic
    c.drawLine(bx - 120, 950, bx - 120, 1380, paint("#55565e", stroke=6))
    c.drawLine(bx - 120, 950, bx - 60, 905, paint("#55565e", stroke=6))
    c.drawRoundRect(skia.Rect.MakeLTRB(bx - 75, 885, bx - 45, 925), 12, 12, paint(INK))
    c.drawLine(bx - 40, 990, bx - 70, 1060, paint("#f4efe6", stroke=28))
    c.drawLine(bx - 70, 1060, bx - 64, 930, paint(SKIN, stroke=24))
    c.restore()
    # bassist
    c.save()
    c.translate(-slide, 0)
    gx = 140
    c.drawLine(gx - 18, 1170, gx - 26, 1380, paint(INK, stroke=28))
    c.drawLine(gx + 18, 1170, gx + 26, 1380, paint(INK, stroke=28))
    c.drawRoundRect(skia.Rect.MakeLTRB(gx - 50, 960, gx + 50, 1190), 30, 30, paint("#2f7d6d"))
    c.drawOval(skia.Rect.MakeLTRB(gx - 38, 850, gx + 42, 955), paint(SKIN_DK))
    c.drawCircle(gx + 4, 870, 54, paint(INK))
    c.drawOval(skia.Rect.MakeLTRB(gx - 34, 870, gx + 40, 960), paint(SKIN_DK))
    c.save()
    c.translate(gx, 1100)
    c.rotate(-32)
    c.drawRoundRect(skia.Rect.MakeLTRB(-60, -40, 60, 40), 36, 36, paint("#d9782a"))
    c.drawRect(skia.Rect.MakeLTRB(50, -9, 260, 9), paint("#5a3a1e"))
    c.drawRect(skia.Rect.MakeLTRB(250, -14, 290, 14), paint(INK))
    c.restore()
    c.drawLine(gx + 40, 1000, gx + 10, 1100, paint(SKIN_DK, stroke=24))
    c.restore()
    c.restore()


def draw_producer(c, t, ev, a):
    """Producer at a table with a 4x4-pad sampler, around world x=1520."""
    if a <= 0:
        return
    c.saveLayerAlpha(None, int(255 * a))
    px = 1520
    tap = drum_state(ev, t, ("snare", "kick"))
    # chair back + body
    c.drawRoundRect(skia.Rect.MakeLTRB(px - 80, 960, px + 80, 1190), 50, 50, paint("#2f8a8a"))
    c.drawRoundRect(skia.Rect.MakeLTRB(px - 60, 900, px + 60, 920), 8, 8, paint("#2f8a8a"))
    c.drawOval(skia.Rect.MakeLTRB(px - 50, 800, px + 46, 925), paint("#c98f62"))
    c.drawPath(path_of([(px - 58, 830), (px - 40, 780), (px + 30, 776), (px + 60, 806), (px - 58, 830)]),
               paint("#e04f3f"))
    c.drawRoundRect(skia.Rect.MakeLTRB(px - 112, 812, px - 30, 826), 6, 6, paint("#e04f3f"))  # cap brim
    # headphones
    c.drawArc(skia.Rect.MakeLTRB(px - 62, 790, px + 62, 930), 200, 140, False, paint(INK, stroke=10))
    c.drawRoundRect(skia.Rect.MakeLTRB(px + 34, 848, px + 66, 900), 12, 12, paint(INK))
    c.drawCircle(px - 26, 862, 5, paint(INK))
    # table + sampler
    c.drawRect(skia.Rect.MakeLTRB(px - 220, 1180, px + 220, 1206), paint("#6b4426"))
    c.drawLine(px - 190, 1206, px - 190, 1380, paint("#6b4426", stroke=16))
    c.drawLine(px + 190, 1206, px + 190, 1380, paint("#6b4426", stroke=16))
    box = skia.Rect.MakeLTRB(px - 170, 1110, px + 60, 1182)
    c.drawRoundRect(box, 10, 10, paint("#8d8f96"))
    c.drawRoundRect(skia.Rect.MakeLTRB(px - 160, 1118, px - 70, 1140), 4, 4, paint("#3b6b3f"))
    lit = int((t / STEP)) % 16
    for i in range(4):
        for j in range(2):
            idx = i + 4 * j
            on = (idx == lit % 8) and tap > 0.3
            c.drawRoundRect(skia.Rect.MakeLTRB(px - 60 + i * 28, 1120 + j * 28, px - 38 + i * 28, 1142 + j * 28),
                            4, 4, paint(RED if on else "#c9ccd3"))
    # arm tapping pads
    hand = (px - 20, 1110 - 30 * tap)
    c.drawLine(px - 50, 990, px - 110, 1080, paint("#2f8a8a", stroke=40))
    c.drawLine(px - 110, 1080, hand[0], hand[1], paint("#c98f62", stroke=30))
    c.drawCircle(hand[0], hand[1], 18, paint("#c98f62"))
    c.restore()


def wave_curve():
    ctrl = [(395, 1110), (250, 1040), (150, 860), (150, 600), (300, 380), (520, 320),
            (720, 420), (760, 600), (660, 720), (520, 690), (480, 570), (560, 520), (610, 570)]
    pts, L = resample(catmull(ctrl), 6.0)
    return pts, L


WAVE_PTS, WAVE_LEN = wave_curve()
WAVE_PATH = path_of([tuple(p) for p in WAVE_PTS])


def draw_wave(c, t, grow, fade, phase_speed=1.0):
    """Sound-wave curl: waveform bars standing perpendicular on the spiral."""
    if grow <= 0 or fade <= 0:
        return
    pts = WAVE_PTS
    n = len(pts)
    upto = int(n * clamp(grow))
    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    s = np.linspace(0, 1, n)
    width = 26 + 150 * np.sin(np.pi * np.clip(s * 1.15, 0, 1)) ** 1.3 * (1 - 0.75 * s)
    # soft body
    left = pts + nrm * width[:, None] * 0.55
    right = pts - nrm * width[:, None] * 0.55
    body = np.concatenate([left[:upto], right[:upto][::-1]])
    if upto > 3:
        c.drawPath(path_of([tuple(p) for p in body]), paint("#3d7be0", 0.18 * fade))
    stops = [col("#16308f"), col("#2f63d6"), col("#59a8ff"), col("#d8ecff")]
    for i in range(0, upto, 2):
        u = s[i] * 3
        k = min(int(u), 2)
        fr = u - k
        cc = skia.Color4f(skia.Color4f(stops[k]).fR * (1 - fr) + skia.Color4f(stops[k + 1]).fR * fr,
                          skia.Color4f(stops[k]).fG * (1 - fr) + skia.Color4f(stops[k + 1]).fG * fr,
                          skia.Color4f(stops[k]).fB * (1 - fr) + skia.Color4f(stops[k + 1]).fB * fr, fade)
        ph = i * 0.21 - t * 9 * phase_speed
        amp = (0.35 + 0.65 * abs(math.sin(ph) * math.sin(ph * 0.37 + 1.3)) + 0.15 * hash01(i, int(t * 12)))
        tip_fade = clamp((upto - i) / 25)
        h = width[i] * amp * 0.5 * (0.3 + 0.7 * tip_fade)
        p = pts[i]
        q0, q1 = p + nrm[i] * h, p - nrm[i] * h
        pp = skia.Paint(AntiAlias=True, Color4f=cc, StrokeWidth=7, Style=skia.Paint.kStroke_Style,
                        StrokeCap=skia.Paint.kRound_Cap)
        c.drawLine(q0[0], q0[1], q1[0], q1[1], pp)
    # spray of droplets/notes at the leading edge
    if upto > 10:
        head = pts[upto - 1]
        for k in range(14):
            r0 = hash01("spray", k)
            ang = r0 * 2 * math.pi
            dist = 30 + 90 * ((t * 0.9 + hash01("d", k)) % 1)
            rr = 3 + 9 * hash01("r", k)
            c.drawCircle(head[0] + math.cos(ang) * dist, head[1] + math.sin(ang) * dist, rr,
                         paint(WHITE if k % 3 else "#59a8ff", 0.85 * fade))


def draw_dashed_curl(c, t, a, draw_on=1.0, w=6):
    if a <= 0 or draw_on <= 0:
        return
    eff = skia.DashPathEffect.Make([24, 15], -t * 40)
    c.drawPath(trimmed(WAVE_PATH, 0, draw_on), paint(RED, a, stroke=w, effect=eff))


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
    for fi, t in enumerate(stills or [i / fps for i in range(frames)]):
        c = surf.getCanvas()
        c.clear(col(CREAM))
        z, cx, cy = camera_at(keys, t)
        c.save()
        c.translate(W / 2, H / 2)
        c.scale(z, z)
        c.translate(-cx, -cy)
        # background is laid out for screen space; stretch it under the world camera
        c.drawImage(bg, BG_X0, BG_Y0)

        playing = any(s0 <= t < s1 and "drums" in parts for s0, s1, parts in music_sections(T, total))
        hero_a = window(t, 0, T["older"] + 0.1, 0, 0.3) + window(t, T["everywhere"] - 0.1, total, 0.3, 0.01)
        hero_grow = ease_out(t / 1.6) if t < T["older"] else ease_out((t - T["everywhere"] + 0.1) / 1.2)
        hero_fade = 1 - smooth((t - T["almost"] - 0.3) / 0.9) if t > T["everywhere"] else 1
        draw_wave(c, t, hero_grow * min(1, hero_a), hero_fade * min(1, hero_a))
        # red dashed trace of the curl: first as the "it's a loop" reveal, then at the end
        draw_dashed_curl(c, t, window(t, T["almost"], total, 0.3, 0.01), smooth((t - T["almost"]) / 1.2))

        band_a = window(t, T["band"] - 0.1, E["dropout"] + 0.8, 0.4, 0.6)
        band_slide = 420 * smooth((t - T["dropout"] - 0.4) / 1.0)
        draw_band(c, t, band_a, band_slide)

        meter_rise = smooth((t - T["royalty"] - 0.2) / 0.6) * (1 - smooth((t - E["almost"]) / 0.6))
        meter_rise = max(meter_rise, window(t, 0, T["band"], 0, 0.4))
        draw_meter(c, t, meter_rise, t > T["royalty2"] + 0.2 and t < E["royalty2"] + 0.5)

        bob = 6 * drum_state(events, t, ("snare", "kick")) if playing else 0
        ghost = smooth((t - T["almost"] - 0.2) / 1.0)
        if ghost > 0:
            c.saveLayerAlpha(None, int(255 * (1 - 0.72 * ghost)))
        draw_drummer(c, t, events, playing, bob)
        if ghost > 0:
            c.restore()

        draw_producer(c, t, events, window(t, T["sampled"], T["royalty"] + 0.3, 0.6, 0.5))
        strip_a = window(t, T["twenty"] - 0.05, T["era"] + 0.3, 0.3, 0.4)
        draw_waveform_strip(c, t, strip_a, smooth((t - T["twenty"] - 0.2) / 0.3), cx=540, y=560)
        # dashed cable from the highlighted break to the sampler
        cable = smooth((t - T["sampled"] - 0.5) / 0.9) * window(t, T["sampled"], T["era"] + 0.3, 0.2, 0.4)
        if cable > 0:
            cab = path_of([tuple(p) for p in catmull([(830, 490), (1150, 380), (1450, 700), (1440, 1100)], 30)])
            eff = skia.DashPathEffect.Make([22, 14], -t * 60)
            c.drawPath(trimmed(cab, 0, cable), paint(RED, stroke=7, effect=eff))
        # loop arrow over the sampler
        loop_a = window(t, T["looped"], T["royalty"], 0.3, 0.4)
        if loop_a > 0:
            c.save()
            c.translate(1450, 960)
            c.rotate(t * 220)
            p = paint(RED, loop_a, stroke=12)
            c.drawArc(skia.Rect.MakeLTRB(-90, -90, 90, 90), 20, 300, False, p)
            c.drawPath(path_of([(84, -48), (60, 20), (118, 4)]), paint(RED, loop_a))
            c.restore()
        # motion lines during the solo
        solo_a = window(t, T["solo"], T["twenty"], 0.2, 0.3)
        if solo_a > 0:
            for k in range(8):
                ang = math.radians(200 + k * 22)
                r0 = 260 + 30 * math.sin(t * 20 + k)
                c.drawLine(560 + math.cos(ang) * r0, 1040 + math.sin(ang) * r0,
                           560 + math.cos(ang) * (r0 + 70), 1040 + math.sin(ang) * (r0 + 70),
                           paint(NAVY, 0.6 * solo_a, stroke=6))
        c.restore()  # end world camera

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
