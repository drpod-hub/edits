#!/usr/bin/env python3
"""Render a "THE WORST (…) I'VE EVER HEARD" vertical (1080x1920) lyric edit.

Format mirrors the RealjN "The WORST Rap Freestyles of ALL TIME" short:
a crumpled-paper intro (title over a photo, zoom-blur out, then one word at a
time: "<TOPIC>" / "I'VE" / "EVER" / "HEARD..."), crossfading into one
segment per bar. Each segment shows ARTIST / (YEAR) / "SONG" in the top
third and the lyrics karaoke-style underneath: the next line waits in grey,
then turns white the moment it is rapped. A grey caps "note" line can be
dropped in as commentary.

Usage:  python3 make_worst.py [worst_config.json]

Missing media falls back to placeholders (procedural Yeezus-style CD for the
intro photo and the segment backgrounds, silence for audio), so the video
always renders.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "fonts")

# Geometry measured from the reference (720x1280, scaled x1.5).
HEAD_Y = [282, 357, 435]   # centre y of ARTIST / (YEAR) / "SONG"
LYRIC_Y0 = 558             # centre y of the first lyric line
LYRIC_PITCH = 112
HEAD_SIZE = 58
LYRIC_SIZE = 84
TITLE_Y = [250, 365]       # intro "THE WORST" / "(TOPIC)"
WORD_Y = H / 2

WHITE = (255, 255, 255)
RED = (235, 16, 16)
GREY = (196, 196, 196)
INK = (12, 12, 12)

PREVIEW = 0.6      # an upcoming line shows in grey this long before it's rapped
LIGHT_UP = 0.1     # grey -> white transition
XFADE = 0.3        # intro -> first segment crossfade


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def resolve(path):
    if not path:
        return None
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    return p if os.path.exists(p) else None


def ease_out_back(p):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def clamp01(x):
    return max(0.0, min(1.0, x))


# --------------------------------------------------------------------------
# Fonts + text: fill with a dark outline and a soft drop shadow
# --------------------------------------------------------------------------
_fonts = {}


def head_font(size):
    key = ("head", size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, "Poppins-ExtraBold.ttf"), size)
    return _fonts[key]


def lyric_font(size):
    key = ("lyric", size)
    if key not in _fonts:
        f = ImageFont.truetype(os.path.join(FONT_DIR, "Nunito-Variable.ttf"), size)
        f.set_variation_by_name("Black")
        _fonts[key] = f
    return _fonts[key]


def fit(make, text, size, max_w):
    f = make(size)
    while f.getlength(text) > max_w and size > 20:
        size -= 2
        f = make(size)
    return f


_text_cache = {}


def text_img(text, fnt, fill, stroke=5, shadow=7):
    key = (text, id(fnt), fill, stroke, shadow)
    if key in _text_cache:
        return _text_cache[key]
    pad = stroke + shadow * 2 + 6
    l, t, r, b = fnt.getbbox(text, stroke_width=stroke)
    asc, desc = fnt.getmetrics()
    img = Image.new("RGBA", (r - l + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    org = (pad - l, pad)

    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(org, text, font=fnt, fill=255, stroke_width=stroke, stroke_fill=255)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(mask.filter(ImageFilter.GaussianBlur(shadow)).point(lambda v: int(v * 0.9)))
    img.alpha_composite(sh, (2, 5))
    ImageDraw.Draw(img).text(org, text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=INK)
    _text_cache[key] = img
    return img


def with_alpha(img, a):
    if a >= 1:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


def paste_c(canvas, img, cx, cy, scale=1.0, alpha=1.0):
    if alpha <= 0:
        return
    if abs(scale - 1) > 1e-3:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
    img = with_alpha(img, alpha)
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# --------------------------------------------------------------------------
# Procedural art
# --------------------------------------------------------------------------
def crumpled_paper(seed=7):
    """Light-grey crumpled paper: Voronoi facets with random tilts, lit from the top-left."""
    rng = np.random.default_rng(seed)
    w, h = W // 2, H // 2
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    n = 260
    sx, sy = rng.uniform(-20, w + 20, n), rng.uniform(-20, h + 20, n)
    d = np.stack([(x - sx[i]) ** 2 + (y - sy[i]) ** 2 for i in range(n)])
    order = np.argsort(d, axis=0)[:2]
    near = order[0]
    d1 = np.sqrt(np.take_along_axis(d, order[:1], 0)[0])
    d2 = np.sqrt(np.take_along_axis(d, order[1:2], 0)[0])
    tilt = rng.normal(0, 0.2, (n, 2)).astype(np.float32)
    nx, ny = tilt[near, 0], tilt[near, 1]
    shade = (-nx * 0.6 - ny * 0.8) / np.sqrt(nx ** 2 + ny ** 2 + 1)
    crease = np.clip(1 - (d2 - d1) / 3.0, 0, 1)        # thin dark/bright lines on fold edges
    low = rng.normal(0, 1, (12, 7)).astype(np.float32)
    low = np.asarray(Image.fromarray(low).resize((w, h), Image.BICUBIC))
    v = 210 + shade * 45 - crease * 8 + low * 9 + rng.normal(0, 1.2, (h, w))
    img = Image.fromarray(np.clip(v, 120, 248).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(2.2)).resize((W, H), Image.BICUBIC)
    return img.convert("RGBA")


def yeezus_disc(size=900):
    """Clear CD with a strip of red tape — stand-in for a photo of the artist."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    y, x = np.mgrid[0:s, 0:s].astype(np.float32) - s / 2
    r = np.sqrt(x ** 2 + y ** 2) / (s / 2)
    a = np.arctan2(y, x)
    sheen = 0.5 + 0.5 * np.cos(a * 2 + 0.6) ** 8 + 0.15 * np.sin(r * 90)
    lum = np.clip(150 + 80 * sheen, 0, 255)
    alpha = np.where(r < 1, 120 + 60 * sheen, 0)
    alpha = np.where(r < 0.36, 70, alpha)            # clear inner ring
    alpha = np.where(r < 0.12, 0, alpha)             # spindle hole
    edge = (np.abs(r - 1) < 0.008) | (np.abs(r - 0.36) < 0.006) | (np.abs(r - 0.12) < 0.008)
    lum = np.where(edge, 245, lum)
    alpha = np.where(edge & (r <= 1.01), 230, alpha)
    rgba = np.dstack([lum, lum, lum * 1.02, alpha]).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    tape = Image.new("RGBA", (int(s * 0.5), int(s * 0.1)), (214, 20, 24, 255))
    td = ImageDraw.Draw(tape)
    for i in range(0, tape.width, 7):  # torn ends + tape texture
        td.line([(i, 0), (i, tape.height)], fill=(196, 14, 18, 255))
    tape = tape.rotate(-28, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(tape, (int(s * 0.48), int(s * 0.74)))
    return img


def load_cutout(path, max_w, max_h):
    img = Image.open(path).convert("RGBA")
    k = min(max_w / img.width, max_h / img.height)
    return img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)


# --------------------------------------------------------------------------
# Media helpers (ffmpeg)
# --------------------------------------------------------------------------
def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])


def envelope(path, start, dur, fps):
    """Per-frame loudness (0..1) of an audio window, for the beat pulse."""
    if not path:
        return np.zeros(int(dur * fps) + 2)
    sr = 8000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", path,
                          "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = sr // fps
    n = len(a) // hop
    rms = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-9)
    lo, hi = np.percentile(rms, 20), np.percentile(rms, 98)
    e = np.clip((rms - lo) / (hi - lo + 1e-9), 0, 1)
    return np.concatenate([e, np.zeros(4)])


class ClipReader:
    """Streams a clip as 1080x1920 RGB frames (cover-cropped to 9:16)."""

    def __init__(self, path, start, dur, fps, zoom=1.0):
        vf = (f"scale={int(W * zoom)}:{int(H * zoom)}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},fps={fps}")
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur + 1),
                                   "-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE)
        self.last = None

    def next(self):
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.last = Image.frombuffer("RGB", (W, H), buf).convert("RGBA")
        return self.last if self.last is not None else Image.new("RGBA", (W, H), (0, 0, 0, 255))

    def close(self):
        self.p.stdout.close()
        self.p.wait()


# --------------------------------------------------------------------------
# Intro
# --------------------------------------------------------------------------
class Intro:
    def __init__(self, cfg):
        c = cfg["intro"]
        pp = resolve(c.get("paper"))
        if pp:
            img = Image.open(pp).convert("RGBA")
            k = max(W / img.width, H / img.height)
            img = img.resize((math.ceil(img.width * k), math.ceil(img.height * k)), Image.LANCZOS)
            l, tp = (img.width - W) // 2, (img.height - H) // 2
            self.paper = img.crop((l, tp, l + W, tp + H))
        else:
            self.paper = crumpled_paper(c.get("paper_seed", 7))
        p = resolve(c.get("image"))
        if p:
            self.photo = load_cutout(p, W * 0.95, H * 0.78)
            self.photo_y = H - self.photo.height / 2
        else:
            print("  ! intro image missing -> Yeezus disc placeholder")
            self.photo = yeezus_disc(860)
            self.photo_y = H * 0.62
        self.t1 = text_img(c["title"], fit(head_font, c["title"], 132, W - 140), WHITE, stroke=7, shadow=9)
        self.t2 = text_img(c["subtitle"], fit(head_font, c["subtitle"], 118, W - 110), RED, stroke=7, shadow=9)
        self.words = [(w, text_img(w, fit(head_font, w, 96, W - 160), WHITE, stroke=6, shadow=8))
                      for w in c["words"]]
        self.title_end = c.get("title_seconds", 0.75)
        self.word_secs = c.get("word_seconds", [0.5, 0.3, 0.3, 0.55])
        self.length = self.title_end + 0.12 + sum(self.word_secs)

    def frame(self, t):
        img = self.paper.copy()
        # Title + photo, slow push-in, then zoom-blur out.
        blur_t = clamp01((t - (self.title_end - 0.18)) / 0.3)
        if blur_t < 1:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            push = 1 + 0.05 * t / self.title_end
            paste_c(layer, self.photo, W / 2, self.photo_y, push)
            paste_c(layer, self.t1, W / 2, TITLE_Y[0], push)
            paste_c(layer, self.t2, W / 2, TITLE_Y[1], push)
            if blur_t > 0:
                k = 1 + 0.35 * blur_t ** 2
                layer = layer.resize((int(W * k), int(H * k)), Image.BILINEAR)
                l, tp = (layer.width - W) // 2, (layer.height - H) // 2
                layer = layer.crop((l, tp, l + W, tp + H)).filter(ImageFilter.GaussianBlur(28 * blur_t))
                layer = with_alpha(layer, 1 - blur_t ** 1.5)
            img.alpha_composite(layer)
        # One word at a time.
        t0 = self.title_end + 0.12
        for (w, wi), d in zip(self.words, self.word_secs):
            if t0 <= t < t0 + d or (w is self.words[-1][0] and t >= t0):
                p = clamp01((t - t0) / 0.14)
                paste_c(img, wi, W / 2, WORD_Y, 0.82 + 0.18 * ease_out_back(p), clamp01(p * 2))
            t0 += d
        return img


# --------------------------------------------------------------------------
# Segments
# --------------------------------------------------------------------------
class Segment:
    def __init__(self, seg, cfg, disc):
        self.s = seg
        self.fps = cfg["fps"]
        self.dur = seg["end"] - seg["start"]
        self.audio = resolve(seg.get("audio"))
        self.env = envelope(self.audio, seg["start"], self.dur, self.fps)
        self.clip_path = resolve(seg.get("clip"))
        self.disc = disc
        self.tint = hex_rgb(seg.get("tint", "#1a1a1a"))
        if not self.clip_path:
            print(f"  ! clip missing for {seg['song']} -> procedural background")

        name, year, song = seg["artist"].upper(), f"({seg['year']})", f"“{seg['song'].upper()}”"
        self.head = [text_img(name, fit(head_font, name, HEAD_SIZE, W - 160), WHITE),
                     text_img(year, head_font(HEAD_SIZE), WHITE),
                     text_img(song, fit(head_font, song, HEAD_SIZE, W - 120), RED)]
        self.lines = []
        for i, ln in enumerate(seg["lines"]):
            if ln.get("note"):
                f = fit(head_font, ln["text"], 70, W - 140)
                white = grey = text_img(ln["text"], f, GREY)
            else:
                f = fit(lyric_font, ln["text"], LYRIC_SIZE, W - 110)
                white, grey = text_img(ln["text"], f, WHITE), text_img(ln["text"], f, GREY)
            prev = seg["lines"][i - 1]["t"] - seg["start"] + 0.15 if i else 0
            t = ln["t"] - seg["start"]
            self.lines.append((max(prev, t - PREVIEW), t, white, grey, bool(ln.get("note"))))
        self._bg_cache = None

    # -- background ---------------------------------------------------------
    def open(self):
        if self.clip_path:
            self.reader = ClipReader(self.clip_path, self.s.get("clip_start", 0), self.dur, self.fps,
                                     self.s.get("clip_zoom", 1.0))

    def close(self):
        if self.clip_path:
            self.reader.close()

    def background(self, t, n):
        pulse = float(self.env[min(n, len(self.env) - 1)])
        if self.clip_path:
            return self.reader.next()
        if self._bg_cache is None:
            base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
            d = ImageDraw.Draw(base)
            for yy in range(0, H, 4):
                k = 0.35 + 0.65 * (1 - abs(yy / H - 0.55) * 1.5)
                d.rectangle([0, yy, W, yy + 4], fill=tuple(int(c * k) for c in self.tint) + (255,))
            disc = self.disc.resize((1500, 1500), Image.BICUBIC).filter(ImageFilter.GaussianBlur(10))
            rng = np.random.default_rng(3)
            grain = [Image.fromarray(rng.normal(0, 14, (H // 2, W // 2)).clip(-40, 40).astype(np.int8).view(np.uint8) + 128)
                     .resize((W, H)) for _ in range(4)]
            self._bg_cache = (base, disc, grain)
        base, disc, grain = self._bg_cache
        img = base.copy()
        k = 1 + 0.06 * pulse + 0.02 * t
        d2 = disc.rotate(-t * 9, resample=Image.BILINEAR)
        d2 = d2.resize((int(d2.width * k), int(d2.height * k)), Image.BILINEAR)
        shake = (math.sin(t * 37) * 6 * pulse, math.cos(t * 29) * 6 * pulse)
        img.alpha_composite(with_alpha(d2, 0.55), (int(W / 2 - d2.width / 2 + shake[0]),
                                                  int(H * 0.68 - d2.height / 2 + shake[1])))
        g = grain[n % 4]
        img = Image.composite(Image.new("RGBA", (W, H), (255, 255, 255, 255)), img,
                              g.point(lambda v: max(0, v - 128) // 3))
        return img

    # -- text ---------------------------------------------------------------
    def overlay(self, img, t, alpha=1.0):
        for im, y in zip(self.head, HEAD_Y):
            paste_c(img, im, W / 2, y, alpha=alpha)
        row = 0
        for show, start, white, grey, note in self.lines:
            if t < show:
                break
            y = LYRIC_Y0 + row * LYRIC_PITCH
            row += 1
            fade = clamp01((t - show) / 0.15) * alpha
            if note or t < start:
                paste_c(img, grey, W / 2, y, alpha=fade * (0.8 if note else 0.7))
            else:
                p = clamp01((t - start) / LIGHT_UP)
                if p < 1:
                    paste_c(img, grey, W / 2, y, alpha=(1 - p) * 0.7 * alpha)
                paste_c(img, white, W / 2, y, 1 + 0.06 * (1 - ease_out_back(clamp01((t - start) / 0.18))),
                        p * alpha)

    def frame(self, t, n, alpha=1.0):
        img = self.background(t, n)
        self.overlay(img, t, alpha)
        return img


# --------------------------------------------------------------------------
def build_audio(cfg, intro_len, seg_starts, segs, tmp):
    """Intro bed + each segment's window, loudness-matched, laid on one timeline."""
    out = os.path.join(tmp, "audio.wav")
    total = seg_starts[-1] + segs[-1].dur
    inputs, parts = [], []
    ic = cfg["intro"]
    pieces = [(resolve(ic.get("audio")), ic.get("audio_start", 0), intro_len, 0.0, ic.get("gain_db", -4))]
    pieces += [(s.audio, s.s["start"], s.dur, st, 0) for s, st in zip(segs, seg_starts)]
    for i, (path, start, dur, at, gain) in enumerate(pieces):
        if path:
            inputs += ["-ss", str(start), "-t", str(dur), "-i", path]
        else:
            inputs += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo"]
        fo = 0.25 if i == 0 else 0.06
        parts.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,"
                     f"loudnorm=I=-14:TP=-1.5:LRA=11,volume={gain}dB,"
                     f"afade=t=in:d=0.03,afade=t=out:st={max(0, dur - fo)}:d={fo},"
                     f"adelay={int(at * 1000)}|{int(at * 1000)},apad=whole_dur={total}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(pieces)))
    fc = ";".join(parts) + f";{mix}amix=inputs={len(pieces)}:normalize=0:duration=longest,atrim=0:{total}[out]"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[out]", out])
    return out, total


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "worst_config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    fps = cfg["fps"]
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)

    print("Preparing intro + segments…")
    intro = Intro(cfg)
    disc = intro.photo if not resolve(cfg["intro"].get("image")) else yeezus_disc(860)
    segs = [Segment(s, cfg, disc) for s in cfg["segments"]]
    # The first segment starts under the intro's last XFADE seconds.
    seg_starts, t = [], intro.length - XFADE
    for s in segs:
        seg_starts.append(t)
        t += s.dur

    tmp = tempfile.mkdtemp(prefix="worst_")
    try:
        print("Mixing audio…")
        audio, total = build_audio(cfg, intro.length, seg_starts, segs, tmp)

        print("Rendering frames…")
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-i", audio, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        nframes = int(round(total * fps))
        idx = -1
        fade_out = cfg.get("fade_out", 0.25)
        for n in range(nframes):
            gt = n / fps
            while idx + 1 < len(segs) and gt >= seg_starts[idx + 1]:
                if idx >= 0:
                    segs[idx].close()
                idx += 1
                segs[idx].open()
                seg_n0 = n
            if idx < 0:
                img = intro.frame(gt)
            else:
                s = segs[idx]
                lt = gt - seg_starts[idx]
                img = s.frame(lt, n - seg_n0)
                if gt < intro.length:  # crossfade from the paper intro
                    a = clamp01((gt - seg_starts[0]) / XFADE)
                    img = Image.blend(intro.frame(gt), img, a)
            if gt > total - fade_out:
                img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)),
                                  clamp01((gt - (total - fade_out)) / fade_out))
            enc.stdin.write(img.tobytes())
            if n % (fps * 2) == 0:
                print(f"  {gt:5.1f}s / {total:.1f}s")
        segs[idx].close()
        enc.stdin.close()
        if enc.wait():
            sys.exit("final encode failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("Done ->", out)


if __name__ == "__main__":
    main()
