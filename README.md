# Popular vs Best — Part 5

Generator for a 1080×1920 "Popular vs Best Songs" edit in the OWNeast format (title block, covers down the left, each song popping in with its rating while its clip plays behind it).

Albums: Life After Death · 4:44 · Donda · MBDTF · Utopia — 10 songs × 5.5 s = 55 s.

## Render

```bash
pip install pillow          # ffmpeg must be on PATH
python3 make_video.py                     # part 5 (config.json)
python3 make_video.py config_part6.json   # part 6
```

## Add your media

Drop files at the paths listed in `config.json` (or edit the paths):

| Folder | What | Notes |
|---|---|---|
| `assets/covers/` | album art (`life_after_death.jpg`, `4_44.jpg`, `donda.jpg`, `mbdtf.jpg`, `utopia.jpg`) | any size, centre-cropped to square |
| `assets/clips/` | music-video clip per song (`hypnotize.mp4`, …) | auto-cropped to 9:16; set `clip_start` (seconds) |
| `assets/audio/` | song audio per song (`hypnotize.mp3`, …) | set `audio_start` to the part you want (hook/drop) |

Anything missing falls back to a placeholder (generated cover card, blurred-cover background, silence). If a song has a clip but no audio file, the clip's own audio is used.

## Customize

In `config.json`: song picks, ratings, name colours, title lines, handle, `segment_seconds`, `fps` (reference is 60).

Any number of albums works: with fewer than 5, the covers grow so the list still fills the same space.

## Artist review format

`make_review.py` renders the "ARTIST REVIEW" format (red title box, 8 rows +
artist rating, green song + yellow stream count per row):

```bash
python3 make_review.py review_kanye.json   # -> output/kanye_review.mp4
```

Each of the 8 `items` (BIGGEST, SMALLEST, BEST, WORST, UNDERRATED, OVERRATED,
BEST FEATURE, BEST ALBUM, in that order) takes `song`, optional `streams`,
and the same `clip`/`audio`/`cover` fields as above. `segment_seconds`
(default 7.5 -> 60 s total) and `rating_delay` (seconds into the last item
when the rating pops in) control timing.

## "What if" story format

`make_story.py` renders a narrated-style science short ("WHAT IF EARTH
SUDDENLY STOPPED SPINNING?"): title card, a procedurally drawn scene (city
park or a 3D globe), a HUD across the top with animated numbers, captions
with `*highlighted*` words, and an end card. No footage needed; sound is
synthesised.

```bash
python3 make_story.py story_earth_stops.json             # -> output/earth_stops.mp4
python3 make_story.py story_earth_stops.json --still 30  # one PNG at 30 s
python3 make_story.py story_earth_stops.json --draft     # fast encode
```

It also writes `output/earth_stops_script.txt`, the captions with timestamps,
so you can record a voiceover to it. Save the recording as
`assets/audio/earth_stops_vo.mp3` (the `voiceover` path) and re-render: it is
mixed on top and the sound bed is ducked. `music` adds a track the same way.

Each beat in `beats` takes `scene` (`city`, `globe`, `end`), `dur`, `caption`,
`hud` (`tag`, `label`, `value`, `unit`, `sub`), `right` (`label`, `value`,
`unit`), and `fx`. A `value` can count: `{"from": 0, "to": 1270, "dur": 2}`.
`fx` values are constants or `[start, end]` ramps across the beat:

- city: `shake`, `wind`, `debris`, `dust`, `scorch`, `lean`, `flash`, `launch` (+`launch_at`)
- city: `thoughts` (0–1 density of thought bubbles), `mood` (`busy` / `kind`), `warm` (golden-hour tint)
- globe: `yaw`, `tilt`, `radius`, `cy`, `drain` (oceans to the poles), `sun_az`, `sun_el`, `dim`
- neurons: `zoom`, `activity` (signal pulses), `heat` (calm blue → overload red), `flicker`, `yaw`, `cy`
- end: `bg` picks the scene behind the end card (`globe` or `neurons`) plus that scene's fx
- any scene: `flash`, `shake`

- city giant: `giant` (height px), `gx`, `gfeet`, `gwalk` (0–1 stride), `gfall` (0–1 topple); `stomp` shakes on each footfall

Stories: `story_earth_stops.json` (Earth stops spinning), `story_mind_reading.json` (mind reading), `story_80ft.json` (80 feet tall).
