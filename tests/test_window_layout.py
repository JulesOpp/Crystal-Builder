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

def test_only_the_three_starting_docks_open_on_a_first_run(window):
    """Seven panels tabbed on the right take, between them, the width
    the viewport is there to use.  What opens instead is the three a
    person editing a structure reads: what it is, where it came from,
    and the asymmetric unit."""
    visible = {d.objectName() for d in window.docks if not d.isHidden()}
    assert visible == {window.info_dock.objectName(),
                       window.file_dock.objectName(),
                       window.sites_dock.objectName()}


def test_the_first_run_puts_structure_and_workspace_down_the_left(
        window):
    """Structure over Workspace, split and not tabbed -- tabbing them
    would mean never seeing both -- with Sites raised on the right.
    A default layout that hides half of itself behind a tab bar is
    the one people rearrange before they start."""
    assert window.info_dock in window.left_docks
    assert window.file_dock in window.left_docks
    assert window.sites_dock in window.right_docks
    assert (window.dockWidgetArea(window.info_dock)
            == Qt.LeftDockWidgetArea)
    assert (window.dockWidgetArea(window.file_dock)
            == Qt.LeftDockWidgetArea)
    assert (window.dockWidgetArea(window.sites_dock)
            == Qt.RightDockWidgetArea)
    assert window.info_dock not in window.tabifiedDockWidgets(
        window.file_dock)


def test_reset_layout_lands_on_the_default_arrangement(window):
    """Reset layout is the way back, so it has to arrive at the same
    place a first run does -- one function and not two descriptions
    of the same thing."""
    window.style_dock.setVisible(True)
    window.sites_dock.setVisible(False)
    window.addDockWidget(Qt.RightDockWidgetArea, window.info_dock)

    window.reset_layout()

    visible = {d.objectName() for d in window.docks if not d.isHidden()}
    assert visible == {window.info_dock.objectName(),
                       window.file_dock.objectName(),
                       window.sites_dock.objectName()}
    assert (window.dockWidgetArea(window.info_dock)
            == Qt.LeftDockWidgetArea)


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


# ------------------------------------------------------------ resizing

def test_no_panel_insists_on_more_room_than_a_column_can_spare(window):
    """A dock area is as wide as the widest minimum of any dock shown
    in it.  The Measure panel's was 419 px, Net's and Structure's 380,
    Move's 566 px of height, so a column with one of them open would
    not drag narrower however small the panel in front was.  A panel
    that needs more room scrolls instead."""
    from xtalapp.docks import MAXIMUM_MINIMUM

    too_big = {d.windowTitle(): (d.minimumSizeHint().width(),
                                 d.minimumSizeHint().height())
               for d in window.docks
               if max(d.minimumSizeHint().width(),
                      d.minimumSizeHint().height()) > MAXIMUM_MINIMUM}
    assert too_big == {}


def test_opening_every_panel_leaves_the_column_free_to_narrow(
        qtbot, window):
    """Which panels had been opened decided whether dragging the
    divider did anything, so it seemed to work only sometimes.  With
    all eight right-hand panels open the column stopped at 397 px --
    the tab bar, eight elided titles wide -- before a single panel's
    own minimum was reached."""
    from xtalapp.docks import MAXIMUM_MINIMUM

    window.show()
    qtbot.waitExposed(window)
    for dock in window.right_docks:
        dock.show()
    window.sites_dock.raise_()
    window.resizeDocks([window.sites_dock], [100], Qt.Horizontal)
    qtbot.wait(50)
    assert window.sites_dock.width() <= MAXIMUM_MINIMUM


def test_tabbed_panels_scroll_their_tabs_rather_than_widen(qtbot,
                                                           window):
    """Qt makes a new tab bar whenever docks are tabbed together --
    the default layout, a restored one, a panel dropped on another --
    so each has to arrive with scroll arrows, not only the first."""
    from PySide6.QtWidgets import QTabBar

    window.show()
    qtbot.waitExposed(window)
    window.tabifyDockWidget(window.info_dock, window.modules_dock)
    window.modules_dock.show()
    qtbot.wait(50)
    bars = [b for b in window.findChildren(QTabBar)
            if b.parent() is window]
    assert bars
    assert all(b.usesScrollButtons() for b in bars)


def test_the_viewport_does_not_make_the_panels_native_windows(qtbot,
                                                              window):
    """VTK draws into a native window, and by default Qt makes every
    sibling of one native too: all fourteen docks were separate macOS
    views, the ones tabbed out of sight parked off every screen, and
    dragging and resizing them was unreliable."""
    from xtalapp.application import keep_siblings_non_native

    keep_siblings_non_native()
    native = QWidget(window.tabs)
    native.winId()
    window.show()
    qtbot.waitExposed(window)
    assert not [d.windowTitle() for d in window.docks
                if d.testAttribute(Qt.WA_NativeWindow)]


def test_the_left_column_still_starts_wide_enough_for_structure(
        qtbot, window):
    """Structure's 380 px was a minimum, and it set the first-run width
    as a side effect.  It is a starting width now, so the cell
    parameters are not clipped when the window first opens."""
    from xtalapp.layout import DEFAULT_LEFT_WIDTH

    window.show()
    qtbot.waitExposed(window)
    assert window.info_dock.width() >= DEFAULT_LEFT_WIDTH - 10
