"""
xtal.io.pmg
===========
pymatgen's ``Structure`` as JSON.

pymatgen serialises almost everything through an ``MSONable``
convention: a dict carrying ``@module`` and ``@class`` beside the
object's own fields, which ``MontyDecoder`` reads back.  For a
``Structure`` those fields are a lattice matrix and a list of sites,
each with its species, its occupancies and its fractional coordinates.

**This does not import pymatgen, and does not want to.**  The format
is a documented shape rather than a pickle, and the half of it a
crystal needs is small: reading it here costs no dependency at all,
where depending on pymatgen would cost a large one, and one that
brings its own numpy and its own spglib to argue with the ones already
installed.  What that buys is interchange with a scripting ecosystem
this application otherwise has no door onto -- a structure can be
handed to pymatgen, ASE through pymatgen, or anything that has
learned to read a ``Structure`` dict.

Partial occupancy survives in both directions.  Symmetry does not:
a pymatgen ``Structure`` is a list of sites in a cell and has nowhere
to record a space group, so what is written is P1 and what is read
back is P1 -- :func:`xtal.core.symmetry.detect` is how a group is
found again.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.structure import Structure
from xtal.io.text import read_text

MODULE = "pymatgen.core.structure"
CLASS = "Structure"


def read_pmg_json(path) -> Structure:
    """Read a pymatgen ``Structure`` dict."""
    path = Path(path)
    data = json.loads(read_text(path))
    return from_dict(data, name=path.stem, source=str(path))


def from_dict(data: dict, name: str = "structure",
              source: str = "") -> Structure:
    """The conversion itself, so a dict in memory can use it too."""
    if not isinstance(data, dict):
        raise ValueError("a pymatgen structure is a JSON object")
    if data.get("@class") not in (None, CLASS):
        raise ValueError(
            f"this is a pymatgen {data['@class']}, not a {CLASS}")
    try:
        matrix = np.array(data["lattice"]["matrix"], dtype=float)
        rows = data["sites"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"not a pymatgen structure: no {exc}") from None

    sites = []
    for row in rows:
        frac = row.get("abc")
        if frac is None:
            raise ValueError(
                "a site with no fractional coordinates; this reader "
                "does not accept cartesian-only sites")
        # A disordered site is a list of species with occupancies.
        # Each becomes one site here, which is how this application
        # writes partial occupancy too.
        for species in row.get("species") or [{}]:
            element = str(species.get("element")
                          or species.get("symbol") or "X")
            sites.append(Site(
                element=element,
                frac=np.array(frac, dtype=float),
                occupancy=float(species.get("occu", 1.0)),
                label=row.get("label") or None))

    structure = Structure(lattice=Lattice(matrix), sites=sites)
    structure.meta.update({"title": name, "format": "pmg-json"})
    if source:
        structure.meta["source"] = source
    structure.ensure_labels()
    return structure


def write_pmg_json(structure: Structure, path, **_ignored) -> Path:
    """Write the P1 cell as a pymatgen ``Structure`` dict."""
    path = Path(path)
    path.write_text(json.dumps(to_dict(structure), indent=2),
                    encoding="utf-8")
    return path


def to_dict(structure: Structure) -> dict:
    """The P1 cell, as the dict pymatgen's ``from_dict`` expects."""
    from xtal.core import p1
    cell = p1.expand(structure)
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    sites = []
    for index in range(cell.n_atoms):
        element = cell.elements[index]
        sites.append({
            "species": [{"element": element,
                         "occu": float(cell.occupancy[index])}],
            "abc": [float(v) for v in cell.frac[index]],
            "label": cell.labels[index] or element,
            "properties": {},
        })
    return {
        "@module": MODULE,
        "@class": CLASS,
        "charge": 0,
        "lattice": {
            "matrix": [[float(v) for v in row] for row in matrix],
            "a": float(structure.lattice.parameters[0]),
            "b": float(structure.lattice.parameters[1]),
            "c": float(structure.lattice.parameters[2]),
            "alpha": float(structure.lattice.parameters[3]),
            "beta": float(structure.lattice.parameters[4]),
            "gamma": float(structure.lattice.parameters[5]),
            "volume": float(structure.lattice.volume),
        },
        "sites": sites,
    }
