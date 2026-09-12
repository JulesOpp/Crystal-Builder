"""
xtalapp.viewport.vtk_scene
==========================
SceneModel -> VTK actors.

VTK but no Qt, on purpose: the whole render path can be exercised
offscreen in a test (:func:`render_offscreen`), which is also how the
screenshots in the docs get made.

Everything is drawn with as few actors as possible, because actor count
-- not triangle count -- is what makes a viewer stutter:

* every atom is one point in a single polydata, drawn by one
  :class:`vtkGlyph3DMapper` with per-point radius and colour arrays;
* ORTEP's octant shading is a second glyph over the same points,
  instanced from one small source of arcs and shaded octants -- the
  boundary is the same curve on every ellipsoid because every
  ellipsoid is the same unit sphere transformed;
* every bond half is one line in a third polydata, thickened by one
  tube filter, coloured per line -- a double bond contributes two of
  those lines and a triple three, so the actor count does not move
  when the orders are drawn;
* the thin dashed inner lines that mark aromatic bonds are a fourth,
  because a tube filter has one radius and they need a smaller one;
* every coordination polyhedron is a set of triangles in a fifth,
  translucent polydata, coloured per face;
* a site more than one thing shares is a sphere cut into wedges in a
  sixth, opaque, standing over the spheres it replaces;
* the net, when a chemist has drawn one, is a seventh -- thicker,
  translucent, one flat colour, running over the real bonds rather
  than in place of them;
* the planes the user defined are an eighth, translucent triangles
  like the polyhedra, with their normals in a ninth set of lines;
* the cell is a tenth polydata of lines.

Ten actors for the structure, however many atoms there are.

The scale bar is the one thing here that is not geometry.  It is two
2-D actors in the corner and its length is a question about the
camera, so it is refreshed from an observer rather than from the
model -- see :meth:`VtkScene._refresh_scale_bar`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

# Importing these registers the OpenGL and text rendering factories.
import vtkmodules.vtkRenderingFreeType  # noqa: F401
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from vtkmodules.util.numpy_support import (
    numpy_to_vtk,
    numpy_to_vtkIdTypeArray,
)
from vtkmodules.vtkCommonCore import (
    VTK_FLOAT,
    VTK_UNSIGNED_CHAR,
    vtkFloatArray,
    vtkIdTypeArray,
    vtkPoints,
    vtkUnsignedCharArray,
)
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkTubeFilter
from vtkmodules.vtkFiltersSources import vtkSphereSource
from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
from vtkmodules.vtkIOImage import (
    vtkJPEGWriter,
    vtkPNGWriter,
    vtkTIFFWriter,
)
from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkActor2D,
    vtkBillboardTextActor3D,
    vtkCoordinate,
    vtkGlyph3DMapper,
    vtkPolyDataMapper,
    vtkPolyDataMapper2D,
    vtkRenderer,
    vtkRenderWindow,
    vtkTextActor,
    vtkWindowToImageFilter,
)

from xtalapp.viewport import scene as scene_model
from xtalapp.viewport.scene import (
    CUE_GRADIENT_MAX,
    CUE_GRADIENT_MIN,
    CUE_START_MAX,
    DASH_RADIUS,
    HIGHLIGHT_BOND_GROWTH,
    HIGHLIGHT_COLOR,
    HIGHLIGHT_GROWTH,
    HIGHLIGHT_OPACITY,
    OCTANT_DARKEN,
    split_by_order,
)

# vtkIdType is 32- or 64-bit depending on how VTK was built; the
# connectivity arrays have to match or VTK reads them as garbage.
ID_TYPE = np.int64 if vtkIdTypeArray().GetDataTypeSize() == 8 \
    else np.int32

SPHERE_RESOLUTION = 24
TUBE_SIDES = 12

# ORTEP's octant shading, in glyph space -- the unit sphere every
# ellipsoid is a transform of.  Both radii are just over 1 so the
# furniture sits outside the ellipsoid rather than z-fighting with it,
# and the arcs are outside the shading for the same reason.  They
# scale with the ellipsoid because the glyph does, so the margin stays
# proportional however big the atom is drawn.
#
# **The margin is set by the tessellation and not by taste.**  Nothing
# here is a sphere: a triangle spanning an angle t on a sphere of
# radius R sags to R cos(t/2) in the middle, and the ellipsoid
# underneath is inscribed -- so an octant patch clears it only while
# ``R cos(t/2) > 1``.  At five subdivisions a 90-degree octant sags
# 1.2% and 1.006 sank *inside* the atom over the middle of every
# facet, which is what the speckled first attempt was.  Ten
# subdivisions sag 0.3%, which 1.012 clears with room for the depth
# buffer; raising the radius instead is the fix that grows the atom.
OCTANT_ARC_RADIUS = 1.020
OCTANT_SHADE_RADIUS = 1.012
OCTANT_SEGMENTS = 48            # per principal section
OCTANT_SUBDIVISIONS = 10        # of each shaded octant
MAX_LABELS = 400            # beyond this, labels are noise anyway

# A matte surface: the same shading with the highlight taken off and
# the shadowed side lifted, because a figure that will be printed
# cannot afford a white hole on every atom -- and because the side of
# an atom facing away from the light has to keep its colour when the
# picture is the atoms and nothing else.  VTK's own defaults (ambient
# 0, diffuse 1) are what "lit" puts back.
MATTE_AMBIENT = 0.38
MATTE_DIFFUSE = 0.72

# A flat surface: all ambient and no diffuse, which is one colour edge
# to edge because an ambient term is unshaded.
#
# **Not ``SetLighting(False)``, and that distinction is a bug fixed
# rather than a preference.**  With lighting switched off VTK stops
# declaring ``vertexVCVSOutput`` in the fragment shader -- there is no
# lighting left to need a view-space position -- and the depth-cue
# replacement below is written in terms of exactly that.  The shader
# then fails to compile and the actor draws *nothing*: turning the
# fade on made a cartoon picture, and a wireframe before it, vanish
# into the background.  Ambient-only is the same picture and keeps the
# varying, so the fade has something to measure.
FLAT_AMBIENT = 1.0
FLAT_DIFFUSE = 0.0


# The element legend, in fractions of the window.
LEGEND_X = 0.90
LEGEND_TOP = 0.94
LEGEND_ROW = 0.045
LEGEND_SWATCH = 0.018
LEGEND_FONT = 15


# The scale bar, in fractions of the window: where its left end sits,
# and how much of the width it aims for before the length is rounded
# to something a reader can multiply by.
# Clear of the orientation gizmo, which owns the bottom-left corner
# out to x = 0.16 -- see :func:`orientation_marker`.
BAR_X = 0.21
BAR_Y = 0.055
BAR_TICK = 0.012            # half-height of the end caps
BAR_TARGET = 0.22
BAR_FONT = 15
#: The lengths a scale bar is allowed to be, per decade.  1, 2 and 5
#: are the numbers a reader can count off a picture; 3 and 7 are not.
BAR_STEPS = (1.0, 2.0, 5.0)

# The ghost: the atom a click would place, drawn in its own colour and
# see-through, so that what is behind it stays readable while it is
# being aimed.  Solid enough to read as an atom, faint enough that
# nobody mistakes it for one that is there.
GHOST_OPACITY = 0.45

# Depth cueing, as a shader replacement.  VTK 9 has no SetFog on either
# the property or the renderer, and vtkDepthOfFieldPass is a blur
# rather than a fade, so the fade is written into the fragment shader
# of the actors that carry it.
#
# ``vertexVCVSOutput.z`` and not ``gl_FragCoord.z``: the first is a
# distance in view space and is linear, the second is the depth buffer
# and is so heavily skewed by a perspective projection that nearly the
# whole scene lands in the last few thousandths of it.  Fading by that
# gives a picture that is either untouched or entirely washed out, with
# nothing in between.
#
# The near and far distances are uniforms rather than constants because
# they are the scene's own bounds along the view direction, and they
# change whenever the camera moves or the display range grows -- see
# :meth:`VtkScene._refresh_depth_cue`.  ``cueNear`` is where the fade
# *begins* and not where the structure does: the start control moves
# it back into the scene, which is the whole of leaving the front of a
# slab crisp.  ``cueGradient`` is the exponent on the ramp.
#
# The same arithmetic lives in
# :func:`~xtalapp.viewport.scene.cue_fraction`, in numpy, for the one
# actor this replacement cannot reach.
DEPTH_CUE_SHADER = """//VTK::Light::Impl
  float cueDistance = -vertexVCVSOutput.z;
  float cueT = clamp((cueDistance - cueNear)
                     / max(cueFar - cueNear, 1e-6), 0.0, 1.0);
  gl_FragData[0].rgb = mix(gl_FragData[0].rgb, cueColor,
                           pow(cueT, cueGradient) * cueStrength);
"""


def _to_uchar(colors: np.ndarray, name: str) -> vtkUnsignedCharArray:
    arr = numpy_to_vtk(np.ascontiguousarray(colors, dtype=np.uint8),
                       deep=True, array_type=VTK_UNSIGNED_CHAR)
    arr.SetName(name)
    return arr


def _to_float(values: np.ndarray, name: str) -> vtkFloatArray:
    arr = numpy_to_vtk(np.ascontiguousarray(values, dtype=np.float32),
                       deep=True, array_type=VTK_FLOAT)
    arr.SetName(name)
    return arr


def _points(positions: np.ndarray) -> vtkPoints:
    pts = vtkPoints()
    pts.SetData(numpy_to_vtk(
        np.ascontiguousarray(positions, dtype=np.float64), deep=True))
    return pts


def _interleave(starts, ends) -> np.ndarray:
    """``[start0, end0, start1, end1, ...]`` -- the point order a line
    polydata is built in, and the order it has to be refilled in."""
    n = len(starts)
    out = np.empty((2 * n, 3), dtype=np.float64)
    out[0::2] = starts
    out[1::2] = ends
    return out


def _line_polydata(starts, ends, colors) -> vtkPolyData:
    """One line cell per segment, coloured by cell data.

    Every array is handed to VTK whole.  Writing these point by point
    is what used to make a click on a large structure visibly stutter:
    the geometry is already in numpy, and copying it a tuple at a time
    costs more than drawing it.
    """
    n = len(starts)
    poly = vtkPolyData()
    poly.SetPoints(_points(_interleave(starts, ends)))
    lines = vtkCellArray()
    lines.SetData(
        numpy_to_vtkIdTypeArray(
            np.arange(0, 2 * n + 1, 2, dtype=ID_TYPE), deep=True),
        numpy_to_vtkIdTypeArray(
            np.arange(2 * n, dtype=ID_TYPE), deep=True))
    poly.SetLines(lines)
    poly.GetCellData().SetScalars(_to_uchar(colors, "colors"))
    return poly


def _triangle_polydata(points, faces, colors) -> vtkPolyData:
    """Triangles over a shared vertex list, coloured by cell data."""
    poly = vtkPolyData()
    poly.SetPoints(_points(points))
    faces = np.ascontiguousarray(faces, dtype=ID_TYPE)
    cells = vtkCellArray()
    cells.SetData(
        numpy_to_vtkIdTypeArray(
            np.arange(0, 3 * len(faces) + 1, 3, dtype=ID_TYPE),
            deep=True),
        numpy_to_vtkIdTypeArray(faces.ravel(), deep=True))
    poly.SetPolys(cells)
    poly.GetCellData().SetScalars(_to_uchar(colors, "colors"))
    return poly


def _flat(prop) -> None:
    """Draw with this property's colour and no shading on it.

    See :data:`FLAT_AMBIENT`: ambient-only rather than lighting off,
    because lighting off takes the depth cue's shader with it.
    """
    prop.SetAmbient(FLAT_AMBIENT)
    prop.SetDiffuse(FLAT_DIFFUSE)
    prop.SetSpecular(0.0)


def _darken(colors, amount: float) -> np.ndarray:
    """The same hue, further towards black."""
    return np.clip(np.asarray(colors, float) * amount,
                   0, 255).astype(np.uint8)


def _spherical_triangle(corners, radius: float, subdivisions: int):
    """One octant of a sphere, as points and triangles.

    A barycentric grid over the flat triangle pushed out onto the
    sphere.  Subdividing and then normalising -- rather than
    normalising three corners and calling it a face -- is what keeps
    the shaded octant against the surface instead of cutting a chord
    across it, which at a 3:1 axis ratio is the difference between a
    shaded region and a visible facet.
    """
    n = subdivisions
    corners = np.asarray(corners, dtype=float)
    index, points = {}, []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            weights = np.array([i, j, n - i - j], dtype=float) / n
            v = weights @ corners
            index[(i, j)] = len(points)
            points.append(radius * v / np.linalg.norm(v))
    faces = []
    for i in range(n):
        for j in range(n - i):
            faces.append((index[(i, j)], index[(i + 1, j)],
                          index[(i, j + 1)]))
            if i + j < n - 1:
                faces.append((index[(i + 1, j)], index[(i + 1, j + 1)],
                              index[(i, j + 1)]))
    return np.array(points), np.array(faces, dtype=ID_TYPE)


def _octant_source() -> vtkPolyData:
    """The ORTEP furniture for one ellipsoid, in glyph space.

    Three principal sections as closed polylines, and **two opposite
    octants** filled.  Two and not the one ORTEP draws on paper,
    because a paper figure is drawn from a chosen viewpoint and this
    is not: an octant fixed in the ellipsoid's own frame faces away
    from the camera for half of the orientations in a crystal, and an
    atom that loses its shading as the structure is turned reads as a
    different kind of atom.  A centrosymmetric pair cannot: whichever
    way the camera looks, one of the two is on the near side.

    Built in glyph space once and instanced, which is the whole reason
    this costs one actor rather than one mesh per atom -- every
    ellipsoid is the same unit sphere under a different transform, so
    the octant boundary is the same curve on all of them.
    """
    axes = np.eye(3)
    blocks, cells = [], []
    lines = vtkCellArray()
    base = 0
    for u, v in ((0, 1), (1, 2), (2, 0)):
        angle = np.linspace(0.0, 2 * np.pi, OCTANT_SEGMENTS,
                            endpoint=False)
        ring = OCTANT_ARC_RADIUS * (
            np.cos(angle)[:, None] * axes[u]
            + np.sin(angle)[:, None] * axes[v])
        blocks.append(ring)
        lines.InsertNextCell(OCTANT_SEGMENTS + 1)
        for k in range(OCTANT_SEGMENTS):
            lines.InsertCellPoint(base + k)
        lines.InsertCellPoint(base)             # close the loop
        base += OCTANT_SEGMENTS

    for sign in (1.0, -1.0):
        points, faces = _spherical_triangle(
            sign * axes, OCTANT_SHADE_RADIUS, OCTANT_SUBDIVISIONS)
        blocks.append(points)
        cells.append(faces + base)
        base += len(points)
    faces = np.concatenate(cells)

    poly = vtkPolyData()
    poly.SetPoints(_points(np.concatenate(blocks)))
    poly.SetLines(lines)
    polys = vtkCellArray()
    polys.SetData(
        numpy_to_vtkIdTypeArray(
            np.arange(0, 3 * len(faces) + 1, 3, dtype=ID_TYPE),
            deep=True),
        numpy_to_vtkIdTypeArray(
            np.ascontiguousarray(faces.ravel(), dtype=ID_TYPE),
            deep=True))
    poly.SetPolys(polys)
    return poly


def _nice_length(wanted: float) -> float:
    """The nearest length at or below ``wanted`` that a reader can
    count in: 1, 2 or 5 times a power of ten.

    Never zero, however far in the camera is -- a bar of no length is
    a bar that says nothing, and the picture is better off claiming
    0.001 A than claiming nothing.
    """
    wanted = max(float(wanted), 1e-6)
    decade = 10.0 ** np.floor(np.log10(wanted))
    for step in reversed(BAR_STEPS):
        if step * decade <= wanted:
            return float(step * decade)
    return float(decade)                            # pragma: no cover


def _swatch(x: float, y: float, color) -> vtkActor2D:
    """A filled square in normalized viewport coordinates."""
    poly = vtkPolyData()
    half = LEGEND_SWATCH / 2
    corners = np.array([[x - half, y - half, 0.0],
                        [x + half, y - half, 0.0],
                        [x + half, y + half, 0.0],
                        [x - half, y + half, 0.0]])
    poly.SetPoints(_points(corners))
    quad = vtkCellArray()
    quad.SetData(
        numpy_to_vtkIdTypeArray(np.array([0, 4], dtype=ID_TYPE),
                                deep=True),
        numpy_to_vtkIdTypeArray(np.arange(4, dtype=ID_TYPE),
                                deep=True))
    poly.SetPolys(quad)

    mapper = vtkPolyDataMapper2D()
    mapper.SetInputData(poly)
    coordinate = vtkCoordinate()
    coordinate.SetCoordinateSystemToNormalizedViewport()
    mapper.SetTransformCoordinate(coordinate)
    actor = vtkActor2D()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*color)
    return actor


class VtkScene:
    """Owns the actors for one structure and keeps them in sync with a
    :class:`~xtalapp.viewport.scene.SceneModel`."""

    def __init__(self, renderer: vtkRenderer | None = None):
        self.renderer = renderer or vtkRenderer()
        self.model = None
        self._atom_poly = vtkPolyData()
        self._axes = np.zeros((0, 3), np.float32)
        self._quaternions = np.zeros((0, 4), np.float32)
        self._label_actors: list[vtkBillboardTextActor3D] = []
        self._legend_actors: list = []
        self._build_atom_actor()
        self._build_outline_actor()
        self._build_octant_actor()
        self._build_bond_actor()
        self._build_polyhedron_actor()
        self._build_pie_actor()
        self._build_topology_actor()
        self._build_pore_actors()
        self._build_plane_actors()
        self._build_cell_actor()
        self._build_highlight_actors()
        self._build_ghost_actors()
        self._build_scale_bar()
        self._cue_on = False
        self._cue_strength = 0.7
        self._cue_start = 0.0
        self._cue_gradient = 1.0
        self._cue_observer = None
        # The line-drawn bonds' own colours, kept so the fade that
        # recolours them has something to fade *from*.
        self._line_colors = None
        self._line_middles = np.zeros((0, 3), np.float32)
        self._line_cue_state = None
        # The ORTEP furniture's own colours, kept for the same reason.
        self._octant_colors = None
        self._octant_points = np.zeros((0, 3), float)
        self._octant_cue_state = None
        self._bar_on = False
        self._bar_observer = None
        self._pies_on = False
        self._pie_observer = None
        self._pie_frame = None

    # -- actor construction --------------------------------------------

    def _build_atom_actor(self):
        sphere = vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(SPHERE_RESOLUTION)
        sphere.SetPhiResolution(SPHERE_RESOLUTION)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceConnection(sphere.GetOutputPort())
        mapper.SetInputData(self._atom_poly)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SetScaleArray("radii")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.SelectColorArray("colors")
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        self.atom_mapper = mapper
        self.atom_actor = vtkActor()
        self.atom_actor.SetMapper(mapper)
        self.atom_actor.GetProperty().SetSpecular(0.3)
        self.atom_actor.GetProperty().SetSpecularPower(30)
        self.renderer.AddActor(self.atom_actor)

    def _build_outline_actor(self):
        """The ink around every atom and bond: two more instanced
        glyphs, and no per-atom geometry anywhere.

        **An inverted hull.**  There is no per-atom mesh to run a
        silhouette filter over -- the whole picture is one glyph
        mapper instancing one sphere -- so the outline is the same
        glyph grown by the ink width, drawn in the ink colour with the
        *front* faces culled.  What is left is the inside of the back
        of a slightly larger atom, which the atom itself covers
        everywhere except the ring around its silhouette.  It costs
        one actor for the whole structure, it follows an ellipsoid's
        three scales and its rotation exactly as the atom does, and it
        occludes correctly against everything else in the scene
        because it is real geometry at a real depth.

        The bonds get the same treatment through their own tube: a
        wider tube behind a narrower one is the same trick, and
        without it a cartoon picture has outlined atoms floating on
        unoutlined sticks.
        """
        self._outline_poly = vtkPolyData()
        sphere = vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(SPHERE_RESOLUTION)
        sphere.SetPhiResolution(SPHERE_RESOLUTION)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceConnection(sphere.GetOutputPort())
        mapper.SetInputData(self._outline_poly)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SetScaleArray("radii")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.ScalarVisibilityOff()
        self.outline_mapper = mapper
        self.outline_actor = vtkActor()
        self.outline_actor.SetMapper(mapper)
        self._style_outline(self.outline_actor)
        self.renderer.AddActor(self.outline_actor)

        self._outline_bond_poly = vtkPolyData()
        self._outline_tube = vtkTubeFilter()
        self._outline_tube.SetInputData(self._outline_bond_poly)
        self._outline_tube.SetNumberOfSides(TUBE_SIDES)
        self._outline_tube.CappingOn()
        bond_mapper = vtkPolyDataMapper()
        bond_mapper.SetInputConnection(self._outline_tube.GetOutputPort())
        bond_mapper.ScalarVisibilityOff()
        self.outline_bond_actor = vtkActor()
        self.outline_bond_actor.SetMapper(bond_mapper)
        self._style_outline(self.outline_bond_actor)
        self.renderer.AddActor(self.outline_bond_actor)

    @staticmethod
    def _style_outline(actor):
        prop = actor.GetProperty()
        _flat(prop)                 # ink is ink, wherever the light is
        prop.FrontfaceCullingOn()
        prop.BackfaceCullingOff()
        actor.SetVisibility(False)

    def _build_octant_actor(self):
        """ORTEP's octant shading: a second glyph over the same atoms.

        The same scale and orientation arrays as the ellipsoids
        themselves, so the arcs land on the surface of every one of
        them without a single per-atom mesh -- and its own input
        polydata, because only the atoms whose orientation was
        measured are in it.  See
        :attr:`~xtalapp.viewport.scene.SceneModel.octant_atoms`.
        """
        self._octant_poly = vtkPolyData()
        self._octant_rows = np.zeros(0, int)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceData(_octant_source())
        mapper.SetInputData(self._octant_poly)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray("colors")
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        mapper.SetScaleArray("axes")
        mapper.SetScaleModeToScaleByVectorComponents()
        mapper.SetOrientationArray("quaternions")
        mapper.SetOrientationModeToQuaternion()
        mapper.OrientOn()
        self.octant_mapper = mapper
        self.octant_actor = vtkActor()
        self.octant_actor.SetMapper(mapper)
        prop = self.octant_actor.GetProperty()
        # Mostly ambient: an ORTEP figure is ink and the arcs have to
        # stay readable on the side of the ellipsoid facing away from
        # the light, where a diffuse-lit line goes to nothing.
        prop.SetAmbient(0.65)
        prop.SetDiffuse(0.35)
        prop.SetSpecular(0.0)
        prop.SetLineWidth(1.4)
        self.octant_actor.SetVisibility(False)
        self.renderer.AddActor(self.octant_actor)

    def _build_bond_actor(self):
        self._bond_poly = vtkPolyData()
        self._tube = vtkTubeFilter()
        self._tube.SetInputData(self._bond_poly)
        self._tube.SetNumberOfSides(TUBE_SIDES)
        self._tube.CappingOn()
        self.bond_mapper = vtkPolyDataMapper()
        self.bond_mapper.SetScalarModeToUseCellData()
        self.bond_mapper.SetColorModeToDirectScalars()
        self.bond_actor = vtkActor()
        self.bond_actor.SetMapper(self.bond_mapper)
        self.bond_actor.GetProperty().SetSpecular(0.2)
        self.renderer.AddActor(self.bond_actor)

        # The aromatic inner line: the same geometry pipeline at a
        # smaller radius, which is the only reason it cannot share the
        # actor above -- a tube filter has one radius for everything
        # it is given.
        self._dash_poly = vtkPolyData()
        self._dash_tube = vtkTubeFilter()
        self._dash_tube.SetInputData(self._dash_poly)
        self._dash_tube.SetNumberOfSides(TUBE_SIDES)
        self._dash_tube.CappingOn()
        self.dash_mapper = vtkPolyDataMapper()
        self.dash_mapper.SetScalarModeToUseCellData()
        self.dash_mapper.SetColorModeToDirectScalars()
        self.dash_mapper.SetInputConnection(
            self._dash_tube.GetOutputPort())
        self.dash_actor = vtkActor()
        self.dash_actor.SetMapper(self.dash_mapper)
        self.dash_actor.GetProperty().SetSpecular(0.2)
        self.dash_actor.SetVisibility(False)
        self.renderer.AddActor(self.dash_actor)

    def _build_polyhedron_actor(self):
        self._polyhedron_poly = vtkPolyData()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(self._polyhedron_poly)
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        self.polyhedron_mapper = mapper
        self.polyhedron_actor = vtkActor()
        self.polyhedron_actor.SetMapper(mapper)
        prop = self.polyhedron_actor.GetProperty()
        prop.SetSpecular(0.25)
        prop.SetSpecularPower(20)
        # Lit from both sides: a hull is a closed surface, but a
        # translucent one shows its inside faces and they must not read
        # as black holes in the polyhedron.
        prop.BackfaceCullingOff()
        self.renderer.AddActor(self.polyhedron_actor)

    def _build_pie_actor(self):
        """Occupancy pies: opaque triangles, and their own actor.

        Not the polyhedron actor, though the geometry is the same
        kind: a hull is translucent and a pie is the surface of an
        atom, and a pie that took the polyhedron opacity would show
        the sphere it is drawn to replace straight through itself.
        """
        self._pie_poly = vtkPolyData()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(self._pie_poly)
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        self.pie_mapper = mapper
        self.pie_actor = vtkActor()
        self.pie_actor.SetMapper(mapper)
        self.pie_actor.GetProperty().SetSpecular(0.3)
        self.pie_actor.GetProperty().SetSpecularPower(30)
        self.pie_actor.SetVisibility(False)
        self.renderer.AddActor(self.pie_actor)

    def _set_pies(self, model):
        """The wedges, and an observer to keep them facing the camera.

        A pie chart is only readable face on -- cut about a fixed
        crystallographic axis, the same 60/40 site reads as any split
        at all from most directions -- so the frame follows the camera
        the way the depth cue and the scale bar already do, from a
        render observer rather than from a rebuilt scene.
        """
        self._pies_on = bool(model.n_pie_faces)
        self._pie_frame = None
        if not self._pies_on:
            self.pie_actor.SetVisibility(False)
            self._watch_camera()
            return
        points, normals = model.pie_geometry(*self._camera_frame())
        self._pie_poly = _triangle_polydata(points, model.pie_faces,
                                            model.pie_colors)
        self._pie_poly.GetPointData().SetNormals(
            _to_float(normals, "normals"))
        self.pie_mapper.SetInputData(self._pie_poly)
        self.pie_actor.SetVisibility(True)
        self._watch_camera()
        self._refresh_pies()

    def _camera_frame(self):
        camera = self.renderer.GetActiveCamera()
        return (np.array(camera.GetDirectionOfProjection(), float),
                np.array(camera.GetViewUp(), float))

    def _refresh_pies(self) -> None:
        """Turn the pies onto the camera's axes, if it has moved.

        The guard is not an optimisation to be tidied away: this runs
        before every render, and a render happens while the camera is
        being dragged.
        """
        if not self._pies_on or self.model is None:
            return
        frame = self._camera_frame()
        if (self._pie_frame is not None
                and np.allclose(frame, self._pie_frame, atol=1e-9)):
            return
        self._pie_frame = frame
        points, normals = self.model.pie_geometry(*frame)
        self._pie_poly.SetPoints(_points(points))
        self._pie_poly.GetPointData().SetNormals(
            _to_float(normals, "normals"))
        self._pie_poly.Modified()

    def _build_topology_actor(self):
        """The net: its own actor, on purpose.

        Seeing the net and the chemistry that justifies it at the same
        time is the whole point of drawing it rather than printing it,
        so it needs its own radius, its own opacity and its own
        colour -- which is three reasons it cannot share the bond
        actor.
        """
        self._topology_poly = vtkPolyData()
        self._topology_tube = vtkTubeFilter()
        self._topology_tube.SetInputData(self._topology_poly)
        self._topology_tube.SetNumberOfSides(TUBE_SIDES)
        self._topology_tube.CappingOn()
        mapper = vtkPolyDataMapper()
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        mapper.SetInputConnection(self._topology_tube.GetOutputPort())
        self.topology_mapper = mapper
        self.topology_actor = vtkActor()
        self.topology_actor.SetMapper(mapper)
        self.topology_actor.GetProperty().SetSpecular(0.1)
        self.topology_actor.SetVisibility(False)
        self.renderer.AddActor(self.topology_actor)

    def _set_topology(self, model):
        if not model.n_topology_edges:
            self.topology_actor.SetVisibility(False)
            return
        colors = np.tile(model.topology_color,
                         (model.n_topology_edges, 1))
        # A selected edge is recoloured rather than haloed: the net is
        # already translucent and already one flat colour, so it has
        # nothing to lose by saying which edge is picked.
        if len(model.topology_selected):
            colors[np.asarray(model.topology_selected, bool)] = \
                HIGHLIGHT_COLOR
        self._topology_poly = _line_polydata(model.topology_starts,
                                             model.topology_ends,
                                             colors)
        self._topology_tube.SetInputData(self._topology_poly)
        self._topology_tube.SetRadius(float(model.topology_radius))
        self.topology_actor.GetProperty().SetOpacity(
            float(model.topology_opacity))
        self.topology_actor.SetVisibility(True)

    def _build_pore_actors(self):
        """Where the pores are: a glyphed sphere and a tube.

        Both borrowed wholesale -- the sphere mapper is the atom
        actor's and the tube is the net's -- because that is what a
        pore network is shaped like, and because borrowing means the
        SVG export already knows how to draw it.

        Their own actors all the same, for the reason the planes have
        theirs: a pore is an external program's *measurement* of the
        crystal, not part of it, and sharing an actor would put it
        under the atom style, the outline and the element colours,
        none of which it has any business following.

        ``BackfaceCullingOff`` on the sphere: it is translucent and
        the framework runs through the middle of it, so the inside of
        the far wall is part of the picture.
        """
        self._pore_poly = vtkPolyData()
        sphere = vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(SPHERE_RESOLUTION)
        sphere.SetPhiResolution(SPHERE_RESOLUTION)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceConnection(sphere.GetOutputPort())
        mapper.SetInputData(self._pore_poly)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SetScaleArray("radii")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.SelectColorArray("colors")
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        self.pore_mapper = mapper
        self.pore_actor = vtkActor()
        self.pore_actor.SetMapper(mapper)
        self.pore_actor.GetProperty().SetSpecular(0.2)
        self.pore_actor.GetProperty().SetSpecularPower(20)
        self.pore_actor.GetProperty().BackfaceCullingOff()
        self.pore_actor.SetVisibility(False)
        self.renderer.AddActor(self.pore_actor)

        self._pore_edge_poly = vtkPolyData()
        self._pore_edge_tube = vtkTubeFilter()
        self._pore_edge_tube.SetInputData(self._pore_edge_poly)
        self._pore_edge_tube.SetNumberOfSides(TUBE_SIDES)
        self._pore_edge_tube.CappingOn()
        edge_mapper = vtkPolyDataMapper()
        edge_mapper.SetScalarModeToUseCellData()
        edge_mapper.SetColorModeToDirectScalars()
        edge_mapper.SetInputConnection(
            self._pore_edge_tube.GetOutputPort())
        self.pore_edge_mapper = edge_mapper
        self.pore_edge_actor = vtkActor()
        self.pore_edge_actor.SetMapper(edge_mapper)
        self.pore_edge_actor.GetProperty().SetSpecular(0.1)
        self.pore_edge_actor.SetVisibility(False)
        self.renderer.AddActor(self.pore_edge_actor)

    def _set_pores(self, model):
        poly = vtkPolyData()
        if model.n_pore_spheres:
            poly.SetPoints(_points(model.pore_centres))
            poly.GetPointData().AddArray(
                _to_float(model.pore_radii, "radii"))
            poly.GetPointData().AddArray(
                _to_uchar(model.pore_colors, "colors"))
        self._pore_poly = poly
        self.pore_mapper.SetInputData(poly)
        self.pore_actor.GetProperty().SetOpacity(
            float(model.pore_opacity))
        self.pore_actor.SetVisibility(model.n_pore_spheres > 0)

        if not model.n_pore_edges:
            self.pore_edge_actor.SetVisibility(False)
            return
        self._pore_edge_poly = _line_polydata(model.pore_edge_starts,
                                              model.pore_edge_ends,
                                              model.pore_edge_colors)
        self._pore_edge_tube.SetInputData(self._pore_edge_poly)
        self._pore_edge_tube.SetRadius(float(model.pore_edge_radius))
        self.pore_edge_actor.GetProperty().SetOpacity(
            float(model.pore_opacity))
        self.pore_edge_actor.SetVisibility(True)

    def _build_plane_actors(self):
        """The planes the user defined, and their normals.

        Their own actors and not the polyhedron's, though the geometry
        is the same kind: a plane is a note about the crystal rather
        than part of it, and sharing an actor would mean a plane
        disappearing with the polyhedra and taking their opacity.  The
        normals are lines, because two nearly parallel planes have
        faces that look identical and normals that do not.
        """
        self._plane_poly = vtkPolyData()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(self._plane_poly)
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        self.plane_mapper = mapper
        self.plane_actor = vtkActor()
        self.plane_actor.SetMapper(mapper)
        prop = self.plane_actor.GetProperty()
        prop.SetSpecular(0.0)
        # A quad has one side facing the camera and one facing away,
        # and a plane has no front: culled backfaces would make it
        # vanish from half the orbit.
        prop.BackfaceCullingOff()
        prop.SetAmbient(0.4)
        prop.SetDiffuse(0.6)
        self.plane_actor.SetVisibility(False)
        self.renderer.AddActor(self.plane_actor)

        self._normal_poly = vtkPolyData()
        self.normal_mapper = vtkPolyDataMapper()
        self.normal_mapper.SetInputData(self._normal_poly)
        self.normal_mapper.SetScalarModeToUseCellData()
        self.normal_mapper.SetColorModeToDirectScalars()
        self.normal_actor = vtkActor()
        self.normal_actor.SetMapper(self.normal_mapper)
        self.normal_actor.GetProperty().SetLineWidth(2.0)
        self.normal_actor.GetProperty().SetLighting(False)
        self.normal_actor.SetVisibility(False)
        self.renderer.AddActor(self.normal_actor)

    def _set_planes(self, model):
        if not model.n_plane_faces:
            self.plane_actor.SetVisibility(False)
            self.normal_actor.SetVisibility(False)
            return
        self._plane_poly = _triangle_polydata(model.plane_points,
                                              model.plane_faces,
                                              model.plane_colors)
        self.plane_mapper.SetInputData(self._plane_poly)
        self.plane_actor.GetProperty().SetOpacity(
            float(model.plane_opacity))
        self.plane_actor.SetVisibility(True)

        self._normal_poly = _line_polydata(model.normal_starts,
                                           model.normal_ends,
                                           model.normal_colors)
        self.normal_mapper.SetInputData(self._normal_poly)
        self.normal_actor.SetVisibility(True)

    def _build_cell_actor(self):
        self._cell_poly = vtkPolyData()
        self.cell_mapper = vtkPolyDataMapper()
        self.cell_mapper.SetInputData(self._cell_poly)
        self.cell_mapper.SetScalarModeToUseCellData()
        self.cell_mapper.SetColorModeToDirectScalars()
        self.cell_actor = vtkActor()
        self.cell_actor.SetMapper(self.cell_mapper)
        self.cell_actor.GetProperty().SetLineWidth(2.0)
        self.cell_actor.GetProperty().SetLighting(False)
        self.renderer.AddActor(self.cell_actor)

    def _build_highlight_actors(self):
        self._halo_poly = vtkPolyData()
        sphere = vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(SPHERE_RESOLUTION)
        sphere.SetPhiResolution(SPHERE_RESOLUTION)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceConnection(sphere.GetOutputPort())
        mapper.SetInputData(self._halo_poly)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SetScaleArray("radii")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.ScalarVisibilityOff()
        self.halo_mapper = mapper
        self.halo_actor = vtkActor()
        self.halo_actor.SetMapper(mapper)
        self._style_highlight(self.halo_actor)
        self.renderer.AddActor(self.halo_actor)

        self._halo_bond_poly = vtkPolyData()
        self._halo_tube = vtkTubeFilter()
        self._halo_tube.SetInputData(self._halo_bond_poly)
        self._halo_tube.SetNumberOfSides(TUBE_SIDES)
        self._halo_tube.CappingOn()
        bond_mapper = vtkPolyDataMapper()
        bond_mapper.SetInputConnection(self._halo_tube.GetOutputPort())
        bond_mapper.ScalarVisibilityOff()
        self.halo_bond_actor = vtkActor()
        self.halo_bond_actor.SetMapper(bond_mapper)
        self._style_highlight(self.halo_bond_actor)
        self.renderer.AddActor(self.halo_bond_actor)

    def _build_ghost_actors(self):
        """The atom that is not there yet, and its bond.

        An overlay and not part of the model: one sphere and one tube,
        moved and shown as the cursor moves, so a ghost costs a
        transform rather than a rebuild of the scene.  Both start
        hidden, which is what every mode but Add atom leaves them.
        """
        sphere = vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(SPHERE_RESOLUTION)
        sphere.SetPhiResolution(SPHERE_RESOLUTION)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())
        mapper.ScalarVisibilityOff()
        self.ghost_actor = vtkActor()
        self.ghost_actor.SetMapper(mapper)
        self.ghost_actor.GetProperty().SetOpacity(GHOST_OPACITY)
        self.ghost_actor.SetVisibility(False)
        self.renderer.AddActor(self.ghost_actor)

        self._ghost_bond_poly = vtkPolyData()
        self._ghost_tube = vtkTubeFilter()
        self._ghost_tube.SetInputData(self._ghost_bond_poly)
        self._ghost_tube.SetNumberOfSides(TUBE_SIDES)
        self._ghost_tube.CappingOn()
        bond_mapper = vtkPolyDataMapper()
        bond_mapper.SetInputConnection(self._ghost_tube.GetOutputPort())
        bond_mapper.ScalarVisibilityOff()
        self.ghost_bond_actor = vtkActor()
        self.ghost_bond_actor.SetMapper(bond_mapper)
        self.ghost_bond_actor.GetProperty().SetOpacity(GHOST_OPACITY)
        self.ghost_bond_actor.SetVisibility(False)
        self.renderer.AddActor(self.ghost_bond_actor)

    def set_ghost(self, ghost) -> None:
        """Show the atom a click would place now, or ``None`` to stop
        showing one."""
        if ghost is None:
            self.ghost_actor.SetVisibility(False)
            self.ghost_bond_actor.SetVisibility(False)
            return
        position = np.asarray(ghost.position, dtype=float)
        colour = [c / 255 for c in ghost.color]
        self.ghost_actor.SetPosition(*position)
        self.ghost_actor.SetScale(float(ghost.radius))
        self.ghost_actor.GetProperty().SetColor(*colour)
        self.ghost_actor.SetVisibility(True)

        if ghost.anchor is None:
            self.ghost_bond_actor.SetVisibility(False)
            return
        anchor = np.asarray(ghost.anchor, dtype=float)
        self._ghost_bond_poly = _line_polydata(
            anchor.reshape(1, 3), position.reshape(1, 3),
            np.asarray(ghost.color, dtype=np.uint8).reshape(1, 3))
        self._ghost_tube.SetInputData(self._ghost_bond_poly)
        self._ghost_tube.SetRadius(float(ghost.bond_radius))
        self.ghost_bond_actor.GetProperty().SetColor(*colour)
        self.ghost_bond_actor.SetVisibility(True)

    @staticmethod
    def _style_highlight(actor):
        prop = actor.GetProperty()
        prop.SetColor(*[c / 255 for c in HIGHLIGHT_COLOR])
        prop.SetOpacity(HIGHLIGHT_OPACITY)
        prop.SetAmbient(0.5)
        prop.SetDiffuse(0.5)
        prop.SetSpecular(0.0)
        actor.SetVisibility(False)

    # -- updating ------------------------------------------------------

    def set_model(self, model) -> None:
        """Rebuild every actor from a new scene model."""
        self.model = model
        r, g, b = model.background
        self.renderer.SetBackground(r / 255, g / 255, b / 255)

        self._set_atoms(model)
        self._set_outline(model)
        self._set_octants(model)
        self._set_bonds(model)
        self._set_polyhedra(model)
        self._set_pies(model)
        self._set_topology(model)
        self._set_pores(model)
        self._set_planes(model)
        self._set_cell(model)
        self._set_labels(model)
        self._set_legend(model)
        self._set_highlight(model)
        self.set_depth_cue(model.depth_cue, model.depth_cue_strength,
                           model.depth_cue_start,
                           model.depth_cue_gradient)
        self.set_scale_bar(model.scale_bar)

    def set_positions(self, model) -> None:
        """Move what is already drawn instead of rebuilding it.

        A geometry change leaves the topology alone: the same atoms,
        the same colours and radii, joined by the same bonds.  So the
        actors, the mappers and the glyph sources all stand, and only
        the coordinates underneath them are replaced -- which is what
        makes watching a relaxation on a large cell affordable.

        **The cell is one of the things that move.**  A variable-cell
        relaxation changes the lattice, and the box has the same
        twelve lines per cell before and after -- so ``_same_shape``
        says nothing has changed shape and this path is taken, and for
        a long time the atoms then contracted inside a box that was
        still the old one.  The frame is rebuilt here alongside the
        atoms; it is ninety-six lines at the most, which is nothing
        beside the geometry it stands around, and without it the scale
        bar would be measuring against a lie.

        Falls back to a full rebuild when the arrays no longer have the
        same shape, because then the caller was wrong about what
        changed and the honest answer is to rebuild.
        """
        if self.model is None or not self._same_shape(model):
            self.set_model(model)
            return
        self.model = model
        if model.n_atoms:
            self._atom_poly.SetPoints(_points(model.positions))
            self._atom_poly.Modified()
        if model.is_outlined and model.n_atoms:
            self._outline_poly.SetPoints(_points(model.positions))
            self._outline_poly.Modified()
        if len(self._octant_rows):
            self._octant_points = np.asarray(
                model.positions[self._octant_rows], float)
            self._octant_poly.SetPoints(_points(self._octant_points))
            self._octant_poly.Modified()
            self._octant_cue_state = None
        if model.n_bond_halves:
            solid, dashed = split_by_order(model)
            self._bond_poly.SetPoints(
                _points(_interleave(solid[0], solid[1])))
            self._bond_poly.Modified()
            if self._line_colors is not None:
                # The bonds moved, so the distances the fade is a
                # function of did too.
                self._line_middles = 0.5 * (np.asarray(solid[0], float)
                                            + np.asarray(solid[1], float))
                self._line_cue_state = None
            if self.outline_bond_actor.GetVisibility():
                self._outline_bond_poly.SetPoints(
                    _points(_interleave(solid[0], solid[1])))
                self._outline_bond_poly.Modified()
            if len(dashed[0]):
                self._dash_poly.SetPoints(
                    _points(_interleave(dashed[0], dashed[1])))
                self._dash_poly.Modified()
        if model.n_polyhedron_faces:
            self._polyhedron_poly.SetPoints(
                _points(model.polyhedron_points))
            self._polyhedron_poly.Modified()
        if model.n_pie_faces:
            # The centres moved, and the camera did not -- so the
            # frame cache has to be dropped or the refresh below
            # decides there is nothing to do.
            self._pie_frame = None
            self._refresh_pies()
        if model.n_topology_edges:
            self._topology_poly.SetPoints(
                _points(_interleave(model.topology_starts,
                                    model.topology_ends)))
            self._topology_poly.Modified()
        if model.n_plane_faces:
            self._plane_poly.SetPoints(_points(model.plane_points))
            self._plane_poly.Modified()
            self._normal_poly.SetPoints(
                _points(_interleave(model.normal_starts,
                                    model.normal_ends)))
            self._normal_poly.Modified()
        self._set_cell(model)
        # These two are placed *at* atoms, so they move with them.
        self._set_highlight(model)
        self._set_labels(model)

    def _same_shape(self, model) -> bool:
        """Does this model draw the same things as the current one?"""
        current = self.model
        return (model.n_atoms == current.n_atoms
                and model.draws_ellipsoids == current.draws_ellipsoids
                and model.ellipsoid_octants == current.ellipsoid_octants
                and model.n_bond_halves == current.n_bond_halves
                and np.array_equal(model.bond_orders,
                                   current.bond_orders)
                and model.bond_render == current.bond_render
                and model.shading == current.shading
                and model.outline == current.outline
                and model.n_polyhedron_faces
                == current.n_polyhedron_faces
                and len(model.polyhedron_points)
                == len(current.polyhedron_points)
                and model.n_pie_faces == current.n_pie_faces
                and len(model.pie_local) == len(current.pie_local)
                and model.n_cell_lines == current.n_cell_lines
                and model.n_topology_edges == current.n_topology_edges
                and model.n_plane_faces == current.n_plane_faces
                and model.n_planes == current.n_planes
                and model.scale_bar == current.scale_bar
                and model.background == current.background)

    def _set_atoms(self, model):
        """Spheres, or ellipsoids when the model carries tensors.

        The same mapper and the same actor either way: an ellipsoid is
        a sphere with three scales and a rotation, and
        :class:`vtkGlyph3DMapper` will take both as per-point arrays.
        """
        poly = vtkPolyData()
        if model.n_atoms:
            poly.SetPoints(_points(model.positions))
            poly.GetPointData().AddArray(_to_float(model.radii, "radii"))
            poly.GetPointData().AddArray(_to_uchar(model.colors,
                                                   "colors"))
            if model.draws_ellipsoids:
                axes, quaternions = _decompose(model.atom_tensors)
                # Kept for the octant glyph, which needs the same two
                # arrays over a subset of the same atoms.  One SVD per
                # picture rather than two.
                self._axes, self._quaternions = axes, quaternions
                poly.GetPointData().AddArray(_to_float(axes, "axes"))
                poly.GetPointData().AddArray(
                    _to_float(quaternions, "quaternions"))
        self._atom_poly = poly
        self._set_glyph_shape(model)
        self.atom_mapper.SetInputData(poly)
        self._apply_shading(self.atom_actor, model.shading, 0.3)
        self.atom_actor.SetVisibility(model.n_atoms > 0)

    def _set_glyph_shape(self, model):
        mapper = self.atom_mapper
        if model.draws_ellipsoids and model.n_atoms:
            mapper.SetScaleArray("axes")
            mapper.SetScaleModeToScaleByVectorComponents()
            mapper.SetOrientationArray("quaternions")
            mapper.SetOrientationModeToQuaternion()
            mapper.OrientOn()
        else:
            mapper.SetScaleArray("radii")
            mapper.SetScaleModeToScaleByMagnitude()
            mapper.OrientOff()

    def _set_octants(self, model):
        """The arcs and the shaded octants, over the anisotropic atoms.

        Nothing here is geometry of its own: the points are the atoms
        already drawn, and the shape comes from the glyph source built
        once in :func:`_octant_source`.
        """
        rows = model.octant_atoms
        self._octant_rows = rows
        self._octant_cue_state = None
        if not len(rows):
            self.octant_actor.SetVisibility(False)
            self._octant_colors = None
            return
        poly = vtkPolyData()
        poly.SetPoints(_points(model.positions[rows]))
        data = poly.GetPointData()
        data.AddArray(_to_float(self._axes[rows], "axes"))
        data.AddArray(_to_float(self._quaternions[rows],
                                "quaternions"))
        # Kept, like the line-drawn bonds' colours, because this
        # actor's fade is a recolour rather than a shader.
        self._octant_colors = _darken(model.colors[rows], OCTANT_DARKEN)
        self._octant_points = np.asarray(model.positions[rows], float)
        data.AddArray(_to_uchar(self._octant_colors, "colors"))
        self._octant_poly = poly
        self.octant_mapper.SetInputData(poly)
        self.octant_actor.SetVisibility(True)

    def _set_outline(self, model):
        """The ink glyphs, grown by the style's outline width.

        Called after :meth:`_set_atoms`, which is where ``_axes`` and
        ``_quaternions`` are decomposed: an outlined ellipsoid is the
        same transform as the ellipsoid, scaled, and doing the SVD
        twice for one picture would be the only expensive thing here.
        """
        if not model.is_outlined:
            self.outline_actor.SetVisibility(False)
            self.outline_bond_actor.SetVisibility(False)
            return
        grow = 1.0 + float(model.outline)
        ink = [c / 255 for c in model.outline_color]
        poly = vtkPolyData()
        if model.n_atoms:
            poly.SetPoints(_points(model.positions))
            poly.GetPointData().AddArray(
                _to_float(np.asarray(model.radii, np.float32) * grow,
                          "radii"))
        mapper = self.outline_mapper
        if model.draws_ellipsoids and model.n_atoms:
            poly.GetPointData().AddArray(
                _to_float(self._axes * grow, "axes"))
            poly.GetPointData().AddArray(
                _to_float(self._quaternions, "quaternions"))
            mapper.SetScaleArray("axes")
            mapper.SetScaleModeToScaleByVectorComponents()
            mapper.SetOrientationArray("quaternions")
            mapper.SetOrientationModeToQuaternion()
            mapper.OrientOn()
        else:
            mapper.SetScaleArray("radii")
            mapper.SetScaleModeToScaleByMagnitude()
            mapper.OrientOff()
        self._outline_poly = poly
        mapper.SetInputData(poly)
        self.outline_actor.GetProperty().SetColor(*ink)
        self.outline_actor.SetVisibility(model.n_atoms > 0)

        # Lines have no surface to grow, so a wireframe picture is
        # outlined at its atoms and nowhere else -- which is the whole
        # of what a wireframe draws anyway.
        tubes = bool(model.n_bond_halves) and model.bond_render != "line"
        if tubes:
            solid, _dashed = split_by_order(model)
            self._outline_bond_poly = _line_polydata(*solid)
            self._outline_tube.SetInputData(self._outline_bond_poly)
            self._outline_tube.SetRadius(model.bond_radius * grow)
            self.outline_bond_actor.GetProperty().SetColor(*ink)
        self.outline_bond_actor.SetVisibility(tubes)

    @staticmethod
    def _apply_shading(actor, shading: str, specular: float) -> None:
        """The material ``shading`` names, on one actor.

        ``specular`` is the highlight that actor is drawn with when a
        style asks for nothing, and is the actor's own: bonds have
        always carried less of one than atoms.
        """
        prop = actor.GetProperty()
        if shading == "flat":
            _flat(prop)
        elif shading == "matte":
            prop.SetAmbient(MATTE_AMBIENT)
            prop.SetDiffuse(MATTE_DIFFUSE)
            prop.SetSpecular(0.0)
        else:
            prop.SetAmbient(0.0)
            prop.SetDiffuse(1.0)
            prop.SetSpecular(specular)

    def _set_bonds(self, model):
        """One line per tube: a double bond arrives here as two.

        The split is :func:`~xtalapp.viewport.scene.split_by_order`,
        which is plain arithmetic over the scene model and is tested
        without a render window.
        """
        if not model.n_bond_halves:
            self.bond_actor.SetVisibility(False)
            self.dash_actor.SetVisibility(False)
            self._line_colors = None
            return
        solid, dashed = split_by_order(model)
        poly = _line_polydata(*solid)
        self._bond_poly = poly
        # Kept only for the style that draws lines, which is the one
        # whose fade is a recolour rather than a shader.
        if model.bond_render == "line":
            self._line_colors = np.asarray(solid[2], np.uint8)
            self._line_middles = 0.5 * (np.asarray(solid[0], float)
                                        + np.asarray(solid[1], float))
        else:
            self._line_colors = None
        self._line_cue_state = None
        self._apply_shading(self.bond_actor, model.shading, 0.2)
        self._apply_shading(self.dash_actor, model.shading, 0.2)
        if model.bond_render == "line":
            self.bond_mapper.SetInputData(poly)
            self.bond_actor.GetProperty().SetLineWidth(2.0)
            # A line has no surface to light, whatever the style asks.
            _flat(self.bond_actor.GetProperty())
        else:
            self._tube.SetInputData(poly)
            self._tube.SetRadius(model.bond_radius)
            self.bond_mapper.SetInputConnection(self._tube.GetOutputPort())
        self.bond_actor.SetVisibility(True)

        if len(dashed[0]):
            self._dash_poly = _line_polydata(*dashed)
            self._dash_tube.SetInputData(self._dash_poly)
            self._dash_tube.SetRadius(model.bond_radius * DASH_RADIUS)
            self.dash_mapper.SetInputConnection(
                self._dash_tube.GetOutputPort())
        self.dash_actor.SetVisibility(bool(len(dashed[0])))

    def _set_polyhedra(self, model):
        if not model.n_polyhedron_faces:
            self.polyhedron_actor.SetVisibility(False)
            return
        poly = _triangle_polydata(model.polyhedron_points,
                                   model.polyhedron_faces,
                                   model.polyhedron_colors)
        self._polyhedron_poly = poly
        self.polyhedron_mapper.SetInputData(poly)
        self.polyhedron_actor.GetProperty().SetOpacity(
            float(model.polyhedron_opacity))
        self.polyhedron_actor.SetVisibility(True)

    def _set_cell(self, model):
        if not model.n_cell_lines:
            self.cell_actor.SetVisibility(False)
            return
        self._cell_poly = _line_polydata(model.cell_starts,
                                         model.cell_ends,
                                         model.cell_colors)
        self.cell_mapper.SetInputData(self._cell_poly)
        self.cell_actor.SetVisibility(True)

    def set_selection(self, selected, selected_bonds,
                      selected_topology=None) -> None:
        """Change only what is highlighted.

        Selecting an atom changes no geometry, so the halo actors are
        the only thing that has to be rebuilt -- and on a big structure
        that is the difference between a click that lands immediately
        and one that hangs on a full scene rebuild.
        """
        if self.model is None:
            return
        if selected_topology is None:
            selected_topology = self.model.topology_selected
        self.model = replace(self.model, selected=selected,
                             selected_bonds=selected_bonds,
                             topology_selected=selected_topology)
        self._set_highlight(self.model)
        self._set_topology(self.model)

    def _set_highlight(self, model):
        picked = (model.selected if len(model.selected)
                  else np.zeros(model.n_atoms, bool))
        indices = np.flatnonzero(picked)
        poly = vtkPolyData()
        if len(indices):
            poly.SetPoints(_points(model.positions[indices]))
            poly.GetPointData().AddArray(_to_float(
                model.radii[indices] * HIGHLIGHT_GROWTH, "radii"))
        self._halo_poly = poly
        self.halo_mapper.SetInputData(poly)
        self.halo_actor.SetVisibility(len(indices) > 0)

        bonds = (model.selected_bonds if len(model.selected_bonds)
                 else np.zeros(model.n_bond_halves, bool))
        chosen = np.flatnonzero(bonds)
        if len(chosen):
            self._halo_bond_poly = _line_polydata(
                model.bond_starts[chosen], model.bond_ends[chosen],
                np.tile(HIGHLIGHT_COLOR, (len(chosen), 1)))
            self._halo_tube.SetInputData(self._halo_bond_poly)
            self._halo_tube.SetRadius(model.bond_radius
                                      * HIGHLIGHT_GROWTH
                                      * HIGHLIGHT_BOND_GROWTH)
        self.halo_bond_actor.SetVisibility(len(chosen) > 0)

    def _set_labels(self, model):
        for actor in self._label_actors:
            self.renderer.RemoveActor(actor)
        self._label_actors = []
        for position, text in model.labels[:MAX_LABELS]:
            actor = vtkBillboardTextActor3D()
            actor.SetPosition(*[float(v) for v in position])
            actor.SetInput(str(text))
            prop = actor.GetTextProperty()
            prop.SetFontSize(14)
            lum = sum(model.background) / 3
            prop.SetColor((0, 0, 0) if lum > 128 else (1, 1, 1))
            self.renderer.AddActor(actor)
            self._label_actors.append(actor)

    def _set_legend(self, model):
        """Element swatches down the right-hand edge.

        Drawn as a coloured square plus a label rather than with
        vtkLegendBoxActor, which sizes its text from the box and gives
        the label the entry's colour -- so a legend for a pale element
        comes out unreadable on a pale background, which is exactly
        when a legend is wanted.
        """
        for actor in self._legend_actors:
            self.renderer.RemoveActor(actor)
        self._legend_actors = []
        if not model.legend:
            return

        light = sum(model.background) / 3 > 128
        text_color = (0.0, 0.0, 0.0) if light else (1.0, 1.0, 1.0)
        top = LEGEND_TOP
        for row, (element, color) in enumerate(model.legend):
            y = top - row * LEGEND_ROW
            if y < LEGEND_ROW:
                break                   # ran out of window
            self._legend_actors.append(
                _swatch(LEGEND_X, y, [c / 255 for c in color]))
            label = vtkTextActor()
            label.SetInput(str(element))
            label.GetPositionCoordinate() \
                .SetCoordinateSystemToNormalizedViewport()
            label.GetPositionCoordinate().SetValue(
                LEGEND_X + LEGEND_SWATCH * 1.6, y - LEGEND_SWATCH / 3)
            prop = label.GetTextProperty()
            prop.SetFontSize(LEGEND_FONT)
            prop.SetColor(*text_color)
            prop.SetJustificationToLeft()
            self._legend_actors.append(label)
        for actor in self._legend_actors:
            self.renderer.AddActor(actor)

    # -- the scale bar -------------------------------------------------

    def _build_scale_bar(self):
        """A ruler in the corner: a capped line and a number.

        Two 2-D actors in normalized viewport coordinates, so nothing
        about the bar is in the scene and nothing in the scene has to
        know about it.  Its geometry is rewritten in place by
        :meth:`_refresh_scale_bar`.
        """
        self._bar_poly = vtkPolyData()
        lines = vtkCellArray()
        lines.SetData(
            numpy_to_vtkIdTypeArray(
                np.arange(0, 7, 2, dtype=ID_TYPE), deep=True),
            numpy_to_vtkIdTypeArray(
                np.arange(6, dtype=ID_TYPE), deep=True))
        self._bar_poly.SetLines(lines)
        mapper = vtkPolyDataMapper2D()
        mapper.SetInputData(self._bar_poly)
        coordinate = vtkCoordinate()
        coordinate.SetCoordinateSystemToNormalizedViewport()
        mapper.SetTransformCoordinate(coordinate)
        self.bar_actor = vtkActor2D()
        self.bar_actor.SetMapper(mapper)
        self.bar_actor.GetProperty().SetLineWidth(2.0)
        self.bar_actor.SetVisibility(False)
        self.renderer.AddActor(self.bar_actor)

        self.bar_label = vtkTextActor()
        self.bar_label.GetPositionCoordinate() \
            .SetCoordinateSystemToNormalizedViewport()
        self.bar_label.GetTextProperty().SetFontSize(BAR_FONT)
        self.bar_label.GetTextProperty().SetJustificationToCentered()
        self.bar_label.SetVisibility(False)
        self.renderer.AddActor(self.bar_label)

    def set_scale_bar(self, enabled: bool) -> None:
        self._bar_on = bool(enabled)
        self.bar_actor.SetVisibility(self._bar_on)
        self.bar_label.SetVisibility(self._bar_on)
        self._watch_camera()
        self._refresh_scale_bar()

    def _refresh_scale_bar(self) -> None:
        """Put the bar where the current camera says it belongs.

        The length in Angstrom is worked out from the camera and from
        nothing else, and that is what makes the bar honest during a
        variable-cell relaxation.  A ruler taken from the *structure's*
        size would shrink with the cell it was there to measure, and
        the picture would show a box and a ruler contracting together
        -- which is a picture of nothing happening.  The camera does
        not move while a run steps the atoms, so this recomputes the
        same number every frame and the bar stands still while the box
        moves against it.

        Rounded to 1, 2 or 5 per decade, because the reader's job is
        to count the bar off against the picture and 3.7 A is not a
        length anybody counts in.
        """
        if not self._bar_on:
            return
        width, height = (int(v) for v in self.renderer.GetSize())
        if width <= 0 or height <= 0:               # never shown yet
            return
        span = self._world_width(width, height)
        if span <= 0:                               # pragma: no cover
            return
        length = _nice_length(span * BAR_TARGET)
        fraction = length / span
        right = BAR_X + fraction
        # the bar, then a cap at each end
        self._bar_poly.SetPoints(_points(np.array([
            [BAR_X, BAR_Y, 0.0], [right, BAR_Y, 0.0],
            [BAR_X, BAR_Y - BAR_TICK, 0.0],
            [BAR_X, BAR_Y + BAR_TICK, 0.0],
            [right, BAR_Y - BAR_TICK, 0.0],
            [right, BAR_Y + BAR_TICK, 0.0]])))
        self._bar_poly.Modified()
        self.bar_label.SetInput(f"{length:g} A")
        self.bar_label.GetPositionCoordinate().SetValue(
            (BAR_X + right) / 2.0, BAR_Y + BAR_TICK * 1.6)
        ink = ((0.0, 0.0, 0.0) if self.model is None
               or sum(self.model.background) / 3 > 128
               else (1.0, 1.0, 1.0))
        self.bar_actor.GetProperty().SetColor(*ink)
        self.bar_label.GetTextProperty().SetColor(*ink)

    def _world_width(self, width: int, height: int) -> float:
        """How many Angstrom the window is across, at the focal plane.

        In parallel projection that is exact everywhere.  In
        perspective it is only true at the depth the camera is focused
        on, and a scale bar in a perspective view is approximate by
        construction -- which is an argument for drawing it in
        orthographic when the number matters, not for refusing to draw
        it.
        """
        camera = self.renderer.GetActiveCamera()
        if camera.GetParallelProjection():
            tall = 2.0 * camera.GetParallelScale()
        else:
            half = np.radians(camera.GetViewAngle()) / 2.0
            tall = 2.0 * camera.GetDistance() * np.tan(half)
        return float(tall) * width / max(height, 1)

    # -- depth cueing --------------------------------------------------

    def set_depth_cue(self, enabled: bool, strength: float = 0.7,
                      start: float = 0.0,
                      gradient: float = 1.0) -> None:
        """Fade the structure towards the background with distance.

        Applied to the atoms, the bonds and the polyhedra, and
        deliberately not to the unit cell or to the selection halo:
        the cell box is the frame the reader measures against and the
        halo is the answer to "what did I just click", and neither is
        improved by being harder to see at the back.

        ``strength`` is how far the back of the picture goes towards
        the background, ``start`` where along the scene's own depth
        the fade begins, and ``gradient`` the exponent on the ramp
        between them.  All three are held here rather than read back
        off the model, because the camera observer refreshes the fade
        long after the model was set.
        """
        self._cue_on = bool(enabled)
        self._cue_strength = float(max(0.0, min(1.0, strength)))
        self._cue_start = float(max(0.0, min(CUE_START_MAX, start)))
        self._cue_gradient = float(max(CUE_GRADIENT_MIN,
                                       min(CUE_GRADIENT_MAX, gradient)))
        shaded = self._cued_actors()
        # Cleared on every actor and added back only to those, because
        # the bond actor moves in and out of that set as the style
        # changes and a replacement left on it would be the same blank
        # picture one style later.
        for actor in self._cueable_actors():
            shader = actor.GetShaderProperty()
            shader.ClearFragmentShaderReplacement("//VTK::Light::Impl",
                                                  True)
            if self._cue_on and actor in shaded:
                shader.AddFragmentShaderReplacement(
                    "//VTK::Light::Impl", True, DEPTH_CUE_SHADER, False)
            uniforms = shader.GetFragmentCustomUniforms()
            uniforms.SetUniformf("cueStrength", self._cue_strength)
            uniforms.SetUniformf("cueGradient", self._cue_gradient)
        self._watch_camera()
        self._refresh_cue()

    def _cued_actors(self):
        """The actors the fade is a shader on.

        **Nothing that draws lines is.**  A line has no surface to
        light, so VTK declares no view-space position in its fragment
        shader -- and with a wide line, which goes through a geometry
        shader, it renames the one it would have declared as well.
        Either way the replacement above does not compile and the
        primitive silently draws nothing at all.  That is what
        happened to the wireframe style for as long as the fade has
        existed, and to ORTEP's principal sections: on CFA1 with the
        fade on, every arc vanished and the terminal filled with
        ``Use of undeclared identifier 'vertexVCGSOutput'``.

        So the bond actor is here only while it draws tubes, and the
        octant actor -- whose source is arcs and shaded octants
        together -- never is.  Both are faded by colour instead, on
        the CPU, in :meth:`_refresh_line_cue` and
        :meth:`_refresh_octant_cue`.
        """
        return tuple(
            a for a in self._cueable_actors()
            if a is not self.octant_actor
            and (a is not self.bond_actor or not self._draws_lines()))

    def _cueable_actors(self):
        return (self.atom_actor, self.octant_actor, self.bond_actor,
                self.dash_actor, self.polyhedron_actor, self.pie_actor,
                self.outline_actor, self.outline_bond_actor)

    def _draws_lines(self) -> bool:
        return (self.model is not None
                and self.model.bond_render == "line"
                and bool(self.model.n_bond_halves))

    def _watch_camera(self) -> None:
        """Keep the near and far distances, and the scale bar, up to
        date as the camera moves.

        The alternative -- fixing them when the scene is built -- makes
        the fade slide off the structure the moment anybody zooms,
        which is the first thing anybody does, and leaves the bar
        claiming a length the picture no longer has.

        One observer each, added only while its feature is on: an
        observer on every render is a Python call on every frame, and
        the scene draws during camera drags.
        """
        for on, name, refresh in (
                (self._cue_on, "_cue_observer", self._refresh_cue),
                (self._bar_on, "_bar_observer", self._refresh_scale_bar),
                (self._pies_on, "_pie_observer", self._refresh_pies)):
            observer = getattr(self, name)
            if on and observer is None:
                setattr(self, name, self.renderer.AddObserver(
                    "StartEvent", lambda *_a, f=refresh: f()))
            elif not on and observer is not None:
                self.renderer.RemoveObserver(observer)
                setattr(self, name, None)

    def _refresh_cue(self) -> None:
        """Both halves of the fade: the uniforms the shader reads,
        and the colours of the actor that has no shader."""
        self._refresh_depth_cue()
        self._refresh_line_cue()
        self._refresh_octant_cue()

    def _refresh_depth_cue(self) -> None:
        """Near and far, from the scene's own extent along the view
        direction."""
        if not self._cue_on or self.model is None:
            return
        near, far = self._cue_range()
        background = np.array(self.model.background, dtype=float) / 255
        for actor in self._cued_actors():
            uniforms = actor.GetShaderProperty() \
                .GetFragmentCustomUniforms()
            uniforms.SetUniformf("cueNear", near)
            uniforms.SetUniformf("cueFar", far)
            uniforms.SetUniform3f("cueColor",
                                  [float(c) for c in background])

    def _cue_range(self) -> tuple[float, float]:
        """Where the fade begins and where it is complete.

        The start control is spent here rather than in the shader: it
        is a fraction of the scene's own depth, and moving the near
        distance back by that much *is* "the fade begins here" -- the
        clamp in front of it already leaves everything nearer
        untouched.
        """
        near, far = self._depth_range()
        return near + (far - near) * self._cue_start, far

    def _cue_recolour(self, colors, points, previous):
        """``(colors, state)`` for a fade done on the CPU, or ``None``
        when what is drawn already shows it.

        ``points`` is one position per colour -- a bond's midpoint, an
        ellipsoid's centre -- and the fade is that point's distance
        along the view direction, which is the granularity a colour
        array gives and is enough for a fade.

        Guarded on where the camera is, like :meth:`_refresh_pies` and
        for the same reason: this runs before every render, including
        every frame of a drag, and a wireframe of a supercell is a lot
        of segments to recolour for a camera that has not moved.
        """
        if not self._cue_on or self.model is None:
            # Its own colours, once, and then nothing to do.
            return None if previous is None else (colors, None)
        eye, direction = self._eye_and_direction()
        near, far = self._cue_range()
        state = (eye, direction, near, far, self._cue_strength,
                 self._cue_gradient)
        if (previous is not None
                and all(np.allclose(a, b, atol=1e-9) for a, b
                        in zip(state, previous, strict=True))):
            return None
        faded = scene_model.fade_towards(
            colors, self.model.background,
            scene_model.cue_fraction(
                (np.asarray(points, float) - eye) @ direction,
                near, far, self._cue_strength, self._cue_gradient))
        return faded, state

    def _refresh_line_cue(self) -> None:
        """Fade the line-drawn bonds by recolouring them.

        One of the two actors a shader cannot reach -- see
        :meth:`_cued_actors`.
        """
        if self._line_colors is None:
            return
        faded = self._cue_recolour(self._line_colors, self._line_middles,
                                   self._line_cue_state)
        if faded is None:
            return
        colors, self._line_cue_state = faded
        self._bond_poly.GetCellData().SetScalars(
            _to_uchar(colors, "colors"))
        self._bond_poly.Modified()

    def _refresh_octant_cue(self) -> None:
        """Fade ORTEP's furniture by recolouring it.

        The other one, and it is the whole actor rather than half of
        it: the arcs and the shaded octants are one glyph source, so
        the shading follows the sections that forced the recolour.
        One colour per atom, which on furniture drawn the width of an
        ellipsoid is as fine as it needs to be.
        """
        if self._octant_colors is None:
            return
        faded = self._cue_recolour(self._octant_colors,
                                   self._octant_points,
                                   self._octant_cue_state)
        if faded is None:
            return
        colors, self._octant_cue_state = faded
        self._octant_poly.GetPointData().AddArray(
            _to_uchar(colors, "colors"))
        self._octant_poly.Modified()

    def _eye_and_direction(self):
        camera = self.renderer.GetActiveCamera()
        return (np.array(camera.GetPosition(), dtype=float),
                np.array(camera.GetDirectionOfProjection(), dtype=float))

    def _depth_range(self) -> tuple[float, float]:
        low, high = self.model.bounds()
        corners = np.array(
            [[[low[0], high[0]][(k >> 2) & 1],
              [low[1], high[1]][(k >> 1) & 1],
              [low[2], high[2]][k & 1]] for k in range(8)],
            dtype=float)
        eye, direction = self._eye_and_direction()
        along = (corners - eye) @ direction
        near, far = float(along.min()), float(along.max())
        if far - near < 1e-6:               # a flat scene, or one atom
            far = near + 1.0
        return near, far

    # -- camera --------------------------------------------------------

    def reset_camera(self) -> None:
        self.renderer.ResetCamera()

    def set_projection(self, projection: str) -> None:
        self.renderer.GetActiveCamera().SetParallelProjection(
            projection == "orthographic")

    def look_along(self, direction, up=None) -> None:
        """Point the camera along a cartesian direction."""
        direction = np.asarray(direction, dtype=float)
        norm = np.linalg.norm(direction)
        if norm < 1e-9:
            return
        direction = direction / norm
        camera = self.renderer.GetActiveCamera()
        focal = np.array(camera.GetFocalPoint())
        distance = camera.GetDistance() or 10.0
        camera.SetPosition(*(focal - direction * distance))
        if up is None:
            trial = np.array([0.0, 0.0, 1.0])
            if abs(np.dot(trial, direction)) > 0.9:
                trial = np.array([0.0, 1.0, 0.0])
            up = np.cross(direction, np.cross(trial, direction))
        camera.SetViewUp(*np.asarray(up, dtype=float))
        self.renderer.ResetCameraClippingRange()


def orientation_marker(interactor) -> vtkOrientationMarkerWidget:
    """The little axes gizmo in the corner."""
    axes = vtkAxesActor()
    widget = vtkOrientationMarkerWidget()
    widget.SetOrientationMarker(axes)
    widget.SetInteractor(interactor)
    widget.SetViewport(0.0, 0.0, 0.16, 0.22)
    widget.SetEnabled(1)
    widget.InteractiveOff()
    return widget


#: The raster writers, by the suffix the export dialog offers.  They
#: are interchangeable at this seam: adding a format is one line here
#: and one in :mod:`xtalapp.dialogs.image_export`.
WRITERS = {
    ".png": vtkPNGWriter,
    ".jpg": vtkJPEGWriter,
    ".jpeg": vtkJPEGWriter,
    ".tif": vtkTIFFWriter,
    ".tiff": vtkTIFFWriter,
}

#: The ones with somewhere to put an alpha channel.  Handing
#: ``vtkJPEGWriter`` four components writes a broken file rather than
#: raising, so transparency is dropped for it rather than refused.
ALPHA_SUFFIXES = frozenset({".png", ".tif", ".tiff"})

SVG_SUFFIX = ".svg"


def projection_for(renderer, size):
    """The camera's world-to-picture transform, as plain arrays.

    ``GetCompositeProjectionTransformMatrix`` is the same 4x4 the
    renderer draws through, so an SVG built from it lands every atom
    where the viewport has it -- including the parallel scale and the
    perspective the user set.

    The camera's horizontal axis comes back with it because
    :class:`~xtalapp.viewport.svg_export.Projection` measures an atom
    by projecting a point one radius to the side of it, and the matrix
    alone does not say which way that is.
    """
    from xtalapp.viewport.svg_export import Projection

    camera = renderer.GetActiveCamera()
    width, height = int(size[0]), int(size[1])
    matrix = camera.GetCompositeProjectionTransformMatrix(
        width / max(height, 1), -1.0, 1.0)
    values = np.array([[matrix.GetElement(i, j) for j in range(4)]
                       for i in range(4)], dtype=float)
    # The cross product is perpendicular to both whatever the view up
    # is, which VTK does not require to be square to the view.
    direction = np.array(camera.GetDirectionOfProjection(), float)
    right = np.cross(direction, np.array(camera.GetViewUp(), float))
    norm = np.linalg.norm(right)
    right = right / norm if norm > 1e-12 else np.array([1.0, 0.0, 0.0])
    return Projection(matrix=values, right=right,
                      size=(width, height), direction=direction)


def write_image(window, path, magnification: int = 2,
                transparent: bool = False):
    """Write what a render window is showing, as the suffix names.

    Raster only -- ``.svg`` is
    :func:`xtalapp.viewport.svg_export.write_svg`, which works from
    the scene model rather than from the pixels and so is not
    something a render window alone can answer.

    A render window and not a widget, so the whole of this is
    exercised offscreen by ``tests/test_vtk_render.py`` -- the same
    reason nothing else in this module knows about Qt.

    ``transparent`` asks the grabber for the alpha channel instead of
    letting it composite over the background colour, which is what
    puts the crystal on a slide of any colour.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    writer = WRITERS[suffix]()
    transparent = transparent and suffix in ALPHA_SUFFIXES
    # An alpha channel has to be in the buffer before the grabber can
    # read one; macOS supplies it either way, a bare X11 visual does
    # not.
    planes = window.GetAlphaBitPlanes()
    if transparent and not planes:
        window.SetAlphaBitPlanes(1)
        window.Render()
    try:
        grabber = vtkWindowToImageFilter()
        grabber.SetInput(window)
        grabber.SetScale(magnification)
        if transparent:
            grabber.SetInputBufferTypeToRGBA()
        # The front buffer is whatever the compositor last put on
        # screen, and on a window that has just been uncovered that is
        # not this scene.
        grabber.ReadFrontBufferOff()
        grabber.Update()
        writer.SetFileName(str(path))
        writer.SetInputConnection(grabber.GetOutputPort())
        writer.Write()
    finally:
        if transparent and not planes:
            window.SetAlphaBitPlanes(planes)
    return path


def render_to_array(model, size=(400, 300), direction=None):
    """Render a scene model offscreen and return the pixels as an
    (H, W, 3) uint8 array.

    Tests assert on this: "are there red pixels where the oxygen is"
    catches a broken colour array, which a file-size check never
    would."""
    from vtkmodules.util.numpy_support import vtk_to_numpy

    scene = VtkScene()
    scene.set_model(model)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(*size)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    if direction is not None:
        scene.look_along(direction)
        scene.renderer.ResetCamera()
    window.Render()

    grabber = vtkWindowToImageFilter()
    grabber.SetInput(window)
    grabber.Update()
    image = grabber.GetOutput()
    width, height, _ = image.GetDimensions()
    pixels = vtk_to_numpy(image.GetPointData().GetScalars())
    window.Finalize()
    return pixels.reshape(height, width, -1)[::-1, :, :3]


def render_offscreen(model, path, size=(800, 600), lattice=None):
    """Render a scene model to a PNG without a window.

    This is what the render tests assert on, and how documentation
    images are made.
    """
    scene = VtkScene()
    scene.set_model(model)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(*size)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    if lattice is not None:
        scene.look_along(np.array([1.0, 1.0, 0.6]))
        scene.renderer.ResetCamera()
    window.Render()

    grabber = vtkWindowToImageFilter()
    grabber.SetInput(window)
    grabber.Update()
    writer = vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(grabber.GetOutputPort())
    writer.Write()
    window.Finalize()
    return Path(path)


def _decompose(tensors) -> tuple[np.ndarray, np.ndarray]:
    """Split ellipsoid transforms into ``(semi-axes, quaternions)``.

    ``vtkGlyph3DMapper`` scales a glyph by three components and *then*
    turns it by a quaternion, so what it draws is ``R diag(s)`` applied
    to a unit sphere.  The singular value decomposition
    ``M = U S V^T`` hands both halves over: the singular values are the
    semi-axes and ``U`` is the orientation.

    ``V^T`` is dropped, and that is the point rather than an
    approximation.  It is a rotation *of the unit sphere*, which the
    unit sphere is invariant under -- so ``U S`` and ``U S V^T`` have
    exactly the same image and describe the same ellipsoid.  Keeping it
    as ``U V^T`` instead, which is the reflex answer for "the rotation
    part of a matrix", pairs the axis lengths with the wrong axes and
    draws every ellipsoid pointing somewhere else.

    VTK reads a quaternion as ``(w, x, y, z)``.
    """
    tensors = np.asarray(tensors, dtype=float)
    if not len(tensors):
        return (np.zeros((0, 3), np.float32),
                np.zeros((0, 4), np.float32))
    rotations, axes, _vt = np.linalg.svd(tensors)
    # A reflection is not a rotation and has no quaternion.  Flipping
    # one axis makes it one and changes nothing visible, because an
    # ellipsoid is symmetric about each of its axes.
    flipped = np.linalg.det(rotations) < 0
    if np.any(flipped):
        rotations = rotations.copy()
        rotations[flipped, :, 2] *= -1
    return axes.astype(np.float32), _to_quaternions(rotations)


def _to_quaternions(rotations) -> np.ndarray:
    """(N, 4) ``(w, x, y, z)`` for a stack of proper rotations.

    Shepperd's method: the naive formula divides by ``w``, and ``w`` is
    zero for a half turn -- which is not an exotic case here, because
    half of a space group's operations are two-fold axes.
    """
    n = len(rotations)
    out = np.zeros((n, 4), dtype=np.float64)
    for k in range(n):
        m = rotations[k]
        trace = m[0, 0] + m[1, 1] + m[2, 2]
        if trace > 0:
            root = np.sqrt(trace + 1.0) * 2
            out[k] = [0.25 * root,
                      (m[2, 1] - m[1, 2]) / root,
                      (m[0, 2] - m[2, 0]) / root,
                      (m[1, 0] - m[0, 1]) / root]
        else:
            i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
            j, q = (i + 1) % 3, (i + 2) % 3
            root = np.sqrt(1.0 + m[i, i] - m[j, j] - m[q, q]) * 2
            out[k, 0] = (m[q, j] - m[j, q]) / root
            out[k, 1 + i] = 0.25 * root
            out[k, 1 + j] = (m[j, i] + m[i, j]) / root
            out[k, 1 + q] = (m[q, i] + m[i, q]) / root
    norm = np.linalg.norm(out, axis=1, keepdims=True)
    return (out / np.where(norm < 1e-12, 1.0, norm)).astype(np.float32)
