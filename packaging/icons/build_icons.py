"""
Render the three SVGs in this folder into the icons the two specs ask
for: ``.icns`` for macOS and ``.ico`` for Windows.

Run it after editing an SVG and commit what it writes.  The SVGs are
the source of truth; the binaries beside them are build output that
happens to be committed, because CI has to be able to build a bundle
without a working librsvg and without a copy of Inkscape.

    python packaging/icons/build_icons.py

**Qt does the rasterising**, not librsvg or cairosvg or Pillow.  That
is not a preference: PySide6 is already a dependency of the thing
being packaged, so this script adds nothing to install, and QtSvg is
the same renderer the application itself draws SVG with -- an icon
that looks right here looks right in the About box.  ``iconutil`` is
macOS's own and is the only supported way to write an ``.icns``;
Pillow writes the ``.ico``, which is a container of PNGs and needs no
platform tool.

Two things worth knowing before editing an SVG:

- **XML comments cannot contain a double hyphen**, so the em dash this
  project writes as ``--`` everywhere else is a comma or a bracket in
  those files.  It is a parse error and not a warning.
- **Text is rendered with whatever font is installed**, so the two
  document icons say CIF and PROJ in Helvetica on this machine and in
  something else elsewhere.  That is why the rendered files are
  committed rather than built in CI: the icons a release ships are the
  ones somebody looked at.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")
# Nothing here opens a window, and CI has no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent

#: The sizes ``iconutil`` expects, as (points, scale).  Anything
#: missing from this table makes it refuse the whole iconset rather
#: than write a smaller icon, so it is exactly Apple's list.
ICNS_SIZES = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
              (256, 1), (256, 2), (512, 1), (512, 2)]

#: Windows reads the largest entry it needs out of the container.  256
#: is what Explorer's extra-large view wants; 16 is the tree and the
#: title bar, and is the size the drawings were made for.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

#: At or below this, the app icon is rendered from ``app-small.svg``
#: instead.  See that file for why one drawing cannot serve both ends
#: of the range.  Only the app icon has a small variant: a document
#: icon at 16 px is a page-shaped smudge whatever is drawn on it, and
#: the coloured band is what tells the two apart at that size.
SMALL = 32


def application():
    """A ``QGuiApplication``, because the document icons carry text.

    Painting a QImage needs no application; resolving a font family to
    a font does, and without one this segfaults rather than raising,
    which is a confusing five minutes.  Offscreen, so it needs no
    display.
    """
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def render(svg: Path, size: int, out: Path) -> Path:
    """Write one square PNG of the SVG, and return where it went.

    Painted onto a transparent image with antialiasing on, which is
    what makes a 16 px render of a shape drawn at 1024 legible rather
    than aliased into noise.

    A file and not a bytes buffer, deliberately.  ``QBuffer`` holds a
    borrowed pointer to the ``QByteArray`` it is handed, so the
    obvious ``QBuffer(QByteArray())`` leaves the buffer pointing at a
    temporary Python has already collected, and this segfaults rather
    than raising.  ``iconutil`` wants files on disk anyway.
    """
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise SystemExit(f"{svg.name} is not valid SVG")

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    if not image.save(str(out), "PNG"):
        raise SystemExit(f"could not write {out}")
    return out


def source_for(svg: Path, size: int) -> Path:
    """The drawing to rasterise at this size.

    ``app.svg`` at 16 px is a smudge, so there is an ``app-small.svg``
    beside it.  A file with no small variant is its own answer at
    every size.
    """
    small = svg.with_name(f"{svg.stem}-small.svg")
    return small if size <= SMALL and small.is_file() else svg


def write_icns(svg: Path, out: Path) -> None:
    """An ``.icns`` via a temporary ``.iconset`` and ``iconutil``."""
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / f"{out.stem}.iconset"
        iconset.mkdir()
        for points, scale in ICNS_SIZES:
            suffix = "" if scale == 1 else f"@{scale}x"
            name = f"icon_{points}x{points}{suffix}.png"
            pixels = points * scale
            render(source_for(svg, pixels), pixels, iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
            check=True)


def write_ico(svg: Path, out: Path) -> None:
    """An ``.ico`` container holding one PNG per size in
    :data:`ICO_SIZES`.

    Rendered at each size from the vector rather than downsampled from
    the 256, because the drawing is tuned for 16 px and a downsample
    of the large one is exactly the grey smudge it was tuned to avoid.
    """
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        frames = [
            Image.open(
                render(source_for(svg, s), s, Path(tmp) / f"{s}.png")
            ).convert("RGBA")
            for s in ICO_SIZES
        ]
        frames[-1].save(out, format="ICO",
                        sizes=[(s, s) for s in ICO_SIZES],
                        append_images=frames[:-1])


def main() -> int:
    if sys.platform != "darwin":
        # The .ico half would work anywhere; the .icns half is
        # iconutil, and there is no point writing half the icons.
        print("icons are rendered on macOS (iconutil); the results "
              "are committed", file=sys.stderr)
        return 1

    app = application()                     # held until the last render

    for name in ("app", "cif", "xtalproj"):
        svg = HERE / f"{name}.svg"
        write_icns(svg, HERE / f"{name}.icns")
        write_ico(svg, HERE / f"{name}.ico")
        print(f"{name}: icns + ico")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
