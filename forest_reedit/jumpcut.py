#!/usr/bin/env python3
"""Corta as pausas (jump cut), clareia as partes escuras e reescala um vídeo.

Uso: python3 jumpcut.py entrada.mp4 saida.mp4 [--db -32] [--min 0.35] [--pad 0.10]
"""
import argparse, re, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst")
ap.add_argument("--db", type=float, default=-32, help="abaixo disso conta como silêncio")
ap.add_argument("--min", type=float, default=0.35, help="pausa mínima (s) para cortar")
ap.add_argument("--pad", type=float, default=0.10, help="respiro (s) mantido em cada lado do corte")
ap.add_argument("--height", type=int, default=720)
a = ap.parse_args()

dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                     "-of", "csv=p=0", a.src]))
log = subprocess.run(["ffmpeg", "-i", a.src, "-vn", "-af", f"silencedetect=n={a.db}dB:d={a.min}",
                      "-f", "null", "-"], capture_output=True, text=True).stderr
starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]

keep, t = [], 0.0
for s, e in zip(starts, ends):
    if s + a.pad > t:
        keep.append((t, s + a.pad))
    t = max(t, e - a.pad)
if t < dur:
    keep.append((t, dur))
cut = dur - sum(e - s for s, e in keep)
print(f"{len(keep)} trechos, {cut:.1f}s de pausa removidos ({dur:.0f}s -> {dur - cut:.0f}s)")

expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in keep)
vf = (f"select='{expr}',setpts=N/FRAME_RATE/TB,"
      # levanta sombras (gameplay escuro) sem estourar as partes claras
      "curves=master='0/0 0.15/0.22 0.5/0.56 1/1',eq=saturation=1.12,"
      f"scale=-2:{a.height}:flags=lanczos,unsharp=5:5:0.6,fps=30")
af = f"aselect='{expr}',asetpts=N/SR/TB,loudnorm=I=-14:TP=-1.5:LRA=11"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-stats", "-i", a.src, "-vf", vf, "-af", af,
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", a.dst], check=True)
