"""The Frameworks and Nets chapter's screenshots, one function per
figure.

Run through the run-app driver with a scratch profile, so every
figure is a first-run window at one size and nothing of the user's is
read or written::

    python .claude/skills/run-app/drive.py --scratch build/manual-shots \
        --script docs/manual/shots/frameworks.py

Each function writes ``docs/manual/figures/frameworks/<name>.png``.
The two builds are run through the window's own module runner, as a
person's Build button runs them, so the Results and Net panels show
what a build really leaves behind; the dialogs are shown, never
exec'd, and closed after the shot.

The names below are the run-app scope: ``win``, ``app``, ``imp``,
``settle``.
"""

import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QPoint

from xtal.modules import MODULES
from xtal.mof.catalog import Slot
from xtalapp.dialogs.build_molecule import BuildMoleculeDialog
from xtalapp.dialogs.draw_block import DrawBlockDialog
from xtalapp.dialogs.mof_build import MofBuildDialog
from xtalapp.dialogs.net_draw import NetDrawDialog

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "frameworks"
FIGURES.mkdir(parents=True, exist_ok=True)

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def say(text: str) -> None:
    print(f"shots: {text}", flush=True)


def wait_until(condition, seconds: float, what: str) -> None:
    """Pump the event loop until ``condition`` holds."""
    deadline = time.monotonic() + seconds
    while not condition():
        app.processEvents(QEventLoop.AllEvents, 50)          # noqa: F821
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what} did not finish in {seconds} s")


def grab_dialog(dialog, name: str, width=None, height=None) -> None:
    """A dialog shown, never exec'd, and closed after the shot."""
    dialog.show()
    if width:
        dialog.resize(width, height)
    settle(900)                                             # noqa: F821
    path = FIGURES / f"{name}.png"
    if not dialog.grab().save(str(path)):
        raise OSError(f"could not write {path}")
    dialog.close()
    say(f"wrote {path.relative_to(ROOT)}")


def grab_dock(dock, name: str, width: int, height: int) -> None:
    """One dock to a PNG, floated at a size and put back -- what
    run-app's ``--grab`` does."""
    floating, visible = dock.isFloating(), dock.isVisible()
    dock.setFloating(True)
    dock.show()
    dock.raise_()
    dock.move(win.geometry().topLeft() + QPoint(60, 60))     # noqa: F821
    dock.resize(width, height)
    settle(600)                                             # noqa: F821
    path = FIGURES / f"{name}.png"
    if not dock.grab().save(str(path)):
        raise OSError(f"could not write {path}")
    dock.setFloating(floating)
    dock.setVisible(visible)
    settle(200)                                             # noqa: F821
    say(f"wrote {path.relative_to(ROOT)}")


def viewport_shot(name: str) -> None:
    settle(600)                                             # noqa: F821
    path = FIGURES / f"{name}.png"
    win.current_viewport().save_image(str(path))            # noqa: F821
    say(f"wrote {path.relative_to(ROOT)}")


def build(values: dict) -> None:
    """Run the MOF builder as its Build button does, with these
    values standing in for the dialog's answer."""
    module, action = MODULES.find("mof.build")
    values = action.coerce(values)
    MofBuildDialog.ask = classmethod(lambda cls, *a, **k: dict(values))
    win.run_module_action("mof", "build")                   # noqa: F821
    wait_until(lambda: win.module_worker is None, 600,      # noqa: F821
               "the MOF build")
    doc = win.current_document()                            # noqa: F821
    say(f"built {doc.title}: {doc.cell.n_atoms} atoms in the cell")


BLANK = {"repeat": "1x1x1", "orientation": "consistent",
         "interpenetration": 1, "spacing": "", "offset": "",
         "topology_dir": "", "bb_dir": ""}


# ----------------------------------------------------------------------
#  frameworks/mof-builder.md
# ----------------------------------------------------------------------

def build_report() -> None:
    """The Results panel after MOF-5 (pcu, N16, E14) is built."""
    build(dict(BLANK, topology="pcu", nodes="N16", edges="E14"))
    grab_dock(win.results_dock, "build-report", 640, 900)   # noqa: F821


# ----------------------------------------------------------------------
#  frameworks/nets.md
# ----------------------------------------------------------------------

def net_panel() -> None:
    """The Net panel naming the net the builder drew on MOF-5."""
    dock = win.net_dock                                     # noqa: F821
    dock.show()
    dock.show_document(win.current_document())              # noqa: F821
    grab_dock(dock, "net-panel", 420, 420)


def net_builder() -> None:
    """The Net builder with hcb chosen."""
    module, action = MODULES.find("net.draw")
    initial = action.coerce({"net": "hcb", "scale": 8.0, "beads": 8})
    dialog = NetDrawDialog(module, action, win, initial)    # noqa: F821
    grab_dialog(dialog, "net-builder", 900, 620)


# ----------------------------------------------------------------------
#  frameworks/blocks.md
# ----------------------------------------------------------------------

def draw_block() -> None:
    """Draw a building block, aimed at a 3-connected node slot."""
    workspace = win.workspace                               # noqa: F821
    slot = Slot("node", 0, 3)
    dialog = DrawBlockDialog(slot, str(workspace.blocks), win)  # noqa: F821
    dialog.form.widgets["smiles"].setText("*c1cc(*)cc(*)c1")
    dialog.form.widgets["name"].setText("benzene-triyl")
    settle(900)                                             # noqa: F821
    # The footer names the folder it saves into.  The scratch run's
    # workspace is a temporary directory, so it is shown under the
    # name of the default workspace a first run makes, ``~/Crystal
    # Builder``; the ``blocks/`` under it is the real one.
    dialog.where.setText(dialog.where.text().replace(
        str(workspace.root), "~/Crystal Builder"))
    grab_dialog(dialog, "draw-block", 560, 700)


# ----------------------------------------------------------------------
#  frameworks/layers.md
# ----------------------------------------------------------------------

def layer_builder() -> None:
    """The MOF builder set up for Ni3(HITP)2 on hcb, a layer net."""
    module, action = MODULES.find("mof.build")
    values = action.coerce(dict(
        BLANK, topology="hcb", nodes="NiHITP_triphenylene",
        edges="NiHITP_NiN4", spacing="3.24"))
    dialog = MofBuildDialog(module, action, win, values)    # noqa: F821
    dialog.two_d.setChecked(True)
    dialog.three_d.setChecked(False)
    grab_dialog(dialog, "mof-builder-layer", 1000, 820)


def layer_built() -> None:
    """Ni3(HITP)2 on hcb, stacked at 3.24 A, seen in the viewport."""
    build(dict(BLANK, topology="hcb", nodes="NiHITP_triphenylene",
               edges="NiHITP_NiN4", spacing="3.24"))
    win.actions_["style_polyhedra_stick"].trigger()         # noqa: F821
    win.reset_view()                                        # noqa: F821
    viewport_shot("layer-built")


# ----------------------------------------------------------------------
#  frameworks/molecule-builder.md
# ----------------------------------------------------------------------

def molecule_builder() -> None:
    """The molecule builder with DMF typed in."""
    module, action = MODULES.find("build.molecule")
    initial = action.coerce({"smiles": "CN(C)C=O", "name": "DMF",
                             "optimise": True, "seed": 61453})
    dialog = BuildMoleculeDialog(module, action, win, initial)  # noqa: F821
    grab_dialog(dialog, "molecule-builder", 560, 640)


build_report()
net_panel()
net_builder()
draw_block()
layer_builder()
layer_built()
molecule_builder()
