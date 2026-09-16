---
name: add-module
description: Add a calculation to Crystal Builder - a new module (an external program like Zeo++ or DFTB+'s native runs, an in-process analysis like PXRD, a builder like the MOF or molecule builder) or a new energy engine for the Force Field panel (like xTB or MACE). Covers the registry entry, Params, availability checks, external binaries and preferences, optional extras, reports and overlays, dialogs, packaging and tests. Use when asked to add an engine, force field, MLIP, module, calculation, analysis, builder, or a new entry under an existing module.
---

# Adding a calculation

Two registries, and choosing the wrong one is the expensive mistake:

| It is... | Registry | Appears as | Examples |
|---|---|---|---|
| **An energy and forces model** the optimiser drives | `xtal.ff.ENGINES` | an entry in the Force Field (or DFTB+) panel's chooser | UFF, xTB, MACE, DFTB+ engine |
| **Something that runs and leaves artefacts**: a measurement, a picture, a new structure | `xtal.modules.MODULES` | a submenu of Modules, a leaf in the Modules dock, a generated form, a run folder, Stop | Zeo++, PXRD, MOF builder, band structure |

Both declare their inputs as `xtal.params.Param` and their readiness as
`Availability`. Neither imports Qt. That is what makes the CLI, the
Help page and the headless tests come for free.

Read `code-map` first and outline the closest existing sibling instead
of reading it whole: `xtal/modules/net.py` (102 lines, no binary, no
extra) is the smallest complete module; `xtal/modules/pxrd.py` shows a
report; `xtal/modules/zeopp.py` an external program; `xtal/ff/xtb/`
an external engine; `xtal/ff/mace/` an in-process one.
`xtal/modules/scan.py` is the one that runs for hours: it writes many
structures and returns **none**, streams a file per point as each
finishes rather than saving at the end, and stays in one job on one
thread deliberately -- copy it for anything long.

---

## A. A module

### 1. The file — `xtal/modules/<name>.py`

```python
PARAMS = (
    Param("probe", "Probe radius", kind="float", default=1.2,
          minimum=0.0, maximum=5.0, decimals=2, suffix=" A",
          help="What a user needs to choose a value -- this is the "
               "Help page and the tooltip."),
)

def run_it(job) -> JobResult:
    job.say("starting")                # log and status bar
    ...                                # job.check() between units of work
    return JobResult(message="...", report=..., structure=...)

MODULE = Module(
    name="thing", label="Thing", description="One or two sentences.",
    order=70, check=_available,
    actions=(Action(name="measure", label="Measure...", tip="...",
                    params=PARAMS, run=run_it),),
)

def register(registry=MODULES) -> Module:
    return registry.register(MODULE)
```

Then import it and call `register()` in `xtal/modules/__init__.py`, in
order with the others. That is the only existing file a module
touches; the menu, the dock, the form and the worker are built from
the declaration.

- `Param.kind` is one of `bool int float choice text path`. `help` is
  mandatory in practice, since `tests/test_help_ui.py` renders it.
- `run(job)` runs on a worker thread with **its own copy** of the
  structure (`job.structure`). It never touches the window.
- **Dummy atoms are held back** before `run` is called
  (`xtalapp/module_runner.py` calls `xtal.modules.job.without_dummies`
  and restores them after), unless `keeps_markers=True`, which is only
  for something that reads bonding and drops markers itself.
- **Failures are results**: `JobResult.failure("sentence", detail)`,
  not an exception, for anything a user could cause.
- **Cancellation**: poll `job.check()` / `job.cancelled` in loops; an
  external process registers itself through `ExternalProcess`, so Stop
  kills the binary.
- Action flags: `needs_structure=False` for a builder,
  `writes_run_folder=False` for something that leaves nothing behind,
  `kind="build"` for the run folder name, per-action `check=` when one
  entry needs an extra the rest do not.

### 2. What comes back — `JobResult`

| Field | Use | Lands |
|---|---|---|
| `message` | one sentence | status bar, log |
| `report` | `xtal.modules.report.Report` of `Table`, `Histogram`, `Curve`, `Bands`, `Dos`, `Modes` | Results dock |
| `structure` | a new geometry | one undoable command on the document the run **started from**, or a new tab for a builder |
| `overlay` | a picture drawn over the crystal, not part of it | `Document.set_overlay`: not undoable, not "modified", dropped when the arrangement changes |
| `trajectory` | frames | the transport bar |

A `structure` from a module that measures is a bug: a force field or
analysis never changes bonding or atoms (CLAUDE.md invariants).

### 3. An external program

```python
PROGRAM = Program(name="network", label="Zeo++", env_var="XTAL_ZEOPP",
                  url="https://...", setting="tools/zeopp")
```

- `check=lambda: PROGRAM.availability()`. It is asked every time the
  menu opens, so `shutil.which` cost only.
- Run it with `ExternalProcess(argv, cwd=job.path, log=job.log)` and
  `.run(cancel=job.cancel, program=PROGRAM)`; read outputs from the run
  folder. **Do not reimplement what the program does natively.**
- Add a `Tool("tools/<name>", "Label (binary)", "file", "what it is
  for")` to `TOOLS` in `xtalapp/external.py`; Preferences ▸ Engines
  is built from that list and the path reaches `Program` through
  `apply_hints`. Put the key in `_PROGRAM_ROWS` in
  `xtalapp/dialogs/preferences.py`, and teach `xtal/modules/probe.py`
  how the program is asked whether it runs (`probe_for`) -- measure
  what it prints and its exit code first; DFTB+ exits 1 when it works.
- Never bundle the binary (licences, citations): `packaging/bundle.py`
  `binaries()` says why.
- Tests use a fake program: `write_program(tmp_path, "network", body)`
  from `tests/conftest_program.py`, pointed at by the env var. It works
  on Windows too; do not write a `#!` file by hand.

### 4. An optional Python package

- Add the extra to `[project.optional-dependencies]` in
  `pyproject.toml`.
- The check is **`importlib.util.find_spec`, never an import**, and
  the reason names the extra:
  `Availability(False, "needs RDKit: pip install 'crystal-builder[build]'")`.
- If Preferences ▸ Engines should list it, add an `Extra` to
  `EXTRAS` in `xtalapp/extras.py`.
- If a frozen build should carry it, add it to `COLLECT` in
  `packaging/bundle.py`, and say in the plan what it adds to the size.
- Tests that need the package: `pytest.importorskip`; tests of the
  greyed-out state patch `find_spec`.

### 5. A dialog instead of the generated form

Only when parameters are not flat or not static (the MOF builder's slots
depend on the topology). Set `dialog="thing-run"` on the `Action`, write
the class in `xtalapp/dialogs/thing_run.py` returning the same values
dict, and add `"thing-run": ("xtalapp.dialogs.thing_run", "ThingDialog")`
to `_BY_NAME` in `xtalapp/dialogs/__init__.py`. **That mapping is how the
frozen build finds the module**: PyInstaller cannot see an
`importlib` import, and a missing entry is a `ModuleNotFoundError` in
the shipped app that no test on a source checkout can see.

### 6. Tests

- `tests/test_<name>.py`, headless, most of the coverage:
  - `MODULES.find("thing.measure")` resolves;
  - `action.run(Job(structure=quartz, params=action.coerce({...})))`
    gives the right numbers on a fixture structure (`rutile`, `quartz`,
    `halite`, `dry_ice`), or `resources/samples/MFU4l.cif` when size is
    the point (then `@pytest.mark.slow`);
  - a bad input comes back as a failed result naming the problem;
  - the greyed-out state names what to install.
- Run folder contents: pass `folder=` from a `Workspace` in `tmp_path`,
  as `xtal/cli.py` `cmd_run` does.
- GUI: `tests/test_modules_ui.py` already ties the Modules menu to the
  registry; add a UI test only for a dialog, a report that renders, or
  an overlay. Patch `ModuleDialog.ask` (see
  `tests/test_run_progress_ui.py`); `QDialog.exec` raises in the suite.
- **The CLI is a free end-to-end check**:
  `xtal run thing.measure resources/samples/MOF-5.cif -p probe=1.2 --workspace "$SCRATCH/ws"`.

---

## B. An engine

1. `xtal/ff/<engine>/calculator.py`: a `Calculator` subclass
   (`xtal/ff/api.py`) with `compute(positions, matrix) -> Result`
   (energy, forces, and stress only if `provides` says so) and
   `summary()`. Declare `provides_stress = False` and let
   `numeric_stress` pay, **unless the engine's stress has been checked
   against `numeric_stress` on quartz**; see docs/TODO.md for why
   tblite's was not trusted.
2. `ENGINES.register(Engine(name=..., label=..., description=...,
   build=..., provides=frozenset({...}), options=(Param(...), ...),
   check=..., order=...))` at the bottom of that file, and import the
   calculator in `xtal/ff/__init__.py`.
3. **Add the name to a dock's hand-written list** in
   `xtalapp/layout.py` (`engines=["uff", "xtb", "mace"]`).
   `test_every_engine_that_is_registered_can_be_chosen` fails until
   you do. MACE shipped unreachable before that test existed.
4. Markers are held back by `Engine.__call__`; always build through
   `ENGINES.build(name, structure)`, never `engine.build(...)`.
5. An in-process model with a heavy load (MACE) keeps one seam, such
   as `_load_model`, that tests replace, so the suite never downloads
   or loads weights.
6. The engine never changes bonding or atoms; the optimiser moves
   positions (and the cell) only.
7. Tests: `tests/test_<engine>.py` computing energy and forces on a
   fixture and comparing forces to finite differences; `conftest_ff.py`
   has helpers. External binary: same fake-program pattern as A.3.

---

## Before calling it done

- `python -m pytest -q tests/test_<name>.py tests/test_modules_ui.py tests/test_help_ui.py`
  (plus `tests/test_ff_ui.py` for an engine); full suite once before
  committing.
- `ruff check .`
- **Click it**, with `run-app`:
  ```bash
  python .claude/skills/run-app/drive.py --scratch "$SCRATCH/drv" \
    --open resources/samples/MOF-5.cif --list-actions | grep thing
  ```
  then run it with the dialog patched, `--settle 3000`, and `--grab
  results_dock` to see the report.
- **Docs**: the method's paper for the manual's bibliography (note it
  in the plan until the manual exists), `docs/RELEASE_NOTES.md` § Known
  issues or § What is in the download only if the module changes what a
  packaged user gets, and the TODO entry deleted.
