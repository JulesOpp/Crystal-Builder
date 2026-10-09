"""
Lay the Linux build out as an AppDir and pack it as an AppImage.

    python packaging/appimage.py "dist/Crystal Builder" dist/ \\
        --tool ./appimagetool-x86_64.AppImage

``linux.spec`` leaves ``dist/Crystal Builder/``, the window and
``xtal`` beside it.  That folder goes in whole as
``usr/lib/crystal-builder/``, and around it the three things
``appimagetool`` insists on at the top of an AppDir -- ``AppRun``, one
``.desktop`` file, and the icon that file names -- with copies of the
entry, the icon and the MIME file under ``usr/share``, where a desktop
integrator (AppImageLauncher, Gear Lever) looks for them when it makes
the menu entry and the file associations.  An AppImage registers
neither by itself.

**Everything is named after the desktop ID**,
:data:`xtalapp.application.DESKTOP_ID`, which the window also hands Qt
as its desktop file name: on Wayland that is the ``app_id`` a
compositor matches against the ``.desktop`` file to find the window's
icon, so a second spelling here would be a window with no icon.

The AppDir is made in a temporary folder and left behind nowhere.  It
is a staging area for one ``appimagetool`` run, and a stale one in the
working tree is how files from an old build reach a new download.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINUX = HERE / "linux"
sys.path.insert(0, str(HERE))

import bundle  # noqa: E402

sys.path.insert(0, str(bundle.ROOT))

from xtalapp.application import DESKTOP_ID  # noqa: E402

WINDOW = "Crystal Builder"
MIME = "crystal-builder.xml"


def layout(collected: Path, appdir: Path) -> Path:
    """Make ``appdir`` from the collected folder and return it.

    An existing ``appdir`` with anything in it is refused rather than
    added to: whatever it holds would be packed too.
    """
    if appdir.exists() and any(appdir.iterdir()):
        raise FileExistsError(f"{appdir} is not empty")
    appdir.mkdir(parents=True, exist_ok=True)

    # Symlinks kept: PyInstaller links each library's soname to its
    # file, and following them carries every one of those twice.
    shutil.copytree(collected, appdir / "usr" / "lib" / "crystal-builder",
                    symlinks=True)

    apprun = appdir / "AppRun"
    shutil.copyfile(LINUX / "AppRun", apprun)
    # Set here, not trusted from the checkout: git on Windows, or an
    # archive of the tree, does not keep the executable bit.
    apprun.chmod(0o755)

    entry = f"{DESKTOP_ID}.desktop"
    icon = f"{DESKTOP_ID}.svg"
    share = appdir / "usr" / "share"
    for source, *targets in [
        (LINUX / entry, appdir / entry, share / "applications" / entry),
        (bundle.ICONS / "app.svg", appdir / icon,
         share / "icons" / "hicolor" / "scalable" / "apps" / icon),
        (LINUX / MIME, share / "mime" / "packages" / MIME),
    ]:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (appdir / ".DirIcon").symlink_to(icon)
    return appdir


def pack(appdir: Path, tool: Path, out: Path, version: str) -> Path:
    """Run ``appimagetool`` over ``appdir`` and return the AppImage.

    ``ARCH`` is given because ``appimagetool`` otherwise guesses the
    architecture from the files it finds, and stops when it finds
    more than one kind.  ``--no-appstream``: there is no AppStream
    metadata to check, and without the flag a missing file is a
    warning that reads like a failure in the build log.
    """
    image = out / f"Crystal_Builder-{version}-x86_64.AppImage"
    subprocess.run(
        [str(tool), "--no-appstream", str(appdir), str(image)],
        check=True, env={**os.environ, "ARCH": "x86_64"})
    return image


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack the Linux build as an AppImage.")
    parser.add_argument("dist", type=Path,
                        help='the folder linux.spec made, '
                             '"dist/Crystal Builder"')
    parser.add_argument("out", type=Path,
                        help="where the AppImage goes")
    parser.add_argument("--tool", type=Path, required=True,
                        help="appimagetool")
    parser.add_argument("--version",
                        help="the version in the file name; the "
                             "installed package's by default")
    args = parser.parse_args(argv)

    collected = args.dist.resolve()
    if not (collected / WINDOW).is_file():
        print(f"{collected} holds no {WINDOW!r}; build linux.spec first",
              file=sys.stderr)
        return 1
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    version = args.version or bundle.version()

    with tempfile.TemporaryDirectory() as tmp:
        appdir = layout(collected, Path(tmp) / "CrystalBuilder.AppDir")
        image = pack(appdir, args.tool.resolve(), out, version)
    print(f"{image.name}  {image.stat().st_size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
