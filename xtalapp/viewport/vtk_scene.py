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
* the cell is a third polydata of lines.

Three actors for the structure, however many atoms there are.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Importing these registers the OpenGL and text rendering factories.
import vtkmodules.vtkRenderingFreeType  # noqa: F401
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from vtkmodules.vtkCommonCore import (
    vtkFloatArray,
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
    vtkBillboardTextActor3D,
    vtkGlyph3DMapper,
    vtkPolyDataMapper,
    vtkRenderer,
    vtkRenderWindow,
    vtkWindowToImageFilter,
)

SPHERE_RESOLUTION = 24
TUBE_SIDES = 12
MAX_LABELS = 400            # beyond this, labels are noise anyway


def _to_uchar(colors: np.ndarray, name: str) -> vtkUnsignedCharArray:
    arr = vtkUnsignedCharArray()
    arr.SetName(name)
    arr.SetNumberOfComponents(3)
    data = np.ascontiguousarray(colors, dtype=np.uint8)
    arr.SetNumberOfTuples(len(data))
    for i, (r, g, b) in enumerate(data):
        arr.SetTypedTuple(i, (int(r), int(g), int(b)))
    return arr


def _to_float(values: np.ndarray, name: str) -> vtkFloatArray:
    arr = vtkFloatArray()
    arr.SetName(name)
    arr.SetNumberOfComponents(1)
    data = np.ascontiguousarray(values, dtype=np.float32)
    arr.SetNumberOfTuples(len(data))
    for i, v in enumerate(data):
        arr.SetValue(i, float(v))
    return arr


def _points(positions: np.ndarray) -> vtkPoints:
    pts = vtkPoints()
    pts.SetNumberOfPoints(len(positions))
    for i, (x, y, z) in enumerate(positions):
        pts.SetPoint(i, float(x), float(y), float(z))
    return pts


def _line_polydata(starts, ends, colors) -> vtkPolyData:
    """One line cell per segment, coloured by cell data."""
    poly = vtkPolyData()
    pts = vtkPoints()
    lines = vtkCellArray()
    pts.SetNumberOfPoints(2 * len(starts))
    for i, (a, b) in enumerate(zip(starts, ends, strict=True)):
        pts.SetPoint(2 * i, *[float(v) for v in a])
        pts.SetPoint(2 * i + 1, *[float(v) for v in b])
        lines.InsertNextCell(2)
        lines.InsertCellPoint(2 * i)
        lines.InsertCellPoint(2 * i + 1)
    poly.SetPoints(pts)
    poly.SetLines(lines)
    poly.GetCellData().SetScalars(_to_uchar(colors, "colors"))
    return poly


class VtkScene:
    """Owns the actors for one structure and keeps them in sync with a
    :class:`~xtalapp.viewport.scene.SceneModel`."""

    def __init__(self, renderer: vtkRenderer | None = None):
        self.renderer = renderer or vtkRenderer()
        self.model = None
        self._atom_poly = vtkPolyData()
        self._label_actors: list[vtkBillboardTextActor3D] = []
        self._build_atom_actor()
        self._build_bond_actor()
        self._build_cell_actor()

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

    # -- updating ------------------------------------------------------

    def set_model(self, model) -> None:
        """Rebuild every actor from a new scene model."""
        self.model = model
        r, g, b = model.background
        self.renderer.SetBackground(r / 255, g / 255, b / 255)

        self._set_atoms(model)
        self._set_bonds(model)
        self._set_cell(model)
        self._set_labels(model)

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

    def _set_cell(self, model):
        if not model.n_cell_lines:
            self.cell_actor.SetVisibility(False)
            return
        self._cell_poly = _line_polydata(model.cell_starts,
                                         model.cell_ends,
                                         model.cell_colors)
        self.cell_mapper.SetInputData(self._cell_poly)
        self.cell_actor.SetVisibility(True)

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
