(frameworks-carbon)=
# The disordered-carbon builder

The carbon builder makes a zeolite-templated carbon or a schwarzite:
one connected, curved sheet of carbon that follows a net, cut into
ribbons and terminated at its edges, in a cell whose size is solved
from the density you ask for.  After this section you can build one
from a recipe, read the ring counts it reports and know why they are
partly decided before any randomness, and know what the builder does
and does not claim about the material.

```{index} single: carbon builder
```
```{index} single: zeolite-templated carbon (ZTC)
```
```{index} single: schwarzite
```
```{index} single: Stone-Wales defect
```
```{index} single: Gauss-Bonnet
```

## What it does

A {term}`zeolite-templated carbon <ZTC>` is made by filling a
zeolite's pores with carbon and dissolving the zeolite away; what is
left is a thin carbon sheet that lined the pores, and it is
three-dimensionally connected because the pores were.  A
{term}`schwarzite` is the idealised version: a periodic negatively
curved surface of three-coordinate carbon.  Neither is a crystal in
the ordinary sense, and a model made of separate plausible fragments
is a model of a material nobody can make, so the builder is organised
around the one property that matters: **the carbon is a single graph
that runs through the cell in all three directions.**

The route is the one fullerenes and schwarzites have always been
described by:

1. **A net, and a surface round it.**  You name a three-periodic net
   from the RCSR {cite}`okeeffe2008rcsr` -- `dia` is the net of the
   supercages of faujasite (FAU), which a ZTC made in faujasite
   follows, and `srs` is a gyroid schwarzite's -- and repeat it, by
   default 2 × 2 × 2.  Each vertex is moved at random (*Node jitter*)
   and each edge bowed (*Edge bow*), and a smooth closed sheet is laid
   round the struts at the radius you set as a share of the edge's
   length.  The sheet is a level set of a sum of Gaussians placed along
   the edges rather than a distance to the nearest edge, because a
   distance has a crease wherever two edges are equally near, which is
   at every node, and a crease is a row of carbons bent through a
   corner.
2. **A triangle mesh, remeshed and given defects.**  The surface is
   triangulated evenly at 2.46 Å, and Stone--Wales defects
   {cite}`stone1986` are made on it as edge flips: four hexagons
   become a 5-7-7-5 group.
3. **Ribbons.**  A closed sheet is all carbon; a ZTC is not -- four
   carbons in ten of the example material are on an edge.  The sheet is
   cut by keeping the triangles within a half-width of a **path** along
   each strut, a seeded, meandering shortest path between anchors that
   all the struts meeting at a node share.  Because the ribbons follow
   the net's own connectivity, the kept carbon percolates exactly as
   the net does, which a cut by a random score did not manage until
   more than half the sheet was kept.
4. **The dual is the carbon.**  Every triangle becomes a carbon at its
   middle and every edge two triangles share becomes a bond.  A vertex
   of valence *n* becomes an *n*-membered ring, so the rings are decided
   on the mesh and the carbon only reads them off.  Where the sheet was
   cut a carbon has two neighbours: an edge carbon, which is where
   terminations go.  Only the largest piece is kept, and it must run on
   through all three pairs of cell faces or the build is refused.
5. **Terminated and relaxed.**  Edge carbons are given hydrogen,
   fluorine, hydroxyl, carbonyl or a ring-ether oxygen in the ratios
   you ask for; edge carbons beyond what the ratios ask for stay bare.
   The result is relaxed with UFF at the solved cell.

:::{note}
**A carbon build is one connected sheet with stated bonds.**  The
bond graph is the dual's, written as the structure's stored graph the
way a MOF build's is ({doc}`mof-builder`); nothing is perceived.  A
curved sheet has carbons closer across a pore than a bond in places,
and perceiving it would bond them.  *Recalculate bonds* is still how
you ask for distance instead.
:::

## The rings are partly decided before anything is random

On a closed sheet the sum of (6 − *n*) over all rings is six times
the sheet's Euler characteristic χ (Gauss--Bonnet).  For a sheet
round a periodic net, χ is twice the net's *V* − *E* per cell, so the
net alone says how many more heptagons than pentagons the sheet must
have, whatever the seed: one cell of `dia` needs 96 more
heptagon-equivalents than pentagons.  The Stone--Wales pairs are added
on top of that.  This is why the recipe sets **Stone--Wales pairs per
100 rings** and not a free five : six : seven ratio, and why the
dialog says what is fixed.

A ring is read here as Franzblau's primitive ring
{cite}`franzblau1991`, the same one *Style ▸ Rings* draws, so the
ring histogram the report prints is the one you can colour in the
view.

## Building one

1. Open *Modules ▸ Disordered carbon builder ▸*
   {ref}`Build a disordered carbon… <cmd-module.carbon.build>`.
2. Choose the **Net** and the **Repeat**, then the **Carbon density**
   in g/cm³ of framework carbon, terminations left out.  The cell is
   not an input: it is **solved** so that the carbon kept is exactly
   this density, which is why a larger *Strut radius / edge* gives a
   larger cell at the same density rather than a denser one.
3. **Sheet kept** is the share of the closed sheet kept as ribbons: 1
   is a closed schwarzite with no edges, lower is narrower ribbons with
   more edge carbon, which is where the terminations go.  **Layers**
   stacks one to three sheets round each strut, 3.35 Å apart, never
   bonded to each other; each must percolate on its own.
4. Set the **terminations** per carbon -- H/C, F/C, O/C -- and how the
   oxygen is shared among a ring ether, a hydroxyl and a carbonyl.
5. **Seed**: the same seed and recipe build the same carbon, atom for
   atom.  Another seed is another draw of the disorder.
6. Press **Run**.  The structure opens in a tab of its own, in
   {term}`P1`, with its bonds stated and a report in the Results panel.
   *Stop* is honoured between steps, including during the relaxation.

The defaults aim at one example material -- `dia`, 2 × 2 × 2, 0.42
g/cm³, H/C 0.07, F/C 0.29, O/C 0.044 and a sheet coverage of 0.38 -- and
match its density, ring ratios, hexagon share and pore-size peak.
Treat them as one worked recipe, not as what a carbon of your own is.

From the command line the same entry is `xtal run carbon.build`, and
it builds, so it takes no file.  One cell of `dia` at the default
density, small enough to see the shape of the answer in a few seconds:

```console
$ xtal run carbon.build -p repeat=1 -o ztc.cif
edge carbons 43%, 15 left bare
rings 4: 1, 5: 7, 6: 43, 7: 27, 8: 4
sheet chi -16 per layer: sum(6 - n) = -96 on the closed sheet, 4 Stone-Wales pairs added
1 piece(s), percolating in 3 directions
closest non-bonded contact 2.29 A
UFF at the solved cell: 300 steps, not converged, max force 1.82 kcal/mol/A
disordered carbon on dia: 420 atoms, 0.419 g/cm3 of carbon

Disordered carbon on dia

What was built
Net                dia x 1x1x1
Cell               24.24 x 24.24 x 24.24  A
Net edge                           10.55  A
Carbon density                     0.419  g/cm3
Atoms                                420
H/C                                0.070
F/C                                0.291
O/C                                0.043
Edge carbons                          43  %
Bare edge carbons                     15
Pieces                                 1
Percolates in      3 directions
Closest contact                     2.29  A
[...]
wrote ztc.cif
```

## What the report says

What was built
: The net and repeat, the cell and the net's edge length, the carbon
  density reached (0.419 against the 0.42 asked: the count is integral),
  the atom count, the H/C, F/C and O/C actually achieved, the share of
  edge carbons, and how many were left bare.  **A ratio the edge has
  too few carbons for is filled as far as it goes, and said.**

Topology
: Χ per layer, the sum of (6 − ring size) the closed sheet had to have,
  and how many Stone--Wales pairs were added.

Rings
: A histogram of ring sizes.  The net fixes the balance of pentagons
  and heptagons; the Stone--Wales pairs and the cut vary it around
  that.

Pieces and percolation
: **One piece, percolating in three directions** per layer.  A recipe
  whose ribbons do not run through the cell is refused, not built: raise
  *Sheet kept* or the density.

Closest contact
: The shortest distance between two atoms that are neither bonded nor
  share a neighbour -- what a sheet folded onto itself, or two layers
  too close, would show.

The relaxation line says whether UFF converged.  In the run above it
did not in 300 steps; the carbon is as built plus those steps, and a
polish with a better engine is the Force Field panel's job, applied to
the tab it opened in.

## Practical notes

- **Mind the size.**  2 × 2 × 2 of `dia` is about 2500 carbons, and a
  larger repeat is both a less periodic carbon and a slower build.
  The size is estimated before anything is made, from one solved
  cell, and cheaply.  Over the soft
  limit of the *Large structures* setting (10 000 atoms under
  Standard) you are asked; over the hard one (30 000) the build is
  refused with the largest repeat that fits.
- **Memory is why the builder is careful.**  The field is summed in
  blocks, a Newton step onto the sheet is capped at 0.5 Å, and a
  remesh that would make more than four times the triangles the
  sheet's area needs stops with an error instead of taking the
  machine with it.
- **The sheet needs room.**  The innermost sheet must be at least
  2.5 Å from its edge, which bounds *Strut radius / edge* below.
- Seeds differ in detail but not in the ring balance, which the net
  fixes.

## Settings

The parameters are listed under {ref}`Build a disordered carbon…
<mod-carbon-build>` in the generated reference, and the module is
{ref}`Disordered carbon builder <mod-carbon>`.

## Limitations

- **It is a model with the right statistics, not a reconstruction.**
  The recipe reproduces the numbers it was tuned against (density,
  ring shares, termination ratios, pore size) for one material; that a
  different recipe gives a realistic carbon of another material is not
  something it shows.
- The geometry is UFF at a fixed cell.  The bond lengths come out
  near 1.43 Å only once the relaxation has converged; the cell is
  never relaxed, because the density is the input.
- Terminations are placed where there is room, per kind, in a seeded
  order; the chemistry of an edge is the ratios you gave, not a
  prediction of one.
- A layer net is refused: a sheet round it cannot percolate in three
  directions.
