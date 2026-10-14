"""Vorschau-Renderings: blender -b fischerbrunnen.blend --python render_preview.py -- <outdir> [views...]"""
import bpy, math, os, sys
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]
views = args[1:] or ["top", "iso_se", "iso_nw", "close"]
sc = bpy.context.scene
for o in bpy.data.collections["Colliders"].objects:
    o.hide_render = True
for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
    try:
        sc.render.engine = eng
        break
    except Exception:
        pass
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.42, 0.40, 0.55, 1); bg.inputs[1].default_value = 0.55
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
sun.data.energy = 2.6; sun.data.color = (1.0, 0.86, 0.68); sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(50), 0, math.radians(150))
sc.collection.objects.link(sun)
try:
    sc.eevee.use_shadows = True
except Exception:
    pass
sc.render.use_freestyle = True
sc.render.line_thickness_mode = 'ABSOLUTE'; sc.render.line_thickness = 1.1
ls = sc.view_layers[0].freestyle_settings.linesets[0] if sc.view_layers[0].freestyle_settings.linesets else sc.view_layers[0].freestyle_settings.linesets.new("L")
if ls.linestyle is None:
    ls.linestyle = bpy.data.linestyles.new("LS")
ls.linestyle.color = (0.22, 0.16, 0.14)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); sc.camera = cam
def look(pos, target, lens=35, ortho=None):
    cam.location = pos
    d = Vector(target) - Vector(pos)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else:
        cam.data.type = 'PERSP'; cam.data.lens = lens
    cam.data.clip_end = 1000
V = {
    "top": ((0, -11, 120), (0, -11, 0), 35, 105),
    "iso_se": ((38, -48, 42), (0, -8, 0), 30, None),
    "iso_nw": ((-34, 30, 38), (0, -6, 0), 30, None),
    "close": ((7, 9, 8), (-1, -1, 0.5), 30, None),
    "south": ((-2, -24, 3.5), (0, 4, 4), 24, None),
    "north": ((-4, 18, 4), (3, -20, 6), 22, None),
    "game": ((0, -32, 30), (0, -4, 0), 35, None),
}
for v in views:
    p, t, lens, orth = V[v]
    look(p, t, lens, orth)
    sc.render.filepath = os.path.join(out, f"preview_{v}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", v)
