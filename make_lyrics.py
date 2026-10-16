#!/usr/bin/env python3
"""Burn word-by-word lyrics onto a clip in the TEENZ_VINYL style.

Thin condensed white type, a left-aligned block of 2-3 lines whose lines
(except the last) are justified to the block width, each word popping in on
its beat with a quick fade, and the whole block cutting to the next phrase.

    python3 make_lyrics.py lyrics_ivy.json   # -> output/ivy_lyrics.mp4
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent


def probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate:format=duration",
        "-of", "json", str(path)])
    d = json.loads(out)
    s = d["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    return s["width"], s["height"], num / den, float(d["format"]["duration"])


def word_sprite(word, font, cfg):
    """White word with tight tracking, squeezed horizontally, soft glow."""
    size = cfg["font_size"]
    track = cfg["tracking"]
    pad = size // 2
    w = int(sum(font.getlength(c) + track for c in word)) + 2 * pad
    h = int(size * 1.4) + 2 * pad
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    x = pad
    for c in word:
        d.text((x, pad), c, font=font, fill=255)
        x += font.getlength(c) + track
    mask = mask.resize((max(1, int(w * cfg["squeeze"])), h), Image.LANCZOS)

    glow = mask.filter(ImageFilter.GaussianBlur(size * 0.12))
    shadow = mask.filter(ImageFilter.GaussianBlur(size * 0.06))
    img = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), (0, 0), shadow.point(lambda v: v * 0.45))
    layer = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    layer.putalpha(glow.point(lambda v: v * 0.35))
    img = Image.alpha_composite(img, layer)
    layer = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    layer.putalpha(mask)
    img = Image.alpha_composite(img, layer)
    adv = (x - pad) * cfg["squeeze"]  # inked advance, without padding
    return img, adv, int(pad * cfg["squeeze"]), pad


def layout_block(block, font, cfg):
    """Return [(time, sprite, x, y)] with all but the last line justified."""
    space = font.getlength(" ") * cfg["squeeze"] * 0.8
    lines = []
    for line in block["lines"]:
        sprites = [word_sprite(w, font, cfg) for w in line.split()]
        natural = sum(s[1] for s in sprites) + space * (len(sprites) - 1)
        lines.append((sprites, natural))
    width = max(n for _, n in lines)

    times = iter(block["times"])
    placed = []
    y = cfg["y"]
    for i, (sprites, natural) in enumerate(lines):
        gap = space
        if i < len(lines) - 1 and len(sprites) > 1:
            gap = (width - sum(s[1] for s in sprites)) / (len(sprites) - 1)
        x = cfg["x"]
        for img, adv, px, py in sprites:
            placed.append((next(times), img, int(x) - px, int(y) - py))
            x += adv + gap
        y += cfg["font_size"] * cfg["line_height"]
    return placed


def main():
    cfg = json.loads((ROOT / (sys.argv[1] if len(sys.argv) > 1 else "lyrics_ivy.json")).read_text())
    video = ROOT / cfg["video"]
    out = ROOT / cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    W, H, fps, dur = probe(video)

    font = ImageFont.truetype(str(ROOT / cfg["font"]), cfg["font_size"])
    try:
        font.set_variation_by_axes([cfg["weight"]])
    except Exception:
        pass

    blocks = cfg["blocks"]
    for b in blocks:
        assert len(b["times"]) == sum(len(l.split()) for l in b["lines"]), b["lines"]
    starts = [b["times"][0] for b in blocks]
    ends = starts[1:] + [cfg["end"]]
    laid = [layout_block(b, font, cfg) for b in blocks]
    fade = cfg["fade_frames"] / fps

    ff = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y",
        "-i", str(video),
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto[v]",
        "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "17",
        "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy",
        "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)

    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    last_key, last_bytes = None, blank.tobytes()
    for f in range(int(round(dur * fps))):
        t = f / fps
        visible = []
        for words, s, e in zip(laid, starts, ends):
            if s <= t < e:
                for wt, img, x, y in words:
                    if t >= wt:
                        visible.append((min(1.0, (t - wt) / fade + 1 / cfg["fade_frames"]), img, x, y))
        key = tuple((round(a, 3), x, y) for a, _, x, y in visible)
        if key != last_key:
            frame = blank.copy()
            for a, img, x, y in visible:
                if a < 1:
                    img = img.copy()
                    img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
                frame.alpha_composite(img, (x, y))
            last_key, last_bytes = key, frame.tobytes()
        ff.stdin.write(last_bytes)
    ff.stdin.close()
    if ff.wait():
        sys.exit("ffmpeg failed")
    print(out)


if __name__ == "__main__":
    main()
