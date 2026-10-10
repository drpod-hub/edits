"""Real Madrid 0-4 Barcelona (La Liga 2015/16) -> vertical highlights Short with scorer captions.

usage: python3 clasico.py SRC.mp4 WORKDIR OUT.mp4

Layout (1080x1920): blurred fill background, the 16:9 broadcast in a centre panel, a live
scoreboard under it that ticks over on each goal, and a "GOAL! / scorer + minute" caption.
Each block keeps the broadcast's own commentary running continuously from its first shot,
so the goal calls carry over the replays and celebrations.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SRC, WORK, OUT = sys.argv[1:4]
W, H, FPS = 1080, 1920, 30
PANEL_H, PANEL_Y = 700, 540
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Each block: caption, goal time within the block (score ticks over / caption pops), and its
# shots as (src_start, src_end, speed). Times read off the broadcast scorebug and clock.
BLOCKS = [
    dict(cap=("GOAL!", "LUIS SUÁREZ 11'"), goal=5.4, shots=[
        (49.5, 55.3, 1.0),     # build-up, Suárez finishes
        (55.4, 57.2, 1.0),     # net cam
        (57.3, 60.3, 1.0),     # celebration
    ]),
    dict(cap=("GOAL!", "NEYMAR 39'"), goal=3.6, shots=[
        (217.5, 222.7, 1.0),   # live
        (265.0, 268.0, 0.7),   # close replay, slowed
        (277.0, 279.8, 1.0),   # fist pump
    ]),
    dict(cap=("GOAL!", "ANDRÉS INIESTA 53'"), goal=5.6, shots=[
        (330.8, 336.6, 1.0),   # live
        (336.8, 339.1, 1.0),   # celebration
    ]),
    dict(cap=("GOAL!", "LUIS SUÁREZ 74'"), goal=5.2, shots=[
        (415.0, 420.5, 1.0),   # live
        (420.6, 423.6, 1.0),   # knee slide
        (432.2, 434.6, 1.0),   # Ronaldo
        (437.2, 440.0, 1.0),   # Suárez + Messi
    ]),
    dict(cap=("RED CARD", "ISCO 84'"), goal=0.0, red=True, audio_from=484.6, shots=[
        (509.5, 513.0, 1.0),   # foul on Neymar (replay)
        (484.6, 487.0, 1.0),   # referee shows red
        (498.3, 500.5, 1.0),   # Isco walks
    ]),
    dict(cap=("...AND MESSI", "STARTED ON THE BENCH"), goal=0.0, outro=True, shots=[
        (236.7, 239.4, 0.8),
    ]),
]

GRADE = "eq=contrast=1.06:saturation=1.18:brightness=0.01"


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode:
        print(r.stderr.decode()[-3000:])
        raise SystemExit(1)


# ---------- overlays ----------

def font(size):
    return ImageFont.truetype(BOLD, size)


def shadowed(layer):
    a = layer.split()[3].point(lambda v: int(v * 0.75))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a)
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (5, 7))
    out.alpha_composite(layer)
    return out


def txt(d, xy, s, size, fill, stroke=6, anchor="mm"):
    d.text(xy, s, font=font(size), fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def make_overlays():
    # Static header
    im = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(im)
    txt(d, (W / 2, 300), "EL CLÁSICO", 110, (255, 255, 255), 8)
    txt(d, (W / 2, 410), "LA LIGA 2015/16 · SANTIAGO BERNABÉU", 38, (255, 210, 60), 5)
    shadowed(im).save(f"{WORK}/header.png")

    # Scoreboard states 0-0 .. 0-4
    for k in range(5):
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        y = PANEL_Y + PANEL_H + 95
        d.rounded_rectangle([70, y - 62, W - 70, y + 62], radius=30, fill=(10, 12, 24, 225))
        d.rounded_rectangle([W / 2 - 115, y - 52, W / 2 + 115, y + 52], radius=18, fill=(255, 255, 255, 255))
        d.text((W / 2 - 50, y), "0", font=font(78), fill=(20, 20, 30), anchor="mm")
        d.text((W / 2, y - 4), "-", font=font(70), fill=(20, 20, 30), anchor="mm")
        d.text((W / 2 + 50, y), str(k), font=font(78), fill=(165, 0, 68), anchor="mm")
        d.text((W / 2 - 145, y), "REAL MADRID", font=font(44), fill=(255, 255, 255), anchor="rm")
        d.text((W / 2 + 145, y), "BARCELONA", font=font(44), fill=(255, 255, 255), anchor="lm")
        # club-colour underlines: white for Madrid, blue/garnet for Barça
        d.rectangle([W / 2 - 145 - 290, y + 30, W / 2 - 145, y + 36], fill=(235, 235, 235))
        d.rectangle([W / 2 + 145, y + 30, W / 2 + 145 + 145, y + 36], fill=(0, 77, 152))
        d.rectangle([W / 2 + 145 + 145, y + 30, W / 2 + 145 + 290, y + 36], fill=(205, 18, 45))
        shadowed(im).save(f"{WORK}/score{k}.png")

    # Captions
    for i, b in enumerate(BLOCKS):
        im = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(im)
        y = PANEL_Y + PANEL_H + 245
        big, small = b["cap"]
        if b.get("red"):
            d.rounded_rectangle([W / 2 - 330, y - 55, W / 2 - 270, y + 30], radius=8, fill=(225, 20, 30))
            txt(d, (W / 2 + 30, y - 12), big, 96, (255, 60, 60), 8)
        elif b.get("outro"):
            txt(d, (W / 2, y - 12), big, 80, (255, 255, 255), 8)
        else:
            txt(d, (W / 2, y - 12), big, 112, (255, 215, 0), 9)
        txt(d, (W / 2, y + 88), small, 66 if not b.get("outro") else 60, (255, 255, 255), 7)
        shadowed(im).save(f"{WORK}/cap{i}.png")


# ---------- video ----------

def render_shot(path, s, e, speed, punch_at=None):
    dur = (e - s) / speed
    pw = round(240 * W / PANEL_H)  # source crop width matching the panel aspect
    z = "1"
    if punch_at is not None:
        z = f"(1+if(gte(t\\,{punch_at:.3f})\\,0.12*exp(-(t-{punch_at:.3f})*2.5)\\,0))"
    fg = [
        "hqdn3d=2:1.5:4:3",
        f"crop={pw}:240:(iw-{pw})/2:0",
        f"minterpolate=fps={round(FPS / speed)}:mi_mode=mci:mc_mode=aobmc:vsbmc=1" if speed < 1 else f"fps={FPS}",
        f"setpts=(PTS-STARTPTS)/{speed}",
        f"fps={FPS}",
        f"scale=w='trunc({W}*{z}/2)*2':h='trunc({PANEL_H}*{z}/2)*2':eval=frame:flags=lanczos",
        f"crop={W}:{PANEL_H}:(iw-{W})/2:(ih-{PANEL_H})/2",
        "unsharp=7:7:1.1:5:5:0", GRADE,
    ]
    bg = ["scale=1080:1920:force_original_aspect_ratio=increase", "crop=1080:1920",
          "boxblur=24:3", "eq=brightness=-0.22:saturation=0.85",
          f"setpts=(PTS-STARTPTS)/{speed}", f"fps={FPS}"]
    fc = (f"[0:v]split[a][b];[a]{','.join(bg)}[bg];[b]{','.join(fg)}[fg];"
          f"[bg][fg]overlay=0:{PANEL_Y},drawbox=x=0:y={PANEL_Y - 4}:w={W}:h=4:color=white@0.85:t=fill,"
          f"drawbox=x=0:y={PANEL_Y + PANEL_H}:w={W}:h=4:color=white@0.85:t=fill,"
          f"trim=duration={dur:.3f},setpts=PTS-STARTPTS[v]")
    run(["ffmpeg", "-y", "-ss", f"{s:.3f}", "-t", f"{e - s + 0.5:.3f}", "-i", SRC, "-filter_complex", fc,
         "-map", "[v]", "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "15",
         "-pix_fmt", "yuv420p", path])
    return dur


def main():
    os.makedirs(WORK, exist_ok=True)
    make_overlays()
    files, auds, t = [], [], 0.0
    events = []  # (block index, block start, goal time abs, block end)
    for bi, b in enumerate(BLOCKS):
        start, local = t, 0.0
        for si, (s, e, sp) in enumerate(b["shots"]):
            p = f"{WORK}/b{bi}s{si}.mp4"
            punch = b["goal"] - local if (not b.get("red") and not b.get("outro")
                                          and 0 <= b["goal"] - local < (e - s) / sp) else None
            d = render_shot(p, s, e, sp, punch) if not os.path.exists(p) else (e - s) / sp
            files.append(p)
            local += d
        t += local
        # Commentary runs continuously from the block's first shot (or a chosen point).
        a0 = b.get("audio_from", b["shots"][0][0])
        ap = f"{WORK}/b{bi}.wav"
        run(["ffmpeg", "-y", "-ss", f"{a0:.3f}", "-t", f"{local:.3f}", "-i", SRC, "-vn", "-ac", "2", "-ar", "48000",
             "-af", f"afade=t=in:d=0.08,afade=t=out:st={max(local - 0.12, 0):.3f}:d=0.12", ap])
        auds.append(ap)
        events.append((bi, start, start + b["goal"], t))
        print(f"block {bi}: {start:6.2f}-{t:6.2f}  goal@{start + b['goal']:.2f}")
    total = t

    with open(f"{WORK}/v.txt", "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in files)
    with open(f"{WORK}/a.txt", "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in auds)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/v.txt", "-c", "copy", f"{WORK}/video.mp4"])
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/a.txt", "-c", "copy", f"{WORK}/audio.wav"])

    # Overlay pass
    goals = [g for bi, s, g, e in events if not BLOCKS[bi].get("red") and not BLOCKS[bi].get("outro")]
    inputs = ["-i", f"{WORK}/video.mp4", "-i", f"{WORK}/audio.wav"]
    img = lambda p: ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", p]
    inputs += img(f"{WORK}/header.png")
    for k in range(5):
        inputs += img(f"{WORK}/score{k}.png")
    for i in range(len(BLOCKS)):
        inputs += img(f"{WORK}/cap{i}.png")
    fc, cur = [], "[0:v]"
    fc.append(f"{cur}[2:v]overlay=0:0[h]")
    cur = "[h]"
    bounds = [0.0] + goals + [total + 1]
    for k in range(5):
        fc.append(f"{cur}[{3 + k}:v]overlay=0:0:enable='between(t,{bounds[k]:.3f},{bounds[k + 1]:.3f})'[s{k}]")
        cur = f"[s{k}]"
    for bi, s, g, e in events:
        b = BLOCKS[bi]
        on = s + 0.2 if b.get("red") or b.get("outro") else g + 0.15
        n = 8 + bi
        fc.append(f"[{n}:v]format=rgba,fade=t=in:st={on:.3f}:d=0.25:alpha=1,"
                  f"fade=t=out:st={e - 0.25:.3f}:d=0.2:alpha=1[c{bi}]")
        fc.append(f"{cur}[c{bi}]overlay=0:0:enable='between(t,{on:.3f},{e:.3f})'[o{bi}]")
        cur = f"[o{bi}]"
    # white flash on each goal, red flash on the card
    flashes = [f"between(t,{g:.3f},{g + 0.1:.3f})" for g in goals]
    rc = next(s for bi, s, g, e in events if BLOCKS[bi].get("red"))
    fc.append(f"{cur}drawbox=x=0:y=0:w=iw:h=ih:color=white@0.55:t=fill:enable='{'+'.join(flashes)}',"
              f"drawbox=x=0:y=0:w=iw:h=ih:color=red@0.35:t=fill:enable='between(t,{rc + 3.5:.3f},{rc + 3.6:.3f})',"
              f"fade=t=in:d=0.3,fade=t=out:st={total - 0.5:.3f}:d=0.5,format=yuv420p[v]")
    fc.append(f"[1:a]loudnorm=I=-13:TP=-1.0:LRA=9,afade=t=out:st={total - 0.6:.3f}:d=0.6[a]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", OUT])
    print("total", round(total, 2))


if __name__ == "__main__":
    main()
