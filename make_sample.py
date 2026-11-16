#!/usr/bin/env python3
"""Render a "sample breakdown" edit (landscape, black background).

Format: the sampled record's waveform runs across the screen. A playhead
plays each chop in turn and paints it in its colour, with the sample's title
underneath. The waveform then zooms in and the beat plays, lighting up
whichever chop is sounding. Finally the waveform fades and the song that used
the sample is credited.

Usage:  python3 make_sample.py sample_config.json

Missing audio falls back to a generated placeholder waveform and silence, so
the layout can be previewed before the tracks are dropped in.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from make_video import ROOT, hex_rgb, resolve, run

FONT_DIR = os.path.join(ROOT, "fonts")

# Geometry measured from the reference (896x576), as fractions of the height.
WAVE_CY = 0.448
WAVE_H = 0.118          # full height of the loudest part of the waveform
PLAYHEAD_H = 0.108
PLAYHEAD_W = 0.0036
PITCH_Y, PITCH_SIZE = 0.622, 0.0255
TITLE_Y, TITLE_SIZE = 0.774, 0.0465
BY_Y, BY_SIZE = 0.845, 0.0315
YEAR_Y, YEAR_SIZE = 0.908, 0.0255
SONG_TITLE_Y = 0.330    # where the song title settles in the outro
CREDIT_Y, CREDIT_PITCH, CREDIT_SIZE = 0.500, 0.056, 0.0315

GREY = (33, 33, 33)     # unlit waveform
DIM = 0.30              # brightness of chops that are not playing in the beat
SOFT = (200, 200, 200)  # secondary text

DEFAULT_COLORS = ["#2e2680", "#a03b58", "#dcae68", "#3f9c8f", "#8a5bd0", "#d0703c"]


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"), max(1, round(size)))


def ease(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def text_sprite(runs, tracking=0):
    """Render [(text, font, rgb), ...] on one baseline as a tight RGBA sprite."""
    asc = max(f.getmetrics()[0] for _, f, _ in runs)
    desc = max(f.getmetrics()[1] for _, f, _ in runs)
    width = sum(f.getlength(t) + tracking * len(t) for t, f, _ in runs)
    img = Image.new("RGBA", (int(width) + 8, asc + desc + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 4.0
    for text, f, rgb in runs:
        y = 4 + asc - f.getmetrics()[0]
        if tracking:
            for ch in text:
                d.text((x, y), ch, font=f, fill=rgb)
                x += f.getlength(ch) + tracking
        else:
            d.text((x, y), text, font=f, fill=rgb)
            x += f.getlength(text)
    return img


def paste(canvas, sprite, cx, cy, alpha=1.0):
    if alpha <= 0.004:
        return
    if alpha < 0.996:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.paste(sprite, (round(cx - sprite.width / 2), round(cy - sprite.height / 2)), sprite)


# ---------------------------------------------------------------- waveform

def decode_mono(path, sr=8000):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode:
        sys.exit("ffmpeg could not read " + path + "\n" + r.stderr.decode()[-2000:])
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0, sr


def placeholder_pcm(seconds, sr=8000):
    """Seeded noise with a slow swell, so the placeholder looks like a record."""
    rng = np.random.default_rng(7)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    swell = 0.55 + 0.25 * np.sin(t * 0.9) * np.sin(t * 0.23 + 1) + 0.2 * np.sin(t * 2.7)
    return (rng.standard_normal(n) * 0.33 * swell).astype(np.float32)


def wave_mask(pcm, cols, height, edges=None):
    """Min/max envelope of `pcm` as an L mask (cols x height), centred.

    `edges` (cols + 1 sample indices) lets the caller stretch the time axis."""
    if edges is None:
        edges = np.linspace(0, len(pcm), cols + 1)
    edges = np.clip(edges, 0, len(pcm)).astype(int)
    lo = np.zeros(cols, np.float32)
    hi = np.zeros(cols, np.float32)
    for i in range(cols):
        chunk = pcm[edges[i]:max(edges[i] + 1, edges[i + 1])]
        if len(chunk):
            lo[i], hi[i] = chunk.min(), chunk.max()
    peak = max(1e-4, float(np.percentile(np.abs(np.concatenate([lo, hi])), 99.7)))
    # Square-root compression: quiet passages stay readable next to loud ones.
    lo = -np.sqrt(np.clip(-lo / peak, 0, 1))
    hi = np.sqrt(np.clip(hi / peak, 0, 1))
    ss = 3                                       # vertical supersampling
    hh = height * ss
    mid = hh / 2
    top = mid - np.maximum(hi * mid, ss)         # keep a hairline through silence
    bot = mid - np.minimum(lo * mid, -ss)
    y = np.arange(hh, dtype=np.float32)[:, None]
    m = ((y >= top[None, :]) & (y <= bot[None, :])).astype(np.uint8) * 255
    return Image.fromarray(m, "L").resize((cols, height), Image.LANCZOS)


# ---------------------------------------------------------------- timeline

class Timeline:
    """Turns the config into: where the playhead is, what is lit, what plays."""

    def __init__(self, cfg, sample_len):
        s = cfg["sample"]
        self.pitch_ratio = 2 ** (float(s.get("pitch", 0)) / 12)
        # Playback speed: follows the pitch like a turntable unless "speed" sets
        # it separately (time-stretch) or "keep_tempo" pins it to 1.
        if s.get("speed"):
            self.rate = float(s["speed"])
        else:
            self.rate = 1.0 if s.get("keep_tempo") else self.pitch_ratio
        self.sample_len = sample_len
        self.chops = cfg["chops"]
        lead_default = float(cfg.get("lead_in", 2.0))
        tail = float(cfg.get("tail", 0.3))
        self.skip = float(cfg.get("skip_seconds", 0.6))
        r = self.rate

        # Part 1: play each chop (with a little lead-in) off the record.
        t = 0.0
        self.intro = []             # (t0, t1, src0)
        for i, c in enumerate(self.chops):
            lead = float(c.get("lead_in", 0.0 if i == 0 else lead_default))
            src0 = max(0.0, c["start"] - lead)
            src1 = min(sample_len, c["end"] + tail)
            dur = (src1 - src0) / r
            self.intro.append((t, t + dur, src0))
            t += dur
        self.intro_end = t
        self.gap = float(cfg.get("beat_gap", 0.4))
        t += self.gap
        self.beat_start = t

        # Part 2: the beat, as a sequence of chop hits.
        self.steps = []             # (t0, t1, chop index, src0)
        for st in cfg["sequence"]:
            c = self.chops[st["chop"]]
            src0 = c["start"] + float(st.get("offset", 0))
            dur = float(st.get("dur", (c["end"] - src0) / r))
            self.steps.append((t, t + dur, st["chop"], src0))
            t += dur
        self.beat_end = t
        self.outro = float(cfg.get("outro_seconds", 5.0))
        self.total = t + self.outro
        self.title_lead = float(cfg.get("song_title_lead", 1.5))

    def state(self, t):
        """-> (playhead source time or None, [(fill_until, brightness)] per chop)."""
        n = len(self.chops)
        r = self.rate
        if t < self.intro_end:
            for i, (t0, t1, src0) in enumerate(self.intro):
                if t < t1:
                    break
            pos = src0 + (t - t0) * r
            if i > 0 and t - t0 < self.skip:        # glide over from the last chop
                p0 = self.intro[i - 1]
                prev_end = p0[2] + (p0[1] - p0[0]) * r
                pos = prev_end + (pos - prev_end) * ease((t - t0) / self.skip)
            fills = [(1e9, 1.0) if j < i else (pos if j == i else -1.0, 1.0) for j in range(n)]
            return pos, fills
        if t < self.beat_start:
            return None, [(1e9, 1.0)] * n
        active, pos, since = None, None, 0.0
        for t0, t1, ci, src0 in self.steps:
            if t0 <= t < t1:
                active, since = ci, t - t0
                p = src0 + since * r
                pos = p if p <= self.chops[ci]["end"] else None
        if active is None:                          # outro: everything dim
            return None, [(1e9, DIM)] * n
        first = t < self.steps[0][1]
        fills = []
        for j in range(n):
            if j == active:
                fills.append((1e9, 1.0))
            elif first:                             # the others dim as the beat starts
                fills.append((1e9, 1.0 + (DIM - 1.0) * ease(since / 0.5)))
            else:
                fills.append((1e9, DIM))
        return pos, fills


# ---------------------------------------------------------------- renderer

class Renderer:
    def __init__(self, cfg, tl, pcm):
        self.cfg, self.tl = cfg, tl
        self.W, self.H = W, H = int(cfg.get("width", 1680)), int(cfg.get("height", 1080))
        s, song = cfg["sample"], cfg["song"]
        win = s.get("window") or [0.0, tl.sample_len]
        self.win0, self.win1 = float(win[0]), float(win[1])

        # Zoom for the beat section, limited so every chop stays on screen.
        mid = (self.win0 + self.win1) / 2
        half = (self.win1 - self.win0) / 2
        reach = max(max(abs(c["start"] - mid), abs(c["end"] - mid)) for c in cfg["chops"])
        self.zoom = max(1.0, min(float(cfg.get("beat_zoom", 1.19)), 0.97 * half / max(reach, 1e-6)))

        self.wave_h = round(H * WAVE_H)
        self.wave_top = round(H * WAVE_CY - self.wave_h / 2)
        sr = 8000
        seg = pcm[int(self.win0 * sr):int(self.win1 * sr)]

        # Very short chops would be slivers on a full-track waveform, so the
        # time axis is locally stretched to give each one a minimum width.
        # warp_u (true position, 0..1) -> warp_x (drawn position, 0..1).
        span = self.win1 - self.win0
        wmin = float(cfg.get("min_chop_width", 0.014))
        ku, kx = [0.0], [0.0]
        for c in sorted(cfg["chops"], key=lambda c: c["start"]):
            ua, ub = (c["start"] - self.win0) / span, (c["end"] - self.win0) / span
            if ub - ua >= wmin:
                continue
            mid, m = (ua + ub) / 2, wmin * 2.5
            pts = [(ua - m, ua - m), (ua, mid - wmin / 2), (ub, mid + wmin / 2), (ub + m, ub + m)]
            if pts[0][0] <= ku[-1] or pts[-1][0] >= 1:     # no room to stretch cleanly
                continue
            ku += [p[0] for p in pts]
            kx += [p[1] for p in pts]
        self.warp_u, self.warp_x = np.array(ku + [1.0]), np.array(kx + [1.0])
        cols = W * 2
        edges = np.interp(np.linspace(0, 1, cols + 1), self.warp_x, self.warp_u) * len(seg)
        self.base_mask = wave_mask(seg, cols, self.wave_h, edges)
        self._masks = {}
        self.colors = [np.array(hex_rgb(c.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])),
                                np.float32) for i, c in enumerate(cfg["chops"])]
        self.grey = np.array(GREY, np.float32)

        # Playhead: a white bar with a soft glow, added on top of the waveform.
        ph_w, ph_h = max(2, round(H * PLAYHEAD_W)), round(H * PLAYHEAD_H)
        pad = ph_w * 4
        bar = Image.new("L", (ph_w + pad * 2, ph_h + pad * 2), 0)
        ImageDraw.Draw(bar).rounded_rectangle([pad, pad, pad + ph_w - 1, pad + ph_h - 1],
                                              radius=ph_w // 2, fill=255)
        glow = bar.filter(ImageFilter.GaussianBlur(ph_w * 1.2))
        self.playhead = np.maximum(np.asarray(bar, np.float32),
                                   np.asarray(glow, np.float32) * 0.55) / 255.0

        white = (255, 255, 255)
        self.t_sample = text_sprite([(s["title"], font("Bold", H * TITLE_SIZE), white)])
        self.t_sample_by = text_sprite([("by ", font("Regular", H * BY_SIZE), SOFT),
                                        (s["artist"], font("SemiBold", H * BY_SIZE), white)])
        self.t_year = (text_sprite([(f"({s['year']})", font("Regular", H * YEAR_SIZE), SOFT)])
                       if s.get("year") else None)
        pitch = s.get("pitch", 0)
        label = s.get("label") or (f"PITCH: {'+' if pitch > 0 else '−'} {abs(pitch):g}" if pitch else "")
        self.t_pitch = (text_sprite([(label, font("SemiBold", H * PITCH_SIZE), white)],
                                    tracking=H * 0.0012) if label else None)
        self.t_song = text_sprite([(song["title"], font("Bold", H * TITLE_SIZE), white)])
        self.t_song_by = text_sprite([("by ", font("Regular", H * BY_SIZE), SOFT),
                                      (song["artist"], font("SemiBold", H * BY_SIZE), white)])
        producers = song.get("produced_by") or []
        if isinstance(producers, str):
            producers = [producers]
        self.t_credits = []
        if producers:
            self.t_credits.append(text_sprite([("Produced by", font("Regular", H * CREDIT_SIZE * 1.08), SOFT)]))
            self.t_credits += [text_sprite([(p, font("SemiBold", H * CREDIT_SIZE), white)])
                               for p in producers]
        handle = cfg.get("handle", "")
        self.t_handle = (text_sprite([("@" + handle.lstrip("@"), font("SemiBold", H * 0.026), white)])
                         if handle else None)

    def mask(self, zoom):
        key = round(zoom, 4)
        if key not in self._masks:
            if len(self._masks) > 4:                # only the two resting zooms are worth keeping
                self._masks = {k: v for k, v in self._masks.items() if k in (1.0, round(self.zoom, 4))}
            w = round(self.W * zoom)
            m = self.base_mask.resize((w, self.wave_h), Image.LANCZOS)
            x0 = (w - self.W) // 2
            self._masks[key] = np.asarray(m.crop((x0, 0, x0 + self.W, self.wave_h)), np.float32) / 255.0
        return self._masks[key]

    def frame(self, t):
        W, H, tl = self.W, self.H, self.tl
        out = np.zeros((H, W, 3), np.float32)

        zoom = 1.0 + (self.zoom - 1.0) * ease((t - tl.intro_end) / max(tl.gap + 0.25, 0.3))
        wave_alpha = 1.0 - ease((t - tl.beat_end) / 0.6)
        pos, fills = tl.state(t)

        def to_x(src):
            u = (src - self.win0) / (self.win1 - self.win0)
            u = float(np.interp(u, self.warp_u, self.warp_x)) if 0 <= u <= 1 else u
            return (u * W - W / 2) * zoom + W / 2

        if wave_alpha > 0:
            xs = np.arange(W, dtype=np.float32)
            row = np.tile(self.grey, (W, 1))
            for c, col, (fill, bright) in zip(self.cfg["chops"], self.colors, fills):
                a, b = to_x(c["start"]), to_x(min(c["end"], fill))
                if b <= a:
                    continue
                # 1px feathered edges so the fill glides instead of stepping.
                cover = np.clip(xs - a + 1, 0, 1) * np.clip(b - xs, 0, 1)
                lit = self.grey + (col - self.grey) * bright
                row += (lit - row) * cover[:, None]
            band = self.mask(zoom)[:, :, None] * row[None, :, :] * wave_alpha
            out[self.wave_top:self.wave_top + self.wave_h] = band
            if pos is not None:
                ph = self.playhead
                x0 = round(to_x(pos) - ph.shape[1] / 2)
                y0 = round(H * WAVE_CY - ph.shape[0] / 2)
                xa, xb = max(0, x0), min(W, x0 + ph.shape[1])
                if xb > xa:
                    region = out[y0:y0 + ph.shape[0], xa:xb]
                    a = ph[:, xa - x0:xb - x0, None] * wave_alpha
                    region += (255.0 - region) * a

        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")

        # Sample title block: on from the start, lifts away when the beat comes in.
        leave = ease((t - tl.intro_end + 0.1) / 0.45)
        if leave < 1:
            dy = -H * 0.03 * leave
            paste(img, self.t_sample, W / 2, H * TITLE_Y + dy, 1 - leave)
            paste(img, self.t_sample_by, W / 2, H * BY_Y + dy, 1 - leave)
            if self.t_year:
                paste(img, self.t_year, W / 2, H * YEAR_Y + dy, 1 - leave)
        if self.t_pitch:
            hold = min(float(self.cfg.get("pitch_label_seconds", 4.5)), tl.intro_end)
            paste(img, self.t_pitch, W / 2, H * PITCH_Y, 1 - ease((t - hold) / 0.4))

        # Song title: fades in under the waveform, then rises for the credits.
        t_in = tl.beat_end - tl.title_lead
        if t > t_in:
            rise = ease((t - tl.beat_end - 0.15) / 0.7)
            y = TITLE_Y + (SONG_TITLE_Y - TITLE_Y) * rise
            a = ease((t - t_in) / 0.5)
            paste(img, self.t_song, W / 2, H * y, a)
            paste(img, self.t_song_by, W / 2, H * (y + BY_Y - TITLE_Y), a)
            for i, sp in enumerate(self.t_credits):
                paste(img, sp, W / 2, H * (CREDIT_Y + CREDIT_PITCH * i),
                      ease((t - tl.beat_end - 1.7) / 0.5))
        if self.t_handle:
            paste(img, self.t_handle, W - self.t_handle.width / 2 - H * 0.03,
                  H * 0.955, 0.9)

        fade = ease((tl.total - t) / 0.35)      # dip to black on the last frames
        if fade < 1:
            img = Image.eval(img, lambda v: int(v * fade))
        return img


# ---------------------------------------------------------------- audio

def audio_piece(out, dur, src=None, start=0.0, ratio=1.0, speed=None,
                gain_db=0.0, fade_out=0.02):
    """Write `dur` seconds of 44.1k stereo wav: silence, or `src` from `start`."""
    if not src:
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{dur:.4f}", out])
        return
    chain = ["aresample=44100"]
    speed = ratio if speed is None else speed
    if abs(ratio - 1) > 1e-6:
        chain += [f"asetrate={44100 * ratio:.3f}", "aresample=44100"]
    if abs(speed / ratio - 1) > 1e-6:           # stretch back to the wanted speed
        chain.append(f"atempo={speed / ratio:.6f}")
    read = dur * speed + 0.5
    chain += ["apad", f"atrim=0:{dur:.4f}", f"volume={gain_db}dB",
              "afade=t=in:d=0.015", f"afade=t=out:st={max(0, dur - fade_out):.4f}:d={fade_out}",
              "aformat=channel_layouts=stereo"]
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, start):.4f}", "-t", f"{read:.4f}", "-i", src,
         "-vn", "-af", ",".join(chain), "-ar", "44100", "-ac", "2", out])


def build_audio(cfg, tl, sample_path, song_path, tmp):
    pieces = []

    def add(dur, **kw):
        if dur <= 0:
            return
        p = os.path.join(tmp, f"a{len(pieces):03d}.wav")
        audio_piece(p, dur, **kw)
        pieces.append(p)

    s, song = cfg["sample"], cfg["song"]
    sk = dict(src=sample_path, ratio=tl.pitch_ratio, speed=tl.rate,
              gain_db=float(s.get("gain_db", 0)))
    for t0, t1, src0 in tl.intro:
        add(t1 - t0, start=src0, **sk)
    add(tl.gap)
    rest = tl.total - tl.beat_start
    if song_path:                               # the real song, straight through
        add(rest, src=song_path, start=float(song.get("audio_start", 0)),
            gain_db=float(song.get("gain_db", 0)), fade_out=min(1.2, tl.outro))
    else:                                       # rebuild the beat from the chops
        for i, (t0, t1, _, src0) in enumerate(tl.steps):
            last = i == len(tl.steps) - 1
            add(t1 - t0 + (tl.outro if last else 0), start=src0,
                fade_out=min(2.5, tl.outro) if last else 0.02, **sk)
    lst = os.path.join(tmp, "audio.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in pieces)
    out = os.path.join(tmp, "audio.wav")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    return out


# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg_path = sys.argv[1]
    with open(cfg_path) as f:
        cfg = json.load(f)
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")

    s = cfg["sample"]
    sample_path = resolve(s.get("audio"))
    song_path = resolve(cfg["song"].get("audio"))
    if sample_path:
        pcm, sr = decode_mono(sample_path)
    else:
        print(f"! sample audio not found ({s.get('audio') or 'none set'}) - placeholder waveform, silent")
        need = max(c["end"] for c in cfg["chops"]) + 5
        pcm, sr = placeholder_pcm(max(need, float(s.get("duration", (s.get("window") or [0, 0])[1])))), 8000
    sample_len = len(pcm) / sr
    for i, c in enumerate(cfg["chops"]):
        if not 0 <= c["start"] < c["end"] <= sample_len + 0.01:
            sys.exit(f"chop {i} ({c['start']}-{c['end']}s) is outside the sample ({sample_len:.1f}s)")
    if not song_path and sample_path:
        print("  no song audio - rebuilding the beat from the chops")

    tl = Timeline(cfg, sample_len)
    rd = Renderer(cfg, tl, pcm)
    fps = int(cfg.get("fps", 30))
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    frames = int(round(tl.total * fps))
    print(f"  {rd.W}x{rd.H} @ {fps}fps, {tl.total:.1f}s "
          f"(chops {tl.intro_end:.1f}s, beat {tl.beat_end - tl.beat_start:.1f}s, outro {tl.outro:.1f}s)")

    tmp = tempfile.mkdtemp(prefix="sample_")
    try:
        audio = build_audio(cfg, tl, sample_path, song_path, tmp)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{rd.W}x{rd.H}", "-r", str(fps), "-i", "-", "-i", audio,
             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out],
            stdin=subprocess.PIPE)
        for n in range(frames):
            enc.stdin.write(rd.frame(n / fps).tobytes())
            if n % (fps * 5) == 0:
                print(f"  frame {n}/{frames}", flush=True)
        enc.stdin.close()
        if enc.wait():
            sys.exit("ffmpeg encode failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
