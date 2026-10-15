"""Builds the "POV: Playing Hide and Seek With Friends" Roblox-style skit in
Blender (bpy) and renders its frames with Cycles.

    python3 build_scene.py --out frames/                 # every frame (resumable)
    python3 build_scene.py --out stills/ --stills 60,420 # a few test frames
"""

import argparse
import math
import os
import random
import sys

import bpy  # must come before bmesh
import bmesh
from bpy_extras import anim_utils
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import faces  # noqa: E402

FONT = os.path.join(HERE, "..", "fonts", "Poppins-Bold.ttf")
FPS = 30
END = 960            # total frames (32 s)
CARD = (810, 840)    # "3 hours later..." card, drawn by compose.py, not rendered
NIGHT = 840
TAU = 2 * math.pi
PREFS = bpy.context.preferences.edit
TEX = None           # texture cache dir, set in main()

# ---------------------------------------------------------------- keyframes
_state = {}


def _val(v):
    return tuple(v) if hasattr(v, "__len__") else v


def key(obj, prop, f, value, interp="BEZIER"):
    PREFS.keyframe_new_interpolation_type = interp
    setattr(obj, prop, value)
    obj.keyframe_insert(prop, frame=f)
    # the interpolation preference is ignored for non-object data, so set it explicitly
    ad = obj.id_data.animation_data
    path = obj.path_from_id(prop)
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    for fc in bag.fcurves:
        if fc.data_path == path:
            for kp in fc.keyframe_points:
                if abs(kp.co.x - f) < 1e-3:
                    kp.interpolation = interp
    _state[(obj.as_pointer(), prop)] = _val(value)


def cur(obj, prop):
    k = (obj.as_pointer(), prop)
    if k not in _state:
        _state[k] = _val(getattr(obj, prop))
    return _state[k]


def move(obj, prop, f0, f1, value, interp="BEZIER"):
    key(obj, prop, f0, cur(obj, prop), interp)
    key(obj, prop, f1, value, interp)


def switch(obj, prop, f, day, night):
    """Day value until NIGHT, then night value (hard cut)."""
    key(obj, prop, 0, day, "CONSTANT")
    key(obj, prop, f, night, "CONSTANT")


# ---------------------------------------------------------------- materials
def lin(c):
    return tuple(x ** 2.2 for x in c)


def _new_mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes["Principled BSDF"]


def mat(name, color, rough=0.55, emit=0.0):
    m, _, _, b = _new_mat(name)
    b.inputs["Base Color"].default_value = (*lin(color), 1)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*lin(color), 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def ramp_mat(name, tex_node, c1, c2, rough=0.6, setup=None, pos=0.5, constant=False):
    m, n, l, b = _new_mat(name)
    tc = n.new("ShaderNodeTexCoord")
    tex = n.new(tex_node)
    if setup:
        setup(tex)
    ramp = n.new("ShaderNodeValToRGB")
    if constant:
        ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].color = (*lin(c1), 1)
    ramp.color_ramp.elements[1].position = pos
    ramp.color_ramp.elements[1].color = (*lin(c2), 1)
    l.new(tc.outputs["Object"], tex.inputs["Vector"])
    l.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    return m


def image_mat(name, path, emit=0.0):
    m, n, l, b = _new_mat(name)
    t = n.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path)
    l.new(t.outputs["Color"], b.inputs["Base Color"])
    l.new(t.outputs["Alpha"], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.8
    if emit:
        l.new(t.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emit
    return m


# ---------------------------------------------------------------- meshes
def link(ob, parent=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def empty(name, parent=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    return link(bpy.data.objects.new(name, None), parent, loc, rot)


def mesh(name, bm, m, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    me.materials.append(m)
    return link(bpy.data.objects.new(name, me), parent, loc, rot)


def box(name, dims, m, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), bevel=0.0, segs=3):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * dims[0], v.co.y * dims[1], v.co.z * dims[2]))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, offset_type="OFFSET",
                        segments=segs, profile=0.5, affect="EDGES")
    return mesh(name, bm, m, parent, loc, rot)


def cyl(name, r1, r2, h, m, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), segs=16):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r1,
                          radius2=r2, depth=h)
    return mesh(name, bm, m, parent, loc, rot, smooth=segs > 8)


def ball(name, r, m, parent=None, loc=(0, 0, 0), sub=1, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    ob = mesh(name, bm, m, parent, loc)
    ob.scale = scale
    return ob


def plane(name, w, h, m, parent=None, loc=(0, 0, 0), rot=(0, 0, 0)):
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new()
    vs = [bm.verts.new((x * w / 2, y * h / 2, 0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    f = bm.faces.new(vs)
    for lp, co in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uv].uv = co
    return mesh(name, bm, m, parent, loc, rot)


def prism(name, w, d, h, m, loc):
    """Gable roof: triangular prism along X, base at loc z."""
    bm = bmesh.new()
    pts = [(-d / 2, 0), (d / 2, 0), (0, h)]
    a = [bm.verts.new((-w / 2, y, z)) for y, z in pts]
    b = [bm.verts.new((w / 2, y, z)) for y, z in pts]
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return mesh(name, bm, m, None, loc)


# ---------------------------------------------------------------- characters
BLINKABLE = {"smile", "look_l", "look_r"}


def face_png(name):
    path = os.path.join(TEX, f"face_{name}.png")
    if not os.path.exists(path):
        faces.face(name).save(path)
    return path


class Char:
    def __init__(self, name, skin, shirt, pants, sleeves=None, shirt_mat=None,
                 shoes=(0.16, 0.16, 0.18)):
        self.name = name
        self.face_events = []
        self.root = empty(name)
        self.hip = empty(name + "_hip", self.root, (0, 0, 2))
        m_skin = mat(name + "_skin", skin, 0.45)
        m_shirt = shirt_mat or mat(name + "_shirt", shirt, 0.6)
        m_sleeve = mat(name + "_sleeve", sleeves, 0.6) if sleeves else m_skin
        m_pants = mat(name + "_pants", pants, 0.65)
        m_shoes = mat(name + "_shoes", shoes, 0.5)

        box(name + "_torso", (2, 1, 2), m_shirt, self.hip, (0, 0, 1), bevel=0.06)
        self.neck = empty(name + "_neck", self.hip, (0, 0, 2))
        box(name + "_head", (1.25, 1.15, 1.15), m_skin, self.neck, (0, 0, 0.6), bevel=0.24, segs=4)
        for side, x in (("R", -1.5), ("L", 1.5)):
            arm = empty(f"{name}_arm{side}", self.hip, (x, 0, 1.75))
            box(f"{name}_sleeve{side}", (0.98, 0.98, 1.5), m_sleeve, arm, (0, 0, -0.5), bevel=0.06)
            box(f"{name}_hand{side}", (0.96, 0.96, 0.5), m_skin, arm, (0, 0, -1.5), bevel=0.08)
            setattr(self, "arm" + side, arm)
            leg = empty(f"{name}_leg{side}", self.hip, (x / 3, 0, 0))
            box(f"{name}_pant{side}", (0.98, 0.98, 1.66), m_pants, leg, (0, 0, -0.83), bevel=0.05)
            box(f"{name}_shoe{side}", (1.0, 1.04, 0.36), m_shoes, leg, (0, -0.02, -1.82), bevel=0.08)
            setattr(self, "leg" + side, leg)

        self.faces = {}
        for n in faces.FACES:
            ob = plane(f"{name}_face_{n}", 1, 1, image_mat(f"{name}_face_{n}", face_png(n)),
                       self.neck, (0, -0.582, 0.62), (math.pi / 2, 0, 0))
            ob.visible_shadow = False
            self.faces[n] = ob

    def spiky_hair(self, color, seed, n=16):
        m = mat(self.name + "_hair", color, 0.5)
        rnd = random.Random(seed)
        box(self.name + "_cap", (1.36, 1.27, 0.42), m, self.neck, (0, 0.03, 1.12), bevel=0.14)
        box(self.name + "_back", (1.36, 0.16, 0.95), m, self.neck, (0, 0.6, 0.78), bevel=0.06)
        for i in range(n):
            x, y = rnd.uniform(-0.5, 0.5), rnd.uniform(-0.35, 0.5)
            cyl(f"{self.name}_spike{i}", 0.24, 0, rnd.uniform(0.6, 0.9), m, self.neck,
                (x, y, 1.52), (-y * 1.3 + rnd.uniform(-0.2, 0.2), x * 1.3, 0), segs=5)
        for i, x in enumerate((-0.42, -0.14, 0.14, 0.42)):
            cyl(f"{self.name}_bang{i}", 0.2, 0, 0.62, m, self.neck,
                (x, -0.62, 1.12), (1.95, x * 0.6, 0), segs=5)

    # --- animation helpers
    def set(self, f, interp="BEZIER", **rots):
        for j, r in rots.items():
            key(getattr(self, j), "rotation_euler", f, r, interp)

    def pose(self, f0, f1, **rots):
        for j, r in rots.items():
            move(getattr(self, j), "rotation_euler", f0, f1, r)

    def turn(self, f0, f1, angle):
        move(self.root, "rotation_euler", f0, f1, (0, 0, angle))

    def goto(self, f0, f1, x=None, y=None, z=None, interp="LINEAR"):
        cx, cy, cz = cur(self.root, "location")
        move(self.root, "location", f0, f1,
             (cx if x is None else x, cy if y is None else y, cz if z is None else z), interp)

    def place(self, f, x, y, z=0.0, angle=None):
        key(self.root, "location", f, (x, y, z), "LINEAR")
        if angle is not None:
            key(self.root, "rotation_euler", f, (0, 0, angle))

    def teleport(self, f, x, y, z):
        key(self.root, "location", f - 1, cur(self.root, "location"), "CONSTANT")
        key(self.root, "location", f, (x, y, z), "CONSTANT")

    def cycle(self, f0, f1, period, amp, bob=0.12):
        """Walk/run limb swing between f0 and f1, ending at rest."""
        half, s, f = period / 2, 1, float(f0)
        while f < f1 - half / 2:
            self.set(round(f), legR=(-amp * s, 0, 0), legL=(amp * s, 0, 0),
                     armR=(amp * s * 0.9, 0, 0), armL=(-amp * s * 0.9, 0, 0))
            key(self.hip, "location", round(f), (0, 0, 2))
            key(self.hip, "location", round(f + half / 2), (0, 0, 2 + bob))
            s, f = -s, f + half
        rest = (0, 0, 0)
        self.set(f1, legR=rest, legL=rest, armR=rest, armL=rest)
        key(self.hip, "location", f1, (0, 0, 2))

    def face(self, f, name):
        self.face_events.append((f, name))

    def finalize_faces(self, rnd):
        ev = sorted(self.face_events)
        out = []
        for i, (f, n) in enumerate(ev):
            out.append((f, n))
            nxt = ev[i + 1][0] if i + 1 < len(ev) else END
            if n in BLINKABLE:
                b = f + rnd.randint(35, 60)
                while b + 4 < nxt - 8:
                    out += [(b, "blink"), (b + 3, n)]
                    b += rnd.randint(70, 110)
        for f, n in sorted(out):
            for fn, ob in self.faces.items():
                key(ob, "hide_render", f, fn != n, "CONSTANT")

    def say(self, text, f0, f1, cam, h=0.8, front=1.4):
        safe = "".join(c if c.isalnum() else "_" for c in text)
        path = os.path.join(TEX, f"bubble_{safe}.png")
        img = faces.bubble(text, FONT)
        img.save(path)
        w = h * img.width / img.height
        ob = plane(f"{self.name}_say_{f0}", w, h, image_mat(f"say_{f0}", path, emit=1.0),
                   self.root, (0, -front, 5.75 + h / 2))
        for attr in ("visible_shadow", "visible_diffuse", "visible_glossy"):
            setattr(ob, attr, False)
        c = ob.constraints.new("TRACK_TO")
        c.target, c.track_axis, c.up_axis = cam, "TRACK_Z", "UP_Y"
        for f, s in ((f0, 0), (f0 + 3, 1.12), (f0 + 5, 1), (f1 - 3, 1), (f1, 0)):
            key(ob, "scale", f, (s, s, s))


# ---------------------------------------------------------------- world
def build_world():
    sc = bpy.context.scene
    grass = ramp_mat("grass", "ShaderNodeTexNoise", (0.33, 0.62, 0.22), (0.42, 0.74, 0.28),
                     rough=0.9, setup=lambda t: setattr(t.inputs["Scale"], "default_value", 0.6))
    plane("ground", 400, 400, grass)
    stone = ramp_mat("stone", "ShaderNodeTexBrick", (0.42, 0.42, 0.46), (0.62, 0.62, 0.66),
                     rough=0.8, constant=True,
                     setup=lambda t: setattr(t.inputs["Scale"], "default_value", 1.2))
    box("path", (2.4, 5.0, 0.06), stone, loc=(3, 12.5, 0.03))

    # house the friends run into
    wall = mat("wall", (0.78, 0.86, 0.95), 0.7)
    box("house", (16, 8, 7), wall, loc=(2, 19, 3.5))
    prism("roof", 17, 9.2, 3.6, mat("roof", (0.30, 0.32, 0.40), 0.7), (2, 19, 7))
    wood = mat("wood", (0.58, 0.38, 0.22), 0.6)
    box("door", (1.9, 0.2, 3.4), wood, loc=(3, 15.0, 1.75), bevel=0.05)
    box("step", (2.8, 0.9, 0.25), wood, loc=(3, 14.6, 0.12), bevel=0.04)
    win = mat("window", (1.0, 0.85, 0.45), 0.2)
    win.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1, 0.7, 0.3, 1)
    for i, x in enumerate((-3.5, 7.5)):
        box(f"window{i}", (2.4, 0.2, 1.9), win, loc=(x, 14.95, 3.6), bevel=0.04)
        box(f"frame{i}", (2.7, 0.15, 2.2), mat(f"wframe{i}", (0.95, 0.95, 0.95)), loc=(x, 15.0, 3.6))
    switch(win.node_tree.nodes["Principled BSDF"].inputs["Base Color"], "default_value", NIGHT,
           (*lin((0.55, 0.75, 0.9)), 1), (1, 0.75, 0.35, 1))
    switch(win.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value",
           NIGHT, 0.0, 6.0)

    # fence with a gap for the path
    for i, (x0, x1) in enumerate(((-30, 1.6), (4.4, 34))):
        rail_w = x1 - x0
        for z in (0.8, 1.6):
            box(f"rail{i}_{z}", (rail_w, 0.15, 0.3), wood, loc=((x0 + x1) / 2, 10, z))
        x = x0
        while x <= x1:
            box(f"post{i}_{x:.0f}", (0.35, 0.35, 2.1), wood, loc=(x, 10, 1.05), bevel=0.04)
            x += 2.6

    # tree the seeker counts against
    bark = mat("bark", (0.45, 0.30, 0.18), 0.8)
    leaf = mat("leaf", (0.26, 0.62, 0.24), 0.7)
    cyl("trunk", 0.5, 0.4, 7, bark, loc=(0, 6.6, 3.5), segs=10)
    for i, (p, r) in enumerate((((0, 6.6, 8.0), 2.3), ((1.5, 6.2, 7.3), 1.6),
                                ((-1.6, 7.0, 7.4), 1.7), ((0.3, 7.6, 9.4), 1.5))):
        ball(f"canopy{i}", r, leaf, loc=p)

    # lamp post Max hides behind
    metal = mat("metal", (0.22, 0.23, 0.26), 0.4)
    cyl("pole", 0.1, 0.1, 8, metal, loc=(-6, 0, 4), segs=12)
    box("lamp_arm", (1.1, 0.12, 0.12), metal, loc=(-5.5, 0, 7.9))
    lampm = mat("lamp", (1.0, 0.9, 0.6), 0.3)
    box("lamp", (0.6, 0.6, 0.35), lampm, loc=(-5.0, 0, 7.75), bevel=0.05)
    lampm.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1, 0.75, 0.35, 1)
    switch(lampm.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value",
           NIGHT, 0.0, 12.0)

    # bush Pip hides in
    bushm = mat("bush", (0.20, 0.55, 0.22), 0.75)
    for i, (p, r) in enumerate((((4.9, -0.9, 0.95), 1.55), ((6.0, 0.05, 1.0), 1.3),
                                ((3.8, -1.85, 1.0), 1.3), ((5.5, -1.5, 0.8), 1.3),
                                ((4.3, -0.2, 0.6), 1.0))):
        ball(f"bush{i}", r, bushm, loc=p, sub=2)

    # neighbourhood backdrop
    rnd = random.Random(3)
    cols = [(0.95, 0.85, 0.65), (0.75, 0.88, 0.75), (0.85, 0.75, 0.70), (0.80, 0.80, 0.92),
            (0.95, 0.95, 0.90), (0.70, 0.80, 0.90)]
    for i, x in enumerate(range(-60, 61, 20)):
        y = 48 + rnd.uniform(-3, 3)
        h = rnd.uniform(6, 9)
        box(f"nb{i}", (14, 10, h), mat(f"nb{i}", cols[i % len(cols)], 0.8), loc=(x, y, h / 2))
        prism(f"nbroof{i}", 15, 11, 4, mat(f"nbr{i}", (0.45, 0.30, 0.25), 0.8), (x, y, h))
    for i in range(10):
        x = rnd.uniform(-60, 60)
        ball(f"bgtree{i}", rnd.uniform(2.5, 4), leaf, loc=(x, rnd.uniform(36, 42), 4))
    cloud = mat("cloud", (1, 1, 1), 1.0, emit=0.4)
    for i in range(9):
        cx, cz = rnd.uniform(-70, 70), rnd.uniform(26, 44)
        for k in range(3):
            ball(f"cloud{i}_{k}", rnd.uniform(3, 5), cloud,
                 loc=(cx + k * 4 - 4, 110 + rnd.uniform(-5, 5), cz + rnd.uniform(-1, 1)),
                 scale=(1.6, 1, 0.6))

    # lighting
    world = bpy.data.worlds.new("sky")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = world.node_tree.nodes["Background"]
    switch(bg.inputs["Color"], "default_value", NIGHT, (*lin((0.55, 0.76, 1.0)), 1),
           (*lin((0.06, 0.08, 0.20)), 1))
    sun_d = bpy.data.lights.new("sun", "SUN")
    sun_d.angle = math.radians(4)
    sun = link(bpy.data.objects.new("sun", sun_d), rot=(0.85, 0.15, -0.55))
    switch(sun_d, "energy", NIGHT, 3.6, 0.35)
    switch(sun_d, "color", NIGHT, (1.0, 0.96, 0.88), (0.6, 0.7, 1.0))
    for name, loc, energy in (("lamp_light", (-5.0, 0, 7.3), 900), ("porch", (2.2, 2.4, 5.0), 260)):
        d = bpy.data.lights.new(name, "POINT")
        d.color = (1.0, 0.75, 0.45)
        d.shadow_soft_size = 0.6
        link(bpy.data.objects.new(name, d), loc=loc)
        switch(d, "energy", NIGHT, 0.0, float(energy))
    return sun


# ---------------------------------------------------------------- cameras
def camera(name, keys):
    """keys: [(frame, cam_loc, look_at, lens)]"""
    d = bpy.data.cameras.new(name)
    d.sensor_width = 36
    ob = link(bpy.data.objects.new(name, d))
    tgt = empty(name + "_tgt")
    c = ob.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    for f, loc, look, lens in keys:
        key(ob, "location", f, loc)
        key(tgt, "location", f, look)
        key(d, "lens", f, lens)
    return ob


def heading(dx, dy):
    """Root Z rotation that makes a character (front = -Y) face direction (dx, dy)."""
    return math.atan2(dx, -dy)


def along(p, d, k, z):
    return (p[0] + d[0] * k, p[1] + d[1] * k, z)


# ---------------------------------------------------------------- story
def story():
    rnd = random.Random(7)
    seek = Char("Noob", skin=(0.98, 0.82, 0.12), shirt=(0.06, 0.42, 0.88), pants=(0.32, 0.72, 0.26))
    maxx = Char("Max", skin=(0.80, 0.56, 0.40), shirt=(1.0, 0.46, 0.10), pants=(0.18, 0.18, 0.22),
                sleeves=(1.0, 0.46, 0.10))
    maxx.spiky_hair((0.08, 0.08, 0.09), seed=1)
    stripes = ramp_mat("Pip_shirt", "ShaderNodeTexWave", (0.92, 0.16, 0.22), (0.97, 0.97, 0.97),
                       constant=True, pos=0.55,
                       setup=lambda t: (setattr(t, "wave_type", "BANDS"),
                                        setattr(t, "bands_direction", "Z"),
                                        setattr(t.inputs["Scale"], "default_value", 1.1),
                                        setattr(t.inputs["Distortion"], "default_value", 0.0)))
    pip = Char("Pip", skin=(1.0, 0.86, 0.74), shirt=None, shirt_mat=stripes,
               pants=(0.13, 0.16, 0.38), sleeves=(0.92, 0.16, 0.22))
    pip.spiky_hair((0.42, 0.95, 0.76), seed=2)

    seek_pos = (0.0, 4.4)
    pole = (-6.0, 0.0)
    to_pole = Vector((pole[0] - seek_pos[0], pole[1] - seek_pos[1])).normalized()
    max_pos = (pole[0] + to_pole.x * 0.7, pole[1] + to_pole.y * 0.7)
    max_face = heading(-to_pole.x, -to_pole.y)              # Max faces the seeker
    seek_look = heading(to_pole.x, to_pole.y) + TAU          # seeker turns to the pole
    bush = (4.9, -0.9)
    pip_dir = Vector((seek_pos[0] - bush[0], seek_pos[1] - bush[1])).normalized()
    pip_face = heading(pip_dir.x, pip_dir.y)
    to_seek = (-to_pole.x, -to_pole.y)

    cams = {
        "wide": camera("C_wide", [(0, (0, -13.0, 4.0), (0, 2.2, 3.6), 22),
                                  (119, (0, -12.0, 4.0), (0, 2.2, 3.6), 22)]),
        "max": camera("C_max", [(120, along(max_pos, to_seek, 4.8, 5.0), (*max_pos, 5.3), 32),
                                (209, along(max_pos, to_seek, 4.3, 5.0), (*max_pos, 5.3), 32)]),
        "bush": camera("C_bush", [(210, along(bush, pip_dir, 3.8, 3.1), (*bush, 2.75), 38),
                                  (299, along(bush, pip_dir, 3.4, 3.1), (*bush, 2.75), 38)]),
        "count": camera("C_count", [(300, (5.2, 4.0, 4.7), (0, 4.8, 4.9), 30),
                                    (389, (4.7, 4.0, 4.7), (0, 4.8, 4.9), 30)]),
        "shoulder": camera("C_shoulder", [(390, (1.24, 6.43, 5.3), (*max_pos, 4.6), 28),
                                          (400, (1.24, 6.43, 5.3), (*max_pos, 4.6), 28),
                                          (445, (1.24, 6.43, 5.3), (*max_pos, 4.6), 62)]),
        "bro": camera("C_bro", [(450, along(seek_pos, to_pole, 4.4, 5.0), (*seek_pos, 5.6), 40),
                                (539, along(seek_pos, to_pole, 3.9, 5.0), (*seek_pos, 5.6), 40)]),
        "how": camera("C_how", [(540, along(max_pos, to_seek, 4.6, 5.0), (*max_pos, 5.25), 36),
                                (548, along(max_pos, to_seek, 4.6, 5.0), (*max_pos, 5.25), 36),
                                (553, along(max_pos, to_seek, 4.6, 5.0), (*max_pos, 5.35), 50),
                                (629, along(max_pos, to_seek, 4.4, 5.0), (*max_pos, 5.35), 52)]),
        "search": camera("C_search", [(630, (8.5, -7.5, 4.4), (2.4, 1.4, 2.9), 28),
                                      (809, (8.0, -6.5, 4.6), (2.8, 4.5, 3.0), 28)]),
        "night": camera("C_night", [(840, along(bush, pip_dir, 5.0, 3.1), (*bush, 3.3), 34),
                                    (959, along(bush, pip_dir, 4.4, 3.1), (*bush, 3.3), 34)]),
    }
    shots = [(0, "wide"), (120, "max"), (210, "bush"), (300, "count"), (390, "shoulder"),
             (450, "bro"), (540, "how"), (630, "search"), (NIGHT, "night")]
    shots = [(f, cams[n]) for f, n in shots]
    C = cams

    # ---- seeker: counts at the tree
    seek.place(0, *seek_pos, angle=math.pi)
    hands = dict(armR=(-2.2, 0, 0.35), armL=(-2.2, 0, -0.35))
    seek.set(0, **hands)
    seek.face(0, "counting")
    for i, f in enumerate(range(0, 356, 15)):
        seek.set(f, neck=(0.12 if i % 2 else 0.0, 0, 0))
    seek.say("1...", 12, 44, C["wide"], h=3.2, front=0)
    seek.say("1... 2...", 46, 78, C["wide"], h=3.2, front=0)
    seek.say("1... 2... 3...", 80, 119, C["wide"], h=3.2, front=0)
    seek.say("...9... 10!", 302, 338, C["count"])
    seek.say("READY OR NOT!", 340, 388, C["count"])
    seek.pose(354, 362, armR=(0, 0, 0), armL=(0, 0, 0), neck=(0, 0, 0))
    seek.face(356, "smirk")
    seek.turn(364, 380, seek_look)
    seek.face(440, "deadpan")
    seek.say("bro.", 462, 536, C["bro"])
    seek.pose(470, 480, neck=(0, 0.18, 0))
    # search
    seek.face(630, "smile")
    stop = (3.4, 0.6)
    seek.turn(630, 640, heading(stop[0] - seek_pos[0], stop[1] - seek_pos[1]) + TAU)
    seek.pose(630, 636, neck=(0, 0, 0))
    seek.goto(632, 680, *stop)
    seek.cycle(632, 680, 16, 0.55)
    seek.pose(684, 694, neck=(0, 0, 0.7))
    seek.face(684, "look_l")
    seek.pose(702, 712, neck=(0, 0, -0.7))
    seek.face(702, "look_r")
    seek.pose(722, 730, neck=(0, 0, 0))
    seek.face(722, "smile")
    seek.say("hmm... where's Pip?", 655, 708, C["search"], h=1.0)
    seek.say("eh, let's go get pizza", 714, 762, C["search"], h=1.0)
    seek.face(745, "happy")
    seek.turn(758, 766, heading(0, 1) + TAU)
    seek.goto(762, 808, 3.2, 9.2)
    seek.cycle(762, 808, 10, 0.95, bob=0.2)
    seek.teleport(812, 0, -200, -50)

    # ---- Max: hides behind the (very thin) lamp post
    maxx.place(0, -1.8, 3.0, angle=0)
    maxx.face(0, "smile")
    maxx.turn(6, 12, heading(max_pos[0] + 1.8, max_pos[1] - 3.0))
    maxx.goto(10, 55, *max_pos)
    maxx.cycle(10, 55, 8, 0.95, bob=0.2)
    maxx.turn(55, 64, max_face)
    maxx.face(60, "smirk")
    maxx.pose(124, 132, neck=(0, 0.14, 0))
    maxx.say("he'll NEVER find me", 128, 206, C["max"], h=0.6)
    maxx.face(548, "shock")
    maxx.pose(548, 553, armR=(0, 2.4, 0), armL=(0, -2.4, 0), neck=(0, 0, 0))
    move(maxx.hip, "location", 548, 552, (0, 0, 2.5))
    move(maxx.hip, "location", 552, 557, (0, 0, 2.0))
    maxx.say("HOW??", 552, 626, C["how"])
    maxx.face(636, "smile")
    maxx.pose(632, 640, armR=(0, 0, 0), armL=(0, 0, 0))
    meet = (1.0, 0.3)
    maxx.turn(640, 648, heading(meet[0] - max_pos[0], meet[1] - max_pos[1]))
    maxx.goto(644, 700, *meet)
    maxx.cycle(644, 700, 16, 0.55)
    maxx.face(742, "happy")
    maxx.pose(744, 750, armR=(0, 2.6, 0), armL=(0, -2.6, 0))
    maxx.say("PIZZA!!", 744, 792, C["search"], h=1.0)
    maxx.pose(758, 763, armR=(0, 0, 0), armL=(0, 0, 0))
    maxx.turn(760, 768, heading(2.2 - meet[0], 8.6 - meet[1]))
    maxx.goto(764, 808, 2.2, 8.6)
    maxx.cycle(764, 808, 10, 0.95, bob=0.2)
    maxx.teleport(812, 0, -210, -50)

    # ---- Pip: dives into the bush and is never found
    pip.place(0, 1.8, 3.0, angle=0)
    pip.face(0, "happy")
    pip.turn(6, 12, heading(bush[0] - 1.8, bush[1] - 3.0))
    pip.goto(10, 50, *bush)
    pip.cycle(10, 50, 8, 0.95, bob=0.2)
    pip.goto(50, 55, z=0.9, interp="BEZIER")
    pip.pose(50, 54, armR=(-2.9, 0, 0), armL=(-2.9, 0, 0))
    pip.goto(55, 64, z=-3.6, interp="BEZIER")
    pip.turn(56, 64, pip_face)
    pip.pose(70, 80, armR=(0, 0, 0), armL=(0, 0, 0))
    pip.face(64, "look_l")
    pip.goto(214, 226, z=-2.35, interp="BEZIER")
    pip.face(236, "look_r")
    pip.face(252, "look_l")
    pip.face(266, "sneaky_r")
    pip.say("hehe", 240, 278, C["bush"], h=0.7)
    pip.goto(282, 292, z=-3.6, interp="BEZIER")
    pip.goto(634, 646, z=-2.35, interp="BEZIER")
    pip.face(634, "look_l")
    pip.face(668, "look_r")
    pip.face(700, "look_l")
    pip.face(730, "sneaky_r")
    pip.face(772, "shock")
    # three hours later...
    pip.face(836, "sad")
    pip.pose(846, 856, neck=(0, 0, 0.45))
    pip.pose(862, 872, neck=(0, 0, -0.45))
    pip.pose(878, 886, neck=(0, 0, 0))
    pip.goto(856, 880, z=-1.75, interp="BEZIER")
    pip.say("guys...?", 888, 958, C["night"], h=0.75)

    for ch in (seek, maxx, pip):
        ch.finalize_faces(rnd)
    return shots


def camera_at(shots, f):
    cam = shots[0][1]
    for start, c in shots:
        if f >= start:
            cam = c
    return cam


def main():
    global TEX
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stills", help="comma-separated frames to render instead of the full range")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=END - 1)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--save-blend", help="also save the scene as a .blend file")
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    TEX = os.path.join(out, "_tex")
    os.makedirs(TEX, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 0, END - 1
    build_world()
    shots = story()
    for f, cam in shots:
        sc.timeline_markers.new(cam.name, frame=f).camera = cam

    r = sc.render
    r.engine = "CYCLES"
    r.resolution_x = a.width
    r.resolution_y = round(a.width * 1400 / 1080)
    r.use_persistent_data = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    sc.view_settings.view_transform = "Standard"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = a.samples
    cy.use_denoising = True
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 4, 2, 1
    cy.transmission_bounces, cy.transparent_max_bounces = 1, 8
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.save_blend))

    frames = [int(x) for x in a.stills.split(",")] if a.stills else range(a.start, a.end + 1)
    for f in frames:
        if CARD[0] <= f < CARD[1]:
            continue
        path = os.path.join(out, f"{f:04d}.png")
        if os.path.exists(path) and not a.stills:
            continue
        sc.frame_set(f)
        sc.camera = camera_at(shots, f)
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f"frame {f} done", flush=True)


if __name__ == "__main__":
    main()
