"""
xtal.io.cif_reader
==================
Reading CIF files into a :class:`~xtal.core.structure.Structure`.

A CIF holds an asymmetric unit plus a space group, which is exactly our
data model, so the read is close to a straight copy.  The only genuine
decision is which symmetry statement to believe when a file carries
several, and files in the wild do:

1. a Hall symbol (unambiguous -- always wins),
2. a symmetry-operation loop (unambiguous about the *setting*),
3. an H-M symbol and/or an international number (ambiguous about
   origin choice and axes),
4. nothing at all (P1, with a warning).

We prefer the operation loop when it identifies a group and agrees in
size with the H-M symbol, and fall back to the symbol otherwise.  Any
disagreement is recorded in ``structure.meta["warnings"]`` so the GUI
can show it rather than the user finding out later.
"""

from __future__ import annotations

import re
from pathlib import Path

import gemmi
import numpy as np

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Bond, CellBond, Structure


def read_cif(path) -> Structure:
    """Read the first data block of a CIF file."""
    blocks = read_cif_all(path)
    if not blocks:
        raise ValueError(f"no structure found in {path}")
    return blocks[0]


#: Tags gemmi reads with ``as_int`` rather than ``as_string``, so that
#: a quoted value throws instead of being read.  A CIF may quote any
#: value it likes and plenty do: everything the RCSR's own generator
#: wrote carries ``_space_group_IT_number \'194\'``, and every one of
#: those files failed to open with ``not an integer: \'``.  The throw
#: is inside gemmi and happens before any of this module runs, so the
#: only place to fix it is before the block is handed over.
_INT_TAGS = (
    "_space_group_IT_number",
    "_symmetry_Int_Tables_number",
    "_cell_formula_units_Z",
)


def _unquote_ints(block):
    """Strip the quotes off the integer tags, in place.

    ``as_string`` is gemmi's own unquoting, so a value that was never
    quoted survives it unchanged and this is a no-op on a file that did
    not need it.
    """
    for tag in _INT_TAGS:
        value = block.find_value(tag)
        if value is not None:
            unquoted = gemmi.cif.as_string(value)
            if unquoted != value:
                block.set_pair(tag, unquoted)
    return block


def _declares_sites(block) -> bool:
    """Whether this block says it holds atoms, however many it holds.

    A block with no site loop is metadata -- a journal reference, a
    publication table -- and is skipped.  A block with the loop and no
    rows in it is a crystal with no atoms yet, which is exactly what
    *File > New* writes into a workspace, and refusing to read one
    back meant the application could not open a file it had written
    itself.
    """
    return bool(block.find_loop("_atom_site_label"))


def read_cif_all(path) -> list[Structure]:
    """Read every data block that contains a structure."""
    path = Path(path)
    doc = gemmi.cif.read_file(str(path))
    out = []
    for block in doc:
        small = gemmi.make_small_structure_from_block(
            _unquote_ints(block))
        if small.cell.volume <= 0:
            continue
        if not small.sites and not _declares_sites(block):
            continue                    # a metadata-only block
        out.append(_from_small_structure(small, block, path))
    return out


def read_cif_string(text: str, name: str = "<string>") -> Structure:
    """Read a CIF held in memory -- used by paste and by tests."""
    doc = gemmi.cif.read_string(text)
    for block in doc:
        small = gemmi.make_small_structure_from_block(
            _unquote_ints(block))
        if small.sites and small.cell.volume > 0:
            return _from_small_structure(small, block, Path(name))
    raise ValueError("no structure found in the CIF text")


def _from_small_structure(small, block, path: Path) -> Structure:
    warnings: list[str] = []
    lattice = Lattice.from_parameters(*small.cell.parameters)
    group = _resolve_space_group(small, block, warnings)

    sites = []
    for s in small.sites:
        symbol = s.element.name
        if not symbol or symbol == "X":
            symbol = s.type_symbol or s.label
        site = Site(
            element=symbol,
            frac=[s.fract.x, s.fract.y, s.fract.z],
            occupancy=s.occ if s.occ > 0 else 1.0,
            label=s.label,
            u_iso=s.u_iso if s.u_iso else None,
            u_aniso=_aniso(s),
            charge=float(s.charge) if s.charge else None,
        )
        if s.disorder_group:
            site.props["disorder_group"] = s.disorder_group
        sites.append(site)

    structure = Structure(lattice=lattice, sites=sites,
                          space_group=group)
    structure.meta.update({
        "title": small.name or block.name,
        "source": str(path),
        "format": "cif",
    })
    for key, tag in (("chemical_formula", "_chemical_formula_sum"),
                     ("mineral", "_chemical_name_mineral"),
                     ("systematic_name",
                      "_chemical_name_systematic")):
        value = block.find_value(tag)
        if value:
            structure.meta[key] = gemmi.cif.as_string(value)
    if warnings:
        structure.meta["warnings"] = warnings
    structure.ensure_labels()
    read_bonds(block, structure)
    read_perception(block, structure)
    return structure


#: The tag that says a ``_geom_bond`` loop is a bond graph rather than
#: a distance table.  See :func:`read_bonds`.
KIND_TAG = "_xtal_bond_kind"

_SYMMETRY_CODE = re.compile(r"^(\d+)_(\d)(\d)(\d)$")


def read_bonds(block, structure) -> None:
    """Take the bonds out of a ``_geom_bond`` loop this program wrote.

    **Only one this program wrote**, which is what ``_xtal_bond_kind``
    is doing here.  Plenty of published CIFs carry a ``_geom_bond``
    loop and it is nearly always a *distance table* from the
    refinement -- a selection of contacts somebody chose to tabulate,
    not the bonding of the crystal.  Reading one of those in as the
    bond graph would hand the user a structure bonded by whoever
    prepared the file, silently, on open, which is the one thing
    `Recalculate Bonds` exists to stay in charge of.

    Everything is taken by label and the row is dropped if anything in
    it does not read: a bond loop that has drifted out of step with
    the atom-site loop is a file to open without its bonds, not a file
    to refuse.
    """
    kinds = _column(block, KIND_TAG)
    if not kinds:
        return
    where = {site.label: i for i, site in enumerate(structure.sites)}
    ones = _column(block, "_geom_bond_atom_site_label_1")
    twos = _column(block, "_geom_bond_atom_site_label_2")
    codes = _column(block, "_geom_bond_site_symmetry_2")
    images = _column(block, "_xtal_bond_image")
    orders = _column(block, "_xtal_bond_order")
    stated = _column(block, "_xtal_bond_stated")
    for n, kind in enumerate(kinds):
        i = where.get(_at(ones, n))
        j = where.get(_at(twos, n))
        if i is None or j is None:
            continue
        op, image = _symmetry_of(_at(codes, n))
        told = _image_of(_at(images, n))
        try:
            order = float(_at(orders, n) or 1.0)
        except ValueError:
            order = 1.0
        try:
            structure.bonds.append(Bond(
                i=i, j=j, image=told if told is not None else image,
                order=order, kind=kind or "explicit", op=op,
                stated=_at(stated, n).lower() in ("yes", "true", "1")))
        except ValueError:
            # A bond that cannot exist -- a site to itself in its own
            # image, an operation index below zero.  A hand-edited
            # file, and one row of it, not the file.
            continue


#: How far a stored bond's length may be from the one its atoms give
#: before the stored graph is taken to describe some other cell.
PERCEIVED_SLACK = 0.01


def read_perception(block, structure) -> None:
    """Take back a perceived bond graph this program wrote.

    See :func:`xtal.io.cif_writer._perception_loop`.  It is the
    answer perception gave, not a request to perceive, so it is
    stored exactly as a project file would store it and Recalculate
    Bonds is still what replaces it.

    The rows index P1 atoms, so the graph is taken only when the
    expansion here is the one it was written over -- the same count,
    and every bond the length it was written at.  A file edited by
    hand fails that and is opened the old way, perceived afresh,
    rather than bonded to atoms that are not the ones meant.
    """
    from xtal.core import p1
    from xtal.core.bonding import BondRules
    from xtal.io.cif_writer import PERCEIVED_COUNT, PERCEIVED_TAGS

    ones = _column(block, PERCEIVED_TAGS[0])
    if not ones:
        return
    cell = p1.expand(structure)
    try:
        if int(gemmi.cif.as_string(
                block.find_value(PERCEIVED_COUNT) or "")) \
                != cell.n_atoms:
            return
        twos, images, lengths = (_column(block, tag)
                                 for tag in PERCEIVED_TAGS[1:])
        matrix = structure.lattice.matrix
        bonds = []
        for n, one in enumerate(ones):
            i, j = int(one), int(_at(twos, n))
            image = _image_of(_at(images, n))
            length = float(_at(lengths, n))
            if image is None or not (0 <= i < cell.n_atoms
                                     and 0 <= j < cell.n_atoms):
                return
            actual = float(np.linalg.norm(
                (cell.frac[j] + image - cell.frac[i]) @ matrix))
            if abs(actual - length) > PERCEIVED_SLACK:
                return
            bonds.append(CellBond(i, j, image, actual))
    except (TypeError, ValueError):
        return
    rules = BondRules.from_dict(structure.bond_rules)
    structure.set_perceived(bonds, rules.signature(), cell)


def _column(block, tag) -> list[str]:
    """One column of a loop, unquoted, or ``[]`` if it is not there."""
    return [gemmi.cif.as_string(v) for v in block.find_loop(tag)]


def _at(column, n: int) -> str:
    return column[n] if n < len(column) else ""


def _symmetry_of(code: str) -> tuple[int, tuple[int, int, int]]:
    """``n_pqr`` back into (operation, lattice translation).

    ``(0, (0, 0, 0))`` -- the identity, in the same cell -- for
    anything that is not that shape, which is what a bare ``.`` in
    that column means and is also the safe reading of a code from
    some other program's conventions.
    """
    match = _SYMMETRY_CODE.match(str(code).strip())
    if not match:
        return 0, (0, 0, 0)
    n, p, q, r = match.groups()
    return int(n) - 1, (int(p) - 5, int(q) - 5, int(r) - 5)


def _image_of(text: str) -> tuple[int, int, int] | None:
    """``1,0,-1`` back into a lattice translation, or ``None``.

    Written for every bond because ``n_pqr`` runs out at four cells,
    so this is the answer whenever there is one.
    """
    parts = str(text).split(",")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def _aniso(site) -> tuple | None:
    """The ``_atom_site_aniso_U_*`` loop for one site, or None.

    A site with no entry in that loop comes back from gemmi as six
    zeros, and zero displacement is not a measurement -- it is the
    absence of one.  Drawing it as a point-sized ellipsoid would say
    the atom was refined to be perfectly still, so it is None here and
    the viewport falls back and says so.
    """
    u = site.aniso
    values = (u.u11, u.u22, u.u33, u.u12, u.u13, u.u23)
    if not any(abs(v) > 0.0 for v in values):
        return None
    return tuple(float(v) for v in values)


def _resolve_space_group(small, block, warnings) -> SpaceGroup:
    from_ops = _group_from_operations(block)
    hall = block.find_value("_space_group_name_Hall") or \
        block.find_value("_symmetry_space_group_name_Hall")
    if hall:
        text = gemmi.cif.as_string(hall)
        try:
            return SpaceGroup.from_hall(text)
        except ValueError:
            # Some depositing software writes the spaces of a Hall
            # symbol as semicolons or commas ("-F 4;2;3").  Repairing
            # that is safe: if the cleaned symbol does not parse
            # either, we fall through to the H-M symbol as before.
            repaired = re.sub(r"\s+", " ",
                              re.sub(r"[;,]+", " ", text)).strip()
            if repaired != text:
                try:
                    group = SpaceGroup.from_hall(repaired)
                except ValueError:
                    pass
                else:
                    warnings.append(
                        f"the Hall symbol {text!r} is malformed; read "
                        f"as {repaired!r}")
                    return group
            warnings.append(f"unreadable Hall symbol {text!r}, ignored")

    from_name = None
    if small.spacegroup_hm:
        try:
            from_name = SpaceGroup.from_name(small.spacegroup_hm)
        except ValueError:
            warnings.append(
                f"unknown space-group symbol {small.spacegroup_hm!r}")
    if from_name is None and small.spacegroup_number:
        try:
            from_name = SpaceGroup.from_number(small.spacegroup_number)
        except ValueError:
            pass

    if from_ops is not None and from_name is not None:
        if from_ops.order == from_name.order:
            return from_ops             # same group, unambiguous setting
        warnings.append(
            f"the symmetry operation loop ({from_ops.order} operations, "
            f"{from_ops.short_name}) disagrees with the symbol "
            f"{from_name.short_name} ({from_name.order} operations); "
            f"using the symbol")
        return from_name
    if from_ops is not None:
        return from_ops
    if from_name is not None:
        return from_name

    warnings.append("no symmetry information in the file; assuming P1")
    return SpaceGroup.p1()


def _group_from_operations(block) -> SpaceGroup | None:
    for tag in ("_space_group_symop_operation_xyz",
                "_symmetry_equiv_pos_as_xyz"):
        loop = block.find_loop(tag)
        triplets = [gemmi.cif.as_string(v) for v in loop]
        if not triplets:
            continue
        try:
            ops = gemmi.GroupOps([gemmi.Op(t) for t in triplets])
            found = gemmi.find_spacegroup_by_ops(ops)
        except (RuntimeError, ValueError):
            return None
        if found is None:
            return None
        return SpaceGroup.from_hall(found.hall)
    return None
