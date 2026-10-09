"""The AppDir a Linux download is packed from.

``appimagetool`` reads a folder with a fixed shape -- ``AppRun``, one
``.desktop`` file and its icon at the top -- and a desktop integrator
(AppImageLauncher, Gear Lever) reads the ``.desktop`` file and the MIME
file inside it to make the menu entry and the file associations.  None
of that is checked by anything but a Linux machine, so it is checked
here, on a fake ``dist/Crystal Builder``, with no ``appimagetool``.
"""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from xtalapp.application import DESKTOP_ID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import appimage  # noqa: E402

needs_sh = pytest.mark.skipif(sys.platform == "win32",
                              reason="AppRun is a POSIX shell script")

WINDOW = "Crystal Builder"
MIME = "{http://www.freedesktop.org/standards/shared-mime-info}"


def _program(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def collected(tmp_path) -> Path:
    """A ``dist/Crystal Builder`` as ``linux.spec`` leaves it: the
    window, ``xtal`` beside it, and ``_internal`` with a library
    symlinked under its soname, as PyInstaller collects them."""
    folder = tmp_path / "dist" / WINDOW
    internal = folder / "_internal"
    internal.mkdir(parents=True)
    _program(folder / WINDOW,
             'echo "window $QT_QPA_PLATFORM"')
    _program(folder / "xtal", 'printf "%s\\n" xtal "$@"')
    (internal / "libQt6Core.so.6.9.0").write_bytes(b"\x7fELF")
    try:
        (internal / "libQt6Core.so.6").symlink_to("libQt6Core.so.6.9.0")
    except OSError:
        pytest.skip("this account cannot make symlinks")
    return folder


@pytest.fixture
def appdir(collected, tmp_path) -> Path:
    return appimage.layout(collected, tmp_path / "CrystalBuilder.AppDir")


def _run(appdir: Path, *args: str, **env: str) -> str:
    environment = {k: v for k, v in os.environ.items()
                   if k != "QT_QPA_PLATFORM"}
    environment.update(env)
    run = subprocess.run(["sh", str(appdir / "AppRun"), *args],
                         capture_output=True, text=True, check=True,
                         env=environment)
    return run.stdout


def test_the_appdir_has_the_layout_appimagetool_expects(appdir):
    """``appimagetool`` refuses a folder without ``AppRun`` and a
    ``.desktop`` file at its top, takes the icon the entry names from
    there too, and ``.DirIcon`` is what a file manager shows for the
    AppImage itself."""
    lib = appdir / "usr" / "lib" / "crystal-builder"
    share = appdir / "usr" / "share"
    for path in [
        appdir / "AppRun",
        appdir / f"{DESKTOP_ID}.desktop",
        appdir / f"{DESKTOP_ID}.svg",
        lib / WINDOW,
        lib / "xtal",
        share / "applications" / f"{DESKTOP_ID}.desktop",
        share / "icons" / "hicolor" / "scalable" / "apps"
        / f"{DESKTOP_ID}.svg",
        share / "mime" / "packages" / "crystal-builder.xml",
    ]:
        assert path.is_file(), path

    icon = appdir / ".DirIcon"
    assert icon.is_symlink()
    assert os.readlink(icon) == f"{DESKTOP_ID}.svg"
    assert icon.read_bytes() == (appimage.bundle.ICONS
                                 / "app.svg").read_bytes()


def test_apprun_is_executable_and_runs_the_collected_program(appdir):
    """The AppImage runtime executes ``AppRun`` directly; without the
    executable bit the download does nothing when it is run."""
    apprun = appdir / "AppRun"
    if sys.platform != "win32":
        assert apprun.stat().st_mode & 0o777 == 0o755
    assert "usr/lib/crystal-builder/Crystal Builder" in apprun.read_text(
        encoding="utf-8")


@needs_sh
def test_apprun_honours_a_platform_the_user_chose(appdir):
    """Wayland first and X11 after it is the right default, and is
    wrong for somebody whose compositor's Wayland Qt mishandles: the
    variable they set must reach the program untouched."""
    assert _run(appdir).strip() == "window wayland;xcb"
    assert _run(appdir, QT_QPA_PLATFORM="xcb").strip() == "window xcb"


@needs_sh
def test_apprun_runs_the_bundled_cli_when_asked_for_xtal(appdir):
    """An AI assistant's client is configured with ``<the AppImage>
    xtal mcp``: the mount the ``xtal`` beside the window lives in is
    gone when the window quits, so the AppImage file itself is the
    only path that lasts, and it has to start the CLI, not the
    window."""
    assert _run(appdir, "xtal", "mcp", "--headless").split() == [
        "xtal", "mcp", "--headless"]
    assert _run(appdir, "a structure.cif").strip() == "window wayland;xcb"


def test_the_desktop_entry_names_the_app_its_icon_and_both_file_types(
        appdir):
    """The menu entry and the file associations an integrator makes
    come from this file alone; an ``Icon`` that is not the desktop ID
    is a menu entry with a blank icon."""
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str
    entry.read(appdir / f"{DESKTOP_ID}.desktop", encoding="utf-8")
    desktop = entry["Desktop Entry"]

    assert desktop["Type"] == "Application"
    assert desktop["Name"] == "Crystal Builder"
    assert desktop["Exec"] == "AppRun %F"
    assert desktop["Icon"] == DESKTOP_ID
    types = desktop["MimeType"].split(";")
    assert "chemical/x-cif" in types
    assert "application/x-crystal-builder-project" in types
    assert "Science" in desktop["Categories"].split(";")
    assert desktop["StartupWMClass"] == "Crystal Builder"
    shared = (appdir / "usr" / "share" / "applications"
              / f"{DESKTOP_ID}.desktop")
    assert shared.read_bytes() == (
        appdir / f"{DESKTOP_ID}.desktop").read_bytes()


def test_the_mime_file_declares_both_globs(appdir):
    """A desktop that has never seen ``.xtalproj`` learns it here, and
    one without ``chemical-mime-data`` learns ``.cif`` too."""
    tree = ET.parse(appdir / "usr" / "share" / "mime" / "packages"
                    / "crystal-builder.xml")
    root = tree.getroot()
    assert root.tag == f"{MIME}mime-info"
    globs = {kind.get("type"): (kind.find(f"{MIME}comment").text,
                                kind.find(f"{MIME}glob").get("pattern"))
             for kind in root.findall(f"{MIME}mime-type")}
    assert globs == {
        "application/x-crystal-builder-project":
            ("Crystal Builder project", "*.xtalproj"),
        "chemical/x-cif":
            ("Crystallographic Information File", "*.cif"),
    }


def test_the_collected_folder_is_copied_with_its_symlinks(appdir):
    """PyInstaller links a library's soname to its file; followed, each
    is carried twice and the download grows by the size of Qt."""
    link = (appdir / "usr" / "lib" / "crystal-builder" / "_internal"
            / "libQt6Core.so.6")
    assert link.is_symlink()
    assert os.readlink(link) == "libQt6Core.so.6.9.0"


def test_pack_names_the_appimage_after_the_version_and_sets_arch(
        appdir, tmp_path):
    """``appimagetool`` guesses the architecture from the files inside
    and stops when it cannot, and the release attaches the file by the
    name this gives it."""
    record = tmp_path / "record.txt"
    script = tmp_path / "fake_tool.py"
    script.write_text(
        "import os, sys\n"
        f"with open({str(record)!r}, 'w', encoding='utf-8') as out:\n"
        "    out.write(os.environ.get('ARCH', '') + '\\n')\n"
        "    out.write('\\n'.join(sys.argv[1:]))\n",
        encoding="utf-8")
    if sys.platform == "win32":
        tool = tmp_path / "appimagetool.cmd"
        tool.write_text(f'@"{sys.executable}" "{script}" %*\n',
                        encoding="utf-8")
    else:
        tool = _program(tmp_path / "appimagetool",
                        f'exec "{sys.executable}" "{script}" "$@"')
    out = tmp_path / "out"
    out.mkdir()

    made = appimage.pack(appdir, tool, out, "1.2.3")

    assert made == out / "Crystal_Builder-1.2.3-x86_64.AppImage"
    arch, *argv = record.read_text(encoding="utf-8").splitlines()
    assert arch == "x86_64"
    assert argv == ["--no-appstream", str(appdir), str(made)]


def test_layout_refuses_a_non_empty_appdir(collected, tmp_path):
    """A folder left from an earlier build would carry its files into
    this one's download, where nothing would notice them."""
    stale = tmp_path / "CrystalBuilder.AppDir"
    stale.mkdir()
    (stale / "left-over").write_text("", encoding="utf-8")

    with pytest.raises(FileExistsError):
        appimage.layout(collected, stale)
    assert sorted(p.name for p in stale.iterdir()) == ["left-over"]

    empty = tmp_path / "empty.AppDir"
    empty.mkdir()
    assert appimage.layout(collected, empty) == empty
