"""
xtal.carbon.lattice
===================
A triangulated sheet to carbon: the dual, pruned, and terminated.

**The dual is the chemistry.**  Every triangle is a carbon at its
middle and every edge two triangles share is a bond between them, so
every carbon of a closed sheet has three neighbours and every vertex of
valence *n* is an *n*-membered ring.  Where the sheet was cut into
ribbons a triangle has an open side, and its carbon is two-coordinate:
an edge carbon, which is what the terminations go on.  A carbon left
with one neighbour is a dangling end no ribbon has, and is pruned, as
often as pruning makes another.

**One piece.**  Only the largest connected piece is kept, and it must
run on through all three pairs of cell faces
(:func:`periodicity`): a disordered carbon of separate fragments is a
model nobody can make, and saying so is what this builder is for.

**Bonds are stated, never perceived.**  The graph is the dual's,
written as the structure's stored graph the way a MOF build's is
(:func:`structure_of`), so Recalculate Bonds is still how a person asks
for distance instead.  A curved sheet's carbons are closer across a
pore than a bond in places, and perceiving it would bond them.

**Edges are terminated by the ratios asked for**, per carbon of the
result: hydrogen, fluorine, hydroxyl, carbonyl, and the ring ether --
an edge carbon made oxygen, which keeps the ring and takes the
carbon's place, as a pyran's oxygen does.  Edge carbons beyond what the
ratios ask for are left bare, as the example ZTC has forty of; a ratio
there are too few edge carbons for is filled as far as it goes and
said.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from xtal.carbon.mesh import Mesh

#: Bond lengths a termination is placed at, Angstrom.  Placed, not
#: relaxed: the relaxation that follows owns the geometry.
C_H = 1.09
C_F = 1.35
C_OH = 1.36
O_H = 0.97
C_O_DOUBLE = 1.23

#: What each termination puts on an edge carbon, in the order they
#: are handed out -- the ring ether first, because it changes which
#: atoms are carbon and so the count every other ratio is taken of.
KINDS = ("ether", "carbonyl", "hydroxyl", "fluorine", "hydrogen")


@dataclass
class Sheet:
    """Carbon of a dualised mesh: ``frac`` wrapped positions, ``bonds``
    (M, 2) and their ``images`` (M, 3), and each carbon's ``normal``
    -- its triangle's, which is the way out of the sheet."""

    matrix: np.ndarray
    frac: np.ndarray
    bonds: np.ndarray
    images: np.ndarray
    normal: np.ndarray

    @property
    def n_atoms(self) -> int:
        return len(self.frac)

    def degree(self) -> np.ndarray:
        out = np.bincount(self.bonds.reshape(-1),
                          minlength=self.n_atoms)
        return out

    def subset(self, keep) -> Sheet:
        """The carbons ``keep`` marks, and the bonds among them."""
        keep = np.asarray(keep, bool)
        index = np.cumsum(keep) - 1
        mask = keep[self.bonds[:, 0]] & keep[self.bonds[:, 1]]
        return Sheet(self.matrix, self.frac[keep],
                     index[self.bonds[mask]], self.images[mask],
                     self.normal[keep])

    def vectors(self) -> np.ndarray:
        """Each bond as a cartesian vector from its first atom."""
        a, b = self.bonds[:, 0], self.bonds[:, 1]
        return (self.frac[b] + self.images - self.frac[a]) @ self.matrix


def dual(mesh: Mesh) -> Sheet:
    """A carbon at the middle of every triangle, bonded across every
    edge two triangles share, with the translation between them."""
    corners = mesh.frac[mesh.tri] + mesh.shift          # (T, 3, 3)
    middle = corners.mean(axis=1)
    home = np.floor(middle)
    frac = middle - home
    keys, side_edge, counts = mesh.edges()
    order = np.argsort(side_edge, kind="stable")
    edge_of = side_edge[order]
    first = np.flatnonzero((edge_of[:-1] == edge_of[1:])
                           & (counts[edge_of[:-1]] == 2))
    s1, s2 = order[first], order[first + 1]
    t1, k1 = s1 // 3, s1 % 3
    t2, k2 = s2 // 3, s2 % 3
    # Side k1 of t1 runs a to b and side k2 of t2 runs b to a, so a is
    # corner k1 of the one and corner k2 + 1 of the other; the
    # difference of their translations carries t2 into t1's frame.
    frame = mesh.shift[t1, k1] - mesh.shift[t2, (k2 + 1) % 3]
    images = home[t2] + frame - home[t1]
    corners_cart = corners @ mesh.matrix
    normal = np.cross(corners_cart[:, 1] - corners_cart[:, 0],
                      corners_cart[:, 2] - corners_cart[:, 0])
    normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-12)[:, None]
    return Sheet(mesh.matrix, frac, np.column_stack([t1, t2]),
                 images.astype(int), normal)


def prune(sheet: Sheet) -> Sheet:
    """No carbon with fewer than two carbon neighbours, however many
    rounds that takes: a carbon on one bond is a dangling end."""
    while sheet.n_atoms:
        low = sheet.degree() < 2
        if not low.any():
            break
        sheet = sheet.subset(~low)
    return sheet


def largest_piece(sheet: Sheet) -> Sheet:
    """The biggest connected piece, alone."""
    if not sheet.n_atoms:
        return sheet
    n = sheet.n_atoms
    graph = coo_matrix((np.ones(len(sheet.bonds)),
                        (sheet.bonds[:, 0], sheet.bonds[:, 1])),
                       shape=(n, n))
    _count, labels = connected_components(graph, directed=False)
    biggest = np.argmax(np.bincount(labels))
    return sheet.subset(labels == biggest)


def pieces(n_atoms: int, bonds, images=None) -> int:
    """How many connected pieces a graph of ``n_atoms`` is in."""
    if not n_atoms:
        return 0
    bonds = np.asarray(bonds, int).reshape(-1, 2)
    graph = coo_matrix((np.ones(len(bonds)), (bonds[:, 0], bonds[:, 1])),
                       shape=(n_atoms, n_atoms))
    return int(connected_components(graph, directed=False)[0])


def periodicity(n_atoms: int, bonds, images) -> int:
    """In how many independent directions a periodic graph runs on
    through the cell faces: 3 for a framework that percolates in all
    of them.  Each atom is placed in an image as it is reached; one
    reached again in another image closes a loop round the cell, and
    the rank of those loops is the answer."""
    bonds = np.asarray(bonds, int).reshape(-1, 2)
    images = np.asarray(images, int).reshape(-1, 3)
    adjacency: list = [[] for _ in range(n_atoms)]
    for (a, b), image in zip(bonds, images, strict=True):
        adjacency[a].append((b, image))
        adjacency[b].append((a, -image))
    where: dict = {}
    loops = []
    for start in range(n_atoms):
        if start in where:
            continue
        where[start] = np.zeros(3, int)
        stack = [start]
        while stack:
            u = stack.pop()
            for v, image in adjacency[u]:
                at = where[u] + image
                if v not in where:
                    where[v] = at
                    stack.append(v)
                elif np.any(at != where[v]):
                    loops.append(at - where[v])
                    if len(loops) % 64 == 0 and np.linalg.matrix_rank(
                            np.array(loops)) == 3:
                        return 3
    if not loops:
        return 0
    return int(np.linalg.matrix_rank(np.array(loops)))


# ======================================================================
#  TERMINATION
# ======================================================================

@dataclass
class Ratios:
    """What the edges carry, per carbon of the result."""

    hydrogen: float = 0.07          # H/C, counting the hydroxyls' H
    fluorine: float = 0.0           # F/C
    oxygen: float = 0.0             # O/C
    ether: float = 0.8              # of the oxygen: in a ring
    hydroxyl: float = 0.18          # of the oxygen: C-OH
    carbonyl: float = 0.02          # of the oxygen: C=O

    def wanted(self, carbons_before: int) -> dict:
        """How many of each kind, for a sheet of ``carbons_before``
        carbons, before any edge carbon has been made an ether
        oxygen.  The ethers come out of the carbon they are counted
        against, so their number solves ``n = r (C - n)``."""
        split = np.array([self.ether, self.hydroxyl, self.carbonyl],
                         float)
        split = split / split.sum() if split.sum() > 0 else split
        r_ether = self.oxygen * split[0]
        ether = int(round(r_ether * carbons_before / (1.0 + r_ether)))
        carbons = carbons_before - ether
        hydroxyl = int(round(self.oxygen * split[1] * carbons))
        return {
            "ether": ether,
            "carbonyl": int(round(self.oxygen * split[2] * carbons)),
            "hydroxyl": hydroxyl,
            "fluorine": int(round(self.fluorine * carbons)),
            "hydrogen": max(0, int(round(self.hydrogen * carbons))
                            - hydroxyl),
        }


@dataclass
class Terminated:
    """The atoms and bonds of a terminated sheet, and what was put
    where."""

    matrix: np.ndarray
    elements: list
    frac: np.ndarray
    bonds: np.ndarray
    images: np.ndarray
    counts: dict = field(default_factory=dict)
    wanted: dict = field(default_factory=dict)
    edge_carbons: int = 0
    bare: int = 0

    @property
    def short(self) -> dict:
        """The kinds there were too few edge carbons for, and by how
        many."""
        return {k: self.wanted[k] - self.counts.get(k, 0)
                for k in self.wanted
                if self.counts.get(k, 0) < self.wanted[k]}


def terminate(sheet: Sheet, ratios: Ratios, rng) -> Terminated:
    """Every two-coordinate carbon given what the ratios ask for, out
    along the bisector of its two bonds and in the sheet's plane, in a
    seeded order; the rest left bare.

    An ether oxygen never goes next to another: two edge carbons made
    oxygen side by side would be a peroxide in a ring.
    """
    degree = sheet.degree()
    edge = np.flatnonzero(degree == 2)
    wanted = ratios.wanted(sheet.n_atoms)
    vectors = sheet.vectors()
    a, b = sheet.bonds[:, 0], sheet.bonds[:, 1]
    outward = np.zeros((sheet.n_atoms, 3))
    np.add.at(outward, a, vectors / np.linalg.norm(
        vectors, axis=1)[:, None])
    np.add.at(outward, b, -vectors / np.linalg.norm(
        vectors, axis=1)[:, None])
    outward = -outward
    neighbours: list = [[] for _ in range(sheet.n_atoms)]
    for i, j in zip(a, b, strict=True):
        neighbours[i].append(j)
        neighbours[j].append(i)

    matrix = np.asarray(sheet.matrix, float)
    inverse = np.linalg.inv(matrix)
    kind_of = {}
    order = list(rng.permutation(edge))
    ether_at = set()
    room = _Room(sheet, outward)
    for kind in KINDS:
        need = wanted[kind]
        left = []
        for atom in order:
            if need and (not any(n in ether_at
                                 for n in neighbours[atom])
                         if kind == "ether" else room.take(atom, kind)):
                kind_of[atom] = kind
                need -= 1
                if kind == "ether":
                    ether_at.add(atom)
            else:
                left.append(atom)
        order = left

    elements = ["O" if kind_of.get(i) == "ether" else "C"
                for i in range(sheet.n_atoms)]
    frac = [p for p in sheet.frac]
    bonds = [tuple(p) for p in sheet.bonds]
    images = [tuple(p) for p in sheet.images]
    counts: dict = {}
    for atom, kind in sorted(kind_of.items()):
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "ether":
            continue
        direction = _in_plane(outward[atom], sheet.normal[atom])
        here = sheet.frac[atom] @ matrix
        if kind == "hydrogen":
            _hang(elements, frac, bonds, images, inverse, atom, "H",
                  here + C_H * direction)
        elif kind == "fluorine":
            _hang(elements, frac, bonds, images, inverse, atom, "F",
                  here + C_F * direction)
        elif kind == "carbonyl":
            _hang(elements, frac, bonds, images, inverse, atom, "O",
                  here + C_O_DOUBLE * direction)
        else:
            oxygen = here + C_OH * direction
            o, o_home = _hang(elements, frac, bonds, images, inverse,
                              atom, "O", oxygen)
            _hang(elements, frac, bonds, images, inverse, o, "H",
                  _hydroxyl_hydrogen(oxygen, direction,
                                     sheet.normal[atom]), o_home)
    return Terminated(matrix, elements, np.array(frac),
                      np.array(bonds, int).reshape(-1, 2),
                      np.array(images, int).reshape(-1, 3), counts,
                      wanted, len(edge), len(edge) - len(kind_of))


#: Where a termination's first atom is probed for room, Angstrom out
#: from its carbon, and how much room it needs: from another
#: termination's probe, and from any atom of the sheet but its own
#: carbon.  Two edge carbons across a bay point at each other, and
#: before this a build's closest contact was 0.31 A, fluorine on
#: fluorine; one of the two is left bare instead, as the example ZTC
#: leaves forty.  A hydrogen sits closer in and needs less: held to
#: fluorine's room, it was what ran out -- handed out last, it found
#: the roomy carbons taken and the ZTC defaults came out at H/C 0.035
#: for 0.07.
PROBE = {"hydrogen": 1.09}
PROBE_HEAVY = 1.3
PROBE_CLEAR = {"hydrogen": 1.25}
PROBE_CLEAR_HEAVY = 1.6
SHEET_CLEAR = {"hydrogen": 1.2}
SHEET_CLEAR_HEAVY = 1.4


class _Room:
    """Which edge carbons have room for a termination, granted one at
    a time in the seed's order, every grant remembered so the next is
    measured against it."""

    def __init__(self, sheet: Sheet, outward):
        from scipy.spatial import cKDTree

        self.sheet = sheet
        self.outward = outward
        self.matrix = np.asarray(sheet.matrix, float)
        self.inverse = np.linalg.inv(self.matrix)
        shifts = np.array([(a, b, c) for a in (-1, 0, 1)
                           for b in (-1, 0, 1) for c in (-1, 0, 1)])
        atoms = ((sheet.frac[None] + shifts[:, None]).reshape(-1, 3)
                 @ self.matrix)
        self.tree = cKDTree(atoms)
        self.granted: list = []

    def take(self, atom: int, kind: str) -> bool:
        """Whether ``kind`` fits on ``atom``; if it does, it is
        granted.  A hydroxyl is two atoms and both need room: probing
        only its oxygen put the hydrogen 0.58 A from a bare edge
        carbon across a bay, seed 2 of the default dia cell."""
        sheet = self.sheet
        direction = _in_plane(self.outward[atom], sheet.normal[atom])
        here = sheet.frac[atom] @ self.matrix
        probes = [(here + PROBE.get(kind, PROBE_HEAVY) * direction,
                   kind)]
        if kind == "hydroxyl":
            probes.append((_hydroxyl_hydrogen(
                here + C_OH * direction, direction,
                sheet.normal[atom]), "hydrogen"))
        if not all(self._clear(atom, probe, as_kind)
                   for probe, as_kind in probes):
            return False
        self.granted.extend(probe for probe, _ in probes)
        return True

    def _clear(self, atom: int, probe, kind: str) -> bool:
        close = [k % self.sheet.n_atoms
                 for k in self.tree.query_ball_point(
                     probe, SHEET_CLEAR.get(kind, SHEET_CLEAR_HEAVY))]
        if any(k != atom for k in close):
            return False
        if self.granted:
            delta = (np.array(self.granted) - probe) @ self.inverse
            delta -= np.round(delta)
            if np.min(np.linalg.norm(delta @ self.matrix, axis=1)) \
                    < PROBE_CLEAR.get(kind, PROBE_CLEAR_HEAVY):
                return False
        return True


def _hydroxyl_hydrogen(oxygen, direction, normal) -> np.ndarray:
    """Where a hydroxyl's hydrogen goes: bent at the oxygen, in the
    sheet's plane, away from the carbon, at about 109 degrees."""
    turn = np.cross(normal, direction)
    return oxygen + O_H * (np.cos(np.radians(71.0)) * direction
                           + np.sin(np.radians(71.0)) * turn)


def _in_plane(vector, normal) -> np.ndarray:
    """``vector`` with its part along ``normal`` taken off, as a unit
    vector; a straight edge carbon with no bisector points along any
    in-plane perpendicular."""
    v = vector - (vector @ normal) * normal
    if np.linalg.norm(v) < 1e-6:
        v = np.cross(normal, [1.0, 0.0, 0.0])
        if np.linalg.norm(v) < 1e-6:
            v = np.cross(normal, [0.0, 1.0, 0.0])
    return v / np.linalg.norm(v)


def _hang(elements, frac, bonds, images, inverse, parent, element,
          cart, parent_home=0):
    """One atom at ``cart`` bonded to ``parent``; returns its index and
    the translation it was wrapped by.

    ``cart`` is reached from the parent as stored, displaced by
    ``parent_home`` cells, so the bond's image is the difference of
    the two wraps.
    """
    raw = cart @ inverse
    home = np.floor(raw)
    elements.append(element)
    frac.append(raw - home)
    bonds.append((parent, len(elements) - 1))
    images.append(tuple((home - parent_home).astype(int)))
    return len(elements) - 1, home


# ======================================================================
#  STRUCTURE
# ======================================================================

def structure_of(terminated: Terminated, title: str = "carbon"):
    """A P1 structure of the atoms, with the bonds stated as its stored
    graph -- the way :func:`xtal.mof.build.state_bonds` states a MOF's
    -- so nothing about them is ever perceived."""
    from xtal.core import p1
    from xtal.core.bonding import BondRules
    from xtal.core.lattice import Lattice
    from xtal.core.site import Site
    from xtal.core.structure import CellBond, Structure

    lattice = Lattice(terminated.matrix)
    frac = np.mod(terminated.frac, 1.0)
    frac[frac >= 1.0] = 0.0
    sites = [Site(element, np.array(f))
             for element, f in zip(terminated.elements, frac, strict=True)]
    for k, site in enumerate(sites):
        site.label = f"{site.element}{k + 1}"
    structure = Structure(lattice=lattice, sites=sites)
    structure.meta["title"] = title
    cell = p1.expand(structure)
    # The images were made against the positions as built; the cell
    # wraps them again, so each is re-read against where the two
    # atoms are stored.
    shift = np.round(frac - cell.frac).astype(int)
    found = {}
    matrix = terminated.matrix
    for (a, b), image in zip(terminated.bonds, terminated.images,
                             strict=True):
        image = np.asarray(image) + shift[b] - shift[a]
        vector = (cell.frac[b] + image - cell.frac[a]) @ matrix
        bond = CellBond(int(a), int(b), tuple(int(v) for v in image),
                        float(np.linalg.norm(vector)))
        i, j, img = bond.key()
        found[(i, j, img)] = CellBond(i, j, img, bond.distance)
    rules = BondRules.from_dict(structure.bond_rules)
    structure.set_perceived(sorted(found.values(),
                                   key=lambda b: (b.i, b.j, b.image)),
                            rules.signature(), cell)
    return structure
