"""The Skeletal style on screen: the label atlas, and the ink the
renderer cuts for each camera."""

import time
from pathlib import Path

import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderWindow

from tests.conftest import needs_offscreen_gl
from xtal import Lattice, Structure
from xtal.io.cif_reader import read_cif
from xtalapp.viewport import label_atlas, sketch, vtk_scene
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import ViewSettings

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


def methylamine() -> Structure:
    edge = 12.0
    cart = np.array([[0.0, 0.0, 0.0], [1.47, 0.0, 0.0],
                     [-0.36, 1.03, 0.0], [-0.36, -0.51, 0.89],
                     [-0.36, -0.51, -0.89],
                     [1.81, -0.47, 0.82], [1.81, -0.47, -0.82]])
    return Structure.from_arrays(
        Lattice.cubic(edge), ["C", "N", "H", "H", "H", "H", "H"],
        cart / edge + 0.5)


def skeletal(structure, **changes):
    settings = ViewSettings(style="skeletal", show_cell=False)
    for key, value in changes.items():
        setattr(settings, key, value)
    return build_scene(structure, settings)


def a_window(model, size=(320, 240), direction=(0.0, 0.0, -1.0)):
    scene = vtk_scene.VtkScene()
    scene.set_model(model)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(*size)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    scene.look_along(direction)
    scene.renderer.ResetCamera()
    window.Render()
    return scene, window


# -- the atlas, which needs FreeType and no GL -------------------------


def test_every_string_is_set_once_at_every_step_of_the_fade():
    atlas = label_atlas.build(
        [("NH2", "N", (0, 0, 0)), ("Zn", "Zn", (0, 0, 0)),
         ("NH2", "N", (0, 0, 0))], (255, 255, 255), 1.0, 0.2)
    assert len(atlas.rects) == 2 * label_atlas.LEVELS
    u0, v0, u1, v1 = atlas.rects[("NH2", (0, 0, 0), 0)]
    assert 0 <= u0 < u1 <= 1 and 0 <= v0 < v1 <= 1


def test_a_cell_is_the_box_the_lines_stop_short_of():
    """The knockout and the gap are one rectangle: the cell's shape is
    the sketch's padded extents, at the atlas's own scale."""
    left, right, down, up = sketch.label_extents("NH2", "N", 1.0, 0.2)
    image = label_atlas.cell("NH2", "N", (0, 0, 0), (255, 255, 255),
                             1.0, 0.2)
    cap = label_atlas.CAP_PX
    assert image.shape[1] == round((left + right) * cap)
    assert image.shape[0] == round((down + up) * cap)


def test_the_letters_fit_inside_their_box():
    """Nothing is inked in the outermost ring of the cell: letters
    wider than the sketch's metrics would be clipped there."""
    for text in ("NH2", "OH2", "H2O", "Zn", "W", "Mg", "CH3", "Cl"):
        image = label_atlas.cell(text, sketch.symbol_of(text), (0, 0, 0),
                                 (255, 255, 255), 1.0,
                                 sketch.LABEL_PAD / sketch.LABEL_HEIGHT)
        edge = np.concatenate([image[0], image[-1], image[:, 0],
                               image[:, -1]])
        assert edge[:, :3].min() == 255, text
        assert edge[:, 3].max() == 0, text
        assert image[:, :, :3].min() < 64, text     # and it has ink


def test_the_fade_ends_at_the_background():
    colors = label_atlas.level_colors((0, 0, 0), (200, 210, 220))
    assert tuple(colors[0]) == (0, 0, 0)
    assert tuple(colors[-1]) == (200, 210, 220)
    assert label_atlas.level_of([0.0, 1.0]).tolist() == [
        0, label_atlas.LEVELS - 1]


def test_a_label_names_its_own_element():
    assert sketch.symbol_of("NH2") == "N"
    assert sketch.symbol_of("H2O") == "O"
    assert sketch.symbol_of("HCl") == "Cl"
    assert sketch.symbol_of("H") == "H"
    assert sketch.symbol_of("Zn") == "Zn"


# -- on screen ---------------------------------------------------------


@needs_offscreen_gl
def test_a_skeletal_render_has_ink_and_no_spheres():
    """Black lines and letters on white, and none of the palette:
    nitrogen's blue would be a sphere drawn under the label."""
    image = vtk_scene.render_to_array(skeletal(methylamine()), (320, 240),
                                      direction=(0.0, 0.0, -1.0))
    pixels = image.reshape(-1, 3).astype(int)
    assert (pixels.max(axis=1) < 90).sum() > 30          # ink
    spread = pixels.max(axis=1) - pixels.min(axis=1)
    assert spread.max() < 40                              # all grey


@needs_offscreen_gl
def test_the_lines_on_screen_stop_outside_the_label():
    scene, window = a_window(skeletal(methylamine()))
    model = scene.model
    n = model.label_text.index("NH2")
    poly = scene._sketch_line_poly
    points = np.array([poly.GetPoint(k)
                       for k in range(poly.GetNumberOfPoints())])
    assert len(points)
    # Looking down -z: the screen is the xy plane.
    offset = points[:, :2] - model.positions[n][:2]
    left, right, down, up = model.label_extents[n] + model.label_pad
    inside = ((offset[:, 0] > -left + 1e-3) & (offset[:, 0] < right - 1e-3)
              & (offset[:, 1] > -down + 1e-3) & (offset[:, 1] < up - 1e-3))
    assert not inside.any()
    assert scene.label_actor.GetVisibility()
    window.Finalize()


@needs_offscreen_gl
def test_turning_the_camera_recuts_the_ink_without_a_rebuild():
    scene, window = a_window(skeletal(methylamine()),
                             direction=(0.3, 0.2, -1.0))
    labels = scene._label_poly
    before = np.array(scene._sketch_line_poly.GetPoint(0))
    scene.renderer.GetActiveCamera().Azimuth(50)
    window.Render()
    after = np.array(scene._sketch_line_poly.GetPoint(0))
    assert not np.allclose(before, after)
    assert scene._label_poly is labels
    window.Finalize()


@needs_offscreen_gl
def test_a_dark_ground_draws_white_ink():
    image = vtk_scene.render_to_array(
        skeletal(methylamine(), background=(0, 0, 0)), (320, 240),
        direction=(0.0, 0.0, -1.0))
    assert (image.reshape(-1, 3).min(axis=1) > 180).sum() > 30


@needs_offscreen_gl
def test_another_style_hides_the_sketch():
    scene, window = a_window(skeletal(methylamine()))
    scene.set_model(build_scene(methylamine(), ViewSettings()))
    assert not scene.label_actor.GetVisibility()
    assert not scene.sketch_line_actor.GetVisibility()
    assert scene.atom_actor.GetVisibility()
    window.Finalize()


def _mfu4l(cells):
    settings = ViewSettings(style="skeletal", show_cell=False,
                            sketch_explicit_carbon=True)
    settings.set_cells(cells, cells, cells)
    return build_scene(read_cif(SAMPLES / "MFU4l.cif"), settings)


@needs_offscreen_gl
def test_thousands_of_labels_add_no_actors():
    """What the atlas is for: 2000 billboard labels, an actor each,
    took 126 ms a frame.  A 2x2x2 MFU-4l with carbon written out is
    4512 labels, and the scene holds exactly the actors one cell's
    288 need.  Actor count, not a frame time, because a frame on a
    runner with no GPU measures its software GL and not this."""
    one = _mfu4l(1)
    eight = _mfu4l(2)
    assert sum(1 for t in eight.label_text if t) > 4000
    counts = []
    for model in (one, eight):
        scene, window = a_window(model, (200, 200))
        counts.append(scene.renderer.GetActors().GetNumberOfItems())
        window.Finalize()
    assert counts[0] == counts[1]


@needs_offscreen_gl
def test_a_turn_recuts_thousands_of_labels_in_one_numpy_pass():
    """The work a turn of the camera adds on the CPU: 12 224
    half-bonds cut, wedged and faded, 4512 labels pointed at their
    step of the fade.  About 14 ms here; the bound is ten times that,
    for a slow runner, and a loop in Python per label or per bond
    would still be well past it."""
    scene, window = a_window(_mfu4l(2), (200, 200),
                             direction=(1.0, 0.4, -0.7))
    camera = scene.renderer.GetActiveCamera()
    times = []
    for _ in range(5):
        camera.Azimuth(7)
        start = time.perf_counter()
        scene._refresh_sketch()
        times.append(time.perf_counter() - start)
    assert np.median(times) < 0.15
    window.Finalize()


# -- the box under each label, and a pore sphere behind it --------------


def test_the_atlas_is_transparent_outside_the_letters():
    """The alpha is the letters' coverage, which is what lets the
    window draw them without their box."""
    atlas = label_atlas.build([("NH2", "N", (0, 0, 0))],
                              (255, 255, 255), 1.0, 0.2)
    alpha = atlas.image[:, :, 3]
    assert alpha.min() == 0 and alpha.max() > 200
    assert (alpha > 0).mean() < 0.5


def _pore_behind_the_nitrogen(**changes):
    """Methylamine with a 2 A pore sphere 3 A behind its N, as the
    camera looking down -z sees it."""
    from xtal.analysis.porosity import PoreNetwork
    settings = ViewSettings(style="skeletal", show_cell=False)
    for key, value in changes.items():
        setattr(settings, key, value)
    pores = PoreNetwork(nodes=np.array([(0.5 + 1.47 / 12, 0.5,
                                         0.5 - 3.0 / 12)]),
                        radii=np.array([2.0]))
    return build_scene(methylamine(), settings, pores=pores)


def _box_corner_pixel(scene, window):
    """The colour inside the N label's box, in its padding, where no
    letter is."""
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    model = scene.model
    n = model.label_text.index("NH2")
    left, right, down, up = model.label_extents[n]
    pad = model.label_pad
    corner = model.positions[n] + np.array(
        [right + pad / 2, up + pad / 2, 0.0])
    renderer = scene.renderer
    renderer.SetWorldPoint(*corner, 1.0)
    renderer.WorldToDisplay()
    x, y, _z = renderer.GetDisplayPoint()
    grab = vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.Update()
    image = grab.GetOutput()
    w, h, _ = image.GetDimensions()
    pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(
        h, w, -1)
    return pixels[int(round(y)), int(round(x)), :3].astype(int)


@needs_offscreen_gl
def test_a_pore_sphere_shows_through_the_box_by_default():
    """The white rectangle a label left in a sphere behind it is what
    this setting exists to take away."""
    scene, window = a_window(_pore_behind_the_nitrogen())
    assert scene.label_box_actor.GetVisibility()
    r, g, b = _box_corner_pixel(scene, window)
    assert b - r > 10                           # the sphere's blue


@needs_offscreen_gl
def test_a_box_over_pores_hides_the_sphere_as_it_always_did():
    scene, window = a_window(
        _pore_behind_the_nitrogen(sketch_box_over_pores=True))
    assert tuple(_box_corner_pixel(scene, window)) == (255, 255, 255)
    assert scene.renderer.GetUseOIT()


@needs_offscreen_gl
def test_without_backgrounds_there_is_no_box_actor():
    scene, _window = a_window(
        _pore_behind_the_nitrogen(sketch_label_box=False))
    assert not scene.label_box_actor.GetVisibility()
    assert scene.label_actor.GetVisibility()
    assert scene.renderer.GetUseOIT()


@needs_offscreen_gl
def test_leaving_the_skeletal_style_turns_order_independence_back_on():
    """It is off only while a box lets a sphere through: every other
    picture's translucency is sorted by it."""
    scene, window = a_window(_pore_behind_the_nitrogen())
    assert not scene.renderer.GetUseOIT()
    scene.set_model(build_scene(methylamine(), ViewSettings()))
    assert scene.renderer.GetUseOIT()
