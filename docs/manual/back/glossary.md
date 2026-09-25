# Glossary

```{glossary}
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
```
