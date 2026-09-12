"""A module run that answers in frames puts them in the transport bar."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.io.trajectory import Trajectory, frame_of  # noqa: E402
from xtal.modules import MODULES, Action, JobResult, Module  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Traj{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _frames(job):
    moved = job.structure.copy()
    moved.sites[1].frac = moved.sites[1].frac + [0.01, 0.0, 0.0]
    moved.touch()
    return JobResult(message="two frames", trajectory=Trajectory(
        [frame_of(job.structure, step=0), frame_of(moved, step=1)]))


@pytest.fixture
def frames_module():
    module = MODULES.register(Module(
        name="_frames", label="Frames", actions=(
            Action(name="go", label="Go", run=_frames,
                   writes_run_folder=False),)))
    yield module
    MODULES.unregister(module.name)


def test_the_frames_a_run_returns_are_played_against_its_tab(
        window, frames_module, rutile, qtbot):
    document = window.new_document()
    document.set_structure(rutile, modified=False)

    window.run_module_action("_frames", "go")
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    assert document.is_playing
    assert document.playback.n_frames == 2
    assert not document.modified


def test_frames_of_a_tab_no_longer_in_front_are_not_opened_over_another(
        window, frames_module, rutile, quartz, qtbot):
    ran = window.new_document()
    ran.set_structure(rutile, modified=False)
    window.run_module_action("_frames", "go")
    other = window.new_document()
    other.set_structure(quartz, modified=False)
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    assert not ran.is_playing
    assert not other.is_playing
