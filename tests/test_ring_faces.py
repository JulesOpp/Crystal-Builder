"""Rings filled by size: what the scene draws, without a GPU."""

from pathlib import Path

import numpy as np

from xtal import Lattice, Structure
from xtal.core.site import Site
from xtal.io.cif_reader import read_cif
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import RING_COLORS, ViewSettings

SAMPLES = Path(__file__).resolve().parent.parent / "resources" / "samples"


def _graphene(n):
    lattice = Lattice.from_parameters(2.46 * n, 2.46 * n, 10.0,
                                      90, 90, 120)
    sites = [Site("C", np.array([(i + x) / n, (j + y) / n, 0.5]))
             for i in range(n) for j in range(n)
             for x, y in ((1 / 3, 2 / 3), (2 / 3, 1 / 3))]
    return Structure(lattice=lattice, sites=sites)


def test_rings_are_not_drawn_unless_asked_for():
    """Off by default: it is a search of the whole graph, and a
    picture of something particular rather than of the crystal."""
    assert build_scene(_graphene(3), ViewSettings()).n_ring_faces == 0


def test_ring_faces_are_coloured_by_size_and_listed_in_the_legend():
    """MFU-4l's triazolate pentagons and its benzene and benzotriazole
    hexagons: two sizes, two colours, two legend rows after the
    elements.  Fails if a ring takes another size's colour or the
    legend forgets the rings."""
    mfu = read_cif(SAMPLES / "MFU4l.cif")
    scene = build_scene(mfu, ViewSettings(show_rings=True,
                                          show_legend=True))
    assert scene.n_ring_faces
    colours = {tuple(c) for c in scene.ring_colors}
    assert colours == {RING_COLORS[5], RING_COLORS[6]}
    assert scene.legend[-2:] == (("5-ring", RING_COLORS[5]),
                                 ("6-ring", RING_COLORS[6]))
    assert scene.ring_faces.max() < len(scene.ring_points)


def test_a_ring_is_a_fan_from_its_centre():
    """One triangle per bond of the ring, about a centre that is the
    middle of its atoms: six for a hexagon, round a point 1.42 A from
    each corner."""
    scene = build_scene(_graphene(3), ViewSettings(show_rings=True))
    assert scene.n_ring_faces % 6 == 0
    centre, *corners = scene.ring_points[:7]
    assert np.allclose(np.linalg.norm(np.array(corners) - centre,
                                      axis=1), 1.42, atol=0.01)


def test_a_ring_with_an_atom_out_of_the_picture_is_not_drawn():
    """A face over a corner the display range cut away is a face over
    nothing.  Half the cell along a draws fewer rings than the whole
    of it."""
    sheet = _graphene(4)
    whole = build_scene(sheet, ViewSettings(show_rings=True))
    half = build_scene(sheet, ViewSettings(show_rings=True,
                                           range_a=(0.0, 0.5)))
    assert 0 < half.n_ring_faces < whole.n_ring_faces


def test_a_colour_chosen_for_a_size_is_the_one_drawn():
    chosen = (10, 20, 30)
    scene = build_scene(_graphene(3), ViewSettings(
        show_rings=True, ring_colors={6: chosen}))
    assert {tuple(c) for c in scene.ring_colors} == {chosen}


def test_ring_settings_round_trip_through_the_project():
    """Fails if a size comes back as the string JSON wrote it as, and
    the chosen colour is then never looked up again."""
    view = ViewSettings(show_rings=True, ring_max_size=10,
                        ring_opacity=0.3, ring_colors={7: (1, 2, 3)})
    back = ViewSettings.from_dict(view.to_dict())
    assert back.show_rings and back.ring_max_size == 10
    assert back.ring_opacity == 0.3
    assert back.ring_color(7) == (1, 2, 3)
    assert back.ring_color(6) == RING_COLORS[6]


def test_a_copy_of_the_settings_does_not_share_the_ring_colours():
    view = ViewSettings(ring_colors={5: (1, 2, 3)})
    copy = view.copy()
    copy.ring_colors[5] = (4, 5, 6)
    assert view.ring_color(5) == (1, 2, 3)
