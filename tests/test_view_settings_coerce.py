"""Checking what an assistant asks a tab to look like (no Qt, no VTK).

``coerce_view`` stands between a client's JSON and ``ViewSettings``:
it gives back values of the record's own types, or one sentence that
says what was wrong.  Nothing half-applied, nothing silently replaced
by a default the way ``from_dict`` does for an old project.
"""

import dataclasses

import pytest

from xtal.core import scalars
from xtalapp.viewport import colormaps, styles
from xtalapp.viewport.view_settings import (
    BACKGROUNDS,
    BOUNDARIES,
    DUMMY_RADIUS_MAX,
    ELEMENT_RADIUS_RANGE,
    LABEL_MODES,
    PORE_SPHERES,
    VIEW_CHOICES,
    ViewSettings,
    coerce_view,
    view_schema,
)


def test_every_field_of_view_settings_is_in_the_schema():
    """A field added to ViewSettings without a schema entry would be a
    setting the assistant can neither see nor change."""
    schema = view_schema()
    names = {f.name for f in dataclasses.fields(ViewSettings)}
    assert set(schema) == names
    defaults = ViewSettings().to_dict()
    for name, entry in schema.items():
        assert set(entry) == {"type", "choices", "default"}, name
        assert isinstance(entry["type"], str) and entry["type"], name
        assert entry["default"] == defaults[name], name
        if name in VIEW_CHOICES:
            assert entry["choices"] == list(VIEW_CHOICES[name]), name
        else:
            assert entry["choices"] is None, name


def test_every_field_can_be_set_to_its_own_default():
    """If a field's type had no coercer, sending back what view() gave
    would be refused -- the round trip the assistant relies on."""
    defaults = ViewSettings().to_dict()
    cleaned = coerce_view(defaults)
    assert isinstance(cleaned, dict), cleaned
    assert set(cleaned) == set(defaults)


def test_the_choice_lists_are_the_existing_ones():
    """A list copied here would drift from the one the panel and the
    scene use, and offer a style that no longer draws."""
    assert VIEW_CHOICES["style"] == tuple(styles.names())
    assert VIEW_CHOICES["color_by"] == ("",) + tuple(scalars.QUANTITIES)
    assert VIEW_CHOICES["color_map"] == tuple(colormaps.COLOR_MAPS)
    assert VIEW_CHOICES["boundary"] == BOUNDARIES
    assert VIEW_CHOICES["pore_spheres"] == tuple(
        v for v, _label, _tip in PORE_SPHERES)
    assert VIEW_CHOICES["label_mode"] == LABEL_MODES
    assert VIEW_CHOICES["projection"] == ("perspective", "orthographic")


@pytest.mark.parametrize("name", sorted(VIEW_CHOICES))
def test_each_choice_list_takes_its_members_and_refuses_an_outsider(name):
    """Without this a misspelt style would reach the scene and raise on
    every redraw, or a refusal would leave the client guessing."""
    for choice in VIEW_CHOICES[name]:
        assert coerce_view({name: choice}) == {name: choice}
    refusal = coerce_view({name: "not_a_choice"})
    assert isinstance(refusal, str)
    assert name in refusal and "not_a_choice" in refusal
    for choice in VIEW_CHOICES[name]:
        assert repr(choice) in refusal


def test_a_misspelt_key_is_refused_with_a_suggestion():
    """An unknown key passed through would be set on the record as a
    stray attribute and draw nothing; without the suggestion the client
    cannot tell what it meant."""
    refusal = coerce_view({"show_ring": True})
    assert isinstance(refusal, str)
    assert "show_ring" in refusal
    assert "did you mean show_rings" in refusal
    # Every valid name is listed, so the client can correct itself.
    for f in dataclasses.fields(ViewSettings):
        assert f.name in refusal


def test_a_key_with_no_close_match_lists_the_fields_sorted():
    """The list is what a client reads to recover; unsorted, the field
    it wanted is somewhere in sixty."""
    refusal = coerce_view({"zzzz": 1})
    assert isinstance(refusal, str)
    assert "did you mean" not in refusal
    names = sorted(f.name for f in dataclasses.fields(ViewSettings))
    positions = [refusal.index(n) for n in names]
    assert positions == sorted(positions)


def test_types_are_coerced_from_what_a_client_sends():
    """A client sends JSON, often with numbers as text; refusing "1.5"
    would make the assistant fail at things the person can do."""
    assert coerce_view({"show_rings": "true"}) == {"show_rings": True}
    assert coerce_view({"show_rings": "False"}) == {"show_rings": False}
    assert coerce_view({"show_rings": True}) == {"show_rings": True}
    assert coerce_view({"atom_scale": "1.5"}) == {"atom_scale": 1.5}
    assert coerce_view({"atom_scale": 2}) == {"atom_scale": 2.0}
    assert isinstance(coerce_view({"atom_scale": 2})["atom_scale"], float)
    assert coerce_view({"ring_max_size": "3"}) == {"ring_max_size": 3}
    assert coerce_view({"ring_max_size": 10.0}) == {"ring_max_size": 10}
    assert coerce_view({"pore_copy": -1}) == {"pore_copy": -1}
    assert coerce_view({"topology_color": [255, 0, 0]}) == {
        "topology_color": (255, 0, 0)}
    assert coerce_view({"range_a": [0, 2]}) == {"range_a": (0.0, 2.0)}
    assert coerce_view({"range_c": ["-0.5", 1.5]}) == {
        "range_c": (-0.5, 1.5)}
    assert coerce_view({"background": "white"}) == {
        "background": BACKGROUNDS["white"],
        "background_follows_theme": False}
    assert coerce_view({"background": [10, 20, 30]}) == {
        "background": (10, 20, 30), "background_follows_theme": False}
    assert coerce_view({"color_range": None}) == {"color_range": None}
    assert coerce_view({"color_range": [1, "2.5"]}) == {
        "color_range": (1.0, 2.5)}
    assert coerce_view({"polyhedron_centres": ["ti", "Zn"]}) == {
        "polyhedron_centres": ("Ti", "Zn")}
    assert coerce_view({"polyhedron_pairs_off": ["Ti-O", ["zn", "N"]]}) \
        == {"polyhedron_pairs_off": ("O-Ti", "N-Zn")}
    assert coerce_view({"element_colors": {"o": [0, 0, 255]}}) == {
        "element_colors": {"O": (0, 0, 255)}}
    assert coerce_view({"element_radii": {"Fe": "0.9"}}) == {
        "element_radii": {"Fe": 0.9}}
    assert coerce_view({"ring_colors": {"5": [1, 2, 3], 6: [4, 5, 6]}}) \
        == {"ring_colors": {5: (1, 2, 3), 6: (4, 5, 6)}}


def test_numbers_are_taken_up_to_their_limits():
    """The ends of each range are values the panel offers; refusing
    them would refuse what a person can set by hand."""
    for changes in ({"ellipsoid_probability": 0.9},
                    {"ellipsoid_probability": "0.99"},
                    {"depth_cue_start": 0}, {"depth_cue_end": 1},
                    {"polyhedron_opacity": 0.05}, {"ring_opacity": 1},
                    {"atom_scale": 3}, {"bond_radius": 0.01},
                    {"axes_scale": 0.5}, {"ring_max_size": 12},
                    {"pore_cavity": 0}, {"polyhedron_min_vertices": 3},
                    {"element_radii": {"Fe": ELEMENT_RADIUS_RANGE[1]}},
                    # A marker the size of a pore is what one is for.
                    {"element_radii": {"X": DUMMY_RADIUS_MAX}}):
        assert isinstance(coerce_view(changes), dict), changes


@pytest.mark.parametrize("changes", [
    {"show_rings": 2},
    {"show_rings": 1},
    {"show_rings": "yes"},
    {"show_rings": None},
    {"atom_scale": "big"},
    {"atom_scale": True},
    {"atom_scale": float("nan")},
    {"ring_max_size": 1.5},
    {"ring_max_size": "1.5"},
    {"ring_max_size": False},
    {"style": 3},
    {"topology_color": [300, 0, 0]},
    {"topology_color": [-1, 0, 0]},
    {"topology_color": [255, 0]},
    {"topology_color": [255, 0, 0.5]},
    {"topology_color": "red"},
    {"background": "mauve"},
    {"range_a": [2, 0]},
    {"range_a": [0, 1, 2]},
    {"range_a": 1},
    {"color_range": [3, 1]},
    {"color_range": [2, 2]},
    {"ellipsoid_probability": 90},
    {"ellipsoid_probability": 1},
    {"ellipsoid_probability": 0},
    {"atom_scale": 0},
    {"atom_scale": 4},
    {"bond_radius": -0.1},
    {"axes_scale": 10},
    {"polyhedron_opacity": 1.5},
    {"pore_opacity": 0},
    {"depth_cue_start": 1.2},
    {"depth_cue_strength": -0.1},
    {"ring_max_size": 2},
    {"ring_max_size": 13},
    {"polyhedron_min_vertices": 2},
    {"pore_cavity": -1},
    {"pore_copy": -2},
    {"color_range": "auto"},
    {"polyhedron_centres": ["Xx"]},
    {"polyhedron_centres": "Ti"},
    {"polyhedron_pairs_off": ["Ti"]},
    {"polyhedron_pairs_off": [["Ti", "Qq"]]},
    {"element_colors": {"Xx": [0, 0, 0]}},
    {"element_colors": {"O": [0, 0, 256]}},
    {"element_colors": ["O"]},
    {"element_radii": {"Fe": 0}},
    {"element_radii": {"Fe": -0.5}},
    {"element_radii": {"Fe": 6}},
    {"element_colors": {"o": [0, 0, 0], "O": [1, 1, 1]}},
    {"ring_colors": {"6": [1, 2, 3], 6: [4, 5, 6]}},
    {"ring_colors": {"2": [1, 2, 3]}},
    {"ring_colors": {"13": [1, 2, 3]}},
    {"ring_colors": {"six": [1, 2, 3]}},
], ids=repr)
def test_nonsense_values_are_refused(changes):
    """Each of these, let through, either raises in the scene builder
    or draws something nobody asked for."""
    refusal = coerce_view(changes)
    assert isinstance(refusal, str), refusal
    assert next(iter(changes)) in refusal


def test_one_bad_key_refuses_the_lot():
    """Half a change applied is a picture neither the person nor the
    assistant asked for, with no record of which half."""
    refusal = coerce_view({"show_rings": True, "style": "nonsense"})
    assert isinstance(refusal, str)
    assert "style" in refusal


def test_something_other_than_a_dict_is_refused():
    """A list or a string from a confused client must be a sentence,
    not an AttributeError out of the verb."""
    assert isinstance(coerce_view(["style"]), str)
    assert isinstance(coerce_view("style=polyhedra"), str)


def test_nothing_asked_is_nothing_changed():
    """An empty request is not an error; the verb says so itself."""
    assert coerce_view({}) == {}


def test_coerced_values_round_trip_through_to_dict_and_from_dict():
    """What coerce_view hands back must be what the record stores, or a
    saved project would come back different from the tab it saved."""
    changes = {
        "style": "polyhedra" if "polyhedra" in styles.names()
        else styles.names()[-1],
        "show_rings": "true",
        "ring_max_size": "10",
        "color_by": "coordination",
        "color_map": "plasma",
        "color_range": [1, 6],
        "label_mode": "element",
        "projection": "orthographic",
        "boundary": "bonded",
        "pore_spheres": "all",
        "background": "slate",
        "topology_color": [1, 2, 3],
        "range_a": [0, 2],
        "range_b": ["-0.5", "1.5"],
        "polyhedron_centres": ["Ti"],
        "polyhedron_pairs_off": ["O-Ti"],
        "element_colors": {"O": [0, 0, 255]},
        "element_radii": {"Fe": 0.9},
        "ring_colors": {"5": [10, 20, 30]},
        "atom_scale": "1.25",
    }
    cleaned = coerce_view(changes)
    assert isinstance(cleaned, dict), cleaned
    settings = dataclasses.replace(ViewSettings(), **cleaned)
    back = ViewSettings.from_dict(settings.to_dict())
    assert back == settings
    for key, value in cleaned.items():
        assert getattr(back, key) == value, key


def test_a_background_given_by_hand_stops_following_the_theme():
    """A colour chosen by hand is never overwritten: left following
    the theme, the next light-to-dark switch would paint over the
    background the assistant was asked for, as View > Background's
    own colours already know."""
    assert coerce_view({"background": "slate"})[
        "background_follows_theme"] is False
    # Said outright, both together, the request is taken as it is.
    assert coerce_view({"background": "slate",
                        "background_follows_theme": True})[
        "background_follows_theme"] is True
    assert "background_follows_theme" not in coerce_view(
        {"show_rings": True})
