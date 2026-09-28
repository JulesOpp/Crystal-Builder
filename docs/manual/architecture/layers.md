(architecture-layers)=
# The core and the shell

Crystal Builder is two Python packages with a wall between them: a
headless core, `xtal`, that holds everything crystallographic and
imports no Qt, and a shell, `xtalapp`, that is the PySide6 + VTK
window and holds no crystallography of its own.  After this page you
know which package a piece of behaviour lives in, what each folder
holds, and which test fails if the wall is breached.

```{index} single: architecture; core and shell
```
```{index} single: xtalapp (package)
```
```{index} single: headless core
```

## The rule

The core's own docstring states it: *the core is a headless library:
no Qt, no VTK, no display required; the desktop application lives in
`xtalapp`*.  The shell's docstring states the other half: *the window
owns documents and wires them to widgets; it holds no crystallography
of its own.  Anything it needs to know about a structure it asks the
Document, and anything it wants to change it asks the Document to
change.*

The consequences are the ones you meet as a user.  Everything the
window runs, the `xtal` command runs without it, into the same
{term}`workspace` and leaving the same files
({doc}`/workflows/cli`); the core can be imported in a notebook or on
a cluster node with no display ({doc}`/workflows/scripting`); and
more than half of the test suite runs without building a single
window ({doc}`testing`).  The dependency runs one way: `xtalapp`
imports `xtal` everywhere, and nothing under `xtal/` imports
`xtalapp` or a GUI toolkit.

The one place the two meet in the core is deliberately small.  A
command's *host* -- the thing it changes -- is "anything with a
mutable `structure` attribute: the Document in the application, a
one-line stand-in in the tests", and keeping it to that one attribute
"is what stops Qt from leaking into the core" (`xtal/commands/base.py`).
Where the shell has to hand the core an answer only it knows -- the
path a person typed into Preferences for an external program -- it
does so through a plain dictionary the core exposes for the purpose,
"exactly as a shell puts one in an environment variable"
(`xtal/modules/process.py`; see {doc}`plugins`).

## What each package holds

The table is drawn from the repository's `CLAUDE.md` and `README.md`
and from the tree itself.

**The core, `xtal/`**

```{tabularcolumns} \X{1}{3}\X{2}{3}
```

| Where | What it holds |
|---|---|
| `xtal/core/` | Structure, lattice, sites, space groups and symmetry operations, subgroups, the P1 expansion, neighbours, bonding (perception, bond orders, nets), supercells and transforms, measurement, properties, and `prepare.py`, the steps behind *Prepare for simulation* |
| `xtal/io/` | Reading and writing: CIF, the `.xtalproj` project file, POSCAR, pymatgen JSON, CSSR, DFTB+ `.gen`, extended XYZ and trajectories, and the format registry `FORMATS` that `xtal formats` prints ({doc}`/utilities/formats`) |
| `xtal/commands/` | The undoable operations: the command stack, and the atom, bond, cell, symmetry, connection-point and interpenetration commands and the clipboard fragment ({doc}`document`) |
| `xtal/ff/` | The `Calculator` API and the engine registry `ENGINES`; UFF and its typer and charges, the DFTB+, xTB, MACE, ORB and MatterSim engines, Ewald sums, the optimisers, constraints and the relaxed scan ({doc}`/energy/index`) |
| `xtal/modules/` | The module registry `MODULES`: what can be run, the job and its cancellation, the external-process runner, the report a run comes back with, and the modules themselves (Zeo++, the MOF, molecule and net builders, PXRD, the scan, the Blender export) |
| `xtal/analysis/` | Porosity from Zeo++'s output, nets as periodic graphs and their RCSR identification, net search, interpenetration, PXRD, k-paths, grids and isosurfaces |
| `xtal/mof/`, `xtal/build/` | PORMAKE frameworks -- PORMAKE is vendored at `xtal/mof/pormake/`, trimmed of jax, pymatgen and networkx, with its own `PROVENANCE.md` -- and SMILES to a molecule ({doc}`/frameworks/index`) |
| `xtal/workspace.py` | The workspace layout on disk and the {term}`run folder` a calculation leaves ({doc}`/workflows/workspaces`) |
| `xtal/params.py` | The `Param`, `Availability` and `Registry` declarations that modules and engines share ({doc}`registries`) |
| `xtal/plugins.py` | Entry-point discovery for registrations from outside the tree ({doc}`plugins`) |
| `xtal/cli.py` | The `xtal` command line |

**The shell, `xtalapp/`**

```{tabularcolumns} \X{1}{3}\X{2}{3}
```

| Where | What it holds |
|---|---|
| `xtalapp/main.py`, `application.py` | The `crystal-builder` entry point, the workspace chooser before the window, `--selftest` |
| `xtalapp/mainwindow.py` | The window: menus, toolbar, docks, tabs and status bar, with three mixins split out of it -- `shell_state.py` (refreshing and enabling), `symmetry_actions.py` (the Symmetry and Cell commands) and `edit_actions.py` (editing, selection, bonds, measurements) |
| `xtalapp/document.py` | `Document`: one open structure, its view state, its selection and its undo history ({doc}`document`) |
| `xtalapp/actions.py`, `menus.py` | The action registry, and the menus, toolbar, Modules menu and context menus built by reading it ({doc}`registries`) |
| `xtalapp/viewport/` | The 3D view: the scene model and builder, draw styles, view settings, the VTK widget and the mouse modes |
| `xtalapp/docks/` | The panels: Workspace and Structure trees, Modules, Info, Inspector, Sites, Move, Style, Measure, Net, Force Field, DFTB+, Results, Log, the trajectory transport bar |
| `xtalapp/dialogs/` | Every dialog, from *Add atom* to the MOF builder, Preferences, the generated module form and the Help window |
| `xtalapp/workers.py`, `module_runner.py` | Long jobs off the GUI thread: the worker and its thread, and the runner that gives a module its run folder, live log and Stop button |
| `xtalapp/plot.py`, `histogram.py`, `curve.py` | The optimisation trace, the pore-size distribution and the PXRD pattern, drawn with QPainter |
| `xtalapp/settings.py`, `external.py`, `extras.py` | Preferences; where the external programs are; which optional packages are present and how to get them |
| `xtalapp/selftest.py` | What `crystal-builder --selftest` checks ({doc}`testing`) |

## The test that enforces it

`tests/test_core_is_headless.py` is the guard, and its docstring
names the failure it prevents: "a stray convenience import quietly
making the library un-installable in CI, in a notebook, or on a
cluster node".  It has four tests:

1. **No forbidden import anywhere under `xtal/`.**  Every file is
   parsed with `ast` and its imports are checked against a set that
   names the GUI toolkits and the shell itself:

   ```python
   FORBIDDEN = {"PySide6", "PySide2", "PyQt5", "PyQt6", "qtpy", "tkinter",
                "wx", "vtk", "vtkmodules", "matplotlib", "pyqtgraph",
                "xtalapp"}
   ```

2. **`import xtal` loads none of them.**  A fresh interpreter imports
   the package and prints which of those names reached `sys.modules`;
   the answer must be `[]`.
3. **No module of the core does either.**  The same, but importing
   every module under `xtal/` one by one, because the top-level
   import reaches only four of them; a module whose optional extra is
   not installed is skipped, which "is the extra being optional, not
   the wall leaking".
4. **The wall holds in the other direction too.**  The shell may ask
   for a covalent radius in exactly two functions, both of which
   *draw* an atom that size; anywhere else it would be deciding what
   is bonded, which is the core's job.  The test lists the two and
   fails on a third.

The second check is one line you can run yourself; the
{doc}`scripting page </workflows/scripting>` shows it and its output.
The conventions the whole tree follows -- 79-column hand formatting,
`ruff check` and never `ruff format`, test names that are sentences,
a deprecation warning that fails the suite -- are in `CLAUDE.md` at
the root of the repository, which is the first thing to read before
changing anything.
