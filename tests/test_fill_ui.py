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
