(architecture-document)=
# The Document and undoable commands

Every change to a structure in the window goes through one object,
the Document, which runs it as a command, pushes one undo step and
tells the panels what kind of thing changed.  After this page you know
why Undo is one step for a whole selection, what the {term}`Change flag`
on a command decides, and why the window has three separate refresh
paths rather than one.

```{index} single: Document
```
```{index} single: undo; how it works
```
```{index} single: Change flag
```
```{index} single: command (undoable)
```

## What a Document is

`xtalapp/document.py` describes it in one sentence: *a Document is
one open structure: the crystal, how it is being viewed, what is
selected, and its undo history*.  Every tab in the window is one.
The rule that follows is the one the rest of this page rests on:

> Widgets never hold a Structure of their own and never mutate one --
> they hold a Document, listen to its signals, and change it by
> running Commands through `Document.run`.  That single funnel is what
> makes every edit in the application undoable, scriptable and
> testable without a window.

The Document is a Qt object, so it lives in the shell, but the
commands it runs and the stack that holds them are in the core
(`xtal/commands/`).  Its verbs are the operations the menus name --
`add_atom`, `delete_selection`, `set_selected_bond_type`,
`find_symmetry`, `make_supercell`, `prepare_for_simulation`,
`add_hydrogens`, `apply_optimization` and the rest -- and each
returns the sentence the status bar shows.

It announces what happened through signals.  The ones a panel listens
to are:

| Signal | When |
|---|---|
| `structureChanged(int)` | A command ran, undid or redid; the integer is the `Change` flag below |
| `previewChanged` | A geometry is being shown but not committed -- an optimiser step, a dialog's preview |
| `selectionChanged`, `measurementsChanged`, `planesChanged` | The selection, the measurement list or the fitted planes changed |
| `poresChanged`, `overlayChanged` | A pore network, a charge colouring or an orbital was drawn or dropped |
| `viewChanged` | How the structure is drawn changed, not the structure |
| `historyChanged`, `modifiedChanged(bool)` | The undo stack moved; the document became dirty or clean |
| `playbackChanged` | A trajectory was opened or closed against this document |

"Modified" is not a flag that edits set.  It is derived from the undo
stack, so undoing back to the point you last saved makes the document
clean again, "exactly as in any other editor".

## Commands

`xtal/commands/base.py` is the command pattern: *every change to a
structure, as an object that knows how to undo itself*.  A `Command`
has a `label` (what Undo will be called), a `change` flag, and two
methods, `do(host)` and `undo(host)`.  Two rules keep it cheap:

- **Commands store their own inverse, not a snapshot.**  Deleting
  three atoms remembers three atoms, not the whole crystal.
- **Commands are pushed after they are built, not after they are
  run.**  The stack runs them, which is what lets it merge a drag
  into one undo step, group a dialog's changes into one, and keep the
  redo branch correct.

Three base classes cover the cases a plain command does not:

`ReplaceStructure`
: Swaps the whole structure, "the honest form for operations that
  rebuild it (supercell, symmetry changes, cell transformations)":
  the old structure *is* the undo data, and nothing smaller would be
  correct.

`StructureOperation`
: A rebuild that "can say what it will do before it does it".  A
  subclass implements `apply_to(structure)` and returns the new
  structure *and a report*; `preview` runs the same computation
  without committing.  "Symmetry and cell operations are the ones
  users hesitate over -- 'how many atoms will this leave me with?',
  'did it find the group I expected?' -- so every one of them computes
  a result *and* a report, and the dialog can ask for both through
  `preview` while the user is still deciding."  Find symmetry, Merge
  duplicates, Invert, Prepare for simulation, the cell transformations
  and the subgroup descent are all of this kind, and running the
  command then reuses that work.

`SnapshotEdit`
: An arbitrary mutation made undoable by keeping a copy: "the escape
  hatch for edits that have no dedicated command yet -- a line in the
  Python console, a one-off script, a test".  It costs a full copy of
  the structure, "which is why it is the exception and not the rule".
  `Document.apply(mutate, change, label)` is the door to it.

`CommandStack` is the bounded history (200 steps by default).  Its
`push` runs the command and then asks the command on top whether it
will absorb the new one (`merge_with`), which is what turns a drag or
a held spinbox into a single {kbd}`Ctrl+Z`; `break_merge` ends the
gesture "on the button coming up, on the drag ending", so that the
next nudge an hour later is its own step.  `transaction(label)` groups
everything pushed inside it into one `MacroCommand`; an empty
transaction adds nothing, and an exception inside one rolls back what
had already run, because "a half-applied dialog is worse than a
cancelled one".

:::{note}
Structure edits go through the Document with a `Change` flag, so they
land as one undo step and refresh only the panels that care; nothing
mutates a structure behind the Document's back.  That is a product
decision recorded in the repository's invariants, not an
implementation detail, and it is why every operation in the manual
that says "one undo step" -- *Prepare for simulation*, adopting a
frame of a trajectory, recovering an autosave, interpenetrating --
really is one.
:::

## Why a selection-wide change is one batch

A long operation over a whole selection is applied in one batch, not
atom by atom with a redraw between.  The invariant names the case
that taught it: Select All followed by Set Bond Type stalled on
MFU-4l.  `Document.set_selected_bond_type` explains the fix in its
own docstring:

> One command for the whole selection, not one per bond: the
> structure is touched once, the cell is expanded once and the
> viewport redraws once.  Select All on a framework selects eight
> hundred bonds, and the version of this that ran a command each made
> the application stop for a quarter of a minute drawing pictures
> nobody asked to see.

So a verb that touches many atoms builds one command over all of them
(`SetBondTypes`, `DeleteSites` and their kind), or runs several inside
a `transaction`, and the stack pushes one step.  It is also why such a
command is reported "in orbit terms": the statement is stored against
the asymmetric unit, so calling one C--O of an acetate double calls
its symmetry mate double as well, and the status line counts what
actually changed.

## The `Change` flag

Every command carries a `Change`, an integer flag defined in
`xtal/core/structure.py` whose docstring gives its purpose: *what a
mutation touched.  The viewport uses this to decide between "update
one numpy array" and "rebuild the scene"*.

```python
class Change(IntFlag):
    NONE = 0
    POSITIONS = 1        # coordinates moved, nothing else
    TOPOLOGY = 2         # atoms or bonds added / removed / retyped
    CELL = 4             # lattice changed
    SYMMETRY = 8         # space group changed
    METADATA = 16        # labels, title, provenance
    ALL = POSITIONS | TOPOLOGY | CELL | SYMMETRY | METADATA
```

After a command runs, `Document._after_change(change)` reads the flag
before anything is redrawn.  A change that touched the topology, the
symmetry or the cell prunes the selection to the atoms that still
exist and drops the measurements whose atoms have gone; a change of
positions only re-measures every distance and angle and re-fits every
plane, and prunes the selection only if the number of atoms in the
cell changed all the same -- "an atom taken off a special position
splits its orbit, and one moved onto one merges it".  A pore network
drawn over the crystal is dropped when the crystal it measured
changes.  Then `structureChanged` is emitted with the flag, and every
listener makes the same cheap-or-expensive decision for itself.

## The three refresh paths

The window's refreshing is deliberately split three ways, and the
repository's own guidance says why the distinction matters: *rebuilding
a site table because a spinbox moved is how a large structure loses
interactivity*.  The three methods live in `xtalapp/shell_state.py`,
a mixin of the main window.

`_update_ui`
: Runs when the **current document changes** -- another tab, a file
  opened, the last one closed.  It *rebinds* every panel to the new
  document (`set_document` on the Info, Net, Inspector, Sites, Move,
  Style, Measure, Force Field, DFTB+ and trajectory panels), rebuilds
  the element menu and refreshes the shell.  It is the expensive one,
  and it is meant to run rarely.

`_on_structure_changed(change)`
: Runs on `structureChanged`, and refreshes only the panels the change
  actually reached.  Its docstring: "the formula, the density, the
  space group, the elements present and the force field's typing are
  all decided by *what* the atoms are, not by where they are -- so a
  geometry change refreshes the panels that show coordinates and
  leaves the rest alone".  A positions-only change refreshes the
  Inspector, Sites and Move panels; anything else also refreshes Info,
  Style, Force Field and DFTB+ and rebuilds the element menu.  The Net
  panel is handed the flag and left to decide, because identifying a
  net "walks ten shells of an infinite graph, and a change that did
  not touch a bond cannot have changed the answer".  Previews never
  arrive here at all: they travel on `previewChanged` and reach the
  viewport only, which is what lets an optimiser show you every step
  without the tables catching up on each one.

`_on_view_changed`
: Runs on `viewChanged` -- a style, a colour, a display range -- and
  touches only the shell's own widgets and the Style panel, "the thing
  that shows view state".  Nothing that reads the structure is
  rebuilt.

The comment at the end of `_on_structure_changed` records the trap
the split avoids: it calls the shell's refresh and not `_update_ui`,
because that one "*rebinds* every panel to the document, which is for
when the current document changes and which would undo every skip
above".

## Playback is not an edit

A document playing a trajectory back refuses to run commands:
`Document.run` raises `PlaybackActive`, because "the atoms are showing
a frame, so an edit made against them would be an edit of somebody
else's geometry, and it would be wiped by the next frame".  The window
disables the editing actions while a trajectory is open, and the
exception is the backstop that makes it a rule.  *Adopt this frame* is
the one way out that keeps a geometry, and it is a single undoable
command like everything else.

## Reading further

`.claude/skills/add-action/SKILL.md` in the repository is the
contributor's walk-through of the chain a new command follows -- from
the action registry, through a thin window method, to a Document verb
that runs one or more commands in a transaction and returns a
sentence -- with *Merge atoms* as its worked example.  The
{doc}`registries page <registries>` covers the first link of that
chain.
