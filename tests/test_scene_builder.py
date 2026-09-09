"""The render model: what actually gets drawn, asserted without a GPU."""

import math

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1
from xtalapp.viewport.builder import build_scene, selection_flags
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


# ---------------------------------------------------------- selection

def test_selected_atoms_are_flagged(rutile):
    from xtal.core import p1
    from xtal.core.selection import Selection

    selection = Selection()
    selection.set_atoms([0])                # one Ti of the P1 cell
    scene = build_scene(rutile, ViewSettings(), selection=selection)

    assert scene.n_selected > 0
    cell = p1.expand(rutile)
    for i in range(scene.n_atoms):
        expected = int(scene.atom_index[i]) == 0
        assert bool(scene.selected[i]) is expected
    assert all(cell.elements[scene.atom_index[i]] == "Ti"
               for i in np.flatnonzero(scene.selected))


def test_no_selection_flags_nothing(rutile):
    scene = build_scene(rutile, ViewSettings())
    assert scene.n_selected == 0
    assert not scene.selected_bonds.any()


def test_selected_bonds_are_flagged(rutile):
    from xtal.core import bonding
    from xtal.core.selection import Selection

    graph = bonding.graph(rutile)
    selection = Selection()
    selection.bonds = {graph.bonds[0].key()}
    scene = build_scene(rutile, ViewSettings(), selection=selection)
    assert scene.selected_bonds.any()
    assert scene.selected_bonds.sum() < scene.n_bond_halves


def test_selection_flags_follow_the_display_range(rutile):
    """Selecting one atom of the P1 cell lights up every image of it
    that is drawn, which is what makes a 2x2x2 view legible."""
    from xtal.core.selection import Selection

    selection = Selection()
    selection.set_atoms([0])
    settings = ViewSettings()
    one = build_scene(rutile, settings, selection=selection).n_selected
    settings.set_cells(2, 2, 2)
    many = build_scene(rutile, settings, selection=selection).n_selected
    assert many > one


# --------------------------------------------------------- fast paths

def test_bond_halves_know_which_bond_they_draw(quartz):
    """Provenance, not geometry: a click on a bond has to name the two
    atoms and the lattice translation it really joins."""
    from xtal.core import bonding
    from xtalapp.viewport.builder import build_scene

    scene = build_scene(quartz, ViewSettings())
    keys = {b.key() for b in bonding.graph(quartz).bonds}
    assert len(scene.bond_keys) == scene.n_bond_halves
    for half in range(scene.n_bond_halves):
        assert scene.bond_key(half) in keys
    # the two halves of one bond name the same bond
    assert scene.bond_key(0) == scene.bond_key(1)


def test_bond_keys_survive_hidden_atoms(rutile):
    """Wireframe draws no atom geometry, so nothing can be recovered
    from the atom arrays -- the bond keys still have to be right."""
    scene = build_scene(rutile, ViewSettings(style="wireframe"))
    assert scene.n_atoms == 0
    assert len(scene.bond_keys) == scene.n_bond_halves > 0
    assert scene.bond_key(0)[0] >= 0


def test_boundary_completes_a_chain_at_both_ends():
    """An atom bonded to its own periodic image is a chain running
    through the picture.  With boundary='bonded' it has to be completed
    at *both* ends: stopping dead at one edge and continuing at the
    other is worse than either, because the picture then implies an
    asymmetry the crystal does not have."""
    chain = Structure.from_arrays(
        Lattice.orthorhombic(1.45, 9.0, 9.0), ["C"],
        [[0.0, 0.5, 0.5]], space_group="P1")

    inside = build_scene(chain, ViewSettings(boundary="in_range"))
    assert inside.n_atoms == 2                  # x = 0 and x = 1
    assert inside.n_bond_halves == 2            # one bond between them

    bonded = build_scene(chain, ViewSettings(boundary="bonded"))
    x = np.sort(chain.lattice.to_frac(bonded.positions)[:, 0])
    assert np.allclose(x, [-1.0, 0.0, 1.0, 2.0])
    assert bonded.n_bond_halves == 6            # three links, six halves


def test_selection_flags_match_a_full_rebuild(rutile):
    """The viewport reuses a scene and swaps the highlight flags in.
    It must land on exactly what rebuilding would have produced."""
    from xtal.core import bonding
    from xtal.core.selection import Selection
    from xtalapp.viewport.builder import selection_flags

    selection = Selection()
    selection.set_atoms([0, 3])
    selection.bonds = {bonding.graph(rutile).bonds[0].key()}

    settings = ViewSettings()
    plain = build_scene(rutile, settings)
    rebuilt = build_scene(rutile, settings, selection=selection)
    atoms, bonds, net = selection_flags(plain, selection)

    assert np.array_equal(atoms, rebuilt.selected)
    assert np.array_equal(bonds, rebuilt.selected_bonds)
    assert np.array_equal(net, rebuilt.topology_selected)
    assert bonds.any()


def test_a_large_cell_builds_without_scanning_every_pair(quartz):
    """Matching bonds to endpoints by scanning every drawn atom is
    quadratic, and a multi-cell view of a real structure is where that
    stops being academic.  Eight cells must cost about eight times one,
    not sixty-four."""
    import time

    settings = ViewSettings()
    build_scene(quartz, settings)                   # warm the caches

    def elapsed(cells):
        settings.set_cells(*cells)
        start = time.perf_counter()
        build_scene(quartz, settings)
        return time.perf_counter() - start

    one = elapsed((1, 1, 1))
    eight = elapsed((2, 2, 2))
    assert eight < 40 * max(one, 1e-4)


# --------------------------------------------------- polyhedra, legend

def test_polyhedra_are_convex_hulls_of_the_coordination_sphere(rutile):
    """Rutile is edge-sharing TiO6: every Ti drawn gets an octahedron,
    and an octahedron is eight triangles."""
    scene = build_scene(rutile, ViewSettings(style="polyhedra"))
    centres = sum(1 for i in range(scene.n_atoms)
                  if scene.atom_index[i] in (0, 1))
    assert scene.n_polyhedron_faces == 8 * centres
    assert len(scene.polyhedron_points) == 6 * centres
    assert scene.polyhedron_faces.max() < len(scene.polyhedron_points)
    assert len(scene.polyhedron_colors) == scene.n_polyhedron_faces


def test_a_polyhedron_uses_the_neighbours_the_bonds_point_at(rutile):
    """Four of an octahedron's six vertices are in the next cell along.
    Taking the copy inside the cell instead gives a shape that is not
    the coordination sphere of anything -- and one that is far too
    big."""
    scene = build_scene(rutile, ViewSettings(style="polyhedra"))
    hull = scene.polyhedron_points[:6]
    centre = hull.mean(axis=0)
    spread = np.linalg.norm(hull - centre, axis=1)
    assert spread.max() < 2.1                   # Ti-O is about 1.97 A
    assert spread.min() > 1.8


def test_only_the_named_elements_get_polyhedra(rutile):
    everything = build_scene(rutile, ViewSettings(style="polyhedra"))
    titanium = build_scene(rutile, ViewSettings(
        style="polyhedra", polyhedron_centres=("Ti",)))
    oxygen = build_scene(rutile, ViewSettings(
        style="polyhedra", polyhedron_centres=("O",)))
    assert titanium.n_polyhedron_faces == everything.n_polyhedron_faces
    assert oxygen.n_polyhedron_faces == 0       # O is 3-coordinate


def test_polyhedra_need_enough_vertices(quartz):
    """Silicon is tetrahedral, so four is the useful floor; asking for
    more leaves the tetrahedra out."""
    four = build_scene(quartz, ViewSettings(style="polyhedra"))
    six = build_scene(quartz, ViewSettings(
        style="polyhedra", polyhedron_min_vertices=6))
    assert four.n_polyhedron_faces == 4 * (four.n_polyhedron_faces // 4)
    assert four.n_polyhedron_faces > 0
    assert six.n_polyhedron_faces == 0


def test_other_styles_draw_no_polyhedra(rutile):
    for name in ("ball_stick", "stick", "wireframe", "spacefill"):
        scene = build_scene(rutile, ViewSettings(style=name))
        assert scene.n_polyhedron_faces == 0
        assert len(scene.polyhedron_points) == 0


def test_polyhedra_follow_the_display_range(rutile):
    settings = ViewSettings(style="polyhedra")
    one = build_scene(rutile, settings).n_polyhedron_faces
    settings.set_cells(2, 2, 2)
    many = build_scene(rutile, settings).n_polyhedron_faces
    assert many > one


def test_the_legend_lists_what_is_drawn(rutile):
    assert build_scene(rutile, ViewSettings()).legend == ()

    scene = build_scene(rutile, ViewSettings(show_legend=True))
    assert [element for element, _color in scene.legend] == ["O", "Ti"]

    from xtal.core import elements as el
    assert dict(scene.legend)["Ti"] == el.color("Ti")


def test_the_legend_follows_a_colour_override(rutile):
    settings = ViewSettings(show_legend=True)
    settings.element_colors["Ti"] = (1, 2, 3)
    assert dict(build_scene(rutile, settings).legend)["Ti"] == (1, 2, 3)


def test_the_legend_does_not_list_what_the_range_cut_away(rutile):
    """A legend for an element that is not in the picture describes a
    different picture."""
    settings = ViewSettings(show_legend=True, show_atoms=True)
    settings.element_radii["Ti"] = 0.5
    full = build_scene(rutile, settings)
    assert len(full.legend) == 2

    # A slice that holds the oxygen at (0.305, 0.305, 0) and not the
    # titanium at the origin.
    narrow = ViewSettings(show_legend=True)
    narrow.range_a = narrow.range_b = (0.28, 0.33)
    narrow.range_c = (0.0, 0.1)
    only_oxygen = build_scene(rutile, narrow)
    assert [e for e, _c in only_oxygen.legend] == ["O"]


# ==================================================== polyhedra and sticks

def test_the_polyhedral_style_draws_no_bonds(rutile):
    scene = build_scene(rutile, ViewSettings(style="polyhedra"))
    assert scene.n_polyhedron_faces > 0
    assert scene.n_bond_halves == 0


def test_a_polyhedron_never_has_a_cage_of_sticks_inside_it(rutile):
    """The mixed style draws the bonds a hull did not already draw.
    In rutile every bond is an edge of a titanium octahedron, so the
    answer is none of them -- which is the case that would look worst
    if it were got wrong."""
    scene = build_scene(rutile, ViewSettings(style="polyhedra_stick"))
    assert scene.n_polyhedron_faces > 0
    assert scene.n_bond_halves == 0


def test_the_mixed_style_keeps_the_bonds_no_hull_took():
    """An MOF is the case it exists for: polyhedra on the metal nodes,
    tubes on the linker, and both in the same picture."""
    lattice = Lattice.cubic(14.0)
    # A zinc with four oxygens around it, and a C-C fragment off on its
    # own that no polyhedron can possibly claim.
    d = 1.95 / math.sqrt(3.0)
    cart = [[0, 0, 0], [d, d, d], [d, -d, -d], [-d, d, -d], [-d, -d, d],
            [5.0, 5.0, 5.0], [6.5, 5.0, 5.0]]
    structure = Structure.from_arrays(
        lattice, ["Zn", "O", "O", "O", "O", "C", "C"],
        lattice.to_frac(np.array(cart, dtype=float)), space_group="P1")

    hulls = build_scene(structure, ViewSettings(style="polyhedra_stick"))
    assert hulls.n_polyhedron_faces > 0         # the ZnO4 tetrahedron
    assert hulls.n_bond_halves > 0              # and the C-C bond
    keys = {hulls.bond_key(k) for k in range(hulls.n_bond_halves)}
    assert all(0 not in (i, j) for i, j, _image in keys)  # no Zn-O


def _methane_at(origin) -> tuple[list, list]:
    """CH4, as elements and cartesian coordinates about ``origin``."""
    d = 1.09 / math.sqrt(3.0)
    offsets = [[0, 0, 0], [d, d, d], [d, -d, -d], [-d, d, -d],
               [-d, -d, d]]
    return (["C", "H", "H", "H", "H"],
            [[o + p for o, p in zip(origin, offset, strict=True)]
             for offset in offsets])


def test_a_four_coordinate_carbon_is_not_a_polyhedron_node():
    """Which is why the mixed style takes only the metals when the user
    has named no centres: an MOF linker has sp3 carbons in it, and
    drawing those as tetrahedra is the picture this style avoids.

    Tested against a structure that *has* a metal in it, because that
    is the only condition under which the rule applies -- with no metal
    anywhere the style falls back rather than draw nothing, which is
    the test below."""
    lattice = Lattice.cubic(20.0)
    d = 1.95 / math.sqrt(3.0)
    elements = ["Zn", "O", "O", "O", "O"]
    cart = [[10, 10, 10], [10 + d, 10 + d, 10 + d],
            [10 + d, 10 - d, 10 - d], [10 - d, 10 + d, 10 - d],
            [10 - d, 10 - d, 10 + d]]
    carbon, methane = _methane_at([2.0, 2.0, 2.0])
    elements += carbon
    cart += methane
    structure = Structure.from_arrays(
        lattice, elements,
        lattice.to_frac(np.array(cart, dtype=float)), space_group="P1")

    everything = build_scene(
        structure, ViewSettings(style="polyhedra")).n_polyhedron_faces
    metals_only = build_scene(
        structure,
        ViewSettings(style="polyhedra_stick")).n_polyhedron_faces
    assert metals_only > 0                  # the ZnO4 tetrahedron
    assert metals_only < everything         # and not the CH4 one


def test_the_mixed_style_falls_back_when_there_is_no_metal_at_all():
    """The rule above is right about an MOF and wrong about everything
    with no metal in it, and it takes the whole structure to see that:
    asked one atom at a time, "is this a metal?" says no for every atom
    of quartz, of a borate, and of a topology net drawn as hydrogen and
    helium.  *Polyhedra and sticks* then draws none at all, which for a
    silicate means losing the SiO4 tetrahedron -- the polyhedral
    picture there is.

    A style whose name promises polyhedra and delivers none is broken
    rather than restrained, so with no metal present it draws what
    *Polyhedra* would have.  Every structure in ``resources/samples``
    has a metal, so this never changes any of them."""
    lattice = Lattice.cubic(14.0)
    elements, cart = _methane_at([7.0, 7.0, 7.0])
    methane = Structure.from_arrays(
        lattice, elements,
        lattice.to_frac(np.array(cart, dtype=float)), space_group="P1")
    assert build_scene(
        methane, ViewSettings(style="polyhedra")).n_polyhedron_faces > 0
    assert build_scene(
        methane, ViewSettings(style="polyhedra_stick")
    ).n_polyhedron_faces > 0


def test_naming_a_centre_still_overrides_the_style():
    """The fallback is what happens when nobody has said anything.  A
    user who names centres is still the last word, including when what
    they name gets no hull."""
    lattice = Lattice.cubic(14.0)
    elements, cart = _methane_at([7.0, 7.0, 7.0])
    methane = Structure.from_arrays(
        lattice, elements,
        lattice.to_frac(np.array(cart, dtype=float)), space_group="P1")
    assert build_scene(methane, ViewSettings(
        style="polyhedra_stick",
        polyhedron_centres=("H",))).n_polyhedron_faces == 0


def test_naming_the_centres_by_hand_beats_the_style(rutile):
    settings = ViewSettings(style="polyhedra_stick")
    settings.polyhedron_centres = ("O",)
    scene = build_scene(rutile, settings)
    assert scene.n_polyhedron_faces == 0        # O has only 3 partners


def test_the_picture_follows_a_move_in_a_symmetric_cell(rutile):
    """The bug where applying a Move left the picture where it was.

    Almost any move in a symmetric structure takes a site off its
    special position, which splits its orbit and gives the cell more
    atoms than it had.  Building the scene then raised rather than
    returning one -- and it raised inside the viewport's redraw, so the
    structure had changed, the exception went to the console, and the
    atoms on screen stayed exactly where they were.
    """
    before = build_scene(rutile, ViewSettings())
    rutile.set_frac(1, [0.32, 0.30, 0.01])

    after = build_scene(rutile, ViewSettings())
    assert after.n_atoms > before.n_atoms       # the orbit split
    assert not np.array_equal(after.positions[:before.n_atoms],
                              before.positions)


def test_the_picture_follows_a_move_with_bond_orders_drawn(rutile):
    """The same move with the orders switched on -- which is the
    default, and is where the failure actually came from."""
    settings = ViewSettings(show_bond_orders=True)
    build_scene(rutile, settings)
    rutile.set_frac(1, [0.32, 0.30, 0.01])
    scene = build_scene(rutile, settings)
    assert len(scene.bond_orders) == scene.n_bond_halves


# ======================================================== half bonds

def a_chain(spacing: float = 1.45) -> Structure:
    """One carbon bonded to its own periodic image: a chain running
    straight through the picture and out of both sides."""
    return Structure.from_arrays(
        Lattice.orthorhombic(spacing, 9.0, 9.0), ["C"],
        [[0.0, 0.5, 0.5]], space_group="P1")


def test_a_half_bond_draws_no_atom_on_its_far_end():
    """The whole point of the third boundary answer.  'bonded' says
    what is out there by drawing it, which hangs a halo of spheres
    round a picture of one cell; 'half' says it by stopping."""
    chain = a_chain()
    half = build_scene(chain, ViewSettings(boundary="half"))
    bonded = build_scene(chain, ViewSettings(boundary="bonded"))
    inside = build_scene(chain, ViewSettings(boundary="in_range"))

    assert half.n_atoms == inside.n_atoms == 2
    assert bonded.n_atoms == 4
    assert half.n_bond_halves == 4      # one whole bond plus two stubs


def test_a_half_bond_stops_at_the_midpoint():
    """Half of a bond and not all of it: a stub that ran the whole way
    would draw a bond to an atom that is not in the picture."""
    chain = a_chain()
    scene = build_scene(chain, ViewSettings(boundary="half"))
    x_start = chain.lattice.to_frac(scene.bond_starts)[:, 0]
    x_end = chain.lattice.to_frac(scene.bond_ends)[:, 0]
    stubs = (x_end < -1e-6) | (x_end > 1 + 1e-6)
    assert stubs.sum() == 2
    assert sorted(np.round(x_end[stubs], 6)) == [-0.5, 1.5]
    # each leaves from an atom that really is drawn
    assert sorted(np.round(x_start[stubs], 6)) == [0.0, 1.0]


def test_a_half_bond_takes_its_own_atom_s_colour(dry_ice):
    """A stub is one half and there is no second half to take the
    other colour, so it must be the near atom's -- an oxygen stub in
    carbon grey names the wrong element."""
    scene = build_scene(dry_ice, ViewSettings(boundary="half"))
    from xtal.core import elements as el
    cell = p1.expand(dry_ice)
    for k in range(scene.n_bond_halves):
        i, j, _image = scene.bond_key(k)
        near = {tuple(el.color(cell.elements[i])),
                tuple(el.color(cell.elements[j]))}
        assert tuple(scene.bond_colors[k]) in near


def test_a_half_bond_can_still_be_named_and_selected(dry_ice):
    """It is a real bond of the cell drawn short, not a decoration, so
    clicking it has to give the bond back."""
    from xtal.core.selection import Selection
    scene = build_scene(dry_ice, ViewSettings(boundary="half"))
    assert len(scene.bond_keys) == scene.n_bond_halves
    selection = Selection()
    selection.bonds = {scene.bond_key(scene.n_bond_halves - 1)}
    _atoms, bonds, _net = selection_flags(scene, selection)
    assert bonds.any()


def test_half_bonds_carry_orders_like_any_other_half(dry_ice):
    """A double bond that leaves the picture is still double, and the
    order arrays are indexed by half -- a stub missing from them
    silently shifts every order after it onto the wrong bond."""
    settings = ViewSettings(boundary="half", show_bond_orders=True)
    scene = build_scene(dry_ice, settings)
    assert len(scene.bond_orders) == scene.n_bond_halves
    assert len(scene.bond_offsets) == scene.n_bond_halves


def test_the_other_two_boundaries_draw_no_stubs(rutile):
    """A change to what 'half' does must not change what the settings
    that were there before it do."""
    for name in ("in_range", "bonded"):
        settings = ViewSettings(boundary=name)
        scene = build_scene(rutile, settings)
        assert scene.n_bond_halves % 2 == 0
        for k in range(0, scene.n_bond_halves, 2):
            assert np.allclose(scene.bond_ends[k],
                               scene.bond_ends[k + 1])


# ======================================================== the depth fade
#
# The arithmetic only.  What it looks like on screen is in
# tests/test_vtk_render.py, which needs a GL driver; this is the same
# function the shader is a transcription of, and it needs nothing.

def test_the_fade_is_nothing_in_front_and_everything_behind():
    from xtalapp.viewport.scene import cue_fraction
    at = cue_fraction([0.0, 5.0, 10.0], near=0.0, far=10.0,
                      strength=1.0)
    assert at[0] == pytest.approx(0.0)
    assert at[1] == pytest.approx(0.5)
    assert at[2] == pytest.approx(1.0)


def test_nothing_nearer_than_the_start_fades_at_all():
    """What the start control buys: the front of a slab stays crisp
    and the fade is spent on the back of it."""
    from xtalapp.viewport.scene import cue_fraction
    at = cue_fraction([0.0, 4.0, 5.0, 10.0], near=5.0, far=10.0,
                      strength=1.0)
    assert list(at[:3]) == [0.0, 0.0, 0.0]
    assert at[3] == pytest.approx(1.0)


def test_the_gradient_bends_the_ramp_without_moving_its_ends():
    """A gradient above 1 holds the picture clear and then drops it;
    below 1 it fades at once and levels off.  Both have to leave the
    two ends where a straight line put them, or the control is a
    strength control wearing a different name."""
    from xtalapp.viewport.scene import cue_fraction
    args = dict(near=0.0, far=10.0, strength=1.0)
    middle = [5.0]
    straight = cue_fraction(middle, gradient=1.0, **args)[0]
    steep = cue_fraction(middle, gradient=3.0, **args)[0]
    soft = cue_fraction(middle, gradient=1 / 3, **args)[0]
    assert steep < straight < soft
    for gradient in (0.25, 1.0, 4.0):
        ends = cue_fraction([0.0, 10.0], gradient=gradient, **args)
        assert ends[0] == pytest.approx(0.0)
        assert ends[1] == pytest.approx(1.0)


def test_a_fade_goes_towards_the_background_it_is_given():
    """Towards *the background*, not towards white: on a black one a
    distant atom gets darker."""
    from xtalapp.viewport.scene import fade_towards
    colors = np.array([[200, 100, 50]] * 3, np.uint8)
    pale = fade_towards(colors, (255, 255, 255), [0.0, 0.5, 1.0])
    assert list(pale[0]) == [200, 100, 50]
    assert list(pale[2]) == [255, 255, 255]
    dark = fade_towards(colors, (0, 0, 0), [0.0, 1.0, 1.0])
    assert list(dark[1]) == [0, 0, 0]
