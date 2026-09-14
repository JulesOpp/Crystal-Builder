"""Draw the picture on the workspace chooser's side panel.

Run through the run-app driver, which builds the real window with the
real viewport, in a scratch profile so nothing of the developer's is
read or written::

    python .claude/skills/run-app/drive.py --scratch "$TMPDIR/art" \\
        --open resources/samples/MOF-5.cif \\
        --script packaging/render_chooser_art.py

It writes ``resources/chooser/framework.png`` and copies the
application icon beside it.

**A shipped PNG and not a live render.**  The chooser is the first
thing on screen, before any window exists, and starting VTK to draw a
picture there would put an OpenGL context -- the part of a bundle most
likely to fail -- in front of the question "which workspace".  The
icon is copied rather than read from ``packaging/`` because
``packaging/`` does not travel with the application and
``resources/chooser`` does; ``test_workspace_chooser.py`` checks that
the copy has not drifted from the original.
"""

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

import xtalapp

# Not ``__file__``: the driver runs this with ``exec``, which has none.
ROOT = Path(xtalapp.__file__).resolve().parents[1]
OUT = ROOT / "resources" / "chooser"
#: Twice the side panel's width, for a high-density screen.
SIZE = 440

OUT.mkdir(parents=True, exist_ok=True)

# The viewport alone, square, so the picture is not a letterbox.
for dock in win.docks:  # noqa: F821 -- the driver's scope
    dock.hide()
win.resize(760, 820)  # noqa: F821
settle(600)  # noqa: F821

doc.update_view(style="polyhedra_stick", show_cell=False,  # noqa: F821
                show_axes=False, show_legend=False, label_mode="none")
settle(400)  # noqa: F821
viewport.reset_view()  # noqa: F821
camera = viewport.scene.renderer.GetActiveCamera()  # noqa: F821
# Down a body diagonal, turned a little off it, so MOF-5 shows its
# cages rather than lining them up into a grid of squares.
camera.Azimuth(35)
camera.Elevation(25)
viewport.scene.renderer.ResetCamera()  # noqa: F821
camera.Zoom(1.35)
viewport._safe_render()  # noqa: F821
settle(400)  # noqa: F821

raw = OUT / "framework-raw.png"
viewport.save_image(raw, magnification=1, transparent=True)  # noqa: F821
image = QImage(str(raw))
side = min(image.width(), image.height())
image = image.copy((image.width() - side) // 2,
                   (image.height() - side) // 2, side, side)
image = image.scaled(SIZE, SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
image.save(str(OUT / "framework.png"))
raw.unlink()

shutil.copyfile(ROOT / "packaging" / "icons" / "app.svg", OUT / "app.svg")
print(f"wrote {OUT / 'framework.png'} ({image.width()} x "
      f"{image.height()}) and {OUT / 'app.svg'}")
