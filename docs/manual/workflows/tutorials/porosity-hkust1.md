(tutorial-porosity-hkust1)=
# Tutorial: the porosity of HKUST-1

HKUST-1 is the framework every porosity code is first tried on: copper
paddlewheels joined by benzene-1,3,5-tricarboxylate into a cubic
cell, 26.3 Å on an edge, with two large cages and a smaller one.  In
this tutorial you measure its accessible surface area and pore volume
with the two *(faster)* entries, read the result, draw the pore
surface, then repeat the measurement with Zeo++ {cite}`willems2012zeopp`
to see what the pore diameters add and how far the two ways agree.
Without Zeo++ you can do the first half; the page says where the
second begins.

```{index} single: tutorial; porosity of HKUST-1
```

Open *File ▸ Open Sample ▸* {ref}`HKUST-1 <cmd-sample_hkust1>`: Fm-3m,
624 atoms in the cell, density 0.8791 g/cm{sup}`3`, volume
18 280.8 Å{sup}`3`.  The commands below use the same file as
`resources/samples/HKUST1.cif`.

## The surface area, from the grid

1. Choose *Modules ▸ Porosity ▸* {ref}`Surface area (faster)…
   <mod-zeopp-surface-area-grid>`.
2. The **Probe** is *Nitrogen*, 1.86 Å, the default, and the radii are
   Zeo++'s own table.  A BET area is a nitrogen area, so leave both.
   Leave *Points per atom* at 1000 and the *Grid spacing* at 0.4 Å.
3. Run it.  The {ref}`Results panel <panel-results_dock>` fills with
   the table; the run is filed under HKUST-1 in the workspace.

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
```

Read the **Channels** and **Pockets** rows before the number
({doc}`/porosity/grid`).  One channel, no pockets, and a
non-accessible area of zero: the nitrogen probe reaches every surface
the framework has.  The area is per gram of the framework, which is
what an isotherm is divided by, and per cubic centimetre, which is
what a storage target is.

## The pore volume

Choose *Modules ▸ Porosity ▸* {ref}`Accessible volume (faster)…
<mod-zeopp-volume-grid>` with the same probe:

```console
$ xtal run zeopp.volume-grid resources/samples/HKUST1.cif --workspace ws
accessible volume to Nitrogen (1.86 A), radii from Zeo++'s own table
0.770 cm^3/g (67.7% of the cell) to Nitrogen (1.86 A)

Accessible volume (POAV)          0.7701  cm^3/g
Accessible fraction of the cell    67.70  %
Accessible volume in the cell    12375.9  A^3
Non-accessible volume (PONAV)     0.0000  cm^3/g
Channels                               1
Pockets                                0
```

The *Probe-occupiable volume* box is ticked by default: a volume a
probe's centre can sit in, rather than the space the framework leaves.
The two entries take about a second each on the machine this was
written on.

**What to check: that the grid is fine enough.**  A grid has a
resolution.  Run both again with the spacing halved and look for
movement in the third figure:

| Grid spacing | surface area (m²/g) | pore volume (cm³/g) | fraction of cell |
|---|---|---|---|
| 0.4 Å (default) | 2151.6 | 0.7701 | 67.70 % |
| 0.25 Å | 2151 | 0.772 | 67.9 % |

The area moves by about a square metre per gram, as far as the
rounded line shows, and the volume by 0.2 % of the cell:
the grid has resolved this framework, whose windows are far wider
than the probe.  A *Resolution: borderline* row would mean the
opposite ({doc}`/porosity/grid` shows one on ZIF-8).

## Draw the pore surface

Both entries have **Draw the accessible surface** ticked, so the
surface is already in the viewport when the run ends: 189 312
triangles, one channel, on a 66×66×66 grid (the run's `run.log` says
so).  *View ▸ Show ▸* {ref}`Pore network <cmd-show_pores>` hides and
shows it, and the Style panel's **Pores** group has the same box
beside *Pore spheres*.  It is drawn over the *channels* only, because
the number is the channels' volume ({doc}`/porosity/pore-surface`);
the surface is not written into the project, since it is a second to
compute again.

## Where the grid stops: the cage diameters

The grid entries give an area and a volume.  They do not report the
diameters of the pores.  A diameter is a different question -- *how
big a sphere fits* -- and it can be read off the same grid by hand:
the largest distance from any grid point to the nearest atom surface
is the radius of the largest included sphere.

```python
from xtal.agent import Session
from xtal.analysis import grid, porosity
s = Session.open("resources/samples/HKUST1.cif")
f = grid.distance_grid(s.structure, porosity.zeo_radius, spacing=0.2)
n = f.shape[0]
print(2 * f.max(), 2 * f[0, 0, 0], 2 * f[n // 2, n // 2, n // 2])
```

```text
13.197 13.197 11.119
```

The largest sphere is 13.20 Å across and sits at the cell's corner;
the cage at the body centre is 11.12 Å.  These are what the next
section's Zeo++ run reports (13.19 and 11.11 Å), to the grid's
resolution.

## The Zeo++ entries

If Zeo++'s `network` binary is on `PATH`, or *Preferences ▸ Engines*
points at it, the four entries beside the grid ones are enabled;
without it they are greyed with the reason, and everything above stands
alone.  Run *Modules ▸ Porosity ▸* {ref}`Pore diameters and channels…
<mod-zeopp-diameters>`:

```console
$ xtal run zeopp.diameters resources/samples/HKUST1.cif --workspace ws
[...]
network finished in 72.8 s
D_i 13.192 A, D_f 6.668 A, D_if 13.186 A; 3D, crossable in any direction

Pore diameters and channels
Largest included sphere (D_i)                                   13.192  A
Largest free sphere (D_f)                                        6.668  A
Included sphere along free path (D_if)                          13.186  A
Channels                                                             1
Dimensionality                          3D, crossable in any direction
```

The three diameters, in the words of {doc}`/porosity/zeopp`: D_i is
the biggest cavity, 13.19 Å, the one the grid found; D_f is the
biggest sphere that can travel through the whole crystal, 6.67 Å,
which is what decides what the framework admits; D_if is the widest
the channel gets along that path.  The probe radius does not change
them; it changes which channels *count*, and here there is one, 3D.

Then *Surface area…* and *Accessible volume…* (the Zeo++ twins of the
two grid entries):

| Quantity | Zeo++ | grid (0.4 Å) | difference |
|---|---|---|---|
| accessible surface (m²/g) | 2170.5 | 2151.6 | grid 0.9 % lower |
| pore volume, POAV (cm³/g) | 0.7434 | 0.7701 | grid 0.027 cm³/g higher |
| fraction of the cell | 65.35 % | 67.70 % | grid 2.4 points higher |

The surface agrees to about 1 %.  The volume does not, by design: the
grid reads the union of probe spheres, Zeo++'s `-volpo` falls a little
short of it, and the grid page quotes up to 0.03 of the cell
({doc}`/porosity/grid`).  Zeo++ took 7.1 s for the area and 72.8 s for
the volume here; the grid took about a second for each.  When you
compare with a paper, say which you used.

## Draw the cavities

The Zeo++ run leaves a pore network on the document: its accessible
Voronoi nodes, each with the radius that fits there.  Open the **Style**
panel, **Pores** group:

1. **Pore spheres** draws the largest included sphere at its node.
2. **Pore sphere** chooses *By size*, *Along the free path (D_if)* or
   *Every node*.
3. **Cavity** lists the kinds of cavity widest first, and **Copy**
   chooses which copy of that kind is drawn, or *All*.

HKUST-1 has three kinds of cavity.  Read from the run's own network:

| Cavity | diameter (Å) | copies in the cell |
|---|---|---|
| first | 13.19 | 4 |
| second | 11.11 | 4 |
| third | 5.59 | 8 |

The widest sits at the corner and the three face centres, so it is
always drawn at the edge of the cell; choose the second, at the body
centre, to draw a sphere in the middle.  D_f has no sphere, because
Zeo++ reports the width of a bottleneck on an edge and no output says
where it is ({doc}`/porosity/zeopp`).

:::{note}
The pore network belongs to the arrangement it measured.  Move or
delete an atom and it is dropped; there is nothing to refit a Voronoi
decomposition to.  Run it again after an edit.
:::

## What to check

- One channel and no pockets, so no number is a volume nothing can
  reach.
- The grid answer does not move when the spacing is halved.
- D_i is the same from the grid and from Zeo++, to a hundredth of an
  ångström.
- The probe is the one the measurement you compare with used.

## Where this is explained

{doc}`/porosity/grid` for the grid entries and what the
*borderline* row means, {doc}`/porosity/zeopp` for the diameters and
the pore spheres, {doc}`/porosity/pore-surface` for the surface, and
{doc}`/porosity/index` for the chapter.
