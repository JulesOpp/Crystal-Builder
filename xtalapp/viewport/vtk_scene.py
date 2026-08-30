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
* every bond half is one line in a second polydata, thickened by one
  tube filter, coloured per line;
* every coordination polyhedron is a set of triangles in a third,
  translucent polydata, coloured per face;
* the cell is a fourth polydata of lines.

Four actors for the structure, however many atoms there are.
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
from vtkmodules.vtkIOImage import vtkPNGWriter
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

# vtkIdType is 32- or 64-bit depending on how VTK was built; the
# connectivity arrays have to match or VTK reads them as garbage.
ID_TYPE = np.int64 if vtkIdTypeArray().GetDataTypeSize() == 8 \
    else np.int32

SPHERE_RESOLUTION = 24
TUBE_SIDES = 12
MAX_LABELS = 400            # beyond this, labels are noise anyway

# The element legend, in fractions of the window.
LEGEND_X = 0.90
LEGEND_TOP = 0.94
LEGEND_ROW = 0.045
LEGEND_SWATCH = 0.018
LEGEND_FONT = 15

# Selection is drawn as a translucent halo around the real geometry
# rather than by recolouring it: the element colours are how a
# crystallographer reads the picture, and a selection must not take
# them away.
HIGHLIGHT_COLOR = (255, 205, 40)
HIGHLIGHT_OPACITY = 0.45
HIGHLIGHT_GROWTH = 1.30     # halo radius, relative to the atom


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
        self._label_actors: list[vtkBillboardTextActor3D] = []
        self._legend_actors: list = []
        self._build_atom_actor()
        self._build_bond_actor()
        self._build_polyhedron_actor()
        self._build_cell_actor()
        self._build_highlight_actors()

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
        self._set_bonds(model)
        self._set_polyhedra(model)
        self._set_cell(model)
        self._set_labels(model)
        self._set_legend(model)
        self._set_highlight(model)

    def set_positions(self, model) -> None:
        """Move what is already drawn instead of rebuilding it.

        A geometry change leaves the topology alone: the same atoms,
        the same colours and radii, joined by the same bonds.  So the
        actors, the mappers and the glyph sources all stand, and only
        the coordinates underneath them are replaced -- which is what
        makes watching a relaxation on a large cell affordable.

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
        if model.n_bond_halves:
            self._bond_poly.SetPoints(
                _points(_interleave(model.bond_starts, model.bond_ends)))
            self._bond_poly.Modified()
        if model.n_polyhedron_faces:
            self._polyhedron_poly.SetPoints(
                _points(model.polyhedron_points))
            self._polyhedron_poly.Modified()
        # These two are placed *at* atoms, so they move with them.
        self._set_highlight(model)
        self._set_labels(model)

    def _same_shape(self, model) -> bool:
        """Does this model draw the same things as the current one?"""
        current = self.model
        return (model.n_atoms == current.n_atoms
                and model.n_bond_halves == current.n_bond_halves
                and model.bond_render == current.bond_render
                and model.n_polyhedron_faces
                == current.n_polyhedron_faces
                and len(model.polyhedron_points)
                == len(current.polyhedron_points)
                and model.n_cell_lines == current.n_cell_lines
                and model.background == current.background)

    def _set_atoms(self, model):
        poly = vtkPolyData()
        if model.n_atoms:
            poly.SetPoints(_points(model.positions))
            poly.GetPointData().AddArray(_to_float(model.radii, "radii"))
            poly.GetPointData().AddArray(_to_uchar(model.colors,
                                                   "colors"))
        self._atom_poly = poly
        self.atom_mapper.SetInputData(poly)
        self.atom_actor.SetVisibility(model.n_atoms > 0)

    def _set_bonds(self, model):
        if not model.n_bond_halves:
            self.bond_actor.SetVisibility(False)
            return
        poly = _line_polydata(model.bond_starts, model.bond_ends,
                              model.bond_colors)
        self._bond_poly = poly
        if model.bond_render == "line":
            self.bond_mapper.SetInputData(poly)
            self.bond_actor.GetProperty().SetLineWidth(2.0)
            self.bond_actor.GetProperty().SetLighting(False)
        else:
            self._tube.SetInputData(poly)
            self._tube.SetRadius(model.bond_radius)
            self.bond_mapper.SetInputConnection(self._tube.GetOutputPort())
            self.bond_actor.GetProperty().SetLighting(True)
        self.bond_actor.SetVisibility(True)

    def _set_polyhedra(self, model):
        if not model.n_polyhedron_faces:
            self.polyhedron_actor.SetVisibility(False)
            return
        poly = vtkPolyData()
        poly.SetPoints(_points(model.polyhedron_points))
        faces = np.ascontiguousarray(model.polyhedron_faces,
                                     dtype=ID_TYPE)
        cells = vtkCellArray()
        cells.SetData(
            numpy_to_vtkIdTypeArray(
                np.arange(0, 3 * len(faces) + 1, 3, dtype=ID_TYPE),
                deep=True),
            numpy_to_vtkIdTypeArray(faces.ravel(), deep=True))
        poly.SetPolys(cells)
        poly.GetCellData().SetScalars(
            _to_uchar(model.polyhedron_colors, "colors"))
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

    def set_selection(self, selected, selected_bonds) -> None:
        """Change only what is highlighted.

        Selecting an atom changes no geometry, so the halo actors are
        the only thing that has to be rebuilt -- and on a big structure
        that is the difference between a click that lands immediately
        and one that hangs on a full scene rebuild.
        """
        if self.model is None:
            return
        self.model = replace(self.model, selected=selected,
                             selected_bonds=selected_bonds)
        self._set_highlight(self.model)

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
                                      * HIGHLIGHT_GROWTH * 1.4)
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
