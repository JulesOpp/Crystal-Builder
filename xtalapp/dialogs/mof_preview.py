"""
xtalapp.dialogs.mof_preview
===========================
Pictures of the two things a framework is built out of.

PORMAKE ships 2399 nets and 867 building blocks, and their names are
``pcu``, ``rht``, ``N59`` and ``E32``.  A three-letter RCSR symbol is
precise and says nothing to somebody who has not memorised it, and
``N59`` says less: a picker that offers 210 six-connected blocks by
name is a list nobody can choose from.  So both are drawn.

Drawn by hand with ``QPainter``, for the reason :mod:`xtalapp.plot`
gives: the alternative is a second large dependency for two small
widgets, and a hundred lines of painting follows the user's theme for
free.  The 3D viewport is not the alternative either -- it needs a GL
context, a document and a structure, and a building block is none of
those.

**Both are projections and neither is a structure.**  The point of
each picture is recognition -- is that the linear linker or the bent
one, is that net a cube or a diamond -- and recognition survives an
orthographic projection.  It does not always survive a *fixed* angle:
a block is flattened onto its own widest plane, which shows what it
is, but a net whose defining feature is edge-on from the one
direction chosen for it is a picture of a different net.  So the net
turns under a drag, the way the viewport does, and a double-click puts
it back.  It is still painted: a rotation matrix before the
projection, not a GL context.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from xtal.core import elements as el

#: A viewing direction that is not down any axis.  A cubic net drawn
#: along **z** is a square with every edge behind another one, which
#: is the one orientation that hides what makes it a cube.
_VIEW = np.array([
    [0.8660, -0.2500, 0.4330],
    [0.0000, 0.8660, 0.5000],
])

MARGIN = 10
#: Radii on screen, in pixels at the smallest sensible size.  Not the
#: real ratio: hydrogen at its true covalent radius beside cadmium is
#: a dot, and this picture is for telling shapes apart.
MIN_RADIUS = 2.2
MAX_RADIUS = 6.5


#: :data:`_VIEW` as a whole rotation, its third row the direction
#: towards the viewer.  Where a net picture starts and goes back to.
DEFAULT_ROTATION = np.vstack([_VIEW, np.cross(_VIEW[0], _VIEW[1])])


def _project(points: np.ndarray, view=_VIEW) -> np.ndarray:
    """Cartesian points to the plane of the page, seen through
    ``view`` -- its first two rows are the page's x and y."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if not len(points):
        return np.zeros((0, 2))
    return points @ np.asarray(view, dtype=float)[:2].T


def _turned(rotation: np.ndarray, dx: float, dy: float,
            radius: float) -> np.ndarray:
    """``rotation`` after a drag of ``(dx, dy)`` screen pixels.

    A trackball at the rate Move's alt-drag uses, one radius of travel
    to the radian: across the picture turns about the page's up axis,
    down it about the page's right, and the front of the net follows
    the pointer both ways.  Applied in the page's own frame, so it
    turns the way the picture looks and not the way the cell is.
    """
    travel = float(np.hypot(dx, dy))
    if travel < 1e-9 or radius <= 0:
        return rotation
    # Screen y grows downwards; the page's y upwards.  A drag right is
    # a turn about +y, which carries +z (towards the viewer) to +x; a
    # drag down is a turn about +x, which carries +z to -y.
    axis = np.array([dy, dx, 0.0]) / travel
    angle = travel / radius
    k = np.array([[0.0, -axis[2], axis[1]],
                  [axis[2], 0.0, -axis[0]],
                  [-axis[1], axis[0], 0.0]])
    turn = (np.eye(3) + np.sin(angle) * k
            + (1 - np.cos(angle)) * (k @ k))
    return turn @ rotation


def _fit(flat: np.ndarray, rect: QRectF, pad: float):
    """The scale and offset that put ``flat`` inside ``rect``.

    Isotropic, because a picture of a molecule squeezed to fill a
    wide box is a picture of a different molecule.
    """
    low, high = flat.min(axis=0), flat.max(axis=0)
    span = np.maximum(high - low, 1e-6)
    usable = np.array([max(rect.width() - 2 * pad, 1.0),
                       max(rect.height() - 2 * pad, 1.0)])
    scale = float(np.min(usable / span))
    centre = (low + high) / 2
    middle = np.array([rect.center().x(), rect.center().y()])
    return scale, middle, centre


def _placed(flat: np.ndarray, rect: QRectF, pad: float):
    """``flat`` as screen points, y down."""
    scale, middle, centre = _fit(flat, rect, pad)
    out = (flat - centre) * scale
    out[:, 1] *= -1                     # screen y grows downwards
    return out + middle, scale


class _Preview(QWidget):
    """What both pictures share: a box, a border and an empty state."""

    empty_text = ""

    def __init__(self, parent=None, minimum=(210, 170)):
        super().__init__(parent)
        self.setMinimumSize(*minimum)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self._caption = ""

    def paintEvent(self, event) -> None:            # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.fillRect(rect, self.palette().base())
        painter.setPen(QPen(self.palette().color(
            self.palette().ColorRole.Mid), 1))
        painter.drawRect(rect)
        body = rect.adjusted(MARGIN, MARGIN, -MARGIN,
                             -MARGIN - self._caption_height())
        if not self._draw(painter, body):
            painter.setPen(self.palette().color(
                self.palette().ColorRole.PlaceholderText))
            painter.drawText(rect, Qt.AlignCenter, self.empty_text)
        elif self._caption:
            painter.setPen(self.palette().color(
                self.palette().ColorRole.PlaceholderText))
            painter.drawText(
                QRectF(rect.left(),
                       rect.bottom() - self._caption_height() - 2,
                       rect.width(), self._caption_height()),
                Qt.AlignCenter, self._caption)
        painter.end()

    def _caption_height(self) -> float:
        return self.fontMetrics().height() + 2 if self._caption else 0

    def _draw(self, painter, rect) -> bool:
        raise NotImplementedError                   # pragma: no cover


# ======================================================================
#  A BUILDING BLOCK
# ======================================================================

class BlockPreview(_Preview):
    """One building block, with its connection points marked.

    The connection points are the whole reason to look: what
    distinguishes two four-connected blocks is where the four arms
    point, and a picture that drew only the atoms would leave out the
    thing being chosen between.  So they are drawn as open rings on
    dashed stalks, and the atoms are drawn as the molecule they are.

    The projection is onto the block's own two widest directions
    rather than a fixed one.  A linker is nearly planar and a fixed
    angle would show a third of them end-on, as a line.
    """

    empty_text = "no building block"

    def __init__(self, parent=None, minimum=(210, 170)):
        super().__init__(parent, minimum)
        self._block = None

    def set_block(self, block) -> None:
        self._block = block
        self._caption = f"{block.name}  ·  {block.formula}" \
            if block is not None else ""
        self.update()

    def _draw(self, painter, rect) -> bool:
        block = self._block
        if block is None or not len(block.positions):
            return False
        flat = _flatten(block.positions)
        points, scale = _placed(flat, rect, MAX_RADIUS + 2)
        connections = set(block.connections)
        _draw_bonds(painter, block, points, connections,
                    self.palette())
        for index, symbol in enumerate(block.symbols):
            centre = QPointF(points[index][0], points[index][1])
            if index in connections or symbol == "X":
                _draw_connection(painter, centre)
            else:
                _draw_atom(painter, centre, symbol, scale)
        return True


def _flatten(positions: np.ndarray) -> np.ndarray:
    """A block's atoms, seen from the direction that shows the most.

    The two principal axes of the positions, which for a linker is
    its long axis and the plane of its rings, and for a metal node is
    whichever two directions its arms spread furthest in.  A block
    seen down its own short axis is a picture of a line.
    """
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    if len(positions) < 3:
        return _project(positions)
    centred = positions - positions.mean(axis=0)
    try:
        _u, _s, axes = np.linalg.svd(centred, full_matrices=False)
    except np.linalg.LinAlgError:                   # pragma: no cover
        return _project(positions)
    return centred @ axes[:2].T


def _draw_bonds(painter, block, points, connections, palette) -> None:
    """Every pair close enough to be bonded, as a line.

    Distance against the covalent radii, the same rule the
    application's own perception starts from -- a building block is an
    XYZ with no bonds in it, and a picture of unbonded atoms is a
    cloud of dots.
    """
    painter.setPen(QPen(palette.color(palette.ColorRole.Mid), 1.4))
    positions = np.asarray(block.positions, dtype=float)
    radii = [1.0 if (i in connections or s == "X")
             else el.covalent_radius(s)
             for i, s in enumerate(block.symbols)]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            limit = radii[i] + radii[j] + 0.45
            if float(np.linalg.norm(positions[i] - positions[j])) \
                    > limit:
                continue
            dashed = i in connections or j in connections
            painter.setPen(QPen(
                palette.color(palette.ColorRole.Mid), 1.4,
                Qt.DashLine if dashed else Qt.SolidLine))
            painter.drawLine(QPointF(*points[i]), QPointF(*points[j]))


def _draw_atom(painter, centre, symbol: str, scale: float) -> None:
    red, green, blue = el.color(symbol)
    radius = float(np.clip(el.covalent_radius(symbol) * 3.2,
                           MIN_RADIUS, MAX_RADIUS))
    painter.setBrush(QColor(red, green, blue))
    painter.setPen(QPen(QColor(red // 2, green // 2, blue // 2), 1))
    painter.drawEllipse(centre, radius, radius)


def _draw_connection(painter, centre) -> None:
    """A connection point: an open ring, not an atom.

    It is not one -- it is where a bond to the next block will be --
    and drawing it as a filled sphere in some element's colour would
    say the framework has an atom there that it will not have.
    """
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(200, 60, 60), 1.6))
    painter.drawEllipse(centre, MAX_RADIUS - 1, MAX_RADIUS - 1)


# ======================================================================
#  A NET
# ======================================================================

#: One colour per node type.  A net with two kinds of vertex is a net
#: that will be built out of two kinds of node, and which is which is
#: the question the slots below the picture are about.
ORBIT_COLORS = (QColor(58, 122, 200), QColor(206, 110, 40),
                QColor(76, 160, 92), QColor(160, 84, 176),
                QColor(200, 170, 40))


#: How much of an edge that leaves the block is drawn.  A stub rather
#: than the whole line: the point of drawing it at all is that the net
#: continues, and a full-length edge to a vertex that is not there
#: reads as a bond to nothing.
STUB = 0.28

#: How many vertices a picture may hold.  Above it the dots merge and
#: the picture stops being a picture; below it a one-vertex net drawn
#: in one cell is a star with six spokes rather than a cube.
BUSY = 250


class NetPreview(_Preview):
    """A few cells of a topology, as vertices and edges.

    **A net is drawn repeated, not one cell of it.**  One cell of
    **pcu** is a single vertex with six half-edges leaving it, which
    is exactly what pcu is and looks nothing like the cube everybody
    knows it as.  So the cell is repeated until there are enough
    vertices to see the shape and no more than the box can hold.

    Vertices are coloured by node type, in the same order the slot
    rows below ask about them, so "node 2" in the form and the orange
    vertices in the picture are the same thing.

    Edges that leave the block are drawn as stubs.  Wrapping them back
    in would draw a line from one side of the picture to the other,
    which reads as a bond between two vertices that are not
    neighbours; leaving them out would show a framework that stops.
    """

    empty_text = "no topology"

    def __init__(self, parent=None, minimum=(210, 170)):
        super().__init__(parent, minimum)
        self._topology = None
        self._drawing = None
        self._rotation = DEFAULT_ROTATION.copy()
        self._pressed = None
        self.setToolTip("Drag to turn the net; double-click to put it "
                        "back")
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_topology(self, topology) -> None:
        self._topology = topology
        self._drawing = None
        # A new net starts where every net starts, so that two nets
        # can be compared by clicking between them.
        self._rotation = DEFAULT_ROTATION.copy()
        self._caption = topology.name if topology is not None else ""
        if topology is not None:
            try:
                self._drawing = _net_drawing(topology)
            except Exception:                       # noqa: BLE001
                # A net whose file cannot be expanded still has a name
                # and still builds; the picture is what is missing,
                # and the panel beside it says the rest.
                self._drawing = None
                self._caption = f"{topology.name}  ·  no picture"
        self.update()

    # -- turning -------------------------------------------------------

    @property
    def rotation(self) -> np.ndarray:
        return self._rotation.copy()

    def turn_by(self, dx: float, dy: float) -> None:
        """Turn as a drag of ``(dx, dy)`` pixels would."""
        radius = min(self.width(), self.height()) / 2
        self._rotation = _turned(self._rotation, dx, dy, radius)
        self.update()

    def reset_view(self) -> None:
        self._rotation = DEFAULT_ROTATION.copy()
        self.update()

    def mousePressEvent(self, event) -> None:       # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        if self._pressed is not None and \
                event.buttons() & Qt.MouseButton.LeftButton:
            here = event.position()
            self.turn_by(here.x() - self._pressed.x(),
                         here.y() - self._pressed.y())
            self._pressed = here
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802
        self._pressed = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.reset_view()
        super().mouseDoubleClickEvent(event)

    # -- drawing -------------------------------------------------------

    def screen_points(self, rect: QRectF):
        """``(vertices, edge ends)`` as screen points in ``rect``.

        Fitted to the net's **bounding sphere** rather than to the box
        its projection happens to fill: a box fit rescales at every
        step of a turn, and a picture that breathes while it turns is
        one whose shape cannot be read off it.  The sphere holds every
        view, so nothing leaves the box at any angle either.
        """
        cart, _orbits, lines = self._drawing
        everything = np.vstack([cart, lines.reshape(-1, 3)]) \
            if len(lines) else cart
        centre = (everything.min(axis=0) + everything.max(axis=0)) / 2
        radius = max(float(np.max(np.linalg.norm(everything - centre,
                                                 axis=1))), 1e-6)
        pad = 6
        usable = min(rect.width(), rect.height()) - 2 * pad
        scale = max(usable, 1.0) / (2 * radius)
        flat = _project(everything - centre, self._rotation) * scale
        flat[:, 1] *= -1                    # screen y grows downwards
        flat += np.array([rect.center().x(), rect.center().y()])
        return flat[:len(cart)], flat[len(cart):].reshape(-1, 2, 2)

    def _draw(self, painter, rect) -> bool:
        if self._drawing is None:
            return False
        cart, orbits, _lines = self._drawing
        points, ends = self.screen_points(rect)
        painter.setPen(QPen(self.palette().color(
            self.palette().ColorRole.Mid), 1.3))
        for start, stop in ends:
            painter.drawLine(QPointF(*start), QPointF(*stop))
        for index in range(len(cart)):
            _draw_vertex(painter, QPointF(*points[index]),
                         orbits[index])
        return True


def _draw_vertex(painter, centre, orbit: int) -> None:
    colour = ORBIT_COLORS[orbit % len(ORBIT_COLORS)]
    painter.setBrush(colour)
    painter.setPen(QPen(colour.darker(150), 1))
    painter.drawEllipse(centre, 3.6, 3.6)


def _net_drawing(topology):
    """``(vertex positions, node type each, edges as pairs of points)``.

    Cartesian, in the cell the ``.cgd`` states, because a hexagonal
    net drawn in a cube is a picture of a different net.
    """
    net, frac = topology.placement()
    lattice = topology.lattice()
    frac = _padded(frac)
    repeat = _repeat(net.n_vertices)
    cells = [(i, j, k) for i in range(repeat)
             for j in range(repeat) for k in range(repeat)]
    at = {(v, cell): index
          for index, (cell, v) in enumerate(
              (c, v) for c in cells for v in range(net.n_vertices))}
    cart = lattice.to_cart(np.array(
        [frac[v] + np.asarray(cell, dtype=float)
         for cell, v in ((c, v) for c in cells
                         for v in range(net.n_vertices))]))
    orbits = [net.orbits[v] for _cell in cells
              for v in range(net.n_vertices)]
    lines = []
    for cell in cells:
        for edge in net.edges:
            # Both directions, because an edge is stored once and a
            # vertex has to show all of its coordination: the forward
            # placement puts ``i`` in the block and ``j`` wherever the
            # image says, and the backward one puts ``j`` in the block
            # instead.  Drawing only the first leaves every vertex
            # that is never an edge's first end sitting on its own.
            forward = tuple(c + i for c, i in
                            zip(cell, edge.image, strict=True))
            backward = tuple(c - i for c, i in
                             zip(cell, edge.image, strict=True))
            if (edge.j, forward) in at:
                lines.append((cart[at[(edge.i, cell)]],
                              cart[at[(edge.j, forward)]]))
            else:
                lines.append(_stub(cart[at[(edge.i, cell)]], lattice,
                                   frac[edge.j], forward))
            if (edge.i, backward) not in at:
                lines.append(_stub(cart[at[(edge.j, cell)]], lattice,
                                   frac[edge.i], backward))
    return cart, orbits, np.asarray(lines, dtype=float)


def _stub(start, lattice, frac, cell):
    """The first bit of an edge that leaves the block."""
    stop = lattice.to_cart(frac + np.asarray(cell, dtype=float))
    return (start, start + STUB * (stop - start))


def _repeat(n_vertices: int) -> int:
    """How many cells along each axis to draw.

    Two whenever two will fit, which is what turns pcu from a star
    into a cube; one for the nets that already have fifty vertices in
    a single cell and need no help being recognised.
    """
    return 2 if n_vertices * 8 <= BUSY else 1


def _padded(frac: np.ndarray) -> np.ndarray:
    """Two-dimensional vertices, in the three-dimensional cell they
    are drawn in.  A layer net is flat and drawing it flat is right."""
    frac = np.asarray(frac, dtype=float)
    if frac.shape[1] == 3:
        return frac
    return np.column_stack([frac, np.zeros(len(frac))])


def reset_view_row(preview) -> QHBoxLayout:
    """A Reset view button, right-aligned under a net picture.

    A double-click puts the net back as well, but a double-click is a
    gesture nobody finds by looking; a button is.  Not auto-default: a
    dialog's push buttons take Return unless told otherwise, and
    Return belongs to the button that builds.
    """
    button = QPushButton("Reset view")
    button.setAutoDefault(False)
    button.setToolTip("Put the net back to the angle it opened at")
    button.clicked.connect(preview.reset_view)
    preview.reset_button = button
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch(1)
    row.addWidget(button)
    return row
