"""The window fits the screen, and the keys people press work.

Both of these are things that only break on somebody else's machine:
a geometry saved on an external monitor, a laptop keyboard with no
numeric block.  So they are tested against a stated screen rectangle
rather than against whatever display the test happens to run on.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QRect, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp import settings as app_settings  # noqa: E402
from xtalapp.actions import key_sequences  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import (  # noqa: E402
    AppSettings,
    default_size,
    fit_to_screen,
)
from xtalapp.viewport.widget import is_vtk_reserved_key  # noqa: E402


class StubViewport(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Layout{tmp_path.name}")
    settings.clear_recent_files()
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    return settings


@pytest.fixture
def window(qtbot, settings):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def small_screen(monkeypatch):
    """A 1280x800 laptop, minus a menu bar -- the machine the window
    was opening off the bottom of."""
    area = QRect(0, 25, 1280, 775)
    monkeypatch.setattr(app_settings, "screen_area",
                        lambda window=None: area)
    return area


# --------------------------------------------------------------- keys

def test_key_sequences_takes_one_or_many():
    assert key_sequences("Del") == [QKeySequence("Del")]
    assert key_sequences(["Del", "Backspace"]) == [
        QKeySequence("Del"), QKeySequence("Backspace")]


def test_delete_is_bound_to_both_delete_keys(window):
    """The key labelled `delete` on a laptop sends Backspace, and
    QKeySequence("Del") does not match it."""
    bound = window.actions_["delete_selection"].shortcuts()
    assert QKeySequence(Qt.Key_Backspace) in bound
    assert QKeySequence(Qt.Key_Delete) in bound


@pytest.mark.parametrize("text,modifier,reserved", [
    ("e", Qt.NoModifier, True),      # VTK: close the render window
    ("w", Qt.NoModifier, True),      # VTK: wireframe, behind our menu
    ("3", Qt.NoModifier, True),      # VTK: red/cyan stereo
    ("s", Qt.ControlModifier, False),   # ours: Save
    ("a", Qt.NoModifier, False),     # nobody's
])
def test_vtk_hotkeys_are_swallowed_but_ours_are_not(text, modifier,
                                                    reserved):
    event = QKeyEvent(QEvent.KeyPress, ord(text.upper()), modifier, text)
    assert is_vtk_reserved_key(event) is reserved


# ------------------------------------------------------------- screen

def test_a_fresh_window_fits_a_small_screen(small_screen):
    width, height = default_size()
    assert width <= small_screen.width()
    assert height <= small_screen.height()


def test_default_size_is_capped_on_a_huge_screen(monkeypatch):
    monkeypatch.setattr(app_settings, "screen_area",
                        lambda window=None: QRect(0, 0, 5120, 2880))
    assert default_size() == app_settings.MAX_DEFAULT_SIZE


def test_default_size_survives_having_no_screen(monkeypatch):
    monkeypatch.setattr(app_settings, "screen_area",
                        lambda window=None: None)
    assert default_size() == app_settings.MAX_DEFAULT_SIZE


def test_a_window_restored_from_a_bigger_monitor_comes_back(
        qtbot, small_screen):
    """The failure this exists for: a geometry saved on an external
    display, restored on the laptop, and saved again on quit -- with no
    way out of it but deleting the preferences."""
    stray = QWidget()
    qtbot.addWidget(stray)
    stray.setGeometry(QRect(2200, 400, 1800, 1200))   # another monitor

    fit_to_screen(stray)

    assert small_screen.contains(stray.frameGeometry())


def test_fitting_a_window_that_already_fits_changes_nothing(
        qtbot, small_screen):
    fine = QWidget()
    qtbot.addWidget(fine)
    fine.setGeometry(QRect(100, 100, 400, 300))
    fit_to_screen(fine)
    assert fine.geometry() == QRect(100, 100, 400, 300)


# ------------------------------------------------------------- layout

def test_only_two_docks_open_on_a_first_run(window):
    """Seven panels tabbed on the right take, between them, the width
    the viewport is there to use."""
    visible = {d.objectName() for d in window.docks if not d.isHidden()}
    assert visible == {window.file_dock.objectName(),
                       window.inspector_dock.objectName()}


def test_reset_layout_puts_the_panels_back(window, settings):
    window.style_dock.setVisible(True)
    window.file_dock.setVisible(False)
    window.file_dock.setFloating(True)

    window.reset_layout()

    # isHidden rather than isVisible: the window itself is never shown
    # in a headless test, so nothing in it is ever "visible".
    assert not window.file_dock.isHidden()
    assert not window.file_dock.isFloating()
    assert window.style_dock.isHidden()


def test_reset_layout_forgets_the_saved_geometry(window, settings):
    settings.save_window(window)
    assert settings._q.value("geometry") is not None
    window.reset_layout()
    assert settings._q.value("geometry") is None
