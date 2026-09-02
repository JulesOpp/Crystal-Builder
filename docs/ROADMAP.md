# Crystal Builder — delivery plan for the TODO

[docs/PLAN.md](PLAN.md) is the architecture and the roadmap that got
the application built; [docs/TODO.md](TODO.md) is everything that came
out of using it and has never been scheduled.  This file schedules it:
what order, what each phase delivers, what it is allowed to touch, and
what has to be true before the next one starts.

Every phase ends with something runnable and a green suite, which is
the same rule [docs/PLAN.md](PLAN.md) § 16 works to.  Sizes are orders
of magnitude, not estimates: **S** is a day or less, **M** a few days,
**L** a week or more, **XL** a project of its own.

Phases A to I have shipped and their entries are gone from
[docs/TODO.md](TODO.md).  What follows is the plan for what is left,
rewritten around a change of priorities: the application can be
trusted, and the next thing it has to do is **make** something.

---

## 1. What comes first, and why in this order

Three things are wanted before anything else, and they are wanted for
different reasons.

**Breaking up `mainwindow.py` comes first**, and not because 2415
lines is unpleasant.  It comes first because two of the other five
phases land inside it: PORMAKE is a new branch in the module-run
plumbing and a dialog of its own, and the window rearrangement is a
rewrite of the layout code.  Doing the split afterwards means doing it
over code that has just been changed, with the diff of a pure move
tangled up in the diff of a feature — which is the one thing a pure
move must never be.  It is also the only phase here that adds no
capability at all, so it is the one worth getting behind us.

**PORMAKE next**, because it is the phase with a decision in it.  The
dependency question (`pymatgen` and `jax` in an application that today
installs four packages) has to be answered by trying it, and the answer
changes what Phase U is allowed to assume.  Everything else on this
list is work; this one is work plus a fact we do not have yet.

*The fact is now in: 889 MB, 44 packages, and a ten-second import.
Workable, as an extra and never on the import path — § 4.*

**Add Atom at a bond length third**, because it is the smallest of the
three and it does not block anything — but it builds the one piece of
machinery two later entries need: the viewport has no hover event at
all today, and the ghost atom, the tooltip and any future drag-preview
all want the same `on_move`.

*`Mode.on_move` is now there, along with `MoveEvent` and a
`wants_move` flag so only the modes that ask pay for the ray.
Phase T's tooltip inherits all of it — § 5.*

```
    P. split the shell ─┬──> the PORMAKE runner branch     (Phase Q)
                        ├──> the default layout            (Phase T)
                        └──> every phase after it

    Q. PORMAKE ─────────┬──> the dependency answer         (Phase U)
                        └──> "use the linker I drew"       (Phase U)

    R. hover events ────┬──> the ghost atom                (Phase R)
                        └──> the atom tooltip              (Phase T)
```

After those three the order is the user's stated one, with a single
rearrangement: the **half bonds at the boundary** ride in Phase S
rather than waiting, because they are a change to
`viewport/builder.py`, which is the file Phase S is already open in,
and because a net drawn on one cell of **pcu** showing three edges at a
six-coordinate vertex is a wrong picture rather than a missing feature.

---

## 2. Cheap wins, available at any time

Each of these is a day or less, depends on nothing, and can be pulled
out of its phase whenever the pain is worth a detour.

| Item | Phase it belongs to | Size |
|---|---|---|
| Edit cell in the right-click menu | T | S |
| Export a net as `.cgd` for Systre | V | S |

The `.cgd` writer is the one to notice: it is listed last in priority
and it is an afternoon, and Phase Q put a second consumer in front of
it — PORMAKE reads `.cgd` topologies, so a writer is also the route
from *a net the user drew* to *a framework built on it*.  Phase Q used
the **reader** and did not need the writer, so this is still owed and
is now the last piece of "build on the net I drew".

---

## 3. Phase P — break up the shell

**Goal:** `mainwindow.py` is the shell and nothing else, and every
later phase edits a file that is about the thing it is changing.

**Nothing in this phase changes behaviour.**  It follows the
`pure-move` skill: one seam per commit, no renames, no "while I'm here"
fixes, a full green suite between every step.  A step that cannot be
made without a behaviour change is a step that stops and asks.

The file is 2415 lines and splits along five seams that are already
there — they are the banner comments in the file itself.  In order:

| Step | New module | Out of `mainwindow.py` |
|---|---|---|
| 1 | `xtalapp/module_runner.py` | ~250 lines |
| 2 | `xtalapp/menus.py` | ~430 lines |
| 3 | `xtalapp/layout.py` | ~180 lines |
| 4 | `xtalapp/documents.py` | ~250 lines |
| 5 | `xtalapp/workspace_shell.py` | ~190 lines |
| 6 | `xtalapp/refresh.py` | ~270 lines, and optional |

What is left is about 850 lines: construction, the command slots, the
status bar, drag-and-drop and `closeEvent`.  That is the shell.

### Step 1 — `module_runner.py`

**What moves.**  Everything under the `MODULES` banner:
`run_module_action`, `_start_module`, `stop_module`,
`_on_module_finished`, `_on_module_failed`, `_show_report`,
`_save_report_images`, `_finish_module`, `_after_module_run`,
`_adopt_module_structure`, and the three pieces of state they own
(`module_worker`, `_module_thread`, `_module_params`).

**What it depends on.**  From the core: `MODULES`, `Job`,
`ModuleError`, `module_record`, `Change`, `safe_name`.  From the
shell: `ModuleWorker`, `start_in_thread`, `save_histogram`.  From the
window, through a handle it is constructed with: `show_message`,
`show_status`, `current_document`, `actions_`, `modules_dock`,
`run_progress`, `results_dock`, `log_dock`, `refresh_workspace`,
`_refresh_shell`.

**What stays.**  `MainWindow.run_module_action` and
`MainWindow.stop_module` stay as one-line delegations.  The modules
dock, the run-progress dialog and two tests connect to those names, and
a pure move does not get to rename them.

**Shape.**  A `QObject` parented to the window, constructed where the
state it owns was initialised, holding a reference to the window.
`self.module_runner = ModuleRunner(self)`.

**It has to be a `QObject`, and "it owns no signals" is the wrong
test.**  It owns none; it *receives* two, and the worker emits them
from inside its own thread.  Qt picks a queued or a direct connection
from the receiver's thread affinity, and a plain Python object has
none — so the finished handler runs on the worker thread, and the
first thing it does is `_refresh_shell`, which reaches
`setWindowTitle`.  Touching a widget from another thread aborts the
process rather than raising.  **Any of the objects below that receives
a signal is a `QObject` for the same reason**, whether or not it emits
one.

**What cannot move cleanly.**  Two things, and both stay reachable
through the window handle rather than being fixed here:

* the `shell` escape hatch, which looks a name up in `self.actions_`
  and triggers it — the runner has to reach the action registry;
* `_adopt_module_structure`, which needs `current_document()` and
  `document.is_playing`.

Neither is an accident: a module runner needs a shell to run in, and
the window is it.  Naming that dependency in a constructor argument is
the improvement; removing it is not available.

### Step 2 — `menus.py`

**What moves.**  `_build_actions`, `_build_menus`,
`_build_modules_menu`, `_refresh_module_availability`,
`_module_action`, `_build_toolbar`, `build_context_menu`,
`_add_bond_type_menu`, `_add_counted`, `_selection_count`.

**Shape: free functions over a window, not a class.**  There is no
state here — `build_actions(window)`, `build_menus(window)`,
`build_toolbar(window)`, `context_menu(window, kind)` — because every
one of these already does nothing but attach things to `self`.  The
dependency runs one way: `menus.py` imports nothing from
`mainwindow.py`, and `mainwindow.py` calls into it.

**What stays.**  The slots.  Every action's `triggered` connects to a
bound method of `MainWindow` (`self.copy`, `self.find_symmetry`,
`self.set_view(...)`), and those methods stay exactly where they are —
see *what cannot move cleanly* below.

`MainWindow.build_context_menu` stays as a one-line delegation:
`tests/test_context_menu.py` calls it on the window five times.

**Flag.**  `CONTEXT_MENUS`, `COUNTED_ACTIONS` and `BOND_TYPE_MENU` are
class attributes on `MainWindow`.  Moving them to module constants
changes how they are spelled, and Phase T adds entries to
`CONTEXT_MENUS`.  **Leave them on the class** and have `menus.py` read
them off the window it is passed; moving them is not free and buys
nothing.

### Step 3 — `layout.py`

**What moves.**  `_build_docks`, `DEFAULT_VISIBLE`,
`apply_default_layout`, `reset_layout`, and the Window menu built at
the end of `_build_docks`.

**What it depends on.**  Every dock class, and the window for
`addDockWidget`, `tabifyDockWidget`, `splitDockWidget` and the signal
connections each dock makes back to window methods.

**What stays.**  The dock attributes themselves (`self.sites_dock` and
the rest) are set on the window by `build_docks(window)`, because
forty-odd call sites in the refresh paths and the tests read them
there.  `MainWindow.reset_layout` stays as a delegation — it is an
action slot.

**Why its own file rather than part of step 2.**  Phase T rewrites
`apply_default_layout` and `DEFAULT_VISIBLE`.  A file about the
arrangement of the window is the file that change should land in.

### Step 4 — `documents.py`

**What moves.**  The `DOCUMENTS` banner plus save, export and close:
`current_document`, `add_document`, `new_document`, `open_dialog`,
`open_path`, `document_for`, `_paths_naming`, `save_document`,
`save_document_as`, `_suggested_project`, `export_dialog`,
`export_again`, `_export`, `export_image`, `close_current`,
`close_document`, and `_last_export`.

**Shape.**  A `DocumentSet` owning `self.tabs` and `self.documents`,
constructed before the docks.

**What stays.**  `closeEvent`, `dragEnterEvent`, `dropEvent` and
`no_confirm_close()` — a `QMainWindow` closing is the window's own
business.  Every method named in a menu (`open_dialog`,
`save_document`, …) keeps a delegation on the window, because they are
action slots.

**What cannot move cleanly.**  `close_document` puts up the
unsaved-changes prompt and tears down a viewport widget, and
`add_document` builds one through `self._viewport_factory`.  Both are
window-lifetime operations reached from a document-lifetime object.
They move with the rest and take the window handle with them; the
alternative is a seam that runs through the middle of one method,
which is worse than a named dependency.

### Step 5 — `workspace_shell.py`

**What moves.**  The `THE WORKSPACE` banner: `place_in_workspace`,
`_offer_workspace`, `set_workspace`, `restore_workspace`,
`refresh_workspace`, `open_workspace_dialog`, `new_workspace_dialog`,
`_on_workspace_requested`, `_on_run_started`, `_on_run_finished`,
`_on_trajectory_history`, `open_artifact`, and `self.workspace`.

**Why separate from step 4** even though they are adjacent in the
file: a workspace is a directory on disk that runs land in, and a
document is a structure in a tab.  They meet in exactly one place —
`place_in_workspace`, called when a document is opened — and that one
call is a better boundary than the one line of blank space that
separates them today.

**Flag.**  `refresh_workspace` is called from the module runner
(step 1) and from the force field docks.  It keeps a delegation.

### Step 6 — `refresh.py`, and whether to do it at all

**What would move.**  `_update_ui`, `_on_structure_changed`,
`_on_view_changed`, `_refresh_shell`, `_on_selection_changed`,
`_sync_bond_type_actions`, `_refresh_plane_actions`,
`_rebuild_element_menu`, `_refresh_module_actions`,
`_on_measurements_changed`, `_on_planes_changed`.

**This is the step to be willing to stop before.**  The three refresh
paths are the most important thing in the file and the split is
supposed to make them easier to see — but they are pure dispatch over
`self.<dock>`, so moving them turns every line from `self.sites_dock`
into `window.sites_dock` and changes nothing else.  After steps 1 to 5
they are already the only thing in their neighbourhood, which was the
whole objection.  Do it if the file still feels large; do not do it for
the line count.

**If it is done**, it moves as free functions and the eleven method
names all stay as delegations, because they are signal receivers
connected in `add_document` and `_build_docks`.

### What cannot move at all, and why that is right

**The command slots stay in `MainWindow`.**  `copy`, `paste`,
`delete_selection`, `select_all`, `find_symmetry`, `edit_cell`,
`set_style`, `undo` and thirty more are each two or three lines over
`current_document()`, and every one is the target of a registered
action.  Splitting them into `EditCommands` / `SymmetryCommands`
objects means either rewriting every action to bind to
`window.edit.copy` — which is a rename of every action target, not a
move, and would churn the tests that trigger actions by name — or
keeping a forwarding method for each, which is the same file in two
places.  They are ~500 lines of one-liners and they are the shell's
job.  Leave them.

**`_resolved` and `no_confirm_close`** are already module-level
functions and stay in `mainwindow.py`; moving them is churn.

**Verification for every step.**  `python -m pytest -q` green before
and after, and `.claude/skills/run-app/drive.py` opening
`resources/samples/MFU4l.cif` and pressing something, because a pure
move that breaks a signal connection passes the suite and fails on
screen.

| Item | TODO section | Size |
|---|---|---|
| Steps 1–5 | — | M |
| Step 6 | — | S, optional |

---

## 4. Phase Q — build a MOF from a net — **shipped**

**Goal:** pick a topology, a metal node and a linker, and get a
framework in a new tab — with the net of what came out identified
against the net that was asked for.

| Item | TODO section | Size |
|---|---|---|
| Build a MOF from a topology, a node and a linker | Building | M |

### What the spike answered

Three questions decided the shape, and all three are settled.

1. **`pormake` imports and builds on macOS/arm64 with no `jax`
   problem.**  `pcu` with a metal node and a linker is 0.6 s.  So it
   runs in this process and the external-process fallback is not
   needed.
2. **`Database()` finds its bundled database from an installed
   wheel** — 2403 `.cgd` nets and 867 `.xyz` blocks under
   `site-packages/pormake/database`.
3. **A fresh environment holding nothing but `pormake` is 889 MB**,
   44 packages: `jax` and `jaxlib` are 570 MB of it, `pymatgen` brings
   `pandas`, `sympy`, `plotly` and `matplotlib`.  The import itself is
   **ten seconds warm and thirty-three cold**, which is the number
   that shaped the code more than the megabytes did.

So: a `mof` extra in `pyproject.toml`; `Module.check` is
`importlib.util.find_spec` and a directory test, never an import; and
`import pormake` happens once, on the worker thread, inside the run
that needs it.

### What was built

`xtal/mof/` is the headless half and imports no Qt.

* **`catalog.py` reads the database without importing PORMAKE.**  The
  topologies are `.cgd`, which `xtal/io/cgd.py` has read since the
  RCSR work, and a building block is an XYZ whose second line lists
  its connection points.  The whole 3.7 MB parses in 0.4 s, so the
  picker opens instantly.  Node type *i* is the *i*-th `NODE` line of
  the file, which is not a convention invented here — PORMAKE tags
  each expanded site with that index and calls it the node type, so
  reading the file is reading PORMAKE's own numbering.
* **`build.py` runs it, hands over as CIF, and draws the net.**

`Action.dialog` is the one new field, exactly as this phase proposed:
a name the shell resolves to a dialog it opens *instead of* the
generated form, which hands back the same `values` dict.  `run` stays
headless, `xtal run mof.build -p topology=pcu -p nodes=N59 -p
edges=E32` works, and a test calls it with no display.

`FILE` became optional on `xtal run`, required by the action rather
than by the parser — the other half of `needs_structure = False`.

### The check, which turned out better than planned

The phase said `net_of` would identify the framework that came back.
It cannot on its own: `net_of` reads **topology bonds**, and a CIF
read fresh has none.  What closes the gap is that PORMAKE knows
exactly which atoms are one node — so the framework is handed over
with its net **already drawn** on it, as `TOPOLOGY` bonds between each
node's own atoms.

That is worth more than the check it was for.  The Net panel names the
framework the moment the tab opens, without anybody drawing anything;
and the check is then genuinely over the bonds stored in the file
rather than over anything PORMAKE said.  `pcu`, `dia` and `tbo` all
come back named as themselves.

### What is *not* done, and why

**The picker does not identify the net it is showing.**  Naming a net
against the RCSR is milliseconds for `pcu` and *thirty seconds* for
the worst net in the database — far too slow for a click in a list of
2399.  It is drawn instead: `xtalapp/dialogs/mof_preview.py` paints
the net and the building blocks with `QPainter`, the vertices coloured
by node type in the order the slot rows ask about them.  The
identification belongs to the run, where it is a check rather than a
label.

**Four of the 2403 topologies cannot be expanded** — they give edge
midpoints instead of endpoints, and a midpoint does not say what it
joins.  They stay in the list, because the list is where a name is
found, and clicking one says so and disables Build.

**`.cgd` export is still owed** (§ 2).  Phase Q consumed the reader,
not the writer: PORMAKE's topologies come *in* as `.cgd`, and the
route from *a net the user drew* to *a framework built on it* still
wants a writer.  It stays a cheap win and Phase V's Systre entry is
still where it lives.

## 5. Phase R — Add Atom means what the click meant — **shipped**

**Goal:** an atom placed next to an atom lands at a bond length from
it, with the bond drawn, and the key that resets the bonds is the one
people reach for.

| Item | TODO section | Size |
|---|---|---|
| Add Atom should place the atom at a bond length | Editing | M |
| Ctrl+B becomes *Reset bonds to automatic* | Editing | S |
| Add centroid, and dummy atoms | Jules, below | M |

**Note from Jules: also add a feature to Add Centroid in the middle
of selected atoms. This centroid should have the option to be an
atom type, like carbon, or as a Dummy Atom. Dummy Atoms should be
able to be used to draw Topology Bonds and Measure.**

**The anchor has two spellings and the cheap one comes first.**  With
exactly one atom selected, entering Add Atom starts already anchored:
the next click is only a direction.  With nothing selected, the first
click anchors and the second directs.  The second is the full gesture
and the first is the one an experienced user will actually use, and
they are the same state machine with a different entry point.

**The distance is the pair's**: the sum of the two covalent radii from
`xtal.core.elements`, which is what `bonding` already uses to perceive
one.  The second click carries only the direction — project the ray
onto the sphere of that radius around the anchor and take the near
intersection, falling back to the closest approach when the ray
misses.

**The bond is created with the atom**, explicitly, as one undoable
step.  The user has just said what it is bonded to; leaving it for
perception to find would be a different answer to a question that was
not asked.

**Then the gesture repeats.**  The anchor moves to the atom that was
just placed, so a chain is one click per atom rather than two —
re-anchoring by hand between every pair would double the clicks of
the one thing the mode is for.  Each link is still its own undo step,
because each was its own gesture.

**Hovering an existing atom snaps to it**, whatever the distance, and
the click then bonds to that atom and places nothing.  That is what
closes a ring: the last atom of a chain has to join one that is
already there, and a ghost hanging a bond length short of it is a
picture of the wrong answer.  The snapped ghost swells the atom under
the cursor rather than showing a new one, because a translucent
sphere exactly over a solid one is invisible.

**Escape is two stages**, because they are two different things to
want: the first ends the chain, and a second — with nothing left to
end — leaves for Select.  The viewport therefore changes mode by
itself, which is what `ViewportWidget.modeChanged` is for: the
toolbar button has to follow rather than decide, or it shows a mode
nobody is in.

**The new machinery is `Mode.on_move`.**  The mode protocol has
`on_click`, `on_drag` and `on_deactivate` and no hover event at all,
and the ghost atom needs one.  So does Phase T's tooltip, which is why
it is built here and not twice.  `picking.pick` is exact and
vectorised and a mouse-move is not a hot loop, so nothing else is
needed to know what is under the cursor.

**Decide the ghost before building it.**  `document.previewChanged`
moves atoms that exist; a ghost is an atom that does not.  Either the
scene model grows a ghost field, or the preview path is reused with
one atom appended.  The first is honest and is a wider change; the
second is smaller and puts a fictional atom into a structure-shaped
object.  Half a day's decision, made once, before the mode is written.

*Decided: neither.*  Both spellings assume the ghost belongs to the
model, and it does not — a `SceneModel` is built from the document and
rebuilt when the document changes, while a ghost changes at cursor
rate and describes something the document does not contain.  The first
would rebuild the crystal on every mouse move; the second would leave
a fictional atom where picking, the selection flags and `bounds()` all
treat what they find as real.  So `scene.Ghost` is an **overlay**:
its own record, its own two actors on the `VtkScene`, drawn over the
scene and never part of it.  Nothing that reads a SceneModel — every
offscreen render included — had to learn about it.

**Ctrl+B rides along** because it is the same complaint: the gesture
should mean what the user meant.  `reset_bonds` takes the key,
`recompute_bonds` keeps the menu entry and the toolbar button.  The
reason reset was left keyless — it throws the user's bond edits away —
is answered by `Document.reset_bonds` running a single `ResetBonds`
command, so Ctrl+Z is exactly one press.  The **toolbar button stays
Recalculate**: a button is pressed by aim rather than by memory, and
the destructive one of a pair is the wrong thing to leave under the
cursor.

### What Add centroid turned out to need

Jules's note is one gesture and three facts about the atom it places.

**The middle is a minimum-image middle.**  `measure.centroid` takes
every atom in the image nearest the *first* one, not in the image the
P1 expansion wrapped it into — the centre of a ring that straddles the
cell boundary is in the ring, and the average of the wrapped
coordinates is a point in the vacuum.  Nearest to the first rather
than chained atom to atom, which is what `unwrapped_positions` does
for an angle: a selection has no order worth following.

**A dummy atom is not chemistry, so perception never bonds one.**
`bonding.DUMMY_ELEMENTS` is checked in `BondRules.allows`, which is
the one place both the cutoff scan and the rules dialog go through.
Without it a ring centre acquires six bonds to its own carbons and a
coordination number nobody asked for: `X` carries a covalent radius in
the tables only because every symbol does.  A bond the *user* draws to
one is a different matter and is stored like any other — and so is a
net edge, which is mostly what they are for.  `D` is deuterium and is
not a dummy.

**A force field has to say so.**  The UFF typer refused `X` with "the
field covers hydrogen to lawrencium and nothing beyond it", which was
a true sentence about the wrong problem — and it is now reachable by
an ordinary gesture (add a centroid, press Optimise), so it names the
dummy instead.

The dummy is the dialog's **default**, because a centroid usually is
one and because it is the answer that cannot quietly change what the
crystal means; an element is the other radio button, and building a
bridging atom into the middle of a ring is a different act with the
same gesture.  The new atom is left selected, because a centroid lands
inside the ring it was taken from where an unhighlighted new atom is
genuinely hard to find.

---

## 6. Phase S — the picture says how big, where, and where it continues

**Goal:** the viewport carries the three things it currently cannot: a
length, the geometry the user has defined on top of the crystal, and
an honest edge to the box.

| Item | TODO section | Size |
|---|---|---|
| A fixed scale bar, so a relaxing cell is seen to relax | Appearance | M |
| A plane you have defined is nowhere on screen | Appearance | M |
| A bond that leaves the drawn cell is all or nothing | Appearance | M |

All three are new generated geometry in the scene, all three are view
state that never touches the undo stack, all three get a View menu
toggle and are saved in the session — so they are one phase, and they
are all in `viewport/builder.py` and `viewport/vtk_scene.py`.

**The scale bar carries a bug with it.**  `VtkScene.set_positions`
updates atoms, bonds, polyhedra, highlights and labels and *not*
`_cell_poly`, and `_same_shape` compares `n_cell_lines`, which does
not change when the cell merely changes size.  So during a
variable-cell relaxation the atoms move inside a box that is still the
old one.  A ruler beside a box that does not move would make that
visible and still be wrong; the frame's points have to be refreshed
alongside the atoms.  **The bar must not rescale during a run** — fix
it when the relaxation starts and leave it, so a cell that contracts
by 4% is a box that visibly shrinks against a ruler that does not.

**Planes have everything but the drawing.**  `measure.plane` already
returns the centroid and the normal; what is missing is a translucent
quad at them, sized from the extent of its own atoms, for the rows
selected in the Planes list.  The normal goes on as a short line,
because two nearly parallel planes are told apart by their normals and
not by their faces.  `VtkScene._set_polyhedra` is the machinery: it
takes triangles and a colour, which is all a quad is.

**The half bond is the one with a real cost in it.**  Today a bond
whose far atom is out of range is either dropped or completed by
drawing the whole far atom, and both are wrong: one under-coordinates
the surface, the other hangs a halo of extra spheres around a picture
that is supposed to be of the cell.  The half — from the near atom to
the midpoint, no sphere on the end — is the notation everybody already
reads.  Mechanically it is the third branch of the `end is None` case
in `_emit_bonds`, and it is the only branch with no drawn atom to
point at, while every array in the scene model is indexed by drawn
atom.  So it needs either a radius-zero entry in `_Drawn` or a
`_Halves` that takes a raw position: decide which first, because it is
the whole of the entry.

**And the net wants it more than the bonds do.**  `_emit_topology`
drops any edge whose far vertex is not drawn, and the comment there
already rules out the obvious fix for the right reason — a net edge's
ends are often whole cells apart, so completing one scatters ghost
vertices across the picture.  The half edge is the answer that comment
was waiting for.  Until it lands, a net drawn on one cell of **pcu**
shows three edges at a six-coordinate vertex, which is a wrong
picture and not a missing feature.

`ViewSettings.boundary` becomes three-valued (`in_range`, `bonded`,
`half`), so the View entry stops being a checkbox and becomes a
submenu of three — and the session reader has to go on accepting the
old two-valued string.

---

## 7. Phase T — the window and the rest of the gestures

**Goal:** the application opens in the arrangement somebody actually
works in, and the things done twenty times an hour take one gesture.

| Item | TODO section | Size |
|---|---|---|
| The window does not open the way it should | Appearance | S |
| Edit cell from the right-click menu | Editing | S |
| Measure from the right-click menu | Editing | M |
| An atom has nothing to say when you hover over it | Appearance | M |

Two of these are a name in a list, one is a change to a type most of
the application touches, and one is a decision about content.

**The layout lands in `layout.py`**, which Phase P step 3 created for
it: Structure top left, Workspace bottom left, the crystal in the
middle, Sites raised on the right.  `info_dock` and `file_dock` move
into `left_docks` and are split vertically rather than tabbed.  **The
default is a default, not a rule** — a saved layout still wins — and
`Reset layout` has to land on the same arrangement or the menu item
stops being a way back.

**Measure from the right-click menu needs an ordered selection.**  With
three atoms picked as A–B–C the vertex is B and no other reading is
right, and `Selection` stores a set with a single `focus` field for the
last atom picked.  Stating the rule ("the order you clicked them")
without keeping the order is a lie, so the order has to be kept — which
is a change to a type most of the application touches, and is the
reason this entry is M and not S.

**Edit cell belongs in all three context menus**, not only the one for
empty space: the cell is the one thing that is always under the cursor,
whatever was clicked.  One name in three lists; the action already
exists, is already undoable and already previews.  `display_range`
deserves the same treatment for the same reason.

**The tooltip's content is the interesting decision**, and it rides on
the `on_move` Phase R added.  It should be what the current view is
about: the label and element always, the UFF type and its reason when
the Force Field dock is open, U_eq when the ORTEP style is drawn.  One
that always says the same four things is one people learn to ignore.

---

## 8. Phase U — draw in 2D, build in 3D

**Goal:** a molecule that does not exist yet, into the open cell — and
into the `bb_dir` Phase Q wired through.

| Item | TODO section | Size |
|---|---|---|
| SMILES to 3D, into the open cell | Building | M |
| Fragment library | Building | S |
| An embedded 2D editor (rdEditor, or Ketcher) | Building | M |

Do the first two, live with them, and only then take the editor.  A
text box that turns `c1ccccc1C(=O)[O-]` into a benzoate sitting in the
cell is a few days of work and covers most of what the sketcher was
wanted for.

**The 3D half is the tractable one** and lives in a new headless
`xtal/build/`: place each atom from the neighbour that put it there,
using `terms.natural_bond_length` for the distance and the type's own
`theta0` for the angle, with staggered torsions and templates for ring
systems — every one of those numbers is already in `xtal/ff/uff` and is
already the geometry UFF wants, so the result starts at the force
field's minimum.  Then relax it with UFF, which needs no new code path,
only a cell with enough vacuum.

**Phase Q changes the dependency argument, and it is worth being
precise about how.**  The objection to RDKit was never that it is a
dependency; it was that it is a large one in a default install.  Phase
Q establishes the pattern that answers that — an extra, absent unless
asked for, with the feature honestly missing when it is — and it does
*not* make RDKit cheaper, because `pymatgen` is not RDKit and
installing `[mof]` gives you nothing towards `[build]`.  So: two
extras, either installable alone, and a default install that has
neither.  Choosing rdEditor is still choosing RDKit, and RDKit still
solves the 3D half.

**The editor is an integration, not a build.**  rdEditor is PySide6,
RDKit-backed, weak-copyleft and written as reusable widgets; the spike
that decides it is half a day — put its editor widget in a bare dialog
and get a `Mol` back out.  If the widget does not come apart from its
shell, Ketcher in a `QWebEngineView` is the fallback.  Writing a canvas
from scratch is not on this list.

**Where it lands** meets Phase Q: a molecule with connection points
marked is a PORMAKE building block, and a molecule without them is a
`PasteFragment` at the camera's focal plane.  The same 3D builder
serves both, and that is the reason these two phases are the same half
of the plan.

---

## 9. Phase V — the engines answer in pictures

**Goal:** the half of the external tools that is a drawing rather than
a number, and the half of DFTB+ that its own driver does better.

| Item | TODO section | Size |
|---|---|---|
| Export a net as `.cgd` for Systre | Topology | S |
| Zeo++: draw the answer, do not only print it | Modules | M |
| DFTB+'s own driver | Modules | L |

**The `.cgd` writer first, and it is an afternoon.**  The naming has
shipped — the Net panel says **pcu** and the canonical key makes that
a decision rather than a match — and there is still no way to *doubt*
it.  `xtal/io/cgd.py` reads the format and does not write it; a writer
and an action that saves the drawn net through it is the only way to
put a net in front of **Systre**, the reference implementation, and
get a second opinion that does not come from the code that produced
the first.  The format is one `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL` and one `NODE` per vertex with an `EDGE` per edge, and the net
is already in exactly that shape.  Take it in Phase Q instead if
PORMAKE's `.cgd` handling makes it fall out — but take it once.

**Zeo++ is the reason this phase exists.**  The three diameters are in
a table and the table is right, and a porous-materials application that
can only *print* 9.18 Å is a spreadsheet.  The largest free sphere
drawn where it actually sits is the picture somebody puts in a paper.
`-res` gives the diameter and not the position, so this needs `-chan`
or `-visVoro` and a new actor beside `_set_polyhedra` — which is the
same actor Phase S builds for planes, and is the argument for S coming
first.  Channel dimensionality (1D, 2D or 3D pores) falls out of
`-chan`'s output for free, and `-vol` is parsed already and wants an
action of its own.

**DFTB+'s own driver is a module, not an engine.**  Reached as an
engine it already does a single point and a geometry optimisation with
the symmetry projection intact; what its internal driver does better
is **lattice relaxation** — ours costs twelve extra energy evaluations
a step because no analytic stress is claimed — and **molecular
dynamics**, which has no route through `Calculator` at all: MD is a
trajectory DFTB+ produces, not a sequence of energies we ask for.

Most of it is already written.  `xtal/ff/dftb/hsd.py` writes the input
and checks the parameter set, `xtal/io/gen.py` reads the geometry back,
and `xtal/modules/process.py` runs, streams and cancels it.  What is
new is a `Driver` block, the parsing of a multi-step output, and the
trajectory read back into the transport bar.

**The cheaper half of the stress question is worth doing first**: read
DFTB+'s printed stress tensor and *check* it against `numeric_stress`
on a structure with a known answer.  If it agrees, the engine can claim
it and variable-cell relaxation gets twelve times cheaper without the
driver being written at all.

**Phase I's redraw rule applies here in full.**  Whatever DFTB+ writes
into its run folder has to be a function of the run and not of what the
window was showing: no frame skipped because nobody was looking, and
the trajectory after a headless `xtal run` byte-for-byte the same as
after a watched one.

---

## 10. Phase W — the klassengleiche half

**Goal:** *Descend to a subgroup* offers the subgroups that split an
orbit without touching the cell, and then the ones that double it.

| Item | TODO section | Size |
|---|---|---|
| A lost centring, in the same cell | Symmetry | M |
| A doubled cell, from the table | Symmetry | L |

One TODO entry, two pieces that are nothing like each other, and they
are separated here because the first is a computation and the second is
a data set.

**A lost centring needs no cell transformation at all.**  Fm-3m
contains Pm-3m as a genuine subset of its operations, at index 4, in
the same cubic cell; rock salt descended that way puts its four sodiums
and four chlorines on eight independent sites, which is the
cation-ordering model.  It is also why halite is the one fixture in the
suite where no descent splits anything.

**It does not fall out of the existing enumeration** by not dividing
the centring out.  `xtal/core/subgroups.py` reduces modulo the centring
translations on purpose: the reduction is what makes the closure
affordable, and the "generated by at most three elements" shortcut — a
fact about crystallographic *point* groups — stops being safe the
moment the translations are back in.  A run that assumes it over
Fm-3m's 192 operations reports 96 maximal subgroups, some maximal only
because the intermediate group needed a fourth generator and was never
found.  The tractable route keeps the reduction: enumerate the
subgroups of the *centring* group that the point group leaves
invariant, lift the reduced generators through each coset
representative, and close.  For F that is a handful of closures.
Naming and application need nothing new.

**The doubled cell is the table.**  Superstructures and
antiferromagnetic ordering live there, every relation carries its own
cell transformation and origin shift, and that is Bilbao's MAXSUB
rather than a computation.  Worth doing last, and worth not implying
the earlier versions do it — the dialog says *translationengleiche*
and no cell is doubled, which stays true until this lands.

---

## 11. Summary

| Phase | Theme | Rough size | |
|---|---|---|---|
| **P** | Break up the shell | M | *shipped* |
| **Q** | Build a MOF from a net | M | *shipped* |
| **R** | Add Atom means what the click meant | M | *shipped* |
| **S** | The picture says how big, where, and where it continues | M | |
| **T** | The window and the rest of the gestures | M | |
| **U** | Draw in 2D, build in 3D | M (XL with the sketcher) | |
| **V** | The engines answer in pictures | L | |
| **W** | The klassengleiche half | L | |

Phases R to W schedule **every entry left in
[docs/TODO.md](TODO.md)**, and nothing else.  P is the one phase with
no TODO entry behind it, because nobody using the application ever
asked for it and nobody using it will see it.  An entry ships when its
phase does; a new entry arriving in TODO.md joins the phase it belongs
to rather than starting a new one, and the day one does not fit any of
them is the day this file is wrong and gets rewritten again.

The order is one argument, and it has changed since the last version of
this file.  It used to be *a wrong number is worse than a missing one*,
and those phases have shipped.  It is now: **clear the ground, then
build something new, then make what is already there easier to see.**
P cleared the ground and Q built the first thing; U is the other
phase that produces a structure rather than trusting one; R, S and T
are the ordinary hour;
V and W are the two places where an external tool and a piece of
crystallography most users will never reach are still owed work.

## 12. What this plan does not do

* It does not schedule PXRD, volumetric data, SHELX round-trips or
  Rietveld.  Those are in [docs/PLAN.md](PLAN.md) § 12 and stay there
  until something in this list is finished.
* It does not promise the 2D sketcher.  It promises the 3D builder
  underneath it, a text route into it, and — in Phase Q — a builder for
  the one class of material where the 2D half is not needed at all.
* It does not write a reticular builder.  Phase Q integrates one, and
  the argument for that is in the phase.
* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase above keeps the core
  Qt-free, keeps every mutation a command, and adds capability through
  registries — and where an entry in TODO.md is expensive, it is
  usually because it is being made to obey those rules rather than go
  around them.
