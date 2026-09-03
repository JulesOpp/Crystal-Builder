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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from xtal.build.chem import CONNECTION

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

    ``connection_points`` is the dialog's ``not pastes`` and decides
    only whether the tool for one is on the toolbar.  The entry that
    pastes into an open cell refuses a starred string in the box, and
    a toolbar that hands out a tool the box will refuse would be
    offering a button that answers with an error.
    """

    smilesChanged = Signal(str)                     # noqa: N815

    def __init__(self, parent=None, connection_points: bool = True):
        super().__init__(parent)
        self.view = _canvas()
        self.tools = _Tools(self.view, self, connection_points)
        # rdeditor sets WA_DeleteOnClose on the canvas itself, which
        # is right for the standalone window it ships in and wrong
        # here: this dialog is opened, closed and opened again, and a
        # canvas that deletes itself on the first close leaves the
        # second one holding a freed C++ object.
        self.view.setAttribute(Qt.WA_DeleteOnClose, False)
        # Their default is a white canvas whatever the application
        # looks like, which on a dark theme is the brightest thing on
        # screen.  Read once, at construction: this dialog is built
        # fresh each time it is opened, so following the theme live
        # would be machinery for a case that cannot arise.
        self.view.darkmode = is_dark(self.palette())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tools)
        layout.addWidget(_Square(self.view, self), 1)
        self.setMinimumHeight(240)
        self._smiles = ""
        self.view.molChanged.connect(self._on_mol)

    # -- the interface the picture also has ----------------------------

    def smiles(self) -> str:
        return self._smiles

    def set_smiles(self, text: str) -> None:
        """Draw what the box says, unless it already says it."""
        text = str(text or "")
        if canonical(text) == canonical(self._smiles):
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
        text = canonical(_raw_smiles(self.view.mol))
        if canonical(self._smiles) == canonical(text):
            return
        self._smiles = text
        self.smilesChanged.emit(text)

    def undo(self) -> None:
        self.view.undo()


# ======================================================================
#  THE TOOLBAR
# ======================================================================

#: What a click does, by rdeditor's own name for it.  Four of the ten
#: their shell offers: charges, atom numbering and the two stereo
#: toggles are chemistry this application does not carry through
#: :func:`xtal.build.from_smiles` anyway, and a toolbar of ten buttons
#: over a canvas this size is a toolbar nobody reads.
ACTIONS = (
    ("Select", "Select atoms; click the canvas to clear"),
    ("Add", "Add whatever is chosen on the right"),
    ("Remove", "Delete the atom or bond clicked"),
    ("Replace", "Replace the atom or bond clicked"),
)

#: The elements a linker is made of, and no periodic table.  rdeditor
#: ships one -- ``ptable_widget`` -- and it is not taken: it wants a
#: ``QActionGroup`` built by their ``MainWindow`` and would couple this
#: dialog to plumbing that is not coming with the widget.  Anything
#: off this row is typed into the box, which is still the fastest way
#: to enter a molecule and is why the box did not go away.
ELEMENTS = ("C", "N", "O", "S", "F", "Cl", "Br")

#: Bond orders, as the glyphs they are drawn with.
BONDS = (("\u2014", "SINGLE", "Single bond"),
         ("=", "DOUBLE", "Double bond"),
         ("\u2261", "TRIPLE", "Triple bond"))

#: Ring templates, by rdeditor's label for them.  A label the
#: installed version does not know is left out rather than offered:
#: ``available_rings`` was ``("ARO6", "ALI6")`` before 0.5 and asking
#: for a name that is gone logs an error and places nothing.
RINGS = (("Benzene", "benzene"), ("Cyclohexane", "cyclohexane"))

#: The connection-point tool, which is an atom of atomic number zero
#: and needs no special case anywhere below it: ``*`` is what RDKit
#: writes for one, ``*`` is what the box already accepts, and
#: :func:`xtal.build.from_smiles` already turns it into
#: :data:`~xtal.build.chem.CONNECTION`.
#:
#: rdeditor draws it ``R`` and there is no talking it out of that --
#: its ``mol`` setter relabels every zero-atomic-number atom on the
#: way in.  So the tooltip says so, rather than leaving somebody to
#: work out why the canvas disagrees with the box and the tab.
CONNECTION_TIP = ("Connection point -- an X in the structure and a "
                  "* in the box; rdeditor draws it R")


class _Tools(QWidget):
    """Our own chrome over rdeditor's canvas.

    ``MolEditWidget`` has none of its own -- everything a user presses
    in rdEditor lives on their ``MainWindow``, which is a
    thousand-line application and is not coming with us.  So the
    buttons are here, they set ``action`` and ``chemEntity`` and read
    nothing back, and that is the entire coupling to the widget.

    Two exclusive groups because they are two independent choices:
    *Replace* with *O* is how a carbon becomes an oxygen, and folding
    them into one row of buttons would have lost that.
    """

    def __init__(self, view, parent=None,
                 connection_points: bool = True):
        super().__init__(parent)
        self.view = view
        self.actions_ = QButtonGroup(self)
        self.entities = QButtonGroup(self)
        self._buttons: dict[str, QToolButton] = {}

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        for name, tip in ACTIONS:
            top.addWidget(self._button(name, tip, self.actions_,
                                       view.setAction, name))
        top.addStretch(1)
        undo = QToolButton(self)
        undo.setText("Undo")
        undo.setToolTip("Undo the last change to the drawing")
        undo.clicked.connect(view.undo)
        self._buttons["Undo"] = undo
        top.addWidget(undo)

        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 0, 0, 0)
        for symbol in ELEMENTS:
            self._add(symbol, f"Draw {symbol}", symbol)
        self.row.addWidget(_separator(self))
        for glyph, order, tip in BONDS:
            self._add(glyph, tip, order)
        self.row.addWidget(_separator(self))
        for label, ring in RINGS:
            if ring in view.available_rings:
                self._add(label, f"Add a {label.lower()} ring", ring)
        if connection_points:
            self.row.addWidget(_separator(self))
            self._add(CONNECTION, CONNECTION_TIP, 0)
        self.row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(self.row)
        # Add and carbon, because the first click on an empty canvas
        # has to put an atom somewhere: a bond tool on nothing draws
        # nothing and reads as a broken editor.
        self.check("Add")
        self.check("C")

    def _add(self, label, tip, entity) -> None:
        self.row.addWidget(self._button(label, tip, self.entities,
                                        self.view.setChemEntity,
                                        entity))

    def _button(self, label, tip, group, slot, value):
        button = QToolButton(self)
        button.setText(label)
        button.setToolTip(tip)
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False: slot(value))
        group.addButton(button)
        self._buttons[label] = button
        return button

    def button(self, label: str):
        """The button with that label, or ``None``.

        By label rather than by index: the rows are built from the
        tables above and from what the installed rdeditor admits to
        knowing, so anything counting positions would break the first
        time a ring template was left out.
        """
        return self._buttons.get(label)

    def check(self, label: str) -> None:
        """Press a tool as if it had been clicked."""
        button = self.button(label)
        if button is not None:                      # pragma: no cover
            button.click()


def _separator(parent) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class _Square(QWidget):
    """One child, square, centred, and as large as it fits.

    rdeditor asks RDKit for a **300 x 300** drawing whatever shape its
    canvas is, and ``QSvgWidget`` stretches what it is given to fill
    the widget -- so in a canvas twice as wide as it is tall, a
    benzene is drawn as a flattened hexagon.

    Letterboxing the renderer instead would fix the picture and break
    the clicking.  rdeditor turns a click into SVG coordinates by
    scaling x and y independently by the widget's own width and
    height, which is exactly right for a stretched render and wrong
    for a centred one -- every click would land somewhere the cursor
    was not.  Making the widget the shape of the drawing keeps both
    halves true at once, and costs only the margin either side.

    The child is placed by hand rather than by a layout because that
    is the whole job: a layout that could express "square" would
    still have to be told the side.
    """

    def __init__(self, child, parent=None):
        super().__init__(parent)
        self.child = child
        child.setParent(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        side = max(min(self.width(), self.height()), 1)
        self.child.setGeometry((self.width() - side) // 2,
                               (self.height() - side) // 2,
                               side, side)

    def sizeHint(self) -> QSize:
        return QSize(360, 360)

    def minimumSizeHint(self) -> QSize:
        return QSize(220, 220)


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

def is_dark(palette: QPalette) -> bool:
    """Whether the window colour is a dark one.

    Asked of the palette rather than of a setting, because the theme
    here is the desktop's: on macOS the application follows the
    system appearance and nothing in this program is consulted about
    it.
    """
    return palette.color(QPalette.Window).lightness() < 128


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


def canonical(text: str) -> str:
    """The string as RDKit would write it, or the string itself.

    Unchanged for anything unreadable, which is what makes this safe
    to compare with: two identical half-typed strings still match,
    and two different ones still differ.
    """
    text = str(text or "")
    mol = _parse(text)
    return _raw_smiles(mol) if mol is not None else text


__all__ = ["ACTIONS", "BONDS", "ELEMENTS", "MISSING", "RINGS",
           "SketchEditor", "canonical", "installed", "is_dark"]
