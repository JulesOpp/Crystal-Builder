"""Structure > Fill pores with molecules, through its dialog.

The dialog is driven through its methods and never ``exec`` -- see
``tests/conftest.py``, which makes reaching a modal fail the test.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialogButtonBox, QWidget  # noqa: E402

from xtal import Lattice, Structure  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtalapp.dialogs.fill_pores import FillPoresDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Fill{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def sparse():
    """Room for a lot of CO2, and a group to be reduced out of."""
    return Structure.from_arrays(Lattice.cubic(14.0), ["Na"],
                                 [[0.0, 0.0, 0.0]], space_group="Fm-3m")


def _host_and_solvent(window, sparse, dry_ice):
    solvent = window.new_document()
    solvent.set_structure(dry_ice, modified=False)
    host = window.new_document()
    host.set_structure(sparse, modified=False)
    return host, solvent


def _dialog(window, qtbot, host):
    sources = [(d.title, d.structure) for d in window.documents]
    dialog = FillPoresDialog(host, sources, window)
    qtbot.addWidget(dialog)
    return dialog


def test_the_dialog_offers_the_molecule_from_the_other_tab(
        window, qtbot, sparse, dry_ice):
    """The host has no molecule in it; the tab that has one is chosen
    without being asked for, and what is offered is its formula."""
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _dialog(window, qtbot, host)

    assert dialog.source.currentIndex() == 0
    assert dialog.molecule.count() == 1
    assert dialog.molecule.currentText().startswith("CO2")
    assert "room for at most about" in dialog.headline.text()
    assert "Fm-3m" in dialog.detail.text()
    assert "not recalculated" in dialog.detail.text()
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert host.structure.n_sites == 1          # nothing yet


def test_a_source_with_only_a_framework_offers_nothing(window, qtbot,
                                                        rutile, sparse):
    host = window.new_document()
    host.set_structure(sparse, modified=False)
    dialog = FillPoresDialog(host, [("rutile", rutile)], window)
    qtbot.addWidget(dialog)

    assert dialog.molecule.count() == 0
    assert dialog.headline.text() == "no molecule to fill with"
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_a_file_can_be_the_source(window, qtbot, tmp_path, sparse,
                                  dry_ice):
    host = window.new_document()
    host.set_structure(sparse, modified=False)
    path = tmp_path / "solvent.cif"
    write_cif(dry_ice, path)
    dialog = FillPoresDialog(host, [], window)
    qtbot.addWidget(dialog)
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()

    assert dialog.open_file(path)
    assert dialog.source.currentText() == "solvent.cif"
    assert dialog.molecule.currentText().startswith("CO2")


def test_filling_is_one_undo_step_and_selects_what_arrived(
        window, qtbot, sparse, dry_ice):
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _dialog(window, qtbot, host)
    dialog.count.setValue(6)

    message = dialog.fill()

    assert message == "placed 6 CO2"
    assert host.structure.space_group.is_p1
    assert host.structure.n_sites == 4 + 18
    assert len(host.selection.atoms) == 18
    assert host.modified
    host.undo()
    assert host.structure.space_group.short_name == "Fm-3m"
    assert host.structure.n_sites == 1
    assert not host.can_undo


def test_fill_pores_is_an_edit_and_greys_with_the_others(window):
    action = window.actions_["fill_pores"]
    assert not action.isEnabled()               # no document
    window.new_document()
    assert action.isEnabled()


def test_one_beside_each_atom_needs_a_selection_and_greys_the_count(
        window, qtbot, sparse, dry_ice):
    """The count is the selection's in this mode, so its box is not
    the question; and with nothing selected there is nothing to put a
    copy beside, which is said rather than discovered after Fill."""
    from xtalapp.dialogs.fill_pores import BESIDE

    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _dialog(window, qtbot, host)
    assert not dialog.near.isEnabled()

    dialog.where.setCurrentText(BESIDE)

    assert not dialog.count.isEnabled()
    assert dialog.near.isEnabled()
    assert "select the atoms" in dialog.headline.text()
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_filling_beside_the_selection_places_one_each_in_one_step(
        window, qtbot, sparse, dry_ice):
    """Two of the four sodiums selected: two CO2, one by each, and one
    Ctrl+Z takes them and the reduction to P1 back together."""
    from xtalapp.dialogs.fill_pores import BESIDE

    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    host.select([0, 1])
    dialog = _dialog(window, qtbot, host)
    dialog.where.setCurrentText(BESIDE)
    assert "beside each of 2 selected atom(s)" in dialog.headline.text()

    message = dialog.fill()

    assert message == "placed 2 CO2, one beside each of 2 atom(s)"
    assert host.structure.space_group.is_p1
    assert host.structure.n_sites == 4 + 6
    host.undo()
    assert host.structure.space_group.short_name == "Fm-3m"
    assert not host.can_undo


# ------------------------------------------------------- at a point

def _at_point(window, qtbot, host):
    from xtalapp.dialogs.fill_pores import AT_POINT
    dialog = _dialog(window, qtbot, host)
    dialog.where.setCurrentText(AT_POINT)
    return dialog


def test_at_a_point_greys_the_count_and_shows_the_point(
        window, qtbot, sparse, dry_ice):
    """One molecule is the count, so its box is not the question; the
    point and its options are, and the button says what it does."""
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _dialog(window, qtbot, host)
    assert not dialog.point.isEnabled()
    assert not dialog.turn.isEnabled()

    from xtalapp.dialogs.fill_pores import AT_POINT
    dialog.where.setCurrentText(AT_POINT)

    assert not dialog.count.isEnabled()
    assert not dialog.near.isEnabled()
    assert dialog.point.isEnabled()
    assert dialog.turn.isEnabled()
    assert dialog.keep_group.isEnabled()        # Fm-3m
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert ok.text() == "Insert"
    assert ok.isEnabled()
    assert "will insert one CO2 at (0.5000, 0.5000, 0.5000)" in \
        dialog.headline.text()
    assert "reduced to P1" in dialog.detail.text()


def test_inserting_at_a_point_is_one_undo_step_and_selects_it(
        window, qtbot, sparse, dry_ice):
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _at_point(window, qtbot, host)
    dialog.set_point((0.3, 0.2, 0.1))

    report = dialog.fill()

    assert report.message == "placed CO2 at (0.3000, 0.2000, 0.1000)"
    assert report.warnings == []
    assert host.structure.space_group.is_p1
    assert host.structure.n_sites == 4 + 3
    assert len(host.selection.atoms) == 3
    host.undo()
    assert host.structure.space_group.short_name == "Fm-3m"
    assert not host.can_undo


def test_keeping_the_group_lets_it_copy_the_molecule(
        window, qtbot, sparse, dry_ice):
    """Kept, the host stays Fm-3m and the preview's atom count is the
    cell's."""
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _at_point(window, qtbot, host)
    dialog.set_point((0.11, 0.23, 0.37))
    dialog.keep_group.setChecked(True)
    assert "copies it to 576 atoms" in dialog.detail.text()

    dialog.fill()

    assert host.structure.space_group.short_name == "Fm-3m"
    assert host.cell.n_atoms == 4 + 576


def test_from_selection_fills_in_the_selection_centre(
        window, qtbot, sparse, dry_ice):
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    host.select([0, 1])
    dialog = _at_point(window, qtbot, host)
    assert dialog.from_selection.isEnabled()

    dialog.from_selection.click()

    assert dialog.frac == pytest.approx(tuple(host.selection_centre()))
    assert dialog.frac != pytest.approx((0.5, 0.5, 0.5))


def test_keep_the_group_is_disabled_on_a_p1_host(window, qtbot,
                                                 dry_ice):
    """A P1 host has no group to keep, and a ticked box that does
    nothing is a question with no answer."""
    host, _solvent = _host_and_solvent(
        window, Structure.empty(Lattice.cubic(14.0)), dry_ice)
    dialog = _at_point(window, qtbot, host)
    dialog.keep_group.setChecked(True)
    assert not dialog.keep_group.isEnabled()
    assert not dialog.keeping_group


def test_a_clash_at_the_point_is_warned_before_insert(
        window, qtbot, sparse, dry_ice):
    """On top of the sodium: the preview names the contact and still
    offers Insert -- the point was chosen."""
    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    dialog = _at_point(window, qtbot, host)
    dialog.set_point((0.0, 0.0, 0.0))

    assert not dialog.warning.isHidden()
    assert "Crowded" in dialog.warning.text()
    assert "Na" in dialog.warning.text()
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()

    report = dialog.fill()
    assert report.warnings
    assert host.structure.n_sites == 4 + 3


def test_a_crowded_insert_puts_up_the_warning_box(
        window, qtbot, monkeypatch, sparse, dry_ice):
    """After the fact too: the status bar alone is gone in eight
    seconds, and a molecule on top of an atom is worth a box."""
    from PySide6.QtWidgets import QMessageBox

    host, _solvent = _host_and_solvent(window, sparse, dry_ice)
    guest = FillPoresDialog(host, [(d.title, d.structure)
                                   for d in window.documents]).guest()
    shown = []
    monkeypatch.setattr(
        FillPoresDialog, "ask",
        classmethod(lambda cls, document, *a, **k:
                    document.insert_molecule(guest, (0, 0, 0))))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *args: shown.append(args[2]))

    window.fill_pores_dialog()

    assert len(shown) == 1 and "Crowded" in shown[0]


def test_a_file_source_can_be_inserted_at_a_point(
        window, qtbot, tmp_path, sparse, dry_ice):
    """The molecule from one file into the structure of another --
    the whole of the request this mode answers."""
    from xtalapp.dialogs.fill_pores import AT_POINT

    host = window.new_document()
    host.set_structure(sparse, modified=False)
    path = tmp_path / "solvent.cif"
    write_cif(dry_ice, path)
    dialog = FillPoresDialog(host, [], window)
    qtbot.addWidget(dialog)
    assert dialog.open_file(path)
    dialog.where.setCurrentText(AT_POINT)
    dialog.set_point((0.25, 0.25, 0.25))

    report = dialog.fill()

    assert report.message.startswith("placed CO2 at (0.2500,")
    assert host.structure.n_sites == 4 + 3
