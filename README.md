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

---

# Music lore explainer (illustrated short)

`make_explainer.py` renders a ~36 s 1080×1920 illustrated "fact" short in the flat-illustration explainer style: one drawn scene the camera pushes around, a swirling sound-wave hero shot, karaoke captions with the spoken word boxed in red, a pop-in liner-notes card, a red dashed reveal trace, a moving watermark and a logo/handle outro.

First story: **Funky Drummer**, the James Brown break (Clyde Stubblefield) that hip-hop sampled over a thousand times.

```bash
pip install skia-python numpy kokoro-onnx soundfile   # ffmpeg must be on PATH
python3 make_explainer.py                             # -> output/funky_drummer_explainer.mp4
STILLS=1.5,12,25 python3 make_explainer.py            # just PNG stills in output/work/
```

- **Voiceover:** generated offline with Kokoro TTS. The model downloads to `models/kokoro/` on the first run. Change `voice` (`am_michael`, `am_adam`, `af_heart`, …) and `voice_speed` in `explainer_funky_drummer.json`, or set `voice_file` to your own recording.
- **Music/SFX:** an original funk drum loop, bass, whooshes and pops, all synthesised. The drummer's sticks hit in time with the loop, and the band drops out on "the band drops out".
- **Branding:** `handle`, `brand` and `brand_accent_index` (the red letter in the outro logo).
- **Script:** edit the `text` of each line. The scenes are keyed to the line `id`s, so keep those.

## Stickman version

```bash
python3 make_stickman.py      # -> output/funky_drummer_stickman.mp4 (~40 s render)
```

The same script, voice and beat, retold with ink stickmen on graph paper. The floor is the song's real waveform scrolling under a playhead. The band falls through trapdoors in it on "the band drops out". A giant mouse cursor drag-selects the drummer, then Ctrl+C / Ctrl+V pastes copies of him. The copies stack into a pyramid with rappers standing on top. The screen fills with 1,000 tiny drummers, he gets a $0.00 cheque, and in the end the cursor turns him into a dashed outline while his copies keep playing. A few frames flash inverted on big hits, like stick-fight animations.
