"""Vorschau der Moewen-Animationen: rendert je Clip ausgewaehlte Frames.
Aufruf: blender -b seagull.blend --python render_seagull.py -- <outdir> [Clip:frame ...]
"""
import bpy, sys, os, math
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]
shots = args[1:] or ["Idle:0", "Walk:4", "Hop:10", "Swim:8", "Fly:0", "Fly:6", "Glide:10", "Land:5", "Peck:10", "Squawk:20"]
os.makedirs(out, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 420, 340
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.new("W") if not scene.world else scene.world
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.52, 0.7, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.9

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), 0, math.radians(-40))
scene.collection.objects.link(sun)
# Boden
me = bpy.data.meshes.new("floor")
me.from_pydata([(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)], [], [(0, 1, 2, 3)])
fl = bpy.data.objects.new("floor", me)
m = bpy.data.materials.new("floorm")
m.diffuse_color = (0.6, 0.55, 0.5, 1)
m.use_nodes = True
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.5, 0.45, 1)
fl.data.materials.append(m)
scene.collection.objects.link(fl)

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.data.lens = 60
scene.collection.objects.link(cam)
scene.camera = cam


def look(pos, target):
    cam.location = Vector(pos)
    d = Vector(target) - Vector(pos)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


views = {"34": ((-0.9, -1.1, 0.75), (0, 0, 0.2)), "side": ((-1.5, 0, 0.35), (0, 0, 0.22)),
         "top": ((0.0, -0.01, 2.6), (0, 0, 0.2)), "front": ((0.0, -1.5, 0.4), (0, 0, 0.22))}

objs = [o for o in scene.objects if o.animation_data]
for shot in shots:
    parts = shot.split(":")
    clip, fr = parts[0], int(parts[1])
    view = parts[2] if len(parts) > 2 else "34"
    for o in objs:
        for tr in o.animation_data.nla_tracks:
            tr.mute = tr.name != clip
    scene.frame_set(fr)
    p, t = views[view]
    if clip in ("Fly", "Glide") and view == "34":
        p = (-1.5, -1.8, 1.4)
    look(p, t)
    scene.render.filepath = os.path.join(out, f"{clip}_{fr}_{view}.png")
    bpy.ops.render.render(write_still=True)
