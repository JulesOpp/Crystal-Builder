"""The main toolbar's own widgets: the element box and its periodic
table, and the words between the boxes."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.viewport import modes  # noqa: E402
from xtalapp.widgets.periodic_table import PeriodicTableDialog  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Bar{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_toolbar_words_use_the_toolbar_buttons_font(window):
    """A bare label takes the application font, 13 pt on macOS, among
    buttons drawn at 10: "cells" and "along" read as a different
    size from everything around them."""
    expected = QApplication.font("QToolButton").pointSizeF()
    labels = window.toolbar.findChildren(QLabel)
    words = [label for label in labels
             if label.text().strip() in ("cells", "along", "a", "b", "c")]
    assert len(words) == 5
    for label in words:
        assert label.font().pointSizeF() == expected


def test_the_table_button_fills_the_element_box_and_picks_add_atom(
        window, monkeypatch):
    """Picking from the toolbar's table is asking to place that
    element: the box shows it, Add atom places it, and the mouse is
    in Add atom -- not in whatever mode it was in before."""
    monkeypatch.setattr(PeriodicTableDialog, "ask",
                        classmethod(lambda cls, parent, current: "Pd"))
    window.set_mode("select")
    window.element_table.click()
    assert window.element_combo.currentText() == "Pd"
    assert modes.get("add_atom").element == "Pd"
    assert window.actions_["mode_add_atom"].isChecked()


def test_cancelling_the_table_leaves_the_element_and_the_mode(
        window, monkeypatch):
    monkeypatch.setattr(PeriodicTableDialog, "ask",
                        classmethod(lambda cls, parent, current: None))
    window.set_mode("select")
    window.element_table.click()
    assert window.element_combo.currentText() == "C"
    assert window.actions_["mode_select"].isChecked()
