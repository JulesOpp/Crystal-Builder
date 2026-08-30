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

def test_recalculating_bonds_is_not_an_undo_step(rutile_cif):
    """Nothing in the structure changed -- what was dropped is a memo
    -- so there is nothing to undo and nothing to save."""
    document = Document.load(rutile_cif)
    document.recompute_bonds()
    assert document.stack.depth == 0
    assert not document.modified


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
