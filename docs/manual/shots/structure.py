"""Chapter 4's screenshots (Structure and Optimisation), one function
per figure.

Run through the run-app driver with a scratch profile::

    python .claude/skills/run-app/drive.py --scratch build/manual-shots \
        --script docs/manual/shots/structure.py

Each function writes ``docs/manual/figures/structure/<name>.png``.  A
dialog is shown, never exec'd, grabbed and closed, as ``--grab`` does.
The names below are the run-app scope: ``win``, ``app``, ``imp``,
``settle``.
"""

from pathlib import Path

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "structure"
SAMPLES = ROOT / "resources" / "samples"

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def _out(name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    return FIGURES / f"{name}.png"


def _save(pixmap, path: Path) -> None:
    if not pixmap.save(str(path)):
        raise OSError(f"could not write {path}")
    print(f"shots: wrote {path.relative_to(ROOT)}")


def _open(path: Path):
    win.open_path(path)                                     # noqa: F821
    settle(600)                                             # noqa: F821
    return win.current_document()                           # noqa: F821


def grab_dialog(dialog, path: Path, width=None, height=None) -> None:
    dialog.show()
    if width:
        dialog.resize(width, height)
    settle(700)                                             # noqa: F821
    _save(dialog.grab(), path)
    dialog.close()


def prepare_dialog() -> None:
    """Structure > Prepare for simulation... on the COD MIL-88B."""
    doc = _open(SAMPLES / "cod" / "MIL-88B.cif")
    PrepareDialog = imp("xtalapp.dialogs.prepare.PrepareDialog")  # noqa: F821
    grab_dialog(PrepareDialog(doc, win), _out("prepare-mil88b"),  # noqa: F821
                640, 560)


def interpenetrate_dialog() -> None:
    """Structure > Interpenetrate... on the COD MOF-5, at 2-fold."""
    doc = _open(SAMPLES / "cod" / "MOF-5.cif")
    Dialog = imp("xtalapp.dialogs.interpenetrate.InterpenetrateDialog")  # noqa: F821
    grab_dialog(Dialog(doc, win), _out("interpenetrate-mof5"),  # noqa: F821
                760, 480)


prepare_dialog()
interpenetrate_dialog()
