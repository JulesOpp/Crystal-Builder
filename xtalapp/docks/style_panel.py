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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.core import elements as el
from xtalapp.viewport import styles
from xtalapp.viewport.view_settings import BACKGROUNDS

LABEL_MODES = [("none", "None"), ("element", "Element"),
               ("label", "Site label"), ("index", "Atom index")]
ELEMENT_COLUMNS = ["El", "Colour", "Radius"]
# Sliders are integers; these turn a percentage into a scale factor.
SCALE_STEPS = 200
SCALE_MAX = 3.0


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

        self.labels = QComboBox()
        for value, label in LABEL_MODES:
            self.labels.addItem(label, value)
        self.labels.currentIndexChanged.connect(
            lambda: self._set(label_mode=self.labels.currentData()))
        form.addRow("Labels", self.labels)

        self.background = QComboBox()
        for name in BACKGROUNDS:
            self.background.addItem(name.capitalize(),
                                    BACKGROUNDS[name])
        self.background.addItem("Custom...", None)
        self.background.currentIndexChanged.connect(
            self._on_background)
        form.addRow("Background", self.background)

        self.legend = QCheckBox("Element legend")
        self.legend.toggled.connect(
            lambda v: self._set(show_legend=v))
        self.cell_box = QCheckBox("Unit cell")
        self.cell_box.toggled.connect(lambda v: self._set(show_cell=v))
        toggles = QHBoxLayout()
        toggles.addWidget(self.legend)
        toggles.addWidget(self.cell_box)
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
        self._choose(self.background, tuple(view.background))
        self.legend.setChecked(view.show_legend)
        self.cell_box.setChecked(view.show_cell)
        self._refreshing = False
        self._fill_elements()

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

    def _on_background(self, _index: int) -> None:
        if self._refreshing or self.document is None:
            return
        value = self.background.currentData()
        if value is not None:
            self._set(background=tuple(value))
            return
        current = QColor(*self.document.view.background)
        chosen = QColorDialog.getColor(current, self, "Background")
        if chosen.isValid():
            self._set(background=(chosen.red(), chosen.green(),
                                  chosen.blue()))
        else:
            self.refresh()              # put the old choice back

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
