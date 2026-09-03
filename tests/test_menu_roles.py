"""Which entries macOS moves into the application menu, said out loud.

Quit, About and Preferences do not stay where a menu bar puts them on
macOS: Qt relocates them into the *Crystal Builder* menu, which is
where every Mac user looks for them.  Left to itself Qt decides which
entries those are by reading their **English** text, so the relocation
works until an entry is reworded -- and then stops, silently, on one
platform.

These assert the role and not where the action is drawn.  A test that
looked for Quit in the File menu would pass on Linux CI and fail on the
machine this is developed on, which is the worst kind of test to own.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.actions import ActionRegistry  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Roles{tmp_path.name}")
    settings.clear_window()
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_quit_says_it_is_the_quit_entry(window):
    assert window.actions_["quit"].menuRole() == \
        QAction.MenuRole.QuitRole


def test_about_says_it_is_the_about_entry(window):
    assert window.actions_["about"].menuRole() == \
        QAction.MenuRole.AboutRole


def test_an_action_given_no_role_is_left_to_qt(qtbot):
    """The default has to stay the heuristic: a hundred-odd actions
    belong in the menus they were added to, and NoRole would be a
    different claim about them."""
    parent = QWidget()
    qtbot.addWidget(parent)
    registry = ActionRegistry(parent)

    action = registry.add("plain", "&Plain")

    assert action.menuRole() == QAction.MenuRole.TextHeuristicRole
