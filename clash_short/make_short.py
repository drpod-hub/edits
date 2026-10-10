#!/usr/bin/env python3
"""Cut a 16:9 Clash Royale video into a 1080x1920 YouTube Short.

The edit decision list lives in edit.json: each clip is a source range plus a
framing mode, chapter and caption. Every frame is composited here (blurred
fill, punch-zoomed foreground, header, pop-in caption, flash, progress bar)
and piped to ffmpeg. Audio is the source audio for the same ranges with
synthesized whoosh/boom hits on the cuts, normalized to -14 LUFS.

Usage:  python3 clash_short/make_short.py [edit.json] [--source path.mp4]
"""
import json
import math
import os
import random
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1080, 1920
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_DIR = os.path.join(ROOT, "fonts")

FG_Y = 470              # top of the 1080x1080 foreground band
FG_H = 1080
HEADER_Y = 300          # centre of the header block
CAPTION_Y = 1390        # centre of the caption (sits over the bottom of the clip)
BAR_Y = FG_Y + FG_H     # progress bar under the clip

YELLOW = (255, 221, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

PUNCH = 0.22            # seconds of zoom-punch at the start of every clip
POP = 0.18              # caption pop-in time
FLASH = 0.12            # white flash on a new chapter


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"), size)


def ease_out_back(p):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


# --------------------------------------------------------------------------
# Text: "*word*" is yellow, "|" breaks the line. Thick black stroke + shadow.
# --------------------------------------------------------------------------
def parse_runs(text):
    lines = []
    for line in text.split("|"):
        runs, hot = [], False
        for i, part in enumerate(line.split("*")):
            if part:
                runs.append((part, YELLOW if i % 2 else WHITE))
        lines.append(runs)
    return lines


def render_text(text, size, max_w=W - 120, stroke=None):
    lines = parse_runs(text)
    fnt = font("ExtraBold", size)
    while max(sum(fnt.getlength(t) for t, _ in ln) for ln in lines) > max_w and fnt.size > 30:
        fnt = font("ExtraBold", fnt.size - 2)
    stroke = stroke or max(4, fnt.size // 9)
    asc, desc = fnt.getmetrics()
    lh = int((asc + desc) * 0.92)
    pad = stroke + 18
    widths = [sum(fnt.getlength(t) for t, _ in ln) for ln in lines]
    img = Image.new("RGBA", (int(max(widths)) + pad * 2, lh * len(lines) + desc + pad * 2), (0, 0, 0, 0))

    def draw(d, offset, solid=None):
        for li, (ln, lw) in enumerate(zip(lines, widths)):
            x = (img.width - lw) / 2
            y = pad + li * lh + offset
            for t, col in ln:
                d.text((x, y), t, font=fnt, fill=solid or col, stroke_width=stroke,
                       stroke_fill=solid or BLACK)
                x += fnt.getlength(t)

    mask = Image.new("L", img.size, 0)
    draw(ImageDraw.Draw(mask), 6, solid=255)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.8)))
    img.alpha_composite(shadow)
    draw(ImageDraw.Draw(img), 0)
    return img


def render_header(chapter):
    text = render_text(chapter["header"], 76 if "|" in chapter["header"] else 72)
    badge = chapter.get("badge")
    if not badge:
        return text
    bf = font("ExtraBold", 64)
    bw, bh = int(bf.getlength(badge)) + 44, 96
    b = Image.new("RGBA", (bw + 16, bh + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle([8, 12, bw + 8, bh + 12], 22, fill=(0, 0, 0, 160))
    d.rounded_rectangle([8, 6, bw + 8, bh + 6], 22, fill=YELLOW, outline=BLACK, width=5)
    d.text((8 + bw / 2, 6 + bh / 2 + 2), badge, font=bf, fill=BLACK, anchor="mm")
    out = Image.new("RGBA", (max(b.width, text.width), b.height + text.height - 14), (0, 0, 0, 0))
    out.alpha_composite(b, ((out.width - b.width) // 2, 0))
    out.alpha_composite(text, ((out.width - text.width) // 2, b.height - 14))
    return out


def popped(img, t, dur=POP, start_scale=1.7, tilt=0.0):
    """img scaled/faded for a pop-in t seconds after it appears."""
    if t >= dur:
        return img
    p = max(t, 0) / dur
    s = start_scale - (start_scale - 1) * ease_out_back(p)
    im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BICUBIC)
    if tilt:
        im = im.rotate(tilt * (1 - p) ** 2, resample=Image.BICUBIC, expand=True)
    a = min(1.0, p * 2.5)
    if a < 1:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def paste_c(canvas, img, cx, cy):
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# --------------------------------------------------------------------------
# Source frames
# --------------------------------------------------------------------------
def probe_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", path],
                       capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def read_frames(src, start, n, fps, sw, sh):
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", src, "-frames:v", str(n),
         "-vf", f"fps={fps},eq=saturation=1.25:contrast=1.06,format=rgb24",
         "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = sw * sh * 3
    last = None
    for _ in range(n):
        buf = p.stdout.read(size)
        if len(buf) == size:
            last = Image.frombytes("RGB", (sw, sh), buf)
        yield last  # repeats the final frame if the source runs short
    p.stdout.close()
    p.wait()


def lerp_cx(cx, p):
    if isinstance(cx, list):
        return cx[0] + (cx[1] - cx[0]) * p
    return cx


def compose_bg(frame):
    sw, sh = frame.size
    cw = sh * W // H
    small = frame.crop(((sw - cw) // 2, 0, (sw - cw) // 2 + cw, sh)).resize((60, 107), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(2.5))
    bg = small.resize((W, H), Image.BILINEAR)
    return ImageEnhance.Brightness(bg).enhance(0.42).convert("RGBA")


def compose_fg(frame, clip, t, dur, sharpen=True):
    sw, sh = frame.size
    p = t / dur
    # punch from 1.14x down to the clip zoom, then a slow push-in
    k = min(t / PUNCH, 1)
    zoom = clip.get("zoom", 1.0) * (1 + 0.14 * (1 - ease_out_cubic(k))) * (1 + 0.05 * p)
    if clip.get("mode") == "wide":
        out_w, out_h = W, int(W * sh / sw)
        cw, ch = sw / zoom, sh / zoom
    else:
        out_w, out_h = W, FG_H
        cw = ch = sh / zoom
    cx = lerp_cx(clip.get("cx", 0.5), p) * sw
    x0 = min(max(cx - cw / 2, 0), sw - cw)
    y0 = (sh - ch) / 2
    fg = frame.resize((out_w, out_h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
    if sharpen:  # only worth it when upscaling low-res sources
        fg = fg.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    return fg


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------
def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])


def build_audio(src, plan, total, tmp):
    parts, labels = [], []
    for i, (clip, start_out, n, fps) in enumerate(plan):
        a, b = clip["src"], clip["src"] + n / fps
        parts.append(f"[0:a]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"afade=t=in:d=0.03,afade=t=out:st={n / fps - 0.04:.4f}:d=0.04[a{i}]")
        labels.append(f"[a{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(labels)}:v=0:a=1[src]"

    # synthesized hits: boom on chapter changes, whoosh into every other cut
    sfx, k = [], 0
    for i, (clip, start_out, n, fps) in enumerate(plan):
        if i == 0 or clip["chapter"] != plan[i - 1][0]["chapter"]:
            ms = int(start_out * 1000)
            sfx.append(f"aevalsrc='0.9*sin(2*PI*(38+110*exp(-t*14))*t)*exp(-t*4.5)':s=48000:d=0.9,"
                       f"aformat=channel_layouts=stereo,adelay={ms}|{ms}[s{k}]")
            k += 1
        if i > 0:
            ms = max(0, int((start_out - 0.22) * 1000))
            sfx.append(f"anoisesrc=d=0.34:c=pink:a=0.5:s=48000,highpass=f=500,lowpass=f=5000,"
                       f"afade=t=in:d=0.22:curve=exp,afade=t=out:st=0.22:d=0.12,volume=0.55,"
                       f"aformat=channel_layouts=stereo,adelay={ms}|{ms}[s{k}]")
            k += 1
    graph += ";" + ";".join(sfx)
    graph += (f";[src]{''.join(f'[s{j}]' for j in range(k))}amix=inputs={k + 1}:normalize=0:duration=first,"
              f"loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000,alimiter=limit=0.84:attack=0.5:release=40:level=false,atrim=0:{total:.4f}[out]")
    out = os.path.join(tmp, "audio.m4a")
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-filter_complex", graph, "-map", "[out]",
         "-c:a", "aac", "-b:a", "192k", out])
    return out


# --------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    src_override = None
    if "--source" in args:
        i = args.index("--source")
        src_override = args[i + 1]
        del args[i:i + 2]
    edl_path = args[0] if args else os.path.join(HERE, "edit.json")
    with open(edl_path) as f:
        edl = json.load(f)
    fps = edl["fps"]
    src = src_override or os.path.join(ROOT, edl["source"])
    if not os.path.exists(src):
        sys.exit(f"source video not found: {src}  (pass --source path.mp4)")
    out = os.path.join(ROOT, edl["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sw, sh = probe_size(src)

    plan, t = [], 0.0
    for clip in edl["clips"]:
        n = int(round(clip["dur"] * fps))
        plan.append((clip, t, n, fps))
        t += n / fps
    total_frames = sum(n for _, _, n, _ in plan)
    total = total_frames / fps
    print(f"{len(plan)} clips, {total:.1f}s")

    headers = {k: render_header(v) for k, v in edl["chapters"].items()}
    captions = [render_text(c["caption"], 92) if c.get("caption") else None for c, *_ in plan]

    with tempfile.TemporaryDirectory(prefix="short_") as tmp:
        print("Building audio…")
        audio = build_audio(src, plan, total, tmp)

        print("Rendering frames…")
        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-i", audio, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
             "-profile:v", "high", "-c:a", "copy", "-movflags", "+faststart", "-shortest", out],
            stdin=subprocess.PIPE)
        rng = random.Random(7)
        done = 0
        chapter_start = 0.0
        for ci, (clip, start_out, n, _) in enumerate(plan):
            new_chapter = ci == 0 or clip["chapter"] != plan[ci - 1][0]["chapter"]
            if new_chapter:
                chapter_start = start_out
            dur = n / fps
            for fi, frame in enumerate(read_frames(src, clip["src"], n, fps, sw, sh)):
                t = fi / fps
                canvas = compose_bg(frame)
                fg = compose_fg(frame, clip, t, dur, edl.get("sharpen", True))
                dx = dy = 0
                if clip.get("shake") and t < 0.35:
                    amp = 18 * (1 - t / 0.35)
                    dx, dy = rng.uniform(-amp, amp), rng.uniform(-amp, amp)
                fy = FG_Y + (FG_H - fg.height) // 2
                canvas.paste(fg, (int(dx), int(fy + dy)))
                # thin rim so the clip reads as a card on the blurred fill
                d = ImageDraw.Draw(canvas)
                d.line([(0, fy - 2), (W, fy - 2)], fill=(0, 0, 0, 255), width=4)
                d.line([(0, fy + fg.height), (W, fy + fg.height)], fill=(0, 0, 0, 255), width=4)

                hdr = headers[clip["chapter"]]
                paste_c(canvas, popped(hdr, start_out + t - chapter_start, 0.24, 1.5, tilt=-6),
                        W / 2, HEADER_Y)
                if captions[ci] is not None:
                    paste_c(canvas, popped(captions[ci], t - 0.03), W / 2, CAPTION_Y)

                prog = (done + 1) / total_frames
                d = ImageDraw.Draw(canvas)
                d.rectangle([0, BAR_Y, W, BAR_Y + 12], fill=(0, 0, 0, 255))
                d.rectangle([0, BAR_Y + 2, int(W * prog), BAR_Y + 10], fill=YELLOW + (255,))

                if new_chapter and ci > 0 and t < FLASH:  # frame 0 is the thumbnail: no flash
                    a = int(200 * (1 - t / FLASH))
                    canvas.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, a)))

                enc.stdin.write(canvas.convert("RGB").tobytes())
                done += 1
            print(f"  clip {ci + 1}/{len(plan)}  ({done / fps:.1f}s)")
        enc.stdin.close()
        if enc.wait():
            sys.exit("encode failed")
    print("Done ->", out)


if __name__ == "__main__":
    main()
