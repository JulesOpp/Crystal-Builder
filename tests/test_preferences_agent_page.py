"""Preferences > AI assistant: the switch, and the two lines to paste.

The page is the only place a person learns how to point an assistant
at this window.  A line with a stale port or token is one that fails
in the assistant's log with nothing in the window saying why.
"""

import importlib.util

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal import install  # noqa: E402
from xtal.agent import discovery  # noqa: E402
from xtalapp.dialogs.preferences import AgentPage  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def settings(tmp_path):
    return AppSettings("CrystalBuilderTest", f"AgentPage{tmp_path.name}")


@pytest.fixture
def window(qtbot, tmp_path, settings, monkeypatch):
    monkeypatch.setenv(discovery.ENV, str(tmp_path / "appdata"))
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_the_settings_default_to_off_on_7781(settings):
    assert settings.agent_serve is False
    assert settings.agent_port == 7781
    settings.agent_serve = True
    settings.agent_port = 7790
    assert settings.agent_serve is True
    assert settings.agent_port == 7790


def test_the_page_shows_both_connection_lines_with_the_live_port_and_token(
        qtbot, window):
    pytest.importorskip("mcp")
    dialog = window.preferences_dialog()
    qtbot.addWidget(dialog)
    page = dialog.page(AgentPage.TITLE)
    assert page.status.text() == "Off"

    with qtbot.waitSignal(window.agent_server.started, timeout=10000):
        page.serve.setChecked(True)

    server = window.agent_server
    assert page.status.text() == f"Listening on 127.0.0.1:{server.port}"
    http = page.http.text()
    assert http.startswith("claude mcp add --transport http "
                           "crystal-builder ")
    assert f"http://127.0.0.1:{server.port}/mcp" in http
    assert f'--header "Authorization: Bearer {server.token}"' in http
    assert page.stdio.text() == AgentPage.stdio_line()
    assert page.stdio.text().endswith(" mcp")
    assert str(discovery.launcher()) in page.stdio.text()


def test_the_port_is_kept_for_the_next_start(qtbot, window):
    dialog = window.preferences_dialog()
    qtbot.addWidget(dialog)
    page = dialog.page(AgentPage.TITLE)

    with qtbot.waitSignal(dialog.portChanged):
        page.port.setValue(7790)

    assert window.settings.agent_port == 7790
    assert window.agent_server.preferred_port == 7790


def test_without_the_extra_the_switch_is_off_and_says_what_to_install(
        qtbot, settings, monkeypatch):
    real = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if name == "mcp":
            return None
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    page = AgentPage(settings)
    qtbot.addWidget(page)

    assert not page.serve.isEnabled()
    assert install.command("mcp") in page.status.text()
    assert "(install the mcp extra)" in page.stdio_note.text()
