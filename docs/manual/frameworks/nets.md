# Reading the net out of a crystal

A net is what a framework reduces to once you have said which parts
are vertices and which are edges.  After this section you can draw one
over any structure, read the *Net* panel's name and the two invariants
it rests on, understand what the identification can and cannot
decide, check it against Systre, search the RCSR's nets by what you
know about them, and draw a named net on its own.

```{index} single: net; identifying
```
```{index} single: RCSR
```
```{index} single: Net panel
```

## A net is a periodic graph

A {term}`net`, as the application treats it, is a periodic graph and
nothing else: which vertex is joined to which, and by what lattice
translation.  The cell, the coordinates and the space group of the
crystal underneath are irrelevant to its identity, which is what makes
the answer stable under everything else you do to a structure -- a
net survives a change of setting, a supercell and a relaxation
unchanged, because none of those touch which vertex is joined to
which.  What it does not survive is a change in *which atoms are the
vertices*, and that choice is yours.

## Topology bonds

```{index} single: topology bond
```
```{index} single: Draw net mode
```

You draw a net as {term}`topology bonds <topology bond>`: thick
translucent rods over the real bonds, invisible to every chemical
question -- perception, the force field, the atom typer.  The
{doc}`tutorial </quickstart/first-build>` draws two on the same
framework; the mechanics are:

1. Choose {ref}`Draw net <cmd-mode_topology>` in the toolbar.  The
   status bar says *click two atoms to draw a net edge · click an edge
   to select it, Del removes it*.
2. Click two atoms.  A topology bond is a bond of the
   {term}`asymmetric unit` like any other, so it expands over the
   symmetry {term}`orbit`: one click in P6{sub}`3`/mmc drew the six
   edges of a trimer in the tutorial, and the status bar counts them
   (*net edge drawn -- 6 in the cell*).
3. To put a vertex where there is no atom -- the middle of a ring, of a
   cluster -- select the atoms and choose *Structure ▸*
   {ref}`Add centroid… <cmd-add_centroid>` with **Dummy atom (X)**.  A
   {term}`dummy atom` is a marker, not chemistry; net edges take it
   like any atom, which is what it is for.
4. Click an edge to select it and press {kbd}`Del`; the orbit goes as
   one (*removed 6 net edge(s)*).

:::{note}
**A click inside a net edge is the net edge**, whatever chemistry
crosses under it: near the edge's axis the edge wins, outside that
whatever is behind it does, and an atom always does.  Depth alone was
the old rule, and it meant a click aimed at the net selected the
chemical bond beneath -- with {kbd}`Del` then suppressing that bond and
its whole orbit, 96 chemical bonds on MOF-5 with the net still on
screen.
:::

*View ▸ Style ▸* {ref}`Net only <cmd-style_net>` draws the net and
nothing else.  The net is saved with the structure: the workspace copy
of a CIF carries it, and the export path strips it.

## The Net panel

```{index} single: coordination sequence
```
```{index} single: point symbol
```

The {ref}`Net panel <panel-net_dock>` (*Window ▸ Net*) names the net
in the active document and shows what the name rests on
({numref}`fig-frameworks-net-panel`).  For the MOF-5 built in
{doc}`mof-builder`, whose net the builder drew, it reads:

```text
pcu
6-coordinated, 3-periodic
coordination sequence  6, 18, 38, 66, 102, 146, 198, 258, 326, 402
point symbol           4^12.6^3

1 vertices and 3 edges drawn in the cell
```

:::{figure} /figures/frameworks/net-panel.png
:name: fig-frameworks-net-panel
:width: 45%

The *Net* panel on the MOF-5 build: the name, the invariants it rests
on, how much of the cell the net is, and the two buttons.
:::

The **headline** is the name.  Under it: the coordination and
periodicity, then a block per kind of vertex with the two invariants
the RCSR names a net by {cite}`okeeffe2008rcsr,blatov2010symbols`:

Coordination sequence
: How many vertices lie exactly *k* edges from a vertex, for *k* from
  1 to 10, counted on the infinite net: **pcu** is 6, 18, 38, 66, …
  and, as the code notes, nothing else is.  It is the same for a net
  described in a larger cell, which is what lets a **pcu** drawn on
  eight vertices be recognised against the RCSR's one.

Point symbol
: For every pair of edges meeting at the vertex, the size of the
  smallest ring containing that angle, collected with multiplicities:
  `4^12.6^3` for **pcu**.  A vertex of degree *n* has *n(n−1)/2*
  angles; an angle with no ring within the search bound (12) is
  written `*`, as the RCSR does.

The last line says how much of the cell the net is -- a **pcu** found
on eight vertices and twenty-four edges is the same net the RCSR
draws with one and three, and seeing both numbers is what makes that
believable.  **Copy** puts the whole identification on the clipboard;
**Export for Systre…** is described below.

The panel recomputes only when the bonds change, and only while it is
on screen: a cell edit, a relaxation and a change of setting leave
the net alone, and a panel nobody has opened remembers that it is
stale and catches up when shown.  Identification walks ten shells of
an infinite graph and looks for the smallest ring at every angle,
which is milliseconds on **pcu** and half a minute on the worst net in
the database.

## What the identification decides

```{index} single: net; canonical key
```

The lookup has two layers, computed independently, and neither is
allowed to hide the other.

The **invariants** -- the coordination sequence to ten terms and the
point symbol, over the distinct vertices -- are a filter.  They name
2665 of the 2679 3-periodic RCSR nets uniquely; the commonest net in
the field is the proof that the sequence alone is not enough, since
**pcu** shares 6, 18, 38, 66, 102, 146 with **tfs**, **smd**, **sxd**
and **vng**, and the point symbol separates them.  Two nets, **sxd**
and **vng**, share both and are not the same net.

The **canonical key** -- the net reduced to the smallest cell it has
and written down the one way that does not depend on how it arrived --
decides.  Equal keys mean the same net and unequal keys different
nets, so it separates the fourteen names the invariants cannot, and it
turns "no catalogued net has these invariants" into "no catalogued net
*is* this net".

What the headline can say, and the line under the invariants that
explains it:

- **pcu** -- one name, and the key proved it.  Where the key could not
  run (a net too large to key within the budget a lookup allows
  itself), the caveat says *named by its invariants; … nothing has
  proved it*.
- **sxd or vng** -- the invariants match two names and the key could
  not tell them apart.
- **not in the RCSR** -- with *nearest by …* naming the catalogued nets
  closest on what they share, or, when the key settled it, *no
  catalogued net has this net's canonical form; X, Y share its
  invariants and are other nets*.  For a genuinely new net this is a
  result and not a failure.
- **not catalogued** -- the drawn net is 0- or 1-periodic and the RCSR's
  file holds only 2- and 3-periodic nets.
- **2-fold interpenetrated pcu** -- the drawn net is several
  independent copies of one net; and **2 separate nets** when the
  components are different nets, each then identified on its own.

The catalogue is the RCSR's net file of 2019-06-01, expanded once and
shipped as an index inside the package.

## Checking with Systre

```{index} single: Systre
```
```{index} single: cgd file
```

Systre {cite}`delgadofriedrichs2003systre` names a net from a
description of its graph, and is a second opinion that does not come
from the code that gave the first.  **Export for Systre…** in the
panel, or *File ▸* {ref}`Export Net for Systre… <cmd-export_net>`,
writes the drawn net as a `.cgd` file -- Systre's input format, and
the format the RCSR publishes its nets in.  Every vertex of the expanded cell is
written as a node, in {term}`P1`, and every edge as a pair of points,
so the file is the net exactly as the panel sees it and nothing a
reader has to take on trust.  Two vertices so close that an endpoint
could be matched to either are refused, because Systre finds an edge's
ends by position and a file that joins the wrong one describes a
different net.

(net-search)=
## Finding a net by what you know about it

```{index} single: net search
```
```{index} single: transitivity
```

The MOF builder and the Net builder list the same few thousand nets,
and their names are three letters of no mnemonic value.  Above both
lists the same search takes the four fields a chemist knows -- the
ones the MOF+ database prints beside a net:

Name
: A substring: `pcu`, `dia`, `hcb`.

Coordination
: The coordination numbers the net has, `3,6` or `3 6` or `3,6-c`.
  With **Exclusive** ticked, those and no others.

Spg #
: The space group number, a list (`191,194`) or a range (`221-230`).
  A layer answers to its **plane group** number, 1 to 17.

Transitivity
: `p q r s` -- the kinds of vertex, edge, face and tile -- as the RCSR
  gives them: `1 1 1 1`, `1,2`, `[1 1 1 1]` or packed as `11**`.  `*`
  matches anything.

The transitivity is **the RCSR's, and unknown where it has none**.
*r* and *s* belong to a net's natural tiling, which the net file does
not carry, so all four numbers come from the RCSR's own data files: a
layer has no tiles, half the 3-periodic nets have no natural tiling on
record, and a net of your own has only its `NODE` and `EDGE` lines for
*p* and *q*.  A number typed where the value is unknown matches
nothing -- a list that answered "faces: 2" with every net would be
claiming knowledge it does not have -- and an unknown is left off the
row rather than printed as `?`.  Each row shows what it is matched on:
`hcb  3-c · p6mm (17) · [1 1 1]`.  A field that cannot be read keeps
the list as it was and says why underneath, because emptying the list
would be a claim about nets when the typing was what was wrong.  The
**3D** and **2D** boxes keep the two group numberings apart.  Under the
list, links open the chosen net's page in the RCSR.

## The Net builder

```{index} single: Net builder
```

*Modules ▸ Net builder ▸* {ref}`Draw a net… <cmd-module.net.draw>`
draws a named RCSR net on its own, in a tab of its own, for looking at
({numref}`fig-frameworks-net-builder`).  Every net in the RCSR's file
that has a cell can be drawn, the layers among them; nothing is
optional about it, so the entry is never greyed.

:::{figure} /figures/frameworks/net-builder.png
:name: fig-frameworks-net-builder
:width: 90%

The Net builder with **hcb** chosen: the search above the list, the
net's picture and its description, and the two drawing settings.
:::

**The elements are notation, not chemistry.**  A vertex is a hydrogen
and an edge is a string of heliums, the two smallest atoms in the
table, so the spheres stay out of the way of the rods and nothing
refuses the pairs.  The beads along an edge are what make coordination
polyhedra work: a polyhedron is drawn over an atom's *neighbours*, and
the bead nearest each vertex is a corner, which is why an edge is a
string of atoms rather than one long bond.  **Cell scale** (8 by
default) sets how far apart the beads are -- the RCSR's cells are
normalised so an edge is about one unit long, and eight puts the atoms
along an edge about 1 Å apart -- and **Atoms per edge** (8, counting
the two vertices) how smooth the rod is.

```console
$ xtal run net.draw -p net=hcb -o hcb-net.cif
drew hcb from the RCSR
hcb: 1 vertex site(s), 5 in the asymmetric unit, P 6/m m m
wrote hcb-net.cif
```

:::{warning}
**Recalculate Bonds cannot give a drawn net back.**  Its edges are
written from the net's own edge list, not perceived from distances,
and no distance rule would do the same job: in **rht** two beads on
*different* edges are 0.82 Å apart while a bond along an edge is
1.00 Å, and in **soc** the two distances are equal.  Pressing
{ref}`Recalculate bonds <cmd-recompute_bonds>` on a drawn net replaces
its bonds with something else.
:::

## A net is a choice

The tutorial's closing point is the author's, and it is the point of
this chapter; quoting it from {doc}`there </quickstart/first-build>`:

> The crystal has not changed between the two nets.  The same atoms,
> the same cell, the same space group, and two names for the net,
> both right.  **A net is a choice of vertices, not a property of the
> crystal**: the cluster taken whole is a 6-connected node and the
> framework is **acs**; the cluster taken apart into its metals is
> three 4-connected nodes and the framework is **ssa**.  The *Net*
> panel names what you drew, and drawing it is where the chemistry
> is.

## Settings

The Net builder's three parameters are under {ref}`Draw a net…
<mod-net-draw>`; the panel is {ref}`described <panel-net_dock>` with
the other panels; the export command is {ref}`Export Net for Systre…
<cmd-export_net>`.

## Limitations

- The identification is only as good as the net you drew.  A net
  drawn on the wrong atoms is identified correctly as the net of
  those atoms.
- A net too large to key within the lookup's budget is named by its
  invariants alone, and the panel says so.
- The index is the RCSR's 2019 file; a net named since is *not in the
  RCSR* here.
- The Net panel is not in the default layout; open it from the
  *Window* menu.
