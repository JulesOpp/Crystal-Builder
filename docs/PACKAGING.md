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

## 1. What already exists

More than the empty `packaging/` directory suggests.

| Piece | State |
|---|---|
| `packaging/` | exists, empty — this is where the specs go |
| `pyinstaller>=6` | already in the `dev` extra |
| CI on all three targets | `macos-14` (arm64), `macos-13` (x86_64), `windows-latest`, already green |
| Version from git tags | `setuptools-scm`, and CI already fetches with `fetch-depth: 0` |
| Tag trigger | `ci.yml` already runs on `tags: ["v*"]` — it just does nothing extra with them |
| A GUI entry point | `crystal-builder = "xtalapp.main:main"`, which takes file paths on argv |
| Granular VTK imports | `xtalapp/viewport/` imports `vtkmodules.vtkRenderingCore` and thirteen siblings, never `vtk` or `vtkmodules.all` — which is the form a frozen build can actually prune |
| Package data declared | `[tool.setuptools.package-data]` already names the RCSR index and the fragment library |
| A way to drive the real window | the **run-app** skill |

What does not exist: any spec file, any icon (there is not a single
`.icns`, `.ico`, `.png` or `.svg` in the tree), any installer script,
any release job, and any of the four code changes in § 3.

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

## 3. Four code changes the frozen app needs

These come **first**, before any spec is written.  Each is testable
in the normal suite on a source checkout, and each is a bug in the
shipped app if it is skipped.

Three of the four turned out to be larger than "small", and they grew
a fifth — Preferences, without which a frozen app has no way to be
told where Zeo++ is.  The buildable version of all of it, with the
layout proposals and the order, is [SHELL.md](SHELL.md); what stays
below is the packaging-side summary of why each exists.

### 3.1 The three `bundled()` lookups — no change, but a constraint

`xtal/analysis/rcsr.py:source_file`, `xtal/modules/zeopp.py:bundled`
and `xtal/ff/dftb/hsd.py:bundled` all compute the same thing:

```python
Path(xtal.__file__).resolve().parent.parent.joinpath(*SOURCE)
```

In a PyInstaller onedir bundle `xtal.__file__` is
`<bundle>/_internal/xtal/__init__.pyc`, so `parent.parent` is
`_internal`, which is `sys._MEIPASS`.  **So all three keep working
unchanged, provided anything they look for is placed at
`_internal/resources/...`.**  That is a free win and it is worth not
throwing away: do not add a `sys.frozen` branch to any of these three,
and do not flatten `resources/` into the package.  Put the tree where
they already look.

The one caveat is macOS, where PyInstaller 6 splits a `.app` between
`Contents/Frameworks` and `Contents/Resources` and symlinks between
them.  It resolves — but `.resolve()` on a symlinked path is exactly
the kind of thing that works on one PyInstaller point release and not
the next, so **§ 8 has a test that asserts it from inside the built
bundle** rather than trusting this paragraph.

### 3.2 `copy_metadata('crystal-builder')`

Two things read the installed distribution's metadata and both fail
quietly without it:

- `xtal/__init__.py:16` — `version("crystal-builder")`, which falls
  back to `"0.0.dev0"`.  Help → About would report `0.0.dev0` on
  every release build, which is worse than no version at all because
  it looks like a number.
- `xtal/plugins.py:load` — `entry_points(group=...)`.  With no
  metadata this returns nothing, silently, and every out-of-tree
  plugin stops existing.  Phase 9's whole claim is that a plugin
  installed from outside the tree works; in a bundle there is nowhere
  to install one *to*, so the honest position is that **the shipped
  app supports in-tree modules only**, and § 7 says so in the release
  notes rather than leaving a dead menu.

This is one line in `bundle.py`, but it needs a test that a built
bundle reports the tag it was built from — see § 8.

### 3.3 A log file, because windowed builds have no stderr

`xtalapp/main.py:36` prints plugin load failures to `sys.stderr`.  In
a `--windowed` build there is no stderr, so that warning goes
nowhere; and any uncaught exception anywhere in the app takes the
window down with no traceback and nothing on disk to say why.  For a
scientific tool that runs external binaries and parses other people's
CIFs this is not acceptable — the first bug report will be "it
closed".

So: a `xtalapp/logging.py` that writes to
`QStandardPaths.AppDataLocation/crystal-builder.log`, installs a
`sys.excepthook` that logs the traceback and then shows a QMessageBox
naming the log file, and a **Help → Show log** menu item that reveals
it in Finder/Explorer.  Plugin failures and module-run stderr go
there too.

This is worth doing whether or not the app is ever frozen, which is
why it is a change to the app and not to the spec.

### 3.4 `QFileOpenEvent`, or file associations only half work

`xtalapp/main.py` reads paths off `argv`, which is how Windows
associations and a *cold* macOS launch deliver a file.  It is **not**
how macOS delivers one to an app that is already running: that
arrives as a `QFileOpenEvent` on the `QApplication`, and today nothing
handles it.  Double-clicking a second `.cif` with the window open
would do nothing at all, which reads as the association being broken.

A `QApplication` subclass (or an `installEventFilter`) that turns the
event into the same `MainWindow.open` call the argv loop at
`mainwindow.py:140` already makes.  Note the ordering trap: the event
can arrive *before* the window exists, so it queues into a list that
the window drains on construction.

---

## 4. What goes in the bundle, and what does not

### In

`numpy`, `scipy`, `gemmi`, `spglib` — the core's four — plus
`PySide6` and `vtkmodules`, plus the package data already declared in
`pyproject.toml` (`xtal.analysis/data/*.json.gz`, the RCSR index, and
`xtal.build.data/*.json`, the fragment library).  Both of those are
non-optional by the argument already in `pyproject.toml`: a net panel
that cannot name anything and a fragment picker with nothing in it are
broken features, not smaller ones.

`resources/samples/` — 164 KB of seven real structures.  Nothing in
the app references them today, and that is the gap: a first-run
**File → Open Sample** submenu is what makes a freshly installed app
show something in the viewport within one click instead of presenting
an empty window to somebody who does not own a CIF yet.  Small
feature, large effect on the only impression this build gets to make.

### Out

`resources/topo/` — 13 MB, and only `python -m xtal.analysis.rcsr
build` reads it.  The built index ships; its source does not.

`pormake`, the `mof` extra, and nothing else.  **Decided** —
`rdkit`, `rdeditor` and `ase` are bundled; the argument and the
numbers are [SHELL.md](SHELL.md) § 3.  The short version: RDKit buys
two whole features for ~107 MB against a bundle already heading for
~300 MB, rdeditor is a rounding error on top of PySide6, ase is 20 MB
of pure Python, and PORMAKE is 44 packages and ~889 MB including
`jax` and `pymatgen` for one dialog.

That makes the MOF builder the single feature a bundled user cannot
have.  It greys out saying so, and the Preferences extras page says
what to do about it — which is the thing that had to exist before
this could be decided, because "run `pip install`" is not advice you
can give somebody who double-clicked a DMG.

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
plugins, `tkinter`, `matplotlib`) is the difference between a ~300 MB
download and a ~1 GB one.  The app uses exactly four Qt modules —
`QtCore`, `QtGui`, `QtWidgets`, `QtSvgWidgets` — which makes the
PySide6 half of this unusually easy to be aggressive about.

Build the exclude list **empirically**: build once with nothing
excluded, read `build/*/xref-*.html`, cut the biggest thing that is
obviously unused, rebuild, launch.  Guessing at it produces a bundle
that starts and then fails on the one dialog nobody tested.

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
* **DMG**: `create-dmg`, with the `.app` and a symlink to
  `/Applications`.  A background image and a window layout are nice
  and are not phase 8.
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

`ci.yml` already triggers on `tags: ["v*"]` and already has the three
runners.  Add a `build` job, `needs: test`, `if:
startsWith(github.ref, 'refs/tags/v')`:

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
   load, writes a viewport PNG, and exits non-zero on any failure.
   That single flag covers § 3.1, § 3.2 and the VTK OpenGL context,
   which are the three things that break in a bundle and nowhere
   else.
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

## 10. Order of work

Nine steps.  Each ends with a green suite; steps 1–4 also end with
something visible on a source checkout, which is what makes them
worth doing first.

| | Step | Done when |
|---|---|---|
| 1 | Everything in [SHELL.md](SHELL.md) — logging, `QFileOpenEvent`, samples, Preferences | its own eight-step table, green suite throughout |
| 2 | Icons: draw `app.svg`, render `.icns`/`.ico` + the two document icons | they exist and look right at 16 px |
| 3 | `packaging/bundle.py` + `tests/test_packaging.py` (§ 8.1) | the test passes and fails when a data file is removed from it |
| 4 | `--selftest` (§ 8.2) | it passes on a source checkout |
| 5 | `packaging/macos.spec` → an `.app` that launches | `--selftest` passes inside the bundle; § 3.1 confirmed through the symlinks |
| 6 | Prune the bundle empirically (§ 4) | under ~350 MB, `--selftest` still green, dialogs still open |
| 7 | `packaging/windows.spec` + `.iss` | installer installs, associates, uninstalls cleanly on a fresh VM |
| 8 | DMG + the CI jobs (§ 7), build-on-main included | a tag produces three attached artifacts |
| 9 | The `workers.py` fix (§ 9), then tag `v0.1.0` | a hundred module runs finish without a hang |

Steps 5 and 7 are the ones that will take longer than they look —
both are "build, launch, read the traceback, add a hidden import,
repeat", and on Windows that loop is slow.  Budget for that rather
than for the spec files, which are short.
