"""
Trap beat from "Way Too Long" - Delicate Steve.

The record sits on an exact 120 BPM grid (bar = 2.000 s), tuned -4 cents.
It is varispeeded x1.125 (+2.04 st) to exactly 135 BPM, which also puts it
back in tune with A440 (F major / D minor -> G major / E minor). One bar
becomes exactly 78,400 samples, so every chop stays sample-locked to the grid.

  intro    the outro's sparse slide-guitar melody (2:12), filter opening
  hook     4-bar bridge loop (1:18): Bb F | F C | C7 | Bb Gm -> C G | G D | D7 | C Am
  verse    the gated riff (0:20): 8 bars, the most seamless loop in the song
  break    MPC stutter of the riff + riser

The record has no separate drum kit (its "drums" are the gated strum
attacks), so the sample stays raw; it is only high-passed so the 808 owns the
sub, and mid/side corrected for mono. On top: 808s that follow the record's
own bassline, punch kick, clap on 3, and trap hats with 1/16 bursts, 1/32
rolls, triplet rolls and pitch-rising rolls.

Usage: python3 waytoolong_trap.py <source audio> <out dir>
"""
import os
import sys

import librosa
import numpy as np
import soundfile as sf

from chop import SR, biquad, fades, sweep_lp, varispeed
from circus_flip import bass808, clap, crash, hat, kick, limiter, mono_place, mono_safe, room, sidechain

rng = np.random.default_rng(135)

SRC_BAR = 2.000       # measured: onset fold, exactly 120 BPM
DOWN = 1.87           # first downbeat (harmonic-change phase)
RATIO = 1.125         # -> 135 BPM, +2.04 st
BPM = 120 * RATIO
BAR = SRC_BAR / RATIO
STEP = BAR / 16
NB = int(round(BAR * SR))  # 78,400 samples

HOOK = (39, 4)        # bridge, 1:18
RIFF = (9, 8)         # gated riff, 0:20 (restart matches: chroma sim 1.00)
LEAD = (66, 8)        # outro slide melody, 2:12

# 808 roots per half bar, after the +2 lift, from the record's own bassline
NOTE = {n: librosa.note_to_hz(n) for n in ("E1", "G1", "A1", "C2", "D2", "G2")}
HOOK_ROOTS = ["C2", "G1", "G1", "D2", "D2", "D2", "C2", "A1"]  # bar 3 is D7 throughout
RIFF_ROOTS = ["G1"] * 10 + ["E1", "E1"] + ["G1"] * 4

KIT = {"K": kick(), "C": clap(), "H": hat(), "O": hat(True), "X": crash()}


def pitched_hat(semitones):
    return varispeed(KIT["H"][None], 2 ** (semitones / 12))[0]


def drums(n_bars, roots, style="hook"):
    """Trap pattern. Returns drums, the 808 line and the 808/kick hit times."""
    d = np.zeros((2, n_bars * NB + SR))
    b = np.zeros((2, n_bars * NB + SR))
    hits = []
    kicks = {"hook": [[0, 7, 10], [0, 3, 11, 14]],
             "verse": [[0, 10], [0, 6, 11]],
             "final": [[0, 7, 10, 13], [0, 3, 6, 11, 14]]}[style]
    for bar in range(n_bars):
        o = bar * BAR
        ks = kicks[bar % 2]
        for k, s in enumerate(ks):
            half = s // 8
            r = roots[(2 * bar + half) % len(roots)]
            end = ks[k + 1] if k + 1 < len(ks) else 16
            length = (end - s) * STEP + 0.01
            nxt = roots[(2 * bar + (end // 8)) % len(roots)] if end < 16 else roots[(2 * bar + 2) % len(roots)]
            f0 = NOTE[r]
            if NOTE[nxt] != f0 and k == len(ks) - 1:     # late slide into the next root
                x = bass808(f0, length, NOTE[nxt], glide=0.12, glide_at=max(0.0, length - 0.14))
            elif style != "verse" and s in (3, 13):     # octave flick down
                x = bass808(f0 * 2, length, f0, glide=0.06)
            else:
                x = bass808(f0, length)
            i = int(round((o + s * STEP) * SR))
            b[:, i:i + x.shape[1]] = x[:, :b.shape[1] - i]  # choke
            mono_place(d, KIT["K"], o + s * STEP, 0.85)
            hits.append(o + s * STEP)
        mono_place(d, KIT["C"], o + 8 * STEP, 1.0)
        if style == "final" and bar % 4 == 3:
            mono_place(d, KIT["C"], o + 15 * STEP, 0.45)
        # hats
        phrase_end = bar % 4 == 3
        for s in range(0, 16, 2):
            if phrase_end and s >= 12:
                continue
            mono_place(d, KIT["H"], o + s * STEP, 0.5 + 0.3 * rng.random(), pan=-0.12)
        if style != "verse" or bar % 2:
            for s in (5, 13) if bar % 2 else (7,):      # 1/16 bursts
                mono_place(d, KIT["H"], o + s * STEP, 0.4, pan=0.12)
        if bar % 4 == 1:                                # 1/16-triplet roll
            for r in range(3):
                mono_place(d, KIT["H"], o + 10 * STEP + r * (2 * STEP / 3), 0.55, pan=0.15)
        if phrase_end:
            if style == "final" or bar % 8 == 7:        # pitch-rising 1/32 roll
                for r in range(8):
                    mono_place(d, pitched_hat(r), o + 12 * STEP + r * STEP / 2, 0.3 + 0.05 * r, pan=0.15)
            else:                                       # straight 1/32 roll
                for r in range(8):
                    mono_place(d, KIT["H"], o + 12 * STEP + r * STEP / 2, 0.3 + 0.05 * r, pan=0.15)
        if style != "verse" and bar % 2 == 0:
            mono_place(d, KIT["O"], o + 14 * STEP, 0.5, pan=0.2)
    n = n_bars * NB
    return d[:, :n], b[:, :n], hits


def riser(n_bars):
    n = n_bars * NB
    t = np.arange(n) / n
    common = rng.standard_normal(n)
    noise = np.vstack([common + 0.3 * rng.standard_normal(n), common + 0.3 * rng.standard_normal(n)])
    out = np.zeros((2, n))
    edges = np.linspace(0, n, 49).astype(int)
    for k in range(48):
        out[:, edges[k]:edges[k + 1]] = biquad(noise[:, edges[k]:edges[k + 1]], "bp", 300 * 30 ** (k / 47), 1.5)
    return out * t ** 2.2 * 0.45


def stutter_bar(src, pattern):
    out = np.zeros((2, NB))
    for s, frm, ln in pattern:
        a = int(round(frm * STEP * SR))
        x = fades(src[:, a:a + int(round(ln * STEP * SR))], 0.002, 0.01)
        i = int(round(s * STEP * SR))
        out[:, i:i + x.shape[1]] += x[:, :NB - i]
    return out


def seam(x, ms=25):
    """Short crossfade of the loop's tail into its own head (clean restart)."""
    n = int(ms / 1000 * SR)
    x = x.copy()
    x[:, -n:] = x[:, -n:] * np.linspace(1, 0, n) + x[:, :n] * np.linspace(0, 1, n)
    return x


def master(x, loudness_db=-11.0):
    x = biquad(x, "hp", 25)
    x = x / np.sqrt(np.mean(x ** 2)) * 10 ** (loudness_db / 20)
    return limiter(np.tanh(x * 1.1) / 1.1)


def main(src, out_dir):
    os.makedirs(os.path.join(out_dir, "kit"), exist_ok=True)
    y, _ = librosa.load(src, sr=SR, mono=False)

    def layer(first, n, hp=True):
        a = int(round((DOWN + first * SRC_BAR) * SR))
        x = varispeed(y[:, a:a + int(round(n * SRC_BAR * SR))], RATIO)
        x = np.pad(x, ((0, 0), (0, max(0, n * NB - x.shape[1]))))[:, :n * NB]
        if hp:
            x = biquad(biquad(x, "hp", 110), "hp", 110)  # the 808 owns the sub
        return mono_safe(x)

    hook = seam(layer(*HOOK))
    riff = seam(layer(*RIFF))
    lead = layer(*LEAD, hp=False)
    rep = lambda x, k: np.concatenate([x] * k, axis=1)

    secs = []

    def section(name, smp, style=None, roots=None, extra=None):
        mix = smp.copy()
        if style:
            d, b, hits = drums(smp.shape[1] // NB, roots, style)
            mix = sidechain(mix, hits, depth=0.5) + d * 0.9 + b
        if extra is not None:
            mix = mix + extra[:, :mix.shape[1]]
        secs.append((name, mix))

    # 1) intro: the slide-guitar melody alone, filter opens, riser into the hook
    r = np.zeros_like(lead)
    r[:, -2 * NB:] = riser(2)
    section("intro: slide-guitar melody, filter opens", sweep_lp(lead, 400, 16000), extra=r)

    # 2) hook
    imp = np.zeros((2, 8 * NB))
    mono_place(imp, KIT["X"], 0, 1.0)
    section("hook: bridge loop + trap drums + 808", rep(hook, 2), "hook", HOOK_ROOTS, imp)

    # 3) verse: the gated riff
    section("verse: gated riff, lighter drums", rep(riff, 2), "verse", RIFF_ROOTS)

    # 4) hook
    section("hook", rep(hook, 2), "hook", HOOK_ROOTS, imp)

    # 5) break: MPC stutter of the riff, riser
    pats = [
        [(0, 0, 3), (3, 0, 3), (6, 0, 2), (8, 8, 3), (11, 8, 3), (14, 8, 2)],
        [(0, 0, 2), (2, 0, 2), (4, 0, 4), (8, 0, 2), (10, 0, 2), (12, 0, 1), (13, 0, 1), (14, 0, 1), (15, 0, 1)],
        [(0, 0, 3), (3, 0, 3), (6, 0, 2), (8, 8, 3), (11, 8, 3), (14, 8, 2)],
        [(k, 0, 1) for k in range(16)],
    ]
    bd = np.concatenate([stutter_bar(riff[:, k * NB:], p) for k, p in enumerate(pats)], axis=1)
    r = np.zeros_like(bd)
    r[:, -2 * NB:] = riser(2)
    section("break: MPC stutter, riser", sweep_lp(bd, 12000, 1500), extra=r)

    # 6) final hook: busiest drums, pitch-rising rolls every phrase
    section("final hook: busiest drums", rep(hook, 2), "final", HOOK_ROOTS, imp)

    # 7) outro: melody's last bars, filter closes, tape stop
    out = sweep_lp(lead[:, 4 * NB:].copy(), 16000, 500)
    last = out[:, -NB:]
    pos = np.clip(np.cumsum(np.linspace(1, 0, NB) ** 0.7), 0, NB - 1)
    out[:, -NB:] = np.vstack([np.interp(pos, np.arange(NB), c) for c in last]) * np.linspace(1, 0, NB) ** 0.5
    section("outro: melody, filter closes, tape stop", out)

    rms = lambda x: np.sqrt(np.mean(x ** 2))
    ref = rms(secs[1][1])
    trims = {0: -3.0, 2: -1.0, 4: -2.5, 5: 0.5, 6: -3.0}
    secs = [(nm, x * ref / rms(x) * 10 ** (trims.get(k, 0) / 20)) for k, (nm, x) in enumerate(secs)]
    full = master(room(np.concatenate([x for _, x in secs], axis=1), wet=0.05))
    sf.write(os.path.join(out_dir, "way_too_long_trap.wav"), full.T, SR, subtype="PCM_24")

    kit = {"01_hook_loop_4bar": hook, "02_riff_loop_8bar": riff, "03_melody_8bar": lead}
    d, b, _ = drums(8, HOOK_ROOTS, "hook")
    kit["04_drums_8bar"] = d * 0.9
    kit["05_808_hook_8bar"] = b
    for name, x in kit.items():
        sf.write(os.path.join(out_dir, "kit", f"{name}.wav"), x.T, SR, subtype="PCM_24")

    t = 0.0
    with open(os.path.join(out_dir, "arrangement.txt"), "w") as f:
        f.write(f"{BPM:.0f} BPM, G major / E minor (record +2 st). Hook: C G | G D | D7 | C Am\n\n")
        for name, x in secs:
            f.write(f"{int(t // 60)}:{t % 60:05.2f}  {name:42s} {x.shape[1] / NB:.0f} bars\n")
            t += x.shape[1] / SR
    print(f"rendered {full.shape[1] / SR:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
