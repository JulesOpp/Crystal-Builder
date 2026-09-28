(workflows-scripting)=
# Using the core from Python

The `xtal` package is a headless library -- no Qt, no VTK, no display
-- and everything the command line does, it does by calling it.  After
this page you can read and write structures, prepare a deposited CIF,
run an engine for a single point or a relaxation, and run a module
action, from a script of your own, using the same entry points
`xtal/cli.py` uses.

```{index} single: Python; scripting the core
```
```{index} single: xtal (package)
```

:::{warning}
**This is not a stable API.**  No document in the repository promises
that these names, signatures or return types will stay as they are
between releases, and this manual does not either.  What is shown
here is what the command line itself calls, which is the most likely
to survive; pin the version you script against, and prefer the
{doc}`command line <cli>` for anything that has to keep working.
:::

## What you can import

`xtal` imports no Qt.  The check is one line, and it is what keeps the
core testable without a display:

```console
$ python -c "import sys, xtal, xtal.io, xtal.ff, xtal.core.prepare, xtal.workspace, xtal.modules.report; print(sorted(m for m in sys.modules if 'PySide' in m or m.startswith('vtk')))"
[]
```

The package's own top level exports `Structure`, `Lattice`, `Site`,
`SpaceGroup`, `SymOp`, `Bond`, `Change` and `__version__`; the entry
points below live one level down.  Every snippet on this page was run
from a folder containing the `ws` workspace of the {doc}`workspaces
page <workspaces>` and a `resources` link to the repository's
samples, and the output under each is what it printed.

## Reading and writing structures

`xtal.io.FORMATS` is the registry `xtal formats` prints.  It reads by
extension and writes by extension, and iterating it lists what it
knows:

```python
from xtal.io import FORMATS

print([fmt.name for fmt in FORMATS])
structure = FORMATS.read("resources/samples/prepared/MIL-53.cif")
print(structure)
print(structure.n_sites, structure.elements, structure.space_group)
print(structure.lattice.parameters)
FORMATS.write(structure, "MIL-53.poscar")
print(FORMATS.by_extension("MIL-53.poscar").name)
```

```text
['cif', 'xtalproj', 'poscar', 'pmg-json', 'cssr', 'gen', 'xyz']
Structure(C16Cr2H10O10, P1, 38 sites, V=754.77 A^3)
38 ['O', 'C', 'Cr', 'H'] SpaceGroup(P1 #1)
(np.float64(11.191207), np.float64(11.191207000000002), np.float64(11.191207000000002), 82.9338, 108.0699, 144.3742)
poscar
```

`n_sites` counts the asymmetric unit, not the atoms in the cell; for
a P1 file the two are the same.  `FORMATS.read_all` reads every block
of a multi-block file, and `FORMATS.write(structure, path, fmt)` names
the format explicitly when the extension does not.

## Preparing a deposited CIF

`xtal.core.prepare` is what `xtal prepare` and *Prepare for
simulation* run ({doc}`the steps </structure/prepare>`).  `diagnose`
says what `prepare` would change without changing it; `prepare`
returns the new structure and one sentence per step:

```python
from xtal.core.prepare import diagnose, prepare
from xtal.io import FORMATS

deposited = FORMATS.read("resources/samples/cod/MOF-5.cif")
print(diagnose(deposited).text())
prepared, said = prepare(deposited)
for line in said:
    print(line)
print(deposited.n_sites, "sites ->", prepared.n_sites, "sites")
FORMATS.write(prepared, "MOF-5-prepared.cif")
```

```text
- the cell is F-centred, 4 times the primitive one (424 atoms against 106)
no site written twice
no deuterium
primitive cell of the F-centred lattice: 106 atoms, from 424
nothing is disordered
no solvent molecules
no hydrogens to add
7 sites -> 106 sites
```

The deposited file has 7 sites in Fm-3m and 424 atoms in its cell;
the prepared one is the primitive cell written in P1, 106 sites and
106 atoms.  `prepare(structure, steps=...)` takes the same step names
as `--steps`; the default runs every step but `cap`, which changes the
chemistry and is only run when named.

## An engine and a single point

`xtal.ff.ENGINES` is the registry `xtal engines` prints.  An engine
is built for one structure with its options as keyword arguments;
the calculator it returns computes an energy, forces and, where the
engine can, a stress, for cartesian positions of the P1 cell and the
lattice matrix.  This is `xtal energy`, line for line:

```python
from xtal.core import p1
from xtal.ff import ENGINES
from xtal.io import FORMATS

structure = FORMATS.read("resources/samples/prepared/MOF-5.cif")
engine = ENGINES.get("uff")
print(engine.defaults())
print(engine.availability())
calculator = engine(structure, **engine.defaults())
print(calculator.summary())
cell = p1.expand(structure)
result = calculator.compute(cell.cart, structure.lattice.matrix)
print(result.breakdown())
print(f"max force {result.max_force:.5f} kcal/mol/A")
print(result.forces.shape, result.stress.shape)
```

```text
{'parameter_set': 'uff4mof', 'coulomb': False, 'charges': 'site', 'vdw_cutoff': 12.0, 'skin': 2.0}
Availability(ok=True, reason='')
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions
torsion            646.7626
angle              330.0816
bond               259.6529
van der Waals      118.6581
inversion            0.0000
total             1355.1552
max force 110.00889 kcal/mol/A
(106, 3) (3, 3)
```

- `engine.defaults()` are the values `xtal engines` shows; pass any
  subset to override them (`engine(structure, coulomb=True,
  charges="eqeq")`), and `engine.coerce(...)` turns strings into the
  typed values, which is how `-p` gets in.
- `engine.availability(**options)` is the check the panel greys an
  entry out with; ask it before building, because for an external
  engine half of what makes it available is in the options.
- `ENGINES.build("uff", structure, **options)` is the same call in
  one step.
- `Result.energy` is in kcal/mol, `forces` an (N, 3) array in
  kcal/mol/Å, `stress` a 3×3 array in kcal/mol/Å³ or `None`, and
  `terms` the per-term breakdown `breakdown()` prints.
- The calculator's `warnings` are what the command prints as
  `warning:` lines (the EQeq caution, for example).

## A relaxation

`xtal.ff.optimize.run` is `xtal optimize` and the Force Field panel's
**Optimise geometry**: it takes the calculator and the structure, the
optimiser's name and the keyword options the command's flags map to
(`max_steps`, `force_tolerance`, `stress_tolerance`, `relax_cell`,
`pressure`), and an optional `callback(step)` that is called after
every step and may return `False` to stop early.  Which optimiser to
choose is {doc}`optimisation </structure/optimisation>`.

```python
from xtal.ff import ENGINES, optimize
from xtal.io import FORMATS

structure = FORMATS.read("resources/samples/prepared/MIL-53.cif")
calculator = ENGINES.build("uff", structure)
result = optimize.run(calculator, structure, method="smart",
                      max_steps=50, force_tolerance=0.05)
print(result.converged)
print(result.summary())
```

```text
False
stopped without converging after 50 steps: -185.5120 kcal/mol to 399.6829, |F|max 0.1538 kcal/mol/A
```

Fifty steps were not enough here (the command-line run of the same
structure converged in 266).  `run` does not move the structure it
was given: the relaxed fractional coordinates are `result.frac` and
the relaxed cell, when the cell was free, `result.matrix`, which the
command copies back onto the structure before writing `-o`.

## A module action

The module registry is what `xtal run` and the *Modules* panel share.
`MODULES.find("module.action")` gives the module and the action;
`action.coerce` types the parameters as `-p` would; and the action is
run with a `Job` that carries the structure, the parameters and,
optionally, a run folder.  Without a folder the run leaves nothing on
disk, which is normal rather than an error:

```python
from xtal import plugins
from xtal.io import FORMATS
from xtal.modules import MODULES, Job

plugins.load()
structure = FORMATS.read("resources/samples/prepared/MIL-53.cif")
module, action = MODULES.find("pxrd.simulate")
params = action.coerce({"two_theta_max": "20"})
result = action.run(Job(structure=structure, params=params,
                        label="pxrd.simulate"))
print(result.ok)
print(result.summary())
print(result.report.tables[0].as_text()[:400])
```

```text
True
20 reflections between 5 and 20.01 deg, strongest (0 0 1) at 8.540 deg
Reflections (20)
No.  hkl       d (Å)    2θ (°)  I (%)
  1  (0 0 1)   10.3460   8.540  100.00
  2  (1 -1 0)  10.3460   8.540   99.99
  3  (-1 1 1)   8.3860  10.541    5.02
  4  (1 -1 1)   6.5725  13.461    0.62
  5  (0 1 0)    6.3391  13.959    0.00
  6  (1 0 -1)   6.3391  13.959    0.00
  7  (1 0 0)    6.0726  14.575    7.52
  8  (0 1 -1)   6.0726  14.575    7.52
  9  (0 0 2)    5.1730  17.127   
```

To file the run as `--workspace` does, open a run folder on the
structure's entry with `xtal.modules.record` before running and
close it after -- the two functions the window's worker and the
command both use, so that the folder, the log and its header are the
ones the {doc}`previous page <reports>` describes:

```python
from xtal import plugins
from xtal.io import FORMATS
from xtal.modules import MODULES, Job
from xtal.modules import record
from xtal.workspace import Workspace

plugins.load()
path = "resources/samples/prepared/MIL-53.cif"
structure = FORMATS.read(path)
module, action = MODULES.find("pxrd.simulate")
params = action.coerce({"two_theta_max": "20"})
workspace = Workspace.create("ws")
entry = workspace.add_structure(path)
folder = record.open_run(entry, module, action, params, structure)
result = action.run(Job(structure=structure, params=params,
                        folder=folder, label="pxrd.simulate"))
record.close_run(folder, result)
print(result.ok, result.summary())
print(folder.path)
```

```text
True 20 reflections between 5 and 20.01 deg, strongest (0 0 1) at 8.540 deg
ws/MIL-53/pxrd-pxrd-005
```

`Workspace.create` makes the workspace or adopts a directory that
already is one; `add_structure` copies the file in, or finds the entry
that already holds an identical copy ({doc}`de-duplication
<workspaces>`); and `record.close_run` writes the *Result* block and
the `finished` line whether the run succeeded, failed or was stopped.
`plugins.load()` registers anything a package installed *beside*
Crystal Builder declares through the `crystal_builder.plugins` entry
point; the in-tree modules register themselves on import.  The
command calls it before `MODULES.find`, and a second call is free.

A module that builds a structure rather than reading one (`mof.build`,
`build.molecule`, `net.draw`) is run with `structure=None`, and its
result's `structure` is the thing built; filing it as the window does
is `workspace.adopt_build(result.structure, run=folder.path,
artifacts=result.artifacts)`, which the command does for you.
