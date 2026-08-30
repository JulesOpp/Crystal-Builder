"""Bond perception, explicit overrides, and the connectivity graph."""

import numpy as np
import pytest

from xtal import Bond, Lattice, Structure
from xtal.core import bonding, p1


def test_rutile_coordination(rutile):
    """Ti is octahedral, O is three-coordinate -- the textbook rutile
    connectivity."""
    graph = bonding.graph(rutile)
    assert list(graph.coordination()) == [6, 6, 3, 3, 3, 3]
    assert len(graph.bonds) == 12
    assert all(1.9 < b.distance < 2.0 for b in graph.bonds)


def test_quartz_tetrahedra(quartz):
    graph = bonding.graph(quartz)
    cell = p1.expand(quartz)
    for k in range(cell.n_atoms):
        expected = 4 if cell.elements[k] == "Si" else 2
        assert len(graph.neighbors(k)) == expected
    assert all(b.distance == pytest.approx(1.61, abs=0.02)
               for b in graph.bonds)


def test_molecular_crystal_gives_discrete_fragments(dry_ice):
    graph = bonding.graph(dry_ice)
    fragments = graph.fragments()
    assert len(fragments) == 4
    assert all(len(f) == 3 for f in fragments)
    assert all(not f.periodic and f.kind == "molecule"
               for f in fragments)


def test_framework_is_flagged_as_periodic(rutile):
    graph = bonding.graph(rutile)
    fragments = graph.fragments()
    assert len(fragments) == 1
    assert fragments[0].periodic
    assert fragments[0].kind == "framework"
    assert len(graph.fragment_containing(0)) == 6


def test_metals_do_not_bond_to_each_other_by_default():
    """Bare bcc iron: chemically bonded, but drawing metal-metal bonds
    turns a metal structure into a hairball, so VESTA and we leave them
    off unless asked."""
    iron = Structure.from_arrays(
        Lattice.cubic(2.87), ["Fe"], [[0, 0, 0]], space_group="Im-3m")
    assert len(bonding.perceive(iron)) == 0
    rules = bonding.BondRules(allow_metal_metal=True)
    assert len(bonding.perceive(iron, rules)) > 0


def test_pair_ranges_override_the_radii(rutile):
    rules = bonding.BondRules(pair_ranges={("O", "Ti"): (0.0, 1.95)})
    bonds = bonding.perceive(rutile, rules)
    assert len(bonds) == 8                  # only the shorter Ti-O
    assert all(b.distance < 1.95 for b in bonds)


def test_forbidden_pairs(quartz):
    rules = bonding.BondRules(forbidden={("Si", "O")})
    assert bonding.perceive(quartz, rules) == []


def test_explicit_bonds_propagate_through_symmetry(rutile):
    """Draw one Ti-O bond in the asymmetric unit and every symmetry
    equivalent gets it -- the VESTA behaviour."""
    rules = bonding.BondRules(forbidden={("Ti", "O")})
    assert bonding.perceive(rutile, rules) == []

    rutile.add_bond(Bond(0, 1))
    bonds = bonding.perceive(rutile, rules)
    # The whole orbit of the *pair*: rutile's octahedron has two
    # apical Ti-O bonds and there are two Ti in the cell.
    assert len(bonds) == 4
    assert all(b.explicit for b in bonds)
    assert len({round(b.distance, 6) for b in bonds}) == 1
    cell = p1.expand(rutile)
    touched = {b.i for b in bonds} | {b.j for b in bonds}
    assert {int(cell.site_idx[k]) for k in touched} == {0, 1}


def test_suppressed_bonds_remove_perceived_ones(rutile):
    before = len(bonding.perceive(rutile))
    rutile.add_bond(Bond(0, 1, kind="suppressed"))
    after = len(bonding.perceive(rutile))
    assert before == 12                     # 4 apical + 8 equatorial
    assert after == before - 4              # the apical orbit, entire


def test_bonds_across_the_cell_boundary_are_found():
    """The two atoms are at opposite ends of the cell and bonded only
    through the periodic image."""
    s = Structure.from_arrays(
        Lattice.cubic(6.0), ["C", "C"],
        [[0.02, 0.5, 0.5], [0.77, 0.5, 0.5]])
    bonds = bonding.perceive(s)
    assert len(bonds) == 1                  # 1.5 A through the wall,
    assert bonds[0].image != (0, 0, 0)      # 4.5 A inside the cell
    assert bonds[0].distance == pytest.approx(1.5)


def test_shell_expansion(dry_ice):
    graph = bonding.graph(dry_ice)
    seed = {0}
    assert graph.shell(seed, 0) == seed
    assert len(graph.shell(seed, 1)) == 3       # the whole CO2
    assert len(graph.shell(seed, 5)) == 3       # and no further


def test_rules_round_trip_through_a_dict():
    rules = bonding.BondRules(
        scale=1.3, pair_ranges={("O", "Ti"): (0.5, 2.1)},
        forbidden={("O", "O")}, allow_metal_metal=True)
    back = bonding.BondRules.from_dict(rules.to_dict())
    assert back.scale == 1.3
    assert back.allow_metal_metal
    assert back.cutoff("Ti", "O") == (0.5, 2.1)
    assert not back.allows("O", "O")
    assert bonding.BondRules.from_dict({}).scale == \
        bonding.DEFAULT_SCALE


def test_cutoffs_are_symmetric_and_radius_based():
    rules = bonding.BondRules()
    assert rules.cutoff("Si", "O") == rules.cutoff("O", "Si")
    assert rules.max_cutoff(["Si", "O"]) >= rules.cutoff("Si", "O")[1]
    assert rules.max_cutoff([]) == 0.0


def test_bond_keys_ignore_direction():
    a = bonding.CellBond(1, 2, (1, 0, 0), 1.5)
    b = bonding.CellBond(2, 1, (-1, 0, 0), 1.5)
    assert a.key() == b.key()


def test_empty_structure_has_no_bonds():
    assert bonding.perceive(Structure.empty()) == []


# ------------------------------------------------ drawing bonds by hand

def _all_fixtures(rutile, quartz, halite, dry_ice):
    return {"rutile": rutile, "quartz": quartz, "halite": halite,
            "dry ice": dry_ice}


def test_every_drawn_bond_can_be_drawn_by_hand(rutile, quartz, halite,
                                               dry_ice):
    """Click two atoms that already have a bond between them and the
    bond you get back must be that bond.

    A stored bond used to be able to relate its two sites only through
    the *same* operation, so most pairs had to be refused: in Fm-3m
    that was every single one of them, which made Add Bond look broken
    rather than restricted.
    """
    for name, structure in _all_fixtures(rutile, quartz, halite,
                                         dry_ice).items():
        cell = p1.expand(structure)
        for perceived in bonding.graph(structure).bonds:
            stored = bonding.bond_between(
                structure, cell, perceived.i, perceived.j,
                (0, 0, 0), perceived.image)
            orbit = {b.key() for b in bonding.map_explicit_bond(
                structure, cell, stored)}
            assert perceived.key() in orbit, (
                f"{name}: {perceived} came back as {stored}")


def test_hand_drawn_bonds_partition_the_perceived_ones(rutile, quartz,
                                                       halite, dry_ice):
    """Every bond belongs to exactly one orbit, every orbit is one bond
    length, and the orbits between them cover the cell."""
    for name, structure in _all_fixtures(rutile, quartz, halite,
                                         dry_ice).items():
        cell = p1.expand(structure)
        perceived = bonding.graph(structure).bonds
        remaining = {b.key() for b in perceived}
        covered = set()
        for b in perceived:
            if b.key() in covered:
                continue
            stored = bonding.bond_between(structure, cell, b.i, b.j,
                                          (0, 0, 0), b.image)
            orbit = bonding.map_explicit_bond(structure, cell, stored)
            keys = {c.key() for c in orbit}
            assert not (keys & covered), f"{name}: orbits overlap"
            assert keys <= remaining, f"{name}: orbit escapes the cell"
            lengths = {round(c.distance, 6) for c in orbit}
            assert len(lengths) == 1, f"{name}: orbit is not one length"
            covered |= keys
        assert covered == remaining, f"{name}: orbits miss a bond"


def test_a_hand_drawn_bond_keeps_the_length_it_was_drawn_with():
    """A bond across a periodic boundary must expand to the short
    contact it was drawn on, not to the long way round.  The sign of
    the stored translation is the whole of that."""
    s = Structure.from_arrays(
        Lattice.cubic(5.0), ["C", "O"],
        [[0.1, 0.5, 0.5], [0.9, 0.5, 0.5]], space_group="P1")
    cell = p1.expand(s)
    perceived = bonding.perceive(s)
    assert len(perceived) == 1
    assert perceived[0].distance == pytest.approx(1.0)

    stored = bonding.bond_between(s, cell, 0, 1, (0, 0, 0),
                                  perceived[0].image)
    expanded = bonding.map_explicit_bond(s, cell, stored)
    assert len(expanded) == 1
    assert expanded[0].key() == perceived[0].key()
    assert expanded[0].distance == pytest.approx(1.0)

    # ... and the geometry the drawing code reads off it agrees
    separation = (cell.frac[expanded[0].j]
                  + np.array(expanded[0].image)
                  - cell.frac[expanded[0].i])
    assert np.linalg.norm(separation @ s.lattice.matrix) == \
        pytest.approx(1.0)


def test_bonding_the_copy_next_door_is_a_different_bond():
    """The same two P1 atoms, clicked in different cells, are two
    different bonds."""
    s = Structure.from_arrays(
        Lattice.cubic(5.0), ["C", "O"],
        [[0.1, 0.5, 0.5], [0.9, 0.5, 0.5]], space_group="P1")
    cell = p1.expand(s)
    near = bonding.bond_between(s, cell, 0, 1, (0, 0, 0), (-1, 0, 0))
    far = bonding.bond_between(s, cell, 0, 1)
    assert near.image == (-1, 0, 0)
    assert far.image == (0, 0, 0)
    assert near.key() != far.key()


def test_a_bond_and_the_same_bond_backwards_are_one_bond(halite):
    """Whichever end you click first, it is the same bond -- so the
    second click must not add a second copy."""
    cell = p1.expand(halite)
    perceived = bonding.graph(halite).bonds[0]
    forward = bonding.bond_between(halite, cell, perceived.i,
                                   perceived.j, (0, 0, 0),
                                   perceived.image)
    backward = bonding.bond_between(
        halite, cell, perceived.j, perceived.i,
        perceived.image, (0, 0, 0))

    group = halite.space_group
    assert forward.key(group) == backward.key(group)
    assert halite.add_bond(forward) is True
    assert halite.add_bond(backward) is False       # already there
    assert len(halite.bonds) == 1
    assert halite.remove_bond(backward) is True


def test_reversing_a_bond_twice_gives_it_back(rutile):
    group = rutile.space_group
    for op in range(group.order):
        bond = Bond(0, 1, image=(1, -2, 0), op=op)
        there_and_back = bond.reverse(group).reverse(group)
        assert there_and_back.i == bond.i
        assert there_and_back.j == bond.j
        assert there_and_back.op == bond.op
        assert there_and_back.image == bond.image
