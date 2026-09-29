"""Selections over the P1 cell, and their mapping back to sites."""

import numpy as np

from xtal.core import bonding, p1
from xtal.core import selection as sel
from xtal.core.selection import Selection


def test_basic_editing():
    s = Selection()
    assert s.is_empty and len(s) == 0

    s.set_atoms([3, 1, 1])
    assert s.atoms == {1, 3} and s.focus == 1
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
    assert s.focus == 9
    s.prune(6)
    assert s.atoms == {0, 5}
    assert s.order == [0, 5]
    assert s.bonds == {(0, 5, (0, 0, 0))}
    assert s.focus == 5


def test_copy_is_independent():
    s = Selection()
    s.set_atoms([1, 2])
    c = s.copy()
    c.add_atoms([3])
    assert s.atoms == {1, 2}


def test_a_copy_keeps_every_set_it_had():
    """All three sets and the order, each in its own field: the net
    edges used to land in the focus, which made a copied selection
    claim to have edges nobody drew."""
    s = Selection()
    s.set_atoms([2, 1])
    s.bonds = {(1, 2, (0, 0, 0))}
    s.topology = {(1, 2, (0, 0, 1))}

    c = s.copy()
    c.add_atoms([7])

    assert c.atoms == s.atoms | {7}
    assert c.bonds == s.bonds
    assert c.topology == s.topology
    assert s.order == [2, 1]


def test_a_selection_remembers_the_order_atoms_were_clicked():
    """Three atoms picked A-B-C make an angle about B, and the set
    alone cannot say which one B was."""
    s = Selection()
    for atom in (7, 2, 5):
        s.toggle_atom(atom)
    assert s.order == [7, 2, 5]
    assert s.focus == 5


def test_re_picking_an_atom_moves_it_to_the_end():
    """Clicking one off and on again is how somebody corrects the
    vertex, so the second click is when it was picked."""
    s = Selection()
    for atom in (7, 2, 5):
        s.toggle_atom(atom)
    s.toggle_atom(2)
    s.toggle_atom(2)
    assert s.order == [7, 5, 2]


def test_a_selection_that_was_never_clicked_is_in_index_order():
    """Select all, an orbit, an element: none of those was clicked in
    an order, and a set's own iteration order is not one anybody can
    predict twice."""
    s = Selection()
    s.set_atoms({5, 1, 9})
    assert s.order == [1, 5, 9]


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


def test_bonds_between_elements_match_either_way_round(rutile):
    """Stored bonds have an order; a Ti-O bond written O-Ti would be
    missed by a match on one direction, and half the bonds with it."""
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    every = {b.key() for b in graph.bonds}
    assert sel.bonds_between_elements(graph, cell, "Ti", "O") == every
    assert sel.bonds_between_elements(graph, cell, "O", "Ti") == every


def test_bonds_between_elements_leave_out_other_pairs(rutile):
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    assert sel.bonds_between_elements(graph, cell, "O", "O") == set()
    assert sel.bonds_between_elements(graph, cell, "Ti", "Ti") == set()


def test_bonds_to_any_element_are_every_bond_it_makes(rutile):
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    every = {b.key() for b in graph.bonds}
    assert sel.bonds_between_elements(graph, cell, "O") == every
    assert sel.bonds_between_elements(graph, cell, "Ti", None) == every


def test_coordination_selects_only_atoms_with_that_many_neighbours(
        rutile):
    """Rutile's Ti are six-coordinate and its O three: a count that
    let the element or the comparison slip would take the other."""
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    assert sel.by_coordination(graph, cell, "Ti", "=", 6) == {0, 1}
    assert sel.by_coordination(graph, cell, "O", "=", 6) == set()
    assert sel.by_coordination(graph, cell, None, "=", 3) == {2, 3, 4, 5}
    assert sel.by_coordination(graph, cell, None, ">=", 4) == {0, 1}
    assert sel.by_coordination(graph, cell, None, "<=", 6) == set(range(6))


def test_a_label_pattern_selects_every_image_of_matching_sites(rutile):
    """The label is the site's, so a match is the whole orbit -- and
    the case is part of the name."""
    rutile.ensure_labels()
    cell = p1.expand(rutile)
    oxygens = sel.by_element(cell, "O")
    assert sel.by_label(cell, "O1*") == oxygens
    assert sel.by_label(cell, "Ti?") == {0, 1}
    assert sel.by_label(cell, "o1") == set()


def test_a_box_selects_only_atoms_inside_it(rutile):
    """Rutile's cell is two layers along c, at z = 0 and z = 1/2."""
    cell = p1.expand(rutile)
    assert sel.in_box(cell, (0, 0, 0), (1, 1, 0.25)) == {0, 2, 4}
    assert sel.in_box(cell, (0, 0, 0.25), (1, 1, 1)) == {1, 3, 5}
    assert sel.in_box(cell, (0.25, 0.25, 0), (0.75, 0.75, 1)) == \
        {1, 2, 4}


def test_bonds_by_length_select_only_bonds_in_the_range(rutile):
    """Rutile's octahedron is eight bonds of 1.947 A and four of
    1.984 A in the cell; the range is read from where the atoms are
    now, not from when the bonds were perceived."""
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    short = sel.bonds_where(graph, cell, rutile.lattice, longest=1.96)
    long = sel.bonds_where(graph, cell, rutile.lattice, shortest=1.96)
    assert len(short) == 8 and len(long) == 4
    assert short | long == {b.key() for b in graph.bonds}
    assert sel.bonds_where(graph, cell, rutile.lattice, first="O",
                           second="O") == set()
    assert sel.bonds_where(graph, cell, rutile.lattice,
                           kind="explicit") == set()
    assert len(sel.bonds_where(graph, cell, rutile.lattice,
                               order=1.0)) == 12


def test_grow_to_neighbours_only_drops_the_old_selection(rutile):
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    shell = sel.neighbours_only(graph, {0})
    assert 0 not in shell
    assert shell == set(graph.neighbors(0))
    assert all(cell.elements[a] == "O" for a in shell)


def test_bonded_to_takes_every_atom_touching_that_element(rutile):
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    assert sel.bonded_to(graph, cell, "Ti") == {2, 3, 4, 5}
    assert sel.bonded_to(graph, cell, "O") == {0, 1}
    assert sel.bonded_to(graph, cell, "Xe") == set()


def test_a_point_selects_atoms_near_it_across_the_faces(rutile):
    """The corner is every corner: a Ti at the origin is as near the
    point (1, 1, 1) as to (0, 0, 0)."""
    cell = p1.expand(rutile)
    assert sel.near_point(cell, rutile.lattice, (1, 1, 1), 0.5) == {0}
    assert sel.near_point(cell, rutile.lattice, (0.5, 0.5, 0.5),
                          2.1) == sel.within_radius(
        cell, rutile.lattice, {1}, 2.1)


def test_a_region_rule_brings_its_bonds_and_an_atom_rule_does_not(
        rutile):
    graph = bonding.graph(rutile)
    cell = p1.expand(rutile)
    region = sel.pick("radius", cell, graph, rutile.lattice, {0},
                      radius=2.1)
    assert region.bonds == sel.bonds_within(graph, region.atoms)
    assert region.bonds
    named = sel.pick("element", cell, graph, rutile.lattice,
                     symbols=["Ti", "O"])
    assert named.atoms == set(range(6)) and not named.bonds
    bonds = sel.pick("bonds", cell, graph, rutile.lattice, first="Ti")
    assert not bonds.atoms and len(bonds.bonds) == 12


def test_combining_replaces_adds_removes_and_intersects():
    held = Selection()
    held.set_atoms([1, 2, 3])
    held.bonds = {(1, 2, (0, 0, 0)), (3, 4, (0, 0, 0))}
    picked = Selection()
    picked.set_atoms([3, 4])
    assert sel.combine(held, picked, "replace").atoms == {3, 4}
    assert sel.combine(held, picked, "add").order == [1, 2, 3, 4]
    removed = sel.combine(held, picked, "remove")
    assert removed.atoms == {1, 2}
    assert removed.bonds == {(1, 2, (0, 0, 0))}     # 3-4 hung off 3
    common = sel.combine(held, picked, "intersect")
    assert common.atoms == {3} and not common.bonds
    assert held.atoms == {1, 2, 3}                  # untouched


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
