# Glossary

```{glossary}
:sorted:

Asymmetric unit
  The smallest set of sites from which the space group's operations
  generate every atom of the cell.

Building block
  A molecule with connection points, written as the ``.xyz`` PORMAKE
  reads.  A node block goes on a vertex of the net, a linker on an
  edge, and a block fits a slot when it has as many connection points
  as the slot is coordinated.

Connection point
  A dummy atom, ``X``, standing 0.75 Å from the atoms of a building
  block that the next block attaches to.  Two blocks are joined by
  fusing their connection points.

Dummy atom
  An atom of element ``X``: a marker, not chemistry.  Perception never
  bonds one, a force field sets it aside, and net edges and
  measurements take it like any other atom.  A centroid and a
  connection point are both dummy atoms.

Net
  The periodic graph a framework reduces to once its vertices and
  edges have been chosen: the drawn topology bonds, named against the
  RCSR by coordination sequence and point symbol.

Topology bond
  An edge of the net drawn over a structure, thick and translucent,
  over the real bonds rather than in place of them.  It is stored
  against the asymmetric unit like any bond, so it expands over the
  symmetry orbit, and it is invisible to every chemical question.

Workspace
  The folder a session works in.  Every structure opened, built or
  started in it gets a folder of its own, and every run is filed
  under the structure it was run against.

P1
  The space group with no symmetry but the lattice translations.  A
  structure in P1 lists every atom of the cell as its own site.

Space group
  The group of symmetry operations -- rotations, reflections,
  translations and their combinations -- that maps a crystal onto
  itself.

Special position
  A point that one or more of the space group's operations, other
  than the identity, map onto itself.  An atom there has fewer
  symmetry-equivalent copies in the cell than one on a general
  position.

Wyckoff position
  A set of points in the cell with the same site symmetry, labelled
  by a letter in the International Tables.

Atom type
  The label a force field gives an atom -- its element and bonding
  environment, such as `C_3` or `C_R` in UFF -- which decides every
  parameter applied to it.  A wrong type gives a plausible number, not
  an obvious error.

Charge equilibration
  Setting atomic charges from the geometry so that every atom has the
  same electronegativity while the whole stays neutral.  QEq and EQeq
  are the two methods offered.

Disorder
  A structure in which some sites are occupied in only a fraction of
  the cells, as the refinement found them.  *Prepare for simulation*
  orders it into whole atoms.

Dispersion correction
  An energy term added to a method to account for dispersion (van der
  Waals attraction), such as D3 with Becke-Johnson damping.

Foundation model
  A machine-learned potential fitted once over a public dataset of many
  materials, not to one system.

Holonomic constraint
  A coordinate held at a value during a relaxation by projecting it
  out of each step and restoring it, rather than by freezing the atoms
  that define it.

Hysteresis
  The difference between the two branches of a scan walked in both
  directions, reported apart rather than averaged.

Interpenetration
  Copies of a framework threaded through each other's pores.  Class Ia
  copies are related by a translation of the whole array; Class II by
  an operation that is not a translation.

Minimum image
  The shortest distance between two atoms over all lattice
  translations: the one every measurement reports.

Occupancy
  The fraction of cells in which a site is present, as refined.  An
  engine given a partially occupied site counts it as a whole atom.

Orbit
  Every atom of the cell that the space group's operations generate
  from one site.  Edits act on whole orbits.

Relaxed scan
  A coordinate set to each of a list of values, everything else relaxed
  at each value, the energies forming a landscape.

Residual stress
  The largest component of the stress the cell can still relax, with
  the part the space group forbids removed and any applied pressure
  included, in GPa.

Session
  What a project holds beyond the structure: the view, the selection,
  measurements, planes and atom-type overrides.

Slater-Koster file
  The parameters a DFTB calculation needs for one pair of elements,
  downloaded as part of a parameter set.

Standard setting
  The conventional cell and origin of a space group, as spglib defines
  them.  Find symmetry can re-express a cell in it.

Suppressed bond
  A bond you deleted, stored so that perception cannot put it back and
  saved with the project.  Reset bonds to automatic removes it.

Symmetry-adapted strain
  A strain of the cell that the space group's point group leaves
  unchanged: the only kind a cell relaxation may use.

Accessible surface area
  The area a probe's centre can touch, counted over the channels only.
  Quoted against a probe radius.

Attachment
  One connection point together with the distinct atoms bonded to it:
  monodentate with one atom, polydentate with several.

Channel
  A void a probe can reach from outside the cell: it continues into its
  own periodic image.  A void that does not is a pocket.

Coordination sequence
  The number of vertices exactly *k* edges from a vertex of a net, for
  *k* = 1, 2, 3 ..., on the infinite net.

Distance grid
  A field, on a grid over the cell, of the distance to the nearest atom
  surface.  The grid-based porosity entries and the pore surface are
  read off it.

Face
  The plane a connection point presents when its atom has exactly two
  other neighbours.  Faces across a joint are scored, never bonded.

Joint
  Two connection points fused in a build, bonded with as many bonds as
  the two ends have members.

Largest free sphere
  $D_f$: the diameter of the biggest sphere that can pass all the way
  through the framework -- what decides what it will admit.

Largest included sphere
  $D_i$: the diameter of the biggest cavity in the crystal, reachable
  or not.

Layer net
  A 2-periodic net.  A framework built on one is stacked along *c*
  after the build, one spacing between the sheets' mean planes.

Pocket
  A void a probe cannot reach from outside the cell.  Its volume is
  not counted as accessible.

Point symbol
  For each pair of edges at a vertex of a net, the size of the smallest
  ring containing both, with multiplicities.

Probe-occupiable volume
  The volume a probe of a given radius occupies within the channels,
  as distinct from the volume its centre can reach.

Probe radius
  The radius of the sphere standing for a gas molecule.  Every
  porosity number is quoted against one.

Slot
  A node type, or a kind of edge, of a net, for which a building block
  has to be chosen.

Systematic absence
  A reflection the space group's symmetry forbids: its intensity is
  zero whatever the atoms.

Transitivity
  Four numbers [p q r s]: how many kinds of vertex, edge, face and
  tile a net has, from the RCSR.
```
