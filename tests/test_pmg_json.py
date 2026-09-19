"""pymatgen's Structure as JSON, read and written without pymatgen.

The format is a documented shape rather than a pickle -- an MSONable
dict of a lattice matrix and a list of sites -- so the half a crystal
needs costs no dependency at all. Depending on pymatgen would cost a
large one, with its own numpy and its own spglib to argue with the
ones already installed.
"""

import json

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1
from xtal.io import FORMATS
from xtal.io.pmg import from_dict, to_dict


def _nacl():
    return Structure.from_arrays(
        Lattice.cubic(5.64), ["Na", "Cl"],
        [[0, 0, 0], [0.5, 0.5, 0.5]], space_group="Fm-3m")


def test_a_structure_survives_the_round_trip(tmp_path):
    original = _nacl()
    path = tmp_path / "s.json"
    FORMATS.write(original, path, fmt="pmg-json")
    back = FORMATS.read(path)
    cell = p1.expand(original)
    assert len(back.sites) == cell.n_atoms
    assert np.allclose(original.lattice.matrix, back.lattice.matrix)
    assert sorted({s.element for s in back.sites}) == ["Cl", "Na"]


def test_what_is_written_is_the_shape_pymatgen_reads():
    """@module and @class are how MontyDecoder knows what to build;
    a dict without them is just a dict."""
    data = to_dict(_nacl())
    assert data["@module"] == "pymatgen.core.structure"
    assert data["@class"] == "Structure"
    assert "matrix" in data["lattice"]
    assert data["sites"][0]["species"][0]["element"] in ("Na", "Cl")
    assert len(data["sites"][0]["abc"]) == 3
    json.dumps(data)              # it has to actually serialise


def test_partial_occupancy_survives_both_ways(tmp_path):
    """A disordered site is a list of species with occupancies, which
    is how this application writes partial occupancy too."""
    data = to_dict(_nacl())
    data["sites"][0]["species"] = [{"element": "Na", "occu": 0.6}]
    assert from_dict(data).sites[0].occupancy == pytest.approx(0.6)


def test_a_disordered_site_becomes_one_site_per_species():
    """pymatgen writes two species on one site; there is no single
    site here that can be two elements at once."""
    data = to_dict(_nacl())
    data["sites"][0]["species"] = [{"element": "Na", "occu": 0.5},
                                   {"element": "K", "occu": 0.5}]
    elements = [s.element for s in from_dict(data).sites]
    assert elements.count("Na") + elements.count("K") >= 2


def test_json_that_is_not_a_structure_says_so(tmp_path):
    """`.json` is a common suffix and this is not the only thing that
    uses it, so the refusal has to name what was missing."""
    path = tmp_path / "workspace.json"
    path.write_text('{"session": ["a.cif"]}')
    with pytest.raises(ValueError, match="not a pymatgen structure"):
        FORMATS.read(path)


def test_another_pymatgen_class_is_refused_by_name():
    with pytest.raises(ValueError, match="Molecule"):
        from_dict({"@class": "Molecule", "lattice": {}, "sites": []})


def test_the_format_says_it_keeps_occupancy_and_not_symmetry():
    """A pymatgen Structure is a list of sites in a cell: it has
    nowhere to record a space group."""
    keeps = FORMATS.get("pmg-json").keeps
    assert "occupancy" in keeps
    assert "symmetry" not in keeps
