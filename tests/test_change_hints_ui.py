"""What the window redraws when the crystal changes.

The companion to tests/test_change_hints.py: that one covers the data
model keeping what a change did not touch, this one covers the panels
being told only about the changes that reached them.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from tests.test_change_hints import Counter  # noqa: E402
from xtal.core.structure import Change  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


def test_recalculating_bonds_is_what_changes_them(rutile_cif):
    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)

    document.apply(lambda s: s.set_frac(1, [0.45, 0.45, 0.0]),
                   Change.POSITIONS)
    assert len(document.graph.bonds) == before      # not yet

    message = document.recompute_bonds()
    assert len(document.graph.bonds) != before      # now
    assert "removed" in message

def test_recalculating_unchanged_bonds_says_so(rutile_cif):
    document = Document.load(rutile_cif)
    assert "unchanged" in document.recompute_bonds()

def test_recalculating_bonds_can_be_undone(rutile_cif):
    """The graph is stored on the structure and travels with the
    project, so replacing it is a change like any other -- and the
    graph it replaced has to be reachable again."""
    document = Document.load(rutile_cif)
    before = {b.key() for b in document.graph.bonds}

    document.apply(lambda s: s.set_frac(1, [0.45, 0.45, 0.0]),
                   Change.POSITIONS)
    document.recompute_bonds()
    assert document.stack.depth
    assert {b.key() for b in document.graph.bonds} != before

    assert document.undo()
    assert {b.key() for b in document.graph.bonds} == before


# --------------------------------- bonds following the geometry, or not

def test_bonds_do_not_follow_the_geometry_by_default(rutile_cif):
    document = Document.load(rutile_cif)
    before = {b.key() for b in document.graph.bonds}
    document.apply(lambda s: s.set_frac(1, [0.45, 0.45, 0.0]),
                   Change.POSITIONS)
    assert {b.key() for b in document.graph.bonds} == before


def test_the_preference_makes_them_follow(rutile_cif):
    """For the person building a molecule by hand, who wants to drag
    two atoms together and see the bond form."""
    document = Document.load(rutile_cif)
    document.bonds_follow_geometry = True
    before = {b.key() for b in document.graph.bonds}

    document.apply(lambda s: s.set_frac(1, [0.45, 0.45, 0.0]),
                   Change.POSITIONS)
    assert {b.key() for b in document.graph.bonds} != before

    # and undoing the move is enough to undo the perception, because
    # the perception is derived from the geometry the undo puts back
    assert document.undo()
    assert {b.key() for b in document.graph.bonds} == before


def test_the_window_hands_the_preference_to_every_document(
        qtbot, tmp_path, rutile_cif):
    settings = AppSettings("CrystalBuilderTest", f"Follow{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    settings.bonds_follow_geometry = False
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)

    document = win.open_path(rutile_cif)
    assert not document.bonds_follow_geometry

    win.set_bonds_follow_geometry(True)
    assert document.bonds_follow_geometry
    assert settings.bonds_follow_geometry
    # a document opened afterwards starts the same way
    assert win.open_path(rutile_cif).bonds_follow_geometry
    settings.bonds_follow_geometry = False


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Hints{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _count_refreshes(window, monkeypatch):
    """How many times each panel is asked to redraw itself."""
    counts = {}
    for name, method in (("info", "show_document"),
                         ("sites", "refresh"),
                         ("style", "refresh"),
                         ("ff", "refresh")):
        dock = getattr(window, f"{name}_dock")
        counts[name] = Counter(monkeypatch, dock, method)
    return counts


def test_a_move_refreshes_only_the_panels_that_show_coordinates(
        window, rutile_cif, monkeypatch):
    document = window.open_path(rutile_cif)
    counts = _count_refreshes(window, monkeypatch)

    document.apply(lambda s: s.set_frac(1, [0.31, 0.31, 0.0]),
                   Change.POSITIONS)

    assert counts["sites"].calls == 1       # it lists coordinates
    assert counts["info"].calls == 0        # formula, density, group
    assert counts["style"].calls == 0       # the elements present
    assert counts["ff"].calls == 0          # the atom typing


def test_a_topology_change_refreshes_everything(window, rutile_cif,
                                                monkeypatch):
    document = window.open_path(rutile_cif)
    counts = _count_refreshes(window, monkeypatch)

    document.delete_selection() if document.selection.atoms else None
    document.add_atom("C", [0.2, 0.2, 0.2])

    assert all(c.calls >= 1 for c in counts.values())


def test_a_preview_reaches_nothing_but_the_viewport(window, rutile_cif,
                                                    monkeypatch):
    """Two hundred of these arrive during a run.  None of them is a
    change to anything a panel is showing."""
    document = window.open_path(rutile_cif)
    counts = _count_refreshes(window, monkeypatch)
    seen = []
    document.structureChanged.connect(lambda _c: seen.append(1))

    document.preview_positions(np.array([[0.0, 0.0, 0.0],
                                         [0.31, 0.31, 0.0]]))

    assert seen == []
    assert all(c.calls == 0 for c in counts.values())


# ------------------------------------- a move that changes the atom count

def test_a_move_that_splits_an_orbit_prunes_the_selection(rutile_cif):
    """A move is a positions-only change and still changes how many
    atoms the cell holds -- so the selection can be left naming atoms
    that are no longer there, which would light up whichever atoms
    inherited their indices."""
    document = Document.load(rutile_cif)
    document.select(range(document.cell.n_atoms))
    before = document.cell.n_atoms

    document.move_selection([0.02, 0.01, 0.01])   # off the special one

    assert document.cell.n_atoms != before
    assert max(document.selection.atoms) < document.cell.n_atoms


def test_a_move_that_changes_nothing_leaves_the_selection_alone(
        qtbot, rutile_cif):
    """The common case, and the one an optimiser runs through hundreds
    of times: no announcement when there is nothing to announce."""
    document = Document.load(rutile_cif)
    document.select([0, 1])
    seen = []
    document.selectionChanged.connect(lambda: seen.append(1))

    document.move_selection([0.0, 0.0, 0.001])

    assert seen == []
    assert document.selection.atoms == {0, 1}
