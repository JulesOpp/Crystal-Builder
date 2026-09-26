"""Chapter 5's screenshots (Porosity and Properties), one function per
figure.

Run through the run-app driver with a scratch profile::

    python .claude/skills/run-app/drive.py --scratch build/manual-shots \
        --script docs/manual/shots/porosity.py

Each function writes ``docs/manual/figures/porosity/<name>.png``.  The
names below are the run-app scope: ``win``, ``app``, ``imp``,
``settle``.

Neither figure needs Zeo++: the pore surface is the application's own
grid (:mod:`xtal.analysis.grid`, :mod:`xtal.analysis.voids`), drawn the
way the *(faster)* volume entry draws it, and the pattern window is
built from the same report block the Results panel shows.
"""

import importlib
from pathlib import Path

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "porosity"
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
    settle(900)                                             # noqa: F821
    _save(dialog.grab(), path)
    dialog.close()


class _Job:
    """The two things ``channel_overlay`` asks of a job."""

    def __init__(self, structure):
        self.structure = structure

    def note(self, text):
        print(f"shots: {text}")


def pore_surface() -> None:
    """The channels' surface on ZIF-8 to a hydrogen probe, as the
    Accessible volume (faster) entry draws it."""
    grids = importlib.import_module("xtal.analysis.grid")
    voids = importlib.import_module("xtal.analysis.voids")
    porosity = importlib.import_module("xtal.analysis.porosity")
    zeopp = importlib.import_module("xtal.modules.zeopp")

    doc = _open(SAMPLES / "ZIF-8.cif")
    structure = doc.structure
    probe = porosity.probe_radius("h2")
    field = grids.distance_grid(structure, porosity.zeo_radius,
                                spacing=0.4)
    split = voids.classify(structure, field, porosity.zeo_radius, probe)
    network = zeopp.channel_overlay(_Job(structure), field, split)
    if network is None:
        raise RuntimeError("no channel surface to draw on ZIF-8")
    doc.set_pores(network)
    settle(1200)                                            # noqa: F821
    viewport = win.current_viewport()                       # noqa: F821
    path = _out("pore-surface-zif8")
    viewport.save_image(str(path))
    _crop_to_content(path)
    print(f"shots: wrote {path.relative_to(ROOT)}")


def _crop_to_content(path: Path, margin: int = 40) -> None:
    """Cut the viewport shot down to what is drawn.

    A viewport shot is the whole window's aspect and the crystal is a
    small cell in the middle of it; the figure wants the cell.  The
    background is the colour of the top-left pixel, and everything
    that differs from it is content -- the axes triad included.
    """
    import numpy as np
    QImage = imp("PySide6.QtGui.QImage")                    # noqa: F821
    image = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888)
    width, height = image.width(), image.height()
    pixels = np.frombuffer(image.constBits(), np.uint8).reshape(
        height, image.bytesPerLine())[:, :width * 4].reshape(height, width, 4)
    content = (pixels[:, :, :3] != pixels[0, 0, :3]).any(axis=2)
    rows, cols = np.nonzero(content)
    if not len(rows):
        return
    top, bottom = max(0, rows.min() - margin), min(height, rows.max() + margin)
    left, right = max(0, cols.min() - margin), min(width, cols.max() + margin)
    cropped = image.copy(int(left), int(top), int(right - left),
                         int(bottom - top))
    if not cropped.save(str(path)):
        raise OSError(f"could not write {path}")


def pattern_window() -> None:
    """The pattern window (the pxrd extra) on HKUST-1's calculated
    pattern, Cu Ka1, 5 to 50 degrees."""
    pxrd = importlib.import_module("xtal.analysis.pxrd")
    module = importlib.import_module("xtal.modules.pxrd")
    Dialog = imp("xtalapp.dialogs.pattern.PatternDialog")   # noqa: F821

    doc = _open(SAMPLES / "HKUST1.cif")
    simulation = pxrd.simulate(doc.structure, with_absences=True,
                               label=doc.structure.meta.get("title", ""))
    source = pxrd.wavelength_label("cu-ka1")
    report = module.report_for(simulation, source)
    curve = report.blocks[0]
    grab_dialog(Dialog(curve, win), _out("pattern-window-hkust1"),  # noqa: F821
                960, 640)


pore_surface()
pattern_window()
