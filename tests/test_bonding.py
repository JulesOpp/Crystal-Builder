"""Bond perception, explicit overrides, and the connectivity graph."""

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
    assert len(bonds) == 2                  # one per Ti image
    assert all(b.explicit for b in bonds)
    cell = p1.expand(rutile)
    touched = {b.i for b in bonds} | {b.j for b in bonds}
    assert {int(cell.site_idx[k]) for k in touched} == {0, 1}


def test_suppressed_bonds_remove_perceived_ones(rutile):
    before = len(bonding.perceive(rutile))
    rutile.add_bond(Bond(0, 1, kind="suppressed"))
    after = len(bonding.perceive(rutile))
    assert after == before - 2


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
