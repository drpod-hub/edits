# Chipmunk-soul flip: "You Ain't Livin' Unless You're Lovin'"

A College Dropout-style chop of The Smith Connection's soul record.

**Source:** 75.5 BPM, C major (I–vi–IV–ii–V changes), half-step key change to Db at ~2:26.
**Flip:** varispeed +3 semitones (tape-style, pitch and tempo move together) → **90 BPM, Eb major**.
The final hook keeps the record's own key change, so it lifts to **E**.
Every beat of every chop is quantized to the 90 BPM grid, so the pads lock to any drum machine.

## Files
- `output/beat_full_90bpm_Eb.mp3`: the full beat (2:51)
- `output/kit/`: 16 MPC-style pads (24-bit WAV, 90 BPM)
- `output/arrangement.txt`: the section timeline
- `chop.py`: re-renders everything: `python3 chop.py <song.mp3> <out_dir>`

| Pad | What it is | Source |
|---|---|---|
| 01 | Intro, 4 bars | 0:00 |
| 02 | **Main loop**, instrumental break, 4 bars (Bb7 Eb \| Eb Cm \| Cm Ab \| Ab Fm) | 1:35 |
| 03 | Hook loop with the vocal phrase, same changes | 1:22 |
| 04 | Key-change vocal vamp (E major), 4 bars | 2:55 |
| 05–12 | Main loop sliced per chord (half bar each) | |
| 13–15 | One-beat vocal stabs | 1:24, 1:25, 2:00 |
| 16 | Two-beat vocal phrase | 1:24 |

## Arrangement
| Time | Section | |
|---|---|---|
| 0:00 | Intro | Filter opens over 4 bars, vocal stab teaser |
| 0:10 | Hook | Vocal loop, boom-bap drums, sub bass on the roots |
| 0:32 | Verse 1 | Instrumental break loop, vocal stabs, "you-you-you" stutter into the hook |
| 1:14 | Hook | |
| 1:36 | Verse 2 | MPC re-chop: each chord cut into 8ths and re-sequenced |
| 2:18 | Hook 3 | Rides the record's half-step key change |
| 2:40 | Outro | Drums out, filter closes, tape stop |

Drums are synthesized (kick, snare with clap layer, swung hats) and crunched to 26 kHz/12-bit for an SP-1200 feel.
The sample is low-shelved under 120 Hz to leave room for the kick and sub.

Clear the sample before you release anything commercially.
