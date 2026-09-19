# UI / UX review — does this meet the standard needs of a desktop scientific application?

> **Written 2026-09-18** against `Crystal-Builder` at commit `3cd15e2` (v0.2.1), the base of branch `features/deep-review`. `origin/main` has since moved to `fb38d25`. Line numbers, measurements and code references below were true at `3cd15e2` — re-verify before acting on one if the file has changed since.


Reviewer topic: interface and interaction. Judged against what somebody who
already uses VESTA, Mercury, Avogadro or CrystalMaker expects on day one.
Everything below was produced with the real window through
`.venv/bin/python .claude/skills/run-app/drive.py --scratch ...` on
2026-09-18; screenshots are in `../shots/`, probe scripts in `../probes/`.

**Summary.** The parts a crystallographer touches — dialogs, panels, menus,
the wording of what a command *does* — are better than most academic
software: live previews before you commit, units on nearly every number,
plain-English tooltips on 134 of 141 actions, macOS menu roles said rather
than guessed, Esc cancels every dialog. What is weak is the *shell* around
them: on a fresh launch the 3-D view gets 352 px of a 1249 px window (133 px
at 1024×700), the empty window offers no next step at all, and the one
irreversible thing the app does silently — Save File converting a CIF into a
project — is explained only in Preferences. Nothing is autosaved, and
closing the window stops a running calculation without asking. The
accessibility story is untried: no `accessibleName` and no `setBuddy`
anywhere, and the amber warning styling is hard-coded for a light theme.
Ranked findings follow, then a panel/dialog table, then ten improvements
that are in neither `docs/ROADMAP.md` nor `docs/TODO.md`.

---

## Findings

### 1. `[important]` The 3-D view is a quarter of the window, and unusable at 1024×700

**Where** `xtalapp/layout.py` (default dock layout), `xtalapp/settings.py:320`
`restore_window` (no deliberate default size), `xtalapp/docks/sites.py`.

**Evidence**

```
$ .venv/bin/python .claude/skills/run-app/drive.py --scratch review/shots/scratch9 \
    --open resources/samples/MOF-5.cif --eval '...widths...'
window PySide6.QtCore.QSize(1249, 849)
  info_dock: 380px  file_dock: 380px  sites_dock: 515px
central 352
after 1024:
  info_dock: 377   file_dock: 377   sites_dock: 512
central 133
```

A *fresh* window (`--scratch`, no saved geometry) sized to 1024×700 gives the
same 133 px: this is not an artefact of shrinking a restored layout.
[First run with MOF-5](../shots/02-mof5-default-layout.png) ·
[fresh window at 1024×700](../shots/11-fresh-window-1024x700.png) ·
[resized to 1024×700](../shots/10-window-resized-1024x700.png), where the
central area is a 133 px sliver of stale framebuffer between two panels and
the tab is elided to `MOF…`.

**Why it matters** This is a structure viewer. In VESTA, Mercury and
CrystalMaker the model owns most of the window and the tables are the side
show; here three text panels own 72 % of it on first run and 87 % on a
1024-wide screen (a projector, a small MacBook, a split-screen half). The
Sites table alone asks for 515 px so that eight columns of five significant
figures fit, and it is shown by default. The `MAXIMUM_MINIMUM` invariant is
honoured — every panel's *minimum* is ≤ 115 px, so the dividers do move —
but nothing sets the *initial* proportions, so they come from the sum of
size hints.

**A fix** Give the central widget a starting share (`resizeDocks` on first
construction, e.g. 22 % / 50 % / 28 %), and/or show only Structure +
Workspace by default with Sites tabbed behind Structure. A saved layout
still wins, so this only changes the first run.

---

### 2. `[important]` The empty window offers no next step

**Where** `xtalapp/mainwindow.py:165` (`setCentralWidget(self.tabs)`),
`xtalapp/mainwindow.py:1524` (`"No structure open"`).

**Evidence** [First run, nothing open](../shots/01-first-run-empty-window.png):
the centre is an empty grey `QTabWidget`, the Structure panel says
`No structure open.`, the Workspace panel says `Nothing in this workspace
yet`, and the status bar is showing a filesystem path. There is no Welcome
pane, no "Open a sample", no drop hint — even though **drag-and-drop already
works** (`setAcceptDrops(True)`, `dropEvent`, `mainwindow.py:111,1739`) and
seven samples are bundled (`File ▸ Open Sample`).

The workspace chooser that precedes it is *good* — see
[the chooser](../shots/dlg/workspace_chooser.png): it explains the word
("Structures, calculations and everything they leave behind are kept in one
folder."), preselects the last workspace so Return is the answer, and offers
`Open Sample` right there. All that goodwill lands on a blank grey rectangle.

Two smaller things visible in the same shot. The status bar's first words on
a first run are `workspace: /Users/.../scratch/workspace` — a six-second
transient (`workspace_shell.py:178`) that *hides* the permanent line, so the
one sentence written for this state ("No structure open") is not what the
user reads. And the grab catches the two painted over each other
([crop](../shots/04-first-run-statusbar.png)); that one is a repaint race at
startup rather than a layout bug — `win.status_label.isVisible()` is `False`
while a message is up, and a later grab is clean
([later](../shots/30b-statusbar-transient-message-crop.png)) — but it is what
the window looked like in the first frame after launch.

**Why it matters** Day-one abandonment happens on this screen. Mercury and
Avogadro both put a start pane in the empty central area.

**A fix** Draw a placeholder in the empty tab area: the app icon, "Open a
file (⌘O), drag one here, or try a sample", and the seven sample buttons —
the same list the chooser already builds.

---

### 3. `[important]` A missing external program is a greyed word with no reason

**Where** `xtalapp/module_runner.py:112-117`, `xtal/modules/process.py:224`
(`availability`), `xtalapp/docks/modules.py`.

**Evidence** With no Zeo++, DFTB+ or Blender installed:

```
$ ... --script review/probes/docks_and_modules.py
  dftb  ok=False  DFTB+ is not installed, or not on PATH (XTAL_DFTB is not set).
                  It is at https://dftbplus.org  (conda install 'dftbplus=*=nompi_*' -c conda-forge)
  zeopp ok=False  Zeo++ is not installed, or not on PATH (XTAL_ZEOPP is not set).
                  It is at https://www.zeoplusplus.org/
  action enabled: True
  status message after clicking Zeo++ volume: 'Zeo++ is not installed, or not on PATH ...'
```

The sentence is excellent — it names what was looked for, which variable is
unset, where to get it, and even the conda line. Where it is *shown*:

* `Modules ▸ Zeo++` / `DFTB+` / `Blender` — the submenu is greyed, so the
  user never opens it and never sees a reason
  ([modules panel](../shots/40-docks-structure-sites-workspace-modules.png),
  right pane: the same entries greyed);
* the DFTB+ panel prints it in `palette(mid)` grey
  ([DFTB+ panel](../shots/42-docks-ff-dftb-net-results.png), second pane);
* the status bar, for six seconds, if you reach the action another way.

Clicking `DFTB+: Single point energy` (which is enabled as an action) reveals
the DFTB+ panel and says **nothing**: `status message: ''`, no message box
([after the click](../shots/33-after-dftb-click.png)).

**Why it matters** "The Zeo++ menu is greyed out" is the single most common
support question this class of application generates, and the answer already
exists as a formatted sentence one function call away.

**A fix** `menu.setToolTipsVisible(True)` plus the availability reason as the
disabled action's tooltip, and a one-line label under the greyed group in
the Modules panel. Better still, keep the entries live and open a small
"Zeo++ is not installed — here is where to get it / point me at it" sheet
with a Browse button that writes the preference.

---

### 4. `[important]` Save File converts a CIF and never says so the first time

**Where** `xtalapp/documents.py:365-403` (`save_document`), `:405`
(`_save_target`), `xtalapp/dialogs/preferences.py` (General page).

**Evidence** The invariant is deliberate and documented (CLAUDE.md, "Save
File converts, and never asks where"). What the user gets on ⌘S over
`MOF-5.cif` is `show_message(f"saved {written.name}")` — a six-second status
line reading `saved MOF-5.xtalproj` — plus a tab title that quietly changes.
The explanation exists, but only in
[Preferences ▸ General](../shots/dlg/preferences.png): *"Save File writes
the session over the file the tab is… A structure opened as a CIF becomes
the project beside it on its first save, and that CIF is left where it is."*
— in the low-contrast hint grey, under a checkbox that is off by default.

**Why it matters** Every other program the user has ⌘S'd in this field
updated the file they opened. Somebody who edits a CIF, saves, and mails
"the CIF" to a collaborator mails the unedited one. The design is right; the
*disclosure* is missing at the one moment it is being made.

**A fix** A first-time-only sheet at the moment of conversion — "Saving keeps
the measurements, planes and view, which a CIF cannot hold, so this tab is
now MOF-5.xtalproj. MOF-5.cif is unchanged. [Don't show this again]" —
stored next to `settings.confirm_overwrite`, which is exactly the same shape.

---

### 5. `[important]` No autosave, no crash recovery, and quitting stops a run without asking

**Where** `xtalapp/mainwindow.py:1807-1818` (`closeEvent`),
`xtalapp/module_runner.py:249` (`stop_module`).

**Evidence**

```
$ grep -rni "autosave\|auto-save\|crash recover\|recovery" xtal/ xtalapp/ --include=*.py
(no matches)
$ ... --eval 'print([n for n in dir(win) if "autosav" in n.lower()])'
[]
```

```python
def closeEvent(self, event):
    self.stop_module()                       # <- no question asked
    if not self._quit_confirmed and not self.may_discard_unsaved():
```

The unsaved-edit question is asked properly (and `close_all` asks once per
window, not per tab). But a module run — which the scan documentation
itself calls an overnight job — is cancelled *before* the question, so
answering "Cancel" to the quit prompt does not bring the run back. And an
app that is killed, or that hits the known `workers.py` teardown deadlock
(CLAUDE.md § Testing the GUI, seen in the shipped app 2026-09-15), loses
every unsaved edit in every tab.

**Why it matters** A structure is usually 20 minutes of fiddly hand editing.
Mercury, Avogadro and VESTA all lose it too — but none of them ship with a
documented hang that "can hang the shipped application when a module run
finishes".

**A fix** (a) ask before stopping a run: "A calculation is still running.
Stop it and quit?"; (b) write each modified document to
`<workspace>/.autosave/<entry>.xtalproj` on a timer and on every N undo
steps, and offer recovery at the next launch from the chooser, which is
already the right place to offer it.

---

### 6. `[important]` Find symmetry's default button is *Close*, and it sits left of *Adopt*

**Where** `xtalapp/dialogs/find_symmetry.py`.

**Evidence** from `review/probes/dialogs.py`:

```
--- find_symmetry: FindSymmetryDialog
    buttonbox: 'Adopt this group'[AcceptRole], 'Close'[RejectRole]*DEFAULT,
               'Label Wyckoff only'[ActionRole]
```

[Screenshot](../shots/22-dialogs-symmetry-and-export.png) (top-left): the
blue, focused button is **Close**, and `Adopt this group` is to its right,
outside it. Pressing Return after reading `Fm-3m (#225), 192 operations,
7 independent sites` throws the answer away.

Every other dialog in the app gets this right (`'OK'*DEFAULT` /
`'Merge'*DEFAULT` / `'Run'*DEFAULT` with Cancel to the left), which is why
this one reads as a slip rather than a house style.

**A fix** `setDefault(True)` on the accept button and let `QDialogButtonBox`
order them; keep `Label Wyckoff only` as the ActionRole button on the left.

---

### 7. `[minor]` Panel labels overlap at the width the app's own column gives them

**Where** `xtalapp/docks/trajectory.py`, `xtalapp/docks/__init__.py:17`
(`scrolling`).

**Evidence** Trajectory panel floated at 440 px (the right column is 515 px
by default):
[Loop/Speed collision](../shots/45-trajectory-labels-overlap.png) —
`Loop` and `Speed` are painted on top of each other, and lower down
`No trajectory open` is painted over the `Adopt this frame` button
([full panel](../shots/43-docks-trajectory-log.png)). Measured minimums:

```
trajectory_dock: dock min 69   content min 69   hint 554
move_dock:       dock min 69   content min 69   hint 335
measure_dock:    dock min 69   content min 69   hint 419
```

The `MAXIMUM_MINIMUM` invariant is satisfied by giving the scroll area a 69 px
minimum — but the inner layout is then squeezed 485 px below its hint and Qt
stops honouring spacing rather than scrolling.

**A fix** Give the *inner* widget of each scrolling panel a sensible
`minimumWidth` (≈ its hint) so the scroll area scrolls instead of squeezing;
the dock's own minimum stays small because a `QScrollArea` has one of its own.

---

### 8. `[minor]` Only the Style panel reflows; the rest scroll sideways

**Where** `xtalapp/docks/columns.py` (`ReflowColumns`, used by the Style
panel).

**Evidence** [Every panel at 240 px](../shots/44-docks-squeezed-to-240px.png):
Style reflows to a single legible column (the mechanism works and is nice);
Force Field, Move, Measure and Trajectory all sprout a horizontal scroll bar
and hide half their controls off the right edge. A horizontal scroll bar in
a form is the least usable answer to "narrow".

**A fix** Use `ReflowColumns` (or a `QFormLayout` in `WrapLongRows` mode) for
the other form panels; the Style panel proves the machinery.

---

### 9. `[minor]` The Move panel's buttons are live with nothing selected

**Evidence**

```
move_dock: 'Apply' enabled=True   'Apply -' enabled=True   'Apply' enabled=True
           'Mirror' enabled=True  'Make planar' enabled=True
measure_dock:  every button enabled=False
inspector_dock: 'Delete' False  'Reduce to P1' False
```

The panel's own header says `Nothing selected`
([screenshot](../shots/41-docks-style-measure-move-inspector.png), third
pane) while five buttons that need a selection invite a click. Measure and
Inspector disable correctly, so this is an inconsistency rather than a house
rule. `Edit ▸ Paste` is similarly enabled with an empty clipboard and
answers `nothing to paste` (`mainwindow.py:519`).

Also worth noting: `Apply -` is not a label anybody will read correctly.

---

### 10. `[minor]` The toolbar overflows at the app's own default window size

**Evidence** `toolbar sizeHint: QSize(1342, 34)  width now: 1249` — so on
first run `Along a`, `Along b`, `Along c` are folded into the `»` chevron:
[the right end of the toolbar](../shots/05-toolbar-overflow-chevron.png).
`docs/MENUS.md` § 3 measured the bar at 1214 pt and reasoned it fitted; it is
1342 pt now, and the window the app opens at is 1249 pt.

**A fix** Either icon-only buttons for the three axis views (their icon text
is already one letter) or `Qt.ToolButtonTextBesideIcon` on the heavy ones.
`docs/MENUS.md` already owns the "icons are a separate piece of work"
decision; the point here is that the bar has since crossed its own limit.

---

### 11. `[minor]` Dark mode: the chrome follows the system, three things do not

`docs/TODO.md` line 2 asks for "an option for dark mode". Going past that:
the Qt chrome **already** follows the system theme — every screenshot here is
dark without a line of configuration, and there are only 22 hard-coded hex
colours in `xtalapp/` (`grep -rn "#[0-9a-fA-F]\{6\}" xtalapp/ | wc -l` → 22)
against 41 palette-role uses. So "dark mode" is mostly a question of three
specific places:

1. **The 3-D background is hard-coded white** — `settings.py:404-406`,
   `view_settings.py:196` default `BACKGROUNDS["white"]`. The result is a
   white rectangle in the middle of a dark application:
   [viewport](../shots/03-mof5-viewport-white-background.png). A "Follow the
   system" choice belongs beside `View ▸ Background ▸ White/Black/Slate/Paper`.
2. **14 warning labels are `color: #8a5a00`**, six of them with
   `background: #fdf3e0` (cell_edit, find_symmetry, spacegroup, subgroup,
   inspector, info). Dark amber on the dark panel background is barely
   legible, and the cream box is a light patch in a dark window.
3. **Hint text is `color: palette(mid)`** (`preferences.py:76` and the run
   progress dialog), which on the macOS dark palette is close to the
   background: see the Preferences and Cell-edit screenshots
   ([1](../shots/dlg/preferences.png),
   [2](../shots/21-dialogs-structure-edits.png), middle) — the sentence
   explaining what Save File does is nearly invisible. `palette(placeholder-
   text)` or a 60 %-alpha `WindowText` reads in both themes.

---

### 12. `[minor]` Screen readers have nothing to read

**Evidence**

```
$ ... --eval 'count accessibleName over QAbstractSpinBox/QLineEdit/QComboBox/QCheckBox/QAbstractItemView'
input widgets in the window: 173, with an accessibleName: 0
$ grep -rn "setBuddy" xtalapp/ --include=*.py | wc -l        → 0
$ grep -rn "setAccessibleName" xtalapp/ --include=*.py | wc -l → 0
$ grep -rn "setToolTip" xtalapp/ --include=*.py | wc -l       → 142
```

Tooltips are thorough (134 of 141 registry actions carry a tip beyond their
own text); accessibility names are entirely absent, and with no
`QLabel::setBuddy` the label beside a spin box is not associated with it
either, so VoiceOver reads "text field" for the cell lengths. The custom
widgets (viewport, periodic table, heat map, site table) expose nothing at
all. Keyboard-only navigation of the docks could not be judged headlessly
(`focusNextChild` reported `focusWidget() is None` with the window inactive)
— it needs a person at the keyboard, like the panel-drag entry in TODO.md.

Good news in the same area: the font is the system font at the system size
(`.AppleSystemUIFont 13.0`) with **no** hard-coded pixel sizes anywhere, so
text scaling works; screenshots come back at 2498×1698 for a 1249×849 window,
so the whole UI is rendering at 2× and there are no bitmap icons to go soft.

---

### 13. `[minor]` Two different things are called "Log"; one number is asked for three ways

*Naming.* `Window ▸ Log` is a read-only view of **a module run's** log file
(`xtalapp/docks/logview.py:49`, "No log open" when nothing has run), while
`Help ▸ Show Log` reveals **the application's** crash log folder in Finder
(`applog.reveal`). Same word, unrelated things.

*Widgets.* The same kind of quantity — a length tolerance in Å — is asked for
with three different controls:
`Find symmetry` uses an editable combo box (`Tolerance (A) [0.1 ▾]`),
`Merge duplicate sites` a spin box **plus** a slider (`0.050 A` + slider),
`Bond rules` a spin box plus a slider for `Radius factor` and plain spin
boxes for `Extra allowance` / `Ignore closer than`. See
[22-dialogs](../shots/22-dialogs-symmetry-and-export.png) and
[23-dialogs](../shots/23-dialogs-bondrules-fill-progress-help.png).
Likewise `Add atom` offers an element combo **plus** a `Table...` button onto
the periodic table, while `Add centroid` offers the combo alone.

*Units.* Every unit in the interface is ASCII — `A`, `A^3`, `deg`, `1/A`,
`A^2`, `kcal/mol/A` — including the status bar (`V = 17305.33 A^3`). It is
*consistent*, which is the hard half; but `Å`, `Å³` and `°` are what every
neighbouring program prints, and the status line is the app's shop window.
(Phase 2 rewords strings, so this is a typography decision to make before
that batch rather than a new task.)

---

### 14. `[minor]` An error is a modal and then it is gone

**Evidence** (`review/probes/errors.py`, with `QMessageBox` recorded rather
than refused):

```
missing file  -> warning['Could not open the file',
    'does-not-exist.cif\n\n[Errno 2] unable to open() file ... : No such file or directory']
corrupt CIF   -> warning['Could not open the file',
    'corrupt.cif\n\nreview/probes/corrupt.cif:6:0(95): Wrong number of values in loop _atom_site_*']
empty file    -> warning['Could not open the file', 'empty.cif\n\nno structure found in empty.cif']
a .py file    -> warning['Could not open the file', "errors.py\n\nno format is registered for '.py'"]
```

Three of the four are in the user's words and the CIF one even carries a line
number — much better than a traceback. But: the `[Errno 2] unable to open()`
string leaks the C API; and `documents.py:233-238` shows the box and does
**not** log, so once it is dismissed there is no record anywhere (the Log
dock shows module runs only). A user who wants to paste the parser error into
an email has to reproduce it.

**A fix** Route these through `logging` as well as the box (the handler is
already installed, `applog.setup`), and let `Help ▸ Show Log` be where they go.

---

### 15. `[strength]` What is already good, specifically

* **Every dialog can be cancelled with Esc**: none of the 18 dialogs
  overrides `keyPressEvent` or `reject`, so `QDialog`'s Esc works
  everywhere; and of the 16 that have an accept button, 15 make it the
  default (the exception is finding 6).
* **Live preview before committing**: Supercell says
  `supercell 1x1x1: 424 sites, 424 atoms, V = 17305.33 A^3`; Set space group
  says `424 sites generate 424 atoms in P1`; Merge duplicates says
  `no duplicates within 0.05 A … Widen it if the same atom was refined into
  two places`; Bond rules says `512 bonds -- no change from the current
  rules`; Display range says `1 x 1 x 1 cells -- roughly 424 atoms of the 424
  in one cell, plus the closing faces`. Very few programs in this field tell
  you the answer before you press OK.
* **The scan dialog costs the job before you start it**: *"14 points, up to
  about 19 minutes. Relaxed scan holding a at each of 7 values, with the cell
  relaxed, holding a, seeded from the previous point, walked in both
  directions."* ([module dialogs](../shots/50-module-dialogs-zeopp-scan-pxrd-dftb.png))
* **Run progress is honest**: indeterminate bar by choice ("a bar creeping to
  90 % and sitting there is a worse lie"), the latest log line, elapsed time
  that ticks, `Stop` that becomes `Stopping…` and disables itself, `Hide`
  that leaves the run alone, and closing the window does not kill the job
  (`run_progress.py:168`).
* **macOS conventions are stated, not guessed**: `QuitRole`, `AboutRole`,
  `PreferencesRole` with ⌘, and a comment explaining that Qt's text
  heuristic would break on the first reword (`actions.py:43`). `⌘N ⌘O ⌘S
  ⇧⌘S ⌘W ⇧⌘W ⌘Z ⇧⌘Z ⌘X ⌘C ⌘V ⌘A ⌘I ⌘0 ⌦` are all where a Mac user's fingers
  go, and Help is on ⌘?.
* **Selection is richer than VESTA's**: `Select ▸ By element ▸ C/H/O/Zn`
  built from the structure, `Grow ▸ bonded neighbours / whole fragment /
  symmetry orbit`, invert over orbits, box select, plus a hover tooltip
  naming the atom under the cursor (`widget.py:602`), a two-way link between
  the Sites table and the 3-D selection, and a status line reading
  `424 atoms (C192 H96 O104 Zn32), 512 bonds`.
* **Context menus are counted**: `Measure` appears only at the counts where
  it means something, and `Delete 11 bonds` says eleven (`menus.py:850-870`).
* **Energy units are consistent across engines**: MACE (eV), DFTB+ and xTB
  (Hartree) are all converted at the boundary so the interface only ever says
  kcal/mol (`ff/mace/calculator.py:69`, `ff/dftb/calculator.py:68`,
  `ff/xtb/calculator.py:74`); electronic quantities stay in eV, which is
  correct. Gradients are `kcal/mol/A`, stresses `GPa`, everywhere.
* **The built-in Help window** already lists every command, its key and what
  it does, generated from the registry
  ([screenshot](../shots/23-dialogs-bondrules-fill-progress-help.png)).
* **Empty states mostly say what to do**: "Switch to the Measure tool, then
  click atoms", "Pick Draw net in the toolbar and click two atoms", "Nothing
  has been run yet. A module that produces a table, a histogram or a curve …
  shows it here when it finishes", "open a molecule, or browse for one".
  The empty *window* (finding 2) is the exception.

---

## Every panel and every dialog, one line each

Panels — `--list-docks` on a fresh window; 14 docks, 3 shown by default.
Screenshots: `../shots/dock/<name>.png`.

| Panel | Shown at start | Verdict |
|---|---|---|
| Structure (`info_dock`) | yes | Dense, readable, monospaced; the `file` row is clipped at any real width and scrolls sideways rather than eliding. |
| Workspace (`file_dock`) | yes | Clear tree, bold marks the open file; **no context menu at all** — no Reveal in Finder, rename, delete or "open in new tab". |
| Sites (`sites_dock`) | yes | Editable, two-way selection sync — the best panel here; not sortable, and its 515 px hint is what squeezes the 3-D view. |
| Modules | no | Correctly greys DFTB+/Zeo++/Blender, but never says why (finding 3). |
| Inspector | no | Good empty state, buttons correctly disabled, hard-coded cream warning box. |
| Net | no | Good empty-state sentence, but it does not wrap and is clipped at 440 px. |
| Move | no | Buttons live with nothing selected (finding 9); `Apply -` is opaque; needs 335 px. |
| Style | no | The model panel: groups reflow to one column when narrow, editable per-element colour/radius (Jmol/CPK default, `xtal/core/elements.py:29`). |
| Measure | no | Clean table, disables correctly, tells you which tool to switch to. |
| Force Field | no | Units on every field, atom types with "What it means"/"Sure?" columns — excellent. |
| DFTB+ | no | Mirrors Force Field; shows the "not installed" sentence in near-invisible grey. |
| Trajectory | no | Labels overlap at 440 px (finding 7); unusable below ~300 px. |
| Log | no | A module run's log, monospaced with a `Follow` toggle; raw binary output, so useful to a specialist, not to a beginner — and it is not where application errors go. |
| Results | no | Good empty state explaining what will appear there. |

Dialogs — built with `imp(...)` and grabbed (`review/probes/dialogs.py`,
`review/probes/modules_dialogs.py`); screenshots `../shots/dlg/`.

| Dialog | Buttons (default first) | Verdict |
|---|---|---|
| Workspace chooser | `Continue*` / Quit, + New / Open Other / Open Sample | Best screen in the app; Esc = quit the application with no confirmation, and there is no "don't ask me again". |
| Preferences | `Close` only | Four sensible pages, settings apply live; one `Browse...` is the dialog's **default button**, so Return opens a folder picker; hint text nearly invisible in dark mode. |
| Supercell | `OK*` / Cancel | Multiples/Transformation tabs, live preview. Good. |
| Edit unit cell | `OK*` / Cancel / Reset | Live volume preview and a constraint note; units `A`, `deg`. Good. |
| Find symmetry | `Close*` / Adopt this group / Label Wyckoff only | Wrong default and wrong order (finding 6); the table itself is excellent. |
| Set space group | `OK*` / Cancel | Searchable list of every number/H-M/Hall setting, Generate/Impose radios, live count. Good. |
| Descend to a subgroup | `Descend*` / Cancel | Works; slow to build on MOF-5 with no progress hint. |
| Merge duplicate sites | `Merge*` / Cancel | Live "no duplicates within 0.05 A" and an explanation; Merge correctly disabled. |
| Display range | `OK*` / Cancel / One whole cell | Clear from/to grid, boundary-bond radios, live atom estimate. Good. |
| Add atom | `OK*` / Cancel + `Table...` | Fractional/cartesian combo, occupancy, `auto` label placeholder. Good. |
| Add centroid | `OK*` / Cancel | Good, but its element picker is a bare combo where Add atom has combo + periodic table. |
| Add hydrogens | `Add*` / Cancel | Reports what it will and will not touch ("32 metal site(s) (Zn) — what a metal is missing is a coordination number…"); Add disabled when there is nothing to do. |
| Bond rules | `OK*` / Cancel / Restore Defaults | Rich, previews the bond count, offers "use these rules from now on". |
| Export | `Export*` / Cancel | Format combo explains each format; symmetry vs P1 radios; "Selected atoms only" greys out correctly. |
| Export Image | `Export*` / Cancel | Resolution as a multiplier with the pixel size beside it. Good. |
| Save as a building block | `Save*` / Cancel | Save disabled with a **magenta** warning sentence — the only magenta in the app. |
| Fill pores | `Fill*` / Cancel | Fill disabled with "open a molecule, or browse for one". Good. |
| Run progress | `Hide*` / `Stop` (no button box) | Honest and well behaved; `Hide` being the default means Return dismisses it, which is the safe choice. |
| Help | `Close*` | Generated command and module reference; shortcuts print as `Ctrl+N` where the menu shows `⌘N`. |
| Zeo++ / PXRD / STL / DFTB+ forms (`ModuleDialog`) | `Run*` / Cancel | Generated forms with unit suffixes (`A`, `deg`, `A^2`, `eV`, `mm`) and a description at the top; values remembered per action for the session only. |
| Relaxed scan | `Run*` / Cancel | Costs the run in points and minutes before you start it. Outstanding. |
| MOF builder | `Build*` / Cancel | 616×931 — the largest dialog; slot rows with previews. |
| Net builder / Molecule builder | `Draw*` / `Build*` / Cancel | Sketch and library panes, consistent button naming. |
| Band structure | `Run*` / Cancel | Brillouin-zone picture, "Recommended path" button, k-points listed. Very good. |

---

## Ten improvements that are in neither ROADMAP nor TODO

Sizes as `docs/ROADMAP.md` uses them: **S** ≤ a day, **M** a few days,
**L** a week or more.

1. **Give the 3-D view a fair share on first run** (finding 1) — `resizeDocks`
   proportions at construction, Sites tabbed behind Structure. **S**
2. **A start pane in the empty central area** (finding 2) — icon, ⌘O, "drag a
   file here", the seven samples. Reuses the chooser's sample list. **S**
3. **Say why a greyed module is greyed** (finding 3) — `setToolTipsVisible`
   plus the `Availability.reason` on the disabled action, and a line under
   the greyed group in the Modules panel. **S**
4. **A first-time conversion notice for Save File** (finding 4), with
   "Don't show again", beside `confirm_overwrite`. **S**
5. **Autosave and crash recovery** (finding 5) — periodic
   `<workspace>/.autosave/*.xtalproj`, offered back from the chooser; plus
   "a calculation is running — stop it and quit?" in `closeEvent`. **M**
6. **A context menu on the Workspace tree** — Reveal in Finder, Open, Open in
   a new tab, Rename, Delete run, Copy path. Today the panel is read-only and
   a run folder can only be reached through Finder. **S**
7. **Energy units as a preference** (kcal/mol · kJ/mol · eV, and Å vs A) —
   the conversion layer already exists at the engine boundary, so this is a
   display setting; MOF and framework literature quotes kJ/mol, and periodic
   DFT people read eV. **M**
8. **Selection tools a VESTA/Avogadro user will look for and not find**:
   select within a radius of the selection, select by Wyckoff letter or label
   pattern, select by site symmetry, named/saved selections, and "select
   what is visible in the display range". The primitives (`Document.select`,
   orbit expansion) are all there. **M**
9. **Screen-reader names and label buddies** (finding 12) — `setBuddy` in the
   form builders, `setAccessibleName` on the custom widgets, and an
   accessible description for the viewport saying what is selected. The
   142 existing tooltips are most of the text already. **M**
10. **A theme-aware viewport and warning style** (finding 11) —
    `Background ▸ Follow the system`, and one `warning_label()` helper using
    palette roles to replace the 14 hard-coded `#8a5a00` / `#fdf3e0` styles.
    **S**

Runners-up, not in the ten: sortable Sites columns; a keyboard zoom
(`⌘+`/`⌘-`) and arrow-key nudge to match the Move panel's ± buttons; a
"recent workspaces" entry in the File menu (only the chooser has them);
per-session module parameters persisted to preferences.

---

## What I did not get to

* **Keyboard-only navigation and focus visibility** could not be judged
  through the driver (the window is not the active application, so
  `focusWidget()` stays `None`). It needs a person at the keyboard, the same
  gap `docs/TODO.md` § Interface records for dragging a panel with a mouse.
* **No long-running job was actually run** — no Zeo++, DFTB+, xTB or Blender
  binary on this machine, and the machine is at 9.0 GB of 10 GB swap — so
  `Stop`, the progress line and the post-run message were read from
  `run_progress.py` and `module_runner.py` rather than watched. The UFF
  optimiser and a MACE run would both have been drivable and were not.
* **The MOF builder, net builder, molecule sketcher and landscape/contour
  windows** were grabbed but not *used*; their interaction (drag a block into
  a slot, draw a molecule) is where their UX actually lives.
* **The trajectory and playback panels** were judged empty; with a real
  trajectory loaded the overlap in finding 7 may be worse or better.
* **Printing, high-DPI on an external 1× monitor, and Windows/Linux
  conventions** (where OK/Cancel order is reversed) were not looked at at all.
* **Colour-blind safety of the Jmol/CPK palette** was noted as "default, and
  editable per element", but no palette was measured for confusability, and
  the heat-map/contour colour scales in the scan results were not examined.
