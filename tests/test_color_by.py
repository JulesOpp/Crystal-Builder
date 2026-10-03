"""Colour by a number per bond or per atom: what the scene draws."""

import numpy as np

from xtal.core import bonding, p1, scalars
from xtalapp.viewport import colormaps
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import ViewSettings


def _bond_colour_by_length(scene, structure):
    """Each drawn bond's length beside the colour its halves wear."""
    graph = bonding.graph(structure)
    lengths = scalars.values(structure, "bond_length", graph=graph)
    pairs = {}
    for start, end, color in zip(scene.bond_starts, scene.bond_ends,
                                 scene.bond_colors, strict=True):
        half = float(np.linalg.norm(end - start))
        pairs.setdefault(round(2 * half, 2), set()).add(tuple(color))
    return lengths, pairs


def test_bond_length_colours_follow_the_length_not_the_element(rutile):
    """Rutile's two Ti-O lengths are two colours -- the ends of the
    map -- and both halves of a bond wear its colour, the titanium's
    half as much as the oxygen's.  Fails if a half keeps its atom's
    element colour."""
    view = ViewSettings(color_by="bond_length")
    scene = build_scene(rutile, view)
    lengths, pairs = _bond_colour_by_length(scene, rutile)
    lo, hi = lengths.min(), lengths.max()
    bottom, top = (tuple(int(c) for c in row)
                   for row in colormaps.colors([lo, hi], lo, hi))
    assert pairs == {round(lo, 2): {bottom}, round(hi, 2): {top}}
    # The atoms are still their elements.
    assert {tuple(c) for c in scene.colors} == {
        view.color_for("Ti"), view.color_for("O")}


def test_an_undefined_angle_is_grey_not_the_bottom_of_the_scale(rutile):
    """Six-coordinate titanium has no one ideal angle, so it is grey
    and off the scale; the colour bar says *none* because some of
    what is drawn is.  A NaN taken as zero would be the map's bottom
    colour -- the most regular atom in the picture."""
    scene = build_scene(rutile, ViewSettings(color_by="angle_deviation",
                                             show_legend=True))
    elements = np.array(p1.expand(rutile).elements)[scene.atom_index]
    titanium = {tuple(c) for c in scene.colors[elements == "Ti"]}
    assert titanium == {colormaps.UNDEFINED}
    oxygen = {tuple(c) for c in scene.colors[elements == "O"]}
    assert colormaps.UNDEFINED not in oxygen
    assert scene.legend[0] == ("Angle from ideal (°)", None)
    assert scene.legend[-1] == ("none", colormaps.UNDEFINED)


def test_turning_colour_by_off_restores_hand_chosen_colours(rutile):
    """A colour chosen by hand is never overwritten: colouring by
    coordination draws over it, and turning that off draws it again,
    with the element legend back in place of the bar."""
    view = ViewSettings(show_legend=True)
    view.element_colors["Ti"] = (12, 34, 56)
    colored = build_scene(rutile, ViewSettings(
        color_by="coordination", show_legend=True,
        element_colors=dict(view.element_colors)))
    assert (12, 34, 56) not in {tuple(c) for c in colored.colors}
    assert view.element_colors == {"Ti": (12, 34, 56)}
    plain = build_scene(rutile, view)
    assert (12, 34, 56) in {tuple(c) for c in plain.colors}
    assert ("Ti", (12, 34, 56)) in plain.legend


def test_a_count_has_a_bar_of_whole_numbers(rutile):
    """Coordination is 3 or 6 in rutile: the bar reads 6, 5, 4, 3 from
    the top, never 4.2."""
    scene = build_scene(rutile, ViewSettings(color_by="coordination",
                                             show_legend=True))
    assert [label for label, _c in scene.legend] == [
        "Coordination", "6", "5", "4", "3"]


def test_a_range_set_by_hand_clamps_what_falls_outside_it(rutile):
    """Every Ti-O bond is longer than 1.5 A, so a range of 1.0 to 1.5
    paints them all the top of the map rather than off it."""
    scene = build_scene(rutile, ViewSettings(color_by="bond_length",
                                             color_range=(1.0, 1.5)))
    top = tuple(colormaps.COLOR_MAPS["viridis"][-1])
    assert {tuple(c) for c in scene.bond_colors} == {top}


def test_colour_by_is_saved_with_the_view():
    view = ViewSettings(color_by="mean_angle", color_map="plasma",
                        color_range=(100.0, 130.0))
    again = ViewSettings.from_dict(view.to_dict())
    assert (again.color_by, again.color_map, again.color_range) == (
        "mean_angle", "plasma", (100.0, 130.0))
    assert ViewSettings.from_dict({"color_by": "nonsense"}).color_by == ""
