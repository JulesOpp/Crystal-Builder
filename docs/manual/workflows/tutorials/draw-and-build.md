(tutorial-draw-and-build)=
# Tutorial: draw a linker and build a MOF

A framework is a net, a node and a linker.  PORMAKE
{cite}`lee2021pormake` ships 867 blocks, but the one you want is
usually not among them.  In this tutorial you draw a *para*-phenylene
linker with the 2D sketcher, mark its connection points, save it as a
building block, build a MOF-5-like framework from it on the **pcu**
net with a Zn{sub}`4`O node, read the build's report, and then put
an amino group on the linker twice: once by drawing it into the
block, once by substituting the built framework.

```{index} single: tutorial; draw a linker and build a MOF
```

You need the molecule builder's extra (*RDKit*, the `build` extra;
{doc}`/quickstart/installation`) and the MOF builder's (`ase`).  Both
are checked without being imported, and an entry greys out naming the
extra it lacks.

## What the node already holds

MOF-5 is Zn{sub}`4`O(bdc){sub}`3`: terephthalate, a benzene with a
carboxylate at each end.  PORMAKE's node for it, **N16** (*6-connected,
metal · C6O13Zn4*), already includes the six carboxylate carbons --
each carries a connection point -- so the linker that completes it is
the benzene ring alone, with a connection point at each *para*
position.  That is the block you draw.  A drawn dicarboxylate would be
a block for a bare Zn{sub}`4`O node, which has to be a node you cut
out yourself ({doc}`/frameworks/blocks`).

## Draw the linker

1. Open *Modules ▸ MOF builder ▸* {ref}`Build a framework (MOF)…
   <cmd-module.mof.build>`.
2. Under **Topology**, type `pcu` and select **pcu**.  The net has one
   kind of node, 6-connected, and one kind of edge.
3. In **Node 1, 6-connected**, choose **N16**.
4. In **Linker at node 1**, press **Draw…**.  The *Draw a building
   block* dialog is the molecule builder's SMILES box and canvas,
   aimed at this slot.  Type `*c1ccc(*)cc1` in the SMILES box -- a
   benzene ring with a `*` at each *para* position, which is how a
   connection point is written -- and the sketcher draws it.  Or draw
   it on the canvas -- a ring from the ring buttons, a bond out of
   each *para* carbon, and `*` typed over the atom at the end of each
   bond ({doc}`/frameworks/molecule-builder` lists the gestures) -- and
   the string appears in the box.
5. Read the footer.  It names the formula, the atom count and the
   connection points, and says whether they fit the slot: *C6H4, 12
   atom(s), 2 connection point(s) -- fits linker at node 1*.  **Save
   and use** is enabled only when they do.
6. Name it `phenylene` and press **Save and use**.  The block is
   written to `blocks/phenylene.xyz` in your workspace -- the
   *Workspace* panel shows it -- and the linker row selects it.

The molecule is embedded with each `*` capped by a hydrogen, relaxed
with MMFF, and the caps are then relabelled `X` and pulled in to
0.75 Å from the atom they hang off, which is where a connection point
sits whatever the bond length is
({doc}`/frameworks/blocks`).  The file the dialog writes is PORMAKE's
`.xyz` with the two points as its second line:

```text
12
   10   11
C    -1.2258 0.6553 -0.1164
C    -1.1722 -0.6354 0.4097
[...]
X    -1.8849 1.0077 -0.1790
X    1.8849 -1.0077 0.1790
```

The same file without the window: the dialog's own two calls are
the molecule builder and the block writer, so

```python
from xtal.modules.build import molecule_for
from xtal.mof.block import write_building_block

m = molecule_for(dict(smiles="*c1ccc(*)cc1", name="phenylene",
                      optimise=True), connection_points=True)
print(m.formula, m.n_atoms, m.n_connections)       # C6H4 12 2
write_building_block(m.to_structure(), "ws/blocks/phenylene.xyz")
```

and `xtal run mof.build` finds `ws/blocks/` by walking up from the run
folder, as the window does.

## Build the framework

7. Open **How it is built**, set **Repeat the net** to `2x2x2` and
   leave the rest -- node orientation *Consistent across every
   joint*, no interpenetration -- and press **Build**.

```console
$ xtal run mof.build -p topology=pcu -p nodes=N16 -p edges=phenylene -p repeat=2x2x2 --workspace ws
PORMAKE: building pcu-2x2x2-N16-phenylene
topology pcu: 6-c  ·  Pm-3m (221)  ·  [1 1 1 1]
placing 1 node type(s) and 1 linker type(s) on 32 slots
orientation consistent: joints disagree by 16.000000 over 24 edge(s), against 48.000000 as found
settled 24 block(s) about their own axis, of 24 that could turn
bonded 48 joint(s) between blocks
drew 24 net edge(s); identifying what came out
the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.15 A, 48 joint(s) bonded
424 atoms; the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 2.15 A, 48 joint(s) bonded
```

(SciPy also prints its *Optimal rotation is not uniquely defined*
warning; the rule that follows is what fixes the angle it leaves
open.  {doc}`/frameworks/orientation`.)  The framework opens in a new
tab, `pcu-2x2x2-N16-phenylene`, filed in the workspace with the build's
log, and the net is already drawn over it.

## Read the report

The results table is the build's own account of itself
({doc}`/frameworks/mof-builder`):

```text
What was built
Topology          pcu
Node blocks       N16
Linkers           phenylene
Net repeated      2x2x2
Atoms                                    424
Joints bonded                             48
Cell              25.911 x 25.911 x 25.911 A

How well the blocks fit the net
Largest RMSD      0.0000  A
Mean RMSD         0.0000  A
Cell relaxation   0.0000
Closest contact    2.155  A
Joint twist left  16.000

The net that came out
Asked for              pcu
Built                  pcu
coordination sequence  6, 18, 38, 66, 102, 146, 198, 258, 326, 402
point symbol           4^12.6^3
```

Read it in order of how much it can be wrong:

- **Built is Asked for.**  The net it drew over the framework is read
  from the bonds in the file, so *pcu* here is a check and not an
  echo.
- **424 atoms, 48 joints.**  Eight nodes of 23 atoms and twenty-four
  linkers of 10 make 184 + 240 = 424 -- the connection points are
  not atoms of the structure.  48 joints is one per linker end, six
  per node over eight nodes, which is what *Joints bonded* should be.
- **RMSD 0.0000 and cell relaxation 0.0000.**  A block fits its slot
  exactly when the net's geometry suits it, as pcu's does.
- **Closest contact 2.155 Å** is the nearest pair of unbonded atoms,
  well clear of the 1.0 Å below which the report warns of overlap.
- **Joint twist left** is how much turning the orientation rule
  could not remove.  It is 16.000 here; the shipped benzene linker
  E14 on the same net and node gives 0.000 and a closest contact of
  2.33 Å.  A drawn block is not E14: its ring is a real benzene, with
  1.39 Å bonds where E14's are 1.54 Å, so the cell comes out
  25.911 Å against 26.49 Å for E14.  Whether the twist matters is for the closest contact to say, and
  it is clear.

:::{note}
The cell is the net's cell scaled to the blocks, not a relaxation.
MOF-5's own sample has a cell of 25.866 Å (`resources/samples/MOF-5.cif`);
the drawn linker's 25.911 is within 0.2 % of it, before any force
field.
:::

## A substituted linker, drawn into the block

Add an amino group to the block and build again.  In the **Draw…**
dialog the string is `*c1cc(N)c(*)cc1` (or draw a bond out of a ring
carbon and type `N` over its end); the footer reads two connection
points again.  Save it as `amino-phenylene` and build with it.

```console
$ xtal run mof.build -p topology=pcu -p nodes=N16 -p edges=amino-phenylene -p repeat=2x2x2 --workspace ws
[...]
472 atoms; the framework is pcu, as asked -- blocks fit to 0.000 A, closest contact 1.69 A, 48 joint(s) bonded
```

Forty-eight atoms more than the plain framework: 24 linkers, each
with one NH{sub}`2` (3 atoms) in place of an H (1): 24 × 2 = 48.
Every linker carries one amino group, in the position the block was
drawn; *Joint twist left* is 0.000 for this one.  The closest contact
has fallen to 1.69 Å: an NH{sub}`2` beside a carboxylate is a close
pair, and nothing relaxes it yet.  The report warns only under 1.0 Å, but a
force field is the next step before reading anything from it.

## A substituted linker, put on the built framework

The other way round keeps the plain block and edits the result.  Build
**pcu** with N16 and the shipped **E14** (one cell, 53 atoms), then:

1. Choose *Structure ▸* {ref}`Substitute hydrogens…
   <cmd-substitute_rings>`.
2. Choose the group **NH2**, and **One per ring**.
3. Press **Substitute**.

```python
from xtal.agent import Session

s = Session.build("mof.build", workspace="ws",
                  topology="pcu", nodes="N16", edges="E14")
print(s.n_atoms)                                   # 53
r = s.substitute("Amino", per_ring=True)
print(r.message)       # replaced 3 H with Amino (H2N)
print(s.inspect().formula, s.n_atoms)              # C24H15N3O13Zn4 59
```

Three hydrogens, one on each of the cell's three rings, become three
amino groups: C{sub}`24`H{sub}`12`O{sub}`13`Zn{sub}`4` becomes
C{sub}`24`H{sub}`15`N{sub}`3`O{sub}`13`Zn{sub}`4`, 59 atoms.  The
group's first atom is put a bond's length out along the old C--H and
the rest turned to where it has most room; it is bonded to that carbon
and to nothing else, as every edit here is (no bond is perceived).
One per ring reduces the cell to P1 in the same step -- this build was
P1 already -- and the whole edit is one undo step.

(If you build on a larger repeat, *One per ring* puts one on every
ring of that cell, and a *Share* below 100 % takes a fraction of them
at random by the seed.)

## What to check

- The footer fits the slot before you save, and the block opens in
  the picker with its connection points.
- *Built* equals *Asked for*, the closest contact is above 1.5 Å and
  the joints are what the node and net give.
- The substituted framework's formula is the unsubstituted one plus
  what you added.
- The build is a *starting geometry*.  Relax it before reading
  anything from its energy, and {doc}`prepare-relax` is how.

## Where this is explained

{doc}`/frameworks/molecule-builder` for the sketcher and SMILES,
{doc}`/frameworks/blocks` for connection points and attachments,
{doc}`/frameworks/mof-builder` for the report and the verdict,
{doc}`/frameworks/orientation` for the twist, and
{doc}`/essentials/structure` for *Substitute hydrogens…*.
