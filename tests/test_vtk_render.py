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
