"""Help > User Manual: the manual in ``docs/manual``, opened in the
browser from the copy that ships with the application."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp import manual  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    """Stands in for the VTK viewport."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Man{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _front_page(root, *parts):
    page = root.joinpath(*parts, "index.html")
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    return page


def test_a_bundle_opens_the_manual_it_carries(tmp_path, monkeypatch):
    """The packaged copy, over one a checkout happens to have built:
    in a bundle there is no checkout, and in a checkout the bundled
    folder does not exist, so the order only matters for a test."""
    monkeypatch.setattr(manual, "root", lambda: tmp_path)
    built = _front_page(tmp_path, *manual.CHECKOUT)
    assert manual.index() == built
    shipped = _front_page(tmp_path, *manual.BUNDLED)
    assert manual.index() == shipped


def test_nothing_built_is_nothing_to_open(tmp_path, monkeypatch):
    monkeypatch.setattr(manual, "root", lambda: tmp_path)
    assert manual.index() is None


def test_the_help_menu_offers_the_manual_after_the_help_pages(window):
    """Where somebody who has read the generated pages looks next."""
    help_menu = next(a.menu() for a in window.menuBar().actions()
                     if a.text() == "&Help")
    names = [a.text() for a in help_menu.actions() if not a.isSeparator()]
    first = window.actions_["help_contents"].text()
    assert names[names.index(first) + 1] == \
        window.actions_["user_manual"].text()


def test_the_manual_opens_at_its_front_page_in_the_browser(
        window, tmp_path, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    page = _front_page(tmp_path, *manual.BUNDLED)
    monkeypatch.setattr(manual, "root", lambda: tmp_path)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url) or True)

    window.actions_["user_manual"].trigger()

    # As paths: on Windows the URL spells it C:/Users/..., the same
    # file with the other separator.
    assert [Path(u.toLocalFile()) for u in opened] == [page]


def test_a_checkout_that_never_built_it_is_told_how(
        window, tmp_path, monkeypatch):
    """Not a dead menu entry: the command that builds it, which is
    the manual CI job's own."""
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(manual, "root", lambda: tmp_path)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(url) or True)

    window.actions_["user_manual"].trigger()

    assert not opened
    said = window.statusBar().currentMessage()
    assert "sphinx-build -b html docs/manual build/manual/html" in said
