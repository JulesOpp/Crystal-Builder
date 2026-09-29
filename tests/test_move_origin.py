"""Cell > Move origin...: the corner of the cell somewhere else.

For cutting a cluster out of a crystal when a face of the cell runs
through it.  The fold itself -- bonds carried, P1 only -- is tested in
``test_cell_commands.py``; this is the centring, the dialog and the
menu entry.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QWidget  # noqa: E402

from xtal.core import p1, supercell, symmetry  # noqa: E402
from xtalapp import menus  # noqa: E402
from xtalapp.dialogs.origin import OriginDialog  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Origin{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def big_rutile(rutile):
    """Rutile 2x2x2 in P1: one cell of rutile is 2.96 A along c, too
    short to hold a whole octahedron at all."""
    return symmetry.reduce_to_p1(supercell.supercell(rutile, 2, 2, 2))


def octahedron(structure) -> list[int]:
    """The Ti at the origin and its six oxygens: a cluster every face
    through the corner cuts."""
    from xtal.core import bonding
    graph = bonding.graph(structure)
    return [0, *graph.neighbors(0)]


def test_centre_the_selection_puts_its_middle_at_the_cell_centre(
        rutile):
    """The middle is gathered across the faces; the mean of the wrapped
    coordinates of an octahedron at the corner is in the pore."""
    structure = big_rutile(rutile)
    atoms = octahedron(structure)
    shift = supercell.centring_shift(structure, atoms)
    assert np.all(shift >= -0.5) and np.all(shift < 0.5)
    moved = supercell.shift_origin(structure, shift)
    frac = p1.expand(moved).frac[atoms]
    assert frac.mean(axis=0) == pytest.approx([0.5, 0.5, 0.5], abs=1e-6)
    # Whole: nothing of it left on the far side of a face.
    assert np.ptp(frac, axis=0).max() <= 0.5 + 1e-9


def test_the_dialog_fills_in_the_centring_shift(qtbot, rutile):
    document = Document(big_rutile(rutile))
    document.select(octahedron(document.structure))
    dialog = OriginDialog(document)
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert not ok.isEnabled()             # an origin that did not move
    dialog.centre.click()
    assert dialog.shift() == pytest.approx(
        document.selection_centring_shift(), abs=1e-4)
    assert ok.isEnabled()


def test_centre_the_selection_needs_a_selection(qtbot, rutile):
    document = Document(big_rutile(rutile))
    dialog = OriginDialog(document)
    qtbot.addWidget(dialog)
    assert not dialog.centre.isEnabled()
    assert document.selection_centring_shift() is None


def test_moving_the_origin_is_one_undo_step(window, rutile,
                                            monkeypatch):
    document = Document(big_rutile(rutile))
    window.add_document(document)
    before = [site.frac.copy() for site in document.structure.sites]

    def accept(dialog):
        dialog.set_shift([0.25, 0.1, 0.0])
        return QDialog.Accepted

    monkeypatch.setattr(OriginDialog, "exec", accept)
    window.actions_["move_origin"].trigger()
    assert document.structure.sites[0].frac == pytest.approx(
        [0.75, 0.9, 0.0])
    assert document.undo_label == "Move origin"
    document.undo()
    assert np.allclose([s.frac for s in document.structure.sites],
                       before)
    assert not document.can_undo


def test_move_origin_is_greyed_outside_p1(window, rutile_cif):
    """Greyed with the reason, not absent: the entry is where somebody
    cutting a node will look, and Reduce to P1 is what they need."""
    document = window.open_path(rutile_cif)
    action = window.actions_["move_origin"]
    assert not action.isEnabled()
    assert action.toolTip() == menus.MOVE_ORIGIN_NEEDS_P1
    document.reduce_to_p1()
    assert action.isEnabled()
    assert action.toolTip() == menus.MOVE_ORIGIN_TIP


def test_move_origin_sits_after_wrap_in_the_cell_menu(window):
    cell = next(action.menu() for action in window.menuBar().actions()
                if action.text() == "&Cell")
    keys = [action.objectName() or action.text()
            for action in cell.actions() if not action.isSeparator()]
    wrap = window.actions_["wrap_cell"]
    move = window.actions_["move_origin"]
    order = [a for a in cell.actions() if a in (wrap, move)]
    assert order == [wrap, move], keys
