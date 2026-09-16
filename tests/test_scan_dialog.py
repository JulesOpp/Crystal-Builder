"""Setting up a relaxed scan.

A scan is the one calculation here that can take all night, so the
dialog's job is to make three things unmissable before Run: how many
points, how long, and what is held fixed while each relaxes.  Most of
what is pinned below is those three, plus the refusal to offer a cell
parameter the space group does not leave free -- which would produce a
structure its own symmetry operations no longer fit, with nothing
downstream reporting it.

The widget is built and its methods are called; ``exec`` is never
reached, because ``QDialog.exec`` raises in this suite.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.modules.registry import MODULES  # noqa: E402
from xtalapp.dialogs.scan import ScanDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Dlg{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _dialog(qtbot, window, structure_path):
    window.open_path(structure_path)
    module, action = MODULES.find("scan.run")
    dialog = ScanDialog(module, action, window)
    qtbot.addWidget(dialog)
    return dialog


@pytest.fixture
def hexagonal(qtbot, window):
    """Ni2Cl2BTDD: H-3m, and a and c are every free parameter it has.

    The structure the whole feature was asked for.
    """
    return _dialog(qtbot, window, "resources/samples/Ni2Cl2BTDD.cif")


@pytest.fixture
def triclinic(qtbot, window, tmp_path, quartz):
    from xtal.io import write_cif
    path = tmp_path / "quartz.cif"
    write_cif(quartz, path)
    return _dialog(qtbot, window, path)


def _offered(dialog):
    box = dialog.first.kind
    return [box.itemData(i) for i in range(box.count())]


# ----------------------------------------------------------------------
#  Which coordinates are on offer
# ----------------------------------------------------------------------

def test_the_dialog_offers_only_the_parameters_the_group_leaves_free(
        hexagonal):
    """H-3m leaves a and c.  Offering b would be offering a structure
    whose own operations no longer map it onto itself."""
    offered = _offered(hexagonal)
    assert "a" in offered and "c" in offered
    assert "b" not in offered
    assert "gamma" not in offered


def test_a_tied_parameter_is_named_beside_the_one_it_follows(
        hexagonal):
    """"Scanning a also moves b" is the whole difference between a
    trigonal crystal and a broken one, so it is on the label rather
    than in a tooltip."""
    box = hexagonal.first.kind
    label = box.itemText(box.findData("a"))
    assert "b follows it" in label


def test_the_volume_and_every_internal_coordinate_are_always_offered(
        hexagonal):
    offered = _offered(hexagonal)
    for name in ("volume", "distance", "angle", "torsion", "plane"):
        assert name in offered


def test_only_the_second_axis_may_be_none(hexagonal):
    """A scan needs at least one coordinate; the second is the one
    that turns a profile into a landscape."""
    assert "" not in _offered(hexagonal)
    assert "" in [hexagonal.second.kind.itemData(i)
                  for i in range(hexagonal.second.kind.count())]


# ----------------------------------------------------------------------
#  What it says before the click
# ----------------------------------------------------------------------

def test_a_cell_axis_opens_on_a_range_around_the_crystal(hexagonal):
    """Typing 38.528 twice to find out where the cell already is
    would be a poor first impression."""
    box = hexagonal.first
    assert box.start.value() < 38.528 < box.stop.value()


def test_the_axis_says_what_the_coordinate_is_now(hexagonal):
    assert "38.5" in hexagonal.first.status.text()


def test_the_summary_counts_the_points_and_the_hours(hexagonal):
    """A twelve-by-twelve grid of a real framework is a couple of
    hours, and that is a thing to learn from a dialog rather than
    from the clock."""
    hexagonal.first.steps.setValue(7)
    hexagonal.second.kind.setCurrentIndex(
        hexagonal.second.kind.findData("c"))
    hexagonal.second.steps.setValue(7)
    said = hexagonal.summary.text()
    assert "98 points" in said
    assert "hours" in said or "minutes" in said


def test_the_summary_says_what_will_be_held(hexagonal):
    """A profile that does not say what was fixed cannot be read, and
    the place to learn it is before the scan, not after."""
    assert "holding a" in hexagonal.summary.text()


def test_scanning_every_free_parameter_holds_the_cell_fixed(
        hexagonal):
    """The measurement the design turns on, surfaced in the dialog: a
    and c are all H-3m leaves free, so the cell needs no strain
    variables at all."""
    hexagonal.second.kind.setCurrentIndex(
        hexagonal.second.kind.findData("c"))
    assert "cell held fixed" in hexagonal.summary.text()


def test_scanning_one_of_them_relaxes_the_other(hexagonal):
    assert "cell relaxed" in hexagonal.summary.text()


def test_a_volume_axis_says_the_shape_relaxes(hexagonal):
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("volume"))
    assert "holding volume" in hexagonal.summary.text()


# ----------------------------------------------------------------------
#  Internal coordinates
# ----------------------------------------------------------------------

def test_the_atom_box_is_only_for_an_internal_coordinate(hexagonal):
    assert not hexagonal.first.atoms.isEnabled()
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("torsion"))
    assert hexagonal.first.atoms.isEnabled()


def test_a_half_typed_coordinate_says_so_and_does_not_run(hexagonal):
    """The ordinary state of a dialog being filled in is not an
    error to raise, it is a message under the box."""
    from PySide6.QtWidgets import QDialogButtonBox

    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("torsion"))
    hexagonal.first.atoms.setText("0 1 2")
    assert "4 anchors" in hexagonal.first.status.text()
    assert not hexagonal.buttons.button(
        QDialogButtonBox.Ok).isEnabled()


def test_a_finished_coordinate_reports_its_value(hexagonal):
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("distance"))
    hexagonal.first.atoms.setText("0 1")
    assert "distance 0-1 is" in hexagonal.first.status.text()


def test_the_selection_fills_an_anchor(hexagonal, window):
    """A group of several atoms is their centroid, which is how "the
    middle of that ring" is said."""
    document = window.current_document()
    document.selection.set_atoms([4, 5, 6])
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("distance"))
    hexagonal.first.from_selection.click()
    assert hexagonal.first.atoms.text() == "4,5,6"


def test_two_selections_make_two_anchors(hexagonal, window):
    document = window.current_document()
    document.selection.set_atoms([4, 5, 6])
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("distance"))
    hexagonal.first.from_selection.click()
    document.selection.set_atoms([9])
    hexagonal.first.from_selection.click()
    assert hexagonal.first.spec() == "distance 4,5,6 9"
    assert "distance {4,5,6}-9 is" in hexagonal.first.status.text()


def test_adding_nothing_says_nothing_is_selected(hexagonal, window):
    window.current_document().selection.clear()
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("distance"))
    hexagonal.first.from_selection.click()
    assert "nothing is selected" in hexagonal.first.status.text()


# ----------------------------------------------------------------------
#  What it hands back
# ----------------------------------------------------------------------

def test_the_values_are_the_grammar_the_module_reads(hexagonal):
    """One way of writing an axis for the dialog, the command line and
    the log, so a scan can be re-run from the line it printed."""
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("torsion"))
    hexagonal.first.atoms.setText("0 1 2 3")
    assert hexagonal.values()["axis1"] == "torsion 0 1 2 3"


def test_an_empty_second_axis_comes_back_empty(hexagonal):
    assert hexagonal.values()["axis2"] == ""


def test_the_engine_comes_from_the_force_field_panel(hexagonal,
                                                     window):
    """One place to set an engine up.  The same bargain the DFTB+ run
    dialog strikes with the Hamiltonian."""
    assert hexagonal.values()["engine"] == window.ff_dock.engine_name()


def test_the_values_round_trip_through_set_values(hexagonal):
    """So that running a scan again offers what was run last time."""
    hexagonal.first.kind.setCurrentIndex(
        hexagonal.first.kind.findData("volume"))
    hexagonal.first.steps.setValue(11)
    before = hexagonal.values()
    hexagonal.set_values(before)
    assert hexagonal.values()["axis1"] == before["axis1"]
    assert hexagonal.values()["axis1_steps"] == 11


def test_the_dialog_is_what_the_action_asks_for():
    """Registered by name, which is also what the bundle reads: a
    dialog reached only through importlib is invisible to PyInstaller
    and raises the first time anybody clicks it in a frozen build."""
    from xtalapp.dialogs import dialog_modules, module_dialog

    assert module_dialog("scan") is ScanDialog
    assert "xtalapp.dialogs.scan" in dialog_modules()
    _module, action = MODULES.find("scan.run")
    assert action.dialog == "scan"
