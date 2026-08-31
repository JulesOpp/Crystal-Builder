"""The VTK render path, exercised offscreen.

These tests draw a structure into an offscreen buffer and assert on the
pixels.  A file-size check would pass on a blank image; "there are red
pixels where the oxygen is" would not.
"""

import numpy as np
import pytest

vtk_scene = pytest.importorskip("xtalapp.viewport.vtk_scene")


def _offscreen_gl_works() -> bool:
    """Some CI images have no GL driver at all; there the render tests
    are skipped rather than failing on the environment."""
    try:
        from xtalapp.viewport.scene import SceneModel
        image = vtk_scene.render_to_array(SceneModel(), (8, 8))
        return image.shape == (8, 8, 3)
    except Exception:                       # pragma: no cover
        return False


pytestmark = pytest.mark.skipif(
    not _offscreen_gl_works(),
    reason="offscreen OpenGL is not available here")

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


def _brightness_by_depth(structure, cue: bool, strength=0.85):
    """(distance from the eye, mean pixel value) for each atom."""
    settings = ViewSettings(style="spacefill", show_cell=False)
    settings.depth_cue = cue
    settings.depth_cue_strength = strength
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
