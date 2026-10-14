"""
Freche Silbermoewe (Larus argentatus) - stylisiertes Low-Poly-Modell mit Animationen fuer three.js.

Aufruf:
  blender -b --factory-startup --python build_seagull.py

Ergebnis: seagull.blend + seagull.glb (Hierarchie aus starren Teilen, Objekt-Animationen als NLA-Spuren,
eine glTF-Animation pro Spurname).

Masse: 1 Einheit = 1 m, Silbermoewe in Naturgroesse (ca. 60 cm lang, 1,4 m Spannweite).
Ausrichtung: Blick nach -Y (glTF/three: +Z), oben = +Z, linke Koerperseite = +X.
Der Wurzelknoten "Gull" steht mit den Fuessen auf z = 0, die Spiel-Logik bewegt nur ihn.

Animationen (24 fps):
  Idle, Walk, Hop, Swim, Fly, Glide, Land, Peck, Squawk
"""
import bpy, bmesh, math, os
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 24

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS


# ---------------------------------------------------------------- Materialien
def mat(name, color, rough=0.7, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*color, 1)
    return m


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


M = {
    "White": mat("Gull_White", srgb("#f6f3ec"), 0.8),
    "Grey": mat("Gull_Grey", srgb("#9fadc0"), 0.75),
    "GreyDark": mat("Gull_GreyDark", srgb("#7d8a9e"), 0.75),
    "Black": mat("Gull_Black", srgb("#26262c"), 0.6),
    "Beak": mat("Gull_Beak", srgb("#f6c63b"), 0.45),
    "BeakRed": mat("Gull_BeakRed", srgb("#e0402e"), 0.45),
    "Leg": mat("Gull_Leg", srgb("#eaa79c"), 0.6),
    "Eye": mat("Gull_Eye", srgb("#f7e15a"), 0.3),
    "Pupil": mat("Gull_Pupil", srgb("#111111"), 0.2),
    "Brow": mat("Gull_Brow", srgb("#c9ced6"), 0.8),
}
MAT_ORDER = list(M)


# ---------------------------------------------------------------- Gull-Raum -> Blender
# f = vorwaerts, s = links, u = oben
def G(f, s, u):
    return Vector((s, -f, u))


class MB:
    """Kleiner Mesh-Baukasten: sammelt Polygone mit Material und Glaettung."""

    def __init__(self):
        self.v, self.faces = [], []

    def add_v(self, p):
        self.v.append(Vector(p))
        return len(self.v) - 1

    def face(self, idx, m, smooth=True):
        self.faces.append((idx, m, smooth))

    def merge(self, other, mtx=Matrix()):
        o = len(self.v)
        self.v += [mtx @ p for p in other.v]
        self.faces += [([i + o for i in f], m, s) for f, m, s in other.faces]

    def build(self, name, origin, parent=None):
        """origin: Gelenkpunkt (Blender-Koordinaten, Weltraum) - wird Objektursprung."""
        me = bpy.data.meshes.new(name)
        me.from_pydata([p - origin for p in self.v], [], [f for f, _, _ in self.faces])
        for mn in MAT_ORDER:
            me.materials.append(M[mn])
        for poly, (_, m, s) in zip(me.polygons, self.faces):
            poly.material_index = MAT_ORDER.index(m)
            poly.use_smooth = s
        me.validate()
        me.update()
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        ob.location = origin
        WORLD[name] = Vector(origin)
        if parent:
            set_parent(ob, parent)
        # ungenutzte Materialslots entfernen
        used = {p.material_index for p in me.polygons}
        for i in reversed(range(len(me.materials))):
            if i not in used:
                me.materials.pop(index=i)  # verschiebt die Indizes der Flaechen selbst
        return ob


WORLD = {}  # Weltposition der Gelenkpunkte (beim Aufbau sind alle Rotationen 0)


def set_parent(ob, parent):
    WORLD[ob.name] = ob.location.copy()
    ob.parent = parent
    ob.location = WORLD[ob.name] - WORLD.get(parent.name, Vector())


def empty(name, origin, parent=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 0.05
    scene.collection.objects.link(ob)
    ob.location = origin
    WORLD[name] = Vector(origin)
    if parent:
        set_parent(ob, parent)
    return ob


def loft(mb, rings, seg, m_fn, cap0=True, cap1=True, smooth=True):
    """rings: Liste von (zentrum G-Vector, rs (seitlich), ru (oben)); Querschnitt-Ellipse in der s/u-Ebene,
    optional mit eigener Achse: (zentrum, rs, ru, axis_up, axis_side)."""
    idx = []
    for ring in rings:
        c, rs, ru = ring[:3]
        up = ring[3] if len(ring) > 3 else Vector((0, 0, 1))
        side = ring[4] if len(ring) > 4 else Vector((1, 0, 0))
        row = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            row.append(mb.add_v(c + side * (math.sin(a) * rs) + up * (math.cos(a) * ru)))
        idx.append(row)
    for i in range(len(idx) - 1):
        for k in range(seg):
            a, b = idx[i][k], idx[i][(k + 1) % seg]
            c2, d = idx[i + 1][(k + 1) % seg], idx[i + 1][k]
            cen = sum((mb.v[j] for j in (a, b, c2, d)), Vector()) / 4
            nrm = (mb.v[b] - mb.v[a]).cross(mb.v[d] - mb.v[a])
            mb.face([a, d, c2, b], m_fn(cen, nrm, i, k), smooth)
    if cap0:
        c = mb.add_v(sum((mb.v[j] for j in idx[0]), Vector()) / seg)
        for k in range(seg):
            mb.face([c, idx[0][k], idx[0][(k + 1) % seg]], m_fn(mb.v[c], Vector((0, 1, 0)), 0, k), smooth)
    if cap1:
        c = mb.add_v(sum((mb.v[j] for j in idx[-1]), Vector()) / seg)
        for k in range(seg):
            mb.face([c, idx[-1][(k + 1) % seg], idx[-1][k]], m_fn(mb.v[c], Vector((0, -1, 0)), len(idx) - 1, k), smooth)
    return idx


def sphere(mb, c, r, m, seg=10, rings=7, scale=(1, 1, 1), smooth=True):
    sx, sy, sz = scale
    vi = []
    top = mb.add_v(c + Vector((0, 0, r * sz)))
    bot = mb.add_v(c - Vector((0, 0, r * sz)))
    for i in range(1, rings):
        th = math.pi * i / rings
        row = []
        for k in range(seg):
            ph = 2 * math.pi * k / seg
            row.append(mb.add_v(c + Vector((math.sin(th) * math.cos(ph) * r * sx, math.sin(th) * math.sin(ph) * r * sy, math.cos(th) * r * sz))))
        vi.append(row)
    for k in range(seg):
        mb.face([top, vi[0][k], vi[0][(k + 1) % seg]], m, smooth)
        mb.face([bot, vi[-1][(k + 1) % seg], vi[-1][k]], m, smooth)
    for i in range(len(vi) - 1):
        for k in range(seg):
            mb.face([vi[i][k], vi[i + 1][k], vi[i + 1][(k + 1) % seg], vi[i][(k + 1) % seg]], m, smooth)


def slab(mb, outline, thick, m_top, m_bot=None, smooth=False, bulge=0.0):
    """Flaches Prisma aus einem Umriss (Liste von Blender-Punkten, ungefaehr in einer Ebene, Normale +Z)."""
    m_bot = m_bot or m_top
    n = len(outline)
    cen = sum(outline, Vector()) / n
    top = [mb.add_v(p + Vector((0, 0, thick / 2))) for p in outline]
    bot = [mb.add_v(p - Vector((0, 0, thick / 2))) for p in outline]
    ct = mb.add_v(cen + Vector((0, 0, thick / 2 + bulge)))
    cb = mb.add_v(cen - Vector((0, 0, thick / 2)))
    for k in range(n):
        k2 = (k + 1) % n
        mb.face([ct, top[k], top[k2]], m_top, smooth)
        mb.face([cb, bot[k2], bot[k]], m_bot, smooth)
        mb.face([top[k], bot[k], bot[k2], top[k2]], m_bot, smooth)


def tube(mb, a, b, ra, rb, m, seg=6, caps=True):
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-4:
        side = d.cross(Vector((1, 0, 0)))
    side.normalize()
    up = side.cross(d).normalized()
    loft(mb, [(a, ra, ra, up, side), (b, rb, rb, up, side)], seg, lambda *x: m, cap0=caps, cap1=caps)


# ================================================================ GEOMETRIE
# Gelenkpunkte (Gull-Raum)
HIP = G(0.0, 0, 0.20)
NECK = G(0.13, 0, 0.27)
HEAD = G(0.175, 0, 0.355)
JAW = G(0.225, 0, 0.345)
TAIL = G(-0.16, 0, 0.235)
SHOULDER = G(0.08, 0.068, 0.275)
ELBOW_S, WRIST_S, TIP_S = 0.27, 0.46, 0.76

root = empty("Gull", Vector((0, 0, 0)))
root.empty_display_size = 0.3

# --- Rumpf (weiss, Rueckenmantel grau) -------------------------------------------------------
body_mb = MB()
prof = [  # f, rs, ru, u-zentrum
    (-0.175, 0.035, 0.022, 0.235),
    (-0.13, 0.065, 0.05, 0.225),
    (-0.06, 0.088, 0.075, 0.212),
    (0.02, 0.095, 0.085, 0.205),
    (0.09, 0.088, 0.082, 0.215),
    (0.14, 0.066, 0.068, 0.235),
    (0.165, 0.04, 0.045, 0.255),
]


def body_mat(c, n, i, k):
    f = -c.y
    u = c.z
    if n.normalized().z > 0.35 and -0.17 < f < 0.13 and u > 0.235:
        return "Grey"
    return "White"


loft(body_mb, [(G(f, 0, uc), rs, ru) for f, rs, ru, uc in prof], 12, body_mat)
body = body_mb.build("Body", HIP, root)

# --- Hals ---------------------------------------------------------------------------------------
neck_mb = MB()
loft(neck_mb, [
    (G(0.105, 0, 0.255), 0.052, 0.055),
    (G(0.135, 0, 0.29), 0.046, 0.046),
    (G(0.16, 0, 0.325), 0.042, 0.042),
    (G(0.17, 0, 0.345), 0.04, 0.04),
], 10, lambda *a: "White", cap0=False, cap1=False)
neck = neck_mb.build("Neck", NECK, body)

# --- Kopf mit frechem Blick ----------------------------------------------------------------------
head_mb = MB()
sphere(head_mb, G(0.18, 0, 0.36), 0.052, "White", seg=12, rings=8, scale=(0.9, 1.15, 0.9))
for s in (1, -1):
    eye_c = G(0.205, 0.036 * s, 0.372)
    sphere(head_mb, eye_c, 0.0115, "Eye", seg=8, rings=5)
    sphere(head_mb, eye_c + G(0.004, 0.006 * s, 0.0), 0.0055, "Pupil", seg=6, rings=4)
    # grimmige "Augenbraue": schraeger grauer Keil -> freches Gesicht
    brow = [G(0.218, 0.029 * s, 0.383), G(0.195, 0.04 * s, 0.391), G(0.198, 0.041 * s, 0.385), G(0.218, 0.031 * s, 0.377)]
    tm = MB()
    a = [tm.add_v(p) for p in brow]
    b = [tm.add_v(p + G(0, 0.004 * s, 0)) for p in brow]
    tm.face(a if s < 0 else a[::-1], "Brow", False)
    tm.face(b[::-1] if s < 0 else b, "Brow", False)
    for k in range(4):
        tm.face([a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]] if s > 0 else [a[k], b[k], b[(k + 1) % 4], a[(k + 1) % 4]], "Brow", False)
    head_mb.merge(tm)
# Oberschnabel mit Haken
beak_rings = [
    (G(0.215, 0, 0.352), 0.016, 0.014),
    (G(0.245, 0, 0.350), 0.012, 0.011),
    (G(0.27, 0, 0.349), 0.009, 0.009),
    (G(0.285, 0, 0.346), 0.007, 0.008),
]
loft(head_mb, beak_rings, 8, lambda *a: "Beak", cap0=False, cap1=False)
hook = G(0.285, 0, 0.346)
tube(head_mb, hook, G(0.296, 0, 0.336), 0.007, 0.002, "Beak", seg=6)
head = head_mb.build("Head", HEAD, neck)

# Unterschnabel (Kiefer) mit rotem Fleck
jaw_mb = MB()
loft(jaw_mb, [
    (G(0.218, 0, 0.338), 0.012, 0.006),
    (G(0.25, 0, 0.337), 0.010, 0.005),
    (G(0.278, 0, 0.338), 0.007, 0.005),
], 8, lambda c, n, i, k: "BeakRed" if i == 1 and n.z < 0.2 else "Beak", cap0=True, cap1=True)
sphere(jaw_mb, G(0.268, 0, 0.334), 0.0065, "BeakRed", seg=6, rings=4, scale=(1.2, 0.9, 0.8))
jaw = jaw_mb.build("Jaw", JAW, head)

# --- Schwanz -------------------------------------------------------------------------------------
tail_mb = MB()
tail_outline = [G(-0.15, 0.045, 0.24), G(-0.27, 0.05, 0.238), G(-0.285, 0.0, 0.236), G(-0.27, -0.05, 0.238), G(-0.15, -0.045, 0.24)]
slab(tail_mb, tail_outline, 0.018, "White", smooth=False, bulge=0.004)
tail = tail_mb.build("Tail", TAIL, body)

# --- Beine & Fuesse -----------------------------------------------------------------------------
legs, feet = {}, {}
for side, s in (("L", 1), ("R", -1)):
    lm = MB()
    tube(lm, G(-0.005, 0.042 * s, 0.15), G(0.0, 0.042 * s, 0.022), 0.011, 0.0075, "Leg", seg=6)
    sphere(lm, G(-0.002, 0.042 * s, 0.15), 0.02, "White", seg=8, rings=5)  # Federhose
    legs[side] = lm.build("Leg_" + side, G(-0.005, 0.042 * s, 0.14), body)
    fm = MB()
    a = G(0.0, 0.042 * s, 0.012)
    toes = [G(0.075, (0.042 + 0.03) * s, 0.006), G(0.085, 0.042 * s, 0.006), G(0.075, (0.042 - 0.028) * s, 0.006)]
    web = [a] + [toes[0], toes[1], toes[2]]
    # Schwimmhaut als flache Flaeche zwischen den Zehen
    sl = MB()
    o = [a, toes[0], G(0.06, 0.057 * s, 0.006), toes[1], G(0.06, 0.028 * s, 0.006), toes[2]]
    if s < 0:
        o = o[::-1]
    slab(sl, [p.copy() for p in o], 0.006, "Leg")
    fm.merge(sl)
    for t in toes:
        tube(fm, a, t, 0.005, 0.0035, "Leg", seg=5)
    feet[side] = fm.build("Foot_" + side, G(0.0, 0.042 * s, 0.022), legs[side])

# --- Fluegel: angelegt (Bodenposen) ---------------------------------------------------------------
fold = {}
for side, s in (("L", 1), ("R", -1)):
    wm = MB()
    rings = []
    pts = [  # f, u, rs(dicke), ru(hoehe)
        (0.11, 0.255, 0.010, 0.026),
        (0.06, 0.256, 0.017, 0.043),
        (-0.04, 0.253, 0.019, 0.046),
        (-0.13, 0.248, 0.015, 0.04),
        (-0.21, 0.245, 0.011, 0.032),
        (-0.28, 0.24, 0.007, 0.02),
        (-0.33, 0.238, 0.003, 0.008),
    ]
    for f, u, rs, ru in pts:
        # leicht schraeg: Oberkante naeher am Koerper
        sx = 0.078 + 0.006 * (f > -0.15)
        rings.append((G(f, sx * s, u), rs, ru, Vector((-0.25 * s, 0, 1)).normalized(), Vector((1, 0, 0.25 * s)).normalized()))

    def fold_mat(c, n, i, k, s=s):
        f = -c.y
        if f < -0.19:
            return "Black"
        if f < -0.13 and c.z < 0.25:
            return "White"  # weisser Hinterrand ueber den Handschwingen
        return "Grey"

    loft(wm, rings, 8, fold_mat)
    # weisse Spiegelflecken an den Spitzen
    for f, du in ((-0.255, 0.0), (-0.3, 0.004)):
        sphere(wm, G(f, 0.088 * s, 0.24 + du), 0.008, "White", seg=6, rings=4, scale=(0.4, 1.4, 1.0))
    fold[side] = wm.build("WingFold_" + side, G(0.08, 0.068 * s, 0.275), body)

# --- Fluegel: ausgebreitet (Flugposen), drei Segmente --------------------------------------------
wing, fore, hand = {}, {}, {}
for side, s in (("L", 1), ("R", -1)):
    sh = G(0.08, 0.068 * s, 0.275)
    el = G(0.075, ELBOW_S * s, 0.275)
    wr = G(0.07, WRIST_S * s, 0.275)

    def outline(pts):
        out = [G(f, sp * s, 0.275) for f, sp in pts]
        return out if s > 0 else out[::-1]

    # Innenfluegel
    m1 = MB()
    slab(m1, outline([(0.105, 0.065), (0.098, ELBOW_S + 0.005), (-0.075, ELBOW_S + 0.005), (-0.1, 0.065)]), 0.022, "Grey", "White", bulge=0.008)
    slab(m1, [p + Vector((0, 0, -0.004)) for p in outline([(-0.08, 0.07), (-0.07, ELBOW_S), (-0.115, ELBOW_S), (-0.125, 0.07)])], 0.01, "White")
    wing[side] = m1.build("Wing_" + side, sh, body)
    # Unterarm
    m2 = MB()
    slab(m2, outline([(0.098, ELBOW_S - 0.005), (0.088, WRIST_S + 0.005), (-0.06, WRIST_S + 0.005), (-0.075, ELBOW_S - 0.005)]), 0.018, "Grey", "White", bulge=0.006)
    slab(m2, [p + Vector((0, 0, -0.003)) for p in outline([(-0.07, ELBOW_S), (-0.055, WRIST_S), (-0.095, WRIST_S), (-0.11, ELBOW_S)])], 0.009, "White")
    fore[side] = m2.build("WingFore_" + side, el, wing[side])
    # Hand mit schwarzer Spitze und weissen Spiegeln
    m3 = MB()
    slab(m3, outline([(0.088, WRIST_S - 0.005), (0.07, 0.56), (-0.06, 0.56), (-0.065, WRIST_S - 0.005)]), 0.014, "Grey", "White", bulge=0.004)
    slab(m3, outline([(0.07, 0.555), (0.03, 0.70), (-0.0, TIP_S), (-0.045, 0.66), (-0.06, 0.555)]), 0.012, "Black")
    for sp, r in ((0.70, 0.016), (0.64, 0.012)):
        sphere(m3, G(-0.012, sp * s, 0.282), r, "White", seg=6, rings=3, scale=(1.0, 1.4, 0.25), smooth=False)
    hand[side] = m3.build("WingHand_" + side, wr, fore[side])

bpy.context.view_layer.update()

# ================================================================ ANIMATIONEN
# Achsen (Elternraum, Blender): rx>0 = Nase/Fuss nach unten bzw. hinten, rz>0 = nach links (+X) drehen,
# Fluegel L: ry>0 = Spitze nach unten, rz>0 = Spitze nach hinten (R gespiegelt: ry/rz negiert).
JOINTS = ["Body", "Neck", "Head", "Jaw", "Tail", "Leg_L", "Leg_R", "Foot_L", "Foot_R",
          "WingFold_L", "WingFold_R", "Wing_L", "Wing_R", "WingFore_L", "WingFore_R", "WingHand_L", "WingHand_R"]
OBJ = {n: bpy.data.objects[n] for n in JOINTS}
REST_LOC = {n: OBJ[n].location.copy() for n in JOINTS}

WING_FOLDED = 0.001


def base_pose(flying):
    p = {n: {"rot": (0, 0, 0), "loc": (0, 0, 0), "scl": 1.0} for n in JOINTS}
    ws = 1.0 if flying else WING_FOLDED
    fs = WING_FOLDED if flying else 1.0
    for s in "LR":
        p["Wing_" + s]["scl"] = ws
        p["WingFold_" + s]["scl"] = fs
    return p


def wingrot(side, rx=0.0, flap=0.0, sweep=0.0):
    """flap>0: Spitze nach unten; sweep>0: Spitze nach hinten."""
    m = 1 if side == "L" else -1
    return (rx, flap * m, sweep * m)


def sym(name, side):
    return name + "_" + side


CLIPS = {}


def clip(name, frames, loop=True):
    def deco(fn):
        CLIPS[name] = (frames, fn, loop)
        return fn
    return deco


def lerp(a, b, t):
    return a + (b - a) * t


# Jede Clip-Funktion bekommt die Phase t in [0,1) und liefert eine Pose.
@clip("Idle", 48)
def idle(t):
    p = base_pose(False)
    w = 2 * math.pi * t
    p["Body"]["loc"] = (0, 0, 0.003 * math.sin(2 * w))
    p["Body"]["rot"] = (0.02 * math.sin(w), 0, 0)
    # Kopf schaut sich frech um: links - geradeaus - rechts - Kopf schraeg
    yaw = 0.0
    tilt = 0.0
    if 0.15 < t < 0.4:
        yaw = 0.7 * math.sin((t - 0.15) / 0.25 * math.pi)
    if 0.5 < t < 0.8:
        yaw = -0.6 * math.sin((t - 0.5) / 0.3 * math.pi)
        tilt = 0.25 * math.sin((t - 0.5) / 0.3 * math.pi)
    p["Head"]["rot"] = (0.05 * math.sin(2 * w), tilt, yaw)
    p["Neck"]["rot"] = (-0.04 + 0.03 * math.sin(w), 0, 0.15 * yaw)
    p["Tail"]["rot"] = (-0.04, 0, 0.12 * math.sin(3 * w) * (t > 0.85))
    return p


@clip("Walk", 16)
def walk(t):
    p = base_pose(False)
    w = 2 * math.pi * t
    sw = math.sin(w)
    p["Leg_L"]["rot"] = (0.55 * sw, 0, 0)
    p["Leg_R"]["rot"] = (-0.55 * sw, 0, 0)
    # Fuesse bleiben einigermassen flach, beim Vorschwingen leicht angehoben
    p["Foot_L"]["rot"] = (-0.55 * sw + 0.35 * max(0, -math.cos(w)), 0, 0)
    p["Foot_R"]["rot"] = (0.55 * sw + 0.35 * max(0, math.cos(w)), 0, 0)
    # Watscheln: Rollen zur Standbein-Seite, Auf und Ab
    p["Body"]["rot"] = (0.06, 0.1 * math.cos(w), 0.05 * math.cos(w))
    p["Body"]["loc"] = (0.006 * math.cos(w), 0, 0.008 * abs(math.sin(w)) - 0.004)
    # Kopfnicken im Doppeltakt
    p["Neck"]["rot"] = (-0.12 + 0.12 * math.sin(2 * w), 0, -0.04 * math.cos(w))
    p["Head"]["rot"] = (0.08 - 0.1 * math.sin(2 * w), 0, 0)
    p["Tail"]["rot"] = (-0.05, 0, -0.15 * math.cos(w))
    return p


@clip("Hop", 18, loop=False)
def hop(t):
    fl = 0.24 < t < 0.8
    p = base_pose(fl)
    # 0-0.24 Hocken, 0.24-0.8 Luft (Wurzelhoehe macht der Code), danach Landung
    if t < 0.24:
        k = math.sin(t / 0.24 * math.pi)
        p["Body"]["loc"] = (0, 0, -0.03 * k)
        p["Body"]["rot"] = (0.25 * k, 0, 0)
        p["Leg_L"]["rot"] = p["Leg_R"]["rot"] = (-0.35 * k, 0, 0)
        p["Foot_L"]["rot"] = p["Foot_R"]["rot"] = (0.35 * k, 0, 0)
        p["Neck"]["rot"] = (0.25 * k, 0, 0)
    elif fl:
        k = (t - 0.24) / 0.56
        flap = -0.9 + 1.3 * math.sin(k * math.pi)  # einmal kraeftig schlagen
        op = math.sin(k * math.pi)  # wie weit geoeffnet
        for s in "LR":
            p["Wing_" + s]["rot"] = wingrot(s, 0.1, flap, 0.55 - 0.4 * op)
            p["WingFore_" + s]["rot"] = wingrot(s, 0, 0.15 * op, -0.6 + 0.4 * op)
            p["WingHand_" + s]["rot"] = wingrot(s, 0, 0.2, 0.7 - 0.4 * op)
        p["Leg_L"]["rot"] = p["Leg_R"]["rot"] = (0.4 * math.sin(k * math.pi), 0, 0)
        p["Foot_L"]["rot"] = p["Foot_R"]["rot"] = (0.6 * math.sin(k * math.pi), 0, 0)
        p["Body"]["rot"] = (-0.15 * math.sin(k * math.pi), 0, 0)
        p["Neck"]["rot"] = (-0.15, 0, 0)
        p["Tail"]["rot"] = (-0.15, 0, 0)
    else:
        k = math.sin((t - 0.8) / 0.2 * math.pi)
        p["Body"]["loc"] = (0, 0, -0.025 * k)
        p["Body"]["rot"] = (0.18 * k, 0, 0)
        p["Leg_L"]["rot"] = p["Leg_R"]["rot"] = (-0.25 * k, 0, 0)
        p["Foot_L"]["rot"] = p["Foot_R"]["rot"] = (0.25 * k, 0, 0)
        p["Neck"]["rot"] = (0.2 * k, 0, 0)
    return p


@clip("Swim", 32)
def swim(t):
    p = base_pose(False)
    w = 2 * math.pi * t
    # Paddeln: Beine kraeftig vor und zurueck, Fuesse klappen beim Vorziehen ein
    p["Leg_L"]["rot"] = (0.25 + 0.6 * math.sin(w), 0, 0)
    p["Leg_R"]["rot"] = (0.25 - 0.6 * math.sin(w), 0, 0)
    p["Foot_L"]["rot"] = (0.9 * max(0, math.cos(w)), 0, 0)
    p["Foot_R"]["rot"] = (0.9 * max(0, -math.cos(w)), 0, 0)
    p["Body"]["rot"] = (-0.06 + 0.02 * math.sin(2 * w), 0.04 * math.sin(w), 0)
    p["Body"]["loc"] = (0, 0, 0.004 * math.sin(2 * w))
    p["Neck"]["rot"] = (-0.12 + 0.05 * math.sin(2 * w + 1), 0, 0.1 * math.sin(w * 0.5 * 2))
    p["Head"]["rot"] = (0.05, 0, 0.25 * math.sin(w))
    p["Tail"]["rot"] = (-0.25, 0, 0.06 * math.sin(w))
    return p


def flight_body(p, t, w):
    # Beine nach hinten angelegt, Hals etwas vorgestreckt
    p["Leg_L"]["rot"] = p["Leg_R"]["rot"] = (1.35, 0, 0)
    p["Foot_L"]["rot"] = p["Foot_R"]["rot"] = (1.2, 0, 0)
    p["Neck"]["rot"] = (0.35, 0, 0)
    p["Head"]["rot"] = (-0.3, 0, 0)


@clip("Fly", 12)
def fly(t):
    p = base_pose(True)
    w = 2 * math.pi * t
    flight_body(p, t, w)
    c = math.cos(w)  # +1 oben, -1 unten
    for s in "LR":
        p["Wing_" + s]["rot"] = wingrot(s, 0.08 * math.sin(w), -0.55 * c + 0.08, 0.05)
        p["WingFore_" + s]["rot"] = wingrot(s, 0, -0.2 * math.cos(w - 0.6), -0.1 + 0.12 * math.sin(w))
        p["WingHand_" + s]["rot"] = wingrot(s, -0.1 * math.sin(w), -0.25 * math.cos(w - 1.1), 0.25 + 0.15 * math.sin(w))
    p["Body"]["loc"] = (0, 0, 0.02 * c)
    p["Body"]["rot"] = (0.04 * math.sin(w), 0, 0)
    p["Tail"]["rot"] = (-0.05 + 0.04 * math.sin(w), 0, 0)
    p["Head"]["rot"] = (-0.3 - 0.06 * c, 0, 0)
    return p


@clip("Glide", 48)
def glide(t):
    p = base_pose(True)
    w = 2 * math.pi * t
    flight_body(p, t, w)
    for s in "LR":
        m = 1 if s == "L" else -1
        p["Wing_" + s]["rot"] = wingrot(s, 0.0, -0.18 + 0.04 * math.sin(w) * m, 0.05)
        p["WingFore_" + s]["rot"] = wingrot(s, 0.0, 0.12, -0.05)
        p["WingHand_" + s]["rot"] = wingrot(s, -0.05, 0.12 + 0.03 * math.sin(w + 1), 0.3)
    p["Body"]["rot"] = (0, 0.05 * math.sin(w), 0)
    p["Head"]["rot"] = (-0.3, 0, 0.35 * math.sin(w))
    p["Tail"]["rot"] = (0, 0, 0.08 * math.sin(w))
    return p


@clip("Land", 14, loop=False)
def land(t):
    p = base_pose(t < 0.82)
    w = 2 * math.pi * t * 2
    # Bremsen: Koerper aufgerichtet, Fluegel nach vorn/oben schlagend, Beine nach vorn
    k = min(1.0, t / 0.3)
    p["Body"]["rot"] = (-0.45 * k * (1 - max(0, (t - 0.75) / 0.25)), 0, 0)
    for s in "LR":
        p["Wing_" + s]["rot"] = wingrot(s, -0.5 * k, -0.7 * math.cos(w), -0.35 * k)
        p["WingFore_" + s]["rot"] = wingrot(s, 0, -0.3 * math.cos(w - 0.6), -0.3)
        p["WingHand_" + s]["rot"] = wingrot(s, -0.2, -0.3 * math.cos(w - 1.1), 0.4)
    p["Leg_L"]["rot"] = p["Leg_R"]["rot"] = (-0.5 * k * (1 - max(0, (t - 0.75) / 0.25)), 0, 0)
    p["Foot_L"]["rot"] = p["Foot_R"]["rot"] = (-0.4 * k * (1 - max(0, (t - 0.75) / 0.25)), 0, 0)
    p["Neck"]["rot"] = (0.25, 0, 0)
    p["Tail"]["rot"] = (-0.4 * k, 0, 0)
    if t > 0.82:  # Aufsetzen mit kleinem Federn
        q = math.sin((t - 0.82) / 0.18 * math.pi)
        p["Body"]["loc"] = (0, 0, -0.02 * q)
    return p


@clip("Peck", 20)
def peck(t):
    p = base_pose(False)
    # Kopf zum Boden, zweimal picken, wieder hoch
    if t < 0.25:
        k = math.sin(t / 0.25 * math.pi / 2)
    elif t > 0.8:
        k = math.cos((t - 0.8) / 0.2 * math.pi / 2)
    else:
        k = 1.0
    pk = 0.0
    if 0.3 < t < 0.75:
        pk = abs(math.sin((t - 0.3) / 0.45 * 2 * math.pi))
    p["Body"]["rot"] = (0.45 * k, 0, 0)
    p["Body"]["loc"] = (0, 0, -0.015 * k)
    p["Neck"]["rot"] = (1.2 * k + 0.15 * pk, 0, 0)
    p["Head"]["rot"] = (0.35 * k + 0.15 * pk, 0, 0)
    p["Tail"]["rot"] = (-0.35 * k, 0, 0)
    p["Leg_L"]["rot"] = p["Leg_R"]["rot"] = (-0.45 * k, 0, 0)
    p["Foot_L"]["rot"] = p["Foot_R"]["rot"] = (0.45 * k, 0, 0)
    p["Jaw"]["rot"] = (0.25 * pk, 0, 0)
    return p


@clip("Squawk", 36)
def squawk(t):
    p = base_pose(False)
    # Langruf: Kopf runter, dann hochwerfen, Schnabel weit auf, Fluegel leicht abgespreizt
    if t < 0.25:
        k = math.sin(t / 0.25 * math.pi / 2)
        p["Neck"]["rot"] = (0.9 * k, 0, 0)
        p["Head"]["rot"] = (0.3 * k, 0, 0)
        p["Body"]["rot"] = (0.35 * k, 0, 0)
        p["Jaw"]["rot"] = (0.2 * k, 0, 0)
    elif t < 0.85:
        k = (t - 0.25) / 0.6
        e = 1 - (1 - min(1, k * 3)) ** 2
        cal = math.sin(k * math.pi * 6) * 0.5 + 0.5  # "kjau-kjau-kjau"
        p["Neck"]["rot"] = (lerp(0.9, -0.55, e), 0, 0)
        p["Head"]["rot"] = (lerp(0.3, -0.6, e) - 0.08 * cal, 0, 0)
        p["Body"]["rot"] = (lerp(0.35, -0.1, e), 0, 0)
        p["Jaw"]["rot"] = (0.25 + 0.4 * cal, 0, 0)
        for s in "LR":
            m = 1 if s == "L" else -1
            p["WingFold_" + s]["rot"] = (0, -0.25 * m * e, 0)
        p["Tail"]["rot"] = (-0.2 * e, 0, 0)
    else:
        k = math.cos((t - 0.85) / 0.15 * math.pi / 2)
        p["Neck"]["rot"] = (-0.55 * k, 0, 0)
        p["Head"]["rot"] = (-0.6 * k, 0, 0)
        p["Body"]["rot"] = (-0.1 * k, 0, 0)
        p["Jaw"]["rot"] = (0.25 * k, 0, 0)
        for s in "LR":
            m = 1 if s == "L" else -1
            p["WingFold_" + s]["rot"] = (0, -0.25 * m * k, 0)
    return p


def bake():
    for name, (frames, fn, loop) in CLIPS.items():
        tracks = {}
        for n in JOINTS:
            ob = OBJ[n]
            ob.animation_data_create()
            act = bpy.data.actions.new(f"{name}_{n}")
            ob.animation_data.action = act
            tracks[n] = act
        for fr in range(frames + 1):
            t = fr / frames
            if loop and fr == frames:
                t = 0.0
            if not loop:
                t = min(fr / frames, 0.999)
            pose = fn(t)
            for n in JOINTS:
                ob = OBJ[n]
                pp = pose[n]
                ob.location = REST_LOC[n] + Vector(pp["loc"])
                ob.rotation_euler = Euler(pp["rot"], 'XYZ')
                ob.scale = (pp["scl"],) * 3
                ob.keyframe_insert("location", frame=fr)
                ob.keyframe_insert("rotation_euler", frame=fr)
                ob.keyframe_insert("scale", frame=fr)
        for n in JOINTS:
            ob = OBJ[n]
            act = tracks[n]
            tr = ob.animation_data.nla_tracks.new()
            tr.name = name
            st = tr.strips.new(name, 0, act)
            st.name = name
            if hasattr(st, "action_slot") and st.action_slot is None and len(act.slots):
                st.action_slot = act.slots[0]
            ob.animation_data.action = None
    # Grundpose zuruecksetzen
    for n in JOINTS:
        ob = OBJ[n]
        ob.location = REST_LOC[n]
        ob.rotation_euler = (0, 0, 0)
    for s in "LR":
        OBJ["Wing_" + s].scale = (WING_FOLDED,) * 3


bake()
scene.frame_start, scene.frame_end = 0, 48

tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH')
print(f"[gull] Objekte: {len(scene.objects)}, Dreiecke: {tris}, Clips: {list(CLIPS)}")

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "seagull.blend"))
bpy.ops.export_scene.gltf(
    filepath=os.path.join(HERE, "seagull.glb"),
    export_format='GLB',
    export_animations=True,
    export_animation_mode='NLA_TRACKS',
    export_force_sampling=True,
    export_frame_step=1,
    export_optimize_animation_size=False,
    export_optimize_animation_keep_anim_object=True,
    export_apply=False,
    export_yup=True,
)
print("[gull] exportiert:", os.path.join(HERE, "seagull.glb"))
