# Phase 8, step 1 — what the shell owes before it can be frozen

[PACKAGING.md](PACKAGING.md) is how the app gets built.  This is the
work that comes **before** the first spec file, because every item
here is a change to the application that is testable on a source
checkout today, and every one of them is a bug in the shipped app if
it is skipped.

Four of the five are the same bug wearing different clothes: **the
app assumes there is a terminal, a developer, and a `pip`.**  A
double-clicked `.app` has none of those.  There is no stderr to print
a warning to, no shell to set `XTAL_ZEOPP` in, no environment to
`pip install` into, and nobody who knows what a Slater-Koster set is
until the app tells them.  Preferences, the log file, the sample
menu and the extras page are all answers to that.

---

## 1. Preferences

### Where it goes

`File → Preferences…`, `Ctrl+,` / `Cmd+,`.

One detail that will otherwise look like a bug: on macOS Qt
**relocates** this entry into the application menu — it appears as
*Crystal Builder → Settings…* and vanishes from File, which is
correct and is what every Mac user expects.  That happens when the
action's `menuRole` is `PreferencesRole`.  Qt guesses the role from
the action's text, and it guesses from the *English* text, so relying
on the guess is how this silently stops working.  Set it explicitly:

- `ActionRegistry.add` grows a `role=None` parameter (it currently
  takes `shortcut`, `checkable`, `checked`, `tip`, `group`), and
  `menus.py` passes `role=QAction.MenuRole.PreferencesRole`.
- A test asserting "Preferences is in the File menu" **will fail on
  macOS and pass on Linux CI**, which is the worst kind of test.
  Assert the action exists in the registry with the right role and
  shortcut, and let Qt decide where it is drawn.

`Ctrl+Q` is already `quit`; the same relocation applies to it and to
About, and neither has an explicit role today.  Setting all three at
once is one line each and is the right moment.

### The shape

A `QDialog` with a **left-hand list and a `QStackedWidget`**, not a
`QTabWidget`.  Five pages is where tabs start eliding their own
labels, the list scales to a sixth page without a redesign, and it is
what both platforms' own settings windows look like.

**Applied live, with no OK button** — a `QDialogButtonBox` carrying
`Close` only.  Every value here is a `QSettings` write plus at most a
refresh; there is nothing to roll back, and an OK/Cancel pair implies
a transaction that does not exist.  The one exception is the external
paths, which validate as you type (§ 1.5) and would be actively
misleading behind a Cancel.

`window.settings` (`AppSettings`) is the only thing the dialog talks
to, plus a `changed` signal per page for the handful of settings that
have to reach the open documents.  It gets `AppSettings` injected the
way every other dialog does, so a test can hand it a scratch domain.

### 1.1 General

| Control | Setting | Note |
|---|---|---|
| On launch | new: `startup/action` | *Empty window* / *Reopen last file* / *Open a sample*.  There is no such setting today; the app always opens empty. |
| Make a workspace beside a structure opened without one | `workspace/auto` | Exists, is `False`, and is currently reachable from nowhere at all |
| Default workspace folder | new: `workspace/root` | `default_workspace_root` is hard-coded to `~/Crystal Builder` |
| Recent files | — | a **Clear** button, mirroring `File → Open Recent → Clear` |
| Window layout | — | a **Reset** button for `clear_window`, which today is only in `Window → Reset layout` |

### 1.2 View defaults

`view/style` and `view/background` already exist and are written from
the View menu — and that is the confusion worth fixing rather than
moving.  Today, choosing *Ball and stick* in the View menu changes
**this document** and silently records a **default for the next
one**; the menu says nothing about the second half.

So: the View menu keeps acting on the current document *only*, and
this page owns the defaults, spelled *What a newly opened structure
starts as*.  Also here: `preview_interval` (milliseconds between
redraws while a calculation runs, currently a toolbar spin box), as
the same number with a sentence next to it.

**Decided**, and it is the one page that changes existing behaviour,
so it is worth a line in the release notes.  The alternative
considered was leaving the View menu writing both — which keeps the
hidden side effect, and a setting nobody knows they are changing is
not a feature.

### 1.3 Bonding

- `bonds/follow_geometry` — the checkbox currently in the Structure
  menu.  It stays in both places; it is one `QAction` and this page
  shows the same action's state.
- `bonds/default_rules` — today the only way to set these is to open
  the Bond Rules dialog *on a structure* and press its make-default
  button, so a user with no file open cannot reach them.  This page
  gets **Edit defaults…**, opening `dialogs/bond_rules.py` in a mode
  with no structure and no preview, plus **Reset to built-in**.

### 1.4 Optional features — the extras page

See § 3.  This is the page that replaces "run `pip install`".

### 1.5 External tools — the page packaging exists for

The one that matters most for a shipped app, because in a frozen
build there is no shell in which to export `XTAL_ZEOPP`.

Five rows, each: a label, a path field, **Browse…**, and a live
status line underneath.

| Row | Reads today |
|---|---|
| Zeo++ (`network`) | `PATH`, then `XTAL_ZEOPP`, then `resources/zeo++-0.3/` |
| DFTB+ (`dftb+`) | `PATH`, then its env var |
| Slater-Koster parameters | the run form's field, then `DFTB_PREFIX`, then `resources/PTBP/` |
| PORMAKE topologies | `mof/topology_dir` (exists) |
| PORMAKE building blocks | `mof/bb_dir` (exists) |

The status line is the whole point and should say what was actually
tried, in the app's own voice: *Found at `/usr/local/bin/network`* or
*Not found — looked on PATH and at `XTAL_ZEOPP`, which is not set.*
A path field that goes red with no explanation is how people conclude
the feature is broken.

**There is already a seam for this and it has never been wired.**
`xtal/modules/process.py:106` declares

```python
setting: str = ""               # the preference that names a path
```

on `Program`, and nothing sets it and nothing reads it.  `locate()`
takes a `hint` as its first candidate, ahead of the environment
variable and PATH, which is exactly the precedence a preference
should have.  So the work is:

1. Fill in `setting=` on Zeo++'s and DFTB+'s `Program`.
2. Give `xtal/` **no way to read QSettings** — the core imports no Qt
   and that rule does not bend for this.  Instead the GUI resolves
   the preference and passes it as the `hint` that `locate()` already
   takes.  One small `xtalapp` helper that maps `Program.setting` to
   an `AppSettings` key, called from the availability refresh that
   `menus.refresh_module_availability` already runs on
   `aboutToShow`.
3. The Slater-Koster directory is not a `Program`; it is
   `hsd.slater_koster_directory(given)`, whose `given` is currently a
   per-run form field. The preference becomes the form field's
   *default*, so a user sets it once instead of on every run — and
   the docstring's stated precedence (given, then `DFTB_PREFIX`, then
   bundled) is unchanged.

Doing this needs a small decision recorded in the code: **does the
preference beat `XTAL_ZEOPP`?**  Yes — `_candidates` already yields
the hint first, an environment variable is the thing a *shell* sets
and a preference is the thing a *person* set on purpose, and the
status line names whichever one won.

---

## 2. What point 2 was — `copy_metadata`, in plain terms

This one was badly explained.  It is not a feature; it is a hole
`pip` fills that PyInstaller does not.

When you `pip install` anything, pip writes a small folder of
metadata beside the code — `crystal_builder-0.4.1.dist-info/` —
holding the version number, and the list of entry points.  The code
itself does not contain either of those.  Two places in this project
read that folder at runtime:

- `xtal/__init__.py:16` calls `version("crystal-builder")` to get the
  version, with a `try/except` that falls back to `"0.0.dev0"`.  That
  is the number Help → About shows.
- `xtal/plugins.py:load` calls `entry_points(group=...)` to find
  plugins installed from outside the tree.

PyInstaller copies **code**, not that metadata folder.  So in a
bundle, with no change:

- `version("crystal-builder")` raises `PackageNotFoundError`, the
  `except` catches it, and **About reports `0.0.dev0` on every
  release**.  That is worse than showing nothing, because it looks
  like a real version and a bug report quoting it is useless.
- `entry_points(...)` returns an empty list and every out-of-tree
  plugin silently stops existing.

`copy_metadata('crystal-builder')` is one line in the spec telling
PyInstaller to bring that folder along.  Then About shows the git tag
the release was built from.

The plugin half deserves an honest answer rather than a fix: a
frozen app has no `pip` and therefore nowhere to install a plugin
*to*.  So the shipped build supports in-tree modules only, the
release notes say so, and § 3 is what stands in for it.

---

## 3. Extras in a frozen app — and why `pip install` is not an answer

The four optional features are gated by `find_spec` and grey out
naming an extra: `mof` (pormake), `build` (rdkit), `sketch`
(rdeditor), and ase.  In a source checkout the greyed-out entry's
advice — `pip install 'crystal-builder[mof]'` — is exactly right.

**In a bundle it is meaningless.**  There is no environment to
install into; the bundled interpreter is not on the user's PATH and
has no `pip`.  Repeating that sentence in a nice dialog would be a
polished way of saying something untrue.

So the answer is mostly *bundle it*, and the rest is honesty:

| | Bundle? | Why |
|---|---|---|
| **rdkit** (~107 MB) | **yes** | Buys two whole features — build from SMILES, and the sketcher.  Greying out *Draw* in a GUI-only distribution hides Phase U from exactly the people it was for. |
| **rdeditor** (~1 MB) | **yes** | PySide6 + a theme package, both already bundled.  Free. |
| **ase** (~20 MB) | **yes** — changed | I had this excluded.  It is small, pure Python, and it is I/O; excluding it saves nothing and costs a format. |
| **pormake** | **no** | 44 packages, ~889 MB, `jax` and `pymatgen`, and a ten-second import, for one dialog. |

That leaves **pormake as the only feature a bundled user cannot
have**, which is a much smaller problem than four of them, and it is
the one where the size argument is overwhelming.

### The extras page, then

A page that tells the truth about each, with what is actually
actionable:

- **Bundled and working** — rdkit, rdeditor, ase: a tick, one line
  saying what it powers.  No command, because there is nothing to do.
- **PORMAKE — not included** — a short paragraph saying why (the
  honest one: it is larger than the rest of the application put
  together), what is lost (the MOF builder; net identification and
  the `.cgd` reader are this project's own and keep working), and the
  two real routes:
  1. *Run Crystal Builder from Python instead*: `pip install
     'crystal-builder[gui,mof]'`, then `crystal-builder` — a **Copy**
     button beside the command and a link to the README.  This is the
     supported route.
  2. *Add it to this copy*: a user-writable folder — `Application
     Support/CrystalBuilder/packages` on macOS, `%APPDATA%` on
     Windows — that the app prepends to `sys.path` at startup, with
     **Reveal in Finder** and a copyable `pip install --target
     "<that folder>" pormake`.

**Decided: build both.**  Route 2 needs a warning printed **on the
page and not in a doc nobody opens** — it works for pure-Python
packages, and it is not reliable for pormake, whose dependencies are
compiled and must match the bundled interpreter's exact Python
version and ABI, and whose numpy would collide with the bundled one.
So the page recommends route 1 for pormake specifically, and route 2
exists because it is ten lines and it is the mechanism that makes any
future plugin possible in a bundle at all — which § 2 otherwise
leaves with no answer.

Rejected: bundling pormake and shipping a ~1 GB download.

---

## 4. The log file, and the exception nobody sees

`xtalapp/main.py:36` prints plugin failures to `sys.stderr`.  A
`--windowed` build has no stderr, so that warning goes nowhere — and
worse, an uncaught exception anywhere takes the window down with no
traceback and nothing on disk.  For a tool that shells out to other
people's binaries and parses other people's CIFs, the first bug
report is going to be "it closed", with nothing attached.

**`xtalapp/applog.py`** — not `logging.py`; absolute imports mean it
would not actually shadow the standard library, but a file called
`logging.py` inside a package that also imports `logging` is a
half-hour somebody loses later.

```
applog.setup(directory=None) -> Path
```

- Writes to `QStandardPaths.AppDataLocation` —
  `~/Library/Application Support/CrystalBuilder/` on macOS,
  `%APPDATA%\CrystalBuilder\` on Windows — as
  `crystal-builder.log`, and **returns the path** so callers can
  name it.
- `RotatingFileHandler`, 1 MB × 3.  A tool that runs 200-step
  relaxations and tails Zeo++'s tens of thousands of voro++ lines
  will produce a log that grows without bound otherwise.
- `sys.excepthook` logs the traceback, then shows a `QMessageBox`
  naming the log with a **Show log** button.  Guarded so a failure
  *inside* the hook cannot recurse, and inert during interpreter
  shutdown.
- `qInstallMessageHandler`, so Qt's own warnings — every one of which
  goes to stderr today and vanishes in a windowed build — land in the
  same file.
- The plugin-failure `print` in `main.py` becomes a log call.

**Called from `main()` only, never from `MainWindow.__init__`.**  A
window built by a test must not install a process-wide excepthook or
scribble in the developer's real Application Support — which is
exactly the mistake that left 278 plists behind, so it is a mistake
this repo has already paid for once.  `conftest.py` points
`applog.setup` at a temp directory the same way it already points the
QSettings INI backend at one.

Two interactions with logging that already exist and must not
regress, both worth a test:

- `xtalapp/dialogs/sketch.py:383` saves and restores the **root**
  logger's level and handlers around constructing rdeditor's widget,
  because `MolWidget.__init__` calls `logging.basicConfig` and sets
  the root level.  Our file handler goes on the root logger, so that
  save/restore is what protects it — it works, and the test is what
  says so.
- `xtal/mof/build.py:399` swaps `logging.FileHandler` while importing
  pormake, so pormake's `runtime.log` lands in a temp folder rather
  than the working directory.  Our handler is installed long before
  and is untouched by that.

**Help → Show log** reveals the file in Finder/Explorer
(`QDesktopServices.openUrl` on the containing folder — revealing the
folder, not opening a 1 MB text file in whatever claims `.log`).  The
Help menu currently has exactly one entry, About.

---

## 5. `QFileOpenEvent`

`main.py` reads paths off `argv`, which is how Windows file
associations and a **cold** macOS launch deliver a file.  It is not
how macOS delivers one to an app that is **already running**: that
arrives as a `QFileOpenEvent` on the `QApplication`, and nothing
handles it today.  So with the window open, double-clicking a second
`.cif` does nothing at all — which reads as the association being
broken, and is the first thing anybody tries after installing.

A `QApplication` subclass in `xtalapp/application.py` overriding
`event()`:

- The event can arrive **before the window exists** — macOS delivers
  it during startup for a cold launch-by-double-click, ahead of
  `MainWindow` being constructed.  So the app queues paths, and the
  window drains the queue on construction.  Getting this backwards
  is the classic version of this bug: it works when you test it with
  the app already open and silently drops the file on a cold launch.
- Draining calls the same `MainWindow.open` that the argv loop at
  `mainwindow.py:140` already calls, so a file opened this way is
  identical to one opened any other way.
- Test note: check whether PySide6 exposes a `QFileOpenEvent`
  constructor.  If it does, `app.event(...)` is a real end-to-end
  test.  If it does not, test the queue-and-drain as a plain object
  and the `event()` override with a stub — do not skip it, because
  this is a code path no developer ever exercises by hand.

---

## 6. File → Open Sample

`resources/samples/` holds seven real structures — MOF-5, HKUST-1,
ZIF-8, MFU-4l, Ni₂Cl₂BTDD, CFA-1, zinc acetate — 164 KB in total, and
**nothing in the application references them.**

A freshly installed app currently opens an empty window to somebody
who may not own a CIF yet.  A submenu that puts a real framework on
screen in one click is the cheapest possible improvement to the only
first impression this build gets, and it is also what makes the
`--selftest` in [PACKAGING.md](PACKAGING.md) § 8 have something to
open.

They open **read-only-ish**: as a new untitled document with no path,
so `Ctrl+S` asks where to put it rather than writing inside the
application bundle, which on macOS is signed and on Windows is under
`Program Files`.

---

## 7. Order, and what each step is done by

Every step ends with a green suite.  Steps 1–3 are also useful on a
source checkout on their own, which is why they come first.

| | Step | Done when |
|---|---|---|
| 1 | `applog.py`, the excepthook, the Qt message handler, `Help → Show log`; `conftest` redirection | a raised exception writes a traceback to a temp log in the suite, and the sketcher test still passes |
| 2 | `xtalapp/application.py` + the queue/drain; argv path unchanged | tested cold and warm |
| 3 | `File → Open Sample` | seven entries, opening as untitled documents |
| 4 | `ActionRegistry.add(role=...)`; explicit roles on Preferences, Quit, About | the action exists with `PreferencesRole` and `Ctrl+,` |
| 5 | The Preferences shell + **General** and **View defaults** pages | settings round-trip through a scratch `AppSettings` |
| 6 | **Bonding** page; Bond Rules opens with no structure | defaults editable with no file open |
| 7 | **External tools** page; `Program.setting` wired through `locate(hint=...)` | a path set in Preferences makes a greyed-out module light up without restarting |
| 8 | **Optional features** page; the `sys.path` folder; README section | the page tells the truth on a source checkout *and* would in a bundle |

Step 7 is the one with a design decision in it (§ 1.5) and step 8 is
the one with a product decision in it (§ 3).  The rest is ordinary
work.

Only after all eight does [PACKAGING.md](PACKAGING.md) § 3 shrink to
`copy_metadata` alone and the first spec file become worth writing.
