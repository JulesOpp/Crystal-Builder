"""Seven real structures ship in resources/samples, and now open.

They had been in the repository since the early phases with nothing in
the application referring to them, so a fresh installation opened an
empty window to somebody who may not own a CIF yet.

The part with teeth is *how* they open: as untitled documents with no
path.  The files live inside the application's own folder -- a signed
bundle on macOS, under Program Files on Windows -- so a sample that
adopted its path would answer Ctrl+S by trying to write there.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QFileDialog, QWidget  # noqa: E402

from xtal.io import FORMATS  # noqa: E402
from xtalapp import menus, samples  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Sample{tmp_path.name}")
    settings.clear_window()
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_every_sample_in_the_catalogue_is_a_file_that_is_there():
    """A renamed CIF turns an entry into a dialog saying nothing is
    installed, which reads as the whole feature being broken."""
    missing = [s.label for s in samples.SAMPLES if s.path is None]

    assert missing == []
    assert len(samples.SAMPLES) == 7


def test_every_sample_is_a_structure_this_application_can_read():
    """The menu offers them, so each has to survive the reader that
    the menu will hand it to."""
    for sample in samples.SAMPLES:
        structure = FORMATS.read(sample.path)
        assert structure.n_sites > 0, sample.label


def test_a_sample_opens_as_an_untitled_document(window):
    document = window.open_sample("mof5")

    assert document is not None
    assert document.path is None
    assert window.tabs.count() == 1


def test_the_tab_is_named_after_the_sample_not_the_data_block(window):
    """MOF-5.cif calls its block VESTA_phase_1.  A pathless document
    takes its title from the structure, so the label goes in there."""
    document = window.open_sample("mof5")

    assert document.title == "MOF-5"
    assert window.tabs.tabText(0) == "MOF-5"


def test_saving_a_sample_asks_where_to_put_it(window, tmp_path,
                                              monkeypatch):
    """The whole reason they open without a path: Ctrl+S must not
    write inside the application's own folder."""
    asked = []

    def fake(parent, title, start, filters):
        asked.append(start)
        return str(tmp_path / "mine.xtalproj"), filters

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake)
    window.open_sample("hkust1")
    window.save_document()

    assert len(asked) == 1
    assert str(samples.folder()) not in asked[0]
    assert asked[0].endswith("HKUST-1.xtalproj")
    assert (tmp_path / "mine.xtalproj").exists()


def test_a_sample_does_not_join_the_recent_files(window, tmp_path):
    """Recent files are a way back to a file the user has.  A sample
    is not one, and last_directory must not move into resources/."""
    window.open_sample("hkust1")

    assert window.settings.recent_files() == []
    assert window.settings.last_directory == str(tmp_path)


def test_the_same_sample_twice_gives_two_documents(window):
    """Unlike two tabs over one file, two untitled copies cannot
    overwrite each other, so there is nothing to protect against."""
    first = window.open_sample("hkust1")
    second = window.open_sample("hkust1")

    assert first is not second
    assert window.tabs.count() == 2


def test_a_freshly_opened_sample_is_not_modified(window):
    """Closing it asks nothing, because nothing has been done to it."""
    document = window.open_sample("hkust1")

    assert not document.modified


def test_the_file_menu_offers_every_sample(window):
    """The submenu is asked which menu it is in, rather than the File
    menu being asked what is in it.  ``QAction.menu()`` is the obvious
    way to reach a submenu from the menu bar and it destroys the menu
    it hands back the moment the wrapper is collected -- which kills
    ``window.modules_menu`` on a checkout with none of this in it."""
    labels = [a.text() for a in window.sample_menu.actions()]

    assert labels == [s.label for s in samples.SAMPLES]
    assert window.sample_menu.isEnabled()
    assert window.sample_menu.parentWidget().title() == "&File"


def test_every_sample_has_an_action_of_its_own(window):
    """Named the way the run-app driver and a keyboard shortcut would
    have to type it."""
    for sample in samples.SAMPLES:
        name = f"sample_{sample.name}"
        assert name in window.actions_
        assert window.actions_[name].toolTip() == sample.description


def test_pressing_a_sample_entry_opens_it(window):
    """Through the QAction, which is what a menu click reaches."""
    window.actions_["sample_zif8"].trigger()

    assert window.tabs.tabText(0) == "ZIF-8"


def test_an_installation_without_the_samples_says_so(window, tmp_path,
                                                     monkeypatch):
    """resources/ is not package data, so a wheel install has none of
    them -- a supported state that gets a sentence, not seven entries
    that each raise a dialog."""
    monkeypatch.setattr(samples, "folder", lambda: tmp_path / "nothing")
    menus.build_sample_menu(window)

    assert not window.sample_menu.isEnabled()
    assert window.sample_menu.toolTip() == samples.MISSING
    assert not window.actions_["sample_mof5"].isEnabled()
