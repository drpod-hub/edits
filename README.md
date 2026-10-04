# Popular vs Best — Part 5

Generator for a 1080×1920 "Popular vs Best Songs" edit in the OWNeast format (title block, covers down the left, each song popping in with its rating while its clip plays behind it).

Albums: Life After Death · 4:44 · Donda · MBDTF · Utopia — 10 songs × 5.5 s = 55 s.

## Render

```bash
pip install pillow          # ffmpeg must be on PATH
python3 make_video.py       # -> output/popular_vs_best_part5.mp4
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

---

## Outro formato: Fofoca / Drama da Internet

`fofoca/` gera shorts de "drama da internet": narração, cortes rápidos com memes e legenda laranja palavra por palavra. Veja [fofoca/README.md](fofoca/README.md).
