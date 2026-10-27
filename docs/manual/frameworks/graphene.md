(frameworks-graphene)=
# The graphene builder

The graphene builder lays out honeycomb sheets {cite}`novoselov2004electric`:
one layer of graphene or hexagonal boron nitride, or several stacked
the way graphite stacks.  After this section you can choose the
layers, their stacking and spacing, build bulk graphite or a slab,
and pick the cell a calculation wants.

```{index} single: graphene; builder
```
```{index} single: graphite; stacking
```
```{index} single: boron nitride; hexagonal (h-BN)
```

## Building one

1. Open *Modules ▸ Carbon builder ▸*
   {ref}`Graphene… <cmd-module.graphene.build>`.
2. Choose **Element A** and **Element B**: C and C is graphene, B and
   N hexagonal boron nitride.  Every bond joins an A to a B.
3. Set **Layers** and, for more than one, the **Stacking**:
   - **AA** puts every atom over an atom of the layer below.
   - **AB** (Bernal) shifts every other layer by one bond, so half the
     atoms sit over a hexagon's centre: graphite's own stacking
     {cite}`bernal1924structure`.
   - **ABC** shifts each layer by one bond more than the last:
     rhombohedral graphite.
   - **AA′** is AA with the two elements swapped on every other
     layer, boron over nitrogen: h-BN's stacking.  It needs two
     different elements.
4. Choose the **Stack**:
   - **Bulk** is periodic along *c*, with no gap but the layer
     spacing: graphite itself.  The stacking repeats along *c*, so the
     layer count must be a whole number of its period -- 2 for AB and
     AA′, 3 for ABC -- and any other is refused, naming the counts
     that work.
   - **Slab** is the layers with **Vacuum** above the top one, for a
     sheet alone or a surface.
5. Press **Run**.  The sheets open in a new tab, in {term}`P1`, with
   their bonds stated, so nothing is perceived.  No bond joins two
   layers.

**Layer spacing**, left empty, is graphite's 3.35 Å, or h-BN's 3.33 Å
for boron and nitrogen.  **Bond length**, left empty, is the two
elements' aromatic bond from Pyykkö's covalent radii: 1.42 Å for C--C,
1.47 Å for B--N.

## The cell

The sheet's own cell is hexagonal, two atoms a layer, with *a* = √3
bonds and γ = 120°.  **Rectangular cell** gives the orthogonal one
instead, *a* by √3 *a* with four atoms a layer: *a* runs along the
zigzag direction and *b* along the armchair one, which is the cell a
ribbon or a strain along one direction wants.  **Repeat along a** and
**Repeat along b** repeat whichever cell it is.

## Reading the report

The report gives the cell (*a*, *b*, *c*, γ), the atoms a layer, the
bond and the layer spacing with where each came from, and the
**Closest contact** -- the shortest distance between two atoms that
are neither bonded nor share a neighbour, which in a stack is the
layer spacing.  In the two-atom cell every atom is a neighbour of its
own images, so there is nothing to measure and the row says so;
repeat the cell to see it.
