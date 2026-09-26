(architecture-testing)=
# How it is tested

The suite is large, most of it runs without a display, and the parts
that cannot be tested from a checkout are checked by the built
application itself.  After this page you can run the half of the suite
that matters for a change you are making, know what a widget test does
in place of the 3D view, and know what continuous integration and the
manual's own checks will refuse.

```{index} single: tests; running the suite
```
```{index} single: selftest
```
```{index} single: continuous integration
```

## The suite

On the checkout this manual was written from, `pytest --collect-only`
counted 3778 tests in 175 files under `tests/`; 2115 of them are
selected by `-m "not gui"` and 65 are marked `slow`.  The commands the
repository's `CLAUDE.md` gives are:

```bash
python -m pytest -q -n 3               # full suite, three workers, ~2 min
python -m pytest -q -n0 tests/test_bonding.py  # while iterating
python -m pytest -q -n 3 -m "not gui"  # headless core only, ~1 min
python -m pytest -q -m "not slow"      # skips the ones marked slow
python -m pytest -q --durations=20     # what the run is actually spending
```

`pyproject.toml` defaults to `-n auto`, which starts a worker per core
and leaves the machine unusable; three workers finish in about two
minutes.  Use `python -m pytest` and not bare `pytest`: the `-m` form
puts the working directory on `sys.path`, and a dozen test modules
import from `tests.conftest_ff`.

The `gui` marker is not written on any test.  `tests/conftest.py` adds
it to every test in a module whose source imports `xtalapp` or
`PySide6`, "judged by what the *module* imports and not by fixture,
because a test of a `Document` asks for no `qtbot` and is still a Qt
test".  So `-m "not gui"` is the headless half: the core, checked
without building any of the thousand-odd windows that are a quarter
of the suite's time.  The wall between the halves has a test of its
own, described on the {doc}`layers page <layers>`.

Three conventions from `CLAUDE.md` shape what a test looks like.  Test
names are sentences describing the behaviour --
`test_a_modified_tab_closes_without_a_question`, not
`test_close_document` -- and docstrings say what breaks if the test
regresses.  A `DeprecationWarning` is an error, so a new deprecation
fails the suite rather than scrolling past.  Anything that takes
seconds is marked `slow`, and no single test should take anything
like a minute.

## Widget tests and the stub viewport

`MainWindow` takes a `viewport_factory`, "so the shell can be tested
headless with a stub in place of the VTK widget".  A widget test
builds the real window with a plain `QWidget` where the 3D view would
be and never opens an OpenGL context; 44 test files pass such a
factory, and the `window` fixture in `tests/test_open_once.py` is the
one to copy:

```python
@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Once{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win
```

`tests/conftest.py` provides four real structures as fixtures --
`rutile`, `quartz`, `halite` and `dry_ice`, chosen so that tetragonal,
non-orthogonal, centred and molecular cases are covered -- and
`resources/test/` and `resources/samples/` hold the larger files;
`MFU4l.cif` is the usual stress case.

Several guards in `conftest.py` keep the suite from ever waiting on a
person or touching the developer's own machine, and `CLAUDE.md` says
each must stay:

- `XTAL_NO_CONFIRM_CLOSE=1` is set for the session, so tearing down a
  window with unsaved edits raises no quit prompt.
- `QDialog.exec` and the `QMessageBox` static helpers are patched to
  **raise**: reaching one is a bug in the test, which patches the
  dialog or the class method above it instead.  Context menus are all
  raised through `xtalapp.menus.popup`, which is patched the same way,
  because `QMenu.exec` is resolved in C++ and cannot be.
- Settings are pointed at a scratch directory before any settings
  object exists, because on macOS `QSettings` is CFPreferences and
  each window fixture would otherwise leave a plist in
  `~/Library/Preferences`; the default workspace root is a temporary
  directory per test for the same reason.
- Every window a test built is deleted when the test ends, since
  `deleteLater` is never delivered outside a running event loop.

Two more rules are about memory rather than dialogs: upstream PORMAKE
and MACE never load into the test process -- the comparison against
real PORMAKE reads a recording, and the MACE tests run in a fresh
interpreter -- and `QT_QPA_PLATFORM=offscreen` is not set locally,
because it stops a dialog being drawn without stopping it waiting.

## `--selftest`: the built application checks itself

The ordinary suite tests a source checkout "and can say nothing about
a frozen one".  `crystal-builder --selftest` runs *inside* whatever it
was built into and, per `xtalapp/selftest.py`, checks the things that
break in a bundle and nowhere else: the version (a bundle without its
metadata reports `0.0.dev0` and "About just quietly lies"), the
resource lookups, the package data read two different ways, the
bundled extras, and the VTK OpenGL context, by writing a PNG of the
3D view, "the only honest way to ask".  It never opens a dialog: as in
the suite, reaching one is an error rather than a hung job.  Run on a
source checkout while writing this page, with scratch settings and a
scratch workspace:

```console
$ crystal-builder --selftest --selftest-image selftest.png
version...
  version 0.3.1.dev49+g0db248ed6.d20260926
RCSR index...
  RCSR index: 2931 nets
fragment library...
  fragment library: 26 fragments
samples...
  samples: 39 of 39 present
bundled extras...
  RDKit: benzene embedded, 12 atoms, 12 bonds
  rdeditor: present
module dialogs...
  module dialogs: 8 actions resolve to 6 modules
MOF builder...
  MOF catalogue: 2599 nets, 879 blocks
[...]
  MOF builder: pcu-N59-E32, 98 atoms, net identified as pcu
  MOF builder: MFU-4l, 81 atoms, 12 joint(s) bonded
  MOF builder: Ni3(HITP)2, 75 atoms, c = 3.2380 A, net identified as hcb
window and 3D view...
  opened MOF-5.cif: 424 sites
  viewport image: [...]/selftest.png (1016944 bytes)

selftest passed
```

It is also the one check that draws the real 3D view, which every
widget test replaces with a stub -- so a PySide6 that hangs the
viewport passes the whole suite and fails this.

## Continuous integration

`.github/workflows/ci.yml` runs on every push to `main`, every tag
`v*` and every pull request.  Its jobs:

**test**
: One job per platform shipped, "and nothing else": `macos-14` (Apple
  silicon), `macos-15-intel` and `windows-latest`, each on Python
  3.12, with the extras `gui,build,sketch,pxrd,ase,test` installed.
  The suite runs under `QT_QPA_PLATFORM=offscreen` with
  `faulthandler_timeout=180`, so a test still going after three
  minutes dumps every thread's stack and names itself; the job is
  capped at twelve minutes, "twice the longest honest run".  On macOS
  the same job then runs `crystal-builder --selftest` from the
  checkout and fails unless the output contains `selftest passed` and
  the image is non-empty.

**lint**
: `ruff check .` -- check only, never format, because the tree is
  hand-formatted to 79 columns.

**manual**
: This manual, built as HTML with every warning an error and then as a
  PDF through XeLaTeX, both uploaded as artefacts.  The reference
  pages are generated and committed, so the job needs neither a
  display nor the application.

**build** and **release**
: On a push to `main` or a tag, PyInstaller builds the bundle from
  `packaging/macos.spec` or `packaging/windows.spec`, macOS bundles are
  stripped and signed, and `--selftest` is run against the *built*
  application -- on Windows with a software OpenGL laid beside the
  executable for the duration and removed again afterwards, checked
  for -- with the same two greps.  On a tag the bundles are packaged
  into a `.dmg` and an installer and a draft GitHub release is made
  from `docs/RELEASE_NOTES.md`.

## The manual's own checks

Three things stop this manual from drifting.

1. **A strict build.**  Locally and in CI the HTML is built with
   `sphinx-build -n -W`, so a cross-reference to a command, module,
   engine or panel that no longer exists is an error.  Since every
   such reference points at an anchor generated from a registry key
   ({doc}`registries`), renaming a key in the code breaks the build
   of the manual until the prose is updated.
2. **The reference is regenerated, never edited.**  A wrong sentence
   under a command or a setting is fixed in the `tip=`, the
   `Param.help` or the dock's docstring in the source, and
   `reference.py` is run again; the script prints which commands and
   settings still have no text.
3. **The tutorial is proven in the real window.**
   `docs/manual/tutorial_check.py` performs the first-build exercise of
   the {doc}`quickstart </quickstart/first-build>` through the run-app
   driver, "through the doors a person uses" -- the block-drawing
   dialog's own save, the MOF builder's run, the Force Field panel's
   Optimise, the Find symmetry dialog's Adopt, the Document's net-edge
   verbs -- and reads the answers off the Net panel rather than off
   the core.  A step whose answer is not the one the chapter prints
   raises and stops the run, "then the tutorial is wrong or the
   application is, and that is a decision for a person".  It prints
   the space group and both net names, writes the chapter's figures,
   and is rerun whenever the builder, the force field, the symmetry
   finder or the net identification changes.
