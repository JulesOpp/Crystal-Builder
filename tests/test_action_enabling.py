"""The selection's actions are enabled by one rule, whoever asks.

``_refresh_shell`` and ``_on_selection_changed`` used to decide the
same twelve actions separately, and only the first knew that a
trajectory being played makes the crystal read-only.  Clicking an atom
during playback turned Cut and Delete back on, and pressing one raised
``PlaybackActive`` into the log.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.io.trajectory import Trajectory, frame_of  # noqa: E402
from xtalapp import shell_state  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Enable{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _enabled(window) -> dict[str, bool]:
    return {name: window.actions_[name].isEnabled()
            for name in shell_state.SELECTION_ACTIONS}


def _playing(window, structure):
    document = window.new_document()
    document.set_structure(structure, modified=False)
    moved = structure.copy()
    moved.sites[0].frac = moved.sites[0].frac + [0.01, 0.0, 0.0]
    moved.touch()
    document.open_trajectory(Trajectory(
        [frame_of(structure, step=0), frame_of(moved, step=1)]))
    assert document.is_playing
    return document


def test_selecting_an_atom_during_playback_leaves_cut_greyed(
        window, rutile):
    """Cut, Duplicate and Delete would reach Document.run's refusal."""
    document = _playing(window, rutile)
    window._refresh_shell()

    document.select([0, 1])

    enabled = _enabled(window)
    for name in ("cut", "duplicate", "change_element",
                 "delete_selection", "add_centroid", "merge_atoms"):
        assert not enabled[name], name
    # Reading the selection is not editing it.
    assert enabled["copy"] and enabled["expand_bonded"]


@pytest.mark.parametrize("playing", [False, True])
def test_both_refresh_paths_agree_in_either_order(
        window, rutile, playing):
    """A second copy of the rule is what let the first drift."""
    document = (_playing(window, rutile) if playing
                else window.new_document())
    if not playing:
        document.set_structure(rutile, modified=False)
    document.select([0, 1])

    window._refresh_shell()
    window._on_selection_changed()
    selection_last = _enabled(window)
    window._on_selection_changed()
    window._refresh_shell()
    shell_last = _enabled(window)

    assert selection_last == shell_last
    assert shell_last == shell_state.selection_states(document)


def test_delete_is_enabled_by_a_bond_alone(window, rutile):
    """With a bond and no atom selected, Del once did nothing."""
    document = window.new_document()
    document.set_structure(rutile, modified=False)
    key = document.graph.bonds[0].key()

    document.select_bond(key)

    assert window.actions_["delete_selection"].isEnabled()
    assert window.actions_["delete_bond"].isEnabled()
    assert not window.actions_["cut"].isEnabled()


def test_closing_the_last_tab_greys_every_selection_action(
        window, rutile):
    """No document is a complete answer, not a stale one."""
    document = window.new_document()
    document.set_structure(rutile, modified=False)
    document.select([0, 1])
    window.close_all_documents(force=True)

    assert not any(_enabled(window).values())
