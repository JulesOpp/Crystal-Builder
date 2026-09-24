"""Mapping a stored bond through the group, by tree and in one pass.

``map_explicit_bond`` asks, for every operation, which atom of the
cell sits at each end.  That was a scan of the whole cell per end --
4.7 million distances to map MFU-4l's 19 records through Fm-3m -- and
is now one KD-tree query for all of them.  These tests hold the new
lookup to the old answer: the same atom, the lowest-numbered one when
two are within reach, and the same minimum-image length.
"""

import numpy as np
import pytest

from xtal.core import bonding, neighbors, p1, symmetry
from xtal.io import FORMATS


def scanned(cell, frac, lattice, tol=1e-3):
    """The lookup as it was: every atom of the cell, first one wins."""
    d = cell.frac - frac
    d -= np.round(d)
    hit = np.flatnonzero(np.linalg.norm(d @ lattice.matrix, axis=1) < tol)
    return int(hit[0]) if len(hit) else -1


@pytest.fixture
def mfu4l():
    return FORMATS.read("resources/samples/MFU4l.cif")


@pytest.mark.parametrize("name", ["rutile", "quartz", "halite", "mfu4l"])
def test_every_atom_is_found_where_the_scan_found_it(name, request):
    """Each atom's own position, nudged by less than the tolerance and
    folded across the cell faces, finds the atom the scan found.  A
    miss drops every bond of that orbit from the picture."""
    structure = request.getfixturevalue(name)
    cell = p1.expand(structure)
    rng = np.random.default_rng(0)
    nudge = rng.normal(size=cell.frac.shape)
    nudge *= 4e-4 / np.linalg.norm(nudge @ structure.lattice.matrix,
                                   axis=1)[:, None]
    points = p1._wrap(cell.frac + nudge)
    found = bonding._find_atoms(cell, points, structure.lattice)
    expected = [scanned(cell, q, structure.lattice) for q in points]
    assert found.tolist() == expected
    assert (found >= 0).all()


def test_a_point_nowhere_near_an_atom_is_found_nowhere(halite):
    cell = p1.expand(halite)
    found = bonding._find_atoms(cell, [[0.25, 0.25, 0.25]],
                                halite.lattice)
    assert found.tolist() == [-1]


def test_a_point_just_below_a_cell_face_finds_the_atom_on_it(halite):
    """Na sits at the origin; the point 1e-4 A below it folds to 0.9999
    on every axis.  They are the same point, and the periodic tree must
    say so exactly as the minimum-image scan did."""
    cell = p1.expand(halite)
    origin = int(np.flatnonzero(np.all(cell.frac == 0, axis=1))[0])
    step = 1e-4 / halite.lattice.lengths[0]
    probe = p1._wrap(np.array([-step, -step, -step]))
    assert probe.min() > 0.99
    found = bonding._find_atoms(cell, [probe], halite.lattice)
    assert found.tolist() == [origin]


def test_bond_lengths_in_one_pass_match_the_minimum_image_one_at_a_time(
        quartz):
    """The lengths carried on mapped bonds, in a non-orthogonal cell
    where the rounded fractional difference is not always the shortest
    image."""
    rng = np.random.default_rng(1)
    a, b = rng.random((50, 3)), rng.random((50, 3)) * 3 - 1
    batched = bonding._min_image_distances(a, b, quartz.lattice)
    single = [neighbors.min_image_distance(x, y, quartz.lattice)
              for x, y in zip(a, b, strict=True)]
    assert np.allclose(batched, single, rtol=0, atol=1e-12)


def test_every_stored_bond_of_mfu4l_draws_what_it_drew_before(mfu4l):
    """Every perceived bond stored as a record, then drawn again: the
    graph the records draw is the perceived one, bond for bond, with
    the stated order on each."""
    from xtal.commands import bonds as bond_commands
    perceived = bonding.graph(mfu4l)
    cell = p1.expand(mfu4l)
    records = [bonding.bond_between(mfu4l, cell, int(i), int(j),
                                    (0, 0, 0), tuple(int(v) for v in im))
               for i, j, im in sorted({b.key() for b in perceived.bonds})]

    class Host:
        structure = mfu4l
    bond_commands.SetBondTypes(records, 1.0).do(Host)
    drawn = bonding.graph(mfu4l)
    assert ({b.key() for b in drawn.bonds}
            == {b.key() for b in perceived.bonds})
    assert all(b.order == 1.0 for b in drawn.bonds)


# --------------------------------------------- nearest, not first

def test_the_nearest_atom_by_tree_is_the_nearest_by_scan(quartz):
    """``p1.nearest_atoms`` is what the subgroup descent matches a
    mapped orbit with: the closest atom within reach, not merely the
    first.  Held against a scan over the whole cell."""
    cell = p1.expand(quartz)
    rng = np.random.default_rng(2)
    points = p1._wrap(cell.frac[rng.integers(len(cell.frac), size=40)]
                      + rng.normal(scale=0.02, size=(40, 3)))
    found = p1.nearest_atoms(cell, points, quartz.lattice, 0.5)
    for point, atom in zip(points, found, strict=True):
        d = cell.frac - point
        d -= np.round(d)
        dist = np.linalg.norm(d @ quartz.lattice.matrix, axis=1)
        best = int(np.argmin(dist))
        assert atom == (best if dist[best] < 0.5 else -1)


def test_two_atoms_equally_near_give_the_lower_index(halite):
    """The scan's argmin took the first of two equal distances; the
    tree must as well, or a descent would name a different site."""
    cell = p1.expand(halite)
    a, b = 0, int(np.flatnonzero(np.all(cell.frac == [0.5, 0.5, 0], 1))[0])
    middle = (cell.frac[a] + cell.frac[b]) / 2
    found = p1.nearest_atoms(cell, [middle], halite.lattice, 3.0)
    assert found.tolist() == [min(a, b)]


def test_every_edge_of_a_chain_net_runs_along_the_chain():
    """Ni2Cl2BTDD's Ni1 images land a rounding error below a cell face
    -- 0.99999 on *c* -- where the atom found for them is stored at 0.
    The image was taken from the wrapped point rather than that atom,
    so six of the eighteen edges drawn from one Ni-Ni pair on a chain
    ran 5.9 to 39 A across the cell instead of 3.44 A along it."""
    structure, _ = symmetry.merge_duplicates(
        FORMATS.read("resources/samples/Ni2Cl2BTDD.cif"))
    cell = p1.expand(structure)
    lattice = structure.lattice.matrix
    nickel = [k for k, e in enumerate(cell.elements) if str(e) == "Ni"]
    a = nickel[0]
    offsets = [cell.frac[b] - cell.frac[a] for b in nickel[1:]]
    images = [-np.round(d) for d in offsets]
    lengths = [np.linalg.norm((d + t) @ lattice)
               for d, t in zip(offsets, images, strict=True)]
    k = int(np.argmin(lengths))
    bond = bonding.bond_between(
        structure, cell, a, nickel[1:][k], (0, 0, 0),
        tuple(int(v) for v in images[k]))
    edges = bonding.map_explicit_bond(structure, cell, bond)
    drawn = [np.linalg.norm((cell.frac[e.j] + e.image - cell.frac[e.i])
                            @ lattice) for e in edges]
    assert len(edges) == 18
    assert np.allclose(drawn, lengths[k], atol=1e-3)
