#!/usr/bin/env python3
"""Build a PADS·12 trailer from a scripted capture (trailer/capture.mjs).

Usage:  python3 trailer/compose.py [steam|tiktok]

steam  -> output/pads12_steam_trailer.mp4   1920x1080, captions in the strip left of the device
tiktok -> output/pads12_tiktok.mp4          1080x1920, captions in a band above the device

Inputs (trailer/build/<format>/): screen.webm (Playwright video) and audio.webm (the site's
own output). The magenta sync marker shown at t0 is located in the video so picture and
sound line up exactly.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FORMAT = "tiktok" if len(sys.argv) > 1 and sys.argv[1] == "tiktok" else "steam"
W, H = (1080, 1920) if FORMAT == "tiktok" else (1920, 1080)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build", FORMAT)
OUT = os.path.join(ROOT, "output", "pads12_tiktok.mp4" if FORMAT == "tiktok" else "pads12_steam_trailer.mp4")
FONTS = os.path.join(ROOT, "fonts")
PIX_B = os.path.join(FONTS, "Silkscreen-Bold.ttf")
PIX = os.path.join(FONTS, "Silkscreen-Regular.ttf")
BODY = os.path.join(FONTS, "Barlow-Medium.ttf")

INK = (244, 240, 250)
SOFT = (196, 188, 214)
NEON = [(255, 61, 240), (61, 252, 255), (125, 255, 61), (255, 232, 61)]

LEAD = 0.45                 # skip the sync marker
DUR = 35.0
END_AT = 31.3
CTA = "WISHLIST NOW ON STEAM"
SCENES = [  # kicker, heading lines, subline, colour, capture-time window
    ("SAMPLER", ["12 PADS.", "YOUR SOUNDS."], "Drop in samples and play them with mouse, keys or touch.", NEON[0], 3.0, 9.4),
    ("KIT IMPORT", ["IMPORT", "ANY KIT."], "Every kick, snare and hat lands on the right pad.", NEON[1], 9.6, 14.4),
    ("DRUM MACHINE", ["ORGANIC", "DRUMS."], "Tape saturation, heavy compression and a swirling phaser.", NEON[2], 14.6, 21.8),
    ("KEYS", ["BUILD", "CHORDS."], "One key, one chord. Or turn any sound into an instrument.", NEON[3], 22.0, 31.0),
]


def font(path, size):
    return ImageFont.truetype(path, size)


def fit(path, lines, width, start, floor=20):
    size = start
    while size > floor and max(font(path, size).getlength(l) for l in lines) > width:
        size -= 2
    return size


def glow_text(img, xy, text, f, color, glow, radius=10, anchor="la"):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=f, fill=glow + (255,), anchor=anchor)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=color + (255,), anchor=anchor)


def wrap(text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if f.getlength(t) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def night_bg(alpha=255):
    bg = Image.new("RGBA", (W, H))
    top, mid, bot = (9, 11, 34), (37, 23, 71), (106, 43, 95)
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        if t < 0.62:
            c = [int(top[i] + (mid[i] - top[i]) * min(1, t * 1.6)) for i in range(3)]
        else:
            c = [int(mid[i] + (bot[i] - mid[i]) * (t - 0.62) / 0.38) for i in range(3)]
        d.line([(0, y), (W, y)], fill=tuple(c) + (alpha,))
    return bg


def brand(img, cx, cy, size, glow):
    """'PADS·12' with a drawn square dot (the pixel face's middle dot reads as a dash when large)."""
    f = font(PIX_B, size)
    a, b = "PADS", "12"
    gap = size * 0.55
    wa, wb = f.getlength(a), f.getlength(b)
    x0 = cx - (wa + gap + wb) / 2
    glow_text(img, (x0, cy), a, f, INK, glow, size // 9, "lm")
    glow_text(img, (x0 + wa + gap, cy), b, f, INK, glow, size // 9, "lm")
    dot = size * 0.16
    dx = x0 + wa + gap / 2
    ImageDraw.Draw(img).rectangle([dx - dot / 2, cy - dot / 2, dx + dot / 2, cy + dot / 2], fill=INK + (255,))


def brand_size(width):
    size = 230
    while size > 60:
        f = font(PIX_B, size)
        if f.getlength("PADS") + f.getlength("12") + size * 0.55 <= width:
            return size
        size -= 4
    return size


def caption(kicker, head, sub, color, name):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    d = ImageDraw.Draw(img)
    if FORMAT == "steam":
        pd.rounded_rectangle([40, 330, 470, 760], 26, fill=(8, 6, 20, 175))
        img.alpha_composite(panel.filter(ImageFilter.GaussianBlur(2)))
        x, y = 78, 372
        d.text((x, y), kicker, font=font(PIX_B, 26), fill=color + (255,))
        y += 58
        size = fit(PIX_B, head, 360, 52)
        for line in head:
            glow_text(img, (x, y), line, font(PIX_B, size), INK, color, 12)
            y += int(size * 1.3)
        y += 18
        for line in wrap(sub, font(BODY, 30), 360):
            d.text((x, y), line, font=font(BODY, 30), fill=SOFT + (255,))
            y += 40
    else:
        # band above the device, clear of TikTok's top bar
        pd.rounded_rectangle([50, 150, W - 50, 440], 30, fill=(8, 6, 20, 185))
        img.alpha_composite(panel.filter(ImageFilter.GaussianBlur(2)))
        cx = W // 2
        d.text((cx, 196), kicker, font=font(PIX_B, 30), fill=color + (255,), anchor="mm")
        line = " ".join(head)
        size = fit(PIX_B, [line], W - 180, 70)
        glow_text(img, (cx, 278), line, font(PIX_B, size), INK, color, 12, "mm")
        sf = font(BODY, 36)
        y = 352
        for l in wrap(sub, sf, W - 200)[:2]:
            d.text((cx, y), l, font=sf, fill=SOFT + (255,), anchor="mm")
            y += 46
    img.save(name)


def title_card(name):
    img = night_bg(232)
    cy = H // 2 - (30 if FORMAT == "steam" else 120)
    size = min(190, brand_size(W - 140))
    brand(img, W // 2, cy, size, NEON[0])
    tf = font(PIX, 40 if FORMAT == "steam" else 44)
    lines = ["A BEAT MACHINE FOR LATE-NIGHT IDEAS"] if FORMAT == "steam" else ["A BEAT MACHINE FOR", "LATE-NIGHT IDEAS"]
    y = cy + size * 0.76
    for l in lines:
        ImageDraw.Draw(img).text((W // 2, y), l, font=tf, fill=NEON[1] + (255,), anchor="mm")
        y += 62
    img.save(name)


def end_card(name):
    img = night_bg(255)
    d = ImageDraw.Draw(img)
    if FORMAT == "steam":
        brand(img, W // 2, 400, 210, NEON[0])
        d.text((W // 2, 545), "SAMPLER  ·  KEYS  ·  ORGANIC DRUMS  ·  LOOPER", font=font(PIX, 38), fill=SOFT + (255,), anchor="mm")
        d.text((W // 2, 610), "Import any kit. Play chords. Record your jam.", font=font(BODY, 40), fill=INK + (255,), anchor="mm")
        glow_text(img, (W // 2, 760), CTA, font(PIX_B, 64), (255, 255, 255), NEON[1], 16, "mm")
    else:
        size = min(200, brand_size(W - 140))
        brand(img, W // 2, 640, size, NEON[0])
        y = 640 + size * 0.85
        for l in ["SAMPLER  ·  KEYS", "ORGANIC DRUMS  ·  LOOPER"]:
            d.text((W // 2, y), l, font=font(PIX, 42), fill=SOFT + (255,), anchor="mm")
            y += 60
        y += 30
        for l in ["Import any kit. Play chords.", "Record your jam."]:
            d.text((W // 2, y), l, font=font(BODY, 46), fill=INK + (255,), anchor="mm")
            y += 60
        cs = fit(PIX_B, [CTA], W - 140, 70)
        glow_text(img, (W // 2, y + 150), CTA, font(PIX_B, cs), (255, 255, 255), NEON[1], 16, "mm")
    img.save(name)


def find_sync():
    """Time of the first frame showing the magenta marker in the bottom-left corner."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "screen.webm", "-t", "10", "-vf", f"fps=25,crop=20:20:8:{H - 30}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    px = 20 * 20 * 3
    for i in range(len(raw) // px):
        c = raw[i * px + (10 * 20 + 10) * 3: i * px + (10 * 20 + 10) * 3 + 3]
        if c[0] > 180 and c[1] < 100 and c[2] > 180:
            return i / 25
    sys.exit("sync marker not found in screen.webm")


def main():
    os.chdir(BUILD)
    sync = find_sync()
    title_card("ov_title.png")
    caps = []
    for k, (kicker, head, sub, color, a, b) in enumerate(SCENES):
        caption(kicker, head, sub, color, f"ov_c{k + 1}.png")
        caps.append((f"ov_c{k + 1}.png", a - LEAD, b - LEAD))
    end_card("ov_end.png")

    inputs = ["-i", "screen.webm", "-i", "audio.webm", "-loop", "1", "-t", "3.4", "-i", "ov_title.png"]
    for f, a, b in caps:
        inputs += ["-loop", "1", "-t", f"{b - a:.2f}", "-i", f]
    inputs += ["-loop", "1", "-t", f"{DUR - END_AT:.2f}", "-i", "ov_end.png"]

    fc = [f"[0:v]trim=start={sync + LEAD:.3f}:duration={DUR},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v0]",
          "[2:v]format=rgba,fade=out:st=2.6:d=0.7:alpha=1[t]",
          "[v0][t]overlay=0:0:eof_action=pass[v1]"]
    last = "v1"
    for k, (f, a, b) in enumerate(caps):
        d = b - a
        fc.append(f"[{3 + k}:v]format=rgba,fade=in:st=0:d=0.35:alpha=1,fade=out:st={d - 0.35:.2f}:d=0.35:alpha=1,"
                  f"setpts=PTS-STARTPTS+{a:.2f}/TB[c{k}]")
        fc.append(f"[{last}][c{k}]overlay=0:0:eof_action=pass[v{k + 2}]")
        last = f"v{k + 2}"
    fc.append(f"[{3 + len(caps)}:v]format=rgba,fade=in:st=0:d=0.6:alpha=1,setpts=PTS-STARTPTS+{END_AT}/TB[e]")
    fc.append(f"[{last}][e]overlay=0:0:eof_action=pass,format=yuv420p[vout]")
    fc.append(f"[1:a]atrim=start={LEAD}:duration={DUR},asetpts=PTS-STARTPTS,alimiter=limit=0.9,"
              f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.3,afade=t=out:st={DUR - 2.2}:d=2.2[aout]")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", str(DUR), OUT], check=True)
    print(OUT)


if __name__ == "__main__":
    main()
