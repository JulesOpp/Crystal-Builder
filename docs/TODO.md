# TODO
# In preferences add an option for dark mode

Work that is wanted but not yet scheduled into a phase.
[docs/PLAN.md](PLAN.md) holds the architecture;
[docs/ROADMAP.md](ROADMAP.md) schedules what is in here.  This file
holds everything that came up while using the application.  An entry
gets deleted when it ships, not ticked.

---

## Interface

### Dragging a panel has not been tried with a real mouse

The dividers were measured through `QMainWindow.resizeDocks`, which is
what a drag ends up calling, and the causes found that way are fixed:
per-panel minimums, the tab bar's width, and every dock being a native
window (`xtalapp.application.keep_siblings_non_native`).  Nothing has
driven an actual pointer, because run-app cannot without taking over
the user's.  If a drag still misbehaves -- especially one that ends
over the 3D view, which is still a native window -- that is the next
place to look.

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

The DFTB+ panel's own variable-cell relaxation has the same gap:
DFTB+'s printed stress tensor has never been checked against a numeric
one, so the panel pays for a numeric stress.  The native driver
(*Optimise with DFTB+'s driver*) sidesteps it, because LatticeOpt uses
DFTB+'s stress inside DFTB+.

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

### A chelate's joint comes out 0.3 A long, and the cell with it

Measured in Phase 8, 2026-09-21.  Ni3(HITP)2 built on `hcb` has the
crystal's Ni-N to the thousandth (1.836-1.840 A against 1.838) and
the crystal's bite angle, 88.2 degrees -- and the N-C bond across
every cut is **1.606 A against the crystal's 1.294**.  Two such
joints on every path from one triphenylene to the next make *a*
**22.731 A against 21.552, +5.5 %**; MFU-4l's +3.9 % on `pcu` is
the same thing at a C-C cut.

The cause is the invariant, not a bug in applying it.  A connection
point is `CONNECTION_DISTANCE` = 0.75 A from the centroid of the
atoms it stands for, so two ends meet with their centroids **1.5 A
apart** -- right for one atom onto one atom, which is what the
number was measured over.  A chelate's bonds lean inwards: two
nitrogens 2.56 A apart bonded to two carbons 1.42 A apart put the
centroids **1.16 A** apart along the axis, and the 0.34 A difference
is what every joint carries.

Two ways out, neither taken because both change a product decision:

* **Write the point where the crystal has it.**  A block cut from a
  real crystal knows its own bond: the point could sit half the
  measured centroid-to-centroid distance out rather than 0.75 A, and
  *Mark as one connection point* would record it.  That makes the
  distance a property of the block, which the invariant exists to
  stop -- a block written at a bond length builds every linker twice
  too long with nothing reporting it.
* **Leave it and say so.**  The build places blocks and stops;
  relaxation is the user's, in the Force Field panel, and a UFF
  relaxation will pull a 1.6 A C-N back.  The report could name the
  longest joint against a typical bond for the pair, so the number
  that is already measured reads as a warning rather than a figure.

`test_nihitp_builds_with_the_cell_the_crystal_has` pins 22.731 and
1.606, so either change has to move a test and say why.

### The .cgd writer has never met Systre

File ▸ Export Net for Systre is checked by reading the file back
through this application's own expansion, which is not an independent
check.  Run Systre on MOF-5's and rutile's exported nets once and keep
the output beside the tests.  Java 8 is installed; Systre is not.

### Net search knows vertices and edges, not faces and tiles

The Transitivity field takes `p q r s`, as MOF+ does, but only p and
q are known: they are the RCSR entry's `NODE` and `EDGE` lines
(`xtal.analysis.netsearch`).  r and s belong to the natural tiling,
and nothing here has it, so a number there matches nothing.  RCSR
publishes the transitivity of every net; vendor it as a small JSON
beside `xtal/analysis/data/rcsr-2019-06-01.json.gz`, with the script
that makes it, and fill `NetFacts.transitivity`.  A net of PORMAKE's
or the user's that the RCSR does not name keeps r and s unknown.

## Scans

The relaxed scan shipped on 2026-09-15
([docs/PLAN.md](PLAN.md) § 12a).  What it deliberately left out:

### A stopped scan cannot be carried on

`scan.csv` is written a row at a time and already holds everything
needed -- the targets, what was achieved, the branch, and the file each
point left behind -- so a run that was stopped at point 60 of 144 could
be resumed rather than restarted.  It is not, and on an overnight job
that is the difference between losing an evening and losing nothing.
The shape is a `--resume` that reads the CSV, drops the finished
indices from the raster, and seeds the first new point from the last
finished one.

### A sweep still starts at the end of its range, not at the crystal

The two branches of a scan now form a loop -- the way back starts
where the way out finished -- but the loop's *first* point is still
reached from the input structure by one jump, and that jump can be the
whole width of the scan.  Measured on `MIL53.cif`, a volume scan from
50% to 120% of the deposited cell: the forward branch opens at 1511
A^3 having been handed a geometry relaxed at 3023, lands in a poor
basin, and stays 318-435 kcal/mol above the reverse branch for three
points before it recovers.  The lower envelope hides it, which is why
this is not urgent, but the numbers on that branch are still wrong.

The fix is to sweep *outward from the crystal*: begin at the grid
point nearest the structure's own value for that axis, walk to one
end, then return to the start and walk to the other, so no point is
ever seeded by more than one step.  It changes what "forward" and
"reverse" traverse, which is why it is written down rather than done
in passing.

### E(V) is not F(V)

A scan is at zero kelvin and the report says so, but for the flexible
frameworks it was built for that is the whole question: MIL-53(Al)'s
large- and narrow-pore difference runs 18.67 / 9.74 / -0.67 kJ/mol at
100 / 300 / 500 K, so entropy decides which phase is stable and the
landscape cannot see it.  The cheapest honest route is **quasi-harmonic
F(V,T)**: phonons at each scanned volume, which is what Cockayne did
for MIL-53(Cr) (*J. Phys. Chem. C* **2017**, *121*, 4312).  Affordable
with MACE, where the Hessians are seconds rather than hours.  It needs
a phonon calculation this application does not have.

### The scan has never been run on a real framework end to end

Every test is on quartz, zinc acetate or a fixture, because the point
was the machinery.  Ni2Cl2BTDD is the structure it was asked for -- H-3m,
a and c its only free parameters, 1152 atoms, 0.44 s an optimiser step
under UFF -- and a 7x7 grid of it is about two and a half hours.  Run
one overnight with MACE and keep the landscape beside the tests; UFF4MOF
was never fitted to reproduce a breathing double well, and whether it
shows one at all is unknown.

Pre-relaxation has been measured once, small: `MIL53.cif` (104 atoms),
volume at 90% and 80%, MACE-MPA-0 to 0.1 kcal/mol/A, forward only.
MACE alone took 467 s; UFF4MOF first (80 and 73 steps) then MACE took
196 s, and landed 0.02 and 0.08 kcal/mol lower.  Whether that holds on
a 7x7 grid of a 1152-atom framework, where the neighbour it starts from
is already close, is the thing the overnight run should also answer.
