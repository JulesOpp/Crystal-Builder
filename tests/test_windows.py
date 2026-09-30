"""Bringing a window forward goes through one door, and the suite's
guard on that door keeps every test off the developer's screen."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget

from xtalapp import windows


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
