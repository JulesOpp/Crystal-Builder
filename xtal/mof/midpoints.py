"""
xtal.mof.midpoints
==================
PORMAKE's reading of a net, with a third way to find its edges.

PORMAKE writes a net as nodes and edge centres and pairs them by
distance: every centre within 0.5 of a node (after scaling the
shortest edge to one), and failing that the two nearest nodes within
0.7.  Both assume every edge is about as long as every other.  A
merged net is not: sph's two edges are 1 : sqrt(3), and 180 of the 291
merged nets of Jiang et al. (2024) that only the paper has were
refused that way -- as nia-d was, and the decorated nets' long filler
edges.

The third reading is exact whatever the lengths: **an edge centre's
two nodes are the nearest pair it is halfway between.**  The file
puts the centre at the midpoint, so the displacements to its two
nodes cancel; a further pair cancelling too would be two nodes
symmetric about the same point, always further out.  It is tried only
after both of PORMAKE's own fail, so a net that read before reads as
it did, to the bit, and PORMAKE's own validity check still decides.

A subclass made here rather than an edit to the vendored file, which
stays as PROVENANCE.md records it.  ``Topology.__mul__`` copies the
object, so a repeated net reads the same way.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

#: How close two displacements must come to cancelling, in the net's
#: own units (the shortest edge is one).
CANCEL = 1e-3

#: How many nearest nodes of a centre are paired up.
CANDIDATES = 24


@lru_cache(maxsize=1)
def topology_class(pormake):
    """``pormake.Topology`` with the midpoint reading as a last
    resort.  ``reader(pormake, ends)`` is the one to construct."""

    class Topology(pormake.Topology):
        #: A callable giving each EDGE line's two node lines, asked
        #: only when the midpoint reading runs.
        edge_ends = None

        def update_properties(self):
            try:
                super().update_properties()
                return
            except Exception:                       # noqa: BLE001
                ends = self.edge_ends() if self.edge_ends else None
                found = midpoint_list(self.atoms, ends)
            if found is None:
                raise Exception(f"Invalid cgd file: {self.name}")
            self.neighbor_list = found
            if not self.check_validity():
                raise Exception(f"Invalid cgd file: {self.name}")
            self.calculate_properties()

    Topology.__qualname__ = "Topology"
    return Topology


def reader(pormake, ends=None):
    """The class to read one net with: ``ends`` is a callable giving
    each EDGE line's ``(node line, node line)``, which tells two
    pairs of nodes about one centre apart (thw: the centre between
    two 10-c vertices is also halfway between two 3-c ones, and no
    edge joins two 3-c)."""
    base = topology_class(pormake)
    if ends is None:
        return base
    return type("Topology", (base,), {"edge_ends": staticmethod(ends)})


def edge_ends(entry) -> tuple[tuple[int, int], ...]:
    """Each EDGE line of ``entry`` as the two node lines it joins."""
    from xtal.analysis.rcsr import resolved, space_group_operations

    symbol = resolved(entry)[2]
    ops = space_group_operations(symbol)
    nodes = [np.asarray(n.frac, dtype=float) for n in entry.nodes]

    def line_of(point):
        point = np.asarray(point, dtype=float)
        for n, here in enumerate(nodes):
            for rot, trans in ops:
                delta = rot @ here + trans - point
                if np.allclose(delta - np.round(delta), 0, atol=1e-4):
                    return n
        return -1

    return tuple((line_of(a), line_of(b)) for a, b in entry.edges)


def midpoint_list(atoms, ends=None):
    """A ``NeighborList`` pairing each edge centre with the nearest
    two nodes whose midpoint it is -- of the two node kinds its EDGE
    line joins, when ``ends`` says -- or ``None`` when one has
    none."""
    from scipy.spatial import cKDTree

    from xtal.mof.pormake.neighbor_list import Neighbor, NeighborList

    symbols = np.asarray(atoms.get_chemical_symbols())
    positions = atoms.get_positions()
    cell = np.asarray(atoms.cell)
    nodes = np.flatnonzero(symbols == "C")
    centres = np.flatnonzero(symbols == "O")
    shifts = np.array(list(np.ndindex(3, 3, 3))) - 1
    images = np.vstack([positions[nodes] + s @ cell for s in shifts])
    owner = np.tile(nodes, len(shifts))
    tags = atoms.get_tags()
    tree = cKDTree(images)
    found = [[] for _ in range(len(atoms))]
    k = min(CANDIDATES, len(images))
    for centre in centres:
        here = positions[centre]
        _d, near = tree.query(here, k=k)
        steps = images[near] - here
        line = -int(tags[centre]) - 1
        wanted = (sorted(ends[line]) if ends is not None
                  and 0 <= line < len(ends) else None)
        best = None
        for a in range(len(near)):
            for b in range(a + 1, len(near)):
                if np.abs(steps[a] + steps[b]).max() > CANCEL:
                    continue
                kinds = sorted((int(tags[owner[near[a]]]),
                                int(tags[owner[near[b]]])))
                if wanted is not None and kinds != wanted:
                    continue
                length = float(np.linalg.norm(steps[a]))
                if best is None or length < best[0]:
                    best = (length, a, b)
        if best is None:
            return None
        for at in best[1:]:
            node, step = int(owner[near[at]]), steps[at]
            found[centre].append(Neighbor(node, step))
            found[node].append(Neighbor(int(centre), -step))
    made = NeighborList.__new__(NeighborList)
    made._neighbor_list = found
    made.max_index = len(found) - 1
    return made
