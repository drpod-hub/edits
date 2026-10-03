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

# The Worst (Kanye Bars)

`make_worst.py` + `worst_config.json` render a 1080×1920 "THE WORST (…) I'VE EVER HEARD" lyric edit in the RealjN freestyle format: crumpled-paper intro (title over a photo → zoom-blur → one word at a time), then one segment per bar with ARTIST / (YEAR) / "SONG" up top and karaoke lyrics underneath (next line waits in grey, turns white when rapped), plus grey caps commentary lines.

Bars: Hold My Liquor ("When I park my Range Rover…") and Guilt Trip ("Star Wars fur…"), ~13.7 s.

```bash
pip install pillow numpy
python3 make_worst.py       # -> output/worst_kanye_bars.mp4
```

| Path | What | Fallback |
|---|---|---|
| `assets/audio/hold_my_liquor.mp3`, `assets/audio/guilt_trip.mp3` | song audio (lyric times are song timestamps) | silence |
| `assets/clips/hold_my_liquor.mp4`, `assets/clips/guilt_trip.mp4` | footage behind each bar, auto-cropped to 9:16 (`clip_start`, `clip_zoom`) | Yeezus-style disc pulsing to the beat |
| `assets/intro/kanye.png` | transparent cut-out shown under the intro title | Yeezus-style disc |
| `assets/intro/paper.jpg` | crumpled-paper texture | procedural paper |

Lyric timings were located with an offline Whisper transcription of the two songs; nudge `t`, `start` and `end` in `worst_config.json` if you swap audio sources.
