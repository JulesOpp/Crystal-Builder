"""View settings and the draw-style registry (no Qt, no VTK)."""

import pytest

from xtalapp.viewport import styles
from xtalapp.viewport.view_settings import (
    BACKGROUNDS,
    BOUNDARIES,
    ViewSettings,
)


def test_defaults():
    s = ViewSettings()
    assert s.style == "ball_stick"
    assert s.show_atoms and s.show_bonds and s.show_cell
    assert s.ranges == ((0.0, 1.0),) * 3
    assert s.cells == (1, 1, 1)


def test_element_colours_and_radii_can_be_overridden():
    s = ViewSettings()
    assert s.color_for("O") == (255, 13, 13)        # Jmol red
    s.element_colors["O"] = (0, 0, 255)
    assert s.color_for("O") == (0, 0, 255)

    default = s.base_radius("Fe", "covalent")
    s.element_radii["Fe"] = 0.9
    assert s.base_radius("Fe", "covalent") == 0.9
    assert default != 0.9


def test_radius_sources():
    s = ViewSettings()
    assert s.base_radius("C", "vdw") > s.base_radius("C", "covalent")
    assert s.base_radius("C", "bond") == s.bond_radius


def test_set_cells_updates_the_range():
    s = ViewSettings()
    s.set_cells(2, 3, 1)
    assert s.ranges == ((0.0, 2.0), (0.0, 3.0), (0.0, 1.0))
    assert s.cells == (2, 3, 1)
    with pytest.raises(ValueError):
        s.set_cells(0, 1, 1)


def test_copy_is_deep():
    s = ViewSettings()
    s.element_colors["O"] = (1, 2, 3)
    c = s.copy()
    c.element_colors["O"] = (9, 9, 9)
    c.style = "spacefill"
    assert s.element_colors["O"] == (1, 2, 3)
    assert s.style == "ball_stick"


def test_dict_round_trip():
    s = ViewSettings(style="spacefill", atom_scale=0.8,
                     background=BACKGROUNDS["slate"])
    s.set_cells(2, 2, 2)
    s.element_colors["Fe"] = (10, 20, 30)
    back = ViewSettings.from_dict(s.to_dict())
    assert back.style == "spacefill"
    assert back.atom_scale == 0.8
    assert back.background == BACKGROUNDS["slate"]
    assert back.ranges == s.ranges
    assert back.element_colors["Fe"] == (10, 20, 30)


def test_the_appearance_choices_survive_a_session():
    """Colours the user chose for the net and the planes, and whether
    the ellipsoids are shaded -- all of it saved with the project, none
    of it with the CIF."""
    s = ViewSettings(topology_color=(10, 200, 90),
                     plane_color=(0, 0, 255))
    s.ellipsoid_octants = False
    back = ViewSettings.from_dict(s.to_dict())
    assert back.topology_color == (10, 200, 90)
    assert back.plane_color == (0, 0, 255)
    assert not back.ellipsoid_octants


def test_a_session_written_before_the_colours_existed_reads_defaults():
    """Every project on disk was written without them, and a reader
    that needed them would fail to open all of them."""
    s = ViewSettings.from_dict({"style": "spacefill"})
    assert s.topology_color == ViewSettings().topology_color
    assert s.plane_color == ViewSettings().plane_color
    assert s.ellipsoid_octants


def test_a_planes_normal_is_darker_than_the_plane_itself():
    """One control, two things: the normal is the plane's arrow and
    reading as a separate object is what it must not do."""
    s = ViewSettings(plane_color=(200, 100, 50))
    assert all(n < c for n, c in zip(s.normal_color, s.plane_color,
                                     strict=True))
    assert ViewSettings(plane_color=(0, 0, 0)).normal_color == (0, 0, 0)


# --------------------------------------------- the three boundaries

def test_the_boundary_starts_at_the_one_that_misleads_nobody():
    """``in_range`` under-coordinates every atom on the surface of the
    picture and ``bonded`` draws a box surrounded by atoms that are
    not in it.  Only one of the three is not wrong about something,
    so it is the one the application opens with."""
    assert BOUNDARIES == ("in_range", "bonded", "half")
    assert ViewSettings().boundary == "half"


def test_the_new_view_state_survives_a_session():
    s = ViewSettings(boundary="half", show_planes=False,
                     show_scale_bar=True)
    back = ViewSettings.from_dict(s.to_dict())
    assert back.boundary == "half"
    assert not back.show_planes
    assert back.show_scale_bar


def test_a_session_written_before_half_existed_still_reads():
    """The two-valued string is what every project on disk holds, and
    a reader that rejected it would lose the setting on every file
    saved before this."""
    for old in ("in_range", "bonded"):
        assert ViewSettings.from_dict({"boundary": old}).boundary == old


def test_a_boundary_this_version_does_not_know_falls_back():
    """A project from a later version names a fourth answer.  Drawing
    it the default way is right; refusing to open it is not."""
    assert ViewSettings.from_dict(
        {"boundary": "sliced"}).boundary == ViewSettings().boundary


def test_the_new_toggles_default_the_way_they_were_argued_for():
    """Planes on, because defining one and seeing nothing is the
    complaint.  Scale bar off, like depth cueing: an effect a picture
    must not acquire on its own."""
    s = ViewSettings()
    assert s.show_planes
    assert not s.show_scale_bar


def test_style_registry():
    assert set(styles.names()) == {"ball_stick", "ball_stick_occupancy",
                                   "stick", "wireframe", "net",
                                   "spacefill", "polyhedra",
                                   "polyhedra_stick", "ortep",
                                   "platon", "cartoon"}
    ball = styles.get("ball_stick")
    assert ball.draw_bonds and ball.bond_render == "tube"
    assert not styles.get("spacefill").draw_bonds
    assert styles.get("wireframe").bond_render == "line"
    net = styles.get("net")
    assert net.radius_factor == 0.0 and not net.draw_bonds
    assert styles.get("ball_stick_occupancy").occupancy_pies
    assert not ball.occupancy_pies
    polyhedra = styles.get("polyhedra")
    assert polyhedra.draw_polyhedra and not polyhedra.draw_bonds
    assert not ball.draw_polyhedra
    mixed = styles.get("polyhedra_stick")
    assert mixed.draw_polyhedra and mixed.draw_bonds
    assert styles.get("ortep").ellipsoids
    assert not ball.ellipsoids
    platon = styles.get("platon")
    assert platon.ellipsoids and platon.outline and platon.tint
    cartoon = styles.get("cartoon")
    assert cartoon.shading == "flat" and cartoon.outline
    assert not ball.outline and ball.shading == "lit"
    with pytest.raises(ValueError):
        styles.get("hologram")


def test_style_radii_follow_the_settings():
    s = ViewSettings()
    ball = styles.get("ball_stick")
    fill = styles.get("spacefill")
    assert fill.atom_radius("C", s) > ball.atom_radius("C", s)
    s.atom_scale = 2.0
    assert ball.atom_radius("C", s) == pytest.approx(
        2.0 * 0.5 * s.base_radius("C", "covalent"))
    assert styles.get("wireframe").atom_radius("C", s) == 0.0
