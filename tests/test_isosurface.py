"""The distance grid and the surface marched over it.

Both are arithmetic with an exact answer, which is the only reason
this is testable at all: a pore surface has no reference to compare
against, but a *sphere* does -- 4 pi r^2 and 4/3 pi r^3 -- and a
surface that reproduces both to a fraction of a percent is not
accidentally right.

Nothing here needs Zeo++, and nothing here imports Qt.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.analysis.grid import distance_grid, shape_for
from xtal.analysis.isosurface import isosurface

SIDE = 10.0
RADIUS = 3.0


def sphere_grid(centre=(5.0, 5.0, 5.0), n=50, radius=RADIUS):
    """``radius - |r - centre|`` on a periodic grid: the zero set is a
    sphere of that radius, wrapped."""
    axis = np.arange(n) / n * SIDE
    coords = np.meshgrid(axis, axis, axis, indexing="ij")
    squared = np.zeros_like(coords[0])
    for values, middle in zip(coords, centre, strict=True):
        offset = values - middle
        offset -= SIDE * np.round(offset / SIDE)
        squared += offset ** 2
    return radius - np.sqrt(squared)


def mesh_area(points, faces, lattice) -> float:
    cart = lattice.to_cart(points)
    a, b, c = cart[faces[:, 0]], cart[faces[:, 1]], cart[faces[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum()


def enclosed_volume(points, faces, lattice, about) -> float:
    """The divergence theorem, which only gives the right answer if
    every triangle faces the same way."""
    cart = lattice.to_cart(points) - np.asarray(about, float)
    a, b, c = cart[faces[:, 0]], cart[faces[:, 1]], cart[faces[:, 2]]
    return abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


# ------------------------------------------------------------- the grid

def test_the_grid_measures_to_the_atom_surface_not_its_centre():
    """One atom of radius 1 at the middle of a 10 A cube: the middle
    is 1 A *inside* it."""
    lattice = Lattice.cubic(SIDE)
    one = Structure.from_arrays(lattice, ["C"], [[0.5, 0.5, 0.5]],
                                space_group="P1")
    grid = distance_grid(one, lambda _e: 1.0, spacing=0.5)
    middle = grid.shape[0] // 2
    assert grid[middle, middle, middle] == pytest.approx(-1.0)


def test_the_grid_wraps():
    """The corner of the cell is as far from that atom as the body
    diagonal allows, and not further -- an atom in the next cell over
    is the nearest one to a point near a face, and a tree has no idea
    the box repeats."""
    lattice = Lattice.cubic(SIDE)
    one = Structure.from_arrays(lattice, ["C"], [[0.5, 0.5, 0.5]],
                                space_group="P1")
    grid = distance_grid(one, lambda _e: 1.0, spacing=0.5)
    assert grid[0, 0, 0] == pytest.approx(np.sqrt(3) * 5 - 1)


def test_a_bigger_atom_wins_even_from_further_away():
    """The nearest atom *surface* is not the nearest atom centre, so
    asking the tree for one neighbour would be wrong."""
    lattice = Lattice.cubic(SIDE)
    pair = Structure.from_arrays(
        lattice, ["C", "Xe"], [[0.3, 0.5, 0.5], [0.7, 0.5, 0.5]],
        space_group="P1")
    radii = {"C": 0.5, "Xe": 3.0}
    grid = distance_grid(pair, radii.get, spacing=0.25, shape=(40, 40, 40))
    # A point 1 A from the small atom and 3 A from the big one: the
    # big one's skin is at 0.0 and the small one's at 0.5.
    value = grid[16, 20, 20]
    assert value == pytest.approx(0.0, abs=0.3)


def test_the_shape_follows_the_cell_lengths():
    """A layered cell wants more planes than rows, or the surface is
    finer in one direction than the other."""
    shape = shape_for(Lattice.orthorhombic(5.0, 5.0, 30.0),
                      spacing=0.5)
    assert shape == (10, 10, 60)


def test_an_empty_structure_has_no_nearest_atom():
    grid = distance_grid(Structure.empty(Lattice.cubic(SIDE)),
                         lambda _e: 1.0, spacing=2.0)
    assert np.isinf(grid).all()


# ------------------------------------------------------- the surface

def test_a_sphere_comes_back_with_the_area_a_sphere_has():
    lattice = Lattice.cubic(SIDE)
    points, faces = isosurface(sphere_grid(), lattice, 0.0)
    assert len(faces) > 1000
    assert mesh_area(points, faces, lattice) == pytest.approx(
        4 * np.pi * RADIUS ** 2, rel=0.01)


def test_the_triangles_all_face_the_same_way():
    """A surface wound half one way and half the other lights as a
    patchwork of bright and black facets -- and gives a nonsense
    volume, which is how this test sees it."""
    lattice = Lattice.cubic(SIDE)
    centre = (5.13, 4.77, 5.31)
    points, faces = isosurface(sphere_grid(centre), lattice, 0.0)
    assert enclosed_volume(points, faces, lattice,
                           centre) == pytest.approx(
        4 / 3 * np.pi * RADIUS ** 3, rel=0.02)


def test_the_mesh_is_watertight():
    """Every edge in exactly two triangles.  A marching-cubes table
    with an ambiguous case wrong fails this and nothing else."""
    from collections import Counter

    lattice = Lattice.cubic(SIDE)
    points, faces = isosurface(sphere_grid((5.13, 4.77, 5.31)),
                               lattice, 0.0)
    rounded = [tuple(np.round(p, 5)) for p in points]
    edges: Counter = Counter()
    for triangle in faces:
        for u, v in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((rounded[triangle[u]],
                                rounded[triangle[v]])))] += 1
    assert all(count % 2 == 0 for count in edges.values())


def test_a_surface_across_a_cell_face_is_whole():
    """The grid wraps, so a cavity at the corner is one cavity in
    eight pieces and not eight eighths of nothing.  Its area is a
    sphere's however it is cut."""
    lattice = Lattice.cubic(SIDE)
    points, faces = isosurface(sphere_grid((0.13, 0.07, 9.81)),
                               lattice, 0.0)
    assert mesh_area(points, faces, lattice) == pytest.approx(
        4 * np.pi * RADIUS ** 2, rel=0.01)


def test_a_level_nothing_reaches_draws_nothing():
    """A probe too big for any pore in a dense solid is a real answer
    and it is "nothing to draw", not an error."""
    lattice = Lattice.cubic(SIDE)
    points, faces = isosurface(sphere_grid(), lattice, 99.0)
    assert len(points) == 0 and len(faces) == 0


def test_a_finer_grid_converges_rather_than_wandering():
    lattice = Lattice.cubic(SIDE)
    exact = 4 * np.pi * RADIUS ** 2
    coarse = mesh_area(*isosurface(sphere_grid(n=24), lattice, 0.0),
                       lattice)
    fine = mesh_area(*isosurface(sphere_grid(n=64), lattice, 0.0),
                     lattice)
    assert abs(fine - exact) < abs(coarse - exact)


# ------------------------------------------ the two together, for real

def test_the_accessible_fraction_agrees_with_what_zeo_measures():
    """The end-to-end check, and the only one that can catch a wrong
    radii table: Zeo++ samples MFU-4l's accessible volume at a 1.86 A
    probe by Monte Carlo and reports 46.2% of the cell.  The grid says
    the same to within its own spacing.
    """
    from pathlib import Path

    from xtal.analysis import porosity
    from xtal.io import FORMATS

    path = Path(__file__).resolve().parent.parent.joinpath(
        "resources", "samples", "MFU4l.cif")
    if not path.is_file():                          # pragma: no cover
        pytest.skip("the sample structures are not in this checkout")
    structure = FORMATS.read(path)
    grid = distance_grid(structure, porosity.zeo_radius, spacing=0.5)
    assert (grid >= 1.86).mean() == pytest.approx(0.4616, abs=0.03)


# ------------------------------------------------- memory, not answers

def triangle_set(points, faces) -> set:
    """The mesh as a set of triangles, each an unordered set of
    corners -- the same surface whatever order it was emitted in."""
    return {frozenset(map(tuple, points[t].tolist())) for t in faces}


def test_the_slab_march_gives_the_triangles_of_one_pass(monkeypatch):
    """Cells are marched a slab at a time so that MFU-4l's pore
    surface peaks at a quarter of the memory.  A slab of one plane is
    the hardest cut: every triangle must still come out once, whole,
    and facing the way it faced before."""
    from xtal.analysis import isosurface as iso

    lattice = Lattice.cubic(SIDE)
    grid = sphere_grid((5.13, 0.07, 5.31), n=24)
    whole = isosurface(grid, lattice, 0.0)
    monkeypatch.setattr(iso, "_SLAB_CELLS", 1)
    sliced = isosurface(grid, lattice, 0.0)
    assert triangle_set(*sliced) == triangle_set(*whole)
    assert enclosed_volume(*sliced, lattice, (5.13, 0.07, 5.31)) \
        == pytest.approx(enclosed_volume(*whole, lattice,
                                         (5.13, 0.07, 5.31)))


def test_the_grid_queried_in_blocks_is_the_grid_queried_at_once(
        monkeypatch):
    """The nearest-surface query runs a block of points at a time; a
    block edge that dropped or doubled a point would leave a stripe of
    wrong distances through the cell."""
    from xtal.analysis import grid as grids

    pair = Structure.from_arrays(
        Lattice.cubic(SIDE), ["C", "O"],
        [[0.1, 0.2, 0.3], [0.6, 0.55, 0.9]])
    radii = {"C": 1.7, "O": 1.5}.get
    whole = distance_grid(pair, radii, shape=(11, 13, 7))
    monkeypatch.setattr(grids, "_POINT_BLOCK", 5)
    assert np.array_equal(distance_grid(pair, radii, shape=(11, 13, 7)),
                          whole)
    assert whole.dtype == np.float32
