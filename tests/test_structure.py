"""The Structure data model: mutation, bonds, caching, copying."""

import numpy as np
import pytest

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Bond, Change, Structure


def rocksalt() -> Structure:
    return Structure.from_arrays(
        Lattice.cubic(5.64), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="Fm-3m")


# ---------------------------------------------------------------- basics

def test_construction_and_derived_values():
    s = rocksalt()
    assert s.n_sites == len(s) == 2
    assert s.elements == ["Na", "Cl"]
    assert s.composition() == {"Na": 1.0, "Cl": 1.0}
    assert s.space_group.number == 225
    assert not s.is_p1
    assert np.allclose(s.frac[1], [0.5, 0.5, 0.5])
    assert np.allclose(s.cart[1], [2.82, 2.82, 2.82])
    assert s[0].element == "Na"
    assert [site.element for site in s] == ["Na", "Cl"]


def test_empty_structure_is_a_p1_box():
    s = Structure.empty()
    assert s.n_sites == 0 and s.is_p1
    assert s.composition() == {}
    assert "empty" in repr(s)


def test_from_arrays_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        Structure.from_arrays(Lattice.cubic(4.0), ["Na", "Cl"],
                              [[0, 0, 0]])


def test_partial_occupancy_shows_in_the_composition():
    s = Structure.from_arrays(
        Lattice.cubic(4.0), ["Na", "K"], [[0, 0, 0], [0, 0, 0]],
        occupancies=[0.5, 0.5])
    assert s.composition() == {"Na": 0.5, "K": 0.5}


# ------------------------------------------------------------- mutation

def test_every_mutation_bumps_the_revision_with_a_hint():
    s = rocksalt()
    rev = s.revision

    s.add_site(Site("O", [0.25, 0.25, 0.25]))
    assert s.revision > rev and s.last_change == Change.TOPOLOGY

    rev = s.revision
    s.set_frac(2, [0.3, 0.3, 0.3])
    assert s.revision > rev and s.last_change == Change.POSITIONS

    rev = s.revision
    s.set_lattice(Lattice.cubic(6.0))
    assert s.revision > rev and s.last_change == Change.CELL

    rev = s.revision
    s.set_space_group("P 1")
    assert s.revision > rev and s.last_change == Change.SYMMETRY
    assert s.is_p1


def test_add_and_remove_sites_returns_undo_data():
    s = rocksalt()
    idx = s.add_sites([Site("O", [0.25, 0.25, 0.25]),
                       Site("H", [0.75, 0.75, 0.75])])
    assert idx == [2, 3] and s.n_sites == 4
    removed = s.remove_sites([2, 3])
    assert [site.element for site in removed] == ["O", "H"]
    assert s.n_sites == 2


def test_remove_sites_renumbers_surviving_bonds():
    s = Structure.from_arrays(
        Lattice.cubic(6.0), ["C", "N", "O", "S"],
        [[0, 0, 0], [0.1, 0, 0], [0.2, 0, 0], [0.3, 0, 0]])
    s.add_bond(Bond(0, 1))
    s.add_bond(Bond(2, 3, image=(1, 0, 0)))
    s.remove_sites([0])                 # drops bond 0-1, shifts 2-3
    assert [site.element for site in s] == ["N", "O", "S"]
    assert len(s.bonds) == 1
    assert (s.bonds[0].i, s.bonds[0].j) == (1, 2)
    assert s.bonds[0].image == (1, 0, 0)


def test_remove_sites_checks_bounds():
    s = rocksalt()
    with pytest.raises(IndexError):
        s.remove_sites([5])
    assert s.remove_sites([]) == []


def test_wrap_and_labels():
    s = Structure.from_arrays(
        Lattice.cubic(4.0), ["Na", "Na", "Cl"],
        [[1.25, 0, 0], [-0.5, 0, 0], [0.5, 0.5, 0.5]],
        labels=["Na9", "", ""])
    s.wrap_sites()
    assert np.allclose(s.frac[0], [0.25, 0, 0])
    assert np.allclose(s.frac[1], [0.5, 0, 0])
    s.ensure_labels()
    assert [site.label for site in s] == ["Na9", "Na1", "Cl1"]
    labels = [site.label for site in s]
    assert len(set(labels)) == len(labels)


def test_ensure_labels_does_not_collide_with_existing_ones():
    s = Structure.from_arrays(
        Lattice.cubic(4.0), ["O", "O"], [[0, 0, 0], [0.5, 0, 0]],
        labels=["O1", ""])
    s.ensure_labels()
    assert [site.label for site in s] == ["O1", "O2"]


# ---------------------------------------------------------------- bonds

def test_bonds_are_direction_independent():
    a = Bond(0, 1, image=(1, 0, 0))
    b = Bond(1, 0, image=(-1, 0, 0))
    assert a.key() == b.key()
    s = Structure.from_arrays(Lattice.cubic(4.0), ["C", "N"],
                              [[0, 0, 0], [0.5, 0, 0]])
    assert s.add_bond(a) is True
    assert s.add_bond(b) is False       # same bond, written backwards
    assert len(s.bonds) == 1
    assert s.remove_bond(b) is True
    assert s.bonds == []
    assert s.remove_bond(a) is False


def test_periodic_image_distinguishes_bonds():
    s = Structure.from_arrays(Lattice.cubic(4.0), ["C", "N"],
                              [[0, 0, 0], [0.5, 0, 0]])
    s.add_bond(Bond(0, 1))
    s.add_bond(Bond(0, 1, image=(1, 0, 0)))
    assert len(s.bonds) == 2            # both are real, different bonds


def test_bond_validation():
    s = rocksalt()
    with pytest.raises(IndexError):
        s.add_bond(Bond(0, 7))
    with pytest.raises(ValueError):
        Bond(0, 0)                      # self-bond in the same image
    assert Bond(0, 0, image=(1, 0, 0))  # ... but this one is legal
    assert s.bonds_of(0) == []


# ---------------------------------------------------------------- cache

def test_cached_values_survive_reads_and_die_on_writes():
    s = rocksalt()
    calls = []

    def expensive():
        calls.append(1)
        return len(s.sites)

    assert s.cached("n", expensive) == 2
    assert s.cached("n", expensive) == 2
    assert len(calls) == 1              # memoised

    s.add_site(Site("O", [0.25, 0.25, 0.25]))
    assert s.cached("n", expensive) == 3
    assert len(calls) == 2              # recomputed after the mutation


# ------------------------------------------------- copying / round trips

def test_copy_shares_nothing_mutable():
    s = rocksalt()
    s.meta["title"] = "halite"
    c = s.copy()
    assert c == s
    c.sites[0].frac[0] = 0.4
    c.meta["title"] = "other"
    c.add_site(Site("O", [0.1, 0.1, 0.1]))
    assert s.sites[0].frac[0] == 0.0
    assert s.meta["title"] == "halite"
    assert s.n_sites == 2


def test_dict_round_trip():
    s = rocksalt()
    s.add_bond(Bond(0, 1, image=(0, 0, 1), order=0.5))
    s.meta["source"] = "test"
    back = Structure.from_dict(s.to_dict())
    assert back == s
    assert back.space_group == s.space_group
    assert back.bonds[0].order == 0.5
    assert back.meta["source"] == "test"


def test_equality_is_structural_not_identity():
    assert rocksalt() == rocksalt()
    moved = rocksalt()
    moved.set_frac(1, [0.6, 0.5, 0.5])
    assert moved != rocksalt()
    retyped = rocksalt()
    retyped.sites[0].element = "K"
    assert retyped != rocksalt()
    regrouped = rocksalt()
    regrouped.set_space_group(SpaceGroup.p1())
    assert regrouped != rocksalt()
