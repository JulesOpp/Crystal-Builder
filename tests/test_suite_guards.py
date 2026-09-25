"""The guards in conftest.py that keep the suite off the machine.

A guard that silently stops working does not fail anything -- it just
lets the suite write where it should not, which is how 374 plists
built up in ~/Library/Preferences behind a redirection everybody
believed in.  So each one is asserted here, by where things land.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402

from xtalapp.settings import SETTINGS_DIR_ENV, AppSettings  # noqa: E402


def test_no_window_settings_reach_the_real_preferences(tmp_path):
    """What regresses here is ``open_settings`` going back to the
    organisation/application constructor, which on macOS ignores the
    default format and talks to CFPreferences whatever conftest said.
    Nothing else in the suite would notice: the settings read back
    either way."""
    scratch = Path(os.environ[SETTINGS_DIR_ENV])
    settings = AppSettings("CrystalBuilderTest",
                           f"Guard{tmp_path.name}")
    settings.last_directory = str(tmp_path)

    store = settings._q
    assert store.format() == QSettings.IniFormat
    assert scratch in Path(store.fileName()).parents


# ------------------------------------------- nothing waits for a click
#
# Each checks that the guard is in place before calling through it:
# without the guard the call does not fail, it waits -- which is the
# hang these exist to prevent.


def _from_conftest(function) -> bool:
    code = getattr(function, "__code__", None)
    return code is not None and code.co_filename.endswith("conftest.py")

def test_a_dialog_reached_in_a_test_fails_rather_than_waits(qapp):
    """If this guard ever stopped being installed, a test that reached
    a dialog would sit until CI's twelve-minute cap -- which is what a
    context menu did, three jobs at thirty minutes each, before the
    cap existed."""
    from PySide6.QtWidgets import QDialog

    assert _from_conftest(QDialog.exec)
    with pytest.raises(AssertionError, match="wait for a click"):
        QDialog().exec()


def test_a_context_menu_reached_in_a_test_fails_rather_than_waits(qapp):
    """QMenu.exec cannot be patched from Python, so every context menu
    goes through xtalapp.menus.popup and that is what the guard
    replaces.  A menu raised any other way would not be caught -- and
    nor would a guard that stopped replacing it."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu

    from xtalapp import menus

    assert _from_conftest(menus.popup)
    with pytest.raises(AssertionError, match="context menu"):
        menus.popup(QMenu(), QPoint(0, 0))


def test_a_message_box_reached_in_a_test_fails_rather_than_waits(qapp):
    from PySide6.QtWidgets import QMessageBox

    for name in ("question", "warning", "information", "critical"):
        assert _from_conftest(getattr(QMessageBox, name))
        with pytest.raises(AssertionError, match="wait for a click"):
            getattr(QMessageBox, name)(None, "title", "text")
