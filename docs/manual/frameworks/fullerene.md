(frameworks-fullerene)=
# The fullerene builder

The fullerene builder closes a cage of three-coordinate atoms with
twelve pentagons and the rest hexagons {cite}`kroto1985c60`: C60's
truncated icosahedron, C70's rugby ball, or any of the isomers in
between.  After this section you can pick a cage by its formula and
isomer, build one the table does not hold from its face spiral, and
read the report.

```{index} single: fullerene; builder
```
```{index} single: fullerene; face spiral
```
```{index} single: fullerene; isolated pentagon rule (IPR)
```

## Sizes and isomers

Every fullerene has exactly twelve pentagons: Euler's formula fixes
them, whatever the size.  Where they go is the isomer.  C60 has 1812
ways to place them, and only one keeps every pentagon surrounded by
hexagons -- the **isolated pentagon rule** (IPR) that the cages people
isolate obey.

The builder ships a table of isomers:

- **every isomer from C20 to C40** (C40 has forty), and
- **every IPR isomer from C60 to C100** (C100 has 450).

An isomer is numbered in the order of its spiral, the numbering of
Fowler and Manolopoulos's *Atlas of Fullerenes*; from C60 the numbers
count the IPR isomers only, so C76's isomer 2 is its second IPR cage,
the Td one.

## Building one

1. Open *Modules ▸ Carbon builder ▸*
   {ref}`Fullerene… <cmd-module.fullerene.build>`.
2. Set the **Size**.  The **Isomer** list fills with the size's
   isomers, each named by its point group where it was checked by hand
   and by the order of its group otherwise.  **Default** is the cage
   the formula usually means: C60-Ih, C70-D5h, C76-D2, C80-Ih, C84-D2.
3. Choose the **Element**.  A cage takes one: a pentagon is an odd
   ring, so two elements cannot alternate round it as boron and
   nitrogen do on a sheet, and the builder refuses two.
4. Tick **Hydrogen on every atom** for the fully hydrogenated cage,
   C60H60, each hydrogen pointing out at UFF's sp3 X--H length.
5. Press **Build**.  The cage opens in a new tab, alone in a cubic
   box, in {term}`P1`, with its bonds stated, so nothing is perceived.

**Spiral** builds a cage the table does not hold.  A fullerene is
peeled off face by face in one continuous spiral, and the twelve
places the pentagons fall in it name the cage: C60-Ih is
`1 7 9 11 13 15 18 20 22 24 26 32`.  Type the twelve numbers and the
size; the isomer list greys, since the spiral is the cage.  A spiral
that does not close into a cage is refused before anything is built,
saying at which face it failed.

**Bond length**, left empty, is the element's from Pyykkö's covalent
radii: aromatic for a bare cage (1.42 Å for carbon) and single for a
hydrogenated one (1.50 Å).

## How the atoms are placed

The spiral gives the graph and nothing else.  The atoms are put on a
closed surface by its **topological coordinates**
{cite}`manolopoulos1992molecular`: the three eigenvectors of the
adjacency matrix just below the largest each have one nodal plane, so
read as *x*, *y* and *z* they place the atoms round a sphere in the
graph's own order.  Springs then even out the bonds, and **Relax**
(UFF in a fixed box, by default) relaxes the cage over its stated
bonds.

UFF types every carbon of a bare cage as aromatic, so its bonds come
out nearly equal, 1.40--1.42 Å, where C60's real bonds alternate 1.40
and 1.45 Å; the report says so.  For the bond alternation, relax the
cage again with DFTB+ or an ML potential in the Force Field panel.

## Reading the report

**Spiral** is the cage's canonical spiral: of every spiral the cage
has, the one whose pentagons come earliest.  **Point group** gives the
order of the cage's symmetry group, reflections included -- 120 for
C60-Ih -- counted as the number of starting points that give that
same spiral.  **Isolated pentagons** says how many bonds two pentagons
share when it is not an IPR cage.  **Closest contact** is the shortest
distance between two atoms that are neither bonded nor share a
neighbour.
