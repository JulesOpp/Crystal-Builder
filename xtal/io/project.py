"""
xtal.io.project
===============
The ``.xtalproj`` project file: everything about an open document, not
just its crystal.

A CIF holds a structure.  A *session* holds the structure plus how you
were looking at it -- the style, the colours you overrode, the display
range, what was selected, the measurements you had taken.  Reopening a
project puts all of that back; reopening a CIF cannot, and should not
pretend to.

The file is a zip of small, readable parts:

    structure.cif    the crystal, in the interchange format
    cell.json        the bare cell, written only when there are no
                     atoms yet -- a CIF with no sites is not a CIF
    bonds.json       the hand-drawn and suppressed bonds
    view.json        the ViewSettings record
    session.json     selection, measurements, and provenance

Two decisions are worth stating.  **It is a zip of text, not a pickle**:
a project should still be openable in five years and diffable today, and
every part of it can be read with an editor.  And the **bonds are stored
beside the CIF rather than in it**, because a CIF has nowhere to put
them -- a bond here is (site, site, symmetry operation, lattice
translation), which no CIF tag expresses.  Writing them separately keeps
``structure.cif`` a real CIF that any other program can open.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from xtal.core.structure import Bond
from xtal.io.cif_reader import read_cif_string
from xtal.io.cif_writer import cif_string

EXTENSION = ".xtalproj"
FORMAT_VERSION = 1

STRUCTURE_PART = "structure.cif"
CELL_PART = "cell.json"
BONDS_PART = "bonds.json"
VIEW_PART = "view.json"
SESSION_PART = "session.json"


def write_project(structure, path, view=None,
                  session=None) -> Path:
    """Write a project.

    ``view`` and ``session`` are plain dicts -- whatever the
    application wants to remember.  The core neither defines nor reads
    their schema, which is what keeps ``xtalapp``'s view settings out
    of the crystallography.  The argument order is (structure, path),
    matching every other writer so the format registry can call it.
    """
    path = Path(path)
    if path.suffix != EXTENSION:
        path = path.with_suffix(EXTENSION)

    bonds = {
        "bonds": [b.to_dict() for b in structure.bonds],
        "bond_rules": dict(structure.bond_rules),
    }
    header = {"format": "xtalproj", "version": FORMAT_VERSION}

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(STRUCTURE_PART, cif_string(structure))
        if not structure.n_sites:
            # A CIF with no atoms is not a readable CIF, and a project
            # of a structure you have only just started -- a cell and
            # nothing in it -- has to survive being saved.
            archive.writestr(CELL_PART, _dump({
                "lattice": structure.lattice.to_dict(),
                "space_group": structure.space_group.to_dict(),
            }))
        archive.writestr(BONDS_PART, _dump(bonds))
        archive.writestr(VIEW_PART, _dump(view or {}))
        archive.writestr(SESSION_PART,
                         _dump({**header, **(session or {})}))
    return path


def read_project(path) -> tuple:
    """``(structure, view, session)`` from a project file.

    A project written by a later version is read as far as it can be
    rather than refused: the structure is the part that matters, and
    losing a view setting is not a reason to lose a crystal.
    """
    path = Path(path)
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"{path.name} is not a project file: {exc}") from exc

    with archive:
        names = set(archive.namelist())
        if STRUCTURE_PART not in names:
            raise ValueError(
                f"{path.name} has no {STRUCTURE_PART}; it is a zip "
                f"but not a project")
        structure = _read_structure(archive, names, path)
        view = _load(archive, VIEW_PART, names)
        session = _load(archive, SESSION_PART, names)
        _restore_bonds(structure, _load(archive, BONDS_PART, names))

    structure.meta.setdefault("source", str(path))
    structure.meta["title"] = structure.meta.get("title") or path.stem
    return structure, view, session


def read_project_structure(path):
    """Just the crystal, for the format registry.

    Opening a project through the generic reader gets the structure
    and nothing else; the application calls :func:`read_project` when
    it wants the view and the session back too.
    """
    return read_project(path)[0]


def is_project(path) -> bool:
    return Path(path).suffix.lower() == EXTENSION


# ======================================================================
#  PARTS
# ======================================================================

def _read_structure(archive, names: set, path):
    """The crystal, from the CIF -- or from the bare cell when there
    are no atoms in it yet."""
    text = archive.read(STRUCTURE_PART).decode("utf-8")
    try:
        return read_cif_string(text, path.name)
    except ValueError:
        if CELL_PART not in names:
            raise
        return _empty_structure(_load(archive, CELL_PART, names))


def _empty_structure(data: dict):
    from xtal.core.lattice import Lattice
    from xtal.core.spacegroup import SpaceGroup
    from xtal.core.structure import Structure

    return Structure(
        lattice=Lattice.from_dict(data["lattice"]),
        space_group=SpaceGroup.from_dict(data["space_group"]))


def _restore_bonds(structure, data: dict) -> None:
    """Put the hand-drawn bonds back on the structure the CIF gave us.

    Bond indices are positions in the asymmetric unit and the operation
    is an index into the space group, so both only mean anything
    against the structure they were saved with.  A bond that no longer
    fits -- because the CIF part was edited by hand, say -- is dropped
    with the rest kept, rather than taking the whole project down.
    """
    structure.bond_rules = dict(data.get("bond_rules", {}))
    for record in data.get("bonds", []):
        try:
            structure.add_bond(Bond.from_dict(record))
        except (ValueError, IndexError, KeyError, TypeError):
            structure.meta.setdefault("warnings", []).append(
                f"dropped an unreadable bond: {record}")


def _dump(data: dict) -> str:
    return json.dumps(data, indent=1, sort_keys=True, default=_plain)


def _plain(value):
    """numpy scalars and arrays, as JSON understands them."""
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"cannot store {type(value).__name__} in a project")


def _load(archive, name: str, names: set) -> dict:
    if name not in names:
        return {}
    try:
        return json.loads(archive.read(name).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
