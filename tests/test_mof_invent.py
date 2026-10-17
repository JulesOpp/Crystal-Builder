"""New linkers made for a requirement (xtal.mof.invent).

What breaks if these regress: a suggestion offered for a span it does
not have, a clicked new linker that cannot be built by its name, or
an element outside C, H, N and O in what is meant to be a simple
isoreticular series.
"""

from __future__ import annotations

import pytest

from xtal.build import chem
from xtal.mof import invent, linkers
from xtal.mof.linkers import Requirement

needs_rdkit = pytest.mark.skipif(not chem.installed(),
                                 reason="needs the build extra")


def _span(value, tolerance=0.3, donor="aryl"):
    return Requirement(2, value, value - tolerance, value + tolerance,
                       donor)


@needs_rdkit
def test_every_unit_adds_the_length_it_is_stored_with():
    """The estimate is the stored lengths summed; a length that drifts
    from what RDKit embeds sends the embedding budget to molecules a
    whole unit away."""
    pp = linkers.measure_smiles(invent._linear_smiles(("P", "P"),
                                                      "aryl"))[0]
    for unit, length in invent.LENGTHS.items():
        chain = ("P", unit, "P")
        measured = linkers.measure_smiles(
            invent._linear_smiles(chain, "aryl"))[0] - pp
        # A whole unit is 2-4 A; Windows' embedding bends P-V-P
        # 0.09 A shorter than macOS's, which is no unit at all.
        assert measured == pytest.approx(length, abs=0.15), unit


def test_an_invented_name_spells_its_molecule():
    """A clicked new linker is built by name in a process that never
    suggested it, so the name must give back the same SMILES."""
    req = _span(12.9, donor="any")
    for _value, name, _smiles in invent.estimates(req)[:40]:
        assert invent.by_name_is_one(name)
        found = invent._NAME.match(name)
        assert found, name
    linear = invent.name_of(2, "", ("P", "Pn", "P"), "aryl")
    assert linear == "G-L-P_Pn_P-aryl"
    branched = invent.name_of(3, "amine", ("P",), "pyridyl")
    assert branched == "G-T-amine-P-py"
    assert not invent.by_name_is_one("E14")


def test_the_series_is_carbon_hydrogen_nitrogen_and_oxygen():
    allowed = set("CHNOcno*[]+()=#/0123456789%")
    for topicity, value in ((2, 12.0), (3, 8.0), (4, 6.0), (6, 6.0)):
        req = Requirement(topicity, value, value - 3, value + 3,
                          "any")
        for _value, _name, smiles in invent.estimates(req):
            assert set(smiles) <= allowed, smiles


@needs_rdkit
def test_a_new_linker_is_offered_only_where_it_measures_inside():
    """Estimated, then judged by its embedding: every one offered
    measures inside the range, and the nearest is a terphenyl's
    span with a functional group on its middle ring."""
    req = _span(12.9)
    made = invent.invent(req)
    assert made
    assert all(req.low <= c.value <= req.high for c in made)
    assert all(c.source == "invented" for c in made)
    assert any("_P" in c.name and c.name != "G-L-P_P_P-aryl"
               for c in made)


@needs_rdkit
def test_an_invented_name_builds_the_molecule_it_was_offered_as(
        tmp_path):
    from xtal.mof.catalog import read_building_block

    offered = invent.invent(_span(12.9))[0]
    again = linkers.generated(offered.name)
    assert again.smiles == offered.smiles
    path = linkers.write_block(again, tmp_path)
    assert read_building_block(path).n_connections == 2


@needs_rdkit
def test_a_suggestion_keeps_room_for_new_molecules_and_marks_them():
    """Asked with ``invent``, a third of the list is kept for new
    molecules, each marked + and said to be new."""
    req = _span(12.9, tolerance=1.0)
    found = linkers.suggest(req, None, n=6, invent=True)
    new = [s for s in found if s.candidate.source == "invented"]
    assert 1 <= len(new) <= 2
    assert all(linkers.mark(s) == "+" for s in new)
    assert "+ is a new molecule" in linkers.legend(found)
    assert "(new)" in new[0].sentence(req)
    plain = linkers.suggest(req, None, n=6)
    assert all(s.candidate.source != "invented" for s in plain)
