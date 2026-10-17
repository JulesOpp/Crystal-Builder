"""A rod linker drawn whole: its carboxylates and phenolates found by
their bonds and made its connection points, each named by its donor."""

from pathlib import Path

import numpy as np
import pytest

from xtal.mof import donors
from xtal.mof.block import CONNECTION_DISTANCE
from xtal.mof.rod import Rod, shipped
from xtal.mof.trimer import Block

DATA = Path(__file__).resolve().parent / "data"


def molecule(symbols, bonds):
    """A block with nothing but its graph: the donors are bonds."""
    return Block(list(symbols), np.arange(3 * len(symbols), dtype=float)
                 .reshape(-1, 3), [(i, j, "S") for i, j in bonds], [])


def test_a_phenol_drawn_as_the_acid_or_the_anion_is_one_kind():
    """Phenol and phenoxide are one donor; groups.py would call the
    anion a ketone, which is why this module reads its own bonds."""
    ring = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0)]
    acid = molecule("CCCCCCOH", ring + [(0, 6), (6, 7)])
    anion = molecule("CCCCCCO", ring + [(0, 6)])
    assert [d.kind for d in donors.find(acid)] == [donors.PHENOLATE]
    assert [d.kind for d in donors.find(anion)] == [donors.PHENOLATE]
    assert donors.find(acid)[0].atoms == (6, 7)


def test_a_carboxylic_acid_is_one_carboxylate_and_not_a_phenolate():
    """Its hydroxyl oxygen is on a carbon with three bonds too; claimed
    by the carboxylate first, it is never also a phenolate."""
    acid = molecule("CCOOH", [(0, 1), (1, 2), (1, 3), (3, 4)])
    found = donors.find(acid)
    assert [(d.kind, d.attach, d.partner) for d in found] == [
        (donors.CARBOXYLATE, 1, 0)]
    assert found[0].atoms == (1, 2, 3, 4)


def test_an_alcohol_is_no_donor():
    """An oxygen on an sp3 carbon is not what MOF-74's rod holds."""
    ethanol = molecule("CCOHHHHHH", [(0, 1), (1, 2), (2, 3), (0, 4),
                                     (0, 5), (0, 6), (1, 7), (1, 8)])
    assert donors.find(ethanol) == []


def test_a_drawn_donor_becomes_an_x_where_a_cut_one_would_be():
    """The donor's atoms go and an X stands 0.75 A from its attaching
    atom toward the linker, as linker_from_structure puts one -- so
    the joint the rod's X and the linker's meet at is the crystal's."""
    whole = Block.read(DATA / "rod_dobpdc_whole.xyz")
    core = donors.as_linker(whole)
    assert core.kinds == ("carboxylate", "phenolate") * 2
    assert sorted(s for s in core.symbols if s != "X") == \
        ["C"] * 12 + ["H"] * 6
    for found, x in zip(donors.find(whole), core.connections,
                        strict=True):
        attach = whole.positions[found.attach]
        partner = whole.positions[found.partner]
        assert np.linalg.norm(core.positions[x] - attach) == \
            pytest.approx(CONNECTION_DISTANCE)
        assert np.linalg.norm(core.positions[x] - partner) < \
            np.linalg.norm(attach - partner)


def test_a_linker_with_bare_points_is_left_as_drawn():
    """A shipped linker's X atoms name no donor, and pair with any
    rod point as they always did."""
    from xtal.mof.rod import shipped_linkers

    bare = Block.read(shipped_linkers()["BTDD"])
    assert donors.as_linker(bare) is bare
    assert bare.kinds == ()


def test_a_drawing_with_no_points_and_no_donors_is_refused():
    with pytest.raises(donors.DonorError, match="no carboxylate"):
        donors.as_linker(molecule("CC", [(0, 1)]))


def test_mof_74s_rod_names_its_carboxylate_and_phenolate_points():
    """By the atoms each X hangs off: one carbon with two oxygens, or
    one oxygen.  Ni2Cl2BTDD's triazolate is named by its symbols."""
    rod = Rod.read(shipped()["MOF-74_Zn"])
    kinds = sorted(rod.kind(x) for x in rod.connections)
    assert kinds == ["carboxylate"] * 3 + ["phenolate"] * 3
    btdd = Rod.read(shipped()["Ni2Cl2BTDD_Ni"])
    assert {btdd.kind(x) for x in btdd.connections} == {"CC"}
