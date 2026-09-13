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
| V | The engines answer in pictures | S |

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
a number.

| Item | TODO entry | Size |
|---|---|---|
| Export a net as `.cgd` for Systre | Topology | S |

**The `.cgd` writer is an afternoon.**  The Net panel says **pcu** and
the canonical key makes that a decision rather than a match, and there
is still no way to doubt it.  `xtal/io/cgd.py` reads the format and
does not write it; a writer and an action that saves the drawn net
through it is the only second opinion that does not come from the code
that produced the first.  One `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL`, and a `NODE` per vertex with an `EDGE` per edge — the net is
already in that shape.

**Zeo++ has shipped.**  A porous-materials application that can only
*print* 9.18 Å is a spreadsheet, and it no longer only prints:
`-chan` gives the number of channels and the dimensionality they run
in, `-visVoro` puts the largest included sphere in the viewport where
it actually sits with the channel skeleton through it, `-vol`/`-volpo`
has an entry of its own, and that entry draws the accessible surface
of the volume it measured.

The surface turned out not to be a Zeo++ job at all -- both of its
grid writers fail on this application's own stress case -- so the
distance grid is built here, by KD-tree, with the radii the run was
given.  That is the better answer anyway: the picture and the number
are one measurement, and the grid's accessible fraction agrees with
Zeo++'s Monte Carlo one to within its own spacing, which is a check
neither half could make alone.

The one thing that cannot be drawn is where D_f *sits*: it is the
width of a bottleneck on a Voronoi edge, and no Zeo++ output carries
edge radii.  The table says so in words rather than putting a ball
somewhere plausible.  What is left over is in
[docs/TODO.md](TODO.md) § Modules and is small.

**DFTB+'s native runs have shipped**, as entries of the DFTB+ module
that write the input, run DFTB+ (and `waveplot` or `modes`) in the run
folder, and read the answer -- nothing DFTB+ does natively is done
again here.  Band structure along ASE's path with the Brillouin zone
drawn, the density of states projected per element beside it, Mulliken
charges colouring the atoms, an orbital's two lobes, DFTB+'s own
relaxation with the cell (mapped back onto the space group, and refused
when it would split an orbit), molecular dynamics into the transport
bar, and vibrational modes that animate there.

What that did not do is the stress question for the *engine*: the
DFTB+ panel's own variable-cell relaxation still takes a numeric stress
because DFTB+'s printed tensor was never checked against one.  The
native driver sidesteps it -- LatticeOpt uses DFTB+'s stress inside
DFTB+ -- and the engine can claim it once somebody has made that
check on a structure with a known answer.

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
