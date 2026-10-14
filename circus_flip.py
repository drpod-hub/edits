"""
Cinematic half-time flip of "CIRCUS MAXIMUS" - Travis Scott ft. The Weeknd & Swae Lee.

The record sits on an exact 125 BPM grid (bar = 1.9199 s), and three of its
sections run the same 8-bar cycle on Eb minor -> Cb -> Ab minor roots
(Eb x4 | B x2 | Ab x2). Those sections are made drumless with a strong
harmonic/percussive split (transient score 3.8 -> 1.6), high-passed, and
rebuilt into a new half-time beat:

  pad      the beat switch's pad (2:34), for the intro
  strings  the outro's rising string glides (3:47), the main loop
  synths   the rage section's synths (2:03), layered under drop 2
  melodic  the melodic section's sustained layer (3:05), for the switch-up

New production on top: 808s tuned to the record's own measured 808 pitches
(Eb1 39.6 Hz, B1 62.8 Hz, Ab1 52.15 Hz) with glides into each chord change,
a punch kick, layered clap, trap hats with 1/32 and triplet rolls, sidechain
pumping of the sample layers, a noise riser and the record's own string glide
reversed into each drop, an MPC stutter breakdown and a tape stop.

Usage: python3 circus_flip.py <source audio> <out dir>
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

from chop import SR, biquad, fades, sweep_lp

rng = np.random.default_rng(125)

BAR = 1.9199          # measured: onset fold over the whole song, 125.0 BPM
DOWN = 0.72           # first downbeat: where the harmony changes
BEAT = BAR / 4
STEP = BAR / 16
NB = int(round(BAR * SR))

LAYERS = {"pad": (80, 8), "strings": (118, 8), "synths": (64, 8), "melodic": (96, 8)}
ROOTS = ["Eb", "Eb", "Eb", "Eb", "B", "B", "Ab", "Ab"]           # per bar of the cycle
HZ_808 = {"Eb": 39.6, "B": 62.8, "Ab": 52.15}  # the record's own 808, measured


# ---------------------------------------------------------------- sample layers
def drumless(x):
    """Harmonic part of x. One mask, from the average of the two channels'
    magnitudes and clamped to [0, 1], is applied to both sides so left and
    right keep their phase relationship (mono-safe)."""
    D = [librosa.stft(c, n_fft=4096, hop_length=512) for c in x]
    M = (np.abs(D[0]) + np.abs(D[1])) / 2
    H, _ = librosa.decompose.hpss(M, kernel_size=(31, 31), margin=3.0)
    mask = np.clip(H / (M + 1e-9), 0, 1)
    out = [librosa.istft(d * mask, hop_length=512, length=x.shape[1]) for d in D]
    x = biquad(biquad(np.array(out), "hp", 110), "hp", 110)  # the new 808 owns the low end
    return mono_safe(x)


def mono_safe(x, max_side_db=-3.0):
    """Per-frequency M/S correction: wherever side is louder than mid - 3 dB,
    turn side down to that. These synths are side-heavy (the pad below 600 Hz,
    the strings' top octave), which would make them cancel in mono."""
    Mid = librosa.stft((x[0] + x[1]) / 2, n_fft=4096, hop_length=512)
    Sid = librosa.stft((x[0] - x[1]) / 2, n_fft=4096, hop_length=512)
    r = np.sqrt((np.abs(Sid) ** 2).mean(1)) / (np.sqrt((np.abs(Mid) ** 2).mean(1)) + 1e-12)
    g = np.minimum(1.0, 10 ** (max_side_db / 20) / (r + 1e-12))
    g = np.convolve(g, np.ones(9) / 9, mode="same")  # smooth across frequency
    side = librosa.istft(Sid * g[:, None], hop_length=512, length=x.shape[1])
    mid = (x[0] + x[1]) / 2
    return np.vstack([mid + side, mid - side])


# ---------------------------------------------------------------- drums
def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def bass808(f0, length, f_to=None, glide=0.0, glide_at=0.0):
    """808: pitch-drop attack, long body, saturated. With f_to, the pitch slides
    from f0 to f_to over `glide` seconds starting at `glide_at`."""
    t = t_axis(length)
    f = np.full(len(t), f0)
    if f_to is not None and glide > 0:
        g = np.clip((t - glide_at) / glide, 0, 1)
        f = f0 * (f_to / f0) ** (g * g * (3 - 2 * g))  # smooth log glide
    f = f * (1 + 1.2 * np.exp(-t * 55))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR)
    env = np.minimum(1, t / 0.003) * np.exp(-t * 0.9)
    env[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))
    x = np.tanh(2.4 * body * env) * 0.8
    return np.vstack([x, x])


def kick():
    t = t_axis(0.18)
    x = np.sin(2 * np.pi * np.cumsum(55 + 140 * np.exp(-t * 60)) / SR) * np.exp(-t * 22)
    x += biquad(rng.standard_normal(len(t)), "bp", 4000, 0.8) * np.exp(-t * 300) * 0.4
    return np.tanh(1.8 * x) * 0.7


def clap():
    t = t_axis(0.6)
    x = np.zeros(len(t))
    for d in (0.0, 0.009, 0.018, 0.026):
        i = int(d * SR)
        x[i:] += biquad(rng.standard_normal(len(t) - i), "bp", 1700, 1.0) * np.exp(-t[:len(t) - i] * 55)
    snare = biquad(rng.standard_normal(len(t)), "hp", 2500) * np.exp(-t * 18) * 0.5
    snare += np.sin(2 * np.pi * 210 * t) * np.exp(-t * 30) * 0.4
    x = x + snare
    tail = biquad(rng.standard_normal(int(0.8 * SR)) * np.exp(-t_axis(0.8) * 6), "lp", 7000)
    x = x + 0.06 * fftconvolve(x, tail)[:len(x)]
    return x / np.max(np.abs(x)) * 0.8


def hat(open_=False):
    t = t_axis(0.4 if open_ else 0.06)
    x = biquad(biquad(rng.standard_normal(len(t)), "hp", 8000), "hp", 8000)
    return x * np.exp(-t * (10 if open_ else 90)) * 0.35


def crash():
    t = t_axis(2.5)
    return biquad(rng.standard_normal(len(t)), "hp", 3500) * np.exp(-t * 2.2) * 0.3


KIT = {"K": kick(), "C": clap(), "H": hat(), "O": hat(True), "X": crash()}


def mono_place(dst, smp, at, gain=1.0, pan=0.0):
    i = int(round(at * SR))
    if i >= dst.shape[1]:
        return
    j = min(dst.shape[1], i + len(smp))
    dst[0, i:j] += smp[:j - i] * gain * (1 - pan)
    dst[1, i:j] += smp[:j - i] * gain * (1 + pan)


def drums(n_bars, style="full", roots=ROOTS):
    """Half-time trap pattern. Returns (drums, bass808, sidechain trigger times)."""
    d = np.zeros((2, n_bars * NB + SR))
    b = np.zeros((2, n_bars * NB + SR))
    hits = []
    kick_steps = {"full": [[0, 10], [0, 3, 10, 14]], "switch": [[0], [0, 11]], "drop2": [[0, 7, 10], [0, 3, 6, 10, 14]]}[style]
    for bar in range(n_bars):
        o = bar * BAR
        ks = kick_steps[bar % 2]
        root = roots[bar % len(roots)]
        nxt = roots[(bar + 1) % len(roots)]
        for k, s in enumerate(ks):
            at = o + s * STEP
            nxt_step = ks[k + 1] if k + 1 < len(ks) else 16
            length = (nxt_step - s) * STEP + (0.02 if k + 1 < len(ks) else 0.0)
            f0 = HZ_808[root]
            last = k == len(ks) - 1
            if last and nxt != root:            # late slide into the next chord
                x = bass808(f0, length, HZ_808[nxt], glide=0.14, glide_at=max(0.0, length - 0.16))
            elif style == "drop2" and s == 14:   # octave flick: start an octave up, drop
                x = bass808(f0 * 2, length, f0, glide=0.07)
            else:
                x = bass808(f0, length)
            i = int(round(at * SR))
            b[:, i:i + x.shape[1]] = x[:, :b.shape[1] - i]  # choke: new 808 replaces the tail
            mono_place(d, KIT["K"], at, 0.9)
            hits.append(at)
        if style != "switch":
            mono_place(d, KIT["C"], o + 8 * STEP, 1.0)
        else:
            mono_place(d, KIT["C"], o + 8 * STEP, 0.6)
        # hats
        if style == "switch":
            for k in range(12):                 # triplet hats
                mono_place(d, KIT["H"], o + k * BAR / 12, 0.5 + 0.3 * rng.random(), pan=-0.15)
        else:
            for s in range(0, 16, 2):
                if bar % 4 == 3 and s >= 12:
                    continue
                mono_place(d, KIT["H"], o + s * STEP, 0.55 + 0.35 * rng.random(), pan=-0.15)
            if bar % 4 == 3:                    # 1/32 roll, then a triplet run into the 1
                for r in range(8):
                    mono_place(d, KIT["H"], o + 12 * STEP + r * STEP / 2, 0.3 + 0.06 * r, pan=0.15)
            if bar % 4 == 1:
                for r in range(3):
                    mono_place(d, KIT["H"], o + 6 * STEP + r * (2 * STEP / 3), 0.6, pan=0.15)
            if style == "drop2" and bar % 2 == 0:
                mono_place(d, KIT["O"], o + 14 * STEP, 0.6, pan=0.2)
    n = n_bars * NB
    return d[:, :n], b[:, :n], hits


def sidechain(x, hits, depth=0.55, release=0.16):
    g = np.ones(x.shape[1])
    t = t_axis(release * 4)
    shape = 1 - depth * np.exp(-t / release * 2.5)
    for at in hits:
        i = int(round(at * SR))
        j = min(len(g), i + len(shape))
        g[i:j] = np.minimum(g[i:j], shape[:j - i])
    return x * g


# ---------------------------------------------------------------- fx
def riser(n_bars, glide_rev=None):
    n = n_bars * NB
    t = np.arange(n) / n
    common = rng.standard_normal(n)
    noise = np.vstack([common + 0.3 * rng.standard_normal(n), common + 0.3 * rng.standard_normal(n)])
    out = np.zeros((2, n))
    blocks = 48
    edges = np.linspace(0, n, blocks + 1).astype(int)
    for k in range(blocks):
        f = 300 * (9000 / 300) ** (k / (blocks - 1))
        out[:, edges[k]:edges[k + 1]] = biquad(noise[:, edges[k]:edges[k + 1]], "bp", f, 1.5)
    out *= (t ** 2.2) * 0.5
    if glide_rev is not None:
        g = glide_rev[:, -n:] if glide_rev.shape[1] >= n else np.pad(glide_rev, ((0, 0), (n - glide_rev.shape[1], 0)))
        out += g * (t ** 1.5) * 1.2
    return out


def stutter_bar(src, pattern):
    """MPC re-trigger: pattern = list of (step, source step, length steps)."""
    out = np.zeros((2, NB))
    for s, frm, ln in pattern:
        a = int(round(frm * STEP * SR))
        x = fades(src[:, a:a + int(round(ln * STEP * SR))], 0.002, 0.01)
        i = int(round(s * STEP * SR))
        out[:, i:i + x.shape[1]] += x[:, :NB - i]
    return out


def room(x, wet=0.12, sec=2.2):
    t = t_axis(sec)
    common = rng.standard_normal(len(t))
    ir = np.vstack([common + 0.5 * rng.standard_normal(len(t)), common + 0.5 * rng.standard_normal(len(t))])
    ir = biquad(ir * np.exp(-t * 2.6), "lp", 6500)
    tail = np.stack([fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)])
    return x + wet * tail / (np.max(np.abs(tail)) + 1e-9) * np.max(np.abs(x))


def limiter(x, ceiling=0.89, attack=0.002, release=0.08):
    """Look-ahead peak limiter: the gain dips just before each peak and recovers."""
    from scipy.ndimage import maximum_filter1d
    la = int(attack * SR)
    peak = maximum_filter1d(np.max(np.abs(x), axis=0), size=2 * la + 1)
    target = np.minimum(1.0, ceiling / (peak + 1e-9))
    a = np.exp(-1 / (release * SR))
    g = np.empty_like(target)
    cur = 1.0
    for i, v in enumerate(target):  # instant down, smooth release back up
        cur = v if v < cur else v + (cur - v) * a
        g[i] = cur
    return x * g


def master(x, loudness_db=-11.5):
    x = biquad(x, "hp", 25)
    x = x / np.sqrt(np.mean(x ** 2)) * 10 ** (loudness_db / 20)
    x = np.tanh(x * 1.1) / 1.1      # gentle glue
    return limiter(x)


# ---------------------------------------------------------------- main
def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)

    def bars(first, n):
        a = int(round((DOWN + first * BAR) * SR))
        return y[:, a:a + n * NB]

    L = {k: drumless(bars(*v)) for k, v in LAYERS.items()}  # already wide stereo synths
    strings, synths, melodic, pad = L["strings"], L["synths"], L["melodic"], L["pad"]
    glide = strings[:, int(2 * NB):int(4 * NB)]          # the rising string line, bars 3-4
    glide_rev = glide[:, ::-1].copy()

    secs = []

    def section(name, layer, drum_style=None, extra=None, sc=True, gain=1.0):
        n = layer.shape[1]
        mix = layer * gain
        if drum_style:
            d, b, hits = drums(n // NB, drum_style)
            if sc:
                mix = sidechain(mix, hits)
            mix = mix + d * 0.9 + b * 1.0
        if extra is not None:
            mix = mix + extra[:, :n]
        secs.append((name, mix))

    rep = lambda x, k: np.concatenate([x] * k, axis=1)

    # 1) intro: beat-switch pad, filter opening, riser + reversed glide into the drop
    intro = sweep_lp(pad, 350, 15000)
    r = np.zeros_like(intro)
    r[:, -2 * NB:] = riser(2, glide_rev)
    section("intro: pad, filter opens, riser", intro, extra=r, gain=1.1)

    # 2) drop 1: strings x2, full drums, 808, sidechain, crash on the 1
    imp = np.zeros((2, 16 * NB))
    mono_place(imp, KIT["X"], 0, 1.0)
    section("drop 1: strings + drums + tuned 808", rep(strings, 2), "full", extra=imp)

    # 3) switch: melodic layer, triplet hats, sparse 808
    section("switch: melodic layer, triplet hats", melodic, "switch", gain=1.1)

    # 4) breakdown: MPC stutter of the strings, no drums, riser into drop 2
    pats = [
        [(0, 0, 3), (3, 0, 3), (6, 0, 2), (8, 8, 4), (12, 8, 2), (14, 8, 2)],
        [(0, 0, 4), (4, 0, 2), (6, 0, 2), (8, 0, 1), (9, 0, 1), (10, 0, 1), (11, 0, 1), (12, 0, 4)],
        [(0, 0, 3), (3, 0, 3), (6, 0, 2), (8, 8, 4), (12, 8, 2), (14, 8, 2)],
        [(0, 0, 2), (2, 0, 2), (4, 0, 1), (5, 0, 1), (6, 0, 1), (7, 0, 1)] + [(8 + k, 0, 1) for k in range(8)],
    ]
    bd = np.concatenate([stutter_bar(strings[:, (k % 4) * NB:], p) for k, p in enumerate(pats)], axis=1)
    bd = sweep_lp(bd, 9000, 1200)
    r = np.zeros_like(bd)
    r[:, -2 * NB:] = riser(2, glide_rev)
    section("breakdown: MPC stutter, riser", bd, extra=r)

    # 5) drop 2: strings + synths layered, busier drums and 808 flicks
    imp = np.zeros((2, 16 * NB))
    mono_place(imp, KIT["X"], 0, 1.0)
    section("drop 2: strings + synths, busier drums", rep(strings, 2) + 0.6 * rep(synths, 2), "drop2", extra=imp)

    # 6) outro: strings alone, filter closes, tape stop
    out = sweep_lp(strings[:, :4 * NB].copy(), 15000, 500)
    n = NB
    last = out[:, -n:]
    pos = np.clip(np.cumsum(np.linspace(1, 0, n) ** 0.7), 0, n - 1)
    out[:, -n:] = np.vstack([np.interp(pos, np.arange(n), c) for c in last]) * np.linspace(1, 0, n) ** 0.5
    section("outro: strings, filter closes, tape stop", out)

    # level-match to drop 1 (quieter intro/breakdown/outro so drops hit)
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    ref = rms(secs[1][1])
    trims = {0: -3.0, 2: -1.0, 3: -2.5, 4: 0.5, 5: -3.0}
    secs = [(nm, x * ref / rms(x) * 10 ** (trims.get(k, 0) / 20)) for k, (nm, x) in enumerate(secs)]
    full = master(room(np.concatenate([x for _, x in secs], axis=1), wet=0.06))
    sf.write(os.path.join(out_dir, "circus_maximus_flip.wav"), full.T, SR, subtype="PCM_24")

    # kit: drumless layers, a drum loop, the 808 notes
    for k, (name, x) in enumerate(L.items(), 1):
        sf.write(os.path.join(out_dir, "kit", f"{k:02d}_{name}_8bar_drumless.wav"), fades(x).T, SR, subtype="PCM_24")
    d, b, _ = drums(8, "full")
    sf.write(os.path.join(out_dir, "kit", "05_drums_8bar_halftime.wav"), (d * 0.9).T, SR, subtype="PCM_24")
    sf.write(os.path.join(out_dir, "kit", "06_808_8bar_tuned.wav"), b.T, SR, subtype="PCM_24")
    for note in ("Eb", "B", "Ab"):
        sf.write(os.path.join(out_dir, "kit", f"07_808_{note}.wav"), bass808(HZ_808[note], 1.5).T, SR, subtype="PCM_24")

    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write("125 BPM (half-time feel), Eb minor. Cycle: Eb x4 | B x2 | Ab x2\n\n")
        for name, x in secs:
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:44s} {x.shape[1] / NB:.0f} bars\n")
            t += x.shape[1] / SR
    print(f"rendered {full.shape[1] / SR:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
