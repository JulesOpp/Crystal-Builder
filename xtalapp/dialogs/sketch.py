"""
xtalapp.dialogs.sketch
======================
Whether the molecule can be drawn, and the words to say when it
cannot.

`rdeditor <https://github.com/EBjerrum/rdeditor>`_ is the 2D editor
:class:`xtalapp.dialogs.build_molecule._Sketch` was written to make
room for: a PySide6 widget over the same RDKit, LGPL-3.0, and used as
a dependency rather than vendored because that licence is the whole
of what makes it usable here.

**Its own extra and not part of ``build``.**  RDKit is a library;
rdeditor is a library plus PySide6 plus a theme package.  ``xtal/``
imports no Qt at all, so somebody installing ``[build]`` on a cluster
node to turn SMILES into structures must not be handed a widget
toolkit to get it.  Two extras, and ``[build]`` alone still greys the
Build entries in exactly the way it always did.

**Two greying axes, not one.**  No RDKit is the coarse one and is
unchanged: the menu entry itself is off, naming ``[build]``.  RDKit
without rdeditor is the fine one, and it is not an error -- the
dialog opens, the picture is the read-only depiction that shipped
with the fragment library, and it names this extra underneath.  A
feature that is missing says so where somebody is looking for it.

:func:`installed` is ``find_spec`` and never an import, the same rule
:func:`xtal.build.installed` follows and for a sharper reason here:
``rdeditor/__init__.py`` does ``from .rdEditor import MainWindow``, so
importing anything from the package executes a thousand-line
application shell and pulls in ``qdarktheme``.  That is fine at the
moment a dialog is built and unaffordable on every menu rebuild.
"""

from __future__ import annotations

import importlib.util
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

MISSING = ("rdeditor is not installed, so the molecule is drawn "
           "rather than drawable -- pip install "
           "'crystal-builder[sketch]'")


def installed() -> bool:
    """Whether ``rdeditor`` is importable -- without importing it.

    See the module docstring: importing it to find out costs a
    ``MainWindow`` class and a theme package that are never used.
    """
    try:
        return importlib.util.find_spec("rdeditor") is not None
    except (ImportError, ValueError):           # pragma: no cover
        return False


# ======================================================================
#  THE EDITOR
# ======================================================================

class SketchEditor(QWidget):
    """A molecule that can be drawn on, behind the picture's
    interface.

    ``set_smiles`` in and ``smilesChanged`` out, and nothing else --
    which is the whole of what
    :class:`xtalapp.dialogs.build_molecule._Sketch` promised and the
    reason this is a widget swap rather than a rewrite of that dialog.

    **Both directions are guarded on canonical SMILES, and a raw
    string compare is not enough.**  Drawing emits into the box, the
    box restarts the dialog's build timer, and the build sets the
    string back on this widget -- a cycle, unless one of the hops
    stops.  The strings on either side of it are never equal as text:
    RDKit hands back ``C1=CC=CC=C1`` for a benzene ring template where
    the box says ``c1ccccc1``, and a text compare would set the mol
    again, re-lay the depiction out under the cursor, and do it on
    every keystroke.  Round-tripping both sides through
    ``MolToSmiles`` makes them the same molecule, which is the
    question actually being asked.

    A string RDKit cannot read leaves the drawing alone, for the
    reason :class:`_Sketch` gives: every ring is unreadable while it
    is being typed.

    :attr:`view` is the ``MolEditWidget`` itself, and it is a
    ``QSvgWidget`` -- so the assertions written against the read-only
    picture's renderer hold here unchanged.
    """

    smilesChanged = Signal(str)                     # noqa: N815

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = _canvas()
        # rdeditor sets WA_DeleteOnClose on the canvas itself, which
        # is right for the standalone window it ships in and wrong
        # here: this dialog is opened, closed and opened again, and a
        # canvas that deletes itself on the first close leaves the
        # second one holding a freed C++ object.
        self.view.setAttribute(Qt.WA_DeleteOnClose, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)
        self.setMinimumHeight(200)
        self._smiles = ""
        self.view.molChanged.connect(self._on_mol)

    # -- the interface the picture also has ----------------------------

    def smiles(self) -> str:
        return self._smiles

    def set_smiles(self, text: str) -> None:
        """Draw what the box says, unless it already says it."""
        text = str(text or "")
        if _canonical(text) == _canonical(self._smiles):
            return
        mol = _parse(text)
        if mol is None:
            return
        self._smiles = text
        self.view.mol = mol

    # -- the other direction -------------------------------------------

    def _on_mol(self) -> None:
        """What was drawn, as a string for the box.

        Canonical rather than raw, so that a benzene drawn from the
        template reads ``c1ccccc1`` in the box and not the kekulized
        form the template handler builds -- and so that the string
        going out is the one :meth:`set_smiles` will compare against
        when it comes back.
        """
        text = _canonical(_raw_smiles(self.view.mol))
        if _canonical(self._smiles) == _canonical(text):
            return
        self._smiles = text
        self.smilesChanged.emit(text)

    def undo(self) -> None:
        self.view.undo()


def _canvas():
    """The ``MolEditWidget``, with the global it changes put back.

    Built with no parent, because ``MolEditWidget.__init__`` passes
    its ``parent`` to ``MolWidget.__init__``, whose first parameter is
    the *molecule* -- so a parent handed in is used as one and the
    constructor dies inside RDKit.  The layout below adopts it, which
    is what the parent was for.

    ``MolWidget.__init__`` calls :func:`logging.basicConfig` and then
    sets the level of the *root* logger, which is the application's
    and not theirs.  Constructing a dialog must not decide how the
    rest of this program logs, so the root logger is restored around
    the call -- their own ``logger.error`` still reaches stderr
    through ``lastResort``.

    The import is here rather than at the top of the file: see the
    module docstring for what ``import rdeditor`` executes.
    """
    from rdeditor.molEditWidget import MolEditWidget

    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    try:
        return MolEditWidget()
    finally:
        root.setLevel(level)
        root.handlers = handlers


# ======================================================================
#  SMILES, BOTH WAYS
# ======================================================================

def _parse(text: str):
    """The molecule a string means, or ``None`` for an unreadable one.

    The empty string is a molecule -- an empty one -- and not a
    failure: clearing the box has to clear the canvas.
    """
    from rdkit import Chem, rdBase

    with rdBase.BlockLogs():
        return Chem.MolFromSmiles(str(text or ""))


def _raw_smiles(mol) -> str:
    """What the canvas holds, as SMILES.

    A half-drawn molecule is often not sanitizable -- a carbon with
    five bonds on the way to being a carbon with four -- and
    ``MolToSmiles`` raises rather than returns for those.  An empty
    string is the right answer: the box keeps what it had and the
    footer is already saying what is wrong.
    """
    from rdkit import Chem, rdBase

    if mol is None:
        return ""
    try:
        with rdBase.BlockLogs():
            return Chem.MolToSmiles(mol)
    except (RuntimeError, ValueError):           # pragma: no cover
        return ""


def _canonical(text: str) -> str:
    """The string as RDKit would write it, or the string itself.

    Unchanged for anything unreadable, which is what makes this safe
    to compare with: two identical half-typed strings still match,
    and two different ones still differ.
    """
    text = str(text or "")
    mol = _parse(text)
    return _raw_smiles(mol) if mol is not None else text


__all__ = ["MISSING", "SketchEditor", "installed"]
