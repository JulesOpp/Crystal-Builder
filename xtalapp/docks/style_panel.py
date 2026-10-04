"""
xtalapp.docks.style_panel
=========================
Everything about how the structure looks, in one place.

Two halves.  The top is global -- the draw style, how big atoms are,
how thick bonds are, what the labels say, whether there is a legend --
and the bottom is per element: the colour and the radius of every
element actually in the structure, each overridable and each resettable
back to the palette.

Nothing here touches the crystal.  Every control writes a ViewSettings
field through ``Document.update_view``, which means none of it lands on
the undo stack, none of it marks the document modified, and all of it
is saved with a project rather than with the CIF.  That separation is
why changing a colour cannot corrupt a structure.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.core import elements as el
from xtal.core import scalars
from xtal.core.transforms import ELLIPSOID_LEVELS
from xtalapp import docks
from xtalapp.docks.columns import Collapsible, ReflowColumns
from xtalapp.viewport import colormaps, styles
from xtalapp.viewport.scene import CUE_MIN_SPAN, cue_fraction
from xtalapp.viewport.view_settings import (
    BACKGROUNDS,
    FOLLOW_THE_SYSTEM,
    PORE_SPHERES,
    RING_COLORS,
    theme_background,
)

#: The flat colours that belong to no element: the net a chemist drew
#: over the framework, the planes the user defined, and the pore
#: network a porosity run found.  They are side by side here because
#: they are the same kind of thing -- a note about the crystal rather
#: than part of it -- and because the picture they are chosen against
#: is the same picture.
#: The largest radius an element can be drawn at, in Angstrom.
ELEMENT_RADIUS_MAX = 5.0
#: A dummy atom is a marker and not an atom, and a marker the size of
#: a pore is one of the things it is for -- so it has no ceiling worth
#: the name.  Qt needs a number.
DUMMY_RADIUS_MAX = 1e4

FLAT_COLORS = [("topology_color", "Net", "The colour of the topology "
                                         "net drawn over the bonds"),
               ("plane_color", "Planes", "The colour of every plane "
                                         "that has not been given one "
                                         "of its own in the Measure "
                                         "dock, and of its normal"),
               ("pore_color", "Pores", "The colour of the pore "
                                       "spheres a porosity run drew")]

#: The entry that stands for "none of the four".  A name rather than
#: ``None``, so that a colour picked through it is a background the
#: combo can go on showing instead of falling back to the first entry.
CUSTOM_BACKGROUND = "custom"

LABEL_MODES = [("none", "None"), ("element", "Element"),
               ("label", "Site label"), ("index", "Atom index")]
ELEMENT_COLUMNS = ["El", "Colour", "Radius"]
#: Inside each group box.  macOS's own are about twenty pixels a side,
#: which is forty a group can never give back when the column narrows.
GROUP_MARGINS = (8, 6, 8, 8)
#: The narrowest a colour swatch button may be made.
SWATCH_WIDTH = 44

#: Ring swatches to a row: four of them are 176 px with their gaps,
#: inside what a panel may ask of its column.
RING_SWATCHES_PER_ROW = 4
#: How many elements the table shows before it scrolls.
ELEMENT_ROWS = 8
# Sliders are integers; these turn a percentage into a scale factor.
SCALE_STEPS = 200
SCALE_MAX = 3.0


class PercentControl(QWidget):
    """A slider with its value beside it, in percent.

    The three fade sliders had no readout between them, and one had no
    label either: dragging one changed the picture by an amount nobody
    could read back or type again.  ``valueChanged`` is the slider's,
    so both halves move together and the signal is emitted once.
    """

    def __init__(self, tip: str, parent=None):
        super().__init__(parent)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.spin = QSpinBox()
        self.spin.setRange(0, 100)
        self.spin.setSuffix(" %")
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        for widget in (self, self.slider, self.spin):
            widget.setToolTip(tip)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        self.valueChanged = self.slider.valueChanged

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, value: int) -> None:
        self.slider.setValue(int(value))


class CuePreview(QWidget):
    """The fade drawn as a strip, front of the structure on the left
    and back on the right, against the background it fades to.

    What a start, an end and an amount *mean* is easiest to read off a
    picture of them, and this is the same arithmetic the renderer
    uses -- :func:`~xtalapp.viewport.scene.cue_fraction` -- so the
    strip cannot promise a fade the viewport does not draw.
    """

    ATOM = (110, 110, 120)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(14)
        self.setMaximumHeight(14)
        self.setToolTip("Front of the structure on the left, back on "
                        "the right")
        self.start, self.end, self.strength = 0.3, 1.0, 0.7
        self.background = (255, 255, 255)
        self.enabled = False

    def show_fade(self, enabled, start, end, strength,
                  background) -> None:
        self.enabled = bool(enabled)
        self.start, self.end = float(start), float(end)
        self.strength = float(strength)
        self.background = tuple(background)
        self.update()

    def fractions(self, n: int) -> np.ndarray:
        depth = (np.arange(n) + 0.5) / max(n, 1)
        if not self.enabled:
            return np.zeros(n)
        return cue_fraction(depth, self.start, self.end, self.strength)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        width, height = self.width(), self.height()
        atom = np.array(self.ATOM, float)
        ground = np.array(self.background, float)
        for x, amount in enumerate(self.fractions(width)):
            r, g, b = (atom + (ground - atom) * amount).astype(int)
            painter.setPen(QColor(int(r), int(g), int(b)))
            painter.drawLine(x, 0, x, height)
        painter.end()


def _background_name(color) -> str:
    """Which named background ``color`` is, or ``custom``."""
    for name, preset in BACKGROUNDS.items():
        if tuple(preset) == tuple(color):
            return name
    return CUSTOM_BACKGROUND


class StylePanelDock(QDockWidget):
    """Draw style, sizes, colours, labels and the legend."""

    def __init__(self, parent=None):
        super().__init__("Style", parent)
        self.setObjectName("StylePanelDock")
        self.document = None
        self._refreshing = False

        body = QVBoxLayout()
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(8)
        self.columns = self._build_global()
        body.addWidget(self.columns)
        # Full width and below both columns: a table is the one thing
        # here that is as wide as it is given.
        body.addWidget(self._build_elements())
        body.addStretch(1)

        inner = QWidget()
        inner.setLayout(body)
        self.setWidget(docks.scrolling(inner))
        self.set_document(None)

    # -- construction --------------------------------------------------

    def _build_global(self) -> ReflowColumns:
        """The eight groups, in the order one column reads them.

        Two columns put Drawing and Transparency -- how the atoms are
        drawn -- on the left, and Show, Scene, Colours and Depth cue --
        what is drawn with them and around them -- on the right.  One
        column was 747 px of controls with no heading anywhere, and
        the thing somebody came to change was always below the fold.
        Scene was on the left until 2026-10, which made that column
        1250 px against the right's 420.
        """
        self.groups = [self._drawing_group(), self._transparency_group(),
                       self._show_group(), self._scene_group(),
                       self._colours_group(), self._rings_group(),
                       self._color_by_group(), self._depth_cue_group()]
        return ReflowColumns(self.groups, split=2)

    @staticmethod
    def _form(title: str) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setContentsMargins(*GROUP_MARGINS)
        # A label above its field once the pair no longer fits beside
        # it, which is what lets one column go narrower than a label
        # and a combo side by side.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return box, form

    def _drawing_group(self) -> QGroupBox:
        box, form = self._form("Drawing")

        self.style = QComboBox()
        for name in styles.names():
            self.style.addItem(styles.get(name).label, name)
        # Sized to its longest style it was the widest control in the
        # panel, and the width one column could not narrow past.
        self.style.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.style.setMinimumContentsLength(8)
        self.style.currentIndexChanged.connect(
            lambda: self._set(style=self.style.currentData()))
        form.addRow("Style", self.style)

        self.atom_scale = QSlider(Qt.Horizontal)
        self.atom_scale.setRange(1, SCALE_STEPS)
        self.atom_scale.setToolTip("Atom size, relative to the style")
        self.atom_scale.valueChanged.connect(
            lambda v: self._set(atom_scale=v * SCALE_MAX / SCALE_STEPS))
        form.addRow("Atom size", self.atom_scale)

        self.bond_radius = QDoubleSpinBox()
        self.bond_radius.setRange(0.01, 1.0)
        self.bond_radius.setSingleStep(0.02)
        self.bond_radius.setDecimals(3)
        self.bond_radius.setSuffix(" A")
        self.bond_radius.valueChanged.connect(
            lambda v: self._set(bond_radius=v))
        form.addRow("Bond radius", self.bond_radius)

        # Every published ORTEP states its probability level, because
        # the same refinement at 50% and at 90% looks like two
        # different crystals.  A combo of the levels people actually
        # use rather than a free number: 50 and 90 are conventions, and
        # a picture drawn at 63% invites the question of why.
        self.ellipsoid_probability = QComboBox()
        for level in ELLIPSOID_LEVELS:
            self.ellipsoid_probability.addItem(
                f"{level * 100:g}%", level)
        self.ellipsoid_probability.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ellipsoid_probability.setMinimumContentsLength(3)
        self.ellipsoid_probability.setToolTip(
            "How much of each atom's displacement its ellipsoid "
            "encloses")
        self.ellipsoid_probability.currentIndexChanged.connect(
            lambda: self._set(ellipsoid_probability=(
                self.ellipsoid_probability.currentData())))
        # The level and the shading answer the same question -- what
        # this ellipsoid claims -- so they sit together, the shading
        # under the level: side by side they were the widest row in
        # the panel.
        self.octants = QCheckBox("Octants")
        self.octants.setToolTip(
            "ORTEP's principal sections and octant shading, drawn on "
            "the atoms refined anisotropically")
        self.octants.toggled.connect(
            lambda v: self._set(ellipsoid_octants=v))
        form.addRow("Ellipsoids", self.ellipsoid_probability)
        form.addRow("", self.octants)

        # The Skeletal style's choices, under the ellipsoids for
        # the same reason those are here: they belong to one style,
        # and are greyed under every other.
        self.carbon = QComboBox()
        self.carbon.addItem("Implicit", False)
        self.carbon.addItem("Shown as C", True)
        self.carbon.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.carbon.setMinimumContentsLength(6)
        self.carbon.setToolTip(
            "Leave carbon unwritten where lines meet, as a chemist "
            "draws it, or write every carbon as C")
        self.carbon.currentIndexChanged.connect(
            lambda: self._set(
                sketch_explicit_carbon=self.carbon.currentData()))
        self.color_labels = QCheckBox("Colour by element")
        self.color_labels.setToolTip(
            "Write each label in its element's colour rather than in "
            "ink; carbon and hydrogen stay ink")
        self.color_labels.toggled.connect(
            lambda v: self._set(sketch_color_labels=v))
        self.wedges = QComboBox()
        self.wedges.addItem("Wedges", True)
        self.wedges.addItem("Plain lines", False)
        self.wedges.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.wedges.setMinimumContentsLength(6)
        self.wedges.setToolTip(
            "Draw a bond tilted towards or away from the viewer as a "
            "solid or hashed wedge, or every single bond as a plain "
            "line")
        self.wedges.currentIndexChanged.connect(
            lambda: self._set(sketch_wedges=self.wedges.currentData()))
        self.label_box = QCheckBox("Label backgrounds")
        self.label_box.setToolTip(
            "Set each label on a box of the background, which "
            "interrupts whatever runs behind it; off writes the letters "
            "alone")
        self.label_box.toggled.connect(
            lambda v: self._set(sketch_label_box=v))
        self.box_over_pores = QCheckBox("Over pore spheres too")
        self.box_over_pores.setToolTip(
            "Let the boxes hide a pore sphere behind a label as well as "
            "the bonds; off, the sphere shows through them")
        self.box_over_pores.toggled.connect(
            lambda v: self._set(sketch_box_over_pores=v))
        form.addRow("Carbon", self.carbon)
        form.addRow("Bonds", self.wedges)
        form.addRow("", self.color_labels)
        form.addRow("", self.label_box)
        # Indented under the box it qualifies.
        indented = QWidget()
        row = QHBoxLayout(indented)
        row.setContentsMargins(18, 0, 0, 0)
        row.addWidget(self.box_over_pores)
        form.addRow("", indented)
        return box

    def _transparency_group(self) -> QGroupBox:
        box, form = self._form("Transparency")

        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setToolTip(
            "How solid coordination polyhedra are drawn")
        self.opacity.valueChanged.connect(
            lambda v: self._set(polyhedron_opacity=v / 100.0))
        form.addRow("Polyhedra", self.opacity)

        self.pore_opacity = QSlider(Qt.Horizontal)
        self.pore_opacity.setRange(5, 100)
        self.pore_opacity.setToolTip(
            "How solid the pore spheres and the channel skeleton are "
            "drawn.  The framework has to stay readable through the "
            "cavity, which is the point of drawing it there")
        self.pore_opacity.valueChanged.connect(
            lambda v: self._set(pore_opacity=v / 100.0))
        form.addRow("Pores", self.pore_opacity)

        self.ring_opacity = QSlider(Qt.Horizontal)
        self.ring_opacity.setRange(5, 100)
        self.ring_opacity.setToolTip(
            "How solid the ring faces are drawn.  The atoms and bonds "
            "they are made of have to read through them")
        self.ring_opacity.valueChanged.connect(
            lambda v: self._set(ring_opacity=v / 100.0))
        form.addRow("Rings", self.ring_opacity)
        return box

    def _scene_group(self) -> QGroupBox:
        box, form = self._form("Scene")

        # Each entry carries the *name* of a background and not the
        # colour: QComboBox.findData compares through QVariant, which
        # never matches a Python tuple against an equal one, so a combo
        # holding colours answered -1 for every background there is and
        # ``refresh`` fell back to index 0 -- the panel read White
        # whatever the picture was.  ``preferences.py`` carries names
        # for the same reason.
        self.background = QComboBox()
        # Follow the system first, as in View > Background and
        # Preferences.  Without it the panel read White or Slate over
        # a view that was following, and picking a colour here left
        # the view following -- so the next theme change painted over
        # a colour chosen by hand.
        self.background.addItem("Follow the system", FOLLOW_THE_SYSTEM)
        for name in BACKGROUNDS:
            self.background.addItem(name.capitalize(), name)
        self.background.addItem("Custom...", CUSTOM_BACKGROUND)
        self.background.currentIndexChanged.connect(
            self._on_background)
        self.background.activated.connect(self._on_custom_background)
        form.addRow("Background", self.background)

        self.labels = QComboBox()
        for value, label in LABEL_MODES:
            self.labels.addItem(label, value)
        self.labels.currentIndexChanged.connect(
            lambda: self._set(label_mode=self.labels.currentData()))
        form.addRow("Labels", self.labels)

        # Which pore sphere, here rather than in the View menu, because
        # it is a question about how much of a measurement to draw and
        # not about whether to draw it -- and because what every node
        # does to a framework has to be looked at to be believed.
        self.pore_spheres = QComboBox()
        for value, label, tip in PORE_SPHERES:
            self.pore_spheres.addItem(label, value)
            self.pore_spheres.setItemData(
                self.pore_spheres.count() - 1, tip, Qt.ToolTipRole)
        self.pore_spheres.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.pore_spheres.setMinimumContentsLength(8)
        self.pore_spheres.setToolTip(
            "Which sphere a porosity run's pores are drawn with")
        self.pore_spheres.currentIndexChanged.connect(
            lambda: self._set(
                pore_spheres=self.pore_spheres.currentData()))
        form.addRow("Pore sphere", self.pore_spheres)
        # Which cavity and which copy of it, filled from the network in
        # front: HKUST-1's D_i is at the corner and the face centres,
        # and the cage at the body centre is its second kind.
        self.pore_cavity = QComboBox()
        self.pore_cavity.setToolTip(
            "Which cavity, widest first: the first is D_i, the largest "
            "included sphere")
        self.pore_cavity.currentIndexChanged.connect(
            lambda: self._set(pore_cavity=self.pore_cavity.currentData()))
        self.pore_copy = QComboBox()
        self.pore_copy.setToolTip(
            "Which copy of that sphere in the cell, the most central "
            "first -- or every copy")
        self.pore_copy.currentIndexChanged.connect(
            lambda: self._set(pore_copy=self.pore_copy.currentData()))
        for combo in (self.pore_cavity, self.pore_copy):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy
                .AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
        form.addRow("Cavity", self.pore_cavity)
        form.addRow("Copy", self.pore_copy)

        self.legend = QCheckBox("Element legend")
        self.legend.toggled.connect(
            lambda v: self._set(show_legend=v))
        form.addRow(self.legend)
        return box

    def _show_group(self) -> QGroupBox:
        box = QGroupBox("Show")
        column = QVBoxLayout(box)
        column.setContentsMargins(*GROUP_MARGINS)

        self.cell_box = QCheckBox("Unit cell")
        self.cell_box.toggled.connect(lambda v: self._set(show_cell=v))
        self.cell_axes = QCheckBox("Cell axes")
        self.cell_axes.setToolTip(
            "The a, b, c triad in the corner of the view")
        self.cell_axes.toggled.connect(lambda v: self._set(show_axes=v))
        # The same switch as View > Show > Net.  Here as well because
        # the net is drawn over the chemistry, and the moment somebody
        # wants the atoms underneath it back they are already in this
        # dock choosing its colour.
        self.topology = QCheckBox("Net (topology bonds)")
        self.topology.setToolTip(
            "Draw the net edges laid over the framework.  Hidden, they "
            "are not picked either, so a click reaches the bond "
            "underneath")
        self.topology.toggled.connect(
            lambda v: self._set(show_topology=v))
        # The same setting as *View > Show > Pore network*, so either
        # one ticks the other.  The sphere is not part of it.
        self.pore_network = QCheckBox("Pore network")
        self.pore_network.setToolTip(
            "Draw the channel skeleton and the surface a porosity run "
            "found")
        self.pore_network.toggled.connect(
            lambda v: self._set(show_pores=v))
        # The sphere, on or off whatever the network is doing.
        self.pore_sphere_box = QCheckBox("Pore spheres")
        self.pore_sphere_box.setToolTip(
            "Draw the pore sphere a porosity run found, with or without "
            "the network")
        self.pore_sphere_box.toggled.connect(
            lambda v: self._set(show_pore_spheres=v))
        for check in (self.cell_box, self.cell_axes, self.topology,
                      self.pore_network, self.pore_sphere_box):
            column.addWidget(check)
        return box

    def _colours_group(self) -> QGroupBox:
        box = QGroupBox("Colours")
        row = QHBoxLayout(box)
        row.setContentsMargins(*GROUP_MARGINS)
        # A swatch button each, not a combo: there is no shortlist of
        # sensible net colours the way there is of backgrounds, and the
        # only question worth asking is "which one".
        self.flat = {}
        for field, label, tip in FLAT_COLORS:
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(
                lambda _checked=False, f=field, t=label:
                self._choose_flat(f, t))
            # macOS gives a push button 75 px whatever it says, which
            # three abreast made the widest row in the panel.  The
            # stylesheet swatch has no bezel to need the room.
            button.setMinimumWidth(SWATCH_WIDTH)
            self.flat[field] = button
            row.addWidget(button)
        return box

    def _rings_group(self) -> QGroupBox:
        """Rings filled by size, how large a ring is looked for, and a
        swatch per size.

        The rings are the primitive ones (:mod:`xtal.core.rings`), so
        two hexagons sharing an edge are two faces and never a third
        round the outside of both.
        """
        box, form = self._form("Rings")
        self.rings = QCheckBox("Fill rings by size")
        self.rings.setToolTip(
            "A translucent face over every ring, coloured by how many "
            "atoms it has -- the five- and seven-membered rings that "
            "curve a carbon sheet, say")
        self.rings.toggled.connect(lambda v: self._set(show_rings=v))
        form.addRow(self.rings)

        self.ring_max_size = QSpinBox()
        self.ring_max_size.setRange(3, 12)
        self.ring_max_size.setToolTip(
            "The largest ring looked for.  Each size up costs more on "
            "a large framework, and above ten it is seconds")
        self.ring_max_size.valueChanged.connect(
            lambda v: self._set(ring_max_size=v))
        form.addRow("Up to", self.ring_max_size)

        # Straight into the group's layout and not a form row: a form
        # sizes a nested widget's row before the swatches are painted,
        # and a painted button is taller than a bare one, so the second
        # row came out drawn over the first.
        grid = QGridLayout()
        grid.setSpacing(4)
        self.ring_swatches = {}
        for k, size in enumerate(RING_COLORS):
            button = QPushButton(str(size) if size < max(RING_COLORS)
                                 else f"{size}+")
            button.setToolTip(f"The colour of a {size}-membered ring"
                              if size < max(RING_COLORS) else
                              f"The colour of a ring of {size} or more")
            button.setMinimumWidth(SWATCH_WIDTH)
            # A macOS button is laid out by a rectangle inside the one
            # it paints, which a swatch fills to the edge: stacked two
            # rows deep, each row was drawn over the one above.
            button.setAttribute(Qt.WA_LayoutUsesWidgetRect)
            button.clicked.connect(
                lambda _checked=False, n=size: self._choose_ring(n))
            self.ring_swatches[size] = button
            grid.addWidget(button, k // RING_SWATCHES_PER_ROW,
                           k % RING_SWATCHES_PER_ROW)
        form.addRow(grid)
        return box

    def _color_by_group(self) -> QGroupBox:
        """Colour by a number per atom or per bond, the map it is
        drawn in, and the range the map spans.

        Nothing chosen here is written over the element colours, so
        *Element* puts back whatever was chosen for them by hand.
        """
        box, form = self._form("Colour by")
        self.color_by = QComboBox()
        self.color_by.addItem("Element", "")
        for quantity in scalars.QUANTITIES.values():
            self.color_by.addItem(quantity.label, quantity.name)
        self.color_by.setToolTip(
            "Colour every atom, or every bond, by a number instead of "
            "its element.  Grey is a value that does not exist -- an "
            "atom with one neighbour has no angle -- and is off the "
            "scale")
        self.color_by.currentIndexChanged.connect(
            lambda _i: self._set(color_by=self.color_by.currentData(),
                                 color_range=None))
        form.addRow("Colour", self.color_by)

        self.color_map = QComboBox()
        for name in colormaps.COLOR_MAPS:
            self.color_map.addItem(name, name)
        self.color_map.setToolTip(
            "Viridis and plasma for a quantity that only grows; "
            "coolwarm for one whose middle means something")
        self.color_map.currentIndexChanged.connect(
            lambda _i: self._set(color_map=self.color_map.currentData()))
        form.addRow("Map", self.color_map)

        self.color_auto = QCheckBox("Range from the values")
        self.color_auto.setToolTip(
            "Span the map from the least value in the cell to the "
            "greatest.  Untick to set the ends, so two structures can "
            "be coloured on one scale")
        self.color_auto.toggled.connect(self._on_color_auto)
        form.addRow(self.color_auto)

        self.color_lo = QDoubleSpinBox()
        self.color_hi = QDoubleSpinBox()
        for spin, tip in ((self.color_lo, "The value at the bottom of "
                           "the map.  Anything below it is drawn as it"),
                          (self.color_hi, "The value at the top of the "
                           "map.  Anything above it is drawn as it")):
            spin.setRange(-1e4, 1e4)
            spin.setDecimals(3)
            spin.setToolTip(tip)
            spin.editingFinished.connect(self._on_color_range)
        form.addRow("From", self.color_lo)
        form.addRow("To", self.color_hi)
        return box

    def _depth_cue_group(self) -> QGroupBox:
        """Folded unless the document has it on: three sliders and a
        strip are the tallest group here, and for the structures that
        do not fade -- most of them -- they are the ones in the way.
        The switch stays in the header, so on or off reads without
        opening it."""
        box = QGroupBox("Depth cue")
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        # A switch, then three numbers that each say what they are
        # and show their value, then a picture of the result.  It was
        # one unlabelled slider beside the checkbox, "Fade from" as a
        # fraction of a bounding box, and an exponent called a
        # gradient -- and nobody could say what any of them would do
        # before dragging it.
        # "On" rather than the group's name again: it sits under the
        # heading that already says what it turns on.
        self.depth_cue = QCheckBox("On")
        self.depth_cue.setToolTip(
            "Fade distant atoms towards the background, so a thick "
            "slab reads as having depth")
        self.depth_cue.toggled.connect(self._on_depth_cue)

        # Percent of the atoms' depth, front to back: 0% is the
        # nearest atom and 100% the farthest, whichever way the
        # structure is turned.
        self.depth_cue_start = PercentControl(
            "Atoms nearer than this are not faded at all.  0% is the "
            "front of the nearest atom, 100% the back of the farthest")
        self.depth_cue_start.valueChanged.connect(self._on_cue_start)
        form.addRow("Fade starts at", self.depth_cue_start)

        self.depth_cue_end = PercentControl(
            "Atoms farther than this are faded by the whole amount")
        self.depth_cue_end.valueChanged.connect(self._on_cue_end)
        form.addRow("Fully faded at", self.depth_cue_end)

        self.depth_cue_strength = PercentControl(
            "How far into the background the fade goes: at 100% the "
            "farthest atoms disappear into it")
        self.depth_cue_strength.valueChanged.connect(
            lambda v: self._set(depth_cue_strength=v / 100.0))
        form.addRow("Amount", self.depth_cue_strength)

        self.depth_cue_preview = CuePreview()
        form.addRow(self.depth_cue_preview)

        self.depth_cue_fold = Collapsible("Depth cue", body,
                                          switch=self.depth_cue)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(*GROUP_MARGINS)
        inner.addWidget(self.depth_cue_fold)
        return box

    def _build_elements(self) -> QWidget:
        self.elements = QTableWidget(0, len(ELEMENT_COLUMNS))
        self.elements.setHorizontalHeaderLabels(ELEMENT_COLUMNS)
        self.elements.verticalHeader().setVisible(False)
        self.elements.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        self.elements.setEditTriggers(QTableWidget.NoEditTriggers)
        self.elements.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.elements.cellDoubleClicked.connect(self._on_element_cell)
        # A set number of rows that scroll inside the table.  Stretched
        # to fill the panel it was 4 rows of MOF-5 and 400 px of white,
        # and it pushed everything above it apart as the column grew.
        header = self.elements.horizontalHeader().sizeHint().height()
        row = self.elements.verticalHeader().defaultSectionSize()
        frame = 2 * self.elements.frameWidth()
        self.elements.setFixedHeight(header + ELEMENT_ROWS * row + frame)

        reset = QPushButton("Reset colours and radii")
        reset.setToolTip(
            "Back to the element palette and the standard radii")
        reset.clicked.connect(self.reset_elements)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.elements)
        layout.addWidget(reset)
        page = QWidget()
        page.setLayout(layout)
        return page

    # -- binding -------------------------------------------------------

    def set_document(self, document) -> None:
        changed = document is not self.document
        self.document = document
        self.refresh()
        # Open for a document that fades, folded for one that does not
        # -- and only when the document changes, so a fold somebody
        # opened by hand stays open while they work in it.
        if changed:
            self.depth_cue_fold.set_open(
                document is not None and document.view.depth_cue)

    def refresh(self) -> None:
        document = self.document
        self.widget().setEnabled(document is not None)
        if document is None:
            self.elements.setRowCount(0)
            return

        view = document.view
        self._refreshing = True
        self._choose(self.style, view.style)
        self.atom_scale.setValue(
            max(1, round(view.atom_scale * SCALE_STEPS / SCALE_MAX)))
        self.bond_radius.setValue(view.bond_radius)
        self.opacity.setValue(round(view.polyhedron_opacity * 100))
        self._choose(self.labels, view.label_mode)
        self._choose(self.background,
                     FOLLOW_THE_SYSTEM if view.background_follows_theme
                     else _background_name(view.background))
        self._choose(self.ellipsoid_probability,
                     view.ellipsoid_probability)
        ellipsoids = styles.get(view.style).ellipsoids
        self.ellipsoid_probability.setEnabled(ellipsoids)
        self.octants.setChecked(view.ellipsoid_octants)
        self.octants.setEnabled(ellipsoids)
        labelled = styles.get(view.style).atom_render == "label"
        self._choose(self.carbon, view.sketch_explicit_carbon)
        self.carbon.setEnabled(labelled)
        self._choose(self.wedges, view.sketch_wedges)
        self.wedges.setEnabled(labelled)
        self.color_labels.setChecked(view.sketch_color_labels)
        self.color_labels.setEnabled(labelled)
        self.label_box.setChecked(view.sketch_label_box)
        self.label_box.setEnabled(labelled)
        self.box_over_pores.setChecked(view.sketch_box_over_pores)
        self.box_over_pores.setEnabled(labelled and view.sketch_label_box)
        # A label style draws no sphere and no tube, so neither size
        # means anything under it.
        self.atom_scale.setEnabled(not labelled)
        self.bond_radius.setEnabled(not labelled)
        self.depth_cue.setChecked(view.depth_cue)
        self.depth_cue_strength.setValue(
            round(view.depth_cue_strength * 100))
        self.depth_cue_start.setValue(round(view.depth_cue_start * 100))
        self.depth_cue_end.setValue(round(view.depth_cue_end * 100))
        for control in (self.depth_cue_strength, self.depth_cue_start,
                        self.depth_cue_end):
            control.setEnabled(view.depth_cue)
        self.depth_cue_preview.show_fade(
            view.depth_cue, view.depth_cue_start, view.depth_cue_end,
            view.depth_cue_strength, view.background)
        for field, button in self.flat.items():
            self._paint(button, getattr(view, field))
        self.pore_opacity.setValue(round(view.pore_opacity * 100))
        self.ring_opacity.setValue(round(view.ring_opacity * 100))
        self.rings.setChecked(view.show_rings)
        self.ring_max_size.setValue(view.ring_max_size)
        self.ring_max_size.setEnabled(view.show_rings)
        for size, button in self.ring_swatches.items():
            self._paint(button, view.ring_color(size))
        self._choose(self.color_by, view.color_by)
        self._choose(self.color_map, view.color_map)
        coloring = bool(view.color_by)
        self.color_map.setEnabled(coloring)
        self.color_auto.setChecked(view.color_range is None)
        self.color_auto.setEnabled(coloring)
        if view.color_range is not None:
            self.color_lo.setValue(view.color_range[0])
            self.color_hi.setValue(view.color_range[1])
        for spin in (self.color_lo, self.color_hi):
            spin.setEnabled(coloring and view.color_range is not None)
        self.legend.setChecked(view.show_legend)
        self.cell_box.setChecked(view.show_cell)
        self.cell_axes.setChecked(view.show_axes)
        self.topology.setChecked(view.show_topology)
        self._choose(self.pore_spheres, view.pore_spheres)
        self.pore_network.setChecked(view.show_pores)
        self.pore_sphere_box.setChecked(view.show_pore_spheres)
        self.pore_spheres.setEnabled(view.show_pore_spheres)
        self._fill_pore_choices(document, view)
        self._refreshing = False
        self._fill_elements()

    @staticmethod
    def _paint(button: QPushButton, color) -> None:
        """Show a colour on the button that changes it.

        The swatch is the label's background rather than an icon
        because a stylesheet survives the button being disabled with
        no document open, and an icon rendered once does not.
        """
        r, g, b = (int(c) for c in color)
        # Black text on a light swatch and white on a dark one: a
        # fixed ink colour is unreadable against half of the range
        # the dialog can return, and the label is what says which
        # button this is.
        ink = "#000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 \
            else "#fff"
        button.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); color: {ink};")

    def _fill_pore_choices(self, document, view) -> None:
        """The cavities of the network in front, and the copies of the
        one chosen; empty and greyed where there is nothing to choose
        between."""
        network = document.pores
        lattice = document.structure.lattice
        kinds = found = None
        if network is not None and view.pore_spheres == "largest":
            kinds = network.cavities(lattice)
            if kinds:
                found = kinds[min(max(view.pore_cavity, 0),
                                  len(kinds) - 1)]
        elif (network is not None and view.pore_spheres == "along_free"
              and network.included_along_free is not None):
            found = network.copies_of(network.included_along_free,
                                      lattice)
        for combo in (self.pore_cavity, self.pore_copy):
            combo.blockSignals(True)
            combo.clear()
        for k, kind in enumerate(kinds or ()):
            self.pore_cavity.addItem(
                f"{2 * kind.radius:.2f} A" + (" (D_i)" if k == 0 else ""),
                k)
        if found is not None:
            n = len(found.copies)
            for k, place in enumerate(found.copies):
                self.pore_copy.addItem(f"{k + 1} of {n}", k)
                self.pore_copy.setItemData(
                    k, "at " + ", ".join(f"{x:.3f}" for x in place),
                    Qt.ToolTipRole)
            if n > 1:
                self.pore_copy.addItem(f"All {n}", -1)
        self.pore_cavity.setCurrentIndex(
            min(max(view.pore_cavity, 0), self.pore_cavity.count() - 1))
        # Past the end is the last copy, as the drawing clamps it.
        copies = 0 if found is None else len(found.copies)
        every = self.pore_copy.findData(-1)
        self.pore_copy.setCurrentIndex(
            max(every, 0) if view.pore_copy < 0
            else min(view.pore_copy, max(copies - 1, 0)))
        for combo in (self.pore_cavity, self.pore_copy):
            combo.blockSignals(False)
        self.pore_cavity.setEnabled(view.show_pore_spheres
                                    and self.pore_cavity.count() > 1)
        self.pore_copy.setEnabled(view.show_pore_spheres
                                  and self.pore_copy.count() > 1)

    @staticmethod
    def _choose(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _fill_elements(self) -> None:
        document = self.document
        symbols = sorted(document.structure.elements,
                         key=el.atomic_number)
        view = document.view
        self.elements.setRowCount(len(symbols))
        for row, symbol in enumerate(symbols):
            color = view.color_for(symbol)
            radius = view.base_radius(symbol, "covalent")

            name = QTableWidgetItem(symbol)
            name.setData(Qt.UserRole, symbol)
            swatch = QTableWidgetItem("")
            swatch.setBackground(QColor(*color))
            swatch.setToolTip("Double-click to choose a colour")
            size = QTableWidgetItem(f"{radius:.3f}")
            size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size.setToolTip("Double-click to set the radius")
            for column, item in enumerate((name, swatch, size)):
                self.elements.setItem(row, column, item)

    # -- editing -------------------------------------------------------

    def _set(self, **values) -> None:
        if self._refreshing or self.document is None:
            return
        self.document.update_view(**values)

    def _on_depth_cue(self, on: bool) -> None:
        # Turned on with its settings folded away, the next thing
        # anybody wants is those settings.
        if on and not self._refreshing:
            self.depth_cue_fold.set_open(True)
        self._set(depth_cue=on)

    def _on_cue_start(self, value: int) -> None:
        """A start dragged past the end pushes the end along, rather
        than the slider refusing to move -- which reads as broken."""
        gap = round(CUE_MIN_SPAN * 100)
        if not self._refreshing and value > self.depth_cue_end.value() \
                - gap:
            end = min(100, value + gap)
            self._set(depth_cue_start=(end - gap) / 100.0,
                      depth_cue_end=end / 100.0)
            return
        self._set(depth_cue_start=value / 100.0)

    def _on_cue_end(self, value: int) -> None:
        gap = round(CUE_MIN_SPAN * 100)
        if not self._refreshing and value < \
                self.depth_cue_start.value() + gap:
            start = max(0, value - gap)
            self._set(depth_cue_start=start / 100.0,
                      depth_cue_end=(start + gap) / 100.0)
            return
        self._set(depth_cue_end=value / 100.0)

    def _on_background(self, _index: int) -> None:
        """One of the four named backgrounds, or following the system."""
        name = self.background.currentData()
        if name == FOLLOW_THE_SYSTEM:
            self._set(background=theme_background(),
                      background_follows_theme=True)
            return
        color = BACKGROUNDS.get(name)
        if color is not None:
            self._set(background=tuple(color),
                      background_follows_theme=False)

    def _on_custom_background(self, index: int) -> None:
        """*Custom...*, which is a button wearing a combo entry.

        On ``activated`` rather than ``currentIndexChanged`` because
        the entry now *stays* showing once a colour has been picked
        through it, and a combo does not report the entry that is
        already current being chosen again -- so the second visit to
        the colour dialog would have nothing to open it.
        """
        if (self.background.itemData(index) != CUSTOM_BACKGROUND
                or self._refreshing or self.document is None):
            return
        current = QColor(*self.document.view.background)
        chosen = QColorDialog.getColor(current, self, "Background")
        if chosen.isValid():
            self._set(background=(chosen.red(), chosen.green(),
                                  chosen.blue()),
                      background_follows_theme=False)
        else:
            self.refresh()              # put the old choice back

    def _choose_flat(self, field: str, title: str) -> None:
        if self.document is None:
            return
        current = QColor(*getattr(self.document.view, field))
        chosen = QColorDialog.getColor(current, self, f"{title} colour")
        if chosen.isValid():
            self._set(**{field: (chosen.red(), chosen.green(),
                                 chosen.blue())})

    def _choose_ring(self, size: int) -> None:
        if self.document is None:
            return
        view = self.document.view
        chosen = QColorDialog.getColor(
            QColor(*view.ring_color(size)), self,
            f"{size}-ring colour")
        if chosen.isValid():
            colors = dict(view.ring_colors)
            colors[size] = (chosen.red(), chosen.green(), chosen.blue())
            self._set(ring_colors=colors)

    def _on_color_auto(self, on: bool) -> None:
        """Unticked, the ends start where the values put them, so the
        picture does not jump before anybody has typed a number."""
        if self._refreshing or self.document is None:
            return
        if on:
            self._set(color_range=None)
            return
        view = self.document.view
        span = scalars.auto_range(scalars.values(
            self.document.structure, view.color_by,
            max_ring=view.ring_max_size)) if view.color_by else None
        self._set(color_range=span or (0.0, 1.0))

    def _on_color_range(self) -> None:
        if self.document is None or self.document.view.color_range is None:
            return
        span = (self.color_lo.value(), self.color_hi.value())
        if span != tuple(self.document.view.color_range):
            self._set(color_range=span)

    def _on_element_cell(self, row: int, column: int) -> None:
        item = self.elements.item(row, 0)
        if item is None or self.document is None:
            return
        symbol = item.data(Qt.UserRole)
        if column == 1:
            self._choose_color(symbol)
        elif column == 2:
            self._choose_radius(symbol)

    def _choose_color(self, symbol: str) -> None:
        view = self.document.view
        chosen = QColorDialog.getColor(
            QColor(*view.color_for(symbol)), self, f"{symbol} colour")
        if not chosen.isValid():
            return
        colors = dict(view.element_colors)
        colors[symbol] = (chosen.red(), chosen.green(), chosen.blue())
        self.document.update_view(element_colors=colors)

    def _choose_radius(self, symbol: str) -> None:
        from PySide6.QtWidgets import QInputDialog

        view = self.document.view
        value, ok = QInputDialog.getDouble(
            self, f"{symbol} radius", "Radius (A):",
            view.base_radius(symbol, "covalent"), 0.05,
            DUMMY_RADIUS_MAX if el.is_dummy(symbol)
            else ELEMENT_RADIUS_MAX, 3)
        if not ok:
            return
        radii = dict(view.element_radii)
        radii[symbol] = float(value)
        self.document.update_view(element_radii=radii)

    def reset_elements(self) -> None:
        if self.document is not None:
            self.document.update_view(element_colors={},
                                      element_radii={})
