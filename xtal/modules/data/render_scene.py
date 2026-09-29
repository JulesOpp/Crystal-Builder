"""
render_scene
============
Blender's side of File > Render in Blender: Julius's scene, built from
nothing around a PDB, saved and rendered.

Blender runs this with its own Python, headless::

    blender --background --factory-startup --python-exit-code 1 \\
        --python render_scene.py -- --input structure.pdb \\
        --blend scene.blend --image render.png

Unlike ``pdb_to_printable_stl.py`` beside it, the script is ours, so it
is held to this project's lint.  The scene is the one settled on
2026-09-28 and its values are the constants below, named after it; the
only thing not taken as given is where the camera stands, which
``render_framing`` works out for whatever was imported (``--no-frame``
puts it back at the fixed place).

Exit status 2 is "Atomic Blender could not be enabled", as it is for
the STL script, so :mod:`xtal.modules.blender` reads both the same way.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_framing  # noqa: E402  -- beside this file, not installed

#: What every line this script says starts with, so the app can tell it
#: from Blender's own housekeeping.
PREFIX = "[render]"

ADDON_MISSING = 2
ADDON_MODULES = ("io_mesh_atomic",                            # to 4.1
                 "bl_ext.blender_org.atomic_blender_pdb_xyz",  # 4.2+
                 "bl_ext.user_default.atomic_blender_pdb_xyz")

LIGHT_SCALE = 100.0
LIGHT_Z = 25.0
LIGHT_POWER = 100_000.0                 # W

VIEWPORT_SAMPLES = 10
RENDER_SAMPLES = 50

CAMERA_FOCAL = 40.0                     # mm
CAMERA_ROTATION = (70.7437, 0.000522, 146.958)          # degrees, XYZ
CAMERA_LOCATION = (42.0251, 64.6089, 26.9517)           # m, --no-frame


def say(text: str) -> None:
    print(f"{PREFIX} {text}", flush=True)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _importer() -> bool:
    # Not hasattr: an operator namespace answers every name, and only
    # fails when it is called.
    return "pdb" in dir(bpy.ops.import_mesh)


def enable_atomic_blender() -> bool:
    if _importer():
        return True
    for module in ADDON_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except Exception:
            continue
        if _importer():
            return True
    return False


def import_pdb(path: str) -> None:
    """The importer's own defaults, which are what a person gets from
    File > Import, but for three: its camera and lamp are declined,
    because the scene has its own, and so is its centring.  Atomic
    Blender divides by the distance from the origin to a stick's line,
    so a stick whose line passes through the origin is a
    ZeroDivisionError -- and a symmetric cell cut, centred on its mean,
    has such lines (MOF-5 does).  The app writes the PDB already
    centred, off by :data:`xtal.modules.blender.OFF_CENTRE`."""
    bpy.ops.import_mesh.pdb(filepath=path, use_camera=False,
                            use_light=False, use_center=False)


def outline() -> list[tuple[float, float, float]]:
    """The corners of everything drawn, instances included -- every
    atom of an element is one instance of one ball, so the objects'
    own boxes would miss all but the prototypes, and the mesh that
    places them is not drawn, while its box is the whole structure's.
    Instances at one
    place with one shape (a stick is drawn as many short pieces) give
    the same corners, and only the extremes matter, so each object's
    corners are kept once per distinct place."""
    graph = bpy.context.evaluated_depsgraph_get()
    points = set()
    for instance in graph.object_instances:
        obj = instance.object
        if obj.type not in {"MESH", "SURFACE", "META", "CURVE"}:
            continue
        if not instance.is_instance and obj.instance_type != "NONE":
            continue            # a cloud of vertices that places balls
        matrix = instance.matrix_world
        for corner in obj.bound_box:
            point = matrix @ Vector(corner)
            points.add((round(point[0], 2), round(point[1], 2),
                        round(point[2], 2)))
    return sorted(points) or [(0.0, 0.0, 0.0)]


def add_light() -> None:
    light = bpy.data.lights.new("Area", type="AREA")
    light.energy = LIGHT_POWER
    obj = bpy.data.objects.new("Area", light)
    obj.location = (0.0, 0.0, LIGHT_Z)
    obj.scale = (LIGHT_SCALE,) * 3
    bpy.context.scene.collection.objects.link(obj)


def add_camera(location) -> None:
    camera = bpy.data.cameras.new("Camera")
    camera.lens = CAMERA_FOCAL
    camera.sensor_width = render_framing.SENSOR_WIDTH
    camera.sensor_fit = "AUTO"
    obj = bpy.data.objects.new("Camera", camera)
    obj.location = location
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = [math.radians(value) for value in CAMERA_ROTATION]
    scene = bpy.context.scene
    scene.collection.objects.link(obj)
    scene.camera = obj


def set_render(args) -> None:
    scene = bpy.context.scene
    render = scene.render
    render.engine = "CYCLES"
    scene.cycles.preview_samples = args.viewport_samples
    scene.cycles.samples = args.samples
    render.use_simplify = True
    render.use_border = True
    render.resolution_x = args.width
    render.resolution_y = args.height
    render.resolution_percentage = 100
    render.image_settings.file_format = "PNG"
    render.filepath = os.path.abspath(args.image)


def parse(argv):
    parser = argparse.ArgumentParser(prog="render_scene.py")
    parser.add_argument("--input", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--viewport-samples", type=int,
                        default=VIEWPORT_SAMPLES)
    parser.add_argument("--samples", type=int, default=RENDER_SAMPLES)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--no-frame", dest="frame", action="store_false")
    return parser.parse_args(argv)


def main() -> int:
    argv = sys.argv
    args = parse(argv[argv.index("--") + 1:] if "--" in argv else [])
    clear_scene()
    if not enable_atomic_blender():
        say("ERROR: could not find/enable the Atomic Blender PDB "
            "add-on.  Blender <= 4.1: Edit > Preferences > Add-ons > "
            "'Atomic'; 4.2+: Edit > Preferences > Get Extensions > "
            "'Atomic'.")
        return ADDON_MISSING
    say("Importing PDB")
    import_pdb(os.path.abspath(args.input))
    points = outline()
    set_render(args)
    add_light()
    if args.frame:
        location = render_framing.frame(
            points, CAMERA_ROTATION, CAMERA_FOCAL, args.width,
            args.height)
    else:
        location = CAMERA_LOCATION
    add_camera(location)
    left, right, bottom, top = render_framing.region(
        points, location, CAMERA_ROTATION, CAMERA_FOCAL, args.width,
        args.height)
    render = bpy.context.scene.render
    render.border_min_x, render.border_max_x = left, right
    render.border_min_y, render.border_max_y = bottom, top
    say("Camera at ({:.2f}, {:.2f}, {:.2f})".format(*location))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend))
    say(f"Saved {os.path.basename(args.blend)}")
    say(f"Rendering {args.samples} samples")
    bpy.ops.render.render(write_still=True)
    say(f"Wrote {os.path.basename(args.image)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
