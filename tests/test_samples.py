"""Seven real structures ship in resources/samples, and now open.

They had been in the repository since the early phases with nothing in
the application referring to them, so a fresh installation opened an
empty window to somebody who may not own a CIF yet.

The part with teeth is *how* they open: copied into the workspace and
opened from there.  The files live inside the application's own folder
-- a signed bundle on macOS, under Program Files on Windows -- so a
sample that adopted its own path would answer Ctrl+S by trying to
write there.  The copy is what makes a sample an ordinary structure of
this workspace instead.
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


def test_a_sample_is_copied_into_the_workspace(window):
    """Never opened in place: the application's own folder is signed
    on macOS and under Program Files on Windows."""
    document = window.open_sample("mof5")

    assert document is not None
    assert window.tabs.count() == 1
    assert document.entry is not None
    assert document.path == document.entry.structure_path
    assert document.path.parent.parent == window.workspace.root
    assert str(samples.folder()) not in str(document.path)


def test_the_entry_is_named_after_the_sample_not_the_data_block(window):
    """MOF-5.cif calls its block VESTA_phase_1.  The folder the copy
    goes in is named from the catalogue instead."""
    document = window.open_sample("mof5")

    assert document.entry.name == "MOF-5"
    assert window.tabs.tabText(0) == document.path.name


def test_saving_a_sample_never_writes_inside_the_application(
        window, monkeypatch):
    """The whole reason they used to open without a path.  It is the
    copy that is saved now, so Ctrl+S asks nothing and still cannot
    reach resources/samples -- a signed bundle on macOS, and under
    Program Files on Windows."""
    def refuse(*args, **kwargs):
        raise AssertionError("Save File asked where")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", refuse)
    document = window.open_sample("hkust1")

    window.save_document()

    assert document.path.suffix == ".xtalproj"
    assert document.path.parent == document.entry.path
    assert str(samples.folder()) not in str(document.path)
    assert document.path.is_file()
    assert not document.modified


def test_last_directory_never_moves_into_the_application(window,
                                                         tmp_path):
    """The copy is what is opened, so the directory that is remembered
    is the workspace and never resources/samples."""
    window.open_sample("hkust1")

    assert str(samples.folder()) not in window.settings.last_directory
    assert window.settings.recent_files() != []


def test_the_same_sample_twice_returns_to_the_one_entry(window):
    """The bytes are compared, so the second click is the same file
    and the same tab -- not a second copy of it."""
    first = window.open_sample("hkust1")
    second = window.open_sample("hkust1")

    assert first is second
    assert window.tabs.count() == 1
    assert len(window.workspace.entries()) == 1


def test_a_sample_opened_over_an_edited_copy_opens_the_clicked_one(
        window):
    """Same name, different bytes: what opens is what was clicked, and
    the work already in that entry is not written over."""
    first = window.open_sample("hkust1")
    first.path.write_text(first.path.read_text() + "\n# edited\n")

    second = window.open_sample("hkust1")

    assert second is not first
    assert second.entry.name == "HKUST-1-2"
    assert "# edited" in first.path.read_text()


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

    assert window.tabs.count() == 1
    assert window.current_document().entry.name == "ZIF-8"


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
