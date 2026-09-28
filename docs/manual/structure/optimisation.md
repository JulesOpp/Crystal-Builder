# Single Points and Geometry Optimisation

A single point is one energy at the geometry you have; an optimisation
moves the atoms downhill until the forces are below a tolerance.
After this section you know what the optimiser's variables are and
why the space group survives a relaxation, which of the seven
optimisers to choose and what *Smart* does, what the convergence
numbers mean, how to run one from the Force Field panel or the
command line, and what a run leaves behind in the workspace.

```{index} single: geometry optimisation
```
```{index} single: single point
```
```{index} single: optimiser; choosing
```
```{index} single: convergence; force tolerance
```

## What a relaxation is here

Every engine in {doc}`/energy/index` answers the same questions -- the
energy, the force on each atom and, where it can, the stress on the
cell -- and the optimiser asks them the same way whichever engine is
chosen.  What is particular to Crystal Builder is *what it moves*.

**The variables are the asymmetric unit, not the cell.**  A calculator
works on the {term}`P1` cell, because that is what has an energy; an
optimiser that moved those atoms independently would break the
symmetry on its first step, and there would then be no way to write
the answer back -- a structure in P4{sub}`2`/mnm has nowhere to put six
independently displaced oxygens.  So the variables are the sites of
the {term}`asymmetric unit`, the P1 cell is regenerated from them at
every step, and the gradient is carried back through the symmetry
operations that generated each atom.  Every atom of the cell is
$x_\mathrm{parent} W + b$ for a rotation $W$ and an offset $b$ fixed by
its operation, so moving a site moves its whole orbit rigidly, and
the force on the site is the sum of its images' forces carried back
through $W^\mathsf{T}$.

Three things follow at once:

- The {term}`space group` is preserved exactly, and for free: nothing
  checks that it was.
- An atom on a {term}`special position` stays on it.  The operations
  that map a site onto itself form its site-symmetry group, and the
  average of their Cartesian matrices is the projector onto the
  displacements they all leave alone; the step is projected onto it.
  A site on a three-fold axis moves along the axis; the oxygen of
  rutile moves along the [110] direction it is free in and nowhere
  else.  A site on a general position is projected onto everything,
  which is no projection at all.
- A structure already in P1 is the ordinary case: every atom free, no
  projection, no special path through the code.

:::{note}
A site is on a special position when its coordinates say it is, to
0.05 Å (`SPECIAL_POSITION_TOL`).  The optimiser's site projectors use
the same tolerance, so a site written a rounding place off its mirror
is treated as *on* the mirror and relaxed along it, rather than
walked off it and tripled.  Snapping a site exactly onto its position
is idealisation, which is what {ref}`Standardise cell <cmd-standardize>`
is for.
:::

:::{note}
A force field or optimiser never changes the bonding or the atoms.  It
reads the bonds the structure has and moves atoms and, if asked, the
cell; the bonds after a run are the bonds before it, and they are
recalculated only when you press
{ref}`Recalculate bonds <cmd-recompute_bonds>`.  A {term}`dummy atom`
(a centroid, a connection point) is held back at the door: the engine
is built over a structure without it, and it is shown with zero force.
:::

## Convergence, tolerances and units

A run is converged when the **largest force on any atom** is below the
force tolerance, 0.05 kcal/mol/Å by default -- loose enough to reach on
a framework, tight enough that the geometry has stopped moving
visibly.  The force is per atom, after the symmetry projection, and is
measured over the *atoms* only: when the cell is a variable too, its
convergence is a separate number, the residual stress in GPa
({doc}`cell`), and quietly folding the strain rows into |F|max would
make two runs of the same structure incomparable.

The step limit is 500.  It was 200, and two hundred stopped every
variable-cell relaxation of UiO-66 and ZIF-8 short with the atoms still
moving; *run it again* then restarted the optimiser's history from
nothing, which is why a cell took three runs.  A run that reaches the
limit is reported as *stopped without converging*, and the geometry is
wherever it got to.

No single step moves an atom further than 0.2 Å, whatever the
optimiser asks for.  A bad first guess -- two atoms almost on top of
each other, which happens whenever someone builds by hand -- gives a
force of tens of thousands, and without the cap the first step would
throw the atom out of the crystal.

## The optimisers

```{index} single: L-BFGS
```
```{index} single: FIRE
```
```{index} single: ABNR
```
```{index} single: quasi-Newton
```
```{index} single: conjugate gradient
```
```{index} single: steepest descent
```
```{index} single: Smart optimiser
```

Seven are offered, under the names `xtal optimize --method` takes.
All but FIRE share one loop: a *direction rule* proposes a direction,
the step is projected onto what the symmetry (and any constraint)
allows, and a backtracking line search along it accepts the first
length at which the energy has gone down enough.  A search that fails
is not the end of the run: the rule's memory is dropped and steepest
descent is tried once from the same point, and only if that cannot go
downhill either does the run stop -- and then it says so on its last
step (*the line search could not lower the energy from here, even
straight down the gradient -- the forces are finer than the energy can
resolve, or the tolerance is tighter than this engine can reach*).

`steepest_descent`
: Straight down the gradient, with a length that remembers: the length
  that worked last time is where the next search starts, grown a
  little, because a search that always accepts its first try is being
  too timid.

`conjugate_gradient`
: Polak--Ribière with the non-negative restart (PR+).  Each direction is
  the new gradient plus a share of the last direction, which is what
  stops steepest descent zig-zagging down a long valley.  The share is
  clipped at zero, and the history is dropped every $n$ steps or when
  the result stops pointing downhill.

`quasi_newton`
: BFGS with the whole inverse Hessian, built up one step at a time --
  what Materials Studio calls quasi-Newton.  Over the symmetry-reduced
  variables it is small for most crystals (MOF-5 in Fm-3m is seven
  sites and two strain rows), and holding all of it is what makes it
  faster than L-BFGS once near a minimum.  Above 6000 variables it is
  refused with a message saying to use L-BFGS, which reaches the same
  minimum without the matrix.

`lbfgs`
: L-BFGS {cite}`liu1989lbfgs`: the last ten steps stand in for the
  Hessian, applied by the two-loop recursion without the matrix ever
  being formed.  Curvature pairs that fail the $s \cdot y > 0$ test are
  dropped rather than stored, because keeping one makes the
  approximation indefinite and the next direction points uphill.  The
  command line's default.

`abnr`
: Adopted-basis Newton--Raphson, after CHARMM's
  {cite}`brooks1983charmm`: a Newton step in the small space the last
  few steps span, where the Hessian can be measured from how the
  gradient changed along them, plus a steepest-descent step for the
  part of the gradient that space does not reach.  Cheap per step like
  steepest descent and converging like Newton along the directions that
  matter, which is why Materials Studio hands it the middle of a
  minimisation.  A subspace curvature that is not positive is taken in
  magnitude and floored, so the step still goes downhill.

`fire`
: FIRE {cite}`bitzek2006fire`: molecular dynamics with the velocity
  steered towards the force and the time step grown while progress
  continues, thrown away the moment it stops.  Slower than L-BFGS near
  a minimum and far more forgiving a long way from one, which is what a
  hand-built structure needs.  FIRE has no line search; the step cap
  still applies.

`smart`
: **Steepest descent, then ABNR, then quasi-Newton, as the forces
  fall** -- each where it is best.  Steepest descent runs while |F|max
  is above 10 kcal/mol/Å and survives a structure with two atoms on top
  of each other that would send a Newton step anywhere; ABNR takes over
  down to 1 kcal/mol/Å and is quick through the middle; quasi-Newton
  finishes, or L-BFGS where there are too many variables for it.  It
  never goes back a stage: a force that rises again on the way down is
  a line search overshooting, not a structure that has become
  hand-built.  The Force Field panel's default, and the scan's, because
  every point after the first starts near a minimum but the first one
  may not.

Each optimiser is a generator that yields one step and waits, which is
what lets the panel draw the geometry as it moves, pause, and stop
without leaving a half-applied structure behind; the command line
prints a line per step from the same stream.

## Practical notes

- Run a **single point** first ({ref}`Single point energy
  <cmd-single_point>`).  Its per-term breakdown says which term a
  large energy lives in, and the Force Field panel's atom-type table
  says whether the typing that energy rests on is one to believe
  ({ref}`uff-typing`).  A deposited structure's forces are routinely
  large; the example below starts at 110 kcal/mol/Å.
- Leave the optimiser at **Smart** unless you have a reason: it is
  steepest descent when the structure is hand-built and quasi-Newton
  when it is nearly done.  Choose **FIRE** for a start so bad that a
  line search keeps failing, **L-BFGS** for a large P1 cell near its
  minimum.
- **Freeze the selected atoms** holds the selected sites still and
  relaxes everything else.  Freezing every site is refused (*Every
  site is selected, so freezing the selection would leave nothing to
  relax*).  To hold a *coordinate* -- a distance, an angle -- rather
  than atoms, use a scan ({doc}`scans`).
- A run that ends with *The optimiser stopped before converging -- the
  forces (…) still above the tolerance* has a geometry that is where it
  got to and not a minimum.  Press **Optimise** again to carry on: the
  optimiser's history starts afresh, but from that geometry.
- A relaxation under a force field finds *a* minimum near where it
  started.  Which one is a property of the starting geometry; the
  scan is the tool for asking about more than one ({doc}`scans`).

## Worked example: MOF-5 under UFF4MOF

The prepared primitive cell of MOF-5 (*File ▸ Open Sample ▸ Prepared
for simulation ▸* {ref}`MOF-5 <cmd-sample_prep_mof5>`: 106 atoms, P1,
at the experimental cell) relaxed with the command line's default
engine and optimiser, into a {term}`workspace`:

```console
$ xtal optimize resources/samples/prepared/MOF-5.cif --workspace ws -o MOF-5_opt.cif
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

step          energy            max force
    0  E =     1355.15520  |F|max =  110.00889
    1  E =     1193.22014  |F|max =   78.38898
    2  E =     1130.65477  |F|max =   40.67828
    3  E =     1068.65394  |F|max =   32.04739
    4  E =     1035.05197  |F|max =   17.70108
    5  E =     1032.62353  |F|max =    7.86926
    6  E =     1031.73670  |F|max =    2.73714
    7  E =     1031.53576  |F|max =    2.31381
    8  E =     1031.20889  |F|max =    1.57151
    9  E =     1031.18112  |F|max =    0.41027
   10  E =     1031.17713  |F|max =    0.15529
   11  E =     1031.17675  |F|max =    0.05161
   12  E =     1031.17668  |F|max =    0.04077

converged after 12 steps: -323.9785 kcal/mol to 1031.1767, |F|max 0.0408 kcal/mol/A
wrote ws/MOF-5/uff-optimise-001
wrote MOF-5_opt.cif
```

Twelve steps and under a second: the deposited geometry is a
refinement's, not a force field's, and it gives up 324 kcal/mol.  The
per-term breakdown at the end of the run's log reads torsion 646.8,
angle 300.1, van der Waals 61.3, bond 23.0 kcal/mol.  What the node's
bonds came out at, and how UFF4MOF's fitted zinc differs from UFF's,
is in {ref}`the UFF section <uff-uff4mof>`.

## What a run leaves in the workspace

```{index} single: workspace; run folder
```
```{index} single: run.log
```
```{index} single: trajectory.extxyz
```

Every run is filed under the structure it was run against, in a folder
named for the engine, the kind of run and a counter --
`MOF-5/uff-optimise-001/` above -- and the layout is the same whether
the run came from the panel or from `xtal optimize --workspace`, which
is what lets a run started from a script open in the window.  The
folder holds three files:

`run.log`
: The version, the structure, the engine and **every option it was
  given**; the full atom-type table with the confidence and the reason
  for each assignment (a wrong type gives a plausible number rather
  than an obvious error); the topology counts; the per-step lines; the
  verdict; and the per-term energy breakdown, largest first.  The
  {ref}`Log panel <panel-log_dock>` shows it, and follows it while the
  run goes; the run folder is in the
  {ref}`Workspace panel <panel-file_dock>` under its structure.

`trajectory.extxyz`
: One extended-XYZ frame per step of the P1 cell, with the step, the
  energy and the largest force on each frame's header line.  The
  {ref}`Trajectory panel <panel-trajectory_dock>` scrubs it against
  the open structure; while it plays, the atoms on screen are a frame
  and every editing command is greyed out, and *Adopt this frame*
  keeps a geometry as one undoable edit.

`final.cif`
: The relaxed structure.

A document with no workspace entry still runs; it just leaves nothing
behind, and the panel says so once.

## In the window

1. Open the panel with *Modules ▸ Forcefield ▸*
   {ref}`Force Field panel <cmd-show_ff>` ({ref}`panel-ff_dock`), and
   choose the engine and its options under **Model**; the atom-type
   table underneath is the typing the energy will rest on.
2. Under **Optimisation**, choose the **Optimiser** (Smart by
   default), the step limit and the force tolerance in kcal/mol/Å,
   and tick **Freeze the selected atoms** if some sites are to stay
   put.  **Relax the cell as well**, **Stress below** and **Pressure**
   are {doc}`the next section's <cell>`.
3. **Redraw** is how often the 3D view repaints while the run goes.
   Every step is announced in the plot and the status line whatever
   it says; on a large cell the repaint is the most expensive thing
   happening, so a long run is often best watched as the plot alone.
4. Press **Optimise** (or *Modules ▸ Forcefield ▸*
   {ref}`Optimise geometry <cmd-optimize>`, {kbd}`Ctrl+Shift+E`).  The
   structure moves in the view, the energy and largest force are
   plotted live, and the button becomes **Stop**; **Pause** holds the
   run between steps.
5. The report under the plot gives the summary line and the per-term
   breakdown, and the hint beneath it says what is still worth
   checking -- the sites whose type the typer is not sure of, or that
   the run stopped short.

:::{warning}
The whole run is one undo step: {kbd}`Ctrl+Z` gives back the
structure you started with, not the second-to-last iteration.  A
stopped run keeps the steps it finished rather than becoming a
failure: the panel says *stopped without converging* and leaves the
trace on screen.
:::

## Settings

The three Force Field entries are listed under
{ref}`Forcefield <mod-forcefield>`, the panel under
{ref}`Force Field <panel-ff_dock>`, and each engine's own options under
its name in the {ref}`engine reference <engine-uff>`.  On the command
line, `xtal optimize FILE` takes `--engine`, `-p name=value` for an
engine option, `--method` (one of the seven above; `lbfgs` when not
given), `--max-steps`, `--tolerance` in kcal/mol/Å, `--relax-cell`,
`--stress-tolerance` in GPa, `--pressure` in GPa, `--workspace DIR`,
`-o OUTPUT` and `-q` to print no line per step; `xtal optimize --help`
lists them.

% TODO(Sam): `xtal optimize --help` prints no help text and no default
% for --method (the default is lbfgs, from xtal/cli.py) or --max-steps;
% the panel's default optimiser is Smart.  Reported for the CLI.

## Limitations

- A relaxation finds a local minimum near its starting geometry and
  cannot tell you it is the lowest one.
- The energy, and so the geometry, is the engine's.  A cell relaxed
  under UFF is a UFF cell ({doc}`cell`), and the typing decides the
  answer before the optimiser starts ({ref}`uff-typing`).
- Quasi-Newton is refused above 6000 variables; Smart falls through
  to L-BFGS there on its own.
- A run that reaches the step limit, or whose line search cannot go
  downhill, stops with the geometry where it is; the message says
  which.
