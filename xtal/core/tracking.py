"""
xtal.core.tracking
==================
The same atoms found again after an edit renumbers the cell.

A set of P1 indices names atoms only until the next edit that adds or
removes one: replacing a hydrogen takes its site out and appends the
group, so every atom after it moves down one, and a set of indices
would then name its neighbours.  :func:`record` writes down what the
atoms are and where -- element and fractional coordinates -- and
:func:`find` looks for them in the cell as it is now.  An atom an edit
did not touch is where it was, so that is how it is found; what an
edit added was never recorded, and is not.

An operation that rebuilds the cell -- a supercell, a standard
setting, the other hand -- is different: it may move every atom, and
only it knows where to.  It states an :class:`AtomMap`, and
:func:`follow` finds the atoms through it.

View state that names atoms (View > Show Only Selected's hidden set)
is kept this way, so it lives here, with no Qt, where it can be
tested without a window.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Record:
    """Where a set of atoms was: their elements, their fractional
    coordinates in the same order, and the lattice those are on (rows),
    which a map through a change of cell needs to measure in
    Angstrom."""

    symbols: tuple = ()
    frac: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    lattice: np.ndarray = field(default_factory=lambda: np.eye(3))

    def __len__(self) -> int:
        return len(self.symbols)


def record(cell, atoms, lattice=None) -> Record:
    """What ``atoms`` of ``cell`` are and where, to find them again;
    ``lattice`` is the cell's, for :func:`follow`."""
    order = sorted(int(a) for a in atoms)
    rows = (np.eye(3) if lattice is None
            else np.asarray(lattice.matrix, float))
    return Record(tuple(cell.elements[a] for a in order),
                  np.asarray(cell.frac[order], float).reshape(-1, 3),
                  rows)


def find(cell, where: Record) -> set[int]:
    """The atoms of ``cell`` that ``where`` recorded: same element,
    same fractional coordinates, wrapped into the cell."""
    from scipy.spatial import cKDTree

    symbols, frac = where.symbols, where.frac
    found: set[int] = set()
    if cell.n_atoms and len(symbols):
        home = np.mod(np.asarray(cell.frac, float), 1.0)
        home[home >= 1.0] = 0.0
        wanted = np.mod(frac, 1.0)
        wanted[wanted >= 1.0] = 0.0
        tree = cKDTree(home, boxsize=1.0)
        distance, atom = tree.query(wanted)
        for symbol, d, a in zip(symbols, distance, atom,
                                strict=True):
            if d < 1e-4 and cell.elements[int(a)] == symbol:
                found.add(int(a))
    return found


# ======================================================================
#  THROUGH A SYMMETRY OR CELL CHANGE
# ======================================================================
#
# An operation that rebuilds the cell -- a supercell, a standard
# setting, the other hand -- may move every atom and number them all
# afresh, and where an atom went is only known to the operation.  It
# says so with an AtomMap, and :func:`follow` uses it.

#: How far an atom may sit from where the map sends it and still be the
#: same atom, in Angstrom: :data:`xtal.core.p1.SPECIAL_POSITION_TOL`,
#: the distance at which this program stops believing two coordinates
#: are different places.  A Standardize that idealises moves atoms by
#: up to its tolerance, which is well under it.
MATCH_TOL = 0.05


@dataclass(frozen=True)
class AtomMap:
    """How a rebuilt cell's fractional coordinates relate to those of
    the cell it was rebuilt from: ``old = M @ new + t``.

    Fractional and not Cartesian, because Standardize turns the axes as
    well as moving the origin, and an operation knows its basis change
    exactly where a pair of Cartesian frames would only know it to the
    rounding of an idealised cell.
    """

    M: np.ndarray
    t: np.ndarray

    @classmethod
    def identity(cls) -> AtomMap:
        return cls(np.eye(3), np.zeros(3))

    @classmethod
    def keeping_frame(cls, before, after) -> AtomMap:
        """The map when every atom keeps its Cartesian position:
        ``before`` and ``after`` are the two lattices."""
        rows_new = np.asarray(after.matrix, float)
        rows_old = np.asarray(before.matrix, float)
        return cls((rows_new @ np.linalg.inv(rows_old)).T, np.zeros(3))

    def back(self, new) -> np.ndarray:
        """Fractional coordinates in the new cell, in the old one."""
        return np.asarray(new, float) @ self.M.T + self.t

    def forward(self, old) -> np.ndarray:
        """Fractional coordinates in the old cell, in the new one."""
        return (np.asarray(old, float) - self.t) @ np.linalg.inv(self.M).T

    def inverse(self) -> AtomMap:
        """The map of the undo."""
        inverse = np.linalg.inv(self.M)
        return AtomMap(inverse, -inverse @ self.t)

    def then(self, later: AtomMap) -> AtomMap:
        """This step followed by ``later``: the map from the cell
        ``later`` made back to the one this step started from."""
        return AtomMap(self.M @ later.M, self.M @ later.t + self.t)


def follow(cell, lattice, where: Record, via: AtomMap) -> set[int]:
    """The atoms of ``cell`` (on ``lattice``) that ``where`` recorded,
    through an operation whose map is ``via``.

    Matched both ways, because "the same atoms" in a cell of another
    size means more than one thing.  Each new atom is taken back to the
    old cell: every copy of a recorded atom in a supercell lands on it,
    so a supercell keeps them all.  Each recorded atom is taken forward
    to the new cell: an atom of a primitive cell stands for several of
    the conventional cell's, and is kept if any of them was recorded.
    A ball and not the nearest atom, so that two duplicates Merge
    Duplicates made one are one atom kept if either was.
    """
    found: set[int] = set()
    if not cell.n_atoms or not len(where):
        return found
    elements = np.asarray(cell.elements)
    symbols = np.asarray(where.symbols)
    old_rows = np.asarray(where.lattice, float)
    new_rows = np.asarray(lattice.matrix, float)
    near = _within(where.frac, old_rows, via.back(cell.frac))
    for atom, recorded in enumerate(near):
        if any(symbols[r] == elements[atom] for r in recorded):
            found.add(atom)
    near = _within(cell.frac, new_rows, via.forward(where.frac))
    for r, atoms in enumerate(near):
        found.update(int(a) for a in atoms if elements[a] == symbols[r])
    return found


def _within(points, rows, queries, tol: float = MATCH_TOL) -> list:
    """For each query, the points within ``tol`` Angstrom of it,
    periodically -- all fractional, on the lattice ``rows``.

    Searched in fractional space with a radius no Cartesian ball of
    ``tol`` can exceed, then held to the Cartesian distance."""
    from scipy.spatial import cKDTree

    points = _wrapped(points)
    queries = _wrapped(queries)
    reach = tol * np.linalg.norm(np.linalg.inv(rows), 2)
    tree = cKDTree(points, boxsize=1.0)
    out = []
    for query, candidates in zip(
            queries, tree.query_ball_point(queries, reach), strict=True):
        if not candidates:
            out.append([])
            continue
        d = points[candidates] - query
        d -= np.round(d)
        close = np.linalg.norm(d @ rows, axis=1) <= tol
        out.append([c for c, ok in zip(candidates, close, strict=True)
                    if ok])
    return out


def _wrapped(frac) -> np.ndarray:
    out = np.mod(np.asarray(frac, float).reshape(-1, 3), 1.0)
    out[out >= 1.0] = 0.0
    return out
