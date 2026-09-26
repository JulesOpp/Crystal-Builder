# The MOF builder

The MOF builder puts a building block on every vertex and every edge
of a named net and hands back a framework with its net already drawn.
After this section you can pick a topology and the blocks that fit it,
read the builder's verdict and its results table, know which way round
its nodes were turned and why, run the same build from the command
line, and find what it left in your workspace.

```{index} single: MOF builder
```
```{index} single: PORMAKE
```
```{index} single: framework; building
```

## What it is

The builder is PORMAKE {cite}`lee2021pormake`, a program that
assembles a framework from a topology and a set of building blocks by
placing each block on the slot of the net whose coordination number
it matches, scaling the net's cell so that the blocks meet, and
fusing the blocks' connection points.  Crystal Builder ships PORMAKE
**vendored and trimmed**: its code and its database of nets and
blocks are inside the application, with the two large dependencies it
barely used (a gradient from `jax` and one call into `pymatgen`)
replaced by a few lines over the numerical libraries already present.
For you that means three things:

- there is nothing to install or configure -- the packaged application
  builds frameworks as it comes, and a source install needs only the
  `ase` extra, which the menu entry names when it is missing (*The MOF
  builder needs ase -- ... pip install -e ".[ase]"*);
- the database is PORMAKE's own: its 3-periodic nets and its 867
  building blocks, read from files rather than through PORMAKE, so the
  picker lists them without loading the builder;
- a build is **not bit-identical** to one from an installed upstream
  PORMAKE.  The replaced gradient is evaluated in double precision
  where upstream's ran in single, so the two land on slightly
  different points of the same minimum.  The application's own tests
  compare a build against upstream by composition, fit and net rather
  than by coordinates.

The database is described in `xtal/mof/pormake/PROVENANCE.md`, which
lists every difference from upstream 0.2.3.

The dialog is *Modules ▸ MOF builder ▸*
{ref}`Build a framework… <cmd-module.mof.build>`.  It does not need a
structure open: what it makes is a new document.

## Topologies and building blocks

```{index} single: topology; choosing
```
```{index} single: building block; picking
```

A **topology** is a net from the RCSR {cite}`okeeffe2008rcsr`, and the
picker's list is the union of two sources: the nets in PORMAKE's
database, all of them periodic in three directions, and the RCSR's
own 2-periodic nets, which the application writes flat for PORMAKE to
build on (see {doc}`layers`).  The **3D** and **2D** boxes above the
list show how many of each there are and hide one kind or the other;
the fields beside them search by name, coordination, group number and
transitivity, and are described with the Net builder in
{ref}`net-search`, because both use the same search.

Choosing a topology draws a few cells of it on the right, with one
colour per kind of vertex, and describes it: *hcb p6mm, 2 vertices and
3 edges in the cell, node 1: 3-connected, 1 kind(s) of edge*.  Under
**Building blocks** one row appears per **slot** the net has -- one
for each kind of node, and one for each kind of edge, named for the
node types it joins (*Node 1, 6-connected*; *Linker at node 1*).  A
node type is a `NODE` line of the net's file, in the file's order,
which is also PORMAKE's numbering; a kind of edge is a pair of node
types, worked out by expanding the net when it is picked.

Each row offers only the blocks that fit it.  **A block fits a slot
when it has as many {term}`connection points <connection point>` as
the slot is coordinated, and nothing else fits it at all**: a
6-connected slot takes a 6-connected block.  The row says how many fit
(*81 block(s) fit* for a 3-connected node) and draws the chosen one
beside it, connection points as open rings.  The search box above the
rows narrows every row at once, by name (`N59`) or by composition --
`6C 4N 3Zn` asks for exactly those counts, a bare `Zn` only that zinc
be present, and every word in the box must hold.  The
**Monodentate** and **Polydentate** boxes split the blocks by whether
any connection point stands for more than one atom (a chelate, as in
MFU-4l or Ni{sub}`3`(HITP){sub}`2`); all of PORMAKE's are
monodentate, and the counts say before you click whether the other
kind is worth asking for.  **Draw…** on a row sketches a new block for
that slot, checked against its coordination as you type; see
{doc}`blocks`.

A linker slot may be left empty.  Then the nodes are joined directly,
which is what PORMAKE builds for a net with no linker in it.

## How a block fits a slot

```{index} single: building block; fitting a slot
```

PORMAKE places a block by turning it so that its connection directions
lie along the slot's -- a best-fit rotation of one set of vectors onto
another {cite}`kabsch1976` -- and reports how far the fitted
connection points are from where the net wanted them as an **RMSD**
per block.  The net's cell is then scaled so that neighbouring blocks'
connection points coincide, which is the **cell relaxation** in the
results table.  Where two blocks meet, their two connection points are
fused into one **joint** and the atoms they stood for are bonded.

:::{note}
**A joint is as many bonds as its two ends have members.**  A
connection point may stand for one atom or for several (a chelate's
two nitrogens), and every atom at either end of a joint arrives
bonded, paired across the joint by distance.  PORMAKE itself writes
one bond per joint and which atom it keeps is an accident, so the
application enumerates the joints itself: MFU-4l on **pcu** has 12
joints where PORMAKE's file would give it 6.  These bonds are stored
as your own, so they survive {ref}`Recalculate bonds
<cmd-recompute_bonds>` however long they are; everything *inside* a
block was perceived from its geometry.
:::

A symmetric node fits its slot equally well in many ways -- an
octahedral node in 24 -- and which one PORMAKE takes is whichever its
search reached first.  **Node orientation** under *How it is built*
decides what is done about that:

Consistent across every joint
: The default.  Each node is turned, among the ways that fit equally
  well, so that the faces at the two ends of every linker agree --
  carboxylate against carboxylate, chelate against chelate -- and only
  where that is measurably better than what the fit chose.  It is what
  builds MOF-5 with its clusters alternating.

As found by the fit
: Whatever the fit reached first, exactly as PORMAKE builds it.  Choose
  it to reproduce an upstream PORMAKE build.

{doc}`orientation` explains the rule; the short version is that it
never makes a block fit worse and never moves the cell.  Independent
of that choice, every two-connected block is turned about its own axis
after the build until its ends face the blocks they meet, because the
fit leaves that angle undetermined rather than deciding it.

The other settings under *How it is built* are **Repeat the net**
(tile the net before anything is placed on it -- the same material in
a larger cell, which a defect, a guest or an interpenetrated pair needs
room for), **Layer spacing** and **Stacking offset** (layer nets only:
{doc}`layers`), and **Interpenetration** (copies of the framework
threaded through one another, placed where the closest contact
between copies is largest, and refused by name when no placement has
room; *Structure ▸ Interpenetrate…* lists every placement, see
{doc}`/structure/interpenetration`).  Under *Your own topologies and
building blocks*, two folders of `.cgd` nets and `.xyz` blocks are read
alongside PORMAKE's, and a file in a later folder replaces one of the
same name in an earlier one.

## The verdict

```{index} single: MOF builder; verdict
```

Every build ends with one line in the status bar and at the head of
its report, and the line says **what was measured and nothing that was
not**:

```text
the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.33 A, 6 joint(s) bonded
```

The first half is not a repetition of the request.  The builder draws
the net it built on over the framework as {term}`topology bonds
<topology bond>` -- it knows which atoms are one node -- and then reads
that net back off the bonds in the structure and names it against the
RCSR with the same code the *Net* panel uses.  A build asked for
**tbo** that produces something else says *asked for tbo and built …
-- these are different nets*, and an interpenetrated build says how
many copies it read back.  The numbers are the worst block's fit, the
shortest distance between two atoms that are not bonded, how many
joints were bonded and, where it was measured, the longest bond a
joint made.

What the verdict never says is anything about the *shape* of the
cell.  A topology is combinatorial and its metric is free -- the code
notes DMOF-1 as a tetragonal **pcu** and MIL-53 as monoclinic -- so
"relaxed to triclinic where pcu is cubic" would be a false alarm on
real materials.  Whether a build is any good is the fit and the
contacts, and those are given as numbers.

## The results table

```{index} single: MOF builder; results table
```
```{index} single: Joint twist left
```

The {ref}`Results panel <panel-results_dock>` shows three tables
({numref}`fig-frameworks-build-report`).

:::{figure} /figures/frameworks/build-report.png
:name: fig-frameworks-build-report
:width: 70%

The Results panel after MOF-5 is built on **pcu** from **N16** and
**E14**: what was built, how well the blocks fit, and the net read
back off the framework.
:::

**What was built** records the request -- topology, node blocks,
linkers, the repeat, the interpenetration, the orientation rule -- and
the atom count, the number of joints bonded and the cell.

**How well the blocks fit the net** has PORMAKE's own three numbers
and one or three of the application's:

Largest RMSD, Mean RMSD
: How far a block's connection points sit from the directions the net
  asked for, in Å; the largest is the worst slot in the framework.

Cell relaxation
: The value PORMAKE's cell scaling converged to.

Closest contact
: The shortest distance between two atoms that are not bonded.  The
  table's own note gives the yardstick: every framework in
  `resources/samples` sits between 1.996 and 2.170 Å, and blocks that
  do not fit their net come out below that.

Longest joint
: Shown only when a connection point stood for several atoms, so that
  there was something to measure.  The longest bond a joint made says
  whether the two ends of a joint actually met, which the RMSDs cannot:
  a block can sit perfectly on its own slot and still present the
  wrong face to its neighbour.

Joint twist left
: Shown only when the orientation rule scored something.  It is how
  far the faces at the two ends of each edge still disagree once the
  nodes were turned, summed over the edges -- 0 where they agree, 2 an
  edge at a quarter turn -- with the number of edges in the row's
  note.  It is what the rule could not fix.  MOF-5 on one cell of
  **pcu** reads **6.000** over 3 edges, because the single node slot
  cannot alternate with itself; the same build on a 2×2×2 net reads
  **0.000** (see the worked example).

**The net that came out** gives the topology asked for, the net
identified from the bonds, and its coordination sequence and point
symbol -- the two invariants the RCSR names a net by ({doc}`nets`).
The table's note says why the check is worth anything: it is over the
bonds in the file, not over anything PORMAKE said.

## What a build leaves in the workspace

```{index} single: workspace; a build in it
```

A build is filed in the {term}`workspace` like any document, as one
entry named for the build: the topology, the repeat when there is one,
the interpenetration when there is one, then the blocks --
`pcu-N16-E14`, `pcu-2x2x2-N16-E14`.  The orientation rule is not in the
name, because it changes which way round the blocks are and never
what the framework is made of.  The entry holds **one CIF, written
from the structure** -- with the net drawn over it and the joints'
bonds in it -- and the run underneath it:

```text
<workspace>/pcu-N16-E14/pcu-N16-E14.cif
<workspace>/pcu-N16-E14/mof-build-001/run.log
```

PORMAKE's own copy of the CIF, written before the net was drawn, is
dropped rather than kept beside it.  The tab that opens is that file.
A second build with the same name gets `-2`.  Filing is the core's
rule, not the window's, so `xtal run mof.build --workspace DIR` files a
build exactly as the window does.

## Worked example: MOF-5 on pcu

```{index} single: MOF-5; building
```

MOF-5 is a Zn{sub}`4`O node with six carboxylates on the primitive
cubic net, joined by a phenylene.  In PORMAKE's database the node is
**N16** (*6-connected, metal · C6O13Zn4*) and the linker **E14**
(*2-connected · C6H4*).  From the command line, `xtal run` takes the
module entry and its parameters as `-p name=value` (`xtal run --help`;
`xtal modules` lists the entries and their defaults), and
`--workspace` files the result:

```console
$ xtal run mof.build -p topology=pcu -p nodes=N16 -p edges=E14 --workspace ws
PORMAKE: building pcu-N16-E14
topology pcu: 6-c  ·  Pm-3m (221)  ·  [1 1 1 1]
loading PORMAKE
placing 1 node type(s) and 1 linker type(s) on 4 slots
[...]/scipy/spatial/transform/_rotation.py:2576: UserWarning: Optimal rotation is not uniquely or poorly defined for the given sets of vectors.
[...]
orientation consistent: joints disagree by 6.000000 over 3 edge(s), against 6.000000 as found
the fit had already put the nodes the best way round; keeping it
settled 1 block(s) about their own axis, of 3 that could turn
wrote pcu-N16-E14.cif
bonded 6 joint(s) between blocks
drew 3 net edge(s); identifying what came out
the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.33 A, 6 joint(s) bonded
filed as [...]/ws/pcu-N16-E14/pcu-N16-E14.cif
53 atoms; the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.33 A, 6 joint(s) bonded

pcu-N16-E14

What was built
Topology          pcu
Node blocks       N16
Linkers           E14
Net repeated      1x1x1
Interpenetration  none
Node orientation  consistent
Atoms                                     53
Joints bonded                              6
Cell              13.246 x 13.246 x 13.246 A

How well the blocks fit the net
Largest RMSD      0.0000  A
Mean RMSD         0.0000  A
Cell relaxation   0.0000
Closest contact    2.329  A
Joint twist left   6.000
[...]
The net that came out
Asked for              pcu
Built                  pcu
coordination sequence  6, 18, 38, 66, 102, 146, 198, 258, 326, 402
point symbol           4^12.6^3
[...]
```

The `UserWarning` from SciPy is expected: placing a two-connected
block is a fit of two vectors, which SciPy says out loud is not
uniquely defined, and the angle it leaves open is what *settled 1
block(s) about their own axis* then fixes ({doc}`orientation`).  The
build took about a second on the machine this was written on.

One cell of **pcu** has one node slot, so every edge joins the node to
an image of itself and no turn can make its two ends disagree less:
*Joint twist left* is 6.000 over 3 edges.  Repeating the net gives the
rule room:

```console
$ xtal run mof.build -p topology=pcu -p nodes=N16 -p edges=E14 -p repeat=2x2x2 --workspace ws
[...]
placing 1 node type(s) and 1 linker type(s) on 32 slots
orientation consistent: joints disagree by 0.000000 over 24 edge(s), against 48.000000 as found
settled 24 block(s) about their own axis, of 24 that could turn
[...]
424 atoms; the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.33 A, 48 joint(s) bonded
[...]
Joint twist left   0.000
```

Eight nodes in the cell can alternate, and the disagreement goes from
48 across 24 edges -- a quarter turn at every one, as the fit left them
-- to none.  The same build with `-p orientation=as-found` runs no
rule, prints no *Joint twist left* row, and is what PORMAKE makes.

## Settings

Every parameter -- topology, the two block assignments, the repeat,
the orientation, the layer spacing and offset, the interpenetration
and the two extra folders -- is listed with its default under
{ref}`Build a framework… <mod-mof-build>` in the reference, and the
module itself under {ref}`MOF builder <mod-mof>`.  On the command line
each is `-p name=value`; node and linker assignments are spelled `N59`
when the net has one kind of node, `0=N19,1=N59` when it has more, and
`0-0=E32,0-1=E14` for two kinds of edge.

## Limitations

- **A build places blocks and stops.**  Nothing is relaxed: the bond
  across a joint is whatever the fused connection points made it, and
  a relaxation is yours to run in the Force Field panel.
- **A joint between two chelating ends comes out about 0.3 Å long,
  and the cell with it** (`docs/TODO.md`).  A connection point is
  0.75 Å from the centroid of the atoms it stands for, which is right
  for one atom meeting one atom; a chelate's bonds lean inwards, so
  two such ends meet with their centroids further apart than the bond
  between them.  Measured on Ni{sub}`3`(HITP){sub}`2` on **hcb**: the
  Ni--N bonds to the thousandth of the crystal's, and the N--C bond
  across every cut 1.606 Å against 1.294, giving *a* = 22.731 Å
  against 21.552 (+5.5 %).  The *Longest joint* row is where this
  shows.
- Four of PORMAKE's net files give edge midpoints instead of endpoints
  and cannot be expanded by the application; those report their slots
  as unknown and the build falls back on asking PORMAKE.
- A build is not bit-identical to upstream PORMAKE's, for the
  precision reason above.
