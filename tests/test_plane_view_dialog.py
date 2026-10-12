"""View ▸ Along (hkl)...: looking straight onto a lattice plane.

The dialog stays open so that several planes can be stepped through,
which is why it is a window of its own and not an ``exec``: whatever
it does, it does to the tab in front *when Look is pressed*, and it
never touches the document -- a camera is not an edit.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.dialogs.plane_view import PlaneViewDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    """Records the planes it was asked to look along."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.planes = []

    def look_along_plane(self, hkl):
        self.planes.append(tuple(hkl))


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Plane{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _dialog(window) -> PlaneViewDialog:
    window.actions_["view_hkl"].trigger()
    return window.plane_view_dialog


def _set(dialog, hkl) -> None:
    for spin, value in zip(dialog.indices, hkl, strict=True):
        spin.setValue(value)


def test_look_turns_the_viewport_onto_the_plane(window, quartz_cif):
    """The chain from the menu to the camera; breaks if the action,
    the dialog or the window method drops the index on the way."""
    window.open_path(quartz_cif)
    dialog = _dialog(window)
    _set(dialog, (1, 1, 0))
    dialog.look_button.click()
    assert window.current_viewport().planes == [(1, 1, 0)]


def test_the_dialog_stays_open_after_looking(window, quartz_cif):
    """Stepping through (100), (110), (111) is the use: a dialog that
    closed on Look would have to be reopened for each."""
    window.open_path(quartz_cif)
    dialog = _dialog(window)
    dialog.look_button.click()
    assert dialog.isVisible()
    _set(dialog, (1, 1, 1))
    dialog.look_button.click()
    assert window.current_viewport().planes == [(0, 0, 1), (1, 1, 1)]


def test_a_zero_index_cannot_be_looked_along(window, quartz_cif):
    """(0 0 0) has no normal; Look is greyed and says why rather than
    handing the camera nothing to point along."""
    window.open_path(quartz_cif)
    dialog = _dialog(window)
    _set(dialog, (0, 0, 0))
    assert not dialog.look_button.isEnabled()
    assert not dialog.hint.isHidden()
    dialog.look()
    assert window.current_viewport().planes == []
    _set(dialog, (0, 1, 0))
    assert dialog.look_button.isEnabled()
    assert dialog.hint.isHidden()


def test_opening_it_twice_raises_the_same_dialog(window, quartz_cif):
    """One per window, keeping the last index: a second dialog would
    be two answers to which plane is being looked along."""
    window.open_path(quartz_cif)
    first = _dialog(window)
    _set(first, (2, -1, 3))
    first.close()
    second = _dialog(window)
    assert second is first
    assert second.hkl() == (2, -1, 3)


def test_look_acts_on_the_tab_in_front_when_pressed(
        window, quartz_cif, rutile_cif):
    """The dialog outlives a tab switch, so it must not have kept the
    viewport it was opened over."""
    window.open_path(quartz_cif)
    dialog = _dialog(window)
    quartz_view = window.current_viewport()
    window.open_path(rutile_cif)
    dialog.look_button.click()
    assert window.current_viewport().planes == [(0, 0, 1)]
    assert quartz_view.planes == []


def test_looking_never_marks_the_document_modified(window, quartz_cif):
    document = window.open_path(quartz_cif)
    dialog = _dialog(window)
    dialog.look_button.click()
    assert not document.modified


def test_the_action_is_off_with_no_structure_open(window, quartz_cif):
    window.close_all_documents(force=True)
    assert not window.actions_["view_hkl"].isEnabled()
    window.open_path(quartz_cif)
    assert window.actions_["view_hkl"].isEnabled()


def test_it_is_in_the_view_menu_after_the_axis_views(window):
    """Asked for in the View menu, beside Along a, b and c."""
    view_menu = next(a.menu() for a in window.menuBar().actions()
                     if a.text().replace("&", "") == "View")
    actions = view_menu.actions()
    positions = [actions.index(window.actions_[key]) for key in
                 ("view_a", "view_b", "view_c", "view_hkl", "reset_view")]
    assert positions == sorted(positions)


def test_return_looks_and_does_not_close(window, quartz_cif, qtbot):
    """Return in an index box is Look: on macOS the button box made
    Close the default, so typing an index and pressing Return shut the
    dialog instead of turning the view."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton
    window.open_path(quartz_cif)
    dialog = _dialog(window)
    defaults = [b.text() for b in dialog.findChildren(QPushButton)
                if b.isDefault()]
    assert defaults == ["Look"]
    _set(dialog, (1, 0, 1))
    qtbot.keyClick(dialog.indices[2], Qt.Key_Return)
    assert window.current_viewport().planes == [(1, 0, 1)]
    assert dialog.isVisible()
