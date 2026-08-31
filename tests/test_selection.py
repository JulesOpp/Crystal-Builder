"""Selections over the P1 cell, and their mapping back to sites."""

import numpy as np

from xtal.core import bonding, p1
from xtal.core import selection as sel
from xtal.core.selection import Selection


def test_basic_editing():
    s = Selection()
    assert s.is_empty and len(s) == 0

    s.set_atoms([3, 1, 1])
    assert s.atoms == {1, 3} and s.focus == 3
    s.add_atoms([5])
    assert s.atoms == {1, 3, 5}
    s.remove_atoms([1])
    assert s.atoms == {3, 5}
    assert s.toggle_atom(3) is False        # was selected, now not
    assert s.toggle_atom(7) is True
    assert 7 in s
    s.clear()
    assert s.is_empty and s.focus is None


def test_invert_and_mask():
    s = Selection()
    s.set_atoms([0, 2])
    s.invert(4)
    assert s.atoms == {1, 3}
    assert list(s.mask(4)) == [False, True, False, True]
    assert list(Selection().mask(3)) == [False] * 3


def test_prune_after_the_structure_shrinks():
    s = Selection()
    s.set_atoms([0, 5, 9])
    s.bonds = {(0, 5, (0, 0, 0)), (5, 9, (0, 0, 0))}
    s.focus = 9
    s.prune(6)
    assert s.atoms == {0, 5}
    assert s.bonds == {(0, 5, (0, 0, 0))}
    assert s.focus is None


def test_copy_is_independent():
    s = Selection()
    s.set_atoms([1, 2])
    c = s.copy()
    c.add_atoms([3])
    assert s.atoms == {1, 2}


def test_a_copy_keeps_every_set_it_had():
    """All three sets and the focus, each in its own field: the net
    edges used to land in the focus, which made a copied selection
    claim to have edges nobody drew."""
    s = Selection()
    s.set_atoms([1, 2])
    s.bonds = {(1, 2, (0, 0, 0))}
    s.topology = {(1, 2, (0, 0, 1))}
    s.focus = 2

    c = s.copy()

    assert c.atoms == s.atoms
    assert c.bonds == s.bonds
    assert c.topology == s.topology
    assert c.focus == 2


def test_by_element_and_by_site(rutile):
    cell = p1.expand(rutile)
    assert sel.by_element(cell, "Ti") == {0, 1}
    assert len(sel.by_element(cell, "O")) == 4
    assert sel.by_element(cell, "Ti", "O") == set(range(6))
    assert sel.by_element(cell, "Xe") == set()
    assert sel.by_site(cell, 0) == {0, 1}


def test_symmetry_orbit_grows_to_the_whole_site(quartz):
    cell = p1.expand(quartz)
    assert sel.symmetry_orbit(cell, {0}) == {0, 1, 2}        # Si, 3a
    assert len(sel.symmetry_orbit(cell, {3})) == 6           # O, 6c


def test_orbit_completeness_is_what_gates_an_edit(rutile):
    """One image of a two-fold site is not something the asymmetric
    unit can express on its own."""
    cell = p1.expand(rutile)
    assert not sel.covers_whole_orbits(cell, {0})
    assert sel.covers_whole_orbits(cell, {0, 1})
    assert sel.covers_whole_orbits(cell, set())
    assert "symmetry ties them together" in sel.orbit_report(cell, {0})
    assert "1 site" in sel.orbit_report(cell, {0, 1})


def test_sites_for(rutile):
    cell = p1.expand(rutile)
    assert sel.sites_for(cell, {0, 1}) == {0}
    assert sel.sites_for(cell, {0, 3}) == {0, 1}


def test_expand_shell_and_fragment(dry_ice):
    graph = bonding.graph(dry_ice)
    assert sel.expand_shell(graph, {0}, 0) == {0}
    assert len(sel.expand_shell(graph, {0}, 1)) == 3     # a CO2
    assert len(sel.expand_fragment(graph, {0})) == 3
    # two molecules at once
    other = next(iter(set(range(12)) - sel.expand_fragment(graph, {0})))
    assert len(sel.expand_fragment(graph, {0, other})) == 6


def test_within_radius(rutile):
    cell = p1.expand(rutile)
    close = sel.within_radius(cell, rutile.lattice, {0}, 2.1)
    assert 0 in close
    assert len(close) == 5                  # Ti plus its first shell
    assert len(sel.within_radius(cell, rutile.lattice, {0}, 0.1)) == 1
    assert sel.within_radius(cell, rutile.lattice, set(), 5.0) == set()


def test_bonds_within(rutile):
    graph = bonding.graph(rutile)
    everything = sel.bonds_within(graph, range(6))
    assert len(everything) == len(graph.bonds)
    assert sel.bonds_within(graph, {0}) == set()


def test_describe(rutile):
    cell = p1.expand(rutile)
    s = Selection()
    assert "nothing" in sel.describe(rutile, cell, s)
    s.set_atoms([0, 1, 2])
    text = sel.describe(rutile, cell, s)
    assert "3 atoms" in text and "Ti2" in text and "O" in text
    s.bonds = {(0, 2, (0, 0, 0))}
    assert "1 bonds" in sel.describe(rutile, cell, s)


def test_selection_survives_a_big_real_structure():
    """A 648-atom MOF: the orbit of one peripheral Zn is 32 atoms, and
    its first coordination shell is four ligands."""
    from xtal.io import read_cif
    structure = read_cif("resources/samples/MFU4l.cif")
    cell = p1.expand(structure)
    graph = bonding.graph(structure)

    zinc = sel.by_element(cell, "Zn")
    assert len(zinc) == 40                  # 32 peripheral + 8 central
    one = {min(zinc)}
    assert len(sel.symmetry_orbit(cell, one)) == 32
    assert len(sel.expand_shell(graph, one, 1)) == 5
    assert not sel.covers_whole_orbits(cell, one)
    assert np.all(cell.frac >= 0)
