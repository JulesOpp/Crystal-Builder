"""Structure ▸ Determine topology on TopCryst...: a file written, its
folder shown and the site opened -- and nothing uploaded from here."""

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QWidget

from xtal.io import write_cif
from xtal.io.export import TOPCRYST_URL
from xtalapp.dialogs.topcryst import TopCrystDialog
from xtalapp.mainwindow import MainWindow
from xtalapp.settings import AppSettings


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Top{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def opened(window, rutile, tmp_path):
    write_cif(rutile, tmp_path / "rutile.cif")
    return window.open_path(tmp_path / "rutile.cif")


@pytest.fixture
def urls(monkeypatch):
    opened = []

    def fake(url):
        opened.append(url.toString())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(fake))
    return opened


def test_the_topcryst_action_opens_the_site_and_reveals_the_file(
        window, opened, urls, monkeypatch):
    """The file goes in the entry, where the structure is, and the
    person is shown both it and the page to drop it on."""
    asked = []
    monkeypatch.setattr(
        TopCrystDialog, "ask",
        classmethod(lambda cls, path, dropped="", parent=None:
                    asked.append(path) or True))

    window.actions_["topcryst"].trigger()

    written = opened.entry.path / "topcryst" / "rutile.cif"
    assert asked == [written]
    assert written.is_file()
    assert urls == [f"file://{written.parent}", TOPCRYST_URL]


def test_a_cancelled_topcryst_upload_opens_nothing(
        window, opened, urls, monkeypatch):
    """Cancel leaves the file written -- it is harmless and was already
    named in the question -- and opens no browser."""
    monkeypatch.setattr(TopCrystDialog, "ask",
                        classmethod(lambda cls, *a, **k: False))

    window.actions_["topcryst"].trigger()

    assert (opened.entry.path / "topcryst" / "rutile.cif").is_file()
    assert urls == []


def test_the_topcryst_action_needs_a_structure(window, rutile, tmp_path):
    """With no tab there is nothing to write, and the entry would
    otherwise answer with a warning about nothing."""
    assert not window.actions_["topcryst"].isEnabled()
    write_cif(rutile, tmp_path / "rutile.cif")
    window.open_path(tmp_path / "rutile.cif")
    assert window.actions_["topcryst"].isEnabled()


def test_the_dialog_states_the_daily_limit(qtbot, tmp_path):
    """The eleventh upload of a day is refused on the site, so the
    limit is said before the first."""
    dialog = TopCrystDialog(tmp_path / "topcryst" / "rutile.cif",
                            "1 dummy atom will not be written")
    qtbot.addWidget(dialog)
    text = " ".join(label.text()
                    for label in dialog.findChildren(QLabel))
    assert "10 structures a day" in text
    assert "1 dummy atom" in text
