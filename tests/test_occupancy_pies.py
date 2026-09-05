"""Occupancy spheres: VESTA's picture of a site more than one thing
shares.

Every other style draws a shared site as a lie.  Two atoms at the same
coordinates are two spheres exactly on top of each other, of which the
reader sees whichever happens to be larger, with nothing on screen to
say the other is there -- and a half-occupied site looks exactly like a
full one.

The tests are about what the wedges *say*: how many there are, how big
each is, and that a full site is left alone.  How round the sphere is
drawn is not tested and should not be, because it is a tessellation
constant.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core.site import Site
from xtalapp.viewport.builder import VACANCY_COLOR, build_scene
from xtalapp.viewport.scene import view_basis
from xtalapp.viewport.view_settings import ViewSettings

PIES = "ball_stick_occupancy"


def pies_settings(**kwargs) -> ViewSettings:
    return ViewSettings(style=PIES, show_cell=False, **kwargs)


def a_disordered_crystal() -> Structure:
    """One mixed site, one half-empty site, one ordinary atom."""
    return Structure(
        lattice=Lattice.cubic(6.0),
        sites=[Site("Fe", [0.0, 0.0, 0.0], occupancy=0.6),
               Site("Ni", [0.0, 0.0, 0.0], occupancy=0.4),
               Site("O", [0.5, 0.5, 0.5], occupancy=0.5),
               Site("Na", [0.25, 0.25, 0.25])],
        space_group="P1")


#: A camera looking down -z with y up -- the frame the pies are turned
#: onto in every test here, so that "how much of the circle" is a
#: question with one answer.
DOWN_Z = ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0))


def pie_points(model) -> np.ndarray:
    return model.pie_geometry(*DOWN_Z)[0]


def wedge_colors(model) -> dict:
    """Which colours the pies are made of, and how much of the circle
    each one covers.

    Read back off the triangles, because that is what the renderer
    gets: a colour that never reaches a face is a colour the picture
    does not have, whatever the builder thought it emitted.
    """
    faces = np.asarray(model.pie_faces, int)
    if not len(faces):
        return {}
    corners = np.asarray(pie_points(model), float)[faces]
    area = 0.5 * np.linalg.norm(
        np.cross(corners[:, 1] - corners[:, 0],
                 corners[:, 2] - corners[:, 0]), axis=1)
    out: dict = {}
    for color, size in zip(map(tuple, model.pie_colors), area,
                           strict=True):
        out[color] = out.get(color, 0.0) + float(size)
    total = sum(out.values())
    return {color: size / total for color, size in out.items()}


def test_a_shared_site_is_cut_in_proportion_to_what_shares_it():
    """0.6 Fe and 0.4 Ni is 60% of that sphere's surface in one colour
    and 40% in the other -- which is the whole claim the style makes."""
    model = build_scene(
        Structure(lattice=Lattice.cubic(6.0),
                  sites=[Site("Fe", [0.5, 0.5, 0.5], occupancy=0.6),
                         Site("Ni", [0.5, 0.5, 0.5], occupancy=0.4)],
                  space_group="P1"),
        pies_settings())
    shares = wedge_colors(model)
    assert len(shares) == 2
    assert sorted(shares.values()) == pytest.approx([0.4, 0.6], abs=0.01)


def test_the_empty_part_of_a_site_is_drawn_and_not_left_out():
    """A half-occupied site drawn as half a sphere would read as a
    small atom.  The vacancy gets a wedge of its own, in a grey that is
    not the background -- a wedge the colour of the paper reads as a
    hole in the picture."""
    model = build_scene(
        Structure(lattice=Lattice.cubic(6.0),
                  sites=[Site("O", [0.5, 0.5, 0.5], occupancy=0.25)],
                  space_group="P1"),
        pies_settings())
    shares = wedge_colors(model)
    assert shares[VACANCY_COLOR] == pytest.approx(0.75, abs=0.01)


def test_a_full_ordinary_site_gets_no_pie_at_all():
    """Otherwise every structure pays for the style, and every sphere
    in the picture is a mesh instead of a glyph."""
    quiet = Structure(lattice=Lattice.cubic(6.0),
                      sites=[Site("Na", [0.0, 0.0, 0.0])],
                      space_group="P1")
    assert build_scene(quiet, pies_settings()).n_pie_faces == 0


def test_only_the_disordered_sites_of_a_mixed_structure_are_cut():
    model = build_scene(a_disordered_crystal(), pies_settings())
    shares = wedge_colors(model)
    # Fe, Ni, O and the vacancy beside it -- and nothing for the Na
    assert len(shares) == 4
    assert VACANCY_COLOR in shares


def test_no_other_style_draws_a_pie():
    """A field on the style and not a setting: the picture is chosen
    by choosing the style, the way ellipsoids are."""
    structure = a_disordered_crystal()
    for style in ("ball_stick", "spacefill", "ortep", "polyhedra"):
        model = build_scene(structure, ViewSettings(style=style))
        assert model.n_pie_faces == 0, style


def test_the_spheres_underneath_are_still_drawn():
    """Every array in the scene model is indexed by drawn atom -- the
    labels, the legend, the selection flags, the picking -- so dropping
    the occupants of a shared site to save hidden geometry would put
    four other things out of step."""
    structure = a_disordered_crystal()
    plain = build_scene(structure, ViewSettings(show_cell=False))
    model = build_scene(structure, pies_settings())
    assert model.n_atoms == plain.n_atoms
    assert np.array_equal(model.atom_index, plain.atom_index)


def test_a_pie_covers_the_largest_sphere_it_stands_on():
    """It has to hide them, and a wedge sagging inside the sphere
    underneath z-fights into speckle."""
    structure = Structure(
        lattice=Lattice.cubic(8.0),
        sites=[Site("H", [0.5, 0.5, 0.5], occupancy=0.5),
               Site("I", [0.5, 0.5, 0.5], occupancy=0.5)],
        space_group="P1")
    model = build_scene(structure, pies_settings())
    centre = model.positions[0]
    reach = np.linalg.norm(np.asarray(pie_points(model)) - centre,
                           axis=1)
    assert reach.min() > float(model.radii.max())


def test_the_normals_are_the_directions_the_points_lie_in():
    """Without them every pie is flat-shaded and reads as a stack of
    rings rather than as a sphere."""
    model = build_scene(a_disordered_crystal(), pies_settings())
    points, normals = model.pie_geometry(*DOWN_Z)
    assert len(normals) == len(points)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-5)
    # and they point out of the sphere they are on, after the turn
    out = points - np.asarray(model.pie_centres, float)
    out = out / np.linalg.norm(out, axis=1, keepdims=True)
    assert np.allclose(out, normals, atol=1e-5)


def test_the_wedges_are_cut_about_whichever_axis_the_camera_is_on():
    """A pie chart is only readable face on: cut about a fixed
    crystallographic axis, the same 60/40 site reads as any split at
    all from most directions.

    The claim is that the cut is a plane *containing* the view axis --
    which is what puts the boundary across the middle of the disc the
    reader sees -- so each occupant's vertices land wholly on one side
    of the screen's horizontal, whichever way the camera is turned.
    """
    model = build_scene(
        Structure(lattice=Lattice.cubic(6.0),
                  sites=[Site("Fe", [0.5, 0.5, 0.5], occupancy=0.5),
                         Site("Ni", [0.5, 0.5, 0.5], occupancy=0.5)],
                  space_group="P1"),
        pies_settings())
    faces = np.asarray(model.pie_faces, int)
    for direction, up in (((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
                          ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
                          ((1.0, 2.0, -3.0), (0.0, 0.0, 1.0))):
        points, _ = model.pie_geometry(direction, up)
        offsets = points - np.asarray(model.pie_centres, float)
        # the screen's vertical, from the same frame the pie is turned
        # onto: the two wedges must be either side of it
        height = (offsets @ view_basis(direction, up)[:, 1])[faces]
        reach = {}
        for color, corners in zip(map(tuple, model.pie_colors), height,
                                  strict=True):
            low, high = reach.get(color, (0.0, 0.0))
            reach[color] = (min(low, corners.min()),
                            max(high, corners.max()))
        assert len(reach) == 2
        above, below = sorted(reach.values())
        assert above[1] < 1e-6              # one wedge is all below
        assert below[0] > -1e-6             # the other all above


def test_an_over_full_site_is_shown_full_rather_than_trimmed():
    """0.7 and 0.5 is somebody's refinement and not this module's to
    correct.  The wedges are scaled to fit the circle, so both are
    still visible and neither is silently dropped."""
    structure = Structure(
        lattice=Lattice.cubic(6.0),
        sites=[Site("Fe", [0.5, 0.5, 0.5], occupancy=0.7),
               Site("Ni", [0.5, 0.5, 0.5], occupancy=0.5)],
        space_group="P1")
    shares = wedge_colors(build_scene(structure, pies_settings()))
    assert VACANCY_COLOR not in shares
    assert sorted(shares.values()) == pytest.approx(
        [0.5 / 1.2, 0.7 / 1.2], abs=0.01)


def test_a_split_site_is_two_sites_and_not_one_pie():
    """0.245 and 0.255 is a split position, which VESTA draws as two
    partly empty atoms -- so the grouping rounds rather than
    clusters."""
    structure = Structure(
        lattice=Lattice.cubic(20.0),
        sites=[Site("Fe", [0.245, 0.5, 0.5], occupancy=0.5),
               Site("Fe", [0.255, 0.5, 0.5], occupancy=0.5)],
        space_group="P1")
    model = build_scene(structure, pies_settings())
    shares = wedge_colors(model)
    # one iron colour and one vacancy, half the drawn area each,
    # because each of the two sites is drawn half empty
    assert len(shares) == 2
    assert shares[VACANCY_COLOR] == pytest.approx(0.5, abs=0.01)
