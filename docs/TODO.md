# TODO
# In the DFTB+ module, add options to calculate band structures, plot them, and export the band structures. Present me some options for other functionality of DFTB+ that we can wrap into this app. I want to also show the unit cell so the user knows what the gamma point, x point, etc are.

Work that is wanted but not yet scheduled into a phase.
[docs/PLAN.md](PLAN.md) holds the roadmap; this file holds everything
that came up while using the application and does not belong to a phase
yet.  An entry gets deleted when it ships, not ticked.

[docs/ROADMAP.md](ROADMAP.md) is the delivery plan for what is in
here: which phase each entry belongs to, in what order, and what has to
exist before it.

---

## Symmetry

### Merge duplicates cannot see a site duplicated by its own group

`symmetry.duplicate_groups` compares a site against *other* sites'
images and never against its own, so a site far enough off a special
position for the group to generate two of it is invisible to Merge
Duplicates at any tolerance.  Raising `p1.SPECIAL_POSITION_TOL` to
0.05 A closed this at the tolerance the dialog opens on -- the
expansion now collapses anything the default merge would have wanted
to -- but a user who drags the tolerance to 0.2 A can still be told
"no duplicates" about images 0.1 A apart.

It is a *reporting* gap rather than a merging one: merging drops whole
sites and a site's own orbit cannot be half-dropped, so the honest fix
is for the preview to say "Zn1 is 0.06 A off its mirror and the group
is making three of it" and point at Standardize, not to offer a merge
that cannot happen.  Wanted with whatever finally reports a site
sitting just off a special position, which nothing does today.

## Force fields

### UFF4MOF's O_2_z has no rule behind it

The type is in the table and is reachable only through the per-atom
override.  The obvious reading of it -- the carboxylate oxygen on a
framework metal -- was tried and measured: relaxing MOF-5 with it puts
Zn-O(carboxylate) at 1.834 A against an experimental 1.941, where
leaving those oxygens as `O_3` gives 1.891.  It makes the one number
it is supposed to fix worse, so `xtal/ff/uff/typer.py`'s `_oxygen`
deliberately does not assign it and says so.

What is wanted is the environment the 2014 paper actually fitted it
for.  Its parameters are an sp2 oxygen with `O_3_z`'s shortened radius,
which is a clue and not an answer.

### Neither tblite nor xtb gives a stress this application can use

`xtal/ff/xtb/calculator.py` sets `provides_stress = False` and pays
`numeric_stress`'s twelve evaluations a step, which is the same price
DFTB+ pays and for a better-measured reason: tblite writes a virial,
and dividing it by the cell volume disagrees with a numeric stress by
ten per cent on quartz under GFN1-xTB -- 0.874 against 0.972
kcal/mol/A^3 on the two equal diagonal components, with the numeric
one stable to four decimals from a 1e-3 strain down to 1e-5.

Ten per cent is not noise and not a sign convention.  Finding the
normalisation makes variable-cell relaxation twelve times cheaper for
both external engines.  The measurement above is the whole method:
build the engine over quartz, compare `Result.stress` against
`Calculator.numeric_stress`, and vary the strain to show which of the
two is the unreliable one.  `tests/test_xtb.py` asserts only that no
stress is claimed, which is today's behaviour and not the wanted one.

### The GFN methods are one binary each, and it is not by choice

`xtal/ff/xtb/calculator.py`'s `METHODS` routes GFN1 and GFN2 to tblite
and GFN-FF to xtb, and offers no control over it, because measurement
left nothing to choose:

| | tblite 0.3.0 | tblite 0.6.0 | xtb 6.7.1 |
|---|---|---|---|
| GFN2, periodic | works | **SIGSEGV** | refuses: "Multipoles not available with PBC" |
| GFN1, periodic | works | works | **SIGSEGV** |
| GFN-FF, periodic | — | — | works |

Both crashes are the program's and not this application's.  tblite
0.6.0 segfaults on a two-atom silicon cell as readily as on MOF-5's
424, right after printing its repulsion energy; xtb's periodic GFN1
fails to diagonalise the silicon cell and segfaults on MOF-5 *after*
reporting its own SCC converged, with or without `--grad` and with
none of our flags involved.

So GFN2 needs a tblite that works, and this application cannot tell
which one it has been pointed at short of running it.  What would help
is a cheap self-test -- a two-atom cell through the chosen binary,
once, when the path preference changes -- which is the same shape as
the Slater-Koster check DFTB+ does before it launches.

### UFF4MOF-II redefines Pt4+2 and the table does not

The machine-readable UFF4MOF table carries a second `Pt4+2` with
`r1 = 1.125` where Rappe's is 1.364, under the same name -- so it is a
replacement and not an addition, and there is no way to hold both.
`xtal/ff/uff/params.py` keeps Rappe's and skips it, because changing a
row the 1992 paper prints is a different decision from adding ninety-one
new ones, and `tests/test_uff_params.py` asserts the published value.

## Modules

### DFTB+'s own driver

Jules note that overrides anything below: We want to use all of the 
Native features of DFTB+. Do not rewrite anything that already exists
Within DFTB+ natively. We just need to make a wrapper for it.

DFTB+ is here as an *engine*: a `Calculator` in `ENGINES`, so the
optimiser already in this application drives it with the symmetry
projection intact and the panel, the plot, the trajectory and Stop all
work unchanged.  That is the right way in for a single point and for a
geometry optimisation, and it is the wrong way in for two things
DFTB+'s internal driver does better.

* **Lattice relaxation.**  Ours costs twelve extra energy evaluations
  a step because no analytic stress is claimed -- DFTB+ prints one and
  its sign and volume conventions were not worth guessing at, since a
  stress read the wrong way round relaxes a cell in the wrong
  direction and reports converging while it does it.  DFTB+'s own
  `Driver = ConjugateGradient { MovedAtoms ... LatticeOpt = Yes }`
  uses it directly.  Either that, or read the block and *check* it
  against a numeric stress on a structure with a known answer, which
  is the cheaper of the two and would let the engine claim it.
* **Molecular dynamics**, which has no route through `Calculator` at
  all: it is a trajectory DFTB+ produces, not a sequence of energies
  we ask for.
* As a **module** rather than an engine, then: one entry per driver,
  the run folder holding `dftb_in.hsd`, `detailed.out`, `geo_end.gen`
  and `md.out`, and the trajectory read back into the transport bar --
  which already plays anything `xtal/io/trajectory.py` can read.
* The parts that would be reused rather than rewritten are most of it:
  `xtal/ff/dftb/hsd.py` writes the input and checks the parameter set,
  `xtal/io/gen.py` reads the geometry back, and
  `xtal/modules/process.py` runs, streams and cancels it.  What is new
  is a `Driver` block and the parsing of a multi-step output.

### The pore surface is not a contour of anything but distance

The accessible surface ships: `xtal/analysis/grid.py` samples the
distance to the nearest atom surface over the cell and its periodic
images, `xtal/analysis/isosurface.py` marches it, and the
accessible-volume run draws the boundary of the volume it just
reported.  Two things it does not do, and neither blocks anything:

* **Pockets are drawn with the channels.**  Zeo++ splits its numbers
  into AV and NAV -- what a probe can reach from outside, and closed
  voids it cannot -- and the surface makes no such distinction, so a
  framework with sealed cavities draws them alongside its channels.
  Telling them apart means a connected-component pass over the grid
  with a union-find that carries periodic offsets, which is the same
  algorithm `CHANNEL::findChannels` is, and it would also give the
  surface a per-component colour.
* **Nothing welds the vertices.**  Marching tetrahedra emits six per
  cut cell and shares none between them, so MFU-4l's surface is
  567 000 points for 189 000 triangles.  It renders, and the mesh is
  thrown away on the next run, so this is only worth doing if the
  surface ever needs to be *written* -- an STL for a figure, or the
  project file it is deliberately kept out of.

## Topology

### Nothing can export a net for Systre to check

The naming itself has shipped: the Net panel says **pcu**, the
invariants it rests on are underneath it, and the canonical key of
[docs/TOPOLOGY.md](TOPOLOGY.md) § 5 makes that a decision rather than a
match.  What is missing is the way to doubt it.

`xtal/io/cgd.py` reads `.cgd` and does not write it.  A writer, and an
action that saves the drawn net through it, is the only way to put a
net in front of **Systre** -- the reference implementation, in Java --
and get a second opinion that does not come from the same code that
produced the first.  The key checks itself against a supercell of
itself and against 2929 catalogued nets, and neither of those is an
independent check.

Small: the format is one `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL` and one `NODE` per vertex with an `EDGE` per edge, and the net
is already in exactly that shape.

## Testing

### The parallel suite hangs about one run in ten

`python -m pytest -q` finishes in 40-55 s almost every time, and
roughly once in ten it stops at about 96% and never returns.  Serial
(`-n0`) has never done it in 1563 tests, and the GUI files on their own
have never done it either -- it takes the whole suite under `-n auto`.

* **Nothing is computing when it happens.**  Sampling the processes at
  the stall shows the controller *and* all eight workers parked in
  `lock_PyThread_acquire_lock`, with the receiver threads blocked
  reading their pipes: everyone is waiting to be told what to do next.
  It is xdist losing a unit of work, not a test looping.
* **The test left unfinished is a different one each time**, and it has
  always so far been one that builds the `window` fixture and starts a
  worker thread -- `test_the_pressure_box_follows_the_cell_checkbox`,
  `test_freezing_everything_refuses_instead_of_running`,
  `test_the_parameters_are_offered_again_next_time`.  Each of them
  passes on its own and passes with the other GUI files, repeatedly.
* The suspicion worth starting from is a worker thread outliving the
  window that parented it -- `start_in_thread(worker, window)` in
  `xtalapp/workers.py` -- and the report for that test never being
  sent, rather than anything in the test itself.
* **It predates the shell split.**  Measured against
  `xtalapp/layout.py`'s commit: HEAD 8 runs clean, the branch 10 clean
  and 1 hung, which is the same rate either side.
* Until it is found: a hang is not a failed run, it is *this*.  Kill it
  and run again, and clear the orphans first --- `pkill -f pytest;
  pkill -9 -f "stdin.readline"` --- because a killed run leaves workers
  that wedge every later one, which is how this gets mistaken for a
  regression in whatever was being worked on at the time.
