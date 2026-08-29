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

from pathlib import Path

import gemmi

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure


def read_cif(path) -> Structure:
    """Read the first data block of a CIF file."""
    blocks = read_cif_all(path)
    if not blocks:
        raise ValueError(f"no structure found in {path}")
    return blocks[0]


def read_cif_all(path) -> list[Structure]:
    """Read every data block that contains a structure."""
    path = Path(path)
    doc = gemmi.cif.read_file(str(path))
    out = []
    for block in doc:
        small = gemmi.make_small_structure_from_block(block)
        if not small.sites or small.cell.volume <= 0:
            continue                    # a metadata-only block
        out.append(_from_small_structure(small, block, path))
    return out


def read_cif_string(text: str, name: str = "<string>") -> Structure:
    """Read a CIF held in memory -- used by paste and by tests."""
    doc = gemmi.cif.read_string(text)
    for block in doc:
        small = gemmi.make_small_structure_from_block(block)
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
    return structure


def _resolve_space_group(small, block, warnings) -> SpaceGroup:
    from_ops = _group_from_operations(block)
    hall = block.find_value("_space_group_name_Hall") or \
        block.find_value("_symmetry_space_group_name_Hall")
    if hall:
        try:
            return SpaceGroup.from_hall(gemmi.cif.as_string(hall))
        except ValueError:
            warnings.append(f"unreadable Hall symbol {hall!r}, ignored")

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
