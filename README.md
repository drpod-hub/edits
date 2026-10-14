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

---

# Stem-separated flip: "Dope Man" - N.W.A.

The record is a drum machine at exactly **88.235 BPM** (bar = 2.720 s). The beat tracker reads it as 117, a dotted-8th artifact; the snare backbeat folded over the whole song gives the real grid. Because the beat repeats bar for bar, **REPET-style separation** works here: the median of many bars rebuilds the beat alone, and what changes between bars is the foreground. So instead of chopping the full mix, this pulls out real stems:

- **Lead:** the synth hook (0:17–0:44), then a harmonic/percussive split to strip drum bleed
- **Vocals:** the chorus shouts. The three choruses are different takes, so each shout uses its cleanest take.
- **Beat:** the instrumental outro (5:37–6:15), the plain drum machine

The whole flip is varispeeded down to **exactly 79 BPM** (−1.9 semitones), so it's heavier and darker.

| Time | Section |
|---|---|
| 0:00 | The lead alone, tape delay, filter opening |
| 0:12 | The original hook, slowed, with shouts answering the lead |
| 0:36 | Chorus flip: outro drums + re-sequenced shouts + lead stabs on the &s |
| 1:01 | Breakdown: kick only, reversed lead swell, delayed shout |
| 1:13 | Hook again, shouts in call and response |
| 1:37 | The lead alone into a tape stop |

## Files (`output/dope_man/`)
- `dope_man_flip.mp3`: the full flip (1:49)
- `kit/` (all 79 BPM): the separated lead (8 bars), the full hook (8 bars), the outro drums (4 bars), and four vocal shouts
- `dope_flip.py`: re-renders it: `python3 dope_flip.py <song.mp3> <out_dir>`

---

# Cinematic half-time flip: "CIRCUS MAXIMUS" - Travis Scott ft. The Weeknd & Swae Lee

The record is on an exact **125 BPM** grid (bar = 1.9199 s). Three of its sections run the same 8-bar cycle on **Eb minor → Cb → Ab minor** roots (Eb ×4 | B ×2 | Ab ×2), so they can be switched and stacked freely.

**Sample layers (drumless):** a harmonic/percussive split removes the rage drums (transient score 3.8 → 1.6). Each layer is high-passed so the new 808 owns the low end, and corrected for mono:
- **Pad:** the beat switch (2:34), used for the intro
- **Strings:** the outro's rising string glides (3:47), the main loop
- **Synths:** the rage section (2:03), layered under drop 2
- **Melodic:** the sustained layer from 3:05, used for the switch-up

**Mono safety:** the record's pads are side-heavy stereo synths, so on their own they'd cancel in mono. The drum-removal mask is shared by both channels (magnitude-based, clamped). A per-frequency mid/side correction then holds side 3 dB under mid. Every section stays positively correlated.

**New production:**
- **808s:** tuned to the record's own measured 808 pitches (Eb1 39.6 Hz, B1 62.8 Hz, Ab1 52.15 Hz), with late slides into each chord change and octave flicks in drop 2
- **Drums:** a punch kick, a layered clap on 3 (half time), and trap hats with 1/32 rolls and triplet runs
- **Sidechain:** the sample layers pump against the 808s
- **Risers:** a noise riser plus the record's own string glide reversed into each drop
- **Breakdown:** an MPC stutter of the strings
- **Master:** a look-ahead peak limiter

| Time | Section |
|---|---|
| 0:00 | Intro: beat-switch pad, filter opens, riser |
| 0:15 | Drop 1: strings + drums + tuned 808 (16 bars) |
| 0:46 | Switch: melodic layer, triplet hats, sparse 808 |
| 1:01 | Breakdown: MPC stutter, riser |
| 1:09 | Drop 2: strings + synths, busier drums, 808 flicks (16 bars) |
| 1:40 | Outro: strings, filter closes, tape stop |

## Files (`output/circus_maximus/`)
- `circus_maximus_flip.mp3`: the full flip (1:48)
- `kit/`: the four drumless 8-bar layers, an 8-bar drum loop, the 8-bar tuned 808 line, and single 808 notes (Eb, B, Ab)
- `circus_flip.py`: re-renders it: `python3 circus_flip.py <song.mp3> <out_dir>`

---

# Trap beat: "Way Too Long" - Delicate Steve

The record sits on an exact **120 BPM** grid (bar = 2.000 s), tuned −4 cents. It's varispeeded ×1.125 (+2.04 semitones) to **exactly 135 BPM**. That lift also cancels the −4 cents, so the result is in tune with A440: F major / D minor becomes **G major / E minor**. One bar is exactly 78,400 samples, so every chop stays sample-locked to the grid.

The record has no separate drum kit. Its rhythm comes from gated strum attacks on syncopated 16ths, so the sample stays raw (that stutter is the charm). It's only high-passed so the 808 owns the sub, and mid/side-corrected for mono.

- **Hook:** a 4-bar bridge loop (1:18), **C G | G D | D7 | C Am** after the lift
- **Verse:** the gated riff (0:20), an 8-bar loop whose restart matches the original (chroma similarity 1.00)
- **Intro and outro:** the record's sparse slide-guitar melody (2:12)
- **808s:** follow the record's own bassline, checked half-bar by half-bar against the sample's chords, with late slides into chord changes and octave flicks
- **Drums:**
  - **Kick and clap:** a punch kick and a clap on 3
  - **Hats:** 1/16 bursts, 1/16-triplet rolls, and 1/32 rolls that rise in pitch at phrase ends
- **Mix:** sidechain pump, noise risers, an MPC stutter break, a tape stop, and a look-ahead limiter

| Time | Section |
|---|---|
| 0:00 | Intro: slide-guitar melody, filter opens, riser |
| 0:14 | Hook: bridge loop + trap drums + 808 |
| 0:28 | Verse: gated riff, lighter drums (16 bars) |
| 0:57 | Hook |
| 1:11 | Break: MPC stutter of the riff, riser |
| 1:18 | Final hook: busiest drums, pitch-rising rolls |
| 1:32 | Outro: melody, filter closes, tape stop |

## Files (`output/way_too_long/`)
- `way_too_long_trap.mp3`: the full beat (1:40)
- `kit/` (all 135 BPM): hook loop (4 bars), riff loop (8 bars), melody (8 bars), drums (8 bars), 808 line (8 bars)
- `waytoolong_trap.py`: re-renders it: `python3 waytoolong_trap.py <song.mp3> <out_dir>`

---

# "CIRCUS MAXIMUS" redo: the record's own drums, a crafted sample

Same 125 BPM grid and Eb ×4 | B ×2 | Ab ×2 cycle as the first flip. This time **the drums and 808 are the record's own**, and the sample is built like a producer's chop rather than raw layers.

**Drums:** Travis raps over every bar of the rage beat, so a plain harmonic/percussive split would drag his consonants along. Instead the percussive layer is masked to what *repeats*. The median of all 72 rage bars (per bar parity, so 2-bar patterns survive) models the drum pattern, and each real bar keeps only what that model explains. In the vocal range, the stem's sustained-to-percussive ratio drops from 0.81 to 0.30. Bars 64–79 are used, which is two full chord cycles, so fills and variation are the record's own. The pattern is kick and clap on every quarter, with hats on top.

**808:** the low band (< 100 Hz) of the same bars. It's the record's distorted 808, already walking Eb → B → Ab with syncopated attacks on 0-3-7-11-15.

**Sample (8 bars, every bar checked against the record's 808):**
- **Body:** the outro strings (3:47, with their rising glide) plus the melodic layer (3:05), drumless and mono-corrected
- **Chop hook:** the melodic layer gated 3-3-2 on eighths, with an octave-up copy underneath for shimmer
- **Reverse swells:** the next chord reversed into every chord change
- **Glue:** ducked by the record's own quarter-note kick, plus light tape saturation

| Time | Section |
|---|---|
| 0:00 | Intro: sample, filter opens, the record's hats tease in |
| 0:15 | Hook: record drums + 808, sample + chop hook (16 bars) |
| 0:46 | Verse: drums + 808, darker sample (room for vocals) |
| 1:17 | Break: chop stutter, riser |
| 1:24 | Hook (16 bars) |
| 1:55 | Outro: sample, tape stop |

## Files (`output/circus_maximus_redo/`)
- `circus_maximus_redo.mp3`: the full beat (2:03)
- `kit/`: the record's drums (16 bars), the record's 808 (16 bars), sample (8 bars), chop hook (8 bars), sample + hook (8 bars)
- `circus_redo.py`: re-renders it: `python3 circus_redo.py <song.mp3> <out_dir>`
