"""
xtal.core.scalars
=================
A number per bond or per atom, for colouring a structure by it: how
long each bond is, how far it is from the sum of its covalent radii,
how many neighbours an atom has, how its angles sit against the ideal
one for that many, the smallest ring it is in, and its charge.

**Undefined is NaN, never zero.**  An atom with one neighbour has no
angle, a four-coordinate metal no ring, a site nobody charged no
charge -- and a zero coloured as the bottom of the scale is the
smallest angle in the picture, or the most negative charge, which is
a claim about the crystal nobody made.  The viewport draws NaN grey,
off the scale.

Everything is read off the stored graph, never perceived, and a dummy
atom is held back the way everything chemical holds one back: it has
no value of its own, and a bond to one counts towards neither the
coordination nor the angles of the atom at its other end.  A bond to
a marker still has a length -- that is what a marker is measured by --
but no ideal one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import bonding, p1, rings
from xtal.core import elements as el


@dataclass(frozen=True)
class Quantity:
    """What one entry of *Colour by* measures."""

    name: str
    label: str
    unit: str
    per: str                        # "bond" or "atom"
    integer: bool = False


QUANTITIES = {q.name: q for q in (
    Quantity("bond_length", "Bond length", "Å", "bond"),
    Quantity("bond_strain", "Bond length - ideal", "Å", "bond"),
    Quantity("coordination", "Coordination", "", "atom", integer=True),
    Quantity("mean_angle", "Mean bond angle", "°", "atom"),
    Quantity("angle_deviation", "Angle from ideal", "°", "atom"),
    Quantity("smallest_ring", "Smallest ring", "", "atom",
             integer=True),
    Quantity("charge", "Charge", "e", "atom"),
)}

#: The angle an atom's bonds make when nothing pulls them out of the
#: shape their number gives: trigonal, tetrahedral.  Two neighbours
#: have no one angle -- 180 for an sp carbon, 105 for water, 144 for
#: quartz's oxygen -- and nor do five and up, so those atoms have no
#: deviation rather than a wrong one: an ether oxygen 63 degrees "off"
#: a straight line was the brightest thing on MFU-4l.
IDEAL_ANGLE = {3: 120.0, 4: float(np.degrees(np.arccos(-1.0 / 3.0)))}


def values(structure, name: str, rules=None, graph=None,
           max_ring: int = rings.DEFAULT_MAX_SIZE) -> np.ndarray:
    """``name``'s value per bond of ``graph`` or per P1 atom.

    ``graph`` is the caller's when it has one, so the values line up
    with the bonds it is drawing; otherwise the structure's own.
    """
    quantity = QUANTITIES[name]
    if quantity.per == "bond":
        return bond_values(structure, name, rules, graph)
    return atom_values(structure, name, rules, graph, max_ring)


def bond_values(structure, name: str, rules=None,
                graph=None) -> np.ndarray:
    """One value per bond of ``graph``, in its order."""
    cell = p1.expand(structure)
    if graph is None:
        graph = bonding.graph(structure, rules)
    if not graph.bonds:
        return np.zeros(0)
    ends, images = _ends(graph)
    vectors = cell.lattice.to_cart(
        cell.frac[ends[:, 1]] + images - cell.frac[ends[:, 0]])
    lengths = np.linalg.norm(vectors, axis=1)
    if name == "bond_length":
        return lengths
    if name == "bond_strain":
        elements = cell.elements
        ideal = np.array([
            np.nan if el.is_dummy(elements[i]) or el.is_dummy(elements[j])
            else bonding.bond_distance(elements[i], elements[j])
            for i, j in ends])
        return lengths - ideal
    raise KeyError(name)


def atom_values(structure, name: str, rules=None, graph=None,
                max_ring: int = rings.DEFAULT_MAX_SIZE) -> np.ndarray:
    """One value per atom of the P1 cell."""
    cell = p1.expand(structure)
    n = cell.n_atoms
    dummy = np.array([el.is_dummy(e) for e in cell.elements], bool)
    if name == "charge":
        charges = [structure.sites[s].charge for s in cell.site_idx]
        out = np.array([np.nan if c is None else float(c)
                        for c in charges])
    elif name == "smallest_ring":
        out = np.full(n, np.nan)
        for ring in rings.rings_of(structure, rules, max_ring):
            size = len(ring)
            for atom, _shift in ring:
                if not size >= out[atom]:     # NaN compares False
                    out[atom] = size
    else:
        if graph is None:
            graph = bonding.graph(structure, rules)
        out = _from_neighbours(cell, graph, name, dummy)
    out = np.asarray(out, float).reshape(n)
    out[dummy] = np.nan
    return out


def _from_neighbours(cell, graph, name: str, dummy) -> np.ndarray:
    """Coordination and the angles, from each atom's bond vectors."""
    n = cell.n_atoms
    vectors: list = [[] for _ in range(n)]
    if graph.bonds:
        ends, images = _ends(graph)
        d = cell.lattice.to_cart(
            cell.frac[ends[:, 1]] + images - cell.frac[ends[:, 0]])
        for (i, j), v in zip(ends, d, strict=True):
            if not dummy[j]:
                vectors[i].append(v)
            if not dummy[i]:
                vectors[j].append(-v)
    if name == "coordination":
        return np.array([len(v) for v in vectors], float)
    out = np.full(n, np.nan)
    for i, v in enumerate(vectors):
        if len(v) < 2:
            continue
        angles = _angles(np.array(v))
        if name == "mean_angle":
            out[i] = angles.mean()
        elif name == "angle_deviation":
            ideal = IDEAL_ANGLE.get(len(v))
            if ideal is not None:
                out[i] = np.abs(angles - ideal).mean()
        else:
            raise KeyError(name)
    return out


def _angles(vectors: np.ndarray) -> np.ndarray:
    """Every angle between two of ``vectors``, in degrees."""
    unit = vectors / np.linalg.norm(vectors, axis=1)[:, None]
    a, b = np.triu_indices(len(unit), k=1)
    cosine = np.einsum("ij,ij->i", unit[a], unit[b])
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _ends(graph) -> tuple[np.ndarray, np.ndarray]:
    ends = np.array([(b.i, b.j) for b in graph.bonds], dtype=int)
    images = np.array([b.image for b in graph.bonds], dtype=float)
    return ends, images


def auto_range(found: np.ndarray) -> tuple[float, float] | None:
    """The finite values' least and greatest, or None for none."""
    finite = np.asarray(found, float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return None
    return float(finite.min()), float(finite.max())
