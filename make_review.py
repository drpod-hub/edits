#!/usr/bin/env python3
"""Render an "ARTIST REVIEW" vertical (1080x1920) edit.

Layout mirrors the "OUTKAST REVIEW" format: a red title on a white rounded
box, nine rows (BIGGEST ... BEST ALBUM, then ARTIST RATING), and each row's
answer (green song title + yellow stream count) popping in while that song's
clip and audio play behind it. The rating pops in near the end.

Usage:  python3 make_review.py review_config.json

Background/audio handling (clips, audio, placeholders, loudness matching) is
shared with make_video.py.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from make_video import (H, ROOT, W, build_segment, hex_rgb, load_cover,
                        paste_centered, paste_left, resolve, run, text_runs)

FONT_DIR = os.path.join(ROOT, "fonts")

# Geometry measured from the reference (720x1280), scaled x1.5.
TITLE_CY = 340
TITLE_BOX_W, TITLE_BOX_H, TITLE_RADIUS = 584, 147, 16
ROW_X = 90              # left edge of the row labels
ROW_TOP = 490           # centre y of the first row label
ROW_PITCH = 133
VALUE_GAP = 26          # space between "LABEL:" and its value
STREAMS_DY = 57         # streams line, below the song title

WHITE = (255, 255, 255)
RED = (255, 22, 22)
GREEN = (52, 255, 40)
YELLOW = (255, 228, 58)

POP_IN = 0.28
SQUEEZE = 0.84          # horizontal squeeze on answer text (reference uses a condensed face)

LABELS = ["BIGGEST", "SMALLEST", "BEST", "WORST", "UNDERRATED", "OVERRATED",
          "BEST FEATURE", "BEST ALBUM"]


def anton(size):
    return ImageFont.truetype(os.path.join(FONT_DIR, "Anton-Regular.ttf"), size)


def lilita(size):
    return ImageFont.truetype(os.path.join(FONT_DIR, "LilitaOne-Regular.ttf"), size)


def squeeze(img, pad):
    """Condense rendered text horizontally; returns (img, scaled left pad)."""
    return img.resize((max(1, int(img.width * SQUEEZE)), img.height), Image.LANCZOS), int(pad * SQUEEZE)


def pop(img, sx, cy, spad, t):
    """Pop-in transform (scale 1.6 -> 1, tilt, fade) anchored at the left edge."""
    p = min(1.0, t / POP_IN)
    c1, c3 = 1.70158, 2.70158
    e = 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
    scale = 1.6 - 0.6 * e
    w, h = img.size
    im = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BICUBIC)
    cx = sx - spad * scale + im.width / 2
    im = im.rotate(8 * (1 - p) ** 2, resample=Image.BICUBIC, expand=True)
    if p < 0.5:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * p * 2)))
    return im, (int(cx - im.width / 2), int(cy - im.height / 2))


class ReviewOverlay:
    def __init__(self, cfg):
        base = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # title on a white rounded box
        box = Image.new("RGBA", (TITLE_BOX_W + 40, TITLE_BOX_H + 40), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle([20, 24, TITLE_BOX_W + 20, TITLE_BOX_H + 24],
                                              TITLE_RADIUS, fill=(0, 0, 0, 120))
        base.alpha_composite(box.filter(ImageFilter.GaussianBlur(10)),
                             (W // 2 - TITLE_BOX_W // 2 - 20, TITLE_CY - TITLE_BOX_H // 2 - 20))
        ImageDraw.Draw(base).rounded_rectangle(
            [W // 2 - TITLE_BOX_W // 2, TITLE_CY - TITLE_BOX_H // 2,
             W // 2 + TITLE_BOX_W // 2, TITLE_CY + TITLE_BOX_H // 2],
            TITLE_RADIUS, fill=WHITE)
        tf = anton(78)
        while tf.getlength(cfg["title"]) > TITLE_BOX_W - 50:
            tf = anton(tf.size - 2)
        title, _ = text_runs([(cfg["title"], RED)], tf, stroke=2, shadow=4)
        paste_centered(base, title, W / 2, TITLE_CY + 2)

        label_font = anton(64)
        song_font, streams_font = lilita(48), lilita(45)
        self.slots = []  # (x, cy, img, pad) for each answer, then the rating
        rows = LABELS + ["ARTIST RATING"]
        for i, label in enumerate(rows):
            cy = ROW_TOP + i * ROW_PITCH
            colour = RED if label == "ARTIST RATING" else WHITE
            limg, lpad = text_runs([(label + ":", colour)], label_font, stroke=3, shadow=6)
            paste_left(base, limg, lpad, ROW_X, cy)
            vx = ROW_X + label_font.getlength(label + ":") + VALUE_GAP

            if label == "ARTIST RATING":
                img, pad = text_runs([(cfg["rating"], YELLOW)], anton(64), stroke=3, shadow=6)
                self.slots.append((vx, cy, img, pad))
                continue

            item = cfg["items"][i]
            sf = song_font
            while sf.getlength(item["song"]) * SQUEEZE > W - vx - 30 and sf.size > 24:
                sf = lilita(sf.size - 1)
            song, spad = squeeze(*text_runs([(item["song"], GREEN)], sf, stroke=3, shadow=5))
            lines = [(song, spad, 0)]
            if item.get("streams"):
                st, stpad = squeeze(*text_runs([(f"({item['streams']} streams)", YELLOW)],
                                               streams_font, stroke=3, shadow=5))
                lines.append((st, stpad, STREAMS_DY))
            # stack the song and streams lines into one image so they pop together
            pad = max(p for _, p, _ in lines)
            top = min(-im.height / 2 + dy for im, _, dy in lines)
            bottom = max(im.height / 2 + dy for im, _, dy in lines)
            wid = max(im.width - p + pad for im, p, _ in lines)
            img = Image.new("RGBA", (int(wid), int(bottom - top)), (0, 0, 0, 0))
            for im, p, dy in lines:
                img.alpha_composite(im, (pad - p, int(dy - im.height / 2 - top)))
            # keep the song line centred on the label: shift by the stack's offset
            self.slots.append((vx, cy + 4 + (top + bottom) / 2, img, pad))
        self.base = base
        self._static = {}

    def static(self, n):
        if n not in self._static:
            img = self.base.copy()
            for sx, cy, simg, spad in self.slots[:n]:
                paste_left(img, simg, spad, sx, cy)
            self._static[n] = img
        return self._static[n]

    def frame(self, n_done, anim=None):
        """n_done answers fully shown; anim=(slot index, seconds since it appeared)."""
        if anim is None or anim[1] >= POP_IN:
            return self.static(n_done + (1 if anim else 0))
        img = self.static(n_done).copy()
        sx, cy, simg, spad = self.slots[anim[0]]
        im, pos = pop(simg, sx, cy, spad, anim[1])
        img.alpha_composite(im, pos)
        return img


def placeholder_bg(item, tmp, i):
    """Dark gradient card used as the 'cover' when an item has none."""
    p = os.path.join(tmp, f"ph{i:02d}.png")
    img = Image.new("RGB", (800, 800), (20, 20, 24))
    d = ImageDraw.Draw(img)
    for y in range(800):
        k = y / 800
        d.line([(0, y), (800, y)], fill=(int(30 + 30 * k), int(20 + 10 * k), int(40 + 20 * k)))
    return img


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "review_config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    assert len(cfg["items"]) == len(LABELS), f"need {len(LABELS)} items ({', '.join(LABELS)})"
    fps, dur = cfg["fps"], cfg["segment_seconds"]
    rating_at = cfg.get("rating_delay", 4.0)
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="review_")
    try:
        print("Building background segments…")
        segs = []
        for i, item in enumerate(cfg["items"]):
            cover = load_cover(item) if resolve(item.get("cover")) else placeholder_bg(item, tmp, i)
            segs.append(build_segment(i, item, cover, cfg, tmp))
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{p}'\n" for p in segs)
        bg = os.path.join(tmp, "bg.mp4")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg])

        print("Rendering overlay + compositing…")
        overlay = ReviewOverlay(cfg)
        per = int(round(dur * fps))
        last = len(cfg["items"]) - 1
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-i", bg,
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]",
             "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        cache = {}
        for n in range(per * len(cfg["items"])):
            seg, k = divmod(n, per)
            t = k / fps
            if seg == last and t >= rating_at:
                key, args = ("r", t - rating_at), (seg + 1, (seg + 1, t - rating_at))
            else:
                key, args = (seg, t), (seg, (seg, t))
            if key[1] >= POP_IN:
                ck = key[0]
                if ck not in cache:
                    cache[ck] = overlay.frame(*args).tobytes()
                enc.stdin.write(cache[ck])
            else:
                enc.stdin.write(overlay.frame(*args).tobytes())
        enc.stdin.close()
        if enc.wait():
            sys.exit("final encode failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("Done ->", out)


if __name__ == "__main__":
    main()
