"""A triangulated sheet to carbon: xtal.carbon.lattice."""

from collections import Counter

import numpy as np
import pytest

from xtal.carbon import lattice as lt
from xtal.carbon import mesh as ms
from xtal.carbon import surface as sf
from xtal.core import bonding, rings
from xtal.core.structure import Change


@pytest.fixture(scope="module")
def closed():
    """dia's conventional cell at a 10.3 A edge, remeshed and closed."""
    lattice, vertices, edges = sf.net_of("dia")
    frame = sf.skeleton(lattice, vertices, edges, 10.3)
    radius = 0.3 * frame.edge_length
    width = sf.WIDTH_FRACTION * radius
    field = sf.Field(frame, width)
    level = sf.level_for(radius, width)
    return ms.remesh(sf.march(field, level, 1.8), field, level)


def _striped(mesh, periods=3, keep=-0.2):
    """The triangles on one side of a wave across the cell: plenty of
    cut edge, for terminating."""
    middle = (mesh.frac[mesh.tri] + mesh.shift).mean(axis=1) % 1.0
    wave = np.sin(2 * np.pi * periods * middle[:, 0]) + np.sin(
        2 * np.pi * periods * middle[:, 1])
    return lt.prune(lt.largest_piece(lt.dual(mesh.subset(wave > keep))))


def test_the_dual_of_a_closed_mesh_is_all_three_coordinate_carbon(closed):
    """One carbon a triangle, one bond an edge, three bonds a carbon,
    and the bonds about graphene's 1.42 A before anything is
    relaxed."""
    sheet = lt.dual(closed)
    assert sheet.n_atoms == closed.n_triangles
    assert set(sheet.degree()) == {3}
    assert len(sheet.bonds) == 3 * closed.n_triangles // 2
    lengths = np.linalg.norm(sheet.vectors(), axis=1)
    assert lengths.mean() == pytest.approx(1.42, abs=0.05)


def test_a_valence_n_vertex_becomes_an_n_ring(closed):
    """The rings of the carbon, read off its stored graph as primitive
    rings, are exactly the mesh's vertices by valence: the mesh decides
    the five-, six-, seven- and eight-membered rings and the dual only
    reads them off."""
    structure = lt.structure_of(lt.terminate(
        lt.dual(closed), lt.Ratios(), np.random.default_rng(0)))
    valences = Counter(closed.valence().tolist())
    assert rings.census(structure, max_size=max(valences)) == dict(
        sorted(valences.items()))


def test_the_carbon_graph_is_one_component_percolating_in_three_directions(
        closed):
    """Closed or cut into ribbons, what is kept is one piece that runs
    on through all three pairs of faces -- the gap in a model of
    separate fragments."""
    for sheet in (lt.dual(closed), _striped(closed, keep=-0.6)):
        assert lt.pieces(sheet.n_atoms, sheet.bonds) == 1
        assert lt.periodicity(sheet.n_atoms, sheet.bonds,
                              sheet.images) == 3


def test_pruning_leaves_no_carbon_on_one_bond(closed):
    sheet = _striped(closed)
    assert sheet.degree().min() >= 2
    assert (sheet.degree() == 2).any()


def test_the_built_bonds_are_stated_never_perceived(closed):
    """The structure's stored graph is the dual's, bond for bond, and
    reading it perceives nothing: a carbon moved 0.9 A from one it is
    not bonded to stays unbonded to it, where asking for distance --
    what Recalculate Bonds does -- bonds the two."""
    sheet = lt.dual(closed)
    structure = lt.structure_of(lt.terminate(
        sheet, lt.Ratios(hydrogen=0.0), np.random.default_rng(0)))
    graph = bonding.graph(structure)
    pairs = {(b.i, b.j) for b in graph.bonds}
    assert pairs == {tuple(sorted(p)) for p in sheet.bonds.tolist()}

    partners = {j for b in graph.bonds for i, j in ((b.i, b.j),
                                                    (b.j, b.i))
                if i == 0}
    far = next(k for k in range(1, sheet.n_atoms)
               if k not in partners)
    lattice = structure.lattice
    near = lattice.to_cart(structure.sites[far].frac) + [0.9, 0.0, 0.0]
    structure.sites[0].frac = lattice.to_frac(near) % 1.0
    structure.touch(Change.POSITIONS)
    assert {(b.i, b.j) for b in bonding.graph(structure).bonds} == pairs
    structure.clear_perceived()          # as Recalculate Bonds does
    structure.touch(Change.TOPOLOGY)
    perceived = {(b.i, b.j) for b in bonding.graph(structure).bonds}
    assert tuple(sorted((0, far))) in perceived


def test_terminations_hit_the_requested_ratios_within_point_zero_one(
        closed):
    """H/C (the hydroxyls' hydrogen counted), F/C and O/C of the
    result, ethers included, each within 0.01 of what was asked."""
    sheet = _striped(closed)
    ratios = lt.Ratios(hydrogen=0.07, fluorine=0.08, oxygen=0.044)
    done = lt.terminate(sheet, ratios, np.random.default_rng(1))
    assert not done.short
    count = Counter(done.elements)
    carbons = count["C"]
    assert count["H"] / carbons == pytest.approx(0.07, abs=0.01)
    assert count["F"] / carbons == pytest.approx(0.08, abs=0.01)
    assert count["O"] / carbons == pytest.approx(0.044, abs=0.01)
    assert done.bare == done.edge_carbons - sum(done.counts.values())


def test_too_few_edge_carbons_are_said_not_hidden(closed):
    """A closed sheet has no edge at all: every termination asked for
    is short by all of it, and nothing is placed."""
    done = lt.terminate(lt.dual(closed), lt.Ratios(hydrogen=0.1),
                        np.random.default_rng(0))
    assert done.edge_carbons == 0
    assert done.short == {"hydrogen": done.wanted["hydrogen"]}
    assert set(done.elements) == {"C"}


def test_an_ether_oxygen_is_never_next_to_another(closed):
    sheet = _striped(closed)
    done = lt.terminate(sheet, lt.Ratios(oxygen=0.3, ether=1.0,
                                         hydroxyl=0.0, carbonyl=0.0),
                        np.random.default_rng(2))
    ether = {i for i in range(sheet.n_atoms) if done.elements[i] == "O"}
    assert ether
    for a, b in sheet.bonds.tolist():
        assert not (a in ether and b in ether)


def test_each_termination_hangs_at_its_bond_length(closed):
    """H 1.09, F 1.35, C-OH 1.36 with O-H 0.97, C=O 1.23 -- bonded to
    the edge carbon it was put on, whichever cell face is between."""
    sheet = _striped(closed)
    done = lt.terminate(sheet, lt.Ratios(hydrogen=0.05, fluorine=0.05,
                                         oxygen=0.05, ether=0.0,
                                         hydroxyl=0.5, carbonyl=0.5),
                        np.random.default_rng(3))
    structure = lt.structure_of(done)
    expected = {("C", "H"): {lt.C_H}, ("C", "F"): {lt.C_F},
                ("C", "O"): {lt.C_OH, lt.C_O_DOUBLE},
                ("H", "O"): {lt.O_H}}
    seen = set()
    for bond in bonding.graph(structure).bonds:
        pair = tuple(sorted((done.elements[bond.i],
                             done.elements[bond.j])))
        if pair == ("C", "C"):
            continue
        seen.add(pair)
        assert min(abs(bond.distance - d)
                   for d in expected[pair]) < 1e-6, pair
    assert seen == set(expected)
