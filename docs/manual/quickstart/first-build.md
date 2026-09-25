# Your first crystal build

In this exercise you build a framework from a net, a metal node and a
linker you draw yourself, relax it with UFF4MOF, recover its space
group, and name its net -- twice, with two different choices of what
counts as a vertex.  Every number below is what the application printed when the steps
were run.

```{index} single: tutorial; first build
```

The framework is **acs** built on **N134**, a Ni{sub}`3`O trimer with six
carboxylates, joined by a *para*-phenylene linker.  You need nothing
installed beyond the application: the MOF builder and PORMAKE
{cite}`lee2021pormake` ship with it, and the force field is in
process.

## Build the framework

```{index} single: MOF builder; first build
```

1. Open *Modules ▸ MOF builder ▸*
   {ref}`Build a framework… <cmd-module.mof.build>`.  The dialog
   ({numref}`fig-first-build-mof-builder`) has a topology list at the
   top and one row per slot the chosen net has underneath.
2. Under **Topology**, type `acs` in the name box and select **acs**
   in the list.  The picture beside it shows the net -- *acs P6{sub}`3`/mmc,
   2 vertices and 6 edges in the cell, node 1: 6-connected, 1 kind of
   edge* -- so the net wants one kind of node block and one kind of
   linker.
3. In the row **Node 1, 6-connected**, choose **N134** (*6-connected,
   metal · C6Ni3O16*).  The list only ever offers blocks with as many
   connection points as the slot is coordinated.
4. In the row **Linker at node 1**, press **Draw…**.  In the *Draw a
   building block* dialog type the SMILES `*c1ccc(*)cc1` -- a benzene
   ring with a `*` at each *para* position, which is how a connection
   point is written -- and `benzene` as the name.  The footer reads
   *C6H4, 12 atom(s), 2 connection point(s) -- fits linker at node 1*.
   Press **Save and use**: the block is written to `blocks/` in your
   workspace, appears in the tree, and the row selects it.
5. Leave *How it is built* folded (the defaults are one cell of the
   net, node orientation *Consistent across every joint*, no
   interpenetration) and press **Build**.

:::{figure} /figures/quickstart/first-build-mof-builder.png
:name: fig-first-build-mof-builder
:width: 100%

The MOF builder ready to build: **acs**, **N134** in the node slot,
and the linker row waiting for the drawn block.
:::

The framework opens in a new tab, `acs-N134-benzene`, filed in the
workspace with the build's log underneath it.  The status bar reports
what was built -- 110 atoms in the cell -- and the *Structure* panel
gives the cell PORMAKE scaled the net to:

```
a = 17.996  b = 18.310  c = 12.817 A    space group P1
```

The net is already drawn over the framework as thick translucent
rods, and the *Net* panel names it **acs**: the builder records which
node went in which slot, so the net it built on is the net it draws.
To see the metal nodes as polyhedra, choose *View ▸ Style ▸
Polyhedra and sticks*.

:::{note}
A build places blocks and stops.  The joints between blocks are
stored as your own bonds, so they survive
{ref}`Recalculate bonds <cmd-recompute_bonds>` however long they are;
everything inside a block was perceived from its geometry.  Nothing
has been relaxed yet, and *a* and *b* are not equal because PORMAKE's
cell is a fit, not a hexagonal one.
:::

## Relax it with UFF4MOF

```{index} single: Force Field panel; first build
```

1. Open the panel with *Modules ▸ Forcefield ▸*
   {ref}`Force Field panel <cmd-show_ff>`.
2. Under **Model**, leave *Force field* at **UFF** and *Parameters* at
   **UFF4MOF (UFF plus framework nodes)** -- the default, and the one
   that has rows fitted to metal nodes
   {cite}`addicoat2014uff4mof,coupry2016uff4mof2` on top of UFF
   {cite}`rappe1992uff`.  The table beneath lists every site's atom
   type, what it means, and how sure the typer was.
3. Under **Optimisation**, leave *Optimiser* at **Smart (descent, then
   ABNR, then quasi-Newton)**, and tick **Relax the cell as well**.
   *Stress below* becomes live at 0.050 GPa.
4. Press **Optimise**.  The structure moves in the 3D view as it
   goes, and the energy and the largest force are plotted live.

:::{figure} /figures/quickstart/first-build-forcefield.png
:name: fig-first-build-forcefield
:width: 60%

The Force Field panel after the run: UFF4MOF, the Smart optimiser,
the cell relaxed, and the report underneath the trace.
:::

The run converges in a few seconds.  The report under the plot reads:

```
converged after 217 steps: -2319.0085 kcal/mol to 649.9145, |F|max
0.0472 kcal/mol/A, cell -44.62% by volume
```

followed by the energy broken down by term, and the *Structure* panel
now gives

```
a = 18.988  b = 18.988  c = 6.533 A
```

The cell is hexagonal to the last figure, and the hint under the
report says why you should not read too much into it: *A cell relaxed
under UFF is a UFF cell: for a framework it is routinely a few percent
out.  Use it as a starting geometry, not as a measured lattice
constant.*  It also says *6 site(s) have a type the typer is not sure
of (Ni4+2, …).  Check them before trusting the energy.*  The nickel
atoms of a trimer are not an environment UFF4MOF is certain about,
and the panel says so rather than hiding it.

:::{note}
A force field never changes the bonding or the atoms: it moves them.
The bonds you see after the run are the bonds the build made, and
they are recalculated only when you press
{ref}`Recalculate bonds <cmd-recompute_bonds>`.
:::

:::{warning}
The whole run is one undo step: {kbd}`Ctrl+Z` gives back the
structure you started with, not the second-to-last iteration.  If a
run ends with *The optimiser stopped before converging*, the geometry
is where it got to and not a minimum; press **Optimise** again to
carry on.
:::

## Find the space group

```{index} single: Find symmetry; first build
```

The framework is still in P1 with 110 sites.  The relaxation was
done under no symmetry at all, so what the atoms have settled into is
worth asking.

1. Open *Symmetry ▸* {ref}`Find symmetry… <cmd-find_symmetry>`
   ({kbd}`Ctrl+Shift+F`).
2. At the default tolerance of 0.1 Å the dialog
   ({numref}`fig-first-build-find-symmetry`) reads **P6_3/mmc (#194),
   24 operations, 8 independent sites**, with the Wyckoff table under
   it: the μ{sub}`3`-oxygen on *2d* with site symmetry −6m2, the nickel on
   *6h*, the linker carbons on *12k*.  The box offers other
   tolerances and the answer is re-detected as you change it.
3. The dialog warns that *this cell is not in the standard setting of
   P6_3/mmc*, and *Re-express the cell in the standard setting first*
   is ticked, so adopting will move the atoms into that setting.
   Press **Adopt this group**.

:::{figure} /figures/quickstart/first-build-find-symmetry.png
:name: fig-first-build-find-symmetry
:width: 60%

*Find symmetry* on the relaxed framework: P6{sub}`3`/mmc at 0.1 Å, the
warning about the setting, and the Wyckoff table.
:::

The *Structure* panel now reads **P63/mmc (#194)** with 8 sites in
the asymmetric unit, and the view resets to frame the re-expressed
cell.  The 110 atoms are still there; they are now generated from
eight.

One more thing has changed: the *Net* panel is empty.  It says *No
net has been drawn*, because the net the builder drew did not survive
the re-expression of the cell.  Drawing it yourself is the next step,
and the point of the exercise.

## Draw the net on the metal clusters

```{index} single: net; drawing
```
```{index} single: topology bond
```

A {term}`net` is a statement about which parts of a framework are
vertices and which are edges.  The obvious choice for this framework
is the trimer: one vertex at each Ni{sub}`3`O cluster, and an edge for
each linker between two of them.  The atom at the middle of the
cluster is the μ{sub}`3`-oxygen, so that is what you draw between.

1. Press **Draw net** in the toolbar
   ({ref}`Mouse mode ▸ Draw net <cmd-mode_topology>`).  The status
   bar says *click two atoms to draw a net edge · click an edge to
   select it, Del removes it*.
2. Click the μ{sub}`3`-oxygen at the centre of one trimer, then the
   μ{sub}`3`-oxygen of a neighbouring trimer -- the one at the other end of
   a linker, 11.44 Å away.  The status bar answers *net edge drawn --
   6 in the cell*.

One click drew six edges.  A {term}`topology bond` is a bond of the
asymmetric unit like any other, so it expands over the symmetry
orbit, and in P6{sub}`3`/mmc the six edges at a trimer are one orbit.  The
*Net* panel now reads:

```
acs
6-coordinated, 3-periodic
coordination sequence  6, 20, 42, 74, 114, 164, 222, 290, 366, 452
point symbol           4^9.6^6

2 vertices and 6 edges drawn in the cell
```

The name comes from the RCSR {cite}`okeeffe2008rcsr`, matched on the
coordination sequence and point symbol of the net you drew.  It is
the net you built on ({numref}`fig-first-build-net-acs`), recovered
from the framework by drawing rather than remembered from the
builder.  **Export Net for Systre…** in the same panel writes the net
as a `.cgd` file for Systre {cite}`delgadofriedrichs2003systre` to
name, which is a second opinion that does not come from the code that
gave the first.

:::{figure} /figures/quickstart/first-build-net-acs.png
:name: fig-first-build-net-acs
:width: 90%

The **acs** net drawn between the μ{sub}`3`-oxygens, over the relaxed
framework, seen down *c*.
:::

## Choose different vertices: ssa

```{index} single: Add centroid; first build
```

Now make a different choice.  Instead of one vertex per trimer, take
one per *metal atom* and one per *linker*, joined where a
carboxylate binds.

1. Still in *Draw net* mode, click any net edge to select it and
   press {kbd}`Del` ({ref}`Delete <cmd-delete_selection>`).  The status
   bar says *removed 6 net edge(s)*: the orbit goes as one, and the
   *Net* panel is empty again.
2. Switch to **Select** and select the six carbons of one benzene
   ring -- click one, shift-click the other five.
3. Choose *Structure ▸* {ref}`Add centroid… <cmd-add_centroid>` and
   accept **Dummy atom (X)**.  The status bar says *centroid of 6
   atoms added as X1*, and every ring in the cell has one, because the
   new site's orbit is generated with it.  A {term}`dummy atom` is a
   marker, not chemistry: it bonds to nothing, the force field sets
   it aside, and net edges and measurements take it like any atom --
   which is what it is for.
4. Back in **Draw net**, click the new marker at the centre of a
   ring, then the nearest nickel atom, 5.10 Å away.  The status bar
   says *net edge drawn -- 24 in the cell*.

The *Net* panel now reads:

```
ssa
4-coordinated, 3-periodic
4-coordinated vertex
coordination sequence  4, 10, 22, 38, 72, 102, 154, 190, 260, 314
point symbol           4^2.6^4
4-coordinated vertex
coordination sequence  4, 10, 22, 46, 72, 120, 154, 210, 260, 330
point symbol           4^2.8^4

12 vertices and 24 edges drawn in the cell
```

Two kinds of 4-connected vertex: each nickel meets four linkers, and
each linker's marker meets four nickels, two at each end.  *View ▸
Style ▸* {ref}`Net only <cmd-style_net>` draws the net and nothing
else ({numref}`fig-first-build-net-ssa`).

:::{figure} /figures/quickstart/first-build-net-ssa.png
:name: fig-first-build-net-ssa
:width: 90%

The same framework as **ssa**: vertices at the nickel atoms and at
the ring centroids, drawn on its own with *Net only*.
:::

The crystal has not changed between the two nets.  The same
atoms, the same cell, the same space group, and two names for the
net, both right.  **A net is a choice of vertices, not a property of
the crystal**: the cluster taken whole is a 6-connected node and the
framework is **acs**; the cluster taken apart into its metals is
three 4-connected nodes and the framework is **ssa**.  The *Net*
panel names what you drew, and drawing it is where the chemistry is.

Save the result with {kbd}`Ctrl+S`.  The framework becomes
`acs-N134-benzene.xtalproj` beside its CIF, with the net, the marker
and the relaxed cell in it.

:::{note}
This exercise is scripted, start to finish, in
`docs/manual/tutorial_check.py`, which drives the real application
through the run-app driver and stops at the first step whose answer
is not the one printed here; the figures above come from that run.
If a step gives you a different answer, the application or this page
has changed since it was last run.
:::
