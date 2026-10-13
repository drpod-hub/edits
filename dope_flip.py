"""
Stem-separated flip of "Dope Man" - N.W.A.

The record is an 88.235 BPM drum machine (bar = 2.720 s) whose beat repeats
bar for bar. That makes REPET-style separation possible: the median of many
bars rebuilds the beat alone, and what changes from bar to bar is the
foreground. So instead of chopping the full mix, this pulls out:

  lead    the synth hook (0:17-0:44), cleaned with a harmonic/percussive split
  vocals  the chorus shouts, best take of each from the three choruses
  beat    the instrumental outro (5:37-6:15), plain drum machine

and rebuilds a West Coast flip, varispeeded down to exactly 79 BPM (-1.9 st,
Bb minor -> Ab minor area):

  intro      the lead alone, tape delay, filter opening
  hook       the original hook, slowed, with shouts answering the lead
  chorus     outro drums + re-sequenced vocal shouts + lead stabs
  breakdown  kick only, reversed lead swell, delayed shout
  hook       again, shouts in call and response
  outro      the lead alone into a tape stop

Usage: python3 dope_flip.py <source audio> <out dir>
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy import signal
from scipy.signal import fftconvolve

from chop import SR, biquad, fades, sweep_lp, varispeed

rng = np.random.default_rng(9)

BAR = 2.720            # measured: snare fold over the whole song, 88.235 BPM
DOWN = 0.446           # first downbeat (snare backbeat phase - one beat)
TARGET_BPM = 79.0
RATIO = TARGET_BPM / (240 / BAR)  # 0.895 varispeed

HOOK = list(range(6, 16))         # 0:17-0:44, repeats at bars 76-83
HOOK_REPEAT = list(range(76, 84))
OUTRO = list(range(124, 137))     # 5:37-6:15, instrumental, 98% identical bars
VERSE = list(range(16, 39)) + list(range(56, 71))
CHORUS_STARTS = (39, 71, 115)     # 4-bar choruses; bars 40-41 repeat 3 times
# Shouts: (position in bars from chorus start, length s, best take 0-2).
# Takes chosen by voice-to-bleed ratio; the three choruses are separate takes.
SHOUTS = {"A": (1.74, 0.95, 2), "B": (0.86, 0.50, 0), "C": (0.33, 0.70, 2), "D": (2.85, 0.55, 1)}

NF, HOP, PAD = 4096, 512, 4096


# ---------------------------------------------------------------- separation
class Repet:
    def __init__(self, y):
        self.y = y
        self.n = int(round(BAR * SR))

    def start(self, i):
        return int(round((DOWN + i * BAR) * SR))

    def stft(self, i):
        a = self.start(i) - PAD
        seg = self.y[:, a:a + self.n + 2 * PAD]
        return np.stack([librosa.stft(c, n_fft=NF, hop_length=HOP, center=False) for c in seg])

    def split(self, region, model):
        """Foreground (what changes) and background (the repeating beat) of
        the bars in `region`, with the beat modeled as the median of `model`."""
        M = np.median(np.stack([np.abs(self.stft(i)).mean(0) for i in model]), axis=0)
        fg, bg = [], []
        for i in region:
            X = self.stft(i)
            V = np.abs(X).mean(0) + 1e-9
            W = np.minimum(M, V)
            mask = W ** 2 / (W ** 2 + np.maximum(V - W, 0) ** 2 + 1e-12)
            for out, m in ((fg, 1 - mask), (bg, mask)):
                out.append(np.stack([
                    librosa.istft(X[c] * m, hop_length=HOP, center=False, length=self.n + 2 * PAD)
                    for c in range(2)])[:, PAD:PAD + self.n])
        return np.concatenate(fg, 1), np.concatenate(bg, 1)

    def bars(self, first, count):
        a = self.start(first)
        return self.y[:, a:a + count * self.n]


def clean_lead(x):
    out = []
    for c in x:
        H, _ = librosa.decompose.hpss(librosa.stft(c, n_fft=NF, hop_length=HOP), margin=(1.0, 2.0))
        out.append(librosa.istft(H, hop_length=HOP, length=len(c)))
    return biquad(biquad(np.array(out), "hp", 380), "lp", 9000)


# ---------------------------------------------------------------- fx
def tape_delay(x, time, feedback=0.38, mix=0.35, lp=3500):
    d = int(round(time * SR))
    out = x.copy()
    tap = x.copy()
    for _ in range(6):
        tap = biquad(np.pad(tap, ((0, 0), (d, 0)))[:, :x.shape[1]], "lp", lp) * feedback
        out += tap * mix / feedback
    return out


def room(x, wet=0.1, sec=1.2):
    t = np.arange(int(sec * SR)) / SR
    ir = biquad(rng.standard_normal((2, len(t))) * np.exp(-t * 4), "lp", 6000)
    tail = np.stack([fftconvolve(x[c], ir[c])[:x.shape[1]] for c in range(2)])
    return x + wet * tail / (np.max(np.abs(tail)) + 1e-9) * np.max(np.abs(x))


def place(dst, x, at):
    i = int(round(at * SR))
    if i >= dst.shape[1]:
        return
    j = min(dst.shape[1], i + x.shape[1])
    dst[:, i:j] += x[:, :j - i]


def finish(x):
    x = biquad(biquad(x, "hp", 28), "lp", 16000)
    x = np.tanh(x / np.max(np.abs(x)) * 1.25)
    return x / np.max(np.abs(x)) * 0.89


# ---------------------------------------------------------------- main
def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)
    r = Repet(y)
    n = r.n
    beat = BAR / 4

    lead_fg, _ = r.split(HOOK, HOOK + HOOK_REPEAT + OUTRO)
    lead = clean_lead(lead_fg)                     # bars 6-15
    vox_fg, _ = r.split([s + k for s in CHORUS_STARTS for k in range(4)], VERSE + OUTRO)
    vox_fg = biquad(vox_fg, "hp", 150)
    shouts = {}
    for name, (pos, dur, take) in SHOUTS.items():
        a = int(round((take * 4 * BAR + pos * BAR - 0.03) * SR))
        shouts[name] = fades(vox_fg[:, a:a + int((dur + 0.06) * SR)], 0.004, 0.05)
    drums = r.bars(OUTRO[1], 4)                    # 4 real bars of the outro beat
    hook = r.bars(7, 8)                            # the original hook, full mix
    lead8 = lead[:, n:9 * n]                       # bars 7-14, separated

    # ---- arrange on the record's own grid; varispeed the whole thing at the end
    L = lambda bars: int(round(bars * n))
    sections = []

    # 1) intro: the lead alone, delay + filter opening
    intro = tape_delay(lead8[:, :L(4)], 0.75 * beat)
    sections.append(("intro: the lead alone, tape delay", sweep_lp(intro, 400, 14000)))

    # 2) hook with shouts answering the lead at the end of each 4 bars
    h = hook.copy()
    for b in (3, 7):
        place(h, shouts["A"] * 1.1, b * BAR + 2 * beat)
    sections.append(("hook (original, slowed) + shouts", h))

    # 3) chorus flip: outro drums, re-sequenced shouts, lead stabs on the &s
    ch = np.concatenate([drums, drums], axis=1).copy()
    stab = fades(lead8[:, int(0.15 * n):int(0.15 * n) + int(beat / 2 * SR)], 0.003, 0.03)
    for k in range(2):
        o = k * 4 * BAR
        place(ch, shouts["C"], o + 0 * BAR + 1 * beat)
        place(ch, shouts["B"], o + 0 * BAR + 3 * beat)
        place(ch, shouts["A"], o + 1 * BAR + 1 * beat)
        place(ch, shouts["D"], o + 2 * BAR + 1 * beat)
        for s in range(4):  # stutter B: 16th retriggers into the next bar
            place(ch, fades(shouts["B"][:, :int(beat / 4 * SR)]), o + 3 * BAR + 2 * beat + s * beat / 4)
        place(ch, shouts["B"], o + 3 * BAR + 3 * beat)
        for b in range(4):
            for e in (1, 3):
                place(ch, stab * 0.7, o + b * BAR + e * beat + beat / 2)
    sections.append(("chorus flip: drums + shout chops + lead stabs", ch))

    # 4) breakdown: kick only (lowpassed drums), reversed lead swell, delayed shout
    bd = biquad(biquad(drums, "lp", 160), "lp", 160)
    rev = lead8[:, :L(2)][:, ::-1] * np.linspace(0.1, 1, L(2)) ** 2
    place(bd, rev, 2 * BAR)
    place(bd, tape_delay(np.pad(shouts["A"], ((0, 0), (0, L(2)))), 0.75 * beat, 0.5, 0.6), 0)
    sections.append(("breakdown: kick, reversed lead, delayed shout", bd))

    # 5) hook again, call and response
    h2 = hook.copy()
    for b in range(8):
        place(h2, shouts["CBAD"[b % 4]] * 0.9, b * BAR + (3 if b % 2 else 1) * beat)
    sections.append(("hook + shouts call and response", h2))

    # 6) outro: lead alone, tape stop on the last bar
    out = tape_delay(lead8[:, L(4):L(8)], 0.75 * beat, 0.45, 0.4)
    last = out[:, -n:]
    pos = np.clip(np.cumsum(np.linspace(1, 0, n) ** 0.7), 0, n - 1)
    out[:, -n:] = np.vstack([np.interp(pos, np.arange(n), c) for c in last]) * np.linspace(1, 0, n) ** 0.5
    sections.append(("outro: the lead alone, tape stop", sweep_lp(out, 14000, 600)))

    # level-match: sections relative to the hook (dB); solo lead and the
    # breakdown sit a little under so the drops still land
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    ref = rms(sections[1][1])
    trims = {0: -3.0, 3: -2.0, 5: -3.0}
    sections = [(name, x * (ref / rms(x)) * 10 ** (trims.get(k, 0.0) / 20))
                for k, (name, x) in enumerate(sections)]
    full = np.concatenate([s for _, s in sections], axis=1)
    full = finish(room(varispeed(full, RATIO)))
    sf.write(os.path.join(out_dir, "dope_man_flip.wav"), full.T, SR, subtype="PCM_24")

    # ---- kit, all at 79 BPM
    kit = {"01_lead_hook_8bar_separated": lead8, "02_hook_8bar_full": hook,
           "03_drums_4bar_outro": drums}
    for k, (name, x) in enumerate(shouts.items(), 4):
        kit[f"0{k}_shout_{name}"] = x
    for name, x in kit.items():
        sf.write(os.path.join(out_dir, "kit", f"{name}.wav"), fades(varispeed(x, RATIO)).T, SR, subtype="PCM_24")

    bar_out = BAR / RATIO
    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write(f"{TARGET_BPM:.0f} BPM (record: {240 / BAR:.3f} BPM, varispeed x{RATIO:.4f})\n\n")
        for name, s in sections:
            bars = s.shape[1] / n
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:48s} {bars:.0f} bars\n")
            t += bars * bar_out
    print(f"rendered {full.shape[1] / SR:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
