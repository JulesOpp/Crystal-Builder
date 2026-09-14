# Packaging — phase 8

[PLAN.md](PLAN.md) § 13 says what to ship and § 16 says it has not
been shipped.  This file is how.  It is a plan and not a record: an
entry is **deleted when it ships**, like everything else in `docs/`.

The goal is narrow and worth stating, because it is the thing that
decides most of what follows.  **A person who has never installed
Python gets a `.dmg` and a `.exe`, double-clicks a `.cif`, and the
window opens.**  Not a conda environment, not `pip install`, not a
README with a prerequisites section.  Everything below is either in
service of that or is explicitly deferred.

---

## 1. Where this got to

| Piece | State |
|---|---|
| `packaging/bundle.py` + `tests/test_packaging.py` | done; 11 tests, no PyInstaller needed |
| `packaging/icons/` | done; `.svg` sources, `.icns`/`.ico` rendered by `build_icons.py`, plus a separate `app-small.svg` for 16 and 32 px |
| `packaging/macos.spec` | done; builds a `.app` that passes `--selftest` |
| `packaging/postbuild.py` | done; strip and Qt pruning, then the ad-hoc signature |
| `packaging/windows.spec`, `crystal-builder.iss` | **written, never run** — no Windows machine here; CI is the first execution |
| `crystal-builder --selftest` | done; passes on a checkout and inside the bundle |
| CI `build` + `release` jobs | written; build-on-main included, first run is the proof |
| A tag | **none yet.** Until there is one, every build says `0.1.devN` |

---

## 2. The shape of the build

**PyInstaller 6, onedir, one spec per platform, both driven by one
shared Python module.**

Onedir and not onefile.  A onefile build unpacks a 300 MB bundle to a
temporary directory on every launch, which is seconds of delay before
the splash screen the app does not have, and it breaks the resource
lookup in § 3.1 in a way that is tedious to debug.  Onedir is what
goes inside a `.app` and inside an installer anyway.

One spec per platform because the two differ in real ways — an
`Info.plist` and a `BUNDLE` step against a `versionfile` and
`console=False` — but the *contents* are identical, so:

```
packaging/
    bundle.py            # the shared answer: datas, hiddenimports,
                         # excludes, and the two icon paths
    macos.spec           # imports bundle.py, adds BUNDLE + Info.plist
    windows.spec         # imports bundle.py, adds the version resource
    crystal-builder.iss  # Inno Setup
    icons/
        app.icns  app.ico  app.svg   # the .svg is the source of truth
        cif.icns  cif.ico            # document icons
        xtalproj.icns  xtalproj.ico
```

`bundle.py` exists so that "we forgot to collect the fragment library"
is one fix and not two.  It is not a build script — `pyinstaller
packaging/macos.spec` stays the command.

---
## 3. The one constraint, and the one line

SHELL.md used to sit here with five pieces of shell work in it, on
the grounds that each was a bug in the shipped app if it was skipped.
All five have shipped — `xtalapp/applog.py`, `xtalapp/application.py`,
`xtalapp/samples.py`, `xtalapp/extras.py` and the Preferences window,
with `Program.setting` wired through `locate(hint=...)` — so that
file is gone, as an entry is when it ships.  What is left of it is
the bundle/don't-bundle decision, which is § 4.

### 3.1 The four `parent.parent` lookups — a constraint, not a change

`xtal/analysis/rcsr.py:source_file`, `xtal/modules/zeopp.py:bundled`,
`xtal/ff/dftb/hsd.py:bundled` and `xtalapp/samples.py:folder` all
compute the same thing:

```python
Path(<a module>.__file__).resolve().parent.parent.joinpath(*PARTS)
```

There were three of these when this was written; `samples.py` made it
four, and it is the one that matters most, because it is the only one
whose target actually ships.

In a PyInstaller onedir bundle `xtal.__file__` is
`<bundle>/_internal/xtal/__init__.pyc`, so `parent.parent` is
`_internal`, which is `sys._MEIPASS`.  **All four keep working
unchanged provided anything they look for is placed at
`_internal/resources/...`.**  Do not add a `sys.frozen` branch to any
of them and do not flatten `resources/` into the package.

**Confirmed on a real bundle**, which is the only way this could be
confirmed: `--selftest` opens a sample from inside the built `.app`,
so `.resolve()` is demonstrably surviving PyInstaller 6's
`Contents/Frameworks` ↔ `Contents/Resources` symlink split rather
than being asserted to in a paragraph.

### 3.2 `copy_metadata('crystal-builder')`

One line in `bundle.py`, and invisible until it is missing.  `pip`
writes `crystal_builder-<version>.dist-info/` beside the code, holding
the version and the entry points; PyInstaller copies code and not
that.  Without it `version("crystal-builder")` raises,
`xtal/__init__.py`'s `except` catches it, and **Help → About reports
`0.0.dev0` on every release** — worse than showing nothing, because it
looks like a real number and a bug report quoting it is useless.

A tag has to exist as well, and that is easy to miss: with no tag
anywhere in the repository, setuptools-scm has nothing to derive a
number *from*, and `copy_metadata` faithfully carries a dev string.
`--selftest` fails on both cases rather than either.

The other half is `xtal/plugins.py:load`, which calls
`entry_points(group=...)`.  That works again with this line, but the
honest position is that a frozen app has no `pip` and nowhere to
install a plugin *to*: **the shipped build supports in-tree modules
only**, plus whatever is in the folder `xtalapp/extras.py` prepends to
`sys.path`.  The release notes say so.

### 3.3 A dependency bound, found by `--selftest` on its first run

**PySide6 must stay below 6.10.**  VTK's
`QVTKRenderWindowInteractor.paintEvent` is one line — `self._Iren.Render()`
— and from 6.10.0 Qt re-posts a paint event for the render, so the
widget repaints forever at 100% of a core: the window comes up, the 3D
view stays empty, nothing responds again.  Bisected on macOS 13
against VTK 9.6.2 and 9.7.0, which are both fine: 6.9.3 works, 6.10.0
does not.  `pyproject.toml` carries the bound and the reason.

The suite cannot catch this and never will: widget tests inject a stub
`QWidget` in place of the viewport precisely so they never open a GL
context, so two thousand tests pass against a PySide6 that hangs the
real window.  That gap is the whole argument for § 8.2 drawing a
picture rather than asserting a window exists.

## 4. What goes in the bundle, and what does not

### In

`numpy`, `scipy`, `gemmi`, `spglib` — the core's four — plus
`PySide6` and `vtkmodules`, plus the package data already declared in
`pyproject.toml` (`xtal.analysis/data/*.json.gz`, the RCSR index, and
`xtal.build.data/*.json`, the fragment library).  Both of those are
non-optional by the argument already in `pyproject.toml`: a net panel
that cannot name anything and a fragment picker with nothing in it are
broken features, not smaller ones.

`xtal.analysis/data/*.cgd.gz` — the RCSR nets themselves, 331 KB, and
**not a second copy of the index beside it**.  The index carries
invariants and a canonical key and no coordinates at all, so it can
say a structure is **pcu** and cannot draw one; drawing one is
`xtal.build.topology`, and it needs the cell and the vertices the
`.cgd` has.  Compressed it is smaller than the index it sits next to.

`resources/samples/` — 164 KB of seven real structures.  **File →
Open Sample** now opens each of them as an untitled document
(`xtalapp/samples.py`), so this folder has to be in the bundle or
seven menu entries grey out with a sentence about a source checkout.
It is also what `--selftest` in § 8 opens.

`matplotlib` — **new, and the second reversal on this page.**  It was
on the exclude list below, and the reason it was there was true when
it was written: every plot this application drew was a hundred lines
of `QPainter`, and the only `matplotlib` in the environment arrived as
a dependency of RDKit's drawing code, which is never used.  PXRD
changed what is being asked for.  Laying a measured pattern over a
calculated one and reading off which peak moved wants axes that pan,
zoom and pick; putting the result in a paper wants a vector figure
whose text is still text.  Neither is a hundred lines of anything, and
`xtalapp/dialogs/pattern.py` is the one window that uses it.

It is on `COLLECT` rather than being traced, because the Qt back end
and `mpl-data` are found at run time and are invisible to the import
analysis — the same reason `rdkit` and `rdeditor` are there.  What
keeps this bounded rather than a slide is the line in
`pyproject.toml`: **every panel still draws with nothing installed.**
`xtalapp/plot.py`, `xtalapp/histogram.py` and `xtalapp/curve.py` are
still `QPainter`, the pattern is still calculated and still written as
`.xy`, and a build that failed to collect `matplotlib` loses one
window and no answers — which is exactly what *Preferences → Optional
features* says it would.

### Out

`resources/topo/` — the uncompressed `.cgd`, which only `python -m
xtal.analysis.rcsr build` reads.  A gzipped copy ships as package data
and `xtal.analysis.rcsr.nets()` prefers it, so the shipped app draws
every net without this folder.

It used to be 13 MB, 12 of which was `TopCIF/` — 2728 CIFs generated
once from the `.cgd` beside them by `resources/topo/Top2Cif.py` and
committed.  `xtal.build.topology` generates the same structures in
about 20 ms each, so the folder is gone: the answer was always
cheaper than looking it up.

Nothing, now.  **This section used to say `pormake` and the `mof`
extra, and that is the decision that got reversed** — see below.  The
table it was decided from lived in SHELL.md § 3 and is worth keeping
because the reversal is only legible against it:

| | Bundle? | Why |
|---|---|---|
| **rdkit** (~107 MB) | **yes** | Buys two whole features — build from SMILES, and the sketcher.  Greying out *Draw* in a GUI-only distribution hides Phase U from exactly the people it was for. |
| **rdeditor** (~1 MB) | **yes** | PySide6 plus a theme package, both already bundled.  Free. |
| **ase** (20 MB installed, **1.4 MB in the bundle**) | ~~no~~ **yes** | Was "nothing in this tree imports it".  The vendored PORMAKE does, throughout.  It is traced and not collected whole, so what it costs is the 200 modules of its 1218 the builder reaches — measured, see `COLLECT` in `bundle.py`. |
| **pormake** | ~~no~~ **vendored** | Was 44 packages, ~889 MB, `jax` and `pymatgen`, and a ten-second import, for one dialog.  All three are gone. |

"Repeat `pip install 'crystal-builder[mof]'` in a nicer dialog" is not
an answer in a bundle, because there is no environment to install
into: the bundled interpreter is not on the user's PATH and has no
`pip`.  That is why *Preferences → Engines* knows which
build it is in and says different things.

### The reversal, which is the interesting part

The MOF builder was the single feature a bundled user could not have,
and the sentence above is why: there was no honest advice to give
somebody who double-clicked a DMG.  An external-tool route — point at
a conda environment, the way the app finds DFTB+ — was designed and
proven working, then rejected, because it still asks the user to
configure something.

**The 889 MB turned out to be almost entirely two dependencies PORMAKE
barely uses.**  `networkx` was declared and never imported.  `jax` and
`jaxlib` were 554 MB supplying **one gradient** to a `scipy` optimiser
that was already there.  `pymatgen` and its ~250 MB of sympy, pandas,
plotly and matplotlib were **one call**, expanding a net's asymmetric
unit — which `xtal/analysis/rcsr.py` already does over gemmi.

So PORMAKE is **vendored**, at `xtal/mof/pormake/`, MIT and trimmed of
all three: 12 files of Python, 2.8 MB of nets and blocks, and `ase`.
Measured on a built bundle it is **5.2 MB** where it was 889 — see
"On the size" for that measurement and for the reason the same
addition is 15.8 MB on disk.  `xtal/mof/pormake/PROVENANCE.md`
records every difference from upstream 0.2.3, and
`tests/test_mof_vendored.py` diffs the vendored copy against a real
installed one — same slots, same composition, same RMSD, same net —
whenever a machine has both.

`ase` moved with it and stays an extra: the core's four packages are
what make `pip install crystal-builder` usable on a cluster node, and
`xtal.modules.mof.available` greys the entry out naming
`crystal-builder[ase]` when it is missing.  The build jobs install it.

**Preferences → Engines (then Optional features) no longer lists the
MOF builder at all**, because a page listing a feature that ships as optional is the
untrue thing that page exists to avoid.  What is left of that box is
the folder on `sys.path`, which was always the general mechanism and
is now described as one.

### Never

**No third-party binaries and no parameter sets.**  Zeo++'s `network`
and the DFTB+ Slater-Koster sets are gitignored, so CI could not
bundle them even if we wanted to, and we do not want to: they carry
their own licences and citation obligations, DFTB+ itself is a conda
package the user installs, and `Program.locate` plus `XTAL_ZEOPP`,
`DFTB_PREFIX` and the preference already give three ways to point at
a local copy, with a greyed-out module entry that says which.  The
shipped app finds these; it does not carry them.

### Excludes, and why they are not optional

`vtkmodules` on this machine is 619 MB on disk.  The thirteen modules
`xtalapp/viewport/` actually imports are a small fraction of that,
and PyInstaller will happily bundle all of it.  The exclude list
(`vtkmodules.all`, the unused rendering back ends, `QtWebEngine`,
`Qt3D`, `QtCharts`, `QtQuick`, `QtMultimedia`, `QtNetwork`'s TLS
plugins, `tkinter`) is the difference between a ~300 MB download and a
~1 GB one.  `matplotlib` was on that list and is not any more — see
*In* above; it is the one entry that came off for a feature rather
than for a size.  The app uses exactly four Qt modules —
`QtCore`, `QtGui`, `QtWidgets`, `QtSvgWidgets` — which makes the
PySide6 half of this unusually easy to be aggressive about.

Build the exclude list **empirically**: build once with nothing
excluded, read `build/*/xref-*.html`, cut the biggest thing that is
obviously unused, rebuild, launch.  Guessing at it produces a bundle
that starts and then fails on the one dialog nobody tested.

**And two things the exclude list cannot do, which together beat it.**
Both are in `packaging/postbuild.py`, run after PyInstaller.

*Strip, with the right flag.*  The VTK wheel ships its dylibs with
their local symbol tables: 54.7 MB of `libvtkCommonCore.dylib`'s
98.4 MB is one `__LINKEDIT` segment.  **PyInstaller's own
`strip=True` does not remove it** — on macOS it runs `strip -S`,
which takes out *debug* symbols these libraries have none of.  The
flag that works is `-x`: measured on that library, `-S` leaves it at
98.4 MB and `-x` takes it to 45.6.  So the specs set `strip=False`,
because PyInstaller's pass costs minutes for nothing, and postbuild
does `strip -x` instead.  About 150 MB.

*Removing two Qt plugins.*  `imageformats/libqpdf.dylib` renders a
PDF as an image, and `platforminputcontexts/libqtvirtualkeyboardplugin.dylib`
is an on-screen keyboard for touch devices.  Neither can ever be
called here, and each is the **only** thing in the bundle linking a
chain of frameworks: the first is what drags in QtPdf, the second the
whole of QtQuick, QtQml and QtVirtualKeyboard.  About 25 MB reachable
from two files.  Qt finds plugins by scanning a directory, so a
missing optional one is never offered rather than looked up and
missed.

The removal checks itself rather than trusting that list: postbuild
re-runs `otool` over everything still in the bundle and keeps any
framework that turns out to have a dependent, saying so.  Note that
PyInstaller rewrites Qt's install names down to a bare `@rpath/QtSvg`
— matching on `QtSvg.framework/` finds nothing and cheerfully reports
that every framework is unused, which is a convincing way to delete
something load-bearing.

---

## 5. macOS

* **`.app` via `BUNDLE`**, with an `Info.plist` declaring
  `CFBundleDocumentTypes` for `.cif` (`public.chemical-file`, viewer
  + editor) and `.xtalproj` (owner, with its own icon), plus
  `NSHighResolutionCapable`, `LSMinimumSystemVersion`, and
  `NSRequiresAquaSystemAppearance = false` so the dark theme the app
  already follows is not overridden.
* **Two architectures, not universal2.** VTK does not publish
  universal2 wheels, so `--target-arch universal2` cannot work
  without building VTK, which is not a thing this project is going to
  do.  CI already has `macos-14` and `macos-13`; ship
  `Crystal-Builder-<version>-arm64.dmg` and `-x86_64.dmg` and let the
  download page name them.  Do not ship arm64 only and tell Intel
  users about Rosetta — Rosetta cannot help, the app is not there.
* **DMG**: `packaging/makedmg.py`, with the `.app` and a symlink to
  `/Applications`.  `hdiutil` and **not** `create-dmg`, which was
  tried first: it positions the mounted window's icons by driving
  Finder over Apple events, and anything without macOS Automation
  permission gets `Not authorized to send Apple events to Finder
  (-1743)`.  A developer can grant that in System Settings; a CI
  runner cannot be asked.  What it buys is a background image and
  icon placement, which this section already put outside phase 8.
* **Signing.** Be honest about the three options and pick one:
  1. *Ad-hoc* (`codesign -s -`) — required on Apple silicon or the
     app will not launch at all, and still Gatekeeper-blocked.  The
     user does right-click → Open once, or
     `xattr -dr com.apple.quarantine`.  Free.  Documented in the
     release notes.
  2. *Developer ID + notarisation* — $99/year, and the only option
     where a stranger can double-click the DMG and have it work.
     Needs `--options runtime` (hardened runtime), an entitlements
     plist, and `notarytool` in CI with the credentials in secrets.
  3. Homebrew cask, later, which needs (2) anyway.

  **Do (1) for the first release and write the dance into the release
  notes.**  Get a Developer ID before the first release anybody
  outside the project is asked to install; the hardened runtime
  interacts with VTK's OpenGL and with `subprocess`-launching Zeo++,
  so it is a real debugging session and not a checkbox, and it is
  much better done once the unsigned build is known to work.

---

## 6. Windows

* **onedir, `console=False`.** A console window flashing up behind a
  GUI is the single most amateur-looking thing a Python app does.
  This is also what makes § 3.3 mandatory rather than nice.
* **Inno Setup** for `crystal-builder.iss`: Start-menu entry, an
  optional desktop shortcut, `.cif` and `.xtalproj` associations
  written to `HKCU` (per-user install, so no UAC prompt — a
  scientific tool on a managed lab machine frequently cannot get
  admin), an uninstaller, and `ChangesAssociations=yes` so Explorer
  refreshes its icon cache.
* **Do not register `.cif` as the default handler without asking.**
  Offer it as an unticked checkbox.  A CIF is usually already
  associated with VESTA or Mercury and silently stealing it is the
  fastest way to be uninstalled.
* **A version resource** (`versionfile` in the spec, generated from
  the `setuptools-scm` version) so the `.exe` properties dialog and
  SmartScreen report a name and a publisher rather than nothing.
* **SmartScreen.** An unsigned installer shows "unrecognised app" and
  needs *More info → Run anyway*.  A code-signing certificate is
  ~$200–400/year and an EV one buys immediate reputation; the same
  recommendation as macOS applies — ship unsigned first, document
  the click, and buy a certificate before asking strangers to
  install it.

---

## 7. CI: the release job

### First, the thing this file got wrong

This section used to open by saying CI was "already green on all
three targets".  **It was not, and had not been for at least six runs
on `main` going back to Phase G**: `lint` passed and every test job
failed, on every platform.  Since `build` is `needs: test`, the whole
release path was dead on arrival, and the Windows build — which only
CI can produce, because PyInstaller cannot cross-compile — could
never have run at all.

None of the three causes was a failing test:

- **Windows never got as far as installing Python.** `git checkout`
  failed on `resources/topo/TopCIF/nul.cif`; `nul` is a reserved
  device name and git cannot create the path, so the *entire clone*
  failed. Renamed, with a test that fails if another reserved name
  appears — there is no way to catch this from macOS or Linux except
  by looking.
- **macOS could not import its own test helpers.** A dozen modules do
  `from tests.conftest_ff import ...`, there is no
  `tests/__init__.py`, and CI ran bare `pytest`, which does not put
  the working directory on `sys.path`. CLAUDE.md had prescribed
  `python -m pytest` all along, which does.
- **Linux failed before the first test.** PySide6 links `libEGL` and
  the runner image does not carry it; pytest-qt imports QtGui during
  `pytest_configure`, so it was an `INTERNALERROR` rather than a skip.

The lesson worth keeping is not any of the three. It is that **a
green badge was assumed and never looked at**, for long enough that a
plan got written on top of it.

### The job

`ci.yml` triggers on `tags: ["v*"]` and has the three runners.  Add a
`build` job, `needs: test`, `if: startsWith(github.ref,
'refs/tags/v')`:

| Runner | Produces |
|---|---|
| `macos-14` | `Crystal-Builder-<v>-arm64.dmg` |
| `macos-13` | `Crystal-Builder-<v>-x86_64.dmg` |
| `windows-latest` | `Crystal-Builder-<v>-setup.exe` |

Each: checkout with `fetch-depth: 0`, `pip install -e ".[gui,build,
sketch,ase]"` plus `pyinstaller`, run the spec, run the § 8 smoke test
against the *built* bundle, then package and upload.  A final job
attaches all three to a GitHub Release with a body that carries the
Gatekeeper/SmartScreen instructions and the "these features need
`pip`" note from § 4.

**Also build on every push to `main`, without packaging or
uploading.** A spec file rots the moment somebody adds an import, and
finding that out at tag time — when the tag is already pushed — is
the worst moment.  A build-only job that just has to produce a
bundle and pass § 8 catches it on the commit that broke it.  It is
the whole value of having CI on three platforms already.

---

## 8. Testing a thing the suite cannot import

The normal suite tests a source checkout and can say nothing about a
bundle.  Three layers, cheapest first:

1. **`tests/test_packaging.py`**, in the normal suite: assert that
   `bundle.py`'s `datas` names every path the three `bundled()`
   lookups in § 3.1 and the two package-data globs in
   `pyproject.toml` reference.  This is the test that fails when
   somebody adds a data file and forgets the spec, and it needs no
   PyInstaller and no display.  It is the highest-value test here.
2. **A smoke run against the built bundle**, in CI, from the
   packaging job: launch the executable with
   `XTAL_NO_CONFIRM_CLOSE=1` (per CLAUDE.md — otherwise a modal
   nobody answers hangs the job) and a `--selftest` flag that opens
   `resources/samples/MOF-5.cif`, asserts the version is not
   `0.0.dev0`, asserts the RCSR index and the fragment library both
   load, embeds a benzene through RDKit, **resolves every dialog an
   action can only name**, **builds a pcu framework and checks the net
   that comes out**, writes a viewport PNG, and exits non-zero on any
   failure. That single flag covers § 3.1, § 3.2 and the VTK OpenGL
   context, which are the three things that break in a bundle and
   nowhere else.

   The MOF check is layer 2's whole justification in miniature: layer
   1 asserts `bundle.py` *names* the 3271 nets and blocks, and only a
   built bundle can say they survived PyInstaller. A build with the
   code and no database imports perfectly and then greys the entry out
   — indistinguishable, to a user, from the feature having been
   dropped again.

   **The dialog check is there because layer 2 missed one.** The first
   bundle carrying the MOF builder passed every check above and then
   raised `ModuleNotFoundError: No module named
   'xtalapp.dialogs.mof_build'` the moment somebody clicked *Build
   MOF* — and *Build molecule* and *Insert molecule* with it. A module
   declares its parameters as data and imports no Qt, so an action
   wanting a dialog of its own can only name one, and
   `xtalapp.dialogs.module_dialog` resolves that name with
   `importlib`; PyInstaller cannot see through it. The lesson is the
   one this section already argues: exercising `xtal.mof.build` proved
   the *feature* worked in the bundle and said nothing about the
   *button*, and only one of those is what a user has.
3. **Look at it, once per release**, on both platforms, with the
   **run-app** skill's checklist: open a CIF, find symmetry, run a
   UFF optimisation to completion, run a Zeo++ job if a binary is
   present, save a `.xtalproj`, reopen it.

---

## 9. Ship blockers

Two things should be settled before a build is put in front of
anybody, and neither is a packaging problem.

**The `workers.py` deadlock.**  CLAUDE.md is explicit: the lock-order
inversion between Qt's connection mutex and the GIL "can hang the
shipped application the same way when a module run finishes", and it
is **unfixed**.  In the suite it is a wedged run one time in four; in
a shipped app it is a hang with no traceback, in the one code path
that runs after a calculation the user waited for.  Shipping the app
with a known hang at the end of a long job is worse than shipping it
a fortnight later.  This is its own piece of work — the note says
holding the pair alive from Python is not enough on its own — and it
should be fixed, or reduced to a documented and rare case, before
release rather than after.

**Nothing is signed and nothing is notarised**, so § 5 and § 6's
instructions are load-bearing.  That is acceptable for a first
release aimed at people who know the project.  It is not acceptable
for one aimed at anybody else, and the decision about which of those
this is belongs to the release and not to this file.

---

## 10. What is left

Steps 1 to 6 and the DMG have shipped and are deleted from this list.
What remains:

| | Step | Done when |
|---|---|---|
| 7 | `windows.spec` + `.iss`, through CI | the installer installs, associates and uninstalls cleanly on a real machine |
| 8 | The first tagged release | a tag produces three attached artifacts and `--selftest` is green on all three |
| 9 | The `workers.py` fix (§ 9), then `v0.1.0` | a hundred module runs finish without a hang |

**Step 7 is the one with real risk left in it.**  Everything in it was
written on a Mac and has never been executed: PyInstaller cannot
cross-compile, so `windows.spec` and `crystal-builder.iss` are the
only pieces of this that have not been run even once.  Expect the
usual "build, read the traceback, add a hidden import, repeat" loop,
at a CI round trip of about ten minutes a turn, plus the things that
only appear on Windows — a missing MSVC runtime, a path with a space
in it, an antivirus scanner holding a file open.

### On the size

**The DMG is about 185 MB and the installed `.app` is 493 MB**,
measured on an arm64 build of this tree rather than estimated.  The
first is the one a user experiences and it is fine; UDZO compresses
the bundle to about a third.

*About* 185, because **`hdiutil ... UDZO` is not reproducible.**  Six
DMGs of the same build, minutes apart, measured 181, 183, 187, 187,
188 and 189 MB.  The variance arrived with the MOF database — four
runs against a bundle without it gave the identical byte count three
times — so it is the 3271 tiny files being laid out
and compressed differently each time.  Nobody should read a few MB of
movement between two release DMGs as a regression.

One correction before the numbers, because this section used to
compare two things measured differently.  The 166 MB it quoted for the
DMG was `du -h`, which is MiB; the same file is **174 MB of bytes**,
which is what Finder and a download page say.  The `.app`'s 487 was
already decimal MB, from `postbuild.py`.  Everything below is decimal
MB, and where bytes and disk differ both are given.

Where it goes, after stripping: VTK 205 MB, RDKit 86 MB, PySide6
62 MB, scipy 55 MB, numpy 24 MB, and about 60 MB of Python, Pillow,
gemmi, spglib, the PyInstaller archive and the application itself.
This list used to open with "VTK 184 MB", and that was simply a stale
figure: the pre-MOF bundle measures 205 MB of VTK as well, so nothing
grew.  Nothing on the list is optional:

- **VTK** is the 3D view.
- **RDKit** is *Build from SMILES* and the sketcher, which the extras
  page promises a packaged user has, and dropping it saves 86 MB by
  removing two whole features.
- **scipy** is the force field's optimiser.

So 493 MB installed is what this application weighs once it is honest
about what it does, and the remaining levers are all bad trades.  The
~185 MB download is the number to quote.

#### What the MOF builder cost

Measured against a control build of this same tree with `ase` excluded
and the database left uncollected — the bundle as it would be without
the feature — rather than against the older build, so that nothing
else in between is being attributed to it:

| | without | with | difference |
|---|---|---|---|
| `.app`, bytes | 487.4 MB | 492.5 MB | **+5.2 MB** |
| `.app`, on disk | 490.9 MB | 506.7 MB | **+15.8 MB** |
| files in the `.app` | 2113 | 5386 | +3273 |
| DMG | 176.3 MB | 181–189 MB | **about +9 MB** |

The 5.2 MB is fully accounted for, and the last of the three is the
one worth knowing about:

- **2.85 MB** the vendored database, plus its licence and
  `PROVENANCE.md` — 3273 files.
- **1.41 MB** `ase` and the twelve vendored PORMAKE modules, compiled
  into the PyInstaller archive.
- **0.95 MB** the ad-hoc signature's own hash list.  `CodeResources`
  carries a digest per file, so it grows with the *count* and not with
  the bytes, and 3273 more files is nearly a megabyte of hashes.

**The shipped `.app` is 493 MB of bytes and 507 MB on disk**, and
three quarters of that 14 MB gap is the database alone.  3271 of the
new files are a single net or building block of a few hundred bytes
and each one pays a 4 KB block, so 2.85 MB of database occupies
13.5 MB of disk.  Quote 493 MB where the context is bytes — a download
page's "space required" — and 507 MB for what a disk actually loses.

The estimate this replaces was +35 MB installed and +5 MB on the
download.  The download was about half of what it costs — and only
the `.app` rows above are precise enough to argue with.  The installed
figure was wrong in a way worth keeping: it assumed `ase` arrived as
its whole 20 MB, which is what `COLLECT` in `packaging/bundle.py` was
doing conservatively.  Taking it off — PyInstaller traces 200 of ase's
1218 modules, which is every one the MOF builder touches, and they
compress into 1.4 MB of the archive — is worth **16 MB of the `.app`** on its
own, and `--selftest` still builds pcu inside the bundle.  The three
measurements that settled it are recorded above `COLLECT`; § 4's
"build the exclude list empirically" is what they are an instance of.
