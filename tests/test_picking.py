"""Ray casting: turning a click into an atom or a bond."""

import numpy as np
import pytest

from tests.conftest import needs_offscreen_gl
from xtal import Lattice, Structure
from xtalapp.viewport import picking
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import ViewSettings


@pytest.fixture
def diatomic():
    """C and O 1.5 A apart along x, in a roomy P1 box."""
    return Structure.from_arrays(
        Lattice.cubic(10.0), ["C", "O"],
        [[0.2, 0.5, 0.5], [0.35, 0.5, 0.5]])


@pytest.fixture
def scene(diatomic):
    return build_scene(diatomic, ViewSettings(show_cell=False))


def test_a_ray_through_an_atom_hits_it(scene):
    kind, index = picking.pick(scene, [-10, 5, 5], [1, 0, 0])
    assert kind == "atom" and index == 0        # the C, nearest first


def test_the_nearest_atom_wins(scene):
    kind, index = picking.pick(scene, [20, 5, 5], [-1, 0, 0])
    assert kind == "atom" and index == 1        # coming from the far
                                                # side, the O is first


def test_a_ray_through_the_bond_midpoint_hits_the_bond(scene):
    kind, index = picking.pick(scene, [2.75, 5, -10], [0, 0, 1])
    assert kind == "bond"
    assert 0 <= index < scene.n_bond_halves


def test_an_atom_in_front_of_a_bond_wins(scene):
    """Regression: comparing sphere *centres* with bond *midpoints*
    made a bond that grazes past a big atom beat the atom the ray
    actually entered first."""
    origin = np.array([2.0, 5.0, -10.0])
    kind, index = picking.pick(scene, origin, [0, 0, 1])
    assert kind == "atom" and index == 0


def test_empty_space_and_things_behind_the_camera(scene):
    assert picking.pick(scene, [0, 0, -10], [0, 0, 1]) == (None, None)
    assert picking.pick(scene, [2.75, 5, 20], [0, 0, 1]) == (None, None)


def test_picking_an_empty_scene():
    from xtalapp.viewport.scene import SceneModel
    empty = SceneModel()
    assert picking.pick_atom(empty, [0, 0, 0], [0, 0, 1]) is None
    assert picking.pick_bond(empty, [0, 0, 0], [0, 0, 1]) is None
    assert picking.pick(empty, [0, 0, 0], [0, 0, 1]) == (None, None)


def test_hits_report_the_entry_point_not_the_centre(scene):
    index, depth = picking.atom_hit(scene, [-10, 5, 5], [1, 0, 0])
    centre = float(np.linalg.norm(scene.positions[index]
                                  - np.array([-10.0, 5.0, 5.0])))
    assert depth < centre
    assert depth == pytest.approx(centre - scene.radii[index], abs=1e-5)


def test_a_ray_just_past_an_atom_misses_it(scene):
    radius = float(scene.radii[0])
    x = float(scene.positions[0][0])
    assert picking.pick_atom(
        scene, [x, 5 + radius * 1.2, -10], [0, 0, 1]) is None
    assert picking.pick_atom(
        scene, [x, 5 + radius * 0.5, -10], [0, 0, 1]) == 0


def test_bond_picking_tolerates_a_near_miss(scene):
    """Bonds are thin; a click that lands just off one should still
    take it, or selecting a bond becomes a game of darts."""
    inside = scene.bond_radius * 1.2
    outside = scene.bond_radius * 3.0
    assert picking.pick_bond(scene, [2.6, 5 + inside, -10],
                             [0, 0, 1]) is not None
    assert picking.pick_bond(scene, [2.6, 5 + outside, -10],
                             [0, 0, 1]) is None


# ============================================ picking a net edge


@pytest.fixture
def net(diatomic):
    """The same two atoms, with a net edge drawn between them."""
    from xtal.core.structure import TOPOLOGY, Bond

    diatomic.bonds.append(Bond(0, 1, (0, 0, 0), kind=TOPOLOGY))
    diatomic.touch()
    return build_scene(diatomic, ViewSettings(show_cell=False))


def test_a_click_down_the_axis_of_an_edge_means_the_edge(net):
    """A net edge is drawn over the bond it covers, and a click near
    its axis means the edge in every mode -- not only in Draw net,
    where it is preferred outright.

    Deliberately changed.  Depth alone gave the bond underneath, and
    Del then suppressed that bond and its whole orbit: a click aimed
    at the net, deleting the chemistry and leaving the net on screen.
    """
    assert picking.pick(net, [2.75, 5, -10], [0, 0, 1],
                        prefer_topology=True) == ("topology", 0)
    assert picking.pick(net, [2.75, 5, -10], [0, 0, 1]) == ("topology", 0)


def test_a_click_out_at_the_rim_of_an_edge_takes_what_is_under_it(net):
    """The other half of the rule, and what keeps a bond that runs
    under an edge selectable: outside the core, whatever is behind the
    edge wins as it always did."""
    core = net.topology_radius * picking.TOPOLOGY_CORE_FRACTION
    reach = net.bond_radius * picking.BOND_PICK_SLACK
    assert core < reach                 # there is a ring to aim at

    inside_the_bond = (core + reach) / 2
    assert picking.pick(net, [2.75, 5 + inside_the_bond, -10],
                        [0, 0, 1])[0] == "bond"

    # Further out the bond is gone as well, and the edge is all that
    # is left -- the last resort that makes the span of an edge
    # selectable where it crosses open space.
    past_the_bond = (reach + net.topology_radius) / 2
    assert picking.pick(net, [2.75, 5 + past_the_bond, -10],
                        [0, 0, 1])[0] == "topology"


def test_an_atom_with_a_net_edge_on_it_is_still_an_atom(net):
    """Drawing the second edge of a net starts where the first one
    ended, and a net edge runs centre to centre -- so an edge that won
    a click outright would swallow both its own ends and there would be
    no way to carry on.  It wins on depth and loses to the atom."""
    for atom, x in ((0, 2.0), (1, 3.5)):
        assert picking.pick(net, [x, 5, -10], [0, 0, 1],
                            prefer_topology=True) == ("atom", atom)


# Renders for real, so it needs a GL driver; the rest of this
# file does not and must keep running without one.  See
# conftest.offscreen_gl_works.
@needs_offscreen_gl
def test_ray_from_display_needs_a_renderer(rutile):
    """The one VTK-dependent piece: a ray from the camera through a
    pixel, aimed into the scene."""
    vtk_scene = pytest.importorskip("xtalapp.viewport.vtk_scene")
    scene = vtk_scene.VtkScene()
    model = build_scene(rutile, ViewSettings())
    scene.set_model(model)
    scene.reset_camera()
    scene.renderer.GetRenderWindow()

    from vtkmodules.vtkRenderingCore import vtkRenderWindow
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(200, 200)
    window.AddRenderer(scene.renderer)
    window.Render()

    origin, direction = picking.ray_from_display(scene.renderer, 100,
                                                 100)
    assert np.isclose(np.linalg.norm(direction), 1.0)
    # the centre pixel looks at the middle of the structure
    to_centre = model.center() - origin
    to_centre /= np.linalg.norm(to_centre)
    assert np.dot(to_centre, direction) > 0.99
    window.Finalize()
