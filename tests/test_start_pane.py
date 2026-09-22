"""What the middle of the window shows when nothing is open.

It was an empty grey tab widget: no next step on the screen where a
first run decides whether to keep the program, though drag-and-drop
worked and seven structures were one menu away.  Every button on the
pane is a window action, so these tests check the pane swaps with the
tabs and that its buttons are the actions -- never its wording, which
is the user's to write.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.io import write_cif  # noqa: E402
from xtalapp import samples  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Start{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_an_empty_window_shows_the_start_pane(window):
    assert window.tabs.count() == 0
    assert window.central.currentWidget() is window.start_pane


def test_opening_a_structure_puts_the_tabs_in_front(window, tmp_path,
                                                    rutile):
    write_cif(rutile, tmp_path / "rutile.cif")

    window.open_path(tmp_path / "rutile.cif")

    assert window.central.currentWidget() is window.tabs


def test_closing_the_last_tab_brings_the_start_pane_back(window,
                                                         tmp_path,
                                                         rutile):
    write_cif(rutile, tmp_path / "rutile.cif")
    window.open_path(tmp_path / "rutile.cif")

    window.close_document(0)

    assert window.tabs.count() == 0
    assert window.central.currentWidget() is window.start_pane


def test_the_start_pane_buttons_are_the_window_actions(window):
    """So a label, a shortcut or a greyed sample is the registry's,
    and nothing here can drift from the File menu."""
    pane = window.start_pane
    assert pane.open_button.defaultAction() is window.actions_["open"]
    assert pane.new_button.defaultAction() is window.actions_["new"]
    for sample in samples.SAMPLES:
        button = pane.sample_buttons[sample.name]
        assert (button.defaultAction()
                is window.actions_[f"sample_{sample.name}"])


@pytest.mark.skipif(samples.get("mof5").path is None,
                    reason="the samples are not in this install")
def test_opening_a_sample_from_the_start_pane_opens_one_tab(window):
    window.start_pane.sample_buttons["mof5"].click()

    assert window.tabs.count() == 1
    assert window.central.currentWidget() is window.tabs
