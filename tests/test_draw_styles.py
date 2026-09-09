"""The two report styles: the pictures a paper wants.

*Ellipsoid plot (PLATON)* is the drawing every structure report is
checked in -- pale outlined atoms, thin dark bonds, no highlight -- and
*Cartoon* is flat colour inside an outline, which exists so that the
SVG export is circles and strokes rather than a hundred radial
gradients.  Both of them are still records in
:mod:`xtalapp.viewport.styles`; what they cost is an outline, and an
outline round an instanced glyph is a second glyph.

So the claims worth pinning are in three places, and the tests follow
them: the scene model carries the style's decisions as plain fields,
the SVG exporter reads those fields and nothing else, and the renderer
draws ink where the exporter says there is ink.
"""

import xml.etree.ElementTree as ET

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core.site import Site
from xtalapp.viewport import styles
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.svg_export import Projection, render_svg
from xtalapp.viewport.view_settings import ViewSettings

SIZE = (400, 300)


def a_molecule(**kwargs) -> Structure:
    """Three atoms of three elements, far enough from the cell edge
    that a display range cannot double any of them."""
    return Structure(
        lattice=Lattice.cubic(14.0),
        sites=[Site("C", [0.35, 0.50, 0.50], **kwargs),
               Site("O", [0.46, 0.50, 0.50], **kwargs),
               Site("N", [0.29, 0.60, 0.50], **kwargs)],
        space_group="P1")


def refined() -> Structure:
    """The same molecule with one atom refined anisotropically and the
    others not -- which is what decides who gets principal sections."""
    return Structure(
        lattice=Lattice.cubic(14.0),
        sites=[Site("C", [0.35, 0.50, 0.50],
                    u_aniso=(0.030, 0.020, 0.020, 0.004, 0.0, 0.0)),
               Site("O", [0.46, 0.50, 0.50], u_iso=0.03),
               Site("N", [0.29, 0.60, 0.50])],
        space_group="P1")


def fitted(model) -> Projection:
    """A projection that puts the whole model on the canvas."""
    points = np.asarray(model.positions, float).reshape(-1, 3)
    span = max(float(np.ptp(points, axis=0).max()), 1.0) * 2.0
    matrix = np.diag([2.0 / span, 2.0 / span, -2.0 / span, 1.0])
    return Projection(matrix=matrix, right=np.array([1.0, 0.0, 0.0]),
                      size=SIZE, direction=np.array([0.0, 0.0, -1.0]))


def drawn(structure, style, **kwargs):
    return build_scene(structure,
                       ViewSettings(style=style, show_cell=False,
                                    **kwargs))


def markup(model) -> ET.Element:
    return ET.fromstring(render_svg(model, fitted(model)))


def by_class(root, name):
    return [e for e in root.iter() if e.get("class") == name]


# ==================================================== what a style says

def test_a_report_style_pales_the_atoms_and_inks_the_bonds():
    """PLATON's picture is ink on paper: the atoms are tinted back so
    a black outline reads on them, and the bonds stop being two-tone
    because a report figure does not colour a bond by its ends."""
    plain = drawn(a_molecule(), "ball_stick")
    report = drawn(a_molecule(), "platon")
    assert np.all(report.colors >= plain.colors)
    assert np.any(report.colors > plain.colors)
    ink = styles.get("platon").outline_color
    assert {tuple(c) for c in report.bond_colors} == {tuple(ink)}
    assert report.bond_radius < plain.bond_radius


def test_the_palette_the_user_set_still_shows_through_the_tint():
    """A tint is the style speaking and an element colour is the user
    speaking, in that order -- an element recoloured in the
    preferences has to stay recognisable in a report figure, not be
    replaced by the one it would have had."""
    settings = ViewSettings(style="platon", show_cell=False,
                            element_colors={"C": (0, 0, 200)})
    model = build_scene(a_molecule(), settings)
    carbon = model.colors[0]
    assert carbon[2] > carbon[0] and carbon[2] > carbon[1]
    assert tuple(carbon) != (0, 0, 200)


def test_the_legend_names_the_colours_the_picture_uses():
    """A legend built from the palette under a style that tints it is
    telling the reader about colours that are nowhere on screen."""
    model = drawn(a_molecule(), "platon", show_legend=True)
    swatches = dict(model.legend)
    for i, element in enumerate(("C", "O", "N")):
        assert swatches[element] == tuple(int(c) for c in model.colors[i])


def test_only_the_two_report_styles_carry_ink():
    """Every style reads the same fields; the ones that came before
    these two ask for none of it, and a regression that turned
    outlines on everywhere would be invisible in any other test."""
    inked = {name for name in styles.names()
             if styles.get(name).outline}
    assert inked == {"platon", "cartoon"}
    assert not drawn(a_molecule(), "ball_stick").is_outlined
    assert drawn(a_molecule(), "cartoon").is_outlined


# =========================================================== the export

def test_a_cartoon_atom_exports_as_a_flat_circle_and_no_gradient():
    """The whole reason the cartoon style exists.  A lit atom is a
    circle filled with a radial gradient, and recolouring every carbon
    then means editing ``<defs>``; a flat one is a fill an illustrator
    can select by class and change in one go."""
    root = markup(drawn(a_molecule(), "cartoon"))
    circles = by_class(root, "atom")
    assert circles
    assert all(c.get("fill").startswith("#") for c in circles)
    assert not root.findall(".//{http://www.w3.org/2000/svg}defs")
    r, g, b = styles.get("cartoon").outline_color
    assert {c.get("stroke") for c in circles} == {f"#{r:02x}{g:02x}{b:02x}"}


def test_a_lit_style_still_exports_the_gradients_it_always_did():
    """The flat path is a branch, not a replacement."""
    model = drawn(a_molecule(), "ball_stick")
    assert "<radialGradient" in render_svg(model, fitted(model))


def test_every_bond_is_outlined_and_the_outline_is_underneath():
    """Outlined atoms floating on unoutlined sticks is not a cartoon.
    SVG has no z-buffer, so "underneath" is "written first" -- the
    outline is emitted at its bond's own depth and the sort is
    stable."""
    model = drawn(a_molecule(), "cartoon")
    root = markup(model)
    order = [e.get("id") for e in root]
    outlines = by_class(root, "outline")
    assert len(outlines) == len(by_class(root, "bond"))
    for element in outlines:
        name = element.get("id")
        assert order.index(name) < order.index(name[len("outline-"):])


def test_an_ellipsoid_plot_exports_the_sections_it_draws_on_screen():
    """The furniture that tells a sphere from an ellipsoid seen down
    its long axis.  On the measured atom only: three arcs on an atom
    whose orientation was never refined draw three directions nobody
    measured."""
    model = drawn(refined(), "platon")
    sections = by_class(markup(model), "ellipsoid-section")
    assert len(sections) == 3
    assert all(e.get("fill") == "none" for e in sections)
    assert len(model.octant_atoms) == 1


def test_turning_the_octants_off_takes_the_sections_out_of_the_file():
    """The same switch the viewport obeys, and the export is the
    picture on the screen or it is a second opinion about it."""
    model = drawn(refined(), "platon", ellipsoid_octants=False)
    assert not by_class(markup(model), "ellipsoid-section")


# ========================================================= the renderer

vtk_scene = pytest.importorskip("xtalapp.viewport.vtk_scene")

from tests.conftest import needs_offscreen_gl  # noqa: E402


@needs_offscreen_gl
def test_the_outline_is_one_glyph_over_the_atoms_that_are_there():
    """No per-atom mesh anywhere: the ink is the same instanced sphere
    grown by the outline width, over the same points.  Its polydata is
    the whole of that claim."""
    scene = vtk_scene.VtkScene()
    model = drawn(a_molecule(), "cartoon")
    scene.set_model(model)
    assert scene.outline_actor.GetVisibility()
    assert scene.outline_bond_actor.GetVisibility()
    assert scene._outline_poly.GetNumberOfPoints() == model.n_atoms

    scene.set_model(drawn(a_molecule(), "ball_stick"))
    assert not scene.outline_actor.GetVisibility()
    assert not scene.outline_bond_actor.GetVisibility()


@needs_offscreen_gl
def test_hiding_the_atoms_does_not_take_the_ink_off_the_bonds():
    """The atom ink and the bond ink are two glyphs and are switched
    on separately, because *Show atoms* turns one of them off."""
    scene = vtk_scene.VtkScene()
    scene.set_model(drawn(a_molecule(), "cartoon", show_atoms=False))
    assert not scene.outline_actor.GetVisibility()
    assert scene.outline_bond_actor.GetVisibility()


@needs_offscreen_gl
def test_an_outlined_ellipsoid_is_ink_shaped_like_the_ellipsoid():
    """A round outline on an ellipsoid is a halo, not an outline.  The
    ink glyph takes the same three scales and the same rotation the
    atom did -- and goes back to a plain radius when the style
    does."""
    scene = vtk_scene.VtkScene()
    scene.set_model(drawn(refined(), "platon"))
    assert scene.outline_mapper.GetOrient()

    scene.set_model(drawn(a_molecule(), "cartoon"))
    assert not scene.outline_mapper.GetOrient()


@needs_offscreen_gl
def test_a_cartoon_atom_is_one_colour_from_edge_to_edge():
    """Flat means flat: a lit sphere spreads its colour over a
    gradient from the highlight to the terminator, and this one may
    not.  Counted as distinct colours inside the picture, which is
    what a vectoriser sees."""
    def shades(style):
        image = vtk_scene.render_to_array(
            drawn(a_molecule(), style), (300, 240),
            direction=(0.0, 0.0, -1.0))
        flat = image.reshape(-1, 3)
        inside = flat[np.any(flat < 250, axis=1)]
        return len(np.unique(inside, axis=0))

    assert shades("cartoon") < 0.1 * shades("ball_stick")


@needs_offscreen_gl
def test_the_ink_reaches_the_pixels_and_not_only_the_model():
    """An outline that exists in the scene model and nowhere on the
    screen is the failure this style would have shipped with: the ink
    is an inverted hull, and one culling flag the wrong way round
    hides it behind the atom it surrounds."""
    def inked(style):
        image = vtk_scene.render_to_array(
            drawn(a_molecule(), style), (300, 240),
            direction=(0.0, 0.0, -1.0))
        ink = np.array(styles.get("cartoon").outline_color)
        return float(np.all(np.abs(image.astype(int) - ink) < 10,
                            axis=2).mean())

    # Against ball and stick rather than against zero: the dark side
    # of a lit sphere passes through the ink colour on its way to
    # black, and a handful of those pixels is not an outline.
    assert inked("cartoon") > 10 * inked("ball_stick")
