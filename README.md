# Crystal Builder

A desktop application for building, manipulating, analysing and
exporting crystal structures.  The visual and interaction model follows
**VESTA**; the symmetry and force-field capability follows **Materials
Studio**.  Python throughout, shipped to macOS and Windows.

Status: **phase 5 complete** — the core, the headless CLI, and an
application you can build structures in: click to place atoms and draw
bonds, move and rotate the selection, copy and paste, find the symmetry
at a tolerance you choose, change the space group, build supercells and
edit the cell, and undo all of it.  Next up is appearance and analysis.
See [docs/PLAN.md](docs/PLAN.md) for the full architecture and roadmap,
and [docs/TODO.md](docs/TODO.md) for what is wanted but not yet
scheduled.

---

## Layout

    xtal/       core library — no Qt, no VTK, importable anywhere
      core/     lattice, sites, space groups, structure,
                symmetry, P1 expansion, neighbours, bonding,
                supercells, properties
      io/       CIF and extended XYZ, format registry
      cli.py    the `xtal` command line
      commands/ undoable mutations: the stack, atom/bond/cell/
                symmetry commands, the clipboard fragment
      ff/       UFF force field                  (phase 7)
      analysis/ RDF, coordination, later PXRD    (phase 6+)
    xtalapp/    the PySide6 + VTK application
      viewport/ scene model, builder, draw styles, VTK, the widget
      docks/    file tree, structure information
      document.py, mainwindow.py, actions.py, settings.py
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
gemmi, spglib).  The `[gui]` extra adds PySide6, VTK and pyqtgraph.

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

The *Cell* menu edits the cell itself: parameters (keeping either the
fractional or the cartesian coordinates -- it asks, because the two
mean opposite things), supercells as multiples or as a general integer
matrix, and Niggli and Delaunay reduction.  *View → Display range*
controls how much of the crystal is drawn, and whether bonds at the
edge are completed with the atoms just outside.

`resources/samples/MFU4l.cif` (CCDC 776578) is a worked example: a
648-atom metal-organic framework in Fm-3m.

## What works today

From the command line:

```bash
xtal info quartz.cif
xtal symmetry quartz.cif --symprec 1e-3 --wyckoff
xtal bonds quartz.cif
xtal convert quartz.cif big.xyz --supercell 2 2 2 --p1
```

From Python:

```python
from xtal import Lattice, Structure
from xtal.commands import CommandStack, Host
from xtal.commands import cell as cell_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.commands import atoms as atom_commands
from xtal.core import bonding, properties, symmetry
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

Reading a CIF gives you the asymmetric unit and its space group, held
as a Hall symbol so non-standard settings (origin choice 2,
rhombohedral axes) survive a round trip.  Every expanded atom knows
which site and which symmetry operation produced it, so an edit made to
a symmetry image can be mapped back onto its parent.

## Licence

MIT.
