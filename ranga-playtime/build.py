#!/usr/bin/env python3
"""Build a vertical YouTube Short from the Crunchyroll "Survive Ranga Playtime Challenge" clip.

Usage: python3 build.py SOURCE.mp4 OUTPUT.mp4 [WORKDIR]

Layout (1080x1920): blurred/darkened background, full-width 16:9 video in the
middle, a big title on top, meme stickers that pop over the video's top edge,
dialogue subtitles (Japanese audio, English captions) under the video and a
progress bar. Opens with the payoff as a cold-open hook, then "HOW IT STARTED".
"""
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_TITLE = os.path.join(HERE, "fonts", "Anton.ttf")
FONT_COMIC = os.path.join(HERE, "fonts", "Bangers.ttf")
FONT_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

W, H = 1080, 1920
VID_H = 608
VID_Y = 640
SPEED = 1.1  # global speed-up for pacing (pitch preserved)

YELLOW = (255, 214, 10)
WHITE = (255, 255, 255)

# (src_start, src_end, zoom). First entry is the cold-open hook.
SEGMENTS = [
    (58.30, 61.50, 1.00),  # HOOK: washing-machine spin + Ranga pinning him
    (2.00, 10.60, 1.00),   # general / captain challenge
    (10.60, 19.60, 1.00),  # Ranga bowls through the knights
    (19.60, 22.70, 1.20),  # captain's shocked face (zoom punch)
    (24.19, 33.87, 1.00),  # captain powers up, Gobta rides in
    (48.09, 58.30, 1.00),  # Gobta's battle cry
    (58.30, 63.81, 1.00),  # spin + "playtime"
    (63.81, 70.20, 1.00),  # Gobta: stop, he'll die
    (70.20, 76.45, 1.18),  # Ranga: doesn't he want to play more? (zoom)
    (76.45, 79.50, 1.00),
    (79.50, 82.60, 1.18),  # "...that would be bad."
]

TITLE = "HE TRIED TO 1v1\nRIMURU'S *'GOOD BOY'* 💀"

# Subtitles: (speaker or None, text with *highlight*, src_start, src_end)
SUBS = [
    (None, "You! Take on *THAT* thing!", 2.50, 4.60),
    (None, "Bison! Garcia! Guard the *GENERAL!*", 4.90, 10.50),
    (None, "N-NOOO!", 12.47, 13.40),
    (None, "*HYAAAH!*", 19.90, 21.00),
    (None, "You *BASTARD!*", 21.50, 22.70),
    (None, "*WHAT?!*", 25.40, 26.60),
    ("GOBTA", "*AAAAAAAAH!*", 51.60, 53.20),
    ("GOBTA", "H-HYAH!", 55.70, 58.20),
    ("GOBTA", "Ranga-san, *STOP!* Any more and he'll *DIE!*", 64.40, 67.30),
    (None, "Oh no! We need to *heal* him, quick!", 67.40, 70.15),
    ("RANGA", "Hm? But doesn't he want to *PLAY* some more?", 70.20, 74.70),
    ("GOBTA", "Nonono, he does *NOT!*", 74.70, 76.40),
    (None, "Exactly! Stop now, or *Lord Rimuru* will...", 76.45, 79.45),
    ("RANGA", "...That would be *BAD.*", 79.50, 81.40),
]
SPEAKER_COLORS = {"GOBTA": (120, 220, 90), "RANGA": (150, 170, 255)}

# Meme stickers: (text, bg color, rotation deg, src_start, src_end, segment index or None)
POPS = [
    ("HOW IT ENDED 💀", (230, 40, 40), -4, 58.30, 61.50, 0),
    ("HOW IT STARTED 👇", (25, 25, 25), 3, 2.00, 4.20, None),
    ("BOWLING FOR KNIGHTS 🎳", (230, 40, 40), -3, 13.30, 17.68, None),
    ("THE 'PUPPY' ⚡", (110, 70, 230), 4, 17.68, 19.60, None),
    ("BRO JUST REALIZED 😨", (25, 25, 25), -3, 19.60, 22.70, None),
    ("MAIN CHARACTER AURA ✨", (240, 150, 0), 3, 24.19, 31.20, None),
    ("...MEANWHILE GOBTA 🐺", (60, 160, 60), -4, 31.20, 33.87, None),
    ("GOBTA'S BATTLE CRY 🗣️", (60, 160, 60), 3, 51.63, 53.68, None),
    ("WASHING MACHINE MODE 🌀", (30, 120, 230), -4, 58.31, 60.06, 6),
    ("PLAYTIME 🐶", (230, 40, 40), 4, 60.06, 63.81, 6),
    ("HIS IDEA OF 'GENTLE' 🐾", (110, 70, 230), -3, 70.20, 74.70, None),
    ("THE ONE NAME HE FEARS 😰", (25, 25, 25), 3, 79.50, 81.46, None),
    ("RANGA 1 — KNIGHTS 0 🏆", (240, 150, 0), -3, 81.46, 82.60, None),
]

# Bass "boom" hits on the punchlines (src time, segment index or None)
BOOMS = [(58.31, 0), (70.20, None), (79.50, None)]


# ---------------------------------------------------------------- timeline

def seg_offsets():
    offs, t = [], 0.0
    for s, e, _ in SEGMENTS:
        offs.append(t)
        t += e - s
    return offs, t


OFFS, TOTAL = seg_offsets()


def to_out(t, seg=None):
    """Map a source time to output (pre-speed) time. Story segments win over the hook."""
    idxs = [seg] if seg is not None else range(1, len(SEGMENTS))
    for i in idxs:
        s, e, _ = SEGMENTS[i]
        if s - 1e-3 <= t <= e + 1e-3:
            return OFFS[i] + (t - s)
    raise ValueError(f"time {t} not in any segment")


def span(a, b, seg=None):
    """Output span for a source span, clipped to the segment(s) it falls in."""
    idxs = [seg] if seg is not None else range(1, len(SEGMENTS))
    for i in idxs:
        s, e, _ = SEGMENTS[i]
        if s - 1e-3 <= a < e:
            return OFFS[i] + (a - s), OFFS[i] + (min(b, e) - s)
    # start fell in a gap: find first segment overlapping
    for i in idxs:
        s, e, _ = SEGMENTS[i]
        if a < e and b > s:
            return OFFS[i] + (max(a, s) - s), OFFS[i] + (min(b, e) - s)
    raise ValueError(f"span {a}-{b} not in any segment")


# ---------------------------------------------------------------- text render

EMOJI_RE = re.compile(
    "([\U0001F300-\U0001FAFF☀-➿⭐✨⚡\U0001F000-\U0001F2FF]️?)"
)
_emoji_font = ImageFont.truetype(FONT_EMOJI, 109)


def parse(line, base, hl):
    """'a *b* c' -> [(text, color, is_emoji)]"""
    runs = []
    for i, part in enumerate(line.split("*")):
        color = hl if i % 2 else base
        for piece in EMOJI_RE.split(part):
            if not piece:
                continue
            runs.append((piece, color, bool(EMOJI_RE.fullmatch(piece))))
    return runs


def emoji_img(ch, size):
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=_emoji_font, embedded_color=True)
    im = im.crop(im.getbbox())
    r = size / im.height
    return im.resize((max(1, int(im.width * r)), size), Image.LANCZOS)


def run_width(runs, font, size):
    w = 0
    for text, _, emo in runs:
        w += emoji_img(text, int(size * 0.9)).width + 8 if emo else font.getlength(text)
    return w


def wrap(text, font, size, max_w):
    out = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for wd in words:
            cand = (line + " " + wd).strip()
            if line and run_width(parse(cand.replace("*", ""), WHITE, WHITE), font, size) > max_w:
                out.append(line)
                line = wd
            else:
                line = cand
        out.append(line)
    # re-balance '*' markup that got split across lines
    fixed, open_ = [], False
    for ln in out:
        if open_:
            ln = "*" + ln
        open_ = ln.count("*") % 2 == 1
        if open_:
            ln = ln + "*"
        fixed.append(ln)
    return fixed


def draw_lines(canvas, lines, font_path, size, cx, top, base=WHITE, hl=YELLOW,
               stroke=8, line_gap=1.12, shadow=True):
    font = ImageFont.truetype(font_path, size)
    d = ImageDraw.Draw(canvas)
    y = top
    for ln in lines:
        runs = parse(ln, base, hl)
        lw = run_width(runs, font, size)
        x = cx - lw / 2
        for text, color, emo in runs:
            if emo:
                em = emoji_img(text, int(size * 0.9))
                canvas.alpha_composite(em, (int(x + 4), int(y + size * 0.08)))
                x += em.width + 8
                continue
            if shadow:
                d.text((x + 6, y + 8), text, font=font, fill=(0, 0, 0, 150),
                       stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
            d.text((x, y), text, font=font, fill=color, stroke_width=stroke,
                   stroke_fill=(0, 0, 0))
            x += font.getlength(text)
        y += size * line_gap
    return y


def render_title(path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    font = ImageFont.truetype(FONT_TITLE, 104)
    lines = wrap(TITLE, font, 104, W - 100)
    n = len(lines)
    top = 330 - (n * 104 * 1.12) / 2
    draw_lines(im, lines, FONT_TITLE, 104, W / 2, top, stroke=9)
    im.save(path)


def render_sub(path, speaker, text):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    size = 84
    font = ImageFont.truetype(FONT_COMIC, size)
    top = VID_Y + VID_H + 70
    if speaker:
        tag_font = ImageFont.truetype(FONT_COMIC, 52)
        tw = tag_font.getlength(speaker)
        d = ImageDraw.Draw(im)
        col = SPEAKER_COLORS.get(speaker, (200, 200, 200))
        d.rounded_rectangle((W / 2 - tw / 2 - 22, top - 6, W / 2 + tw / 2 + 22, top + 62),
                            radius=16, fill=col + (255,))
        d.text((W / 2 - tw / 2, top + 2), speaker, font=tag_font, fill=(15, 15, 15))
        top += 82
    lines = wrap(text, font, size, W - 120)
    draw_lines(im, lines, FONT_COMIC, size, W / 2, top, stroke=7)
    im.save(path)


def render_pop(path, text, bg, rot):
    size = 76
    font = ImageFont.truetype(FONT_COMIC, size)
    runs = parse(text, WHITE, WHITE)
    tw = run_width(runs, font, size)
    pad_x, pad_y = 34, 18
    tile = Image.new("RGBA", (int(tw + pad_x * 2), int(size * 1.05 + pad_y * 2)), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), radius=22,
                        fill=bg + (255,), outline=(255, 255, 255), width=6)
    draw_lines(tile, [text], FONT_COMIC, size, tile.width / 2, pad_y, stroke=5, shadow=False)
    tile = tile.rotate(rot, resample=Image.BICUBIC, expand=True)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    im.alpha_composite(tile, (int(W / 2 - tile.width / 2), int(VID_Y - tile.height / 2 + 6)))
    im.save(path)


# ---------------------------------------------------------------- ffmpeg

def build(src, out, work):
    os.makedirs(work, exist_ok=True)
    inputs = ["-i", src]
    overlays = []  # (png path, out_start, out_end)

    title_png = os.path.join(work, "title.png")
    render_title(title_png)
    overlays.append((title_png, 0.0, TOTAL))

    for i, (spk, text, a, b) in enumerate(SUBS):
        p = os.path.join(work, f"sub{i:02d}.png")
        render_sub(p, spk, text)
        overlays.append((p, *span(a, b)))

    for i, (text, bg, rot, a, b, seg) in enumerate(POPS):
        p = os.path.join(work, f"pop{i:02d}.png")
        render_pop(p, text, bg, rot)
        overlays.append((p, *span(a, b, seg)))

    fc = []
    # cut + layout every segment
    for i, (s, e, z) in enumerate(SEGMENTS):
        vw = int(round(W * z / 2)) * 2
        vh = int(round(VID_H * z / 2)) * 2
        fc.append(f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS,fps=24000/1001,"
                  f"scale={vw}:{vh},crop={W}:{VID_H},setsar=1[v{i}]")
        d = e - s
        fc.append(f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d=0.02,afade=t=out:st={d - 0.03:.3f}:d=0.03[a{i}]")
    n = len(SEGMENTS)
    fc.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[fg][dlg]")
    fc.append("[fg]split[fg1][fg2]")
    fc.append(f"[fg2]scale=-2:{H // 2},crop={W // 2}:{H // 2},boxblur=18:2,"
              f"eq=brightness=-0.22:saturation=1.3,scale={W}:{H}[bg]")
    fc.append(f"[bg][fg1]overlay=0:{VID_Y}[base0]")

    # progress bar under the video
    fc.append(f"color=c=0xFF7A00:s={W}x12:d={TOTAL:.3f},format=rgba[bar]")
    fc.append(f"[base0][bar]overlay=x='-{W}+{W}*t/{TOTAL:.3f}':y={VID_Y + VID_H}[base1]")

    # white flash when the hook hands over to the story
    flash_t = OFFS[1]
    fc.append(f"color=c=white:s={W}x{H}:d=0.35,format=rgba,fade=t=out:st=0:d=0.35:alpha=1,"
              f"setpts=PTS+{flash_t:.3f}/TB[flash]")

    cur = "base1"
    for k, (png, a, b) in enumerate(overlays):
        idx = k + 1  # input 0 is the source video
        inputs += ["-loop", "1", "-t", f"{b - a:.3f}", "-framerate", "24000/1001", "-i", png]
        fade = "" if k == 0 else ",fade=t=in:st=0:d=0.10:alpha=1"
        fc.append(f"[{idx}:v]format=rgba{fade},setpts=PTS+{a:.3f}/TB[o{k}]")
        fc.append(f"[{cur}][o{k}]overlay=0:0:eof_action=pass[c{k}]")
        cur = f"c{k}"
    fc.append(f"[{cur}][flash]overlay=0:0:eof_action=pass[vfull]")
    fc.append(f"[vfull]setpts=PTS/{SPEED},format=yuv420p[vout]")

    # audio: dialogue + booms, sped up, loudness-normalised
    boom_labels = []
    for k, (t, seg) in enumerate(BOOMS):
        ot = to_out(t, seg)
        fc.append(f"aevalsrc='0.9*sin(2*PI*(48+40*exp(-12*t))*t)*exp(-3.2*t)':s=48000:d=1.2,"
                  f"aformat=channel_layouts=stereo,adelay={int(ot * 1000)}:all=1[boom{k}]")
        boom_labels.append(f"[boom{k}]")
    fc.append(f"[dlg]aformat=sample_rates=48000:channel_layouts=stereo[dlg2]")
    fc.append(f"[dlg2]{''.join(boom_labels)}amix=inputs={1 + len(boom_labels)}:"
              f"duration=first:normalize=0[mix]")
    fc.append(f"[mix]atempo={SPEED},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    graph = os.path.join(work, "graph.txt")
    with open(graph, "w") as f:
        f.write(";\n".join(fc))

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex_script", graph, "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
           "-r", "24000/1001", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           "-t", f"{TOTAL / SPEED:.3f}", out]
    subprocess.run(cmd, check=True)
    print(f"done: {out}  ({TOTAL / SPEED:.1f}s)")


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    work = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(out)), "_work")
    build(src, out, work)
