#!/usr/bin/env python3
"""Render a 3D stop-motion style clay short (1080x1920, 30 s):
"Did you know you can grow dreads naturally?"

Everything is procedural: a clay character, clay letters and a macro shot of
coily strands twisting into a loc are built with Blender's Python module and
rendered with Cycles. Poses are computed per frame in Python and rendered at
12 poses/s, then held for two frames each at 24 fps ("shooting on twos").
Hand-made jitter on every object, camera and light ("boil") sells the
stop-motion look.

Requires:  pip install bpy numpy   (bpy needs the matching Python, e.g. 3.13)
           ffmpeg on PATH
Usage:     python make_animation.py                 # full render + encode
           python make_animation.py --preview       # half res, few samples
           python make_animation.py --times 1,5.5   # single stills (review)
           python make_animation.py --encode-only   # re-mux existing frames
Frames already on disk are skipped, so an interrupted render resumes.
"""
import argparse
import math
import os
import random
import subprocess
import sys
import wave
import zlib

import bpy  # noqa: I001  (bpy must be imported before bmesh)
import bmesh
import numpy as np
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_PATH = os.path.join(ROOT, "fonts", "Poppins-ExtraBold.ttf")
OUT_DIR = os.path.join(ROOT, "output", "dreads")

W, H = 1080, 1920
FPS = 12                # unique poses per second
OUT_FPS = 24            # each pose is held for two frames
DURATION = 30.0
CAP_D = 6.0             # captions sit this far in front of the camera
MACRO_X = 60.0          # the macro set is built off to the side

# Clay palette (sRGB hex)
SKIN = "#8d5a3b"
HAIR = "#2a1a12"
DREAD = "#3b2619"
DREAD2 = "#4a3020"
SHIRT = "#f2b134"
PANTS = "#2f4b7c"
SHOES = "#f3efe6"
BLUSH = "#c46a58"
MOUTH = "#4a1616"
TEAL = "#5fb8b0"
PINK = "#f2a7b3"
CREAM = "#fbefd5"
YELLOW = "#ffc414"
CORAL = "#ff5f4f"
PLUM = "#3a1f2b"
RED = "#e0483e"

R_HEAD = 0.8
KEY, FILL = 1700, 450


# ---------------------------------------------------------------- helpers ---
def srgb(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def clamp01(x):
    return max(0.0, min(1.0, x))


def smooth(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, u):
    return a + (b - a) * u


def back_out(u):
    """0 -> 1 with an overshoot, like a squashed clay pop."""
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0
    c1 = 2.4
    c3 = c1 + 1
    return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


def window(t, a, b, ramp):
    """1 inside [a, b], easing in/out over `ramp` seconds."""
    return smooth((t - a) / ramp) * (1 - smooth((t - b) / ramp))


def rng(*keys):
    return random.Random(zlib.crc32(repr(keys).encode()))


def jit(key, frame, amp):
    """Per-frame hand jitter: a different nudge every pose."""
    r = rng(key, frame)
    return Vector((r.uniform(-amp, amp), r.uniform(-amp, amp), r.uniform(-amp, amp)))


def link(obj, parent=None):
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def empty(name, loc=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    o.location = loc
    return link(o, parent)


# -------------------------------------------------------------- materials ---
_mats = {}


def clay(hexcol, rough=0.6, bump=0.22, scale=5.0, name=None):
    key = (hexcol, rough, bump, scale)
    if key in _mats:
        return _mats[key]
    mat = bpy.data.materials.new(name or f"clay{len(_mats)}")
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    base = srgb(hexcol)
    dark = tuple(c * 0.78 for c in base[:3]) + (1.0,)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = 0.35

    tc = nodes.new("ShaderNodeTexCoord")
    nz = nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 6.0
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = scale * 6
    links.new(tc.outputs["Object"], nz.inputs["Vector"])
    links.new(tc.outputs["Object"], vor.inputs["Vector"])

    # Slightly blotchy colour, like kneaded clay
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = dark
    mix.inputs[7].default_value = base
    ramp = nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.35
    ramp.inputs["From Max"].default_value = 0.6
    ramp.inputs["To Min"].default_value = 0.55
    ramp.inputs["To Max"].default_value = 1.0
    links.new(nz.outputs["Fac"], ramp.inputs["Value"])
    links.new(ramp.outputs["Result"], mix.inputs[0])
    links.new(mix.outputs[2], bsdf.inputs["Base Color"])

    # Lumps + little thumb/tool dents
    add = nodes.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = 0.35
    links.new(vor.outputs["Distance"], add.inputs[0])
    links.new(nz.outputs["Fac"], add.inputs[2])
    bmp = nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.03
    links.new(add.outputs["Value"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    _mats[key] = mat
    return mat


# ----------------------------------------------------------------- meshes ---
def mesh_from_bm(name, bm, mat, parent=None):
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    return link(bpy.data.objects.new(name, me), parent)


def blob(name, r, loc, mat, scale=(1, 1, 1), parent=None, lump=0.012, segs=48):
    """A slightly irregular sphere, as if rolled between palms."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r)
    seed = Vector((zlib.crc32(name.encode()) % 97, 3.1, 7.7))
    for v in bm.verts:
        n = v.co.normalized()
        v.co += n * r * lump * noise.noise(n * 2.2 + seed) * 6
    o = mesh_from_bm(name, bm, mat, parent)
    o.location = loc
    o.scale = scale
    return o


def rounded_box(name, size, loc, mat, parent=None, bevel=0.08):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bmesh.ops.bevel(bm, geom=list(bm.verts) + list(bm.edges), offset=bevel,
                    segments=4, affect="EDGES", profile=0.5)
    o = mesh_from_bm(name, bm, mat, parent)
    o.location = loc
    return o


def cyclorama(x0, hexcol):
    """Curved paper backdrop: floor sweeping up into a wall."""
    prof = []
    for i in range(12):
        prof.append((lerp(-16, 2.0, i / 11), 0.0))
    for i in range(1, 16):
        a = -math.pi / 2 + (math.pi / 2) * i / 15
        prof.append((2.0 + 2.5 * math.cos(a), 2.5 + 2.5 * math.sin(a)))
    for i in range(1, 6):
        prof.append((4.5, lerp(2.5, 16, i / 5)))
    xs = [x0 + lerp(-16, 16, i / 8) for i in range(9)]
    bm = bmesh.new()
    grid = [[bm.verts.new((x, y, z)) for (y, z) in prof] for x in xs]
    for i in range(len(xs) - 1):
        for j in range(len(prof) - 1):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_from_bm(f"cyc{x0}", bm, clay(hexcol, rough=0.85, bump=0.06, scale=1.2))


def curve_obj(name, mat, n_splines, n_pts, bevel, parent=None, nurbs=True, res=3):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = res
    cu.use_fill_caps = True
    cu.resolution_u = 4
    for _ in range(n_splines):
        sp = cu.splines.new("NURBS" if nurbs else "POLY")
        sp.points.add(n_pts - 1)
        if nurbs:
            sp.order_u = 4
            sp.use_endpoint_u = True
    cu.materials.append(mat)
    return link(bpy.data.objects.new(name, cu), parent)


def set_spline(sp, pts, radii=None):
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
        sp.points[i].radius = radii[i] if radii else 1.0


# ---------------------------------------------------------------- letters ---
_font = None


def letter(ch, size, mat, parent):
    global _font
    if _font is None:
        _font = bpy.data.fonts.load(FONT_PATH)
    cu = bpy.data.curves.new(f"ch_{ch}", "FONT")
    cu.body = ch
    cu.font = _font
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "BOTTOM_BASELINE"
    cu.extrude = size * 0.13
    cu.bevel_depth = size * 0.045
    cu.bevel_resolution = 3
    cu.materials.append(mat)
    o = link(bpy.data.objects.new(f"L_{ch}", cu), parent)
    o.visible_shadow = False
    return o


class Caption:
    """A block of clay letters parented to the camera."""

    def __init__(self, cam, lines, t_in, t_out, y_top, style="pop", stagger=0.05):
        self.t_in, self.t_out, self.style = t_in, t_out, style
        self.letters = []   # (obj, base_local, appear_t, exit_t, tilt, idx)
        built = []
        for text, size, col in lines:
            mat = clay(col, rough=0.5, bump=0.12, scale=9.0)
            objs = [(letter(c, size, mat, cam) if c != " " else None) for c in text]
            built.append((text, size, objs))
        bpy.context.view_layer.update()
        y = y_top
        idx = 0
        max_w = 2 * CAP_D * math.tan(math.atan(18 / 50) * W / H) * 0.86
        for text, size, objs in built:
            gap = -size * 0.02
            widths = [(o.dimensions.x if o else size * 0.32) for o in objs]
            total = sum(widths) + gap * (len(objs) - 1)
            k = min(1.0, max_w / total)
            if k < 1.0:
                for o in objs:
                    if o:
                        o.data.size = size * k
                widths = [w * k for w in widths]
                total *= k
                gap *= k
            cap_h = size * k * 0.72
            y -= cap_h
            x = -total / 2
            for o, w in zip(objs, widths):
                if o:
                    r = rng("tilt", text, idx)
                    tilt = math.radians(r.uniform(-4, 4))
                    t0 = t_in + idx * stagger
                    t1 = t_out + idx * 0.025
                    self.letters.append((o, Vector((x + w / 2, y, -CAP_D)), t0, t1, tilt, idx))
                    idx += 1
                x += w + gap
            y -= size * k * 0.38
        self.pops = [l[2] for l in self.letters]

    def pose(self, t, frame):
        for o, base, t0, t1, tilt, idx in self.letters:
            if t < t0 or t > t1 + 0.35:
                o.hide_render = True
                continue
            loc = base.copy()
            sx = sy = 1.0
            if self.style == "drop":
                u = t - t0
                fall = 0.22
                if u < fall:
                    loc.y += 1.6 * (1 - (u / fall) ** 2)
                    sy, sx = 1.15, 0.9
                else:
                    v = u - fall
                    loc.y += 0.18 * abs(math.sin(v * 9)) * math.exp(-v * 7)
                    if v < 1 / FPS:
                        sy, sx = 0.72, 1.2      # squash on landing
            else:
                s = back_out((t - t0) / 0.3)
                sx = sy = s
            e = smooth((t - t1) / 0.25)
            if e > 0:
                sx *= 1 - e
                sy *= 1 - e
                loc.y += 0.25 * e
            if sx < 0.02:
                o.hide_render = True
                continue
            o.hide_render = False
            j = jit(("L", idx, self.t_in), frame, 0.006)
            o.location = loc + Vector((j.x, j.y, 0))
            o.rotation_euler = (0, 0, tilt + math.radians(jit(("Lr", idx), frame, 1.4).x))
            o.scale = (sx, sy, (sx + sy) / 2)


# -------------------------------------------------------------- character ---
def sph(az, el, r):
    """Point on the head (local), az=0/el=0 is the middle of the face (-Y)."""
    return Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * r


def hair_keep(n, strict=0.0):
    if n.z > 0.3 + strict:
        return True
    if n.y > -0.2 + strict and n.z > -0.32 + strict:
        if abs(n.x) > 0.82 and -0.4 < n.z < 0.25 and n.y < 0.35:
            return False        # leave the ears clear
        return True
    return False


class Character:
    def __init__(self):
        skin = clay(SKIN, bump=0.18)
        shirt = clay(SHIRT, bump=0.2)
        pants = clay(PANTS)
        self.root = empty("char")
        self.body = blob("body", 1.0, (0, 0, 0.98), shirt, (0.62, 0.5, 0.62), self.root)
        for s in (-1, 1):
            blob(f"leg{s}", 1.0, (0.24 * s, 0, 0.42), pants, (0.2, 0.2, 0.34), self.root)
            blob(f"shoe{s}", 1.0, (0.26 * s, -0.1, 0.1), clay(SHOES), (0.22, 0.32, 0.13), self.root)
        blob("neck", 0.26, (0, 0, 1.5), skin, parent=self.root)
        self.arms = {}
        for s in (-1, 1):
            arm = curve_obj(f"arm{s}", shirt, 1, 4, 0.13, self.root)
            hand = blob(f"hand{s}", 0.14, (0, 0, 0), skin, parent=self.root)
            self.arms[s] = (arm, hand)

        self.head = empty("head", (0, 0, 2.05), self.root)
        hd = self.head
        blob("skull", R_HEAD, (0, 0, 0), skin, parent=hd, segs=72, lump=0.006)
        for s in (-1, 1):
            blob(f"ear{s}", 1.0, (0.79 * s, 0.05, -0.08), skin, (0.08, 0.13, 0.18), hd)
            blob(f"cheek{s}", 1.0, sph(0.55 * s, -0.22, R_HEAD - 0.03), clay(BLUSH),
                 (0.11, 0.05, 0.08), hd)
        blob("nose", 0.12, sph(0, -0.12, R_HEAD + 0.02), skin, (1, 0.85, 0.85), hd)

        white = clay("#fbf8f0", rough=0.35, bump=0.05)
        black = clay("#140d0a", rough=0.25, bump=0.03)
        self.eyes = {}
        for s in (-1, 1):
            c = sph(0.33 * s, 0.12, R_HEAD - 0.07)
            ew = blob(f"eye{s}", 0.17, c, white, parent=hd)
            pu = blob(f"pupil{s}", 0.085, c, black, parent=hd)
            hl = blob(f"glint{s}", 0.024, c, white, parent=hd)
            self.eyes[s] = (ew, pu, hl, c)
        self.brows = {s: curve_obj(f"brow{s}", clay(HAIR), 1, 5, 0.038, hd) for s in (-1, 1)}
        self.mouth = curve_obj("mouth", clay(MOUTH, rough=0.4), 1, 7, 0.034, hd)
        self.mouth_o = blob("mouth_o", 1.0, sph(0, -0.36, R_HEAD - 0.02), clay(MOUTH, rough=0.4),
                            (0.1, 0.05, 0.12), hd)

        # Short coily hair: a nubby clay cap
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=128, v_segments=64, radius=1.0)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not hair_keep(v.co.normalized())],
                         context="VERTS")
        for v in bm.verts:
            n = v.co.normalized()
            f1 = noise.voronoi(n * 9.0, distance_metric="DISTANCE")[0][0]
            bump = max(0.0, 1 - f1 * 1.7) ** 1.5
            v.co = n * (R_HEAD + 0.015 + 0.07 * bump + 0.015 * noise.noise(n * 4))
        cap = mesh_from_bm("hair_cap", bm, clay(HAIR, bump=0.35, scale=14), hd)
        sol = cap.modifiers.new("solid", "SOLIDIFY")
        sol.thickness = 0.05
        sol.offset = -1
        cap.modifiers.new("sub", "SUBSURF").levels = 1

        # Dread anchors on the scalp (Fibonacci sphere, filtered)
        self.anchors = []
        N = 120
        for i in range(N):
            z = 1 - 2 * (i + 0.5) / N
            rr = math.sqrt(1 - z * z)
            a = i * math.pi * (3 - math.sqrt(5))
            n = Vector((rr * math.cos(a), rr * math.sin(a), z))
            if hair_keep(n, strict=0.06) and not (n.y < -0.3 and abs(n.x) < 0.45 and n.z < 0.8):
                r = rng("dread", i)
                self.anchors.append((n, r.uniform(0.8, 1.2), r.uniform(0, 6.28), r.uniform(0, 6.28)))
        self.M = 12
        self.dreads = curve_obj("dreads", clay(DREAD, bump=0.4, scale=9), len(self.anchors),
                                self.M, 0.09, hd)
        self.dreads2_idx = None

    # ---- per-frame posing --------------------------------------------------
    def pose(self, t, frame, st):
        hd = self.head
        hd.location = Vector((0, 0, 2.05 + st["bob"])) + jit("head", frame, 0.004)
        hd.rotation_euler = (st["nod"], 0, st["tilt"])

        for s in (-1, 1):
            ew, pu, hl, c = self.eyes[s]
            open_ = st["wink"] if s == 1 else 1.0
            open_ *= st["blink"]
            sz = st["eye_size"]
            ew.scale = (sz, sz, sz * max(0.12, open_))
            n = c.normalized()
            look = Vector((st["look"][0], 0, st["look"][1]))
            pdir = (n + look * 0.55).normalized()
            pc = c + pdir * 0.17 * sz * 0.86
            pu.location = pc
            pu.scale = (sz, sz * 0.7, sz * max(0.1, open_))
            pu.hide_render = open_ < 0.3
            hl.location = pc + Vector((0.03, -0.06, 0.035)) * sz
            hl.hide_render = open_ < 0.3
            # brows
            br = st["brow"]
            pts = [sph((0.33 + lerp(-0.13, 0.13, k / 4)) * s, 0.36 + br - 0.03 * ((k / 2 - 1) ** 2) * (1 - br * 3),
                       R_HEAD + 0.005) for k in range(5)]
            set_spline(self.brows[s].data.splines[0], pts)

        sm = st["smile"]
        mpts = [sph(lerp(-0.26, 0.26, k / 6), -0.34 + sm * 0.13 * (abs(lerp(-1, 1, k / 6)) ** 2) - sm * 0.02,
                    R_HEAD + 0.005) for k in range(7)]
        set_spline(self.mouth.data.splines[0], mpts)
        self.mouth.hide_render = st["mouth_o"] > 0.5
        self.mouth_o.hide_render = st["mouth_o"] <= 0.5

        # noodle arms
        for s in (-1, 1):
            arm, hand = self.arms[s]
            phi, bend = st["arm"][s]
            S = Vector((0.42 * s, 0, 1.28))
            E = S + 0.45 * Vector((math.sin(phi) * s, -0.05, -math.cos(phi)))
            Hh = E + 0.42 * Vector((math.sin(phi + bend) * s, -0.08, -math.cos(phi + bend)))
            mid = (S + E) / 2
            set_spline(arm.data.splines[0], [S, mid, E, Hh], [1.0, 0.95, 0.9, 0.85])
            hand.location = Hh + (Hh - E).normalized() * 0.08
        self.pose_dreads(t, frame, st["dread_len"], st["sway"])

    def pose_dreads(self, t, frame, L, sway):
        cu = self.dreads.data
        self.dreads.hide_render = L < 0.03
        if L < 0.03:
            return
        thick = 0.55 + 0.45 * min(1.0, L / 0.6)
        down = Vector((0, 0, -1))
        for i, (n, lf, ph, ph2) in enumerate(self.anchors):
            Li = L * lf * (0.72 if n.y < -0.1 else 1.0)
            ds = Li / (self.M - 1)
            p = n * (R_HEAD + 0.02)
            bias = Vector((math.copysign(0.9, n.x if abs(n.x) > 1e-3 else 1), 0.7, 0.25)) if n.y < 0.05 else Vector()
            # long locs drape over the scalp; short buds stick straight out
            tang = down - n * down.dot(n)
            if tang.length < 1e-3:
                tang = Vector((n.x, n.y, 0)) if n.xy.length > 1e-3 else Vector((0, 1, 0))
            out = lerp(1.0, 0.3, min(1.0, L / 0.8))
            d = (n * out + tang.normalized() * (1 - out) + bias).normalized()
            sw = Vector((sway * math.sin(t * 5.2 + ph), sway * 0.5 * math.cos(t * 4.1 + ph2), 0))
            j = jit(("dr", i), frame, 0.06)
            pts, radii = [], []
            for k in range(self.M):
                s = k / (self.M - 1)
                if k:
                    d = (d + down * 2.6 * ds + (sw + j) * ds * 1.5).normalized()
                    p = p + d * ds
                    if p.length < R_HEAD + 0.085:
                        p = p.normalized() * (R_HEAD + 0.085)
                    if p.y < -0.2 and abs(p.x) < 0.68 and p.z < 0.6:
                        p.x = math.copysign(0.68, p.x if abs(p.x) > 1e-3 else n.x)
                pts.append(p.copy())
                r = (0.8 + 0.2 * min(1, s * 4)) * (1 + 0.17 * math.sin(k * 2.3 + ph) + 0.08 * math.sin(k * 5.1 + ph2))
                if s > 0.82:
                    r *= 1 - (s - 0.82) / 0.18 * 0.35
                radii.append(r * thick)
            set_spline(cu.splines[i], pts, radii)


# ------------------------------------------------------------- macro set ---
class Strands:
    """Coily strands (and shed hairs) that twist together into a loc."""

    def __init__(self):
        self.root = empty("macro", (MACRO_X, 0, 0))
        self.main = [(k * 2 * math.pi / 5, 0.0, 8.5, 1.95 + 0.22 * (k % 3)) for k in range(5)]
        # shed hairs: (angle, fall-start time, top z, bottom z)
        self.shed = [(0.6, 12.9, 6.3, 2.6), (2.9, 13.5, 5.6, 1.9), (4.6, 14.1, 6.8, 3.0)]
        self.P = 170
        mats = [clay(DREAD, bump=0.3, scale=12), clay(DREAD2, bump=0.3, scale=12)]
        self.objs = []
        for i in range(len(self.main) + len(self.shed)):
            o = curve_obj(f"strand{i}", mats[i % 2], 1, self.P, 0.05, self.root, nurbs=False, res=2)
            self.objs.append(o)

    def pose(self, t, frame):
        # 0 = loose separate coils, 1 = one tight lumpy loc
        g = smooth((t - 15.2) / 4.0)
        tw = smooth((t - 10.5) / 9.5)
        Rb = lerp(0.62, 0.11, g)
        tau = lerp(0.15, 1.9, tw)
        spin = 0.5 * t + 3.0 * tw
        rc = lerp(0.12, 0.05, g)
        thick = lerp(0.045, 0.13, smooth((t - 16.6) / 3.5))
        everyone = [(a, 0.0, top, bot, False) for (a, _, top, bot) in self.main] + \
                   [(a, ts, top, bot, True) for (a, ts, top, bot) in self.shed]
        for i, (a, ts, top, bot, is_shed) in enumerate(everyone):
            o = self.objs[i]
            fall = 0.0
            rb = Rb
            if is_shed:
                u = clamp01((t - ts) / 0.9)
                if t < ts:
                    o.hide_render = True
                    continue
                fall = 6.5 * (1 - smooth(u)) ** 1.5
                rb = Rb + 0.9 * (1 - smooth(u))
            o.hide_render = False
            pts, radii = [], []
            j = jit(("st", i), frame, 0.012)
            for k in range(self.P):
                z = lerp(top, bot, k / (self.P - 1))
                ang = a + tau * z + spin
                axis = Vector((rb * math.cos(ang), rb * math.sin(ang), z + fall))
                ca = 2 * math.pi * 2.6 * z + a * 3
                coil = Vector((rc * math.cos(ca), rc * math.sin(ca), 0))
                pts.append(axis + coil + j)
                s = k / (self.P - 1)
                taper = 1 - 0.55 * max(0.0, (s - 0.85) / 0.15)
                if is_shed:
                    taper *= 1 - 0.55 * max(0.0, (0.15 - s) / 0.15)
                lump = 1 + g * 0.25 * math.sin(z * 9 + a * 2)
                radii.append(taper * lump)
            o.data.bevel_depth = thick
            set_spline(o.data.splines[0], pts, radii)


# --------------------------------------------------------------- calendar ---
class Calendar:
    def __init__(self):
        self.root = empty("calendar", (1.22, -0.45, 0))
        rounded_box("cal_body", (0.78, 0.3, 0.92), (0, 0, 0.46), clay(CREAM, bump=0.1), self.root)
        rounded_box("cal_top", (0.8, 0.32, 0.22), (0, 0, 0.86), clay(RED, bump=0.1), self.root, bevel=0.06)
        for s in (-1, 1):
            blob(f"ring{s}", 0.05, (0.2 * s, -0.12, 0.98), clay("#888888", rough=0.3), (1, 1, 1.6), self.root)
        dark = clay(PLUM, rough=0.5, bump=0.08)
        self.label = self._text("MONTH", 0.15, (0, -0.17, 0.8), clay(CREAM, bump=0.05))
        self.nums = {n: self._text(n, 0.56 if len(n) == 1 else 0.48, (0, -0.16, 0.22), dark)
                     for n in ("1", "6", "12")}

    def _text(self, s, size, loc, mat):
        cu = bpy.data.curves.new("cal_" + s, "FONT")
        cu.body = s
        cu.font = _font or bpy.data.fonts.load(FONT_PATH)
        cu.size = size
        cu.align_x = "CENTER"
        cu.align_y = "BOTTOM_BASELINE"
        cu.extrude = 0.02
        cu.bevel_depth = 0.008
        cu.materials.append(mat)
        o = link(bpy.data.objects.new("cal_" + s, cu), self.root)
        o.location = loc
        o.rotation_euler = (math.pi / 2, 0, 0)
        return o


# --------------------------------------------------------------- timeline ---
MONTHS = [("1", 21.6, 0.3), ("6", 23.1, 0.8), ("12", 24.6, 1.35)]


def month_state(t):
    cur, ln = None, 0.3
    prev = 0.3
    for name, t0, L in MONTHS:
        if t >= t0:
            cur = name
            ln = lerp(prev, L, smooth((t - t0) / 0.4))
            prev = L
    return cur, ln


def char_state(t):
    st = dict(bob=0.0, nod=0.0, tilt=0.0, look=(0.0, 0.0), blink=1.0, wink=1.0, eye_size=1.0,
              brow=0.0, smile=0.6, mouth_o=0.0, arm={-1: (0.25, 0.15), 1: (0.25, 0.15)},
              dread_len=0.0, sway=0.15)
    st["bob"] = 0.02 * math.sin(t * 2.2)
    st["tilt"] = 0.04 * math.sin(t * 0.9)
    for b in (2.3, 6.9, 23.8):
        if b <= t < b + 1.5 / FPS:
            st["blink"] = 0.1
    if t < 4.0:
        st["look"] = (0.0, 0.55 * window(t, 0.4, 3.4, 0.3))
        st["nod"] = -0.12 * window(t, 0.4, 3.4, 0.3)
    elif t < 9.0:
        surprise = window(t, 4.6, 6.6, 0.15)
        st["mouth_o"] = surprise
        st["eye_size"] = 1 + 0.18 * surprise
        st["brow"] = 0.08 * surprise
        st["smile"] = 0.6 + 0.4 * smooth((t - 6.6) / 0.3)
        st["dread_len"] = 0.55 * smooth((t - 4.9) / 2.4)
        st["look"] = (0.0, 0.25 * surprise)
        st["sway"] = 0.15 + 0.4 * surprise
        st["arm"] = {s: (0.25 + 0.5 * surprise, 0.15 + 0.6 * surprise) for s in (-1, 1)}
    elif t >= 21.0:
        cur, ln = month_state(t)
        st["dread_len"] = ln if t >= MONTHS[0][1] else 0.3
        st["look"] = (0.45 * window(t, 21.8, 25.6, 0.25), -0.05)
        st["tilt"] += 0.08 * window(t, 21.8, 25.6, 0.25)
        for _, t0, _ in MONTHS[1:]:
            if t0 <= t < t0 + 0.6:
                st["eye_size"] = 1.12
                st["brow"] = 0.05
        if t >= 26.0:
            st["dread_len"] = 1.35
            st["smile"] = 1.0
            st["bob"] = 0.06 * abs(math.sin(t * 4.2))
            st["sway"] = 0.55
            w = smooth((t - 26.3) / 0.4)
            st["arm"][1] = (lerp(0.25, 2.0, w), lerp(0.15, 0.6 + 0.45 * math.sin(t * 9), w))
            if 28.0 <= t < 28.5:
                st["wink"] = 0.1
    return st


def camera_state(t):
    def mv(a, b, u):
        return Vector(a).lerp(Vector(b), u)
    if t < 8.5:
        return mv((0, -8.2, 2.75), (0, -7.7, 2.75), smooth((t - 4) / 4.5)), 50
    if t < 9.0:
        u = ((t - 8.5) / 0.5) ** 2
        return mv((0, -7.7, 2.75), (0, -2.6, 3.0), u), lerp(50, 70, u)
    if t < 9.6:
        u = smooth((t - 9.0) / 0.6)
        return mv((MACRO_X, -5.0, 3.2), (MACRO_X, -8.2, 2.9), u), 50
    if t < 20.4:
        return mv((MACRO_X, -8.2, 2.9), (MACRO_X, -7.4, 2.9), smooth((t - 9.6) / 10.8)), 50
    if t < 20.9:
        u = ((t - 20.4) / 0.5) ** 2
        return mv((MACRO_X, -7.4, 2.9), (MACRO_X, -3.0, 3.2), u), lerp(50, 70, u)
    if t < 21.5:
        u = smooth((t - 20.9) / 0.6)
        return mv((0.35, -4.5, 2.6), (0.35, -8.6, 2.75), u), 50
    if t < 26.0:
        return mv((0.35, -8.6, 2.75), (0.35, -8.2, 2.7), smooth((t - 21.5) / 4.5)), 50
    return mv((0.35, -8.2, 2.7), (0.1, -7.8, 2.7), smooth((t - 26) / 3)), 50


# ------------------------------------------------------------------ scene ---
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 3
    sc.cycles.diffuse_bounces = 1
    sc.cycles.glossy_bounces = 1
    sc.cycles.transparent_max_bounces = 2
    sc.cycles.adaptive_threshold = 0.04
    sc.render.use_persistent_data = True
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass

    world = bpy.data.worlds.new("w")
    sc.world = world
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = srgb("#cfe8e4")
    bg.inputs["Strength"].default_value = 0.35

    cam_data = bpy.data.cameras.new("cam")
    cam_data.sensor_fit = "VERTICAL"
    cam_data.sensor_height = 36
    cam = link(bpy.data.objects.new("cam", cam_data))
    cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.camera = cam

    tgt = empty("light_target", (0, 0, -10), cam)
    lights = {}
    for name, loc, size, energy in (("key", (-4.5, 4.5, 1.5), 5.0, KEY),
                                    ("fill", (5.5, 0.5, 0.5), 7.0, FILL)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.size = size
        ld.energy = energy
        lo = link(bpy.data.objects.new(name, ld), cam)
        lo.location = loc
        c = lo.constraints.new("TRACK_TO")
        c.target = tgt
        c.track_axis = "TRACK_NEGATIVE_Z"
        c.up_axis = "UP_Y"
        lights[name] = lo
    for x0 in (0.0, MACRO_X):
        ld = bpy.data.lights.new(f"rim{x0}", "AREA")
        ld.size = 4
        ld.energy = 500
        lo = link(bpy.data.objects.new(f"rim{x0}", ld))
        lo.location = (x0 + 1.5, 3.0, 6.5)
        c = lo.constraints.new("TRACK_TO")
        c.target = empty(f"rim_t{x0}", (x0, 0, 2.2))
        c.track_axis = "TRACK_NEGATIVE_Z"
        c.up_axis = "UP_Y"

    cyclorama(0.0, TEAL)
    cyclorama(MACRO_X, PINK)

    world_objs = dict(cam=cam, lights=lights, char=Character(), strands=Strands(),
                      cal=Calendar())
    caps = [
        Caption(cam, [("DID YOU", 0.5, CREAM), ("KNOW?", 0.66, YELLOW)], 0.3, 3.55, 1.75,
                style="drop", stagger=0.11),
        Caption(cam, [("YOU CAN GROW", 0.3, CREAM), ("DREADS", 0.58, YELLOW),
                      ("NATURALLY!", 0.4, CREAM)], 4.2, 8.15, 1.8),
        Caption(cam, [("COILY HAIR", 0.36, PLUM), ("WRAPS AROUND ITSELF", 0.2, PLUM)],
                9.5, 12.45, -0.85),
        Caption(cam, [("WE SHED ~100 HAIRS A DAY", 0.17, PLUM), ("SKIP THE COMB AND", 0.25, PLUM),
                      ("THEY GET TRAPPED", 0.3, CORAL)], 12.7, 16.4, -0.75),
        Caption(cam, [("THEY TANGLE", 0.34, PLUM), ("INTO A LOC", 0.4, CORAL)], 16.7, 20.3, -0.8),
        Caption(cam, [("GIVE IT", 0.3, CREAM), ("TIME...", 0.5, YELLOW)], 21.6, 25.7, 1.8),
        Caption(cam, [("FREEFORM", 0.5, YELLOW), ("LOCS", 0.66, CREAM),
                      ("A.K.A. NATURAL DREADS", 0.17, CREAM)], 26.1, 31.0, 1.85),
    ]
    world_objs["caps"] = caps
    return world_objs


def pose(S, t, frame):
    cam = S["cam"]
    loc, lens = camera_state(t)
    cam.location = loc + jit("cam", frame, 0.006)
    cam.rotation_euler = (math.pi / 2 + jit("camr", frame, 0.0015).x, 0, jit("camr", frame, 0.0015).y)
    cam.data.lens = lens
    for name, base in (("key", KEY), ("fill", FILL)):
        S["lights"][name].data.energy = base * (1 + rng("flick", frame).uniform(-0.035, 0.035))

    S["char"].pose(t, frame, char_state(t))
    S["strands"].pose(t, frame)

    cal = S["cal"]
    cur, _ = month_state(t)
    vis = 21.4 <= t < 26.2
    s = back_out((t - 21.4) / 0.35) * (1 - smooth((t - 25.9) / 0.3))
    cal.root.scale = (s, s, s) if vis else (0, 0, 0)
    cal.root.rotation_euler = (0, 0, -0.3 + jit("cal", frame, 0.01).z)
    for name, o in cal.nums.items():
        o.hide_render = not vis or name != cur
        if name == cur:
            t0 = dict((n, a) for n, a, _ in MONTHS)[name]
            sq = back_out((t - t0) / 0.3)
            o.scale = (1, max(0.05, sq), 1)
    cal.label.hide_render = not vis
    for c in S["caps"]:
        c.pose(t, frame)


# ------------------------------------------------------------------ audio ---
SR = 44100


def synth_audio(S, path):
    n = int(SR * (DURATION + 0.5))
    mix = np.zeros(n)

    def put(sig, t, gain):
        i = int(t * SR)
        if i >= n:
            return
        seg = sig[: n - i] * gain
        mix[i:i + len(seg)] += seg

    def tone(f, dur, decay):
        tt = np.arange(int(dur * SR)) / SR
        env = np.exp(-tt * decay) * np.minimum(1, tt * 400)
        return env * (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(4 * np.pi * f * tt)
                      + 0.12 * np.sin(6 * np.pi * f * tt))

    # Plucky marimba-ish loop, 120 bpm: C - Am - F - G
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [(60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62)]
    beat = 0.5
    t = 0.0
    bar = 0
    while t < DURATION:
        ch = chords[bar % 4]
        put(tone(midi(ch[0] - 24), 0.9, 4), t, 0.22)
        put(tone(midi(ch[0] - 24), 0.9, 4), t + 2 * beat, 0.18)
        arp = [ch[0], ch[1], ch[2], ch[1] + 12, ch[2], ch[1], ch[0] + 12, ch[2]]
        for k, m in enumerate(arp):
            put(tone(midi(m + 12), 0.4, 9), t + k * beat / 2, 0.07 if k % 2 else 0.1)
        for k in range(4):
            tick = np.random.default_rng(k + bar).normal(0, 1, int(0.03 * SR))
            tick *= np.exp(-np.arange(len(tick)) / SR * 160)
            put(np.diff(tick, prepend=0), t + k * beat + beat / 2, 0.05)
        t += 4 * beat
        bar += 1
    # fade the music under the end card and out
    tt = np.arange(n) / SR
    mix *= np.clip((DURATION - tt) / 1.5, 0, 1)

    rgen = np.random.default_rng(7)
    for c in S["caps"]:
        for k, tp in enumerate(c.pops):
            f0 = rgen.uniform(500, 900)
            d = 0.07
            tt2 = np.arange(int(d * SR)) / SR
            f = f0 * np.exp(-tt2 * 18)
            sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt2 * 45)
            put(sig, tp + (0.2 if c.style == "drop" else 0.04), 0.18)
    for tw in (8.5, 20.4):          # whooshes into / out of the macro shot
        d = 0.6
        sig = rgen.normal(0, 1, int(d * SR))
        k = 60
        sig = np.convolve(sig, np.ones(k) / k, mode="same")
        tt2 = np.arange(len(sig)) / SR
        put(sig * np.sin(np.pi * tt2 / d) ** 2, tw, 2.5)
    for _, t0, _ in MONTHS:          # calendar page "thock"
        put(tone(140, 0.25, 22), t0, 0.5)

    mix /= max(1.0, np.abs(mix).max() / 0.9)
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------- main ---
def main():
    argv = sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="half resolution, low samples")
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--scale", type=int, default=67, help="render resolution %%; upscaled on encode")
    ap.add_argument("--frames", default="", help="A:B range of pose indices")
    ap.add_argument("--times", default="", help="comma separated seconds to render as stills")
    ap.add_argument("--encode-only", action="store_true")
    ap.add_argument("--no-encode", action="store_true")
    a = ap.parse_args(argv)

    os.makedirs(OUT_DIR, exist_ok=True)
    frames_dir = os.path.join(OUT_DIR, "frames_preview" if a.preview else "frames")
    os.makedirs(frames_dir, exist_ok=True)
    S = build()
    sc = bpy.context.scene
    sc.cycles.samples = 12 if a.preview else a.samples
    sc.render.resolution_percentage = 50 if a.preview else a.scale

    total = int(DURATION * FPS)
    if a.times:
        for ts in a.times.split(","):
            tv = float(ts)
            f = int(round(tv * FPS))
            pose(S, tv, f)
            sc.render.filepath = os.path.join(OUT_DIR, f"still_{tv:05.2f}.png")
            bpy.ops.render.render(write_still=True)
        return
    if not a.encode_only:
        lo, hi = 0, total
        if a.frames:
            lo, hi = (int(x) for x in a.frames.split(":"))
        for f in range(lo, hi):
            out = os.path.join(frames_dir, f"f_{f:04d}.png")
            if os.path.exists(out):
                continue
            pose(S, f / FPS, f)
            sc.render.filepath = out
            bpy.ops.render.render(write_still=True)
            print(f"frame {f + 1}/{total}", flush=True)
    if a.no_encode:
        return
    audio = os.path.join(OUT_DIR, "audio.wav")
    synth_audio(S, audio)
    mp4 = os.path.join(OUT_DIR, "dreads_naturally_preview.mp4" if a.preview else "dreads_naturally.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(FPS), "-i", os.path.join(frames_dir, "f_%04d.png"),
        "-i", audio,
        "-vf", f"fps={OUT_FPS},scale={W}:{H}:flags=lanczos,noise=alls=5:allf=t,vignette=PI/5",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", mp4,
    ], check=True)
    print("wrote", mp4)


if __name__ == "__main__":
    main()
