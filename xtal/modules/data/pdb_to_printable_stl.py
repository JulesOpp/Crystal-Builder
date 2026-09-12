#!/usr/bin/env python3
"""
pdb_to_printable_stl.py
=======================

Headless Blender automation of a crystal-structure -> 3D-print workflow.

Replaces these manual Blender steps:

    1. Import .pdb with Atomic Blender (balls = Mesh, low poly, scaled radii;
       sticks = instancing type, custom radius + sectors)
    2. Scale the parent Hydrogen ball so all H instances get bigger
    3. Make instances real
    4. Delete the parent/prototype objects for spheres and bonds
    5. Export .stl
    6. Re-import the .stl, remesh to repair geometry and cut file size
    7. Export the final .stl

Steps 3-6 are the slow ones when done by hand. This script replaces the
"make instances real -> join -> export -> re-import" round trip with a
direct depsgraph bake: it reads the instance transforms straight out of the
dependency graph and welds every sphere and cylinder into ONE mesh with
numpy. No thousands of temp objects, no intermediate file on disk. For big
structures this is typically one to two orders of magnitude faster and uses
far less RAM.

The old operator-based path is still available via --realize-method operator
in case you want to reproduce the manual result exactly.

--------------------------------------------------------------------------
USAGE (command line, recommended)
--------------------------------------------------------------------------

    blender --background --factory-startup --python pdb_to_printable_stl.py -- \
        --input  /path/to/structure.pdb \
        --output /path/to/structure_print.stl

Everything after the bare `--` is passed to this script, not to Blender.

Common options:

    --max-tris 1000000         triangle budget for the final STL (default).
                               Adaptivity is raised automatically until the
                               mesh fits. Use 0 to disable the budget.
    --voxel-size 0.08          finer remesh (more detail, bigger file)
    --adaptivity 0.25          STARTING adaptivity; raised as needed
    --h-scale 2.0              hydrogen enlargement factor
    --ball-scale 0.8           Atomic Blender "Balls" scaling factor
    --ball-subdiv 16           sphere azimuth/zenith sectors
    --stick-radius 0.4         value typed into the stick "Radius" field
    --stick-sectors 10         stick sector count
    --no-remesh                skip the remesh entirely
    --save-raw                 also write <output>_raw.stl before remeshing
    --target-size 60           uniformly scale so the longest axis = 60 (mm)
    --blend-out scene.blend    save a .blend for inspection

Batch a whole folder (every *.pdb inside it):

    blender --background --factory-startup --python pdb_to_printable_stl.py -- \
        --input /path/to/folder --outdir /path/to/results

--------------------------------------------------------------------------
USAGE (inside Blender's Text Editor)
--------------------------------------------------------------------------
Edit the CONFIG block below, then press "Run Script". With no `--` on the
command line the CONFIG values are used and CLEAR_SCENE defaults to False so
your open scene is not wiped.

--------------------------------------------------------------------------
REQUIREMENTS
--------------------------------------------------------------------------
* Blender 2.83+ (tested logic covers 2.8x through 4.x; version differences in
  the STL operators and mesh API are handled automatically)
* The "Atomic Blender PDB/XYZ" add-on. The script tries to enable it for you.
  If that fails, enable it once by hand:
      Edit > Preferences > Add-ons > search "Atomic"  (Blender <= 4.1)
      Edit > Preferences > Get Extensions > search "Atomic"  (Blender 4.2+)
  It only needs to be enabled once; the preference is remembered. Note that
  --factory-startup ignores saved preferences, so if you use that flag the
  script's auto-enable is what makes it work.

Bonds come from CONECT records in the .pdb. Atomic Blender never computes
bonds itself, which is exactly why the VESTA .xyz -> .pdb detour exists.
"""

import os
import sys
import glob
import time
import argparse

import bpy

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:  # Blender always ships numpy, but just in case
    HAVE_NUMPY = False


# =========================================================================
# CONFIG - used when the script is run without command-line arguments
# =========================================================================
CONFIG = {
    "input":            "",        # .pdb file, or a folder of .pdb files
    "output":           "",        # final .stl (defaults to <input>_print.stl)
    "outdir":           "",        # used for folder/batch mode

    # --- Atomic Blender import settings (your manual values) ---
    "ball_type":        "MESH",    # NURBS | MESH | META
    "ball_subdiv":      16,        # azimuth AND zenith sectors (default 32)
    "ball_scale":       0.8,       # "Balls" scaling factor (default 1.0)
    "radius_type":      "ATOMIC",  # PREDEFINED | ATOMIC | VDW
    "use_sticks":       True,
    "stick_type":       "DEFAULT", # DEFAULT (instancing) | SKIN | NORMAL
    "stick_radius":     0.4,       # stick "Radius" field (default 0.2)
    "stick_sectors":    10,        # stick "Sector" field
    "stick_smooth":     True,

    # --- post-import tweaks ---
    "h_scale":          2.0,       # multiply the Hydrogen prototype ball by this
    "extra_scales":     {},        # e.g. {"Oxygen": 1.2} - element name -> factor

    # --- realize ---
    "realize_method":   "depsgraph",  # depsgraph (fast) | operator (classic)

    # --- remesh ---
    "do_remesh":        True,
    "voxel_size":       0.10,      # Blender units; see notes at the bottom
    "adaptivity":       0.0,       # STARTING adaptivity; raised automatically
    "max_tris":         1000000,   # triangle budget (0 = no budget)
    "max_remesh_attempts": 4,      # each attempt costs one full remesh
    "adaptivity_cap":   0.9,       # never push adaptivity past this
    "auto_decimate":    True,      # Decimate backstop if adaptivity saturates
    "remesh_smooth":    True,
    "decimate_ratio":   0.0,       # extra manual decimate; 0 = off

    # --- output ---
    "target_size":      0.0,       # 0 = leave as-is; else scale longest axis to this
    "save_raw":         False,     # also write the pre-remesh STL
    "blend_out":        "",        # optional .blend dump for inspection
    "ascii_stl":        False,     # binary STL is much smaller - keep False
}

# Wipe the scene before working. Auto-set to True in --background mode.
CLEAR_SCENE = bpy.app.background


# =========================================================================
# Small helpers
# =========================================================================

def log(msg):
    print("[mol2stl] %s" % msg, flush=True)


def bversion():
    return bpy.app.version


def tri_count():
    n = 0
    for ob in bpy.context.scene.objects:
        if ob.type == 'MESH':
            ob.data.calc_loop_triangles()
            n += len(ob.data.loop_triangles)
    return n


def deselect_all():
    for ob in bpy.context.scene.objects:
        ob.select_set(False)


def activate(ob):
    deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def purge_orphans():
    """Free unused datablocks. Never fatal - it is only a memory optimisation.
    Anything that must survive should carry use_fake_user = True."""
    for _ in range(4):
        try:
            bpy.ops.outliner.orphans_purge(do_local_ids=True,
                                           do_linked_ids=True,
                                           do_recursive=True)
        except Exception:
            try:
                bpy.ops.outliner.orphans_purge()
            except Exception:
                return


# =========================================================================
# Add-on handling
# =========================================================================

ATOMIC_MODULE_CANDIDATES = [
    "io_mesh_atomic",                                # 2.8x - 4.1 bundled
    "bl_ext.blender_org.atomic_blender_pdb_xyz",     # 4.2+ extension
    "bl_ext.user_default.atomic_blender_pdb_xyz",
    "bl_ext.blender_org.io_mesh_atomic",
    "io_mesh_pdb",                                   # very old name
]


def pdb_operator_available():
    return "pdb" in dir(bpy.ops.import_mesh)


def ensure_atomic_addon():
    if pdb_operator_available():
        return True
    for mod in ATOMIC_MODULE_CANDIDATES:
        try:
            bpy.ops.preferences.addon_enable(module=mod)
        except Exception:
            continue
        if pdb_operator_available():
            log("Enabled Atomic Blender add-on: %s" % mod)
            return True
    return False


# =========================================================================
# Version-agnostic property mapping for import_mesh.pdb
# =========================================================================
# The Atomic Blender operator has renamed a few properties over the years,
# so instead of hard-coding names we look at the operator's RNA and use
# whichever alias actually exists in this Blender build.

PROP_ALIASES = {
    "ball_type":      ["ball"],
    "azimuth":        ["mesh_azimuth", "Ball_azimuth"],
    "zenith":         ["mesh_zenith", "Ball_zenith"],
    "ball_scale":     ["scale_ballradius", "Ball_radius_factor"],
    "radius_type":    ["atomradius", "radiustype"],
    "use_sticks":     ["use_sticks"],
    "stick_type":     ["use_sticks_type"],
    "stick_radius":   ["sticks_radius", "Stick_diameter"],
    "stick_sectors":  ["sticks_sectors", "Stick_sectors"],
    "stick_smooth":   ["use_sticks_smooth"],
    "stick_color":    ["use_sticks_color"],
    "use_center":     ["use_center", "put_to_center"],
    "use_camera":     ["use_camera"],
    "use_light":      ["use_light", "use_lamp"],
}

# Enum values in this add-on are index strings, not words.
BALL_TYPE_ENUM   = {"NURBS": '0', "MESH": '1', "META": '2'}
RADIUS_TYPE_ENUM = {"PREDEFINED": '0', "ATOMIC": '1', "VDW": '2'}
STICK_TYPE_ENUM  = {"DEFAULT": '0', "SKIN": '1', "NORMAL": '2'}


def operator_prop_names(op):
    try:
        return set(op.get_rna_type().properties.keys())
    except Exception:
        return set()


def build_import_kwargs(cfg):
    available = operator_prop_names(bpy.ops.import_mesh.pdb)

    wanted = {
        "ball_type":     BALL_TYPE_ENUM.get(cfg["ball_type"].upper(), '1'),
        "azimuth":       int(cfg["ball_subdiv"]),
        "zenith":        int(cfg["ball_subdiv"]),
        "ball_scale":    float(cfg["ball_scale"]),
        "radius_type":   RADIUS_TYPE_ENUM.get(cfg["radius_type"].upper(), '1'),
        "use_sticks":    bool(cfg["use_sticks"]),
        "stick_type":    STICK_TYPE_ENUM.get(cfg["stick_type"].upper(), '0'),
        "stick_radius":  float(cfg["stick_radius"]),
        "stick_sectors": int(cfg["stick_sectors"]),
        "stick_smooth":  bool(cfg["stick_smooth"]),
        "stick_color":   False,     # irrelevant for printing, keeps it simpler
        "use_center":    True,
        "use_camera":    False,
        "use_light":     False,
    }

    kwargs = {}
    missing = []
    for key, value in wanted.items():
        for alias in PROP_ALIASES.get(key, []):
            if alias in available:
                kwargs[alias] = value
                break
        else:
            missing.append(key)

    if missing:
        log("NOTE: importer has no property for %s - using its defaults. "
            "Available props: %s" % (", ".join(missing), sorted(available)))
    return kwargs


# =========================================================================
# STL import/export wrappers (operator names changed in Blender 4.1)
# =========================================================================

def stl_export(filepath, ascii_format=False, selected_only=False):
    filepath = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    if "stl_export" in dir(bpy.ops.wm):                      # 4.1+
        bpy.ops.wm.stl_export(filepath=filepath,
                              ascii_format=ascii_format,
                              export_selected_objects=selected_only,
                              apply_modifiers=True)
    elif "stl" in dir(bpy.ops.export_mesh):                  # <= 4.1 legacy
        bpy.ops.export_mesh.stl(filepath=filepath,
                                ascii=ascii_format,
                                use_selection=selected_only,
                                use_mesh_modifiers=True)
    else:
        raise RuntimeError(
            "No STL export operator found. On Blender 4.2+ either use the "
            "built-in wm.stl_export (should exist) or enable the legacy "
            "'STL format (legacy)' add-on.")
    return filepath


def stl_import(filepath):
    filepath = os.path.abspath(filepath)
    if "stl_import" in dir(bpy.ops.wm):                      # 4.1+
        bpy.ops.wm.stl_import(filepath=filepath)
    elif "stl" in dir(bpy.ops.import_mesh):                  # legacy
        bpy.ops.import_mesh.stl(filepath=filepath)
    else:
        raise RuntimeError("No STL import operator found.")


# =========================================================================
# Step 2 - enlarge hydrogen (and anything else) via the prototype ball
# =========================================================================
# Atomic Blender builds, per element, an instancing-vertices object named
# e.g. "Hydrogen_mesh" whose single child "Hydrogen_ball" is the prototype
# sphere. Scaling that child scales every instance, which is exactly the
# manual step. Names are matched loosely so add-on version differences and
# ".001" suffixes don't break it.

def find_instancers():
    return [ob for ob in bpy.context.scene.objects
            if ob.instance_type in {'VERTS', 'FACES'}]


def scale_element_prototype(element_name, factor):
    """Scale the prototype ball for one element. Returns True if found."""
    target = element_name.lower()
    hits = 0
    for parent in find_instancers():
        if target not in parent.name.lower():
            continue
        for child in parent.children:
            if child.type != 'MESH':
                continue
            child.scale = tuple(s * factor for s in child.scale)
            hits += 1
            log("  scaled prototype '%s' by %.3f" % (child.name, factor))
    bpy.context.view_layer.update()
    return hits > 0


# =========================================================================
# Steps 3-6 - realize instances into ONE mesh
# =========================================================================

def _cached_triangles(ob, cache):
    """Return (verts Nx3 float64, tris Mx3 int32) for an evaluated object,
    cached per mesh datablock so each prototype is only converted once."""
    key = ob.data.name_full if ob.data else ob.name_full
    if key in cache:
        return cache[key]

    me = ob.to_mesh()
    try:
        me.calc_loop_triangles()
        nv = len(me.vertices)
        nt = len(me.loop_triangles)
        if nv == 0 or nt == 0:
            result = (None, None)
        else:
            co = np.empty(nv * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            co.shape = (nv, 3)
            tri = np.empty(nt * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", tri)
            tri.shape = (nt, 3)
            result = (co, tri)
    finally:
        ob.to_mesh_clear()

    cache[key] = result
    return result


def realize_depsgraph(name="Structure"):
    """Bake every depsgraph instance into a single mesh object.

    This is the fast replacement for:
        Select All -> Object > Apply > Make Instances Real
        -> delete prototypes/parents -> Ctrl+J -> export STL -> import STL
    """
    if not HAVE_NUMPY:
        raise RuntimeError("numpy is required for the depsgraph method; "
                           "use --realize-method operator instead.")

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()

    instancers = set(find_instancers())
    prototypes = set()
    for p in instancers:
        prototypes.update(p.children)

    cache = {}
    all_verts = []
    all_tris = []
    v_offset = 0
    n_inst = 0

    for inst in depsgraph.object_instances:
        ob = inst.object
        if ob is None or ob.type != 'MESH':
            continue

        if inst.is_instance:
            pass                                # an instanced copy - keep it
        else:
            orig = ob.original
            if orig in instancers or orig in prototypes:
                continue                        # skip vertex clouds & prototypes
            if len(ob.data.polygons) == 0:
                continue                        # skip point-only meshes
            # a plain mesh object (e.g. sticks imported as "Normal" type) - keep

        verts, tris = _cached_triangles(ob, cache)
        if verts is None:
            continue

        M = np.array(inst.matrix_world, dtype=np.float64)
        xf = verts @ M[:3, :3].T + M[:3, 3]

        all_verts.append(xf.astype(np.float32))
        all_tris.append(tris + v_offset)
        v_offset += xf.shape[0]
        n_inst += 1

    if not all_verts:
        raise RuntimeError("Nothing to realize - did the PDB import produce "
                           "any geometry?")

    verts = np.concatenate(all_verts, axis=0)
    tris = np.concatenate(all_tris, axis=0).astype(np.int32)
    log("  baked %d instances -> %d verts / %d tris"
        % (n_inst, verts.shape[0], tris.shape[0]))

    mesh = _mesh_from_arrays(name + "_mesh", verts, tris)

    # The new mesh has no object using it yet, so the orphan purge below
    # would happily delete it. A temporary fake user keeps it alive.
    mesh.use_fake_user = True

    # Remove everything that came from the importer.
    for ob in list(scene.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    purge_orphans()

    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    mesh.use_fake_user = False
    activate(obj)
    return obj


def _mesh_from_arrays(name, verts, tris):
    """Fast mesh construction with a safe fallback."""
    nv = int(verts.shape[0])
    nt = int(tris.shape[0])

    mesh = bpy.data.meshes.new(name)
    try:
        mesh.vertices.add(nv)
        mesh.loops.add(nt * 3)
        mesh.polygons.add(nt)

        mesh.vertices.foreach_set("co", verts.ravel())
        mesh.loops.foreach_set("vertex_index", tris.ravel())
        starts = np.arange(0, nt * 3, 3, dtype=np.int32)
        mesh.polygons.foreach_set("loop_start", starts)
        try:
            # Read-only from Blender 4.0 on, where it is derived from
            # loop_start; harmless to skip there.
            mesh.polygons.foreach_set("loop_total",
                                      np.full(nt, 3, dtype=np.int32))
        except Exception:
            pass

        mesh.update(calc_edges=True)
        mesh.validate(verbose=False, clean_customdata=False)

        if len(mesh.polygons) != nt or len(mesh.vertices) != nv:
            raise RuntimeError("fast mesh build produced wrong counts")
    except Exception as exc:
        log("  fast mesh build failed (%s); falling back to from_pydata" % exc)
        bpy.data.meshes.remove(mesh)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts.tolist(), [], tris.tolist())
        mesh.update(calc_edges=True)
        mesh.validate(verbose=False)
    return mesh


def realize_operator(name="Structure"):
    """Classic path: duplicates_make_real + delete originals + join.
    Slower and much heavier on RAM, but mirrors the manual clicks exactly."""
    scene = bpy.context.scene

    instancers = set(find_instancers())
    prototypes = set()
    for p in instancers:
        prototypes.update(p.children)

    before = set(scene.objects)

    deselect_all()
    for ob in instancers:
        ob.select_set(True)
    if instancers:
        bpy.context.view_layer.objects.active = next(iter(instancers))
        bpy.ops.object.duplicates_make_real(use_base_parent=False,
                                            use_hierarchy=False)

    made_real = [ob for ob in scene.objects if ob not in before]
    log("  duplicates_make_real produced %d objects" % len(made_real))

    # delete parents (vertex clouds) and prototype balls/sticks
    for ob in list(instancers) + list(prototypes):
        if ob.name in bpy.data.objects:
            bpy.data.objects.remove(ob, do_unlink=True)

    meshes = [ob for ob in scene.objects
              if ob.type == 'MESH' and len(ob.data.polygons) > 0]
    if not meshes:
        raise RuntimeError("Nothing left after make-instances-real.")

    activate(meshes[0])
    for ob in meshes:
        ob.select_set(True)
    if len(meshes) > 1:
        bpy.ops.object.join()

    obj = bpy.context.view_layer.objects.active
    obj.name = name
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


# =========================================================================
# Step 6 - remesh
# =========================================================================

def apply_modifier_safe(obj):
    """Apply all modifiers without relying on operator context."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    obj.modifiers.clear()
    old = obj.data
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def voxel_remesh(obj, voxel_size, adaptivity=0.0, smooth=True):
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    mod = obj.modifiers.new(name="VoxelRemesh", type='REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = float(voxel_size)
    try:
        mod.adaptivity = float(adaptivity)
    except Exception:
        pass
    try:
        mod.use_smooth_shade = bool(smooth)
    except Exception:
        pass

    apply_modifier_safe(obj)
    return obj


def decimate(obj, ratio):
    if ratio <= 0 or ratio >= 1:
        return obj
    activate(obj)
    mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = float(ratio)
    apply_modifier_safe(obj)
    return obj


# -------------------------------------------------------------------------
# Triangle budget
# -------------------------------------------------------------------------
# Voxel remesh emits mostly quads at adaptivity 0 and mostly triangles above
# it, so face count is a poor proxy. STL stores triangles, so the number that
# actually governs the file size is the triangulated count:
#     binary STL bytes = 84 + 50 * triangles
# A 1,000,000 triangle budget therefore lands at roughly 50 MB.
#
# Adaptivity cannot be solved for analytically - its effect depends on how
# much of the surface is locally flat, which varies from structure to
# structure. So we measure: remesh, count, and if we are over budget, raise
# adaptivity and remesh again from a pristine copy of the pre-remesh mesh.
# Attempts are capped because each one pays the full voxel remesh cost.
# If adaptivity saturates before reaching the budget (it does saturate - past
# roughly 0.6 the returns get small), a final Decimate pass closes the gap,
# since that can hit an exact ratio.

STL_BYTES_PER_TRI = 50


def obj_tri_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def estimated_stl_mb(tris):
    return (84 + STL_BYTES_PER_TRI * tris) / 1e6


def _swap_mesh(obj, new_mesh):
    old = obj.data
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _adaptivity_ladder(start, cap):
    """Escalating candidates, coarse at first because the response is
    strongly sub-linear near zero."""
    rungs = [0.15, 0.30, 0.45, 0.60, 0.75, cap]
    out = [start] + [r for r in rungs if r > start + 1e-6 and r <= cap + 1e-6]
    seen = []
    for a in out:
        if not seen or a > seen[-1] + 1e-6:
            seen.append(min(a, cap))
    return seen


def remesh_to_budget(obj, voxel_size, max_tris, start_adaptivity=0.0,
                     smooth=True, max_attempts=4, adaptivity_cap=0.9,
                     allow_decimate=True):
    """Voxel remesh, raising adaptivity until the triangle count fits the
    budget. Returns (adaptivity_used, final_triangle_count)."""

    # Pristine copy of the pre-remesh mesh so each attempt starts clean.
    backup = obj.data.copy()
    backup.use_fake_user = True

    ladder = _adaptivity_ladder(start_adaptivity, adaptivity_cap)
    if max_tris <= 0:
        ladder = ladder[:1]          # budget disabled: single pass

    used = start_adaptivity
    tris = None

    try:
        for attempt, a in enumerate(ladder[:max(1, max_attempts)], start=1):
            if attempt > 1:
                _swap_mesh(obj, backup.copy())   # restore, keep backup pristine

            t0 = time.time()
            voxel_remesh(obj, voxel_size, a, smooth)
            tris = obj_tri_count(obj)
            used = a
            log("  attempt %d: adaptivity=%.2f -> %s triangles "
                "(~%.1f MB STL, %.1f s)"
                % (attempt, a, format(tris, ","), estimated_stl_mb(tris),
                   time.time() - t0))

            if max_tris <= 0 or tris <= max_tris:
                break

            if a >= adaptivity_cap - 1e-6:
                log("  adaptivity is capped at %.2f and still over budget"
                    % adaptivity_cap)
                break
            if attempt >= max_attempts:
                log("  attempt limit (%d) reached" % max_attempts)
                break
    finally:
        backup.use_fake_user = False
        if backup.users == 0:
            bpy.data.meshes.remove(backup)

    # Backstop: Decimate hits an exact ratio, so it can always close the gap.
    if max_tris > 0 and tris and tris > max_tris and allow_decimate:
        ratio = (max_tris / float(tris)) * 0.97      # margin for rounding
        log("  applying Decimate (ratio=%.4f) to reach the budget" % ratio)
        decimate(obj, ratio)
        tris = obj_tri_count(obj)
        log("  after decimate: %s triangles (~%.1f MB STL)"
            % (format(tris, ","), estimated_stl_mb(tris)))

    if max_tris > 0 and tris and tris > max_tris:
        log("  WARNING: still %s triangles, above the %s budget. Increase "
            "--voxel-size (count scales as 1/size^2) for a better-looking "
            "result than pushing adaptivity further."
            % (format(tris, ","), format(max_tris, ",")))

    return used, tris


def scale_to_size(obj, target):
    """Uniformly scale so the longest bounding-box axis equals `target`.
    STL carries no units; most slicers read 1 Blender unit as 1 mm."""
    if target <= 0:
        return obj
    activate(obj)
    dims = obj.dimensions
    longest = max(dims)
    if longest <= 0:
        return obj
    f = target / longest
    obj.scale = tuple(s * f for s in obj.scale)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    log("  scaled by %.4f -> bounding box %.2f x %.2f x %.2f"
        % (f, obj.dimensions[0], obj.dimensions[1], obj.dimensions[2]))
    return obj


# =========================================================================
# Pipeline
# =========================================================================

def process_one(pdb_path, out_path, cfg):
    t0 = time.time()
    log("=" * 66)
    log("Input : %s" % pdb_path)
    log("Output: %s" % out_path)
    log("Blender %s" % (".".join(str(v) for v in bversion())))

    if CLEAR_SCENE:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        ensure_atomic_addon()   # factory settings can drop the add-on state
    else:
        for ob in list(bpy.context.scene.objects):
            bpy.data.objects.remove(ob, do_unlink=True)

    # ---- 1. import ------------------------------------------------------
    kwargs = build_import_kwargs(cfg)
    log("Importing PDB with: %s" % kwargs)
    bpy.ops.import_mesh.pdb(filepath=os.path.abspath(pdb_path), **kwargs)

    n_obj = len(bpy.context.scene.objects)
    log("Imported %d objects (%d instancing parents)"
        % (n_obj, len(find_instancers())))
    if n_obj == 0:
        raise RuntimeError("Import produced no objects.")
    if cfg["use_sticks"] and len(find_instancers()) < 2:
        log("WARNING: only one instancing parent found - the PDB may have no "
            "CONECT records, so no bonds were created.")

    # ---- 2. enlarge hydrogen -------------------------------------------
    if cfg["h_scale"] and abs(cfg["h_scale"] - 1.0) > 1e-9:
        log("Scaling Hydrogen prototype by %.3f" % cfg["h_scale"])
        if not scale_element_prototype("Hydrogen", cfg["h_scale"]):
            log("  no Hydrogen instancer found - skipping "
                "(check the element naming in your PDB)")
    for element, factor in (cfg.get("extra_scales") or {}).items():
        log("Scaling %s prototype by %.3f" % (element, factor))
        scale_element_prototype(element, factor)

    # ---- 3-5. realize + join -------------------------------------------
    log("Realizing instances (method=%s)..." % cfg["realize_method"])
    if cfg["realize_method"] == "operator":
        obj = realize_operator()
    else:
        obj = realize_depsgraph()
    log("Realized mesh: %d verts / %d polys"
        % (len(obj.data.vertices), len(obj.data.polygons)))

    if cfg["save_raw"]:
        raw = os.path.splitext(out_path)[0] + "_raw.stl"
        stl_export(raw, ascii_format=cfg["ascii_stl"])
        log("Wrote raw STL: %s (%.1f MB)" % (raw, os.path.getsize(raw) / 1e6))

    # ---- 6. remesh ------------------------------------------------------
    if cfg["do_remesh"]:
        budget = int(cfg["max_tris"])
        log("Voxel remesh: size=%.4f start adaptivity=%.3f budget=%s tris"
            % (cfg["voxel_size"], cfg["adaptivity"],
               format(budget, ",") if budget > 0 else "off"))
        dims = obj.dimensions
        est = (dims[0] / cfg["voxel_size"]) * (dims[1] / cfg["voxel_size"]) \
              * (dims[2] / cfg["voxel_size"])
        log("  bbox %.2f x %.2f x %.2f -> ~%.1f M voxels"
            % (dims[0], dims[1], dims[2], est / 1e6))
        if est > 4e9:
            log("  WARNING: that is a very large voxel grid. If Blender runs "
                "out of memory, increase --voxel-size.")

        used_a, tris = remesh_to_budget(
            obj,
            voxel_size=cfg["voxel_size"],
            max_tris=budget,
            start_adaptivity=cfg["adaptivity"],
            smooth=cfg["remesh_smooth"],
            max_attempts=cfg["max_remesh_attempts"],
            adaptivity_cap=cfg["adaptivity_cap"],
            allow_decimate=cfg["auto_decimate"],
        )
        log("  settled on adaptivity=%.2f -> %d verts / %d polys / %s tris"
            % (used_a, len(obj.data.vertices), len(obj.data.polygons),
               format(tris, ",")))

    if cfg["decimate_ratio"]:
        decimate(obj, cfg["decimate_ratio"])
        log("  after decimate: %d verts / %d polys"
            % (len(obj.data.vertices), len(obj.data.polygons)))

    # ---- 7. scale + export ---------------------------------------------
    scale_to_size(obj, cfg["target_size"])

    activate(obj)
    stl_export(out_path, ascii_format=cfg["ascii_stl"])
    size_mb = os.path.getsize(out_path) / 1e6
    log("Wrote %s (%.1f MB) in %.1f s" % (out_path, size_mb, time.time() - t0))

    if cfg["blend_out"]:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(cfg["blend_out"]))
        log("Saved blend: %s" % cfg["blend_out"])

    return out_path


# =========================================================================
# CLI
# =========================================================================

def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="pdb_to_printable_stl.py",
        description="Blender: PDB -> print-ready STL")
    p.add_argument("--input", required=True,
                   help=".pdb file or a folder containing .pdb files")
    p.add_argument("--output", default="", help="final .stl path (single file)")
    p.add_argument("--outdir", default="", help="output folder (batch mode)")

    p.add_argument("--ball-type", default=CONFIG["ball_type"],
                   choices=["NURBS", "MESH", "META"])
    p.add_argument("--ball-subdiv", type=int, default=CONFIG["ball_subdiv"])
    p.add_argument("--ball-scale", type=float, default=CONFIG["ball_scale"])
    p.add_argument("--radius-type", default=CONFIG["radius_type"],
                   choices=["PREDEFINED", "ATOMIC", "VDW"])
    p.add_argument("--no-sticks", action="store_true")
    p.add_argument("--stick-type", default=CONFIG["stick_type"],
                   choices=["DEFAULT", "SKIN", "NORMAL"])
    p.add_argument("--stick-radius", type=float, default=CONFIG["stick_radius"])
    p.add_argument("--stick-sectors", type=int, default=CONFIG["stick_sectors"])

    p.add_argument("--h-scale", type=float, default=CONFIG["h_scale"])
    p.add_argument("--scale-element", action="append", default=[],
                   metavar="NAME=FACTOR",
                   help="extra per-element scaling, e.g. --scale-element Oxygen=1.2")

    p.add_argument("--realize-method", default=CONFIG["realize_method"],
                   choices=["depsgraph", "operator"])

    p.add_argument("--no-remesh", action="store_true")
    p.add_argument("--voxel-size", type=float, default=CONFIG["voxel_size"])
    p.add_argument("--adaptivity", type=float, default=CONFIG["adaptivity"],
                   help="starting adaptivity; raised automatically to meet "
                        "--max-tris")
    p.add_argument("--max-tris", type=int, default=CONFIG["max_tris"],
                   help="triangle budget for the final STL (0 disables). "
                        "Binary STL is ~50 bytes/triangle, so 1000000 is "
                        "about a 50 MB file.")
    p.add_argument("--max-remesh-attempts", type=int,
                   default=CONFIG["max_remesh_attempts"],
                   help="cap on adaptivity retries; each costs a full remesh")
    p.add_argument("--adaptivity-cap", type=float,
                   default=CONFIG["adaptivity_cap"])
    p.add_argument("--no-auto-decimate", action="store_true",
                   help="do not use Decimate to close the last gap to budget")
    p.add_argument("--decimate", type=float, default=CONFIG["decimate_ratio"])

    p.add_argument("--target-size", type=float, default=CONFIG["target_size"])
    p.add_argument("--save-raw", action="store_true")
    p.add_argument("--ascii-stl", action="store_true")
    p.add_argument("--blend-out", default="")
    return p.parse_args(argv)


def cfg_from_args(a):
    cfg = dict(CONFIG)
    cfg.update({
        "input": a.input,
        "output": a.output,
        "outdir": a.outdir,
        "ball_type": a.ball_type,
        "ball_subdiv": a.ball_subdiv,
        "ball_scale": a.ball_scale,
        "radius_type": a.radius_type,
        "use_sticks": not a.no_sticks,
        "stick_type": a.stick_type,
        "stick_radius": a.stick_radius,
        "stick_sectors": a.stick_sectors,
        "h_scale": a.h_scale,
        "realize_method": a.realize_method,
        "do_remesh": not a.no_remesh,
        "voxel_size": a.voxel_size,
        "adaptivity": a.adaptivity,
        "max_tris": a.max_tris,
        "max_remesh_attempts": a.max_remesh_attempts,
        "adaptivity_cap": a.adaptivity_cap,
        "auto_decimate": not a.no_auto_decimate,
        "decimate_ratio": a.decimate,
        "target_size": a.target_size,
        "save_raw": a.save_raw,
        "ascii_stl": a.ascii_stl,
        "blend_out": a.blend_out,
    })
    extra = {}
    for item in a.scale_element:
        if "=" in item:
            k, v = item.split("=", 1)
            try:
                extra[k.strip()] = float(v)
            except ValueError:
                log("Ignoring bad --scale-element value: %s" % item)
    cfg["extra_scales"] = extra
    return cfg


def main():
    argv = sys.argv
    if "--" in argv:
        cfg = cfg_from_args(parse_args(argv[argv.index("--") + 1:]))
    else:
        cfg = dict(CONFIG)
        if not cfg["input"]:
            log("No input given. Either run:\n"
                "  blender --background --factory-startup --python %s -- "
                "--input file.pdb --output out.stl\n"
                "or fill in the CONFIG block at the top of the script."
                % os.path.basename(__file__))
            return 1

    if not ensure_atomic_addon():
        log("ERROR: could not find/enable the Atomic Blender PDB add-on.\n"
            "  Blender <= 4.1: Edit > Preferences > Add-ons > search 'Atomic'\n"
            "  Blender 4.2+ : Edit > Preferences > Get Extensions > 'Atomic'\n"
            "Then re-run. (Remember that --factory-startup ignores saved "
            "preferences, which is why the script tries to enable it itself.)")
        return 2

    src = os.path.abspath(os.path.expanduser(cfg["input"]))

    if os.path.isdir(src):
        files = sorted(glob.glob(os.path.join(src, "*.pdb")))
        if not files:
            log("No .pdb files in %s" % src)
            return 1
        outdir = os.path.abspath(cfg["outdir"] or os.path.join(src, "stl_out"))
        os.makedirs(outdir, exist_ok=True)
        log("Batch mode: %d files -> %s" % (len(files), outdir))
        failures = 0
        for f in files:
            base = os.path.splitext(os.path.basename(f))[0]
            out = os.path.join(outdir, base + "_print.stl")
            try:
                process_one(f, out, cfg)
            except Exception as exc:
                failures += 1
                log("FAILED on %s: %s" % (f, exc))
        log("Batch done. %d/%d succeeded." % (len(files) - failures, len(files)))
        return 1 if failures else 0

    if not os.path.isfile(src):
        log("Input not found: %s" % src)
        return 1

    out = cfg["output"]
    if not out:
        out = os.path.splitext(src)[0] + "_print.stl"
    elif cfg["outdir"]:
        out = os.path.join(cfg["outdir"], out)
    process_one(src, os.path.abspath(os.path.expanduser(out)), cfg)
    return 0


if __name__ == "__main__":
    code = main()
    if bpy.app.background:
        sys.exit(code)


# =========================================================================
# NOTES ON TUNING
# =========================================================================
#
# VOXEL SIZE is the single most important knob. It is in Blender units, and
# Atomic Blender puts 1 unit = 1 Angstrom, so with your settings:
#     sphere radii  ~ 0.8 x atomic radius   (roughly 0.5 - 1.6 units)
#     bond diameter ~ 2 x 0.4 = 0.8 units
# The thinnest feature is the bond. Aim for at least 6-8 voxels across it:
#     voxel 0.10 -> ~8 voxels per bond   (good default)
#     voxel 0.15 -> ~5 voxels, coarser, much smaller file
#     voxel 0.06 -> crisp, but memory and triangle count climb fast
# Cost scales as 1/voxel_size^3, so halving it is ~8x the work.
#
# ADAPTIVITY is now driven by the --max-tris budget rather than set by hand.
# The script remeshes at the starting adaptivity, counts triangles, and if it
# is over budget restarts from a saved copy with a higher value, walking
# 0.15 -> 0.30 -> 0.45 -> 0.60 -> 0.75 -> cap. Each attempt costs one full
# remesh, so --max-remesh-attempts bounds the runtime. Adaptivity saturates
# past roughly 0.6, so a Decimate pass closes any remaining gap; that always
# hits the target because it takes an exact ratio.
#
# WHICH KNOB TO REACH FOR when the budget forces heavy adaptivity: raising
# --voxel-size is usually the better trade. Triangle count scales with
# surface area over voxel_size^2, so 0.10 -> 0.14 roughly halves it while
# keeping triangles evenly distributed. High adaptivity instead concentrates
# error on the flattest regions, which on a ball-and-stick model means the
# middles of the spheres go faceted while the bond junctions stay dense.
# Watch the per-attempt log lines and decide from there.
#
# BALL SUBDIV: after voxel remeshing, the input sphere tessellation barely
# matters, because the remesher resamples everything. Dropping from 16 to 12
# makes the bake faster and does not change the printed result. Skip the
# remesh (--no-remesh) and it matters again.
#
# WHY THE REMESH HELPS PRINTING: the realized mesh is thousands of separate,
# interpenetrating closed shells. Many slicers cope, but some produce
# artifacts at the intersections. Voxel remesh performs a true union and
# emits one watertight manifold surface, which is what you want.
#
# ONE CAVEAT: voxel remesh will fuse atoms that are closer together than
# about one voxel, and it rounds off sharp creases. For a ball-and-stick
# print that is usually desirable. If you need the raw booleans instead,
# use --no-remesh --save-raw and clean up elsewhere.
#
# VESTA: the .cif -> truncate -> .xyz -> .pdb part cannot be scripted, VESTA
# has no Python API. If you want to remove that step entirely, ASE, pymatgen
# or Open Babel can read a CIF, build a supercell, cut a slab, and write a
# PDB with CONECT records - then this script takes over from there.
