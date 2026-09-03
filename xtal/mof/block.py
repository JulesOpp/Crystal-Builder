"""
xtal.mof.block
==============
Where a connection point sits, and how a building block is written.

:mod:`xtal.mof.catalog` reads the database; this is the other
direction -- a molecule somebody made here, on its way out to
PORMAKE's ``bb_dir``.  The reader stays there because it is about the
database; the writer is here because it is about the format.

**A connection point is 0.75 A from the atom it hangs off.**  That is
not a bond length and it is not a guess: over the 867 blocks PORMAKE
ships, the 4256 X-to-body distances have a median of 0.750 and 70 % of
them fall within 0.05 of it.  A block written with its connection
points at a real bond length builds a framework with every linker bond
roughly twice too long, and nothing anywhere reports an error -- which
is why the number is a named constant with this paragraph attached to
it rather than a literal in the one function that needs it.
"""

from __future__ import annotations

import numpy as np

#: How far a connection point sits from the atom it hangs off.
CONNECTION_DISTANCE = 0.75

#: Bond order -> PORMAKE's letter, in the bond block that follows the
#: atoms.  The four orders this application already offers are the four
#: PORMAKE writes and the four RDKit has, so no translation table is
#: needed anywhere else in the build path.
BOND_LETTERS = {1.0: "S", 2.0: "D", 3.0: "T", 1.5: "A"}


def pull_in(cart, bonds, connections,
            distance: float = CONNECTION_DISTANCE) -> np.ndarray:
    """Move each connection point to ``distance`` from its neighbour.

    The direction is kept and only the length is changed, because the
    direction is the half that carries chemistry -- it is where the
    next building block goes -- and it came from a relaxed geometry.
    A connection point with no bond, or with more than one, is left
    exactly where it is: there is no single direction to place it
    along, and silently picking one of two would be worse than a block
    that :func:`problems` can then complain about.
    """
    cart = np.array(cart, dtype=float).reshape(-1, 3)
    for index in connections:
        anchors = [j if i == index else i for i, j, _ in bonds
                   if index in (i, j)]
        if len(anchors) != 1:
            continue
        anchor = cart[anchors[0]]
        offset = cart[index] - anchor
        length = float(np.linalg.norm(offset))
        if length < 1e-9:
            continue
        cart[index] = anchor + offset * (distance / length)
    return cart
