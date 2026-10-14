"""
"CIRCUS MAXIMUS" redo: the record's own drums and 808, with a crafted sample on top.

Drums: Travis raps over every bar of the rage beat, so a plain harmonic/
percussive split would drag his consonants along. Instead the percussive layer
is masked to what *repeats*: the median of all 72 rage bars (per bar parity, so
2-bar patterns survive) models the drum pattern, and each real bar keeps only
the energy that model explains. Bars 64-79 (two full chord cycles) are used, so
fills and variation are the record's own. The 808 is the same bars' low band
(< 100 Hz), which already walks the cycle: Eb x4 | B x2 | Ab x2.

Sample, on the same cycle (all sources run Eb x4 | B x2 | Ab x2):
  body      outro strings (3:47, with their rising glide) + melodic layer (3:05),
            drumless and mono-corrected
  chop hook the melodic layer gated 3-3-2 on 8ths, with an octave-up copy
  swells    the next chord reversed into every chord change
  glue      ducked by the record's own kick, light tape saturation

Usage: python3 circus_redo.py <source audio> <out dir>
"""
import os
import subprocess
import sys
import tempfile

import librosa
import numpy as np
import soundfile as sf

from chop import SR, biquad, fades, fit, sweep_lp
from circus_flip import (BAR, DOWN, NB, STEP, drumless, master, mono_safe, riser,
                         room, sidechain, stutter_bar)

NF, HOP, PAD = 2048, 256, 2048
RAGE = range(8, 80)        # the rage beat: model bars for the drum pattern
DRUM_BARS = (64, 16)       # two cycles: Eb 64-67, B 68-69, Ab 70-71, Eb 72-75, B 76-77, Ab 78-79
STRINGS = (118, 8)
MELODIC = (96, 8)
CHANGES = (4, 6, 8)        # bars where the chord changes (B, Ab, back to Eb)


# ---------------------------------------------------------------- the record's drums
class Record:
    def __init__(self, y):
        self.y = y

    def seg(self, i, n=1, pad=0):
        a = int(round((DOWN + i * BAR) * SR))
        return self.y[:, a - pad:a + n * NB + pad]

    def _stft(self, x):
        return [librosa.stft(c, n_fft=NF, hop_length=HOP, center=False) for c in x]

    def _perc(self, Ds):
        M = (np.abs(Ds[0]) + np.abs(Ds[1])) / 2
        _, Pm = librosa.decompose.hpss(M, margin=2.0)
        return M, Pm

    def drums(self, first, n):
        models = {}
        for par in (0, 1):
            mags = [self._perc(self._stft(self.seg(i, pad=PAD)))[1] for i in RAGE if i % 2 == par]
            k = min(m.shape[1] for m in mags)
            models[par] = np.median(np.stack([m[:, :k] for m in mags]), 0)
        out = []
        for i in range(first, first + n):
            Ds = self._stft(self.seg(i, pad=PAD))
            M, Pm = self._perc(Ds)
            Mo = models[i % 2]
            k = min(Mo.shape[1], M.shape[1])
            mask = np.zeros_like(M)
            mask[:, :k] = np.clip(np.minimum(Mo[:, :k], Pm[:, :k]) / (M[:, :k] + 1e-9), 0, 1)
            out.append(np.stack([librosa.istft(D * mask, hop_length=HOP, center=False, length=NB + 2 * PAD)
                                 for D in Ds])[:, PAD:PAD + NB])
        return biquad(np.concatenate(out, 1), "hp", 90)  # sub belongs to the 808 stem

    def sub(self, first, n):
        x = self.seg(first, n)
        lo = biquad(biquad(biquad(biquad(x, "lp", 100), "lp", 100), "lp", 100), "lp", 100)
        return np.vstack([lo.mean(0)] * 2)  # mono sub


def kick_times(drums):
    """The rage beat's kick lands on every quarter (clap on top, 808 syncopated
    on 0-3-7-11-15). Keep the quarters where the stem actually has kick energy."""
    m = biquad(biquad(drums.mean(0), "lp", 200), "hp", 90)
    beat = BAR / 4
    n = int(round(drums.shape[1] / SR / beat))
    e = np.array([np.sqrt(np.mean(m[int(k * beat * SR):int((k * beat + 0.06) * SR)] ** 2)) for k in range(n)])
    return [k * beat for k in range(n) if e[k] > 0.5 * np.median(e)]


# ---------------------------------------------------------------- the sample
def rb_pitch(x, semitones):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        sf.write(a, x.T, SR, subtype="FLOAT")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a, "-af",
                        f"rubberband=pitch={2 ** (semitones / 12):.6f}", b], check=True)
        out, _ = sf.read(b, always_2d=True)
    return fit(out.T, x.shape[1])


def chop_hook(src, octave):
    """Gate the layer 3-3-2 on 8ths (per half bar), octave-up copy underneath."""
    n_bars = src.shape[1] // NB
    gate = np.zeros(src.shape[1])
    pattern = [(0, 3), (3, 3), (6, 2)]  # in 16ths, per half bar
    for h in range(n_bars * 2):
        for s, ln in pattern:
            i = int(round((h * 8 + s) * STEP * SR))
            n = int(round(ln * STEP * SR * 0.85))   # short tail: choppy
            env = np.ones(n)
            env[:int(0.003 * SR)] = np.linspace(0, 1, int(0.003 * SR))
            env[-int(0.03 * SR):] = np.linspace(1, 0, int(0.03 * SR))
            gate[i:i + n] = np.maximum(gate[i:i + n], env[:len(gate) - i])
    return src * gate + 0.4 * octave * gate


def swells(strings):
    """Reverse the first beat of each new chord into the change."""
    out = np.zeros_like(strings)
    beat = int(round(4 * STEP * SR))
    for b in CHANGES:
        src = strings[:, (b % 8) * NB:(b % 8) * NB + beat]
        rev = src[:, ::-1] * np.linspace(0, 1, beat) ** 2
        i = b * NB - beat
        out[:, i:i + beat] += rev[:, :out.shape[1] - i]
    return out


def tape(x, drive=1.4):
    return np.tanh(biquad(x, "lp", 13000) * drive) / drive


# ---------------------------------------------------------------- main
def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)
    rec = Record(y)

    drums = rec.drums(*DRUM_BARS)           # 16 bars
    sub = rec.sub(*DRUM_BARS)
    kicks = kick_times(drums)
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    drums = drums / rms(drums) * 0.12
    sub = sub / rms(sub) * 0.10

    strings = drumless(rec.seg(*STRINGS))
    melodic = drumless(rec.seg(*MELODIC))
    body = mono_safe(tape(strings + 0.7 * melodic))
    body = body / rms(body) * 0.08
    octave = rb_pitch(melodic, 12)
    hook = mono_safe(tape(chop_hook(melodic, octave)))
    hook = hook / rms(hook) * 0.06
    sw = swells(strings)
    sw = sw / (rms(sw) + 1e-9) * 0.03
    sample8 = body + sw                      # 8-bar sample loop
    rep = lambda x, k: np.concatenate([x] * k, axis=1)

    def beat(n_bars, sample, with_drums=True, hats_only=False):
        s = rep(sample, n_bars // 8 + 1)[:, :n_bars * NB]
        if not with_drums:
            return s
        d = rep(drums, n_bars // 16 + 1)[:, :n_bars * NB]
        b = rep(sub, n_bars // 16 + 1)[:, :n_bars * NB]
        hits = [t + k * 16 * BAR for k in range(n_bars // 16 + 1) for t in kicks if t + k * 16 * BAR < n_bars * BAR]
        if hats_only:
            return s + biquad(biquad(d, "hp", 6000), "hp", 6000) * 1.5
        return sidechain(s, hits, depth=0.35, release=0.11) + d + b

    secs = []
    # 1) intro: the sample alone, filter opens; hats tease + riser in the last 2 bars
    intro = sweep_lp(beat(8, sample8, with_drums=False), 300, 16000)
    tease = beat(8, np.zeros_like(sample8), hats_only=True)
    intro[:, 6 * NB:] += tease[:, 6 * NB:] + riser(2)
    secs.append(("intro: sample, filter opens, hats tease", intro))
    # 2) hook: drums + 808 + body + chop hook
    secs.append(("hook: the record's drums + 808, sample + chop hook", beat(16, sample8 + hook)))
    # 3) verse: drums + 808 + body only, darker (room for vocals)
    secs.append(("verse: drums + 808, sample darker", beat(16, sweep_lp(sample8, 6000, 6000))))
    # 4) break: chop hook stutter, no drums, riser
    pats = [[(0, 0, 3), (3, 0, 3), (6, 0, 2), (8, 8, 3), (11, 8, 3), (14, 8, 2)]] * 3 + [[(k, 0, 1) for k in range(16)]]
    hk = sample8 + hook
    br = np.concatenate([stutter_bar(hk[:, k * NB:], p) for k, p in enumerate(pats)], axis=1)
    br[:, 2 * NB:] += riser(2)
    secs.append(("break: chop stutter, riser", sweep_lp(br, 14000, 2000)))
    # 5) hook again
    secs.append(("hook", beat(16, sample8 + hook)))
    # 6) outro: sample, tape stop
    out = sweep_lp(sample8[:, :4 * NB].copy(), 16000, 600)
    last = out[:, -NB:]
    pos = np.clip(np.cumsum(np.linspace(1, 0, NB) ** 0.7), 0, NB - 1)
    out[:, -NB:] = np.vstack([np.interp(pos, np.arange(NB), c) for c in last]) * np.linspace(1, 0, NB) ** 0.5
    secs.append(("outro: sample, tape stop", out))

    ref = rms(secs[1][1])
    trims = {0: -3.0, 2: -1.0, 3: -3.0, 5: -3.5}
    secs = [(nm, x * ref / rms(x) * 10 ** (trims.get(k, 0) / 20)) for k, (nm, x) in enumerate(secs)]
    full = master(room(np.concatenate([x for _, x in secs], axis=1), wet=0.04))
    sf.write(os.path.join(out_dir, "circus_maximus_redo.wav"), full.T, SR, subtype="PCM_24")

    kit = {"01_drums_16bar_record": drums, "02_808_16bar_record": sub,
           "03_sample_8bar": sample8, "04_chop_hook_8bar": hook,
           "05_sample_plus_hook_8bar": sample8 + hook}
    for name, x in kit.items():
        sf.write(os.path.join(out_dir, "kit", f"{name}.wav"), (x / np.max(np.abs(x)) * 0.89).T, SR, subtype="PCM_24")

    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write("125 BPM, Eb minor. Cycle: Eb x4 | B x2 | Ab x2. Drums + 808 are the record's own.\n\n")
        for name, x in secs:
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:52s} {x.shape[1] / NB:.0f} bars\n")
            t += x.shape[1] / SR
    print(f"rendered {full.shape[1] / SR:.1f}s, {len(kicks)} kicks detected in 16 bars")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
