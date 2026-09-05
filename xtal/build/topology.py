"""
xtal.build.topology
===================
An RCSR net as a structure, so that a picture can be made of it.

:mod:`xtal.analysis.topology` is a net as the only thing a net *is* --
a periodic graph, with the cell and the coordinates thrown away.  This
module is the other direction and exists for the other purpose: to
put a named net on screen, where the cell and the coordinates are all
there is.

**The elements are notation, not chemistry.**  A node is a hydrogen
and an edge is a string of heliums, which is what
``resources/topo/Top2Cif.py`` wrote and what the pictures were made
from.  Nothing about it is a claim: the two are the smallest atoms in
the table, so the spheres stay out of the way of the rods, and neither
is a metal, so nothing in :func:`xtal.core.bonding.BondRules.allows`
refuses the pairs.

**The beads are what make the polyhedra work.**  A coordination
polyhedron is drawn over an atom's *neighbours*, so a net drawn as
bare vertices and edges has nothing to put the hull's corners on.  The
bead nearest each node is that corner, which is why the edges are
strings of atoms rather than bonds between distant nodes -- and it is
the whole reason this shape was chosen over the obvious one.

**Recalculate Bonds does not give this back, and cannot.**  The
edges are written here from the net's own edge list, not perceived
from distances, and there is no set of distance criteria that would
do the same job: in **rht** two beads on *different* edges are 0.82 A
apart while a bond along an edge is 1.00, and in **soc** the two
distances are equal.  A rule tuned on **pcu** looks right and is
wrong four nets later.  So the bonds are the generator's answer and
pressing Recalculate Bonds on a drawn net replaces them with
something else.

**Nothing here is stored.**  These structures used to be 2728 files
and 12 MB of generated CIF sitting in the repository; the file they
were generated from is 1.8 MB, ships gzipped at 331 KB, and is read
by :mod:`xtal.io.cgd` already.  All 2726 drawable nets build in 53
seconds, which is 20 ms each -- so there is no cache and no folder.
The outliers are worth knowing rather than guarding against: **fav**
takes 1.7 s because it is 264 sites and 48960 atoms once expanded,
and a net that large is slow to *draw* whatever produced it.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np

from xtal.analysis import rcsr
from xtal.core import bonding, p1, symmetry
from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure

#: A node, and a point along an edge.  See the module docstring: these
#: are notation and the choice is free, but changing them changes every
#: picture and every saved file that came out of here.
NODE_ELEMENT = "H"
EDGE_ELEMENT = "He"

#: The ``.cgd`` cells are normalised so that an edge is about one unit
#: long, which puts every atom on top of every other one.  Eight is the
#: factor ``Top2Cif.py`` used and it is the right one for a reason it
#: did not state: with :data:`BEADS` beads it leaves them almost
#: exactly 1 A apart, which is the separation the drawing reads as a
#: rod rather than as a row of beads.
SCALE = 8.0

#: Beads per edge, counting the two nodes.  Seven atoms are placed
#: between them; the endpoints are already there as nodes.
BEADS = 8

#: Two points are the same atom within this, in Angstrom.  The ``.cgd``
#: coordinates run to five decimals and their symmetry images to rather
#: fewer -- the same tolerance argument :data:`xtal.analysis.rcsr.
#: TOLERANCE` makes, in cartesian rather than fractional terms.
TOLERANCE = 1e-2


class NetDrawingError(ValueError):
    """A net that cannot be drawn, and why.

    Distinct from :class:`xtal.analysis.topology.TopologyError`, which
    is a net that cannot be *keyed*: the two modules fail at opposite
    ends of the same object, and a net can be perfectly drawable and
    unkeyable or the reverse.
    """


def names() -> list[str]:
    """Every net worth offering, in the file's own order.

    The 2-periodic nets and the four with no ``CELL`` are left out
    rather than offered and then refused: a picker whose entries raise
    when they are picked is worse than a shorter picker.

    That is everything knowable without drawing the net.  **thz** is
    still in here and still will not draw, because the only way to
    find that out is to try -- see :func:`structure_for`.  Building
    2727 nets to shorten a list by one is not a trade worth making, so
    it is one failed run rather than a slower dialog.
    """
    return [entry.name for entry in rcsr.nets()
            if entry.dimension == 3 and entry.cell]


def by_name(name: str, scale: float = SCALE,
            beads: int = BEADS) -> Structure:
    """The named RCSR net, drawn.

    The name is the RCSR's own -- ``pcu``, ``acs``, ``dia-b`` -- which
    is what the Net panel reports and what :func:`names` lists.
    """
    try:
        entry = rcsr.nets()[name]
    except KeyError:
        raise NetDrawingError(
            f"no net named {name!r} in the RCSR") from None
    return structure_for(entry, scale, beads)


def structure_for(entry, scale: float = SCALE,
                  beads: int = BEADS) -> Structure:
    """The net of one ``.cgd`` entry, as a structure with its bonds.

    The bonds are set here and not perceived later, which is the rule
    every generated structure in this application works to: an atom
    arrives with the bonds whatever made it gave it.  Writing them is
    also the only check this performs -- every point of every edge has
    to be findable in the expanded cell, and **thz** is the one net of
    2727 where one is not.
    """
    if entry.dimension != 3:
        raise NetDrawingError(
            f"{entry.name} is a {entry.dimension}-periodic net, and "
            "only 3-periodic nets have a cell to draw in")
    if not entry.cell:
        raise NetDrawingError(
            f"{entry.name} carries no CELL, so there is no cell to "
            "draw it in")
    if beads < 2:
        raise NetDrawingError("an edge needs at least two beads")

    structure = _sites(entry, scale, beads)
    structure, _report = symmetry.merge_duplicates(structure,
                                                   tol=TOLERANCE)
    structure.set_bonds(_edge_bonds(structure, entry, beads))
    structure.meta["title"] = entry.name
    structure.meta["topology"] = entry.name
    return structure


def _sites(entry, scale: float, beads: int) -> Structure:
    """The asymmetric unit: a node per vertex, beads along each edge.

    The beads are the *interior* points of the edge and not its ends.
    ``Top2Cif.py`` placed one at each of ``n/beads`` for ``n`` up to
    and including ``beads``, so its last bead landed exactly on the far
    node -- in the ``acs.cif`` it wrote, ``He8`` is a symmetry image of
    ``H0``.  A duplicate atom inside a picture is invisible and inside
    a structure is not.
    """
    a, b, c, alpha, beta, gamma = entry.cell
    lattice = Lattice.from_parameters(a * scale, b * scale, c * scale,
                                      alpha, beta, gamma)
    sites = [Site(element=NODE_ELEMENT, frac=list(node.frac),
                  label=f"{NODE_ELEMENT}{i + 1}")
             for i, node in enumerate(entry.nodes)]
    count = 0
    for start, end in entry.edges:
        for point in _chain(start, end, beads)[1:-1]:
            count += 1
            sites.append(Site(element=EDGE_ELEMENT, frac=list(point),
                              label=f"{EDGE_ELEMENT}{count}"))
    return Structure(lattice=lattice, sites=sites,
                     space_group=SpaceGroup.from_name(entry.group))


def _chain(start, end, beads: int) -> list[np.ndarray]:
    """Both nodes and every bead between them, in order along the
    edge."""
    start, end = np.asarray(start, float), np.asarray(end, float)
    return [start + (end - start) * n / beads
            for n in range(beads + 1)]


def _edge_bonds(structure: Structure, entry, beads: int) -> list:
    """One bond per consecutive pair along every edge of the net.

    Written rather than perceived because the edges are known: this
    module put the beads there and does not have to find them again by
    distance.  What it does have to do is name each bond in the
    asymmetric unit's terms, and
    :func:`xtal.core.bonding.bond_between` is that -- it takes two
    atoms of the expanded cell and gives back the ``(site, site,
    image, operation)`` the structure stores, which is the same
    question a user drawing a bond in the viewport asks.

    Duplicates are dropped rather than refused.  Every edge of the net
    appears once in the file and many times in the cell, so the same
    stored bond is reached from several of them, and
    :meth:`~xtal.core.structure.Structure.add_bond` would silently
    discard the repeats anyway.
    """
    cell = p1.expand(structure)
    bonds, seen = [], set()
    for start, end in entry.edges:
        found = [_locate(cell, structure.lattice, point)
                 for point in _chain(start, end, beads)]
        if any(atom is None for atom, _image in found):
            raise NetDrawingError(
                f"{entry.name}: a point on one of its edges is not in "
                "the expanded cell, so the net cannot be drawn")
        for (i, image_i), (j, image_j) in pairwise(found):
            bond = bonding.bond_between(structure, cell, i, j,
                                        image_i, image_j)
            key = (bond.i, bond.j, bond.image, bond.op)
            if key not in seen:
                seen.add(key)
                bonds.append(bond)
    return bonds


def _locate(cell, lattice, point):
    """Which atom of the expanded cell a point is, and in which image.

    The image is the half a plain lookup throws away: a bead at
    ``(1.1, 0, 0)`` is the atom at ``(0.1, 0, 0)`` seen one cell along,
    and a bond drawn to the wrong one of those is a bond drawn across
    the whole crystal.
    """
    delta = cell.frac - point
    delta -= np.round(delta)
    distance = np.linalg.norm(delta @ lattice.matrix, axis=1)
    hit = int(np.argmin(distance))
    if distance[hit] > TOLERANCE:
        return None, None
    return hit, tuple(int(v) for v in np.round(point - cell.frac[hit]))
