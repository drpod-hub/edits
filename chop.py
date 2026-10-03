"""
Kanye-style (College Dropout era) chipmunk-soul flip of
"The Smith Connection - You Ain't Livin' Unless You're Lovin'".

Pipeline:
  1. Beat-track the record (live band, ~75.5 BPM) and snap beats to transients.
  2. Varispeed the sample +3 semitones (tape-style: pitch and tempo up together),
     which lands it at 90 BPM, key C -> Eb (and the Db key change -> E).
  3. Quantize every beat of every chop to an exact 90 BPM grid (rubberband
     fine-fit of a few percent, pitch untouched) so it locks with the drums.
  4. Build an MPC-style 16-pad kit, synthesize dusty SP-1200 style drums and a
     sub bass, then sequence a full beat.

Usage: python3 chop.py <source audio> <out dir>
"""
import os
import subprocess
import sys
import tempfile

import librosa
import numpy as np
import soundfile as sf
from scipy import signal

SR = 44100
SEMITONES = 3
RATIO = 2 ** (SEMITONES / 12)  # varispeed ratio, 1.1892
BPM = 90.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(7)


# ---------------------------------------------------------------- analysis
def analyze(y_mono):
    yy = librosa.resample(y_mono, orig_sr=SR, target_sr=22050)
    _, beats = librosa.beat.beat_track(y=yy, sr=22050)
    bt = librosa.frames_to_time(beats, sr=22050)
    oenv = librosa.onset.onset_strength(y=yy, sr=22050)
    ot = librosa.times_like(oenv, sr=22050)

    def strength(ts):
        return np.mean(np.interp(ts, ot, oenv))

    # tracker locks to 8th notes (~152); keep the stronger phase as quarters
    q = bt[0::2] if strength(bt[0::2]) >= strength(bt[1::2]) else bt[1::2]
    snapped = []
    for x in q:
        m = (ot > x - 0.05) & (ot < x + 0.05)
        snapped.append(ot[m][np.argmax(oenv[m])] if m.any() else x)
    return np.array(snapped)


# ---------------------------------------------------------------- dsp utils
def rubberband_tempo(x, tempo):
    """Time-stretch stereo x by `tempo` (>1 = shorter) keeping pitch."""
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        sf.write(a, x.T, SR, subtype="FLOAT")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", a, "-af",
             f"rubberband=tempo={tempo:.6f}:transients=crisp", b],
            check=True,
        )
        out, _ = sf.read(b, always_2d=True)
    return out.T


def varispeed(x, ratio):
    """Tape-style speed change: pitch and tempo move together."""
    n = int(round(x.shape[1] / ratio))
    return signal.resample_poly(x, 10000, int(round(10000 * ratio)), axis=1)[:, :n]


def fit(x, n):
    if x.shape[1] >= n:
        return x[:, :n]
    return np.pad(x, ((0, 0), (0, n - x.shape[1])))


def fades(x, fin=0.003, fout=0.008):
    x = x.copy()
    a, b = int(fin * SR), int(fout * SR)
    if a:
        x[:, :a] *= np.linspace(0, 1, a)
    if b:
        x[:, -b:] *= np.linspace(1, 0, b)
    return x


def biquad(x, kind, f, q=0.707, gain_db=0.0):
    w = 2 * np.pi * f / SR
    cw, sw = np.cos(w), np.sin(w)
    al = sw / (2 * q)
    A = 10 ** (gain_db / 40)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "bp":
        b = [al, 0, -al]; a = [1 + al, -2 * cw, 1 - al]
    elif kind == "lowshelf":
        sA = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * cw + sA), 2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - sA)]
        a = [(A + 1) + (A - 1) * cw + sA, -2 * ((A - 1) + (A + 1) * cw),
             (A + 1) + (A - 1) * cw - sA]
    return signal.lfilter(b, a, x, axis=-1)


def sweep_lp(x, f0, f1):
    """Lowpass whose cutoff glides f0 -> f1 (log) across the clip, block-wise."""
    out = np.zeros_like(x)
    blocks = 64
    n = x.shape[1]
    edges = np.linspace(0, n, blocks + 1).astype(int)
    zi = None
    for i in range(blocks):
        f = f0 * (f1 / f0) ** (i / (blocks - 1))
        w = 2 * np.pi * min(f, 20000) / SR
        cw, sw = np.cos(w), np.sin(w); al = sw / (2 * 0.707)
        b = np.array([(1 - cw) / 2, 1 - cw, (1 - cw) / 2]) / (1 + al)
        a = np.array([1, -2 * cw / (1 + al), (1 - al) / (1 + al)])
        if zi is None:
            zi = np.zeros((x.shape[0], 2))
        out[:, edges[i]:edges[i + 1]], zi = signal.lfilter(
            b, a, x[:, edges[i]:edges[i + 1]], axis=-1, zi=zi)
    return out


# ---------------------------------------------------------------- chopping
class Chopper:
    def __init__(self, y, beats):
        self.y, self.q = y, beats

    def beats(self, first, count, quantize=True):
        """Chop `count` beats starting at beat index `first`, pitched up and
        quantized to exactly `count` beats at BPM."""
        n_beat = int(round(BEAT * SR))
        if not quantize:
            a, b = int(self.q[first] * SR), int(self.q[first + count] * SR)
            return fit(varispeed(self.y[:, a:b], RATIO), n_beat * count)
        pad = int(0.03 * SR)
        xf = int(0.006 * SR)
        out = np.zeros((2, n_beat * count + xf))
        for k in range(count):
            a, b = int(self.q[first + k] * SR), int(self.q[first + k + 1] * SR)
            seg = self.y[:, a:b + pad]
            seg = varispeed(seg, RATIO)
            tempo = ((b - a) / RATIO) / n_beat
            if abs(tempo - 1) > 0.004:
                seg = rubberband_tempo(seg, tempo)
            seg = fit(seg, n_beat + xf)
            ramp = np.ones(n_beat + xf)
            ramp[:xf] = np.linspace(0, 1, xf) if k else 1
            ramp[-xf:] = np.linspace(1, 0, xf)
            out[:, k * n_beat:k * n_beat + n_beat + xf] += seg * ramp
        return out[:, :n_beat * count]

    def bars(self, first_bar, count, **kw):
        return self.beats(first_bar * 4, count * 4, **kw)


# ---------------------------------------------------------------- drums
def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def kick():
    t = t_axis(0.5)
    f = 46 + 120 * np.exp(-t * 32)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6.5)
    click = biquad(rng.standard_normal(len(t)), "bp", 3500, 1.0) * np.exp(-t * 400) * 0.6
    return np.tanh(2.2 * (body + click)) * 0.95


def snare():
    t = t_axis(0.45)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28) * 0.7
    body += np.sin(2 * np.pi * 330 * t) * np.exp(-t * 40) * 0.3
    nz = rng.standard_normal(len(t))
    nz = biquad(biquad(nz, "hp", 1200), "lp", 9000) * np.exp(-t * 15)
    clap = np.zeros(len(t))
    for d in (0.0, 0.011, 0.022):  # hand-clap flams layered on top
        i = int(d * SR)
        burst = rng.standard_normal(len(t) - i) * np.exp(-t[:len(t) - i] * 70)
        clap[i:] += biquad(burst, "bp", 1600, 1.2)
    s = body + 0.9 * nz + 0.5 * clap
    room = rng.standard_normal(int(0.35 * SR)) * np.exp(-t_axis(0.35) * 14)
    s = s + 0.05 * signal.fftconvolve(s, room)[:len(s)]
    return np.tanh(1.6 * s) * 0.85


def hat(open_=False):
    t = t_axis(0.35 if open_ else 0.09)
    nz = biquad(biquad(rng.standard_normal(len(t)), "hp", 7000), "hp", 7000)
    return nz * np.exp(-t * (11 if open_ else 75)) * 0.5


def crunch(x, sr_low=26040, bits=12):
    """SP-1200-ish: sample-and-hold to 26 kHz and 12-bit quantize."""
    idx = (np.floor(np.arange(len(x)) * sr_low / SR) * SR / sr_low).astype(int)
    held = x[np.clip(idx, 0, len(x) - 1)]
    steps = 2 ** (bits - 1)
    return np.round(held * steps) / steps


KIT = {k: crunch(v) for k, v in
       {"K": kick(), "S": snare(), "H": hat(), "O": hat(True)}.items()}

# 16th-step boom-bap patterns, two bars (A, B); hats added separately with swing
PATTERNS = {
    "full": [{"K": [0, 7, 10], "S": [4, 12]},
             {"K": [0, 3, 10, 14], "S": [4, 12, 15]}],
    "verse2": [{"K": [0, 10, 11], "S": [4, 12]},
               {"K": [0, 6, 10], "S": [4, 12]}],
}
VEL = {"K": 1.0, "S": 0.9, "H": 0.32, "O": 0.28}


def drum_bars(n_bars, pattern="full", hats=True, drop_last_beat=False):
    step = BAR / 16
    swing = step * 0.17  # MPC-ish 58% swing on off 16ths
    out = np.zeros(int(n_bars * BAR * SR) + SR)
    for bar in range(n_bars):
        pat = PATTERNS[pattern][bar % 2]
        hits = [(s, k) for k, steps in pat.items() for s in steps]
        if hats:
            hits += [(s, "H") for s in range(0, 16, 2)]
            if bar % 4 == 3:
                hits.append((14, "O"))
        for s, k in hits:
            if drop_last_beat and bar == n_bars - 1 and s >= 12:
                continue
            t0 = bar * BAR + s * step + (swing if s % 2 else 0)
            v = VEL[k] * (0.45 if (k == "S" and s == 15) else 1.0)
            if k == "H":
                v *= 0.8 + 0.4 * rng.random()  # humanized hat velocity
            i = int(t0 * SR)
            smp = KIT[k] * v
            out[i:i + len(smp)] += smp
    return np.vstack([out, out])[:, :int(n_bars * BAR * SR)]


# ---------------------------------------------------------------- bass
def note_hz(name, octave=1):
    names = "C C# D D# E F F# G G# A A# B".split()
    return 440 * 2 ** ((names.index(name) + 12 * (octave + 1) - 69) / 12)


def bassline(roots, n_bars):
    """roots: list of note names, one per half bar (already transposed)."""
    half = BAR / 2
    out = np.zeros(int(n_bars * BAR * SR))
    for i in range(n_bars * 2):
        r = roots[i % len(roots)]
        f = note_hz(r, 1)
        if f > 75:
            f /= 2
        t = t_axis(half * 0.95)
        env = np.minimum(1, t / 0.01) * np.exp(-t * 1.2)
        tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)
        i0 = int(i * half * SR)
        seg = np.tanh(1.5 * tone * env) * 0.55
        out[i0:i0 + len(seg)] += seg[:len(out) - i0]
    return np.vstack([out, out])


# ---------------------------------------------------------------- main
def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)
    q = analyze(y.mean(0))
    ch = Chopper(y, q)
    print(f"source tempo ~{60 / np.median(np.diff(q)):.1f} BPM -> {BPM} BPM, +{SEMITONES} st")

    # ---- the pads (bar/beat indexes are relative to the record's first downbeat)
    pads = {
        "01_intro_4bar":        ch.bars(0, 4),     # Fmaj7 G7 | Dm7 F | Am C | Am   (0:00)
        "02_main_loop_4bar":    ch.bars(30, 4),    # instrumental break G7 C|C Am|Am F|F Dm  (1:35)
        "03_hook_loop_4bar":    ch.bars(26, 4),    # same changes with the vocal phrase  (1:22)
        "04_keychange_vamp_4bar": ch.bars(55, 4),  # after the half-step lift, vocal vamp (2:55)
    }
    loop = pads["02_main_loop_4bar"]
    hb = int(BAR / 2 * SR)
    chords = ["G7", "C", "C", "Am", "Am", "F", "F", "Dm"]
    for i in range(8):  # one pad per chord / half bar of the main loop
        pads[f"{5 + i:02d}_loop_chop_{chords[i]}->{transpose_chord(chords[i])}"] = loop[:, i * hb:(i + 1) * hb]
    pads["13_vox_stab_a"] = ch.beats(26 * 4 + 2, 1)   # strongest vocal beats
    pads["14_vox_stab_b"] = ch.beats(26 * 4 + 3, 1)
    pads["15_vox_stab_c"] = ch.beats(38 * 4, 1)
    pads["16_vox_phrase_2beat"] = ch.beats(26 * 4 + 2, 2)
    for name, x in pads.items():
        sf.write(os.path.join(out_dir, "kit", f"{name.replace('->', '_to_')}.wav"),
                 fades(x).T, SR, subtype="PCM_24")

    # ---- arrangement
    L = lambda bars: int(round(bars * BAR * SR))
    sections = []

    def section(name, sample, drums, bass=None, stabs=()):
        n = sample.shape[1]
        mix = sample.copy()
        if drums is not None:
            mix[:, :drums.shape[1]] += fit(drums, n)
        if bass is not None:
            mix += fit(bass, n) * 0.8
        for pos, stab, gain in stabs:
            i = int(pos * SR)
            j = min(n, i + stab.shape[1])
            mix[:, i:j] += stab[:, :j - i] * gain
        sections.append((name, mix))

    def loop_n(x, times):
        return np.concatenate([x] * times, axis=1)

    def hp_sample(x):  # make room for the kick/sub like the MPC days
        return biquad(biquad(x, "lowshelf", 120, gain_db=-6), "hp", 45)

    v_a, v_b, v_c = pads["13_vox_stab_a"], pads["14_vox_stab_b"], pads["15_vox_stab_c"]
    stutter_src = v_a[:, :int(BEAT / 2 * SR)]

    def stutter(at_bar_end, gain=0.55):
        # "you-you-you-you" 16th retrigger over the last beat of a bar
        s16 = int(BEAT / 4 * SR)
        return [(at_bar_end - BEAT + k * BEAT / 4, fades(stutter_src[:, :s16]), gain) for k in range(4)]

    roots_c = ["G", "C", "C", "A", "A", "F", "F", "D"]
    roots = [transpose_note(r) for r in roots_c]
    roots_lift = [transpose_note(r) for r in ["C#", "C#", "A#", "A#", "F#", "F#", "D#", "G#"]]

    # 1) Intro: filter opens up over 4 bars, vocal stab teaser on the last beat
    intro = sweep_lp(pads["01_intro_4bar"], 350, 18000) * 0.9
    section("intro", intro, None, stabs=[(4 * BAR - BEAT, v_c, 0.8)])

    # 2) Hook: chipmunk vocal loop + full drums, drop the drums' last beat
    hook = loop_n(pads["03_hook_loop_4bar"], 2)
    section("hook1", hp_sample(hook), drum_bars(8, drop_last_beat=True), bassline(roots, 8))

    # 3) Verse 1: instrumental break loop, stabs every 4 bars
    v1 = loop_n(loop, 4)
    stabs = []
    for b in (4, 8, 12):
        stabs.append(((b - 1) * BAR + 2 * BEAT, v_a, 0.6))
    stabs += stutter(16 * BAR)
    section("verse1", hp_sample(v1), drum_bars(16, drop_last_beat=True), bassline(roots, 16), stabs)

    # 4) Hook again
    section("hook2", hp_sample(hook), drum_bars(8, drop_last_beat=True), bassline(roots, 8))

    # 5) Verse 2: MPC re-chop. Each half bar (one chord) is cut into 8th notes
    #    and re-sequenced, so the harmony stays put but the groove gets flipped.
    e8 = int(BEAT / 2 * SR)
    orders = [[0, 1, 0, 3], [0, 1, 2, 2], [0, 0, 1, 3], [0, 3, 2, 3]]
    flipped = []
    for h in range(8):
        half = loop[:, h * hb:(h + 1) * hb]
        sl = [fades(half[:, k * e8:(k + 1) * e8], 0.002, 0.004) for k in range(4)]
        flipped += [sl[k] for k in orders[h % 4]]
    flip = np.concatenate(flipped, axis=1)
    flip = fit(flip, loop.shape[1])
    v2 = loop_n(flip, 4)
    stabs = [((b - 1) * BAR + 3 * BEAT, v_b, 0.6) for b in (2, 6, 10, 14)]
    stabs += stutter(8 * BAR) + stutter(16 * BAR)
    section("verse2", hp_sample(v2), drum_bars(16, "verse2", drop_last_beat=True),
            bassline(roots, 16), stabs)

    # 6) Final hook on the record's own key change (half-step lift, Eb -> E)
    lift = loop_n(pads["04_keychange_vamp_4bar"], 2)
    section("hook3_keychange", hp_sample(lift), drum_bars(8), bassline(roots_lift, 8))

    # 7) Outro: drums out, filter closes, tape stop on the last bar
    outro = loop_n(pads["04_keychange_vamp_4bar"], 1)
    outro = sweep_lp(outro, 16000, 500)
    stop_n = L(1)
    tail = outro[:, -stop_n:]
    pos = np.cumsum(np.linspace(1, 0.05, stop_n))  # slowing playhead
    pos = np.clip(pos, 0, stop_n - 1)
    outro[:, -stop_n:] = np.vstack([np.interp(pos, np.arange(stop_n), c) for c in tail])
    outro[:, -stop_n:] *= np.linspace(1, 0, stop_n) ** 0.5
    section("outro", outro, None)

    # ---- render
    full = np.concatenate([m for _, m in sections], axis=1)
    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write(f"{BPM:.0f} BPM, key Eb major (C +{SEMITONES} st); final hook lifts to E\n\n")
        for name, m in sections:
            bars = m.shape[1] / SR / BAR
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:16s} {bars:4.0f} bars\n")
            t += m.shape[1] / SR
    full = master(full)
    sf.write(os.path.join(out_dir, "beat_full.wav"), full.T, SR, subtype="PCM_24")
    print(f"rendered {full.shape[1] / SR:.1f}s")


def master(x):
    x = biquad(x, "hp", 25)
    x = biquad(x, "lp", 16500)  # a touch of vinyl dull-down
    crackle = np.zeros(x.shape[1])
    pops = rng.random(x.shape[1]) < 4 / SR
    crackle[pops] = rng.standard_normal(pops.sum()) * 0.15
    crackle = biquad(crackle, "hp", 2000) + biquad(rng.standard_normal(x.shape[1]), "bp", 4000, 0.5) * 0.002
    x = x + crackle
    x = x / np.max(np.abs(x)) * 1.4
    x = np.tanh(x)  # soft clip glue
    return x / np.max(np.abs(x)) * 0.89


def transpose_note(n, st=SEMITONES):
    names = "C C# D D# E F F# G G# A A# B".split()
    return names[(names.index(n) + st) % 12]  # sharps: note_hz expects these


def transpose_chord(c):
    root = c[:2] if len(c) > 1 and c[1] == "#" else c[0]
    flats = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
    t = transpose_note(root)
    return flats.get(t, t) + c[len(root):]


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
