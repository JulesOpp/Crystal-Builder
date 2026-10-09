# Performance and resource usage

> **Written 2026-09-18** against `Crystal-Builder` at commit `3cd15e2` (v0.2.1), the base of branch `features/deep-review`. `origin/main` has since moved to `fb38d25`. Line numbers, measurements and code references below were true at `3cd15e2` — re-verify before acting on one if the file has changed since.


**This machine has 8 GB of RAM, not 16** (`sysctl hw.memsize` =
8589934592; `hw.ncpu` = 8). That single fact explains most of the 819 s
vs 332 s swing: at the moment of measuring, 1.67 GB was wired and the
compressor held **19.9 GB of compressed anonymous memory in 3.20 GB of
physical pages**, leaving roughly 3 GB for everything running.

**The application itself is not the problem.** The headless core is
fast and properly vectorised (a UFF energy+force on 1152 atoms is 823
Python calls), the viewport uses glyph mappers and holds a constant 19
actors whether it draws 648 atoms or 5184, and `rdkit`, `matplotlib`
and `ase` are all function-level imports. Startup is 2.0 s and 211 MB
empty, 2.6 s and 372 MB with MFU-4l.

**What is slow is a small number of accidentally-quadratic paths**, all
in `xtal/core`, all reachable by clicking: `Structure.add_bond` is
O(n²) with a numpy matmul in the comparison (3200 bonds = 29.8 s),
`SpaceGroup._build_inverses` is O(ops²) `np.allclose` and cached
per-instance (177 ms every time an Fm-3m group object is made), and
`bonding._find_atom` is a linear scan over the whole cell.

Consequences a user sees on MFU-4l: **Set Bond Type over the selection
freezes the main thread for 0.72 s** (3.14 s on Ni2Cl2BTDD),
**Supercell 2×2×2 for 1.18 s**, **Reduce to P1 for 0.46 s**, and
**opening a 21 KB `.xtalproj` takes 2.10 s**. There is exactly one
`setOverrideCursor` in all of `xtalapp/`, so none of these shows a busy
cursor.

The suite is **memory-bound, not CPU-bound**: 481 tests in 46.8 s wall
against 35.5 s of CPU, peak RSS 497 MB, and RSS oscillates rather than
growing — the `pytest_runtest_teardown` fix holds.

---

# Every measurement

Swap was recorded before each run (`sysctl vm.swapusage`); it sat
between 5.67 and 6.30 GB used of 7.17 GB throughout, so these numbers
are all from one regime. `pgrep -fl "pytest|drive.py"` was empty before
each. All probes are under `review/probes/perf/`.

## Startup — the real window (`drive.py --scratch … --eval 'print("open")'` under `/usr/bin/time -l`)

`review/probes/perf/startup.sh`, fresh `--scratch` per case so a
remembered tab does not inflate the next.

| case | asym sites | P1 atoms | wall s | max RSS MB |
|---|---:|---:|---:|---:|
| no file | – | – | **2.02** | **211** |
| MOF-5 | 424 | 424 | 3.02 | 321 |
| MFU4l | 10 | 648 | 2.59 | 372 |
| Ni2Cl2BTDD | 40 | 1152 | 2.79 | 420 |
| CFA1 | 43 | 242 | 2.43 | 320 |
| `crystal-builder --selftest` (opens MOF-5, builds a MOF) | – | – | 4.62 | 373 |

## Imports (`review/probes/perf/imports.py`, min of 3 subprocesses)

| module | s | note |
|---|---:|---|
| `xtalapp.main` | **0.024** | the entry point imports almost nothing — deliberate, and right |
| `xtalapp.mainwindow` | 0.367 | |
| `xtalapp.viewport.widget` | 0.472 | this is the one that pulls VTK |
| `xtal` | 0.082 | |
| `xtal.core.bonding` | 0.197 | |
| `scipy.spatial` | 0.178 | pulled by `xtal.core.neighbors` |
| `vtkmodules.vtkRenderingOpenGL2` | 0.188 | |
| `PySide6.QtWidgets` | 0.082 | |
| `spglib` | 0.058 | |
| `numpy` | 0.052 | |
| `rdkit.Chem` | 0.126 | **never imported at module level** |
| `matplotlib.pyplot` | 0.259 | **never imported at module level** |
| `ase` | 0.054 | **never imported at module level** |

`review/probes/perf/importtime.txt`, top of the cumulative ranking for
`import xtalapp.mainwindow` (451 ms total):

```
451 ms  xtalapp.mainwindow
 161      xtal.commands.bonds -> xtal.core.bonding -> xtal.core.neighbors
 157        scipy.spatial          (124 scipy.spatial._kdtree, 64 _ckdtree, 58 distance)
  86      xtal.build
  55      PySide6.QtCore
  49        spglib
  47      xtal.ff.dftb
  39      numpy
```

So of the 0.45 s, **0.16 s is scipy.spatial** (one KD-tree), 0.05 s
PySide6.QtCore, 0.05 s spglib. Nothing heavy is eagerly imported.

## The headless core (`review/probes/perf/hotops.py`, `core_mem.py`)

Base process after `import numpy, xtal, xtal.io, xtal.core, xtal.ff` is
**63 MB**; 11 MB of that is numpy + xtal, 29 MB is scipy + spglib.

| operation | MFU4l (648 at, 848 bonds) | Ni2Cl2BTDD (1152 at, 6786 bonds) | thread |
|---|---:|---:|---|
| `FORMATS.read` | 0.009 s | 0.002 s | main |
| `p1.expand` | 0.012 s | 0.004 s | main |
| `p1.expand` (memoised) | 0.000 s | 0.000 s | main |
| `symmetry.detect` | 0.012 s | *fails*¹ | main |
| `symmetry.reduce_to_p1` (no stored bonds) | 0.002 s | 0.004 s | main |
| `symmetry.asymmetrize` | 0.024 s | *fails*¹ | main |
| `bonding.graph` | 0.011 s | 0.189 s | main |
| `bonding.perceive` (cold structure) | 0.023 s | 0.067 s | main |
| `bonding.orders` (bond orders, rings) | 0.063 s | 0.115 s | main |
| `supercell(2,2,2)` core fn | 0.018 s | 0.057 s | main |
| `Supercell(2,2,2).apply_to` | 0.030 s | 0.057 s | main |
| `bonding.perceive` on the supercell | 0.082 s | **1.518 s** | main |
| `ENGINES.build("uff")` | 0.088 s (+1 MB) | **1.559 s (+117 MB)** | worker |
| one `compute` (energy+forces) | 0.044 s | **0.571 s (+298 MB)** | worker |
| 10 optimiser steps, atoms only | 0.113 s | 3.145 s | worker |
| `write_cif` | 0.001 s | 0.004 s | main |
| `write_project` (.xtalproj) | 0.005 s | 0.027 s | main |
| `read_project` (no stored bonds) | 0.003 s | 0.010 s | main |
| **`read_project` with 848 / 768 stored bonds** | **2.095 s** | – | main |
| `grid.distance_grid` (Zeo++-free pore grid) | 0.763 s, +113 MB, 78³ = 474 552 pts | 0.349 s, 96×96×20 | worker |
| `isosurface` march | 0.307 s, +190 MB, **307 680 triangles** | 0.095 s, 62 304 tri | worker |
| PXRD reflections | 0.023 s | 0.012 s | worker |
| 50 × `Structure.copy()` | 0.002 s (20 KB each) | 0.006 s | main |

¹ `symmetry.detect` raises `ValueError: symmetry detection failed: too
close distance between atoms` on **Ni2Cl2BTDD and CFA1** — spglib
refusing the raw asymmetric unit. Off my topic, but it aborts any probe
that calls it, so the next reviewer should know.

Peak RSS reached in that headless process: **530 MB on Ni2Cl2BTDD**,
almost all of it the UFF term arrays and the grid/isosurface temporaries.

## UFF term arrays — where the memory goes

```
$ .venv/bin/python review/probes/perf/uff_build.py resources/samples/Ni2Cl2BTDD.cif
MOF-5       424 atoms    512 bonds  ->    512 bond /    912 angle /    960 torsion terms,  0.32 MB
MFU4l       648 atoms    848 bonds  ->    848 /  1 656 /  2 112 terms,                      0.65 MB
Ni2Cl2BTDD 1152 atoms  6 786 bonds  ->  6 786 / 102 240 / 526 176 terms,                   75.51 MB
```

`ewald=None` in every case: **electrostatics are default off**
(`uff/calculator.py:641 Param("coulomb", …, default=False)`), so none
of this is an Ewald sum.

The 6786 bonds are the reason. Degree histogram
(`review/probes/perf/` inline probe):

```
MFU4l       648 atoms   848 bonds  avg 2.62  max  6
Ni2Cl2BTDD 1152 atoms  6786 bonds  avg 11.78 max 28   <-- 7.48 disordered waters per formula unit
MOF-5       424 atoms   512 bonds  avg 2.42  max  4
```

`Ni2Cl2BTDD.cif` is `_chemical_formula_sum 'C12 H22.96 Cl2 N6 Ni2
O11.48'` — CSD entry POSWUS with partially-occupied solvent water. The
overlapping images give degree-28 atoms, torsions go as
Σ<sub>bonds</sub> deg(i)·deg(j), and 526 176 of them is what makes
*this* structure the expensive one. **CLAUDE.md's "0.44 s a step on
Ni2Cl2BTDD's 1152 atoms" is not a per-atom cost — it is a
per-disordered-solvent-torsion cost.**

## The GUI thread on MFU-4l (`review/probes/perf/gui_thread.py`)

`call` is the handler returning; `drain` is `app.processEvents(AllEvents,
60000)` afterwards, the pattern from run-app's SKILL.md.

| operation | call ms | drain ms | **total ms** | RSS MB |
|---|---:|---:|---:|---:|
| `select_all` (648 atoms) | 19.4 | 21.3 | 41 | 337 |
| `recompute_bonds` | 171.7 | 25.0 | **197** | 355 |
| **Set Bond Type: Single over the selection** | **715.7** | 24.0 | **740** | 349 |
| Set Bond Type: Automatic | 291.9 | 23.1 | **315** | 367 |
| style → polyhedra | 15.4 | 3.4 | 19 | 385 |
| style → wireframe | 61.8 | 2.8 | 65 | 371 |
| style → ball and stick | 68.0 | 1.0 | 69 | 385 |
| toggle a dock (hide) | 0.0 | 0.0 | 0 | 385 |
| toggle a dock (show) | 3.1 | 27.1 | 30 | 395 |
| `select_none` (partial refresh) | 3.8 | 14.8 | 19 | 379 |
| `select_all` (partial refresh) | 12.8 | 20.0 | 33 | 380 |
| `scene.set_model(model)` | 1.1 | 0.0 | 1 | 380 |
| `builder.build_scene` (648 atoms) | 32.2 | – | 32 | – |
| **Reduce to P1** | 255.7 | 206.8 | **463** | 355 |
| **`Supercell(2,2,2)` → 4960 sites** | 1182 | – | **1182** (+149 MB) | 489 |
| `build_scene` on 4960 sites | 252 | – | 252 | – |
| one `MoveSites` (drag one atom) | 66.5 | – | **67** (612 KB/step) | – |
| 50 `MoveSites` then 50 undos | 3.33 s / 3.38 s | – | – | +29.9 MB |

## The GUI thread on Ni2Cl2BTDD (`review/probes/perf/gui_ni.txt`)

| operation | call ms | drain ms | total ms | RSS MB |
|---|---:|---:|---:|---:|
| `select_all` (1152 atoms) | 87.1 | 52.7 | 140 | 459 |
| `recompute_bonds` | 382.7 | 59.1 | 442 | 549 |
| **Set Bond Type: Single** | **3140.2** | 66.8 | **3207** | 496 |
| **Set Bond Type: Automatic** | **1812.1** | 85.2 | **1897** | 450 |
| style → ball and stick | 155.8 | 4.5 | 160 | 465 |
| Reduce to P1 | 450.1 | 210.0 | 660 | 526 |

Idle window: **12 OS threads, 19 `vtkActor`s, 22 view props** — the
same 19 whether the structure is 648 atoms or 5184.

`renderWindow.Render()` calls, counted with a patched bound method:
**2 per `recompute_bonds`, 1 per selection change.** No redundant
rendering.

## Worker jobs, and how many cores they use

`review/probes/perf/opt_step.py`, `psutil.cpu_times()` around the loop:

| structure | relax cell | s/step | CPU s / wall s | OS threads | max RSS |
|---|---|---:|---:|---:|---:|
| MFU4l | no | **0.008** | 1.00× | 2 | 113 MB |
| MFU4l | yes | **0.102** | 1.00× | 2 | 121 MB |
| Ni2Cl2BTDD | no | **0.297** | 0.99× | 2 | 578 MB |
| Ni2Cl2BTDD | yes | **3.883** | 0.99× | 2 | 586 MB |

**Parallelism is 0.99×. A running job pins exactly one core and leaves
seven idle.** And it cannot do otherwise: numpy here is built against
**Apple Accelerate**, not OpenBLAS (`np.show_config()` → `"blas":
{"name": "accelerate"}`), which ignores `OMP_NUM_THREADS` entirely — and
nothing in the repo sets `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` or
`MKL_NUM_THREADS` anyway (`grep -rn` over the tree excluding `.venv`
returns nothing). The UFF path is elementwise numpy and `np.bincount`,
with no GEMM for a BLAS to thread. **So the "BLAS threads inside a
QThread" contention theory is wrong for this application** — worth
saying, because it would otherwise be the first thing anyone tried.

Where one Ni2Cl2BTDD step goes (`cProfile`, tottime, 5 steps):

```
0.427  uff/terms.py:466 TorsionTerm.energy_and_gradient     (70% with its children)
0.262  uff/terms.py:163 _scatter                            (the already-fixed bincount)
0.196  uff/terms.py:667 vdW energy_and_gradient             (22%)
0.170  numpy cross
0.049  uff/terms.py:324 AngleTerm.energy_and_gradient
0.004  ff/optimize.py:395 SymmetryDOF._projectors   <-- once per run, 0.2%
```

**The projectors are not the cost** — 4 ms once. It is 99 % energy and
forces, and 70 % of that is the 526 176 torsions.

## The test suite (`review/probes/perf/pytest4.*`, `pytest10.*`)

Not the full suite. Both runs with `-p no:cacheprovider -o
faulthandler_timeout=120` under `/usr/bin/time -l`, with a sidecar
(`rss_watch.py`) sampling RSS once a second.

| run | tests | wall s | CPU s | max RSS | off-CPU |
|---|---:|---:|---:|---:|---:|
| `test_open_once test_window_layout test_modules_ui test_scan_ui` | 108 | 10.91 | 9.26 | 352 MB | 15 % |
| the 10 largest test files | 481 | 46.84 | 35.51 | **497 MB** | **24 %** |

RSS over the 481-test run, one sample per second
(`review/probes/perf/rss_pytest10.txt`):

```
  t_s   rss_mb
    0      183   #########
    4      270   #############
    9      345   #################
   13      384   ###################
   20      267   #############
   24      215   ##########
   31      365   ##################
   34      215   ##########
   40      239   ###########
   43      405   ####################
   45      438   #####################
```

It **oscillates between 200 and 440 MB and does not grow monotonically**
— `pytest_runtest_teardown` (`tests/conftest.py:196`) is doing its job
and the documented 74-live-`MainWindow` leak has not come back.

Test-fixture arithmetic: 137 test files, **2794 tests**, 36 files build
a `MainWindow` (53 construction sites). At 46.84 s / 481 tests the whole
suite extrapolates to **272 s** — exactly CLAUDE.md's "235-330 s".

`--durations=20` from the 10 largest files: the slowest single test is
**1.33 s** (`test_build_ui.py::test_the_footer_says_how_far_the_symmetry
_will_multiply_it`) and the next nine are all `test_build_ui` /
`test_mof_ui` between 0.38 and 1.06 s. Nothing approaches a minute;
CLAUDE.md's rule holds.

## Packaging (read only — no build)

`docs/PACKAGING.md:556` — the DMG is ~185 MB, the installed `.app` 493
MB. `packaging/bundle.py:229` explicitly excludes `vtkmodules.all` and
`vtk` with the reason written down ("would pull in every one of the
~180 modules in a 592 MB package"), and thirteen `vtkmodules` are named
individually. `du -sm` on this venv agrees: `PySide6` 1201 MB,
`vtkmodules` 518 MB, `rdkit` 103 MB, `scipy` 77 MB, `matplotlib` 29 MB.
`COLLECT = ["rdkit", "rdeditor", "qdarktheme", "matplotlib"]`, so RDKit
(~107 MB) and matplotlib are bundled whole, each with a written
justification. **This is the best-documented part of the project's
non-functional story and I found nothing to fix in it.**

---

# Findings

## 1. `[critical]` `Structure.add_bond` is O(n²), with a numpy matmul inside the comparison

**Where.** `xtal/core/structure.py:538-541`.

```python
identity = self._bond_identity(bond)
if any(self._bond_identity(b) == identity for b in self.bonds):
    return False
```

`_bond_identity` calls `bond.key(self.space_group)` → `canonical` →
`reverse`, and `reverse` (`structure.py:140`) does `rot @
np.asarray(self.image)` plus `tuple(int(round(v)) for v in image)` and
constructs a fresh `Bond` whose `__post_init__` re-validates. So each
comparison is a matmul, three `round`s and an object construction — and
it is done once per bond already stored, per bond added.

**Evidence.** `review/probes/perf/addbond.py`, synthetic P1 chain:

```
n=  200 bonds:    115.0 ms  (  578 us/bond)
n=  400 bonds:    466.9 ms  ( 1170 us/bond)
n=  800 bonds:   1895.3 ms  ( 2372 us/bond)
n= 1600 bonds:   7624.6 ms  ( 4768 us/bond)
n= 3200 bonds:  29757.9 ms  ( 9302 us/bond)
```

Textbook quadratic: per-bond cost doubles with n. And in a real path —
opening a project with the bonds a document carries:

```
$ .venv/bin/python review/probes/perf/proj_bonds.py
MOF-5   424 sites  512 bonds   write  13.7 ms   read   773.4 ms    13 KB
MFU4l   648 sites  848 bonds   write  19.1 ms   read  2095.1 ms    21 KB
HKUST1  624 sites  768 bonds   write  17.0 ms   read  1731.9 ms    18 KB
```

`cProfile` of that `read_project` names it exactly:

```
360824  0.980  structure.py:140 reverse        # 848^2/2 = 359 552
1082472 0.618  builtins.round
362520  0.515  structure.py:124 Bond.__post_init__
```

**Why it matters.** Opening a 21 KB file takes 2.1 s on the main
thread. `reduce_to_p1` with stored bonds is 798 ms on MOF-5's 512. The
loop callers are all user paths: `xtal/core/symmetry.py:243` (Reduce to
P1), `xtal/io/project.py:191` (every project open),
`xtal/mof/build.py:517` (every MOF built), `xtal/build/molecule.py:105`
(every SMILES molecule), `xtal/commands/clipboard.py:271` (paste),
`xtal/commands/connections.py:146`. It gets worse the bigger the
framework, which is exactly the wrong direction.

**Fix.** Keep a `set` of bond identities on the `Structure` beside
`self.bonds`, maintained by `add_bond`/`remove_bond`/`set_bonds`, and
make the duplicate test a hash lookup. The bulk form `set_bonds`
(`structure.py:555`) already exists and already documents why loops are
wrong ("a loop over them re-expands the cell once per bond"); the six
loop callers above should use it, and `add_bond` should stop being
O(n) for the ones that cannot.

## 2. `[important]` `SpaceGroup._build_inverses` is 177 ms per fresh Fm-3m object, and the cache is per-instance

**Where.** `xtal/core/spacegroup.py:238-253`, reached from
`inverse_of` at `:223`.

```python
for op in ops:
    rot = np.linalg.inv(op.rot)
    for m, candidate in enumerate(ops):
        if not np.allclose(candidate.rot, rot, atol=1e-9):
```

O(ops²) with an `np.allclose` in the inner loop: 192² = 36 864 for
Fm-3m.

**Evidence.**

```
MFU4l        Fm-3m   192 ops   cold inverse table  177.0 ms   warm 0.5 us
Ni2Cl2BTDD   H-3m     36 ops   cold               7.3 ms
second SpaceGroup(225) instance, cold: 173.1 ms   (a shared cache would be ~0)
```

and in the GUI profile of Set Bond Type it is the single largest entry:
`spacegroup.py:238 _build_inverses  0.332 s cumulative`, 30 221
`np.allclose` calls. `Structure.copy()` does reuse the object, so it is
paid on CIF read, project load, `set_space_group`, and every
`reduce_to_p1` — not on every edit.

**Why it matters.** 177 ms is a third of the time a user waits for Set
Bond Type on MFU-4l and a sixth of `Supercell`. It is pure waste: the
inverse table is a function of the group number and setting, nothing
else.

**Fix.** Memoise the table on the class, keyed by the group's
identity rather than the instance; and replace the O(n²) `allclose`
search with a dict keyed on the rotation matrix rounded to integers —
rotations in a space group *are* integers in the fractional basis, so
`tuple(np.round(rot).astype(int).ravel())` is an exact key and the
whole thing becomes one pass.

## 3. `[important]` Set Bond Type over a whole selection blocks the main thread for 0.72 s on MFU-4l and 3.14 s on Ni2Cl2BTDD

**Where.** `xtalapp/document.py:1264 set_selected_bond_type` →
`xtal/commands/bonds.py:506 plan` / `:481 _keyed`, and the refresh
that follows.

**Evidence.** `review/probes/perf/setbond_prof.py`, cumulative:

```
1.083  document.py:1264 set_selected_bond_type
0.830    document.py:447 run
0.341      commands/bonds.py:506 plan -> _keyed -> 848 x Bond.key
0.332        spacegroup.py:238 _build_inverses        (finding 2)
0.489    document.py:525 _after_change
0.321      mainwindow.py:1252 _on_selection_changed
0.321        mainwindow.py:1282 _sync_bond_type_actions
0.321          document.py:1335 selected_bond_type -> bonding.graph  (x2)
```

**Why it matters.** CLAUDE.md's invariant — "A long operation over a
whole selection is applied in one batch, not atom-by-atom with a redraw
between" — is honoured: `Render()` is called twice, not 848 times. The
batching is not the problem. The problem is that the *batch itself*
costs 0.34 s (finding 2) and the *refresh afterwards* costs another
0.32 s because `_sync_bond_type_actions`, an action-enablement handler,
calls `Document.selected_bond_type` which calls `bonding.graph` — twice.
Building a bond graph to decide whether a menu item should be ticked is
the "rebuilding a site table because a spinbox moved" failure mode that
CLAUDE.md warns about, in the enablement path rather than the panel
path.

**Fix.** Have `_sync_bond_type_actions` read a cached order off the
selection instead of re-deriving the graph, and fix finding 2; the two
together take 0.72 s to roughly 0.05 s.

## 4. `[important]` One UFF energy evaluation on Ni2Cl2BTDD allocates 298 MB, on an 8 GB machine

**Where.** `xtal/ff/uff/terms.py:466 TorsionTerm.energy_and_gradient`.

**Evidence.** `review/probes/perf/hotops.py`: `uff compute (1
energy+forces)  0.571 s  RSS +298.0 MB`. The term arrays themselves are
75.5 MB (526 176 torsions × index/parameter columns); the 298 MB is the
temporaries — `u`, `v`, two `np.cross` results, two `np.linalg.norm`s,
the gradient — each a `(526176, 3)` float64 at 12.6 MB, roughly twenty
of them live at once.

**Why it matters.** `ENGINES.build` plus one `compute` takes the
headless process from 63 MB to 530 MB. In the GUI that is on top of a
420 MB window. On a machine with ~3 GB of usable RAM, a scan on this
structure is one of the things pushing the compressor to 19.9 GB.

**Fix.** Chunk the torsion evaluation — process the term arrays in
blocks of, say, 50 000 and accumulate — which costs nothing in speed
(the arrays are already contiguous) and caps the transient at a few MB.
`float32` for the shift arrays would help too; they hold small integers.

## 5. `[important]` Variable-cell relaxation costs 13 energy evaluations per step, and the code knows

**Where.** `xtal/ff/api.py:120 numeric_stress`, called from
`xtal/ff/optimize.py:725`.

**Evidence.** Measured cost ratio, cell-free vs cell-relaxed
(`opt_step.py`): MFU-4l **0.008 → 0.102 s/step (12.8×)**, Ni2Cl2BTDD
**0.297 → 3.883 s/step (13.1×)**. A `cProfile` of 5 cell-relaxed steps
shows **78 calls** to `UFFCalculator.compute` — 15.6 per step, i.e. the
12 central differences plus the line search.

The comment above it already says so: *"twelve more energy evaluations
a step. Affordable for a few hundred atoms, not for a few thousand —
and the reason the first thing to write after this is an analytic
virial."*

**Why it matters.** CLAUDE.md sizes an overnight scan at "0.44 s a step
… so a 12×12 grid is ~2.6 hours". At **3.88 s/step with the cell
relaxing**, which is what a flexible-framework scan actually does, the
same grid is a **23-hour** job. That is the difference between an
overnight run and a weekend.

**Fix.** The analytic virial the comment names. UFF's terms are all
pairwise/three-body in cartesian displacements, so the virial is
`Σ r ⊗ f` accumulated in the same pass that already computes the
forces — no new derivatives, and it turns 13 evaluations into 1.

## 6. `[important]` `bonding._find_atom` is a linear scan of the whole cell, called twice per operation per bond

**Where.** `xtal/core/bonding.py:584`, called from `map_explicit_bond`
(`:449`) once per group operation per end.

```python
d = cell.frac - frac
dist = np.linalg.norm(d @ lattice.matrix, axis=1)
hit = np.flatnonzero(dist < tol)
```

**Evidence.** In the GUI profile of Set Bond Type on MFU-4l: `7296
calls, 0.195 s cumulative` for 19 mapped bonds — 192 operations × 19
bonds × 2 ends, each scanning all 648 atoms ≈ 4.7 M distance
computations to look up 7296 points.

**Why it matters.** It scales as (cell atoms × group order × bonds),
so it is worst on exactly the high-symmetry frameworks the application
is for. It also shows up in `reduce_to_p1` (8992 calls, 0.258 s).

**Fix.** The fix this repo already made twice: a KD-tree. `P1Cell`
could carry a `scipy.spatial.cKDTree` over its wrapped fractional
coordinates, built once and memoised beside the expansion — the same
move as `read_cgd`'s overlap check (`xtal/mof/pormake/PROVENANCE.md`),
which took `test_mof_vendored.py` from 42 s to 11 s.

## 7. `[important]` Dragging one atom rebuilds the whole scene, including 588 SVDs

**Where.** `xtalapp/viewport/builder.py:608 _bond_frames` →
`:652 _offset_direction` → `transforms.best_fit_plane` (an SVD) →
`:633 _substituents`.

**Evidence.** `review/probes/perf/move_prof.py` — 10 single-atom
`MoveSites` in the real window, tottime:

```
0.212  vtkCocoaRenderWindow.Render            (10 calls, 21 ms each)
0.101  p1.py:238 _distinct                    (100 calls)
0.101  numpy.linalg.svd                       (5880 calls = 588 per move)
0.100  builder.py:633 _substituents           (5760 calls)
0.397  builder.py:652 _offset_direction       (cumulative)
```

One move costs **66.5 ms** and **612 KB** (`review/probes/perf/
undo_scene.py`: 50 moves = 3.33 s, +29.9 MB).

**Why it matters.** 66 ms is 15 fps — a drag on MFU-4l is visibly
sticky, and this is the interaction the "A drag moves the copy the
cursor has hold of" invariant exists to make feel right.

**Fix.** Two things. `_bond_frames` only depends on the *bonding*, not
the positions, for everything except the final cross product — cache the
per-bond substituent index lists on the graph and recompute only the
geometry. And `best_fit_plane` over 576 small clouds is one batched
`np.linalg.eigh` on a stacked `(576, 3, 3)` covariance array, not 576
SVDs. This is the same class of fix as `_scatter` in `ff/uff/terms.py`
— a Python loop with numpy inside it, on a per-bond array.

## 8. `[important]` A long main-thread operation gives no sign that it is working

**Where.** All of `xtalapp/`.

**Evidence.**

```
$ grep -rn "setOverrideCursor" --include=*.py xtalapp/ | wc -l
1
xtalapp/dialogs/subgroup.py:302: QGuiApplication.setOverrideCursor(Qt.WaitCursor)
```

One, in a dialog. Meanwhile, measured above on the main thread:
Supercell 1182 ms, Set Bond Type 740 ms (3207 on Ni2Cl2BTDD), Reduce to
P1 463 ms, recompute_bonds 197 ms (442 on Ni2Cl2BTDD). `QProgressDialog`
appears once (`xtalapp/dialogs/run_progress.py`) and that is for worker
jobs.

**Why it matters.** Anything over ~100 ms with no feedback reads as the
application having missed the click; over a second it reads as a hang.
On Ni2Cl2BTDD, Set Bond Type is three seconds of a frozen window.

**Fix.** A small context manager that sets `Qt.WaitCursor` and restores
it, wrapped around the `_run` / `apply` prologue in `mainwindow.py` —
one place, since the factoring review found `_run` is already the shared
prologue for symmetry and cell operations. Cheaper than moving the work
off the thread and enough for everything under ~2 s.

## 9. `[minor]` The Zeo++-free pore surface costs 340 MB of transient on MFU-4l

**Where.** `xtal/analysis/grid.py:55 distance_grid` and
`xtal/analysis/isosurface.py:78 isosurface`, called from
`xtal/modules/zeopp.py:322-324`.

**Evidence.** `review/probes/perf/hotops.py` on MFU-4l: grid `0.763 s,
+113 MB` on a 78³ = 474 552-point array, march `0.307 s, +190 MB`,
**307 680 triangles**, leaving the process at 402 MB from a 64 MB base.

**Why it matters.** It is on a worker thread, so it is not a freeze —
but 340 MB of transient inside a 400 MB GUI process is a third of what
is left of this machine's RAM. Incidentally, CLAUDE.md records "190 000
triangles and 3 s"; at `DEFAULT_SPACING = 0.4` and probe 1.2 it is now
**307 680 triangles and 1.07 s** — faster and denser than the note says,
and the note deserves updating either way.

**Fix.** March the grid in slabs along `c` and emit triangles
incrementally, and store the grid as `float32` (it is a distance in
Ångström; `float64` buys nothing). That is 113 → 57 MB for the field and
caps the march's own peak.

## 10. `[strength]` The things that would normally be wrong here are right

Recording these because a review that only lists problems misrepresents
the code.

- **VTK is imported by name, never wholesale.** `grep -rn "^from
  vtkmodules\|^import vtk"` over `xtal/` and `xtalapp/` returns fifteen
  lines, each naming specific classes; there is no `import vtk`
  anywhere, and `packaging/bundle.py:229` excludes `vtkmodules.all`
  with the reason written down.
- **`rdkit`, `matplotlib` and `ase` are function-level imports** —
  `xtal/build/chem.py:95`, `xtalapp/dialogs/pattern.py:126`,
  `xtal/analysis/kpath.py:88` — so a user who never opens the sketcher
  or the PXRD window never pays 0.13 s or 0.26 s. `xtalapp/main.py`
  imports in 0.024 s.
- **The viewport uses glyph mappers, not an actor per atom.** 19
  `vtkActor`s and 22 props with 648 atoms on screen; still 19 with
  5184. `scene.set_model` is 1.1 ms and `set_positions` 0.4 ms — the
  cost is all in `build_scene` on the Python side, which is the half
  that can be optimised.
- **Rendering is not triggered redundantly.** 2 `Render()` calls per
  `recompute_bonds`, 1 per selection change, counted with a patched
  bound method.
- **`compute` is genuinely vectorised.** 823 Python function calls for
  a 1152-atom energy and gradient. The `_scatter` fix generalised: there
  is no per-atom Python loop anywhere in the energy path.
- **`Structure.copy()` is cheap and shares.** 50 copies of MFU-4l cost
  2 ms and 1 MB (20 KB each); the space group object is shared, not
  deep-copied.
- **The test teardown fix holds.** RSS across 481 tests oscillates
  200-440 MB and does not trend upward.
- **Packaging is measured, not guessed.** `docs/PACKAGING.md` carries
  the size of every decision and two reversals with their reasons.

---

# Why this machine is contended

## The numbers

```
$ sysctl hw.memsize hw.ncpu
hw.memsize: 8589934592          # 8 GB, not 16
hw.ncpu: 8

$ vm_stat
Pages wired down:                        106706    #  1.67 GB, unswappable
Pages stored in compressor:             1306503    # 19.94 GB of data...
Pages occupied by compressor:            209711    # ...held in 3.20 GB of RAM
Pages free:                                3922    #  61 MB
Swapins:                               18295692    # 279 GB read back from swap
Swapouts:                              19760073

$ sysctl vm.swapusage
total = 7168.00M  used = 5681.69M            # and it has been up to 9.4 GB today
```

Wired (1.67 GB) plus compressor (3.20 GB) is **4.87 GB of 8 GB gone
before any application gets a page**. What is left for everything
running is about 3.1 GB, and the compressor is holding six times that
much data at a 6.2:1 ratio. Every allocation above the working set
either compresses something or pages it to the encrypted swap file.

## What each thing needs

| | resident | note |
|---|---:|---|
| empty Crystal Builder window | **211 MB** | |
| window with MFU-4l | **372 MB** | |
| window with Ni2Cl2BTDD | **420 MB** | 549 MB after Recalculate Bonds |
| window after Supercell 2×2×2 | **489 MB** | |
| headless UFF on Ni2Cl2BTDD | **578 MB** | 298 MB of it one energy evaluation |
| headless porosity surface, MFU-4l | **402 MB** | 340 MB of it transient |
| `pytest` on 4 GUI files (108 tests) | **352 MB** | |
| `pytest` on the 10 largest files (481 tests) | **497 MB** | |
| **one full serial suite** | **~500 MB sustained for ~270 s** | |

So one test run plus one driven window is about 900 MB. Two agents doing
that at once is 1.8 GB out of a 3.1 GB budget, and the compressor
absorbs the difference by evicting the *other* processes' pages — which
is why the effect is superlinear rather than proportional.

## 819 s vs 332 s: memory-bound, not CPU-bound

The suite's own CPU demand is modest and single-threaded. My 481-test
run: **46.84 s wall, 35.51 s CPU, 373.6 G instructions, 111.0 G cycles
(IPC 3.37)**. IPC of 3.4 is a core doing real work, not stalling on
memory locally. But **24 % of the wall clock was not on CPU at all**, and
the four-file run's figure was 15 % — the difference between them is
that the bigger run holds more resident and therefore faults more. That
fraction is what grows without bound as the machine fills:

- 332 s ≈ the 272 s my sample extrapolates to, plus coverage's tracer.
- 819 s is 2.5× that, and the suite did not do 2.5× more work. At 20:00
  swap was 8.9 of 9.2 GB — 97 % full, the state CLAUDE.md warns about —
  so essentially every `MainWindow` construction was touching pages that
  had to be decompressed or read back from disk first. The machine's
  lifetime counters (18.3 M swapins = 279 GB) say that is the normal
  condition here, not an anomaly.

It is also why CLAUDE.md's "Aborted runs" section exists: `dlopen`
failing with *"pmap_enter retried due to resource shortage"* is the same
shortage, hit during a large library load rather than during an
allocation.

## What would help, in order of effect per unit of work

1. **Don't run two heavy things at once.** The single biggest lever and
   it costs nothing. `pgrep -fl "pytest|drive.py"` before measuring, as
   this review did.
2. **Share one `QApplication` and build fewer full `MainWindow`s.** 36
   files build one, 53 times; a `MainWindow` is the expensive object
   (the 211 MB baseline). Several of those files test one dock or one
   dialog and could take a fixture that builds only that widget. This
   is a real reduction in the suite's *resident* set, which is what the
   machine is short of.
3. **`-p no:cacheprovider`** (already used above) and a `--forked`-free
   serial run keep the process count at one; do not reach for `-n auto`,
   which multiplies a 500 MB process by the worker count *and* hits the
   `workers.py` deadlock CLAUDE.md documents.
4. **Mark and split.** A `-m "not slow"` pass is already available;
   adding a `gui` marker would let a headless-core change be verified in
   the ~60 s the `xtal/` tests need rather than the 272 s the suite
   needs.
5. **Fix findings 1, 2 and 4.** They are the application's own memory
   and time, and the suite exercises them on every structure fixture.
6. **More RAM.** Nothing above changes the fact that 8 GB with 19.9 GB
   in the compressor is a machine already living beyond its means; the
   software fixes buy headroom, not immunity.

---

# The three optimisations that pay back most for MFU-4l-sized frameworks

### S — Hash the bond identity, and memoise the inverse table
*Findings 1 and 2. Two files, `xtal/core/structure.py` and
`xtal/core/spacegroup.py`, a day's work, no behaviour change.*

A `set` of identities beside `self.bonds` makes `add_bond` O(1); a
class-level cache keyed on the group, plus an integer dict instead of
the O(n²) `allclose` search, makes the inverse table free after the
first time. Measured payoff: **project open 2.10 s → well under 0.1 s**,
**Reduce to P1 with bonds 798 ms → tens of ms**, **Set Bond Type 740 ms
→ ~0.4 s** (the rest is finding 3's refresh), and every MOF build and
every paste along with them. Verified by the existing bond round-trip
tests; the semantics of `_bond_identity` do not change, only how it is
looked up.

### M — An analytic virial for UFF, and a chunked torsion evaluation
*Findings 5 and 4. `xtal/ff/uff/terms.py` and `xtal/ff/uff/calculator.py`,
with `numeric_stress` kept as the reference the finite-difference tests
compare against.*

The virial accumulates in the same pass as the forces, so it turns 13
energy evaluations per cell-relaxation step into 1: **MFU-4l 0.102 →
~0.012 s/step, Ni2Cl2BTDD 3.88 → ~0.35 s/step**. A 12×12 flexible-cell
scan on Ni2Cl2BTDD goes from ~23 hours to ~2. Chunking the torsion
arrays at the same time caps the 298 MB transient at a few MB, which on
this machine is worth as much as the speed. The code already names this
as the next thing to write.

### L — Make the scene builder incremental, and put the long edits behind a cursor
*Findings 7 and 8, plus finding 3's refresh path.
`xtalapp/viewport/builder.py`, `xtalapp/mainwindow.py`, and whatever
`_sync_bond_type_actions` should be reading instead of a bond graph.*

Three pieces: cache the per-bond substituent lists on the graph so a
position change recomputes geometry and not topology; batch
`best_fit_plane` into one `eigh` over a stacked array; and stop the
enablement handlers from deriving a bond graph. That takes a drag from
**66.5 ms to something near the 21 ms `Render()` floor** — 15 fps to 45 —
and takes the refresh half off Set Bond Type and Reduce to P1. The busy
cursor is a one-line context manager around the shared `_run` prologue
and should land first, because it makes the remaining 400 ms
*legible* rather than alarming while the rest is being written.

---

# What I did not get to

- **The Zeo++ module end to end.** I measured `grid.distance_grid` and
  `isosurface` headlessly, which is the part CLAUDE.md says is ours; I
  did not run a real Zeo++ binary, so the subprocess's own memory and
  the `-visVoro` parse are unmeasured.
- **`.xtalproj` with a pore network or a scan surface in it.** CLAUDE.md
  says the surface is deliberately not written into the project (59 MB
  of JSON); I did not verify the size of a project that carries a
  Voronoi network and a session.
- **DFTB+, xTB and MACE.** All three are external or heavyweight and
  CLAUDE.md is explicit that loading MACE mid-process is what causes the
  aborted runs. I did not load any of them.
- **The `workers.py` deadlock's performance cost.** The threads review
  has it; I only note that every worker job I measured used one core.
- **PXRD at a realistic 2θ range and peak count** — I timed
  `reflections` at 5-50° with default settings (23 ms on MFU-4l) but not
  the profile convolution over a fine grid, which is where a PXRD
  window's redraw cost would be.
- **A cold start with a cold page cache.** Every startup number above is
  warm; a first launch after boot will be worse and `--selftest` is the
  natural place to measure it (it already builds a window and opens a
  sample, and has no `perf_counter` in it at all — three lines would
  give every build a cold-start number).
- **Windows and Linux.** Everything here is macOS 13.2 on arm64 with
  numpy on Accelerate. The "one core per job" conclusion may not hold on
  a build where numpy uses OpenBLAS, and setting `OPENBLAS_NUM_THREADS`
  would then matter.
