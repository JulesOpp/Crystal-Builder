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

The picture is read-only and behind :class:`_Sketch`, whose whole
interface is ``set_smiles`` in and ``smilesChanged`` out.  That is the
seam the rdEditor spike lands on: a live editor is a widget with the
same two, and nothing else in this file would change.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from xtal.build import BuildError
from xtal.commands.clipboard import PasteFragment
from xtal.modules.build import molecule_for

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
        self.sketch = _Sketch(self)
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

        layout = QVBoxLayout(self)
        layout.addWidget(self.form)
        layout.addWidget(self.sketch, 1)
        layout.addWidget(self.footer)
        layout.addWidget(self.buttons)
        self.resize(520, 560)

    # -- the molecule, as it is typed ----------------------------------

    def _touched(self, *_args) -> None:
        self._quiet.start()

    def _on_sketch(self, text: str) -> None:
        """What a live editor would send back.

        Nothing emits it today -- the picture is read-only -- and the
        slot exists so that the editor that replaces :class:`_Sketch`
        is a widget swap and not a rewrite of this dialog.
        """
        widget = self.form.widgets.get("smiles")
        if widget is not None and widget.text() != text:
            widget.setText(text)

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
#  THE PICTURE
# ======================================================================

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.empty, 1)
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
