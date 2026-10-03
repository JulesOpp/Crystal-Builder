"""Remeshing a periodic sheet and giving it defects: xtal.carbon.mesh."""

import numpy as np
import pytest

from xtal.carbon import mesh as ms
from xtal.carbon import surface as sf


@pytest.fixture(scope="module")
def sheet():
    """dia's conventional cell at a 10.3 A edge, remeshed: the field,
    its level, and a closed mesh of about 800 triangles."""
    lattice, vertices, edges = sf.net_of("dia")
    frame = sf.skeleton(lattice, vertices, edges, 10.3)
    radius = 0.3 * frame.edge_length
    width = sf.WIDTH_FRACTION * radius
    field = sf.Field(frame, width)
    level = sf.level_for(radius, width)
    mesh = ms.remesh(sf.march(field, level, 1.8), field, level)
    return field, level, mesh


def _edge_lengths(mesh):
    keys, _inverse, _counts = mesh.edges()
    return np.linalg.norm((mesh.frac[keys[:, 1]] + keys[:, 2:]
                           - mesh.frac[keys[:, 0]]) @ mesh.matrix, axis=1)


def test_a_remeshed_sheet_is_closed_with_edges_near_the_target(sheet):
    """The remesh keeps the sheet's topology and makes every triangle
    about the size graphene's dual asks for: edges 2.46 A on average,
    so the hexagons come out with 1.42 A sides."""
    _field, _level, mesh = sheet
    assert mesh.is_closed()
    assert mesh.euler() == -16
    lengths = _edge_lengths(mesh)
    assert lengths.mean() == pytest.approx(ms.TARGET_EDGE, rel=0.06)
    assert lengths.std() < 0.15 * ms.TARGET_EDGE
    # About half hexagons, as the example ZTC is (381 of some 700
    # rings): a sheet round dia is curved negatively nearly everywhere.
    assert np.mean(mesh.valence() == 6) > 0.45


def test_a_flip_changes_four_valences_by_one(sheet):
    """The two ends of the edge lose a neighbour and the two far
    corners gain one: a Stone-Wales rotation in the dual turns four
    hexagons into a 5-7-7-5."""
    _field, _level, mesh = sheet
    editor = ms.Editor(mesh)
    for t in sorted(editor.tris):
        quad = editor._quad(t, 0)
        _t, _k, u, _m, c, d, _frame = quad
        ends = (editor.tris[t][0], editor.tris[t][1],
                editor.tris[t][c], editor.tris[u][d])
        if len(set(ends)) < 4:
            continue
        before = [editor.valence(v) for v in ends]
        if editor.flip(t, 0):
            break
    after = [editor.valence(v) for v in ends]
    assert np.subtract(after, before).tolist() == [-1, -1, 1, 1]
    assert editor.mesh().is_closed()


def test_gauss_bonnet_holds_after_any_sequence_of_moves(sheet):
    """Splits, collapses and flips at random, two hundred of them: the
    sheet stays closed, its chi stays the net's, and the sum of six
    minus each valence stays six chi -- the ring count no edit of the
    mesh can change."""
    _field, _level, mesh = sheet
    rng = np.random.default_rng(7)
    editor = ms.Editor(mesh)
    for _ in range(200):
        ids = sorted(editor.tris)
        t = ids[int(rng.integers(len(ids)))]
        k = int(rng.integers(3))
        move = rng.integers(3)
        if move == 0:
            editor.flip(t, k)
        elif move == 1:
            editor.split(t, k)
        else:
            editor.collapse(t, k, longest=10.0)
    after = editor.mesh()
    assert after.is_closed()
    assert after.euler() == mesh.euler()
    found, expected = ms.gauss_bonnet(after)
    assert found == expected == 6 * mesh.euler()


def test_stone_wales_turns_hexagons_into_pairs_of_fives_and_sevens(
        sheet):
    """Each defect is two fives and two sevens where there were four
    sixes, so the count of sixes falls by four a defect."""
    field, level, mesh = sheet
    sixes = int(np.sum(mesh.valence() == 6))
    after, made = ms.stone_wales(mesh, 3, np.random.default_rng(0))
    assert made == 3
    assert int(np.sum(after.valence() == 6)) == sixes - 4 * made
    assert ms.gauss_bonnet(after)[0] == ms.gauss_bonnet(mesh)[0]


def test_the_same_seed_gives_the_same_mesh(sheet):
    """A build is reproducible: the defects land in the same places
    for the same seed, and somewhere else for another."""
    field, level, mesh = sheet
    first, _ = ms.stone_wales(mesh, 6, np.random.default_rng(3),
                              field, level)
    again, _ = ms.stone_wales(mesh, 6, np.random.default_rng(3),
                              field, level)
    other, _ = ms.stone_wales(mesh, 6, np.random.default_rng(4),
                              field, level)
    assert np.array_equal(first.tri, again.tri)
    assert np.allclose(first.frac, again.frac)
    assert not np.array_equal(first.tri, other.tri)


def test_a_projected_point_is_on_the_sheet(sheet):
    """Newton along the gradient puts a point at the level, and a
    point in the middle of a pore, where the field is flat, moves no
    further than the cap a step allows rather than off to infinity."""
    field, level, mesh = sheet
    start = mesh.frac[:20] @ mesh.matrix + 0.3
    on = ms.project(start, field, level, steps=8)
    assert np.allclose(field(on), level, rtol=1e-3)
    far = np.array([[0.5, 0.5, 0.5]]) @ mesh.matrix + 50.0
    moved = ms.project(far, field, level, steps=2)
    assert np.linalg.norm(moved - far) <= 2 * ms.MAX_PROJECTION_STEP + 1e-9
