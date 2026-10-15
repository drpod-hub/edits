#!/usr/bin/env python3
"""Stickman version of the Funky Drummer explainer (1080x1920).

Ink stick figures on graph paper. The floor the drummer sits on is the song's
real waveform, scrolling under a playhead. The story is acted out literally:
the band drops out through trapdoors in the waveform, a giant mouse cursor
drag-selects the drummer, Ctrl+C / Ctrl+V pastes copies of him, an era of
rappers is built on a pyramid of drummer copies, the screen fills with 1,000
tiny drummers, he gets a $0.00 cheque, and in the end the cursor
turns the original into an outline while his copies keep playing.

Uses the same script/voice config and audio engine as make_explainer.py.

Usage:  python3 make_stickman.py [explainer_funky_drummer.json]
        STILLS=1.5,12,25 python3 make_stickman.py   # PNG stills only
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
import skia

from make_explainer import (
    BPM, H, INK, RED, ROOT, SR, STEP, W, WHITE, back_out, build_music, build_timeline, camera_at, catmull,
    clamp, col, draw_captions, draw_ig_glyph, draw_outro, draw_text, draw_watermark, drum_events, drum_state,
    ease_out, font, hash01, hit_env, ik, lerp, music_sections, p_poly, p_rrect, paint, path_of, set_events,
    smooth, text_w, trimmed, window, write_wav,
)

PAPER = "#f5f1e8"
PAPER_DK = "#ebe5d8"
GRID = "#d9dde3"
BLUE = "#3d7be0"
GROUND = 1300            # world y of the waveform floor
SCROLL = 450             # waveform pixels per second
INK_W = 13               # body stroke width


def V(x, y):
    return np.array([x, y], float)


class Ink:
    """Stroke style shared by a whole figure (solid ink, or a dashed ghost)."""

    def __init__(self, color=INK, alpha=1.0, dashed=False, t=0.0):
        self.color, self.alpha = color, alpha
        self.effect = skia.DashPathEffect.Make([18, 12], -t * 30) if dashed else None
        self.dashed = dashed

    def line(self, c, pts, w, color=None):
        c.drawPath(path_of([tuple(p) for p in pts]),
                   paint(color or self.color, self.alpha, stroke=w, effect=self.effect))

    def disc(self, c, x, y, r, color=None):
        if self.dashed:
            c.drawCircle(x, y, r, paint(color or self.color, self.alpha, stroke=6, effect=self.effect))
        else:
            c.drawCircle(x, y, r, paint(color or self.color, self.alpha))

    def oval(self, c, cx, cy, rx, ry, w=7, fill=PAPER):
        r = skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry)
        if fill:
            c.drawOval(r, paint(fill, self.alpha))
        c.drawOval(r, paint(self.color, self.alpha, stroke=w, effect=self.effect))


# --------------------------------------------------------------------------
# rig

def make_pose(hip, lh, rh, lf, rf, spine=150, lean=0.0, head_r=36, head_drop=0.0,
              arms=(92, 92), legs=(100, 100)):
    hip = V(*hip)
    a = math.radians(lean)
    d = V(math.sin(a), -math.cos(a))
    neck = hip + d * spine
    head = neck + d * (head_r + 8) + V(0, head_drop)
    lh, rh, lf, rf = V(*lh), V(*rh), V(*lf), V(*rf)
    return {
        "hip": hip, "neck": neck, "head": head, "hr": head_r,
        "le": ik(neck, lh, *arms, -1), "lh": lh, "re": ik(neck, rh, *arms, 1), "rh": rh,
        "lk": ik(hip, lf, *legs, 1), "lf": lf, "rk": ik(hip, rf, *legs, -1), "rf": rf,
    }


def draw_body(c, j, ink, w=INK_W, legs=True, arms=True, head=True):
    if legs:
        ink.line(c, [j["hip"], j["lk"], j["lf"]], w)
        ink.line(c, [j["hip"], j["rk"], j["rf"]], w)
    ink.line(c, [j["neck"], j["hip"]], w)
    if arms:
        ink.line(c, [j["neck"], j["le"], j["lh"]], w)
        ink.line(c, [j["neck"], j["re"], j["rh"]], w)
    if head:
        ink.disc(c, j["head"][0], j["head"][1], j["hr"])


def lerp_pose(a, b, k):
    return {key: (a[key] * (1 - k) + b[key] * k) for key in a}


def stick_tip(hand, target, length=125):
    d = V(*target) - hand
    return hand + d / (np.linalg.norm(d) + 1e-9) * length


# --------------------------------------------------------------------------
# the drummer (local coords: ground centre of the kit at 0,0)

SNARE = V(-150, -222)
HAT = V(150, -270)


def drummer_joints(t, playing, mood):
    hat_h = sn_h = 0.0
    bob = sway = kick = 0.0
    if playing:
        hat_h = drum_state(t, ("hat",))
        sn_h = drum_state(t, ("snare",))
        bob = 10 * hit_env(t, ("kick", "snare"), 8)
        sway = 4 * math.sin(2 * math.pi * t * BPM / 60 / 2)
        kick = hit_env(t, ("kick",), 14)
    wild = 1.45 if mood == "solo" else 1.0
    lh = (-80, -275 - 95 * sn_h * wild)
    rh = (82, -322 - 95 * hat_h * wild)
    spine, head_drop, lean = 150 - bob * 0.4, 0.0, sway * 0.7
    sticks = "play"
    if mood == "solo":
        head_drop = 8 * math.sin(t * 2 * math.pi * BPM / 60)
    if mood in ("idle", "hold"):
        lh, rh, lean, sticks = (-92, -238), (95, -246), 0, "rest"
        if mood == "hold":
            rh = (70, -350)
    if mood == "sad":
        lh, rh, spine, head_drop, lean, sticks = (-62, -196), (64, -196), 128, 26, 0, "drop"
    j = make_pose((0, -175 + bob * 0.3), lh, rh, (-82, 0), (80, -8 * kick), spine=spine, lean=lean,
                  head_drop=head_drop)
    if sticks == "play":
        j["ls"], j["rs"] = stick_tip(j["lh"], SNARE), stick_tip(j["rh"], HAT)
    elif sticks == "rest":
        j["ls"], j["rs"] = j["lh"] + V(-40, 110), j["rh"] + V(40, 110)
    else:
        j["ls"], j["rs"] = j["lh"] + V(-10, 125), j["rh"] + V(10, 125)
    j["hat_h"], j["kick"] = V(hat_h, 0), V(kick, 0)
    return j


def draw_kit_back(c, t, ink, playing):
    crash = 0.0
    if playing:
        dt = (t / STEP) % 16 * STEP
        crash = 8 * math.exp(-dt * 5) * math.sin(dt * 26)
    ink.line(c, [(-215, -372), (-215, 0)], 6)
    ink.line(c, [(-255, 0), (-215, -45), (-175, 0)], 6)
    c.save()
    c.translate(-215, -385)
    c.rotate(-16 + crash)
    ink.oval(c, 0, 0, 74, 12, w=7, fill=GOLD_FILL)
    c.restore()


GOLD_FILL = "#f2d27a"
SAMPLING = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kNone)


def draw_drummer(c, t, playing, mood, ink=None, trail=0, headband=True):
    ink = ink or Ink()
    j = drummer_joints(t, playing, mood)
    draw_kit_back(c, t, ink, playing)
    # legs behind the bass drum
    draw_body(c, j, ink, arms=False, head=False)
    # bass drum
    kick = j["kick"][0]
    ink.oval(c, 0, -92, 92, 92, w=8)
    ink.oval(c, 0, -92, 72, 72, w=3, fill=None)
    if not ink.dashed:
        c.drawCircle(0, -92, 26, paint(RED, ink.alpha))
        draw_text(c, "1970", 0, -84, font("ExtraBold", 17), PAPER, a=ink.alpha, align="center")
    if kick > 0.03:
        for k in range(2):
            rr = 92 + (60 + 50 * k) * (1 - kick)
            c.drawCircle(0, -92, rr, paint(ink.color, 0.5 * kick * ink.alpha, stroke=4))
    # rack tom
    ink.line(c, [(-46, -205), (-46, -180)], 6)
    ink.line(c, [(46, -205), (46, -180)], 6)
    ink.oval(c, 0, -180, 46, 10, w=6)
    ink.oval(c, 0, -205, 46, 11, w=6)
    # torso + head over the drum
    draw_body(c, j, ink, legs=False, arms=False)
    hx, hy, hr = j["head"][0], j["head"][1], j["hr"]
    if not ink.dashed:
        for k in range(9):                       # afro
            a = math.radians(170 + k * 25)
            ink.disc(c, hx + math.cos(a) * (hr + 4), hy + math.sin(a) * (hr + 4) - 4, 15)
        if headband:
            c.drawLine(hx - hr + 2, hy - 10, hx + hr - 2, hy - 10, paint(RED, ink.alpha, stroke=9))
    # snare
    ink.line(c, [(-150, -200), (-150, 0)], 6)
    ink.line(c, [(-190, 0), (-150, -45), (-110, 0)], 6)
    ink.line(c, [(-214, -222), (-214, -196)], 6)
    ink.line(c, [(-86, -222), (-86, -196)], 6)
    ink.oval(c, -150, -196, 64, 14, w=6)
    ink.oval(c, -150, -222, 64, 15, w=6)
    # hi-hat
    open_ = 3 + 6 * j["hat_h"][0]
    ink.line(c, [(150, -260), (150, 0)], 6)
    ink.line(c, [(112, 0), (150, -45), (188, 0)], 6)
    ink.oval(c, 150, -262 + open_, 58, 9, w=6, fill=GOLD_FILL)
    ink.oval(c, 150, -270 - open_, 58, 9, w=6, fill=GOLD_FILL)
    # arms: afterimages, smears, real arms
    for k in range(trail, 0, -1):
        g = drummer_joints(t - k * 0.03, playing, mood)
        gi = Ink(ink.color, 0.18 * (1 - k / (trail + 1)) * ink.alpha)
        gi.line(c, [g["neck"], g["le"], g["lh"]], INK_W)
        gi.line(c, [g["neck"], g["re"], g["rh"]], INK_W)
        gi.line(c, [g["lh"], g["ls"]], 8)
        gi.line(c, [g["rh"], g["rs"]], 8)
    if playing and not ink.dashed:
        p = drummer_joints(t - 0.05, playing, mood)
        for h0, s0, h1, s1 in ((p["lh"], p["ls"], j["lh"], j["ls"]), (p["rh"], p["rs"], j["rh"], j["rs"])):
            if np.linalg.norm(s1 - s0) > 10:
                c.drawPath(p_poly([tuple(h0), tuple(s0), tuple(s1), tuple(h1)]), paint(ink.color, 0.13))
    ink.line(c, [j["neck"], j["le"], j["lh"]], INK_W)
    ink.line(c, [j["neck"], j["re"], j["rh"]], INK_W)
    ink.line(c, [j["lh"] - (j["ls"] - j["lh"]) * 0.15, j["ls"]], 8, color="#8a5a2b" if not ink.dashed else None)
    ink.line(c, [j["rh"] - (j["rs"] - j["rh"]) * 0.15, j["rs"]], 8, color="#8a5a2b" if not ink.dashed else None)
    # snare accent burst
    if playing and not ink.dashed:
        dts = t - (math.floor(t / STEP) * STEP)
        if hit_env(t, ("snare",), 1) > 0.9 and dts < 0.2:
            p = dts / 0.2
            for k in range(6):
                a = math.radians(-160 + k * 28)
                r0, r1 = 60 + 70 * p, 85 + 100 * p
                c.drawLine(-150 + math.cos(a) * r0, -230 + math.sin(a) * r0 * 0.7,
                           -150 + math.cos(a) * r1, -230 + math.sin(a) * r1 * 0.7,
                           paint(ink.color, 1 - p, stroke=6))
    return j


# --------------------------------------------------------------------------
# other characters

def beat_phase(t, div=2):
    return t * BPM / 60 / div


def bandleader_joints(t, dancing):
    """Cycles through four moves on the half-note, eased between them."""
    moves = [
        dict(hip=(0, -200), lh=(-130, -265), rh=(130, -265), lf=(-85, 0), rf=(85, 0)),
        dict(hip=(0, -205), lh=(-60, -215), rh=(95, -430), lf=(-60, 0), rf=(40, 0)),
        dict(hip=(0, -130), lh=(-110, -370), rh=(110, -370), lf=(-170, 0), rf=(170, 0)),
        dict(hip=(0, -200), lh=(-40, -300), rh=(40, -300), lf=(-30, 0), rf=(70, -90)),
    ]
    if not dancing:
        m = moves[0]
        return make_pose(m["hip"], m["lh"], m["rh"], m["lf"], m["rf"]), 1.0
    ph = beat_phase(t)
    i = int(ph) % 4
    k = smooth((ph % 1) / 0.35)
    a, b = moves[(i - 1) % 4], moves[i]
    mix = {key: tuple(np.array(a[key]) * (1 - k) + np.array(b[key]) * k) for key in a}
    spin = math.cos(math.pi * k) if i == 0 else 1.0
    return make_pose(mix["hip"], mix["lh"], mix["rh"], mix["lf"], mix["rf"]), spin


def draw_bandleader(c, t, dancing, flail=0.0):
    j, spin = bandleader_joints(t, dancing)
    if flail:
        for key, ph in (("lh", 0), ("rh", 2)):
            j[key] = j["neck"] + V(math.cos(t * 18 + ph) * 120, -60 + math.sin(t * 18 + ph) * 80)
        j["le"] = ik(j["neck"], j["lh"], 92, 92, -1)
        j["re"] = ik(j["neck"], j["rh"], 92, 92, 1)
    c.save()
    c.scale(spin if abs(spin) > 0.08 else 0.08, 1)
    n = j["neck"]
    flap = 18 * math.sin(t * 7)
    cape = [n + V(-26, 4), n + V(26, 4), n + V(78 + flap, 230), n + V(-78 + flap, 230)]
    c.drawPath(p_poly([tuple(p) for p in cape]), paint(RED))
    c.drawPath(p_poly([tuple(p) for p in cape]), paint(INK, stroke=6))
    draw_body(c, j, Ink())
    hx, hy = j["head"]
    c.drawPath(p_poly([(hx - 38, hy - 8), (hx - 30, hy - 52), (hx + 20, hy - 66), (hx + 44, hy - 30),
                       (hx + 36, hy - 4)]), paint(INK))                     # pompadour
    c.drawLine(j["rh"][0], j["rh"][1], j["rh"][0] - 8, j["rh"][1] - 34, paint(INK, stroke=8))
    c.drawCircle(j["rh"][0] - 9, j["rh"][1] - 40, 11, paint("#55565e"))
    c.restore()


def draw_bassist(c, t, playing, flail=0.0):
    nod = 10 * hit_env(t, ("kick",), 7) if playing else 0
    strum = 16 * math.sin(beat_phase(t, 0.5) * math.pi) if playing else 0
    j = make_pose((0, -200), (70, -318), (-22, -232 + strum), (-55, 0), (55, 0), head_drop=nod)
    if flail:
        j["lh"] = j["neck"] + V(math.cos(t * 16) * 120, -70 + math.sin(t * 16) * 80)
        j["le"] = ik(j["neck"], j["lh"], 92, 92, -1)
    ink = Ink()
    # guitar behind the arms
    c.save()
    c.translate(-26, -228)
    c.rotate(-36)
    c.drawLine(30, 0, 200, 0, paint(INK, stroke=9))
    c.drawRoundRect(skia.Rect.MakeLTRB(190, -12, 226, 12), 5, 5, paint(INK))
    ink.oval(c, 0, 0, 46, 32, w=7, fill="#f0a24a")
    c.drawCircle(4, 0, 9, paint(INK))
    c.restore()
    draw_body(c, j, ink)
    hx, hy = j["head"]
    c.drawArc(skia.Rect.MakeLTRB(hx - 40, hy - 46, hx + 40, hy + 10), 180, 180, True, paint(BLUE))  # beanie
    c.drawLine(hx - 42, hy - 16, hx + 42, hy - 16, paint(INK, stroke=7))


def draw_producer(c, t, a=1.0, shrug=0.0):
    nod = 9 * hit_env(t, ("kick",), 7)
    lh = lerp(np.array([-45, -250]), np.array([-120, -380]), shrug)
    rh = lerp(np.array([45, -250]), np.array([120, -380]), shrug)
    j = make_pose((0, -200), lh, rh, (-50, 0), (50, 0), head_drop=nod)
    ink = Ink(alpha=a)
    draw_body(c, j, ink)
    hx, hy = j["head"]
    c.drawArc(skia.Rect.MakeLTRB(hx - 38, hy - 40, hx + 38, hy + 6), 180, 180, True, paint(RED, a))
    c.drawLine(hx - 40, hy - 18, hx - 82, hy - 14, paint(RED, a, stroke=9))
    c.drawArc(skia.Rect.MakeLTRB(hx - 48, hy - 50, hx + 48, hy + 30), 200, 140, False, paint(INK, a, stroke=7))
    c.drawRoundRect(skia.Rect.MakeLTRB(hx + 36, hy - 10, hx + 54, hy + 22), 5, 5, paint(INK, a))
    if shrug < 0.5:
        r = skia.Rect.MakeLTRB(-80, -290, 80, -244)
        c.drawRoundRect(r, 6, 6, paint("#cfe0f7", a))
        c.drawRoundRect(r, 6, 6, paint(INK, a, stroke=6))


def draw_rapper(c, t, idx, playing):
    bounce = 14 * abs(math.sin(beat_phase(t, 1) * math.pi)) if playing else 0
    pump = math.sin(beat_phase(t, 1) * math.pi * 2 + idx)
    rh = (70, -300 - 90 * max(0, pump))
    lh = (-26, -342)
    j = make_pose((0, -200 + bounce), lh, rh, (-55, 0), (55, 0))
    draw_body(c, j, Ink())
    c.drawLine(lh[0], lh[1], lh[0] + 10, lh[1] - 26, paint(INK, stroke=8))
    c.drawCircle(lh[0] + 12, lh[1] - 32, 11, paint("#55565e"))
    hx, hy = j["head"]
    hat = ["#f6c343", RED, BLUE][idx % 3]
    c.drawArc(skia.Rect.MakeLTRB(hx - 38, hy - 40, hx + 38, hy + 6), 180, 180, True, paint(hat))
    if idx % 2 == 0:
        c.drawLine(hx + 30, hy - 18, hx + 74, hy - 14, paint(hat, stroke=9))
    for k in range(3):                      # chain
        c.drawCircle(j["neck"][0] - 12 + k * 12, j["neck"][1] + 22, 5, paint("#e2b13c"))


def draw_cursor(c, x, y, s=1.0, pressed=False):
    pts = [(0, 0), (0, 52), (13, 40), (22, 62), (31, 58), (22, 37), (40, 37)]
    c.save()
    c.translate(x, y)
    c.scale(s * (0.9 if pressed else 1), s * (0.9 if pressed else 1))
    c.translate(5, 6)
    c.drawPath(p_poly(pts), paint(INK, 0.2))
    c.translate(-5, -6)
    c.drawPath(p_poly(pts), paint(WHITE))
    c.drawPath(p_poly(pts), paint(INK, stroke=4))
    c.restore()


def draw_keycap(c, x, y, label, press, a):
    w = 120 if len(label) > 1 else 96
    dy = 10 * press
    c.drawRoundRect(skia.Rect.MakeLTRB(x - w / 2, y - 40 + 10, x + w / 2, y + 50), 16, 16, paint(INK, a))
    r = skia.Rect.MakeLTRB(x - w / 2, y - 40 + dy, x + w / 2, y + 40 + dy)
    c.drawRoundRect(r, 16, 16, paint(WHITE, a))
    c.drawRoundRect(r, 16, 16, paint(INK, a, stroke=5))
    draw_text(c, label, x, y + 15 + dy, font("ExtraBold", 40), INK, a=a, align="center")


def puff(c, x, y, p, r=120):
    if not 0 < p < 1:
        return
    for k in range(9):
        a = math.radians(k * 40 + 10)
        d = r * ease_out(p)
        c.drawCircle(x + math.cos(a) * d, y + math.sin(a) * d * 0.8, 34 * (1 - p), paint(PAPER_DK))
        c.drawCircle(x + math.cos(a) * d, y + math.sin(a) * d * 0.8, 34 * (1 - p), paint(INK, stroke=5))


# --------------------------------------------------------------------------
# world: paper, grid, waveform floor

BG_X0, BG_Y0, BG_W, BG_H = -1300, -1300, 3700, 4600


def make_paper():
    surf = skia.Surface(BG_W, BG_H)
    c = surf.getCanvas()
    c.translate(-BG_X0, -BG_Y0)
    c.clear(col(PAPER))
    rng = np.random.default_rng(3)
    for x in range(BG_X0 - BG_X0 % 60, BG_X0 + BG_W, 60):
        c.drawLine(x, BG_Y0, x, GROUND, paint(GRID, 0.9 if x % 300 == 0 else 0.5, stroke=2))
    for y in range(BG_Y0 - BG_Y0 % 60, GROUND, 60):
        c.drawLine(BG_X0, y, BG_X0 + BG_W, y, paint(GRID, 0.9 if y % 300 == 0 else 0.5, stroke=2))
    c.drawRect(skia.Rect.MakeLTRB(BG_X0, GROUND, BG_X0 + BG_W, BG_Y0 + BG_H), paint(PAPER_DK))
    for _ in range(6000):
        x, y = rng.uniform(BG_X0, BG_X0 + BG_W), rng.uniform(BG_Y0, BG_Y0 + BG_H)
        c.drawCircle(x, y, rng.uniform(0.6, 1.6), paint("#c9c0ae", 0.35))
    return surf.makeImageSnapshot()


def music_envelope(music):
    hop = SR // 100
    n = len(music) // hop
    e = np.sqrt((music[:n * hop].reshape(n, hop) ** 2).mean(1))
    e = np.convolve(e, np.ones(3) / 3, "same")
    return e / (e.max() + 1e-9)


def draw_floor(c, t, env, view, doors, red_span=None):
    """Waveform floor: playhead at x=540; bars hang below the ground line."""
    x0, x1 = view
    x = math.floor(x0 / 14) * 14
    gaps = [(d0, d1) for d0, d1, ang in doors if ang > 0.02]
    while x < x1:
        if not any(d0 <= x <= d1 for d0, d1 in gaps):
            tau = t + (x - 540) / SCROLL
            k = int(tau * 100)
            e = env[k] if 0 <= k < len(env) else 0.0
            h = 8 + 170 * e ** 0.8
            colr = RED if (red_span and red_span[0] <= tau <= red_span[1]) else INK
            c.drawLine(x, GROUND + 10, x, GROUND + 10 + h, paint(colr, 0.8, stroke=7))
        x += 14
    # ground line with trapdoor gaps
    segs, cur = [], x0
    for d0, d1 in sorted(gaps):
        segs.append((cur, d0))
        cur = d1
    segs.append((cur, x1))
    for a, b in segs:
        if b > a:
            c.drawLine(a, GROUND, b, GROUND, paint(INK, stroke=7))
    for d0, d1, ang in doors:
        if ang > 0.02:
            rad = math.radians(90 * ang)
            c.drawLine(d0, GROUND, d0 + (d1 - d0) * math.cos(rad), GROUND + (d1 - d0) * math.sin(rad),
                       paint(INK, stroke=7))
    # playhead
    c.drawPath(p_poly([(528, GROUND + 22), (552, GROUND + 22), (540, GROUND + 6)]), paint(RED))


# --------------------------------------------------------------------------
# sfx

def build_sfx(T, E, total):
    rng = np.random.default_rng(5)
    n = int(total * SR) + SR
    out = np.zeros(n, np.float32)

    def add(t, s, g=1.0):
        i = int(t * SR)
        if i >= n or i < 0:
            return
        j = min(n, i + len(s))
        out[i:j] += (s[:j - i] * g).astype(np.float32)

    def env_t(m, k):
        return np.exp(-np.arange(m) / SR * k)

    def noise(m, smooth_k=1):
        x = rng.standard_normal(m)
        return np.convolve(x, np.ones(smooth_k) / smooth_k, "same") if smooth_k > 1 else x

    def whoosh(d=0.45):
        m = int(d * SR)
        return noise(m, 9) * np.sin(np.linspace(0, np.pi, m)) ** 2 * 1.2

    def click():
        m = int(0.03 * SR)
        tt = np.arange(m) / SR
        return (noise(m) * 0.5 + np.sin(2 * np.pi * 2200 * tt)) * env_t(m, 220) * 0.5

    def key():
        m = int(0.06 * SR)
        tt = np.arange(m) / SR
        return (noise(m, 3) * 0.6 + np.sin(2 * np.pi * 900 * tt) * 0.4) * env_t(m, 90)

    def pop(f0=600, f1=1300, d=0.09):
        m = int(d * SR)
        f = np.linspace(f0, f1, m)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * env_t(m, 40) * 0.4

    def thud(g=1.0):
        m = int(0.5 * SR)
        tt = np.arange(m) / SR
        return (np.sin(2 * np.pi * (50 + 60 * np.exp(-tt * 25)) * tt) * np.exp(-tt * 7)
                + noise(m, 5) * np.exp(-tt * 30) * 0.4) * g

    def whistle(d=0.9):
        m = int(d * SR)
        f = np.linspace(1600, 250, m)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.minimum(1, np.linspace(3, 0, m)) * 0.18

    add(T["hook2"] + 0.05, pop(), 1.0)
    add(T["hook2"] + 0.6, thud(0.8))
    add(T["older"] - 0.3, pop(1200, 400, 0.15))
    for k in range(14):
        add(T["older"] + 0.08 * k, click(), 0.5)
    add(T["older"] + 1.25, thud(1.0))
    add(T["band"], whoosh(), 0.6)
    add(T["band"] + 0.45, thud(0.5))
    add(T["dropout"] + 0.75, thud(0.6))
    add(T["dropout"] + 0.8, whistle())
    add(T["solo"], thud(0.7))
    for k in range(3):
        add(T["twenty"] + 0.5 * k, click(), 0.6)
    add(T["sampled"] + 0.45, click(), 1.0)
    add(T["sampled"] + 1.05, click(), 1.0)
    add(T["sampled"] + 1.2, key(), 1.0)
    add(T["sampled"] + 1.32, key(), 1.0)
    add(T["looped"] - 0.12, key(), 1.0)
    add(T["looped"] - 0.02, key(), 1.0)
    for k in range(4):
        add(T["looped"] + 0.08 + 0.14 * k, pop(500 + 120 * k, 1100 + 120 * k), 1.0)
    add(T["era"], whoosh(0.7), 0.6)
    add(T["era"] + 1.2, thud(0.6))
    add(T["names"], pop(), 1.0)
    add(T["names"] + 0.75, pop(), 1.0)
    for k in range(12):
        add(T["thousand"] + 0.08 * k, pop(400 + 60 * k, 900 + 60 * k, 0.05), 0.6)
    add(T["royalty"] + 0.55, whoosh(0.7), 0.6)
    add(T["royalty2"] + 0.2, whoosh(0.3), 0.5)
    add(T["royalty2"] + 0.9, thud(1.1))
    for k in range(7):
        add(T["everywhere"] + 0.12 * k, pop(500, 1000, 0.06), 0.7)
    add(T["almost"] + 0.5, click(), 1.0)
    add(T["almost"] + 0.6, whoosh(0.8), 0.5)
    return out


# --------------------------------------------------------------------------
# direction

def camera_keys(T):
    return [
        (0.0, 0.0, 1.55, 540, 1080),
        (0.25, 1.8, 1.0, 540, 1000),
        (T["hook2"], 0.5, 0.92, 660, 1000),
        (T["older"] + 1.5, 0.5, 0.9, 540, 1000),
        (T["solo"] - 0.05, 0.35, 1.4, 540, 1060),
        (T["twenty"], 0.5, 1.0, 540, 1000),
        (T["looped"], 0.6, 0.5, 540, 1000),
        (T["era"] + 0.2, 0.9, 0.6, 540, 820),
        (T["royalty"], 0.35, 1.0, 600, 1000),
        (T["royalty2"] + 0.1, 0.4, 1.2, 580, 1060),
        (T["everywhere"], 0.5, 0.88, 540, 1010),
        (T["almost"] + 0.4, 1.4, 1.05, 540, 1040),
    ]


def render(cfg_path):
    with open(cfg_path) as fh:
        cfg = json.load(fh)
    fps = cfg.get("fps", 30)
    out = os.path.join(ROOT, cfg.get("stickman_output", "output/funky_drummer_stickman.mp4"))
    work = os.path.join(ROOT, "output", "work")
    os.makedirs(work, exist_ok=True)

    voice, total, chunks = build_timeline(cfg, os.path.join(ROOT, "output", "tts"))
    T = {l["id"]: l["start"] for l in cfg["lines"]}
    T["end"] = cfg["lines"][-1]["end"]
    E = {l["id"]: l["end"] for l in cfg["lines"]}
    events = drum_events(T, total)
    set_events(events)
    sections = music_sections(T, total)
    print(f"duration {total:.2f}s")

    music = build_music(T, total, events)
    sfx = build_sfx(T, E, total)
    n = int(total * SR)
    voice = np.pad(voice, (0, max(0, n - len(voice))))[:n]
    music, sfx = music[:n], sfx[:n]
    env_v = np.convolve((np.abs(voice) > 0.01).astype(np.float32), np.ones(int(0.25 * SR)) / (0.25 * SR), "same")
    mix = voice + music * (0.55 - 0.33 * np.clip(env_v * 3, 0, 1)) + sfx * 0.6
    wav = os.path.join(work, "mix_stick.wav")
    write_wav(wav, mix / max(1.0, np.abs(mix).max() / 0.95))
    env = music_envelope(music)
    break_span = next((s0, s1) for s0, s1, parts in sections if parts == {"drums"})

    paper = make_paper()
    keys = camera_keys(T)
    frames = int(total * fps)
    impacts = [T["older"] + 1.25, T["solo"], T["royalty2"] + 0.9]

    def is_playing(tt):
        return any(s0 <= tt < s1 and "drums" in parts for s0, s1, parts in sections)

    # clones: (paste time, line x, pyramid x, pyramid ground)
    clones = [(T["looped"] + 0.08, -420, 300, GROUND - 480), (T["looped"] + 0.22, 1020, 1020, GROUND),
              (T["looped"] + 0.36, 60, 60, GROUND), (T["looped"] + 0.5, 1500, 780, GROUND - 480)]
    windows = [(60, 190, 300, 230, "sample.wav"), (390, 120, 300, 230, "beat_v3.mp3"),
               (720, 190, 300, 230, "loop_96bpm"), (36, 560, 210, 330, ""), (834, 560, 210, 330, ""),
               (40, 1660, 300, 200, "drums.aif"), (740, 1660, 300, 200, "break.wav")]

    sprite = skia.Surface(380, 340)

    def clone_sprite(tt):
        sc = sprite.getCanvas()
        sc.clear(skia.ColorTRANSPARENT)
        sc.save()
        sc.translate(200, 330)
        sc.scale(0.6, 0.6)
        draw_drummer(sc, tt, is_playing(tt), "play", Ink(), headband=True)
        sc.restore()
        return sprite.makeImageSnapshot()

    def draw_world(c, t, z, cx, cy):
        playing = is_playing(t)
        c.save()
        c.translate(W / 2, H / 2)
        c.scale(z, z)
        c.translate(-cx, -cy)
        c.drawImage(paper, BG_X0, BG_Y0)
        view = (cx - W / 2 / z - 20, cx + W / 2 / z + 20)

        # spinning record backdrop for the 1970 part
        rec_a = window(t, T["band"] - 0.1, T["solo"] + 0.3, 0.3, 0.4)
        if rec_a > 0:
            drop = ease_out((t - T["band"] + 0.1) / 0.45)
            ry = lerp(-600, 700, drop)
            c.saveLayerAlpha(None, int(255 * rec_a))
            c.drawCircle(540, ry, 380, paint(INK))
            for k in range(7):
                c.drawCircle(540, ry, 160 + k * 30, paint("#3a3a44", stroke=3))
            c.save()
            c.rotate(t * 120, 540, ry)
            c.drawArc(skia.Rect.MakeLTRB(200, ry - 340, 880, ry + 340), -40, 30, False,
                      paint(WHITE, 0.25, stroke=40, cap=skia.Paint.kButt_Cap))
            c.restore()
            c.drawCircle(540, ry, 125, paint(RED))
            lbl = smooth((t - T["notes"]) / 0.4)
            if lbl > 0:
                draw_text(c, "FUNKY", 540, ry - 18, font("ExtraBold", 50), PAPER, a=lbl, align="center")
                draw_text(c, "DRUMMER", 540, ry + 34, font("ExtraBold", 40), PAPER, a=lbl, align="center")
            c.drawCircle(540, ry, 9, paint(PAPER))
            c.restore()

        doors_open = smooth((t - T["dropout"] - 0.72) / 0.22) * (1 - smooth((t - T["solo"] - 0.2) / 0.3))
        doors = [(120, 320, doors_open), (760, 960, doors_open)]
        red = break_span if T["twenty"] <= t < T["royalty"] else None
        draw_floor(c, t, env, view, doors, red)

        # band: leap in, dance, fall through the trapdoors
        if T["band"] <= t < T["solo"] + 0.5:
            fall_t = t - T["dropout"] - 0.8
            for x, who, delay in ((860, "lead", 0.15), (220, "bass", 0.3)):
                k = clamp((t - T["band"] - delay) / 0.5)
                if k <= 0:
                    continue
                side = 1 if x > 540 else -1
                jx = lerp(x + side * 520, x, ease_out(k))
                jy = -320 * math.sin(math.pi * k) if k < 1 else 0
                c.save()
                c.translate(jx, GROUND + jy)
                if fall_t > 0:
                    c.translate(0, 0.5 * 3200 * fall_t ** 2)
                    c.rotate(side * 260 * fall_t, 0, -200)
                if k >= 1 and fall_t < 0:
                    sq = math.exp(-(t - T["band"] - delay - 0.5) * 9)
                    c.scale(1 + 0.18 * sq, 1 - 0.18 * sq)
                if who == "lead":
                    draw_bandleader(c, t, t < T["dropout"] + 0.6, flail=1.0 if fall_t > -0.15 else 0)
                else:
                    draw_bassist(c, t, playing, flail=1.0 if fall_t > -0.15 else 0)
                c.restore()

        # producer (not the one who made it)
        if T["hook2"] <= t < T["older"]:
            pk = back_out((t - T["hook2"]) / 0.4)
            gone = smooth((t - T["older"] + 0.35) / 0.2)
            c.save()
            c.translate(930, GROUND)
            c.scale(pk * (1 - gone) + 0.001, pk * (1 - gone) + 0.001)
            draw_producer(c, t, 1, shrug=smooth((t - T["hook2"] - 1.0) / 0.3))
            st = clamp((t - T["hook2"] - 0.6) / 0.25)
            if st > 0:
                s = lerp(2.2, 1.0, ease_out(st))
                c.scale(s, s)
                c.drawLine(-110, -420, 110, -120, paint(RED, st, stroke=30))
                c.drawLine(110, -420, -110, -120, paint(RED, st, stroke=30))
            c.restore()
        puff(c, 930, GROUND - 220, (t - T["older"] + 0.35) / 0.5)

        # copies of the drummer
        era_k = smooth((t - T["era"] - 0.1) / 0.8)
        if T["looped"] <= t < T["thousand"] + 1.2:
            for pt, lx, px, pg in clones:
                if t < pt:
                    continue
                pk = back_out((t - pt) / 0.3)
                x = lerp(lx, px, era_k)
                g = lerp(GROUND, pg, era_k) - 380 * math.sin(math.pi * era_k) * (pg != GROUND)
                off = 40 * (1 - ease_out((t - pt) / 0.3))
                c.save()
                c.translate(x + off, g + off)
                c.scale(pk, pk)
                draw_drummer(c, t, playing, "play")
                c.restore()
            plank = smooth((t - T["era"] - 0.75) / 0.3)
            if plank > 0:
                for y, a0, a1 in ((GROUND - 480, 120, 960), (GROUND - 960, 180, 900)):
                    mid = (a0 + a1) / 2
                    w2 = (a1 - a0) / 2 * plank
                    if y == GROUND - 960 and t < T["era"] + 1.0:
                        continue
                    c.drawRect(skia.Rect.MakeLTRB(mid - w2, y - 4, mid + w2, y + 22), paint("#c9a36b"))
                    c.drawRect(skia.Rect.MakeLTRB(mid - w2, y - 4, mid + w2, y + 22), paint(INK, stroke=6))
            for i, x in enumerate((300, 540, 780)):
                td = T["era"] + 1.0 + 0.12 * i
                if t < td:
                    continue
                fall = clamp((t - td) / 0.35)
                y = lerp(-900, GROUND - 960, fall * fall)
                sq = math.exp(-max(0, t - td - 0.35) * 9) if fall >= 1 else 0
                c.save()
                c.translate(x, y)
                c.scale(1 + 0.2 * sq, 1 - 0.2 * sq)
                draw_rapper(c, t, i, playing)
                c.restore()
            for i, (x, name) in enumerate(((300, "PUBLIC ENEMY"), (780, "LL COOL J"))):
                tn = T["names"] + 0.75 * i
                if t < tn:
                    continue
                k = back_out((t - tn) / 0.35)
                f = font("ExtraBold", 54)
                tw = text_w(f, name)
                y = GROUND - 960 - 560
                c.save()
                c.translate(x, y)
                c.scale(k, k)
                c.drawLine(0, 44, 0, 120, paint(RED, stroke=7))
                c.drawRoundRect(skia.Rect.MakeLTRB(-tw / 2 - 24, -50, tw / 2 + 24, 46), 18, 18, paint(RED))
                draw_text(c, name, 0, 18, f, WHITE, align="center")
                c.restore()

        # the original drummer
        mood = "play"
        if T["solo"] <= t < T["twenty"]:
            mood = "solo"
        if t >= T["royalty"]:
            mood = "idle"
        if T["royalty"] + 1.3 <= t < T["royalty2"] + 0.2:
            mood = "hold"
        if t >= T["royalty2"] + 0.9:
            mood = "sad"
        orig_playing = playing and t < T["royalty"]
        ghost = smooth((t - T["almost"] - 0.7) / 0.8)
        hide_for_grid = window(t, T["thousand"] + 0.6, T["royalty"] - 0.05, 0.01, 0.01) > 0.5
        if not hide_for_grid:
            c.save()
            c.translate(540, GROUND)
            if ghost > 0:
                draw_drummer(c, t, False, mood, Ink("#9aa0aa", 0.9 * ghost, dashed=True, t=t))
                if ghost < 1:
                    c.saveLayerAlpha(None, int(255 * (1 - ghost)))
                    draw_drummer(c, t, False, mood)
                    c.restore()
            else:
                draw_drummer(c, t, orig_playing, mood, trail=4 if mood == "solo" else 0)
            c.restore()

        # envelope flying into his hand
        if T["royalty"] + 0.5 <= t < T["royalty2"] + 0.25:
            k = ease_out((t - T["royalty"] - 0.5) / 0.8)
            ex, ey = lerp(1500, 610, k), lerp(500, GROUND - 360, k) - 260 * math.sin(math.pi * k)
            c.save()
            c.translate(ex, ey)
            c.rotate(360 * (1 - k) * 1.5)
            r = skia.Rect.MakeLTRB(-60, -40, 60, 40)
            c.drawRect(r, paint(WHITE))
            c.drawRect(r, paint(INK, stroke=6))
            c.drawPath(path_of([(-60, -40), (0, 6), (60, -40)]), paint(INK, stroke=5))
            c.restore()

        # selection: cursor drags a marquee around the drummer
        sel = (230, 790, 760, 1318)
        if T["sampled"] <= t < T["looped"] + 0.7:
            down = T["sampled"] + 0.45
            up = T["sampled"] + 1.05
            if t < down:
                k = smooth((t - T["sampled"]) / 0.45)
                cur = (lerp(1250, sel[0], k), lerp(500, sel[1], k))
            elif t < up:
                k = smooth((t - down) / (up - down))
                cur = (lerp(sel[0], sel[2], k), lerp(sel[1], sel[3], k))
            else:
                k = smooth((t - up) / 0.5)
                cur = (lerp(sel[2], 1200, k), lerp(sel[3], 1500, k))
            if t >= down:
                r = skia.Rect.MakeLTRB(sel[0], sel[1], cur[0] if t < up else sel[2], cur[1] if t < up else sel[3])
                c.drawRect(r, paint(BLUE, 0.12))
                c.drawRect(r, paint(BLUE, stroke=5, effect=skia.DashPathEffect.Make([16, 10], -t * 60)))
            draw_cursor(c, cur[0], cur[1], 2.2, pressed=down <= t < up)

        # the cursor comes back for the original
        if t >= T["almost"]:
            k = smooth((t - T["almost"]) / 0.5)
            cx2, cy2 = lerp(1300, 610, k), lerp(1600, 1060, k)
            if t > T["almost"] + 0.5:
                r = skia.Rect.MakeLTRB(sel[0], sel[1], sel[2], sel[3])
                c.drawRect(r, paint(RED, 0.08))
                c.drawRect(r, paint(RED, stroke=5, effect=skia.DashPathEffect.Make([16, 10], -t * 60)))
            draw_cursor(c, cx2, cy2, 2.2, pressed=T["almost"] + 0.5 <= t < T["almost"] + 0.62)

        # loop arrow over the row of copies
        la = window(t, T["looped"] + 0.3, T["era"] + 0.2, 0.2, 0.3)
        if la > 0:
            c.save()
            c.translate(540, 520)
            c.rotate(t * 260)
            c.drawArc(skia.Rect.MakeLTRB(-130, -130, 130, 130), 20, 300, False, paint(RED, la, stroke=22))
            c.drawPath(p_poly([(120, -70), (86, 30), (172, 8)]), paint(RED, la))
            c.restore()

        # spotlight vignette during the solo
        sa = window(t, T["solo"], T["twenty"], 0.15, 0.3)
        if sa > 0:
            sh = skia.GradientShader.MakeRadial((540, 1080), 520, [col(INK, 0), col(INK, 0.75 * sa)], [0.55, 1.0])
            c.drawRect(skia.Rect.MakeLTRB(view[0] - 200, -600, view[1] + 200, 2800), paint(WHITE, shader=sh))
            for k in range(14):
                a = math.radians(k * 360 / 14 + t * 40)
                r0 = 420 + 40 * ((t * 4 + hash01("sl", k)) % 1)
                c.drawLine(540 + math.cos(a) * r0, 1080 + math.sin(a) * r0,
                           540 + math.cos(a) * (r0 + 80), 1080 + math.sin(a) * (r0 + 80),
                           paint(PAPER, 0.7 * sa, stroke=6))
        c.restore()

    stills = [float(x) for x in os.environ.get("STILLS", "").split(",") if x]
    enc = None if stills else subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-i", wav,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-shortest", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)

    surf = skia.Surface(W, H)
    for fi, t in enumerate(stills or [i / fps for i in range(frames)]):
        c = surf.getCanvas()
        c.clear(col(PAPER))

        def cam(tt):
            z, x, y = camera_at(keys, tt)
            if is_playing(tt):
                z *= 1 + 0.012 * hit_env(tt, ("kick",), 12)
            return z, x, y

        z, cx, cy = cam(t)
        z0, cx0, cy0 = cam(t - 1 / fps)
        moving = math.hypot(cx - cx0, cy - cy0) * z > 14 or abs(z / z0 - 1) > 0.015
        subs = 3 if moving else 1
        for j in range(subs):
            if j:
                c.saveLayerAlpha(None, int(255 / (j + 1)))
            draw_world(c, t, *cam(t - (subs - 1 - j) / subs / fps))
            if j:
                c.restore()

        # ---- screen-space overlays
        # year odometer: rolls back from 1985 to 1970
        oa = window(t, T["older"] - 0.05, T["band"] + 0.05, 0.15, 0.25)
        if oa > 0:
            c.drawRect(skia.Rect.MakeWH(W, H), paint(PAPER, 0.88 * oa))
            v = lerp(1985, 1970, ease_out((t - T["older"]) / 1.25))
            land = back_out((t - T["older"] - 1.25) / 0.3) if t > T["older"] + 1.25 else 1.0
            f = font("ExtraBold", 200)
            bw, bh, y0 = 200, 250, 600
            x0 = W / 2 - 2 * bw - 18
            c.save()
            c.translate(W / 2, y0 + bh / 2)
            sc = 1 + 0.08 * (1 - land) if t > T["older"] + 1.25 else 1
            c.scale(sc, sc)
            c.translate(-W / 2, -(y0 + bh / 2))
            for i in range(4):
                p = 10 ** (3 - i)
                base = v / p
                digit = int(math.floor(base)) % 10
                frac = (v % p) / p if i == 3 else max(0.0, ((v % p) - (p - 1)))
                frac = clamp(frac)
                bx = x0 + i * (bw + 12)
                r = skia.Rect.MakeLTRB(bx, y0, bx + bw, y0 + bh)
                c.drawRoundRect(r, 24, 24, paint(WHITE, oa))
                c.save()
                c.clipRect(r)
                for dd, off in ((digit, -frac), ((digit + 1) % 10, 1 - frac)):
                    draw_text(c, str(dd), bx + bw / 2, y0 + bh / 2 + 72 + off * bh, f, INK, a=oa, align="center")
                c.restore()
                c.drawRoundRect(r, 24, 24, paint(INK, oa, stroke=8))
            c.restore()
            if t > T["older"] + 1.3:
                k = back_out((t - T["older"] - 1.3) / 0.35)
                c.save()
                c.translate(W / 2, 980)
                c.rotate(-4)
                c.scale(k, k)
                label = "BEFORE HIP-HOP EXISTED"
                fw = text_w(font("ExtraBold", 50), label)
                c.drawRoundRect(skia.Rect.MakeLTRB(-fw / 2 - 26, -56, fw / 2 + 26, 26), 14, 14, paint(RED, oa))
                draw_text(c, label, 0, 0, font("ExtraBold", 50), WHITE, a=oa, align="center")
                c.restore()

        # handwritten title reveal
        na = window(t, T["notes"], T["solo"], 0.01, 0.3)
        if na > 0:
            k = smooth((t - T["notes"]) / 0.7)
            f = font("ExtraBold", 104)
            tw = text_w(f, "Funky Drummer")
            c.save()
            c.clipRect(skia.Rect.MakeLTRB(0, 0, W / 2 - tw / 2 + (tw + 20) * k, H))
            draw_text(c, "Funky Drummer", W / 2, 330, f, INK, a=na, align="center", outline=PAPER, ow=14)
            c.restore()
            u = smooth((t - T["notes"] - 0.5) / 0.4)
            if u > 0:
                pts = [(W / 2 - tw / 2 + i * tw / 20, 360 + 9 * math.sin(i * 1.3)) for i in range(21)]
                c.drawPath(trimmed(path_of(pts), 0, u), paint(RED, na, stroke=12))
                draw_text(c, "JAMES BROWN  ·  1970", W / 2, 430, font("Bold", 40), INK, a=na * u, align="center")

        # 20-second timer
        ta = window(t, T["twenty"] - 0.05, T["sampled"] + 0.2, 0.2, 0.3)
        if ta > 0:
            k = clamp((t - T["twenty"]) / 1.6)
            c.save()
            c.translate(W / 2, 300)
            c.scale(back_out((t - T["twenty"] + 0.05) / 0.35), back_out((t - T["twenty"] + 0.05) / 0.35))
            r = skia.Rect.MakeLTRB(-330, -44, 330, 44)
            c.drawRoundRect(r, 44, 44, paint(WHITE, ta))
            c.drawRoundRect(skia.Rect.MakeLTRB(-330, -44, -330 + 660 * k, 44), 44, 44, paint(RED, ta))
            c.drawRoundRect(r, 44, 44, paint(INK, ta, stroke=8))
            draw_text(c, f"0:{int(round(20 * k)):02d}", 0, 22, font("ExtraBold", 62), INK if k < 0.55 else WHITE,
                      a=ta, align="center")
            c.restore()

        # keycaps + toast
        for t0, letter, toast in ((T["sampled"] + 1.2, "C", "Copied!"), (T["looped"] - 0.12, "V", "")):
            ka = window(t, t0 - 0.1, t0 + 0.75, 0.1, 0.2)
            if ka > 0:
                kk = back_out((t - t0 + 0.1) / 0.25)
                c.save()
                c.translate(W / 2, 360)
                c.scale(kk, kk)
                draw_keycap(c, -80, 0, "Ctrl", 1.0 if t > t0 else 0.0, ka)
                draw_text(c, "+", 10, 18, font("ExtraBold", 50), INK, a=ka, align="center")
                draw_keycap(c, 90, 0, letter, 1.0 if t > t0 + 0.12 else 0.0, ka)
                c.restore()
                if toast and t > t0 + 0.25:
                    tk = back_out((t - t0 - 0.25) / 0.3)
                    c.save()
                    c.translate(W / 2, 500)
                    c.scale(tk, tk)
                    c.drawRoundRect(skia.Rect.MakeLTRB(-150, -40, 150, 40), 40, 40, paint(INK, ka))
                    draw_text(c, toast, 0, 16, font("ExtraBold", 44), WHITE, a=ka, align="center")
                    c.restore()

        # 1,000 tiny drummers
        ga = window(t, T["thousand"] - 0.05, T["royalty"] + 0.05, 0.25, 0.25)
        if ga > 0:
            c.drawRect(skia.Rect.MakeWH(W, H), paint(PAPER, ga))
            img = clone_sprite(t)
            cols, rows = 25, 40
            tw_, th_ = W / cols, H / rows
            shown = 0
            for r_ in range(rows):
                for q in range(cols):
                    cxq, cyq = (q + 0.5) * tw_, (r_ + 0.5) * th_
                    d = math.hypot(cxq - W / 2, (cyq - 900) * 0.6) / 1100
                    k = clamp((t - T["thousand"] - 0.9 * d) / 0.25)
                    if k <= 0:
                        continue
                    shown += 1
                    s = back_out(k)
                    wq, hq = tw_ * 1.05 * s, th_ * 1.05 * s
                    c.drawImageRect(img, skia.Rect.MakeLTRB(cxq - wq / 2, cyq - hq / 2, cxq + wq / 2, cyq + hq / 2),
                                    SAMPLING, paint(WHITE, ga))
            label = f"{shown:,}" + ("+" if shown >= 1000 and t > T["thousand"] + 1.3 else "")
            c.drawRoundRect(skia.Rect.MakeLTRB(W / 2 - 260, 790, W / 2 + 260, 990), 34, 34, paint(RED, ga))
            c.drawRoundRect(skia.Rect.MakeLTRB(W / 2 - 260, 790, W / 2 + 260, 990), 34, 34, paint(INK, ga, stroke=8))
            draw_text(c, label, W / 2, 935, font("ExtraBold", 130), WHITE, a=ga, align="center")

        # the cheque
        ca = window(t, T["royalty2"] + 0.15, T["everywhere"] - 0.05, 0.05, 0.3)
        if ca > 0:
            k = back_out((t - T["royalty2"] - 0.15) / 0.4)
            c.save()
            c.translate(W / 2, 520)
            c.rotate(-3)
            c.scale(k, k)
            r = skia.Rect.MakeLTRB(-420, -190, 420, 190)
            c.drawRect(r.makeOffset(10, 12), paint(INK, 0.2 * ca))
            c.drawRect(r, paint("#eef6ee", ca))
            c.drawRect(r, paint(INK, ca, stroke=7))
            fb, fs = font("ExtraBold", 40), font("Bold", 30)
            draw_text(c, "ROYALTY PAYMENT", -380, -120, fb, INK, a=ca)
            draw_text(c, "PAY TO:  Clyde Stubblefield", -380, -50, fs, INK, a=ca)
            draw_text(c, "FOR:  1,000+ samples", -380, 0, fs, INK, a=ca)
            c.drawLine(-380, 110, 60, 110, paint(INK, ca, stroke=3))
            box = skia.Rect.MakeLTRB(120, -10, 380, 90)
            c.drawRect(box, paint(WHITE, ca))
            c.drawRect(box, paint(INK, ca, stroke=5))
            draw_text(c, "$0.00", 250, 62, font("ExtraBold", 64), INK, a=ca, align="center")
            st = clamp((t - T["royalty2"] - 0.9) / 0.18)
            if st > 0:
                s = lerp(2.6, 1.0, ease_out(st))
                c.save()
                c.translate(-150, 120)
                c.rotate(-12)
                c.scale(s, s)
                sr = skia.Rect.MakeLTRB(-230, -66, 230, 66)
                c.drawRoundRect(sr, 14, 14, paint(RED, 0.15 * st * ca))
                c.drawRoundRect(sr, 14, 14, paint(RED, st * ca, stroke=10))
                draw_text(c, "ROYALTIES: $0", 0, 24, font("ExtraBold", 62), RED, a=st * ca, align="center")
                c.restore()
            c.restore()

        # the beat is everywhere: windows full of drummers
        wa = window(t, T["everywhere"] - 0.05, total, 0.05, 0.01)
        if wa > 0:
            img = None
            for i, (x, y, w_, h_, title) in enumerate(windows):
                k = back_out((t - T["everywhere"] - 0.12 * i) / 0.35)
                if k <= 0:
                    continue
                img = img or clone_sprite(t)
                fy = 8 * math.sin(t * 2 + i)
                c.save()
                c.translate(x + w_ / 2, y + h_ / 2 + fy)
                c.scale(k, k)
                c.translate(-w_ / 2, -h_ / 2)
                phone = not title
                rr = 28 if phone else 14
                c.drawRoundRect(skia.Rect.MakeLTRB(8, 10, w_ + 8, h_ + 10), rr, rr, paint(INK, 0.2))
                c.drawRoundRect(skia.Rect.MakeLTRB(0, 0, w_, h_), rr, rr, paint(WHITE))
                if not phone:
                    c.drawRoundRect(skia.Rect.MakeLTRB(0, 0, w_, 40), 14, 14, paint("#e4e7ec"))
                    for d_ in range(3):
                        c.drawCircle(22 + d_ * 22, 20, 7, paint([RED, "#f6c343", "#5cc26b"][d_]))
                    draw_text(c, title, w_ - 14, 29, font("Bold", 22), INK, align="right")
                    dst = skia.Rect.MakeLTRB(w_ / 2 - 105, 44, w_ / 2 + 105, h_ - 4)
                else:
                    c.drawRoundRect(skia.Rect.MakeLTRB(w_ / 2 - 30, 12, w_ / 2 + 30, 22), 5, 5, paint(INK))
                    dst = skia.Rect.MakeLTRB(10, 60, w_ - 10, h_ - 60)
                c.drawImageRect(img, dst, SAMPLING, paint(WHITE))
                c.drawRoundRect(skia.Rect.MakeLTRB(0, 0, w_, h_), rr, rr, paint(INK, stroke=6))
                c.restore()

        slot = int(t // 7) % 2 if t < T["end"] else 0
        if t < T["end"] + 0.3 and not (ga > 0.5):
            draw_watermark(c, t, cfg["handle"], slot)
        draw_captions(c, t, chunks)
        draw_outro(c, t, T["end"] + 0.25, cfg)

        frame = surf.makeImageSnapshot().toarray()
        if any(0 <= t - ti < 2.0 / fps for ti in impacts):
            frame = frame.copy()
            frame[..., :3] = 255 - frame[..., :3]          # impact frame
        if stills:
            skia.Image.fromarray(frame, colorType=skia.kBGRA_8888_ColorType).save(
                os.path.join(work, f"stick_{t:05.2f}.png"))
            continue
        enc.stdin.write(frame.tobytes())
        if fi % 150 == 0:
            print(f"frame {fi}/{frames}")
    if stills:
        print("stills written to", work)
        return
    enc.stdin.close()
    enc.wait()
    if enc.returncode:
        sys.exit("ffmpeg failed")
    print("wrote", out)


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "explainer_funky_drummer.json"))
