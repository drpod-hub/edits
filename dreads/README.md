# "Did you know you can grow dreads naturally?" — clay stop-motion short

Procedural 3D claymation (1080×1920, 30 s, 24 fps shot on twos) built and rendered with Blender's Python module (Cycles).

| Time | Scene |
|---|---|
| 0–4 s | "DID YOU KNOW?" clay letters drop in over the character |
| 4–8.5 s | "You can grow dreads naturally!" — hair sprouts into locs |
| 8.5–20.5 s | Macro zoom: coily strands, shed hairs falling in and getting trapped, all twisting into one loc |
| 21–26 s | "Give it time…" — calendar flips month 1 → 6 → 12 as the locs grow |
| 26–30 s | "Freeform locs, a.k.a. natural dreads" end card, wave + wink |

Audio is a synthesized marimba loop with pop/whoosh/thock SFX, kept quiet so a voice-over can go on top.

## Render

```bash
python3.13 -m venv venv && ./venv/bin/pip install bpy numpy   # bpy wheel must match the Python version
./venv/bin/python dreads/make_animation.py              # ~2 h on 4 CPU cores -> output/dreads/dreads_naturally.mp4
./venv/bin/python dreads/make_animation.py --preview    # half res, quick look
./venv/bin/python dreads/make_animation.py --times 2.5,14,28   # review stills
```

Frames already rendered are skipped, so a stopped render resumes. `--samples` (default 10, denoised) and `--scale` (render %, default 67, upscaled on encode) trade speed for quality; `--encode-only` re-muxes after editing captions' audio.

Captions, timings, colours and the month steps are constants at the top / in `build()` and `char_state()` of `make_animation.py`.
