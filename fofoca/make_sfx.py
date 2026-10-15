#!/usr/bin/env python3
"""Synthesize a small royalty-free SFX kit with ffmpeg (no downloads).

Usage:  python3 fofoca/make_sfx.py [out_dir]     (default: assets/fofoca/sfx)

  whoosh.wav   cut to a full-screen shot
  pop.wav      card popping in
  boom.wav     "vine boom"-style low hit for punchlines
  impact.wav   hard hit + noise burst for shocking lines
  riser.wav    1.5 s build-up; place it so it ends on a reveal (offset -1.5)
  ding.wav     bright bell for a reveal / fact card
  glitch.wav   short digital stutter
  bed.wav      30 s loopable suspense bed (drone + heartbeat + tick)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), "assets", "fofoca", "sfx")

SR = 44100
SOUNDS = {
    "whoosh": ["-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.9:r=44100",
               "-af", "highpass=f=400,lowpass=f=5000,"
                      "volume='if(lt(t,0.3),pow(t/0.3,2),pow(max(0,(0.5-t)/0.2),1.5))':eval=frame,"
                      "aecho=0.6:0.4:30:0.25,volume=20dB,alimiter=limit=0.8"],
    "pop": ["-f", "lavfi", "-i", "aevalsrc='0.9*sin(2*PI*(380+5200*t)*t)*exp(-t*45)':d=0.12:s=44100"],
    "boom": ["-f", "lavfi", "-i",
             "aevalsrc='0.95*sin(2*PI*(38+70*exp(-t*3))*t)*exp(-t*2.2)"
             "+0.25*sin(2*PI*(76+140*exp(-t*3))*t)*exp(-t*3)':d=1.6:s=44100",
             "-af", "lowpass=f=900,alimiter=limit=0.95"],
    "impact": ["-f", "lavfi", "-i",
               "aevalsrc='0.9*sin(2*PI*(45+160*exp(-t*8))*t)*exp(-t*4)"
               "+0.6*(random(0)*2-1)*exp(-t*22)':d=1.0:s=44100",
               "-af", "lowpass=f=3000,alimiter=limit=0.95"],
    "riser": ["-f", "lavfi", "-i",
              "aevalsrc='(0.35*sin(2*PI*(180*t+260*t*t)*t)+0.25*(random(0)*2-1))*pow(t/1.5,2)':d=1.5:s=44100",
              "-af", "highpass=f=150,afade=t=out:st=1.45:d=0.05"],
    "ding": ["-f", "lavfi", "-i",
             "aevalsrc='0.5*sin(2*PI*1318*t)*exp(-t*5)+0.25*sin(2*PI*2637*t)*exp(-t*7)"
             "+0.15*sin(2*PI*1975*t)*exp(-t*6)':d=1.2:s=44100"],
    "glitch": ["-f", "lavfi", "-i",
               "aevalsrc='0.6*sin(2*PI*(220+880*floor(mod(t*40,4)))*t)*lt(mod(t,0.05),0.03)':d=0.25:s=44100"],
    # 30 s: 55/82.4 Hz drone breathing every 4 s, heartbeat each second, soft tick on the off-beat
    "bed": ["-f", "lavfi", "-i",
            "aevalsrc='(0.22*sin(2*PI*55*t)+0.14*sin(2*PI*82.4*t)+0.06*sin(2*PI*110*t))"
            "*(0.65+0.35*sin(2*PI*t/4))"
            "+0.55*sin(2*PI*52*t)*exp(-mod(t,1)*14)"
            "+0.35*sin(2*PI*48*t)*exp(-mod(t-0.22,1)*16)*gte(mod(t,1),0.22)"
            "+0.05*sin(2*PI*2400*t)*exp(-mod(t+0.5,1)*120)':d=30:s=44100",
            "-af", "lowpass=f=2600,afade=t=in:d=0.02,afade=t=out:st=29.98:d=0.02"],
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, args in SOUNDS.items():
        path = os.path.join(OUT, f"{name}.wav")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args, "-ar", str(SR), "-ac", "2", path],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"{name} failed:\n{r.stderr[-1500:]}")
        print("  ", path)


if __name__ == "__main__":
    main()
