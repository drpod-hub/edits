"""Cut Denmark 2-4 Portugal footage into a 9:16 beat-synced Short, styled after the reference edit.

usage: python3 build.py SRC.mp4 REF.mp4 WORKDIR OUT.mp4 [OUT_ALT.mp4]

Cut points are copied from the reference edit's own scene changes (which sit on
its ~123 BPM beat grid): slow-mo close-ups during the quiet build, a white flash
+ zoom punch on the drop at 15.4s, then fast celebration/fan cuts.
"""
import os
import subprocess
import sys

SRC, REF, WORK, OUT = sys.argv[1:5]
OUT_ALT = sys.argv[5] if len(sys.argv) > 5 else None
SRC_W, SRC_H = 1280, 720
CW = round(SRC_H * 9 / 16 / 2) * 2  # 9:16 crop width at source res (406)
FPS = 60
DROP = 15.40
END = 30.80

# (timeline_end, src_start, crop_center_x, speed, fx)
# fx: push = slow zoom-in, build = strong zoom-in into the drop, drop = white flash + punch + shake,
#     punch = small zoom punch, flick = rapid flicker frame, fadein / fadeout
SHOTS = [
    (3.117, 116.0, .45, .50, "fadein push"),   # Portugal huddle (hook)
    (3.483, 15.3, .74, 1.0, "punch"),          # fans
    (5.267, 126.2, .57, .60, "push"),          # Cancelo
    (6.983, 132.5, .50, .60, "push"),          # Bernardo
    (7.967, 137.0, .52, .60, "push"),          # Ramos
    (8.700, 142.3, .40, .60, "push"),          # Leao
    (8.867, 152.5, .50, 1.0, "flick"),
    (9.033, 128.0, .60, 1.0, "flick"),
    (9.200, 134.0, .50, 1.0, "flick"),
    (9.367, 138.0, .55, 1.0, "flick"),
    (9.533, 147.5, .58, 1.0, "flick"),
    (13.80, 146.3, .55, .70, "push"),          # Vitinha pointing
    (DROP, 151.5, .50, .50, "build"),          # Felix stare into the drop
    (17.217, 8.6, .60, 1.0, "drop"),           # goal celebration
    (17.933, 11.6, .40, 1.0, "punch"),
    (21.683, 16.6, .74, 1.0, "push"),          # Portugal fans going wild
    (23.433, 23.0, .20, 1.0, "punch"),         # stadium scoreboard + fans
    (24.817, 122.0, .30, .80, "punch"),        # Felix hug
    (27.050, 12.6, .45, .90, "punch"),         # celebration pile
    (27.133, 137.5, .52, 1.0, "flick"),
    (27.217, 133.5, .50, 1.0, "flick"),
    (27.300, 127.0, .57, 1.0, "flick"),
    (27.383, 143.0, .40, 1.0, "flick"),
    (27.467, 153.0, .50, 1.0, "flick"),
    (29.217, 117.6, .45, 1.0, "punch"),        # huddle
    (END, 134.5, .50, .50, "push fadeout"),    # Bernardo, end card
]

GRADE = ("eq=contrast=1.12:saturation=1.28:brightness=-0.015:gamma=0.97,"
         "colorbalance=rs=-0.04:bs=0.05:rh=0.05:bh=-0.03,"
         "unsharp=5:5:0.9:5:5:0.0,vignette=angle=PI/4.5")


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def zoom_expr(fx, dur):
    if "drop" in fx:
        return f"(1.22-0.17*min(t/0.35\\,1)+0.03*t/{dur})"
    if "build" in fx:
        return f"(1.0+0.25*pow(t/{dur}\\,2))"
    if "punch" in fx:
        return f"(1.12-0.08*min(t/0.2\\,1))"
    if "push" in fx:
        return f"(1.0+0.07*t/{dur})"
    return "1.06"


def render_shot(i, start, end, src, cx, speed, fx):
    dur = end - start
    src_len = dur * speed + 0.2
    x = int(min(max(cx * SRC_W - CW / 2, 0), SRC_W - CW))
    z = zoom_expr(fx, dur)
    shake = "drop" in fx
    vf = [
        f"crop={CW}:{SRC_H}:{x}:0",
        f"minterpolate=fps={round(FPS / speed)}:mi_mode=mci:mc_mode=aobmc:vsbmc=1" if speed < 1 else f"fps={FPS}",
        f"setpts=(PTS-STARTPTS)/{speed}",
        f"fps={FPS}",
        f"scale=w='trunc(1080*{z}/2)*2':h='trunc(1920*{z}/2)*2':eval=frame:flags=lanczos",
        ("crop=1080:1920:(iw-1080)/2+14*sin(t*61)*max(0\\,1-t/0.5):(ih-1920)/2+14*cos(t*47)*max(0\\,1-t/0.5)"
         if shake else "crop=1080:1920:(iw-1080)/2:(ih-1920)/2"),
        GRADE,
        f"trim=duration={dur:.3f}",
    ]
    if "fadein" in fx:
        vf.append("fade=t=in:st=0:d=0.6")
    if "drop" in fx:
        vf.append("fade=t=in:st=0:d=0.3:color=white")
    if "flick" in fx:
        vf.append("eq=brightness=0.06:contrast=1.2")
    if "fadeout" in fx:
        vf.append(f"fade=t=out:st={dur - 0.5:.3f}:d=0.5")
    out = f"{WORK}/shot{i:02d}.mp4"
    run(["ffmpeg", "-y", "-ss", f"{src:.3f}", "-t", f"{src_len:.3f}", "-i", SRC, "-an",
         "-vf", ",".join(vf), "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "14",
         "-pix_fmt", "yuv420p", out])
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    run(["python3", os.path.join(os.path.dirname(__file__), "overlays.py"), WORK])
    files, t = [], 0.0
    for i, (end, src, cx, speed, fx) in enumerate(SHOTS):
        files.append(render_shot(i, t, end, src, cx, speed, fx))
        print(f"shot {i:02d} {t:6.3f}-{end:6.3f} src {src}")
        t = end
    with open(f"{WORK}/list.txt", "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in files)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/list.txt", "-c", "copy",
         f"{WORK}/video.mp4"])

    # Overlays: hook title during the build, final score from the drop, question at the end.
    overlay = (
        f"[0:v][1:v]overlay=enable='between(t,0.3,{DROP})'[a];"
        f"[a][2:v]overlay=enable='gte(t,{DROP})'[b];"
        f"[b][3:v]overlay=enable='gte(t,27.467)',format=yuv420p[v]"
    )
    common = ["-i", f"{WORK}/hook.png", "-i", f"{WORK}/score.png", "-i", f"{WORK}/end.png"]

    # Main: the reference edit's slowed soundtrack, which the cuts are timed to.
    run(["ffmpeg", "-y", "-i", f"{WORK}/video.mp4", *common, "-i", REF,
         "-filter_complex", overlay + f";[4:a]atrim=0:{END},afade=t=out:st={END - 0.8}:d=0.8[aout]",
         "-map", "[v]", "-map", "[aout]", "-t", str(END),
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT])

    if OUT_ALT:
        # Alt: the source video's own music, slowed + reverb, in case the reference song gets claimed.
        run(["ffmpeg", "-y", "-i", f"{WORK}/video.mp4", *common, "-ss", "8", "-i", SRC,
             "-filter_complex", overlay +
             f";[4:a]asetrate=44100*0.85,aresample=44100,aecho=0.8:0.7:60|120:0.35|0.2,"
             f"atrim=0:{END},afade=t=in:d=0.5,afade=t=out:st={END - 0.8}:d=0.8,loudnorm=I=-12[aout]",
             "-map", "[v]", "-map", "[aout]", "-t", str(END),
             "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT_ALT])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode()[-3000:])
        raise
