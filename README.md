# Crystal Builder

A desktop application for building, manipulating, analysing and
exporting crystal structures.  The visual and interaction model follows
**VESTA**; the symmetry and force-field capability follows **Materials
Studio**.  Python throughout, shipped to macOS and Windows.

Status: **phase 2 complete** — the crystallography core, the headless
CLI, and a PySide6 + VTK application that opens a CIF and draws it.
Next up is picking and inspection.  See [docs/PLAN.md](docs/PLAN.md)
for the full architecture and roadmap.

---

## Layout

    xtal/       core library — no Qt, no VTK, importable anywhere
      core/     lattice, sites, space groups, structure,
                symmetry, P1 expansion, neighbours, bonding,
                supercells, properties
      io/       CIF and extended XYZ, format registry
      cli.py    the `xtal` command line
      commands/ undoable mutations               (phase 4)
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
```

Reading a CIF gives you the asymmetric unit and its space group, held
as a Hall symbol so non-standard settings (origin choice 2,
rhombohedral axes) survive a round trip.  Every expanded atom knows
which site and which symmetry operation produced it, so an edit made to
a symmetry image can be mapped back onto its parent.

## Licence

MIT.
