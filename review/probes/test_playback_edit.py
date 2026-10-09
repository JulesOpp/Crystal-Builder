"""Calling the method an action the selection handler re-enabled."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.document import Document, PlaybackActive  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Play{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


class _FakePlayback:
    index = 0
    path = None
    frame = None

    def clamp(self, i):
        return 0


def test_mark_connection_points_while_playing(window, quartz):
    doc = Document(quartz)
    window.add_document(doc)
    doc.select([0, 1], "set")
    doc.playback = _FakePlayback()          # a trajectory is open
    window._refresh_shell()
    assert not window.actions_["mark_connection_points"].isEnabled()
    window._on_selection_changed()          # the user clicks an atom
    assert window.actions_["mark_connection_points"].isEnabled()
    with pytest.raises(PlaybackActive):
        doc.duplicate_selection((1.0, 0.0, 0.0))  # what Duplicate calls
