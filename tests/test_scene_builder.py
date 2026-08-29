"""The render model: what actually gets drawn, asserted without a GPU."""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import ViewSettings


def test_inclusive_range_draws_the_closing_atoms(rutile):
    """The atom at x = 0 is drawn again at x = 1, or the cell looks
    gnawed.  Rutile: 6 atoms in the cell, 15 drawn."""
    scene = build_scene(rutile, ViewSettings())
    assert p1.expand(rutile).n_atoms == 6
    assert scene.n_atoms == 15
    frac = rutile.lattice.to_frac(scene.positions)
    assert frac.min() >= -1e-6 and frac.max() <= 1 + 1e-6


def test_display_range_scales_the_picture(rutile):
    settings = ViewSettings()
    one = build_scene(rutile, settings).n_atoms
    settings.set_cells(2, 1, 1)
    two = build_scene(rutile, settings).n_atoms
    settings.set_cells(2, 2, 2)
    eight = build_scene(rutile, settings).n_atoms
    assert two > one and eight > two
    assert eight > 6 * 8                    # cells plus boundaries


def test_cell_box_is_twelve_lines_per_cell(rutile):
    settings = ViewSettings()
    assert build_scene(rutile, settings).n_cell_lines == 12
    settings.set_cells(2, 2, 1)
    assert build_scene(rutile, settings).n_cell_lines == 48


def test_the_three_origin_edges_are_the_axis_colours(rutile):
    scene = build_scene(rutile, ViewSettings())
    colors = {tuple(c) for c in scene.cell_colors}
    assert (220, 60, 60) in colors          # a
    assert (60, 170, 60) in colors          # b
    assert (60, 100, 220) in colors         # c


def test_bonds_are_split_in_half_and_coloured_by_atom(quartz):
    scene = build_scene(quartz, ViewSettings())
    assert scene.n_bond_halves % 2 == 0
    colors = {tuple(c) for c in scene.bond_colors}
    from xtal.core import elements as el
    assert el.color("Si") in colors
    assert el.color("O") in colors
    # each half runs from an atom to the midpoint, so pairs of
    # consecutive halves share an endpoint
    assert np.allclose(scene.bond_ends[0], scene.bond_ends[1])


def test_styles_change_what_is_drawn(rutile):
    ball = build_scene(rutile, ViewSettings(style="ball_stick"))
    fill = build_scene(rutile, ViewSettings(style="spacefill"))
    wire = build_scene(rutile, ViewSettings(style="wireframe"))

    assert fill.n_bond_halves == 0          # no bonds in space filling
    assert fill.radii.max() > ball.radii.max()
    assert wire.n_atoms == 0                # lines only
    assert wire.n_bond_halves == ball.n_bond_halves
    assert wire.bond_render == "line"


def test_visibility_toggles(rutile):
    scene = build_scene(rutile, ViewSettings(show_atoms=False))
    assert scene.n_atoms == 0 and scene.n_bond_halves > 0
    scene = build_scene(rutile, ViewSettings(show_bonds=False))
    assert scene.n_atoms > 0 and scene.n_bond_halves == 0
    scene = build_scene(rutile, ViewSettings(show_cell=False))
    assert scene.n_cell_lines == 0


def test_boundary_mode_completes_bonds(dry_ice):
    """With boundary='bonded', a molecule cut by the cell edge is drawn
    whole instead of losing atoms."""
    inside = build_scene(dry_ice, ViewSettings(boundary="in_range"))
    bonded = build_scene(dry_ice, ViewSettings(boundary="bonded"))
    assert bonded.n_atoms > inside.n_atoms
    assert bonded.n_bond_halves > inside.n_bond_halves


def test_every_drawn_atom_knows_where_it_came_from(quartz):
    scene = build_scene(quartz, ViewSettings())
    cell = p1.expand(quartz)
    assert len(scene.atom_index) == scene.n_atoms
    assert scene.atom_index.max() < cell.n_atoms
    for i in range(scene.n_atoms):
        atom, shift = scene.instance(i)
        expected = cell.frac[atom] + np.array(shift)
        assert np.allclose(quartz.lattice.to_frac(scene.positions[i]),
                           expected, atol=1e-5)


def test_colours_and_radii_follow_the_element(rutile):
    from xtal.core import elements as el
    scene = build_scene(rutile, ViewSettings())
    cell = p1.expand(rutile)
    for i in range(scene.n_atoms):
        element = cell.elements[scene.atom_index[i]]
        assert tuple(scene.colors[i]) == el.color(element)
    assert scene.radii.min() > 0


def test_element_overrides_reach_the_scene(rutile):
    settings = ViewSettings()
    settings.element_colors["Ti"] = (0, 0, 0)
    settings.element_radii["Ti"] = 1.5
    scene = build_scene(rutile, settings)
    assert (0, 0, 0) in {tuple(c) for c in scene.colors}
    assert scene.radii.max() == pytest.approx(0.75)   # 1.5 * 0.5


def test_labels(rutile):
    rutile.ensure_labels()
    assert build_scene(rutile, ViewSettings()).labels == ()
    labelled = build_scene(rutile, ViewSettings(label_mode="element"))
    assert len(labelled.labels) == labelled.n_atoms
    assert {text for _pos, text in labelled.labels} == {"Ti", "O"}


def test_bounds_and_centre(rutile):
    scene = build_scene(rutile, ViewSettings())
    low, high = scene.bounds()
    assert np.all(high > low)
    assert np.allclose(scene.center(), (low + high) / 2)


def test_empty_structure_makes_an_empty_scene():
    empty = Structure.empty(Lattice.cubic(5.0))
    scene = build_scene(empty, ViewSettings(show_cell=False))
    assert scene.is_empty
    assert scene.n_atoms == 0
    assert np.allclose(scene.bounds()[0], 0)


def test_background_travels_with_the_scene(rutile):
    scene = build_scene(rutile, ViewSettings(background=(10, 20, 30)))
    assert scene.background == (10, 20, 30)
