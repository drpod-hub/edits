"""
Chop flip of "Say It" - The Masqueraders. No drums: the groove comes from
where the chops land.

The record is ~74 BPM in G major. It is varispeeded +2 semitones (-> A major)
and every chop is quantized to 84 BPM. The chops are re-sequenced into a
chromatic walk-down the record never plays:

    | Cmaj7 | Bm7  Bbmaj7 | Am7 | D |        (source key)
    | Dmaj7 | C#m7 Cmaj7  | Bm7 | E |        (after the +2 flip)

Each bar is cut on a 3-3-4-3-3 / 3-3-2 sixteenth grid with MPC-style choke
(every hit cuts off the last), so it bounces on its own.

Usage: python3 say_chop.py <source audio> <out dir>
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

from chop import SR, Chopper, analyze, biquad, fades, fit, sweep_lp, varispeed

SEMITONES = 2
RATIO = 2 ** (SEMITONES / 12)
BPM = 84.0
STEP = 60.0 / BPM / 4  # one 16th
BAR_N = int(round(16 * STEP * SR))
rng = np.random.default_rng(3)

# Chop sources, as (first quarter-note index, beats), counted from the first
# downbeat at 0:02.6. One bar = 4 quarters.
SOURCES = {
    "Cmaj7":  (48, 4),   # 0:41.7, the C - G - Bm section
    "Bm7":    (54, 2),   # 0:46.6
    "Am7":    (24, 4),   # 0:22.3
    "D":      (6, 2),    # 0:07.6, intro
    "vox":    (108, 2),  # 1:30.0, sustained vibrato line over Bm7
}
# The band lets the previous chord ring into the downbeat, so these chops
# start one beat (4 sixteenths) late, where the new chord has settled.
TRIM = {"Cmaj7": 4, "Am7": 4}
# The record never plays a clean Bbmaj7 (its intro has a Bb/B cluster), so it
# is made MPC-style: the Cmaj7 chop played two semitones down.
REPITCHED = {"Bbmaj7": ("Cmaj7", -2)}
FLIPPED = {"Cmaj7": "Dmaj7", "Bm7": "C#m7", "Bbmaj7": "Cmaj7", "Am7": "Bm7",
           "D": "E", "vox": "vox"}

# (step, source, source offset in 16ths, length in 16ths, gain, reverse)
MAIN = [
    [(0, "Cmaj7", 0, 3), (3, "Cmaj7", 0, 3), (6, "Cmaj7", 0, 4), (10, "Cmaj7", 4, 3), (13, "Cmaj7", 8, 3)],
    [(0, "Bm7", 0, 3), (3, "Bm7", 0, 3), (6, "Bm7", 4, 2), (8, "Bbmaj7", 0, 3), (11, "Bbmaj7", 0, 3), (14, "Bbmaj7", 4, 2)],
    [(0, "Am7", 0, 3), (3, "Am7", 0, 3), (6, "Am7", 0, 4), (10, "Am7", 4, 6)],
    [(0, "D", 0, 6), (6, "D", 0, 2), (8, "D", 0, 4),
     (12, "vox", 0, 1), (13, "vox", 0, 1), (14, "vox", 0, 1), (15, "vox", 0, 1)],
]
VARIATION = [
    [(0, "Cmaj7", 0, 6), (6, "Cmaj7", 0, 2), (8, "Cmaj7", 4, 8)],
    [(0, "Bm7", 0, 2), (2, "Bm7", 0, 2), (4, "Bm7", 0, 4), (8, "Bbmaj7", 0, 6), (14, "Bbmaj7", 0, 2)],
    [(0, "Am7", 0, 3), (3, "Am7", 0, 3), (6, "Am7", 4, 2), (8, "Am7", 0, 4), (12, "Am7", 0, 4, 1.0, True)],
    [(0, "D", 0, 3), (3, "D", 0, 3), (6, "D", 4, 2), (8, "vox", 0, 8)],
]


def hit(src, offset, length, reverse=False):
    a = int(round(offset * STEP * SR))
    n = int(round(length * STEP * SR))
    x = src[:, a:a + n].copy()
    if reverse:
        x = x[:, ::-1]
        x *= np.linspace(0.3, 1, x.shape[1])  # swell into the next bar
    return fades(x, 0.002, 0.012)


def render_bar(pattern, pads):
    out = np.zeros((2, BAR_N))
    for h in pattern:
        step, name, off, length = h[:4]
        gain = h[4] if len(h) > 4 else 1.0
        rev = h[5] if len(h) > 5 else False
        x = hit(pads[name], off, length, rev) * gain
        i = int(round(step * STEP * SR))
        j = min(BAR_N, i + x.shape[1])
        out[:, i:j] += x[:, :j - i]
    return out


def sustained_bar(chords, pads):
    """Intro version: chords held whole, no retriggers."""
    out = np.zeros((2, BAR_N))
    pos = 0
    for name, length in chords:
        x = fades(pads[name][:, :int(round(length * STEP * SR))], 0.01, 0.03)
        i = int(round(pos * STEP * SR))
        out[:, i:i + x.shape[1]] += x[:, :BAR_N - i]
        pos += length
    return out


def room(x, wet=0.08):
    t = np.arange(int(0.6 * SR)) / SR
    ir = rng.standard_normal((2, len(t))) * np.exp(-t * 7)
    ir = biquad(ir, "lp", 6000)
    tail = np.stack([fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)])
    return x + wet * tail / np.max(np.abs(tail)) * np.max(np.abs(x))


def finish(x):
    x = biquad(biquad(x, "hp", 30), "lp", 15000)
    x = np.tanh(x / np.max(np.abs(x)) * 1.2)
    return x / np.max(np.abs(x)) * 0.89


def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "pads"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)
    q = analyze(y.mean(0))
    src_bpm = 60 * (len(q) - 1) / (q[-1] - q[0])
    print(f"source ~{src_bpm:.1f} BPM, downbeat {q[0]:.2f}s -> {BPM} BPM, +{SEMITONES} st")
    ch = Chopper(y, q, ratio=RATIO, bpm=BPM)
    pads = {name: ch.beats(first, n) for name, (first, n) in SOURCES.items()}
    for name, steps in TRIM.items():
        pads[name] = pads[name][:, int(round(steps * STEP * SR)):]
    for name, (base, st) in REPITCHED.items():
        pads[name] = varispeed(pads[base], 2 ** (st / 12))
    for k, (name, x) in enumerate(pads.items(), 1):
        sf.write(os.path.join(out_dir, "pads", f"{k:02d}_{FLIPPED[name]}_{name}.wav"),
                 fades(x).T, SR, subtype="PCM_24")

    main_loop = np.concatenate([render_bar(b, pads) for b in MAIN], axis=1)
    var_loop = np.concatenate([render_bar(b, pads) for b in VARIATION], axis=1)
    intro = np.concatenate([
        sustained_bar([("Cmaj7", 12), ("Cmaj7", 4)], pads),
        sustained_bar([("Bm7", 8), ("Bbmaj7", 8)], pads),
        sustained_bar([("Am7", 12), ("Am7", 4)], pads),
        sustained_bar([("D", 8), ("D", 8)], pads),
    ], axis=1)
    intro = sweep_lp(intro, 300, 16000)

    # ending: one last Dmaj7 (flipped) hit left to ring out
    end = np.zeros((2, BAR_N))
    last = fit(pads["Cmaj7"], BAR_N)
    end += last * np.linspace(1, 0, BAR_N) ** 1.5

    full = np.concatenate([intro, main_loop, main_loop, var_loop, var_loop, main_loop, end], axis=1)
    full = finish(room(full))
    sf.write(os.path.join(out_dir, "say_it_chop_full.wav"), full.T, SR, subtype="PCM_24")
    sf.write(os.path.join(out_dir, "say_it_main_loop_4bar.wav"),
             finish(room(main_loop)).T, SR, subtype="PCM_24")
    sf.write(os.path.join(out_dir, "say_it_variation_loop_4bar.wav"),
             finish(room(var_loop)).T, SR, subtype="PCM_24")

    bar = 16 * STEP
    layout = [("intro (held chords, filter opens)", 4), ("main chop", 8),
              ("variation (reverse swell, vocal tail)", 8), ("main chop", 4), ("last hit rings out", 1)]
    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write(f"{BPM:.0f} BPM, A major (G +{SEMITONES} st). No drums.\n")
        f.write("Progression: | Dmaj7 | C#m7 Cmaj7 | Bm7 | E |\n\n")
        for name, bars in layout:
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:38s} {bars} bars\n")
            t += bars * bar
    print(f"rendered {full.shape[1] / SR:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
