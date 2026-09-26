"""The Utilities and Export chapter's screenshots, one function per figure.

Run through the run-app driver with a scratch profile, so every
figure is a first-run window at one size and nothing of the user's is
read or written::

    python .claude/skills/run-app/drive.py --scratch build/manual-shots \
        --script docs/manual/shots/utilities.py

Each function writes ``docs/manual/figures/utilities/<name>.png``.
Dialogs are shown, never exec'd, and closed after the shot.  The
crystal itself goes through ``viewport.save_image`` -- the same door
*File > Export Image...* uses -- because a Qt grab cannot see into a
GL surface.  The names below are the run-app scope: ``win``, ``app``,
``imp``, ``settle``.
"""

from pathlib import Path

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "utilities"

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def _out(name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    return FIGURES / f"{name}.png"


def _save(pixmap, path: Path) -> None:
    if not pixmap.save(str(path)):
        raise OSError(f"could not write {path}")
    print(f"shots: wrote {path.relative_to(ROOT)}")


def grab_dialog(dialog, path: Path, width=None, height=None) -> None:
    """A dialog shown, never exec'd, and closed after the shot."""
    dialog.show()
    if width:
        dialog.resize(width, height)
    settle(600)                                             # noqa: F821
    _save(dialog.grab(), path)
    dialog.close()


# ----------------------------------------------------------------------
#  utilities/export.md
# ----------------------------------------------------------------------

def export_dialog() -> None:
    """File > Export... on HKUST-1, with the CIF options showing."""
    doc = win.open_sample("hkust1")                         # noqa: F821
    settle(800)                                             # noqa: F821
    dialog = imp("xtalapp.dialogs.export"                   # noqa: F821
                 ".ExportDialog")(doc, win,                 # noqa: F821
                                  directory=str(Path.home()))
    print("shots: export keeps line:", dialog.keeps.text())
    grab_dialog(dialog, _out("export-dialog"), 620, 320)


# ----------------------------------------------------------------------
#  utilities/images.md
# ----------------------------------------------------------------------

def image_export_dialog() -> None:
    """File > Export Image... with the pixel size the export will
    write, as the dialog computes it from this screen."""
    viewport = win.current_viewport()                       # noqa: F821
    size = viewport.image_size()
    ratio = win.devicePixelRatio()                          # noqa: F821
    print(f"shots: viewport {viewport.width()}x{viewport.height()} "
          f"logical, render window {size[0]}x{size[1]}, "
          f"device pixel ratio {ratio:g}")
    dialog = imp("xtalapp.dialogs.image_export"             # noqa: F821
                 ".ImageExportDialog")(win,                 # noqa: F821
                                       directory=str(Path.home()),
                                       stem="HKUST1", size=size)
    print("shots: image export resolution line:",
          dialog.pixels.text())
    grab_dialog(dialog, _out("image-export-dialog"), 620, 300)


def hkust1_on_white() -> None:
    """The view HKUST-1 opens with, written through save_image on a
    white background -- View > Background > White -- at 1x."""
    win.set_background("white")                             # noqa: F821
    win.reset_view()                                        # noqa: F821
    settle(600)                                             # noqa: F821
    viewport = win.current_viewport()                       # noqa: F821
    path = _out("hkust1-white")
    viewport.save_image(str(path), magnification=1)
    from PySide6.QtGui import QImage
    picture = QImage(str(path))
    print(f"shots: wrote {path.relative_to(ROOT)} "
          f"({picture.width()}x{picture.height()} pixels at 1x)")


# ----------------------------------------------------------------------
#  utilities/stl.md
# ----------------------------------------------------------------------

def stl_dialog() -> None:
    """File > Export as STL...: the settings form, whether or not
    Blender is installed (the dialog is built directly)."""
    module, action = imp("xtal.modules.registry"            # noqa: F821
                         ".MODULES").find("blender.export-stl")
    dialog = imp("xtalapp.dialogs.stl_export"               # noqa: F821
                 ".StlExportDialog")(module, action, win,   # noqa: F821
                                     None)
    grab_dialog(dialog, _out("stl-export-dialog"), 640, 400)


def stl_when_blender_is_missing() -> None:
    """What the menu entry says on a machine without Blender."""
    win.actions_.get("export_stl").trigger()                # noqa: F821
    settle(400)                                             # noqa: F821
    print("shots: status after Export as STL:",
          win.statusBar().currentMessage())                 # noqa: F821
    available = imp("xtal.modules.blender.available")()    # noqa: F821
    print("shots: blender availability:", bool(available),
          getattr(available, "reason", ""))


export_dialog()
image_export_dialog()
hkust1_on_white()
stl_dialog()
stl_when_blender_is_missing()
