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

from pathlib import Path

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


class BlockError(ValueError):
    """A structure that is not a building block, said in a sentence."""


def problems(structure) -> list[str]:
    """Everything that stops this structure being a building block.

    All of them, not the first: a person who has to fix three things
    should be told three things rather than discovering them one save
    at a time.  Empty means :func:`block_string` will write it.

    Each of these is fatal rather than a warning, which is why there
    is one list and not two.  A block with no connection points cannot
    be placed on anything; one whose connection point has two bonds
    has no direction to be placed along; and two molecules in the same
    cell are two blocks, not one -- PORMAKE would build a framework
    out of whichever of them the alignment happened to favour and
    report nothing.
    """
    # Imported here rather than at the top: `pull_in` above is on
    # the path `xtal.build.chem` takes to embed a molecule, and that
    # file is deliberately cheap to import.
    from xtal.core import bonding, p1
    from xtal.mof.catalog import CONNECTION

    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    found: list[str] = []
    marked = [i for i in range(cell.n_atoms)
              if cell.elements[i] == CONNECTION]
    if not marked:
        return ["nothing marks where this joins onto anything -- "
                "select an atom on the end of a bond and use Mark "
                "connection points"]
    for atom in marked:
        n = len(graph.bonds_of(atom))
        if n != 1:
            found.append(
                f"{_label(cell, atom)} is a connection point with "
                f"{n} bond(s), and it needs exactly one to say which "
                f"way it points")
    pieces = graph.fragments()
    if len(pieces) > 1:
        found.append(
            f"this cell holds {len(pieces)} separate pieces, and a "
            f"building block is one -- delete the others, or build "
            f"the molecule in a cell of its own")
    if any(piece.periodic for piece in pieces):
        found.append(
            "this is a framework rather than a molecule: its bonds "
            "close onto the next cell, so it has no outside for a "
            "connection point to point into")
    return found


def _label(cell, atom: int) -> str:
    label = cell.labels[atom] if len(cell.labels) > atom else ""
    return str(label) or f"{cell.elements[atom]} {atom + 1}"


def block_string(structure) -> str:
    """One PORMAKE building block, as the text of its ``.xyz``.

    Four sections, and the third and fourth are the ones a writer
    invents at its peril -- they were read off the 867 files PORMAKE
    ships rather than assumed:

    * the atom count;
    * **the index line**, which is where PORMAKE's own writer puts the
      connection points and what :func:`xtal.mof.catalog._connections`
      reads;
    * the atoms, with the connection points spelled ``X`` -- because
      PORMAKE identifies them by *symbol* and never reads the index
      line.  Both spellings, therefore, and not a choice between them:
      a file with only one of the two is read correctly by exactly one
      of the two readers;
    * the bonds, ``i j`` and a letter in ``S/D/T/A``, which is how a
      molecule's bond orders survive into the built framework's CIF.

    The connection points are written last, which is how 866 of the
    867 shipped blocks are laid out, and pulled in to
    :data:`CONNECTION_DISTANCE` on the way -- see this module's own
    docstring for why 0.75 A and not a bond length.
    """
    from xtal.core import bonding, p1
    from xtal.mof.catalog import CONNECTION

    found = problems(structure)
    if found:
        raise BlockError("; ".join(found))

    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    orders = bonding.orders(structure)

    marked = [i for i in range(cell.n_atoms)
              if cell.elements[i] == CONNECTION]
    order_out = ([i for i in range(cell.n_atoms) if i not in set(marked)]
                 + marked)
    place = {atom: k for k, atom in enumerate(order_out)}

    cart = np.array(cell.cart, dtype=float)[order_out]
    cart = cart - cart.mean(axis=0)
    bonds = [(place[b.i], place[b.j], float(o))
             for b, o in zip(graph.bonds, orders, strict=True)]
    cart = pull_in(cart, bonds,
                   [place[atom] for atom in marked])

    lines = [str(len(order_out)),
             "".join(f"{place[atom]:5d}" for atom in marked)]
    for atom, (x, y, z) in zip(order_out, cart, strict=True):
        lines.append(f"{cell.elements[atom]:<4s} {x:.4f} {y:.4f} "
                     f"{z:.4f}")
    connections = {place[atom] for atom in marked}
    for i, j, order in sorted(bonds):
        # A bond onto a connection point is always S in the shipped
        # files, and an X has no chemistry to have an order about.
        letter = ("S" if connections & {i, j}
                  else BOND_LETTERS.get(order, "S"))
        lines.append(f"{i:4d} {j:4d} {letter}")
    return "\n".join(lines) + "\n"


def write_building_block(structure, path) -> Path:
    """Write one block into a folder PORMAKE reads.

    The file *name* is the block's name -- ``catalog.building_blocks``
    keys on the stem -- so there is nothing about a name in the format
    and nothing to pass here beyond where it goes.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(block_string(structure))
    return path
