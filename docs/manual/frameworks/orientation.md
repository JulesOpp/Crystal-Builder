# Which way round a node goes

A symmetric node fits its slot in many ways that the fit cannot tell
apart, and which one it takes decides what face the node shows its
neighbours.  After this section you know what the tie is, how the
default rule breaks it, what a face is and why it is scored but never
bonded, why a second pass is sometimes thrown away, and how a linker's
angle about its own axis is settled.

```{index} single: node orientation
```
```{index} single: MOF builder; node orientation
```
```{index} single: consistent (orientation rule)
```
```{index} single: as-found (orientation rule)
```

## The tie

A node block is placed by fitting its connection directions onto the
slot's {cite}`kabsch1976`.  For a symmetric node many fits are equally
good: an octahedral node fits its slot **24** ways with the same RMSD
-- the spread across the 24 is 6×10⁻⁸ Å -- while the body of the
block moves up to 8.2 Å between them.  The fit has no reason to prefer
one and takes whichever its search reached first, so which face a
node presents to its neighbour is, on its own, an accident.

That did not matter while a connection point stood for one atom:
there is nothing to present.  It matters as soon as one stands for two,
or for an atom with a plane around it.  Two ends of a joint bond well
exactly when their members line up, and a node turned a quarter turn
about the joint axis has its two members *across* the other end's
rather than along them.  MFU-4l's joints came out as a square -- all
four member-to-member distances equal -- which is that quarter turn
with nothing to break it.

## Faces

```{index} single: face (of a connection point)
```

What a connection point presents to its neighbour is its **frame**.
A point standing for two atoms presents the plane of the two -- the
chelate's bite.  A point standing for one atom presents a plane too,
when that atom has exactly two other neighbours in the block: the
carboxylate on MOF-5's node **N16** (the carbon and its two oxygens),
the ring on the linker **E14**.  An atom with one other neighbour is
linear and has no plane; one with three or more is a free rotor, or a
metal, with no preferred angle.  Of the 4215 connection points in
PORMAKE's database, 3899 present a face this way.

The plane is the atoms' and never where the `X` was written -- 2045 of
those 3899 faces have their `X` more than 0.1 Å off the plane, so a
face read from the `X` would lean with it.

:::{note}
**A face is scored, never bonded.**  The two neighbours that define
the plane are used to compare frames across a joint and for nothing
else; they never become members of the attachment, so the joints and
the bond counts are what they were: MOF-5 keeps its 48 joints, one bond
each.
:::

{term}`Faces <face>` are why MOF-5's clusters alternate.  A tetrahedral
Zn{sub}`4`O
node's opposite carboxylates are a quarter turn apart, so two
neighbouring nodes the *same* way round meet a linker with its two
carboxylates at 90°; in the crystal they are at 0° across all 24
linkers.  Turning every other node is what puts the two carboxylates
on each linker in one plane.

## The cost

```{index} single: pair cost
```

How badly two ends of a joint disagree is one number: the mean squared
difference between the **unit** offsets of their members across the
joint axis, under the best pairing of one end's members with the
other's.  Two things about it are worth knowing:

- The offsets are compared as directions and never as lengths.  The
  two ends of a joint can have quite different spans -- MFU-4l's node
  members are 1.405 Å apart and its linker's 2.861 Å -- so comparing
  the raw offsets leaves a floor that is the span difference and
  nothing to do with orientation.  Normalised, the crystal's own
  orientation scores exactly 0 and a quarter turn exactly 2.
- It is zero when either end presents no frame.  A single atom with no
  face has no offset to disagree about, so a catalogue of such blocks
  reaches none of this and is built exactly as PORMAKE builds it.

*Joint twist left* in the results table is this cost summed over every
edge, after the rule has done what it can.

## The rule: consistent

```{index} single: tie set
```

**Consistent across every joint**, the default since 2026-09-21,
chooses among the tied fits of every node so that the total cost over
every edge is least.  Four things make that safe rather than a second
fit:

The tie set is enumerated, not searched.
: The block's own rotation group -- every proper rotation that maps
  its connection directions onto themselves -- is found from ordered
  *pairs* of connection directions and the normal they span, and
  composed with the fit.  Pairs and never triples, because three
  directions of a planar block span no volume, and triples would call
  a trigonal node unsymmetric.  A rotation counts as one to a
  tolerance of 10⁻³, because a block cut from a real crystal is
  octahedral to about a thousandth of a degree; at 10⁻⁶ the search
  finds only the identity and reads a symmetric block as having no
  symmetry.  Every candidate is then validated by placing it, so the
  placement scored is the placement produced.

A tie is decided by a gap, never by an absolute tolerance.
: The fits are sorted by RMSD and the tie set is everything below the
  first jump of a factor of 100.  The imperfection of a block cut from
  a crystal is around 10⁻⁵ Å, larger than any fixed threshold worth
  writing, while the gap between a fit and a worse one is five orders
  of magnitude.

The search starts from the fit and leaves it only for something strictly cheaper.
: The fit's own permutation is admitted to every node's tie set and
  is where the search begins; a candidate has to be strictly cheaper
  to move a node off it.  *As cheap* is what every net whose edges
  join a node to an image of itself answers, and on such a net "as
  good" would still be a different framework, chosen by nothing.  The
  search takes one rotation per node type first, then descends one
  slot at a time until nothing improves -- for the net whose slots of
  one type are not all alike: an interface, a defect, a repeated cell
  with two blocks in it.

A second pass that fits worse or moves the cell is thrown away.
: The build reaches a second pass only when some node presents a
  frame -- several atoms at a point, or a face -- and the chosen turns
  differ from the fit's; otherwise it returns at the first pass, and
  the log says *the fit had already put the nodes the best way round;
  keeping it*.  The second pass is the same builder with the node
  permutations pinned, and it relaxes the cell again.  It is kept only
  if its worst block fits no worse than the first pass's by more than
  10⁻³ Å, and its cell is the first's to within 0.5 % in every length
  and in volume.  A tie cannot move the cell -- turning MOF-5's
  clusters leaves it unchanged to 2×10⁻¹⁶ -- so a pass that does is
  the relaxation finding a different framework, or collapsing: **dia**
  on **N623** with **E14**, turned, took *b* from 25.2 Å to 0.007 Å
  with every block "fitting" to 10⁻⁴.  Both refusals are said in the
  log (*the turned nodes fit their slots worse (… A against …);
  keeping the fit*; *the turned nodes relaxed to another cell*).

What is scored is the two *nodes* at the ends of an edge, never a
node against its linker: a linker's angle about its own axis is a
continuous freedom and belongs to the next section, while two nodes
presenting faces a quarter turn apart across the same edge is what no
continuous turn can repair.

The worked example in {doc}`mof-builder` shows the rule with nothing
to choose (*Joint twist left* 6.000 over 3 edges on one cell of
**pcu**, where the one slot cannot alternate) and with everything
(0.000 over 24 edges on 2×2×2, against 48 as found).

## The other rule: as-found

**As found by the fit** runs none of this: the framework is byte for
byte what PORMAKE builds, and it is what the application's own
comparison against upstream PORMAKE asks for by name.  It was the
default before 2026-09-21.  Choose it to reproduce an upstream build,
or to see what the default changed.

## A linker's angle about its own axis

```{index} single: linker; angle about its axis
```

A two-connected block's angle about the line through its two points
is **not** "as found", because the fit never found it.  Placing a
block on two directions is a best-fit rotation of two vectors, which
is not uniquely defined -- SciPy says so in a warning you will see in
a command-line build.  So after every build, whatever *Node
orientation* asked for, every two-connected block with a frame to
present is turned about its own axis until its ends face the blocks
they meet.  This is a refinement and not a second fit: both connection
points are on the axis, so a turn about it moves neither, and the RMSD,
the relaxed cell and every fused point stay exactly what they were.

The angle is solved in closed form rather than scanned.  Writing each
member's unit offset across the axis as a complex number $z$ in one
basis shared by both ends, the turn that brings one end's members onto
the other's is

$$
\varphi^{*} = -\arg \sum_{\text{ends}} \sum_{\text{paired members}}
              z_{\text{here}}\, \overline{z_{\text{there}}}
$$ (linker-angle)

because a turn by $\varphi$ multiplies every $z_{\text{here}}$ by
$e^{i\varphi}$, and the sum of squared differences is then least where
$e^{i\varphi}$ times the sum is real and positive.  The pairing of
members is re-solved once at $\varphi^{*}$, since the closed form is
exact only for a fixed pairing.  The cost minimised is the same pair
cost the discrete rule minimises.

Three consequences:

- What turns is asked of the **block** -- two points, and a face at
  one of them -- and never of the slot, so a two-connected *node*
  turns too: Ni{sub}`3`(HITP){sub}`2`'s NiN{sub}`4` sits on a node
  slot and is settled the same way.  On that framework the closed form
  asks for 6×10⁻⁸ radians, which is the crystal's angle, and below
  the threshold at which a block is moved at all.
- **Faces count only under *consistent***.  Under the default a ring
  or a carboxylate at either end is a frame, so **E14** turns until its
  ring lies flat on both carboxylates it meets; under *as-found* only a
  point standing for several atoms is a frame, and no block in
  PORMAKE's database has one, which is what keeps *as-found* PORMAKE's
  build.
- A linker with two-fold symmetry has two equal minima half a turn
  apart, and either is correct; which comes back is decided by the sum
  and so is the same on two runs of one build.  Where the two ends'
  frames cancel exactly -- a symmetric linker meeting a symmetric node
  -- every angle costs the same and the block is left where the fit
  put it.

The log reports the count: *settled 24 block(s) about their own axis,
of 24 that could turn*.

## Settings

*Node orientation* is one parameter of {ref}`Build a framework…
<mod-mof-build>`, `-p orientation=consistent` or `as-found` on the
command line.  The linker's angle has no setting: there is no earlier
decision to be faithful to.

## Limitations

- The rule turns nodes only among the fits that tie.  A node that
  fits its slot loosely, so that only one orientation is within the
  gap, is not turned; and a node whose connection points all stand for
  one atom with no face presents nothing to score.
- The tolerances -- 10⁻³ for a rotation, a factor of 100 for a tie,
  10⁻³ Å and 0.5 % for a second pass -- were measured over PORMAKE's
  database and the sample frameworks; a block much further from ideal
  symmetry than a crystal's own might fall outside them.  The log
  says what was kept and why.
