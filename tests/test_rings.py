"""Primitive rings: the faces a sheet is made of, and nothing more."""

import numpy as np

from xtal import Lattice, Structure
from xtal.core import p1, rings
from xtal.core.site import Site
from xtal.core.structure import Change


def _graphene(n=1):
    """An n x n supercell of graphene, flat in a cell 10 A deep."""
    lattice = Lattice.from_parameters(2.46 * n, 2.46 * n, 10.0,
                                      90, 90, 120)
    sites = []
    for i in range(n):
        for j in range(n):
            for x, y in ((1 / 3, 2 / 3), (2 / 3, 1 / 3)):
                sites.append(Site("C", np.array(
                    [(i + x) / n, (j + y) / n, 0.5])))
    return Structure(lattice=lattice, sites=sites)


def test_two_fused_hexagons_are_two_rings_not_three():
    """Fails if the shortest-path filter goes: the ten-cycle round
    two hexagons sharing an edge would be drawn over both of them,
    1728 of them on a 24 x 24 sheet."""
    assert rings.census(_graphene(3), max_size=10) == {6: 9}


def test_a_ring_closing_through_a_cell_face_is_found_once():
    """Graphene's two-atom cell holds one hexagon, and every one of
    its bonds crosses a cell face.  Fails if the walks reaching it
    from each copy of its lowest atom count as three rings."""
    assert rings.census(_graphene(1)) == {6: 1}
    assert rings.census(_graphene(2)) == {6: 4}


def test_a_lattice_translation_is_not_a_ring():
    """A chain that returns to its own atom one cell along is the
    lattice repeating.  Fails if a closing translation is accepted,
    which would call every framework a ring."""
    chain = Structure(lattice=Lattice.cubic(2.8), sites=[
        Site("C", np.array([0.0, 0.5, 0.5])),
        Site("C", np.array([0.5, 0.5, 0.5]))])
    assert rings.census(chain) == {}


def test_a_dummy_atom_is_never_in_a_ring():
    """A centroid marker bonded into a ring would make a ring of a
    note the user made."""
    sheet = _graphene(2)
    sheet.sites[0].element = "X"
    assert rings.census(sheet) == {6: 1}


def test_rings_are_kept_through_a_drag_and_found_again_after_an_edit():
    """Memoised on the chemistry, so redrawing a large framework
    while an atom is dragged does not search it again on every
    frame -- and a deleted atom does not leave its rings behind."""
    sheet = _graphene(2)
    first = rings.rings_of(sheet)
    sheet.touch(Change.POSITIONS)
    assert rings.rings_of(sheet) is first
    del sheet.sites[0]
    sheet.touch(Change.TOPOLOGY)
    assert rings.census(sheet) == {6: 1}


def test_a_ring_stays_whole_when_an_atom_crosses_a_cell_face():
    """An optimiser step that takes an atom across a face redraws it
    on the far side, and the shifts the memoised rings hold count
    translations between *wrapped* positions.  Fails if they are not
    read against the new wrap: the face is drawn to the atom's copy
    across the cell and spans the whole of it."""
    sheet = _graphene(3)
    rings.rings_of(sheet)
    for site in sheet.sites:
        site.frac = site.frac - np.array([0.12, 0.0, 0.0])
    sheet.touch(Change.POSITIONS)
    cell = p1.expand(sheet)
    found = rings.rings_of(sheet)
    assert len(found) == 9
    for ring in found:
        corners = sheet.lattice.to_cart(np.array(
            [cell.frac[atom] + shift for atom, shift in ring]))
        steps = np.linalg.norm(
            corners - np.roll(corners, 1, axis=0), axis=1)
        assert steps.max() < 1.5
        assert ring[0][1] == (0, 0, 0)
