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

## Sample breakdown format

`make_sample.py` renders the landscape "sample breakdown" format: the sampled
record's waveform on black, a playhead that plays each chop and paints it in
its colour, then the beat replaying those chops (the one sounding lights up),
then the song credit.

```bash
pip install pillow numpy
python3 make_sample.py sample_devil.json   # -> output/sample_devil_in_a_new_dress.mp4
```

In the config:

| Key | What |
|---|---|
| `sample` | `title`, `artist`, `year`, `audio`, `pitch` (semitones; speeds the record up/down like a sampler and shows `PITCH: + 1`; add `"keep_tempo": true` to shift pitch only), `window` (`[start, end]` seconds of the track drawn as the waveform; default whole track) |
| `chops` | `start`/`end` in seconds of the original track, `color`, optional `lead_in` (seconds played before the chop) |
| `song` | `title`, `artist`, `produced_by`, `audio`, `audio_start` (where the beat comes in) |
| `sequence` | the beat: which `chop` is heard and for how long (`dur`, seconds), in order; optional `offset` into the chop |

If `song.audio` is missing the beat is rebuilt by replaying the chops; if the
sample audio is missing too you get a placeholder waveform and silence.
The chop times in `sample_devil.json` are estimates read off the reference
video; nudge them once the real track is in. Other knobs: `width`/`height`,
`fps`, `handle`, `beat_zoom`, `outro_seconds`, `pitch_label_seconds`.
