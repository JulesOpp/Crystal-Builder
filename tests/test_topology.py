"""Topology bonds: the net, drawn.

The underlying net of a framework -- **pcu**, **dia**, **sql** -- is
not its bond graph.  It is what is left after deciding which parts are
nodes and which are linkers, and that decision belongs to a chemist and
not to a distance criterion.

Two things are being tested and they pull in opposite directions.  A
topology bond has to behave like every other stored bond -- saved,
undoable, expanded over the symmetry orbit -- and it has to be
completely invisible to everything chemical, because a net edge in the
force field's topology, in a coordination number or in a valence check
is wrong in all three.

The net invariants are checked against RCSR's published values.  A
coordination sequence that is self-consistent but not 6, 18, 38, 66
is not describing **pcu**, and the whole point of computing one is to
be able to say which net you have.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding
from xtal.core.structure import TOPOLOGY, Bond
from xtalapp.document import Document
from xtalapp.viewport import modes
from xtalapp.viewport.builder import build_scene, selection_flags
from xtalapp.viewport.view_settings import ViewSettings


def pcu(a=5.0) -> Structure:
    """One vertex, three net edges along a, b and c: simple cubic."""
    structure = Structure.from_arrays(Lattice.cubic(a), ["Zn"],
                                      [[0.0, 0.0, 0.0]],
                                      space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        structure.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    structure.touch()
    return structure


def a_framework_with_a_net(a=8.0) -> Structure:
    """Zn nodes joined by O-C-O linkers, with the net running straight
    from node to node through each one -- the case the whole feature
    exists for."""
    elements, frac = ["Zn"], [[0.0, 0.0, 0.0]]
    for axis in range(3):
        for t in (0.25, 0.5, 0.75):
            point = [0.0, 0.0, 0.0]
            point[axis] = t
            elements.append("C" if t == 0.5 else "O")
            frac.append(point)
    structure = Structure.from_arrays(Lattice.cubic(a), elements, frac,
                                      space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        structure.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    structure.touch()
    return structure


# =========================================== invisible to chemistry

def test_the_net_is_not_in_the_bond_graph():
    """Left in, a net edge would land in the force field's topology, in
    every coordination number and in every valence check."""
    structure = pcu()
    assert len(bonding.topology_graph(structure).bonds) == 3
    assert bonding.graph(structure).bonds == []
    assert list(bonding.graph(structure).coordination()) == [0]


def test_the_net_does_not_change_the_chemistry_of_a_framework():
    """The same framework with and without a net drawn on it has the
    same bonds, the same coordination and the same fragments."""
    plain = a_framework_with_a_net()
    plain.bonds = [b for b in plain.bonds if b.kind != TOPOLOGY]
    plain.touch()
    netted = a_framework_with_a_net()

    assert ({b.key() for b in bonding.graph(plain).bonds}
            == {b.key() for b in bonding.graph(netted).bonds})
    assert np.array_equal(bonding.graph(plain).coordination(),
                          bonding.graph(netted).coordination())


def test_the_force_field_never_sees_a_net_edge():
    structure = a_framework_with_a_net()
    from xtal.ff.uff import typer
    typing = typer.assign(structure)
    assert len(typing.bond_orders) == len(
        bonding.graph(structure).bonds)


def test_the_net_survives_a_save(tmp_path):
    from xtal.io import read_project_structure, write_project
    path = write_project(pcu(), tmp_path / "net.xtal")
    back = read_project_structure(path)
    assert len([b for b in back.bonds if b.kind == TOPOLOGY]) == 3
    assert len(bonding.topology_graph(back).bonds) == 3


def test_a_net_edge_and_a_bond_can_join_the_same_pair():
    """In a net whose vertices are directly bonded metals they always
    do.  If they collided, drawing the net would be refused and
    deleting it would take the chemistry with it."""
    structure = Structure.from_arrays(
        Lattice.cubic(5.0), ["Zn", "Zn"],
        [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]], space_group="P1")
    assert structure.add_bond(Bond(0, 1, (0, 0, 0)))
    assert structure.add_bond(Bond(0, 1, (0, 0, 0), kind=TOPOLOGY))
    assert len(structure.bonds) == 2

    structure.remove_bond(Bond(0, 1, (0, 0, 0), kind=TOPOLOGY))
    assert [b.kind for b in structure.bonds] == ["explicit"]


# ============================================== the net's invariants

def test_pcu_has_the_coordination_sequence_rcsr_gives_it():
    """6, 18, 38, 66, 102 -- and nothing else is pcu.  The walk is over
    (atom, lattice offset) pairs; counting atoms instead gives
    1, 0, 0, ... for every net there is."""
    net = bonding.topology_graph(pcu())
    assert bonding.coordination_sequence(net, 0, 5) == \
        [6, 18, 38, 66, 102]


def test_pcu_has_the_point_symbol_rcsr_gives_it():
    assert bonding.point_symbol(bonding.topology_graph(pcu()), 0) == \
        "4^12.6^3"


def test_a_square_lattice_is_not_a_cube():
    """The same code on a two-dimensional net: sql is 4, 8, 12, 16 and
    4^4.6^2, which is what pcu becomes when one edge is taken away."""
    structure = pcu()
    structure.bonds = structure.bonds[:2]
    structure.touch()
    net = bonding.topology_graph(structure)
    assert bonding.coordination_sequence(net, 0, 4) == [4, 8, 12, 16]
    assert bonding.point_symbol(net, 0) == "4^4.6^2"


def test_a_net_drawn_over_a_linker_is_still_pcu():
    """The point of the feature: the net edge runs node to node
    straight through a three-atom linker, and the invariants describe
    the net rather than the framework underneath it."""
    net = bonding.topology_graph(a_framework_with_a_net())
    assert bonding.coordination_sequence(net, 0, 4) == [6, 18, 38, 66]
    assert bonding.point_symbol(net, 0) == "4^12.6^3"


def test_an_isolated_vertex_has_an_empty_symbol():
    structure = pcu()
    structure.bonds = []
    structure.touch()
    net = bonding.topology_graph(structure)
    assert bonding.point_symbol(net, 0) == ""
    assert bonding.coordination_sequence(net, 0, 3) == [0]


def test_an_angle_with_no_ring_inside_the_bound_is_starred():
    """RCSR writes it as ``*`` and so does this, rather than claiming a
    ring the search never found."""
    chain = Structure.from_arrays(
        Lattice.from_parameters(5.0, 30.0, 30.0, 90, 90, 90),
        ["Zn"], [[0.0, 0.0, 0.0]], space_group="P1")
    chain.bonds.append(Bond(0, 0, (1, 0, 0), kind=TOPOLOGY))
    chain.touch()
    net = bonding.topology_graph(chain)
    assert "*" in bonding.point_symbol(net, 0)


# ==================================================== symmetry and IO

def test_one_edge_drawn_becomes_the_whole_orbit():
    """The reason it is stored against the asymmetric unit: drawing one
    edge of a pcu net has to draw all six."""
    structure = Structure.from_arrays(
        Lattice.cubic(5.0), ["Zn"], [[0.0, 0.0, 0.0]],
        space_group="Pm-3m")
    document = Document(structure)
    document.add_topology_bond_between(0, 0, (0, 0, 0), (1, 0, 0))
    net = bonding.topology_graph(document.structure)
    # one stored bond, and the cubic group turns it into three edges
    # -- which is six neighbours at the vertex.
    assert len([b for b in document.structure.bonds
                if b.kind == TOPOLOGY]) == 1
    assert list(net.coordination()) == [6]
    assert bonding.point_symbol(net, 0) == "4^12.6^3"


# ======================================================== the picture

def test_the_net_is_drawn_as_its_own_layer():
    model = build_scene(pcu(), ViewSettings())
    assert model.n_topology_edges > 0
    assert model.n_bond_halves == 0
    assert model.topology_radius > model.bond_radius


def test_the_net_runs_over_the_bonds_and_not_in_place_of_them():
    model = build_scene(a_framework_with_a_net(), ViewSettings())
    assert model.n_topology_edges > 0
    assert model.n_bond_halves > 0


def test_the_net_can_be_turned_off():
    settings = ViewSettings()
    settings.show_topology = False
    assert build_scene(pcu(), settings).n_topology_edges == 0


def test_a_net_edge_is_never_completed_at_the_boundary():
    """Its two ends are often whole cells apart -- that is what makes
    it a net edge -- so completing it would scatter ghost atoms
    wherever the box was cut."""
    settings = ViewSettings(boundary="bonded")
    spread = build_scene(a_framework_with_a_net(), settings)
    tidy = build_scene(a_framework_with_a_net(),
                       ViewSettings(boundary="in_range"))
    assert spread.n_topology_edges == tidy.n_topology_edges


def test_selecting_a_net_edge_lights_that_one_up():
    from xtal.core.selection import Selection
    model = build_scene(pcu(), ViewSettings())
    selection = Selection()
    selection.topology = {model.topology_key(0)}
    _atoms, _bonds, net = selection_flags(model, selection)
    assert net.any()
    assert net.sum() < model.n_topology_edges or \
        model.n_topology_edges == 1


# ==================================================== the interaction

def test_the_mode_draws_an_edge_from_two_clicks():
    document = Document(Structure.from_arrays(
        Lattice.cubic(5.0), ["Zn", "Zn"],
        [[0.1, 0.1, 0.1], [0.6, 0.1, 0.1]], space_group="P1"))
    model = build_scene(document.structure, document.view)
    mode = modes.get("topology")
    mode.pending = None

    lattice = document.structure.lattice
    first, second = (lattice.to_cart(s.frac)
                     for s in document.structure.sites)
    ray = (0.0, 0.0, 1.0)
    assert mode.on_click(document, model, modes.ClickEvent(
        (first[0], first[1], -20.0), ray)) == "pick the second vertex"
    message = mode.on_click(document, model, modes.ClickEvent(
        (second[0], second[1], -20.0), ray))
    assert "net edge" in message
    assert len(bonding.topology_graph(document.structure).bonds) == 1
    assert bonding.graph(document.structure).bonds == []

    document.undo()
    assert bonding.topology_graph(document.structure).bonds == []


def test_a_second_edge_can_start_where_the_first_one_ended():
    """Drawing a net is a chain of edges, and the chain runs through
    the atom the last one ended on.

    A net edge is drawn centre to centre, so it covers both of the
    atoms it joins -- and while the mode asked for the edge to win a
    click outright, clicking that shared atom selected the edge just
    drawn instead of starting the next one.  Draw net stopped after one
    edge, which is not a net.
    """
    document = Document(Structure.from_arrays(
        Lattice.cubic(8.0), ["Zn", "Zn", "Zn"],
        [[0.1, 0.1, 0.1], [0.4, 0.1, 0.1], [0.7, 0.1, 0.1]],
        space_group="P1"))
    mode = modes.get("topology")
    mode.pending = None
    ray = (0.0, 0.0, 1.0)

    def click(atom):
        model = build_scene(document.structure, document.view)
        point = document.structure.lattice.to_cart(
            document.structure.sites[atom].frac)
        return mode.on_click(document, model, modes.ClickEvent(
            (point[0], point[1], -20.0), ray))

    click(0)
    assert "net edge" in click(1)
    assert click(1) == "pick the second vertex"
    assert "net edge" in click(2)
    assert len(bonding.topology_graph(document.structure).bonds) == 2


def test_deleting_a_selected_edge_removes_it_and_undoes():
    document = Document(pcu())
    model = build_scene(document.structure, document.view)
    document.select_topology(model.topology_key(0))
    assert "removed 1 net edge" in document.delete_selected_topology()
    assert len(bonding.topology_graph(document.structure).bonds) == 2

    document.undo()
    assert len(bonding.topology_graph(document.structure).bonds) == 3


def test_deleting_nothing_says_so():
    document = Document(pcu())
    assert "no net edges" in document.delete_selected_topology()


def test_the_report_names_the_net():
    document = Document(pcu())
    report = document.net_report()
    assert "6-coordinated" in report
    assert "6, 18, 38, 66" in report
    assert "4^12.6^3" in report


def test_the_report_is_honest_when_there_is_no_net():
    document = Document(Structure.from_arrays(
        Lattice.cubic(5.0), ["Zn"], [[0, 0, 0]], space_group="P1"))
    assert document.net_report() == "no net has been drawn"


def test_a_net_edge_is_only_picked_when_it_is_asked_for():
    """It is thicker than a bond and drawn over it, so on depth alone
    it would win every click near a framework edge and the bond
    underneath could never be selected."""
    from xtalapp.viewport import picking
    model = build_scene(a_framework_with_a_net(), ViewSettings())
    start = np.asarray(model.topology_starts[0])
    end = np.asarray(model.topology_ends[0])
    middle = (start + end) / 2.0
    # Across the edge rather than along it: down its own axis the atom
    # at the far end is in front of it, and which of those a click
    # means is the question the test below this one asks.
    across = np.cross(end - start, [1.0, 1.0, 0.0])
    ray = tuple(across / np.linalg.norm(across))
    origin = middle - 40.0 * np.asarray(ray)

    kind, _index = picking.pick(model, origin, ray,
                                prefer_topology=True)
    assert kind == "topology"
    plain, _ = picking.pick(model, origin, ray)
    assert plain != "topology"


def test_a_net_edge_does_not_hide_the_atoms_it_joins():
    """The edge covers its own two ends -- it is drawn centre to centre
    -- and while it won every click, clicking the atom a net edge
    arrived at selected that edge instead of starting the next one, so
    Draw net stopped after one edge.  A linker in the middle of the
    edge still belongs to the edge: running straight through it is what
    the edge is for."""
    from xtalapp.viewport import picking
    model = build_scene(a_framework_with_a_net(), ViewSettings())
    start = np.asarray(model.topology_starts[0])
    end = np.asarray(model.topology_ends[0])
    along = (end - start) / np.linalg.norm(end - start)

    node = picking.pick(model, start - 40.0 * along, tuple(along),
                        prefer_topology=True)
    assert node[0] == "atom"
    assert model.instance(node[1])[0] in model.topology_key(0)[:2]

    across = np.cross(end - start, [1.0, 1.0, 0.0])
    across /= np.linalg.norm(across)
    linker = (start + end) / 2.0 - 40.0 * across
    assert picking.pick(model, linker, tuple(across),
                        prefer_topology=True)[0] == "topology"


def test_the_kind_round_trips_through_the_bond_record():
    bond = Bond(0, 1, (1, 0, 0), kind=TOPOLOGY)
    assert Bond.from_dict(bond.to_dict()).kind == TOPOLOGY
    assert bond.reverse(
        Structure.from_arrays(Lattice.cubic(5.0), ["Zn", "Zn"],
                              [[0, 0, 0], [0.5, 0, 0]],
                              space_group="P1").space_group
    ).kind == TOPOLOGY


@pytest.mark.parametrize("depth", [0, 1, 3])
def test_the_sequence_stops_where_it_is_told(depth):
    net = bonding.topology_graph(pcu())
    assert len(bonding.coordination_sequence(net, 0, depth)) == depth
