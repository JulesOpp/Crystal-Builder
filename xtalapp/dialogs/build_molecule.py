"""
xtalapp.dialogs.build_molecule
==============================
Type a molecule, see it, and be told what will happen to it.

One dialog for two entries, which is why it reads
:attr:`~xtal.modules.registry.Action.name` rather than taking an
argument :meth:`ask` does not have.  ``build.molecule`` opens what it
builds in a tab of its own and may carry connection points;
``insert`` pastes into the structure that is already open and refuses
them -- see :mod:`xtal.modules.build` for why only the first of those
is a module action.

**The footer is not decoration.**  Pasting into a structure with
symmetry adds the atoms to the *asymmetric unit*, so the group
multiplies them: eleven atoms of benzoate into Fm-3m is 2112 atoms and
a window that stops responding.  :meth:`PasteFragment.describe` has
said so since the clipboard was written and the paste path shows it
afterwards; a person deciding whether to press the button needs it
before.  So the molecule is built as the string is typed, and the
footer says what the button will do with it.

**The build behind the footer is the cheap one.**  ``optimise=False``
-- ETKDG and no force field -- because the footer needs the atom
count and whether the string is a molecule at all, and neither
changes when the geometry relaxes.  The relaxation happens once, on
the worker thread or at the paste, with the parameters the form
actually says.

**The picture is one of two widgets with the same two members.**
``set_smiles`` in and ``smilesChanged`` out is the whole interface,
and :func:`_sketch_for` chooses between :class:`_Sketch` -- the
read-only depiction -- and
:class:`xtalapp.dialogs.sketch.SketchEditor`, which is rdeditor's
canvas and can be drawn on.  Which one is decided by whether
``rdeditor`` is installed, and nothing else in this file knows the
difference.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from xtal.build import BuildError, library
from xtal.commands.clipboard import PasteFragment
from xtal.modules.build import molecule_for
from xtalapp.dialogs import sketch

#: The action that pastes into the open cell, by name.  Everything
#: else this dialog is opened for builds a document of its own.
PASTES = "insert"

#: How long to wait after a keystroke before building.  Long enough
#: that typing a twenty-character SMILES is one build and not twenty,
#: short enough that it feels like the picture is following the text.
QUIET_MS = 350


class BuildMoleculeDialog(QDialog):
    """A SMILES box, the molecule it means, and what will be done
    with it."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")
        #: Whether this entry pastes into the open structure, and so
        #: whether connection points are on offer.  A molecule with X
        #: on it is a building block on its way out to PORMAKE; a
        #: molecule dropped into a framework is chemistry, and a user
        #: who typed a star into this box meant something by it that
        #: silently dropping the star would not honour.
        self.pastes = action.name == PASTES
        self.molecule = None

        from xtalapp.dialogs.module_form import ParamForm
        self.form = ParamForm(action.params, self)
        self.form.set_values(action.coerce(initial or {}))
        self.library = _Library(self, self.pastes)
        self.library.chosen.connect(self._on_library)
        self.sketch = _sketch_for(self, not self.pastes)
        self.footer = QLabel(self)
        self.footer.setWordWrap(True)
        self.footer.setTextFormat(Qt.RichText)

        # One timer restarted on every keystroke, rather than a build
        # per character: ETKDG on a linker is tens of milliseconds and
        # a dialog that stutters as it is typed into is worse than one
        # whose picture is a moment behind.
        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(QUIET_MS)
        self._quiet.timeout.connect(self._rebuild)
        for name in ("smiles", "optimise", "seed"):
            _on_change(self.form.widgets.get(name), self._touched)
        self.sketch.smilesChanged.connect(self._on_sketch)

        self._build_ui()
        self._rebuild()

    def _build_ui(self) -> None:
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                        QDialogButtonBox.Cancel)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Insert" if self.pastes else "Build")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        picker = QFormLayout()
        picker.setContentsMargins(0, 0, 0, 0)
        picker.addRow("Start from", self.library)

        layout = QVBoxLayout(self)
        layout.addLayout(picker)
        layout.addWidget(self.form)
        layout.addWidget(self.sketch, 1)
        layout.addWidget(self.footer)
        layout.addWidget(self.buttons)
        self.resize(520, 560)

    # -- the molecule, as it is typed ----------------------------------

    def _touched(self, *_args) -> None:
        self._quiet.start()

    def _on_sketch(self, text: str) -> None:
        """What was drawn, into the box.

        **Guarded on the molecule and not on the string.**  This is
        one hop of a cycle -- draw, box, timer, build, back into the
        canvas -- and the two ends of it disagree about spelling
        constantly: a benzene template comes back kekulized where the
        box says ``c1ccccc1``, and a library entry writes
        ``[*:1]c1ccc([*:2])cc1`` where the depiction canonicalises
        the ring.  A text compare would rewrite the box for every one
        of those, restart the timer, rebuild, and re-lay the drawing
        out under the cursor.  The question worth asking is whether
        the molecule changed.
        """
        widget = self.form.widgets.get("smiles")
        if widget is None:                          # pragma: no cover
            return
        if sketch.canonical(widget.text()) != sketch.canonical(text):
            widget.setText(text)

    def _on_library(self, entry) -> None:
        """Fill the boxes from a library entry.

        Into the boxes rather than around them: what is picked is a
        starting point, and the next thing anybody does with a
        phenylene is put a methyl on it.
        """
        self.form.set_values({"smiles": entry.smiles,
                              "name": entry.name})

    def _rebuild(self) -> None:
        """Build what the box says, and report it in the footer."""
        self._quiet.stop()
        values = self.values()
        text = str(values.get("smiles", "") or "")
        self.sketch.set_smiles(text)
        if not text.strip():
            self.molecule = None
            self._say("")
            return
        try:
            # optimise=False: the footer needs the atom count and
            # whether this is a molecule at all, and relaxing changes
            # neither.  The real geometry is built once, afterwards.
            self.molecule = molecule_for(
                dict(values, optimise=False),
                connection_points=not self.pastes)
        except BuildError as exc:
            self.molecule = None
            self._say(str(exc), bad=True)
            return
        self._say(self._outcome(self.molecule))

    def _outcome(self, molecule) -> str:
        """What pressing the button will do, in one sentence."""
        marked = (f", {molecule.n_connections} connection point(s)"
                  if molecule.n_connections else "")
        if not self.pastes:
            return (f"<b>{molecule.formula}</b>, {molecule.n_atoms} "
                    f"atom(s){marked} -- opens in a tab of its own")
        structure = self._structure()
        if structure is None:
            return (f"<b>{molecule.formula}</b>, {molecule.n_atoms} "
                    f"atom(s) -- nothing is open to paste into")
        described = PasteFragment(
            molecule.to_fragment()).describe(structure)
        return f"<b>{molecule.formula}</b> -- {described}"

    def _structure(self):
        """The structure a paste would land in, if there is one.

        Read off the window rather than passed in, because
        :meth:`ask` has the signature every module dialog has and
        growing it an argument for this one would grow it for all of
        them.
        """
        current = getattr(self.parent(), "current_document", None)
        document = current() if callable(current) else None
        return getattr(document, "structure", None)

    def _say(self, message: str, bad: bool = False) -> None:
        self.footer.setText(message)
        self.footer.setStyleSheet(
            "color: palette(link-visited);" if bad
            else "color: palette(mid);")
        self.ok_button.setEnabled(self.molecule is not None)

    # -- the contract --------------------------------------------------

    def values(self) -> dict:
        return self.action.coerce(self.form.values())

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled.

        The same contract as
        :meth:`xtalapp.dialogs.module_form.ModuleDialog.ask`, which is
        the whole of what ``Action.dialog`` promises.
        """
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()


# ======================================================================
#  THE LIBRARY
# ======================================================================

class _Library(QWidget):
    """The shipped fragments, in one combo box.

    Grouped by category, in the file's own order rather than
    alphabetically: it lists solvents before linkers because that is
    the order somebody looks for them in.  The entries with connection
    points are left out of the box that pastes into a cell, which
    refuses a starred string -- offering them there would be offering
    entries that answer with a refusal.

    A library that cannot be read is an empty picker and not an error:
    the box beside it still takes a SMILES string, which is the whole
    feature, and a dialog that refuses to open because a convenience
    file is missing would be a worse failure than the one it reports.
    """

    chosen = Signal(object)                 # a library.Entry

    def __init__(self, parent=None, pastes: bool = False):
        super().__init__(parent)
        self.combo = QComboBox(self)
        self.combo.addItem("(type it yourself)", None)
        try:
            entries = library.matching(connection_points=not pastes)
        except library.LibraryError:            # pragma: no cover
            entries = ()
        for category in _grouped(entries):
            self.combo.insertSeparator(self.combo.count())
            for entry in category:
                self.combo.addItem(f"{entry.name}    "
                                   f"{entry.summary()}", entry)
        self.combo.currentIndexChanged.connect(self._on_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combo)

    def _on_changed(self, *_args) -> None:
        entry = self.combo.currentData()
        if entry is not None:
            self.chosen.emit(entry)

    def count(self) -> int:
        """How many fragments are on offer, separators and the
        type-it-yourself row not counted."""
        return sum(1 for i in range(self.combo.count())
                   if self.combo.itemData(i) is not None)


def _grouped(entries) -> list[list]:
    """The entries by category, both in file order."""
    out: dict[str, list] = {}
    for entry in entries:
        out.setdefault(entry.category, []).append(entry)
    return list(out.values())


# ======================================================================
#  THE PICTURE
# ======================================================================

def _sketch_for(parent, connection_points: bool):
    """The drawable canvas if there is one, the depiction otherwise.

    The choice is made per dialog rather than per session on purpose:
    it is a ``find_spec``, it costs nothing, and a test that takes
    rdeditor away has to be able to see the other branch without
    reaching into a module-level cache.

    ``connection_points`` is ``not self.pastes``, the same flag the
    footer and the library picker read.  The entry that pastes
    refuses a starred string, so it must not hand out the tool that
    draws one either -- a button whose only outcome is the footer
    turning red is worse than no button.
    """
    if sketch.installed():
        return sketch.SketchEditor(parent, connection_points)
    return _Sketch(parent)


class _Sketch(QWidget):
    """A 2D depiction of a SMILES string.

    Read-only, and deliberately the smallest interface an editor could
    also satisfy: ``set_smiles`` in, ``smilesChanged`` out.  rdEditor
    is a PySide6 widget backed by the same RDKit and the spike that
    adopts it replaces this class and touches nothing else in the
    dialog -- which is the reason a picture is behind a widget at all
    rather than being a ``QSvgWidget`` in the layout above.

    A string RDKit cannot read leaves the last good picture up and
    says nothing.  The footer is already saying what is wrong with it,
    and blanking the drawing on the way through an unfinished ring
    closure makes the panel flicker for every molecule with a ring in
    it.
    """

    smilesChanged = Signal(str)                     # noqa: N815

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = QSvgWidget(self)
        self.empty = QLabel("The molecule appears here as it is "
                            "typed", self)
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color: palette(mid);")
        # The offer, made where somebody is looking at the thing they
        # cannot do.  Absent when rdeditor is there, because then this
        # class is not what the dialog is showing.
        self.hint = QLabel(sketch.MISSING, self)
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet("color: palette(mid);")
        self.hint.setVisible(not sketch.installed())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.empty, 1)
        layout.addWidget(self.hint)
        self.setMinimumHeight(200)
        self._smiles = ""
        self._show(False)

    def smiles(self) -> str:
        return self._smiles

    def set_smiles(self, text: str) -> None:
        self._smiles = str(text or "")
        svg = self._draw(self._smiles)
        if svg:
            self.view.load(QByteArray(svg.encode("utf-8")))
            self._show(True)
        elif not self._smiles.strip():
            self._show(False)

    def _show(self, drawn: bool) -> None:
        self.view.setVisible(drawn)
        self.empty.setVisible(not drawn)

    def _draw(self, text: str) -> str:
        """The SVG, or an empty string for anything undrawable.

        Every RDKit name is in here.  It is imported at the call and
        not at the top of the file for the reason
        :mod:`xtal.build.chem` gives: the dialog is reached from a
        menu that is rebuilt constantly, and RDKit is an extra that
        may not be installed at all.
        """
        if not text.strip():
            return ""
        try:
            from rdkit import Chem, rdBase
            from rdkit.Chem import rdDepictor
            from rdkit.Chem.Draw import rdMolDraw2D
        except ImportError:                         # pragma: no cover
            return ""
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(text)
            if mol is None:
                return ""
            try:
                rdDepictor.Compute2DCoords(mol)
                drawer = rdMolDraw2D.MolDraw2DSVG(
                    max(self.view.width(), 240),
                    max(self.view.height(), 180))
                rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
                drawer.FinishDrawing()
                return drawer.GetDrawingText()
            except (ValueError, RuntimeError):      # pragma: no cover
                return ""


def _on_change(widget, slot) -> None:
    """Connect whichever "the user changed this" signal a widget has.

    The form is generated, so what a parameter renders as is
    :mod:`xtalapp.dialogs.module_form`'s decision and not this
    dialog's; asking each widget what it offers is how this one keeps
    following when a parameter changes kind.
    """
    if widget is None:                              # pragma: no cover
        return
    for name in ("textChanged", "valueChanged", "toggled",
                 "currentIndexChanged"):
        signal = getattr(widget, name, None)
        if signal is not None:
            signal.connect(slot)
            return
