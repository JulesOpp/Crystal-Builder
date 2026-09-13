"""
xtalapp.dialogs.dftb_run
========================
The parameters of one of DFTB+'s own runs, and the Hamiltonian it
inherits.

Every run of :mod:`xtal.modules.dftb_runs` is computed with the DFTB+
panel's Hamiltonian, and this is where that is made true: the values
the dialog hands back carry the panel's form under ``hamiltonian``, and
the dialog says which Hamiltonian it is in a line at the top -- because
a band structure started with the panel set to non-SCC, and not
noticed, is an afternoon lost.

:class:`BandStructureDialog` adds what a band structure needs a
picture for: the path, as ASE's letters in a line that can be edited,
drawn through the Brillouin zone of the open cell as it is typed.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from xtal.analysis import kpath
from xtal.ff.dftb import params as dftb_params
from xtalapp.dialogs.module_form import ModuleDialog


def panel_hamiltonian(window) -> dict:
    """The DFTB+ panel's form, or nothing when there is no panel --
    a run then gets :class:`~xtal.ff.dftb.calculator.DFTBOptions`'
    defaults, which are the panel's defaults."""
    dock = getattr(window, "dftb_dock", None)
    forms = getattr(dock, "engine_forms", {}) or {}
    form = forms.get("dftb")
    return dict(form.values()) if form is not None else {}


class DftbRunDialog(ModuleDialog):
    """The generated form, the Hamiltonian line above it, and the
    panel's values under ``hamiltonian`` in what it returns."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(module, action, parent, initial)
        self.hamiltonian = panel_hamiltonian(parent)
        method = dict(dftb_params.METHODS).get(
            self.hamiltonian.get("method", "dftb3"), "DFTB3")
        self.summary = QLabel(
            f"Hamiltonian from the DFTB+ panel: {method}"
            + (f", {self.hamiltonian['dispersion']} dispersion"
               if self.hamiltonian.get("dispersion", "none") != "none"
               else ""))
        self.summary.setWordWrap(True)
        self.layout().insertWidget(0, self.summary)

    def values(self) -> dict:
        values = super().values()
        values["hamiltonian"] = dict(self.hamiltonian)
        values["frozen"] = frozen_labels(self.parent())
        return values

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()


class BandStructureDialog(DftbRunDialog):
    """The path, edited as letters and seen in the zone."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(module, action, parent, initial)
        from xtalapp.widgets.brillouin import BrillouinView

        self.setWindowTitle("DFTB+: Band structure")
        self.lattice = _lattice_of(parent)
        self.preset = None
        self.path_edit = self.form.widgets["path"]
        self.view = BrillouinView(self)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        reset = QPushButton("Recommended path")
        reset.setToolTip("ASE's path for this cell's Bravais lattice")
        reset.clicked.connect(self.use_preset)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(reset)
        layout = self.layout()
        # The form's trailing stretch would take the slack the zone
        # should have, and leave a hole under the path's description.
        for index in range(layout.count() - 1, -1, -1):
            if layout.itemAt(index).spacerItem() is not None:
                layout.takeAt(index)
        layout.insertWidget(layout.count() - 1, self.view, 1)
        layout.insertLayout(layout.count() - 1, row)

        if self.lattice is not None:
            self.view.set_lattice(self.lattice.matrix)
            try:
                self.preset = kpath.band_path(self.lattice)
            except RuntimeError as exc:
                self.status.setText(str(exc))
        if self.preset is not None and not self.path_edit.text():
            self.path_edit.setText(self.preset.text)
        self.path_edit.textChanged.connect(self._path_changed)
        self._path_changed()
        self.resize(460, 620)

    def use_preset(self) -> None:
        if self.preset is not None:
            self.path_edit.setText(self.preset.text)

    def _path_changed(self, *_args) -> None:
        ok = self.buttons.button(QDialogButtonBox.Ok)
        if self.preset is None:
            ok.setEnabled(False)
            return
        try:
            path = self.preset.with_text(self.path_edit.text() or
                                         self.preset.text)
        except ValueError as exc:
            self.status.setText(str(exc))
            ok.setEnabled(False)
            return
        self.view.set_path(path.points, path.runs)
        names = ", ".join(
            f"{kpath.pretty(name)} ({' '.join(f'{v:g}' for v in k)})"
            for name, k in sorted(path.points.items()))
        self.status.setText(f"Points of this cell: {names}")
        ok.setEnabled(True)


def frozen_labels(window) -> list[str]:
    """The labels of the frozen sites of the tab in front.

    Labels and not indices: the run is handed the structure with its
    markers taken out, and an index from the document names a
    different site in that one.
    """
    document = window.current_document() if window is not None and \
        hasattr(window, "current_document") else None
    if document is None:
        return []
    sites = document.structure.sites
    return sorted(sites[i].label for i in document.frozen_sites()
                  if i < len(sites))


def _lattice_of(window):
    document = window.current_document() if window is not None and \
        hasattr(window, "current_document") else None
    return document.structure.lattice if document is not None else None
