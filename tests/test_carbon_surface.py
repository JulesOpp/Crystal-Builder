"""The sheet a disordered carbon is laid on: xtal.carbon.surface."""

import numpy as np
import pytest

from xtal.carbon import surface as sf


def _sheet(name, scale=10.0, ratio=0.3, repeat=(1, 1, 1)):
    lattice, vertices, edges = sf.net_of(name)
    lattice, vertices, edges = sf.repeated(lattice, vertices, edges,
                                           repeat)
    frame = sf.skeleton(lattice, vertices, edges, scale)
    radius = ratio * frame.edge_length
    width = sf.WIDTH_FRACTION * radius
    field = sf.Field(frame, width)
    return (frame, sf.march(field, sf.level_for(radius, width)),
            vertices, edges, radius)


def test_the_welded_srs_surface_has_every_edge_in_two_triangles():
    """Closed and oriented: every edge of the welded sheet is in two
    triangles, wound opposite ways, and it runs on through all three
    pairs of cell faces.  Fails if the weld leaves a seam -- a row of
    edges with one triangle each, where the dual would have a line of
    two-coordinate carbon nobody asked for."""
    _frame, mesh, _v, _e, _r = _sheet("srs")
    _keys, _inverse, counts = mesh.edges()
    assert set(counts) == {2}
    assert mesh.is_closed()
    assert mesh.periodicity() == 3


@pytest.mark.parametrize("name, repeat", [("srs", (1, 1, 1)),
                                          ("dia", (1, 1, 1)),
                                          ("pcu", (2, 1, 1))])
def test_its_euler_characteristic_is_that_of_the_net(name, repeat):
    """A tube round every edge is one handle per independent loop of
    the net: chi = 2 (V - E), so -8 for srs and -16 for dia's
    conventional cell.  This is what Gauss-Bonnet turns into the
    heptagons a schwarzite must have, so a sheet with the wrong chi
    builds the wrong carbon."""
    _frame, mesh, vertices, edges, _r = _sheet(name, repeat=repeat)
    assert mesh.euler() == sf.expected_euler(len(vertices), len(edges))


def test_the_tube_is_the_strut_radius_along_an_edge():
    """Halfway along a pcu edge, far from both nodes, the sheet is R
    from the edge's axis."""
    frame, mesh, _v, _e, radius = _sheet("pcu", scale=12.0)
    a = frame.lattice.matrix[0]
    corners = mesh.corners().reshape(-1, 3)
    near_middle = np.abs(corners @ a / (a @ a) - 0.5) < 0.05
    # The axis is the line along a through the vertex at the origin.
    lateral = corners[near_middle] - np.outer(
        corners[near_middle] @ a / (a @ a), a)
    frac = frame.lattice.to_frac(lateral)
    lateral = frame.lattice.to_cart(frac - np.round(frac))
    distance = np.linalg.norm(lateral, axis=1)
    assert np.median(distance) == pytest.approx(radius, abs=0.15)


def test_the_solved_cell_gives_the_requested_density_within_two_percent():
    """The cell is solved so that the share of the sheet kept, at
    graphene's carbon per area, is the density asked for; and the
    carbon count the build must hit is that density's."""
    lattice, vertices, edges = sf.net_of("dia")
    solved = sf.solve_scale(lattice, vertices, edges, density=0.42,
                            radius_ratio=0.3, coverage=0.4)
    volume = solved.skeleton.volume
    held = sf.GRAPHENE_AREAL * 0.4 * solved.area
    assert held / volume / sf.ATOMS_PER_GCC == pytest.approx(0.42,
                                                             rel=0.02)
    assert solved.carbons / volume / sf.ATOMS_PER_GCC == pytest.approx(
        0.42, rel=0.01)


def test_twice_the_density_is_a_smaller_cell():
    """Area as the square, volume as the cube: double the density and
    the edge halves, near enough."""
    lattice, vertices, edges = sf.net_of("srs")
    light, dense = (sf.solve_scale(lattice, vertices, edges,
                                   density=rho, radius_ratio=0.3,
                                   coverage=1.0)
                    for rho in (0.25, 0.5))
    ratio = dense.skeleton.edge_length / light.skeleton.edge_length
    assert ratio == pytest.approx(0.5, rel=0.03)


def test_a_sheet_too_tight_for_carbon_is_refused():
    """A trilayer's inner sheet on thin struts has no room for a
    carbon sheet: refused with the radius it would have had."""
    lattice, vertices, edges = sf.net_of("dia")
    with pytest.raises(sf.SurfaceError, match="innermost sheet"):
        sf.solve_scale(lattice, vertices, edges, density=0.42,
                       radius_ratio=0.2, coverage=0.4, layers=3)


def test_a_layer_net_is_refused():
    """A sheet round a 2-periodic net cannot percolate in three
    directions."""
    with pytest.raises(sf.SurfaceError, match="3-periodic"):
        sf.net_of("hcb")
