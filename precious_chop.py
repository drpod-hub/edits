"""
Loop and chop of "You're Too Precious" - James Blake. No drums.

The record sits on an exact 100 BPM grid (bar = 2.400 s) with a 6/8-ish
triplet pulse inside it, so nothing is pitched or stretched: Blake's voice and
the swing stay untouched. Pieces are re-cut on the record's own beats.

  Intro motif   the exposed 2-bar figure the record opens with (0:00-0:05)
  Main loop     the 4-bar verse cycle (0:24): D-against-Db/Eb clusters
                resolving to Dbmaj7. Picked because the record repeats it
                exactly, so the loop point is seamless
  The chop      | Gb . Ebm7 | Dbmaj7 | Fm/Db . Bbm7 | Dmaj7 . Db |
                chord chops from across the song, cut 3-3-2, ending on Blake's
                chromatic D -> Db slide
  Vocal chops   one sung Eb5 vowel (0:12.2) pitch-shifted with formants kept,
                playing a new melody over the chop

Usage: python3 precious_chop.py <source audio> <out dir>
"""
import os
import subprocess
import sys
import tempfile

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

from chop import SR, Chopper, biquad, fades, fit, sweep_lp
from honey_flip import track_quarters

BPM = 100.0
BEAT = 60 / BPM
STEP = BEAT / 4
BAR_N = int(round(16 * STEP * SR))
rng = np.random.default_rng(5)

# Chord chops: (first tracked beat, beats). Beat 0 is the beat at 0:14.3.
CHORDS = {
    "Gb":     (96, 2),    # 1:12.1
    "Ebm7":   (98, 2),    # 1:13.3
    "Dbmaj7": (100, 4),   # 1:14.4, cleanest chord in the song
    "Fm7":    (94, 2),    # 1:10.9, F-Ab-C over a ringing Db bass (Fm/Db), E natural on top
    "Bbm7":   (196, 2),   # 2:12.1
    "Dmaj7":  (144, 2),   # 1:40.9, Blake's chromatic chord
    "Db":     (102, 2),   # 1:15.6
}
MAIN_LOOP = (16, 16)      # bars 4-7: the restart matches what follows (seamless)
MOTIF_AT = 0.09           # intro figure: repeats every 2 bars (4.81 s)
VOX_AT, VOX_LEN = 12.24, 0.34  # a sung Eb5

# (step, chord, offset 16ths, length 16ths)
CHOP = [
    [(0, "Gb", 0, 3), (3, "Gb", 0, 3), (6, "Gb", 4, 2), (8, "Ebm7", 0, 3), (11, "Ebm7", 0, 3), (14, "Ebm7", 4, 2)],
    [(0, "Dbmaj7", 0, 6), (6, "Dbmaj7", 0, 2), (8, "Dbmaj7", 8, 3), (11, "Dbmaj7", 8, 5)],
    [(0, "Fm7", 0, 3), (3, "Fm7", 0, 3), (6, "Fm7", 4, 2), (8, "Bbm7", 0, 3), (11, "Bbm7", 0, 3), (14, "Bbm7", 4, 2)],
    [(0, "Dmaj7", 0, 6), (6, "Dmaj7", 0, 2), (8, "Db", 0, 8)],
]
# Vocal-chop melody: (step, semitones from Eb5, length 16ths), one list per bar
MELODY = [
    [(0, -2, 2), (3, 0, 2), (8, 3, 2), (11, 2, 2), (14, 0, 2)],       # Db Eb | Gb F Eb
    [(0, 2, 4), (6, 0, 2), (8, -2, 6)],                              # F Eb Db
    [(0, 2, 2), (3, -3, 2), (8, -2, 2), (11, -5, 4)],                # F C | Db Bb
    [(0, 3, 6), (8, 2, 2), (11, 0, 2), (14, -2, 2)],                 # F#(over D) | F Eb Db
]


def rb_pitch(x, semitones):
    if semitones == 0:
        return x
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        sf.write(a, x.T, SR, subtype="FLOAT")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a, "-af",
                        f"rubberband=pitch={2 ** (semitones / 12):.6f}:formant=preserved", b],
                       check=True)
        out, _ = sf.read(b, always_2d=True)
    return fit(out.T, x.shape[1])


def render_bar(pattern, pads):
    out = np.zeros((2, BAR_N))
    for step, name, off, length in pattern:
        a = int(round(off * STEP * SR))
        x = fades(pads[name][:, a:a + int(round(length * STEP * SR))], 0.002, 0.012)
        i = int(round(step * STEP * SR))
        out[:, i:i + x.shape[1]] += x[:, :BAR_N - i]
    return out


def render_melody(notes, vox):
    out = np.zeros((2, BAR_N))
    for step, st, length in notes:
        n = int(round(length * STEP * SR))
        x = fades(fit(vox[st], n), 0.004, 0.04)
        i = int(round(step * STEP * SR))
        out[:, i:i + n] += x[:, :BAR_N - i]
    return out


def room(x, wet=0.12, sec=1.4):
    t = np.arange(int(sec * SR)) / SR
    ir = biquad(rng.standard_normal((2, len(t))) * np.exp(-t * 3.2), "lp", 7000)
    tail = np.stack([fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)])
    return x + wet * tail / np.max(np.abs(tail)) * np.max(np.abs(x))


def finish(x):
    x = biquad(x, "hp", 30)
    x = np.tanh(x / np.max(np.abs(x)) * 1.15)
    return x / np.max(np.abs(x)) * 0.89


def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)
    q = track_quarters(y.mean(0))
    print(f"beat 16 (loop start) at {q[16]:.2f}s, beat 96 at {q[96]:.2f}s")
    ch = Chopper(y, q, ratio=1.0, bpm=BPM)

    pads = {k: ch.beats(a, n) for k, (a, n) in CHORDS.items()}
    main_loop = ch.beats(*MAIN_LOOP)
    # intro figure: build its own beat grid from the motif's repeat period
    onset = librosa.onset.onset_detect(y=y.mean(0)[:int(15 * SR)], sr=SR, units="time")
    starts = [onset[np.argmin(np.abs(onset - t))] for t in (MOTIF_AT, MOTIF_AT + 4.81)]
    motif_q = starts[0] + np.arange(9) * (starts[1] - starts[0]) / 8
    motif = Chopper(y, motif_q, ratio=1.0, bpm=BPM).beats(0, 8)

    v0 = y[:, int(VOX_AT * SR):int((VOX_AT + VOX_LEN) * SR)]
    vox = {st: rb_pitch(v0, st) for st in {n[1] for bar in MELODY for n in bar}}

    for k, (name, x) in enumerate(list(pads.items()), 1):
        sf.write(os.path.join(out_dir, "kit", f"{k:02d}_chop_{name}.wav"), fades(x).T, SR, subtype="PCM_24")
    sf.write(os.path.join(out_dir, "kit", "08_main_loop_4bar.wav"), fades(main_loop).T, SR, subtype="PCM_24")
    sf.write(os.path.join(out_dir, "kit", "09_intro_motif_2bar.wav"), fades(motif).T, SR, subtype="PCM_24")
    names = {-5: "Bb4", -3: "C5", -2: "Db5", 0: "Eb5", 2: "F5", 3: "Gb5"}
    for st, x in sorted(vox.items()):
        sf.write(os.path.join(out_dir, "kit", f"10_vox_{names[st]}.wav"), fades(x, 0.004, 0.04).T, SR, subtype="PCM_24")

    chop = np.concatenate([render_bar(b, pads) for b in CHOP], axis=1)
    melody = room(np.concatenate([render_melody(b, vox) for b in MELODY], axis=1), wet=0.25)
    chop_vox = chop + 0.55 * melody
    sf.write(os.path.join(out_dir, "precious_chop_4bar.wav"), finish(room(chop_vox)).T, SR, subtype="PCM_24")
    sf.write(os.path.join(out_dir, "precious_main_loop_4bar.wav"), finish(main_loop).T, SR, subtype="PCM_24")

    rep = lambda x, k: np.concatenate([x] * k, axis=1)
    parts = [
        ("intro motif, filter opens", sweep_lp(rep(motif, 2), 300, 16000)),
        ("main loop (verse cycle)", rep(main_loop, 2)),
        ("the chop", chop),
        ("the chop + vocal-chop melody", chop_vox),
        ("main loop", main_loop),
        ("the chop + vocal-chop melody", chop_vox),
        ("intro motif, filter closes", sweep_lp(rep(motif, 2), 16000, 400)
         * np.linspace(1, 0, 2 * motif.shape[1]) ** 0.6),
    ]
    full = finish(room(np.concatenate([p for _, p in parts], axis=1)))
    sf.write(os.path.join(out_dir, "precious_loop_and_chop.wav"), full.T, SR, subtype="PCM_24")

    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write(f"{BPM:.0f} BPM, Db major (original pitch). No drums.\n\n")
        for name, p in parts:
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:32s} {p.shape[1] / SR / (4 * BEAT):.0f} bars\n")
            t += p.shape[1] / SR
    print(f"rendered {full.shape[1] / SR:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
