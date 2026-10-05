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

View state that names atoms (View > Show Only Selected's hidden set)
is kept this way, so it lives here, with no Qt, where it can be
tested without a window.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Record:
    """Where a set of atoms was: their elements, and their fractional
    coordinates in the same order."""

    symbols: tuple = ()
    frac: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))

    def __len__(self) -> int:
        return len(self.symbols)


def record(cell, atoms) -> Record:
    """What ``atoms`` of ``cell`` are and where, to find them again."""
    order = sorted(int(a) for a in atoms)
    return Record(tuple(cell.elements[a] for a in order),
                  np.asarray(cell.frac[order], float).reshape(-1, 3))


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
