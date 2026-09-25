"""The manual's screenshots, one function per figure.

Run through the run-app driver with a scratch profile, so every
figure is a first-run window at one size and nothing of the user's is
read or written::

    python .claude/skills/run-app/drive.py --scratch build/manual-shots \
        --script docs/manual/shots.py

Each function writes ``docs/manual/figures/<chapter>/<name>.png``.
Figures are named after what they show.  A dock or a dialog is grabbed
on its own, as ``--grab`` does; the crystal comes from VTK through
``viewport.save_image``, because a Qt grab cannot see into a GL
surface -- which is also why :func:`window` pastes the render into the
grabbed chrome at the viewport's own geometry rather than leaving the
middle of the window black.

The first-build tutorial's figures are not here: ``tutorial_check.py``
writes them, because they are the evidence that the tutorial works
and have to come from the run that proved it.

The names below are the run-app scope: ``win``, ``app``, ``imp``,
``settle``.
"""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures"

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def _out(chapter: str, name: str) -> Path:
    path = FIGURES / chapter / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _save(pixmap, path: Path) -> None:
    if not pixmap.save(str(path)):
        raise OSError(f"could not write {path}")
    print(f"shots: wrote {path.relative_to(ROOT)}")


def grab_dialog(dialog, path: Path, width=None, height=None) -> None:
    """A dialog shown, never exec'd, and closed after the shot."""
    dialog.show()
    if width:
        dialog.resize(width, height)
    settle(500)                                             # noqa: F821
    _save(dialog.grab(), path)
    dialog.close()


# ----------------------------------------------------------------------
#  quickstart/gui.md
# ----------------------------------------------------------------------

def workspace_chooser() -> None:
    """The question asked before the window opens."""
    chooser = imp("xtalapp.dialogs.workspace_chooser"      # noqa: F821
                  ".WorkspaceChooser")(win.settings, win)   # noqa: F821
    grab_dialog(chooser, _out("quickstart", "workspace-chooser"))


def window() -> None:
    """The window with a sample open: toolbar, panels, tabs, status."""
    win.open_sample("mof5")                                 # noqa: F821
    settle(800)                                             # noqa: F821
    win.reset_view()                                        # noqa: F821
    settle(400)                                             # noqa: F821
    chrome = win.grab().toImage()                           # noqa: F821
    viewport = win.current_viewport()                       # noqa: F821
    render = _out("quickstart", "_viewport-render")
    viewport.save_image(str(render))
    picture = QImage(str(render))
    render.unlink()
    # Where the viewport sits in the window, in the grab's pixels: the
    # grab is at the screen's device pixel ratio and so is VTK's
    # image, so one scale serves both.
    # Where the viewport sits in the window.  The grab carries the
    # screen's device pixel ratio and a painter on it works in logical
    # pixels, so the render -- which VTK wrote at device pixels -- is
    # given the same ratio and drawn at the widget's logical corner.
    ratio = chrome.devicePixelRatio()
    corner = viewport.mapTo(win, QPoint(0, 0))              # noqa: F821
    print(f"shots: viewport {viewport.width()}x{viewport.height()} "
          f"at {corner.x()},{corner.y()} (ratio {ratio:g}); render "
          f"{picture.width()}x{picture.height()}")
    # save_image magnifies on top of the screen's ratio, so the render
    # is brought down to the widget's device-pixel size first.
    picture = picture.scaled(int(viewport.width() * ratio),
                             int(viewport.height() * ratio),
                             Qt.IgnoreAspectRatio,
                             Qt.SmoothTransformation)
    picture.setDevicePixelRatio(ratio)
    painter = QPainter(chrome)
    painter.drawImage(corner, picture)
    painter.end()
    if not chrome.save(str(_out("quickstart", "window"))):
        raise OSError("could not write window.png")
    print("shots: wrote docs/manual/figures/quickstart/window.png "
          "(chrome grab with the VTK render pasted in)")


# ----------------------------------------------------------------------
#  quickstart/installation.md
# ----------------------------------------------------------------------

def preferences_engines() -> None:
    """Preferences > Engines: where the external programs are named."""
    dialog = win.preferences_dialog()                       # noqa: F821
    dialog.show_page("Engines")
    grab_dialog(dialog, _out("quickstart", "preferences-engines"),
                980, 940)


workspace_chooser()
preferences_engines()
window()
