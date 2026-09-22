"""Unsaved edits kept beside the workspace, and offered back.

A structure is twenty minutes of hand editing and nothing kept it but
Ctrl+S; a crash lost every unsaved edit in every tab.  The autosave is
a side file in ``<workspace>/.autosave/`` -- never the document, which
only Save writes -- and it is offered back when the file is opened
again, as one undo step.

The timer is never waited on: ``Autosaver.tick`` is what it calls.
"""

import os
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.core.structure import Bond, Change  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtalapp.autosave import DISCARD, RESTORE  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

MOVED = [0.31, 0.31, 0.0]


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Auto{tmp_path.name}")
    settings.clear_recent_files()
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    return settings


def _window(qtbot, settings, root):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    win.set_workspace(root, create=True)
    return win


@pytest.fixture
def window(qtbot, settings, tmp_path):
    return _window(qtbot, settings, tmp_path / "ws")


@pytest.fixture
def opened(window, tmp_path, rutile):
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    return window.open_path(source)


def _edit(document):
    document.apply(lambda s: s.set_frac(1, MOVED), Change.POSITIONS)
    assert document.modified


def _kept(window, document):
    return window.autosaver.path_for(document)


# -------------------------------------------------------------- writing

def test_a_modified_document_is_autosaved_beside_the_workspace(
        window, opened):
    before = opened.path.read_bytes()
    _edit(opened)

    written = window.autosaver.tick()

    kept = _kept(window, opened)
    assert written == [kept]
    assert kept.is_file()
    assert kept.parent.parent.name == ".autosave"
    assert opened.path.read_bytes() == before       # never the file


def test_an_unmodified_document_writes_no_autosave(window, opened):
    assert window.autosaver.tick() == []
    assert not _kept(window, opened).exists()


def test_a_document_is_written_again_only_after_another_edit(window,
                                                             opened):
    _edit(opened)
    window.autosaver.tick()

    assert window.autosaver.tick() == []


def test_saving_removes_the_autosave(window, opened):
    _edit(opened)
    window.autosaver.tick()
    kept = _kept(window, opened)

    window.save_document()

    assert not kept.exists()


def test_undoing_back_to_the_file_removes_the_autosave(window, opened):
    _edit(opened)
    window.autosaver.tick()

    opened.undo()

    assert not _kept(window, opened).exists()


def test_closing_a_modified_tab_on_purpose_removes_the_autosave(
        window, opened):
    """The suite answers every close question yes; a discard asked
    and answered is work somebody chose to throw away."""
    _edit(opened)
    window.autosaver.tick()
    kept = _kept(window, opened)

    window.close_document(0)

    assert not kept.exists()


def test_a_window_with_no_workspace_autosaves_nothing(qtbot, settings,
                                                      rutile_cif,
                                                      monkeypatch):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    monkeypatch.setattr(type(win), "workspace", property(lambda s: None))
    document = win.open_path(rutile_cif)
    _edit(document)

    assert win.autosaver.tick() == []


def test_the_interval_preference_can_turn_it_off(window):
    window.settings.autosave_interval = 0
    window.autosaver.apply_interval()
    assert not window.autosaver.timer.isActive()

    window.settings.autosave_interval = 60
    window.autosaver.apply_interval()
    assert window.autosaver.timer.interval() == 60_000


# ------------------------------------------------------------- recovery

def _crash_and_reopen(qtbot, settings, window, document, tmp_path):
    """Leave an autosave behind as a crash would, and open again."""
    _edit(document)
    window.autosaver.tick()
    path = document.path
    # A crash: the tab is gone without anything forgetting it.
    window.autosaver._pending.clear()
    window.documents.remove(document)
    window.tabs.removeTab(0)
    return path


def test_a_newer_autosave_is_offered_when_the_entry_opens(
        qtbot, settings, window, opened, tmp_path):
    path = _crash_and_reopen(qtbot, settings, window, opened, tmp_path)

    again = window.open_path(path)

    assert not window.notice.isHidden()
    assert path.name in window.notice.label.text()
    assert not again.modified            # nothing applied until asked


def test_restoring_an_autosave_is_one_undo_step(qtbot, settings, window,
                                                opened, tmp_path):
    path = _crash_and_reopen(qtbot, settings, window, opened, tmp_path)
    again = window.open_path(path)
    original = list(again.structure.sites[1].frac)

    window.notice.button(RESTORE).click()

    assert list(again.structure.sites[1].frac) == pytest.approx(MOVED)
    assert again.modified
    again.undo()
    assert list(again.structure.sites[1].frac) == pytest.approx(original)


def test_restoring_keeps_the_bonds_the_autosave_carried(
        qtbot, settings, window, opened, tmp_path):
    """The bond the user drew comes back, and no others: bonds are
    recalculated only when somebody presses Recalculate."""
    drawn = Bond(i=0, j=1, image=(0, 0, 0))
    opened.apply(lambda s: s.add_bond(drawn), Change.TOPOLOGY)
    path = _crash_and_reopen(qtbot, settings, window, opened, tmp_path)
    again = window.open_path(path)
    assert again.structure.bonds == []

    window.notice.button(RESTORE).click()

    assert [(b.i, b.j, tuple(b.image)) for b in again.structure.bonds] \
        == [(0, 1, (0, 0, 0))]


def test_discarding_an_autosave_deletes_it(qtbot, settings, window,
                                           opened, tmp_path):
    path = _crash_and_reopen(qtbot, settings, window, opened, tmp_path)
    again = window.open_path(path)
    kept = _kept(window, again)

    window.notice.button(DISCARD).click()

    assert not kept.exists()
    assert not again.modified


def test_an_autosave_older_than_the_file_is_not_offered(
        qtbot, settings, window, opened, tmp_path):
    """The file was saved after it -- here or by another program --
    so it is stale, and offering it would undo that save."""
    path = _crash_and_reopen(qtbot, settings, window, opened, tmp_path)
    kept = window.autosaver.path_for(opened)
    past = time.time() - 60
    os.utime(kept, (past, past))

    window.open_path(path)

    assert window.notice.isHidden()
    assert not kept.exists()


def test_two_autosaves_are_asked_about_one_at_a_time(
        qtbot, settings, window, tmp_path, rutile, quartz):
    paths = []
    for name, crystal in (("rutile", rutile), ("quartz", quartz)):
        write_cif(crystal, tmp_path / f"{name}.cif")
        document = window.open_path(tmp_path / f"{name}.cif")
        _edit(document)
        paths.append(document.path)
    window.autosaver.tick()
    window.autosaver._pending.clear()
    for _ in range(2):
        window.documents.pop()
        window.tabs.removeTab(0)

    for path in paths:
        window.open_path(path)
    assert paths[0].name in window.notice.label.text()
    window.notice.button(DISCARD).click()

    assert paths[1].name in window.notice.label.text()


def test_an_autosave_that_cannot_be_written_is_logged_not_raised(
        window, opened, monkeypatch, caplog):
    """A full disk is no reason to interrupt somebody editing; the
    next tick tries again."""
    def refuse(path):
        raise OSError("disk full")
    monkeypatch.setattr(opened, "write_project", refuse)
    _edit(opened)

    with caplog.at_level("WARNING", logger="xtalapp"):
        assert window.autosaver.tick() == []

    assert any("disk full" in r.getMessage() for r in caplog.records)
    assert opened in window.autosaver._pending


def test_the_preferences_interval_restarts_the_timer(window):
    dialog = window.preferences_dialog()

    dialog.page("General").autosave_minutes.setValue(5)

    assert window.settings.autosave_interval == 300
    assert window.autosaver.timer.interval() == 300_000
    dialog.page("General").autosave_minutes.setValue(0)
    assert not window.autosaver.timer.isActive()
