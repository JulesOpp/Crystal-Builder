"""
xtalapp.viewport.widget
=======================
The Qt widget that holds the VTK render window.

One hard-won detail is encoded here: on macOS the render window must be
**realised before it is initialised**.  Calling ``Initialize()`` or
``Render()`` on a QVTKRenderWindowInteractor that has not been shown
and had its events processed segfaults the process -- not an exception,
a crash.  So initialisation happens on the first ``showEvent`` and
never in the constructor, and every render goes through
:meth:`_safe_render`, which does nothing until that has happened.

Mouse behaviour is VTK's trackball camera, which is already what a
crystallographer expects:

    left drag           rotate
    wheel               zoom
    middle drag         pan
    right drag          dolly
"""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

os.environ.setdefault("QT_API", "pyside6")

from vtkmodules.qt.QVTKRenderWindowInteractor import (
    QVTKRenderWindowInteractor,  # noqa: E402
)
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleTrackballCamera,  # noqa: E402
)
from vtkmodules.vtkIOImage import vtkPNGWriter  # noqa: E402
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter  # noqa: E402

from xtalapp.viewport.builder import build_scene  # noqa: E402
from xtalapp.viewport.vtk_scene import (  # noqa: E402
    VtkScene,
    orientation_marker,
)


class ViewportWidget(QWidget):
    """A 3-D view of one document."""

    pickedAtom = Signal(int)            # scene instance index (phase 3)

    def __init__(self, document=None, parent=None):
        super().__init__(parent)
        self.document = None
        self._initialised = False
        self._marker = None

        self._interactor = QVTKRenderWindowInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._interactor)

        self.scene = VtkScene()
        self._interactor.GetRenderWindow().AddRenderer(self.scene.renderer)
        self._interactor.SetInteractorStyle(
            vtkInteractorStyleTrackballCamera())
        self.setFocusPolicy(Qt.StrongFocus)

        if document is not None:
            self.set_document(document)

    # -- lifecycle -----------------------------------------------------

    def showEvent(self, event):
        """Initialise VTK only once the window really exists."""
        super().showEvent(event)
        if not self._initialised:
            self._interactor.Initialize()
            self._marker = orientation_marker(self._interactor)
            self._initialised = True
            self.rebuild(reset_camera=True)

    def closeEvent(self, event):
        self._interactor.Finalize()
        super().closeEvent(event)

    def _safe_render(self):
        if self._initialised:
            self._interactor.GetRenderWindow().Render()

    # -- document binding ----------------------------------------------

    def set_document(self, document) -> None:
        if self.document is not None:
            self.document.structureChanged.disconnect(self._on_structure)
            self.document.viewChanged.disconnect(self._on_view)
        self.document = document
        document.structureChanged.connect(self._on_structure)
        document.viewChanged.connect(self._on_view)
        self.rebuild(reset_camera=True)

    def _on_structure(self, _change: int) -> None:
        self.rebuild(reset_camera=False)

    def _on_view(self) -> None:
        self.rebuild(reset_camera=False)

    def rebuild(self, reset_camera: bool = False) -> None:
        """Rebuild the scene from the document and redraw."""
        if self.document is None:
            return
        model = build_scene(self.document.structure, self.document.view)
        self.scene.set_model(model)
        self.scene.set_projection(self.document.view.projection)
        if reset_camera:
            self.scene.reset_camera()
        self._safe_render()

    # -- camera --------------------------------------------------------

    def reset_view(self) -> None:
        self.scene.reset_camera()
        self._safe_render()

    def look_along_axis(self, axis: int) -> None:
        """Look down a lattice vector (0 = a, 1 = b, 2 = c)."""
        if self.document is None:
            return
        matrix = self.document.structure.lattice.matrix
        self.scene.look_along(matrix[axis])
        self.scene.reset_camera()
        self._safe_render()

    def look_along_reciprocal(self, axis: int) -> None:
        """Look down a reciprocal axis -- for a monoclinic cell this is
        not the same view as looking down the direct axis."""
        if self.document is None:
            return
        rec = self.document.structure.lattice.reciprocal().matrix
        self.scene.look_along(rec[axis])
        self.scene.reset_camera()
        self._safe_render()

    def save_image(self, path, magnification: int = 2):
        """Write a high-resolution PNG of the current view."""
        window = self._interactor.GetRenderWindow()
        grabber = vtkWindowToImageFilter()
        grabber.SetInput(window)
        grabber.SetScale(magnification)
        grabber.Update()
        writer = vtkPNGWriter()
        writer.SetFileName(str(path))
        writer.SetInputConnection(grabber.GetOutputPort())
        writer.Write()
        return path

    def camera_direction(self) -> np.ndarray:
        camera = self.scene.renderer.GetActiveCamera()
        return np.array(camera.GetDirectionOfProjection())
