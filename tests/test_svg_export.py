"""The SVG export, which is shapes rather than pixels.

``Export Image`` offers SVG so that the picture can be taken apart in
Illustrator -- recolour one atom, thicken the cell edges.  The first
attempt went through GL2PS and produced a PNG in an ``<svg>`` wrapper,
which satisfies none of that, so the thing these tests are really
guarding is that every drawn object is its own named element and that
no raster ever creeps back in.

:mod:`xtalapp.viewport.svg_export` reads a
:class:`~xtalapp.viewport.scene.SceneModel` and a
:class:`~xtalapp.viewport.svg_export.Projection` and imports neither
VTK nor Qt, so all of this runs with no window and no GL driver.
"""

import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from xtalapp.viewport import svg_export
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.svg_export import Projection, render_svg
from xtalapp.viewport.view_settings import ViewSettings

SIZE = (400, 300)
#: The world box the test projection maps onto the canvas.
EXTENT = 20.0


@pytest.fixture
def projection():
    """A parallel projection down -z, with arithmetic worth checking by
    hand: a point at the origin lands in the middle of the canvas and
    one Angstrom is ``width / EXTENT`` pixels across."""
    matrix = np.diag([2.0 / EXTENT, 2.0 / EXTENT, -2.0 / EXTENT, 1.0])
    return Projection(matrix=matrix, right=np.array([1.0, 0.0, 0.0]),
                      size=SIZE, direction=np.array([0.0, 0.0, -1.0]))


def parse(markup: str):
    return ET.fromstring(markup)


def by_class(root, name):
    return [e for e in root.iter()
            if e.get("class") == name]


def test_the_origin_lands_in_the_middle_of_the_canvas(projection):
    xy, _depth = projection.to_display([[0.0, 0.0, 0.0]])
    assert xy[0] == pytest.approx([SIZE[0] / 2, SIZE[1] / 2])


def test_y_runs_down_the_page(projection):
    """SVG counts from the top and clip space counts from the bottom;
    getting this backwards flips every picture."""
    xy, _depth = projection.to_display([[0.0, 5.0, 0.0]])
    assert xy[0][1] < SIZE[1] / 2


def test_a_radius_in_angstrom_becomes_a_radius_in_pixels(projection):
    radii = projection.radii_at([[0.0, 0.0, 0.0]], [1.0])
    assert radii[0] == pytest.approx(SIZE[0] / EXTENT)


def test_every_atom_is_its_own_named_circle(rutile):
    """The whole reason for the format: one object per atom, carrying
    the label the crystallographer knows it by."""
    from xtal.core import p1
    model = build_scene(rutile, ViewSettings())
    names = list(p1.expand(rutile).labels)
    root = parse(render_svg(model, _fitted(model), names=names))
    circles = by_class(root, "atom")
    assert len(circles) == model.n_atoms
    assert all(c.get("id") for c in circles)
    assert len({c.get("id") for c in circles}) == len(circles)
    assert any(names[0] in c.get("id") for c in circles)


def test_nothing_is_a_raster(rutile):
    """The regression that prompted the rewrite: GL2PS wrote the whole
    crystal as one embedded PNG, which is not editable artwork."""
    model = build_scene(rutile, ViewSettings())
    markup = render_svg(model, _fitted(model))
    assert "<image" not in markup
    assert "base64" not in markup


def test_bonds_and_cell_edges_are_separately_selectable(rutile):
    """"Thicken every cell edge" is one Select > Same away only if the
    edges are their own elements with their own class."""
    model = build_scene(rutile, ViewSettings())
    root = parse(render_svg(model, _fitted(model)))
    assert len(by_class(root, "cell")) == model.n_cell_lines
    assert by_class(root, "bond")
    assert all(e.get("id").startswith("cell-edge-")
               for e in by_class(root, "cell"))


def test_a_shared_gradient_per_element_and_not_per_atom(rutile):
    """A sphere is faked with a radial gradient, and one gradient per
    atom would be six hundred of them on a framework."""
    model = build_scene(rutile, ViewSettings())
    markup = render_svg(model, _fitted(model))
    gradients = re.findall(r'<radialGradient id="([^"]+)"', markup)
    assert len(gradients) == len(set(gradients))
    assert len(gradients) <= len(np.unique(model.colors, axis=0))


def test_the_nearer_atom_is_written_last(projection):
    """Painter's algorithm: SVG has no z-buffer, so what is drawn last
    is what is on top."""
    from xtalapp.viewport.scene import SceneModel
    model = SceneModel(
        positions=np.array([[0.0, 0.0, -5.0], [0.5, 0.0, 5.0]],
                           np.float32),
        radii=np.array([1.0, 1.0], np.float32),
        colors=np.array([[255, 0, 0], [0, 0, 255]], np.uint8),
        atom_index=np.array([0, 1]))
    markup = render_svg(model, projection)
    near = markup.index('id="atom-1"')
    far = markup.index('id="atom-0"')
    assert far < near


def test_every_bond_half_is_written_before_its_own_atom(projection):
    """The complaint this answers: a bond running towards the camera
    was painted at its *midpoint's* depth, which is nearer than the
    atom it starts at, so it was drawn over the sphere and every atom
    in the picture had sticks laid across its face.

    Two atoms, one of them well in front of the other, joined by a
    bond that therefore runs steeply out of the page.  Each half has
    to land behind its own atom and in front of the far one.
    """
    from xtalapp.viewport.scene import SceneModel
    near, far = [0.0, 0.0, 5.0], [0.0, 0.0, -5.0]
    middle = [0.0, 0.0, 0.0]
    model = SceneModel(
        positions=np.array([far, near], np.float32),
        radii=np.array([1.0, 1.0], np.float32),
        colors=np.array([[255, 0, 0], [0, 0, 255]], np.uint8),
        atom_index=np.array([0, 1]),
        bond_starts=np.array([far, near], np.float32),
        bond_ends=np.array([middle, middle], np.float32),
        bond_colors=np.array([[255, 0, 0], [0, 0, 255]], np.uint8))
    markup = render_svg(model, projection)
    order = [markup.index(f'id="{name}"') for name in
             ("bond-0", "atom-0", "bond-1", "atom-1")]
    assert order == sorted(order)


def test_the_background_is_a_rectangle_that_transparency_drops(rutile):
    """A transparent SVG is one with nothing behind the crystal, and
    the background being its own element is what makes it removable by
    hand as well."""
    model = build_scene(rutile, ViewSettings())
    opaque = render_svg(model, _fitted(model))
    clear = render_svg(model, _fitted(model), transparent=True)
    assert 'id="background"' in opaque
    assert 'id="background"' not in clear


def test_an_ellipsoid_is_drawn_as_a_tilted_ellipse(rutile):
    """ORTEP atoms are not spheres and must not be exported as
    circles: the tensor projects to an ellipse, and its tilt is the
    part a reader is looking at."""
    model = build_scene(rutile, ViewSettings(style="ortep"))
    assert len(model.atom_tensors) == model.n_atoms
    root = parse(render_svg(model, _fitted(model)))
    ellipses = [e for e in root.iter() if e.tag.endswith("ellipse")]
    assert ellipses
    assert all("rotate" in e.get("transform") for e in ellipses)


def test_polyhedron_faces_are_polygons_shaded_by_their_tilt(quartz):
    """Flat fills make a hull read as a blob; the renderer lights it,
    so the export shades each face by how square it is to the eye."""
    model = build_scene(quartz, ViewSettings(style="polyhedra"))
    assert model.n_polyhedron_faces
    root = parse(render_svg(model, _fitted(model)))
    faces = by_class(root, "polyhedron")
    assert len(faces) == model.n_polyhedron_faces
    assert len({f.get("fill") for f in faces}) > 1


def test_an_occupancy_pie_reaches_the_vector_export():
    """The export is the version that goes in a paper, so a style whose
    whole subject is disorder must not quietly become a plain sphere in
    it."""
    from xtal import Lattice, Structure
    from xtal.core.site import Site
    structure = Structure(
        lattice=Lattice.cubic(6.0),
        sites=[Site("Fe", [0.0, 0.0, 0.0], occupancy=0.5),
               Site("O", [0.0, 0.0, 0.0], occupancy=0.5)],
        space_group="P1")
    model = build_scene(structure,
                        ViewSettings(style="ball_stick_occupancy",
                                     show_cell=False))
    assert model.n_pie_faces
    wedges = by_class(parse(render_svg(model, _fitted(model))), "pie")
    assert len(wedges) == model.n_pie_faces
    assert len({w.get("fill") for w in wedges}) > 1


def test_a_selected_atom_gets_a_halo_behind_it(rutile):
    """The viewport marks a selection with a translucent halo rather
    than by recolouring, and the export has to say the same thing."""
    from xtal.core.selection import Selection
    model = build_scene(rutile, ViewSettings(),
                        selection=Selection(atoms={0}))
    root = parse(render_svg(model, _fitted(model)))
    halos = by_class(root, "selection")
    assert halos
    markup = render_svg(model, _fitted(model))
    assert markup.index('id="halo-') < markup.index('id="atom-0')


def test_labels_come_out_as_text_and_not_as_outlines(rutile):
    """Editable means the label can be retyped, which needs a
    ``<text>`` element and a real font family."""
    model = build_scene(rutile, ViewSettings(label_mode="label"))
    assert model.labels
    root = parse(render_svg(model, _fitted(model)))
    texts = by_class(root, "label")
    assert len(texts) == len(model.labels)
    assert all(t.get("font-family") for t in texts)


def test_an_empty_scene_is_still_a_valid_document(projection):
    from xtalapp.viewport.scene import SceneModel
    root = parse(render_svg(SceneModel(), projection))
    assert root.tag.endswith("svg")
    assert root.get("viewBox") == f"0 0 {SIZE[0]} {SIZE[1]}"


def test_a_label_with_an_ampersand_does_not_break_the_file(projection):
    """Labels come off a CIF and a CIF can hold anything."""
    from xtalapp.viewport.scene import SceneModel
    model = SceneModel(labels=(((0.0, 0.0, 0.0), "A&B<1>"),))
    root = parse(render_svg(model, projection))
    assert [e.text for e in by_class(root, "label")] == ["A&B<1>"]


def test_write_svg_leaves_the_suffix_alone(rutile, tmp_path):
    """GL2PS appended its own extension and wrote ``figure.svg.svg``."""
    model = build_scene(rutile, ViewSettings())
    path = svg_export.write_svg(model, _fitted(model),
                                tmp_path / "figure.svg")
    assert path == tmp_path / "figure.svg"
    assert not (tmp_path / "figure.svg.svg").exists()
    assert path.read_text().startswith("<?xml")


def _fitted(model) -> Projection:
    """A projection that puts the whole model on the canvas.

    Not a camera: the scale only has to be sane enough that the shapes
    land inside the viewBox, because what is under test is the markup
    and not where VTK would have put it.
    """
    points = np.asarray(model.positions, float).reshape(-1, 3)
    if not len(points):
        span = EXTENT
    else:
        span = max(float(np.ptp(points, axis=0).max()), 1.0) * 1.5
    matrix = np.diag([2.0 / span, 2.0 / span, -2.0 / span, 1.0])
    return Projection(matrix=matrix, right=np.array([1.0, 0.0, 0.0]),
                      size=SIZE, direction=np.array([0.0, 0.0, -1.0]))


def test_the_pores_are_circles_and_lines(rutile):
    """A flat circle and not the atoms' radial gradient: a pore is a
    hole, and a shaded ball reads as one more atom."""
    from xtal.analysis.porosity import PoreNetwork
    nodes = np.array([[0.5, 0.5, 0.5], [0.25, 0.5, 0.5]])
    network = PoreNetwork(nodes=nodes, radii=np.array([3.0, 1.0]),
                          edge_starts=nodes[:1], edge_ends=nodes[1:],
                          probe=1.86)
    model = build_scene(rutile, ViewSettings(), pores=network)
    root = parse(render_svg(model, _fitted(model)))

    circles = by_class(root, "pore")
    assert len(circles) == 1
    assert circles[0].get("fill-opacity")
    assert "url(" not in circles[0].get("fill")
    assert len(by_class(root, "pore-edge")) == 1
