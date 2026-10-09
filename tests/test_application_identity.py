"""The running window says which application it is.

macOS and Windows read a window's icon off the bundle and the
``.exe``.  A Linux executable carries no icon at all, and a Wayland
desktop matches a window to its ``.desktop`` entry by the name the
application gives itself -- so without both, the AppImage's window is
a generic cog, its windows are not grouped, and the dock shows a
second, nameless entry beside the one that launched it.
"""

import sys
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from xtalapp import application  # noqa: E402
from xtalapp.application import DESKTOP_ID, icon_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import bundle  # noqa: E402


def test_the_application_names_its_desktop_entry(qapp):
    """GNOME on Wayland finds the window's entry by this name; without
    it the window is an unknown application beside its own launcher."""
    assert qapp.desktopFileName() == DESKTOP_ID


def test_the_application_has_its_own_window_icon(qapp):
    """Nothing else gives a Linux window an icon: the executable has
    no resource to read one from."""
    before = qapp.windowIcon()
    try:
        application._apply_window_icon(qapp, "linux")
        assert icon_path().is_file()
        assert not qapp.windowIcon().isNull()
    finally:
        qapp.setWindowIcon(before)


class _Recorder:
    def __init__(self):
        self.icons = []

    def setWindowIcon(self, icon):
        self.icons.append(icon)


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_the_window_icon_is_left_to_the_bundle_on_macos_and_windows(
        platform):
    """On macOS the application's window icon *is* the Dock's, so
    setting it would replace the bundle's at run time; on Windows the
    ``.exe``'s icon already is the taskbar's and the title bar's."""
    app = _Recorder()

    application._apply_window_icon(app, platform)

    assert app.icons == []


def test_the_icon_ships_with_the_package():
    """A wheel carries only what ``pyproject.toml`` lists and a bundle
    only what ``bundle.py`` collects; an icon left out of either is a
    window with no icon in that install and nothing failing to say so.
    """
    path = icon_path()
    package = ROOT / "xtalapp"
    relative = path.relative_to(package).as_posix()

    with (ROOT / "pyproject.toml").open("rb") as handle:
        declared = tomllib.load(handle)["tool"]["setuptools"][
            "package-data"]
    assert relative in declared["xtalapp"]
    assert relative in bundle.PACKAGE_DATA["xtalapp"]

    collected = {Path(source): destination
                 for source, destination in bundle.project_datas()}
    assert collected[path] == path.parent.relative_to(ROOT).as_posix()


def test_the_shipped_icon_is_the_one_the_installers_are_made_from():
    """A copy, because the macOS and Windows icons are built from
    ``packaging/icons``; a redrawn icon there and a stale one here
    would be two applications' worth of icon."""
    original = ROOT / "packaging" / "icons" / "app.svg"
    assert icon_path().read_bytes() == original.read_bytes()
