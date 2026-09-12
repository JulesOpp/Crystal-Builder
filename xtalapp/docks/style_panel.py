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
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.core import elements as el
from xtal.core.transforms import ELLIPSOID_LEVELS
from xtalapp.viewport import styles
from xtalapp.viewport.scene import CUE_MIN_SPAN, cue_fraction
from xtalapp.viewport.view_settings import BACKGROUNDS

#: The flat colours that belong to no element: the net a chemist drew
#: over the framework, the planes the user defined, and the pore
#: network a porosity run found.  They are side by side here because
#: they are the same kind of thing -- a note about the crystal rather
#: than part of it -- and because the picture they are chosen against
#: is the same picture.
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
        body.addLayout(self._build_global())
        body.addWidget(self._build_elements(), 1)

        inner = QWidget()
        inner.setLayout(body)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        self.setWidget(scroll)
        self.set_document(None)

    # -- construction --------------------------------------------------

    def _build_global(self) -> QFormLayout:
        form = QFormLayout()

        self.style = QComboBox()
        for name in styles.names():
            self.style.addItem(styles.get(name).label, name)
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

        self.labels = QComboBox()
        for value, label in LABEL_MODES:
            self.labels.addItem(label, value)
        self.labels.currentIndexChanged.connect(
            lambda: self._set(label_mode=self.labels.currentData()))
        form.addRow("Labels", self.labels)

        # Each entry carries the *name* of a background and not the
        # colour: QComboBox.findData compares through QVariant, which
        # never matches a Python tuple against an equal one, so a combo
        # holding colours answered -1 for every background there is and
        # ``refresh`` fell back to index 0 -- the panel read White
        # whatever the picture was.  ``preferences.py`` carries names
        # for the same reason.
        self.background = QComboBox()
        for name in BACKGROUNDS:
            self.background.addItem(name.capitalize(), name)
        self.background.addItem("Custom...", CUSTOM_BACKGROUND)
        self.background.currentIndexChanged.connect(
            self._on_background)
        self.background.activated.connect(self._on_custom_background)
        form.addRow("Background", self.background)

        # Every published ORTEP states its probability level, because
        # the same refinement at 50% and at 90% looks like two
        # different crystals.  A combo of the levels people actually
        # use rather than a free number: 50 and 90 are conventions, and
        # a picture drawn at 63% invites the question of why.
        self.ellipsoid_probability = QComboBox()
        for level in ELLIPSOID_LEVELS:
            self.ellipsoid_probability.addItem(
                f"{level * 100:g}%", level)
        self.ellipsoid_probability.setToolTip(
            "How much of each atom's displacement its ellipsoid "
            "encloses")
        self.ellipsoid_probability.currentIndexChanged.connect(
            lambda: self._set(ellipsoid_probability=(
                self.ellipsoid_probability.currentData())))
        # The level and the shading answer the same question -- what
        # this ellipsoid claims -- so they share a row.
        self.octants = QCheckBox("Octants")
        self.octants.setToolTip(
            "ORTEP's principal sections and octant shading, drawn on "
            "the atoms refined anisotropically")
        self.octants.toggled.connect(
            lambda v: self._set(ellipsoid_octants=v))
        ellipsoids = QHBoxLayout()
        ellipsoids.addWidget(self.ellipsoid_probability, 1)
        ellipsoids.addWidget(self.octants)
        form.addRow("Ellipsoids", ellipsoids)

        # A switch, then three numbers that each say what they are
        # and show their value, then a picture of the result.  It was
        # one unlabelled slider beside the checkbox, "Fade from" as a
        # fraction of a bounding box, and an exponent called a
        # gradient -- and nobody could say what any of them would do
        # before dragging it.
        self.depth_cue = QCheckBox("Depth cue")
        self.depth_cue.setToolTip(
            "Fade distant atoms towards the background, so a thick "
            "slab reads as having depth")
        self.depth_cue.toggled.connect(
            lambda v: self._set(depth_cue=v))
        form.addRow(self.depth_cue)

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
        form.addRow("", self.depth_cue_preview)

        # A swatch button each, not a combo: there is no shortlist of
        # sensible net colours the way there is of backgrounds, and the
        # only question worth asking is "which one".
        self.flat = {}
        swatches = QHBoxLayout()
        for field, label, tip in FLAT_COLORS:
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(
                lambda _checked=False, f=field, t=label:
                self._choose_flat(f, t))
            self.flat[field] = button
            swatches.addWidget(button)
        form.addRow("Colours", swatches)

        self.legend = QCheckBox("Element legend")
        self.legend.toggled.connect(
            lambda v: self._set(show_legend=v))
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
        # Every accessible Voronoi node rather than only the widest.
        # Off, and here rather than in the View menu, because it is a
        # question about how much of a measurement to draw and not
        # about whether to draw it -- and because what it does to a
        # framework has to be looked at to be believed.
        self.pore_nodes = QCheckBox("All pore nodes")
        self.pore_nodes.setToolTip(
            "Draw a sphere at every accessible Voronoi node instead "
            "of only at the widest one.  Hundreds of them in a cell")
        self.pore_nodes.toggled.connect(
            lambda v: self._set(pore_all_nodes=v))
        shown = QHBoxLayout()
        shown.addWidget(self.cell_box)
        shown.addWidget(self.cell_axes)
        shown.addWidget(self.topology)
        form.addRow("Show", shown)
        toggles = QHBoxLayout()
        toggles.addWidget(self.legend)
        toggles.addWidget(self.pore_nodes)
        form.addRow(toggles)
        return form

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

        reset = QPushButton("Reset colours and radii")
        reset.setToolTip(
            "Back to the element palette and the standard radii")
        reset.clicked.connect(self.reset_elements)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.elements, 1)
        layout.addWidget(reset)
        page = QWidget()
        page.setLayout(layout)
        return page

    # -- binding -------------------------------------------------------

    def set_document(self, document) -> None:
        self.document = document
        self.refresh()

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
        self._choose(self.background, _background_name(view.background))
        self._choose(self.ellipsoid_probability,
                     view.ellipsoid_probability)
        ellipsoids = styles.get(view.style).ellipsoids
        self.ellipsoid_probability.setEnabled(ellipsoids)
        self.octants.setChecked(view.ellipsoid_octants)
        self.octants.setEnabled(ellipsoids)
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
        self.legend.setChecked(view.show_legend)
        self.cell_box.setChecked(view.show_cell)
        self.cell_axes.setChecked(view.show_axes)
        self.topology.setChecked(view.show_topology)
        self.pore_nodes.setChecked(view.pore_all_nodes)
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
        """One of the four named backgrounds."""
        color = BACKGROUNDS.get(self.background.currentData())
        if color is not None:
            self._set(background=tuple(color))

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
                                  chosen.blue()))
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
            view.base_radius(symbol, "covalent"), 0.05, 5.0, 3)
        if not ok:
            return
        radii = dict(view.element_radii)
        radii[symbol] = float(value)
        self.document.update_view(element_radii=radii)

    def reset_elements(self) -> None:
        if self.document is not None:
            self.document.update_view(element_colors={},
                                      element_radii={})
