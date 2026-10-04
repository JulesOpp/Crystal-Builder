(porosity-refinement)=
# Refining against a measured pattern

The refinement workbench takes a measured powder pattern and a
structure and answers the questions that lead from one to the other:
where are the lines, what cell explains them, does that cell and space
group fit the whole pattern, and do the atoms of your model fit it,
alone or together with a force field.  After this section you can open
a pattern from a diffractometer's own file, work through those steps,
read the parameter table that holds every number a fit starts from,
use an energy beside the pattern, and know what a finished fit
changes in your document and what it never does.

```{index} single: refinement workbench
```
```{index} single: Rietveld refinement
```
```{index} single: Pawley fit
```
```{index} single: Le Bail
```
```{index} single: indexing
```
```{index} single: RietX
```

The {doc}`PXRD page <pxrd>` *calculates* a pattern from a structure and
lays a measured one over it for comparison.  It does not subtract,
fit or refine; this page is where that starts.

## What does the physics

**The fitting is RietX's.**  RietX {cite}`wu2026rietx`, an open-source
Python package, fits the peak profiles, searches for the cell,
refines, and reads the diffractometers' file formats; Crystal Builder
is what a structure of this application, a pattern and a radiation look
like to it, and what comes back.  It is the optional **`refine`
extra**, pinned below the next minor release because its API is young,
and it is bundled in the packaged application, which refines rutile
inside the build as a self-test.  Without it the entries are greyed and
the tooltip names the install command; the calculated pattern of the
previous page never needs it.

The methods are the standard ones: the Rietveld method
{cite}`rietveld1969`; the Pawley {cite}`pawley1981` and Le Bail
{cite}`lebail1988` whole-pattern fits, in which a cell and space group
fit the pattern with every reflection's intensity free; refinement in
the order McCusker and co-workers recommend {cite}`mccusker1999`; and
March--Dollase preferred orientation {cite}`dollase1986`.  The names of
the numbers (`zero_error`, `Specimen_Displacement`, `CS_L`, `bkg`) are
TOPAS's wherever there is one, so the dialogs read like an input you
may already know.

## Opening a pattern

Open the workbench with *Modules ▸ PXRD ▸* {ref}`Refine against a
measured pattern… <cmd-refine_workbench>`, over the tab in front, and
**Load pattern…**.  It reads:

- **Two columns of text** -- 2θ and counts, one pair a line (`.xy`,
  `.xye`, `.dat`) -- with our own lenient reader: comments, blank
  lines, commas and a header are not errors, and a third column is
  taken as each point's error when every row has one.
- **A diffractometer's own file**: Rigaku `.rasx` and `.ras`, Bruker
  `.raw`, `.brml` and `.uxd`, PANalytical `.xrdml` and `.udf`, Philips
  `.rd` and `.sd`.  RietX reads these, so they open only with the
  `refine` extra.  Where a file holds several scans the first is taken
  and the notes say so (*scan 0 of 3*).
- **Radiation**, from a list: Cu, Mo or Co with Kα1 and Kα2 (a
  laboratory tube) or Kα1 alone (a monochromated one), or a
  synchrotron with its wavelength, which only then has a box.
  A *Monochromator 2θ* changes the polarisation correction (26.6 for
  graphite (002) with Cu).  **A file that names another anode than the
  radiation box is said, never switched**: the cell is only as right
  as the wavelength.

The pattern is drawn in counts, with the calculated curve over it, the
difference below, and a strip of tick marks for the reflections.
Hovering a tick names the reflection -- `(1 1 0)  27.43°  d 3.249 Å`,
every reflection within a few pixels listed together, because
coincident lines are exactly the ones you cannot tell apart by eye.
The traces are updated and not redrawn, so a live refinement does not
reset your zoom.

## The steps

The list on the left runs in the order a refinement goes.  Each step is
an entry of the PXRD module ({ref}`Fit peaks <mod-pxrd-peaks>`,
{ref}`Index <mod-pxrd-index>`, and so on) that runs on the same worker,
into the same kind of run folder and with the same Stop as any module;
what the workbench adds is that a step's answer stays where the next
step reads it.

Peaks
: *Find peaks* fits every resolvable line in its own window over a
  background envelope: position, area, width, shape and an esd.
  *Refine peaks* then fits the whole range at once under a Chebyshev
  background of the order you give.  Lines are listed in a table you
  can untick, edit by hand (a position, an area, a width) or add to at
  a typed 2θ; the ones in use are what indexing is handed.  Options
  look for shoulders, flag lines where a strong line's Kβ or a
  tungsten-contaminated tube would put one (off by default: a filtered
  tube has none, and the flag would take real ones out), and a *Fit
  only at* list.

Index
: Which unit cells explain the lines.  RietX runs three search engines
  that fail differently, and their agreement is the confidence.  You
  choose which of the fourteen Bravais lattices to search, optionally
  which space groups, a zero-error allowance, the largest volume and
  the longest axis, and a **time budget** (off to start with).  **There
  is no winner unless RietX names one**: the best cell is shown only
  when the engines and the figures of merit agree and the pattern could
  validate it, and every row carries its confidence and the reasons it
  is not higher.  A **space group is a list of classes, never one
  group**: a powder pattern shows the extinction symbol, groups sharing
  one differ only by elements that produce no absences, so a selection
  filters classes.

Pawley / Le Bail
: One cell and space group fitted to the whole range, every
  reflection's intensity a free number (Pawley, with esds) or
  re-partitioned from the observed pattern between cycles (Le Bail,
  cheaper over a long range, no intensity esds).  Zero error and
  specimen displacement, size and strain broadening, and the cell
  numbers the group leaves free are the choices; the form shows the
  free numbers only and derives the rest, so a tetragonal *a = b* is
  never typed twice.  The result is the R factors, the refined cell
  with esds and the reflection list.  **A wider range is not a better
  cell**: every reflection is one more free intensity, and a
  framework's reflections crowd with angle.  On a 14 × 17 Å cell, 4-30°
  was 35 reflections and a second; 4-60° was 199 and more than two
  minutes, and its cell came out further off.  **Apply cell to the
  structure** writes the refined cell onto the structure as one undo
  step (refused when the structure does not fit it), and **New structure
  from this cell** starts an empty one in that cell and group, filed in
  the workspace.

Rietveld
: The structure's own atoms fitted to the whole pattern.  Atoms move
  along each site's allowed directions only -- a site on a special
  position stays on it -- with displacement parameters, optionally
  occupancies, and March--Dollase texture about an axis.  A **Plan**
  chooses what is freed and in what order: the Refine flags of the
  parameter table (below), or one of RietX's own plans, which ignore
  the flags.  The run is watched: its frames move the atoms and redraw
  the calculated curve as it goes.

With energy
: Rietveld and a force field at once, described in its own section.

Pareto
: A sweep of With energy over a list of weights.

Automatic
: Peaks, indexing and a Pawley fit of every leading cell in every
  leading space-group class, ranked in a table, one fit per (cell,
  class), each in a run folder of its own so that a row opens the fit
  it was ranked by.  **A fit RietX refuses is a row with its reason**,
  never a missing row.  It stops at the table unless *Continue to
  Rietveld* is ticked, and then goes on only when the open structure
  is the crystal the table found -- its cell within 1 % and 1° of a
  row's and no class the pattern refutes holding its space group --
  and says which test failed otherwise: a cell 3 % off is a different
  compound more often than a thermal expansion, and atoms refined
  against the wrong pattern converge to a plausible wrong answer.

:::{note}
**From a cell to a structure.**  The workbench finds a cell and space
group that match a pattern.  It does not solve a structure from it
(charge flipping is not part of this application).  The path the
application supports is to build models for that cell and group --
the MOF builder's net search by coordination and space-group number
({doc}`/frameworks/nets`), with your linker and the unit you expect --
and test each against the pattern, refined here or compared by
{doc}`its simulated pattern <pxrd>`.
:::

## The parameter table

Every fitting step starts from **one `ParameterSet`**, shown as one
table (TOPAS's input file as a table) and moved into whichever fitting
step is in front: switching from Pawley to Rietveld shows the same U,
V, W and background, which is the check to make before trusting a run.
Each row has a value, an esd once a fit has given one, and a **Refine**
box; a group's box turns the whole group on or off.  The groups are in
McCusker's order -- scale, background, line positions, peak shape,
sample broadening, preferred orientation, atoms -- and **that is the
order they are freed in**.  The Refine column replaced the old "Refine
…" boxes, so there is one answer to what is refined, not two.

- **Reset Parameters** puts every number back to RietX's preset for
  the radiation and pattern shown.
- A finished fit hands its set back, with its esds, and the rows it
  moved are marked for a moment.  The set is kept between runs: a
  Pawley fit's peak shape is no longer thrown away before the Rietveld
  step, and With energy no longer refits the scale, background and
  profile from nothing where nobody could see it.  Until a run or you
  have changed it, a new pattern or radiation rebuilds it from RietX's
  preset.
- **An atom's Biso and occupancy are the structure's**, shown here and
  editable, but typing one is an edit of the site: one undo step on the
  Document, never a second copy that could drift from it.
- **A held row is shown greyed and never edited**: a tie (a cubic *b*
  follows *a*), a number the plan locks, an atom with no free
  direction.  What RietX holds is read off its own table.
- **Copy** writes the set as text, one row a line, and **Paste** reads it
  back; the format is the same as a parameters file:

```text
zero_error 0.0011987 ± 0.00030 Refine
sample_displacement 0 NoRefine
Ti1_xyz Refine
```

A Pawley fit takes and gives back no scale and no atoms -- its
scaffold's dummy atom has a structure's first atom's paths -- so the
scale, texture and atom groups are hidden on that step and kept for
Rietveld.

## Zero cycles is an evaluation

**Max iterations 0 fits nothing.**  RietX refuses `max_iter=0`, so a
zero is read as an *evaluation*: the pattern is calculated at the
parameters as they stand, the R values and RietX's own statistics are
reported, nothing moves, no esds are produced, and **no undo step** is
pushed.  A Pawley evaluation still finds its intensities.  It is the
way to ask how well a model that you set up by hand, or a parameters
file, already agrees with a pattern:

```console
$ xtal run pxrd.rietveld rutile.cif -p xy=rutile-measured.xy -p radiation=cu-ka1 -p max_iterations=0
Rietveld fit of 2 sites
Rietveld Rwp 11411.05 %, GoF 1392.83 (0 cycles: evaluated at the values shown)
[...]
Rwp 11411.05 %   Rp 2573.30 %   Rexp 8.19 %   GoF 1392.826.  a 4.5937   b 4.5937   c 2.9587   α 90   β 90   γ 90.  the furthest atom moved 0.000 Å.  0 cycles: evaluated at the values shown  Rwp = 11411.1% — this is a mismatch between the model and the data, not a converged refinement; [...]
```

(The pattern here is a synthetic one: the calculated pattern of rutile
from {ref}`Simulate a pattern… <mod-pxrd-simulate>`, scaled to counts,
with a sloping background and Poisson noise added.  Its scale was
never fitted, which is what the first Rwp says.)  **Max iterations**
and **Tolerance** are every stage's; with energy they are L-BFGS's.

## A worked example from the command line

Every step is also a module action: `pxrd.peaks`, `pxrd.refine_peaks`,
`pxrd.index`, `pxrd.pawley`, `pxrd.auto`, `pxrd.rietveld`,
`pxrd.energy` and `pxrd.pareto`, each taking the pattern as `-p
xy=FILE` and the structure as its file.  The same fit, converged:

```console
$ xtal run pxrd.rietveld rutile.cif --workspace ws -p xy=rutile-measured.xy -p radiation=cu-ka1
Rietveld fit of 2 sites
Rietveld Rwp 8.31 %, GoF 1.02; the furthest atom moved 0.046 Å
[...]
Refined (23)
Parameter                                Value        esd
phases.0.cell.a                              4.59326  0.00041
phases.0.cell.c                              2.95851  0.00019
phases.0.scale                            0.00556211  0.00016
phases.0.atoms.1.x                          0.297707   0.0016
[...]
instrument.background.c0                      126.92     0.35
[...]
Rwp 8.31 %   Rp 6.42 %   Rexp 8.17 %   GoF 1.016.  a 4.5933(4)   c 2.95851(19)  [...]
phases.0.atoms.0.biso refined to its bound  [...]  1.7 effective observations per structural parameter (5.0 from 5 measured reflections, against 3 free) — the guideline is at least 3 and preferably 5
run folder: ws/TiO2/pxrd-rietveld-002
```

This is a demonstration of the machinery on a pattern with five
reflections, not of what a refinement of a real material looks like.
The notes at the end are RietX's and are the part to read: a parameter
refined to its bound, pairs of correlated parameters (U, V and W of the
peak shape here, at ρ = −0.999), and the number of effective
observations against the free structural parameters, whose guideline
is at least 3 and preferably 5.  A refinement that is under it is a
model with too many numbers for its data, and says so.

The run folder holds the structure and the files that say what was
done:

`refined.cif`, `fit.xy`
: The refined structure and the observed, calculated and difference
  curves.

`parameters-start.txt`, `parameters.txt`
: The set the run was handed and the set it gave back, in the text
  form above.  Giving one back to a later run -- `-p
  parameters=parameters.txt` -- starts from it, with *its* flags as the
  plan.  Without it, `xtal run` turns the boxes (`background`,
  `positions`, `biso`, ...) into flags, as the window's table does.

`rietx/`
: RietX's own record of the run.  **Every fit is told its run folder,
  never the working directory**: RietX otherwise writes `./.rietx/runs`
  wherever the process was started from, which might be your home
  folder or inside the application bundle.

`run.log`
: The choices and the notes, as for any module.

## Rietveld with energy

With energy fits the atoms to the pattern and to a force field at once.
The objective is one number with a weight in it,

$$
f = (1 - w)\,\frac{\chi^2}{\chi^2_0} + w\,\frac{E - E_0}{\Delta E},
$$ (refinement-energy)

where $\chi^2_0$ and $E_0$ are the pattern's misfit and the energy
where the run starts, and $\Delta E$ is how far the energy falls when
the atoms answer to it alone -- one force-field relaxation at the same
cell, which is the $w = 1$ end.  Both terms are then of order one,
so a weight means the same on rutile and on a framework of a thousand
atoms, and 0.5 is an even split rather than whichever term has the
larger units.  Weight 0 is the pattern alone and 1 the force field
alone.

- **The minimiser is ours**: L-BFGS over RietX's own variables -- each
  atom a step along the directions its site allows, and the cell's free
  numbers when the cell is let move.  RietX has no cost term of anyone
  else's, so the pattern's gradient is its analytic Jacobian and the
  energy's is the engine's forces carried back over each orbit; a test
  holds the pattern's gradient against finite differences.
- **The engine is the Force Field panel's.**  The workbench's *Engine*
  box shares that panel's model and choice, so choosing in either
  chooses in both, and the engine's options stay in the panel (there
  is an *Options…* button to open them over the workbench).  The engine is read,
  never configured, as a {doc}`scan </structure/scans>` reads it; its
  markers are held back at the door.  See {doc}`/energy/index` for the
  engines.
- **What the table flags beyond the atoms is fitted first and then
  held**: the scale, background, zero and peak shape are the pattern's,
  fitted with the atoms and the cell where they are before the atoms
  are asked to answer to anything.  With none of them flagged there is
  no first fit, and the atoms start against the numbers the table
  shows.
- **The cell is held by default**: a cell that moves under an energy is
  a different experiment.  *Let the cell move* refines the cell's free
  numbers with the atoms against both terms, and the energy's pull on
  them is the engine's stress.
- A refinement moves atoms and **never adds, removes or bonds them**:
  the refined structure has the same sites and the same bonds, and
  dummy atoms are markers that never go to RietX and come back where
  they were.

### Pareto sweeps

The right weight is not obvious, so **Pareto** minimises the one
problem at a list of weights (0, 0.05, 0.1 ... 1 by default, denser
near 0 where a little energy changes the answer most) and shows Rwp
and the energy against the weight and against each other -- the front.

- The scale, background and profile are fitted once, so every point is
  scored against the same pattern parameters; fitting them again at
  each point would put each point on an objective of its own, and a
  front of points from different objectives is not a front.
- Each point starts from its neighbour, walked upwards from 0, except
  $w = 1$, which is the relaxation that sets the energy's scale and is
  finished first.  **A point is written as it finishes**, so a stopped
  or crashed sweep leaves every point it reached.
- **A point that did not converge has no numbers** -- a hole, never
  plotted -- because a hole drawn as a number is a point on the front
  that is not there.
- The **knee** is a suggestion: the front point furthest from the chord
  between the front's two ends, where the curve bends most.  **Use this
  weight** puts the knee's weight into With energy.  A front of fewer than three
  points has none.  A point clicked on either plot chooses its row and
  draws its fit over the pattern; A point can be opened as a tab of the
  main window, as a scan's can, and **Show in Results** draws the front
  in the Results panel.
- A sweep returns no structure.  It moves the atoms as it runs and
  puts them back.

## What a finished fit does to your document

**A refinement moves atoms; its live frames are previews and its
finish is one undo step on the document the window was opened over**,
never the tab in front.  Frames go through `Document.preview_positions`
-- no history, no modified flag -- and a finished fit puts the atoms
back where they started and then commits the refined structure, so
Ctrl+Z undoes the whole run.  **Stop**, or a failure, puts them back and
commits nothing.  A workbench opened with no structure files its runs
under an entry named after the pattern, made the first time it runs.

Every fit reached is kept in the **History** page with its R factors
and how far the atoms moved, and **Restore this configuration**
returns the document to the one you choose -- a list of the structures
you have refined, which you can walk back along.

:::{warning}
**A refinement is evidence about a model, not about a material.**
The R factors say how well *this* model fits *this* pattern.  A model
with too many free numbers for its data fits well and means little,
which is what the effective-observations note is for.  A refinement
that is run against the wrong cell converges to a plausible wrong
answer, which is why *Automatic* will not continue into Rietveld unless
the structure is the crystal the table found.
:::

## Practical notes

- Fit the peaks first and look at the table: a line you would not
  index from is better unticked than hidden in a fit.
- Indexing does better without the weak, overlapped high-angle lines:
  set the 2θ range, which the later steps follow until you change theirs.
- Free zero error *or* specimen displacement, not both, unless the range
  is wide: they are strongly correlated with each other and with the
  cell.
- Start a Rietveld fit with the cell and atoms held and free what
  McCusker's order frees later; the default plan does this for you.
- For a framework refined without its disordered solvent, or with
  partial occupancies, the intensities need not be right while the
  positions are; {doc}`Prepare for simulation </structure/prepare>`
  makes the model whole first.

## Settings

Every step's parameters, with ranges and defaults, are in the
generated reference: {ref}`Fit peaks <mod-pxrd-peaks>`, {ref}`Refine
peaks <mod-pxrd-refine_peaks>`, {ref}`Index <mod-pxrd-index>`,
{ref}`Pawley <mod-pxrd-pawley>`, {ref}`Automatic <mod-pxrd-auto>`,
{ref}`Rietveld <mod-pxrd-rietveld>`, {ref}`Rietveld with energy
<mod-pxrd-energy>` and {ref}`Pareto <mod-pxrd-pareto>`.

## Limitations

- Needs the `refine` extra (RietX, below 1.6).  The powder tests run
  locally rather than in CI, because they take minutes.
- A structure is not solved from a pattern: the workbench finds the
  cell, and refines a model you provide.
- The cell's esds are RietX's and nothing wider.  A Bragg--Brentano
  cell also carries a systematic error of order 10⁻⁴ that no esd
  reports, and the fit's notes say so when RietX does.
- Preferred orientation is a single March--Dollase axis.
