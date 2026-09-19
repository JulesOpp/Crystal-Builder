# Are the workflows and code paths well factored?

*Architecture and maintainability review of Crystal Builder v0.2.1 (main, clean).
Topic: factoring of the five end-to-end workflows, the registries, error
conventions, the settings layer, and `mainwindow.py`.*

**Summary (5 lines).**
1. The five workflows are well factored at the seams that matter: the headless wall holds under measurement (116 `xtal` modules imported, zero Qt/VTK reached), the three-way refresh split is honoured everywhere and costs 0.90 / 2.09 / 2.39 ms on MFU-4l, `ruff check .` is clean, and 19 of 3593 functions exceed complexity 10.
2. The recurring fault is not tangle but **the same decision written down twice**, and every pair I checked has drifted.
3. Worst: action enablement is decided in `_refresh_shell` and again in `_on_selection_changed`, and 7 of 12 shared actions disagree (probe output below).
4. Next: the run-folder lifecycle exists in four places and the Force Field path shares none of it with the module path, so the CLI cannot file a build the way the window does — and that filing policy lives in a `QObject` in `xtalapp/`.
5. `mainwindow.py` is large but healthy; a concrete 821-line, three-collaborator split is costed below, and what stops it today is that `menus.build_actions` binds all ~200 actions to `window.<method>`.

Probes are in `review/probes/` (`longfuncs.py`, `dupes.py`, `similarity.py`,
`wall.py`, `sections.py`, `delegators.py`, `test_enable_drift.py`,
`test_refresh_cost.py`, `test_playback_edit.py`).

---

## Measurements first

```
$ .venv/bin/python -m ruff check . --statistics
All checks passed!                        # E,F,W,I,UP,B — 0 findings, 0 by rule
```

```
$ .venv/bin/python review/probes/longfuncs.py 35
total functions/methods: 3593
over 50 lines: 121        over 100 lines: 11
  385 lines / 10 branches  xtalapp/menus.py:107 build_actions
  244 /  1   xtal/ff/uff/params.py:231 _rows          (a parameter table)
  185 / 11   xtalapp/docks/ff_panel.py:139 ForceFieldDock.__init__
  170 / 31   xtalapp/viewport/builder.py:85 build_scene
  158 / 37   xtal/analysis/topology.py:871 _walks
  138 /  8   xtalapp/dialogs/scan.py:370 ScanDialog.__init__
  113 / 14   xtalapp/mainwindow.py:1483 MainWindow._refresh_shell
```

```
$ .venv/bin/python -m ruff check xtal xtalapp --select C901   # not the project's config
19  C901  complex-structure        # 19 functions over complexity 10, in ~75 kLOC
```

Long is not the same as complicated here: `_refresh_shell` is 113 lines and 14
branches — a flat list of `set_enabled` calls, not a thicket. The only spine
methods of the five workflows that C901 flags are `run_module_action` (12) and
`Document._restore_session` (13).

Largest files (excluding vendored PORMAKE):
`xtalapp/viewport/vtk_scene.py` 2181, `xtalapp/document.py` 2054,
`xtalapp/mainwindow.py` 1818, `xtalapp/viewport/builder.py` 1445,
`xtal/ff/optimize.py` 1439, `xtal/analysis/topology.py` 1426.

---

# Findings

## 1. `[important]` The action-enablement rule is written twice, and the copies disagree

**What.** `MainWindow._refresh_shell` and `MainWindow._on_selection_changed` both
decide the enabled state of the same twelve actions. Only `_refresh_shell`
consults `document.is_playing`. Whichever ran last wins.

**Where.** `xtalapp/mainwindow.py:1529-1546` (in `_refresh_shell`) and
`xtalapp/mainwindow.py:1269-1280` (in `_on_selection_changed`).

```python
# _refresh_shell, mainwindow.py:1535
self.actions_.set_enabled(
    ["change_element", "cut", "duplicate", "mark_connection_points"],
    has_selection and editable)          # editable = has_document and not is_playing

# _on_selection_changed, mainwindow.py:1273
self.actions_.set_enabled(
    ["change_element", "select_same", "expand_bonded",
     "expand_fragment", "expand_orbit", "copy", "cut",
     "duplicate", "mark_connection_points"],
    bool(document.selection.atoms))      # is_playing is not consulted
```

**Evidence.** `review/probes/test_enable_drift.py` builds a window, opens quartz,
selects two atoms, makes the document report `is_playing`, then calls the two
methods in turn and diffs the enabled state:

```
$ .venv/bin/python -m pytest -q review/probes/test_enable_drift.py -s
_refresh_shell vs _on_selection_changed, while playing:
  add_centroid             shell=False  selection=True
  change_element           shell=False  selection=True
  cut                      shell=False  selection=True
  delete_selection         shell=False  selection=True
  duplicate                shell=False  selection=True
  mark_connection_points   shell=False  selection=True
  merge_atoms              shell=False  selection=True
```

Seven of twelve. `review/probes/test_playback_edit.py` shows the consequence is
reachable and passes:

```
$ .venv/bin/python -m pytest -q review/probes/test_playback_edit.py
1 passed          # the action is enabled, and what it calls raises PlaybackActive
```

So with a trajectory open, clicking an atom re-enables Cut / Duplicate / Delete /
Change element, and pressing one reaches `Document.run`'s backstop — an exception
into the log rather than a greyed entry. (`Document.run`,
`xtalapp/document.py:447`, is exactly the "backstop that makes that a rule rather
than a habit" its own docstring promises; it is doing its job, which is why this
is a factoring finding and not a crash.)

**Why it matters.** This is the file's own recorded failure mode repeating: the
comment at `mainwindow.py:1264-1268` documents an earlier bug of precisely this
class ("It used to be listed here *and* in the atoms-only call below, and the
second call wins: with a bond selected and no atom, Del was greyed out"). The
fix at the time was to patch one of the two copies rather than to remove the
second copy, so the same trap was left armed for the next condition added. Any
new enabling condition — a read-only document, a locked structure — has to be
remembered in two places that no test compares.

**What a fix would look like.** One function that takes `(document, is_playing,
worker_running)` and returns the complete `{action: bool}` map; both handlers call
it and apply the whole map. A test that calls the two entry points in either order
and asserts the same map is three lines.

---

## 2. `[important]` The run-folder lifecycle exists in four places; the two calculation paths share none of it

**What.** "Open a run folder, write the header, run, close the log, say how it
ended" is implemented four times, and the Force Field path and the module path
share no part of it.

**Where.**

| Path | Opens the run | Closes it |
|---|---|---|
| Modules (GUI) | `xtal/modules/record.py:25 open_run`, called from `xtalapp/module_runner.py:166` | `xtal/modules/record.py:47 close_run`, from `module_runner.py:265, 295` |
| Modules (CLI) | the same `open_run`, `xtal/cli.py:437` | the same `close_run`, `xtal/cli.py:448, 451` |
| Force Field (GUI) | `xtalapp/docks/ff_panel.py:593 _open_run` | `ff_panel.py:821 _close_run` **and again** `ff_panel.py:848 _on_failed` |
| Force Field (CLI) | `xtal/cli.py:265 _recorder` | inline in `cmd_optimize` / `cmd_energy` |

**Evidence.** The two Force Field openers are a copy, comment included:

```
$ diff <(sed -n '276,297p' xtal/cli.py) <(sed -n '605,618p' xtalapp/docks/ff_panel.py)
-    folder = entry.next_run(args.engine, kind)
-    recorder = RunRecorder(
-        folder, structure, calculator, engine=args.engine,
-        options=options, record_trajectory=(kind == "optimise"))
-    recorder.header(kind.replace("-", " "))
-    if "types" in engine.provides:
-        # UFF's typing table.  Writing it for an engine that has no
-        # atom types would put a page of somebody else's answer in
-        # the middle of this one's log.
-        recorder.typing()
+            folder = entry.next_run(self.engine_name(), kind)
+            recorder = RunRecorder(
+                folder, document.structure, calculator,
+                engine=self.engine_name(), options=self.options(),
+                record_trajectory=(kind == "optimise"))
+            recorder.header(kind.replace("-", " "))
+            if self._engine_provides("types"):
+                # UFF's typing table.  Writing it for an engine that
+                # has no atom types would put a page of somebody
+                # else's answer in the middle of this one's log.
+                recorder.typing()
+            recorder.topology()
```

The module half is done right — `xtal/modules/record.py` is headless and both
`xtalapp/module_runner.py` and `xtal/cli.py` call it. The Force Field half has no
such module: the sequence lives in a `QDockWidget` (`ff_panel.py:593`) and is
duplicated into the CLI.

**Why it matters.** `xtal/ff/record.py` already contains everything that is
crystallography (`RunRecorder.header/typing/topology/step/result`); what is
duplicated is only the *policy* — which engine's name the folder is filed under,
whether to write a typing table, what `kind` means for trajectory recording.
Adding a fifth artefact to a force-field run means editing a dock and the CLI and
remembering the failure path in the dock is written twice.

**What a fix would look like.** An `xtal/ff/record.py` pair mirroring
`xtal/modules/record.py` — `open_run(entry, engine, kind, options, structure,
calculator) -> RunRecorder | None` and `close_run(recorder, result, final,
error)` — with the dock and the CLI reduced to calling it.

---

## 3. `[important]` Workspace filing policy lives in the GUI, so the CLI files a build differently

**What.** The rule CLAUDE.md states as an invariant — "A build is filed by
`ModuleRunner._file_build`: one entry, **one** CIF written from the structure, the
run's poorer copy dropped, the run moved underneath" — is 90 lines of filesystem
policy implemented in a `QObject` in `xtalapp/`.

**Where.** `xtalapp/module_runner.py:497 _file_build`, `:542
_drop_the_runs_copy`, `:561 _move_run_under`. The last one does
`shutil.move(str(source), str(entry.path))` and `placeholder.rmdir()` —
`module_runner.py:581-589`.

**Evidence.** `xtal/cli.py:405 cmd_run` is the same workflow without a window:

```python
# xtal/cli.py:432
entry = (workspace.add_structure(args.file) if args.file
         else workspace.add_document(module.label))
folder = module_record.open_run(entry, module, action, params, structure)
...
module_record.close_run(folder, result)          # and nothing else
```

There is no `_file_build`, no `_drop_the_runs_copy`, no `_move_run_under`. So
`xtal run mof.build --workspace W` leaves the placeholder entry named after the
*module*, holding PORMAKE's own poorer CIF and the run — precisely the arrangement
`_file_build`'s docstring exists to prevent ("a second, poorer copy under a folder
name of its own is a question about which one is real"). `xtal/workspace.py` (769
lines, "the folder all the work is in") has `new_document`, `add_structure` and
`next_run`, but nothing to move a run under an entry.

A second cost: the ten tests that hold this rule
(`tests/test_mof_ui.py:185-357`, `test_a_build_files_its_run_under_the_thing_it_built`
and its neighbours) all need a `QMainWindow` to test a rule about directory layout.
No test file references `_file_build` or `_move_run_under` by name.

**Why it matters.** This is the clearest layering violation in the calculation
path, and it is the one that makes "the CLI writes exactly what the window writes"
(`xtal/cli.py:266`) untrue for builds.

**What a fix would look like.** `Workspace.adopt_build(structure, run_folder) ->
Entry` in `xtal/workspace.py`, called by `ModuleRunner` and by `cmd_run`; the
dock keeps only the log re-pointing, which is genuinely GUI.

---

## 4. `[important]` Crystallography leaked into `xtalapp/`: the MOF preview perceives its own bonds

**What.** `xtalapp/dialogs/mof_preview.py:_draw_bonds` decides which atoms are
bonded with its own distance rule, its own tolerance and its own dummy handling,
instead of calling `xtal.core.bonding`. Its docstring claims parity ("the same
rule the application's own perception starts from") and the numbers say otherwise.

**Where.** `xtalapp/dialogs/mof_preview.py:229-252`.

```python
radii = [1.0 if (i in connections or s == "X") else el.covalent_radius(s) ...]
limit = radii[i] + radii[j] + 0.45
```

versus `xtal/core/bonding.py:83-101`, `d <= (r_i + r_j) * 1.15`, plus
`BondRules.allows()` which refuses metal–metal.

**Evidence.**

```
$ .venv/bin/python -c "..."          # BondRules().cutoff vs the preview's rule
C-C:   core max 1.679 A,  mof_preview 1.910 A,  allows=True
C-H:   core max 1.196 A,  mof_preview 1.490 A,  allows=True
Zn-O:  core max 2.162 A,  mof_preview 2.330 A,  allows=True
Zn-Zn: core max 2.806 A,  mof_preview 2.890 A,  allows=False
Cu-Cu: core max 3.036 A,  mof_preview 3.090 A,  allows=False
```

The preview draws C–C bonds up to 0.23 Å longer than the application will, and
draws Zn–Zn and Cu–Cu bonds the application refuses outright.

**Why it matters.** CLAUDE.md's layout table says `xtalapp/` "Holds no
crystallography of its own", and this is the one place it plainly does. The user
picks a building block from a picture whose bonding is not the bonding the block
will have once it is built.

**What a fix would look like.** `bonding.perceive` over a one-molecule
`Structure` built from the block, or a `BondRules.pairs_within(positions,
symbols)` helper in the core that the preview calls. The rule stays in one file
and the picture matches the build.

*Same direction, smaller:* `xtalapp/viewport/modes.py:306 bond_distance` defines
the ideal placement distance for a new atom (`r_a + r_b`) in the GUI. It is
correct and documented, but it is a chemistry constant living in a mouse-mode
module; `xtal.core.bonding` is where the next person will look for it.

---

## 5. `[important]` The headless-wall test is tight in one direction and half-measured in the other

**What.** `tests/test_core_is_headless.py` has two tests. The AST one is a good
guard. The runtime one proves much less than it appears to, and there is no test
at all for crystallography leaking the other way.

**Where.** `tests/test_core_is_headless.py:32` and `:39`.

**Evidence.**

- `test_no_gui_imports_anywhere_in_the_core` walks every `.py` under `xtal/` and
  catches function-level imports as well as module-level ones. Tight. It misses
  only `importlib.import_module("PySide6")`-style dynamic imports, and
  `FORBIDDEN` omits `PySide2`, `qtpy`, `tkinter`, `wx`.
- `test_importing_the_core_does_not_pull_in_qt_or_vtk` runs `import xtal` in a
  subprocess. `xtal/__init__.py` imports four core modules (`lattice`, `site`,
  `spacegroup`, `structure`). So the *transitive* half of the invariant — a
  third-party dependency of, say, `xtal/analysis/pxrd.py` pulling matplotlib in —
  is untested for 112 of the 116 modules.
- `review/probes/wall.py` imports all 116 and checks `sys.modules`:

```
MODULES 116
FAILED []
FORBIDDEN_LOADED []
$ time .venv/bin/python -c "import every xtal module"
116 ok
real  0m0.472s
```

The invariant **does** hold across the whole core today, and proving it costs
0.47 s in one subprocess.

- The reverse direction is unguarded. `xtalapp/` imports 40 distinct `xtal`
  modules (`xtal.core` 31 times, `xtal.commands` 13, `xtal.workspace` 12), which
  is what a thin shell should look like — but nothing stops finding 4 above, and
  nothing would have stopped it.

**What a fix would look like.** Parametrise the subprocess test over every
`xtal.*` module (one process, 0.5 s). For the other direction, a test that
asserts `xtalapp/` calls no bare-distance chemistry is hard to write; a cheaper
guard is to assert that `el.covalent_radius` is imported in `xtalapp/` only by
`viewport/view_settings.py` (a radius to *draw*), which is a one-line allow-list
that would have caught `mof_preview`.

---

## 6. `[important]` The two external-binary engines are a copy of each other

**What.** DFTB+ and xTB both mean "write an input, launch a binary, read forces
back", and they implement it twice rather than sharing a base.

**Where.** `xtal/ff/dftb/calculator.py` (473 lines) and
`xtal/ff/xtb/calculator.py` (540 lines).

**Evidence.**

```
$ .venv/bin/python review/probes/similarity.py xtal/ff/dftb/calculator.py xtal/ff/xtb/calculator.py
xtal/ff/dftb/calculator.py (377) vs xtal/ff/xtb/calculator.py (413):
  119 identical lines (32% of the smaller); runs>=5: [19, 10, 9, 8, 7, 7, 6, 5]
```

Shared method names: `__init__ _launch _read _resolve _why available build close
compute n_atoms summary write`. The `_Log` class at `dftb/calculator.py:439` and
`xtb/calculator.py:504` differ only in one word of a docstring. The `__init__`
prologue is a third copy in `mace/calculator.py:360` (found by
`review/probes/dupes.py`).

A live drift in the copies: the registry entry point.

```python
# dftb/calculator.py:458      known = {p.name for p in OPTIONS}          # registry Params
# xtb/calculator.py:523       known = {f.name for f in fields(XTBOptions)}   # dataclass fields
# mace/calculator.py:454      known = {f.name for f in fields(MACEOptions)}
# uff/calculator.py:620       (no filtering at all — an unknown key is a TypeError)
```

Four engines answer "which keyword arguments do I accept?" three different ways.
`Engine.coerce()` already exists (`xtal/ff/registry.py:68`) and `Engine.__call__`
(`:71`) already centralises the one decision engines must not each make (holding
dummy markers back) — with a docstring explaining exactly why. It does not coerce.

**Why it matters.** The add-module skill promises a new engine touches no existing
file; today a new external engine copies 120 lines and has to guess which of the
three option-filtering idioms is the house style.

**What a fix would look like.** `Engine.__call__` calls `self.coerce(options)`
before `build`, which deletes the filtering from three engines; and an
`ExternalCalculator` base in `xtal/ff/api.py` holding `n_atoms`, `summary`,
`calls`/`seconds` accounting, the positions/matrix guard, and `_Log`.

---

## 7. `[important]` `mainwindow.py`: where the 1818 lines are, and what stops them moving

The file is not unhealthy — 30 of its 149 methods are already one-line forwards to
extracted collaborators, `__init__` is 86 lines of assembly, and
`menus.py`/`layout.py`/`documents.py`/`workspace_shell.py`/`module_runner.py` have
already been carved off. But it is still touched by nearly every change, and the
groups are separable.

```
$ .venv/bin/python review/probes/delegators.py xtalapp/mainwindow.py
xtalapp/mainwindow.py: 149 methods, 30 are a single forward to self.<collaborator>
  self.document_set        17   self.workspace_shell     10
  self.module_runner        2   self.status_label         1
```

Method groups, measured (`review/probes/sections.py` and an AST grouping):

| Group | Lines | Methods | Where it would go |
|---|---:|---:|---|
| refresh / enable | **345** | 17 | `xtalapp/shell_state.py` — `_refresh_shell`, `_update_ui`, `_on_structure_changed`, `_on_view_changed`, `_on_selection_changed`, `_refresh_plane_actions`, `_sync_bond_type_actions`, `_refresh_module_actions`, `_refresh_insert_molecule`, `_rebuild_element_menu`, `_update_history_actions`, `_measurable`, the `_on_*_changed` handlers |
| edit / select / measure verbs | **356** | 34 | `xtalapp/edit_actions.py` |
| symmetry & cell verbs | **120** | 15 | `xtalapp/symmetry_actions.py` (takes `_run`/`_report`/`_announce`, their shared prologue) |
| view verbs | 143 | 14 | could join `style_panel`/`layout` |
| pure delegation | 86 | 32 | stays (the facade) |
| preferences / help / about / log | 114 | 10 | `xtalapp/help_about.py` |
| quit / close / drag-drop | 71 | 7 | stays (it is `QMainWindow` behaviour) |
| unassigned (`__init__`, modes, context menus, properties) | 210 | 20 | stays |

The first three groups are 821 lines. Extracting them the way `DocumentSet` and
`WorkspaceShell` were extracted leaves `mainwindow.py` around 1000 lines plus ~40
new forwarder lines.

**What stops it today.** `xtalapp/menus.py:107 build_actions` is 385 lines of
`add("name", "&Label", window.method, ...)` — every action is bound to an
attribute of the window, so a method that moves must leave a forwarder behind.
That is exactly the price the existing extractions paid (the 30 forwarders above),
so the pattern is established rather than unknown. Two smaller frictions:
`_refresh_shell` reads twelve dock attributes plus `actions_`, `status_label`,
`selection_label`, `cell_spins`, `element_menu`, `bond_type_menu` — a collaborator
would hold `self.window`, as `WorkspaceShell` does. And tests barely couple to
privates (`window._refresh_shell` twice, `window._update_ui` once,
`window._build_modules_menu` twice across 144 test files), so the extraction is
not a test rewrite.

**Secondary evidence that the file has outgrown its own organisation:** the
section banners no longer describe their contents. `display_range_dialog`, `_run`
(the symmetry/cell operation runner), `_on_selection_changed`,
`_sync_bond_type_actions` and `_refresh_plane_actions` all sit under the
`#  MODULES` banner (`mainwindow.py:1174-1372`).

---

## 8. `[minor]` Three registries, five registration idioms, drifted APIs

**Where.** `xtal/ff/registry.py:94`, `xtal/modules/registry.py:215`,
`xtal/io/registry.py:48`, plus `xtalapp/viewport/styles.py:138` and
`xtalapp/viewport/modes.py:1089` (plain dicts with module-level `register`).

The three core registries are the same ~30-line skeleton written three times, and
they have drifted:

| | ENGINES | MODULES | FORMATS |
|---|---|---|---|
| unknown-name error | `ValueError` | `ModuleError` | `ValueError` |
| message names alternatives | yes | yes | **no** |
| `names()` | insertion order | sorted by `(order, label)` | **absent** |
| `__len__` | yes | yes | **absent** |
| `unregister` | **absent** | yes | **absent** |
| `__iter__` order | `(order, label)` | `(order, label)` | insertion |

`ModuleRegistry.unregister`'s docstring gives the reason it exists — "a registry
that can only grow leaks between test cases" — which applies unchanged to the
other two.

The *registration* idiom differs three ways as well:

```
xtal/ff/uff/calculator.py:661    ENGINES.register(Engine(...))      # import side effect
xtal/modules/__init__.py:57      forcefield.register(); dftb.register(); ...   # explicit
xtal/io/__init__.py:52           FORMATS.register(Format(...))      # inline in __init__
```

`xtal/plugins.py` is small, idempotent and failure-tolerant (`:63 load`), and says
"may register into any of the four registries" — but a plugin author has to
reverse-engineer which of the three shapes each one wants, and `.claude/skills/`
has an `add-module` skill and no `add-engine` or `add-format`.

**What a fix would look like.** One `Registry` generic in `xtal/params.py` (which
already holds what `Param` and `Availability` share between engines and modules)
that the three subclass for their extras.

---

## 9. `[minor]` The report block types are enumerated in three places, and the GUI dispatches with `isinstance`

**Where.** `xtal/modules/report.py:758 _BLOCKS` (a proper registry, used for
`save`/`load`), `report.py:710-738` (eight hand-written `@property` accessors, one
per type), and `xtalapp/docks/results.py:230 _render` — an eight-branch
`isinstance` chain.

```python
def _render(self, block):
    if isinstance(block, Table):     return _table_widget(block)
    if isinstance(block, Histogram): return _histogram_widget(block)
    ... eight in all ...
    return None
```

**Why it matters.** PLAN § 1.3 is "Registries, not `if/elif`", and this is the
place a plugin would most plausibly want to extend — a module that produces a new
kind of plot. Today that means three edits in two packages plus a widget.

**What a fix would look like.** A `{block class: widget factory}` dict in
`results.py` keyed by `type(block)`, populated where each widget is defined; and
`Report.tables`/`.curves`/… generated from `_BLOCKS`.

---

## 10. `[minor]` Small decisions made twice, each pair already drifted

These are individually cheap and collectively the strongest evidence for the
pattern.

- **Two `_resolved`, different failure behaviour.** `xtalapp/documents.py:60`
  returns `None` when a path cannot be resolved; `xtalapp/docks/workspace.py:259`
  returns the unresolved `Path`. Both answer "is this the same file"; one for the
  tab, one for the tree highlight.
- **Two readers of the engine panel.** `xtalapp/dialogs/scan.py:91
  panel_options` walks `ff_dock` then `dftb_dock`, prefers `dock.options()` when
  the engine matches and falls back to `dock.engine_forms[engine].values()`;
  `xtalapp/dialogs/dftb_run.py:34 panel_hamiltonian` looks only at `dftb_dock`
  and only at `engine_forms["dftb"]`. Same bargain (CLAUDE.md: "the same bargain
  `dftb_run.py` strikes"), two implementations, different answers. Both are
  `getattr`-chains with no interface — `scan.py` wraps its in
  `except Exception  # noqa: BLE001` (`scan.py:86`).
- **A Stop is recorded twice in one object.** `OptimizationWorker.__init__`
  (`xtalapp/workers.py:69-76`) holds both a `threading.Event` **and** a
  `xtal.modules.job.Cancellation`; `cancel()` sets three things
  (`workers.py:80-83`). `ModuleWorker` uses only the `Cancellation`. Any new
  stopping path has to remember both.
- **Three axis-tick formatters, one drifted.** `xtalapp/plot.py:37`,
  `xtalapp/histogram.py:57` (identical) and `xtalapp/heatmap.py:79` — the last
  uses `< 1e-3` / `>= 1000` / `.3g` where the others use `< 1e-2` / `>= 100` /
  `.2f`. The same energy reads `1.42` on the optimiser trace and `1.418` on the
  landscape. Five hand-drawn plot widgets (`curve` 508, `heatmap` 468, `bands`
  322, `histogram` 306, `plot` 236 = 1840 lines) each define their own
  `LEFT/RIGHT/TOP/BOTTOM` and share their paint scaffold by copy:
  `similarity.py curve.py histogram.py` → *81 identical lines, 33% of the
  smaller*. PLAN § 2's decision to hand-draw rather than depend on a plotting
  library was sound; what is missing is the shared `Axes` helper it implied.
- **The two matplotlib dialogs.** `xtalapp/dialogs/landscape.py` vs
  `xtalapp/dialogs/pattern.py`: *83 identical lines, 30% of the smaller, longest
  run 16* — the figure-saving button, the `rc_context(EDITABLE_TEXT)` block and
  the error path (`landscape.py:140/302/312`, `pattern.py:178/396/406`).
- **The Slater-Koster search order, twice.** `xtalapp/external.py:224
  _parameters_status` re-encodes the order in
  `xtal.ff.dftb.hsd.slater_koster_directory` and says so in its own docstring
  ("The same order … said out loud"). The codebase already solved this shape once
  for *binaries*: `xtal/modules/process.py:183 Program.search()` returns every
  place that was looked and what was there, precisely so the status line does not
  have to guess. `hsd` wants the same method.
- **The status-bar helper is bypassed 20 times.** `MainWindow.show_message`
  (`mainwindow.py:1168`) exists; `statusBar().showMessage(...)` is called directly
  at 20 sites in `mainwindow.py` and 3 in `documents.py`, each with its own
  timeout (4000/5000/6000/8000 ms), including twice inside `DocumentSet.open_path`
  where the method next to it uses `show_message`.
- **Private methods reached across objects.** `self.window._rebuild_recent_menu()`
  (`documents.py:249, 401, 456`) and `self.window._refresh_shell()`
  (`module_runner.py:217, 280, 303`) — the facade has a public surface for
  everything else.

---

## 11. `[minor]` Error conventions are nearly uniform, and the exception is what forces the blind catches

**What.** Seventeen domain exception classes, sixteen of which derive from
`ValueError`, so `except ValueError` in the GUI catches almost everything the core
raises. The one that does not is the calculator family.

**Evidence.**

```
$ grep -rn "^class [A-Za-z]*Error" xtal/ --include=*.py | grep -v pormake
xtal/params.py:40           ParamError(ValueError)
xtal/analysis/topology.py:101   TopologyError(ValueError)
... 14 more (ValueError) ...
xtal/ff/api.py:35           CalculatorError(RuntimeError)      # <-- the odd one
xtal/ff/scan.py:97          ScanError(CalculatorError)
xtal/ff/constraints.py:50   ConstraintError(CalculatorError)
```

Raise counts in `xtal/`: `ValueError` 139, `CalculatorError` 34, then a long tail.
Catch shapes in `xtalapp/`: `except Exception` 24, `except ValueError` 16,
`except (ValueError, OSError, KeyError)` 3, `except (KeyError, TypeError,
ValueError)` 3, and 37 `# noqa: BLE001` blind catches in total. The blind catch
in `ForceFieldDock.single_point` (`ff_panel.py:628`) is there because a UFF typing
failure arrives as `TypingError(ValueError)` and a DFTB+ failure as
`CalculatorError(RuntimeError)`, so no single narrow clause covers the engine
chooser.

**Why it matters.** The convention is good and almost universal; it is one base
class away from letting the GUI write `except XtalError` and delete most of the
37 blind catches, each of which currently hides a genuine bug as readily as an
expected failure.

**What a fix would look like.** `class XtalError(Exception)` in `xtal/__init__.py`,
`ValueError` and `RuntimeError` families both deriving from it as a mixin; catch
sites narrow to it over time.

---

## 12. `[minor]` The settings layer is fine, and its only cost is repetition

`xtalapp/settings.py` is 416 lines: one `AppSettings` class, a hand-written
property pair per setting (~14 of them), plus window geometry and screen fitting.
It is correctly on the GUI side of the wall, it is the only place `QSettings` is
touched, and `conftest.py` redirects its backend at import — the arrangement
CLAUDE.md records as having cost 278 stray plists before it existed. Three
settings (`bonds_follow_geometry`, `preview_interval`, `confirm_overwrite`) are
read by more than one collaborator; the rest have a single reader each. The only
observation worth making is that every setting costs ~12 lines of getter/setter
with hand-rolled `_as_bool`/clamping, which a small declarative table would
collapse — a cosmetic win, not a structural one, and not worth risking.

---

# What is genuinely well done

Be specific, because this is a well-built application and several of these are
worth copying rather than merely noting.

1. **The headless wall actually holds, and I measured it rather than trusting the
   test.** 116 `xtal` modules imported in one interpreter, zero of
   `PySide6/PyQt5/PyQt6/PySide2/vtk/vtkmodules/matplotlib/pyqtgraph/qtpy/tkinter/wx/xtalapp`
   in `sys.modules` (`review/probes/wall.py`). This is the plan's principle 1
   and it is true in fact, not just in intent.

2. **The three-way refresh split is honoured everywhere, and the costs are
   proportionate.** Callers of `_update_ui` are exactly four (construction, add
   document, close document, tab change); `_on_structure_changed` and
   `_on_view_changed` are reached only from the document's signals
   (`documents.py:139-140`). Measured on MFU-4l (648 atoms in the cell,
   `review/probes/test_refresh_cost.py`):

   ```
   _refresh_shell               0.68 ms
   _refresh_module_actions      0.21 ms
   _on_view_changed             0.90 ms
   _update_ui                   2.09 ms
   _on_structure_changed(ALL)   2.39 ms
   ```

   A spinbox move costs 40% of a full rebind, not 100%. I went looking for a
   panel that rebuilds more than it needs to and did not find one; the
   `positions_only` gate in `_on_structure_changed` (`mainwindow.py:1408`) and the
   flag handed to `net_dock.on_structure_changed` are both real.

3. **`Engine.__call__` is a model seam** (`xtal/ff/registry.py:71`). One
   decision — hold dummy markers back at the door — made once, in the registry,
   with a docstring that says exactly why no engine may be trusted to do it: "an
   engine written next year would have to remember, and would not." Everything
   in finding 6 is about the *other* decisions that were not given this treatment.

4. **`Document.run` is a real single door,** with a backstop that is doing its
   job (`xtalapp/document.py:447`). `Document.apply`, `transaction` and
   `_after_change` (`:525`) give one place where change flags drive selection
   pruning, measurement refitting, pore-network staleness and the modified flag.
   The `Change`-flag discipline is what makes finding 2 above *only* a factoring
   problem.

5. **The module path is genuinely shared between the GUI and the CLI.**
   `xtal/modules/record.py` (77 lines) is called from `xtalapp/module_runner.py`
   and from `xtal/cli.py` with the same arguments. This is the template finding 2
   asks the force-field path to follow — the author already knows how to do it.

6. **`xtal/params.py` is shared between two registries that had every excuse not
   to.** `Param`, `Availability`, `defaults()` and `coerce()` serve both
   `Engine.options` and `Action.params`, so a generated form works for either.

7. **The scan, the newest large feature, extended the machinery rather than
   forking it.** `xtal/ff/scan.py` calls `optimize.run` (`:541`, `:580`) and
   plugs its constraints in as a `Holonomic` that the optimiser applies *after*
   the symmetry projectors and the frozen mask (`xtal/ff/optimize.py:560-568`,
   with the reason in the comment). `xtal/modules/scan.py` is an ordinary
   `MODULES` entry with `run_scan(job) -> JobResult` writing through `job.file()`
   and `job.folder`; `xtalapp/dialogs/scan.py` is an ordinary `Action.dialog`
   with the same `ask()` contract as every other. It follows the newer pattern
   more faithfully than the older force-field path does.

8. **`Action.shell` records an asymmetry instead of hiding it.**
   `xtal/modules/forcefield.py:1-38` is the best docstring in the repository: it
   says that the Force Field panel does three things a generic runner cannot,
   that rewriting it to fit would have spent a phase's budget on the one module
   that did not need it, and that `shell` is "the asymmetry … recorded honestly
   rather than hidden". Findings 2 and 6 are the bill for that decision; the
   decision itself was defensible and is documented where the next person will
   read it.

9. **`start_in_thread` and `Cancellation` are shared and well reasoned.**
   `xtalapp/workers.py:179` holds the QThread ownership rule in one place with
   the reason it exists; `xtal/modules/job.py:52 Cancellation` covers in-process
   polling and external-process killing through one object, so `cancel()` does
   not have to know which kind of job it is stopping. (The known teardown race is
   `docs/TODO.md` § Testing and threads and is not mine to rediscover.)

10. **`for_export` really is the one door out.** Every user-facing write goes
    through `Document.export` → `exportable()` → `for_export`
    (`xtalapp/document.py:316-331`). The other `FORMATS.write` call sites
    (`workspace.py:702` final.cif, `module_runner.py:533` the filed build,
    `modules/scan.py:411` a scan point) are deliberately *not* cleaned, which is
    correct under the "the workspace copy of a structure *is* the document"
    invariant.

11. **Measured quality of the code itself.** `ruff check .` clean under
    `E,F,W,I,UP,B`; 19 functions over complexity 10 in ~75 kLOC; 121 of 3593
    functions over 50 lines; 11 over 100, and three of those are data tables or
    menu construction rather than logic.

12. **The comments made this review possible.** The duplication in finding 2 was
    findable because the *comment* was copied too; the drift in finding 10 was
    findable because each copy says what it believes it matches. A codebase whose
    comments say why is a codebase whose copy-paste is visible.

---

# The three refactors that would pay back most

### 1. One owner for action enablement — `xtalapp/shell_state.py`  **S**, low risk

Move the 17 refresh/enable methods (345 lines) out of `MainWindow` into a
collaborator holding `self.window`, exactly as `WorkspaceShell` does, and inside
it replace the two divergent enable blocks with a single
`enabled_for(document, playing, running) -> dict[str, bool]` that both entry
points apply whole.

*Pays back:* removes the highest-traffic duplicated decision in the codebase
(finding 1), removes the mis-filed methods under the `MODULES` banner, and is the
first and safest slice of the `mainwindow.py` split (finding 7) — 345 of the 821
movable lines.
*Risk:* low. Only three test references to the privates involved; the forwarding
pattern is already established by 30 existing forwarders; behaviour is asserted by
the existing widget tests, and a new order-independence test is three lines.

### 2. One run lifecycle, and move workspace filing into `xtal/`  **M**, medium risk

Give `xtal/ff/record.py` an `open_run`/`close_run` pair mirroring
`xtal/modules/record.py`, and have `ForceFieldDock` (`ff_panel.py:593, 821, 848`)
and `cli._recorder` (`cli.py:265`) call it. Then move `_file_build`,
`_drop_the_runs_copy` and `_move_run_under` (`module_runner.py:497-589`) into
`xtal/workspace.py` as `Workspace.adopt_build(structure, run_folder)`, and call it
from both `ModuleRunner` and `cli.cmd_run`.

*Pays back:* collapses four run-lifecycle implementations to two (findings 2 and
3), makes "the CLI writes exactly what the window writes" true for builds, and
makes the ten `test_mof_ui.py` filing tests expressible without a `QMainWindow`.
*Risk:* medium — it touches the file layout of real workspaces, and the failure
paths (no workspace, unwritable home, a run stopped half way) are the ones
CLAUDE.md's "degraded window survives" invariant protects. Do it with
`resources/test/` workspaces in front of you and the `.claude/skills/pure-move`
rule of one seam per commit.

### 3. Put the chemistry back behind the wall  **S–M**, low risk

Replace `mof_preview._draw_bonds`' private perception with a call into
`xtal.core.bonding` (finding 4), move `modes.bond_distance` beside it, and add the
one-line import allow-list test that would have caught both. While the file is
open, add `options = self.coerce(options)` to `Engine.__call__`
(`xtal/ff/registry.py:71`), which deletes the three divergent `build()` filters
(finding 6).

*Pays back:* closes the only outright layering violation in the core direction,
makes the building-block picture agree with the build it produces, and removes the
one idiom a new engine author currently has to guess at.
*Risk:* low. The preview has its own tests; the engine change is covered by the
existing engine tests, and `UFFCalculator`'s unfiltered `build` is the only one
that changes behaviour (it starts ignoring unknown keys instead of raising, which
is what the other three already do).

*Deliberately not in the top three:* the `ExternalCalculator` base (finding 6, M,
medium — 120 duplicated lines, but both engines are stable and the duplication is
not currently costing anyone), and the shared `Axes` helper for the five plot
widgets (finding 10, M, low — real drift, but cosmetic until somebody notices the
tick labels disagree).

---

# What I did not get to

- **I did not run the full suite.** Per the brief and `sysctl vm.swapusage`
  (9274 M of 10240 M in use while I worked), I ran only my own three probe files
  under `review/probes/`, which take 1–2 s each. Every claim above about
  behaviour is from a probe or from reading; nothing rests on a suite result.
- **`resources/test/` is present but thin** — only `MOF-5/` and `workspace.json`.
  I did not exercise the workspace tests that read a tree of real runs, so my
  finding 3 claim about the CLI's build filing is from reading `cli.py:405-464`
  and `module_runner.py:497-589`, not from running `xtal run mof.build`. That
  would be the single cheapest confirmation for the coordinator to ask for.
- **I did not review `xtalapp/viewport/`** beyond the layering questions. It is
  the largest subtree (`vtk_scene.py` 2181, `builder.py` 1445, `modes.py` 1114)
  and `build_scene` (170 lines, 31 branches) and `VtkScene.set_positions` (84
  lines, C901 13) are the two places where a "render model ≠ data model"
  (PLAN § 1.5) review would start.
- **I did not audit `xtal/analysis/topology.py`** (1426 lines, containing
  `_walks` at 158 lines / complexity 26 — the most complex function in the
  repository) or `xtal/core/subgroups.py` (1361). Both are self-contained
  algorithms rather than workflow spine, but `_walks` is where a
  complexity-focused reviewer should look.
- **Duplicate detection was line-window based**, so it finds copy-paste and not
  parallel structure expressed differently. The `similarity.py` numbers for
  specific file pairs are more reliable than the window scan's totals.
- **`git status` note:** clean at start and clean at finish; I created nothing
  outside `review/` (probes in `review/probes/`, this report in
  `review/reports/`). A `.coverage` file appeared at the repository root
  mid-session and disappeared again — not mine, no command I ran used `--cov`.
