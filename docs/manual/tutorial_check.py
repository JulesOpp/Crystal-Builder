"""Prove the quickstart's first-build tutorial in the real window.

Run through the run-app driver, with a scratch profile so nothing of
the user's is touched::

    python .claude/skills/run-app/drive.py --scratch build/tutorial \
        --script docs/manual/tutorial_check.py

It performs the exercise ``quickstart/first-build.md`` describes, in
the order the chapter gives it and through the doors a person uses --
the block-drawing dialog's own save, the MOF builder's module run,
the Force Field panel's Optimise, the Find symmetry dialog's Adopt,
the Document's net-edge verbs -- and reads the answers off the Net
panel rather than off the core.  A step whose answer is not the one
the chapter prints raises, which stops the run: then the tutorial is
wrong or the application is, and that is a decision for a person.

It prints the space group and both net names, and writes the
chapter's figures into ``docs/manual/figures/quickstart/``.  It is the
tutorial's regression check: rerun it whenever the builder, the force
field, the symmetry finder or the net identification changes.

The names below are the run-app scope: ``win``, ``app``, ``imp``,
``settle``.
"""

import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEventLoop, QPoint

from xtal.core import bonding
from xtal.modules import MODULES
from xtal.mof.catalog import Slot
from xtalapp.dialogs.draw_block import DrawBlockDialog
from xtalapp.dialogs.find_symmetry import FindSymmetryDialog
from xtalapp.dialogs.mof_build import MofBuildDialog

ROOT = Path(imp("xtal.__file__")).resolve().parents[1]     # noqa: F821
FIGURES = ROOT / "docs" / "manual" / "figures" / "quickstart"
FIGURES.mkdir(parents=True, exist_ok=True)

EXPECTED_GROUP = "P63/mmc"           # SpaceGroup.short_name's spelling
EXPECTED_NETS = ("acs", "ssa")

win.resize(1600, 1000)                                      # noqa: F821
settle(400)                                                 # noqa: F821


def say(text: str) -> None:
    print(f"tutorial: {text}", flush=True)


def wait_until(condition, seconds: float, what: str) -> None:
    """Pump the event loop until ``condition`` holds."""
    deadline = time.monotonic() + seconds
    while not condition():
        app.processEvents(QEventLoop.AllEvents, 50)          # noqa: F821
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what} did not finish in {seconds} s")


def grab_dock(dock, path: Path, width: int, height: int) -> None:
    """One dock to a PNG, floated at a size and put back -- what
    run-app's ``--grab`` does."""
    floating, visible = dock.isFloating(), dock.isVisible()
    dock.setFloating(True)
    dock.show()
    dock.raise_()
    dock.move(win.geometry().topLeft() + QPoint(60, 60))     # noqa: F821
    dock.resize(width, height)
    settle(500)                                             # noqa: F821
    if not dock.grab().save(str(path)):
        raise OSError(f"could not write {path}")
    dock.setFloating(floating)
    dock.setVisible(visible)
    settle(200)                                             # noqa: F821
    say(f"wrote {path.name}")


def grab_dialog(dialog, path: Path) -> None:
    dialog.show()
    settle(500)                                             # noqa: F821
    if not dialog.grab().save(str(path)):
        raise OSError(f"could not write {path}")
    dialog.close()
    say(f"wrote {path.name}")


def viewport_shot(path: Path) -> None:
    settle(600)                                             # noqa: F821
    win.current_viewport().save_image(str(path))            # noqa: F821
    say(f"wrote {path.name}")


def nearest_image(structure, cell, a: int, b: int):
    """The lattice image of ``b`` closest to ``a``, and the distance."""
    matrix = structure.lattice.matrix
    best = None
    for t in np.ndindex(5, 5, 5):
        shift = np.array(t) - 2
        d = np.linalg.norm(cell.cart[b] + shift @ matrix - cell.cart[a])
        if best is None or d < best[1]:
            best = (tuple(int(v) for v in shift), float(d))
    return best


def net_name(document) -> str:
    """What the Net panel says, read off the panel."""
    dock = win.net_dock                                     # noqa: F821
    dock.show()
    dock.show_document(document)
    settle(200)                                             # noqa: F821
    return dock.name.text()


# ----------------------------------------------------------------------
#  1. The linker, drawn and saved into the workspace's blocks folder
# ----------------------------------------------------------------------

workspace = win.workspace                                   # noqa: F821
assert workspace is not None, "the driver's scratch run has no workspace"
slot = Slot("edge", (0, 0), 2)
draw = DrawBlockDialog(slot, str(workspace.blocks), win)    # noqa: F821
draw.form.widgets["smiles"].setText("*c1ccc(*)cc1")
draw.form.widgets["name"].setText("benzene")
draw.accept()
if draw.path is None:
    raise RuntimeError(
        f"the block was not written: {draw.footer.text()!r}")
say(f"block written to {draw.path.relative_to(workspace.root)}: "
    f"{draw.footer.text()}")

# ----------------------------------------------------------------------
#  2. The build: acs, N134, the drawn linker
# ----------------------------------------------------------------------

module, action = MODULES.find("mof.build")
values = action.coerce({
    "topology": "acs", "nodes": "N134", "edges": draw.path.stem,
    "repeat": "1x1x1", "orientation": "consistent",
    "interpenetration": 1, "spacing": "", "offset": "",
    "topology_dir": "", "bb_dir": ""})
# The dialog as the reader fills it in, for the chapter; then the
# same answer given without showing it, and the run itself is the
# window's own, through the module runner.
dialog = MofBuildDialog(module, action, win, values)        # noqa: F821
values = dialog.values()            # as Build would hand them over
say(f"the MOF builder dialog holds: topology {values['topology']!r}, "
    f"nodes {values['nodes']!r}, edges {values['edges']!r}")
if values["topology"] != "acs" or "N134" not in values["nodes"] \
        or draw.path.stem not in values["edges"]:
    raise RuntimeError("the dialog does not hold the tutorial's answer")
dialog.resize(1000, 760)
grab_dialog(dialog, FIGURES / "first-build-mof-builder.png")
MofBuildDialog.ask = classmethod(lambda cls, *a, **k: dict(values))
win.run_module_action("mof", "build")                       # noqa: F821
wait_until(lambda: win.module_worker is None, 600,          # noqa: F821
           "the MOF build")
doc = win.current_document()                                # noqa: F821
if doc is None or "acs" not in doc.title:
    raise RuntimeError("the build did not open a tab of its own")
structure = doc.structure
a, b, c = structure.lattice.lengths
say(f"built {doc.title}: {structure.n_sites} sites, "
    f"{doc.cell.n_atoms} atoms in the cell, "
    f"a = {a:.3f}, b = {b:.3f}, c = {c:.3f} A, "
    f"space group {structure.space_group.short_name}")
say(f"net drawn by the builder: {net_name(doc)!r}")
win.actions_["style_polyhedra_stick"].trigger()             # noqa: F821
win.reset_view()                                            # noqa: F821

# ----------------------------------------------------------------------
#  3. UFF4MOF, the cell relaxed, the Smart optimiser, to convergence
# ----------------------------------------------------------------------

ff = win.ff_dock                                            # noqa: F821
win.actions_["show_ff"].trigger()                           # noqa: F821
settle(300)                                                 # noqa: F821
ff.engine.setCurrentIndex(ff.engine.findData("uff"))
ff.parameter_set.setCurrentIndex(ff.parameter_set.findData("uff4mof"))
ff.method.setCurrentIndex(ff.method.findData("smart"))
ff.relax_cell.setChecked(True)
assert ff.engine_name() == "uff"
assert ff.options()["parameter_set"] == "uff4mof"
assert ff.method.currentData() == "smart"

runs = 0
summary = ""
while True:
    runs += 1
    started = time.monotonic()
    ff.start()
    if ff.worker is None:
        raise RuntimeError(f"Optimise did not start: "
                           f"{ff.report.toPlainText()!r}")
    # The panel lets go of its worker when the run has ended, which is
    # what the suite waits on too.
    wait_until(lambda: ff.worker is None, 3600, "the relaxation")
    summary = ff.report.toPlainText().splitlines()[0]
    say(f"optimise run {runs}: {summary} "
        f"({time.monotonic() - started:.0f} s)")
    if summary.startswith("converged"):
        break
    if runs >= 4:
        raise RuntimeError("the relaxation did not converge in four "
                           "runs of the panel's Optimise")
a, b, c = doc.structure.lattice.lengths
say(f"relaxed cell a = {a:.3f}, b = {b:.3f}, c = {c:.3f} A")
say(f"panel note: {ff.notes.text()}")
grab_dock(ff, FIGURES / "first-build-forcefield.png", 460, 980)

# ----------------------------------------------------------------------
#  4. Find symmetry: P6_3/mmc
# ----------------------------------------------------------------------

finder = FindSymmetryDialog(doc, win)                       # noqa: F821
say(f"Find symmetry at {finder.symprec()} A says: "
    f"{finder.summary.text()!r}")
grab_dialog(finder, FIGURES / "first-build-find-symmetry.png")
finder.adopt()
if finder.re_expressed:
    win.reset_view()                                        # noqa: F821
group = doc.structure.space_group.short_name
say(f"SPACE GROUP: {group}  (H-M {doc.structure.space_group.hm}, "
    f"No. {doc.structure.space_group.number}); "
    f"{doc.structure.n_sites} sites in the asymmetric unit")
if group != EXPECTED_GROUP:
    raise RuntimeError(f"expected {EXPECTED_GROUP}, got {group}")
say(f"net after Find symmetry: {net_name(doc)!r}")

# ----------------------------------------------------------------------
#  5. Topology bonds on the mu3-oxo centres: acs
# ----------------------------------------------------------------------

structure, cell, graph = doc.structure, doc.cell, doc.graph
elements = list(cell.elements)


def mu3_oxo() -> list[int]:
    return [i for i, e in enumerate(elements)
            if e == "O" and sorted(elements[j]
                                   for j in graph.neighbors(i)) ==
            ["Ni", "Ni", "Ni"]]


centres = mu3_oxo()
say(f"{len(centres)} mu3-oxo centres in the cell: "
    f"{[cell.labels[i] for i in centres]}")
if len(centres) != 2:
    raise RuntimeError("acs on N134 should put two trimers in the cell")

# Start from no net at all, so what is drawn is what the reader draws.
drawn = bonding.topology_graph(structure).bonds
if drawn:
    for bond in drawn:
        doc.select_topology((bond.i, bond.j, bond.image), "toggle")
    say(f"cleared the builder's net: {doc.delete_selected_topology()}")

first, second = centres
image, distance = nearest_image(structure, cell, first, second)
say(f"drawing {cell.labels[first]} -> {cell.labels[second]} "
    f"{image}, {distance:.2f} A apart: "
    + doc.add_topology_bond_between(first, second, (0, 0, 0), image))
acs = net_name(doc)
say(f"NET 1: {acs!r}")
if acs != EXPECTED_NETS[0]:
    raise RuntimeError(f"expected {EXPECTED_NETS[0]}, got {acs!r}")
say("net panel says: " + win.net_dock.text.toPlainText()  # noqa: F821
    .replace("\n", " | "))
win.reset_view()                                            # noqa: F821
viewport_shot(FIGURES / "first-build-net-acs.png")

# ----------------------------------------------------------------------
#  6. Delete an edge, a centroid at the ring, edges to the metals: ssa
# ----------------------------------------------------------------------

edge = bonding.topology_graph(doc.structure).bonds[0]
doc.select_topology((edge.i, edge.j, edge.image))
say(f"delete one net edge: {doc.delete_selected_topology()}")
if not doc.net().is_empty():
    raise RuntimeError("deleting one edge left part of the net behind")

structure, cell, graph = doc.structure, doc.cell, doc.graph
elements = list(cell.elements)
ring_carbons = [i for i, e in enumerate(elements)
                if e == "C" and all(elements[j] in ("C", "H")
                                    for j in graph.neighbors(i))]
ring = {ring_carbons[0]}
frontier = [ring_carbons[0]]
while frontier:
    i = frontier.pop()
    for j in graph.neighbors(i):
        if j in ring_carbons and j not in ring:
            ring.add(j)
            frontier.append(j)
if len(ring) != 6:
    raise RuntimeError(f"a benzene ring has six carbons, found {ring}")
doc.select(sorted(ring), "set")
say("Add centroid: " + doc.add_centroid("X"))
# The new site is left selected -- its whole orbit, one marker in
# every ring the group generates -- and any one of them will do.
centroid = min(doc.selection.atoms)
say(f"{len(doc.selection.atoms)} centroids in the cell, one per ring")

structure, cell, graph = doc.structure, doc.cell, doc.graph
metals = [i for i, e in enumerate(cell.elements) if e == "Ni"]
image, distance = nearest_image(
    structure, cell, centroid,
    min(metals, key=lambda m: nearest_image(structure, cell,
                                            centroid, m)[1]))
metal = min(metals, key=lambda m: nearest_image(structure, cell,
                                                centroid, m)[1])
say(f"drawing {cell.labels[centroid]} -> {cell.labels[metal]} {image}, "
    f"{distance:.2f} A apart: "
    + doc.add_topology_bond_between(centroid, metal, (0, 0, 0), image))
ssa = net_name(doc)
say(f"NET 2: {ssa!r}")
if ssa != EXPECTED_NETS[1]:
    raise RuntimeError(f"expected {EXPECTED_NETS[1]}, got {ssa!r}")
say("net panel says: " + win.net_dock.text.toPlainText()  # noqa: F821
    .replace("\n", " | "))
win.actions_["style_net"].trigger()                         # noqa: F821
win.reset_view()                                            # noqa: F821
viewport_shot(FIGURES / "first-build-net-ssa.png")
win.actions_["style_polyhedra_stick"].trigger()             # noqa: F821

print(f"RESULT space group {group}; nets {acs}, {ssa}")
