# Crystal Builder

A desktop application for building, manipulating, analysing and
exporting crystal structures.  The visual and interaction model follows
**VESTA**; the symmetry and force-field capability follows **Materials
Studio**.  Python throughout, shipped to macOS and Windows.

Status: **phase 7 complete** — the core, the headless CLI, and an
application you can build structures in: click to place atoms and draw
bonds, move and rotate the selection, copy and paste, find the symmetry
at a tolerance you choose, change the space group, build supercells and
edit the cell, draw coordination polyhedra, measure distances, angles,
torsions and the angle between least-squares planes, set a bond's type
by hand, save the whole session as a project, and now put a
**UFF** energy on a structure and relax it without leaving its space
group.  Next up is packaging.  See [docs/PLAN.md](docs/PLAN.md) for the
full architecture and roadmap, and [docs/TODO.md](docs/TODO.md) for
what is wanted but not yet scheduled.

---

## Layout

    xtal/       core library — no Qt, no VTK, importable anywhere
      core/     lattice, sites, space groups, structure,
                symmetry, P1 expansion, neighbours, bonding
                (perception, orders, nets), supercells, transforms,
                measurement, properties
      io/       CIF, extended XYZ (single frame and trajectory),
                CSSR (Zeo++), .gen (DFTB+) and .xtalproj projects,
                format registry
      workspace.py  the workspace layout and the run folders a
                calculation leaves behind
      params.py the parameter and availability declarations that
                modules and engines share
      modules/  the module registry: what can be run, the job and
                its cancellation, the external-process runner, the
                report a run comes back with, and Zeo++
      plugins.py  entry-point discovery for out-of-tree registrations
      cli.py    the `xtal` command line
      commands/ undoable mutations: the stack, atom/bond/cell/
                symmetry commands, the clipboard fragment
      ff/       the Calculator API and engine registry, Ewald
                sums, FIRE and L-BFGS optimisers
        uff/    UFF: parameter table, atom typer, energy terms,
                calculator, QEq charges
        dftb/   DFTB+: HSD input, Slater-Koster check, calculator
      analysis/ porosity (Zeo++ output), later RDF and PXRD
    xtalapp/    the PySide6 + VTK application
      viewport/ scene model, builder, draw styles, VTK, the widget
      docks/    workspace tree, module tree, inspector, sites, style,
                measure, force field, results, log viewer,
                transport bar
      dialogs/  add atom, hydrogens, bond rules, cell, export,
                symmetry, supercell, a module's parameters, and the
                window that says a run is going
      document.py, mainwindow.py, actions.py, settings.py
      workers.py, plot.py, histogram.py   long jobs off the GUI
                thread, and the two plots they produce
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

## Optional features

Three features are gated on a package the core does not install.  Each
greys its own menu entry out and names the extra, and
*Preferences ▸ Optional features* lists all three with what they power
and what to type:

| Extra | Package | What it buys |
|---|---|---|
| `build` | RDKit | *Insert molecule* — build from a SMILES string, and the fragment library |
| `sketch` | rdeditor | Draw the molecule instead of typing it |
| `mof` | PORMAKE | The MOF builder: a framework from a net, a node and a linker |

```bash
pip install 'crystal-builder[gui,build,sketch]'
pip install 'crystal-builder[gui,mof]'      # the MOF builder as well
```

`mof` is its own line because it is not a small ask: `pip install
pormake` pulls in 44 packages and about 889 MB — jax and pymatgen
among them — against the four the core installs.  Net identification
and the `.cgd` reader are this project's own and work without it.

### In a packaged build

A frozen `.app` or `.exe` has no environment to install into: the
Python inside it is not on your PATH and has no pip.  So the build
carries RDKit and rdeditor — both features work with nothing to do —
and **does not carry PORMAKE**, which is larger than the rest of the
application put together.

If you want the MOF builder, run Crystal Builder from Python:

```bash
pip install 'crystal-builder[gui,mof]'
crystal-builder
```

That is the supported route and it is what *Preferences ▸ Optional
features* recommends.  There is a second one on that page: the
application puts a user-writable folder — `~/Library/Application
Support/CrystalBuilder/packages`, `%APPDATA%\CrystalBuilder\packages`
on Windows — first on its import path at start-up, so

```bash
pip install --target "<that folder>" <package>
```

makes a package importable inside the packaged build.  It works for a
package that is pure Python.  It is **not** reliable for PORMAKE:
those dependencies are compiled, they have to match the build's exact
Python version and ABI, and their numpy would collide with the one
already in the bundle.  The folder exists because it is the only way a
frozen build can be given a package at all — a plugin installed with
pip registers an entry point that a bundle cannot see.

## Running the application

```bash
crystal-builder                 # or: python -m xtalapp.main
crystal-builder quartz.cif
```

Open a CIF from the file tree on the left or by dropping it on the
window.  Left-drag orbits, the wheel zooms, middle-drag pans.  The
*View* menu switches between ball-and-stick, stick, wireframe,
space-filling, polyhedral and thermal-ellipsoid pictures; the toolbar
spinboxes set how many unit cells are drawn.

Click an atom or a bond to select it, shift-click to add to the
selection, double-click for the whole molecule or framework.  *Box
select* drags a rectangle and takes everything inside it, front to
back -- the fastest way to grab a slab or one end of a long molecule.
The *Select* menu grows a selection by element, by bonded neighbours,
by fragment or by symmetry orbit.  The Inspector edits the selected site
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
fractional or cartesian units; the arrows beside each step nudge and
auto-repeat while held, and a whole burst of them comes back on one
`Ctrl+Z`.  *Make planar* flattens the selection onto its best-fit
plane and says how far the furthest atom had to move, which is the
difference between straightening a puckered ring and quietly rebuilding
it.  Everything is undoable (`Ctrl+Z` /
`Ctrl+Shift+Z`), and copy/paste works through the system clipboard as
XYZ, so fragments travel to and from other programs.

*Structure → Add hydrogens* puts back the ones an X-ray refinement
never saw.  Where they go is the coordination completed -- the
hybridisation the force field's typer already decided, so a benzene
carbon gets one in the ring plane and a methyl gets three, staggered --
and how far is the bond length UFF itself would relax to.  It says
what it will do before it does it, and it counts in atoms rather than
in sites: "6 hydrogens on 2 atoms (4 sites in the asymmetric unit)",
because two hydrogens either side of a mirror plane are one site.
A metal is left alone, and so is anything else it would have to guess
at -- and it says which.

**Set Bond Type is what overrules it.**  The hybridisation is read from
the geometry, which is the only evidence there is until somebody says
otherwise; a carbon whose two bonds you have called single is sp3
whether the model has them drawn at 109 degrees or at 180, and it gets
the two hydrogens its valence is short.  A ring with every bond called
single builds cyclohexane where the same ring untouched builds
benzene.  One statement among several is not enough -- an atom is
retyped only when *every* bond at it is stated, because one stated bond
says nothing about the total -- and a statement that contradicts the
coordination, four neighbours and a double bond, is left where it
belongs.

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

*Descend to a subgroup* goes the other way, and it is a choice rather
than a measurement: it lists the subgroups of the group you are in, and
each one splits a different orbit into independent sites -- the first
step of a distortion model.  Not only the maximal ones, because an
ordering model usually knows the group it is heading for and should not
have to walk there through three dialogs; the maximal ones are marked
so the step-by-step path is still visible.  Subgroups that differ only
in which axis they keep are conjugate under the parent and give the
same crystal, so they share one row that says how many it stands for.

The list says what each descent costs, because most of them cost
nothing visible: six of rutile's seven maximal subgroups leave both its
sites whole, and the seventh, Cmmm, halves both.  Every subgroup is
named in a standard setting, including the ones whose operations do not
match any tabulated setting of the cell you are in; where a descent
needs the cell re-expressed, it says so, the crystal itself does not
move, and the view resets so the new cell is framed rather than the old
one.

*Invert the structure* is the other hand of the same crystal --
coordinates and space group together, since doing only the first
leaves atoms that no longer obey their own symmetry.  P4_1 comes back
as P4_3.  The Structure panel says which hand you are in at all times,
which is what makes anyone think to check: a structure solved in the
wrong hand looks perfectly good.

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
translucent convex hulls, coloured by the atom at the centre -- and
**Polyhedra and sticks** draws hulls on the metal nodes and tubes on
everything else, which is the picture an MOF wants.  **Thermal
ellipsoids** draws the displacement parameters of a refined structure
at 50%, 90% or 99% probability; an atom refined only isotropically is
a sphere and one with no displacement parameters at all is a small
sphere that does not grow with the level, so the picture never claims
a measurement nobody made.  **Depth cueing** fades the back of a thick
slab towards the background.

Double and triple bonds are drawn as two and three tubes, and an
aromatic bond as a tube with a dashed line inside the ring -- inferred
from the geometry by `xtal.core.bonding`, which is also where the force
field now gets its bond orders.  Where the geometry is not qualified to
decide -- 1.39 A between two carbons is aromatic in benzene and a
stretched double bond in an unrelaxed model -- **Set Bond Type**
overrules it: right-click a bond, or use *Structure -> Set Bond Type*,
and call it single, double, triple or aromatic, or *Automatic* to take
the statement back and let the inference decide again.  A stated order
is stored against the asymmetric unit like every other bond edit, so
setting one C-O of an acetate sets the other, and it is saved with the
project.  It reaches the force field's atom typing, and through that
*Add hydrogens* -- see above.

An edit over a selection is **one** edit: Select All on MFU-4l names
848 bonds, and setting their type is a single command, a single change
to the structure and a single redraw -- not 848 of each -- so it is one
`Ctrl+Z` and takes about a second rather than half a minute.

The commands that name a **region** take the bonds inside it as well as
the atoms: *Select All*, the box, *Invert* and the three *Grow*
commands, so "select the linker, call its bonds aromatic" is one
gesture rather than eleven clicks.  A bond with one end outside the
region is not in it.  Clicking an atom, selecting by element or picking
a row in a table names atoms and leaves the bonds alone, because there
a bond that quietly joined the selection would be edited by the next
command without ever having been asked for.  A **topology bond** is a different
kind of thing: an edge of the underlying net, drawn thick and
translucent over the real bonds rather than in place of them, invisible
to every chemical question, and reported by its coordination sequence
and point symbol -- 6, 18, 38, 66 and 4^12.6^3 for **pcu**.  The
*Measure* tool takes distances, angles and torsions; how many atoms you
click is the whole of the choice between them, and every measurement is
minimum-image aware, so one taken across the cell boundary follows the
bond rather than the long way round the box.  **Planes** are made from
the selection instead of from a run of clicks, because nobody picks
exactly three atoms of a phenyl ring: three atoms determine a plane and
more are fitted by least squares, with the RMS deviation reported
beside it -- 0.00 A for a flat ring and 0.11 A for one that is not,
which is the difference between a plane and a number dressed up as one.
*Measure -> Angle between planes* then measures between them, one angle
per pair, and a plane is re-fitted from its own atoms whenever they
move, so an interplanar angle after a relaxation is the angle the
molecule now has.

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

**The *Modules* menu is what can be run**, and so is the module tree
beside the workspace tree -- one panel to pick a calculation from, the
other to watch its folder appear underneath the structure.  Both are
built from a registry (`xtal/modules/`), so a module declares its name,
its place in the tree, the parameters it needs and the callable that
runs them, and gets its menu entry, its parameter form, its worker
thread, its run folder, its live log and its Stop button without
writing any of them.  A module installed from another package
registers through a `crystal_builder.plugins` entry point and appears
in both, with no file here changing.  Everything external goes through
one process runner: a binary that is not installed greys its module out
and says so before anybody clicks it, its output streams into `run.log`
as it arrives, Stop terminates the process group rather than abandoning
the thread reading it, and a non-zero exit is reported with the last
thing the program printed, which is nearly always what actually went
wrong.

Under *Modules → Forcefield* are the three entries that used to be
*Calculate*, unchanged, with `Ctrl+E` and `Ctrl+Shift+E` still on them.
The **Force Field** panel leads with the thing that decides whether an
energy means anything: a table of every site's UFF atom type, that
type in words (`Zn3+2` is "tetrahedral Zn(II)", and the `3` of `O_3`
is sp3 rather than tetrahedral -- the same character means two
different things and the panel used to say neither), how sure the
typer was, and the sentence explaining why it chose that one --
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

*Relax the cell as well* adds the lattice to the variables, under a
strain the space group allows -- so a cubic cell comes back cubic and
a hexagonal one hexagonal, exactly, because there is no variable that
could take them anywhere else.  An external pressure is a `P V` term
beside it, in GPa.  What comes out is a UFF cell: for a framework it
is routinely a few percent out (MFU-4l relaxes from 31.06 A to 30.30),
which is a starting geometry and not a measured lattice constant, and
the panel says so.

`resources/samples/MFU4l.cif` (CCDC 776578) is a worked example: a
648-atom metal-organic framework in Fm-3m.  Its eight octahedral zincs
come out flagged, because UFF has only a tetrahedral zinc.

## What works today

From the command line:

```bash
xtal info quartz.cif
xtal symmetry quartz.cif --symprec 1e-3 --wyckoff
xtal symmetry quartz.cif --subgroups        # ... and what splits
xtal bonds quartz.cif
xtal convert quartz.cif big.xyz --supercell 2 2 2 --p1
xtal types quartz.cif                       # atom types, and why
xtal energy quartz.cif                      # per-term breakdown
xtal optimize quartz.cif -o relaxed.cif     # a line per step
xtal optimize quartz.cif --relax-cell       # ... the lattice too
xtal modules                                # what can be run
xtal run stub.count quartz.cif -p steps=3   # ... and running it
xtal run zeopp.diameters MOF.cif            # D_i, D_f and D_if
xtal run zeopp.surface-area MOF.cif         # ... to nitrogen
xtal run zeopp.psd MOF.cif -p samples=50000 # ... and the spread
```

The Zeo++ entries need the `network` binary — on PATH, named by
`XTAL_ZEOPP`, or built in `resources/zeo++-0.3/`.  A run that takes
more than a moment puts up a window saying so, with the elapsed time,
the last line the binary printed and Stop; the pore size distribution
leaves its plot in the run folder as a PNG beside the numbers.  DFTB+ is reached
the other way, as an *engine* rather than a module, so that the
optimiser, the symmetry projection and the panel drive it exactly as
they drive UFF:

```bash
conda install 'dftbplus=*=nompi_*' -c conda-forge
export DFTB_PREFIX=/where/you/unpacked/3ob-3-1/
xtal optimize MOF.cif --engine dftb
```

Its Slater-Koster parameter files are a separate download from
dftb.org, and every element pair present is checked against them
*before* anything is launched — a missing pair is named here rather
than several seconds into a subprocess.

`xtal run` writes the same run folder the window does, which is what
makes a run started from a script one the window opens.

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
with no change to the optimiser, the worker thread or the panel.  So is
`MODULES`, for anything that runs and leaves artefacts behind rather
than answering with an energy:

```python
from xtal.modules import MODULES, Action, Module, Param

MODULES.register(Module(
    name="zeopp", label="Zeo++",
    check=lambda: NETWORK.availability(),        # greyed out if absent
    actions=(Action(name="pore-diameter", label="Pore diameter...",
                    params=(Param("radii", "Radii file", kind="path"),),
                    run=zeo.pore_diameter),)))
```

An engine declares the same `Param` objects (`Engine.options`) and gets
the same generated form, which is how DFTB+'s Hamiltonian, parameter
set, k-point mesh and filling temperature reached the Force Field panel
without the panel learning any of those words.  A run that answers with
more than a sentence returns a `Report` of tables and histograms, which
the Results panel draws and the run log prints:

```python
from xtal.analysis import porosity
from xtal.modules import MODULES, Job

module, action = MODULES.find("zeopp.psd")
result = action.run(Job(structure=mof, params=action.defaults()))
print(result.report.as_text())              # the table and the bars
```
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
