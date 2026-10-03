#!/usr/bin/env python3
"""Render a "Popular vs Best" vertical (1080x1920) album edit.

Layout and timing mirror the OWNeast "Popular vs Best Songs" format: a fixed
title block, album covers stacked down the left, and each album's
"Popular:" / "Best:" song popping in one at a time while that song's clip and
audio play behind it.

Usage:  python3 make_video.py [config.json]

Any cover/clip/audio that is missing is replaced by a placeholder (generated
cover card, blurred-cover background, silence), so the video always renders.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "fonts")

# Geometry measured from the reference video (1080x1920).
HANDLE_Y = 184          # centre y of "@owneast"
TITLE1_Y = 226          # centre y of "Popular vs Best"
TITLE2_Y = 292          # centre y of the yellow line
SUB_Y = 340             # centre y of "(in my opinion/part N)"
BLOCK_TOP = 410         # top of the first cover
BLOCK_PITCH = 228       # distance between cover tops
COVER_X, COVER_SIZE = 50, 216
LABEL_X = 284
POPULAR_DY = 48         # label centre y, relative to cover top
BEST_DY = 185
LABEL_GAP = 16          # space between "Popular:" and the song name

GREEN = (34, 230, 28)
YELLOW = (255, 214, 10)
WHITE = (255, 255, 255)

POP_IN = 0.28           # seconds for the song text pop-in animation


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"), size)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def resolve(path):
    if not path:
        return None
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    return p if os.path.exists(p) else None


# --------------------------------------------------------------------------
# Text rendering: coloured runs with a dark outline and a soft drop shadow,
# like the reference.
# --------------------------------------------------------------------------
def text_runs(runs, fnt, stroke=3, shadow=6):
    """Render [(text, rgb), ...] on one line. Returns a tight RGBA image."""
    pad = stroke + shadow * 2 + 4
    widths = [fnt.getlength(t) for t, _ in runs]
    asc, desc = fnt.getmetrics()
    img = Image.new("RGBA", (int(sum(widths)) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))

    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    x = pad
    for (t, _), w in zip(runs, widths):
        md.text((x, pad), t, font=fnt, fill=255, stroke_width=stroke, stroke_fill=255)
        x += w
    shadow_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_img.putalpha(mask.filter(ImageFilter.GaussianBlur(shadow)).point(lambda v: int(v * 0.85)))
    img.alpha_composite(shadow_img, (0, 3))

    d = ImageDraw.Draw(img)
    x = pad
    for (t, col), w in zip(runs, widths):
        d.text((x, pad), t, font=fnt, fill=col, stroke_width=stroke, stroke_fill=(20, 20, 20))
        x += w
    return img, pad


def paste_centered(canvas, img, cx, cy):
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def paste_left(canvas, img, pad, x, cy):
    canvas.alpha_composite(img, (int(x - pad), int(cy - img.height / 2)))


# --------------------------------------------------------------------------
# Covers
# --------------------------------------------------------------------------
def wrap(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def placeholder_cover(album, size=1000):
    base = hex_rgb(album.get("placeholder_color", "#333333"))
    img = Image.new("RGB", (size, size), base)
    d = ImageDraw.Draw(img)
    for i in range(size):  # subtle vertical gradient
        k = 1 - 0.45 * i / size
        d.line([(0, i), (size, i)], fill=tuple(int(c * k) for c in base))
    tf = font("ExtraBold", 110)
    lines = wrap(album["title"].upper(), tf, size * 0.84)
    y = size * 0.5 - len(lines) * 62
    for ln in lines:
        d.text((size / 2, y), ln, font=tf, fill=WHITE, anchor="mt")
        y += 124
    d.text((size / 2, size * 0.86), album["artist"], font=font("SemiBold", 64),
           fill=(230, 230, 230), anchor="mm")
    return img


def load_cover(album):
    p = resolve(album.get("cover"))
    if p:
        img = Image.open(p).convert("RGB")
        s = min(img.size)
        # cover_crop_y: 0 = keep top, 0.5 = centre, 1 = keep bottom (for non-square art)
        fy = album.get("cover_crop_y", 0.5)
        l, t = (img.width - s) // 2, int((img.height - s) * fy)
        return img.crop((l, t, l + s, t + s))
    print(f"  ! cover missing for {album['title']} -> placeholder")
    return placeholder_cover(album)


# --------------------------------------------------------------------------
# Overlay
# --------------------------------------------------------------------------
class Overlay:
    def __init__(self, cfg, covers):
        self.cfg = cfg
        base = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        if cfg.get("handle"):
            handle, _ = text_runs([(cfg["handle"], WHITE)], font("Bold", 30), stroke=2, shadow=5)
            paste_centered(base, handle, W / 2, HANDLE_Y)

        colours = [GREEN, WHITE, GREEN]
        t1, _ = text_runs(list(zip(cfg["title_line1"], colours)), font("ExtraBold", 54), stroke=3)
        paste_centered(base, t1, W / 2, TITLE1_Y)

        f2 = font("ExtraBold", 50)
        while f2.getlength(cfg["title_line2"]) > W - 120 and f2.size > 30:
            f2 = font("ExtraBold", f2.size - 2)
        t2, _ = text_runs([(cfg["title_line2"], YELLOW)], f2, stroke=3)
        paste_centered(base, t2, W / 2, TITLE2_Y)

        sub, _ = text_runs([(cfg["subtitle"], WHITE)], font("SemiBold", 30), stroke=2, shadow=5)
        paste_centered(base, sub, W / 2, SUB_Y)

        label_font = font("Bold", 34)
        self.slots = []  # (x, cy, song_img, pad) in reveal order
        for i, (album, cover) in enumerate(zip(cfg["albums"], covers)):
            top = BLOCK_TOP + i * BLOCK_PITCH
            c = cover.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
            sh = Image.new("RGBA", (COVER_SIZE + 24, COVER_SIZE + 24), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rectangle([12, 12, COVER_SIZE + 12, COVER_SIZE + 12], fill=(0, 0, 0, 140))
            base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (COVER_X - 12, top - 8))
            base.paste(c, (COVER_X, top))

            for key, label, dy in (("popular", "Popular:", POPULAR_DY), ("best", "Best:", BEST_DY)):
                cy = top + dy
                limg, lpad = text_runs([(label, WHITE)], label_font)
                paste_left(base, limg, lpad, LABEL_X, cy)
                s = album[key]
                sx = LABEL_X + label_font.getlength(label) + LABEL_GAP
                sf = label_font
                runs = [(s["song"], hex_rgb(s["color"])), (f" ({s['rating']})", WHITE)]
                while sum(sf.getlength(t) for t, _ in runs) > W - sx - 24 and sf.size > 22:
                    sf = font("Bold", sf.size - 1)
                simg, spad = text_runs(runs, sf)
                self.slots.append((sx, cy, simg, spad))
        self.base = base
        self._static = {}

    def static(self, n):
        """Overlay with the first n songs fully revealed."""
        if n not in self._static:
            img = self.base.copy()
            for sx, cy, simg, spad in self.slots[:n]:
                paste_left(img, simg, spad, sx, cy)
            self._static[n] = img
        return self._static[n]

    def frame(self, seg, t):
        """Overlay for segment index `seg`, t seconds into it."""
        if t >= POP_IN:
            return self.static(seg + 1)
        img = self.static(seg).copy()
        sx, cy, simg, spad = self.slots[seg]
        p = t / POP_IN
        # easeOutBack scale 1.6 -> 1.0, tilt -8deg -> 0, fade in
        c1, c3 = 1.70158, 2.70158
        e = 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
        scale = 1.6 - 0.6 * e
        angle = 8 * (1 - p) ** 2
        w, h = simg.size
        im = simg.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BICUBIC)
        # scale about the text's left edge so it grows out of where it lands
        cx = sx - spad * scale + im.width / 2
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
        if p < 0.5:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * p * 2)))
        img.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))
        return img


# --------------------------------------------------------------------------
# Background segments (ffmpeg)
# --------------------------------------------------------------------------
def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])


def build_segment(i, song, cover, cfg, tmp):
    dur, fps = cfg["segment_seconds"], cfg["fps"]
    out = os.path.join(tmp, f"seg{i:02d}.mp4")
    clip, audio = resolve(song.get("clip")), resolve(song.get("audio"))
    vf_tail = f"fps={fps},format=yuv420p,setsar=1"

    cmd = ["ffmpeg", "-y", "-v", "error"]
    if clip:
        cmd += ["-ss", str(song.get("clip_start", 0)), "-t", str(dur), "-i", clip]
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{vf_tail}"
    else:
        print(f"  ! clip missing for {song['song']} -> blurred cover background")
        cpath = os.path.join(tmp, f"cover{i:02d}.png")
        cover.resize((460, 460), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14)).resize((2300, 2300), Image.BICUBIC).save(cpath)
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", str(dur), "-i", cpath]
        # slow drift so the background isn't static
        vf = (f"crop=w=1180:h=2098:"
              f"x='(in_w-out_w)/2+sin(t*0.9)*90':y='(in_h-out_h)/2+cos(t*0.7)*80',"
              f"scale={W}:{H},eq=brightness=-0.08:saturation=1.15,{vf_tail}")

    if audio:
        cmd += ["-ss", str(song.get("audio_start", 0)), "-t", str(dur), "-i", audio]
        amap = "1:a:0"
    elif clip and has_audio(clip):
        amap = "0:a:0"
    else:
        print(f"  ! audio missing for {song['song']} -> silence")
        cmd += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo"]
        amap = "1:a:0"

    af = f"afade=t=in:d=0.05,afade=t=out:st={dur - 0.08}:d=0.08,aresample=44100,apad"
    cmd += ["-map", "0:v:0", "-map", amap, "-vf", vf, "-af", af, "-t", str(dur),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            "-c:a", "aac", "-b:a", "192k", "-ac", "2", out]
    run(cmd)
    return out


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


# --------------------------------------------------------------------------
def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    fps, dur = cfg["fps"], cfg["segment_seconds"]
    out = os.path.join(ROOT, cfg["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)

    print("Loading covers…")
    covers = [load_cover(a) for a in cfg["albums"]]
    songs = [(a[k], c) for a, c in zip(cfg["albums"], covers) for k in ("popular", "best")]

    tmp = tempfile.mkdtemp(prefix="pvb_")
    try:
        print("Building background segments…")
        segs = [build_segment(i, s, c, cfg, tmp) for i, (s, c) in enumerate(songs)]
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{p}'\n" for p in segs)
        bg = os.path.join(tmp, "bg.mp4")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg])

        print("Rendering overlay + compositing…")
        overlay = Overlay(cfg, covers)
        frames_per_seg = int(round(dur * fps))
        total = frames_per_seg * len(songs)
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-i", bg,
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]",
             "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        cache = {}
        for n in range(total):
            seg, k = divmod(n, frames_per_seg)
            t = k / fps
            if t >= POP_IN:
                key = seg + 1
                if key not in cache:
                    cache[key] = overlay.frame(seg, t).tobytes()
                enc.stdin.write(cache[key])
            else:
                enc.stdin.write(overlay.frame(seg, t).tobytes())
            if n % (fps * 5) == 0:
                print(f"  {n / fps:5.1f}s / {total / fps:.1f}s")
        enc.stdin.close()
        if enc.wait():
            sys.exit("final encode failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("Done ->", out)


if __name__ == "__main__":
    main()
