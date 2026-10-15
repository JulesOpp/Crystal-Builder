"""
Lay the Linux build out as an AppDir and pack it as an AppImage.

    python packaging/appimage.py dist/crystal-builder dist/ \\
        --tool ./appimagetool-x86_64.AppImage --runtime ./runtime-x86_64

``linux.spec`` leaves ``dist/crystal-builder/``, the window
(``crystal-builder``) and ``xtal`` beside it.  That folder goes in whole as
``usr/lib/crystal-builder/``, and around it the three things
``appimagetool`` insists on at the top of an AppDir -- ``AppRun``, one
``.desktop`` file, and the icon that file names -- with copies of the
entry and the MIME file under ``usr/share``, and the icons there at
every ``hicolor`` size, the document icons too, where a desktop
integrator (AppImageLauncher, Gear Lever) looks for them when it makes
the menu entry and the file associations.  An AppImage registers
neither by itself.

**Everything is named after the desktop ID**,
:data:`xtalapp.application.DESKTOP_ID`, which the window also hands Qt
as its desktop file name: on Wayland that is the ``app_id`` a
compositor matches against the ``.desktop`` file to find the window's
icon, so a second spelling here would be a window with no icon.
PR #59's ``.deb`` named its entry ``crystal-builder.desktop``; the
reverse-DNS ID is kept because it is what ``setDesktopFileName`` says
and what freedesktop recommends.  The project's MIME type
(``application/x-xtalproj``), the categories and the icon set follow
his.

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

#: The window's executable, as ``linux.spec`` names it: no space for a
#: shell to split, and the ``.desktop`` entry carries the display name.
WINDOW = "crystal-builder"
MIME = "crystal-builder.xml"
#: The PNG's side, in pixels: the AppImage spec's recommended
#: ``.DirIcon`` size, and a ``hicolor`` size every theme has.
ICON_SIZE = 256

#: The ``hicolor`` sizes the app icon is drawn at, as PR #59's
#: ``write_icons`` drew them: a panel, a title bar and a launcher each
#: ask the theme for their own, and one the theme lacks is scaled from
#: another by the desktop -- a 16 px blur in the title bar.
APP_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
#: At or below this the app icon is drawn from ``app-small.svg``, as
#: ``icons/build_icons.py`` (``SMALL``) does for the .icns and .ico:
#: ``app.svg`` at 16 px is a smudge.
SMALL = 32

#: The document icons, by the SVG they are drawn from and the name a
#: theme looks them up by -- the MIME type with its slash spelled
#: ``-``, which is how freedesktop names a ``mimetypes/`` icon -- and
#: the sizes PR #59 drew them at.
DOCUMENT_ICONS = {
    "cif.svg": "chemical-x-cif",
    "xtalproj.svg": "application-x-xtalproj",
}
DOCUMENT_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(svg: Path, png: Path, size: int = ICON_SIZE) -> None:
    """Draw ``svg`` as a ``size`` square PNG with a transparent
    background.  Needs a ``QGuiApplication``."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise ValueError(f"{svg} is not an svg Qt can draw")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    # As build_icons.py draws them: without it a shape drawn at 1024
    # aliases into noise at 16 px.
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    if not image.save(str(png), "PNG"):
        raise OSError(f"could not write {png}")


def app_icon_source(size: int) -> Path:
    """The drawing the app icon is rendered from at ``size``."""
    small = bundle.ICONS / "app-small.svg"
    if size <= SMALL and small.is_file():
        return small
    return bundle.ICONS / "app.svg"


def write_icons(hicolor: Path, png: str) -> None:
    """The app icon at every size in :data:`APP_ICON_SIZES` under
    ``apps/``, named ``png``, and the two document icons under
    ``mimetypes/``.  Needs a ``QGuiApplication``: the document icons
    carry text, and resolving a font needs one."""
    for size in APP_ICON_SIZES:
        into = hicolor / f"{size}x{size}" / "apps"
        into.mkdir(parents=True, exist_ok=True)
        render_png(app_icon_source(size), into / png, size)
    for svg, name in DOCUMENT_ICONS.items():
        for size in DOCUMENT_ICON_SIZES:
            into = hicolor / f"{size}x{size}" / "mimetypes"
            into.mkdir(parents=True, exist_ok=True)
            render_png(bundle.ICONS / svg, into / f"{name}.png", size)


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
    png = f"{DESKTOP_ID}.png"
    share = appdir / "usr" / "share"
    hicolor = share / "icons" / "hicolor"
    render_png(bundle.ICONS / "app.svg", appdir / png)
    write_icons(hicolor, png)
    for source, *targets in [
        (LINUX / entry, appdir / entry, share / "applications" / entry),
        (bundle.ICONS / "app.svg", appdir / icon,
         hicolor / "scalable" / "apps" / icon),
        (LINUX / MIME, share / "mime" / "packages" / MIME),
    ]:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    # A PNG: thumbnailers draw the AppImage from .DirIcon and skip an
    # svg.  The .desktop entry's Icon= still finds the svg.
    (appdir / ".DirIcon").symlink_to(png)
    return appdir


def pack(appdir: Path, tool: Path, out: Path, version: str,
         runtime: Path | None = None) -> Path:
    """Run ``appimagetool`` over ``appdir`` and return the AppImage.

    ``ARCH`` is given because ``appimagetool`` otherwise guesses the
    architecture from the files it finds, and stops when it finds
    more than one kind.  ``--no-appstream``: there is no AppStream
    metadata to check, and without the flag a missing file is a
    warning that reads like a failure in the build log.

    ``runtime`` is the type2 runtime, the executable every AppImage
    starts with.  Without it ``appimagetool`` downloads whatever its
    upstream calls current at the moment it runs, so a release would
    ship a first stage nobody pinned or looked at.
    """
    image = out / f"Crystal_Builder-{version}-x86_64.AppImage"
    pinned = ["--runtime-file", str(runtime)] if runtime else []
    subprocess.run(
        [str(tool), *pinned, "--no-appstream", str(appdir), str(image)],
        check=True, env={**os.environ, "ARCH": "x86_64"})
    return image


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack the Linux build as an AppImage.")
    parser.add_argument("dist", type=Path,
                        help="the folder linux.spec made, "
                             "dist/crystal-builder")
    parser.add_argument("out", type=Path,
                        help="where the AppImage goes")
    parser.add_argument("--tool", type=Path, required=True,
                        help="appimagetool")
    parser.add_argument("--runtime", type=Path,
                        help="the type2 runtime, handed to appimagetool "
                             "as --runtime-file; it downloads one "
                             "otherwise")
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

    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None:
        # A build machine may have no display, and the icon is drawn
        # into an image, never onto a screen.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QGuiApplication([])  # noqa: F841 -- held while it renders

    with tempfile.TemporaryDirectory() as tmp:
        appdir = layout(collected, Path(tmp) / "CrystalBuilder.AppDir")
        image = pack(appdir, args.tool.resolve(), out, version,
                     args.runtime.resolve() if args.runtime else None)
    print(f"{image.name}  {image.stat().st_size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
