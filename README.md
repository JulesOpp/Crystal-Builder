# Crystal Builder

A desktop application for building, manipulating, analysing and
exporting crystal structures.  The visual and interaction model follows
**VESTA**; the symmetry and force-field capability follows **Materials
Studio**.  Python throughout, shipped to macOS and Windows.

Status: **phase 0** — the crystallography core is taking shape.  See
[docs/PLAN.md](docs/PLAN.md) for the full architecture and roadmap.

---

## Layout

    xtal/       core library — no Qt, no VTK, importable anywhere
      core/     lattice, sites, space groups, structure
      io/       CIF and other formats            (phase 1)
      commands/ undoable mutations               (phase 4)
      ff/       UFF force field                  (phase 7)
      analysis/ RDF, coordination, later PXRD    (phase 6+)
    xtalapp/    the PySide6 + VTK application    (phase 2+)
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

## What works today

```python
from xtal import Lattice, Structure

nacl = Structure.from_arrays(
    Lattice.cubic(5.64), ["Na", "Cl"],
    [[0, 0, 0], [0.5, 0.5, 0.5]], space_group="Fm-3m")

nacl.ensure_labels()
print(nacl)                      # Structure(Cl1Na1, Fm-3m, 2 sites, ...)
print(nacl.space_group.order)    # 192 operations
print(nacl.lattice.d_spacing((2, 0, 0)))
```

## Licence

MIT.
