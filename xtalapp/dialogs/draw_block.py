"""
xtalapp.dialogs.draw_block
===========================
Draw a building block, for one slot and no other.

Reached from a "Draw..." button on a slot row in
:mod:`xtalapp.dialogs.mof_build` rather than from the Structure menu:
that entry point builds a molecule with no idea what it is for, and
this one is opened already knowing -- a six-connected node slot wants
six connection points and nothing else fits it, the same rule
:func:`xtal.mof.build._resolve` enforces before PORMAKE is asked to
place anything.  Checking it here, live, as the string is typed or
the ring is drawn, is cheaper than checking it after a failed build.

**It is the molecule builder's own box and canvas**, not a second
one.  :func:`~xtalapp.dialogs.build_molecule.sketch_for` and
:func:`~xtalapp.dialogs.build_molecule.on_change` used to be private
to that dialog; they are exactly what this one needs too, so they
lost their leading underscore instead of being copied.  The 350 ms
build timer, the cycle-guard on canonical SMILES between the box and
the canvas, and the toolbar all come along with the widget -- nothing
about drawing a linker differs from drawing a molecule until the
question of whether it fits.

**Saving is a smaller job than :mod:`xtalapp.dialogs.save_block`
does for the general case**, because the hard part of that dialog --
:func:`xtal.mof.block.problems` -- cannot fire here.  A molecule built
with connection points already has them marked as single-bonded
``X`` atoms and is a single fragment by construction; the one thing
worth checking before the file is written is the one this dialog
exists to check, and :func:`xtal.mof.block.write_building_block`
still runs :func:`~xtal.mof.block.problems` underneath as the last
word.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from xtal.build import BuildError
from xtal.modules.build import BUILD, molecule_for
from xtal.mof.block import BlockError, write_building_block
from xtal.workspace import safe_name
from xtalapp.dialogs import sketch
from xtalapp.dialogs.build_molecule import on_change, sketch_for
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.widgets.tone import HINT, set_tone

#: How long to wait after a keystroke before building -- the same
#: pause :mod:`xtalapp.dialogs.build_molecule` uses and for the same
#: reason: long enough that a twenty-character SMILES is one build,
#: short enough that the canvas feels like it is following the box.
QUIET_MS = 350


class DrawBlockDialog(QDialog):
    """A SMILES box and a canvas, aimed at one slot's coordination
    number."""

    def __init__(self, slot, folder: str, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.folder = str(folder or "").strip()
        self.molecule = None
        self.path: Path | None = None
        self.setWindowTitle(f"Draw a building block -- {slot.label}")

        # The molecule builder's own parameters -- smiles, name,
        # relax it, conformer seed -- read straight off its action
        # rather than declared again here: a building block is a
        # molecule with connection points, and the fields that ask
        # for one are already exactly right.
        self.action = BUILD.action("molecule")
        self.form = ParamForm(self.action.params, self)
        self.sketch = sketch_for(self, True)
        self.footer = QLabel(self)
        self.footer.setWordWrap(True)
        self.footer.setTextFormat(Qt.RichText)
        self.where = QLabel(self._where(), self)
        set_tone(self.where, HINT)
        self.where.setWordWrap(True)

        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(QUIET_MS)
        self._quiet.timeout.connect(self._rebuild)
        for name in ("smiles", "optimise", "seed"):
            on_change(self.form.widgets.get(name), self._touched)
        self.sketch.smilesChanged.connect(self._on_sketch)

        self._build_ui()
        self._rebuild()

    def _build_ui(self) -> None:
        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Ok)
        # "Save and use", because those are one action here and were
        # being read as two: the block is written, the row that asked
        # selects it, and Build then builds with it.  A button marked
        # "Save" invites somebody to look for a second one that uses
        # what was saved.
        self.save_button.setText("Save and use")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.form)
        layout.addWidget(self.sketch, 1)
        layout.addWidget(self.footer)
        layout.addWidget(self.where)
        layout.addWidget(buttons)
        self.resize(520, 620)

    # -- the molecule, as it is typed or drawn --------------------------

    def _touched(self, *_args) -> None:
        self._quiet.start()

    def _on_sketch(self, text: str) -> None:
        """What was drawn, into the box -- guarded on the molecule
        rather than the string, for the reason
        :meth:`~xtalapp.dialogs.build_molecule.BuildMoleculeDialog._on_sketch`
        gives."""
        widget = self.form.widgets.get("smiles")
        if widget is None:                          # pragma: no cover
            return
        if sketch.canonical(widget.text()) != sketch.canonical(text):
            widget.setText(text)

    def _rebuild(self) -> None:
        self._quiet.stop()
        values = self.action.coerce(self.form.values())
        text = str(values.get("smiles", "") or "")
        self.sketch.set_smiles(text)
        if not text.strip():
            self.molecule = None
            self._say("", ok=False)
            return
        try:
            # optimise=False for the same reason the molecule builder
            # gives: the footer needs the connection count and
            # nothing else, and relaxing changes neither.  The real
            # geometry is built once, when this is saved.
            self.molecule = molecule_for(
                dict(values, optimise=False), connection_points=True)
        except BuildError as exc:
            self.molecule = None
            self._say(str(exc), ok=False)
            return
        fits = self.molecule.n_connections == self.slot.coordination
        self._say(self._outcome(self.molecule, fits), ok=fits)

    def _outcome(self, molecule, fits: bool) -> str:
        have = molecule.n_connections
        need = self.slot.coordination
        base = (f"<b>{molecule.formula}</b>, {molecule.n_atoms} "
                f"atom(s), {have} connection point(s)")
        if fits:
            return f"{base} -- fits {self.slot.label.lower()}"
        return (f"{base} -- {self.slot.label} needs {need}, "
                f"not {have}")

    def _where(self) -> str:
        if not self.folder:
            return ('set the "Extra building blocks" folder below '
                    "before this can be saved")
        return f"saves into {self.folder}"

    def _say(self, message: str, ok: bool) -> None:
        self.footer.setText(message)
        if ok:
            set_tone(self.footer, HINT)
        else:
            set_tone(self.footer, None)
            self.footer.setStyleSheet("color: palette(link-visited);")
        self.save_button.setEnabled(ok and bool(self.folder))

    # -- the save ---------------------------------------------------

    def accept(self) -> None:
        """Write the block, from a fresh build and not the preview.

        Two things :attr:`molecule` is not allowed to be, both fixed
        by rebuilding here rather than reusing it as it stood:

        **Stale.** The 350 ms timer means a click landing inside that
        window after the last edit finds :attr:`molecule` describing
        whatever was drawn *before* it -- one connection point where
        the canvas now shows two.  ``BuildMoleculeDialog`` never has
        this problem, because its ``accept`` is the default one and
        hands back the live form values rather than a built molecule;
        this dialog's ``accept`` is the one place anything gets
        written, so the rebuild has to happen here, synchronously,
        before anything is read off :attr:`molecule`.

        **Unrelaxed.** The preview is always ``optimise=False`` --
        the same shortcut the molecule builder's footer takes, and
        for the same reason: nothing the preview shows changes with
        the geometry.  But unlike ``build_molecule()``, which rebuilds
        from the job's own parameters once a run actually starts,
        this dialog had been writing the *preview* molecule straight
        to disk -- so "Relax it" was checked, drawn, and completely
        ignored.  The block that gets written is built fresh, from
        the form's real values, exactly once.
        """
        self._rebuild()
        if (self.molecule is None or not self.folder or
                self.molecule.n_connections != self.slot.coordination):
            return
        values = self.action.coerce(self.form.values())
        stem = safe_name(str(values.get("name") or "") or
                         self.molecule.name or self.molecule.smiles,
                         "block")
        try:
            final = molecule_for(values, connection_points=True)
        except BuildError as exc:
            self._say(str(exc), ok=False)
            return
        path = Path(self.folder) / f"{stem}.xyz"
        try:
            self.path = write_building_block(
                final.to_structure(), path)
        except (BlockError, OSError) as exc:
            self._say(str(exc), ok=False)
            return
        super().accept()

    @classmethod
    def ask(cls, slot, folder: str, parent=None) -> Path | None:
        """The path just written, or ``None`` if it was cancelled."""
        dialog = cls(slot, folder, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.path
