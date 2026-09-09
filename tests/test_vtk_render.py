"""The VTK render path, exercised offscreen.

These tests draw a structure into an offscreen buffer and assert on the
pixels.  A file-size check would pass on a blank image; "there are red
pixels where the oxygen is" would not.
"""

from pathlib import Path

import numpy as np
import pytest

from tests.conftest import needs_offscreen_gl

vtk_scene = pytest.importorskip("xtalapp.viewport.vtk_scene")

# Rendering needs a GL driver, and where there is none VTK does not
# raise -- it takes the interpreter with it.  See conftest.
pytestmark = needs_offscreen_gl

from xtalapp.viewport.builder import build_scene  # noqa: E402
from xtalapp.viewport.view_settings import ViewSettings  # noqa: E402

SIZE = (240, 180)


def fraction_of(image, predicate) -> float:
    mask = predicate(image.astype(int))
    return float(mask.sum()) / (image.shape[0] * image.shape[1])


def is_red(image):
    return ((image[:, :, 0] > 140) & (image[:, :, 1] < 90)
            & (image[:, :, 2] < 90))


def is_background(image, color=(255, 255, 255)):
    return np.all(np.abs(image - np.array(color)) < 8, axis=2)


def test_a_structure_actually_draws(rutile):
    image = vtk_scene.render_to_array(
        build_scene(rutile, ViewSettings()), SIZE)
    assert image.shape == (SIZE[1], SIZE[0], 3)
    assert fraction_of(image, lambda i: ~is_background(i)) > 0.1


def test_oxygen_is_red(rutile):
    """Colours reach the GPU as per-atom arrays, not as one actor
    colour."""
    image = vtk_scene.render_to_array(
        build_scene(rutile, ViewSettings()), SIZE)
    assert fraction_of(image, is_red) > 0.01


def test_background_colour_is_honoured(rutile):
    settings = ViewSettings(background=(0, 0, 0), show_cell=False)
    image = vtk_scene.render_to_array(build_scene(rutile, settings),
                                      SIZE)
    corner = image[:10, :10].reshape(-1, 3)
    assert corner.max() < 20


def test_space_filling_covers_more_than_ball_and_stick(rutile):
    ball = vtk_scene.render_to_array(
        build_scene(rutile, ViewSettings(style="ball_stick",
                                         show_cell=False)), SIZE)
    fill = vtk_scene.render_to_array(
        build_scene(rutile, ViewSettings(style="spacefill",
                                         show_cell=False)), SIZE)
    assert (fraction_of(fill, lambda i: ~is_background(i))
            > fraction_of(ball, lambda i: ~is_background(i)))


def test_an_empty_scene_renders_the_background_and_nothing_else():
    from xtal import Lattice, Structure
    empty = Structure.empty(Lattice.cubic(5.0))
    image = vtk_scene.render_to_array(
        build_scene(empty, ViewSettings(show_cell=False)), SIZE)
    assert fraction_of(image, is_background) > 0.99


def test_png_export(rutile, tmp_path):
    path = vtk_scene.render_offscreen(
        build_scene(rutile, ViewSettings()), tmp_path / "shot.png",
        size=SIZE)
    assert path.exists() and path.stat().st_size > 1000


def _offscreen_window(model, size=SIZE):
    """A real GL context showing a structure, and nothing Qt.

    :func:`~xtalapp.viewport.vtk_scene.write_image` takes a render
    window rather than the viewport widget precisely so these can
    reach it: a widget would want a realised native surface, which is
    what the rest of the suite stubs out.
    """
    from vtkmodules.vtkRenderingCore import vtkRenderWindow
    scene = vtk_scene.VtkScene()
    scene.set_model(model)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(*size)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    window.Render()
    return window


def _read_image(path):
    """A written file back as an (H, W, C) array.

    VTK's own readers rather than Pillow, which is not a dependency of
    this project and only happens to be installed here.
    """
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkIOImage import vtkJPEGReader, vtkPNGReader

    reader = (vtkJPEGReader() if Path(path).suffix in (".jpg", ".jpeg")
              else vtkPNGReader())
    reader.SetFileName(str(path))
    reader.Update()
    image = reader.GetOutput()
    width, height, _ = image.GetDimensions()
    pixels = vtk_to_numpy(image.GetPointData().GetScalars())
    return pixels.reshape(height, width, -1)


def test_the_suffix_picks_the_writer(rutile, tmp_path):
    """One dialog offers four formats and the path is all that says
    which; a wrong writer here would still leave a file behind."""
    window = _offscreen_window(build_scene(rutile, ViewSettings()))
    try:
        for name, magic in (("shot.png", b"\x89PNG"),
                            ("shot.jpg", b"\xff\xd8\xff"),
                            ("shot.tif", (b"II*\x00", b"MM\x00*"))):
            path = vtk_scene.write_image(window, tmp_path / name,
                                         magnification=1)
            head = path.read_bytes()[:4]
            assert head.startswith(magic), name
    finally:
        window.Finalize()


def test_magnification_multiplies_the_pixels(rutile, tmp_path):
    """What the dialog's "3360 x 3882" is a promise about."""
    window = _offscreen_window(build_scene(rutile, ViewSettings()))
    try:
        one = vtk_scene.write_image(window, tmp_path / "one.png",
                                    magnification=1)
        three = vtk_scene.write_image(window, tmp_path / "three.png",
                                      magnification=3)
    finally:
        window.Finalize()
    assert _read_image(one).shape[:2] == (SIZE[1], SIZE[0])
    assert _read_image(three).shape[:2] == (SIZE[1] * 3, SIZE[0] * 3)


def test_a_transparent_export_keeps_the_atoms_and_drops_the_ground(
        rutile, tmp_path):
    """The point of the box: the background goes and the crystal does
    not, so the picture drops onto a slide of any colour."""
    window = _offscreen_window(
        build_scene(rutile, ViewSettings(show_cell=False)))
    try:
        path = vtk_scene.write_image(window, tmp_path / "clear.png",
                                     magnification=1, transparent=True)
    finally:
        window.Finalize()
    written = _read_image(path)
    assert written.shape[2] == 4, "no alpha channel was written"
    alpha = written[:, :, 3]
    assert alpha[0, 0] < 10                 # the corner is background
    assert (alpha > 200).mean() > 0.05      # the crystal is still there


def test_an_opaque_export_has_no_alpha_to_see_through(rutile, tmp_path):
    window = _offscreen_window(build_scene(rutile, ViewSettings()))
    try:
        path = vtk_scene.write_image(window, tmp_path / "solid.png",
                                     magnification=1)
    finally:
        window.Finalize()
    assert _read_image(path).shape[2] == 3


def test_jpeg_cannot_be_transparent_and_is_written_anyway(rutile,
                                                          tmp_path):
    """The dialog greys the box out, but the option can still arrive
    here; four components would write a broken JPEG rather than
    raise."""
    window = _offscreen_window(build_scene(rutile, ViewSettings()))
    try:
        path = vtk_scene.write_image(window, tmp_path / "solid.jpg",
                                     magnification=1, transparent=True)
    finally:
        window.Finalize()
    written = _read_image(path)
    assert written.shape == (SIZE[1], SIZE[0], 3)


def test_the_camera_projects_the_crystal_onto_the_canvas(rutile):
    """The seam between VTK and the SVG writer.

    ``projection_for`` hands over the renderer's own composite matrix,
    so an atom lands where the viewport has it -- a projection built
    from the wrong convention still writes a plausible-looking file,
    with the crystal off the canvas or upside down.
    """
    scene = build_scene(rutile, ViewSettings())
    window = _offscreen_window(scene)
    try:
        projection = vtk_scene.projection_for(
            window.GetRenderers().GetFirstRenderer(), SIZE)
    finally:
        window.Finalize()
    xy, _depth = projection.to_display(scene.positions)
    assert ((xy[:, 0] >= 0) & (xy[:, 0] <= SIZE[0])).all()
    assert ((xy[:, 1] >= 0) & (xy[:, 1] <= SIZE[1])).all()


def test_an_svg_written_from_the_scene_carries_no_raster(rutile,
                                                         tmp_path):
    """What ``Export Image`` writes for ``.svg``.

    GL2PS wrote the crystal as one embedded PNG here, which is a
    picture of a picture: the format is offered so that each atom can
    be moved and recoloured in Illustrator.
    """
    from xtalapp.viewport.svg_export import write_svg
    scene = build_scene(rutile, ViewSettings())
    window = _offscreen_window(scene)
    try:
        projection = vtk_scene.projection_for(
            window.GetRenderers().GetFirstRenderer(), SIZE)
    finally:
        window.Finalize()
    path = write_svg(scene, projection, tmp_path / "figure.svg")
    text = path.read_text()
    assert "base64" not in text and "<image" not in text
    assert text.count("<circle") == scene.n_atoms


def test_scene_actors_track_the_model(rutile):
    scene = vtk_scene.VtkScene()
    scene.set_model(build_scene(rutile, ViewSettings()))
    assert scene.atom_actor.GetVisibility()
    assert scene.bond_actor.GetVisibility()
    assert scene.cell_actor.GetVisibility()

    scene.set_model(build_scene(
        rutile, ViewSettings(style="spacefill", show_cell=False)))
    assert scene.atom_actor.GetVisibility()
    assert not scene.bond_actor.GetVisibility()
    assert not scene.cell_actor.GetVisibility()


def test_look_along_points_the_camera(rutile):
    scene = vtk_scene.VtkScene()
    scene.set_model(build_scene(rutile, ViewSettings()))
    scene.reset_camera()
    scene.look_along([0.0, 0.0, 1.0])
    direction = np.array(
        scene.renderer.GetActiveCamera().GetDirectionOfProjection())
    assert np.allclose(direction, [0, 0, 1], atol=1e-6)


# ============================================================ depth cue

def _receding_atoms(n=10, box=60.0):
    """A diagonal line of identical atoms, each one further away than
    the last -- so brightness against distance is the whole test."""
    from xtal import Lattice, Structure
    lattice = Lattice.cubic(box)
    cart = np.array([[-13.5 + 3.0 * k, 0.0, -13.5 + 3.0 * k]
                     for k in range(n)], dtype=float)
    return Structure.from_arrays(
        lattice, ["C"] * n, (cart + box / 2) / box, space_group="P1")


def _brightness_by_depth(structure, cue: bool, strength=0.85,
                         **fade):
    """(distance from the eye, mean pixel value) for each atom."""
    settings = ViewSettings(style="spacefill", show_cell=False)
    settings.depth_cue = cue
    settings.depth_cue_strength = strength
    for key, value in fade.items():
        setattr(settings, key, value)
    model = build_scene(structure, settings)

    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkRenderingCore import (
        vtkRenderWindow,
        vtkWindowToImageFilter,
    )
    scene = vtk_scene.VtkScene()
    scene.set_model(model)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(720, 240)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    scene.look_along((0.0, 0.0, 1.0))
    scene.renderer.ResetCamera()
    window.Render()

    grabber = vtkWindowToImageFilter()
    grabber.SetInput(window)
    grabber.Update()
    image = grabber.GetOutput()
    width, height, _ = image.GetDimensions()
    pixels = vtk_to_numpy(image.GetPointData().GetScalars())
    pixels = pixels.reshape(height, width, -1)[::-1, :, :3]

    camera = scene.renderer.GetActiveCamera()
    eye = np.array(camera.GetPosition(), dtype=float)
    view = np.array(camera.GetDirectionOfProjection(), dtype=float)
    out = []
    for position in model.positions:
        scene.renderer.SetWorldPoint(*[float(c) for c in position], 1.0)
        scene.renderer.WorldToDisplay()
        x, y, _z = scene.renderer.GetDisplayPoint()
        patch = pixels[height - int(y) - 2:height - int(y) + 3,
                       int(x) - 2:int(x) + 3]
        if patch.size:
            out.append((float((position - eye) @ view),
                        float(patch.mean())))
    window.Finalize()
    return sorted(out)


def test_depth_cueing_fades_the_far_atoms_and_not_the_near_ones():
    """The point of the effect: a slab has to read as having depth.
    Asserted as a monotone climb towards the background with distance,
    which is what "fade" means and what a shader that compiled but did
    nothing would fail."""
    structure = _receding_atoms()
    cued = _brightness_by_depth(structure, cue=True)
    values = [brightness for _depth, brightness in cued]
    assert len(values) >= 8
    assert values[-1] > values[0] + 30      # the back really recedes
    rising = sum(b > a for a, b in
                 zip(values, values[1:], strict=False))
    assert rising >= len(values) - 2        # and does so all the way


def test_without_depth_cueing_distance_changes_nothing():
    """The control.  Perspective alone makes a far atom smaller, not
    paler, so the uncued line is flat and any drift here would mean the
    test above was measuring the projection instead of the fade."""
    plain = [b for _d, b in _brightness_by_depth(_receding_atoms(),
                                                 cue=False)]
    assert max(plain) - min(plain) < 20


def test_the_fade_goes_to_the_background_colour():
    """Towards *the background*, not towards white: on a black
    background a distant atom gets darker, and a fade that always
    lightened would make the back of the picture glow."""
    structure = _receding_atoms()
    settings = ViewSettings(style="spacefill", show_cell=False,
                            background=(0, 0, 0))
    settings.depth_cue = True
    settings.depth_cue_strength = 0.9
    lit = vtk_scene.render_to_array(
        build_scene(structure, settings), SIZE, direction=(0.0, 0.0, 1.0))
    settings.depth_cue = False
    plain = vtk_scene.render_to_array(
        build_scene(structure, settings), SIZE, direction=(0.0, 0.0, 1.0))
    assert lit.mean() < plain.mean()


def test_the_fade_starts_where_it_is_told_to():
    """The front of the picture is left alone and the fade is spent on
    the back of it -- which is the setting somebody reaches for on a
    slab three cells deep, where fading from the front face washes out
    the half they are looking at."""
    structure = _receding_atoms()
    plain = [b for _d, b in _brightness_by_depth(structure, cue=False)]
    late = [b for _d, b in _brightness_by_depth(structure, cue=True,
                                                depth_cue_start=0.5)]
    half = len(plain) // 3
    # the near third untouched, the far end still going
    assert max(abs(a - b) for a, b
               in zip(plain[:half], late[:half], strict=True)) < 20
    assert late[-1] > plain[-1] + 30


def test_the_gradient_bends_the_fade_it_does_not_move_its_end():
    """Above 1 the picture stays clear and then falls away, so the
    middle of the run is less faded -- and the back of it is not, or
    the control would just be the strength slider again."""
    structure = _receding_atoms()
    straight = [b for _d, b in _brightness_by_depth(structure, True)]
    steep = [b for _d, b in
             _brightness_by_depth(structure, True,
                                  depth_cue_gradient=3.0)]
    middle = len(straight) // 2
    assert steep[middle] < straight[middle] - 20
    assert abs(steep[-1] - straight[-1]) < 20


def test_a_flat_style_still_draws_when_the_fade_is_on():
    """The regression, and it was total: turning lighting off to draw
    a flat style takes ``vertexVCVSOutput`` out of the fragment shader
    with it, the fade's shader replacement then fails to compile, and
    the actor draws nothing at all.  Every style has to survive the
    switch being flipped."""
    from xtal import Lattice, Structure
    from xtal.core.site import Site
    structure = Structure(
        lattice=Lattice.cubic(20.0),
        sites=[Site("C", [0.5, 0.5, 0.2 + 0.08 * k]) for k in range(6)],
        space_group="P1")
    for style in ("cartoon", "wireframe", "platon", "ball_stick"):
        settings = ViewSettings(style=style, show_cell=False)
        drawn = []
        for cue in (False, True):
            settings.depth_cue = cue
            image = vtk_scene.render_to_array(
                build_scene(structure, settings), SIZE,
                direction=(0.0, 0.0, -1.0))
            drawn.append(fraction_of(image, lambda i: ~is_background(i)))
        assert drawn[1] > 0.5 * drawn[0], f"{style} vanished"


def test_the_line_style_fades_even_though_it_has_no_shader():
    """A wide line goes through a geometry shader, which does not
    carry the position the fade measures -- so the line-drawn bonds
    are faded by recolouring them instead.  The picture has to recede
    all the same."""
    from xtal import Lattice, Structure
    from xtal.core.site import Site
    structure = Structure(
        lattice=Lattice.cubic(20.0),
        sites=[Site("C", [0.5, 0.5, 0.15 + 0.07 * k]) for k in range(8)],
        space_group="P1")
    settings = ViewSettings(style="wireframe", show_cell=False)

    def ink(cue):
        settings.depth_cue = cue
        image = vtk_scene.render_to_array(
            build_scene(structure, settings), (400, 400),
            direction=(0.0, 0.0, -1.0))
        return fraction_of(image, lambda i: i.sum(axis=2) < 600)

    assert ink(False) > 0.0
    # Faded lines are paler, so fewer of their pixels are still dark;
    # a wireframe that had vanished would answer 0.
    assert 0.0 < ink(True) < ink(False)


def test_depth_cueing_is_off_unless_it_is_asked_for():
    """Or every documentation image and every render test quietly
    changes under it."""
    structure = _receding_atoms()
    assert not ViewSettings().depth_cue
    model = build_scene(structure, ViewSettings())
    assert not model.depth_cue
    scene = vtk_scene.VtkScene()
    scene.set_model(model)
    assert not scene._cue_on


# =============================================== thermal ellipsoids

def _one_atom_with(u_aniso, box=12.0):
    from xtal import Lattice, Structure
    from xtal.core.site import Site
    return Structure(lattice=Lattice.cubic(box),
                     sites=[Site("C", [0.5, 0.5, 0.5],
                                 u_aniso=u_aniso)],
                     space_group="P1")


def _footprint(structure, probability=0.5):
    """(width, height) in pixels of what gets drawn, seen down z."""
    settings = ViewSettings(style="ortep", show_cell=False)
    settings.ellipsoid_probability = probability
    image = vtk_scene.render_to_array(
        build_scene(structure, settings), (400, 400),
        direction=(0.0, 0.0, -1.0))
    ink = image.sum(axis=2) < 730
    rows, columns = np.nonzero(ink)
    assert len(rows), "nothing was drawn"
    return (int(columns.max() - columns.min()),
            int(rows.max() - rows.min()))


def test_an_ellipsoid_is_drawn_pointing_where_its_tensor_says():
    """The whole of ORTEP, and the one thing that is silently wrong if
    the orientation and the axis lengths get paired up incorrectly: a
    tensor loose along x has to be drawn wide, not tall.

    The camera resets to fit whatever it is given, so the test is the
    *aspect* of each picture and never a size across pictures.
    """
    wide = _footprint(_one_atom_with((0.09, 0.01, 0.01, 0, 0, 0)))
    tall = _footprint(_one_atom_with((0.01, 0.09, 0.01, 0, 0, 0)))
    end_on = _footprint(_one_atom_with((0.01, 0.01, 0.09, 0, 0, 0)))
    round_ = _footprint(_one_atom_with((0.03, 0.03, 0.03, 0, 0, 0)))

    assert wide[0] > 2 * wide[1]
    assert tall[1] > 2 * tall[0]
    assert abs(end_on[0] - end_on[1]) < 0.2 * end_on[0]
    assert abs(round_[0] - round_[1]) < 0.2 * round_[0]


def test_octant_shading_darkens_the_ellipsoid_it_is_drawn_on():
    """A sphere and a 3:1 ellipsoid seen down its long axis have the
    same silhouette, and the arcs are what tell them apart.  So the
    shading has to reach the pixels and not only the scene model."""
    structure = _one_atom_with((0.09, 0.02, 0.01, 0.01, 0.0, 0.0))
    settings = ViewSettings(style="ortep", show_cell=False)

    def dark(on):
        settings.ellipsoid_octants = on
        image = vtk_scene.render_to_array(
            build_scene(structure, settings), (400, 400),
            direction=(0.0, 0.0, -1.0))
        return fraction_of(image, lambda i: i.sum(axis=2) < 200)

    assert dark(True) > 3 * dark(False)


def test_the_octant_glyph_covers_only_the_measured_atoms():
    """One extra actor over a subset of the same points, so the count
    in its polydata is the whole of the claim."""
    from xtal import Lattice, Structure
    from xtal.core.site import Site
    structure = Structure(
        lattice=Lattice.cubic(12.0),
        sites=[Site("C", [0.3, 0.3, 0.3],
                    u_aniso=(0.02, 0.03, 0.05, 0.0, 0.0, 0.0)),
               Site("H", [0.6, 0.6, 0.6], u_iso=0.05)],
        space_group="P1")
    scene = vtk_scene.VtkScene()
    model = build_scene(structure,
                        ViewSettings(style="ortep", show_cell=False))
    scene.set_model(model)
    assert scene.octant_actor.GetVisibility()
    assert scene._octant_poly.GetNumberOfPoints() == 1

    scene.set_model(build_scene(structure,
                                ViewSettings(show_cell=False)))
    assert not scene.octant_actor.GetVisibility()


def test_a_pie_puts_both_occupants_of_a_site_on_the_screen():
    """The complaint the style answers: an Fe/Ni site drawn any other
    way is one sphere, and which of the two you are looking at is a
    coin toss."""
    from xtal import Lattice, Structure
    from xtal.core.site import Site
    structure = Structure(
        lattice=Lattice.cubic(6.0),
        sites=[Site("Fe", [0.5, 0.5, 0.5], occupancy=0.5),
               Site("O", [0.5, 0.5, 0.5], occupancy=0.5)],
        space_group="P1")
    image = vtk_scene.render_to_array(
        build_scene(structure,
                    ViewSettings(style="ball_stick_occupancy",
                                 show_cell=False)),
        (400, 400), direction=(0.0, 0.0, -1.0))
    # By hue and not by brightness: a pie is shaded like any other
    # sphere, so a threshold on the red channel counts the lit half of
    # the oxygen and none of its dark half.
    def scarlet(i):                                     # oxygen
        return ((i[:, :, 0] > 60) & (i[:, :, 1] < 0.25 * i[:, :, 0])
                & (i[:, :, 2] < 0.25 * i[:, :, 0]))

    def rust(i):                                        # iron
        return ((i[:, :, 0] > 60) & (i[:, :, 1] > 0.3 * i[:, :, 0])
                & (i[:, :, 1] < 0.65 * i[:, :, 0])
                & (i[:, :, 2] < 0.45 * i[:, :, 0]))

    oxygen, iron = fraction_of(image, scarlet), fraction_of(image, rust)
    assert oxygen > 0.05 and iron > 0.05
    # half the circle each, so neither may be a sliver beside the other
    assert 0.6 < oxygen / iron < 1.7


def test_the_glyph_goes_back_to_spheres_when_the_style_changes():
    """One mapper draws both, so the switch has to put the scale and
    orientation arrays back or every atom keeps the last ellipsoid it
    was given."""
    structure = _one_atom_with((0.09, 0.01, 0.01, 0, 0, 0))
    settings = ViewSettings(style="ortep", show_cell=False)
    scene = vtk_scene.VtkScene()
    scene.set_model(build_scene(structure, settings))
    assert scene.atom_mapper.GetOrient()

    scene.set_model(build_scene(structure,
                                ViewSettings(show_cell=False)))
    assert not scene.atom_mapper.GetOrient()


# ============================================================ the cell

def test_the_cell_frame_follows_a_relaxing_lattice():
    """The bug the scale bar made visible.  ``set_positions`` moved
    the atoms and left ``_cell_poly`` alone, and ``_same_shape``
    compares the number of cell *lines* -- which is twelve before and
    twelve after -- so a variable-cell relaxation drew the atoms
    contracting inside a box that was still the old one."""
    from xtal import Lattice, Structure
    settings = ViewSettings()

    def box(a):
        return Structure.from_arrays(Lattice.cubic(a), ["Na"],
                                     [[0.0, 0.0, 0.0]],
                                     space_group="P1")

    scene = vtk_scene.VtkScene()
    scene.set_model(build_scene(box(6.0), settings))
    before = np.array(scene._cell_poly.GetPoints().GetData()).max()

    smaller = build_scene(box(5.4), settings)
    assert scene._same_shape(smaller)       # nothing looks different
    scene.set_positions(smaller)
    after = np.array(scene._cell_poly.GetPoints().GetData()).max()
    assert after == pytest.approx(before * 0.9, rel=1e-5)


# ======================================================= the scale bar

def test_a_nice_length_is_one_two_or_five_per_decade():
    """A reader counts the bar off against the picture, and 3.7 A is
    not a length anybody counts in."""
    nice = vtk_scene._nice_length
    assert nice(1.0) == 1.0
    assert nice(3.7) == 2.0
    assert nice(9.9) == 5.0
    assert nice(37.0) == 20.0
    assert nice(0.37) == pytest.approx(0.2)
    assert nice(0.0) > 0.0                  # never a bar of no length


def _with_a_bar(structure, cells=1):
    settings = ViewSettings(show_scale_bar=True)
    settings.set_cells(cells, cells, cells)
    scene = vtk_scene.VtkScene()
    scene.renderer.SetViewport(0.0, 0.0, 1.0, 1.0)
    window = vtk_scene.vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(*SIZE)
    window.AddRenderer(scene.renderer)
    scene.set_model(build_scene(structure, settings))
    scene.reset_camera()
    window.Render()
    # The renderer keeps only a back-pointer to its window, so without
    # this the window is collected and the next Render finds nothing.
    scene.window = window
    return scene


def test_the_scale_bar_appears_only_when_it_is_asked_for(rutile):
    scene = vtk_scene.VtkScene()
    scene.set_model(build_scene(rutile, ViewSettings()))
    assert not scene.bar_actor.GetVisibility()
    assert not scene.bar_label.GetVisibility()

    scene.set_model(build_scene(rutile,
                                ViewSettings(show_scale_bar=True)))
    assert scene.bar_actor.GetVisibility()
    assert scene.bar_label.GetVisibility()


def test_the_bar_says_how_long_it_is(rutile):
    scene = _with_a_bar(rutile)
    label = scene.bar_label.GetInput()
    assert label.endswith(" A")
    assert float(label[:-2]) > 0.0


def test_a_bigger_picture_gets_a_longer_bar(rutile):
    """The bar measures the camera, so drawing three cells instead of
    one has to give a bar worth more Angstrom."""
    one = float(_with_a_bar(rutile, 1).bar_label.GetInput()[:-2])
    three = float(_with_a_bar(rutile, 3).bar_label.GetInput()[:-2])
    assert three > one


def test_the_bar_stands_still_while_the_cell_contracts():
    """The whole point of it.  A ruler taken from the structure's own
    size would shrink with the cell it is there to measure, and the
    picture would show a box and a ruler contracting together -- which
    is a picture of nothing happening."""
    from xtal import Lattice, Structure

    def box(a):
        return Structure.from_arrays(Lattice.cubic(a), ["Na"],
                                     [[0.0, 0.0, 0.0]],
                                     space_group="P1")

    settings = ViewSettings(show_scale_bar=True)
    scene = _with_a_bar(box(10.0))
    before = scene.bar_label.GetInput()
    before_points = np.array(
        scene._bar_poly.GetPoints().GetData()).copy()

    scene.set_positions(build_scene(box(9.6), settings))
    scene.window.Render()
    assert scene.bar_label.GetInput() == before
    assert np.allclose(
        np.array(scene._bar_poly.GetPoints().GetData()), before_points)
