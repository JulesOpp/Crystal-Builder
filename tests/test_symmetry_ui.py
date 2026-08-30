"""The symmetry and cell workflow, through the application.

Every dialog here previews before it commits, so the tests drive the
preview as well as the result: a dialog that shows one number and
applies another is worse than one that shows nothing.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialog, QDialogButtonBox  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal import Lattice, Structure  # noqa: E402
from xtal.core import p1, symmetry  # noqa: E402
from xtalapp.dialogs.cell_edit import CellEditDialog  # noqa: E402
from xtalapp.dialogs.display_range import (  # noqa: E402
    DisplayRangeDialog,
)
from xtalapp.dialogs.find_symmetry import (  # noqa: E402
    FindSymmetryDialog,
)
from xtalapp.dialogs.spacegroup import SpaceGroupDialog  # noqa: E402
from xtalapp.dialogs.supercell import SupercellDialog  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Sym{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def document(rutile):
    return Document(rutile)


@pytest.fixture
def flat_document(rutile):
    """Rutile expanded to P1: the state a symmetry search starts from."""
    return Document(symmetry.reduce_to_p1(rutile))


def n_atoms(document):
    return p1.expand(document.structure).n_atoms


# ------------------------------------------------------- find symmetry

def test_find_symmetry_dialog_detects_and_tabulates(qtbot,
                                                    flat_document):
    dialog = FindSymmetryDialog(flat_document)
    qtbot.addWidget(dialog)
    assert "P4_2/mnm" in dialog.summary.text()
    assert dialog.table.rowCount() == 2              # Ti and O orbits
    letters = {dialog.table.item(row, 2).text()
               for row in range(dialog.table.rowCount())}
    assert letters == {"2a", "4f"}


def test_find_symmetry_dialog_follows_the_tolerance(qtbot, rutile):
    """The whole point of the control: change it and the answer
    changes."""
    nudged = symmetry.reduce_to_p1(rutile)
    nudged.sites[3].frac = nudged.sites[3].frac + [0.004, 0.0, 0.0]
    nudged.touch()
    dialog = FindSymmetryDialog(Document(nudged))
    qtbot.addWidget(dialog)

    dialog.tolerance.setCurrentText("1e-5")
    tight = dialog.info.number
    dialog.tolerance.setCurrentText("0.05")
    assert dialog.info.number > tight
    assert dialog.info.number == 136


def test_find_symmetry_dialog_survives_a_nonsense_tolerance(
        qtbot, flat_document):
    dialog = FindSymmetryDialog(flat_document)
    qtbot.addWidget(dialog)
    dialog.tolerance.setCurrentText("banana")
    assert dialog.info is None
    assert not dialog.adopt_button.isEnabled()
    dialog.tolerance.setCurrentText("1e-3")
    assert dialog.info is not None
    assert dialog.adopt_button.isEnabled()


def test_adopting_the_group_reduces_the_cell(qtbot, flat_document):
    dialog = FindSymmetryDialog(flat_document)
    qtbot.addWidget(dialog)
    dialog.tolerance.setCurrentText("1e-4")
    dialog.adopt()

    assert dialog.result() == QDialog.Accepted
    assert flat_document.structure.space_group.number == 136
    assert flat_document.structure.n_sites == 2
    assert n_atoms(flat_document) == 6
    assert flat_document.can_undo

    flat_document.undo()
    assert flat_document.structure.n_sites == 6


def test_labelling_wyckoff_moves_nothing(qtbot, document):
    before = [s.frac.copy() for s in document.structure.sites]
    dialog = FindSymmetryDialog(document)
    qtbot.addWidget(dialog)
    dialog.label_only()
    assert {s.wyckoff for s in document.structure.sites} == {"2a", "4f"}
    for site, frac in zip(document.structure.sites, before,
                          strict=True):
        assert np.allclose(site.frac, frac)


# --------------------------------------------------- space-group picker

def test_space_group_dialog_starts_on_the_current_group(qtbot,
                                                        document):
    dialog = SpaceGroupDialog(document)
    qtbot.addWidget(dialog)
    assert dialog.group() == document.structure.space_group
    assert dialog.mode() == "reinterpret"


def test_space_group_dialog_searches(qtbot, document):
    dialog = SpaceGroupDialog(document)
    qtbot.addWidget(dialog)
    dialog.search.setText("Fd-3m")
    assert dialog.list.count() == 2                  # two origin choices
    assert "F d -3 m" in dialog.list.item(0).text()

    dialog.search.setText("225")
    assert dialog.group().number == 225

    dialog.search.setText("no such group")
    assert dialog.list.count() == 0
    assert dialog.group() is None
    assert not dialog.buttons.button(
        QDialogButtonBox.Ok).isEnabled()


def test_space_group_dialog_previews_the_atom_count(qtbot):
    flat = Structure.from_arrays(
        Lattice.cubic(5.6402), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="P1")
    document = Document(flat)
    dialog = SpaceGroupDialog(document)
    qtbot.addWidget(dialog)
    dialog.search.setText("Fm-3m")
    dialog.select("Fm-3m")
    assert "8" in dialog.preview.text()              # 2 sites -> 8 atoms

    dialog.modes[1].setChecked(True)                 # impose
    assert dialog.mode() == "impose"
    assert dialog.preview.text()


def test_setting_a_group_is_undoable(qtbot, document):
    flat = Structure.from_arrays(
        Lattice.cubic(5.6402), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="P1")
    document = Document(flat)
    report = document.set_space_group("Fm-3m", "reinterpret")
    assert report.ok and n_atoms(document) == 8
    document.undo()
    assert n_atoms(document) == 2


def test_a_group_the_coordinates_cannot_support_is_not_applied(
        document):
    """A failed operation must leave the undo stack alone -- a Ctrl+Z
    that undoes nothing is worse than no Ctrl+Z."""
    report = document.set_space_group("Fm-3m", "impose")
    assert not report.ok
    assert not document.can_undo
    assert document.structure.space_group.number == 136


# ------------------------------------------------------------ supercell

def test_supercell_dialog_previews_and_builds(qtbot, document):
    dialog = SupercellDialog(document)
    qtbot.addWidget(dialog)
    for spin, value in zip(dialog.counts, (2, 2, 1), strict=True):
        spin.setValue(value)
    assert "24 atoms" in dialog.preview.text()

    document.operate(dialog.command())
    assert n_atoms(document) == 24
    assert document.structure.space_group.is_p1
    document.undo()
    assert n_atoms(document) == 6


def test_supercell_dialog_takes_a_general_matrix(qtbot, halite):
    document = Document(halite)
    dialog = SupercellDialog(document)
    qtbot.addWidget(dialog)
    dialog.tabs.setCurrentIndex(1)
    dialog.matrix[1][0].setValue(1)                  # b' = a + b
    assert np.allclose(dialog.p_matrix(),
                       [[1, 0, 0], [1, 1, 0], [0, 0, 1]])
    assert "atoms" in dialog.preview.text()

    document.operate(dialog.command())
    assert n_atoms(document) == n_atoms(Document(halite))


def test_a_singular_matrix_disables_ok(qtbot, document):
    dialog = SupercellDialog(document)
    qtbot.addWidget(dialog)
    dialog.tabs.setCurrentIndex(1)
    dialog.matrix[1][1].setValue(0)                  # det P = 0
    assert not dialog.buttons.button(
        QDialogButtonBox.Ok).isEnabled()
    assert dialog.preview.text()


# ------------------------------------------------------------ cell edit

def test_cell_edit_dialog_offers_both_meanings(qtbot):
    triclinic = Structure.from_arrays(
        Lattice.from_parameters(5.0, 6.0, 7.0, 88, 92, 97), ["C"],
        [[0.0, 0.0, 0.0]], space_group="P1")
    dialog = CellEditDialog(triclinic)
    qtbot.addWidget(dialog)
    assert dialog.parameters() == pytest.approx(
        (5.0, 6.0, 7.0, 88, 92, 97))
    assert all(spin.isEnabled() for spin in dialog.spins)

    dialog.spins[0].setValue(10.0)
    assert "2" in dialog.preview.text()              # twice the volume
    assert dialog.keep() == "fractional"
    dialog.keeps[1].setChecked(True)
    assert dialog.keep() == "cartesian"
    assert "stay where they are" in dialog.preview.text()

    dialog.reset()
    assert dialog.parameters() == pytest.approx(
        (5.0, 6.0, 7.0, 88, 92, 97))


def test_cell_edit_refuses_angles_that_do_not_close(qtbot):
    triclinic = Structure.from_arrays(
        Lattice.from_parameters(5.0, 6.0, 7.0, 88, 92, 97), ["C"],
        [[0.0, 0.0, 0.0]], space_group="P1")
    dialog = CellEditDialog(triclinic)
    qtbot.addWidget(dialog)
    for spin in dialog.spins[3:]:
        spin.setValue(170.0)
    assert dialog.lattice() is None or dialog.lattice().volume <= 0
    assert not dialog.buttons.button(
        QDialogButtonBox.Ok).isEnabled()


# --------------------------------------------- the symmetry constraint

def test_cell_edit_locks_what_the_group_decides(qtbot, quartz):
    """Quartz is trigonal: only a and c are real numbers.  The others
    must not be editable, because a hexagonal cell with b != a is not a
    cell its own operations map onto itself."""
    dialog = CellEditDialog(quartz)
    qtbot.addWidget(dialog)
    free = [i for i, spin in enumerate(dialog.spins)
            if spin.isEnabled()]
    assert free == [0, 2]                            # a and c
    assert "only a, c" in dialog.symmetry_note.text()
    assert "reduce to P1" in dialog.symmetry_note.text()


def test_editing_a_free_parameter_drags_the_tied_ones(qtbot, quartz):
    dialog = CellEditDialog(quartz)
    qtbot.addWidget(dialog)
    dialog.spins[0].setValue(7.5)                    # a
    a, b, c, alpha, beta, gamma = dialog.parameters()
    assert a == pytest.approx(7.5)
    assert b == pytest.approx(7.5)                   # b follows a
    assert (alpha, beta, gamma) == pytest.approx((90, 90, 120))
    assert dialog.lattice() is not None


def test_a_cubic_cell_has_one_number(qtbot, halite):
    dialog = CellEditDialog(halite)
    qtbot.addWidget(dialog)
    assert [i for i, s in enumerate(dialog.spins) if s.isEnabled()] \
        == [0]
    dialog.spins[0].setValue(6.0)
    assert dialog.parameters() == pytest.approx(
        (6.0, 6.0, 6.0, 90, 90, 90))


def test_reducing_to_p1_frees_the_cell(qtbot, quartz):
    """The documented way out of a symmetry constraint has to actually
    work."""
    from xtal.core import symmetry

    locked = CellEditDialog(quartz)
    qtbot.addWidget(locked)
    assert sum(s.isEnabled() for s in locked.spins) == 2

    freed = CellEditDialog(symmetry.reduce_to_p1(quartz))
    qtbot.addWidget(freed)
    assert all(s.isEnabled() for s in freed.spins)
    assert "every parameter is free" in freed.symmetry_note.text()


def test_the_constraint_survives_a_round_trip_through_the_document(
        quartz):
    """Whatever the dialog offers, the cell that lands on the document
    must be one the group allows."""
    document = Document(quartz)
    constraint = quartz.space_group.cell_constraint
    document.set_lattice(
        Lattice.from_parameters(*constraint.apply(
            (6.0, 3.0, 4.0, 70.0, 80.0, 100.0))))
    assert constraint.allows(document.structure.lattice.parameters,
                             tol=1e-4)
    assert document.structure.lattice.parameters == pytest.approx(
        (6.0, 6.0, 4.0, 90.0, 90.0, 120.0))


def test_setting_the_cell_keeps_what_it_says(document):
    lattice = document.structure.lattice
    before = lattice.to_cart(document.structure.sites[1].frac)
    stretched = lattice.with_parameters(a=lattice.lengths[0] * 1.5)

    document.set_lattice(stretched, "cartesian")
    after = document.structure.lattice.to_cart(
        document.structure.sites[1].frac)
    assert np.allclose(before, after)
    document.undo()
    assert document.structure.lattice.almost_equal(lattice)


# --------------------------------------------------------- display range

def test_display_range_dialog_edits_the_view_only(qtbot, document):
    dialog = DisplayRangeDialog(document)
    qtbot.addWidget(dialog)
    assert dialog.ranges() == ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))

    dialog.los[0].setValue(-0.5)
    dialog.his[0].setValue(1.5)
    dialog.bonded.setChecked(True)
    document.update_view(range_a=dialog.ranges()[0],
                         boundary=dialog.boundary())

    assert document.view.range_a == (-0.5, 1.5)
    assert document.view.boundary == "bonded"
    assert not document.modified                     # view, not crystal
    assert not document.can_undo


def test_display_range_dialog_refuses_a_backwards_range(qtbot,
                                                        document):
    dialog = DisplayRangeDialog(document)
    qtbot.addWidget(dialog)
    dialog.his[1].setValue(-1.0)
    assert not dialog.buttons.button(
        QDialogButtonBox.Ok).isEnabled()
    assert "ends before it starts" in dialog.preview.text()

    dialog.reset()
    assert dialog.ranges() == ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


# ------------------------------------------------------------ the menus

def test_the_symmetry_and_cell_menus_reach_the_document(window,
                                                        rutile_cif):
    document = window.open_path(rutile_cif)

    window.actions_["supercell"]                     # exists
    window.actions_["wrap_cell"].trigger()
    window.actions_["niggli"].trigger()
    window.actions_["wyckoff"].trigger()
    assert {s.wyckoff for s in document.structure.sites} == {"2a", "4f"}

    window.actions_["reduce_p1"].trigger()
    assert document.structure.n_sites == 6
    assert document.stack.depth == 4
    while document.can_undo:
        document.undo()
    assert document.structure.n_sites == 2


def test_menu_actions_need_a_document(window):
    for name in ("find_symmetry", "set_space_group", "supercell",
                 "edit_cell", "niggli", "wrap_cell", "display_range"):
        assert not window.actions_[name].isEnabled()


def test_a_failing_operation_warns_instead_of_crashing(window,
                                                       rutile_cif,
                                                       monkeypatch):
    """spglib raises on a cell it cannot make sense of.  The window has
    to turn that into a message, not a traceback."""
    from PySide6.QtWidgets import QMessageBox

    document = window.open_path(rutile_cif)
    document.set_structure(Structure.empty(Lattice.cubic(5.0)))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warned.append(a[-1]))

    window.actions_["primitive"].trigger()
    assert warned
    assert document.structure.n_sites == 0
