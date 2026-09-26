# The Grid Entries

The two entries marked *(faster)* -- {ref}`Surface area (faster)…
<mod-zeopp-surface-area-grid>` and {ref}`Accessible volume (faster)…
<mod-zeopp-volume-grid>` -- read the same numbers off a distance grid
the application builds itself, in a second or two and with no binary
installed.  After this section you know how the grid is built, how it
tells a channel from a pocket and when it says it cannot, how the area
and the volume are read off it and how they compare with Zeo++, and
what a run on a shipped sample prints.

```{index} single: porosity; grid entries
```
```{index} single: distance grid
```
```{index} single: channel
```
```{index} single: pocket
```
```{index} single: probe-occupiable volume
```

## Why a second way to the same number

Zeo++'s `-volpo` took 68 to 108 s on every sample shipped with the
application; the grid gives MFU-4l's occupiable volume in about
1.5 s, grid and all.  iRASPA {cite}`dubbeldam2018iraspa` answers these
questions instantly because it reads all of them off a single grid,
and the application already builds that grid to draw the pore
surface ({doc}`pore-surface`).  So the two entries sit under their
Zeo++ twins in the *Porosity* module, produce the same report with a
note saying how the numbers were got, and stay enabled when the Zeo++
entries are greyed.

Zeo++ stays beside them because the grid has a resolution and a
Voronoi decomposition does not.  Where that matters the report says
so, and says which entry settles it.

## The distance grid

```{index} single: KD-tree
```

The grid is one scalar field sampled on a regular grid in fractional
coordinates: at each point, the distance to the *surface* of the
nearest atom,

$$
d(\mathbf{r}) = \min_i \bigl( |\mathbf{r} - \mathbf{r}_i| - R_i \bigr),
$$ (grid-field)

negative inside an atom.  Its zero set is the van der Waals surface;
its $r$ set is where the centre of a probe of radius $r$ can sit,
which is the boundary of the accessible volume Zeo++'s `-vol`
measures.  The radii $R_i$ are whichever table the run was given --
Zeo++'s own by default, transcribed for exactly this purpose
({doc}`zeopp`), or this application's van der Waals or covalent
radii, or a radii file, which the grid reads itself and in which an
element it does not name is refused rather than guessed.

It is built by a KD-tree (SciPy's `cKDTree`
{cite}`virtanen2020scipy`) over the atoms of the cell and of its 26
neighbouring cells, so the field wraps: index $n_a$ is index 0 of the
next cell and nothing has to be padded at the faces.  The number of
samples along each axis comes from the cell *lengths*, not the
volume, so an anisotropic cell is sampled evenly in space: a layered
structure with $c = 30$ Å and $a = 5$ Å gets six times as many planes
as rows.  The default **Grid spacing** is 0.4 Å, fine enough that a
3 Å window reads as a window rather than a staircase and coarse
enough that a 30 Å framework is under half a million points; the
field is single precision, because 10⁻⁷ of a distance on a 0.4 Å
grid is not something a surface can show.

The grid is the application's own for a reason recorded in the code:
Zeo++ 0.3 writes a distance grid two ways and neither could be used
-- `-gridGAI` aborts with *Need to resample in grid calc* on MFU-4l,
and `-gridG` ran for six minutes on the same file without writing
anything.

## Channels and pockets

The field says where a probe's centre can *sit*: everywhere
$d \ge r$.  It does not say where the probe can *go*.  A sealed cage
is as roomy as a channel and holds nothing an isotherm will ever put
there, so Zeo++ splits every number into the part a probe can reach
from outside (a **channel**) and the part it cannot (a **pocket**),
and the grid makes the same split.

**Two grid points are joined only if the probe can travel the
straight line between them.**  The code records why the simpler
rules were rejected: joining face neighbours alone closes windows
that are open -- HKUST-1 came out with 104 false pockets and UiO-66
with no channel at all -- and joining all 26 neighbours on the
strength of their endpoints steps diagonally past atoms: nitrogen
walked through ZIF-8's 3.27 Å windows, which it needs 3.72 Å to pass.
So the field is also asked at the segment's middle.  With both ends
and the middle clear, each half is a chord of at most half a grid
step, and a chord $c$ long dips into a sphere of radius $R$ by at
most

$$
\delta \le \frac{c^2}{8R},
$$ (grid-chord)

which is 0.005 Å for a 0.35 Å half-step and the smallest expanded
sphere there is -- well inside what the grid resolves anyway.  Only
segments whose ends are close to an atom are asked, because the field
is a distance and changes by at most 1 Å per Å.

**A channel is a component that meets its own periodic image.**  The
grid is labelled without wrapping, then the links across the cell's
faces join the labels in a union-find that carries each label's cell
offset; two paths to the same label with different offsets are a
path from a point to its own image one cell over.  That is what
percolating means, and it is the same test as Zeo++'s own channel
finder.

:::{note}
**A window the grid cannot see is flagged, not guessed.**  Where a
window is wider than the probe by less than a grid step, whether any
grid point falls in the gap is luck: UiO-66's windows clear nitrogen
by 0.045 Å on the radius, and the answer flips between a 0.4 Å and a
0.3 Å grid.  So the split is made again with the probe half a grid
step smaller, and if any pocket then opens the report puts a
*Resolution: borderline* row above the numbers: *a window is within
half a grid step (0.2 A) of the probe's size, so whether it is open
is a matter of the grid.  Pore diameters (Zeo++) settles it exactly.*
:::

## The numbers

```{index} single: accessible surface area
```

**Surface area** is sampled on the spheres, not measured off the
mesh.  The marched pore surface reads 2--3 % low on MOF-5, HKUST-1 and
MIL-53, because tetrahedra cut every sphere into flat chords; points
on the expanded spheres themselves -- which is how Zeo++ measures it
-- land within 1 %.  **Points per atom** (1000 by default) are a
Fibonacci spiral turned by a seeded rotation per atom, so they are
even over each sphere and the same seed gives the same answer.  A
point counts where no other expanded sphere covers it, and it is
channel or pocket area by the grid points around it.  The report's
own note says exactly this: *1000 points per atom on the spheres;
which of them a probe of 1.86 A reaches is decided on a 0.4 A grid.*

**Accessible volume** (AV) is the fraction of grid points in a
channel.  **Probe-occupiable volume** (POAV) adds every point a probe
sphere centred in a channel covers, and asks that of the grid points
with the field's own bound rather than the probe radius: around an
open point $a$ a ball of radius $d(a) - r$ is open too, so a probe
centred anywhere in it reaches $d(a)$ from $a$.  Asking only $r$
from the grid points ignored the open space between them and read
ZIF-8's cages 0.021 of the cell small.

:::{note}
**POAV reads higher than Zeo++'s `-volpo`, and it is tested against
the union of probe spheres, never against Zeo++.**  The measurements
in the code: MIL-53 0.659 against Zeo++'s 0.651, HKUST-1 0.677 against
0.654, UiO-66 0.456 against 0.430.  Probe spheres centred on a 0.15 Å
grid of open points -- every one a real probe position -- already
cover 0.663 and 0.679 of the first two, so the true volume is at
least that, and the grid's number sits just under it, as a union of
real spheres must.  The shortfall is Zeo++'s, by up to 0.03 of the
cell, and the report says so under the table.
:::

Against Zeo++ on the shipped samples, where the grid resolves the
windows: surface area within 1 %, AV within 0.0035 of the cell, POAV
above Zeo++'s by up to 0.026.

## Worked example: HKUST-1 and ZIF-8

The shipped HKUST-1 (*File ▸ Open Sample ▸* {ref}`HKUST-1
<cmd-sample_hkust1>`; Fm-3m, 624 atoms in the cell), from the command
line with a workspace to file the run in.  The surface area to
nitrogen, 0.8 s wall time:

```console
$ xtal run zeopp.surface-area-grid resources/samples/HKUST1.cif --workspace ws
surface area to Nitrogen (1.86 A), radii from Zeo++'s own table
2152 m^2/g accessible (1891 m^2/cm^3) to Nitrogen (1.86 A)

Surface area to Nitrogen (1.86 A)

Accessible surface area (ASA)        2151.6  m^2/g
Accessible, per volume               1891.4  m^2/cm^3
Accessible, in the cell              3457.7  A^2
Non-accessible surface area (NASA)      0.0  m^2/g
Channels                                  1
Pockets                                   0
Density                              0.8791  g/cm^3
Cell volume                         18280.8  A^3

1000 points per atom on the spheres; which of them a probe of 1.86 A reaches is decided on a 0.4 A grid.

radii from Zeo++'s own table
run folder: ws/HKUST1/zeopp-surface-area-grid-001
```

The occupiable volume, 0.9 s:

```console
$ xtal run zeopp.volume-grid resources/samples/HKUST1.cif --workspace ws
accessible volume to Nitrogen (1.86 A), radii from Zeo++'s own table
0.770 cm^3/g (67.7% of the cell) to Nitrogen (1.86 A)

Accessible volume to Nitrogen (1.86 A)

Accessible volume (POAV)          0.7701  cm^3/g
Accessible fraction of the cell    67.70  %
Accessible volume in the cell    12375.9  A^3
Non-accessible volume (PONAV)     0.0000  cm^3/g
Channels                               1
Pockets                                0
Density                           0.8791  g/cm^3
Cell volume                      18280.8  A^3

The fraction of a 0.4 A grid at a probe radius of 1.86 A.  This reads up to 0.03 of the cell above Zeo++'s -volpo: probe spheres centred on real probe positions cover at least this much, so the shortfall is Zeo++'s.

radii from Zeo++'s own table
run folder: ws/HKUST1/zeopp-volume-grid-002
```

The run's `run.log` records the grid and what was drawn: *1 channel,
0 pockets on a 66x66x66 grid* and *an accessible surface of 189312
triangles at a 1.86 A probe around 1 channel, 0 pockets, on a
66x66x66 grid*.

ZIF-8 (*File ▸ Open Sample ▸* {ref}`ZIF-8 <cmd-sample_zif8>`; 102 atoms
in P1) is where the probe decides the answer.  To nitrogen the whole
void is one pocket -- no channel, so the accessible volume is zero and
the volume is all non-accessible:

```console
$ xtal run zeopp.volume-grid resources/samples/ZIF-8.cif --workspace ws
accessible volume to Nitrogen (1.86 A), radii from Zeo++'s own table
0.000 cm^3/g (0.0% of the cell) to Nitrogen (1.86 A)
[...]
Accessible volume (POAV)         0.0000  cm^3/g
Accessible fraction of the cell    0.00  %
Accessible volume in the cell       0.0  A^3
Non-accessible volume (PONAV)    0.6938  cm^3/g
Channels                              0
Pockets                               1
[...]
```

To hydrogen (1.48 Å) the same void is one channel:

```console
$ xtal run zeopp.volume-grid resources/samples/ZIF-8.cif -p gas=h2 --workspace ws
accessible volume to Hydrogen (1.48 A), radii from Zeo++'s own table
0.722 cm^3/g (58.0% of the cell) to Hydrogen (1.48 A)
[...]
Accessible volume (POAV)         0.7215  cm^3/g
Accessible fraction of the cell   57.96  %
Accessible volume in the cell    1434.3  A^3
Non-accessible volume (PONAV)    0.0000  cm^3/g
Channels                              1
Pockets                               0
[...]
```

And a 1.60 Å probe, near the window's size, is the case the grid
flags rather than decides:

```console
$ xtal run zeopp.volume-grid resources/samples/ZIF-8.cif -p gas=custom -p probe_radius=1.6 --workspace ws
accessible volume to a 1.60 A probe, radii from Zeo++'s own table
0.000 cm^3/g (0.0% of the cell) to a 1.60 A probe

Accessible volume to a 1.60 A probe

Resolution                       borderline
Accessible volume (POAV)             0.0000  cm^3/g
Accessible fraction of the cell        0.00  %
Accessible volume in the cell           0.0  A^3
Non-accessible volume (PONAV)        0.7162  cm^3/g
Channels                                  0
Pockets                                   1
[...]
```

Its log adds *a window is within half a grid step of the probe's size
on the 37x37x37 grid, so whether the drawn surface passes through it
is a matter of resolution*, and *nothing to draw: every void is a
pocket the probe cannot reach*.  Whether that window is open to a
1.60 Å probe is a question for *Pore diameters and channels…*, which
has the exact decomposition.

## Practical notes

- Choose the probe for the measurement you are comparing with, not
  for the framework: a BET area is nitrogen's, and ZIF-8 above is
  either sealed or two thirds empty depending on the probe.
- Read the *Channels* and *Pockets* rows before the number.  A
  volume that is all non-accessible is a volume no experiment will
  find.
- A *Resolution: borderline* row means the answer depends on the
  grid.  A finer **Grid spacing** may settle it; Zeo++'s pore
  diameters settle it exactly.
- The same run draws the pore surface when **Draw the accessible
  surface** is on ({doc}`pore-surface`).  On the *Accessible volume
  (faster)…* entry the surface and the numbers come off one grid.

## Settings

{ref}`Surface area (faster)… <mod-zeopp-surface-area-grid>` and
{ref}`Accessible volume (faster)… <mod-zeopp-volume-grid>` in the
generated reference.  In place of Zeo++'s accuracy switch and channel
radius they take a **Grid spacing**; the probe and the radii settings
are the Zeo++ entries' own.  From the command line they are
`xtal run zeopp.surface-area-grid` and `xtal run zeopp.volume-grid`.

## Limitations

- The grid has a resolution.  A window within half a grid step of the
  probe's size is flagged, and the exact answer is Zeo++'s.
- The two entries give the surface area and the volume.  The three
  pore diameters, the channel dimensionality and the pore size
  distribution are Zeo++'s alone.
- POAV is deliberately not matched to Zeo++'s `-volpo`, which falls
  short of the union of probe spheres; the two will differ by up to
  0.03 of the cell on the same structure.
- Surface area from points on the spheres agrees with Zeo++ to within
  1 % on the shipped samples at 1000 points per atom; a different
  radii table changes both.
- A partially occupied site is refused exactly as the Zeo++ entries
  refuse it.
