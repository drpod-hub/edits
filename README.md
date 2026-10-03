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

---

# Clash Royale TV Royale → YouTube Short

`clash_short/` turns the 16:9 TV Royale video into a ~32 s 1080×1920 Short: a hook on the Evo Electro Giant, then four numbered beats (Hero Electro Wizard, Season 3 C.H.A.O.S, Keep The Lights On, Evo Electro Giant), a comment CTA, and a loop back to the hook.

```bash
python3 clash_short/make_short.py --source path/to/tv_royale.mp4   # -> output/clash_royale_short.mp4
```

Edit `clash_short/edit.json` to change cuts (`src`, `dur`), framing (`mode` square/wide, `cx` crop centre, `zoom`), chapter headers and captions (`*word*` = yellow, `|` = line break).
