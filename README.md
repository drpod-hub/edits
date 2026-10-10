# Popular vs Best — Part 5

Generator for a 1080×1920 "Popular vs Best Songs" edit in the OWNeast format (title block, covers down the left, each song popping in with its rating while its clip plays behind it).

Albums: Life After Death · All Eyez On Me · Donda · MBDTF · Utopia — 10 songs × 5.5 s = 55 s.

## Render

```bash
pip install pillow          # ffmpeg must be on PATH
python3 make_video.py       # -> output/popular_vs_best_part5.mp4
```

## Add your media

Drop files at the paths listed in `config.json` (or edit the paths):

| Folder | What | Notes |
|---|---|---|
| `assets/covers/` | album art (`life_after_death.jpg`, `all_eyez_on_me.jpg`, `donda.jpg`, `mbdtf.jpg`, `utopia.jpg`) | any size, centre-cropped to square |
| `assets/clips/` | music-video clip per song (`hypnotize.mp4`, …) | auto-cropped to 9:16; set `clip_start` (seconds) |
| `assets/audio/` | song audio per song (`hypnotize.mp3`, …) | set `audio_start` to the part you want (hook/drop) |

Anything missing falls back to a placeholder (generated cover card, blurred-cover background, silence). If a song has a clip but no audio file, the clip's own audio is used.

## Customize

In `config.json`: song picks, ratings, name colours, title lines, handle, `segment_seconds`, `fps` (reference is 60).

## Shorts: horizontal clip → vertical Short

`make_short.py` turns a 16:9 clip into a 1080×1920 YouTube Short: cold-open hook, dead-air trimming, blurred background, header + animated captions (with colour emoji), zoom punches on cuts, a bass hit on the reveal and a closing call-to-action. Audio is normalised for Shorts.

```bash
python3 make_short.py shorts/tsukasa_celular.json   # -> output/tsukasa_celular_short.mp4
```

Two configs ship: `shorts/tsukasa_celular.json` (one scene, dead-air trimmed) and `shorts/animes_incriveis.json` (top-7 montage from hand-picked `segments`, cuts snapped to quiet audio with `snap_cuts`).

Put the source clip at the config's `source` path (videos are git-ignored). Caption/punch times in the config are in **source** seconds.
