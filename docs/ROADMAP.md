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

The argument is **wrong before missing, and small before large**.

Phase W has shipped.  *Descend to a subgroup* offers the
klassengleiche half as well as the translationengleiche one: the
descents that give up part of the centring in the same cell — Fm-3m
contains Pm-3m at index 4, and rock salt descended that way is the
cation-ordering model — and the ones that give up enough of the
lattice that the cell grows, which are the superstructures.  Pm-3m
gives Fm-3m and Fm-3c on the doubled cell, and SrTiO₃ descended to
Fm-3m has two independent titaniums, which is the ordered double
perovskite and is not reachable in the parent's own cell.  Each row
says which kind it is and by how much the cell grows.

It needed no table.  Bilbao's MAXSUB was the plan; what it took
instead was to keep the reduction modulo the centring that makes the
closure affordable, and put the translations back afterwards by
lifting the reduced generators through their choices of translation
and keeping the choices that close — in the parent's cell for the
first half, and in the sublattice's own cell for the second, which is
also the only cell the naming probe can be built in.  Two bounds are
forced rather than chosen and are written down where the code makes
them: only maximal sublattices, and not the subgroups isomorphic to
their own parent, because those exist at every prime index and are an
infinite family that no list can hold.

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
| The accessible volume as an isosurface | Modules | L |
| DFTB+'s own driver | Modules | L |

**The `.cgd` writer is an afternoon.**  The Net panel says **pcu** and
the canonical key makes that a decision rather than a match, and there
is still no way to doubt it.  `xtal/io/cgd.py` reads the format and
does not write it; a writer and an action that saves the drawn net
through it is the only second opinion that does not come from the code
that produced the first.  One `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL`, and a `NODE` per vertex with an `EDGE` per edge — the net is
already in that shape.

**Zeo++ was the reason this phase exists, and most of it has
shipped.**  A porous-materials application that can only *print*
9.18 Å is a spreadsheet, and it no longer only prints: `-chan` gives
the number of channels and the dimensionality they run in, `-visVoro`
puts
the largest included sphere in the viewport where it actually sits
with the channel skeleton through it, and `-vol`/`-volpo` has an entry
of its own.  One `network` invocation does all of that over one
Voronoi decomposition, which is a second on MFU-4l.

What is left is the **isosurface**, and it turned out not to be a
Zeo++ job at all: both of its grid writers fail on this application's
own stress case, so the distance grid has to be built here.  That
makes it the first volumetric data in the application rather than an
afternoon over an existing file, which is why it is listed at L.
[docs/TODO.md](TODO.md) § Modules has the measurements.

The one thing that cannot be drawn is where D_f *sits*: it is the
width of a bottleneck on a Voronoi edge, and no Zeo++ output carries
edge radii.  The table says so in words rather than putting a ball
somewhere plausible.

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

## 3. What this plan does not do

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
