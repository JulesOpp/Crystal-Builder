# Porosity with Zeo++

The *Porosity* module asks Zeo++ {cite}`willems2012zeopp` the four
questions a porous-materials paper has to answer: how big the pores
are, how much surface a gas molecule sees, how much room there is for
it, and how the pore sizes are spread.  After this section you know
what each entry measures and in which units, why the probe and the
atom radii decide every number, what the pore network drawn over the
crystal shows and what it deliberately does not, and where the run's
files go.

```{index} single: Zeo++
```
```{index} single: porosity; Zeo++
```
```{index} single: largest included sphere
```
```{index} single: largest free sphere
```
```{index} single: probe radius
```

## What Zeo++ measures

Zeo++ takes a box of atoms with a radius each and builds the Voronoi
decomposition of the space between them: the network of points and
segments that are as far as possible from the nearest atom surfaces.
Every question below is read off that network, and the application
runs the `network` binary with the same decomposition for all of
them.  The input is written by the application itself as a
{term}`P1` box of explicit atoms (a CSSR file), so that Zeo++'s own
CIF reader, which has its own ideas about symmetry operators,
occupancies and labels, never interprets the crystal.

### Pore diameters and channels

{ref}`Pore diameters and channels… <mod-zeopp-diameters>` is Zeo++'s
`-res` and `-chan`.  It reports three diameters, in Å, which the
application labels in the table exactly as its code defines them:

- **D_i, the largest included sphere**: the biggest cavity in the
  crystal, reachable or not.
- **D_f, the largest free sphere**: the biggest sphere that can pass
  all the way through -- what decides what the framework will admit.
  It is always the smallest of the three.
- **D_if, the included sphere along the free path**: the widest point
  of the channel D_f squeezes through.

The three diameters do not depend on the probe: `-res` measures the
crystal.  What the probe decides is which pore networks *count* as
reachable, and that is what the two rows under the diameters say --
the number of **channels** a probe of that size can reach from
outside, and their **dimensionality**: *1D, along one axis*, *2D, a
layer of channels*, or *3D, crossable in any direction*.  A framework
whose channels differ is listed channel by channel rather than
averaged, because an average would describe none of them.  `-chan` is
run every time, since the decomposition is already paid for and the
dimensionality is a number no other Zeo++ output carries.

### Surface area

{ref}`Surface area… <mod-zeopp-surface-area>` is `-sa`: the area a
probe of the chosen radius can touch, sampled by Monte Carlo points on
each atom's sphere (**Samples per atom**, 2000 by default).  It is
reported in m²/g, m²/cm³ and Å² per cell, split into the
**accessible** area (ASA), which belongs to channels connected to the
outside, and the **non-accessible** area (NASA), which belongs to
pockets.  A nitrogen probe is the default because a BET measurement
sees nitrogen, and the accessible half is the one an isotherm can
reproduce.

### Accessible volume

{ref}`Accessible volume… <mod-zeopp-volume>` is `-vol` or `-volpo`,
by the **Probe-occupiable volume** switch.  `-vol` reports the volume
the probe's *centre* can reach (AV); `-volpo` reports the volume the
probe *occupies* (POAV), which is always the larger and is what a
paper means by pore volume.  The switch is on by default for that
reason.  Both are reported in cm³/g, as a fraction of the cell and in
Å³, again split into accessible and non-accessible halves.  Zeo++
writes no channel and pocket counts from `-volpo`, so those rows are
absent from an occupiable run rather than zero.

### Pore size distribution

{ref}`Pore size distribution… <mod-zeopp-psd>` is `-psd`: a
histogram of how much of the pore space sits at each diameter, in
0.1 Å bins.  Zeo++ writes four columns; the application draws the two
that matter -- the count of sample points in each bin, which is the
histogram, and minus the slope of the cumulative distribution, which
is the pore size distribution as a paper plots it -- and shows only
the window of bins that have anything in them.  It defaults to a
1.2 Å probe rather than a gas, because a small probe resolves narrow
pores and a large one sees only what it fits into.  Its **Samples**
setting is the one that decides how long it takes: 20 000 is minutes
on a framework and enough to see the shape; the published figures use
50 000.

## The probe and the radii

```{index} single: radii table; Zeo++
```

**A radius quoted without the probe it was measured with means
nothing**, so the probe is a named gas with its radius in the label:
nitrogen 1.86 Å, argon 1.72 Å, carbon dioxide 1.65 Å, hydrogen
1.48 Å, helium 1.30 Å, methane 1.86 Å, or *Use the radius below*.  The
radii are half the kinetic diameter (nitrogen's 3.72 Å halves to the
1.86 Å a BET area is measured with).  The **Channel radius** is the
size that decides which channels count as reachable; zero means *the
same as the probe*, which is what makes the answer the one the probe
would measure.

**Every number Zeo++ returns is a function of how big it thinks the
atoms are.**  The **Atom radii** setting chooses between Zeo++'s own
table, this application's van der Waals radii and its covalent radii,
and whichever is chosen is written into the log and into the report
(*radii from Zeo++'s own table*).  Zeo++'s table is the default
because it is what the numbers in the Zeo++ papers were computed
with.  It is compiled into the binary and written nowhere it could be
read back, so the application carries a transcription of it,
`porosity.ZEO_RADII` -- the reason is the picture, below, which has
to be drawn with the radii the numbers were computed with -- and a
test checks the transcription against Zeo++'s source, so an upgrade
that changed a radius would fail rather than drift.  A **Radii file**
of your own, two columns of element and radius in Å, overrides the
choice.

**High accuracy** is Zeo++'s `-ha`, on by default: extra Voronoi
vertices so that atoms of different radii are treated properly, at
the price of a slower run.

:::{warning}
A partially occupied site is refused, not averaged.  Zeo++ has no way
to express half an atom; handed one it returns a confident number for
a crystal that does not exist.  So a structure with
{term}`occupancy` below one is stopped before the run folder is
opened, with the sites named: *resolve the disorder first, by
deleting the minor components or by choosing one of them* -- which is
what {doc}`Prepare for simulation </structure/prepare>` does.
:::

## What the view draws

```{index} single: pore network
```

With **Draw the pore network** on, *Pore diameters and channels…*
also runs Zeo++'s `-visVoro` over the decomposition it has already
paid for, and reads back the *accessible* half of what it writes: the
Voronoi nodes a probe can reach, each with the radius of the sphere
that fits at it, and the segments joining them.  The whole diagram
and the unreachable pockets are left out, because a node a probe
cannot reach is not a pore, and the full diagram over a framework is
a picture of the algorithm rather than of the crystal.

:::{note}
**The view shows where the pores are, and does not pretend to know
where D_f is.**  The largest *included* sphere is drawn at its node
exactly -- twice its radius is the D_i in the table beside it.  D_f is
the width of a bottleneck on an *edge*, and no Zeo++ output carries
edge radii, so what is drawn for it is the path the free sphere
travels along, and the report says so under the table: *Where D_f
sits is not something Zeo++ reports: it is the width of a bottleneck
along a channel, and no output carries it.*  Drawing a ball at a
plausible-looking constriction would be inventing a measurement.
:::

One sphere is drawn and not every node: a framework's accessible
network is hundreds of nodes in one cell and thousands across a
display range, and a translucent ball at each would hide the crystal
it is about.  The rest of the pore space is the skeleton, thin enough
to see through.  *View ▸ Show ▸* {ref}`Pore network <cmd-show_pores>`
hides and shows the whole drawing.

The network lives on the document beside the planes, and it follows
four rules:

- It is put there by the run, not by an edit: it is not on the undo
  stack and does not mark the file modified, because finding out
  where the pores are changes nothing.
- It is saved into the project's {term}`session` and comes back when
  the project is opened.
- It is **dropped the moment the arrangement it measured changes** --
  an atom moved, added or deleted -- because a Voronoi decomposition
  belongs to one arrangement of one set of atoms and there is nothing
  to refit it to.  A change that only alters how the crystal is drawn
  or named leaves it alone.
- It goes to the document the run was *started from*, never the tab
  in front: a pore network over the wrong crystal is a plausible
  picture of channels that are not there.

A run whose drawing could not be read is not a failed run.  The
diameters are already read and correct; the log says what was
missing and the numbers stand.

## Running it

1. Open the structure and choose the entry from *Modules ▸ Porosity*,
   or from the {ref}`Modules panel <panel-modules_dock>`.  If the four
   Zeo++ entries are greyed, the tooltip is the reason: *Zeo++ is not
   installed, or not on PATH (XTAL_ZEOPP is not set).  It is at
   https://www.zeoplusplus.org/*.  The binary is `network`; point
   *Preferences ▸ Engines* at it, or put it on `PATH`, or set
   `XTAL_ZEOPP`.  The two *(faster)* entries need no binary and stay
   enabled ({doc}`grid`).
2. Choose the probe, the radii table and the entry's own settings.
3. The report appears in the {ref}`Results panel <panel-results_dock>`
   with the probe and the radii named on it, and the run's files --
   the CSSR input, Zeo++'s output files and `run.log` -- in a folder
   under the structure's entry in the {term}`workspace`.  A run with
   no workspace still answers, into a temporary directory the status
   line says was not kept.

Zeo++ prints tens of thousands of lines of housekeeping; they all go
to the log, and only the lines that say what stage the run has
reached go to the status bar.

## Worked example: HKUST-1 from the command line

The same four entries run from the `xtal` command line, against the
shipped HKUST-1 (*File ▸ Open Sample ▸*
{ref}`HKUST-1 <cmd-sample_hkust1>`; Fm-3m, 624 atoms in the cell):

```console
$ xtal run zeopp.diameters resources/samples/HKUST1.cif --workspace ws
```

On the machine this manual was written on Zeo++ is not installed, and
the command answers with the application's own sentence:

```console
error: Zeo++ is not installed, or not on PATH (XTAL_ZEOPP is not set).  It is at https://www.zeoplusplus.org/
```

% TODO(Sam): with the `network` binary installed, run
%   xtal run zeopp.diameters resources/samples/HKUST1.cif --workspace ws
%   xtal run zeopp.surface-area resources/samples/HKUST1.cif --workspace ws
%   xtal run zeopp.volume resources/samples/HKUST1.cif --workspace ws
% and paste the three reports here: the diameters table with its
% channels and dimensionality rows, the ASA/NASA table and the POAV
% table.  The grid page has the same structure's surface area and
% volume off the grid, for the side-by-side the module is built for.

Until then, the *(faster)* twins on the next page give HKUST-1's
surface area and pore volume without the binary, in the same tables.

## Settings

Every entry's settings, with what each accepts and its default, are
in the generated reference: {ref}`Pore diameters and channels…
<mod-zeopp-diameters>`, {ref}`Surface area… <mod-zeopp-surface-area>`,
{ref}`Accessible volume… <mod-zeopp-volume>` and {ref}`Pore size
distribution… <mod-zeopp-psd>`.  The module's registry key is
`zeopp`, so a run folder is named `zeopp-<entry>-NNN` and the command
line is `xtal run zeopp.<entry>`; `xtal modules` lists the entries
and their parameters.

## Limitations

- The four Zeo++ entries need the `network` binary; without it they
  are greyed with the reason, and the *(faster)* entries are what
  runs.
- A partially occupied site is refused rather than averaged (above).
- The drawn network is the accessible Voronoi network at the probe's
  radius: the largest included sphere and the channels' skeleton.
  Where D_f sits is not drawn, because Zeo++ does not report it.
- The network is a measurement of one arrangement of atoms and is
  dropped when that arrangement changes; run the entry again.
- The pore surface that *Accessible volume…* can draw is not Zeo++'s:
  it is computed here, at the same probe and radii, and is described
  in {doc}`pore-surface`.
