"""
xtal.mof.block
==============
Where a connection point sits, and how a building block is written.

:mod:`xtal.mof.catalog` reads the database; this is the other
direction -- a molecule somebody made here, on its way out to
PORMAKE's ``bb_dir``.  The reader stays there because it is about the
database; the writer is here because it is about the format.

**A connection point is 0.75 A from the centroid of the atoms it
hangs off.**  That is not a bond length and it is not a guess: over
the 867 blocks PORMAKE ships, the 4256 X-to-body distances have a
median of 0.750 and 70 % of them fall within 0.05 of it.  A block
written with its connection points at a real bond length builds a
framework with every linker bond roughly twice too long, and nothing
anywhere reports an error -- which is why the number is a named
constant with this paragraph attached to it rather than a literal in
the one function that needs it.

It reads *the atoms* and not *the atom* because a point may stand for
several -- see :mod:`xtal.mof.attach`.  With one of them the centroid
is that atom and the arithmetic is the same to the bit, which is what
keeps every single-point block written exactly as it was before.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

#: How far a connection point sits from the centroid of the atoms
#: it hangs off.
CONNECTION_DISTANCE = 0.75

#: Bond order -> PORMAKE's letter, in the bond block that follows the
#: atoms.  The four orders this application already offers are the four
#: PORMAKE writes and the four RDKit has, so no translation table is
#: needed anywhere else in the build path.
BOND_LETTERS = {1.0: "S", 2.0: "D", 3.0: "T", 1.5: "A"}


def pull_in(cart, bonds, connections,
            distance: float = CONNECTION_DISTANCE) -> np.ndarray:
    """Move each connection point to ``distance`` from its members.

    From the **centroid** of the atoms it is bonded to, which with one
    of them is that atom and is the arithmetic this always did, to the
    bit.  With two it is the middle of a chelate's bite, which is
    where the next block's own point has to land for the two ends to
    meet -- see :mod:`xtal.mof.attach`.

    The direction is kept and only the length is changed, because the
    direction is the half that carries chemistry -- it is where the
    next building block goes -- and it came from a relaxed geometry.
    A connection point with no bond at all is left exactly where it
    is: there is no direction to place it along, and inventing one
    would be worse than a block that :func:`problems` can then
    complain about.

    The members are the *distinct* partners, never the bond records.
    26 of the 867 shipped blocks name one partner twice, and a
    centroid that counted the record twice would weight that atom
    double for no reason anybody wrote down.  A bond onto another
    connection point is not a member at all.
    """
    cart = np.array(cart, dtype=float).reshape(-1, 3)
    marked = {int(c) for c in connections}
    for index in connections:
        anchors = sorted({j if i == index else i for i, j, _ in bonds
                          if index in (i, j)} - marked)
        if not anchors:
            continue
        anchor = cart[anchors].mean(axis=0)
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
    be placed on anything; one whose connection point has no bond at
    all has no direction to be placed along; and two molecules in the
    same cell are two blocks, not one -- PORMAKE would build a
    framework out of whichever of them the alignment happened to
    favour and report nothing.

    **Two bonds are no longer a refusal.**  They are a bidentate
    attachment, which is how MFU-4l's kernel meets a triazolate and
    how Ni3(HITP)2's nickel meets an imine, and refusing them was what
    made those two crystals unbuildable.  What is refused instead is
    the three ways a *group* can be wrong and a single atom could not
    be: a point bonded to another point, one whose atoms are too far
    apart to be one chelating group
    (:data:`~xtal.mof.attach.MAX_ATTACHMENT_SPAN`), and one pointing
    back into the molecule.  All three are per atom and named.
    """
    # Imported here rather than at the top: `pull_in` above is on
    # the path `xtal.build.chem` takes to embed a molecule, and that
    # file is deliberately cheap to import.
    from xtal.core import bonding, p1
    from xtal.mof.attach import MAX_ATTACHMENT_SPAN
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
    points = set(marked)
    for atom in marked:
        members, inner = _attachment(cell, graph, atom, points)
        others = sorted({j for j, _t in
                         graph.neighbors_with_images(atom)
                         if j in points and j != atom})
        for other in others:
            found.append(
                f"{_label(cell, atom)} is bonded to "
                f"{_label(cell, other)}, and both of them are "
                f"connection points -- a connection point stands for "
                f"the atoms of this block, not for another marker")
        if not members:
            # Said only when there is nothing on the other end at
            # all.  A point whose one bond goes to another point has
            # already been complained about by name, and telling the
            # same atom it has no bonds would be both a second
            # sentence and a false one.
            if not others:
                found.append(
                    f"{_label(cell, atom)} is a connection point "
                    f"with no bonds, and it needs at least one, to "
                    f"say which way it points")
            continue
        span = _span(list(members.values()))
        if span > MAX_ATTACHMENT_SPAN:
            found.append(
                f"{_label(cell, atom)} stands for {len(members)} "
                f"atoms {span:.2f} A apart, and one attachment is at "
                f"most {MAX_ATTACHMENT_SPAN:.1f} A wide -- select the "
                f"atoms of a single chelating group, not two ends of "
                f"the molecule")
        if _points_inward(cell, atom, members, inner):
            found.append(
                f"{_label(cell, atom)} points back into the molecule "
                f"rather than out of it, so the next block would be "
                f"built on top of this one")
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


def _attachment(cell, graph, atom: int, marked: set):
    """``(members, inner)`` for one connection point, unwrapped.

    Both are ``{atom index: cartesian position}`` in the frame the
    ``X`` itself is drawn in, because a molecule lying across a cell
    face is two pieces a cell apart and a span measured over the
    wrapped coordinates is the width of the box.

    ``members`` are the body atoms it is bonded to -- distinct, and
    never another connection point.  ``inner`` is one bond further in:
    the members' own neighbours, which is the only local thing there
    is to say which way is *out* of the molecule.
    """
    matrix = cell.lattice.matrix
    members: dict[int, np.ndarray] = {}
    shifts: dict[int, np.ndarray] = {}
    for j, image in graph.neighbors_with_images(atom):
        if j == atom or j in marked or j in members:
            continue
        shifts[j] = np.asarray(image, dtype=int)
        members[j] = cell.cart[j] + shifts[j] @ matrix
    inner: dict[int, np.ndarray] = {}
    for member, shift in shifts.items():
        for k, image in graph.neighbors_with_images(member):
            if k == atom or k in members or k in inner:
                continue
            inner[k] = cell.cart[k] + (shift + image) @ matrix
    return members, inner


def _span(points) -> float:
    """The widest gap between two of these positions."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(points) < 2:
        return 0.0
    d = points[:, None, :] - points[None, :, :]
    return float(np.linalg.norm(d, axis=-1).max())


def _points_inward(cell, atom: int, members, inner) -> bool:
    """Whether this attachment faces the molecule instead of away.

    Measured locally and not against the block's middle, because a
    block's middle is the wrong reference: a node's arms are concave,
    so 77 of the 4256 shipped connection points point *toward* the
    centroid of their own block and every one of them is correct.
    What is asked instead is whether the point lies on the same side
    of its members as the atoms one bond further in -- the direction
    the molecule continues in.  Over the 4202 shipped points with a
    bond block this fires **zero** times; the closest any of them
    comes is a cosine of -0.032, so the threshold is plain zero and
    has no margin to tune.

    A two-atom molecule has no inner reference and is left alone.
    """
    if not inner:
        return False
    middle = np.mean(list(members.values()), axis=0)
    out = np.asarray(cell.cart[atom], dtype=float) - middle
    into = np.mean(list(inner.values()), axis=0) - middle
    if np.linalg.norm(out) < 1e-9 or np.linalg.norm(into) < 1e-9:
        return False
    return bool(out @ into > 0.0)


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
      molecule's bond orders survive into the built framework's CIF --
      and, for a connection point with more than one of them, the only
      record of which atoms it stands for.

    The connection points are written last, which is how 866 of the
    867 shipped blocks are laid out, and pulled in to
    :data:`CONNECTION_DISTANCE` of the atoms they hang off on the way
    -- see this module's own docstring for why 0.75 A and not a bond
    length.
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
    path.write_text(block_string(structure), encoding="utf-8")
    return path
