# Crystal Builder — Architecture & Implementation Plan

A cross-platform (macOS + Windows) desktop application for building,
manipulating, analysing and exporting crystal structures. Visual and
interaction model follows **VESTA**; structure-editing/symmetry/force-field
capability follows **Materials Studio**. Written entirely in Python.

Decisions locked in before this plan was written:

| Decision | Choice |
|---|---|
| GUI toolkit | **PySide6** (Qt 6, LGPL) + **VTK** viewport |
| Repo | new standalone repo `~/GitHub/Crystal-Builder`, package `xtal` |
| Crystallography backend | **gemmi** (CIF + space-group tables) + **spglib** (symmetry detection), optional ASE bridge |
| Force field | **native NumPy UFF** in-repo, behind a pluggable `Calculator` API |

---

## 1. Design principles

These five rules are what make the app cheap to extend later (PXRD
refinement, SHELX, Zeo++, diffraction simulation, experimental-data
overlays — see §12).

1. **Headless core, Qt-free.** Everything in `xtal/` (data model, I/O,
   symmetry, bonding, force field, analysis) imports *no* Qt and *no*
   VTK. It is unit-testable on a CI box with no display and usable as a
   library/CLI. The GUI in `xtalapp/` is a thin shell over it.
2. **Every mutation is a Command.** No widget ever mutates a
   `Structure` directly. It builds a `Command` and pushes it onto the
   document's `CommandStack`. Undo/redo, copy/paste, macro recording,
   scripting, and the Python console all fall out of this for free.
3. **Registries, not `if/elif`.** File formats, draw styles, analysis
   modules, calculators, selection predicates and interaction modes are
   all registered into dicts (populated in-tree and via
   `importlib.metadata` entry points). Adding PXRD later = adding one
   module + one registration line, touching zero existing files.
4. **Symmetry is first-class, not an afterthought.** The document holds
   an *asymmetric unit + space group*, and derives the P1 cell from it
   (see §5). Getting this right at the start is the single highest-value
   architectural decision; retrofitting it is a rewrite.
5. **Render model ≠ data model.** The viewport consumes a flat,
   numpy-array `SceneModel` produced by a builder. Changing draw style
   or display range never touches the structure; moving an atom triggers
   a cheap positions-only scene update, not a full rebuild.

---

## 2. Stack and dependencies

**Runtime**

| Package | Why | Notes |
|---|---|---|
| `PySide6` | main window, docks, tables, trees, dialogs | LGPL; ships Qt 6 wheels for macOS (arm64+x86_64) and Windows |
| `vtk >= 9.3` | 3-D viewport via `QVTKRenderWindowInteractor` | glyph-based rendering scales to 10⁵ atoms |
| `numpy` | all geometry, all force-field math | |
| `gemmi` | CIF reading, 230 space groups + Hall symbols + settings, symmetry operations | small C++ wheel, fast |
| `spglib` | symmetry detection with tolerance, Wyckoff letters, cell standardisation/refinement, Niggli/Delaunay reduction | |
| `scipy` | `cKDTree` neighbour search, L-BFGS, sparse ops | |

**Optional extras** — `gui` (`PySide6`, `vtk`) and `ase` (bridge to
external calculators/optimisers). The core installs with neither, so
`pip install crystal-builder` stays usable on a headless box.

**No plotting library.** The plan originally listed `pyqtgraph` for the
live convergence plot, and `matplotlib` for future patterns. Neither is
a dependency: the optimisation trace and the pore-size histogram are a
hundred lines each of `QPainter` in `xtalapp/plot.py` and
`xtalapp/histogram.py` — less to pin and package than a second large
GUI dependency, and they follow the user's theme without being asked. A
richer plot (PXRD overlays with pan, zoom and picking) is a real reason
to reconsider.

**Dev** — `pytest`, `pytest-qt`, `pytest-xdist`, `ruff`, `pyinstaller`.
`pytest-qt` is in the `test` extra and not in `dev`: without it every
widget test skips itself, and CI installs `[gui,test]` — so the GUI
half of the suite was passing by not running.

Python **3.11+**. CI runs 3.11/3.12/3.13 on Linux and 3.12 on
macOS-14 (arm64), macOS-13 (x86_64) and Windows. Line length 79 and
heavy module docstrings, matching your existing house style.

---

## 3. Repository layout

```
Crystal-Builder/
├── pyproject.toml            # packaging, deps, extras, entry points, ruff/pytest cfg
├── CLAUDE.md                 # how to work in this repo: layout, commands, invariants
├── README.md
├── .github/workflows/ci.yml  # ruff + pytest, offscreen Qt on Linux
├── docs/
│   ├── PLAN.md               # this file: the architecture, and the phases that built it
│   ├── ROADMAP.md            # the delivery plan for TODO.md — phases A onwards
│   └── TODO.md               # raised by using the app; an entry is deleted when it ships
├── xtal/                     # ---- CORE (no Qt, no VTK) ----
│   ├── core/
│   │   ├── elements.py       # Z, symbol, mass, covalent/vdW radii, CPK+VESTA colours, valence
│   │   ├── lattice.py        # Lattice: (a,b,c,α,β,γ) ⇄ 3×3 matrix, frac⇄cart, metric,
│   │   │                     #   reciprocal, volume, d-spacing, strain, transform(P)
│   │   ├── site.py           # Site: element, frac coords, occupancy, label, Uiso/Uaniso,
│   │   │                     #   charge, wyckoff, props dict
│   │   ├── structure.py      # Structure: Lattice + asymmetric unit + SpaceGroup + stored bonds;
│   │   │                     #   Change flags and the cache mask they invalidate
│   │   ├── spacegroup.py     # SpaceGroup: gemmi tables, Hall symbols, settings, operations
│   │   ├── p1.py             # P1Cell: expanded atoms with provenance (site_idx, op_idx, tau)
│   │   ├── symmetry.py       # spglib detect/refine/standardise; set_space_group / reduce_to_p1 /
│   │   │                     #   asymmetrise / Wyckoff / merge_duplicates
│   │   ├── subgroups.py      # maximal translationengleiche subgroups, named in a standard setting
│   │   ├── neighbors.py      # periodic neighbour lists (cKDTree over padded images), cutoff maps
│   │   ├── bonding.py        # perception, per-pair rules, explicit/suppressed/topology bonds,
│   │   │                     #   bond orders, fragments, coordination sequence and point symbol
│   │   ├── supercell.py      # supercell, general integer P, change_setting, Niggli/Delaunay
│   │   ├── selection.py      # Selection set + predicate registry + query parser
│   │   ├── transforms.py     # translate/rotate/mirror/invert, best-fit plane, symmetry-aware
│   │   ├── measure.py        # distance/angle/torsion/plane (min-image aware)
│   │   └── properties.py     # formula, Z, density, volume, mass, charge balance
│   ├── io/
│   │   ├── registry.py       # FormatRegistry: ext → Reader/Writer, capability flags
│   │   ├── cif_reader.py     # gemmi small-structure read (+ keeps raw block for round-trip)
│   │   ├── cif_writer.py     # structural CIF, with symmetry or in P1, and a "generated by" note
│   │   ├── xyz.py            # single-frame XYZ
│   │   ├── cssr.py           # Zeo++'s format; always written in P1, because that is what it reads
│   │   ├── gen.py            # DFTB+ geometry, read and written
│   │   ├── trajectory.py     # multi-frame extended XYZ, streamed a frame at a time
│   │   └── project.py        # .xtalproj (zip: structure.cif + bonds.json + view/session json)
│   ├── commands/
│   │   ├── base.py           # Command (do/undo/label/merge_with), CommandStack, macro/transaction
│   │   └── atoms.py bonds.py cell.py symmetry.py clipboard.py ff.py
│   ├── ff/
│   │   ├── api.py            # Calculator ABC: energy/forces/stress + capability flags
│   │   ├── registry.py       # ENGINES: name → Calculator, with its options and availability
│   │   ├── uff/              # params.py (Rappé 1992), typer.py, terms.py, calculator.py, qeq.py
│   │   ├── dftb/             # calculator.py, hsd.py (input), params.py (Slater-Koster sets)
│   │   ├── ewald.py          # real+reciprocal Coulomb under PBC
│   │   ├── hydrogens.py      # where the missing hydrogens go, and how many there really are
│   │   ├── optimize.py       # FIRE / L-BFGS, constraints, symmetry projection, cell strain
│   │   └── record.py         # what a run leaves in its folder: log, trajectory, final structure
│   ├── modules/              # registry.py (Module/Action), process.py (external binaries: launch,
│   │                         #   stream, cancel), job.py, record.py, report.py,
│   │                         #   forcefield.py dftb.py zeopp.py stub.py
│   ├── analysis/porosity.py  # Zeo++ output parsed into results (future: pxrd.py)
│   ├── workspace.py          # the directory a structure and its runs live in
│   ├── params.py             # Param and Availability, shared by modules and engines
│   ├── plugins.py            # entry-point discovery + in-tree registration
│   └── cli.py                # headless: convert, symmetry, supercell, optimize, modules, run
├── xtalapp/                  # ---- GUI (PySide6 + VTK) ----
│   ├── main.py               # entry point; `crystal-builder` script
│   ├── mainwindow.py         # QMainWindow, docks, menus, context menus, drag&drop (~2400 lines)
│   ├── document.py           # Document: Structure + CommandStack + Selection + ViewSettings,
│   │                         #   emitting Qt signals with change hints
│   ├── actions.py            # single QAction registry → menus, toolbars, shortcuts, context menus
│   ├── viewport/
│   │   ├── widget.py         # QVTKRenderWindowInteractor host, camera, rubber band, hotkeys
│   │   ├── scene.py          # SceneModel dataclass (numpy arrays)
│   │   ├── builder.py        # Structure + ViewSettings → SceneModel
│   │   ├── vtk_scene.py      # SceneModel → actors; set_positions for a geometry-only change
│   │   ├── styles.py         # ball-and-stick, stick, wireframe, space-filling, polyhedra, ORTEP
│   │   ├── picking.py        # hardware selection → (site, image) ids
│   │   ├── modes.py          # select / add atom / add bond / measure / move
│   │   └── view_settings.py  # what is drawn: never on the undo stack, saved with the session
│   ├── docks/
│   │   ├── workspace.py filetree.py    # what is on disk, and what has been run
│   │   ├── modules.py results.py logview.py trajectory.py   # what can be run, and its output
│   │   ├── info.py sites.py inspector.py measure.py move.py style_panel.py
│   │   └── ff_panel.py       # one class, opened twice: the Forcefield panel and the DFTB+ one
│   ├── dialogs/              # add_atom, add_hydrogens, bond_rules, cell_edit, display_range,
│   │                         #   export, find_symmetry, merge_duplicates, module_form,
│   │                         #   run_progress, spacegroup, subgroup, supercell
│   ├── plot.py histogram.py  # the two plots, drawn by hand — no plotting dependency
│   ├── playback.py           # trajectory transport: play, loop, step, scrub
│   ├── workers.py            # QThread wrappers for long jobs + progress + cancellation
│   └── settings.py           # QSettings, window geometry, recent files, default view settings
├── tests/                    # headless where it can be; pytest-qt for widget logic
├── resources/                # samples/ — real CIFs used as fixtures
│                             # test/    — a workspace of real runs, read by the workspace tests
└── packaging/                # empty; PyInstaller specs and installers are § 16 phase 8
```

Two files named here in the original plan were never written:
`docs/architecture.md`, because [ROADMAP.md](ROADMAP.md) turned out to
be the thing that had to be kept current, and `docs/extending.md`,
which is owed by § 16 phase 9 along with the plugin that proves it.

---

## 4. Core data model

```python
@dataclass(frozen=True)
class Lattice:
    matrix: np.ndarray            # 3×3, rows = a, b, c in Å (a ∥ x, b in xy-plane)
    # from_parameters(a,b,c,al,be,ga) / .parameters / .volume / .reciprocal
    # .to_cart(frac) / .to_frac(cart) / .transform(P) / .strained(eps)

@dataclass
class Site:                       # one asymmetric-unit site
    element: str                  # "Fe"; oxidation state kept separately
    frac: np.ndarray              # (3,) fractional coords
    occupancy: float = 1.0
    label: str = ""               # CIF _atom_site_label; auto-generated if blank
    u_iso: float | None = None
    charge: float | None = None   # formal/partial; used by UFF-QEq
    wyckoff: str | None = None    # filled by symmetry detection
    props: dict = field(default_factory=dict)   # extension point: any future per-site data

@dataclass
class Bond:                       # explicit bond override, in *asymmetric* index space
    i: int; j: int
    image_j: tuple[int,int,int]   # lattice translation applied to j (PBC-correct)
    order: float = 1.0
    kind: str = "explicit"        # "explicit" | "suppressed"

class Structure:
    lattice: Lattice
    sites: list[Site]             # the ASYMMETRIC UNIT
    space_group: SpaceGroup       # gemmi-backed: number, HM symbol, Hall, setting, ops
    bonds: list[Bond]             # user-added/removed edges layered on auto-perception
    bond_rules: BondRules         # global + per-element-pair distance criteria
    meta: dict                    # title, source file, provenance, free-form
```

`Structure` is deliberately small and picklable; everything derived —
P1 expansion, neighbour lists, bond graph, scene arrays — is computed by
free functions and memoised on a `_cache` keyed by a monotonically
increasing `revision` counter. Cache invalidation is therefore a single
integer bump, which also drives the Qt signal hints.

---

## 5. The symmetry model (the key decision)

VESTA and Materials Studio both keep an **asymmetric unit + space
group** and *generate* the full cell for display. We do the same:

```python
class P1Cell:                     # derived, never edited directly
    frac:      np.ndarray  # (N,3) all atoms in [0,1)³
    site_idx:  np.ndarray  # (N,)  which asymmetric site each came from
    op_idx:    np.ndarray  # (N,)  which symmetry operation produced it
    tau:       np.ndarray  # (N,3) integer lattice shift applied after the op
```

Consequences, all handled explicitly:

* **Editing an image atom.** Click on a symmetry image and move/delete
  it: we map the edit back through `op_idx⁻¹` to the parent site, so the
  whole orbit moves consistently. This is the "symmetry-aware editing"
  toggle in the Symmetry menu. When it is **off**, the first such edit
  offers "this requires dropping to P1 — do it?".
* **Setting a space group** (`Symmetry ▸ Set Space Group…`) has two
  modes, exactly like Materials Studio: *(a) reinterpret* — treat the
  current atoms as the asymmetric unit and generate equivalents (with a
  merge tolerance and a clash report), or *(b) impose* — keep the full
  atom list, find the subset that is a valid asymmetric unit, warn on
  atoms that break the symmetry beyond tolerance.
* **Reduce to P1** expands the orbit into explicit sites and sets the
  group to `P 1`. Always available, always safe, and the escape hatch
  for any operation that is awkward under symmetry.
* **Find symmetry** runs spglib at a user tolerance (`symprec`, plus
  angle tolerance) on the P1 cell, reports space group + Wyckoff letters
  + a standardised cell, and offers three follow-ups: *report only*,
  *assign group (keep cell)*, *standardise cell and asymmetrise*.
* **Settings/origin choices** (e.g. origin choice 1 vs 2 for centro-
  symmetric groups, rhombohedral vs hexagonal axes) are carried as Hall
  symbols through gemmi so we never silently pick the wrong setting.
* **Symmetry-constrained relaxation** in the UFF module projects forces
  onto the symmetry-allowed subspace, so an optimisation can preserve
  the space group instead of drifting to P1.

---

## 6. Commands, undo/redo, clipboard

```python
class Command(ABC):
    label: str                                   # shown in Edit ▸ Undo <label>
    def do(self, doc) -> None: ...
    def undo(self, doc) -> None: ...
    def merge_with(self, other) -> bool: return False   # coalesce drag steps
```

* Commands store **their own inverse data** (the deleted sites, the old
  coordinates), not whole-structure snapshots — cheap for a 50 000-atom
  supercell. `StructureSnapshotCommand` is the fallback base class for
  sweeping operations (set space group, supercell, cell transform) where
  a snapshot is genuinely simpler and the structure changes wholesale.
* `CommandStack` supports **transactions/macros**: a dialog that changes
  five things pushes one undoable step.
* `merge_with` lets a continuous interactive drag collapse into a single
  undo entry when the mouse is released.
* **Clipboard** = a `Fragment` (atoms + internal bonds + cartesian
  coords + source cell). Copy puts the fragment on an internal clipboard
  *and* an XYZ/CIF text form on the system clipboard, so paste works
  into other apps and from other apps.
* **Paste** offers: at original coordinates, at centroid of view, or at
  a picked point; with optional "keep fractional coordinates" when
  pasting between cells of different size.

Command list at v1: `AddAtom`, `DeleteAtoms`, `SetAtomType`,
`SetAtomProperty` (occ/label/Uiso/charge), `MoveAtoms`, `AddBond`,
`DeleteBond`, `SetBondOrder`, `RecomputeBonds`, `SetLattice`,
`TransformCell`, `BuildSupercell`, `SetSpaceGroup`, `ReduceToP1`,
`StandardizeCell`, `MergeDuplicates`, `PasteFragment`, `ApplyOptimizedGeometry`.

---

## 7. Document, signals, and the GUI shell

```python
class Document(QObject):
    structureChanged = Signal(ChangeHint)   # TOPOLOGY | POSITIONS | CELL | SYMMETRY | STYLE
    selectionChanged = Signal()
    modifiedChanged  = Signal(bool)
```

`ChangeHint` is what keeps the viewport fast: `POSITIONS` updates a
numpy array and calls `Modified()` on one VTK points object;
`TOPOLOGY`/`CELL` rebuilds the scene. Multiple documents live in a
`QTabWidget` of viewports; the docks always target the *active*
document.

### Window layout

As built — the menu bar gained *Measure* and lost *Calculate* to
*Modules* (ROADMAP phase D), and there is no Python console:

```
┌───────────────────────────────────────────────────────────────────────┐
│ menu bar: File Edit Select Structure Measure Symmetry Cell Modules    │
│           View Window Help                                            │
│ toolbar: open save | undo redo | ⟦select add-atom add-bond measure    │
│          move⟧ | style▾ | cell-range | find-symmetry | UFF ▶          │
├──────────────┬──────────────────────────────────────┬─────────────────┤
│ Workspace    │                                      │ Inspector       │
│ (filesystem  │        VTK viewport (tabs per        │ Structure       │
│  + runs)     │        open structure)               │ Sites           │
│              │                                      │ Style · Move    │
│ Modules      │                                      │ Measurements    │
│ (what can    │                                      │ Force Field     │
│  be run)     │                                      │ DFTB+ · Results │
├──────────────┴──────────────────────────────────────┴─────────────────┤
│ Log (tails a running job) · Trajectory transport                      │
├───────────────────────────────────────────────────────────────────────┤
│ status: mode | 3 atoms selected | Fe2O3 · Z=6 · V=301.3 Å³ | progress │
└───────────────────────────────────────────────────────────────────────┘
```

All docks are `QDockWidget`s: floatable, tabbable, hideable, with the
layout saved/restored via `QSettings` and `Window ▸ Reset layout` as
the way back. The named presets ("Modelling", "Analysis") were not
built; which docks a first run opens is a
[TODO.md](TODO.md) entry.

### Interaction modes

A mode is a small state machine (`on_click`, `on_drag`, `on_key`,
`on_hover`) registered in `viewport/modes.py` — one module rather than
the package the plan drew, because five modes did not need one — owning
its own status-bar hint and cursor. v1 modes: **Select** (default),
**Add atom**, **Add bond**, **Measure**, **Move**.

Mouse (VTK trackball, matching VESTA): left-drag rotate, scroll zoom,
middle-drag (or shift+left) pan, right-drag dolly, double-click centre
on atom, `Ctrl`/`Cmd`+click add to selection, drag a rubber band to box-
select, `F` fit to window, keys `1/2/3` to look down a/b/c.

---

## 8. Rendering

`SceneModel` is pure numpy — trivially testable and snapshot-comparable:

```python
positions (M,3) float32 | radii (M,) | colors (M,3) uint8 | instance_id (M,)
bond_starts/ends (K,3)  | bond_radii | bond_colors (split at midpoint into
two half-bonds so each half takes its atom's colour) | cell_edges | labels
```

* Atoms → `vtkGlyph3DMapper` with a sphere source, scaling from the
  radius array, colouring from the colour array — one actor for the
  whole structure, so 10⁵ atoms stay interactive.
* Bonds → glyphed cylinders oriented by a vector array (or
  `vtkTubeFilter` polylines for the wireframe/line style).
* Cell → `vtkPolyData` line set for the box plus a, b, c axis labels;
  optional extra cells drawn faintly.
* Polyhedra → coordination polyhedra as convex hulls per central atom
  (VESTA's signature style), semi-transparent, colour from centre atom.
* Overlays: orientation axes widget, scale bar, element legend, depth
  cueing/fog toggle, perspective ⇄ orthographic, user-set clipping slab.
* Picking uses `vtkHardwareSelector` on the glyph mapper and maps the
  returned point ids through `instance_id` → `(site_idx, image, cell)`.

**Display range** (`Cell ▸ Display Range…`) is a view setting, not a
structural change: `x/y/z` from −1…2 etc., with VESTA-style boundary
options — *show atoms in the range*, *include atoms whose bonds cross
the boundary*, *complete molecules crossing the boundary*.

---

## 9. Selection system

`Selection` holds sets of atom instance ids, bond ids, and (later)
polyhedra, plus a `focus` for the inspector. Selection sources:

* **Picking** — click / shift-click / rubber band / lasso later.
* **By element** — one click per element chip in the Selection dock.
* **By connectivity** — expand to bonded neighbours (1 shell / n shells
  / whole fragment/molecule); "select molecule" is a BFS over the bond
  graph, PBC-aware, and flags infinite (framework) connectivity.
* **By distance** — everything within r Å of the current selection, with
  optional whole-molecule completion.
* **By symmetry** — the full orbit of the selected sites.
* **By property/query** — a small parser over a predicate registry:
  `element in [Fe, Ni] and occupancy < 1 and coordination >= 4 and z > 0.5`.
  Predicates are registered functions, so future modules can add
  `void_radius > 3` or `refined_flag == True` without touching the parser.
* Boolean ops (add/subtract/intersect/invert), plus **named saved
  selections** stored in the project file.

---

## 10. Feature map (your requirements → where they live)

| # | Requirement | Implementation |
|---|---|---|
| 1 | top bar, left file bar, main window | §7 layout; `mainwindow.py`, `docks/filetree.py` |
| 2 | CIF import/export, minimal export + note | `io/cif_reader.py` (gemmi), `io/cif_writer.py` — writes cell, symmetry ops, `atom_site` loop (label, type, x, y, z, occupancy, Uiso) and a `_computing` / comment line naming the app + version |
| 3 | macOS + Windows | §13 packaging |
| 4a | add atom (type, x/y/z, occupancy) | `AddAtom` command + Add-Atom mode + dialog with frac/cart toggle |
| 4b | click two atoms → bond | Add-Bond mode → `AddBond` (records the PBC image so cross-boundary bonds are correct) |
| 4c | click to select → info / delete / change type | picking → Inspector dock (element, label, frac+cart, occupancy, Uiso, charge, Wyckoff, site symmetry, neighbours with distances) with inline edit, `Del`, and an element combo |
| 4d | determine symmetry with tolerance | `Symmetry ▸ Find Symmetry…`, spglib `symprec`/angle tolerance, live preview of the group as the tolerance slider moves |
| 4e | set space group | `SetSpaceGroup` + picker dialog (number/HM/Hall, setting + origin choice, search box) |
| 4f | drop to P1 | `ReduceToP1` |
| 4g | build supercell | `BuildSupercell` — n₁×n₂×n₃ *and* general integer 3×3 matrix, with symmetry handling (result is P1 unless the group survives) |
| 5 | UFF module | §11 |
| 6 | drag to orbit, scroll to zoom | §7 mouse map |
| 7 | window to move atoms/components | Move dock: numeric translate (frac/cart/along a,b,c), rotate about axis/centroid/point, mirror, invert, snap-to-value; symmetry-aware when enabled. The on-screen gizmo was not built — the numeric panel covered it |
| 8 | select by type, connectivity, … | §9 |
| 9 | background/atom colours, draw styles | Style dock + Preferences: per-element colour+radius overrides, palettes (VESTA/CPK/Jmol), solid/gradient background, ball-and-stick / stick / wireframe / space-filling / polyhedral, per-selection style overrides |
| 10 | change unit cell size | `Cell ▸ Edit Unit Cell…` with the two semantics made explicit: *keep fractional* (atoms deform with the cell) or *keep cartesian* (atoms hold position); also apply a strain tensor |
| 11 | how many cells shown | `Cell ▸ Display Range…` (§8) |
| 12 | undo/redo, copy/paste | §6 |
| 13 | extra features | §12 |
| 14 | room to grow | §3 principle 3, §14 plugin API |

---

## 11. UFF module

**Scope.** Universal Force Field (Rappé et al., *JACS* 1992, 114,
10024) — bond stretch, angle bend, torsion, inversion, van der Waals
(LJ 12-6), and optional electrostatics; periodic under PBC; energies,
analytic forces, and (phase 2) stress for cell relaxation.

**Pipeline**

```
Structure → P1 cell → bond graph → UFF atom typing → parameter assignment
         → term list (bonds/angles/torsions/inversions/pairs)
         → Calculator.compute(positions, cell) → E, F, σ
         → Optimizer (FIRE or L-BFGS) → trajectory → ApplyOptimizedGeometry command
```

**Atom typing** is the part that actually decides whether results are
sane, so it gets its own module, its own tests, and a UI: the typer
infers hybridisation/aromaticity/coordination from the bond graph and
geometry, assigns a 5-character UFF type (`C_3`, `C_R`, `N_2`, `O_3_z`,
`Fe6+2`, …), and the Force Field dock shows a **per-atom type table
where the user can override any assignment** before running. Overrides
are stored in `Site.props["uff_type"]` and survive save/load.

**Terms** (each a module with `energy(...)` and `gradient(...)`, tested
against finite differences):

* Bond: harmonic, `r_ij = r_i + r_j + r_BO − r_EN`, `k_ij = 664.12 Z*_i Z*_j / r_ij³`.
* Angle: general cosine expansion `K(C₀ + C₁cosθ + C₂cos2θ)`, with the
  periodic special cases for linear, trigonal-planar, square-planar and
  octahedral centres.
* Torsion + inversion (sp² centres), with UFF's rules for the barrier.
* van der Waals: LJ 12-6, geometric combining rules, cutoff + neighbour
  list, optional tail correction.
* Coulomb: off by default; charges from the CIF, user-entered, or **QEq**
  charge equilibration; Ewald summation under PBC.

**Optimisation** — FIRE (robust, cheap) and L-BFGS; constraints: freeze
selected atoms, freeze cell, fix a lattice parameter, **preserve space
group** (project forces onto the symmetry-allowed subspace); optional
variable-cell relaxation via numeric stress first, analytic later.

**UI/UX** — runs in a `QThread` worker: live geometry updates in the
viewport, live energy/max-force plot, pause/cancel, then one undoable
`ApplyOptimizedGeometry` command. A results panel gives the per-term
energy breakdown, max/RMS force, and any atoms whose typing was
uncertain.

**Validation** — regression tests against published UFF energies for
small molecules (benzene, water, cyclohexane), a framework lattice
constant after relaxation, and gradient-vs-finite-difference checks on
every term. The lattice-constant regression is **MFU-4l**, not
MOF-5/IRMOF-1 as first written; see [ROADMAP.md](ROADMAP.md) § 8 for
why. The cross-check against ASE+OpenBabel is not built.

**Extensibility** — everything sits behind `ff/api.py::Calculator`, so
LAMMPS, GULP, xTB or an MLIP (MACE/CHGNet) drop in later as alternative
engines with no GUI changes.

---

## 12. Extra features worth building (VESTA/Materials Studio parity)

Ranked by value-per-effort; all are additive under the architecture
above. An entry is deleted from this list when it ships — the
measurement table, the structure info panel, labels, recent files and
drag-and-drop, merge duplicates, `.xtalproj`, tabs, the polyhedral
style, the cell transformation dialog and the Zeo++ bridge were all
here and are all in. What is below has not been built, and what has a
schedule has it in [ROADMAP.md](ROADMAP.md).

**High value, cheap**
* Bond-length/angle listing and coordination table, exportable to CSV.
* Validation panel: overlapping atoms, occupancy sums > 1, odd valences.
* Named saved selections, stored in the project — §9 promises them and
  the project file does not carry them yet.
* Image export at a chosen resolution, with a transparent background:
  `File ▸ Export image` writes what is on screen at the size it is on
  screen, which is not a figure for a paper.
* A sample structure library — the CIFs are in `resources/samples/`
  and nothing in the application opens them.
* **Overlay/compare two structures** in one viewport.

**High value, moderate**
* Embedded Python console driving the same command API (scriptability).
* Symmetry-mode editing of Wyckoff free parameters only.
* Slab/surface builder: cut along (hkl), set thickness + vacuum.
* Molecule/fragment library for pasting common ligands — scheduled, as
  part of [ROADMAP.md](ROADMAP.md) phase N.
* Distance-based site disorder tools (split sites, partial occupancy view).

**Later (already anticipated by the plugin API)**
* PXRD simulation (structure factors, Lorentz-polarisation, profile
  functions) — then import experimental XRD to overlay, then Rietveld/
  Pawley refinement on top of the same machinery.
* Electron/neutron diffraction patterns and reciprocal-space views.
* Volumetric data (CHGCAR/CUBE) import + isosurfaces (VESTA's other
  signature feature) with the same glyph/scene infrastructure.
* SHELX `.ins`/`.res` read/write for refinement round-trips.
* Symmetry-mode analysis / distortion decomposition.
* Other experimental data overlays (PDF, EXAFS, IR/Raman from a Hessian).

---

## 13. Packaging and distribution

The sketch below is the shape of it; the buildable version of this
section -- what the frozen app needs changed before any spec is
written, what goes in the bundle and what does not, and the order --
is [PACKAGING.md](PACKAGING.md).

* **Build**: PyInstaller (onedir) with a spec per platform in
  `packaging/`. VTK and PySide6 both need explicit hidden imports and
  data collection — the spec files handle this once.
* **macOS**: `.app` bundle with `Info.plist` (document types: `.cif`,
  `.xtalproj`), packaged into a DMG; `--target-arch universal2` if the
  wheels allow, otherwise separate arm64 and x86_64 builds. Ad-hoc
  signing plus notarisation instructions in `docs/` (unsigned builds
  need the right-click → Open dance).
* **Windows**: onedir + Inno Setup installer (file associations, Start
  menu entry); no console window (`--windowed`).
* **CI**: GitHub Actions matrix — `macos-14` (arm64), `macos-13`
  (x86_64), `windows-latest` — runs `pytest` headless, then builds and
  uploads artifacts on tags. Version from `setuptools-scm` git tags, as
  in your existing project.
* Core stays `pip install`-able without the GUI extras
  (`pip install crystal-builder` → CLI + library; `[gui]` adds
  PySide6/VTK), so headless scripting and CI work everywhere.

---

## 14. Extension API (making #14 real)

Four registries, all discovered from in-tree modules and from
`importlib.metadata` entry points under `crystal_builder.plugins`:

```python
FORMATS.register(Reader/Writer)      # new file formats (SHELX, CHGCAR, …)
STYLES.register(DrawStyle)           # new draw styles
CALCULATORS.register(Calculator)     # new force fields / engines
ANALYSES.register(Analysis)          # anything with: inputs → result + optional panel
```

An `Analysis` declares its name, the parameters it needs (rendered
automatically into a form), whether it runs in a worker thread, and how
it presents results (table / plot / overlay actor). A PXRD module is
then: `analysis/pxrd.py` (pure numpy, testable headless) + a registration
line + optionally a custom result widget. **No existing file changes.**
`docs/extending.md` will carry a worked example of exactly this.

---

## 15. Testing

* **Core (headless, the bulk)**: lattice round-trips; frac⇄cart against
  known cells; CIF read→write→read fixed points on a corpus of real CIFs
  (including partial occupancy, non-standard settings, rhombohedral
  groups); spglib detection on structures of known symmetry at several
  tolerances; supercell atom counts and density invariance; bond
  perception across PBC.
* **Command invariants**: property-style test — apply a random sequence
  of commands, undo everything, assert the structure equals the original
  (deep compare); redo everything, assert it equals the post-sequence
  state.
* **Force field**: per-term analytic gradient vs finite difference;
  published energies for reference molecules; optimisation reduces energy
  monotonically under FIRE; symmetry-constrained relaxation preserves the
  space group.
* **Scene builder**: `SceneModel` array shapes/values for known inputs —
  catches rendering regressions without a GPU.
* **GUI**: `pytest-qt` for dock logic, dialogs and the action registry;
  no tests depend on an actual GPU render.

---

## 16. Execution roadmap

Each phase ends with something runnable and a green test suite.

| Phase | Deliverable | Contents |
|---|---|---|
| **0. Skeleton** ✅ | `pip install -e .` works, CI green | repo, pyproject, ruff/pytest config, GH Actions, `elements.py`, `lattice.py`, `site.py`, `structure.py` + tests |
| **1. Crystallography core** ✅ | CLI can read a CIF, print symmetry, write a CIF | `cif_reader`/`cif_writer`, `symmetry.py` (detect / set / P1), `neighbors`, `bonding`, `supercell`, `properties`, `cli.py` |
| **2. App shell + viewport** ✅ | window opens a CIF and shows ball-and-stick you can orbit | `mainwindow`, file-tree dock, `Document`, `SceneModel`+builder, VTK widget, camera, cell box, style switching |
| **3. Selection & inspection** ✅ | click atoms/bonds, read and edit their properties | picking, Select mode, Inspector dock, structure tree, atom table, delete, change element |
| **4. Editing & undo** ✅ | build a structure by hand | `CommandStack`, Add-Atom / Add-Bond modes + dialogs, Move dock (numeric; no on-screen gizmo was built), copy/paste, full undo/redo wiring |
| **5. Symmetry & cell** ✅ | full symmetry workflow | Find Symmetry dialog with tolerance, space-group picker, reduce-to-P1, supercell, cell edit, cell transform, display range, boundary options |
| **6. Appearance & analysis** ✅ | looks like VESTA | all draw styles incl. polyhedra, colour/radius editors, background, labels, legend, projection modes, measurements, image export, project save/load |
| **7. UFF** ✅ | single-point + optimisation from the GUI | params, typer (+ override table), terms, calculator, FIRE/L-BFGS, worker + live plot, constraints, validation suite |
| **8. Ship** | signed-ish DMG + Windows installer | PyInstaller specs, icons, file associations, CI release job, user docs |
| **9. Prove extensibility** | a plugin added without touching core | PXRD simulation module as the first registry-based `Analysis`, plus `docs/extending.md` |

Phases 0–1 are pure library work and are worth doing carefully — they
set every interface the rest of the app leans on. Phase 4 (commands) must
land before phase 5, or symmetry operations get retrofitted into
undo/redo later, which is painful.

Phase 8 has not been done: `packaging/` is empty, and there is no
build -- [PACKAGING.md](PACKAGING.md) is the plan for it. Phase 9 has been half-answered from an unexpected direction --
`xtal/modules/` is the registry [ROADMAP.md](ROADMAP.md) phase D built,
and Zeo++ and DFTB+ went in through it and through
`crystal_builder.plugins` without touching an existing file, which is
the claim phase 9 was to prove. What it still owes is
`docs/extending.md` and a plugin shipped from outside the tree.

Work that came out of using the application, and has not been scheduled
into a phase yet, lives in [TODO.md](TODO.md); the plan for delivering
it -- phases A to N, and where phase 8 above falls among them -- is
[ROADMAP.md](ROADMAP.md).

---

## 17. Known footguns

1. **Space-group settings.** Same group number, different origin/axes →
   silently wrong structures. Always carry the Hall symbol; never
   reconstruct operations from a number alone.
2. **Symmetry edits producing near-duplicates.** Every symmetry-changing
   operation must run a merge-with-tolerance pass and report what it
   merged.
3. **Bonds across periodic boundaries.** A bond is (i, j, image); storing
   only (i, j) breaks on supercells and display-range changes.
4. **Editing symmetry images.** Decide (and show in the UI) whether an
   edit propagates to the orbit or drops the structure to P1 — never
   guess silently.
5. **VTK + PySide6 packaging.** Version-pin both; the Qt-VTK interactor
   is the most brittle part of the build. Pin early, upgrade deliberately.
6. **UFF atom typing** is where wrong answers come from, not the math.
   Expose the assignments, allow overrides, and warn on low-confidence
   types (unusual coordination, metals).
7. **Cell edits are ambiguous** — always ask "keep fractional" vs "keep
   cartesian" rather than picking one.
