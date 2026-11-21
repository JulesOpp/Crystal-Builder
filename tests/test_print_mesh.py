"""A cut cell as two printable bodies, one per colour, that meet
without overlapping and without a gap."""

import re
from pathlib import Path

import numpy as np
import pytest

from xtal.core import cellcut
from xtal.core.cellcut import CellCut
from xtal.printing import check, field, mesh, primitives, radii

ATOMIC_BLENDER = Path("/Applications/Blender.app/Contents/Resources")


def _pair(colours=(1, 2), bonds="half", voxel=0.05):
    cut = CellCut(elements=("C", "O"),
                  cart=np.array([[0.0, 0.0, 0.0], [1.4, 0.1, 0.05]]),
                  bonds=((0, 1, 1.0),))
    prims = primitives.build(cut, list(colours), bonds)
    return prims, mesh.two_bodies(prims, voxel)


def _directed(triangles):
    return {tuple(e) for t in triangles
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))}


def _inside(vertices, triangles, points):
    """Whether each point is inside the closed mesh, by the winding
    number: the solid angle the mesh subtends, over 4 pi."""
    v = vertices[triangles][None, :, :, :] - points[:, None, None, :]
    a, b, c = v[:, :, 0], v[:, :, 1], v[:, :, 2]
    la, lb, lc = (np.linalg.norm(x, axis=-1) for x in (a, b, c))
    det = np.einsum("pti,pti->pt", a, np.cross(b, c))
    div = (la * lb * lc + np.einsum("pti,pti->pt", a, b) * lc
           + np.einsum("pti,pti->pt", a, c) * lb
           + np.einsum("pti,pti->pt", b, c) * la)
    winding = 2 * np.arctan2(det, div).sum(axis=1) / (4 * np.pi)
    return winding > 0.5


def test_a_single_ball_is_a_closed_manifold_of_the_right_volume():
    """The marching itself: a hole here is a hole in every print."""
    cut = CellCut(elements=("C",), cart=np.array([[0.01, 0.02, 0.03]]))
    prims = primitives.build(cut, [1])
    vertices, triangles = mesh.two_bodies(prims, 0.05).body(1)
    report = check.report(vertices, triangles)
    assert report.ok, report.says()
    r = prims.radius[0]
    assert report.volume == pytest.approx(4 / 3 * np.pi * r ** 3,
                                          rel=0.02)


@pytest.mark.parametrize("bonds", primitives.BONDS)
def test_each_colour_body_is_closed_and_consistently_wound(bonds):
    """What a slicer counts as non-manifold: an edge used once, used
    by three triangles, or twice the same way round."""
    _prims, bodies = _pair(bonds=bonds)
    for colour in (1, 2):
        report = check.report(*bodies.body(colour))
        assert report.ok, (colour, report.says())


def test_two_touching_balls_of_two_colours_share_every_interface_vertex():
    """The interface is one surface with two names: every triangle of
    it is in both bodies, wound oppositely, on the very same vertices
    -- not two surfaces a rounding error apart."""
    _prims, bodies = _pair()
    one, two = bodies.bodies
    shared_one = {frozenset(t) for t in one} & {frozenset(t) for t in two}
    assert len(shared_one) > 50
    edges_two = _directed(two)
    for t in one:
        if frozenset(t) in shared_one:
            assert (t[1], t[0]) in edges_two


def test_the_two_bodies_add_up_to_the_one_colour_solid():
    """Splitting by colour moves no plastic: the two volumes sum to
    the volume of the same model in one colour."""
    _prims, split = _pair(colours=(1, 2))
    _prims, whole = _pair(colours=(1, 1))
    total = sum(check.volume(*split.body(c)) for c in (1, 2))
    assert total == pytest.approx(check.volume(*whole.body(1)), rel=1e-3)


def test_the_bodies_do_not_overlap():
    """No point of space is in both parts: the slicer would have to
    decide which filament prints it."""
    prims, bodies = _pair()
    rng = np.random.default_rng(3)
    lo, hi = prims.bounds()
    points = rng.uniform(lo.min(axis=0), hi.max(axis=0), size=(150, 3))
    one = _inside(*bodies.body(1), points)
    two = _inside(*bodies.body(2), points)
    assert one.any() and two.any()
    assert not np.any(one & two)


def test_a_half_bond_changes_colour_at_the_middle_of_the_visible_stick():
    """Halfway between the two ball surfaces: zinc's ball is larger
    than oxygen's, so the change is past the midpoint of the nuclei."""
    cut = CellCut(elements=("Zn", "O"),
                  cart=np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]]),
                  bonds=((0, 1, 1.0),))
    prims = primitives.build(cut, [2, 1], "half")
    zn = primitives.ball_radius("Zn", 0.8, 2.0)
    o = primitives.ball_radius("O", 0.8, 2.0)
    middle = zn + (3.0 - zn - o) / 2
    sticks = prims.kind == primitives.STICK
    assert sorted(prims.b[sticks][:, 0])[0] == pytest.approx(middle)
    bodies = mesh.two_bodies(prims, 0.05)
    points = np.array([[middle - 0.1, 0, 0], [middle + 0.1, 0, 0]])
    assert _inside(*bodies.body(2), points).tolist() == [True, False]
    assert _inside(*bodies.body(1), points).tolist() == [False, True]


@pytest.mark.parametrize("colour", [1, 2])
def test_a_whole_bond_takes_the_chosen_colour_whatever_its_atoms_are(
        colour):
    prims, bodies = _pair(colours=(1, 2), bonds=str(colour))
    sticks = prims.kind == primitives.STICK
    assert prims.colour[sticks].tolist() == [colour]
    middle = ((prims.a[sticks] + prims.b[sticks]) / 2).reshape(1, 3)
    assert _inside(*bodies.body(colour), middle).all()
    assert not _inside(*bodies.body(3 - colour), middle).any()


def test_a_one_colour_choice_makes_one_body_and_an_empty_other():
    _prims, bodies = _pair(colours=(1, 1), bonds="1")
    assert check.report(*bodies.body(1)).ok
    vertices, triangles = bodies.body(2)
    assert len(triangles) == 0


def test_no_vertex_sits_on_a_grid_point():
    """A vertex on a grid point is where zero-area triangles come
    from; the clamp keeps every vertex off them."""
    prims, bodies = _pair()
    grid = field.Grid.around(prims, 0.05)
    steps = (bodies.vertices - grid.origin) / grid.voxel
    off = np.abs(steps - np.round(steps))
    assert np.all(off.max(axis=1) > 0.5 * mesh.CLAMP)
    for colour in (1, 2):
        assert check.report(*bodies.body(colour)).degenerate == 0


@pytest.mark.parametrize("bonds", ["half", "1"])
def test_halite_cut_meshes_clean_in_both_bond_modes(halite, bonds):
    cut = cellcut.cut_cell(halite)
    colours = [2 if e == "Na" else 1 for e in cut.elements]
    prims = primitives.build(cut, colours, bonds)
    bodies = mesh.two_bodies(prims, 0.2)
    for colour in (1, 2):
        report = check.report(*bodies.body(colour))
        assert report.ok, (colour, report.says())


def test_a_body_that_is_not_closed_is_named_as_such():
    """The check the run trusts before writing a file has to see a
    hole, not only a clean mesh."""
    _prims, bodies = _pair()
    vertices, triangles = bodies.body(1)
    report = check.report(vertices, triangles[1:])
    assert not report.ok
    assert "open edges" in report.says()


@pytest.mark.slow
def test_mof5_meshes_clean_with_a_body_per_colour():
    from xtal.io.cif_reader import read_cif
    root = Path(__file__).resolve().parents[1]
    structure = read_cif(root / "resources" / "samples" / "MOF-5.cif")
    cut = cellcut.cut_cell(structure)
    colours = [2 if e == "Zn" else 1 for e in cut.elements]
    prims = primitives.build(cut, colours, "half")
    bodies = mesh.two_bodies(prims, 0.2)
    for colour in (1, 2):
        report = check.report(*bodies.body(colour))
        assert report.ok, (colour, report.says())


@pytest.mark.skipif(not ATOMIC_BLENDER.is_dir(),
                    reason="Blender is not installed")
def test_the_radii_are_the_ones_atomic_blender_reads():
    """The two exports should print the same balls; if Atomic Blender's
    table changes, this one has to follow."""
    sources = sorted(ATOMIC_BLENDER.glob(
        "*/scripts/addons/io_mesh_atomic/pdb_import.py"))
    if not sources:
        pytest.skip("Atomic Blender is not bundled with this Blender")
    text = sources[-1].read_text()
    row = re.compile(r'\(\s*\d+,\s*"[^"]+",\s*"(\w+)",\s*\([^)]*\),'
                     r'\s*([\d.]+),\s*([\d.]+),')
    found = {m.group(1): float(m.group(3)) for m in row.finditer(text)}
    assert found
    for symbol, value in radii.RADII.items():
        assert found[symbol] == pytest.approx(value), symbol
