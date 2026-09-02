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

-- except in a mode that wants the left button for itself.  Box select
does: a rubber band and a camera rotation are the same gesture, and
only one of them can have it.  Those modes are marked ``wants_drag``
and the event filter withholds the left button from VTK while they are
active; pan and zoom keep working throughout, so the view is never
stuck.

Two things happen between the clicks.  A mode marked ``wants_move``
is told where the cursor is on every mouse move and may hand back a
ghost -- the atom a click would place, drawn over the scene and never
part of it -- and ``Escape`` tells the active mode to put down
whatever it is halfway through.
"""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QRubberBand,
    QVBoxLayout,
    QWidget,
)

os.environ.setdefault("QT_API", "pyside6")

from vtkmodules.qt.QVTKRenderWindowInteractor import (
    QVTKRenderWindowInteractor,  # noqa: E402
)
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleTrackballCamera,  # noqa: E402
)
from vtkmodules.vtkIOImage import vtkPNGWriter  # noqa: E402
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter  # noqa: E402

from xtal.core.structure import Change  # noqa: E402
from xtalapp.viewport import modes, picking  # noqa: E402
from xtalapp.viewport.builder import (  # noqa: E402
    build_scene,
    selection_flags,
)
from xtalapp.viewport.vtk_scene import (  # noqa: E402
    VtkScene,
    orientation_marker,
)

# A press and release within this many pixels is a click, not a drag;
# anything further is the camera being turned and must not select.
# Fixed at 4 for a mouse, this made a two-click gesture -- add bond,
# add topology bond -- fail far more often than a one-click one under
# the same per-click miss rate, because a trackpad "click" routinely
# carries a few pixels of incidental movement.  Qt's own
# ``startDragDistance()`` is the platform's answer to exactly this
# question -- how far is a click allowed to wander before it is a
# drag -- and every other Qt widget already uses it, so the viewport
# now agrees with the rest of the application instead of being
# stricter than all of it.
CLICK_SLOP = 4


def click_slop() -> int:
    """How far a press may wander and still count as a click.

    Qt's own threshold when there is an application to ask, and the
    historical constant as a floor: some platform styles report a
    ``startDragDistance()`` smaller than what feels right for a 3-D
    pick, and this must never make picking *more* trigger-happy than
    it already was.
    """
    app = QApplication.instance()
    if app is None:                                 # pragma: no cover
        return CLICK_SLOP
    return max(CLICK_SLOP, app.startDragDistance())

# VTK's interactor style binds these single letters to behaviour of its
# own, and none of it is behaviour this application wants: `e` and `q`
# ask the render window to close, `w` and `s` switch every actor to
# wireframe and back behind the style menu, `f` flies the camera at
# whatever is under the cursor, `p` runs VTK's own picker, `r` resets
# the camera behind Reset View, `u` opens a user event, and `3` toggles
# red/cyan stereo.  They are swallowed before VTK sees them, so the
# viewport only does what the application asked it to.
#
# Modified presses are never swallowed, and neither are the keys this
# application binds (`1`, `2`, `3` look down an axis): Qt matches a
# shortcut before the key event is delivered, so those never arrive
# here at all.
VTK_RESERVED_KEYS = frozenset("eqwsfpur3")

# How often a preview is allowed to redraw, in milliseconds.  The
# optimiser emits a step whenever it has one -- the plot and the log
# want every one of them -- and the viewport draws whatever the latest
# geometry is when the timer next fires.  Welding those two rates
# together is what made a long run on a large cell fall a step further
# behind on every step.  0 means draw every step; a negative interval
# means do not draw at all, which is the right way to watch a long run
# on a very large cell.
DEFAULT_PREVIEW_INTERVAL_MS = 50            # 20 frames a second


def is_vtk_reserved_key(event) -> bool:
    """Is this one of VTK's own hotkeys, pressed on its own?"""
    held = (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
    if event.modifiers() & held:
        return False                        # Ctrl+S is Save, not surface
    return event.text().lower() in VTK_RESERVED_KEYS


class ViewportWidget(QWidget):
    """A 3-D view of one document."""

    statusMessage = Signal(str)
    #: what was under the cursor ("atom" | "bond" | "view"), and where
    #: on screen to put the menu.  The window builds the menu, because
    #: the actions in it live in its registry.
    contextRequested = Signal(str, QPoint)
    #: The mode changed, and the window did not ask for it -- Escape
    #: leaves a mode.  Without this the toolbar keeps the old button
    #: pressed, which is a picture of a mode the viewport is not in.
    modeChanged = Signal(str)

    def __init__(self, document=None, parent=None):
        super().__init__(parent)
        self.document = None
        self._initialised = False
        self._marker = None
        self.mode = modes.get("select")
        self._press_position = None
        self._press_button = None
        self._band = None
        self._band_origin = None
        self._ghost = None

        self.preview_interval_ms = DEFAULT_PREVIEW_INTERVAL_MS
        self._preview_pending = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._draw_preview)

        self._interactor = QVTKRenderWindowInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._interactor)

        self.model = None
        self.scene = VtkScene()
        self._interactor.GetRenderWindow().AddRenderer(self.scene.renderer)
        self._interactor.SetInteractorStyle(
            vtkInteractorStyleTrackballCamera())
        self.setFocusPolicy(Qt.StrongFocus)
        # Watch the interactor's own mouse events rather than
        # subclassing it: VTK still gets every event (the filter never
        # consumes one), so the trackball camera keeps working and a
        # click that did not drag is treated as a pick.
        self._interactor.installEventFilter(self)

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
            self.document.previewChanged.disconnect(self._on_preview)
            self.document.viewChanged.disconnect(self._on_view)
            self.document.selectionChanged.disconnect(self._on_selection)
        self.document = document
        document.structureChanged.connect(self._on_structure)
        document.previewChanged.connect(self._on_preview)
        document.viewChanged.connect(self._on_view)
        document.selectionChanged.connect(self._on_selection)
        self.rebuild(reset_camera=True)

    def set_mode(self, name: str) -> None:
        if self.mode is not None:
            self.mode.on_deactivate(self.document)
        self.set_ghost(None)
        self.mode = modes.get(name)
        if self._band is not None:
            self._band.hide()
        self._band_origin = None
        # What the mode makes of the state it is entering, and the
        # plain hint when it makes nothing of it: Add atom with one
        # atom already selected starts halfway through its own
        # gesture, and describing a first click that will not happen
        # is worse than saying nothing.
        message = self.mode.on_activate(self.document, self.model)
        self.modeChanged.emit(name)
        self.statusMessage.emit(message or self.mode.hint)

    def _on_structure(self, change: int) -> None:
        """Redraw as much as the change actually calls for.

        A geometry change leaves every actor in place and only moves
        the points underneath them; anything else rebuilds the scene.
        Ignoring the hint -- which is what this used to do -- makes
        dragging one atom cost the same as loading a new crystal.
        """
        if change and not (change & ~int(Change.POSITIONS)):
            self.update_positions()
        else:
            self.rebuild(reset_camera=False)

    def _on_preview(self) -> None:
        """A geometry is being shown, not committed.

        Coalesced onto a timer so the redraw rate stops being a
        function of how fast the solver is: every step is announced,
        and whatever the geometry is when the timer fires is what gets
        drawn.
        """
        if self.preview_interval_ms < 0:
            return                          # asked not to draw at all
        if self.preview_interval_ms == 0:
            self.update_positions()
            return
        self._preview_pending = True
        if not self._preview_timer.isActive():
            self._preview_timer.start(self.preview_interval_ms)

    def _draw_preview(self) -> None:
        if self._preview_pending:
            self._preview_pending = False
            self.update_positions()

    def update_positions(self) -> None:
        """Move the atoms without rebuilding the scene."""
        if self.document is None:
            return
        if self.model is None:
            self.rebuild(reset_camera=False)
            return
        model = build_scene(self.document.structure,
                            self.document.view,
                            selection=self.document.selection,
                            view_direction=self.camera_direction())
        self.model = model
        self.scene.set_positions(model)
        self._safe_render()

    def _on_view(self) -> None:
        self.rebuild(reset_camera=False)

    def _on_selection(self) -> None:
        """Selecting changes the highlight, not the geometry.

        Rebuilding the whole scene to light up one atom is what made
        clicking around a large structure feel slow; the flags are two
        arrays and the actors underneath them do not move.
        """
        if self.document is None or self.model is None:
            self.rebuild(reset_camera=False)
            return
        atoms, bonds, net = selection_flags(self.model,
                                            self.document.selection)
        self.scene.set_selection(atoms, bonds, net)
        self.model = self.scene.model
        self._safe_render()

    def rebuild(self, reset_camera: bool = False) -> None:
        """Rebuild the scene from the document and redraw."""
        if self.document is None:
            return
        model = build_scene(self.document.structure,
                            self.document.view,
                            selection=self.document.selection,
                            view_direction=self.camera_direction())
        self.model = model
        self.scene.set_model(model)
        self.scene.set_projection(self.document.view.projection)
        if reset_camera:
            self.scene.reset_camera()
        self._safe_render()

    # -- picking -------------------------------------------------------

    def eventFilter(self, watched, event):
        """Turn a non-dragging click into a pick, run the rubber band
        for a mode that wants the drag, and keep VTK's own key bindings
        out of the application."""
        if watched is self._interactor:
            if event.type() == QEvent.MouseButtonPress:
                self._press_position = event.position().toPoint()
                self._press_button = event.button()
                if self._takes_drag(event):
                    self._begin_band(self._press_position)
                    return True         # VTK never starts a rotation
            elif event.type() == QEvent.MouseMove:
                if self._band_origin is not None:
                    self._drag_band(event.position().toPoint())
                    return True
                self._maybe_hover(event)
            elif event.type() == QEvent.Leave:
                self.set_ghost(None)
            elif event.type() == QEvent.MouseButtonRelease:
                if self._band_origin is not None:
                    self._finish_band(event)
                    return True
                self._maybe_pick(event, double=False)
                self._maybe_context_menu(event)
            elif event.type() == QEvent.MouseButtonDblClick:
                self._press_position = event.position().toPoint()
                self._press_button = event.button()
                if self._takes_drag(event):
                    return True
                self._maybe_pick(event, double=True)
            elif event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
                if (event.type() == QEvent.KeyPress
                        and event.key() == Qt.Key_Escape):
                    self.cancel_gesture()
                    return True
                if is_vtk_reserved_key(event):
                    return True             # consumed: VTK never sees it
        return super().eventFilter(watched, event)

    # -- the rubber band -----------------------------------------------

    def _takes_drag(self, event) -> bool:
        return (getattr(self.mode, "wants_drag", False)
                and event.button() == Qt.LeftButton)

    def _begin_band(self, point: QPoint) -> None:
        if self._band is None:
            self._band = QRubberBand(QRubberBand.Rectangle,
                                     self._interactor)
        self._band_origin = point
        self._band.setGeometry(QRect(point, point))
        self._band.show()

    def _drag_band(self, point: QPoint) -> None:
        self._band.setGeometry(
            QRect(self._band_origin, point).normalized())

    def _finish_band(self, event) -> None:
        """The button came up: take what is in the box.

        A band that never left the press point is a click, and is sent
        on as one -- otherwise clicking a single atom in this mode does
        nothing at all and the mode feels broken.
        """
        origin, self._band_origin = self._band_origin, None
        point = event.position().toPoint()
        self._band.hide()
        if self.document is None or self.model is None:
            return
        additive = bool(event.modifiers() & (
            Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier))
        if (point - origin).manhattanLength() <= click_slop():
            self._press_position = origin
            self._press_button = Qt.LeftButton
            self.pick_at(point, additive=additive, double=False)
            return
        message = self.mode.on_drag(
            self.document, self.model,
            modes.DragEvent(self._display_at(origin),
                            self._display_at(point), additive,
                            self._project))
        if message:
            self.statusMessage.emit(message)

    def _project(self, points):
        return picking.project_to_display(self.scene.renderer, points)

    def _maybe_pick(self, event, double: bool) -> None:
        if (self._press_position is None
                or self._press_button != Qt.LeftButton
                or event.button() != Qt.LeftButton):
            return
        moved = (event.position().toPoint()
                 - self._press_position).manhattanLength()
        self._press_position = None
        if moved > click_slop():
            return              # the camera was being turned
        self.pick_at(event.position().toPoint(),
                     additive=bool(event.modifiers() & (
                         Qt.ShiftModifier | Qt.ControlModifier
                         | Qt.MetaModifier)),
                     double=double)

    # -- the ghost -----------------------------------------------------

    def _maybe_hover(self, event) -> None:
        """Tell a mode that asked for it where the cursor is.

        Only for a mode that asks (``wants_move``): casting a ray per
        mouse move for the modes that would ignore it is a cost with
        nothing on the other side of it.  ``picking.pick`` is exact
        and vectorised and a mouse move is not a hot loop, so a mode
        that does ask needs nothing more than this.
        """
        if not getattr(self.mode, "wants_move", False):
            return
        if self.document is None or self.model is None:
            return
        if event.buttons():
            return                  # a button is down: the camera
        origin, direction = self._ray_at(event.position().toPoint())
        focal = self.scene.renderer.GetActiveCamera().GetFocalPoint()
        self.set_ghost(self.mode.on_move(
            self.document, self.model,
            modes.MoveEvent(origin, direction, tuple(focal))))

    def set_ghost(self, ghost) -> None:
        """Draw the atom a click would place, or clear it.

        Nothing to nothing is not a redraw: every mouse move over a
        structure with no gesture in progress arrives here, and
        rendering the same empty overlay each time would put a frame
        on the wire for a cursor that is only passing through.
        """
        if ghost is None and self._ghost is None:
            return
        self._ghost = ghost
        self.scene.set_ghost(ghost)
        self._safe_render()

    def cancel_gesture(self) -> None:
        """Escape: abandon whatever the mode is halfway through, and
        then the mode itself.

        Two stages, because they are two different things to want.
        The first Escape puts down the state the mode is holding -- an
        add-atom chain, the first end of a bond, the atoms gathered
        for a measurement -- which is otherwise unreachable except by
        switching modes and back.  A second Escape, with nothing left
        to put down, means the user is finished: it returns to Select,
        which is the mode a click can do no harm in.
        """
        if self.mode is None:
            return
        message = self.mode.on_cancel(self.document)
        self.set_ghost(None)
        if not message and self.mode.name != "select":
            self.set_mode("select")
            return
        if message:
            self.statusMessage.emit(message)

    def _maybe_context_menu(self, event) -> None:
        """A right click that did not drag asks for a context menu.

        The same press-and-release-within-the-slop test the left button
        uses, because right-drag is the camera dolly and has to keep
        working.
        """
        if (self._press_position is None
                or self._press_button != Qt.RightButton
                or event.button() != Qt.RightButton):
            return
        point = event.position().toPoint()
        moved = (point - self._press_position).manhattanLength()
        self._press_position = None
        if moved > click_slop():
            return                          # the camera was being moved
        kind = self.select_under(point)
        self.contextRequested.emit(
            kind, self._interactor.mapToGlobal(point))

    def select_under(self, point: QPoint) -> str:
        """Select what is under the cursor, and say what it was.

        A menu that acts on a selection the user cannot see is how a
        context menu deletes the wrong thing -- so right-clicking
        something outside the selection selects it first.  Clicking
        *inside* the selection leaves it alone, which is what makes
        "delete these fourteen atoms" reachable.
        """
        if self.document is None or self.model is None:
            return "view"
        origin, direction = self._ray_at(point)
        kind, index = picking.pick(self.model, origin, direction)
        selection = self.document.selection
        if kind == "atom":
            atom, _cell = self.model.instance(index)
            if atom not in selection.atoms:
                self.document.select([atom], "set")
            return "atom"
        if kind == "bond":
            key = self.model.bond_key(index)
            if key not in selection.bonds:
                self.document.select_bond(key, "set")
            return "bond"
        return "view"

    def pick_at(self, point: QPoint, additive: bool = False,
                double: bool = False) -> None:
        """Send a click at a widget position to the active mode."""
        if self.document is None or self.model is None:
            return
        origin, direction = self._ray_at(point)
        focal = self.scene.renderer.GetActiveCamera().GetFocalPoint()
        message = self.mode.on_click(
            self.document, self.model,
            modes.ClickEvent(origin, direction, additive, double,
                             tuple(focal)))
        # The ghost was showing what this click would do, and it has
        # now done it; the next mouse move puts a new one up if the
        # mode still wants one.
        self.set_ghost(None)
        if message:
            self.statusMessage.emit(message)

    def _display_at(self, point: QPoint) -> tuple:
        """Widget coordinates (top-left origin, logical pixels) to VTK
        display coordinates (bottom-left origin, device pixels).

        On a Retina screen the two are not the same size, which is the
        whole reason this is a function and not two subtractions at
        each call site."""
        window = self._interactor.GetRenderWindow()
        _width, height = window.GetSize()
        ratio = (height / max(self._interactor.height(), 1))
        return point.x() * ratio, height - point.y() * ratio

    def _ray_at(self, point: QPoint):
        """The world-space ray under a widget position."""
        x, y = self._display_at(point)
        return picking.ray_from_display(self.scene.renderer, x, y)

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
