# Energy Scans

A relaxed scan sets a coordinate, relaxes everything else, and moves
on: the energy landscape of a flexible framework -- what a breathing
MOF costs as its cell opens -- is the case it was written for.  After
this section you know what a scan holds and how, how to write an
axis, why both directions are walked and unconverged points are
holes, what a scan writes to disk as it goes, and how to open a
landscape again.

```{index} single: energy scan
```
```{index} single: relaxed scan
```
```{index} single: constraint; holonomic
```
```{index} single: hysteresis
```
```{index} single: landscape; energy
```

## What a scan is

An axis is a coordinate and a list of values, and one driver walks
them all: a cell parameter (`a`, `b`, `c`, `alpha`, `beta`, `gamma`),
the cell **volume**, or an internal coordinate -- a **distance**, an
**angle**, a **torsion**, or the angle between two best-fit
**planes**.  One axis is a profile, two are a grid.  At every point
the coordinate is set, the rest of the crystal is relaxed with the
optimiser of {doc}`optimisation` under the same space group, and the
energy, the relaxed structure and what the coordinate actually came
out at are written down.

**A scan holds a coordinate; it does not freeze the atoms that define
it.**  The obvious way to make a dihedral stay put is to freeze its
four atoms, and the application can -- but that removes twelve degrees
of freedom to constrain one, and the profile that comes back is the
constraint's, biased upward by however much the frozen atoms wanted to
move for reasons that had nothing to do with the dihedral.  So the
coordinate is held properly, as a {term}`holonomic constraint`, by
the two halves every constrained minimiser has had since SHAKE
{cite}`ryckaert1977shake`:

- the search direction is **projected** onto the subspace that leaves
  the coordinate alone, so a step does not try to change it; and
- the point is **restored** onto the constraint afterwards by Newton's
  method, because a tangent step leaves it by order of the step squared
  and that accumulates over a few hundred iterations.

Both are done inside the line search and in the optimiser's own
variables -- the {term}`asymmetric unit` and the symmetry-adapted
strain -- so the search walks *along* the constraint, the energy it
compares belongs to a point that satisfies it, and a held coordinate
composes with everything already there: a site on a special position
stays on it, a frozen site stays frozen, a cubic cell stays cubic.  The
projector is applied after the site-symmetry projectors and the frozen
mask, so a constraint can only ever take freedom away.

Two more decisions shape what an axis can be:

- **An endpoint is a group of atoms, not an atom.**  A group of one is
  an atom; a group of many is its centroid, recomputed from wherever
  its atoms are at the time.  A placed centroid marker would have been
  the obvious way to say "the middle of that ring", but a marker is a
  snapshot, and every engine holds {term}`dummy atom`s back at the
  door, so a marker feels no force: constraining a distance to one
  would be satisfied by sliding the marker at no cost -- a flat profile
  that looks like a result.
- **The periodic images are chosen once and then held.**  A
  measurement in a panel re-decides the nearest image on every call; a
  constraint cannot, because an atom drifting past the half-cell would
  make the coordinate jump by a lattice vector, and an optimiser cannot
  descend a function with a step in it.  So an anchor resolves its
  images against the structure the scan was set up on, and from then
  on the coordinate is a smooth function of the positions and the
  cell.

## Writing an axis

```{index} single: scan axis; syntax
```

One grammar serves the dialog, the command line and the log, so any
scan can be re-run from the line it printed.  An axis is a cell
parameter, `volume`, or an internal coordinate over **P1 atom
indices**: `distance 0, 5`, `angle 0, 1, 2`, `torsion 0, 1, 2, 3`,
`plane 0+1+2, 6+7+8`.  Commas or spaces separate the anchors and `+`
joins atoms into one anchor -- their centroid, which follows them -- so
`distance 32, 33` is two atoms and `plane 0+1+2, 6+7+8` is two rings.
(An older form with spaces between anchors and commas inside one still
parses when the new reading gives the wrong count, so old logs
re-run.)  In the dialog, **Add the selection** writes the indices of
the atoms selected in the view, in the order they were picked.

## What the cell does at each point

The cell decision is the substance of setting a scan up, and it is
made before the first point:

- Scanning **every** cell parameter the space group leaves free fixes
  the cell completely; the point then relaxes with no cell variables
  at all, which is exact and one evaluation a step instead of thirteen
  on an engine with no analytic stress.
- Scanning **fewer** than all of them holds the scanned ones and lets
  the rest relax, through the strain subspace of {doc}`cell`.
- Scanning the **volume** holds it with the shape free.  Scanning the
  volume and a lattice parameter together is refused as ambiguous:
  setting one changes the other.
- A parameter the group ties is refused with the ties spelled out;
  scanning with the symmetry broken is
  {ref}`Reduce to P1 <cmd-reduce_p1>` first, because the scan never
  drops the group on its own.

:::{note}
A scan refuses what it cannot hold, **before the first point**.  The
constraint check is run against the asymmetric unit when the scan is
planned, so a distance the group fixes -- every Na--Cl distance in
Fm-3m -- is a message in the dialog (*nothing the optimiser may change
moves the distance …: the space group ties it, or its atoms are
frozen, or it sits where it is undefined.  Reduce to P1 first, or scan
a coordinate the symmetry leaves free*), not a grid of 144 holes each
with the same message after the dialog had said the scan was fine.
:::

## Seeds, directions and holes

```{index} single: scan; seed
```
```{index} single: scan; unconverged point
```

**A point starts from its neighbour, and that is visible.**  Carrying
the last relaxed geometry into the next point (**Starting geometry:
Carry on from the nearest point**, the default) is what makes a scan
affordable, and it is also what makes it path-dependent: near a
transition the optimiser stays in the basin it arrived in.  Measured
on zinc acetate under UFF, the same target cell reached from a relaxed
neighbour and from the original input differed by 2.6 kcal/mol.  So
the seed is a setting (**Restart from this structure** is the other),
**both directions are walked by default**, and the two branches are
reported side by side rather than averaged into one curve.  The way
back starts where the way out finished, and the {term}`hysteresis`
between them is the interesting part.

**A point that did not finish is not a number.**  One whose optimiser
failed, that was stopped in the middle, or whose relaxed cell came out
with a different atom count has no energy at all: NaN, hatched on the
heat map, outside the colour scale, crossed out in the contour window,
`--` in the log, with the reason beside it -- never a number for
another crystal, and it does not seed its neighbour.  A hole plotted as
a zero would be the deepest point of every landscape it appears in,
and a false minimum looks exactly like a real one.  A point that ran
to the step limit keeps the energy where it stopped, is reported
*(not converged)* in the log and `no` in the table, and is drawn apart
from the converged points rather than blended in.  A run that is
stopped keeps the points it finished (*Stopped after N of M points;
they are on disk*).

**A point may be pre-relaxed by a cheaper engine.**  A volume step
scales every coordinate with the cell, so each point starts a long way
from its minimum, and a machine-learned potential pays for all of that
walk at its own price.  **Pre-relax with** spends the first stretch on
something like UFF4MOF, under the same held coordinates and to a loose
tolerance (0.5 kcal/mol/Å by default, because the cheap engine's
minimum is not the one wanted), and the engine the landscape is *of*
finishes from there.  Only the second engine's energy is reported.
Measured once, small: MIL-53 (104 atoms), volume at 90 % and 80 %,
MACE-MPA-0 alone took 467 s; UFF4MOF first then MACE took 196 s and
landed 0.02 and 0.08 kcal/mol lower.

## What a scan leaves behind

```{index} single: scan.csv
```
```{index} single: report.json
```

A scan runs as **one job on one thread**, never one per point, because
a point starts from its relaxed neighbour: the grid is a walk and not
a batch, and splitting it across workers would seed each point from
wherever its worker happened to be.  It is also an overnight job --
0.44 s a step on Ni{sub}`2`Cl{sub}`2`BTDD's 1152 atoms under UFF, so a
12×12 grid is about 2.6 hours -- so **every point is written the
moment it finishes**, not gathered up and saved at the end.  Stop, a
crash or a full disk leaves a landscape behind rather than losing one.
The run folder holds:

`scan.csv`
: One row per finished point: the target and achieved value of each
  axis, the branch, the energy, whether it converged, the steps, the
  largest force, the six cell parameters and the file the point left.

`forward-NN.cif`, `reverse-NN.cif`
: The relaxed structure at each point, by branch and index.  Each
  carries the bond graph perceived on the structure the scan started
  from, because its cell is not the one the bonds were perceived at
  and opening it would otherwise perceive again (MFU-4l at +15 % on
  *a* opens with 560 of its 848 bonds).  Bonding is perceived once,
  before the first point, so every point is the same molecule.

`report.json`, `run.log`
: The report the {ref}`Results panel <panel-results_dock>` shows, and
  the log with every setting and the line per point.

The scan returns **no structure**: the tab it ran on is the crystal the
landscape is *of*, and the points are files to open.  Double-clicking
`report.json` in the {ref}`Workspace panel <panel-file_dock>` puts the
landscape back in the Results panel after the panel was closed, or
the application was; a click on a point of the grid there opens the
structure at that point.  The contour window opens the same grid in a
window of its own -- contours say how steep the walls are and whether
there are two basins with a ridge between them, which is the whole
question asked of a flexible framework -- and needs matplotlib.

## Practical notes

- **The engine is read from the Force Field panel, not configured in
  the scan.**  Set it up there first ({ref}`panel-ff_dock`); the scan
  dialog shows the engine's atom-type table for any engine that
  provides types, and an override made in either place is the same
  undoable edit.  For a flexible framework the engine's own help says
  a machine-learned potential is the better choice: UFF4MOF was never
  fitted to reproduce a breathing double well.
- The dialog says three things in one line that updates as you edit
  the boxes: how many points, how long that is likely to take, and
  what is held while each point relaxes.  Read it before pressing
  **Run**.
- Leave the optimiser at **Smart**: every point after the first starts
  near a minimum, but the first one may not.  **Steps per point** is a
  ceiling, not a target.
- Scan a small grid first.  A 3×3 grid answers whether the axis is the
  one you meant and whether the points converge, at a hundredth of the
  overnight price.
- The achieved value is reported beside the target and the relaxed
  cell so that a kink in the landscape can be told from a jump between
  basins.

## Worked example: a lattice parameter of quartz

A scan through the real module path, on the nine-atom quartz cell the
test suite uses (α-SiO{sub}`2`, P3{sub}`2`21, *a* = 4.9134 Å, *c* =
5.4052 Å; written out of the `quartz` fixture in `tests/conftest.py`).
The group leaves *a* and *c* free, so scanning *a* holds it and lets
*c* relax; three points, both directions, UFF4MOF:

```console
$ xtal run scan.run quartz.cif -p axis1=a -p axis1_start=4.8 -p axis1_stop=5.0 -p axis1_steps=3 --workspace ws
6 points on UFF (uff4mof)
[1/6] a 4.8: -24.3375 kcal/mol
[2/6] a 4.9: -26.1463 kcal/mol
[3/6] a 5: -24.3023 kcal/mol
[4/6] a 5: -24.3023 kcal/mol
[5/6] a 4.9: -26.1463 kcal/mol
[6/6] a 4.8: -24.3375 kcal/mol
6 of 6 points relaxed

Relaxed scan

Every point
a (A)   branch   E (kcal/mol)  dE       steps  |F|max  a       c       converged
4.8000  forward      -24.3375  +1.8088     14  0.0221  4.8000  5.3651  yes
4.9000  forward      -26.1463  +0.0000     14  0.0253  4.9000  5.3221  yes
5.0000  forward      -24.3023  +1.8440     12  0.0289  5.0000  5.2814  yes
5.0000  reverse      -24.3023  +1.8440      0  0.0289  5.0000  5.2814  yes
4.9000  reverse      -26.1463  +0.0000     13  0.0139  4.9000  5.3221  yes
4.8000  reverse      -24.3375  +1.8088     11  0.0403  4.8000  5.3651  yes

The achieved value is reported beside the relaxed cell so that a kink in the landscape can be told from a jump between basins.

Energy profile
    4.80  ###########################################
    4.90  
    5.00  ############################################
          a (A)

Energies from UFF (uff4mof), in kcal/mol for the whole cell.  This is a landscape at zero kelvin: it is an energy, not a free energy, and for a flexible framework the two can order the phases differently.
run folder: ws/quartz/scan-scan-001
```

The log's own description of the plan reads *Relaxed scan holding a
at each of 3 values, with the cell relaxed, holding a, seeded from the
previous point, walked in both directions*.  The reverse branch starts
where the forward one ended (its first point takes 0 steps) and
retraces it: the two branches agree to a ten-thousandth of a kcal/mol
at every point, so there is no hysteresis to report here.  The folder
holds `scan.csv`, `forward-00.cif` to `forward-02.cif`,
`reverse-00.cif` to `reverse-02.cif`, `report.json` and `run.log`.

Asking for a parameter the group ties is refused before anything runs:

```console
$ xtal run scan.run quartz.cif -p axis1=b -p axis1_start=4.8 -p axis1_stop=5.0 -p axis1_steps=3 --workspace ws
[...]
xtal.ff.scan.ScanError: b is not free in SpaceGroup(P3221 #154): b = a, alpha = 90, beta = 90, gamma = 120.  Scan one of a, c.
```

% TODO(Sam): the refusal reaches the command line as a Python
% traceback ending in that sentence rather than as "error: ..."; the
% dialog shows the sentence.  Reported.

The same cell over an internal coordinate -- the Si0--O3 distance,
1.604 Å in the input -- ran every point to the 500-step limit in this
draft's test, with the largest force reported at 10 to 80 kcal/mol/Å,
while the cell scans above converged in 11 to 19 steps:

```console
$ xtal run scan.run quartz.cif -p "axis1=distance 0, 3" -p axis1_start=1.55 -p axis1_stop=1.65 -p axis1_steps=3 -p direction=forward --workspace ws
3 points on UFF (uff4mof)
[1/3] distance 0-3 1.55: -18.8197 kcal/mol (not converged)
[2/3] distance 0-3 1.6: -25.4568 kcal/mol (not converged)
[3/3] distance 0-3 1.65: -13.7216 kcal/mol (not converged)
3 of 3 points relaxed; 3 did not reach the force tolerance and are marked apart
[...]
```

Whether the reaction force of the held distance is being counted in
|F|max -- which would make a held internal coordinate converge only
where the constraint happens to be slack -- is a question for the
author, listed with this draft.

% TODO(Sam): question for Julius -- the distance scan on quartz never
% converges; the convergence test in xtal/ff/optimize.py reads the
% unprojected gradient.  Is |F|max meant to exclude the constraint
% force?

## Settings

Every setting -- engine, the two axes, seed, direction, optimiser,
steps per point, force tolerance and the pre-relaxation -- is listed
under {ref}`Relaxed scan… <mod-scan-run>`; the entry is *Modules ▸
Energy scan ▸* {ref}`Relaxed scan… <cmd-module.scan.run>`.  On the
command line it is `xtal run scan.run FILE -p axis1=… -p
axis1_start=… -p axis1_stop=… -p axis1_steps=… [--workspace DIR]`, with
`axis2…` for a grid and `-p direction=forward` for one branch.

## Limitations

- **The scan has never been run on a real framework end to end.**
  Every test is on quartz, zinc acetate or a fixture, because the point
  was the machinery.  Ni{sub}`2`Cl{sub}`2`BTDD is the structure it was
  asked for -- 1152 atoms, *a* and *c* its only free parameters, 0.44 s
  a step under UFF, a 7×7 grid about two and a half hours -- and
  whether UFF4MOF shows a breathing double well at all is unknown
  (`docs/TODO.md`).
- **A stopped scan cannot be carried on.**  `scan.csv` already holds
  everything a resume would need, but there is no `--resume`; a run
  stopped at point 60 of 144 is restarted.
- **A sweep still starts at the end of its range, not at the
  crystal.**  The first point is reached from the input structure by
  one jump that can be the whole width of the scan; measured on
  MIL-53, a volume scan from 50 % to 120 % opened its forward branch in
  a poor basin 318--435 kcal/mol above the reverse branch for three
  points.  The lower envelope hides it, but the numbers on that branch
  are wrong.
- **E(V) is not F(V).**  The landscape is at zero kelvin and the report
  says so.  For the flexible frameworks it was built for that is the
  whole question: entropy decides which phase of MIL-53 is stable, and
  the quasi-harmonic route Cockayne took for MIL-53(Cr)
  {cite}`cockayne2017mil53` needs a phonon calculation this application
  does not have.
- An internal-coordinate scan's convergence is the open question
  above.
