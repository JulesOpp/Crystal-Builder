"""Bringing a window forward goes through one door, and the suite
keeps every window it shows off the developer's screen."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from xtalapp import windows

#: A run with windows shown on purpose, to watch a test.
_WATCHED = pytest.mark.skipif(
    bool(os.environ.get("XTAL_SHOW_TEST_WINDOWS")),
    reason="XTAL_SHOW_TEST_WINDOWS draws the suite's windows")


class _Stub(QWidget):
    """Stands in for the VTK viewport."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


def test_no_window_is_brought_forward_outside_present():
    """A second caller of ``activateWindow`` is a test run taking the
    keyboard again, one window at a time -- the refinement workbench
    did it 63 times a run before there was one door."""
    offenders = [
        path.as_posix() for path in sorted(Path("xtalapp").rglob("*.py"))
        if path.name != "windows.py"
        and "activateWindow(" in path.read_text(encoding="utf-8")]
    assert offenders == []


@_WATCHED
def test_a_window_a_test_presents_is_shown_but_never_drawn(qtbot):
    """``isVisible`` stays true, so a test asking whether a window
    opened still asks something real; nothing reaches the screen."""
    window = QMainWindow()
    qtbot.addWidget(window)
    windows.present(window)
    assert window.isVisible()
    assert window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    assert window.testAttribute(
        Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_the_refinement_workbench_opens_through_present(
        qtbot, tmp_path, monkeypatch):
    """The workbench is the window that took focus; it has to come
    through the door the guard stands on."""
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest", f"Win{tmp_path.name}")
    settings.clear_window()
    window = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(window)
    presented = []
    monkeypatch.setattr(windows, "present", presented.append)
    bench = window.open_refine_workbench()
    assert presented == [bench]


@_WATCHED
def test_a_window_a_test_shows_itself_is_never_on_screen(qtbot):
    """42 tests call ``show()`` on a dock, a dialog or a whole window;
    each one used to be drawn over the developer's work."""
    window = QMainWindow()
    qtbot.addWidget(window)
    window.show()
    window.raise_()
    assert window.isVisible()
    handle = window.windowHandle()
    assert handle is None or not handle.isVisible()


def test_present_without_activating_leaves_the_keyboard_alone(
        monkeypatch):
    calls = []
    window = SimpleNamespace(
        show=lambda: calls.append("show"),
        raise_=lambda: calls.append("raise"),
        activateWindow=lambda: calls.append("activate"))
    monkeypatch.undo()                  # the real present, not the guard's
    windows.present(window, activate=False)
    assert calls == ["show", "raise"]
    calls.clear()
    windows.present(window)
    assert calls == ["show", "raise", "activate"]


def test_links_made_before_their_parent_never_become_a_window(qtbot):
    """Preferences builds each row's links and then adds them: shown
    on the way, they were a window of their own, one per row, each
    taking the keyboard as the dialog opened."""
    from xtalapp.widgets.links import SourceLinks

    reference = SimpleNamespace(url="https://example.org", label="Paper")
    links = SourceLinks([reference])
    assert not links.isVisible()        # not a window of its own
    parent = QWidget()
    qtbot.addWidget(parent)
    QVBoxLayout(parent).addWidget(links)
    parent.show()
    assert links.isVisible()
    links.set_references([])
    assert not links.isVisible()
    links.set_references([reference])
    assert links.isVisible()

