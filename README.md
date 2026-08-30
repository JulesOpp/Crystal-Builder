# Crystal Builder

A desktop application for building, manipulating, analysing and
exporting crystal structures.  The visual and interaction model follows
**VESTA**; the symmetry and force-field capability follows **Materials
Studio**.  Python throughout, shipped to macOS and Windows.

Status: **phase 7 complete** — the core, the headless CLI, and an
application you can build structures in: click to place atoms and draw
bonds, move and rotate the selection, copy and paste, find the symmetry
at a tolerance you choose, change the space group, build supercells and
edit the cell, draw coordination polyhedra, measure distances, angles
and torsions, save the whole session as a project, and now put a
**UFF** energy on a structure and relax it without leaving its space
group.  Next up is packaging.  See [docs/PLAN.md](docs/PLAN.md) for the
full architecture and roadmap, and [docs/TODO.md](docs/TODO.md) for
what is wanted but not yet scheduled.

---

## Layout

    xtal/       core library — no Qt, no VTK, importable anywhere
      core/     lattice, sites, space groups, structure,
                symmetry, P1 expansion, neighbours, bonding,
                supercells, measurement, properties
      io/       CIF, extended XYZ (single frame and trajectory)
                and .xtalproj projects, format registry
      workspace.py  the workspace layout and the run folders a
                calculation leaves behind
      cli.py    the `xtal` command line
      commands/ undoable mutations: the stack, atom/bond/cell/
                symmetry commands, the clipboard fragment
      ff/       the Calculator API and engine registry, Ewald
                sums, FIRE and L-BFGS optimisers
        uff/    UFF: parameter table, atom typer, energy terms,
                calculator, QEq charges
      analysis/ RDF, coordination, later PXRD    (phase 9)
    xtalapp/    the PySide6 + VTK application
      viewport/ scene model, builder, draw styles, VTK, the widget
      docks/    workspace tree, inspector, sites, style, measure,
                force field, log viewer, transport bar
      document.py, mainwindow.py, actions.py, settings.py
      workers.py, plot.py   long jobs off the GUI thread
    tests/      headless test suite

The wall between `xtal/` and `xtalapp/` is enforced by a test
(`tests/test_core_is_headless.py`): the core may never import Qt or
VTK, so it stays usable from a script, a notebook, or CI.

## Install (development)

```bash
git clone https://github.com/JulesOpp/Crystal-Builder
cd Crystal-Builder
pip install -e ".[dev]"
pytest -q
```

`pip install -e .` alone installs only the headless core (numpy, scipy,
gemmi, spglib) — the force field included.  The `[gui]` extra adds
PySide6 and VTK.

## Running the application

```bash
crystal-builder                 # or: python -m xtalapp.main
crystal-builder quartz.cif
```

Open a CIF from the file tree on the left or by dropping it on the
window.  Left-drag orbits, the wheel zooms, middle-drag pans.  The
*View* menu switches between ball-and-stick, stick, wireframe and
space-filling; the toolbar spinboxes set how many unit cells are drawn.

Click an atom or a bond to select it, shift-click to add to the
selection, double-click for the whole molecule or framework.  The
*Select* menu grows a selection by element, by bonded neighbours, by
fragment or by symmetry orbit.  The Inspector edits the selected site
(element, label, coordinates, occupancy, Uiso, charge) and the Sites
tab is the same data as a table.

Because the document holds an asymmetric unit and a space group, an
edit to one atom is an edit to its whole symmetry orbit -- the
Inspector says so before you make it, and *Reduce to P1* is the way to
edit atoms one at a time.

*Add atom* places an atom of the toolbar's element where you click;
*Add bond* joins two atoms (and removes a bond you click on) -- and
because a drawn atom knows which lattice translation put it there,
bonding the copy in the next cell along makes the bond it looks like.
The Move dock translates, rotates and mirrors the selection, in
fractional or cartesian units.  Everything is undoable (`Ctrl+Z` /
`Ctrl+Shift+Z`), and copy/paste works through the system clipboard as
XYZ, so fragments travel to and from other programs.

Bonds do not change when atoms move -- not while you drag one, and not
during a relaxation.  *Structure → Recalculate bonds* (`Ctrl+B`) is
what changes them, and *Structure → Bond rules* is where the criteria
live: a radius factor with the bond count beside it, metal-metal
bonding as its own switch, and a per-pair table of the elements you
actually have.  The preview says what would change -- "6 added, 2
removed" -- rather than only the total, because a count alone hides a
setting that swaps one bond for another.  If you would rather bonds
followed the geometry, *Structure → Bonds follow the geometry* says so.

The *Symmetry* menu is the workflow the data model was built for.
*Find symmetry* detects the space group at a tolerance you can change
while watching the answer -- the same coordinates are P1 at 10⁻⁵ and
tetragonal at 10⁻², and the Wyckoff table underneath says whether the
answer is the one you expected.  Adopting a group reduces the cell to
its asymmetric unit; a loose tolerance idealises the coordinates and
says by how much.  *Set space group* picks any setting of any of the
230 groups -- by number, symbol or crystal system -- and shows how many
atoms generating or imposing it would leave you with before you
commit.

The *Cell* menu edits the cell itself: parameters, supercells as
multiples or as a general integer matrix, and Niggli and Delaunay
reduction.  The cell editor only lets you change the numbers the space
group leaves free -- a hexagonal cell has *a* and *c* and nothing else,
and the rest follow -- because a cell its own symmetry operations no
longer map onto itself is not a cell.  It also asks whether to hold the
fractional or the cartesian coordinates fixed, because the two mean
opposite things.  *View → Display range* controls how much of the
crystal is drawn, and whether bonds at the edge are completed with the
atoms just outside.

The *Style* panel is where the picture is tuned: draw style, atom size,
bond thickness, labels, background, an element legend, and the colour
and radius of every element, each overridable and each resettable.
**Polyhedra** is the VESTA signature style -- coordination spheres as
translucent convex hulls, coloured by the atom at the centre.  The
*Measure* tool takes distances, angles and torsions; how many atoms you
click is the whole of the choice between them, and every measurement is
minimum-image aware, so one taken across the cell boundary follows the
bond rather than the long way round the box.

**Save is about the session; Export is about producing a file for
something else.**  *File → Save* writes a `.xtalproj`: the structure,
how you were looking at it, what was selected, what you had measured,
and the calculations run against it.  It is a zip of a CIF and three
small JSON files, so it stays readable and diffable, and it is the
only format that keeps the bonds -- both the perceived graph, so a
structure comes back with the bonds you last recalculated rather than
whatever its geometry now implies, and the ones you drew by hand,
which are (site, site, symmetry operation, lattice translation) and
which no CIF tag expresses.  *File → Export* is one way: it never
becomes the document's file, and it says what the format drops before
it writes it ("XYZ keeps occupancy; symmetry, bonds and charges are
not written").

**A workspace is where calculations land.**  Point *File → New
Workspace* at an ordinary folder and every structure opened gets a
folder of its own inside it, with a copy of the file so the workspace
is whole; every run then lands underneath the structure it was run
against:

    MFU4l/
      MFU4l.cif                a copy, so the workspace is whole
      MFU4l.xtalproj           the session, saved beside it
      uff-optimise-001/
        final.cif              the relaxed structure
        trajectory.extxyz      every step
        run.log                what happened, in order

Nothing in it is hidden and nothing needs this application to read it
-- the trajectory opens in OVITO, VMD and ASE, the log is a text file,
and deleting the folder in Finder is a supported way to clean up.  The
run folders are written by the module that ran, not by the tree that
shows them, so `xtal optimize structure.cif --workspace DIR` produces
the identical layout from a script.

Clicking a node in the tree opens it as what it *is*.  A **trajectory**
opens a transport bar under the viewport -- play, loop, step, scrub, a
speed control -- and clicking the energy trace jumps to that frame,
because the plot and the trajectory are the same run seen two ways.  A
frame is not an editable structure: playback puts the document into a
preview state that refuses edits, with *Adopt this frame* as the one
way out that keeps a geometry, as a single undoable command.  A
**log** opens a monospaced viewer that tails the file while the run is
still writing it, and what it contains is what makes a result
defensible three months later: the version, the engine and every
option, the full typing table with the reason for each assignment, the
topology counts, a line per step, and the per-term energy breakdown at
both ends.

The *Calculate* menu and the **Force Field** panel put an energy on the
structure.  The panel leads with the thing that decides whether that
energy means anything: a table of every site's UFF atom type, how sure
the typer was, and the sentence explaining why it chose that one --
"in a flat aromatic ring", "bridges Si and Si at 144 degrees, a
framework oxygen", "6 neighbours, which no Zn type in UFF was fitted
for".  Any of them can be overridden from a drop-down of that
element's types, and the override travels with the structure.

*Single point* gives the energy broken down by term, which is what
tells a strained crystal from a mistyped atom.  *Optimise* relaxes the
geometry on a worker thread: the structure moves in the viewport as it
goes, the energy and maximum force are plotted live, and Pause and Stop
work at every step.  Nothing reaches the undo stack until the run
finishes, and then one command does -- so `Ctrl+Z` gives back the
structure you started with, not the second-to-last iteration.

The relaxation keeps the space group. The variables are the sites of
the asymmetric unit rather than the atoms of the cell, so an atom on a
special position stays on it: rutile's titanium does not move at all,
and its oxygen relaxes along the [110] direction it is free in and
nowhere else. To relax every atom independently, *Reduce to P1* first.

`resources/samples/MFU4l.cif` (CCDC 776578) is a worked example: a
648-atom metal-organic framework in Fm-3m.  Its eight octahedral zincs
come out flagged, because UFF has only a tetrahedral zinc.

## What works today

From the command line:

```bash
xtal info quartz.cif
xtal symmetry quartz.cif --symprec 1e-3 --wyckoff
xtal bonds quartz.cif
xtal convert quartz.cif big.xyz --supercell 2 2 2 --p1
xtal types quartz.cif                       # atom types, and why
xtal energy quartz.cif                      # per-term breakdown
xtal optimize quartz.cif -o relaxed.cif     # a line per step
```

From Python:

```python
from xtal import Lattice, Structure
from xtal.commands import CommandStack, Host
from xtal.commands import cell as cell_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.commands import atoms as atom_commands
from xtal.core import bonding, measure, p1, properties, symmetry
from xtal.io import FORMATS, write_cif

quartz = FORMATS.read("quartz.cif")

print(properties.info(quartz).text())      # formula, Z, density, cell
print(symmetry.detect(quartz).summary())   # P3_221 (#154), 6 operations

flat = symmetry.reduce_to_p1(quartz)       # expand every orbit
back, report = symmetry.asymmetrize(flat)  # ... and find it again
assert back.space_group == quartz.space_group

graph = bonding.graph(quartz)              # 1.61 A Si-O tetrahedra
print(graph.coordination())
print([f.kind for f in graph.fragments()]) # 'framework'

write_cif(back, "quartz_out.cif")

cell = p1.expand(quartz)                   # minimum-image measurement
print(measure.measure(cell, quartz.lattice, [0, 3]).text())

host, stack = Host(quartz.copy()), CommandStack()   # undoable edits
stack.push(atom_commands.SetElement([0], "Ge"), host)
stack.undo(host)                                    # back to Si

big = cell_commands.Supercell(2, 2, 1)             # 36 atoms, P1
print(big.preview(host.structure)[1].message)      # ... before doing it
stack.push(big, host)
stack.push(symmetry_commands.FindSymmetry(1e-4), host)
stack.undo(host); stack.undo(host)                 # exactly as it was
```

Every symmetry and cell operation is a command that can say what it
would do before it does it, which is what the dialogs above them show.

The force field is the same shape:

```python
from xtal.ff import ENGINES, optimize
from xtal.core import p1

calculator = ENGINES.build("uff", quartz)   # types, bonds, terms: once
print(calculator.summary())                 # 9 atoms, 12 bonds, 24 angles...

result = calculator.compute(p1.expand(quartz).cart, quartz.lattice.matrix)
print(result.breakdown())                   # bond / angle / torsion / vdW
print(result.max_force)                     # kcal/mol/A

run = optimize.run(calculator, quartz, method="lbfgs")
print(run.summary())                        # converged after 8 steps: ...
print(run.frac)                             # the asymmetric unit, relaxed
```

`ENGINES` is a registry, so LAMMPS, GULP, xTB or a machine-learned
potential drop in as another `Calculator` and one registration line,
with no change to the optimiser, the worker thread or the panel.
Electrostatics are off by default, as in UFF itself; turned on, charges
come from the sites or from charge equilibration, and the lattice sum
is Ewald's (it reproduces the rock-salt Madelung constant to seven
figures, which is the test).

Reading a CIF gives you the asymmetric unit and its space group, held
as a Hall symbol so non-standard settings (origin choice 2,
rhombohedral axes) survive a round trip.  Every expanded atom knows
which site and which symmetry operation produced it, so an edit made to
a symmetry image can be mapped back onto its parent.

## Licence

MIT.
