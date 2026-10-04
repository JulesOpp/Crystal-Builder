"""
xtalapp.dialogs.sketch
======================
The molecule editor every dialog that draws one embeds, and the words
to say when it cannot be drawn.

The editor is our own (:mod:`xtalapp.widgets.sketcher`): a page that
takes any element in the periodic table, a selection of atoms *and*
bonds that a tool applies to all at once, Ctrl+A, and a key typed over
an atom to change it.  It replaced rdeditor, whose canvas was
mouse-only, selected atoms and never bonds, offered seven elements and
could be told nothing about a metal; it needs RDKit and nothing else,
so the ``build`` extra is the whole of what drawing asks for.

**The contract is unchanged**: ``set_smiles`` in, ``smilesChanged``
out, ``smiles()`` and ``undo()``, so the molecule builder, the MOF
builder's *Draw...*, Substitute's *Draw...* and the polymer builder's
monomer rows took the new editor without a change of their own.

**Both directions are guarded on canonical SMILES**, because drawing
emits into the box, the box rebuilds and sets the string back, and
the two spellings of one molecule are rarely the same text
(``C1=CC=CC=C1`` against ``c1ccccc1``).  Comparing what RDKit makes of
each is the question actually being asked, and setting the same
molecule again would lay the drawing out afresh under the cursor.

A string RDKit cannot read leaves the drawing alone: every ring is
unreadable while it is being typed.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from xtal import build
from xtal.build import chem
from xtal.build.chem import CONNECTION
from xtalapp.widgets.sketcher import SketchCanvas, SketchTools

#: Said where the editor would be, when it cannot be.
MISSING = build.MISSING

#: How a connection point is written on a picture.
CONNECTION_LABEL = CONNECTION


def installed() -> bool:
    """Whether a molecule can be drawn: RDKit, by ``find_spec``."""
    return build.installed()


class SketchEditor(QWidget):
    """A molecule that can be drawn on, behind the picture's
    interface.

    ``connection_points`` is whether a ``*`` is something the box
    below accepts -- the entry that pastes into an open cell refuses
    one, so it gets no tool that draws one.  ``head_tail`` adds Head
    and Tail to a connection point's right-click menu, for a polymer's
    monomer.
    """

    smilesChanged = Signal(str)                     # noqa: N815

    def __init__(self, parent=None, connection_points: bool = True,
                 head_tail: bool = False):
        super().__init__(parent)
        self.view = SketchCanvas(self, connection_points, head_tail)
        self.tools = SketchTools(self.view, self, connection_points)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.tools)
        page = QHBoxLayout()
        page.setSpacing(2)
        page.addWidget(self.tools.side)
        page.addWidget(self.view, 1)
        layout.addLayout(page, 1)
        self._smiles = ""
        self.view.edited.connect(self._on_edit)

    def smiles(self) -> str:
        return self._smiles

    def sketch(self):
        return self.view.sketch

    def set_smiles(self, text: str) -> None:
        """Draw what the box says, unless it already says it."""
        text = str(text or "")
        if canonical(text) == canonical(self._smiles):
            return
        try:
            drawn = chem.sketch_from_smiles(text)
        except chem.BuildError:
            return
        self._smiles = text
        self.view.set_sketch(drawn)

    def _on_edit(self) -> None:
        """What was drawn, as a string for the box -- unless it is not
        a molecule yet, which the page says under the drawing and the
        box is left alone for."""
        if self.view.problem:
            return
        text = self.view.smiles
        if canonical(self._smiles) == canonical(text):
            return
        self._smiles = text
        self.smilesChanged.emit(text)

    def undo(self) -> None:
        self.view.undo()


def is_dark(palette: QPalette) -> bool:
    """Whether the window colour is a dark one.

    Asked of the palette rather than of a setting, because the theme
    here is the desktop's: on macOS the application follows the
    system appearance and nothing in this program is consulted about
    it.
    """
    return palette.color(QPalette.Window).lightness() < 128


def label_connection_points(mol):
    """``mol`` with every connection point labelled ``X``, in place,
    for the read-only picture.

    Only an unlabelled dummy, or one labelled ``*`` or ``R`` -- the
    two things RDKit calls one -- so a label somebody chose on purpose
    survives.  ``None`` passes through.
    """
    if mol is None:
        return None
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 0:
            continue
        if (not atom.HasProp("dummyLabel")
                or atom.GetProp("dummyLabel") in ("*", "R")):
            atom.SetProp("dummyLabel", CONNECTION_LABEL)
    return mol


def canonical(text: str) -> str:
    """The string as RDKit would write it, or the string itself.

    Unchanged for anything unreadable, which is what makes this safe
    to compare with: two identical half-typed strings still match,
    and two different ones still differ.
    """
    return chem.canonical(text)


__all__ = ["CONNECTION_LABEL", "MISSING", "SketchEditor", "canonical",
           "installed", "is_dark", "label_connection_points"]
