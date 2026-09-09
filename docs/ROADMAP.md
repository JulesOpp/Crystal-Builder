# Crystal Builder — delivery plan for the TODO

[docs/PLAN.md](PLAN.md) is the architecture and the roadmap that got
the application built; [docs/TODO.md](TODO.md) is everything that came
out of using it and has never been scheduled.  This file schedules it:
what order, what each phase delivers, and what it is allowed to touch.

Every phase ends with something runnable and a green suite, which is
the same rule [docs/PLAN.md](PLAN.md) § 16 works to.  Sizes are orders
of magnitude, not estimates: **S** is a day or less, **M** a few days,
**L** a week or more.

A phase ships and its entries are deleted from
[docs/TODO.md](TODO.md); a phase that has shipped is deleted from here.
What follows is everything still owed.

---

## 1. The order

| Phase | Theme | Size |
|---|---|---|
| V | The engines answer in pictures | L |
| W | The klassengleiche half | L |

The argument is **wrong before missing, and small before large**.
V and W are where an external tool and a piece of crystallography most
users never reach are owed work, and neither blocks the other.

Phase 6 has shipped: the UFF parameter table carries UFF4MOF and
UFF4MOF-II, the typer chooses between Rappe's rows and the fitted ones
by measuring the coordination shape and asking whether the metal is
held by an organic linker, and the Force Field dock offers a second
engine — GFN1-xTB, GFN2-xTB and GFN-FF through the tblite and xtb
binaries.  What it did *not* deliver is in [docs/TODO.md](TODO.md)
§ Force fields, and the largest of those is that neither program's
stress could be made to agree with a numeric one.

**One cheap win is available at any time**: the `.cgd` writer for
Systre (Phase V, an afternoon).  It is listed last in priority and is
also the only way to *doubt* the net the Net panel names.

---

## 2. Phase V — the engines answer in pictures

**Goal:** the half of the external tools that is a drawing rather than
a number, and the half of DFTB+ its own driver does better.

| Item | TODO entry | Size |
|---|---|---|
| Export a net as `.cgd` for Systre | Topology | S |
| Zeo++: draw the answer, do not only print it | Modules | M |
| DFTB+'s own driver | Modules | L |

**The `.cgd` writer is an afternoon.**  The Net panel says **pcu** and
the canonical key makes that a decision rather than a match, and there
is still no way to doubt it.  `xtal/io/cgd.py` reads the format and
does not write it; a writer and an action that saves the drawn net
through it is the only second opinion that does not come from the code
that produced the first.  One `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL`, and a `NODE` per vertex with an `EDGE` per edge — the net is
already in that shape.

**Zeo++ is the reason this phase exists.**  A porous-materials
application that can only *print* 9.18 Å is a spreadsheet.  `-res`
gives the diameter and not the position, so the largest free sphere
drawn where it sits needs `-chan` or `-visVoro` and a new actor beside
`_set_polyhedra`.  Channel dimensionality falls out of `-chan` for
free, and `-vol` is parsed already and wants an action of its own.

**DFTB+'s own driver is a module, not an engine** — and per the note in
[docs/TODO.md](TODO.md), a wrapper over what DFTB+ already does rather
than a reimplementation of any of it.  As an engine it does a single
point and a geometry optimisation with the symmetry projection intact;
what the internal driver does better is **lattice relaxation** (ours
costs twelve extra energy evaluations a step because no analytic stress
is claimed) and **molecular dynamics**, which has no route through
`Calculator` at all.  `ff/dftb/hsd.py` writes the input, `io/gen.py`
reads the geometry back and `modules/process.py` runs, streams and
cancels it; what is new is a `Driver` block, a multi-step output parser
and the trajectory read into the transport bar.

**The cheaper half of the stress question comes first**: read DFTB+'s
printed stress tensor and *check* it against `numeric_stress` on a
structure with a known answer.  If it agrees, the engine claims it and
variable-cell relaxation gets twelve times cheaper with no driver
written.  Phase I's redraw rule applies in full — what lands in the run
folder is a function of the run and not of what the window was showing.

---

## 3. Phase W — the klassengleiche half

**Goal:** *Descend to a subgroup* offers the subgroups that split an
orbit without touching the cell, and then the ones that double it.

| Item | TODO entry | Size |
|---|---|---|
| A lost centring, in the same cell | Symmetry | M |
| A doubled cell, from the table | Symmetry | L |

**A lost centring needs no cell transformation.**  Fm-3m contains
Pm-3m as a genuine subset of its operations, at index 4, in the same
cubic cell; rock salt descended that way puts its sodiums and chlorines
on eight independent sites, which is the cation-ordering model — and it
is why halite is the one fixture where no descent splits anything.

**It does not fall out of the existing enumeration** by not dividing
the centring out.  `core/subgroups.py` reduces modulo the centring
translations on purpose: the reduction is what makes the closure
affordable, and the "generated by at most three elements" shortcut is a
fact about crystallographic *point* groups that stops being safe the
moment the translations are back in.  The tractable route keeps the
reduction — enumerate the subgroups of the *centring* group the point
group leaves invariant, lift the reduced generators through each coset
representative, and close.  Naming and application need nothing new.

**The doubled cell is a table, not a computation.**  Superstructures
and antiferromagnetic ordering live there and every relation carries
its own cell transformation and origin shift: Bilbao's MAXSUB.  Last,
and worth not implying the earlier versions do it — the dialog says
*translationengleiche* and no cell is doubled, which stays true until
this lands.

---

## 4. What this plan does not do

* It does not schedule the **parallel-suite hang**
  ([docs/TODO.md](TODO.md) § Testing).  Serial is the default and the
  suite is green; the hang costs 60 s a run, not correctness, and the
  diagnosis in [CLAUDE.md](../CLAUDE.md) is where it waits for someone
  with an afternoon and a `faulthandler` dump.
* It does not schedule volumetric data, SHELX round-trips or Rietveld.
  Those are [docs/PLAN.md](PLAN.md) § 12 and stay there until this
  list is finished.  PXRD shipped and is deliberately not Rietveld.
* It does not promise the 2D sketcher — it promises the 3D builder
  under it and a text route into it.
* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase above keeps the core
  Qt-free, keeps every mutation a command, and adds capability through
  registries — and where an entry is expensive, it is usually because
  it is being made to obey those rules rather than go around them.
