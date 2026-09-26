"""Help > Set up an AI assistant: the window's door to the shipped skill.

Somebody who never opens a terminal still has to be able to find the
skill, and somebody who edited their installed copy must not lose the
edits to a menu entry.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox, QWidget  # noqa: E402

from xtal.agent import skill  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    # Never the developer's own ~/.claude.  USERPROFILE as well as
    # HOME: it is what Path.home() reads on Windows.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    settings = AppSettings("CrystalBuilderTest", f"Skill{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _help_entries(window) -> list[str]:
    bar = window.menuBar()
    menu = next(a.menu() for a in bar.actions() if a.text() == "&Help")
    return [a.text() for a in menu.actions()]


def test_the_ai_assistant_entry_is_in_the_help_menu(window):
    label = window.actions_["install_ai_skill"].text()
    assert label in _help_entries(window)
    assert window.actions_["install_ai_skill"].isEnabled()


def test_the_entry_installs_the_skill_where_claude_code_reads_it(
        window, tmp_path):
    window.actions_["install_ai_skill"].trigger()
    installed = tmp_path / "home" / ".claude" / "skills" / \
        "crystal-builder" / "SKILL.md"
    assert installed.read_text(encoding="utf-8") == \
        (skill.source() / "SKILL.md").read_text(encoding="utf-8")


def test_an_edited_copy_is_kept_when_the_answer_is_no(window, tmp_path,
                                                      monkeypatch):
    window.actions_["install_ai_skill"].trigger()
    installed = skill.target() / "SKILL.md"
    installed.write_text("my notes")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.No)
    window.actions_["install_ai_skill"].trigger()
    assert installed.read_text() == "my notes"
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    window.actions_["install_ai_skill"].trigger()
    assert installed.read_text() != "my notes"


def test_opening_an_entry_an_agent_worked_on_says_so(window, tmp_path,
                                                     rutile):
    """Somebody opening a project an assistant made should know it was
    made that way, and where the steps are written down."""
    from xtal.agent import Session
    from xtal.io import write_cif

    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    session = Session.open(cif, workspace=tmp_path / "ws")
    session.set_element([0], "Sn")
    project = session.save()
    window.open_path(project)
    message = window.statusBar().currentMessage()
    assert "AI assistant" in message
    assert "1 step" in message
