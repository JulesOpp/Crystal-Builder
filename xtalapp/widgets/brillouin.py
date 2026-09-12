"""
xtalapp.widgets.brillouin
=========================
The Brillouin zone, turned by hand, with the path drawn through it.

So that the letters under a band structure mean something.  Gamma, X
and L are corners and face centres of a solid most people have only
seen in a textbook's standard orientation, and this cell is not in
it; what makes the picture useful is that it is drawn in *this*
cell's frame, with the reciprocal vectors b1 b2 b3 on it and the real
a b c triad beside them, so a user can see that X lies along b1 + b3
and a lies across it.

A ``QPainter`` wireframe with an orthographic projection -- not VTK,
which would be a second GL context in a dialog for twenty lines --
turned by dragging, the way the viewport's trackball turns.  Faces
pointing away are drawn fainter, which is all the depth a convex
solid needs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from xtal.analysis import kpath

AXIS_COLORS = (QColor(220, 60, 60), QColor(60, 170, 60),
               QColor(60, 100, 220))
PATH_COLOR = QColor(230, 120, 20)


class BrillouinView(QWidget):
    """The zone of a lattice, and optionally a path through it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zone = None
        self.reciprocal = np.eye(3)
        self.real = np.eye(3)
        self.points: dict = {}
        self.runs: tuple = ()
        self.rotation = _rotation(np.radians(-25), np.radians(30))
        self._drag = None
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip("Drag to turn the zone")

    def sizeHint(self):                             # noqa: N802
        return QSize(300, 300)

    # -- what is drawn -------------------------------------------------

    def set_lattice(self, matrix) -> None:
        matrix = np.asarray(matrix, dtype=float)
        from xtal.core.lattice import Lattice
        lattice = Lattice(matrix)
        self.zone = kpath.brillouin_zone(lattice)
        self.reciprocal = kpath.reciprocal(lattice)
        self.real = matrix
        self.update()

    def set_path(self, points, runs) -> None:
        """``points`` as ``{label: (k1, k2, k3)}`` in reciprocal
        fractions; ``runs`` as :attr:`BandPath.runs
        <xtal.analysis.kpath.BandPath.runs>`."""
        self.points = dict(points)
        self.runs = tuple(runs)
        self.update()

    # -- turning it ----------------------------------------------------

    def mousePressEvent(self, event):               # noqa: N802
        self._drag = event.position()

    def mouseMoveEvent(self, event):                # noqa: N802
        if self._drag is None:
            return
        delta = event.position() - self._drag
        self._drag = event.position()
        turn = _rotation(np.radians(delta.y() * 0.6),
                         np.radians(delta.x() * 0.6))
        self.rotation = turn @ self.rotation
        self.update()

    def mouseReleaseEvent(self, _event):            # noqa: N802
        self._drag = None

    # -- drawing -------------------------------------------------------

    def paintEvent(self, _event) -> None:           # noqa: N802
        painter = QPainter(self)
        try:
            self.paint(painter, QRectF(self.rect()))
        finally:
            painter.end()

    def paint(self, painter, rect) -> None:
        painter.fillRect(rect, self.palette().base())
        if self.zone is None:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        text = self.palette().text().color()
        corners = self.zone.vertices @ self.rotation.T
        reach = float(np.linalg.norm(self.zone.vertices, axis=1).max())
        scale = 0.36 * min(rect.width(), rect.height()) / (reach or 1.0)
        centre = rect.center()

        def at(v):
            return QPointF(centre.x() + v[0] * scale,
                           centre.y() - v[1] * scale)

        # Back faces faint, front faces solid: a face whose outward
        # normal points away from the viewer is behind the solid.
        faint = QColor(text)
        faint.setAlpha(60)
        for back in (True, False):
            for face in self.zone.faces:
                ring = corners[list(face)]
                middle = ring.mean(axis=0)
                if (middle[2] < 0) != back:
                    continue
                painter.setPen(QPen(faint if back else text, 1))
                for i in range(len(face)):
                    painter.drawLine(at(ring[i]),
                                     at(ring[(i + 1) % len(ring)]))

        self._draw_axes(painter, at, reach, rect)
        self._draw_path(painter, at, text)

    def _draw_axes(self, painter, at, reach, rect) -> None:
        origin = at(np.zeros(3))
        for number, vector in enumerate(self.reciprocal):
            tip = vector / np.linalg.norm(vector) * reach * 1.25
            tip = tip @ self.rotation.T
            painter.setPen(QPen(AXIS_COLORS[number], 2))
            painter.drawLine(origin, at(tip))
            painter.drawText(at(tip * 1.08), f"b{number + 1}")
        # The real-space triad, small, in a corner: which way a, b and c
        # run in this frame is what relates the zone to the crystal.
        corner = QPointF(rect.left() + 28, rect.bottom() - 28)
        for number, vector in enumerate(self.real):
            direction = vector / np.linalg.norm(vector) @ self.rotation.T
            end = QPointF(corner.x() + 20 * direction[0],
                          corner.y() - 20 * direction[1])
            painter.setPen(QPen(AXIS_COLORS[number], 1.5))
            painter.drawLine(corner, end)
            painter.drawText(QPointF(end.x() + 2, end.y()), "abc"[number])

    def _draw_path(self, painter, at, text) -> None:
        if not self.points:
            return
        cart = {label: np.asarray(k, float) @ self.reciprocal
                @ self.rotation.T for label, k in self.points.items()}
        painter.setPen(QPen(PATH_COLOR, 2.5))
        for run in self.runs:
            for first, second in zip(run, run[1:], strict=False):
                painter.drawLine(at(cart[first]), at(cart[second]))
        visited = {label for run in self.runs for label in run}
        for label, position in cart.items():
            point = at(position)
            painter.setPen(QPen(PATH_COLOR if label in visited else text,
                                1))
            painter.setBrush(PATH_COLOR if label in visited else text)
            painter.drawEllipse(point, 3, 3)
            painter.setPen(QPen(text, 1))
            painter.drawText(QPointF(point.x() + 5, point.y() - 4),
                             kpath.pretty(label))
        painter.setBrush(Qt.NoBrush)


def _rotation(about_x: float, about_y: float) -> np.ndarray:
    cx, sx = np.cos(about_x), np.sin(about_x)
    cy, sy = np.cos(about_y), np.sin(about_y)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    return rx @ ry


def save_zone(zone_block, path, size=(520, 520), scale: int = 2) -> Path:
    """A :class:`~xtal.modules.report.Zone` as a PNG for the run
    folder."""
    from PySide6.QtGui import QPixmap
    view = BrillouinView()
    view.set_lattice(zone_block.lattice)
    view.set_path(dict(zone_block.points), zone_block.runs)
    view.resize(*size)
    picture = QPixmap(size[0] * scale, size[1] * scale)
    picture.setDevicePixelRatio(scale)
    painter = QPainter(picture)
    view.paint(painter, QRectF(0, 0, *size))
    painter.end()
    path = Path(path)
    picture.save(str(path))
    return path
