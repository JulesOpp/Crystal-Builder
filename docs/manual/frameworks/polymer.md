(frameworks-polymer)=
# The polymer builder

The polymer builder packs chains of a repeat unit into a periodic box
or a membrane at a density you choose, as a starting model for a
force field.  After this section you can describe a monomer, build a
homopolymer or a copolymer of any tacticity, build a ladder polymer
such as PIM-1, make a free-standing film, read what the report says
about the chains, and know exactly how much that model is and is not.

```{index} single: polymer builder
```
```{index} single: amorphous polymer
```
```{index} single: monomer; head and tail
```
```{index} single: PIM-1
```

:::{warning}
**A polymer model here is packed, not equilibrated, and says so.**
It has the density you asked for and no close contacts.  Its chains
have the local shape the torsion statistics gave them and have not
relaxed at the scale of a chain: how entangled they are is a question
for molecular dynamics, which this application does not run.  The
last line of every report says this, and for a ladder polymer adds
that its measured density is reached in the literature by MD
compression.
:::

## What it does

The module is *Modules ▸ Polymer builder ▸*
{ref}`Build an amorphous polymer… <cmd-module.polymer.build>`, and
needs the `build` extra (RDKit), like the {doc}`molecule-builder`.

A **monomer** is one repeat unit with two connection points: the
**head**, where it is bonded to the unit before it, and the **tail**,
where the next unit is bonded to it.  In a SMILES string `[*:1]` is
the head and `[*:2]` the tail; an unnumbered string goes by the order
the stars were written, which is all the sketch canvas can say.
`[*:1]CC([*:2])C` is polypropylene with its methyl on the tail carbon,
and a chain of it is head to tail without anything having to say so.
A third connection point is refused by name -- branching is a
different generator, not a walk.

Where the monomer comes from, in the **Monomer** box:

- **The library**: Polyethylene, Polypropylene, Polystyrene, PMMA, PVC,
  PEO, PTFE, PET, Nylon-6, PIM-1 and PIM-EA-TB.
- **A SMILES string** with the two stars, typed or drawn in the 2D
  sketcher (the same sketcher the {doc}`molecule builder
  <molecule-builder>` uses: a right-click on a connection point says
  whether it is the head or the tail).
- **A block file** with two connection points, the first the head.
- **A monomer you saved**: draw the repeat unit in a tab, then use
  *Structure ▸ Building blocks ▸* {ref}`Save as a monomer…
  <cmd-save_monomer>`, which asks which connection point is the head.
  It is written to the workspace's monomers and the polymer builder
  lists it beside its own.

### Joining, and the freedom a joint has

A joint is built from bond lengths -- the sum of the two covalent radii
{cite}`cordero2008` -- never by making two connection points
coincide, because a connection point sits 0.75 Å from its atoms and
that is a convention about direction.  At a **single** joint what is
left free is the torsion about the new bond, which is what a chain's
conformation is made of.  The ends of a finished chain are capped with
hydrogen, so no connection point survives into a built model.

A **ladder** monomer such as PIM-1 is one whose connection point
stands for *two* atoms: its head is bonded to both oxygens of a
catechol and its tail to the two carbons the next unit's oxygens meet.
A ladder joint has no torsion -- two bonds hold the units in one plane
-- and the freedom is which tail atom meets which head atom, the cis
or trans of PIM-1.  A ladder monomer mixed with an ordinary one in a
copolymer is refused.

### Copolymers and tacticity

Two independent choices are made for every unit before any geometry.

Composition
: **Homopolymer**, or a copolymer of the monomer and a **Second
  monomer**: *Alternating A-B*, *Random* (with the **Fraction of A**),
  or in *Blocks* of the lengths given, repeated down the chain.  The
  box is sized by the units' expected numbers, not by a plain mean of
  the masses, which would mis-size a block copolymer.

Tacticity
: Whether each unit has the same hand as the one before it:
  *Isotactic* is all the same, *Syndiotactic* all alternating, and
  *Atactic* is the same with probability **p(meso)** -- 0.5, the
  default, is what a free-radical polymerisation gives, near enough.
  A monomer with no stereocentre, like polyethylene, has nothing to
  choose, and asking changes nothing.

A seed builds the same chain twice.

## How the box is packed

All the chains grow at once.  Each starts from a seed at a random place
and turn, and the chains then take one unit each in a shuffled round
until all are full: grown one at a time, the first would wander through
an empty box and the last would be pushed into whatever holes were
left, which models the order of building rather than a melt.  This is
the argument Theodorou and Suter made for Amorphous Cell
{cite}`theodorou1985`.

Each unit is added by **configurational-bias growth**
{cite}`rosenbluth1955,siepmann1992`: it is tried at **Trials per
step** torsions about its joint bond, and one is taken with a weight
made of its soft overlap with everything already in the box and a
three-fold torsion term that favours trans and gauche over eclipsed.
Without that term the chain is freely rotating, which is too coiled by
half.  A chain that jams gives units back and tries again; the box is
grown at a lower density than the target (*Grow at*; 0 chooses three
quarters of the target, or 0.2 g/cm³ for a ladder) because a hard core
at a melt's density leaves no room for the atoms of one step.

The core is soft while growing, so what overlap remains is taken out by
the **push-off** of Auhl and co-workers {cite}`auhl2003`: positions are
moved holding every bond and angle at the length it was built with, the
cell fixed, until no two atoms three bonds apart or more are closer
than a fraction of their van der Waals radii.  If the box was grown
loose it is compressed to the target by the same minimisation.  It is
not a force field and gives no energy anyone should quote; it is there
so that the first force-field step on the model is not an explosion.

:::{note}
**A polymer build's bonds are the chains' own.**  They are written as
the structure's stored graph and never perceived, no connection point
is left, and a membrane has no bond across *c*.  Use the Force Field
panel on the result afterwards, as with any structure; a force field
never changes the bonds.
:::

### A membrane

**Periodicity ▸ Membrane** grows the chains between two repulsive
walls at the faces of a film **Membrane thickness** thick, periodic in
*a* and *b*, and adds **Vacuum** along *c*, split either side.  Its
surfaces are the chains' own rather than a cut through a bulk box, and
no bond crosses *c*.

## Building one

1. Choose the **Monomer** (and a **Second monomer** for a copolymer),
   the **Composition** and **Tacticity**.
2. **Chains** and **Units per chain** set the size; **Density** is the
   target in g/cm³.  The dialog's help lists amorphous densities
   near room temperature: PE and PP 0.85, PS 1.05, PMMA 1.18,
   PVC 1.39, PEO 1.13, PTFE 2.0, PET 1.33, nylon-6 1.08, PIM-1 1.06.
3. **Push-off steps** and **Trials per step** trade time for room in a
   full box.  **Most atoms** refuses a recipe that would make more
   before anything is grown.
4. **Run**.  The model opens in a tab of its own in {term}`P1`, with
   the report in the Results panel.  *Stop* is honoured between steps.

On the command line it is `xtal run polymer.build`, which builds and so
takes no file.  Six chains of twenty polyethylene units, at the
default density:

```console
$ xtal run polymer.build -p chains=6 -p length=20 -o pe.cif
[...]
6 chains of 20 Polyethylene, homopolymer: 732 atoms
cell 18.74 x 18.74 x 18.74 A, P1
density 0.853 g/cm3 (asked 0.85)
grown at 0.637 g/cm3 and compressed to the target by minimisation
closest non-bonded contact 2.11 A, 0.88 of the van der Waals sum
<R^2>^1/2 19.9 A, Rg 7.7 A, C_19 3.70 over the chains' segments of 19 backbone bonds (freely rotating 2.14)
packed, not equilibrated: the density and contacts are a starting model's, and the chains have not relaxed at their own scale -- [...]
[...]
wrote pe.cif
```

A ladder, three chains of four PIM-1 units at its literature density:

```console
$ xtal run polymer.build -p monomer=PIM-1 -p chains=3 -p length=4 -p density=1.06 -o pim.cif
PIM-1: 3 chains of 4, 672 atoms at 1.062 g/cm3
[...]
Grown at                         0.200  g/cm3
Closest contact                   2.67  A
Meso dyads                          67  %
[...]
```

These are small on purpose: a model to judge a chain's statistics from
has hundreds of units: ten chains of a hundred polyethylene units are
6000 atoms and about twenty seconds.

## What the report says

What was built
: The monomer, chains and units, atoms, the cell, the density reached
  against the one asked, the density it was grown at, and the closest
  non-bonded contact -- as a distance and, for a chain, as a fraction
  of the van der Waals sum.  Tacticity prints the share of meso
  dyads when the monomer has a stereocentre.

Chains
: The root-mean-square end-to-end distance and the radius of gyration
  Rg, and for a chain with a single-bond backbone the **characteristic
  ratio** C{sub}`n` = ⟨R²(n)⟩ / (n l²), averaged over every segment of *n*
  bonds inside every chain (*n* half a chain's backbone) because ten
  end-to-end distances carry a quarter of their mean as noise.  It is
  set beside the freely rotating chain's at the same bond angle -- 2.0
  at the tetrahedral angle, against about 7 for a polyethylene melt --
  which is what a chain with no preference among its torsions would
  give.  A ladder's backbone does not run unit to unit through one
  bond, so it gets R and Rg and no C{sub}`n`.

End-to-end distance
: A histogram over the chains.

Speared rings
: A ring pierced by a bond is a knot no relaxation undoes.  Growth
  cannot make one, but compression and the push-off can, so they are
  counted and the report says when there are any.

## Practical notes

- Use more chains of fewer units to see the packing, fewer chains of
  more units to see a chain's statistics; the statistics of a few
  short chains are noisy, and that is what the seed is for.
- A recipe too full to grow into is said as such (the builder was
  jammed at the density it was *grown* at) and is worth retrying with
  a lower **Grow at**, which a refusal is not.
- Chains grown through a ring cannot be pushed out of it; the
  closest contact it could not clear is reported.
- A force-field relaxation of the result is the next step, with an
  engine chosen in the Force Field panel.  The Larsen--Lin--Colina
  21-step compression scheme {cite}`larsen2011polymer` exists in the
  code only as a table of stages for a future equilibrator; nothing
  runs it.

## Samples

*Open Sample ▸ Polymers* opens three crystalline polymers from the
literature -- polyethylene, isotactic polypropylene and cellulose
I-β -- as the starting point for a crystalline comparison, which is a
different thing from the amorphous model built here.

## Settings

The parameters are listed under {ref}`Build an amorphous polymer…
<mod-polymer-build>` in the generated reference, and the module is
{ref}`Polymer builder <mod-polymer>`.

## Limitations

- **Packed, not equilibrated**, as above.  Do not quote a property
  of the model that depends on entanglement or relaxation.
- No branching, crosslinking or reactive bonding: a monomer has
  exactly two connection points.
- Statistics from a small box are noisy; the characteristic ratio
  needs enough chains and units to mean anything.
- The push-off is geometric, with no energy; chemical realism of
  contacts beyond "no overlap" comes from the force field afterwards.
- The monomer's geometry is RDKit's, one conformer, so a monomer with
  many free torsions starts from one of them, and the packer
  samples the rest.
