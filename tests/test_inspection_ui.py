"""Selection, the inspector, and the site table, driven headless.

The viewport is stubbed (see tests/test_app_shell.py for why); what is
exercised here is the chain from a selection to what the panels show
and to what an edit does to the structure.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.core.structure import Change  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = AppSettings("CrystalBuilderTest", f"Insp{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def open_rutile(window, rutile_cif):
    document = window.open_path(rutile_cif)
    return window, document


# ------------------------------------------------------ Document API

def test_selecting_and_clearing(qtbot, rutile_cif):
    document = Document.load(rutile_cif)
    with qtbot.waitSignal(document.selectionChanged):
        document.select([0])
    assert document.selection.atoms == {0}
    assert document.selected_sites() == {0}
    assert "1 atoms (Ti)" in document.selection_summary()

    document.select([2], "add")
    assert document.selection.atoms == {0, 2}
    document.select([2], "toggle")
    assert document.selection.atoms == {0}
    document.select_none()
    assert document.selection.is_empty


def test_selection_helpers(rutile_cif):
    document = Document.load(rutile_cif)
    document.select_all()
    assert len(document.selection.atoms) == document.cell.n_atoms
    document.invert_selection()
    assert document.selection.is_empty

    document.select_element("O")
    assert len(document.selection.atoms) == 4
    document.select_site(0)
    assert document.selection.atoms == {0, 1}

    document.select([0])
    document.expand_selection("orbit")
    assert document.selection.atoms == {0, 1}
    document.select([0])
    document.expand_selection("shell")
    assert len(document.selection.atoms) == 5      # Ti + its O
    with pytest.raises(ValueError):
        document.expand_selection("telepathy")


def test_selection_is_pruned_when_atoms_disappear(rutile_cif):
    document = Document.load(rutile_cif)
    document.select_all()
    document.select([5], "set")
    document.apply(lambda s: s.remove_sites([1]), Change.TOPOLOGY)
    assert document.selection.atoms <= set(range(document.cell.n_atoms))


def test_deleting_a_selection_removes_the_whole_orbit(rutile_cif):
    document = Document.load(rutile_cif)
    document.select([2])                            # one O of four
    assert not document.selection_is_orbit_complete()
    message = document.delete_selection()
    assert "1 site" in message and "4 atoms" in message
    assert document.structure.n_sites == 1
    assert document.cell.n_atoms == 2
    assert document.modified


def test_changing_the_element_of_a_selection(rutile_cif):
    document = Document.load(rutile_cif)
    document.select_element("Ti")
    document.set_selection_element("Zr")
    assert document.structure.sites[0].element == "Zr"
    assert "Zr" in document.status_text()
    assert document.set_selection_element("Hf") == \
        "changed 1 site(s) to Hf"


def test_editing_one_site_property(rutile_cif):
    document = Document.load(rutile_cif)
    document.set_site_property(1, label="O99", occupancy=0.5,
                               u_iso=0.02, charge=-2.0)
    site = document.structure.sites[1]
    assert site.label == "O99" and site.occupancy == 0.5
    assert site.u_iso == 0.02 and site.charge == -2.0
    assert document.modified


def test_reduce_to_p1_makes_atoms_independent(rutile_cif):
    document = Document.load(rutile_cif)
    assert not document.structure.is_p1
    message = document.reduce_to_p1()
    assert "P42/mnm" in message
    assert document.structure.n_sites == 6
    assert document.structure.is_p1

    document.select([2])
    assert document.selection_is_orbit_complete()   # orbits of one now
    document.delete_selection()
    assert document.structure.n_sites == 5          # a single atom went


# -------------------------------------------------------- Inspector

def test_inspector_shows_one_atom(open_rutile):
    window, document = open_rutile
    document.select([0])
    inspector = window.inspector_dock
    assert "1 atoms (Ti)" in inspector.headline.text()
    assert inspector.element.currentText() == "Ti"
    assert inspector.form_widget.isEnabled()
    details = inspector.details.toPlainText()
    assert "multiplicity" in details
    assert "neighbours" in details
    assert "operation" in details


def test_inspector_neighbours_are_as_far_as_they_are_now(open_rutile):
    """Moving an atom does not perceive its bonds again, so each bond
    still carries the length it had when it was found.  The Inspector
    listed that as the neighbour's distance -- after a relaxation it
    said 1.600 A of an O-H that was 0.990."""
    import re

    import numpy as np

    window, document = open_rutile
    oxygen = next(k for k, e in enumerate(document.cell.elements)
                  if e == "O")
    document.select([oxygen])
    document.move_selection(np.array([0.15, 0.15, 0.0]), cartesian=True)
    document.select([oxygen])

    listed = sorted(float(v) for v in re.findall(
        r"(\d+\.\d+) A$", window.inspector_dock.details.toPlainText(),
        flags=re.M))
    cell, matrix = document.cell, document.structure.lattice.matrix
    now = sorted(round(b.length(cell.frac, matrix), 3)
                 for b in document.graph.bonds_of(oxygen))
    then = sorted(round(b.distance, 3)
                  for b in document.graph.bonds_of(oxygen))
    assert now != then                     # the move was felt
    assert listed == now


def test_inspector_says_what_the_force_field_type_means(open_rutile):
    """The five-character name is what an override is stored as; the
    words beside it are the half a reader can check."""
    window, document = open_rutile
    document.select([0])
    details = window.inspector_dock.details.toPlainText()
    assert "force field    Ti6+4  (octahedral Ti(IV))" in details


def test_inspector_warns_when_symmetry_will_multiply_an_edit(
        open_rutile):
    window, document = open_rutile
    document.select([0])                        # one of two Ti images
    assert not window.inspector_dock.symmetry_note.isHidden()
    assert "every image" in window.inspector_dock.symmetry_note.text()

    document.select([0, 1])                     # the whole orbit
    assert window.inspector_dock.symmetry_note.isHidden()


def test_inspector_edits_reach_the_structure(open_rutile):
    window, document = open_rutile
    inspector = window.inspector_dock
    document.select([0])

    inspector.label.setText("Titan")
    inspector._commit_label()
    assert document.structure.sites[0].label == "Titan"

    inspector.occupancy.setValue(0.5)
    inspector._commit_occupancy()
    assert document.structure.sites[0].occupancy == 0.5

    inspector.coords[0].setValue(0.25)
    inspector._commit_coordinates()
    assert document.structure.sites[0].frac[0] == pytest.approx(0.25)

    inspector.element.setCurrentText("Zr")
    inspector._commit_element()
    assert document.structure.sites[0].element == "Zr"


def test_inspector_ignores_a_nonsense_element(open_rutile):
    window, document = open_rutile
    document.select([0])
    window.inspector_dock.element.setCurrentText("Kryptonite")
    window.inspector_dock._commit_element()
    assert document.structure.sites[0].element == "Ti"


def test_inspector_with_nothing_selected(open_rutile):
    window, document = open_rutile
    document.select_none()
    assert "Nothing selected" in window.inspector_dock.headline.text()
    assert not window.inspector_dock.form_widget.isEnabled()


def test_inspector_with_many_atoms(open_rutile):
    window, document = open_rutile
    document.select_all()
    inspector = window.inspector_dock
    assert "6 atoms" in inspector.headline.text()
    assert "2 site(s)" in inspector.details.toPlainText()


# ------------------------------------------------------- site table

def test_site_table_lists_the_asymmetric_unit(open_rutile):
    window, document = open_rutile
    model = window.sites_dock.model
    assert model.rowCount() == 2
    assert model.columnCount() == 9
    assert model.data(model.index(0, 1)) == "Ti"
    assert model.data(model.index(1, 1)) == "O"
    assert model.data(model.index(1, 2)) == "0.30530"
    assert model.data(model.index(0, 8)) == "2"     # multiplicity
    assert model.data(model.index(1, 8)) == "4"


def test_site_table_edits_the_structure(open_rutile):
    window, document = open_rutile
    model = window.sites_dock.model
    assert model.setData(model.index(1, 1), "S")
    assert document.structure.sites[1].element == "S"
    assert model.setData(model.index(1, 2), "0.25")
    assert document.structure.sites[1].frac[0] == pytest.approx(0.25)
    assert model.setData(model.index(1, 5), "0.5")
    assert document.structure.sites[1].occupancy == 0.5
    assert not model.setData(model.index(1, 2), "not a number")
    assert not model.setData(model.index(1, 1), "Zzz")


def test_site_table_selection_selects_the_orbit(open_rutile):
    window, document = open_rutile
    window.sites_dock.table.selectRow(1)            # the O site
    assert document.selection.atoms == {2, 3, 4, 5}


def test_site_table_follows_the_viewport_selection(open_rutile):
    window, document = open_rutile
    document.select([0])
    rows = {i.row() for i in
            window.sites_dock.table.selectionModel().selectedRows()}
    assert rows == {0}


# ------------------------------------------------- window commands

def test_select_menu_actions(open_rutile):
    window, document = open_rutile
    window.actions_["select_all"].trigger()
    assert len(document.selection.atoms) == 6
    window.actions_["invert_selection"].trigger()
    assert document.selection.is_empty
    window.actions_["select_none"].trigger()
    assert document.selection.is_empty

    document.select([0])
    window.actions_["select_same"].trigger()
    assert document.selection.atoms == {0, 1}       # both Ti
    window.actions_["expand_bonded"].trigger()
    assert len(document.selection.atoms) == 6


def test_element_menu_is_built_from_the_structure(open_rutile):
    window, _document = open_rutile
    labels = [a.text() for a in window.element_menu.actions()]
    assert labels == ["O", "Ti"]
    window.element_menu.actions()[1].trigger()      # Ti
    assert window.current_document().selection.atoms == {0, 1}


def test_delete_action_asks_before_taking_the_orbit(open_rutile,
                                                    monkeypatch):
    window, document = open_rutile
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: (asked.append(a[2]), QMessageBox.No)[1])
    document.select([2])
    window.actions_["delete_selection"].trigger()
    assert asked and "symmetry" in asked[0].lower()
    assert document.structure.n_sites == 2          # refused

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    window.actions_["delete_selection"].trigger()
    assert document.structure.n_sites == 1


def test_change_element_action(open_rutile, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    window, document = open_rutile
    document.select_element("O")
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *a, **k: ("S", True))
    window.actions_["change_element"].trigger()
    assert document.structure.sites[1].element == "S"

    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *a, **k: ("Zzz", True))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warned.append(a[1]))
    window.actions_["change_element"].trigger()
    assert warned
    assert document.structure.sites[1].element == "S"


def test_reduce_to_p1_action(open_rutile):
    window, document = open_rutile
    window.actions_["reduce_p1"].trigger()
    assert document.structure.is_p1
    assert document.structure.n_sites == 6


def test_status_bar_reports_the_selection(open_rutile):
    window, document = open_rutile
    assert window.selection_label.text() == "nothing selected"
    document.select_element("O")
    assert "4 atoms (O4)" in window.selection_label.text()


def test_selection_actions_are_disabled_without_a_selection(
        open_rutile):
    window, document = open_rutile
    document.select_none()
    assert not window.actions_["delete_selection"].isEnabled()
    document.select([0])
    assert window.actions_["delete_selection"].isEnabled()


def test_invert_selection_works_in_whole_orbits(rutile_cif):
    """Every edit acts on whole orbits, so inverting atom-by-atom hands
    back a selection that overlaps the one it came from: half an orbit
    inverted still leaves that orbit selected, through its other half.
    """
    document = Document.load(rutile_cif)
    document.select([0])                        # half of the Ti orbit
    assert document.selected_sites() == {0}
    document.invert_selection()
    # not {1, 2, 3, 4, 5}: atom 1 is the other Ti, and taking it would
    # mean the titanium site is selected either way round
    assert document.selection.atoms == {2, 3, 4, 5}
    assert document.selected_sites() == {1}
    assert document.selection_is_orbit_complete()


def test_inverting_a_selection_twice_returns_it(rutile_cif):
    document = Document.load(rutile_cif)
    document.select([0, 1])
    document.invert_selection()
    document.invert_selection()
    assert document.selection.atoms == {0, 1}


def test_invert_selection_in_p1_is_plain_inversion(rutile_cif):
    """In P1 every orbit is one atom, so this degrades to exactly what
    it did before."""
    document = Document.load(rutile_cif)
    document.reduce_to_p1()
    document.select([0])
    document.invert_selection()
    assert document.selection.atoms == {1, 2, 3, 4, 5}


# ------------------------------------------- selecting a region takes
#                                             the bonds inside it

def test_select_all_takes_the_bonds_too(rutile_cif):
    """So that "select everything, set the bond type" is one gesture
    and not one click per bond."""
    document = Document.load(rutile_cif)
    document.select_all()

    assert len(document.selection.atoms) == document.cell.n_atoms
    assert document.selection.bonds == {b.key()
                                        for b in document.graph.bonds}


def test_select_all_leaves_the_net_alone(rutile_cif):
    """Delete acts on the net before it acts on anything else, so
    taking the edges here would make Select All then Delete take the
    net apart instead of the crystal."""
    document = Document.load(rutile_cif)
    document.select_all()
    assert not document.selection.topology


def test_inverting_everything_leaves_nothing(rutile_cif):
    """The bonds follow the atoms, so the inverse of everything is
    nothing at all -- not "no atoms and every bond"."""
    document = Document.load(rutile_cif)
    document.select_all()
    document.invert_selection()
    assert document.selection.is_empty


def test_growing_to_a_fragment_takes_its_bonds(rutile_cif):
    """A fragment is a region, and a region contains the bonds inside
    it."""
    document = Document.load(rutile_cif)
    document.select([0])
    assert not document.selection.bonds

    document.expand_selection("fragment")

    assert document.selection.bonds
    inside = document.selection.atoms
    assert all(i in inside and j in inside
               for i, j, _image in document.selection.bonds)


def test_clicking_an_atom_does_not_take_bonds(rutile_cif):
    """A click names an atom.  A bond that quietly joined the
    selection would be edited by the next command without ever having
    been asked for."""
    document = Document.load(rutile_cif)
    document.select([0, 2])
    assert not document.selection.bonds


def test_every_bond_type_can_be_set_at_once(rutile_cif):
    """The whole point of the selection change."""
    from xtal.core import bonding

    document = Document.load(rutile_cif)
    document.select_all()
    message = document.set_selected_bond_type(2.0)

    orders = bonding.orders(document.structure)
    assert len(orders) == len(document.graph.bonds)
    assert set(orders) == {2.0}
    assert "double" in message
