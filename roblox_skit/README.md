# Roblox-style skit: "POV: Playing Hide and Seek With Friends 💀"

A 32-second vertical (1080×1920) Roblox-style animated short, built and
rendered entirely from code with Blender's Python module. It uses the same
format as the popular Roblox animation Shorts: a black caption bar, blocky
characters, face decals and chat bubbles.

**Story:** Noob counts at the tree. Max hides behind a lamp post that is
thinner than his head ("he'll NEVER find me"), so he gets found instantly
("bro." / "HOW??"). Pip dives into a bush. Noob can't find Pip, so he and Max
leave for pizza. *3 hours later...* Pip is still in the bush: "guys...?"

## Render

```bash
pip install bpy pillow numpy        # bpy = Blender as a Python module (Python 3.13)
python3 build_scene.py --out frames/                    # Cycles, resumable
python3 compose.py frames/ ../output/hide_and_seek.mp4  # caption, card, audio, encode
```

Rendering at the default settings (`--width 720 --samples 24`) on 4 CPU cores
takes about 7–10 s per frame. To check the look first, render a few frames:
`--stills 60,165,500 --width 480 --samples 16`.

| File | What it does |
|---|---|
| `faces.py` | Face decals (smile, smirk, deadpan, shock, sad, …) and chat bubbles, drawn with Pillow |
| `build_scene.py` | Builds the characters, yard, house, tree, lamp post, bush and lighting, keyframes the whole story and its cameras, then renders with Cycles |
| `compose.py` | Adds the caption bar and the "3 hours later..." card, synthesizes the music and sound effects, and encodes the MP4 |

To change the skit, edit `story()` in `build_scene.py`. Each character has
helpers: `goto`/`turn`/`cycle` for movement, `pose` for limbs, `face` for
expressions and `say` for chat bubbles. All values are in frames at 30 fps.
