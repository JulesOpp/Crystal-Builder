"""View > Show Only Selected: a picture of part of the crystal.

What breaks if these regress: a hidden atom left out of a calculation
or a save, an undo step that only hides atoms (and a document marked
modified by looking at it), or an edit that renumbers the cell then
hiding the neighbours of the atoms that were hidden.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.core import p1  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


def _scene(document):
    return build_scene(document.structure, document.view,
                       selection=document.selection,
                       hidden=document.hidden_mask())


def test_hidden_atoms_are_not_drawn_or_picked_but_stay_in_the_structure(
        rutile):
    """Only the selected titanium is drawn, with no bond reaching an
    oxygen that is not: a half-bond to nothing would be clickable and
    would select a bond nobody can see.  The cell keeps all six."""
    document = Document(rutile)
    document.select([0])
    message = document.show_only_selected()
    assert message == "1 of 6 atoms shown"
    model = _scene(document)
    assert set(model.atom_index.tolist()) == {0}
    assert len(model.bond_keys) == 0
    assert p1.expand(document.structure).n_atoms == 6
    assert "1 of 6 atoms shown" in document.selection_summary()

    document.show_all()
    assert set(_scene(document).atom_index.tolist()) == set(range(6))
    assert document.hidden_mask() is None


def test_showing_only_the_selection_is_not_an_undo_step(rutile):
    """Hiding atoms is looking at the crystal, not changing it."""
    document = Document(rutile)
    document.select([0, 1])
    document.show_only_selected()
    assert not document.can_undo
    assert not document.modified


def test_showing_only_nothing_is_refused_rather_than_blank(rutile):
    document = Document(rutile)
    assert document.show_only_selected() == "nothing selected to show"
    assert document.hidden_mask() is None


def test_the_same_atoms_stay_hidden_when_an_edit_renumbers_the_cell(
        rutile):
    """Deleting an atom before the hidden ones moves every index down;
    the hidden set follows the atoms, not the numbers."""
    document = Document(rutile)
    document.reduce_to_p1()
    cell = document.cell
    oxygens = [a for a in range(cell.n_atoms) if cell.elements[a] == "O"]
    document.select([a for a in range(cell.n_atoms)
                     if cell.elements[a] == "Ti"])
    document.show_only_selected()
    hidden = {tuple(cell.frac[a].round(6)) for a in document.hidden}
    assert len(hidden) == len(oxygens)

    document.select([0])
    document.delete_selection()
    after = document.cell
    assert {tuple(after.frac[a].round(6))
            for a in document.hidden} == hidden
    assert all(after.elements[a] == "O" for a in document.hidden)


def test_the_view_menu_shows_only_the_selection_and_all_again(
        qtbot, tmp_path, rutile):
    """Show Only Selected is greyed until something is selected; Show
    All is always there to come back with."""
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest", f"ShowOnly{tmp_path.name}")
    settings.clear_window()
    window = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(window)
    document = Document(rutile)
    window.add_document(document)
    window.actions_["select_none"].trigger()
    assert not window.actions_["show_only_selected"].isEnabled()
    assert window.actions_["show_all"].isEnabled()
    document.select([0])
    assert window.actions_["show_only_selected"].isEnabled()
    window.actions_["show_only_selected"].trigger()
    assert document.hidden_mask().sum() == 5
    window.actions_["show_all"].trigger()
    assert document.hidden_mask() is None


def test_hidden_atoms_stay_hidden_through_a_supercell_and_a_standardize():
    """One Zn of ZIF-8 shown, the rest hidden.  Standardize moves
    ZIF-8's origin, so matched by where they were, 93 of its 102
    atoms were lost; undo and a supercell renumber everything again.
    The one Zn stays the one shown -- and in a 2x1x1, both copies."""
    from pathlib import Path

    from xtal.io import read_cif

    sample = (Path(__file__).resolve().parents[1] / "resources"
              / "samples" / "ZIF-8.cif")
    document = Document(read_cif(sample))
    cell = document.cell
    zinc = cell.elements.index("Zn")
    document.select([zinc])
    document.show_only_selected()

    def shown():
        n_atoms = document.cell.n_atoms
        return set(range(n_atoms)) - set(document.hidden)

    report = document.standardize_cell(1e-3)
    assert report.ok
    after = document.cell
    (one,) = shown()
    assert after.elements[one] == "Zn"
    went = report.atom_map.forward(cell.frac[zinc])
    d = after.frac[one] - went
    d -= d.round()
    assert abs(d @ document.structure.lattice.matrix).max() < 1e-3

    document.undo()
    assert shown() == {zinc}

    document.make_supercell(2, 1, 1)
    bigger = document.cell
    assert len(shown()) == 2
    assert all(bigger.elements[a] == "Zn" for a in shown())
