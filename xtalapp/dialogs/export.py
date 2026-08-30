"""
xtalapp.dialogs.export
======================
One dialog for writing a file something else will read.

It replaced ``Export as P1 CIF...``, which was one format with one of
its two options reachable, and it is where every later writer -- VASP
POSCAR, SHELX ``.res``, PDB, the ``.gen`` DFTB+ wants, the ``.cssr``
Zeo++ wants -- appears by being registered in ``xtal.io`` and changing
nothing here.

Three things it does that a native save dialog cannot.

**Per-format options, under the picker.**  CIF gets the pair that
prompted this: *with symmetry*, the asymmetric unit plus the
operations, or *P1*, every atom written out.  Both already worked and
only one of them was reachable from the menu.

**It says what the format drops.**  ``Format.keeps`` has existed since
the registry did and nothing read it.  Exporting a partially occupied
structure to a format with nowhere to put the occupancies should not be
a silent loss, so the line under the picker is computed from the set:
"XYZ keeps occupancy; symmetry, bonds and charges are not written."

**Selection only.**  "Export just this molecule" is the second thing
anybody wants after "export this".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from xtal.io import FORMATS

# What a round trip can lose, in the order a chemist would miss it.
# The registry's ``keeps`` is a set of these names.
QUALITIES = (
    ("symmetry", "symmetry"),
    ("occupancy", "occupancy"),
    ("adp", "displacement parameters"),
    ("charges", "charges"),
    ("bonds", "bonds"),
    ("view", "the view"),
)


def keeps_text(fmt) -> str:
    """"CIF keeps symmetry, occupancy...; bonds are not written"."""
    kept = [label for key, label in QUALITIES if key in fmt.keeps]
    lost = [label for key, label in QUALITIES if key not in fmt.keeps]
    name = fmt.name.upper()
    parts = []
    if kept:
        parts.append(f"{name} keeps {_join(kept)}")
    else:
        parts.append(f"{name} keeps the atoms and the cell")
    if lost:
        parts.append(f"{_join(lost)} {'is' if len(lost) == 1 else 'are'}"
                     f" not written")
    return "; ".join(parts) + "."


def _join(words) -> str:
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


class ExportDialog(QDialog):
    """Pick a format, its options, and where the file goes."""

    def __init__(self, document, parent=None, directory=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.document = document
        self.formats = [f for f in FORMATS.writable()
                        if f.name != "xtalproj"]

        self.format = QComboBox()
        for fmt in self.formats:
            self.format.addItem(f"{fmt.description} "
                                f"({' '.join(fmt.extensions)})",
                                fmt.name)
        self.format.currentIndexChanged.connect(self._on_format)

        self.keeps = QLabel()
        self.keeps.setWordWrap(True)
        self.keeps.setStyleSheet("color: palette(mid);")

        # CIF's two answers to "what is a structure file", which are
        # both right and are not the same file.
        self.with_symmetry = QRadioButton(
            "With symmetry (the asymmetric unit and the operations)")
        self.as_p1 = QRadioButton("P1 (every atom written out)")
        self.with_symmetry.setChecked(True)
        self.symmetry_box = QGroupBox("CIF")
        symmetry = QVBoxLayout()
        symmetry.addWidget(self.with_symmetry)
        symmetry.addWidget(self.as_p1)
        self.symmetry_box.setLayout(symmetry)

        self.selection_only = QCheckBox("Selected atoms only")
        selected = len(getattr(document, "selection", None).atoms) \
            if document is not None else 0
        self.selection_only.setEnabled(bool(selected))
        self.selection_only.setToolTip(
            f"Write the {selected} selected atoms and nothing else"
            if selected else "Nothing is selected")

        self.path = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.choose_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Export")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Format", self.format)
        form.addRow("", self.keeps)
        form.addRow("File", path_row)

        body = QVBoxLayout()
        body.addLayout(form)
        body.addWidget(self.symmetry_box)
        body.addWidget(self.selection_only)
        body.addWidget(self.buttons)
        self.setLayout(body)

        self._directory = Path(directory or Path.home())
        self.path.setText(str(self._suggested()))
        self._on_format()

    # -- state ---------------------------------------------------------

    def current_format(self):
        return FORMATS.get(self.format.currentData())

    def _suggested(self) -> Path:
        fmt = self.current_format()
        stem = "structure"
        if self.document is not None:
            source = self.document.path
            stem = (source.stem if source is not None
                    else str(self.document.structure.meta.get("title")
                             or "structure"))
        return self._directory / f"{stem}{fmt.extensions[0]}"

    def _on_format(self) -> None:
        fmt = self.current_format()
        self.keeps.setText(keeps_text(fmt))
        self.symmetry_box.setVisible(fmt.name == "cif")
        text = self.path.text().strip()
        if text:
            self.path.setText(
                str(Path(text).with_suffix(fmt.extensions[0])))

    def choose_path(self) -> None:
        fmt = self.current_format()
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Export", self.path.text() or str(self._suggested()),
            fmt.filter_string())
        if chosen:
            self.path.setText(
                str(Path(chosen).with_suffix(fmt.extensions[0])))

    def target(self) -> Path | None:
        text = self.path.text().strip()
        return Path(text) if text else None

    def options(self) -> dict:
        """What to pass to :meth:`xtalapp.document.Document.export`."""
        options = {
            "selection_only": self.selection_only.isChecked()
            and self.selection_only.isEnabled(),
        }
        if self.current_format().name == "cif":
            options["expand_to_p1"] = self.as_p1.isChecked()
        return options

    def accept(self) -> None:                       # pragma: no cover
        if self.target() is None:
            return
        super().accept()
