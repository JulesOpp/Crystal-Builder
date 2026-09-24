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
