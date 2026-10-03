"""Monomers joined into chains, and the order and hands they come in."""

from __future__ import annotations

import numpy as np
import pytest

from xtal.build import MISSING, installed
from xtal.polymer import chain, monomer, sequence
from xtal.polymer.sequence import Sequence, SequenceError

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


def _angle(a, b, c) -> float:
    u, v = a - b, c - b
    return float(np.degrees(np.arccos(
        u @ v / (np.linalg.norm(u) * np.linalg.norm(v)))))


@needs_rdkit
def test_an_all_trans_pe_chain_is_straight_with_tetrahedral_angles():
    """The planar zigzag: every backbone torsion 180, every angle near
    tetrahedral, and every carbon in one plane.  A joint that got the
    axis or the torsion wrong bends the chain somewhere along it."""
    pe = monomer.from_library("Polyethylene")
    built = chain.single_chain([pe] * 10)
    symbols, cart, _bonds = built.atoms()
    carbons = cart[[i for i, s in enumerate(symbols) if s == "C"]]

    assert len(carbons) == 20
    for k in range(9):
        assert abs(chain.joint_torsion(built.units[k],
                                       built.units[k + 1])) == \
            pytest.approx(180.0, abs=1e-6)
    for k in range(1, 19):
        assert 107.0 < _angle(*carbons[k - 1:k + 2]) < 115.0
    centred = carbons - carbons.mean(axis=0)
    _, spread, _ = np.linalg.svd(centred)
    assert spread[2] < 1e-3                      # planar
    assert spread[1] < 0.1 * spread[0]           # and straight


@needs_rdkit
def test_a_joint_bond_is_the_covalent_radius_sum():
    """Never where the two X happened to meet: an X is 0.75 A out by
    convention and says nothing about the bond it stands for.  Two sp3
    carbons are Cordero's 0.76 each."""
    pe = monomer.from_library("Polyethylene")
    built = chain.single_chain([pe] * 3)

    for k, joint in enumerate(built.joints):
        (t, h), = joint.pairs
        length = np.linalg.norm(built.units[k].cart[t]
                                - built.units[k + 1].cart[h])
        assert length == pytest.approx(1.52, abs=1e-6)


@needs_rdkit
def test_no_connection_point_survives_into_a_chain():
    """Every X is used at a joint or capped -- the door every engine
    holds markers back at would otherwise be the only thing between a
    built polymer and a force field."""
    pmma = monomer.from_library("PMMA")
    symbols, _cart, bonds = chain.single_chain([pmma] * 5).atoms()
    n = len(symbols)
    degree = np.bincount(np.array([[i, j] for i, j, _ in bonds]).ravel(),
                         minlength=n)

    assert "X" not in symbols
    assert symbols.count("C") == 25
    # every carbon four-coordinate, the carbonyl's and the ester's too
    # counted by bond, not by valence
    assert all(degree[i] >= 3 for i in range(n) if symbols[i] == "C")


@needs_rdkit
def test_a_ladder_joint_bonds_both_members_and_has_two_flips():
    """PIM-1 meets the next unit through two C-O bonds, both at an aryl
    ether's length, and the two pairings of members are two different
    chains -- the flip the packer samples instead of a torsion."""
    pim = monomer.from_library("PIM-1")
    straight = chain.single_chain([pim] * 3, flips=[False, False])
    flipped = chain.single_chain([pim] * 3, flips=[False, True])

    for built in (straight, flipped):
        for k, joint in enumerate(built.joints):
            assert len(joint.pairs) == 2
            for t, h in joint.pairs:
                length = np.linalg.norm(built.units[k].cart[t]
                                        - built.units[k + 1].cart[h])
                assert 1.30 < length < 1.45
    assert straight.joints[1].pairs != flipped.joints[1].pairs
    assert not np.allclose(straight.units[2].cart,
                           flipped.units[2].cart, atol=0.5)


@needs_rdkit
def test_a_troger_base_ladder_closes_its_bicycle():
    """PIM-EA-TB's joint is a nitrogen and a methylene meeting two ring
    carbons, a ring that is not flat.  Embedded open, the base splayed
    3.8 A apart and the joint came out 1.19 and 1.75 A."""
    tb = monomer.from_library("PIM-EA-TB")
    built = chain.single_chain([tb] * 2)

    (t1, h1), (t2, h2) = built.joints[0].pairs
    lengths = sorted(
        np.linalg.norm(built.units[0].cart[t] - built.units[1].cart[h])
        for t, h in ((t1, h1), (t2, h2)))
    assert 1.35 < lengths[0] and lengths[1] < 1.55


def test_syndiotactic_alternates_hands_and_isotactic_does_not():
    rng = np.random.default_rng(1)
    iso = sequence.draw(Sequence(tacticity="isotactic"), 1, 8, rng)
    syndio = sequence.draw(Sequence(tacticity="syndiotactic"), 1, 8, rng)

    assert [hand for _, hand in iso] == [False] * 8
    assert [hand for _, hand in syndio] == [False, True] * 4


def test_atactic_draws_meso_dyads_at_the_probability_asked():
    """Bernoullian: each dyad meso with p, independently.  2000 dyads
    put three standard deviations at 0.034."""
    rng = np.random.default_rng(7)
    drawn = sequence.draw(Sequence(tacticity="atactic", p_meso=0.7), 1,
                          2001, rng)
    hands = [hand for _, hand in drawn]
    meso = np.mean(np.diff(np.array(hands, dtype=int)) == 0)

    assert meso == pytest.approx(0.7, abs=0.034)


def test_a_block_copolymer_has_the_blocks_asked_for():
    rng = np.random.default_rng(0)
    drawn = sequence.draw(Sequence(composition="block", blocks=(3, 2)),
                          2, 10, rng)

    assert [which for which, _ in drawn] == [0, 0, 0, 1, 1] * 2


def test_an_alternating_copolymer_alternates():
    rng = np.random.default_rng(0)
    drawn = sequence.draw(Sequence(composition="alternating"), 2, 6, rng)

    assert [which for which, _ in drawn] == [0, 1] * 3


def test_a_random_copolymer_draws_its_fractions():
    rng = np.random.default_rng(3)
    drawn = sequence.draw(Sequence(composition="random",
                                   fractions=(3.0, 1.0)), 2, 4000, rng)

    assert np.mean([which == 1 for which, _ in drawn]) == \
        pytest.approx(0.25, abs=0.03)


def test_a_copolymer_of_one_monomer_is_refused():
    with pytest.raises(SequenceError, match="two monomers"):
        sequence.draw(Sequence(composition="alternating"), 1, 4,
                      np.random.default_rng(0))


@needs_rdkit
def test_a_drawn_hand_is_a_mirrored_unit():
    """A drawn ``True`` is the monomer's reflection, made once and
    reused, so every unit of one hand is the same object."""
    pp = monomer.from_library("Polypropylene")
    drawn = [(0, False), (0, True), (0, True)]
    built = sequence.units([pp], drawn)

    assert [u.mirror for u in built] == [False, True, True]
    assert built[1] is built[2]
