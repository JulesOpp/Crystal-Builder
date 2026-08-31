"""View settings and the draw-style registry (no Qt, no VTK)."""

import pytest

from xtalapp.viewport import styles
from xtalapp.viewport.view_settings import BACKGROUNDS, ViewSettings


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


def test_style_registry():
    assert set(styles.names()) == {"ball_stick", "stick", "wireframe",
                                   "spacefill", "polyhedra",
                                   "polyhedra_stick", "ortep"}
    ball = styles.get("ball_stick")
    assert ball.draw_bonds and ball.bond_render == "tube"
    assert not styles.get("spacefill").draw_bonds
    assert styles.get("wireframe").bond_render == "line"
    polyhedra = styles.get("polyhedra")
    assert polyhedra.draw_polyhedra and not polyhedra.draw_bonds
    assert not ball.draw_polyhedra
    mixed = styles.get("polyhedra_stick")
    assert mixed.draw_polyhedra and mixed.draw_bonds
    assert styles.get("ortep").ellipsoids
    assert not ball.ellipsoids
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
