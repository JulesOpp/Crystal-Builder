"""The status bar says one thing at a time.

Its left half is two texts: the line describing the crystal (a label
added to the bar) and a passing message (``showMessage``).  Qt hides the
label under a message only if the label is visible when the message
arrives, so a message said before the window was shown -- a file's
import warnings, at launch or from Finder -- left both painted over each
other, and neither could be read.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Status{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_a_passing_message_before_the_window_shows_does_not_overlap(
        window, qtbot, rutile_cif):
    """The case that was reported: a structure opened, a message said,
    and only then the window shown."""
    window.open_path(rutile_cif)
    window.show_message("opened with a warning")
    window.show()
    qtbot.wait(10)

    assert window.statusBar().currentMessage() == "opened with a warning"
    assert not window.status_label.isVisible()


def test_the_status_line_comes_back_after_a_passing_message(
        window, qtbot, rutile_cif):
    window.open_path(rutile_cif)
    window.show()
    window.show_message("in passing", 20)

    qtbot.waitUntil(lambda: not window.statusBar().currentMessage(),
                    timeout=2000)
    assert window.status_label.isVisible()
    assert "TiO2" in window.status_label.text()
