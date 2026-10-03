"""A number per bond or per atom, for colouring by: xtal.core.scalars."""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, p1, scalars
from xtal.core.site import Site
from xtal.core.structure import Bond


def _graphene(n=3):
    lattice = Lattice.from_parameters(2.46 * n, 2.46 * n, 10.0,
                                      90, 90, 120)
    sites = [Site("C", np.array([(i + x) / n, (j + y) / n, 0.5]))
             for i in range(n) for j in range(n)
             for x, y in ((1 / 3, 2 / 3), (2 / 3, 1 / 3))]
    return Structure(lattice=lattice, sites=sites)


def _by_element(structure, name):
    found = scalars.values(structure, name)
    elements = np.array(p1.expand(structure).elements)
    return {e: found[elements == e] for e in set(elements)}


def test_bond_lengths_are_one_per_bond_of_the_graph_in_its_order(
        rutile):
    """Rutile's two Ti-O lengths, 1.95 and 1.98 A, in the order the
    graph lists its bonds -- the viewport colours bond k by entry k,
    and one out of step colours the wrong bond."""
    graph = bonding.graph(rutile)
    lengths = scalars.values(rutile, "bond_length", graph=graph)
    assert len(lengths) == len(graph.bonds)
    cell = p1.expand(rutile)
    for bond, length in zip(graph.bonds, lengths, strict=True):
        d = cell.lattice.to_cart(cell.frac[bond.j] + bond.image
                                 - cell.frac[bond.i])
        assert length == pytest.approx(np.linalg.norm(d))
    assert sorted(set(np.round(lengths, 2))) == [1.95, 1.98]


def test_a_bond_against_its_ideal_is_the_sum_of_covalent_radii(quartz):
    """Si-O is 1.61 A in quartz against 1.77 A of covalent radii."""
    strain = scalars.values(quartz, "bond_strain")
    assert np.all(np.abs(strain + 0.16) < 0.03)


def test_coordination_counts_the_stored_graph(rutile):
    """Octahedral titanium, trigonal oxygen."""
    counts = _by_element(rutile, "coordination")
    assert set(counts["Ti"]) == {6.0} and set(counts["O"]) == {3.0}


def test_an_angle_is_measured_against_the_ideal_for_its_coordination(
        quartz):
    """Quartz's silicon is all but a perfect tetrahedron.  Its oxygen
    is bent at 144 degrees, and with two neighbours has no ideal --
    180 is an sp carbon's, not an oxygen's.  Fails if the ideal is not
    taken from the neighbour count."""
    mean = _by_element(quartz, "mean_angle")
    off = _by_element(quartz, "angle_deviation")
    assert np.all(np.abs(mean["Si"] - 109.47) < 0.5)
    assert np.all(off["Si"] < 1.5)
    assert np.all(np.abs(mean["O"] - 143.7) < 1.0)
    assert np.all(np.isnan(off["O"]))


def test_an_angle_with_no_one_ideal_is_undefined_not_zero(rutile):
    """Six neighbours have no single ideal angle; a zero would colour
    rutile's titanium as the most regular atom in the picture."""
    off = _by_element(rutile, "angle_deviation")
    assert np.all(np.isnan(off["Ti"]))
    assert np.all(np.isfinite(off["O"]))


def test_an_atom_with_fewer_than_two_neighbours_has_no_angle():
    """A hydrogen on one bond has no angle at it, so its mean angle is
    NaN and not 0 degrees."""
    s = Structure(lattice=Lattice.cubic(10.0), sites=[
        Site("O", np.array([0.5, 0.5, 0.5])),
        Site("H", np.array([0.5 + 0.096, 0.5, 0.5])),
        Site("H", np.array([0.5 - 0.024, 0.5 + 0.093, 0.5]))])
    mean = scalars.values(s, "mean_angle")
    assert np.isfinite(mean[0])
    assert np.isnan(mean[1]) and np.isnan(mean[2])


def test_the_smallest_ring_is_read_off_the_primitive_rings():
    """Every carbon of graphene is in a hexagon, and nothing else
    would be: no composite ring is primitive."""
    assert set(scalars.values(_graphene(), "smallest_ring")) == {6.0}


def test_an_atom_in_no_ring_has_no_ring_size(rutile):
    """Rutile's smallest cycles are four-membered Ti2O2 rhombs; asked
    only up to three, nothing is in a ring and every value is NaN."""
    found = scalars.values(rutile, "smallest_ring", max_ring=3)
    assert np.all(np.isnan(found))
    assert set(scalars.values(rutile, "smallest_ring")) == {4.0}


def test_a_charge_nobody_set_is_undefined(rutile):
    """No charge is not a charge of zero, which is neutral and a
    claim."""
    assert np.all(np.isnan(scalars.values(rutile, "charge")))
    rutile.sites[0].charge = 1.5
    rutile.sites[1].charge = -0.75
    charges = _by_element(rutile, "charge")
    assert set(charges["Ti"]) == {1.5} and set(charges["O"]) == {-0.75}


def test_a_marker_has_no_value_and_counts_for_nothing_it_touches():
    """An X bonded to graphene is not a neighbour of the carbon it
    sits on: the carbon is still three-coordinate, and the X has no
    coordination, angle or ring of its own."""
    s = _graphene()
    s.sites.append(Site("X", s.sites[0].frac + [0.0, 0.0, 0.14]))
    s.add_bond(Bond(0, len(s.sites) - 1))
    coordination = scalars.values(s, "coordination")
    elements = np.array(p1.expand(s).elements)
    graph = bonding.graph(s)
    assert any(elements[b.i] == "X" or elements[b.j] == "X"
               for b in graph.bonds)
    assert set(coordination[elements == "C"]) == {3.0}
    for name in ("coordination", "mean_angle", "smallest_ring"):
        assert np.all(np.isnan(scalars.values(s, name)[elements == "X"]))


def test_the_automatic_range_ignores_what_is_undefined():
    assert scalars.auto_range(np.array([np.nan, 2.0, 5.0])) == (2.0, 5.0)
    assert scalars.auto_range(np.array([np.nan])) is None
