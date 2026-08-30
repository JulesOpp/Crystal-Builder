"""Building, undo/redo and the clipboard, through the application."""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal import Lattice, Structure  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.viewport import modes  # noqa: E402


class BuildViewport(StubViewport):
    """A stub that also remembers the interaction mode."""

    def __init__(self, document, parent=None):
        super().__init__(document, parent)
        self.mode = modes.get("select")

    def set_mode(self, name):
        self.mode = modes.get(name)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = AppSettings("CrystalBuilderTest", f"Edit{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    win = MainWindow(viewport_factory=BuildViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def empty_document(window):
    document = window.new_document()
    document.set_structure(Structure.empty(Lattice.cubic(10.0)),
                           modified=False)
    return window, document


# ---------------------------------------------------------- undo/redo

def test_undo_and_redo_through_the_document(qtbot, rutile_cif):
    document = Document.load(rutile_cif)
    assert not document.can_undo and not document.modified

    document.select_element("Ti")
    with qtbot.waitSignal(document.historyChanged):
        document.set_selection_element("Zr")
    assert document.can_undo and document.modified
    assert document.undo_label == "Change element to Zr"

    assert document.undo() == "Change element to Zr"
    assert document.structure.sites[0].element == "Ti"
    assert not document.modified                # back to the saved state
    assert document.can_redo

    assert document.redo() == "Change element to Zr"
    assert document.structure.sites[0].element == "Zr"


def test_undo_restores_deleted_atoms(rutile_cif):
    document = Document.load(rutile_cif)
    before = document.structure.copy()
    document.select_element("O")
    document.delete_selection()
    assert document.structure.n_sites == 1
    document.undo()
    assert document.structure == before


def test_saving_makes_the_document_clean_again(rutile_cif, tmp_path):
    document = Document.load(rutile_cif)
    document.select([0])
    document.set_selection_element("Zr")
    assert document.modified
    document.save(tmp_path / "saved.cif")
    assert not document.modified
    document.undo()
    assert document.modified                    # away from the save
    document.redo()
    assert not document.modified                # and back to it


def test_transactions_group_edits(rutile_cif):
    document = Document.load(rutile_cif)
    with document.transaction("Retype everything"):
        document.select_element("Ti")
        document.set_selection_element("Zr")
        document.select_element("O")
        document.set_selection_element("S")
    assert document.stack.depth == 1
    assert document.undo_label == "Retype everything"
    document.undo()
    assert [s.element for s in document.structure.sites] == ["Ti", "O"]


def test_undo_actions_track_the_history(window, rutile_cif):
    document = window.open_path(rutile_cif)
    assert not window.actions_["undo"].isEnabled()

    document.select([0])
    document.set_selection_element("Zr")
    assert window.actions_["undo"].isEnabled()
    assert "Change element" in window.actions_["undo"].text()

    window.actions_["undo"].trigger()
    assert document.structure.sites[0].element == "Ti"
    assert window.actions_["redo"].isEnabled()
    assert "Change element" in window.actions_["redo"].text()
    window.actions_["redo"].trigger()
    assert document.structure.sites[0].element == "Zr"


# ------------------------------------------------------------ building

def test_add_atom(empty_document):
    _window, document = empty_document
    assert document.add_atom("O", [0.5, 0.5, 0.5]) == "added O"
    assert document.structure.n_sites == 1
    assert document.structure.sites[0].label == "O1"
    document.undo()
    assert document.structure.n_sites == 0


def test_build_a_molecule_atom_by_atom(empty_document):
    """Three atoms placed in a P1 box become a water molecule, bonds
    and all, with no symmetry to complicate it."""
    _window, document = empty_document
    document.add_atom("O", [0.50, 0.50, 0.50])
    document.add_atom("H", [0.596, 0.50, 0.50])     # 0.96 A away
    document.add_atom("H", [0.50, 0.596, 0.50])
    assert document.structure.n_sites == 3
    assert len(document.graph.bonds) == 2
    assert [f.kind for f in document.graph.fragments()] == ["molecule"]

    document.undo()
    assert document.structure.n_sites == 2


def test_add_atom_mode_places_where_you_click(empty_document):
    _window, document = empty_document
    mode = modes.get("add_atom")
    mode.element = "Fe"
    model = None
    event = modes.ClickEvent(origin=(0.0, 0.0, -10.0),
                             direction=(0.0, 0.0, 1.0),
                             focal=(3.0, 4.0, 5.0))
    mode.on_click(document, model, event)

    assert document.structure.n_sites == 1
    placed = document.structure.lattice.to_cart(
        document.structure.sites[0].frac)
    assert np.allclose(placed, [0.0, 0.0, 5.0], atol=1e-6)
    assert document.structure.sites[0].element == "Fe"


def test_add_bond_mode_needs_two_atoms(empty_document):
    from xtalapp.viewport.builder import build_scene

    _window, document = empty_document
    document.add_atom("C", [0.4, 0.5, 0.5])
    document.add_atom("C", [0.7, 0.5, 0.5])         # 3 A: too far
    assert len(document.graph.bonds) == 0

    model = build_scene(document.structure, document.view)
    mode = modes.get("add_bond")
    mode.pending = None

    # a ray straight through the first atom, then the second
    first = modes.ClickEvent(origin=(4.0, 5.0, -10.0),
                             direction=(0.0, 0.0, 1.0))
    second = modes.ClickEvent(origin=(7.0, 5.0, -10.0),
                              direction=(0.0, 0.0, 1.0))
    assert mode.on_click(document, model, first) == "pick the second atom"
    assert mode.pending is not None
    assert mode.on_click(document, model, second) == "bond added"
    assert len(document.graph.bonds) == 1
    assert mode.pending is None

    document.undo()
    assert len(document.graph.bonds) == 0


def test_add_bond_mode_cancels_on_empty_space(empty_document):
    from xtalapp.viewport.builder import build_scene
    _window, document = empty_document
    document.add_atom("C", [0.4, 0.5, 0.5])
    model = build_scene(document.structure, document.view)
    mode = modes.get("add_bond")
    mode.on_click(document, model,
                  modes.ClickEvent(origin=(4.0, 5.0, -10.0),
                                   direction=(0.0, 0.0, 1.0)))
    assert mode.pending is not None
    assert mode.on_click(document, model,
                         modes.ClickEvent(origin=(0.0, 0.0, -10.0),
                                          direction=(0.0, 0.0, 1.0))
                         ) == "cancelled"
    assert mode.pending is None


def test_mode_switching(window, rutile_cif):
    window.open_path(rutile_cif)
    viewport = window.current_viewport()
    assert viewport.mode.name == "select"
    window.actions_["mode_add_atom"].trigger()
    assert viewport.mode.name == "add_atom"
    window.actions_["mode_add_bond"].trigger()
    assert viewport.mode.name == "add_bond"
    with pytest.raises(ValueError):
        window.set_mode("telekinesis")


def test_element_combo_drives_the_add_atom_mode(window, rutile_cif):
    window.open_path(rutile_cif)
    window.element_combo.setCurrentText("Se")
    assert modes.get("add_atom").element == "Se"
    window.element_combo.setCurrentText("Nonsense")
    assert modes.get("add_atom").element == "Se"    # unchanged


# ----------------------------------------------------------- clipboard

def test_copy_and_paste_through_the_window(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.select_element("O")
    window.copy()
    assert window.clipboard_fragment.n_atoms == 4
    assert "O" in QGuiApplication.clipboard().text()

    before = document.structure.n_sites
    window.paste()
    assert document.structure.n_sites == before + 4
    document.undo()
    assert document.structure.n_sites == before


def test_cut_is_copy_plus_delete(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.select_element("O")
    window.cut()
    assert window.clipboard_fragment.n_atoms == 4
    assert document.structure.n_sites == 1
    document.undo()
    assert document.structure.n_sites == 2


def test_pasting_xyz_from_another_program(empty_document):
    window, document = empty_document
    QGuiApplication.clipboard().setText(
        "2\nfrom elsewhere\nN 0.0 0.0 0.0\nN 1.1 0.0 0.0\n")
    window.paste()
    assert document.structure.n_sites == 2
    assert {s.element for s in document.structure.sites} == {"N"}


def test_pasting_nothing_is_harmless(empty_document):
    window, document = empty_document
    QGuiApplication.clipboard().setText("")
    window.clipboard_fragment = type(window.clipboard_fragment)()
    window.paste()
    assert document.structure.n_sites == 0


def test_duplicate(window, rutile_cif):
    """Duplicating copies the *drawn* atoms, so selecting an element in
    a symmetric structure duplicates every image of it: both Ti images
    come back as two new independent sites."""
    document = window.open_path(rutile_cif)
    document.select_element("Ti")
    assert len(document.selection.atoms) == 2
    window.duplicate()
    assert document.structure.n_sites == 4
    document.undo()
    assert document.structure.n_sites == 2


# ------------------------------------------------------------ moving

def test_move_dock_translates_the_selection(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.select_element("O")
    start = document.structure.sites[1].frac.copy()

    window.move_dock.units.setCurrentIndex(0)       # fractional
    window.move_dock.steps[0].setValue(0.1)
    window.move_dock.translate()
    assert document.structure.sites[1].frac[0] == pytest.approx(
        start[0] + 0.1)

    window.move_dock.translate(sign=-1.0)
    assert document.structure.sites[1].frac[0] == pytest.approx(
        start[0])
    assert document.stack.depth == 1                # the moves merged


def test_move_dock_uses_cartesian_when_asked(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.select_element("O")
    start = document.structure.lattice.to_cart(
        document.structure.sites[1].frac)

    window.move_dock.units.setCurrentIndex(1)       # cartesian
    window.move_dock.steps[2].setValue(1.0)         # 1 A along z
    window.move_dock.translate()
    moved = document.structure.lattice.to_cart(
        document.structure.sites[1].frac)
    assert np.linalg.norm(moved - start) == pytest.approx(1.0)


def test_move_dock_rotates_and_mirrors(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.select_all()
    window.move_dock.rotation_axis.setCurrentText("c")
    window.move_dock.angle.setValue(90.0)
    assert "rotated" in window.move_dock.rotate()

    window.move_dock.mirror_axis.setCurrentText("x")
    assert "mirrored" in window.move_dock.mirror()
    assert document.stack.depth == 2
    document.undo()
    document.undo()
    assert not document.modified


def test_move_dock_reports_what_symmetry_will_do(window, rutile_cif):
    document = window.open_path(rutile_cif)
    assert "Nothing selected" in window.move_dock.summary.text()
    document.select([2])                            # one O of four
    assert "whole orbit moves" in window.move_dock.summary.text()
    document.select_element("O")
    assert "whole orbit moves" not in window.move_dock.summary.text()


def test_move_dock_does_nothing_without_a_selection(empty_document):
    window, document = empty_document
    window.move_dock.steps[0].setValue(0.5)
    assert window.move_dock.translate() == ""
    assert window.move_dock.rotate() == ""
    assert window.move_dock.mirror() == ""
    assert not document.can_undo


# ------------------------------------------------- regressions, phase 5

def test_move_dock_apply_button_actually_translates(window,
                                                    rutile_cif):
    """QPushButton.clicked carries a `checked` flag.  Connected
    straight to ``translate``, that False arrives as the sign and every
    translation is multiplied by zero -- Apply looked wired up and did
    nothing."""
    document = window.open_path(rutile_cif)
    document.select_element("O")
    start = document.structure.sites[1].frac.copy()

    window.move_dock.units.setCurrentIndex(0)
    window.move_dock.steps[1].setValue(0.25)
    button = _button_labelled(window.move_dock, "Apply")
    button.click()

    assert document.structure.sites[1].frac[1] == pytest.approx(
        start[1] + 0.25)


def test_move_dock_rotate_and_mirror_buttons_fire(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.select_all()
    window.move_dock.angle.setValue(30.0)
    _button_labelled(window.move_dock, "Apply", box="Rotate").click()
    _button_labelled(window.move_dock, "Apply", box="Mirror").click()
    assert document.stack.depth == 2


def _button_labelled(dock, text, box=None):
    from PySide6.QtWidgets import QGroupBox, QPushButton
    parent = dock
    if box is not None:
        parent = next(g for g in dock.findChildren(QGroupBox)
                      if g.title() == box)
    return next(b for b in parent.findChildren(QPushButton)
                if b.text() == text)


def test_a_bond_joins_the_copies_that_were_clicked(empty_document):
    """The same P1 atom is drawn once per cell in view.  Clicking the
    copy in the next cell along must bond *that* copy, not the one at
    the origin -- the stored bond carries the lattice translation."""
    from xtalapp.viewport.builder import build_scene

    _window, document = empty_document
    document.add_atom("C", [0.1, 0.5, 0.5])
    document.add_atom("O", [0.9, 0.5, 0.5])     # 8 A apart, 2 A across
    document.set_cells(2, 1, 1)                 # so both copies exist
    model = build_scene(document.structure, document.view)

    origin_c = _drawn(model, atom=0, cell=(0, 0, 0))
    next_o = _drawn(model, atom=1, cell=(-1, 0, 0))
    assert next_o is None                       # not in a (0,2) range
    next_c = _drawn(model, atom=0, cell=(1, 0, 0))
    origin_o = _drawn(model, atom=1, cell=(0, 0, 0))

    mode = modes.get("add_bond")
    mode.pending = None
    _click_atom(mode, document, model, origin_o)
    _click_atom(mode, document, model, next_c)

    bond = document.structure.bonds[0]
    assert (bond.i, bond.j) == (1, 0)
    assert bond.image == (1, 0, 0)              # the copy next door
    assert len(document.graph.bonds) == 1
    assert document.graph.bonds[0].distance == pytest.approx(2.0)

    assert origin_c is not None                 # the near pair exists
    document.undo()
    assert len(document.graph.bonds) == 0


def test_clicking_a_bond_names_the_atoms_it_really_joins(
        empty_document):
    """The bond half carries its own (i, j, image); guessing it back
    from the geometry is what used to delete the wrong bond."""
    from xtalapp.viewport.builder import build_scene

    _window, document = empty_document
    document.add_atom("C", [0.5, 0.5, 0.5])
    document.add_atom("O", [0.62, 0.5, 0.5])
    model = build_scene(document.structure, document.view)
    assert model.n_bond_halves == 2

    for half in range(model.n_bond_halves):
        assert model.bond_key(half) == document.graph.bonds[0].key()


def test_removing_a_bond_survives_hidden_atoms(empty_document):
    """Wireframe draws no atom geometry at all.  A bond click still
    has to name its ends."""
    from xtalapp.viewport.builder import build_scene

    _window, document = empty_document
    document.add_atom("C", [0.5, 0.5, 0.5])
    document.add_atom("O", [0.62, 0.5, 0.5])
    document.update_view(style="wireframe")
    model = build_scene(document.structure, document.view)
    assert model.n_atoms == 0 and model.n_bond_halves == 2

    mode = modes.get("add_bond")
    mode.pending = None
    middle = document.structure.lattice.to_cart([0.56, 0.5, 0.5])
    event = modes.ClickEvent(
        origin=(float(middle[0]), float(middle[1]), -10.0),
        direction=(0.0, 0.0, 1.0))
    assert mode.on_click(document, model, event) == "bond removed"
    assert len(document.graph.bonds) == 0


def _drawn(model, atom, cell):
    for i in range(model.n_atoms):
        if model.instance(i) == (atom, cell):
            return i
    return None


def _click_atom(mode, document, model, index):
    """Fire a click down z through drawn atom ``index``."""
    x, y, _z = model.positions[index]
    return mode.on_click(document, model, modes.ClickEvent(
        origin=(float(x), float(y), -50.0), direction=(0.0, 0.0, 1.0)))
