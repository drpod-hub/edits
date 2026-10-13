"""
Two-part flip of "Like Honey" - Argent, with a tape spin-up beat switch.

Part 1 "slowed": the drumless intro, varispeeded DOWN 3 semitones (103 -> 87 BPM,
  F#m), with tape wobble and Argent's own drummer re-chopped and pitched down.
      | Am7 | Gmaj7 | D | Bbmaj7 . E |   ->   | F#m7 | Emaj7 | B | Gmaj7 . C# |
  The Bb -> E tritone jump is squeezed into one bar.

Switch: the loop spins up 3 semitones back to the record's own pitch and lands
  on the band's big ensemble hit from 2:23.

Part 2 "full flight": the band's D-A / A-E riff at original pitch and 112 BPM
  (A, the relative major of Part 1's F#m), the same drummer re-sequenced, a
  drums-only break, then the riff again and a tape stop.

Usage: python3 honey_flip.py <source audio> <out dir>
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

from chop import SR, Chopper, biquad, crunch, fades, fit, sweep_lp, varispeed

rng = np.random.default_rng(11)

P1_SEMITONES = -3
P1_RATIO = 2 ** (P1_SEMITONES / 12)
P1_BPM = 87.0   # intro 103.4 BPM x 0.841
P2_BPM = 112.0  # the groove section's own tempo

# Beat indexes (quarter notes from the first beat at 0:00.5). One bar = 4.
P1_PIECES = [(24, 4),   # Am7    0:14.2
             (28, 4),   # Gmaj7  0:16.5
             (32, 4),   # D      0:18.8
             (36, 2),   # Bbmaj7 0:21.1
             (44, 2)]   # E      0:25.7
P2_RIFF = (120, 16)     # 1:07.0, Dsus-A | Asus-E | Dsus-A | Asus-B7

# One-shots, in seconds, picked by onset scoring on the percussive layer
KICK_AT, SNARE_AT, HAT_AT = 47.404, 49.041, 61.904
IMPACT_AT = 143.12      # full-band hit at 2:23


def track_quarters(y_mono):
    yy = librosa.resample(y_mono, orig_sr=SR, target_sr=22050)
    _, beats = librosa.beat.beat_track(y=yy, sr=22050)
    bt = librosa.frames_to_time(beats, sr=22050)
    oenv = librosa.onset.onset_strength(y=yy, sr=22050)
    ot = librosa.times_like(oenv, sr=22050)
    out = []
    for x in bt:  # snap to the transient
        m = (ot > x - 0.04) & (ot < x + 0.04)
        out.append(ot[m][np.argmax(oenv[m])] if m.any() else x)
    return np.array(out)


# ---------------------------------------------------------------- one-shots
def one_shots(y):
    mono = y.mean(0)
    D = librosa.stft(mono, n_fft=2048, hop_length=512)
    _, P = librosa.decompose.hpss(D, margin=(1.0, 3.0))
    perc = librosa.istft(P, length=len(mono))

    def cut(at, sec, fout=0.04):
        i = int(at * SR)
        return fades(perc[None, i:i + int(sec * SR)], 0.001, fout)[0]

    kick = cut(KICK_AT, 0.28)
    t = np.arange(len(kick)) / SR
    sub = np.sin(2 * np.pi * np.cumsum(50 + 60 * np.exp(-t * 40)) / SR) * np.exp(-t * 9)
    kick = kick / np.max(np.abs(kick)) + 0.7 * sub  # the record's kick is thin under the bass
    snare = cut(SNARE_AT, 0.32)
    hat = cut(HAT_AT, 0.11, 0.03)
    shots = {"kick": kick, "snare": snare, "hat": hat}
    return {k: v / np.max(np.abs(v)) for k, v in shots.items()}


def pitched(shots, ratio):
    return {k: varispeed(v[None], ratio)[0] for k, v in shots.items()}


# ---------------------------------------------------------------- drums
def drums(shots, bpm, bars, patterns, swing=0.0, drunk=0.0, drop_last=0):
    """patterns: list of {name: [16th steps]} cycled per bar; drop_last mutes
    the last `drop_last` 16ths of the final bar."""
    step = 60 / bpm / 4
    n = int(round(bars * 16 * step * SR))
    out = np.zeros(n + SR)
    vel = {"kick": 1.0, "snare": 0.85, "hat": 0.35, "ghost": 0.3}
    for b in range(bars):
        for name, steps in patterns[b % len(patterns)].items():
            for s in steps:
                if b == bars - 1 and s >= 16 - drop_last:
                    continue
                t = (b * 16 + s) * step
                if s % 2:
                    t += swing * step
                if name == "hat":
                    t += abs(rng.normal(0, drunk))  # lazy, behind-the-beat hats
                smp = shots["snare" if name == "ghost" else name]
                v = vel[name] * (0.75 + 0.5 * rng.random() if name == "hat" else 1)
                i = int(t * SR)
                out[i:i + len(smp)] += smp * v
    out = crunch(out[:n])
    return np.vstack([out, out])


P1_DRUMS = [  # slow head-nod
    {"kick": [0, 7, 10], "snare": [4, 12], "hat": [0, 2, 4, 6, 8, 10, 12, 14]},
    {"kick": [0, 3, 10, 13], "snare": [4, 12], "ghost": [15], "hat": [0, 2, 4, 6, 8, 10, 12, 14]},
]
P2_DRUMS = [  # straighter, pushes like the band
    {"kick": [0, 6, 8], "snare": [4, 12], "hat": list(range(0, 16, 2))},
    {"kick": [0, 6, 10, 11], "snare": [4, 12], "ghost": [7], "hat": list(range(0, 16, 2))},
    {"kick": [0, 6, 8], "snare": [4, 12], "hat": list(range(0, 16, 2))},
    {"kick": [0, 6, 10], "snare": [4, 12, 14, 15], "hat": list(range(0, 12, 2))},  # fill
]
P2_BREAK = [
    {"kick": [0, 3, 6, 10], "snare": [4, 12], "ghost": [9, 15], "hat": list(range(16))},
    {"kick": [0, 6, 8, 11], "snare": [4, 12], "ghost": [14], "hat": list(range(0, 16, 2))},
    {"kick": [0, 3, 6, 10], "snare": [4, 12], "ghost": [9, 15], "hat": list(range(0, 16, 2))},
    {"kick": [0, 6, 8], "snare": [4, 10, 12, 13, 14, 15], "hat": list(range(0, 8, 2))},
]


# ---------------------------------------------------------------- tape fx
def wobble(x, depth=0.0022, rate=0.55):
    """Tape wow: slowly modulated read position (about +-12 cents)."""
    n = x.shape[1]
    idx = np.arange(n) + depth * SR * np.sin(2 * np.pi * rate * np.arange(n) / SR)
    idx = np.clip(idx, 0, n - 1)
    return np.vstack([np.interp(idx, np.arange(n), c) for c in x])


def speed_ramp(src, n_out, r0, r1, curve=1.0):
    """Read src with playback rate gliding r0 -> r1 (pitch and speed together)."""
    rates = r0 + (r1 - r0) * np.linspace(0, 1, n_out) ** curve
    pos = np.clip(np.cumsum(rates), 0, src.shape[1] - 1)
    return np.vstack([np.interp(pos, np.arange(src.shape[1]), c) for c in src])


def room(x, wet=0.07):
    t = np.arange(int(0.8 * SR)) / SR
    ir = biquad(rng.standard_normal((2, len(t))) * np.exp(-t * 5), "lp", 5000)
    tail = np.stack([fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)])
    return x + wet * tail / np.max(np.abs(tail)) * np.max(np.abs(x))


def finish(x):
    x = biquad(biquad(x, "hp", 28), "lp", 16000)
    x = np.tanh(x / np.max(np.abs(x)) * 1.3)
    return x / np.max(np.abs(x)) * 0.89


def place(dst, x, at):
    i = int(round(at * SR))
    j = min(dst.shape[1], i + x.shape[1])
    dst[:, i:j] += x[:, :j - i]


# ---------------------------------------------------------------- main
def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)
    q = track_quarters(y.mean(0))
    print("bar 6 / 9 / 11 / 30 at", [round(q[i], 2) for i in (24, 36, 44, 120)])

    # ---- Part 1 material
    c1 = Chopper(y, q, ratio=P1_RATIO, bpm=P1_BPM)
    loop1 = np.concatenate([c1.beats(a, n) for a, n in P1_PIECES], axis=1)
    loop1 = wobble(biquad(loop1, "lp", 9000))  # darker and warped
    bar1 = 4 * 60 / P1_BPM
    # ---- Part 2 material
    c2 = Chopper(y, q, ratio=1.0, bpm=P2_BPM)
    riff = c2.beats(*P2_RIFF)
    bar2 = 4 * 60 / P2_BPM
    i0 = int(IMPACT_AT * SR)
    impact = fades(y[:, i0:i0 + int(1.6 * SR)], 0.002, 0.6)

    shots = one_shots(y)
    shots1 = pitched(shots, P1_RATIO)  # fatter, darker drummer for the slow half

    # ---- kit export
    kit = {"01_slowed_loop_4bar_87bpm": loop1, "02_riff_loop_4bar_112bpm": riff,
           "03_impact_hit": impact}
    for k, v in shots.items():
        kit[f"04_{k}_argent"] = np.vstack([v, v])
    for k, v in shots1.items():
        kit[f"05_{k}_argent_slowed"] = np.vstack([v, v])
    for name, x in kit.items():
        sf.write(os.path.join(out_dir, "kit", f"{name}.wav"), fades(x).T, SR, subtype="PCM_24")

    # ---- Part 1: 4 intro + 8 groove + 4 (last bar spins up)
    p1 = np.zeros((2, int(round(16 * bar1 * SR))))
    intro = sweep_lp(loop1, 250, 14000)
    place(p1, intro, 0)
    for k in range(3):
        place(p1, biquad(loop1, "lowshelf", 120, gain_db=-4), (4 + 4 * k) * bar1)
    place(p1, drums(shots1, P1_BPM, 12, P1_DRUMS, swing=0.22, drunk=0.006, drop_last=8) * 0.8, 4 * bar1)
    # spin-up over the last two beats: the loop's final half bar (the C# chop)
    # read faster and faster until it is back at the record's own pitch
    n_spin = int(round(bar1 / 2 * SR))
    tail_src = np.concatenate([loop1[:, -n_spin:], loop1], axis=1)
    spin = speed_ramp(tail_src, n_spin, 1.0, 1 / P1_RATIO, curve=1.6)
    spin = fades(spin, 0.005, 0.02)
    a = int(round((16 * bar1 - bar1 / 2) * SR))
    p1[:, a:] = 0
    p1[:, a:a + n_spin] = spin[:, :p1.shape[1] - a]

    # ---- Part 2: 8 riff + 4 drum break + 8 riff + tape stop
    p2 = np.zeros((2, int(round(21 * bar2 * SR))))
    riff_m = biquad(riff, "lowshelf", 100, gain_db=-3)
    for k in (0, 1):
        place(p2, riff_m, 4 * k * bar2)
    place(p2, impact * 0.9, 0)
    place(p2, drums(shots, P2_BPM, 8, P2_DRUMS, swing=0.08, drunk=0.002), 0)
    # break: drummer alone, riff only as a stab on each downbeat
    place(p2, drums(shots, P2_BPM, 4, P2_BREAK, swing=0.08, drunk=0.002), 8 * bar2)
    stab = fades(riff_m[:, :int(round(bar2 / 8 * SR))], 0.002, 0.03)
    for b in range(4):
        place(p2, stab, (8 + b) * bar2)
    for k in (0, 1):
        place(p2, riff_m, (12 + 4 * k) * bar2)
    place(p2, drums(shots, P2_BPM, 8, P2_DRUMS, swing=0.08, drunk=0.002), 12 * bar2)
    place(p2, impact * 0.6, 12 * bar2)
    # tape stop: one more bar of riff, slowing to a halt
    n_stop = int(round(bar2 * SR))
    stop = speed_ramp(riff_m, n_stop, 1.0, 0.0, curve=0.7) * np.linspace(1, 0, n_stop) ** 0.4
    place(p2, stop, 20 * bar2)

    full = finish(room(np.concatenate([p1, p2], axis=1)))
    sf.write(os.path.join(out_dir, "like_honey_flip.wav"), full.T, SR, subtype="PCM_24")

    p1_len, p2_len = p1.shape[1] / SR, p2.shape[1] / SR
    rows = [(0, "PART 1  slowed (-3 st, 87 BPM, F#m)", ""),
            (0, "intro, filter opens, no drums", "4 bars"),
            (4 * bar1, "loop + Argent's drummer, pitched down", "8 bars"),
            (12 * bar1, "loop + drums, spin-up on the last 2 beats", "4 bars"),
            (p1_len, "PART 2  full flight (original pitch, 112 BPM, A)", ""),
            (p1_len, "the band's 2:23 hit, riff + drums", "8 bars"),
            (p1_len + 8 * bar2, "drum break, riff stabs on the 1", "4 bars"),
            (p1_len + 12 * bar2, "riff + drums", "8 bars"),
            (p1_len + 20 * bar2, "tape stop", "1 bar")]
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        for t, name, bars in rows:
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:48s} {bars}\n")
    print(f"rendered {full.shape[1] / SR:.1f}s ({p1_len:.1f}s + {p2_len:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
