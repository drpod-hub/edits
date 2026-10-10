#!/usr/bin/env python3
"""Turn a horizontal (16:9) clip into a vertical 1080x1920 YouTube Short.

What it does, driven by a JSON config (see shorts/tsukasa_celular.json):
  * cold-open hook: a short teaser from later in the clip plays first, with a
    big "wait for it" caption, then the story starts from the beginning;
  * dead-air removal: silences longer than `min_silence` are tightened down to
    `keep` seconds on each side (except inside `protect` ranges), plus any
    manual `remove` ranges;
  * vertical layout: blurred full-screen background, the clip in the middle,
    a header title above and animated captions below;
  * a zoom punch on every jump cut, a bigger punch + shake + bass hit on the
    `punch` moments, a call-to-action over the last seconds;
  * loudness normalised for Shorts (-14 LUFS).

Usage:  python3 make_short.py shorts/tsukasa_celular.json
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import shutil

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "fonts")
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

SRC_W, SRC_H = 1280, 720     # working size of the decoded clip
FG_W = W
FG_Y = 560                   # top of the clip on the canvas
HEADER_Y = 330               # centre of the header block
TAG_Y = 175                  # centre of the small tag line


def set_layout(fg_crop):
    """fg_crop: fraction of the source width kept (trims edges; 1.0 keeps all)."""
    global FG_CROP, FG_H, CAPTION_Y
    FG_CROP = fg_crop
    FG_H = int(round(FG_W * SRC_H / (SRC_W * FG_CROP) / 2) * 2)
    CAPTION_Y = FG_Y + FG_H + 175


set_layout(0.92)

WHITE = (255, 255, 255)
YELLOW = (255, 221, 0)
PINK = (255, 92, 168)

POP = 0.22                   # caption pop-in seconds
CUT_PUNCH = 0.22             # zoom-punch length on jump cuts
CUT_ZOOM = 0.07


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"), size)


def run(cmd, capture=False):
    r = subprocess.run(cmd, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit("command failed:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])
    return r


def probe_height(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height",
             "-of", "csv=p=0", path], capture=True)
    return int(r.stdout.strip())


def probe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture=True)
    return float(r.stdout.strip())


# --------------------------------------------------------------------------
# Edit decision list
# --------------------------------------------------------------------------
def detect_silences(path, db, min_len):
    r = subprocess.run(["ffmpeg", "-i", path, "-af", f"silencedetect=n={db}dB:d={min_len}",
                        "-f", "null", "-"], stderr=subprocess.PIPE, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def audio_envelope(path, hop=0.01):
    """RMS per `hop` seconds of the clip's audio (mono)."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    n = int(8000 * hop)
    a = a[: len(a) // n * n].reshape(-1, n)
    return np.sqrt((a ** 2).mean(axis=1)), hop


def snap_to_quiet(t, env, hop, radius):
    """Move a cut to the quietest instant within +-radius so speech isn't chopped mid-word."""
    lo, hi = max(0, int((t - radius) / hop)), min(len(env), int((t + radius) / hop) + 1)
    if hi <= lo:
        return t
    i = lo + int(env[lo:hi].argmin())
    return i * hop


def build_edl(cfg, src, duration):
    """Return the list of (src_start, src_end) ranges kept for the main body."""
    if "segments" in cfg:
        # hand-picked ranges (montage); optionally snapped to pauses in the audio
        segs = [tuple(r) for r in cfg["segments"]]
        radius = cfg.get("snap_cuts", 0)
        if radius:
            env, hop = audio_envelope(src)
            segs = [(snap_to_quiet(a, env, hop, radius), snap_to_quiet(b, env, hop, radius))
                    for a, b in segs]
        return [(a, b) for a, b in segs if b - a >= 0.1]
    ts = cfg.get("trim_silence")
    removes = [tuple(r) for r in cfg.get("remove", [])]
    protect = [tuple(r) for r in cfg.get("protect", [])]
    if ts:
        keep = ts["keep"]
        for s, e in detect_silences(src, ts["threshold_db"], ts["min_silence"]):
            if any(overlaps((s, e), p) for p in protect):
                continue
            if e - s > 2 * keep + 0.1:
                removes.append((s + keep, e - keep))
    removes.sort()

    start, end = cfg.get("start", 0.0), cfg.get("end", duration)
    ranges, cur = [], start
    for rs, re_ in removes:
        if re_ <= cur or rs >= end:
            continue
        if rs > cur:
            ranges.append((cur, rs))
        cur = max(cur, re_)
    if cur < end:
        ranges.append((cur, end))
    return [(a, b) for a, b in ranges if b - a >= 0.1]


class Timeline:
    """Maps output frames to source time. Segment 0 is the hook (if any)."""

    def __init__(self, segments, fps, hook):
        self.fps = fps
        self.segments = []  # (src_start, n_frames, is_hook)
        if hook:
            self.segments.append((hook["start"], round((hook["end"] - hook["start"]) * fps), True))
        for a, b in segments:
            self.segments.append((a, round((b - a) * fps), False))
        self.total = sum(n for _, n, _ in self.segments)

    def ffmpeg_ranges(self):
        return [(s, s + n / self.fps) for s, n, _ in self.segments]

    def locate(self, frame):
        """-> (segment index, src time, seconds since segment start, is_hook)"""
        for i, (s, n, hook) in enumerate(self.segments):
            if frame < n:
                return i, s + frame / self.fps, frame / self.fps, hook
            frame -= n
        s, n, hook = self.segments[-1]
        return len(self.segments) - 1, s + n / self.fps, n / self.fps, hook

    def out_time(self, src_t, include_hook=False):
        """First output time at which source time src_t is shown in the main body."""
        t = 0.0
        for s, n, hook in self.segments:
            d = n / self.fps
            if (not hook or include_hook) and s <= src_t < s + d:
                return t + (src_t - s)
            t += d
        return None


# --------------------------------------------------------------------------
# Text: words with a thick outline and shadow; colour emoji from Noto
# --------------------------------------------------------------------------
EMOJI_RE = re.compile(
    "([\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]+)")


class TextRenderer:
    def __init__(self):
        self.emoji_font = ImageFont.truetype(EMOJI_FONT, 109) if os.path.exists(EMOJI_FONT) else None
        self._emoji = {}

    def emoji(self, ch, size):
        key = (ch, size)
        if key not in self._emoji:
            im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((10, 10), ch, font=self.emoji_font, embedded_color=True)
            im = im.crop(im.getbbox() or (0, 0, 1, 1))
            s = size / max(im.size)
            self._emoji[key] = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                                         Image.LANCZOS)
        return self._emoji[key]

    def tokens(self, text, highlight):
        """Split into (word, colour) tokens; emoji runs become their own tokens."""
        hl = {w.upper() for w in highlight}
        out = []
        for word in text.split():
            for part in EMOJI_RE.split(word):
                if not part:
                    continue
                if EMOJI_RE.fullmatch(part):
                    out.append((part, "emoji"))
                else:
                    clean = re.sub(r"[^\wÀ-ÿ]", "", part).upper()
                    out.append((part, "hl" if clean in hl or part.upper() in hl else "plain"))
        return out

    def render(self, text, size, color=WHITE, hl_color=YELLOW, highlight=(), max_w=W - 120,
               stroke=None, upper=True):
        if upper:
            text = text.upper()
        fnt = font("ExtraBold", size)
        stroke = stroke if stroke is not None else max(4, size // 9)
        space = fnt.getlength(" ")
        asc, desc = fnt.getmetrics()
        line_h = asc + desc

        # measure tokens, glue emoji to the previous word
        items = []
        for tok, kind in self.tokens(text, highlight):
            if kind == "emoji":
                if not self.emoji_font:
                    continue
                ims = [self.emoji(c, int(size * 0.95)) for c in tok if c not in "️‍"]
                w = sum(i.width for i in ims) + 4 * (len(ims) - 1)
                items.append(("emoji", ims, w))
            else:
                items.append((kind, tok, fnt.getlength(tok)))

        lines, cur, cur_w = [], [], 0
        for it in items:
            add = it[2] + (space if cur else 0)
            if cur and cur_w + add > max_w:
                lines.append((cur, cur_w))
                cur, cur_w = [], 0
                add = it[2]
            cur.append(it)
            cur_w += add
        if cur:
            lines.append((cur, cur_w))

        pad = stroke + 18
        img_w = int(max(w for _, w in lines)) + pad * 2
        img_h = len(lines) * line_h + pad * 2
        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        mask = Image.new("L", img.size, 0)
        md, d = ImageDraw.Draw(mask), ImageDraw.Draw(img)
        emoji_pastes = []
        for li, (line, lw) in enumerate(lines):
            x, y = (img_w - lw) / 2, pad + li * line_h
            for j, (kind, val, w) in enumerate(line):
                if j:
                    x += space
                if kind == "emoji":
                    ex = x
                    for e in val:
                        emoji_pastes.append((e, int(ex), int(y + (line_h - e.height) / 2 - size * 0.04)))
                        ex += e.width + 4
                else:
                    md.text((x, y), val, font=fnt, fill=255, stroke_width=stroke, stroke_fill=255)
                    d.text((x, y), val, font=fnt, fill=hl_color if kind == "hl" else color,
                           stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += w
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(9)).point(lambda v: int(v * 0.7)))
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(shadow, (0, 6))
        out.alpha_composite(img)
        for e, ex, ey in emoji_pastes:
            out.alpha_composite(e, (ex, ey))
        return out


def pop_scale(p):
    """easeOutBack from 0.55 to 1.0"""
    p = min(max(p, 0.0), 1.0)
    c1, c3 = 1.9, 2.9
    e = 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
    return 0.55 + 0.45 * e


def paste_scaled(canvas, img, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if scale != 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BICUBIC)
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 1.0:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# --------------------------------------------------------------------------
# Compositing
# --------------------------------------------------------------------------
class Composer:
    def __init__(self, cfg, tl):
        self.cfg, self.tl, self.fps = cfg, tl, tl.fps
        tr = self.tr = TextRenderer()

        # static chrome: header + tag + soft shadow under the clip
        chrome = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if cfg.get("tag"):
            tag = tr.render(cfg["tag"], 34, color=(235, 235, 235), stroke=3, upper=False)
            paste_scaled(chrome, tag, W / 2, TAG_Y)
        # each header line stays on one line: shrink it to fit instead of wrapping
        y = HEADER_Y - (len(cfg["header"]) - 1) * 58
        for i, line in enumerate(cfg["header"]):
            img = tr.render(line, 92, color=WHITE if i == 0 else YELLOW, stroke=10, max_w=10 ** 5)
            paste_scaled(chrome, img, W / 2, y, scale=min(1.0, (W - 50) / img.width))
            y += 116
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([0, FG_Y - 6, W, FG_Y + FG_H + 6], fill=(0, 0, 0, 170))
        self.fg_shadow = sh.filter(ImageFilter.GaussianBlur(18))
        self.chrome = chrome

        # captions -> output-time windows
        self.captions = []
        hook = cfg.get("hook")
        if hook:
            img = tr.render(hook["text"], hook.get("size", 84), highlight=hook.get("highlight", []))
            self.captions.append((0.0, tl.segments[0][1] / self.fps, img, True))
        for c in cfg["captions"]:
            a = self._first_out(c["start"], c["end"])
            if a is None:
                continue
            b = self._last_out(c["start"], c["end"])
            img = tr.render(c["text"], c.get("size", 76), highlight=c.get("highlight", []))
            self.captions.append((a, b, img, c.get("big", False)))

        total_s = tl.total / self.fps
        cta = cfg.get("cta")
        self.cta = None
        if cta:
            self.cta = (total_s - cta["seconds"],
                        tr.render(cta["text"], cta.get("size", 70), color=WHITE, hl_color=PINK,
                                  highlight=cta.get("highlight", [])))

        # punch moments in output time (hook copy included)
        self.punches = []
        for p in cfg.get("punch", []):
            for inc in (True, False):
                t = tl.out_time(p, include_hook=inc)
                if t is not None and t not in self.punches:
                    self.punches.append(t)
        self.cut_times = []
        t = 0.0
        for _, n, _ in tl.segments[:-1]:
            t += n / self.fps
            self.cut_times.append(t)

    def _first_out(self, a, b):
        t = 0.0
        for s, n, hook in self.tl.segments:
            d = n / self.fps
            if not hook and overlaps((s, s + d), (a, b)):
                return t + max(0.0, a - s)
            t += d
        return None

    def _last_out(self, a, b):
        t, last = 0.0, None
        for s, n, hook in self.tl.segments:
            d = n / self.fps
            if not hook and overlaps((s, s + d), (a, b)):
                last = t + min(d, b - s)
            t += d
        return last

    def zoom_shake(self, t):
        zoom, dx, dy = 1.0, 0.0, 0.0
        for c in self.cut_times:
            k = t - c
            if 0 <= k < CUT_PUNCH:
                zoom = max(zoom, 1 + CUT_ZOOM * (1 - k / CUT_PUNCH) ** 2)
        for p in self.punches:
            k = t - p
            if 0 <= k < 0.9:
                zoom = max(zoom, 1 + 0.22 * math.exp(-k * 3.0))
                amp = 22 * math.exp(-k * 6.0)
                dx += amp * math.sin(k * 90)
                dy += amp * math.cos(k * 73)
        return zoom, dx, dy

    def frame(self, n, src):
        t = n / self.fps
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))

        # blurred background from the same frame
        small = src.resize((96, 54), Image.BILINEAR)
        bw = int(54 * W / H)
        small = small.crop(((96 - bw) // 2, 0, (96 - bw) // 2 + bw, 54))
        bg = small.filter(ImageFilter.GaussianBlur(2.2)).resize((W, H), Image.BICUBIC)
        bg = Image.eval(bg, lambda v: int(v * 0.45))
        canvas.paste(bg.convert("RGBA"), (0, 0))
        canvas.alpha_composite(self.fg_shadow)

        # foreground clip with zoom punches / shake
        zoom, dx, dy = self.zoom_shake(t)
        cw = SRC_W * FG_CROP / zoom
        ch = SRC_H / zoom
        cx, cy = SRC_W / 2 + dx, SRC_H / 2 + dy
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        fg = src.resize((FG_W, FG_H), Image.BICUBIC, box=box)
        canvas.paste(fg, (0, FG_Y))

        canvas.alpha_composite(self.chrome)

        # captions (the call-to-action takes over the slot at the end)
        in_cta = self.cta and t >= self.cta[0]
        for a, b, img, big in self.captions:
            if not in_cta and a <= t < b:
                k = t - a
                s = pop_scale(k / POP)
                if big:
                    s *= 1 + 0.04 * math.sin(k * 9)
                paste_scaled(canvas, img, W / 2, CAPTION_Y, scale=s, alpha=min(1.0, k / 0.08 + 0.2),
                             angle=-5 * max(0.0, 1 - k / POP))
                break
        if in_cta:
            k = t - self.cta[0]
            paste_scaled(canvas, self.cta[1], W / 2, CAPTION_Y,
                         scale=pop_scale(k / POP) * (1 + 0.03 * math.sin(k * 7)))
        return canvas.convert("RGB")


# --------------------------------------------------------------------------
def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "shorts", "tsukasa_celular.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    fps = cfg.get("fps", 30)
    src = os.path.join(ROOT, cfg["source"])
    if not os.path.exists(src):
        sys.exit(f"source clip not found: {src}")
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)

    set_layout(cfg.get("fg_crop", 0.92))
    duration = probe_duration(src)
    edl = build_edl(cfg, src, duration)
    tl = Timeline(edl, fps, cfg.get("hook"))
    kept = sum(b - a for a, b in edl)
    print(f"Source {duration:.1f}s -> body {kept:.1f}s in {len(edl)} pieces, "
          f"total {tl.total / fps:.1f}s with hook")

    tmp = tempfile.mkdtemp(prefix="short_")
    try:
        # 1) cut + concat (frame-accurate), normalised working size
        print("Cutting…")
        parts, labels = [], ""
        # low-res sources get a light sharpen after upscaling
        sharpen = ",unsharp=5:5:0.7" if probe_height(src) < 600 else ""
        for i, (a, b) in enumerate(tl.ffmpeg_ranges()):
            parts.append(f"[0:v]trim={a:.4f}:{b:.4f},setpts=PTS-STARTPTS,fps={fps},"
                         f"scale={SRC_W}:{SRC_H}:flags=lanczos{sharpen},setsar=1[v{i}];"
                         f"[0:a]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d=0.02,afade=t=out:st={max(0, b - a - 0.03):.4f}:d=0.03[a{i}];")
            labels += f"[v{i}][a{i}]"
        fc = "".join(parts) + f"{labels}concat=n={len(parts)}:v=1:a=1[v][a]"
        cut = os.path.join(tmp, "cut.mp4")
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-c:a", "pcm_s16le",
             cut.replace(".mp4", ".mkv")])
        cut = cut.replace(".mp4", ".mkv")

        # 2) audio: original + bass hits on the punches, loudness-normalised
        comp = Composer(cfg, tl)
        hits = sorted(comp.punches)
        boom = os.path.join(tmp, "boom.wav")
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "aevalsrc='0.9*sin(2*PI*(42+90*exp(-9*t))*t)*exp(-3.2*t)+0.25*sin(2*PI*84*t)*exp(-6*t)'"
             ":s=48000:d=1.2", "-ac", "2", boom])
        audio = os.path.join(tmp, "mix.wav")
        ainputs = ["-i", cut]
        filt = "[0:a]aresample=48000,aformat=channel_layouts=stereo[base];"
        mix = "[base]"
        for i, t in enumerate(hits):
            ainputs += ["-i", boom]
            ms = int(t * 1000)
            filt += f"[{i + 1}:a]adelay={ms}|{ms},volume={cfg.get('hit_volume', 0.5)}[h{i}];"
            mix += f"[h{i}]"
        filt += (f"{mix}amix=inputs={len(hits) + 1}:duration=first:normalize=0,"
                 f"loudnorm=I=-14:TP=-1.5:LRA=11[out]")
        run(["ffmpeg", "-y", "-v", "error", *ainputs, "-filter_complex", filt, "-map", "[out]",
             "-ar", "48000", audio])

        # 3) composite frames in Python, encode
        print("Compositing…")
        dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", cut, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               stdout=subprocess.PIPE)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-i", audio, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        fsize = SRC_W * SRC_H * 3
        for n in range(tl.total):
            buf = dec.stdout.read(fsize)
            if len(buf) < fsize:
                break
            frame = Image.frombytes("RGB", (SRC_W, SRC_H), buf)
            enc.stdin.write(comp.frame(n, frame).tobytes())
            if n % (fps * 5) == 0:
                print(f"  {n / fps:5.1f}s / {tl.total / fps:.1f}s")
        dec.stdout.close()
        dec.wait()
        enc.stdin.close()
        if enc.wait():
            sys.exit("final encode failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("Done ->", out)


if __name__ == "__main__":
    main()
