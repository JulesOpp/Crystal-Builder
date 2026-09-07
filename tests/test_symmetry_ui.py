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
from xtalapp.dialogs.merge_duplicates import (  # noqa: E402
    MergeDuplicatesDialog,
)
from xtalapp.dialogs.spacegroup import SpaceGroupDialog  # noqa: E402
from xtalapp.dialogs.subgroup import SubgroupDialog  # noqa: E402
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


@pytest.fixture
def shifted(rutile):
    """The same coordinates with the origin moved off the standard
    setting -- the cell the dialog cannot adopt without re-expressing
    it, and the common case a file from somewhere else arrives in."""
    out = symmetry.reduce_to_p1(rutile)
    for site in out.sites:
        site.frac = np.mod(site.frac + np.array([0.13, 0.07, 0.21]),
                           1.0)
    out.touch()
    return out


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


def test_re_expressing_the_cell_is_offered_ticked(qtbot,
                                                  flat_document):
    """The common case is a cell that is not in the standard setting,
    and *Adopt* refuses outright without this -- so unticked meant a
    box to find and tick before the dialog would do the thing it was
    opened for."""
    dialog = FindSymmetryDialog(flat_document)
    qtbot.addWidget(dialog)
    assert dialog.standardize.isChecked()


def test_a_cell_in_another_setting_is_adopted_as_it_stands(qtbot,
                                                           shifted):
    """Nothing to tick: the origin shift is re-expressed away and the
    group is adopted in one press."""
    document = Document(shifted)
    dialog = FindSymmetryDialog(document)
    qtbot.addWidget(dialog)
    dialog.tolerance.setCurrentText("1e-4")
    assert not dialog.info.is_standard_setting

    dialog.adopt()

    assert dialog.result() == QDialog.Accepted
    assert document.structure.space_group.number == 136
    assert document.structure.n_sites == 2
    assert dialog.re_expressed


def test_adopting_in_the_standard_setting_re_expresses_nothing(
        qtbot, flat_document):
    """The camera still frames the cell, because the cell has not
    moved -- only the number of sites inside it has."""
    dialog = FindSymmetryDialog(flat_document)
    qtbot.addWidget(dialog)
    dialog.tolerance.setCurrentText("1e-4")
    dialog.adopt()

    assert flat_document.structure.n_sites == 2
    assert not dialog.re_expressed


def test_labelling_wyckoff_re_expresses_nothing(qtbot, shifted):
    """Both buttons come back Accepted and only one of them moves an
    atom, which is why the dialog has to say which happened."""
    dialog = FindSymmetryDialog(Document(shifted))
    qtbot.addWidget(dialog)
    dialog.label_only()

    assert dialog.result() == QDialog.Accepted
    assert not dialog.re_expressed


def test_finding_symmetry_resets_the_view_when_the_cell_moves(
        monkeypatch, window, shifted, tmp_path):
    """The camera belongs to the viewport, so the reset is the
    window's -- the same split the subgroup descent keeps."""
    from xtal.io import write_cif
    path = tmp_path / "shifted.cif"
    write_cif(shifted, path)
    window.open_path(path)
    document = window.current_document()
    viewport = window.current_viewport()
    monkeypatch.setattr(FindSymmetryDialog, "exec",
                        lambda self: self.adopt())
    before = viewport.resets

    window.actions_["find_symmetry"].trigger()

    assert document.structure.space_group.number == 136
    assert viewport.resets == before + 1


def test_finding_symmetry_leaves_a_settled_camera_alone(
        monkeypatch, window, rutile_cif):
    """Labelling Wyckoff letters moves nothing, and a view that jumps
    for it is a view that jumped for no reason."""
    window.open_path(rutile_cif)
    viewport = window.current_viewport()
    monkeypatch.setattr(FindSymmetryDialog, "exec",
                        lambda self: self.label_only())
    before = viewport.resets

    window.actions_["find_symmetry"].trigger()

    assert viewport.resets == before


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
    dialog.boundaries["bonded"].setChecked(True)
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


# ---------------------------------------------------- descend to a subgroup

@pytest.fixture
def quartz_document(quartz):
    return Document(quartz)


def test_subgroup_dialog_lists_the_subgroups(qtbot, quartz_document):
    """P3_2, one row for the three conjugate C2, and P1 at the bottom.

    P1 belongs in the list: dropping every rotation and keeping the
    lattice is a descent like any other, and reaching it from here
    gives the primitive cell of the group rather than the conventional
    one Reduce to P1 leaves you in.
    """
    dialog = SubgroupDialog(quartz_document)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 3
    assert "P 32 2 1" in dialog.heading.text()
    symbols = {dialog.table.item(row, 0).text()
               for row in range(dialog.table.rowCount())}
    assert symbols == {"P 32", "C 1 2 1", "P 1"}


def test_subgroup_dialog_offers_more_than_the_maximal_ones(qtbot,
                                                           document):
    """Rutile's list is not seven rows of index 2: everything below
    them is reachable directly, and the maximal ones are marked so the
    step-by-step path is still visible."""
    dialog = SubgroupDialog(document)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 26
    marks = [dialog.table.item(row, 3).text()
             for row in range(dialog.table.rowCount())]
    assert marks.count("maximal") == 7
    indices = {int(dialog.table.item(row, 2).text())
               for row in range(dialog.table.rowCount())}
    assert indices > {2}                    # deeper descents are there


def test_conjugate_subgroups_are_one_row_that_says_so(qtbot,
                                                      quartz_document):
    """Collapsing must not hide: the row carries the count."""
    dialog = SubgroupDialog(quartz_document)
    qtbot.addWidget(dialog)
    row = next(r for r in range(dialog.table.rowCount())
               if dialog.table.item(r, 0).text() == "C 1 2 1")
    assert dialog.table.item(row, 4).text() == "1 of 3"
    dialog.table.setCurrentCell(row, 0)
    assert "conjugate under the parent" in dialog.detail.text()


def test_subgroup_dialog_says_what_splits(qtbot, quartz_document):
    """The third column is the reason the dialog exists: quartz's one
    oxygen becomes two independent oxygens in P3_2."""
    dialog = SubgroupDialog(quartz_document)
    qtbot.addWidget(dialog)
    row = next(r for r in range(dialog.table.rowCount())
               if dialog.table.item(r, 0).text() == "P 32")
    dialog.table.setCurrentCell(row, 0)
    assert "2 -> 3 sites" in dialog.table.item(row, 5).text()
    assert "independent sites" in dialog.detail.text()


def test_subgroup_dialog_says_when_nothing_splits(qtbot, document):
    """Six of rutile's seven maximal subgroups leave both sites whole,
    and a list that did not say so would look broken for all six."""
    dialog = SubgroupDialog(document)
    qtbot.addWidget(dialog)
    unsplit = None
    for row in range(dialog.table.rowCount()):
        dialog.table.setCurrentCell(row, 0)
        if "none split" in dialog.table.item(row, 5).text():
            unsplit = row
            break
    assert unsplit is not None
    assert "No orbit splits" in dialog.detail.text()


def test_every_row_is_tellable_apart(qtbot, document):
    """Whatever survives the collapsing has to be distinguishable, or
    the list has rows nobody can choose between."""
    dialog = SubgroupDialog(document)
    qtbot.addWidget(dialog)
    rows = {(dialog.table.item(r, 0).text(),
             dialog.table.item(r, 2).text(),
             dialog.table.item(r, 6).text())
            for r in range(dialog.table.rowCount())}
    assert len(rows) == dialog.table.rowCount()


def test_subgroup_dialog_applies_the_row_it_previewed(qtbot,
                                                      quartz_document):
    dialog = SubgroupDialog(quartz_document)
    qtbot.addWidget(dialog)
    row = next(r for r in range(dialog.table.rowCount())
               if dialog.table.item(r, 0).text() == "P 32")
    dialog.table.setCurrentCell(row, 0)
    before = n_atoms(quartz_document)
    report = quartz_document.descend_to_subgroup(dialog.subgroup())
    assert report.ok
    assert quartz_document.structure.space_group.short_name == "P32"
    assert quartz_document.structure.n_sites == 3
    assert n_atoms(quartz_document) == before


def test_descending_resets_the_view(monkeypatch, window, quartz_cif):
    """A descent can halve the cell or swap its axes, so the camera
    that framed the old one frames the new one badly."""
    window.open_path(quartz_cif)
    document = window.current_document()
    viewport = window.current_viewport()
    subgroup = document.maximal_subgroups()[0]
    monkeypatch.setattr(SubgroupDialog, "ask",
                        staticmethod(
                            lambda doc, parent=None:
                            doc.descend_to_subgroup(subgroup)))
    before = viewport.resets
    window.actions_["subgroup"].trigger()
    assert document.structure.space_group.short_name == "P32"
    assert viewport.resets == before + 1


def test_the_view_resets_after_a_descent_that_moves_the_cell(
        monkeypatch, window, quartz_cif):
    """The case that needs it most: descending to C2 re-expresses the
    hexagonal cell on C-centred monoclinic axes, which is where the old
    camera framing is worst.  It also puts up the note about the new
    cell, so the modal is answered here rather than left to block."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: QMessageBox.Ok)
    window.open_path(quartz_cif)
    document = window.current_document()
    viewport = window.current_viewport()
    subgroup = next(s for s in document.subgroups()
                    if not s.keeps_the_cell)
    monkeypatch.setattr(SubgroupDialog, "ask",
                        staticmethod(
                            lambda doc, parent=None:
                            doc.descend_to_subgroup(subgroup)))
    before = viewport.resets
    window.actions_["subgroup"].trigger()
    assert document.structure.space_group.short_name == "C2"
    assert viewport.resets == before + 1


def test_a_cancelled_descent_leaves_the_view_alone(monkeypatch, window,
                                                   quartz_cif):
    window.open_path(quartz_cif)
    viewport = window.current_viewport()
    monkeypatch.setattr(SubgroupDialog, "ask",
                        staticmethod(lambda doc, parent=None: None))
    before = viewport.resets
    window.actions_["subgroup"].trigger()
    assert viewport.resets == before


def test_descending_is_one_undo_step(quartz_document):
    subgroup = quartz_document.maximal_subgroups()[0]
    quartz_document.descend_to_subgroup(subgroup)
    assert quartz_document.structure.n_sites == 3
    quartz_document.undo()
    assert quartz_document.structure.n_sites == 2
    assert quartz_document.structure.space_group.short_name == "P3221"


def test_p1_offers_no_subgroups(qtbot, flat_document):
    dialog = SubgroupDialog(flat_document)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 0
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert "no proper subgroups" in dialog.detail.text()


# ------------------------------------------------------------- inversion

def test_inverting_through_the_document(quartz_document):
    report = quartz_document.invert_structure()
    assert report.ok
    assert quartz_document.structure.space_group.short_name == "P3121"
    quartz_document.undo()
    assert quartz_document.structure.space_group.short_name == "P3221"


def test_the_inversion_preview_says_which_case_this_is(document,
                                                       quartz_document):
    assert "centrosymmetric" in document.preview_inversion().message
    assert "P3221 -> P3121" in \
        quartz_document.preview_inversion().message


def test_the_info_dock_shows_the_hand(qtbot, window, quartz_cif):
    window.open_path(quartz_cif)
    text = window.info_dock.text.toPlainText()
    assert "hand" in text
    assert "enantiomorph P3121" in text


def test_inverting_a_centrosymmetric_structure_asks_nothing(
        monkeypatch, window, rutile_cif):
    """No confirmation, no undo entry: the structure it would produce
    is the one already open."""
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: shown.append(a[2]))
    window.open_path(rutile_cif)
    window.actions_["invert"].trigger()
    assert shown and "centrosymmetric" in shown[0]
    assert not window.current_document().stack.can_undo


def test_inverting_a_chiral_structure_asks_first(monkeypatch, window,
                                                 quartz_cif):
    from PySide6.QtWidgets import QMessageBox
    asked = []

    def answer(*args, **_kwargs):
        asked.append(args[2])
        return QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "question", answer)
    window.open_path(quartz_cif)
    window.actions_["invert"].trigger()
    assert asked and "P3221 -> P3121" in asked[0]
    assert window.current_document().structure.space_group.short_name \
        == "P3121"


# --------------------------------------------------- merge duplicates

@pytest.fixture
def doubled(quartz):
    """Quartz with its Si written a second time, as the symmetry image
    a CIF exported from a full cell would have written."""
    from xtal.core.site import Site
    cell = p1.expand(quartz)
    s = quartz.copy()
    s.add_site(Site("Si", cell.frac[cell.indices_of_site(0)[1]],
                    label="Si1A"))
    return Document(s)


def test_merge_dialog_counts_the_atoms_at_the_tolerance(qtbot,
                                                        doubled):
    dialog = MergeDuplicatesDialog(doubled)
    qtbot.addWidget(dialog)
    assert dialog.tol.value() == pytest.approx(
        symmetry.DEFAULT_MERGE_TOL)
    assert "12 atoms in the cell become 9" in dialog.summary.text()
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_merge_dialog_disables_ok_with_nothing_to_merge(qtbot,
                                                        document):
    """Rutile has no duplicates at any tolerance, and a Merge button
    that pushes an empty undo step is worse than a disabled one."""
    dialog = MergeDuplicatesDialog(document)
    qtbot.addWidget(dialog)
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert "no duplicates" in dialog.summary.text()


def test_the_merge_slider_and_the_number_stay_together(qtbot,
                                                       doubled):
    dialog = MergeDuplicatesDialog(doubled)
    qtbot.addWidget(dialog)
    dialog.slider.setValue(dialog._to_slider(0.3))
    assert dialog.tol.value() == pytest.approx(0.3, abs=0.01)
    dialog.tol.setValue(0.02)
    assert dialog.slider.value() == dialog._to_slider(0.02)


def test_the_merge_dialog_applies_the_tolerance_it_previewed(
        monkeypatch, qtbot, doubled):
    monkeypatch.setattr(MergeDuplicatesDialog, "exec",
                        lambda self: QDialog.Accepted)
    report = MergeDuplicatesDialog.ask(doubled)
    assert report.merged == 1
    assert doubled.structure.n_sites == 2
    assert p1.expand(doubled.structure).n_atoms == 9


def test_cancelling_the_merge_dialog_changes_nothing(monkeypatch,
                                                     qtbot, doubled):
    monkeypatch.setattr(MergeDuplicatesDialog, "exec",
                        lambda self: QDialog.Rejected)
    assert MergeDuplicatesDialog.ask(doubled) is None
    assert doubled.structure.n_sites == 3


def test_the_merge_menu_item_asks_for_the_tolerance(monkeypatch,
                                                    window,
                                                    quartz_cif):
    """It ran at the 0.05 A default with nothing to set, which made the
    one setting that decides the answer unreachable."""
    asked = []

    def ask(cls, document, parent=None):
        asked.append(document)
        return document.merge_duplicates(0.5)

    monkeypatch.setattr(MergeDuplicatesDialog, "ask",
                        classmethod(ask))
    window.open_path(quartz_cif)
    window.actions_["merge_duplicates"].trigger()
    assert asked == [window.current_document()]
