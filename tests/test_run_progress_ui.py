"""The window that says a module is running, and the plot it leaves.

Zeo++'s pore size distribution is minutes of a binary printing Voronoi
housekeeping into a log.  From the outside, a status line at the bottom
of a panel that may not be open is indistinguishable from a frozen
application -- which is what these are about.

The Zeo++ stand-in from tests/conftest_zeo.py is used, so nothing
here needs Zeo++ installed.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from tests.conftest_zeo import write_fake_network  # noqa: E402
from xtal.workspace import Workspace, classify  # noqa: E402
from xtalapp.dialogs.run_progress import (  # noqa: E402
    RunProgressDialog,
    _duration,
    _short,
)
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def fake_network(tmp_path, monkeypatch):
    """The Zeo++ stand-in, so these run without Zeo++ installed."""
    monkeypatch.setenv("XTAL_ZEOPP", str(write_fake_network(tmp_path)))


@pytest.fixture
def dialog(qtbot):
    widget = RunProgressDialog()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Prog{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


# ----------------------------------------------------------- the window

def test_it_does_not_appear_for_a_run_that_is_over_at_once(dialog,
                                                           qtbot):
    """A dialog that flashes up and away for a two-second run is worse
    than no dialog."""
    dialog.start("Stub: Count here", delay_ms=10_000)
    assert dialog.armed                     # waiting to appear
    assert not dialog.isVisible()

    dialog.finish()
    assert not dialog.isVisible()
    assert not dialog.armed


def test_it_appears_when_the_run_outlasts_the_delay(dialog, qtbot):
    dialog.start("Zeo++: Pore size distribution", delay_ms=0)
    assert dialog.isVisible()
    assert dialog.title.text() == "Zeo++: Pore size distribution"


def test_it_shows_the_last_thing_the_binary_said(dialog):
    dialog.start("Zeo++", delay_ms=0)
    dialog.set_progress("Performing Voronoi decomposition.")
    assert "Voronoi" in dialog.line.text()


def test_a_very_long_line_is_cut_rather_than_stretching_the_window(
        dialog):
    dialog.start("Zeo++", delay_ms=0)
    dialog.set_progress("x" * 400)
    assert len(dialog.line.text()) < 120


def test_the_bar_does_not_claim_to_know_how_far_along_it_is(dialog):
    """Zeo++ reports stages, not a fraction.  A bar creeping to 90%
    and sitting there is a worse lie than one that never claimed."""
    assert (dialog.bar.minimum(), dialog.bar.maximum()) == (0, 0)


def test_the_elapsed_time_is_shown(dialog):
    dialog.start("Zeo++", delay_ms=0)
    assert "so far" in dialog.elapsed.text()


def test_stop_asks_once_and_says_it_is_stopping(dialog, qtbot):
    """The gap between asking a binary to stop and it stopping is
    exactly when a user presses the button again."""
    dialog.start("Zeo++", delay_ms=0)
    with qtbot.waitSignal(dialog.stopRequested):
        dialog.stop_button.click()
    assert not dialog.stop_button.isEnabled()
    assert "Stopping" in dialog.stop_button.text()


def test_closing_the_window_hides_it_and_does_not_stop_the_run(dialog):
    """The worst thing this file could do is kill a four-minute
    calculation because its window was in the way."""
    dialog.start("Zeo++", delay_ms=0)
    stopped = []
    dialog.stopRequested.connect(lambda: stopped.append(True))

    dialog.close()

    assert not dialog.isVisible()
    assert not stopped


def test_durations_read_as_durations():
    assert _duration(9) == "9 s"
    assert _duration(90) == "1 min 30 s"
    assert _duration(3700) == "1 h 01 min"


def test_a_progress_line_is_squeezed_to_one_line():
    assert _short("  two\n  lines  ") == "two lines"


# ------------------------------------------------- through a real run

def test_a_run_arms_the_window_and_puts_it_away_afterwards(
        window, fake_network, rutile_cif, qtbot):
    document = window.open_path(rutile_cif)
    assert document is not None

    window.run_module_action("zeopp", "diameters")
    assert window.run_progress.armed

    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)
    assert not window.run_progress.isVisible()
    assert not window.run_progress.armed


def test_the_distribution_is_written_as_a_png_beside_the_run(
        window, fake_network, rutile_cif, qtbot, tmp_path):
    """A run folder holding four columns of numbers and no plot is one
    somebody has to reopen the application to look at."""
    window.set_workspace(Workspace.create(tmp_path / "space").root)
    document = window.open_path(rutile_cif)

    window.run_module_action("zeopp", "psd")
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    run = document.entry.runs()[-1]
    images = [a for a in run.artifacts() if a.kind == "image"]
    assert len(images) == 1
    assert images[0].path.suffix == ".png"
    assert images[0].path.stat().st_size > 1000


def test_the_log_names_the_plot_it_wrote(window, fake_network,
                                         rutile_cif, qtbot,
                                         tmp_path):
    """Written before the log is closed, so the log can name it the
    way it names every other artefact."""
    window.set_workspace(Workspace.create(tmp_path / "space").root)
    document = window.open_path(rutile_cif)

    window.run_module_action("zeopp", "psd")
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    run = document.entry.runs()[-1]
    assert ".png" in run.log_path.read_text()


def test_a_run_with_no_histogram_writes_no_png(window, fake_network,
                                               rutile_cif, qtbot,
                                               tmp_path):
    window.set_workspace(Workspace.create(tmp_path / "space").root)
    document = window.open_path(rutile_cif)

    window.run_module_action("zeopp", "diameters")
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    run = document.entry.runs()[-1]
    assert not [a for a in run.artifacts() if a.kind == "image"]


def test_a_png_is_its_own_kind_of_artefact():
    """So that clicking it in the tree opens it in a picture viewer
    rather than being handed to a structure reader that would refuse
    it."""
    assert classify("pore-size-distribution.png") == "image"
    assert classify("run.log") == "log"
