"""Real Madrid 0-4 Barcelona -> full-screen 9:16 "TikTok style" Short.

usage: python3 clasico_tiktok.py SRC.mp4 SR_WEIGHTS.pth FONT.ttf WORKDIR OUT.mp4

Style follows the reference edit: full-screen vertical (no blurred bars), round team badges with
a "0 x 0" score at the top, and short yellow lowercase captions popping up mid-screen.

Pipeline per shot: decode the 240p broadcast -> pick a 9:16 window (fixed for close-ups, or
auto-tracked on the players for wide shots) -> Real-ESRGAN (realesr-general-x4v3, via onnxruntime) 4x upscale
-> 1080x1920 with grade + zoom punch on goals. The broadcast commentary runs continuously
through each block so the goal calls carry over the cutaways.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr_onnx import Upscaler  # noqa: E402

SRC, WEIGHTS, FONT, WORK, OUT = sys.argv[1:6]
SW, SH = 426, 240           # source frame
CW = 136                    # 9:16 crop width at source res
W, H, FPS = 1080, 1920, 30
AUTO = "auto"

# Blocks of shots: (src_start, src_end, speed, crop_cx | AUTO, [(t_in_shot, caption), ...]).
# "goal" = (shot index, time in shot) where the score ticks over.
BLOCKS = [
    dict(shots=[
        (14.6, 16.4, 1.0, .47, [(0.1, "el clásico"), (0.9, "at the bernabéu")]),
        (19.5, 22.6, 1.0, .63, [(0.1, "benítez"), (1.4, "feeling confident")]),
        (236.7, 239.4, 0.8, .40, [(0.1, "because messi"), (1.6, "is on the bench")]),
    ]),
    dict(goal=(0, 7.3), shots=[
        (47.5, 55.3, 1.0, AUTO, [(0.3, "sergi roberto"), (2.6, "keeps going"), (4.6, "and going"),
                                 (6.3, "suárez..."), (7.3, "goal!!")]),
        (55.4, 57.2, 1.0, .62, [(0.1, "11 minutes")]),
        (57.3, 60.3, 1.0, .60, [(0.1, "too easy")]),
        (71.6, 74.7, 1.0, .50, [(0.2, "cristiano"), (1.4, "not happy")]),
    ]),
    dict(goal=(0, 6.6), shots=[
        (214.5, 222.7, 1.0, AUTO, [(0.3, "barça again"), (3.0, "iniesta's pass"), (5.0, "neymar..."),
                                   (6.6, "goal!!")]),
        (265.0, 268.0, 0.7, AUTO, [(0.2, "slow it down"), (2.4, "cold")]),
        (277.0, 279.8, 1.0, .52, [(0.2, "neymar"), (1.4, "39'")]),
        (232.5, 236.0, 1.0, .48, [(0.2, "ramos"), (1.6, "speechless")]),
    ]),
    dict(goal=(0, 5.6), shots=[
        (330.8, 336.6, 1.0, AUTO, [(0.3, "neymar"), (2.6, "backheel"), (4.0, "iniesta..."),
                                   (5.6, "what a goal")]),
        (336.8, 339.1, 1.0, .48, [(0.1, "don andrés")]),
        (361.6, 364.0, 1.0, .50, [(0.2, "cristiano"), (1.2, "can't believe it")]),
    ]),
    dict(goal=(0, 7.2), shots=[
        (413.0, 420.5, 1.0, AUTO, [(0.3, "counter attack"), (4.5, "suárez..."), (7.2, "again!!")]),
        (420.6, 423.6, 1.0, .40, [(0.2, "four.")]),
        (437.2, 440.0, 1.0, .45, [(0.2, "messi joins in")]),
    ]),
    dict(audio_from=484.6, red=(1, 0.0), shots=[
        (509.5, 513.0, 1.0, AUTO, [(0.2, "isco on neymar"), (2.0, "ouch")]),
        (484.6, 487.0, 1.0, .42, [(0.1, "red card!")]),
        (498.3, 500.5, 1.0, .50, [(0.2, "bye isco")]),
    ]),
    dict(shots=[
        (520.5, 523.5, 1.0, .25, [(0.2, "luis enrique"), (1.5, "loving it")]),
    ]),
]


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


# ---------------- crop tracking ----------------

def track(frames):
    """Per-frame crop centre (px) for wide shots: follow where the players are, biased toward
    the broadcast camera's centre (it usually keeps the ball near the middle), then smoothed."""
    xs = []
    cols = np.arange(SW)
    k = np.exp(-0.5 * (np.arange(-60, 61) / 22.0) ** 2)
    for f in frames.astype(np.int16):
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        grass = (g > r + 12) & (g > b + 12)
        pitch_rows = grass.mean(1) > 0.45
        if pitch_rows.sum() < 40:  # not a pitch shot
            xs.append(SW / 2)
            continue
        players = (~grass) & pitch_rows[:, None]
        # drop thin white lines: keep pixels that are not near-white unless they're in a blob
        hist = players.sum(0).astype(float)
        hist = np.convolve(hist, k, mode="same")
        score = hist * np.exp(-0.5 * ((cols - SW / 2) / 85.0) ** 2)
        xs.append(0.55 * float(np.argmax(score)) + 0.45 * SW / 2)
    xs = np.array(xs)
    # zero-phase smoothing (forward + backward EMA) so the virtual camera glides
    a = 0.08
    for _ in range(2):
        for i in range(1, len(xs)):
            xs[i] = a * xs[i] + (1 - a) * xs[i - 1]
        xs = xs[::-1].copy()
    return xs


# ---------------- overlays ----------------

def font(size, wght=900):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([wght])
    except Exception:
        pass
    return f


def badge_rm(d=200):
    im = Image.new("RGBA", (d, d))
    dr = ImageDraw.Draw(im)
    dr.ellipse([0, 0, d - 1, d - 1], fill=(248, 248, 248))
    dr.ellipse([d * .12, d * .12, d * .88, d * .88], outline=(212, 175, 55), width=int(d * .07))
    dr.text((d / 2, d / 2), "RM", font=font(int(d * .34)), fill=(35, 30, 95), anchor="mm")
    return im


def badge_fcb(d=200):
    im = Image.new("RGBA", (d, d))
    st = Image.new("RGBA", (d, d), (0, 77, 152, 255))
    sd = ImageDraw.Draw(st)
    w = d / 5
    for i in range(1, 5, 2):
        sd.rectangle([i * w, 0, (i + 1) * w, d], fill=(165, 0, 52))
    mask = Image.new("L", (d, d))
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    im.paste(st, (0, 0), mask)
    return im


def soft_shadow(layer, off=(4, 6), blur=8, alpha=0.6):
    a = layer.split()[3].point(lambda v: int(v * alpha))
    s = Image.new("RGBA", layer.size)
    s.putalpha(a)
    s = s.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", layer.size)
    out.alpha_composite(s, off)
    out.alpha_composite(layer)
    return out


def make_score(k):
    im = Image.new("RGBA", (W, H))
    y = 300
    for b, x in ((badge_rm(), 95), (badge_fcb(), W - 95 - 200)):
        im.alpha_composite(b, (x, y - 100))
    d = ImageDraw.Draw(im)
    d.text((W / 2, y), f"0 x {k}", font=font(150), fill=(255, 255, 255), anchor="mm",
           stroke_width=5, stroke_fill=(20, 20, 20))
    return soft_shadow(im)


def make_caption(text):
    im = Image.new("RGBA", (W, 300))
    d = ImageDraw.Draw(im)
    d.text((W / 2, 150), text, font=font(88, 850), fill=(255, 232, 0), anchor="mm",
           stroke_width=7, stroke_fill=(0, 0, 0))
    im = soft_shadow(im, (3, 5), 6, 0.5)
    return im.crop(im.getbbox())


# ---------------- render ----------------

def decode(s, e, speed):
    vf = ["hqdn3d=1.5:1.5:3:3"]
    if speed < 1:
        vf.append(f"minterpolate=fps={round(FPS / speed)}:mi_mode=mci:mc_mode=aobmc:vsbmc=1")
    else:
        vf.append(f"fps={FPS}")
    vf += [f"setpts=(PTS-STARTPTS)/{speed}", f"fps={FPS}"]
    n = int(round((e - s) / speed * FPS))
    raw = sh(["ffmpeg", "-v", "error", "-ss", f"{s:.3f}", "-t", f"{e - s + 0.4:.3f}", "-i", SRC,
              "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, SH, SW, 3)
    return fr[:n]


def render_shot(model, path, s, e, speed, cx, punch=None, flash_red=False):
    fr = decode(s, e, speed)
    xs = track(fr) if cx == AUTO else np.full(len(fr), cx * SW)
    x0 = np.clip(np.round(xs - CW / 2), 0, SW - CW).astype(int)
    crops = np.stack([f[:, x:x + CW] for f, x in zip(fr, x0)])
    up = model(np.ascontiguousarray(crops))      # N x 960 x 544 x 3
    z = "1.0"
    if punch is not None:
        z = f"(1+if(gte(t\\,{punch:.3f})\\,0.16*exp(-(t-{punch:.3f})*2.2)\\,0))"
    vf = [f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame:flags=lanczos",
          f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2",
          "eq=contrast=1.07:saturation=1.22:brightness=0.01", "unsharp=5:5:0.5:5:5:0"]
    if punch is not None:
        vf.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.5:t=fill:enable='between(t,{punch:.3f},{punch + 0.1:.3f})'")
    if flash_red:
        vf.append("drawbox=x=0:y=0:w=iw:h=ih:color=red@0.35:t=fill:enable='lt(t,0.12)'")
    h, w = up.shape[1:3]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(FPS), "-i", "-", "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "medium",
                          "-crf", "16", "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    p.stdin.write(up.tobytes())
    p.stdin.close()
    p.wait()
    return len(fr) / FPS


def main():
    os.makedirs(WORK, exist_ok=True)
    model = Upscaler(WEIGHTS)
    vids, auds, caps, goals = [], [], [], []
    t = 0.0
    for bi, b in enumerate(BLOCKS):
        bstart = t
        for si, (s, e, sp, cx, cl) in enumerate(b["shots"]):
            path = f"{WORK}/b{bi}s{si}.mp4"
            punch = b["goal"][1] if b.get("goal") and b["goal"][0] == si else None
            red = bool(b.get("red")) and b["red"][0] == si
            if os.path.exists(path):
                d = round((e - s) / sp * FPS) / FPS
            else:
                d = render_shot(model, path, s, e, sp, cx, punch, red)
            print(f"  b{bi}s{si} {t:6.2f}-{t + d:6.2f} src {s}", flush=True)
            if punch is not None:
                goals.append(t + punch)
            for i, (ct, text) in enumerate(cl):
                end = cl[i + 1][0] if i + 1 < len(cl) else d
                caps.append((t + ct, t + end, text))
            vids.append(path)
            t += d
        blen = t - bstart
        a0 = b.get("audio_from", b["shots"][0][0])
        ap = f"{WORK}/a{bi}.wav"
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{a0:.3f}", "-t", f"{blen:.3f}", "-i", SRC, "-vn", "-ac", "2",
            "-ar", "48000", "-af", f"afade=t=in:d=0.06,afade=t=out:st={max(blen - 0.1, 0):.3f}:d=0.1", ap])
        auds.append(ap)
    total = t

    for name, lst in (("v", vids), ("a", auds)):
        with open(f"{WORK}/{name}.txt", "w") as f:
            f.writelines(f"file '{os.path.abspath(p)}'\n" for p in lst)
    sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/v.txt", "-c", "copy",
        f"{WORK}/video.mp4"])
    sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/a.txt", "-c", "copy",
        f"{WORK}/audio.wav"])

    # overlays
    for k in range(5):
        make_score(k).save(f"{WORK}/score{k}.png")
    for i, (_, _, text) in enumerate(caps):
        make_caption(text).save(f"{WORK}/cap{i}.png")
    inputs = ["-i", f"{WORK}/video.mp4", "-i", f"{WORK}/audio.wav"]
    loop = lambda p: ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", p]
    for k in range(5):
        inputs += loop(f"{WORK}/score{k}.png")
    for i in range(len(caps)):
        inputs += loop(f"{WORK}/cap{i}.png")
    fc, cur = [], "[0:v]"
    bounds = [0.0] + goals + [total + 1]
    for k in range(5):
        fc.append(f"{cur}[{2 + k}:v]overlay=0:0:enable='between(t,{bounds[k]:.3f},{bounds[k + 1]:.3f})'[s{k}]")
        cur = f"[s{k}]"
    for i, (a, b, _) in enumerate(caps):
        # quick "pop": caption scales from 115% to 100% over 0.12s
        fc.append(f"[{7 + i}:v]format=rgba,trim=start={a:.3f}:end={b:.3f},"
                  f"scale=w='iw*(1+0.15*max(0\\,1-(t-{a:.3f})/0.12))':h=-1:eval=frame,"
                  f"setpts=PTS[c{i}]")
        fc.append(f"{cur}[c{i}]overlay=x='(W-w)/2':y='1010-h/2':"
                  f"enable='between(t,{a:.3f},{b - 0.001:.3f})'[o{i}]")
        cur = f"[o{i}]"
    fc.append(f"{cur}fade=t=in:d=0.25,fade=t=out:st={total - 0.6:.3f}:d=0.6,format=yuv420p[v]")
    fc.append(f"[1:a]loudnorm=I=-13:TP=-1.0:LRA=9,afade=t=out:st={total - 0.7:.3f}:d=0.7[a]")
    sh(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "slow", "-b:v", "3800k", "-maxrate", "5500k",
        "-bufsize", "11000k", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT])
    print("total", round(total, 2))


if __name__ == "__main__":
    main()
