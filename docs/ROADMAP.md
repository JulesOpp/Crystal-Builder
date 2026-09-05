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


## 8. Phase U — draw in 2D, build in 3D — *shipped*

**Goal:** a molecule that does not exist yet, into the open cell — and
into the `bb_dir` Phase Q wired through.

| Item | TODO section | Size | |
|---|---|---|---|
| SMILES to 3D, into the open cell | Building | M | *shipped* |
| Fragment library | Building | S | *shipped* |

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
neither.

> Since written: **there is no `[mof]` extra any more.**  PORMAKE is
> vendored at `xtal/mof/pormake/`, trimmed of `jax`, `pymatgen` and
> `networkx`, so the MOF builder ships and the only extra it needs is
> `[ase]`.  The pattern this phase established is unchanged and is
> what `[build]` and `[sketch]` still use; see
> [PACKAGING.md](PACKAGING.md) § 4.

Choosing rdEditor is still choosing RDKit, and RDKit still solves the
3D half.

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

### What is built, and what the plan above got wrong

**The native fragment builder is withdrawn.**  Writing one means also
writing a SMILES parser -- aromaticity, stereo, ring perception -- for
a result strictly worse than ETKDG, which is most of the phase spent
on the fallback.  So RDKit is **required** for the feature, as a
`build` extra, and absent it the entries grey out naming the extra:
the pattern Phase Q established, applied honestly rather than
half-answered.  Two extras, `mof` and `build`, neither in a default
install, and installing one buys nothing towards the other.

**`xtal/build/` is in** -- `from_smiles` gives a `Molecule` that
converts to a `Fragment` for the open cell or a P1 `Structure` for a
tab of its own, with its bonds set explicitly and nothing perceived.
A connection point is `*` in SMILES and `X` in what comes out, which
is the dummy that already exists: perception, the force field and
every module run hold it back at the door already, and a second
symbol -- radon was proposed -- would have meant teaching all three
about it and putting a radon atom in every CIF this wrote.

**Connection points are capped with hydrogen before the geometry is
touched.**  RDKit's MMFF has no parameters for atomic number zero, so
a `*` left in place either refuses to optimise or falls back silently.
A hydrogen points exactly where a substituent would, so the direction
that comes back is the one the connection point wants -- and the
direction is the whole of what it carries.

**The PORMAKE block format was read rather than assumed**, and three
facts came out of the 867 shipped files that the plan above did not
have.  A connection point sits **0.75 A** from the atom it hangs off
-- median over 4256 X-to-body bonds -- and not at a bond length; a
block written at 1.4 A builds a framework with every linker bond twice
too long and nothing reports it.  PORMAKE identifies connection points
by the **symbol** `X` and never reads the index line, so a writer must
emit both.  And there is a fourth section after the atoms, `i j` and a
letter in `S/D/T/A`, which is how a molecule's bond orders survive
into the built framework's CIF.  `xtal/mof/block.py` holds the
constant and the geometry, and `write_building_block` emits all
three.

**All of that is now in**, and one thing
had to be fixed before any of it: `PasteFragment` grew perceived bonds
onto what it pasted -- it never called `bonding.hold_perception` --
which was a live invariant violation reachable by Ctrl+V, and a
molecule dropped into a framework would have arrived already bonded
into it.  The paste tests missed it by counting `structure.bonds`,
where the perceived half never appears.

**What shipped, and the two shapes worth keeping.**  Building a
molecule into a tab of its own is a module (`xtal/modules/build.py`,
greyed with the extra named when RDKit is absent); dropping the same
molecule into the open cell is **not**, and cannot be -- the registry
has two behaviours for a returned structure, replace the open document
or open a new tab, and a paste is neither.  So it is a shell action,
`Structure > Insert molecule...`, landing at
`ViewportWidget.focal_point` because the centre of a cell somebody has
zoomed into is off screen.  And the two entries share **one** dialog,
which reads the connection-point flag off `action.name`: they differ
only in whether `*` is on offer and in what the footer says, and the
footer is `PasteFragment.describe` shown live, because pasting into
Fm-3m multiplies a molecule by 192 and that has to be said before the
click.

`MarkConnectionPoints` turns a selected atom with exactly one bond
into an `X` at 0.75 A along it, in one command because Ctrl+Z has to
give back both halves; the block writer emits the count, the index
line, `X` atoms *and* the bond block, because PORMAKE reads the
symbols and this application's own reader reads the line.  A block
saved from the Save dialog is in the MOF picker next time with nothing
further clicked, and the acceptance test builds **pcu** from a linker
this application wrote against a shipped node and reads the net back
off the framework to check it is still pcu.

### The editor, and what the seam was worth

**The widget did come apart from its shell**, which is the question
the spike was for.  `rdeditor.molEditWidget.MolEditWidget` is a
`QSvgWidget` subclass that constructs standalone, takes a `Mol` in,
signals `molChanged` out and undoes its own edits.  So Ketcher in a
`QWebEngineView` is not needed and QtWebEngine stays out of the
bundle.  rdeditor is LGPL-3.0, so it is a dependency and never
vendored -- a third extra, `sketch`, separate from `build` because
`xtal/` imports no Qt and this is PySide6 plus a theme package.

**The seam paid for itself exactly as claimed.**  `set_smiles` in and
`smilesChanged` out was the whole interface, and the editor went in
behind it: the footer, the library picker, the build timer and the
two entries' differences are untouched.  What did *not* survive
contact was the assumption that the seam was one-way.  A picture is a
line -- text in, drawing out -- and an editor is a **cycle**: draw,
box, the 350 ms timer, build, and the string back into the canvas.

**Both hops of that cycle guard on the molecule, not the string,**
and a string compare is not close enough.  The two ends disagree
about spelling constantly -- a benzene drawn from the ring template
comes back kekulized where the box says `c1ccccc1`, a library entry
writes `[*:1]c1ccc([*:2])cc1` where the depiction canonicalises the
ring -- and each disagreement would have rewritten the box, restarted
the timer, rebuilt, and re-laid the drawing out under the cursor, on
every keystroke.  Round-tripping both sides through `MolToSmiles`
asks the question that was actually meant.

**The chrome is ours.**  `MolEditWidget` has none: everything a user
presses in rdEditor lives on their `MainWindow`, which is a
thousand-line application and is not coming with the widget.  So:
Select / Add / Remove / Replace, seven elements, three bond orders,
two ring templates, undo.  Their `ptable_widget` is skipped
deliberately -- it wants a `QActionGroup` built by that `MainWindow`
and would couple this dialog to the plumbing the widget was extracted
from.  Anything off the element row is typed into the box, which is
why the box did not go away.

**The connection-point tool needed no chemistry at all.**  An atom of
atomic number zero is `*` in SMILES, `*` is what the box already
takes, and `from_smiles` already turns that into the `X` that
perception, the force field and every module run hold back at the
door.  It is offered only when `not pastes` -- the same flag the
footer and the picker read -- because the entry that pastes refuses a
starred string, and a tool whose only outcome is the footer turning
red is worse than no tool.

**Three things rdeditor does to its host are undone at
construction**, and none of them is a reason not to use it.  It sets
`WA_DeleteOnClose` on the canvas, right for the window it ships in
and wrong for a dialog opened, closed and opened again.
`MolWidget.__init__` calls `logging.basicConfig` and then sets the
level of the *root* logger, which is the application's.  And its own
constructor drops the parent on the floor -- `MolEditWidget` passes
`parent` to `MolWidget`, whose first parameter is the *molecule* --
so the canvas is built unparented and the layout adopts it.  Two
notes without a remedy: `rdeditor/__init__.py` does `from .rdEditor
import MainWindow`, so any import from the package executes that
shell and pulls in `qdarktheme` (0.1.7 on Python 3.13; it imports
fine because their `MainWindow` is never constructed) -- which is why
availability is `find_spec` and never an import.  And rdeditor draws
a connection point labelled `R`, relabelling it in its own `mol`
setter, where the box says `*` and the tab says `X`; the tooltip says
so rather than leaving somebody to work it out.

**The acceptance ran end to end**: benzene-1,4-dicarboxylate drawn
click by click from the toolbar with two connection points, Build,
a tab of 18 atoms with 2 `X` in it, saved as a building block, and
868 blocks in the MOF picker afterwards -- the 867 PORMAKE ships and
the one this application drew, with nothing further clicked.

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
| **V** | The engines answer in pictures | L | |
| **W** | The klassengleiche half | L | |

Phases U to W schedule **every entry left in
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
