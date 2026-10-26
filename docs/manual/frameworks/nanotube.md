(frameworks-nanotube)=
# The nanotube builder

The nanotube builder rolls a honeycomb sheet into a single-walled
tube from its roll-up vector (*n*,*m*), periodic along *c* or cut to
a finite piece.  After this section you can choose the indices and
ends for the calculation you mean to run, build a boron nitride tube,
and read the report.

```{index} single: nanotube; builder
```
```{index} single: nanotube; chirality (n,m)
```
```{index} single: boron nitride nanotube
```

## What (*n*,*m*) means

The sheet is rolled so that *n* **a**₁ + *m* **a**₂ goes once round
the tube {cite}`dresselhaus1995physics`; its length over π is the
diameter.  (*n*,*n*) is **armchair**, (*n*,0) **zigzag**, and
anything else **chiral**: with *m* ≤ *n* the chiral angle runs from
0° (zigzag) to 30° (armchair).  (*m*,*n*) is the mirror image of
(*n*,*m*), the same tube in the other hand, and the report's
*Chirality* row says so.

## Building one

1. Open *Modules ▸ Nanotube builder ▸*
   {ref}`Build a nanotube… <cmd-module.nanotube.build>`.
2. Type **n** and **m**, then choose the **Ends**:
   - **Periodic** is an infinite tube along *c*, for DFTB+ or a
     force field.  **Length** is rounded to whole periods, and a
     chiral tube's period can be long: (6,5)'s is 40.6 Å.
   - **Finite, ends capped with H** is a molecule-like piece: each
     two-coordinate edge atom gets a hydrogen at UFF's own X–H
     length.
   - **Finite, bare ends** leaves the edge atoms two-coordinate, for
     ends of your own.
3. Press **Run**.  The tube opens in a new tab, in {term}`P1`, with
   its bonds stated, so nothing is perceived.

**Vacuum** is the gap to the tube's periodic image, atom to atom:
across, and along a finite tube, caps included.

:::{figure} /figures/frameworks/nanotube-form.png
:name: fig-frameworks-nanotube-form
:width: 60%

The nanotube builder at its defaults: a periodic (10,10) carbon tube.
:::

:::{figure} /figures/frameworks/nanotube-tubes.png
:name: fig-frameworks-nanotube-tubes
:width: 80%

A (10,10) tube 25 Å long with its ends capped with H, seen along *a*.
:::

## Boron nitride

Set **Element A** to B and **Element B** to N.  The bond stays
1.42 Å unless you change it; h-BN's own is 1.446 Å
{cite}`paszkowicz2002lattice`, and the report's note says so.

## Reading the report

The table gives the diameter, chiral angle, period |T|, length,
composition and hydrogens.  *Shortest bond* is the shortest chord
rolling made; over 3 % compression, a note asks you to relax first.

*Electronic character* is the textbook rule and changes nothing
built: armchair is metallic, (*n* − *m*) divisible by 3 small-gap
{cite}`hamada1992new,saito1992electronic,kane1997size`, the rest
semiconducting, and every BN tube a wide-gap semiconductor
{cite}`rubio1994theory`.  Under 7 Å across, the row adds that the
rule is unreliable {cite}`blase1994hybridization`.

```console
$ xtal run nanotube.build -p n=6 -p m=5 -p length=40 -o tube.cif
[...]
Diameter                                     7.47  A
Chiral angle                                27.00  deg
Period |T|                                 40.638  A
Atoms per period                              364
[...]
Electronic character  semiconducting
wrote tube.cif
```

## Limitations

- **Too thin is refused**: when rolling crushes a bond below 90 %,
  or brings two unbonded atoms within bonding distance.  (2,0) is
  refused; (3,0) is built, with the note.
- Over the hard limit of the *Large structures* setting (200 000
  atoms under Standard) the build is refused, naming the longest
  tube that fits.
- Single-walled only, with no fullerene caps, defects or doping.
  Nothing is relaxed: that is the
  {ref}`Force Field panel <panel-ff_dock>`'s job.

The settings are under {ref}`Build a nanotube… <mod-nanotube-build>`.
