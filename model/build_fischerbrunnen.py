"""
Fischerbrunnen / Fischmarkt Greifswald - stylisierte, "cozy" Low-Poly-Szene fuer three.js.

Aufruf:
  blender -b --factory-startup --python build_fischerbrunnen.py -- [--render]

Koordinaten: 1 Blender-Einheit = 1 m, Ursprung = Mitte des Brunnenbeckens, +X = Osten, +Y = Norden, Z = oben.
glTF-Export (Y-up): Norden = -Z, Osten = +X.
Positionen sind aus dem Satellitenbild abgeleitet (1178x1600 px skaliert, ca. 0,06 m/px, Brunnenmitte bei px 594/617).
"""
import bpy, bmesh, math, random, os, sys, json, functools
from contextlib import contextmanager
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "textures")
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
random.seed(42)


def P(px, py):
    """Satellitenbild-Pixel (1178x1600) -> Weltkoordinate in Metern."""
    return ((px - 594) * 0.06, (617 - py) * 0.06)


# ---------------------------------------------------------------- Szene leeren
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'


def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


COLS = {n: collection(n) for n in ["Ground", "Buildings", "Fountain", "Sculptures", "Vegetation", "Props", "Lights", "Markers", "Colliders"]}

# ---------------------------------------------------------------- Materialien
MATS = {}
UVSCALE = {}  # Material -> Kachelgroesse in Metern
IMAGES = {}


def image(name):
    if name not in IMAGES:
        IMAGES[name] = bpy.data.images.load(os.path.join(TEX, name))
    return IMAGES[name]


def mat(name, color, rough=0.85, metal=0.0, emit=None, emit_strength=1.0, alpha=1.0, tex=None, tex_scale=4.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1)
        bsdf.inputs["Emission Strength"].default_value = emit_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", 'BLENDED'), ("blend_method", 'BLEND')):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    if tex:
        it = nt.nodes.new("ShaderNodeTexImage")
        it.image = image(tex)
        if color == (1, 1, 1):
            nt.links.new(it.outputs["Color"], bsdf.inputs["Base Color"])
        else:  # Textur * Farbe -> glTF baseColorTexture + baseColorFactor
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs[0].default_value = 1.0
            nt.links.new(it.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*color, 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        UVSCALE[name] = tex_scale
    m.diffuse_color = (*color, alpha)
    MATS[name] = m
    return m


# Boden & Stein
mat("Cobble", (1, 1, 1), tex="cobble.png", tex_scale=3.0)
mat("Granite", (0.86, 0.84, 0.80), tex="granite.png", tex_scale=1.5)
mat("Granite_Dark", (0.62, 0.60, 0.58), tex="granite.png", tex_scale=1.5)
mat("Basin_Floor", (0.55, 0.72, 0.66), tex="granite.png", tex_scale=1.2)
mat("Water", (0.42, 0.78, 0.76), rough=0.05, alpha=0.72, emit=(0.2, 0.45, 0.45), emit_strength=0.15)
mat("Plinth", (0.58, 0.52, 0.47))
# Waende (Putz-Textur * Farbe)
WALLS = {
    "Wall_Rathaus_Red": (0.80, 0.27, 0.21),
    "Wall_Cream": (0.95, 0.88, 0.72),
    "Wall_Pink": (0.93, 0.72, 0.66),
    "Wall_White": (0.95, 0.94, 0.90),
    "Wall_Beige": (0.94, 0.80, 0.62),
    "Wall_Yellow": (0.98, 0.86, 0.50),
    "Wall_LightYellow": (0.98, 0.91, 0.64),
    "Wall_Green": (0.58, 0.77, 0.52),
    "Wall_Orange": (0.91, 0.47, 0.32),
    "Wall_GothicBlue": (0.84, 0.88, 0.93),
    "Wall_Mint": (0.72, 0.86, 0.76),
    "Wall_Modern": (0.86, 0.87, 0.86),
    "Wall_Peach": (0.97, 0.76, 0.58),
}
for n, c in WALLS.items():
    mat(n, c, tex="plaster.png", tex_scale=6.0)
# Daecher
mat("Roof_Terracotta", (0.78, 0.36, 0.22), tex="roof_tiles.png", tex_scale=2.4)
mat("Roof_TerracottaDark", (0.60, 0.26, 0.19), tex="roof_tiles.png", tex_scale=2.4)
mat("Roof_Brown", (0.55, 0.33, 0.25), tex="roof_tiles.png", tex_scale=2.4)
mat("Roof_Slate", (0.42, 0.44, 0.50), tex="roof_tiles.png", tex_scale=2.0)
mat("Roof_Flat", (0.55, 0.55, 0.52))
mat("Roof_Ridge", (0.50, 0.24, 0.17))
# Details
mat("Trim_White", (0.97, 0.95, 0.90))
mat("Trim_Cream", (0.95, 0.90, 0.78))
mat("Frame_Cream", (0.96, 0.93, 0.85))
mat("Frame_Grey", (0.42, 0.45, 0.50))
mat("Frame_Green", (0.40, 0.55, 0.45))
mat("Glass_Mint", (0.52, 0.78, 0.68), rough=0.2, emit=(0.45, 0.78, 0.62), emit_strength=0.25)
mat("Glass_Warm", (1.0, 0.78, 0.48), rough=0.3, emit=(1.0, 0.70, 0.36), emit_strength=0.55)
mat("Glass_Blue", (0.30, 0.45, 0.70), rough=0.2, emit=(0.30, 0.45, 0.7), emit_strength=0.15)
mat("Glass_Red", (0.75, 0.30, 0.25), rough=0.3, emit=(0.8, 0.3, 0.2), emit_strength=0.2)
mat("Wood_Door", (0.45, 0.28, 0.18))
mat("Wood_Light", (0.70, 0.50, 0.32))
mat("Dark_Arch", (0.18, 0.15, 0.16))
mat("Metal_Dark", (0.20, 0.24, 0.24), rough=0.5, metal=0.6)
mat("Metal_Green", (0.24, 0.36, 0.32), rough=0.5, metal=0.4)
mat("Metal_Zinc", (0.70, 0.72, 0.72), rough=0.4, metal=0.7)
mat("Gold", (0.95, 0.72, 0.30), rough=0.35, metal=0.9)
mat("Bronze", (0.25, 0.31, 0.28), rough=0.45, metal=0.45)
mat("Lamp_Glow", (1.0, 0.82, 0.50), emit=(1.0, 0.70, 0.35), emit_strength=4.0)
mat("Bulb_Glow", (1.0, 0.88, 0.60), emit=(1.0, 0.75, 0.40), emit_strength=6.0)
mat("Cable", (0.15, 0.13, 0.12))
# Stoffe / Deko
mat("Fabric_Cream", (0.96, 0.92, 0.82))
mat("Fabric_Teal", (0.36, 0.62, 0.60))
mat("Fabric_Orange", (0.96, 0.58, 0.30))
mat("Fabric_Red", (0.86, 0.32, 0.30))
mat("Fabric_Green", (0.42, 0.62, 0.40))
mat("Fabric_Mustard", (0.92, 0.72, 0.30))
mat("Wicker", (0.72, 0.52, 0.30))
mat("Chair_Dark", (0.25, 0.25, 0.27))
mat("Leaf_YellowGreen", (0.72, 0.78, 0.30))
mat("Leaf_Green", (0.44, 0.62, 0.28))
mat("Leaf_Dark", (0.30, 0.46, 0.24))
mat("Grass_Gold", (0.92, 0.78, 0.35))
mat("Grass_Green", (0.62, 0.72, 0.30))
mat("Bark", (0.42, 0.32, 0.24))
mat("Soil", (0.36, 0.26, 0.20))
for n, c in {"Flower_Red": (0.92, 0.20, 0.20), "Flower_Pink": (0.98, 0.50, 0.62), "Flower_Yellow": (1.0, 0.85, 0.25),
             "Flower_Violet": (0.52, 0.38, 0.85), "Flower_White": (0.98, 0.96, 0.92), "Flower_Orange": (1.0, 0.55, 0.20)}.items():
    mat(n, c)
FLOWERS = ["Flower_Red", "Flower_Pink", "Flower_Yellow", "Flower_Violet", "Flower_White", "Flower_Orange"]
mat("Car_Blue", (0.45, 0.60, 0.80), rough=0.4)
mat("Car_Cream", (0.95, 0.88, 0.70), rough=0.4)
mat("Car_Red", (0.85, 0.35, 0.30), rough=0.4)
mat("Tire", (0.12, 0.12, 0.13))
mat("Sign_Board", (0.20, 0.22, 0.20))
mat("Collider", (1, 0, 1))


# ---------------------------------------------------------------- Bauteile (Editor: app/editor.js)
# Bewegliche Objekte (Props, Skulpturen) merken sich pro Eckpunkt ihr Bauteil. Die Teile bilden einen Baum, ihr Pfad
# (z.B. "Cafe_Nord/Gruppe_03/Tisch_01/Stuhl_02") ist der Schluessel in model/edits.json. Ein Eintrag (three.js-Koordinaten):
#   {"offset": [x, y, z] (m, x = Ost, y = oben, z = Sued), "rotY": Grad, "scale": Faktor, "deleted": true}
# Verschiebung, Drehung und (gleichmaessige) Skalierung wirken um den Drehpunkt (Mitte der Grundflaeche) und auf alle Kinder.
# Kopien: "Cafe_Nord/Gruppe_01/Tisch_01+1": {"copyOf": "Cafe_Nord/Gruppe_01/Tisch_01", ...} - die Originalgeometrie der
# Quelle (samt Kindern, Pfade darunter wie beim Original) wird unter dem Elternteil der Kopie dupliziert.
# Die Aenderungen werden beim Bauen eingebacken; die Meshes bleiben zusammengefasst (gleiche Draw Calls).
PARTS = [None]  # id -> {"path", "parent", "kind", ...}; id 0 = kein Teil
PATH_ID = {}
PART_STACK = []
COPY_MAPS = []  # pro Kopie: Original-ID -> Kopie-ID (fuer die Kollider)
EDITS_FILE = os.path.join(HERE, "edits.json")
EDITS = json.load(open(EDITS_FILE, encoding="utf-8")) if os.path.exists(EDITS_FILE) else {}


@contextmanager
def part(name, root=False):
    """Alle Flaechen, die im Block entstehen, gehoeren zu diesem Teil. Ohne umgebendes Wurzelteil (z.B. Kuebel auf
    einem Dachgarten) passiert nichts."""
    if not root and not PART_STACK:
        yield 0
        return
    parent = 0 if root else PART_STACK[-1]
    if root:
        path = name
    else:
        n = sum(1 for p in PARTS[1:] if p["parent"] == parent and p["kind"] == name and not p.get("copy")) + 1
        path = f"{PARTS[parent]['path']}/{name}_{n:02d}"
    PARTS.append({"path": path, "parent": parent, "kind": name})
    pid = len(PARTS) - 1
    PATH_ID[path] = pid
    PART_STACK.append(pid)
    try:
        yield pid
    finally:
        PART_STACK.pop()


def as_part(kind):
    """Dekorator: jeder Aufruf der Funktion wird ein eigenes Teil (Stuhl_01, Stuhl_02, ...)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with part(kind):
                return fn(*args, **kwargs)
        return wrapper
    return deco


def current_part():
    return PART_STACK[-1] if PART_STACK else 0


def to_three(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


def edit_matrix(path, pivot):
    """Eintrag aus edits.json -> Matrix in Blender-Koordinaten (Drehung um three-Y = Drehung um Blender-Z)."""
    e = EDITS.get(path)
    if not e:
        return Matrix.Identity(4)
    ox, oy, oz = e.get("offset", (0, 0, 0))
    return (Matrix.Translation(pivot + Vector((ox, -oz, oy))) @ Matrix.Rotation(math.radians(e.get("rotY", 0)), 4, 'Z')
            @ Matrix.Scale(e.get("scale", 1), 4) @ Matrix.Translation(-pivot))


def chain(pid):
    out = []
    while pid:
        out.append(pid)
        pid = PARTS[pid]["parent"]
    return out[::-1]


def deleted(pid):
    return any(EDITS.get(PARTS[a]["path"], {}).get("deleted") for a in chain(pid))


def expand_parts(mb):
    """Vor dem Bauen eines Objekts mit Bauteilen: Drehpunkte bestimmen, Kopien aus edits.json anhaengen, geloeschte Teile
    entfernen. mb.v bleibt in Originallage (fuer die UVs), verschoben wird danach in place_parts.
    Gibt die Teil-Tabelle fuer die glTF-Extras zurueck."""
    own = {a for p in set(mb.vp) if p for a in chain(p)}
    # Drehpunkte aus der Originalgeometrie - unabhaengig von Kopien und Loeschungen, damit Aenderungen stabil bleiben
    lo, hi = {}, {}
    for co, p in zip(mb.v, mb.vp):
        for a in chain(p):
            lo[a] = tuple(map(min, lo.get(a, co), co))
            hi[a] = tuple(map(max, hi.get(a, co), co))
    for i in own:
        PARTS[i]["pivot"] = Vector(((lo[i][0] + hi[i][0]) / 2, (lo[i][1] + hi[i][1]) / 2, lo[i][2]))
    # Kopien (flachere Pfade zuerst, damit Kopien in Kopien ihr Elternteil vorfinden)
    n = len(mb.v)
    for path, e in sorted(EDITS.items(), key=lambda t: t[0].count("/")):
        src = PATH_ID.get(e.get("copyOf"))
        if not src or src not in own or e.get("deleted"):
            continue
        parent_path = path.rpartition("/")[0]
        parent = PATH_ID.get(parent_path, 0)
        if PARTS[src].get("copy") or path in PATH_ID or (parent_path and parent not in own):
            print("WARNUNG: Kopie uebersprungen:", path)
            continue
        m = {}
        for i in sorted(own):
            if not PARTS[i].get("copy") and src in chain(i):
                m[i] = len(PARTS)
                PARTS.append({"path": path + PARTS[i]["path"][len(PARTS[src]["path"]):], "kind": PARTS[i]["kind"], "copy": True,
                              "parent": parent if i == src else m[PARTS[i]["parent"]], "pivot": PARTS[i]["pivot"]})
                PATH_ID[PARTS[-1]["path"]] = m[i]
        COPY_MAPS.append(m)
        own |= set(m.values())
        vmap = {}
        for k in range(n):
            if mb.vp[k] in m:
                vmap[k] = len(mb.v)
                mb.v.append(mb.v[k])
                mb.vp.append(m[mb.vp[k]])
        for fc, mat in list(zip(mb.f, mb.m)):
            if fc[0] in vmap:
                mb.f.append([vmap[k] for k in fc])
                mb.m.append(mat)
    for i in sorted(own):  # Eltern haben kleinere IDs als ihre Kinder
        pt = PARTS[i]
        pt["N"] = (PARTS[pt["parent"]]["N"] if pt["parent"] else Matrix.Identity(4)) @ edit_matrix(pt["path"], pt["pivot"])
    # Loeschen: Flaechen weg, dann unbenutzte Eckpunkte entfernen
    dead = {i for i in own if deleted(i)}
    if dead:
        keep = [k for k, fc in enumerate(mb.f) if mb.vp[fc[0]] not in dead]
        mb.f, mb.m = [mb.f[k] for k in keep], [mb.m[k] for k in keep]
        used = sorted({k for fc in mb.f for k in fc})
        remap = {k: j for j, k in enumerate(used)}
        mb.v, mb.vp = [mb.v[k] for k in used], [mb.vp[k] for k in used]
        mb.f = [[remap[k] for k in fc] for fc in mb.f]
    return [[i, PARTS[i]["parent"], PARTS[i]["path"], to_three(PARTS[i]["pivot"]), EDITS.get(PARTS[i]["path"])] for i in sorted(own)]


def place_parts(me, vp):
    """edits.json auf die Eckpunkte anwenden (nach den UVs: die Textur bleibt am Teil wie im Editor), Teil-ID als Attribut _part."""
    for v, p in zip(me.vertices, vp):
        if p:
            v.co = PARTS[p]["N"] @ v.co
    me.attributes.new("_part", 'FLOAT', 'POINT').data.foreach_set("value", [float(p) for p in vp])


# ---------------------------------------------------------------- Mesh-Builder
class MB:
    def __init__(self):
        self.v, self.f, self.m = [], [], []
        self.vp = []  # Bauteil-ID pro Eckpunkt

    def poly(self, verts, faces, m):
        b = len(self.v)
        self.v += [tuple(x) for x in verts]
        self.vp += [current_part()] * (len(self.v) - b)
        for fc in faces:
            self.f.append([b + i for i in fc])
            self.m.append(m)

    def box(self, mn, mx, m, rz=0.0, pivot=None):
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        vs = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        if rz:
            c = Vector(pivot) if pivot else Vector(((x0 + x1) / 2, (y0 + y1) / 2, 0))
            R = Matrix.Rotation(rz, 3, 'Z')
            vs = [tuple(R @ (Vector(p) - c) + c) for p in vs]
        self.poly(vs, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], m)

    def cbox(self, c, size, m, rz=0.0):
        h = Vector(size) / 2
        self.box(Vector(c) - h, Vector(c) + h, m, rz)

    def bm(self, bm, matrix, m):
        bm.verts.ensure_lookup_table()
        b = len(self.v)
        idx = {v: i for i, v in enumerate(bm.verts)}
        self.v += [tuple(matrix @ v.co) for v in bm.verts]
        self.vp += [current_part()] * len(bm.verts)
        for fc in bm.faces:
            self.f.append([b + idx[v] for v in fc.verts])
            self.m.append(m)
        bm.free()

    def merge(self, other):
        b = len(self.v)
        self.v += other.v
        self.f += [[i + b for i in fc] for fc in other.f]
        self.m += other.m
        self.vp += other.vp

    def transformed(self, matrix):
        o = MB()
        o.v = [tuple(matrix @ Vector(p)) for p in self.v]
        o.f, o.m, o.vp = [list(x) for x in self.f], list(self.m), list(self.vp)
        return o

    def build(self, name, col, bevel=0.0, loc=(0, 0, 0)):
        parts = expand_parts(self) if any(self.vp) else None  # Kopien/Loeschungen aus edits.json
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        names = []
        for m in self.m:
            if m not in names:
                names.append(m)
        for n in names:
            me.materials.append(MATS[n])
        for i, poly in enumerate(me.polygons):
            poly.material_index = names.index(self.m[i])
        # UVs: pro Flaeche planar im Flaechen-Tangentialraum (weltbasiert -> nahtlose Kacheln)
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            n = poly.normal
            if abs(n.z) > 0.97:
                t = Vector((1, 0, 0))
            else:
                t = Vector((0, 0, 1)).cross(n).normalized()
            bvec = n.cross(t)
            sc = UVSCALE.get(names[poly.material_index], 2.0)
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co + Vector(loc)
                uv.data[li].uv = (co.dot(t) / sc, co.dot(bvec) / sc)
        if parts:
            place_parts(me, self.vp)
        bmx = bmesh.new()
        bmx.from_mesh(me)
        if parts:  # nur innerhalb eines Teils verschmelzen, sonst kleben Teile aneinander
            layer = bmx.verts.layers.float.get("_part")
            groups = {}
            for v in bmx.verts:
                groups.setdefault(v[layer], []).append(v)
            for vs in groups.values():
                bmesh.ops.remove_doubles(bmx, verts=vs, dist=0.0005)
        else:
            bmesh.ops.remove_doubles(bmx, verts=bmx.verts, dist=0.0005)
        bmesh.ops.recalc_face_normals(bmx, faces=bmx.faces)
        bmx.to_mesh(me)
        bmx.free()
        ob = bpy.data.objects.new(name, me)
        if parts:
            ob["parts"] = json.dumps(parts, separators=(",", ":"))
        ob.location = loc
        col.objects.link(ob)
        if bevel > 0:
            md = ob.modifiers.new("Bevel", 'BEVEL')
            md.width = bevel
            md.segments = 1
            md.limit_method = 'ANGLE'
            md.angle_limit = math.radians(40)
            md.harden_normals = False
        for poly in me.polygons:
            poly.use_smooth = False
        return ob


def aligned(p1, p2):
    """Matrix, die die Z-Achse von p1 nach p2 legt (Mitte)."""
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    L = d.length
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return Matrix.Translation((p1 + p2) / 2) @ q.to_matrix().to_4x4(), L


def limb(mb, p1, p2, r1, r2, m, seg=8, caps=True):
    M, L = aligned(p1, p2)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r1, radius2=r2, depth=max(L, 0.001))
    mb.bm(bm, M, m)
    if caps:
        sphere(mb, p2, r2 * 1.02, m, sub=1)


def sphere(mb, c, r, m, sub=1, scale=(1, 1, 1), jitter=0.0, rz=0.0):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    if jitter:
        for v in bm.verts:
            v.co *= 1 + random.uniform(-jitter, jitter)
    M = Matrix.Translation(c) @ Matrix.Rotation(rz, 4, 'Z') @ Matrix.Diagonal((r * scale[0], r * scale[1], r * scale[2], 1))
    mb.bm(bm, M, m)


def cyl(mb, c, r, h, m, seg=12, axis='Z', r2=None, rot=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h)
    R = Matrix.Identity(4)
    if axis == 'X':
        R = Matrix.Rotation(math.pi / 2, 4, 'Y')
    elif axis == 'Y':
        R = Matrix.Rotation(math.pi / 2, 4, 'X')
    mb.bm(bm, Matrix.Translation(c) @ Matrix.Rotation(rot, 4, 'Z') @ R, m)


def torus(mb, c, R, r, m, seg=14, rseg=4, axis_rot=None):
    vs, fs = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            vs.append(Vector(((R + r * math.cos(b)) * math.cos(a), r * math.sin(b), (R + r * math.cos(b)) * math.sin(a))))
    for i in range(seg):
        for j in range(rseg):
            a, b2 = i * rseg + j, i * rseg + (j + 1) % rseg
            c2, d = ((i + 1) % seg) * rseg + (j + 1) % rseg, ((i + 1) % seg) * rseg + j
            fs.append((a, b2, c2, d))
    M = Matrix.Translation(c) @ (axis_rot or Matrix.Identity(4))
    mb.poly([M @ v for v in vs], fs, m)


def slab(mb, top, thick, m):
    """Platte aus 4 oberen Eckpunkten, nach unten extrudiert."""
    bot = [Vector(p) - Vector((0, 0, thick)) for p in top]
    mb.poly([*top, *bot], [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)], m)


# ---------------------------------------------------------------- Fassaden-Helfer
def face_box(mb, face, plane, u, z0, w, h, out, inn, m):
    if face == 'S':
        mb.box((u - w / 2, plane - out, z0), (u + w / 2, plane + inn, z0 + h), m)
    elif face == 'N':
        mb.box((u - w / 2, plane - inn, z0), (u + w / 2, plane + out, z0 + h), m)
    elif face == 'W':
        mb.box((plane - out, u - w / 2, z0), (plane + inn, u + w / 2, z0 + h), m)
    else:
        mb.box((plane - inn, u - w / 2, z0), (plane + out, u + w / 2, z0 + h), m)


def face_point(face, plane, u, z, out):
    return {'S': (u, plane - out, z), 'N': (u, plane + out, z), 'W': (plane - out, u, z), 'E': (plane + out, u, z)}[face]


def face_disc(mb, face, plane, u, z, r, out, m, seg=12):
    axis = 'Y' if face in 'NS' else 'X'
    c = face_point(face, plane, u, z, out / 2)
    cyl(mb, c, r, out + 0.02, m, seg=seg, axis=axis)


def window(mb, face, plane, u, z0, w, h, frame="Frame_Cream", glass=None, arch=False, box=None, shutters=None):
    glass = glass or ("Glass_Warm" if random.random() < 0.22 else "Glass_Mint")
    face_box(mb, face, plane, u, z0 - 0.08, w + 0.24, h + 0.16, 0.06, 0.05, frame)
    face_box(mb, face, plane, u, z0, w, h, 0.09, 0.05, glass)
    if arch:
        face_disc(mb, face, plane, u, z0 + h, w / 2 + 0.12, 0.06, frame)
        face_disc(mb, face, plane, u, z0 + h, w / 2, 0.09, glass)
    face_box(mb, face, plane, u, z0 + h * 0.62, w, 0.06, 0.12, 0.0, frame)  # Kaempfer
    face_box(mb, face, plane, u, z0, 0.06, h, 0.12, 0.0, frame)  # Mittelpfosten
    face_box(mb, face, plane, u, z0 - 0.14, w + 0.3, 0.08, 0.16, 0.0, frame)  # Sims
    if box or (box is None and random.random() < 0.12):
        flowerbox(mb, face, plane, u, z0 - 0.12, w)
    if shutters:
        for s in (-1, 1):
            face_box(mb, face, plane, u + s * (w / 2 + 0.3), z0, 0.45, h, 0.1, 0.0, shutters)


def flowerbox(mb, face, plane, u, z, w):
    face_box(mb, face, plane, u, z - 0.25, w, 0.25, 0.32, 0.0, "Wood_Light")
    n = max(3, int(w / 0.22))
    for i in range(n):
        uu = u - w / 2 + 0.1 + i * (w - 0.2) / max(1, n - 1)
        c = face_point(face, plane, uu, z + 0.02, 0.17)
        sphere(mb, c, 0.13, "Leaf_Green", sub=1, jitter=0.15)
        sphere(mb, Vector(c) + Vector((0, 0, 0.08)), 0.08, random.choice(FLOWERS), sub=1)


def door(mb, face, plane, u, w=1.3, h=2.5, m="Wood_Door", frame="Trim_White", pots=True):
    if pots and m == "Wood_Door":
        for s in (-1, 1):
            c = face_point(face, plane, u + s * (w / 2 + 0.55), 0.0, 0.4)
            cyl(mb, (c[0], c[1], 0.25), 0.22, 0.5, "Wall_Orange", seg=8, r2=0.28)
            sphere(mb, (c[0], c[1], 0.75), 0.36, random.choice(["Leaf_Green", "Leaf_Dark"]), sub=1, jitter=0.15)
            for k in range(3):
                sphere(mb, (c[0] + random.uniform(-0.2, 0.2), c[1] + random.uniform(-0.2, 0.2), 0.95), 0.08, random.choice(FLOWERS), sub=1)
    face_box(mb, face, plane, u, 0, w + 0.3, h + 0.2, 0.06, 0.05, frame)
    face_box(mb, face, plane, u, 0, w, h, 0.09, 0.05, m)
    face_box(mb, face, plane, u, h * 0.72, w, 0.05, 0.12, 0.0, frame)
    face_box(mb, face, plane, u, 0, 0.6, 0.12, 0.6, 0.0, "Granite_Dark")  # Stufe


def shopfront(mb, face, plane, u0, u1, z_top, awning=None, door_every=3, frame="Frame_Green"):
    L = u1 - u0
    n = max(1, int(L / 3.2))
    step = L / n
    for i in range(n):
        u = u0 + step * (i + 0.5)
        if i % door_every == 1:
            door(mb, face, plane, u, w=1.5, h=2.7, m="Glass_Warm", frame=frame)
        else:
            face_box(mb, face, plane, u, 0.0, step - 0.5, 0.5, 0.08, 0.05, "Plinth")
            face_box(mb, face, plane, u, 0.5, step - 0.5, z_top - 0.9, 0.06, 0.05, frame)
            face_box(mb, face, plane, u, 0.6, step - 0.75, z_top - 1.1, 0.09, 0.05, "Glass_Warm" if random.random() < 0.5 else "Glass_Mint")
    if awning:
        d = 1.4
        for i in range(n):
            u = u0 + step * (i + 0.5)
            w = step - 0.3
            a, b = u - w / 2, u + w / 2
            z1, z2 = z_top - 0.1, z_top - 0.75
            if face == 'E':
                top = [(plane, a, z1), (plane, b, z1), (plane + d, b, z2), (plane + d, a, z2)]
            elif face == 'W':
                top = [(plane - d, a, z2), (plane - d, b, z2), (plane, b, z1), (plane, a, z1)]
            elif face == 'S':
                top = [(a, plane - d, z2), (b, plane - d, z2), (b, plane, z1), (a, plane, z1)]
            else:
                top = [(a, plane, z1), (b, plane, z1), (b, plane + d, z2), (a, plane + d, z2)]
            slab(mb, [Vector(p) for p in top], 0.08, awning)
            face_box(mb, face, plane, u, z2 - 0.32, w, 0.32, d + 0.02, -d + 0.06, awning)  # Volant


def ivy(mb, face, plane, u, z_top, width, height):
    for i in range(int(width * height * 3)):
        uu = u + random.uniform(-width / 2, width / 2)
        zz = random.uniform(0, height) * random.random() ** 0.3
        c = face_point(face, plane, uu, zz, 0.08)
        sphere(mb, c, random.uniform(0.25, 0.45), random.choice(["Leaf_YellowGreen", "Leaf_Green", "Leaf_Dark"]),
               sub=1, scale=(1, 0.45, 1) if face in 'NS' else (0.45, 1, 1), jitter=0.2)


# ---------------------------------------------------------------- Gebaeude
def pent_prism(mb, a0, a1, b0, b1, eave, roof_h, axis, m):
    """Hauskoerper mit Giebeldreiecken; First entlang 'axis' ('x' oder 'y')."""
    bc = (b0 + b1) / 2
    prof = [(b0, 0), (b1, 0), (b1, eave), (bc, eave + roof_h), (b0, eave)]

    def V(a, b, z):
        return (a, b, z) if axis == 'x' else (b, a, z)
    vs = [V(a0, b, z) for b, z in prof] + [V(a1, b, z) for b, z in prof]
    fs = [(0, 1, 2, 3, 4), (9, 8, 7, 6, 5)] + [(i, (i + 1) % 5, (i + 1) % 5 + 5, i + 5) for i in range(5)]
    mb.poly(vs, fs, m)


def gable_roof(mb, a0, a1, b0, b1, eave, roof_h, axis, m, ov=0.45, ov_a0=0.45, ov_a1=0.45, thick=0.28):
    bc = (b0 + b1) / 2
    half = (b1 - b0) / 2
    s = roof_h / half
    lift = 0.12

    def V(a, b, z):
        return Vector((a, b, z)) if axis == 'x' else Vector((b, a, z))
    za = eave - ov * s + lift
    zr = eave + roof_h + lift
    A0, A1 = a0 - ov_a0, a1 + ov_a1
    slab(mb, [V(A0, b0 - ov, za), V(A1, b0 - ov, za), V(A1, bc, zr), V(A0, bc, zr)], thick, m)
    slab(mb, [V(A0, bc, zr), V(A1, bc, zr), V(A1, b1 + ov, za), V(A0, b1 + ov, za)], thick, m)
    # Firstziegel
    p, q = V(A0, bc, zr + 0.05), V(A1, bc, zr + 0.05)
    limb(mb, p, q, 0.16, 0.16, "Roof_Ridge", seg=6, caps=False)


def hip_roof(mb, x0, x1, y0, y1, eave, roof_h, m, ov=0.45):
    X0, X1, Y0, Y1 = x0 - ov, x1 + ov, y0 - ov, y1 + ov
    w, d = X1 - X0, Y1 - Y0
    half = min(w, d) / 2
    s = roof_h / ((min(x1 - x0, y1 - y0)) / 2)
    zb = eave - ov * s + 0.12
    zt = zb + half * s
    if w >= d:
        r0, r1 = (X0 + half, (Y0 + Y1) / 2, zt), (X1 - half, (Y0 + Y1) / 2, zt)
    else:
        r0, r1 = ((X0 + X1) / 2, Y0 + half, zt), ((X0 + X1) / 2, Y1 - half, zt)
    vs = [(X0, Y0, zb), (X1, Y0, zb), (X1, Y1, zb), (X0, Y1, zb), r0, r1]
    if w >= d:
        fs = [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4), (3, 2, 1, 0)]
    else:
        fs = [(0, 1, 4), (1, 2, 5, 4), (2, 3, 5), (3, 0, 4, 5), (3, 2, 1, 0)]
    mb.poly(vs, fs, m)
    if Vector(r0) != Vector(r1):
        limb(mb, Vector(r0) + Vector((0, 0, 0.05)), Vector(r1) + Vector((0, 0, 0.05)), 0.16, 0.16, "Roof_Ridge", seg=6, caps=False)


def mansard_roof(mb, x0, x1, y0, y1, eave, roof_h, m, inset=1.4):
    X0, X1, Y0, Y1 = x0 - 0.25, x1 + 0.25, y0 - 0.25, y1 + 0.25
    zb, zm = eave + 0.05, eave + roof_h * 0.72
    vs = [(X0, Y0, zb), (X1, Y0, zb), (X1, Y1, zb), (X0, Y1, zb),
          (x0 + inset, y0 + inset, zm), (x1 - inset, y0 + inset, zm), (x1 - inset, y1 - inset, zm), (x0 + inset, y1 - inset, zm)]
    mb.poly(vs, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (3, 2, 1, 0), (4, 5, 6, 7)], m)
    hip_roof(mb, x0 + inset, x1 - inset, y0 + inset, y1 - inset, zm, roof_h * 0.28, m, ov=0.1)


def stepped_gable(mb, face, plane, uc, half, eave, roof_h, steps, wall, trim, style):
    t = 0.5
    dz = roof_h / steps
    for j in range(steps):
        zb = eave + j * dz
        hw = half * (1 - j / steps) + (0.15 if j == 0 else 0)
        face_box(mb, face, plane, uc, zb - 0.3, 2 * hw, dz + 0.3, 0.02, t, wall)
        face_box(mb, face, plane, uc, zb + dz, 2 * hw + 0.12, 0.16, 0.08, t + 0.08, trim)  # Abdeckung
        for s in (-1, 1):
            u = uc + s * hw
            if style == 'gothic':
                face_box(mb, face, plane, u - s * 0.3, zb, 0.6, dz * 1.45, 0.1, t + 0.05, wall)
                face_box(mb, face, plane, u - s * 0.3, zb + dz * 1.45, 0.7, 0.15, 0.15, t + 0.1, trim)
                p = face_point(face, plane, u - s * 0.3, zb + dz * 1.45, -t / 2)
                limb(mb, p, Vector(p) + Vector((0, 0, 0.7)), 0.28, 0.02, wall, seg=4, caps=False)
            elif style == 'volute':
                face_disc(mb, face, plane, u + s * 0.05, zb + dz * 0.38, dz * 0.42, t + 0.12, trim, seg=10)
                face_disc(mb, face, plane, u + s * 0.05, zb + dz * 0.38, dz * 0.25, t + 0.2, wall, seg=10)
                if j % 2 == 0:
                    p = face_point(face, plane, u - s * 0.15, zb + dz + 0.16, -t / 2)
                    sphere(mb, Vector(p) + Vector((0, 0, 0.18)), 0.18, trim, sub=1)
    ztop = eave + roof_h
    face_box(mb, face, plane, uc, ztop - 0.2, 1.4, 1.2, 0.02, t, wall)
    face_box(mb, face, plane, uc, ztop + 1.0, 1.6, 0.18, 0.08, t + 0.08, trim)
    if style == 'gothic':
        for s in (-1, 1):
            u = uc + s * 0.55
            face_box(mb, face, plane, u, ztop, 0.55, 2.4, 0.12, t + 0.05, wall)
            p = face_point(face, plane, u, ztop + 2.4, -t / 2)
            limb(mb, p, Vector(p) + Vector((0, 0, 0.8)), 0.3, 0.02, wall, seg=4, caps=False)
    return ztop + 1.2


def gable_windows(mb, face, plane, uc, half, eave, roof_h, rows, frame, glass=None, arch=False, w=0.9, h=1.3, spacing=2.2):
    for r in range(rows):
        z0 = eave + 1.0 + r * (roof_h - 1.5) / max(rows, 1)
        hw = half * (1 - (z0 + h - eave) / roof_h) - 0.7
        if hw < w / 2:
            break
        n = max(1, int((2 * hw) / spacing) + 1)
        if n == 1:
            us = [uc]
        else:
            us = [uc - hw + w / 2 + i * (2 * hw - w) / (n - 1) for i in range(n)]
        for u in us:
            window(mb, face, plane, u, z0, w, h, frame, glass=glass, arch=arch, box=False)


def house(name, x0, x1, y0, y1, eave, roof="gable_x", roof_h=6.0, wall="Wall_Cream", roofmat="Roof_Terracotta",
          floors=3, faces="NSEW", shop=(), awning=None, gables=None, frame="Frame_Cream", cornice="Trim_White",
          dormers=(), doors=None, ivy_faces=(), win_w=1.15, win_h=1.65, spacing=2.9, arch_windows=False,
          gable_rows=3, gable_glass=None, glass=None, extra=None, plinth=True, shutters=None):
    body, det = MB(), MB()
    gables = gables or {}
    doors = doors or {}
    if roof == "gable_x":
        pent_prism(body, x0, x1, y0, y1, eave, roof_h, 'x', wall)
        gable_roof(body, x0, x1, y0, y1, eave, roof_h, 'x', roofmat,
                   ov_a0=0.0 if gables.get('W') not in (None, 'plain') else 0.45,
                   ov_a1=0.0 if gables.get('E') not in (None, 'plain') else 0.45)
    elif roof == "gable_y":
        pent_prism(body, y0, y1, x0, x1, eave, roof_h, 'y', wall)
        gable_roof(body, y0, y1, x0, x1, eave, roof_h, 'y', roofmat,
                   ov_a0=0.0 if gables.get('S') not in (None, 'plain') else 0.45,
                   ov_a1=0.0 if gables.get('N') not in (None, 'plain') else 0.45)
    else:
        body.box((x0, y0, 0), (x1, y1, eave), wall)
        if roof == "hip":
            hip_roof(body, x0, x1, y0, y1, eave, roof_h, roofmat)
        elif roof == "mansard":
            mansard_roof(body, x0, x1, y0, y1, eave, roof_h, roofmat)
        elif roof == "flat":
            body.box((x0 + 0.3, y0 + 0.3, eave), (x1 - 0.3, y1 - 0.3, eave + 0.1), "Roof_Flat")
            for (a, b) in [((x0, y0), (x1, y0 + 0.3)), ((x0, y1 - 0.3), (x1, y1)), ((x0, y0), (x0 + 0.3, y1)), ((x1 - 0.3, y0), (x1, y1))]:
                body.box((a[0], a[1], eave), (b[0], b[1], eave + 0.7), cornice)
    if plinth:
        det.box((x0 - 0.06, y0 - 0.06, 0), (x1 + 0.06, y1 + 0.06, 0.45), "Plinth")
    if cornice and roof != "flat":
        det.box((x0 - 0.15, y0 - 0.15, eave - 0.35), (x1 + 0.15, y1 + 0.15, eave), cornice)
    gh = 4.2 if shop else 3.6
    upper = (eave - gh - 0.5) / max(1, floors - 1)
    levels = [(1.1, 0)] + [(gh + 0.6 + i * upper, i + 1) for i in range(floors - 1)]
    if cornice and floors > 1 and roof != "flat":
        det.box((x0 - 0.08, y0 - 0.08, gh - 0.1), (x1 + 0.08, y1 + 0.08, gh + 0.1), cornice)
    spans = {'S': (y0, x0, x1), 'N': (y1, x0, x1), 'W': (x0, y0, y1), 'E': (x1, y0, y1)}
    for fc in faces:
        plane, a0, a1 = spans[fc]
        L = a1 - a0
        n = max(1, int((L - 2.0) / spacing) + 1)
        us = [a0 + L / 2] if n == 1 else [a0 + 1.4 + i * (L - 2.8) / (n - 1) for i in range(n)]
        if fc in shop:
            shopfront(det, fc, plane, a0 + 0.4, a1 - 0.4, gh, awning=awning)
        dlist = doors.get(fc, [])
        for z, lvl in levels:
            if lvl == 0 and fc in shop:
                continue
            for u in us:
                if lvl == 0 and any(abs(u - d) < 1.3 for d in dlist):
                    continue
                window(det, fc, plane, u, z, win_w, win_h, frame, glass=glass, arch=arch_windows, shutters=shutters)
        for d in dlist:
            door(det, fc, plane, d)
        # Giebel
        style = gables.get(fc)
        is_gable_face = (roof == "gable_x" and fc in "WE") or (roof == "gable_y" and fc in "SN")
        if is_gable_face:
            half = (y1 - y0) / 2 if roof == "gable_x" else (x1 - x0) / 2
            uc = a0 + L / 2
            if style in ("stepped", "volute", "gothic"):
                steps = max(3, int(roof_h / 1.9))
                stepped_gable(det, fc, plane, uc, half, eave, roof_h, steps, wall, cornice or "Trim_White", style)
            gable_windows(det, fc, plane, uc, half, eave, roof_h, gable_rows, frame, glass=gable_glass, arch=arch_windows)
    # Gauben
    for (fc, us) in dormers:
        for u in us:
            dormer(det, fc, x0, x1, y0, y1, eave, roof_h, roof, u, wall, roofmat, frame)
    for (fc, u, w, h) in ivy_faces:
        plane = spans[fc][0]
        ivy(det, fc, plane, u, eave, w, h)
    if extra:
        extra(body, det)
    ob = body.build(name, COLS["Buildings"], bevel=0.06)
    dob = det.build(name + "_Details", COLS["Buildings"])
    join(ob, [dob])
    collider(name, x0, x1, y0, y1, eave)
    return ob


def dormer(mb, fc, x0, x1, y0, y1, eave, roof_h, roof, u, wall, roofmat, frame):
    w, h = 1.6, 1.7
    if roof == "gable_y":
        half = (x1 - x0) / 2
        dist = 1.6
        plane = x1 - dist if fc == 'E' else x0 + dist
        zb = eave + roof_h * dist / half
        depth = 2.2
        if fc == 'E':
            mb.box((plane - depth, u - w / 2, zb - 0.6), (plane, u + w / 2, zb + h), wall)
        else:
            mb.box((plane, u - w / 2, zb - 0.6), (plane + depth, u + w / 2, zb + h), wall)
        window(mb, fc, plane, u, zb, w - 0.6, h - 0.5, frame, box=False)
        sgn = 1 if fc == 'E' else -1
        a0, a1 = (plane - depth, plane + 0.3) if fc == 'E' else (plane - 0.3, plane + depth)
        gable_roof(mb, a0, a1, u - w / 2 - 0.1, u + w / 2 + 0.1, zb + h, 0.9, 'x', roofmat, ov=0.15, ov_a0=0, ov_a1=0, thick=0.15)
    else:
        half = (y1 - y0) / 2
        dist = 1.6
        plane = y0 + dist if fc == 'S' else y1 - dist
        zb = eave + roof_h * dist / half
        depth = 2.2
        if fc == 'S':
            mb.box((u - w / 2, plane, zb - 0.6), (u + w / 2, plane + depth, zb + h), wall)
            b0, b1 = plane - 0.3, plane + depth
        else:
            mb.box((u - w / 2, plane - depth, zb - 0.6), (u + w / 2, plane, zb + h), wall)
            b0, b1 = plane - depth, plane + 0.3
        window(mb, fc, plane, u, zb, w - 0.6, h - 0.5, frame, box=False)
        gable_roof(mb, b0, b1, u - w / 2 - 0.1, u + w / 2 + 0.1, zb + h, 0.9, 'y', roofmat, ov=0.15, ov_a0=0, ov_a1=0, thick=0.15)


def join(target, others):
    others = [o for o in others if o]
    for o in others:
        for md in list(o.modifiers):
            pass
    bpy.ops.object.select_all(action='DESELECT')
    # Bevel anwenden, dann Details anhaengen
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    for md in list(target.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)
    for o in others:
        o.select_set(True)
    bpy.ops.object.join()


def collider(name, x0, x1, y0, y1, h):
    mb = MB()
    mb.box((x0, y0, 0), (x1, y1, h), "Collider")
    ob = mb.build("COL_" + name, COLS["Colliders"])
    ob.hide_render = True
    ob.display_type = 'WIRE'
    return ob


def chimney(det, x, y, z0, h=1.6, m="Wall_Orange"):
    det.box((x - 0.35, y - 0.35, z0), (x + 0.35, y + 0.35, z0 + h), m)
    det.box((x - 0.45, y - 0.45, z0 + h), (x + 0.45, y + 0.45, z0 + h + 0.15), "Trim_Cream")


# ================================================================ BODEN
SMALL_COLS = []  # (name, x0, x1, y0, y1, h, teil) - gebaut ganz am Ende, wenn Kopien und Loeschungen feststehen


def small_col(x, y, hx, hy, h=1.0):
    n = sum(1 for c in SMALL_COLS if c[0].startswith("COL_prop"))
    SMALL_COLS.append((f"COL_prop_{n:03d}", x - hx, x + hx, y - hy, y + hy, h, current_part()))


def part_collider(name, x0, x1, y0, y1, h, pid):
    """Kollisionsbox eines Bauteils: bewegt sich mit dem Teil (achsparallele Huelle der verschobenen Box).
    Die unverschobene Box steht in den Extras, damit der Editor sie zur Laufzeit genauso nachfuehren kann."""
    N = PARTS[pid]["N"] if pid else Matrix.Identity(4)
    pts = [N @ Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (0, h)]
    mb = MB()
    mb.box(tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3)), "Collider")
    ob = mb.build(name, COLS["Colliders"])
    ob.display_type = 'WIRE'
    if pid:
        ob["part"] = PARTS[pid]["path"]
        ob["box"] = [x0, 0.0, -y1, x1, h, -y0]  # three.js: min xyz, max xyz
    return ob


def build_small_colliders():
    for name, x0, x1, y0, y1, h, pid in SMALL_COLS:
        variants = [(name, pid)] + [(f"{name}_k{j}", m[pid]) for j, m in enumerate(COPY_MAPS) if pid in m]
        for nm, q in variants:
            if not (q and deleted(q)):
                part_collider(nm, x0, x1, y0, y1, h, q)


def ground():
    mb = MB()
    mb.box((-40, -64, -0.4), (40, 41, 0.0), "Cobble")
    gr = MB()
    # Granitplattenband um den Brunnen
    gr.box((-5.6, -5.4, 0.0), (5.6, 5.4, 0.03), "Granite")
    # Rinnen (Entwaesserung) quer ueber den Platz
    for y in (-14.0, -28.5):
        gr.box((-17.6, y - 0.25, 0.0), (13.8, y + 0.25, 0.025), "Granite_Dark")
    gr.box((-8.2, -64, 0.0), (-7.7, -5.4, 0.025), "Granite_Dark")
    # Kanaldeckel
    for (x, y) in [(6.5, -8.0), (-10.0, -12.0), (3.0, -20.0), (-12.0, 4.0)]:
        cyl(gr, (x, y, 0.015), 0.35, 0.03, "Metal_Dark", seg=12)
    mb.merge(gr)
    ob = mb.build("Ground_Fischmarkt", COLS["Ground"])
    return ob


# ================================================================ BRUNNEN
BX, BY = 3.8, 3.6  # halbe Beckenmasse (aus Satellitenbild: 127x120 px)


def fountain():
    mb = MB()
    rim_h, rw = 0.45, 0.45
    # Beckenrand (4 Seiten)
    mb.box((-BX, -BY, 0), (BX, -BY + rw, rim_h), "Granite")
    mb.box((-BX, BY - rw, 0), (BX, BY, rim_h), "Granite")
    mb.box((-BX, -BY + rw, 0), (-BX + rw, BY - rw, rim_h), "Granite")
    mb.box((BX - rw, -BY + rw, 0), (BX, BY - rw, rim_h), "Granite")
    # Beckenboden + Wasser
    mb.box((-BX + rw, -BY + rw, 0), (BX - rw, BY - rw, 0.06), "Basin_Floor")
    ob = mb.build("Fountain_Basin", COLS["Fountain"], bevel=0.05)
    wm = MB()
    wm.box((-BX + rw, -BY + rw, 0.06), (BX - rw, BY - rw, 0.34), "Water")
    wo = wm.build("Fountain_Water", COLS["Fountain"])
    collider("Fountain", -BX, BX, -BY, BY, rim_h)
    return ob, wo


# ================================================================ SKULPTUREN (Bronze)
def fishermen():
    """Stehender Fischer mit Suedwester + knieender Netzzieher (Mitte/Ost im Becken)."""
    mb = MB()
    B = "Bronze"
    z0 = 0.42
    mb.box((-0.9, -0.7, 0.28), (0.9, 0.7, z0), B)
    # stehender Fischer (blickt nach +Y), lokale Position
    o = Vector((0.25, -0.15, 0))
    for s in (-1, 1):
        limb(mb, o + Vector((s * 0.13, 0, z0)), o + Vector((s * 0.12, 0.02, z0 + 0.8)), 0.1, 0.11, B)
        mb.cbox(o + Vector((s * 0.13, 0.07, z0 + 0.05)), (0.15, 0.3, 0.1), B)
    limb(mb, o + Vector((0, 0, z0 + 0.25)), o + Vector((0, 0.02, z0 + 1.5)), 0.33, 0.24, B, seg=10)  # Mantel
    sphere(mb, o + Vector((0, 0.02, z0 + 1.5)), 0.27, B, scale=(1.15, 0.8, 0.55))
    for s in (-1, 1):
        sh = o + Vector((s * 0.27, 0.02, z0 + 1.48))
        el = o + Vector((s * 0.3, 0.12, z0 + 1.1))
        ha = o + Vector((s * 0.22, 0.32, z0 + 0.85))
        limb(mb, sh, el, 0.08, 0.075, B)
        limb(mb, el, ha, 0.07, 0.065, B)
        sphere(mb, ha, 0.08, B)
    limb(mb, o + Vector((0, 0.02, z0 + 1.55)), o + Vector((0, 0.03, z0 + 1.68)), 0.07, 0.07, B)
    sphere(mb, o + Vector((0, 0.04, z0 + 1.8)), 0.13, B, scale=(0.85, 0.95, 1.1))
    hat = o + Vector((0, 0.0, z0 + 1.9))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.3, radius2=0.2, depth=0.06)
    mb.bm(bm, Matrix.Translation(hat) @ Matrix.Rotation(-0.25, 4, 'X'), B)
    limb(mb, hat, hat + Vector((0, 0.02, 0.15)), 0.15, 0.1, B, caps=True)
    # Netz
    n0 = o + Vector((0, 0.36, z0 + 0.85))
    limb(mb, n0, o + Vector((-0.05, 0.45, z0 + 0.12)), 0.26, 0.06, B, seg=8)
    # knieender Mann (blickt nach -X), vor dem Fischer
    k = Vector((-0.25, 0.25, 0))
    H = k + Vector((0.15, 0, z0 + 0.55))
    C = k + Vector((-0.25, 0, z0 + 1.0))
    limb(mb, H, C, 0.17, 0.2, B, seg=8)
    sphere(mb, C + Vector((-0.17, 0, 0.18)), 0.12, B)
    K1 = k + Vector((-0.3, 0.14, z0 + 0.5))
    limb(mb, H + Vector((0, 0.12, 0)), K1, 0.1, 0.09, B)
    limb(mb, K1, k + Vector((-0.28, 0.14, z0 + 0.05)), 0.08, 0.06, B)
    K2 = k + Vector((0.1, -0.12, z0 + 0.08))
    limb(mb, H + Vector((0, -0.12, 0)), K2, 0.1, 0.09, B)
    limb(mb, K2, k + Vector((0.55, -0.12, z0 + 0.1)), 0.08, 0.06, B)
    S1, S2 = C + Vector((0, 0.18, 0.02)), C + Vector((0, -0.18, 0.02))
    limb(mb, S1, K1 + Vector((0.05, 0.05, 0.08)), 0.065, 0.06, B)
    hand = k + Vector((-0.72, -0.2, z0 - 0.02))
    limb(mb, S2, hand, 0.065, 0.06, B)
    limb(mb, hand, hand + Vector((-0.05, 0.0, -0.35)), 0.02, 0.02, B, seg=4)  # Leine ins Wasser
    return mb


def eel_boy():
    """Krabbelnder Junge mit Aal auf Bronzeplatte (blickt nach +X, Platte ragt ueber das Wasser)."""
    mb = MB()
    B = "Bronze"
    top = 0.53
    mb.box((-0.9, -0.42, 0.45), (1.1, 0.42, top), B)
    cyl(mb, (0.75, 0.1, top + 0.005), 0.18, 0.02, "Water", seg=10)  # Loch in der Platte
    hip = Vector((-0.3, 0, top + 0.5))
    sh = Vector((0.25, 0, top + 0.55))
    limb(mb, hip, sh, 0.15, 0.17, B, seg=8)
    sphere(mb, hip, 0.16, B, scale=(1.1, 1, 0.9))
    sphere(mb, sh + Vector((0.18, 0, 0.12)), 0.12, B, scale=(1, 0.9, 1.05))
    for s in (-1, 1):
        kn = Vector((-0.25, s * 0.12, top + 0.06))
        limb(mb, hip + Vector((0, s * 0.1, 0)), kn, 0.08, 0.07, B)
        limb(mb, kn, Vector((-0.75, s * 0.13, top + 0.2)), 0.065, 0.05, B)
    limb(mb, sh + Vector((0, 0.13, 0)), Vector((0.32, 0.18, top + 0.02)), 0.06, 0.055, B)
    hand = Vector((0.55, -0.12, top + 0.45))
    limb(mb, sh + Vector((0, -0.13, 0)), hand, 0.06, 0.055, B)
    # Aal: Wellenkette
    pts = [hand + Vector((0.08 * math.sin(i * 1.3), 0.06 * i * 0, 0.25 - 0.12 * i)) for i in range(7)]
    pts[0] = hand + Vector((0, 0, 0.3))
    for a, b in zip(pts, pts[1:]):
        limb(mb, a, b, 0.045, 0.045, B, seg=6)
    pts2 = [Vector((0.95 - 0.08 * i, 0.18 + 0.06 * math.sin(i * 1.5), top + 0.06 + (0.12 if i < 2 else 0))) for i in range(6)]
    for a, b in zip(pts2, pts2[1:]):
        limb(mb, a, b, 0.04, 0.04, B, seg=6)
    return mb


def window_sculpture():
    """Bronze-Fensterrahmen mit Frau und Kind (Rahmenebene Nord-Sued, Frau auf Ostseite, lokal +X)."""
    mb = MB()
    B = "Bronze"
    mb.box((-0.55, -1.0, 0), (0.55, 1.0, 0.12), B)
    t = 0.16
    mb.box((-t, -0.85, 0.12), (t, 0.85, 1.35), B)
    mb.box((-t, -0.85, 1.35), (t, -0.55, 2.3), B)
    mb.box((-t, 0.55, 1.35), (t, 0.85, 2.3), B)
    mb.box((-t, -0.85, 2.3), (t, 0.85, 2.6), B)
    mb.box((t, 0.35, 0.3), (t + 0.04, 0.6, 1.3), B)  # Tuch
    # Frau lehnt sich hinaus
    limb(mb, Vector((0.3, -0.05, 0.12)), Vector((0.3, -0.05, 1.05)), 0.34, 0.2, B, seg=10)
    limb(mb, Vector((0.3, -0.05, 1.05)), Vector((0.42, -0.05, 1.6)), 0.22, 0.2, B, seg=8)
    sphere(mb, Vector((0.42, -0.08, 1.55)), 0.22, B, scale=(1, 1.2, 0.8))
    sphere(mb, Vector((0.55, -0.05, 1.82)), 0.14, B)
    sphere(mb, Vector((0.48, -0.05, 1.93)), 0.11, B)  # Dutt
    limb(mb, Vector((0.42, -0.3, 1.58)), Vector((0.32, -0.45, 1.38)), 0.07, 0.065, B)
    limb(mb, Vector((0.32, -0.45, 1.38)), Vector((0.42, -0.1, 1.38)), 0.065, 0.06, B)
    # Kind im Fenster
    limb(mb, Vector((0.05, 0.25, 1.38)), Vector((0.05, 0.25, 1.75)), 0.13, 0.11, B)
    sphere(mb, Vector((0.05, 0.25, 1.88)), 0.1, B)
    for s in (-1, 1):
        limb(mb, Vector((0.05, 0.25 + s * 0.07, 1.42)), Vector((0.3, 0.25 + s * 0.07, 1.38)), 0.05, 0.04, B)
    return mb


def place(mb, name, col, x, y, rz=0.0, z=0.0, bevel=0.0):
    M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rz, 4, 'Z')
    return mb.transformed(M).build(name, col, bevel=bevel)


# ================================================================ PROPS
@as_part("Laterne")
def lamp_double(mb, x, y, rz=0.0):
    small_col(x, y, 0.2, 0.2, 4.0)
    M = Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, 'Z')
    m = MB()
    cyl(m, (0, 0, 0.25), 0.16, 0.5, "Metal_Green", seg=8)
    cyl(m, (0, 0, 2.2), 0.07, 3.9, "Metal_Green", seg=8)
    m.box((-0.65, -0.04, 3.85), (0.65, 0.04, 3.95), "Metal_Green")
    for s in (-1, 1):
        cyl(m, (s * 0.6, 0, 4.2), 0.17, 0.5, "Lamp_Glow", seg=6)
        cyl(m, (s * 0.6, 0, 4.5), 0.22, 0.15, "Metal_Green", seg=6, r2=0.05)
        cyl(m, (s * 0.6, 0, 3.97), 0.12, 0.06, "Metal_Green", seg=6)
    # Blumenampel
    sphere(m, (0, 0.2, 2.8), 0.3, "Leaf_Green", sub=1, jitter=0.2)
    for i in range(6):
        a = i * math.pi / 3
        sphere(m, (0.2 * math.cos(a), 0.2 + 0.2 * math.sin(a), 2.85), 0.11, random.choice(["Flower_Pink", "Flower_Red", "Flower_White"]), sub=1)
    mb.merge(m.transformed(M))


@as_part("Bank")
def bench(mb, x, y, rz=0.0, L=2.0):
    q = abs(math.sin(rz)) > 0.7
    small_col(x, y, 0.35 if q else L / 2, L / 2 if q else 0.35, 0.8)
    m = MB()
    for s in (-1, 1):
        m.box((s * L * 0.4 - 0.08, -0.25, 0), (s * L * 0.4 + 0.08, 0.25, 0.42), "Metal_Dark")
    for i in range(3):
        m.box((-L / 2, -0.24 + i * 0.17, 0.42), (L / 2, -0.24 + i * 0.17 + 0.13, 0.48), "Wood_Light")
    for i in range(2):
        m.box((-L / 2, 0.24, 0.6 + i * 0.18), (L / 2, 0.3, 0.73 + i * 0.18), "Wood_Light")
    mb.merge(m.transformed(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, 'Z')))


@as_part("Stuhl")
def chair(m, x, y, rz, mat_seat="Wicker"):
    c = MB()
    c.box((-0.22, -0.22, 0.43), (0.22, 0.22, 0.5), mat_seat)
    c.box((-0.22, 0.17, 0.5), (0.22, 0.22, 0.95), mat_seat)
    for sx in (-1, 1):
        for sy in (-1, 1):
            c.box((sx * 0.18 - 0.025, sy * 0.18 - 0.025, 0), (sx * 0.18 + 0.025, sy * 0.18 + 0.025, 0.43), "Metal_Dark")
    m.merge(c.transformed(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, 'Z')))


@as_part("Tisch")
def cafe_table(m, x, y, chairs=4, seat="Wicker"):
    small_col(x, y, 0.75, 0.75, 0.9)
    cyl(m, (x, y, 0.37), 0.04, 0.74, "Metal_Dark", seg=6)
    cyl(m, (x, y, 0.02), 0.25, 0.04, "Metal_Dark", seg=8)
    cyl(m, (x, y, 0.75), 0.38, 0.04, "Trim_White", seg=12)
    if random.random() < 0.6:
        cyl(m, (x + 0.1, y, 0.83), 0.04, 0.12, "Glass_Warm", seg=6)
    for i in range(chairs):
        a = i * 2 * math.pi / chairs + random.uniform(-0.2, 0.2)
        chair(m, x + 0.68 * math.cos(a), y + 0.68 * math.sin(a), a - math.pi / 2 + math.pi, seat)


@as_part("Schirm")
def umbrella_square(m, x, y, size, fabric, trim):
    cyl(m, (x, y, 1.3), 0.05, 2.6, "Wood_Light", seg=6)
    h = size / 2
    z1, z2 = 2.35, 3.05
    vs = [(x - h, y - h, z1), (x + h, y - h, z1), (x + h, y + h, z1), (x - h, y + h, z1), (x, y, z2)]
    m.poly(vs, [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (3, 2, 1, 0)], fabric)
    for (a, b) in [((x - h, y - h - 0.02), (x + h, y - h + 0.02)), ((x - h, y + h - 0.02), (x + h, y + h + 0.02)),
                   ((x - h - 0.02, y - h), (x - h + 0.02, y + h)), ((x + h - 0.02, y - h), (x + h + 0.02, y + h))]:
        m.box((a[0], a[1], z1 - 0.22), (b[0], b[1], z1), trim)
    sphere(m, (x, y, z2 + 0.06), 0.07, trim, sub=1)


@as_part("Schirm")
def umbrella_round(m, x, y, r, fabric):
    cyl(m, (x, y, 1.3), 0.05, 2.6, "Wood_Light", seg=6)
    cyl(m, (x, y, 2.6), r, 0.7, fabric, seg=10, r2=0.05)


@as_part("Fahrrad")
def bike(m, x, y, rz, color):
    q = abs(math.sin(rz)) > 0.7
    small_col(x, y, 0.3 if q else 0.8, 0.8 if q else 0.3, 1.0)
    b = MB()
    R = Matrix.Rotation(math.pi / 2, 4, 'Z')
    for s in (-0.52, 0.52):
        torus(b, (s, 0, 0.34), 0.31, 0.03, "Tire", seg=12, rseg=4)
    pts = [(-0.52, 0, 0.34), (-0.05, 0, 0.36), (0.3, 0, 0.75), (-0.15, 0, 0.78)]
    limb(b, pts[0], pts[1], 0.025, 0.025, color, seg=4, caps=False)
    limb(b, pts[1], pts[2], 0.03, 0.03, color, seg=4, caps=False)
    limb(b, pts[1], pts[3], 0.03, 0.03, color, seg=4, caps=False)
    limb(b, pts[3], pts[2], 0.03, 0.03, color, seg=4, caps=False)
    limb(b, pts[0], pts[3], 0.022, 0.022, color, seg=4, caps=False)
    limb(b, (0.52, 0, 0.34), (0.3, 0, 0.9), 0.025, 0.025, color, seg=4, caps=False)
    b.box((0.25, -0.28, 0.88), (0.31, 0.28, 0.93), "Metal_Dark")
    b.box((-0.27, -0.09, 0.82), (-0.05, 0.09, 0.88), "Wood_Door")
    if random.random() < 0.5:
        b.box((0.45, -0.18, 0.62), (0.75, 0.18, 0.86), "Wicker")  # Korb
    m.merge(b.transformed(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, 'Z')))


@as_part("Kuebel")
def planter(m, x, y, s=1.0, wood="Wood_Light"):
    small_col(x, y, 0.5 * s, 0.5 * s, 0.6 * s)
    m.box((x - 0.5 * s, y - 0.5 * s, 0), (x + 0.5 * s, y + 0.5 * s, 0.6 * s), wood)
    m.box((x - 0.44 * s, y - 0.44 * s, 0.6 * s), (x + 0.44 * s, y + 0.44 * s, 0.63 * s), "Soil")
    sphere(m, (x, y, 0.95 * s), 0.55 * s, random.choice(["Leaf_Green", "Leaf_Dark"]), sub=2, jitter=0.12)
    for i in range(4):
        a = random.uniform(0, 6.28)
        sphere(m, (x + 0.35 * s * math.cos(a), y + 0.35 * s * math.sin(a), 1.05 * s), 0.1 * s, random.choice(FLOWERS), sub=1)


@as_part("Poller")
def bollard(m, x, y):
    small_col(x, y, 0.15, 0.15, 0.6)
    m.box((x - 0.12, y - 0.12, 0), (x + 0.12, y + 0.12, 0.55), "Granite")


@as_part("Aufsteller")
def sandwich_board(m, x, y, rz):
    b = MB()
    for s in (-1, 1):
        top = [Vector((-0.3, 0.0, 1.0)), Vector((0.3, 0.0, 1.0)), Vector((0.3, s * 0.3, 0.0)), Vector((-0.3, s * 0.3, 0.0))]
        slab(b, top, 0.04, "Sign_Board")
    b.box((-0.25, -0.18, 0.35), (0.25, 0.18, 0.37), "Wood_Light")
    m.merge(b.transformed(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, 'Z')))


@as_part("Muelleimer")
def trash_bin(m, x, y):
    small_col(x, y, 0.28, 0.28, 1.0)
    cyl(m, (x, y, 0.45), 0.25, 0.9, "Metal_Green", seg=10)
    cyl(m, (x, y, 0.93), 0.28, 0.06, "Metal_Green", seg=10)


@as_part("Auto")
def car(m, x, y, rz, color):
    q = abs(math.sin(rz)) > 0.7
    small_col(x, y, 0.9 if q else 2.0, 2.0 if q else 0.9, 1.5)
    c = MB()
    c.box((-2.0, -0.85, 0.3), (2.0, 0.85, 1.0), color)
    c.box((-1.1, -0.75, 1.0), (0.9, 0.75, 1.55), color)
    c.box((-1.0, -0.77, 1.05), (0.8, 0.77, 1.48), "Glass_Mint")
    c.box((-1.15, -0.7, 1.05), (0.95, 0.7, 1.48), "Glass_Mint")
    for sx in (-1.3, 1.3):
        for sy in (-0.8, 0.8):
            cyl(c, (sx, sy, 0.33), 0.33, 0.25, "Tire", seg=10, axis='Y')
    for sy in (-0.6, 0.6):
        c.box((1.98, sy - 0.15, 0.7), (2.03, sy + 0.15, 0.85), "Lamp_Glow")
    m.merge(c.transformed(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rz, 4, 'Z')))


def grass_tuft(m, x, y, s=1.0):
    mt = random.choice(["Grass_Gold", "Grass_Gold", "Grass_Green"])
    for i in range(random.randint(3, 5)):
        a = random.uniform(0, 6.28)
        d = random.uniform(0, 0.12) * s
        h = random.uniform(0.25, 0.5) * s
        tip = (x + d * math.cos(a) + random.uniform(-0.1, 0.1) * s, y + d * math.sin(a) + random.uniform(-0.1, 0.1) * s, h)
        limb(m, (x + d * math.cos(a), y + d * math.sin(a), 0), tip, 0.06 * s, 0.005, mt, seg=4, caps=False)


def tree(name, x, y, r=5.5, h=12.0):
    t = MB()
    limb(t, (x, y, 0), (x + 0.2, y, h * 0.45), 0.42, 0.28, "Bark", seg=8, caps=False)
    for a in (0.3, 2.4, 4.3):
        limb(t, (x + 0.2, y, h * 0.4), (x + 2.2 * math.cos(a), y + 2.2 * math.sin(a), h * 0.62), 0.2, 0.1, "Bark", seg=6)
    rng = random.Random(3)
    for i in range(13):
        a = rng.uniform(0, 6.28)
        d = rng.uniform(0, r * 0.6)
        zz = h * rng.uniform(0.55, 0.85)
        rr = rng.uniform(1.8, 2.7) * r / 5.5
        sphere(t, (x + d * math.cos(a), y + d * math.sin(a), zz), rr, rng.choice(["Leaf_YellowGreen", "Leaf_Green", "Leaf_Green"]),
               sub=2, jitter=0.18, scale=(1, 1, 0.82))
    sphere(t, (x, y, h * 0.9), 2.2 * r / 5.5, "Leaf_YellowGreen", sub=2, jitter=0.18)
    # Baumscheibe
    t.box((x - 1.0, y - 1.0, 0), (x + 1.0, y + 1.0, 0.05), "Metal_Dark")
    for i in range(10):
        grass_tuft(t, x + rng.uniform(-0.8, 0.8), y + rng.uniform(-0.8, 0.8), 1.1)
    ob = t.build(name, COLS["Vegetation"])
    mb = MB()
    mb.box((x - 0.4, y - 0.4, 0), (x + 0.4, y + 0.4, 4), "Collider")
    mb.build("COL_" + name, COLS["Colliders"]).display_type = 'WIRE'
    return ob


def flower_tower(name, x, y):
    with part(name, root=True):
        return _flower_tower(name, x, y)


def _flower_tower(name, x, y):
    small_col(x, y, 0.9, 0.9, 2.8)
    m = MB()
    cyl(m, (x, y, 1.4), 0.08, 2.8, "Metal_Zinc", seg=8)
    rng = random.Random(9)
    for i in range(6):
        z = 0.15 + i * 0.42
        r = 0.88 - i * 0.07
        ox = 0.08 * math.sin(i * 1.7)
        cyl(m, (x + ox, y, z + 0.14), r * 0.75, 0.3, "Metal_Zinc", seg=14, r2=r)
        for k in range(14):
            a = k * 2 * math.pi / 14 + rng.uniform(-0.1, 0.1)
            c = (x + ox + r * 0.88 * math.cos(a), y + r * 0.88 * math.sin(a), z + 0.32)
            sphere(m, c, 0.15, "Leaf_Green", sub=1, jitter=0.2)
            sphere(m, (c[0], c[1], c[2] + 0.1), 0.11, rng.choice(FLOWERS), sub=1, jitter=0.15)
    return m.build(name, COLS["Props"])


def string_lights(m, p1, p2, sag=1.2, spacing=0.9):
    p1, p2 = Vector(p1), Vector(p2)
    L = (p2 - p1).length
    n = max(4, int(L / 0.6))
    pts = []
    for i in range(n + 1):
        t = i / n
        p = p1.lerp(p2, t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(p)
    for a, b in zip(pts, pts[1:]):
        limb(m, a, b, 0.02, 0.02, "Cable", seg=4, caps=False)
    nb = int(L / spacing)
    for i in range(1, nb):
        t = i / nb
        p = p1.lerp(p2, t)
        p.z -= sag * 4 * t * (1 - t) + 0.12
        sphere(m, p, 0.065, "Bulb_Glow", sub=1)


# ================================================================ AUFBAU
def build():
    ground()
    fountain()

    # --- Skulpturen (Positionen aus Satellitenbild + Fotos) ---
    fx, fy = P(603, 605)
    with part("Sculpture_Fischer", root=True) as fischer:
        place(fishermen(), "Sculpture_Fischer", COLS["Sculptures"], fx, fy, rz=math.radians(10))
    bx, by = P(532, 585)
    with part("Sculpture_Aaljunge", root=True):
        place(eel_boy(), "Sculpture_Aaljunge", COLS["Sculptures"], -BX + 0.85, by, rz=math.radians(-12))
    wx, wy = P(500, 655)
    with part("Sculpture_Fenster", root=True) as fenster:
        place(window_sculpture(), "Sculpture_Fenster", COLS["Sculptures"], wx, wy, rz=math.radians(8))
    for nm, (x, y), s, pid in [("Fenster", (wx, wy), (1.2, 2.2), fenster), ("Fischer", (fx, fy), (1.6, 1.3), fischer)]:
        SMALL_COLS.append(("COL_Sculpture_" + nm, x - s[0] / 2, x + s[0] / 2, y - s[1] / 2, y + s[1] / 2, 2.4, pid))

    # --- Gebaeude: Westseite (Fassadenflucht x = -17.9) ---
    house("B_W1_VeroModa", -32.0, -17.6, -7.4, 10.3, 14.5, "gable_y", 7.0, "Wall_White", "Roof_Terracotta", floors=4,
          faces="ENS", shop="E", awning=None, frame="Frame_Cream", dormers=[('E', [-4.0, 0.5, 5.0])],
          extra=lambda b, d: (chimney(d, -27.0, 6.0, 18.0), chimney(d, -22.5, -4.0, 17.0)))
    house("B_W2_Fellini", -36.0, -17.9, -17.0, -7.4, 11.0, "mansard", 4.0, "Wall_Yellow", "Roof_Slate", floors=3,
          faces="ES", shop="E", awning="Fabric_Green", frame="Frame_Cream", win_w=1.5, win_h=1.9, spacing=3.4,
          ivy_faces=[('S', -26.0, 3.0, 7.0)])
    house("B_W3_Ernstings", -36.0, -17.9, -41.0, -17.0, 9.0, "gable_y", 6.5, "Wall_LightYellow", "Roof_Terracotta", floors=2,
          faces="E", shop="E", awning="Fabric_Orange", dormers=[('E', [-37.0, -32.0, -27.0, -22.0])],
          extra=lambda b, d: arch_passage(d, 'E', -17.9, -33.0, 3.4, 3.8, "Trim_Cream"))
    house("B_W4_GruenerGiebel", -34.0, -17.9, -48.0, -41.0, 11.0, "gable_x", 9.0, "Wall_Green", "Roof_TerracottaDark", floors=3,
          faces="EN", gables={'E': 'volute'}, frame="Frame_Cream", cornice="Trim_White", doors={'E': [-44.5]}, spacing=2.4,
          ivy_faces=[('N', -24.0, 2.5, 6.0)],
          gable_rows=3)
    house("B_W5_RoterGiebel", -34.0, -17.9, -54.0, -48.0, 10.0, "gable_x", 8.0, "Wall_Orange", "Roof_Terracotta", floors=3,
          faces="E", gables={'E': 'stepped'}, frame="Frame_Cream", doors={'E': [-51.0]}, spacing=2.2, gable_rows=2)
    house("B_W6_WeisserGiebel", -34.0, -17.9, -61.0, -54.0, 9.0, "gable_x", 7.0, "Wall_White", "Roof_TerracottaDark", floors=3,
          faces="E", gables={'E': 'plain'}, frame="Frame_Grey", doors={'E': [-57.5]}, spacing=2.3)
    house("B_W0_Modern", -36.0, -17.6, 10.3, 19.0, 9.5, "flat", 0, "Wall_Modern", None, floors=3,
          faces="ES", shop="E", frame="Frame_Grey", glass="Glass_Blue", win_w=2.2, win_h=2.0, spacing=2.8,
          extra=lambda b, d: rooftop(d, -30.0, 14.5, 9.6))
    # Nordwestecke
    house("B_NW1", -36.0, -25.4, 19.0, 38.0, 10.0, "hip", 5.0, "Wall_Cream", "Roof_Terracotta", floors=3, faces="SE",
          doors={'S': [-31.0]}, shutters="Frame_Green", extra=lambda b, d: chimney(d, -30.0, 30.0, 13.0))
    house("B_NW2", -25.4, -14.8, 19.0, 38.0, 11.0, "hip", 5.0, "Wall_Pink", "Roof_TerracottaDark", floors=3, faces="SE",
          shop="E", awning="Fabric_Red", ivy_faces=[('S', -22.0, 3.0, 6.0)])
    # Nordseite
    house("B_N1_Schuhhof", -0.2, 14.0, 18.4, 38.0, 11.5, "gable_x", 6.0, "Wall_Beige", "Roof_Terracotta", floors=3,
          faces="SW", shop="S", awning="Fabric_Red", dormers=[('S', [1.8, 12.0])],
          extra=lambda b, d: cross_gable(b, d, 6.9, 18.4, 5.4, 11.5, 4.6, "Wall_Beige", "Roof_Terracotta"))
    house("B_N2_Stadtbaeckerei", 14.0, 26.2, 18.4, 38.0, 13.0, "gable_x", 5.5, "Wall_White", "Roof_TerracottaDark", floors=4,
          faces="S", shop="S", awning="Fabric_Mustard", dormers=[('S', [17.0, 23.0])],
          extra=lambda b, d: chimney(d, 20.0, 31.0, 16.0))
    house("B_N3", 26.2, 37.0, 18.4, 38.0, 11.0, "gable_x", 6.0, "Wall_Mint", "Roof_Terracotta", floors=3, faces="S",
          doors={'S': [31.5]}, shutters="Frame_Cream", ivy_faces=[('S', 35.0, 2.0, 7.0)])
    # Ostseite
    house("B_E1_WeisserStaffelgiebel", 13.6, 37.0, 1.0, 13.3, 12.5, "gable_x", 8.0, "Wall_White", "Roof_Terracotta", floors=4,
          faces="WN", shop="W", awning="Fabric_Teal", gables={'W': 'stepped'}, frame="Frame_Grey", gable_rows=2,
          ivy_faces=[('N', 18.0, 3.0, 5.0)])
    house("B_E1b_Hoffluegel", 18.0, 37.0, -4.4, 1.0, 7.0, "gable_x", 3.5, "Wall_White", "Roof_TerracottaDark", floors=2,
          faces="W", frame="Frame_Grey")
    gate_wall()
    rathaus()
    # Sueden
    keimblatt()
    house("B_S1_GelbesHaus", 13.5, 30.0, -47.0, -34.0, 13.0, "hip", 5.0, "Wall_Peach", "Roof_Terracotta", floors=4,
          faces="NW", shop="N", awning="Fabric_Cream", cornice="Trim_White", ivy_faces=[('W', -45.0, 3.0, 5.0)])
    house("B_S2", -7.4, 12.4, -61.0, -48.6, 11.0, "gable_y", 7.0, "Wall_Cream", "Roof_TerracottaDark", floors=3, faces="W",
          doors={'W': [-55.0]})
    house("B_S3", 30.0, 37.0, -47.0, -34.0, 10.0, "hip", 5.0, "Wall_Pink", "Roof_Brown", floors=3, faces="NW")
    house("B_S4", 13.5, 37.0, -61.0, -48.0, 10.0, "gable_x", 6.0, "Wall_Mint", "Roof_Terracotta", floors=3, faces="N",
          doors={'N': [20.0]})

    vegetation()
    props()
    markers()
    build_small_colliders()


def arch_passage(d, face, plane, u, w, h, trim):
    face_box(d, face, plane, u, 0, w + 0.5, h + 0.2, 0.08, 0.05, trim)
    face_box(d, face, plane, u, 0, w, h - w / 2, 0.1, 0.05, "Dark_Arch")
    face_disc(d, face, plane, u, h - w / 2, w / 2 + 0.25, 0.08, trim, seg=14)
    face_disc(d, face, plane, u, h - w / 2, w / 2, 0.1, "Dark_Arch", seg=14)


def rooftop(d, x, y, z):
    d.box((x - 1.0, y - 0.7, z), (x + 1.0, y + 0.7, z + 1.0), "Metal_Zinc")
    for i in range(4):
        planter(d, x + 4 + i * 1.3, y - 2.5, 0.6)
    bench(d, x + 5.0, y + 1.5, 0, 1.6)
    for i in range(3):
        d.box((x - 6 + i * 0.6, y + 2.0, z), (x - 5.8 + i * 0.6, y + 2.2, z + 0.9), "Wood_Light")


def cross_gable(b, d, xc, y0, w, eave, rh, wall, roofm):
    pent_prism(b, y0, y0 + 6.0, xc - w / 2, xc + w / 2, eave, rh, 'y', wall)
    gable_roof(b, y0, y0 + 6.0, xc - w / 2, xc + w / 2, eave, rh, 'y', roofm, ov=0.35, ov_a0=0.35, ov_a1=0.0)
    gable_windows(d, 'S', y0, xc, w / 2, eave, rh, 2, "Frame_Cream", w=1.0, h=1.3)


def gate_wall():
    mb = MB()
    x = 14.2
    mb.box((x, -4.4, 0), (18.0, -3.9, 4.0), "Wall_Rathaus_Red")
    mb.box((x, 0.5, 0), (18.0, 1.0, 4.0), "Wall_Rathaus_Red")
    mb.box((x, -4.4, 0), (x + 0.5, -2.6, 4.0), "Wall_Rathaus_Red")
    mb.box((x, -0.3, 0), (x + 0.5, 1.0, 4.0), "Wall_Rathaus_Red")
    mb.box((x - 0.1, -4.5, 4.0), (x + 0.6, 1.1, 4.2), "Trim_White")
    for i in range(14):
        yy = -2.55 + i * 0.165
        mb.box((x + 0.2, yy - 0.025, 0), (x + 0.25, yy + 0.025, 3.0 + 0.4 * math.sin(i / 13 * math.pi)), "Metal_Dark")
    mb.box((x + 0.18, -2.6, 2.6), (x + 0.27, -0.3, 2.68), "Metal_Dark")
    mb.box((x + 0.18, -2.6, 0.9), (x + 0.27, -0.3, 0.98), "Metal_Dark")
    mb.build("B_E1c_Rathaustor", COLS["Buildings"])
    collider("Rathaustor", 14.2, 18.0, -4.4, 1.0, 4.0)


def rathaus():
    x0, x1, y0, y1 = 14.2, 37.0, -26.6, -4.4
    eave, rh = 13.0, 13.0

    def extra(b, d):
        # Uhr am Westgiebel
        face_disc(d, 'W', x0, -15.5, eave + 5.6, 0.85, 0.12, "Gold", seg=16)
        face_disc(d, 'W', x0, -15.5, eave + 5.6, 0.68, 0.16, "Wood_Door", seg=16)
        face_box(d, 'W', x0, -15.5, eave + 5.6, 0.08, 0.55, 0.2, 0.0, "Gold")
        face_box(d, 'W', x0, -15.3, eave + 5.6, 0.45, 0.07, 0.2, 0.0, "Gold")
        # Wetterfahne
        top = (x0 + 0.25, -15.5, eave + rh + 1.2)
        limb(d, top, (top[0], top[1], top[2] + 2.2), 0.04, 0.04, "Metal_Dark", seg=6, caps=False)
        sphere(d, (top[0], top[1], top[2] + 1.0), 0.22, "Gold", sub=1)
        d.box((top[0] - 0.02, top[1], top[2] + 1.6), (top[0] + 0.02, top[1] + 0.8, top[2] + 2.0), "Metal_Dark")
        # Dachreiter
        cx = 27.0
        d.box((cx - 0.9, -16.4, eave + rh - 2.5), (cx + 0.9, -14.6, eave + rh + 1.8), "Wall_White")
        cyl(d, (cx, -15.5, eave + rh + 2.9), 1.3, 2.2, "Metal_Green", seg=8, r2=0.05)
        limb(d, (cx, -15.5, eave + rh + 3.8), (cx, -15.5, eave + rh + 5.0), 0.04, 0.04, "Metal_Dark", seg=6, caps=False)
        sphere(d, (cx, -15.5, eave + rh + 4.4), 0.18, "Gold", sub=1)
        # Bogendurchgang im Sueden der Westfassade
        arch_passage(d, 'W', x0, -22.8, 3.6, 4.6, "Trim_White")
        # Steinbank vor der Westfassade
        d.box((x0 - 1.0, -12.0, 0), (x0 - 0.45, -6.0, 0.45), "Granite")
        d.box((x0 - 1.0, -19.5, 0), (x0 - 0.45, -13.5, 0.45), "Granite")
        # Gauben-Reihen auf beiden Dachseiten
        for xx in (19.0, 23.0, 31.0, 35.0):
            for fc in ('N', 'S'):
                dormer(d, fc, x0, x1, y0, y1, eave, rh, "gable_x", xx, "Wall_Rathaus_Red", "Roof_TerracottaDark", "Frame_Grey")

    house("B_E2_Rathaus", x0, x1, y0, y1, eave, "gable_x", rh, "Wall_Rathaus_Red", "Roof_TerracottaDark", floors=3,
          faces="WN", gables={'W': 'volute'}, frame="Frame_Grey", cornice="Trim_White", win_w=1.5, win_h=2.0,
          spacing=3.3, gable_rows=4, doors={'W': [-8.5]}, extra=extra)


def keimblatt():
    """Weisser neugotischer Staffelgiebel (Nordgiebel zum Platz)."""
    x0, x1, y0, y1 = -7.4, 12.4, -48.6, -34.0
    eave, rh = 12.5, 15.0

    def extra(b, d):
        # Balkon
        d.box((-4.6, y1 - 1.1, 8.6), (-1.4, y1, 8.75), "Trim_White")
        for i in range(12):
            d.box((-4.55 + i * 0.27, y1 - 1.05, 8.75), (-4.5 + i * 0.27, y1 - 1.0, 9.6), "Metal_Dark")
        d.box((-4.6, y1 - 1.1, 9.6), (-1.4, y1 - 1.0, 9.68), "Metal_Dark")
        # Lisenen (vertikale Pfeiler)
        for x in (-7.2, -2.6, 2.5, 7.4, 12.2):
            d.box((x - 0.3, y1 - 0.25, 0), (x + 0.3, y1, eave), "Trim_White")
        for t in (-2.0, 7.0):
            planter(d, t, y1 - 1.0, 0.8)

    house("B_S0_Keimblatt", x0, x1, y0, y1, eave, "gable_y", rh, "Wall_GothicBlue", "Roof_TerracottaDark", floors=4,
          faces="NW", shop="N", awning=None, gables={'N': 'gothic'}, frame="Trim_White", cornice="Trim_White",
          arch_windows=True, gable_rows=5, gable_glass="Glass_Blue", win_w=1.1, win_h=1.6, spacing=2.6, extra=extra)


def vegetation():
    tx, ty = P(525, 432)
    tree("Tree_Linde", tx, ty, r=5.5, h=12.5)
    m = MB()
    rng = random.Random(5)
    # Grasbueschel an Hauskanten und Ecken (cozy)
    edges = [(-17.7, y) for y in range(-60, 18, 2)] + [(x, 18.2) for x in range(0, 26, 2)] + \
            [(13.4, y) for y in range(-26, 13, 2)] + [(x, -33.8) for x in range(-7, 12, 2)]
    for (x, y) in edges:
        if rng.random() < 0.55:
            grass_tuft(m, x + rng.uniform(-0.2, 0.2) + (0.25 if x < 0 and abs(x + 17.7) < 0.5 else 0) - (0.25 if abs(x - 13.4) < 0.3 else 0),
                       y + rng.uniform(-0.6, 0.6), rng.uniform(0.8, 1.3))
    for i in range(40):  # vereinzelt zwischen Pflastersteinen
        grass_tuft(m, rng.uniform(-16, 12), rng.uniform(-30, 17), rng.uniform(0.5, 0.8))
    m.build("Vegetation_Grass", COLS["Vegetation"])


def props():
    # Wurzelteil = Objektname; "Gruppe" fasst einen Schirm mit seinen Tischen zusammen (Editor: Klick waehlt die Gruppe,
    # weitere Klicks gehen tiefer: Tisch, Stuhl)
    # --- Cafe Nordost (2x2 quadratische Schirme, Satellit px 600-740 / 380-530) ---
    c = MB()
    with part("Cafe_Nord", root=True):
        for (px, py) in [(632, 415), (700, 415), (632, 490), (700, 490)]:
            x, y = P(px, py)
            with part("Gruppe"):
                umbrella_square(c, x, y, 3.9, "Fabric_Cream", "Fabric_Teal")
                cafe_table(c, x - 0.8, y - 0.6, 4, "Chair_Dark")
                cafe_table(c, x + 0.9, y + 0.7, 3, "Chair_Dark")
        planter(c, *P(590, 380), s=0.8)
        planter(c, *P(745, 380), s=0.8)
        sandwich_board(c, *P(600, 545), 0.2)
        c.build("Cafe_Nord", COLS["Props"])
    # --- Eiscafe West (3 orange Schirme, px 350-435 / 750-990) ---
    c = MB()
    with part("Cafe_Fellini", root=True):
        for py in (790, 870, 950):
            x, y = P(392, py)
            with part("Gruppe"):
                umbrella_square(c, x, y, 4.6, "Fabric_Orange", "Fabric_Cream")
                cafe_table(c, x - 1.0, y - 1.0, 4)
                cafe_table(c, x + 1.0, y + 0.9, 4)
                cafe_table(c, x + 1.0, y - 1.1, 2)
        for py in (745, 1000):
            planter(c, *P(415, py), s=0.75)
        x, y = P(380, 690)
        with part("Gruppe"):
            umbrella_round(c, x, y, 1.9, "Fabric_Red")
            cafe_table(c, x, y, 4)
        sandwich_board(c, -9.5, -9.0, 1.3)
        c.build("Cafe_Fellini", COLS["Props"])
    # --- Cafe vor Vero Moda / unter der Linde (rote Schirme) ---
    c = MB()
    with part("Cafe_Linde", root=True):
        for (x, y) in [(-13.8, 4.5), (-13.8, 8.8)]:
            with part("Gruppe"):
                umbrella_round(c, x, y, 1.8, "Fabric_Red")
                cafe_table(c, x, y, 4)
        c.build("Cafe_Linde", COLS["Props"])

    # --- Blumenturm suedlich des Brunnens (Foto "north") ---
    flower_tower("Prop_Blumenturm", *P(585, 825))

    # --- Laternen ---
    m = MB()
    with part("Props_Laternen", root=True):
        for (x, y, r) in [(-15.5, 1.0, 0), (-15.8, -13.0, 0), (-15.8, -30.0, 0), (-15.8, -46.0, 0), (11.8, -8.5, 0),
                          (11.8, -20.5, 0), (-7.0, 15.5, 0), (9.5, 15.0, 0), (-7.0, -24.0, 0), (25.0, -29.0, 0)]:
            lamp_double(m, x, y, r)
        m.build("Props_Laternen", COLS["Props"])

    # --- Baenke, Poller, Fahrraeder, Muell, Kuebel ---
    m = MB()
    with part("Props_Stadtmobiliar", root=True):
        bench(m, -8.0, 4.5, math.pi / 2)
        bench(m, -8.0, -1.0, math.pi / 2)
        bench(m, 4.0, -8.0, math.pi)
        bench(m, -3.0, 13.5, 0)
        with part("Pollerreihe"):
            for i in range(9):
                bollard(m, -6.0 + i * 2.2, -29.8)
        with part("Pollerreihe"):
            for i in range(5):
                bollard(m, 13.0, -36.0 - i * 2.0)
        with part("Fahrradreihe"):
            for i in range(6):
                bike(m, -17.0, -13.5 - i * 0.65, math.pi / 2 + 0.1, random.choice(["Fabric_Red", "Fabric_Teal", "Metal_Dark", "Fabric_Mustard"]))
        with part("Fahrradreihe"):
            for i in range(5):
                bike(m, 12.8, -0.8 - i * 0.65, -math.pi / 2, random.choice(["Fabric_Red", "Fabric_Teal", "Metal_Dark", "Fabric_Green"]))
        with part("Fahrradreihe"):
            for i in range(4):
                bike(m, -6.0 + i * 0.7, -28.4, 0.05, random.choice(["Fabric_Red", "Car_Blue", "Metal_Dark"]))
        for (x, y) in [(-16.8, -2.0), (12.6, -12.5), (-16.8, -40.0), (8.0, 17.4)]:
            trash_bin(m, x, y)
        for (x, y, s) in [(-16.9, -18.0, 0.8), (-16.9, -16.0, 0.8), (13.0, 2.8, 0.7), (13.0, -26.0, 0.8), (-6.8, -33.0, 0.8),
                          (11.6, -33.0, 0.8), (-16.6, 9.8, 0.8), (-0.8, 17.6, 0.7), (13.2, 17.6, 0.7)]:
            planter(m, x, y, s)
        m.build("Props_Stadtmobiliar", COLS["Props"])

    # --- Autos in der Nordstrasse (Satellit px 380-520 / 0-140) ---
    m = MB()
    with part("Props_Autos", root=True):
        car(m, *P(400, 60), math.pi / 2 + 0.02, "Car_Cream")
        car(m, *P(490, 80), -math.pi / 2, "Car_Blue")
        car(m, -10.5, 33.5, math.pi / 2, "Car_Red")
        m.build("Props_Autos", COLS["Props"])

    # --- Lichterketten ueber dem Platz ---
    m = MB()
    spans = [((-17.6, 6.0, 8.0), (13.6, 9.0, 8.0)), ((-17.9, -6.0, 8.0), (14.2, -3.0, 9.0)),
             ((-17.9, -18.0, 7.5), (14.2, -16.0, 9.0)), ((-17.9, -30.0, 7.0), (2.0, -34.0, 8.0)), ((14.2, -24.0, 8.0), (8.0, -34.0, 7.5)),
             ((-14.8, 19.0, 8.0), (-0.2, 19.0, 8.0)), ((-8.0, 12.0, 6.5), (3.0, 18.4, 8.0))]
    for a, b in spans:
        string_lights(m, a, b, sag=1.4)
    m.build("Lights_Lichterketten", COLS["Lights"])


def markers():
    for name, (x, y) in [("POI_Fischerbrunnen", (0, 0)), ("POI_Fischer", P(603, 605)), ("POI_Aaljunge", P(532, 585)),
                         ("POI_FensterSkulptur", P(500, 655)), ("POI_Rathaus", (14.2, -15.5)), ("POI_Linde", P(525, 432)),
                         ("Spawn_Player", (0.0, -10.0))]:
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = 'PLAIN_AXES'
        e.location = (x, y, 0)
        COLS["Markers"].objects.link(e)


build()

# ---------------------------------------------------------------- Speichern / Export
out_blend = os.path.join(HERE, "fischerbrunnen.blend")
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=out_blend)


def export(path, cols):
    bpy.ops.object.select_all(action='DESELECT')
    for cn in cols:
        for o in COLS[cn].objects:
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True, export_extras=True, export_attributes=True, export_cameras=False, export_lights=False)


export(os.path.join(HERE, "fischerbrunnen.glb"), ["Ground", "Buildings", "Fountain", "Sculptures", "Vegetation", "Props", "Lights", "Markers"])
export(os.path.join(HERE, "fischerbrunnen_colliders.glb"), ["Colliders"])
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH' and not o.name.startswith("COL_"))
print("TRIS", tris, "OBJECTS", len([o for o in scene.objects if o.type == 'MESH']))
print("PARTS", len(PARTS) - 1, "EDITS", len(EDITS))
unknown = sorted(k for k in set(EDITS) - set(PATH_ID) if not (EDITS[k].get("copyOf") and EDITS[k].get("deleted")))
if unknown:
    print("WARNUNG: edits.json nennt Teile, die es nicht (mehr) gibt:", ", ".join(unknown))
