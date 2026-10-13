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

---

# Chop: "Say It" - The Masqueraders

No drums: the groove comes from where the chops land.

**Source:** ~74 BPM, G major, phase-decorrelated stereo (kept stereo, since a mono sum would comb-filter).
**Flip:** varispeed +2 semitones → **84 BPM, A major**, every chop quantized to the grid.

The chops are re-sequenced into a chromatic walk-down the record never plays:

| | Bar 1 | Bar 2 | Bar 3 | Bar 4 |
|---|---|---|---|---|
| Source key | Cmaj7 | Bm7 · Bbmaj7 | Am7 | D |
| After the flip | **Dmaj7** | **C#m7 · Cmaj7** | **Bm7** | **E** |

Each bar is cut in 3-3-4-3-3 / 3-3-2 sixteenths with MPC-style choke (every hit cuts the last one).
The band lets each chord ring into the next downbeat, so the Cmaj7 and Am7 chops start one beat in, where the chord has settled.
The record has no clean Bbmaj7, so that chord is the Cmaj7 chop played two semitones down.

## Files (`output/say_it/`)
- `say_it_chop_84bpm_A.mp3`: the full chop (1:11)
- `say_it_main_loop_4bar.wav`, `say_it_variation_loop_4bar.wav`: seamless 4-bar loops
- `pads/`: the 6 source chops, named `<flipped chord>_<source chord>`
- `say_chop.py`: re-renders it: `python3 say_chop.py <song.mp3> <out_dir>`

| Time | Section |
|---|---|
| 0:00 | Intro: held chords, filter opens |
| 0:11 | Main chop, 8 bars |
| 0:34 | Variation, 8 bars: reverse swell into bar 4, vocal line over the E |
| 0:57 | Main chop, 4 bars |
| 1:08 | Last Dmaj7 rings out |

---

# Flip: "Like Honey" - Argent

A two-part beat with a **tape spin-up beat switch**. The drums are Argent's own drummer, cut from the record and re-sequenced.

**Part 1, slowed:** the drumless intro varispeeded *down* 3 semitones (103 → 87 BPM), with tape wobble.
The record's Bb → E tritone jump is squeezed into one bar:

| | Bar 1 | Bar 2 | Bar 3 | Bar 4 |
|---|---|---|---|---|
| Source | Am7 | Gmaj7 | D | Bbmaj7 · E |
| Slowed | **F#m7** | **Emaj7** | **B** | **Gmaj7 · C#** |

The drummer's kick, snare and hat are pitched down with it, swung, and the hats sit lazily behind the beat.

**The switch:** the loop speeds up until it's back at the record's own pitch, then lands on the band's full ensemble hit from 2:23.

**Part 2, full flight:** the band's riff (Dsus-A | Asus-E | Dsus-A | Asus-B7) at original pitch, 112 BPM, in A, the relative major of Part 1's F#m.
It runs riff + drums, a drums-only break with riff stabs on each downbeat, the riff again, then a tape stop.

One-shots were found by separating the percussive layer and scoring every hit. The record's kick is thin under the bass guitar, so it has a short sub layered underneath.

## Files (`output/like_honey/`)
- `like_honey_flip.mp3`: the full flip (1:29)
- `kit/`: both loops, the impact hit, and the drummer's kick/snare/hat (original and slowed)
- `honey_flip.py`: re-renders it: `python3 honey_flip.py <song.mp3> <out_dir>`

| Time | Section |
|---|---|
| 0:00 | Part 1: intro, filter opens, no drums |
| 0:11 | Loop + the drummer, pitched down (8 bars) |
| 0:33 | 4 more bars, drums drop, spin-up |
| 0:44 | Part 2: the 2:23 hit, riff + drums (8 bars) |
| 1:01 | Drum break, riff stabs |
| 1:09 | Riff + drums (8 bars) |
| 1:27 | Tape stop |

---

# Loop & chop: "You're Too Precious" - James Blake

No drums, and **nothing pitched or stretched**: the record sits on an exact 100 BPM grid (bar = 2.400 s) with a triplet / 6-8 pulse inside it, so every piece is cut on the record's own beats and Blake's voice and swing stay untouched. Key: Db major / Bb minor.

**Main loop (4 bars):** the verse cycle from 0:24, with Blake's D-against-Db/Eb clusters resolving to Dbmaj7. It was picked by scoring every 2- and 4-bar loop for how seamless its restart is. The record repeats this cycle exactly, so the loop point is near-identical to what originally follows it.

**The chop:** chord chops from across the song, cut 3-3-2 and re-sequenced, ending on Blake's chromatic D → Db slide:

| Bar 1 | Bar 2 | Bar 3 | Bar 4 |
|---|---|---|---|
| Gb · Ebm7 | Dbmaj7 | Fm/Db · Bbm7 | Dmaj7 · Db |

**Vocal-chop melody:** one sung Eb5 vowel (0:12.2) pitch-shifted with formants preserved into Bb4, C5, Db5, Eb5, F5 and Gb5, playing a new melody over the chop. On the D chord it sings F#, the common tone.

## Files (`output/youre_too_precious/`)
- `precious_loop_and_chop.mp3`: the full piece (1:17)
- `precious_main_loop_4bar.wav`, `precious_chop_4bar.wav`: seamless loops
- `kit/`: 7 chord chops, the main loop, the intro motif, and 6 vocal-chop notes
- `precious_chop.py`: re-renders it: `python3 precious_chop.py <song.mp3> <out_dir>`

| Time | Section |
|---|---|
| 0:00 | Intro motif (the record's opening figure), filter opens |
| 0:10 | Main loop, 8 bars |
| 0:29 | The chop |
| 0:38 | The chop + vocal-chop melody |
| 0:48 | Main loop |
| 0:58 | The chop + vocal-chop melody |
| 1:07 | Intro motif, filter closes |
