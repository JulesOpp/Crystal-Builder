"""The relatives of the four shipped blocks, built.

Written by script in the shape the first four were cut in -- every
connection point two atoms, 0.75 A from their middle -- so what these
tests pin is that the shape joins onto the node it was written for and
gives the material's own formula, which is the statement that nothing
was lost at a cut and nothing counted twice.

The triazolates leave the triazole's two carbons to the node, because
``MFU4l_Kuratowski`` carries them: a linker that brought them too
would put two carbons where one belongs at every joint.  So the
benzene one is two CH units and no ring -- the ring closes only
across the two joints -- and Zn5Cl4(C6N6H2)3 is the check that it
did.
"""

from collections import Counter

import numpy as np
import pytest

from tests.test_mof_builder import needs_builder, needs_database
from tests.test_mof_targets import needs_layers, needs_library
from xtal.mof import Catalog, database_root
from xtal.mof.attach import MAX_ATTACHMENT_SPAN
from xtal.mof.block import CONNECTION_DISTANCE
from xtal.mof.build import BuildRequest, build
from xtal.mof.catalog import read_topology

KURATOWSKI = "MFU4l_Kuratowski"


@pytest.fixture(scope="module")
def catalog():
    return Catalog.default()


def _build(catalog, folder, topology, nodes, edges=""):
    return build(BuildRequest.parse(topology, nodes, edges), folder,
                 catalog)


def _p1_elements(structure) -> Counter:
    from xtal.core import p1

    return Counter(p1.expand(structure).elements)


def _neighbours(structure) -> dict[int, list[int]]:
    """Every bond, the joints' and the blocks' own -- the stored
    ``bonds`` are the joints alone."""
    from xtal.core import bonding

    graph = bonding.graph(structure)
    return {i: [j for j, _image in graph.neighbors_with_images(i)]
            for i in range(len(structure.sites))}


@needs_database
@needs_library
@pytest.mark.parametrize("name, points, formula", [
    ("bistriazolate_benzene", 2, "C2H2"),
    ("bistriazolate_naphthalene", 2, "C6H4"),
    ("bistriazolate_anthracene", 2, "C10H6"),
    ("tristriazolate_triptycene", 3, "C14H8"),
    ("HHB_benzene_X3", 3, "C6"),
    ("HHB_benzene_X6", 6, "C6"),
    ("CuHTTP_CuS4", 2, "CuS4"),
])
def test_every_relative_is_bidentate_at_the_connection_distance(
        catalog, name, points, formula):
    """The rule the first four are held to, asked of each of these:
    two atoms a point, their middle 0.75 A behind it.  A point cut
    one atom at a time builds with twice the coordination the block
    has; one at a bond length builds every joint twice too long."""
    block = catalog.building_block(name)

    assert block.n_connections == points
    assert block.formula == formula
    for point, members in block.members.items():
        assert len(members) == 2, name
        held = block.positions[list(members)]
        reach = np.linalg.norm(block.positions[point] - held.mean(axis=0))
        assert round(float(reach), 6) == CONNECTION_DISTANCE, name
        assert float(np.linalg.norm(held[0] - held[1])) \
            < MAX_ATTACHMENT_SPAN


@needs_database
@needs_builder
@needs_library
def test_the_benzene_ring_closes_across_the_two_joints(tmp_path,
                                                       catalog):
    """Zn5Cl4(C6N6H2)3 -- MFU-4 with the benzene linker, the
    triazolate carbons from the node and the CH from the linker --
    and every carbon three-connected.  A carbon with two bonds is a
    joint that did not bond both members, and the ring is then open
    on the side nothing reports."""
    built = _build(catalog, tmp_path, "pcu", KURATOWSKI,
                   "bistriazolate_benzene")
    structure = built.structure

    assert built.net_agrees and built.joints == 12
    assert _p1_elements(structure) == Counter(
        {"Zn": 5, "Cl": 4, "N": 18, "C": 18, "H": 6})
    neighbours = _neighbours(structure)
    carbons = [i for i, s in enumerate(structure.sites)
               if s.element == "C"]
    assert all(len(neighbours[i]) == 3 for i in carbons)


@needs_database
@needs_builder
@needs_library
@pytest.mark.parametrize("linker, carbons, hydrogens", [
    ("bistriazolate_naphthalene", 30, 12),
    ("bistriazolate_anthracene", 42, 18),
])
def test_the_longer_acenes_build_mfu4l_s_larger_cousins(
        tmp_path, catalog, linker, carbons, hydrogens):
    built = _build(catalog, tmp_path, "pcu", KURATOWSKI, linker)

    assert built.net_agrees and built.joints == 12
    assert _p1_elements(built.structure) == Counter(
        {"Zn": 5, "Cl": 4, "N": 18, "C": carbons, "H": hydrogens})


@needs_database
@needs_builder
@needs_library
def test_the_triptycene_is_a_three_connected_node_for_the_kernel(
        tmp_path, catalog):
    """rtl is the 3,6-c rutile net: two kernels and four triptycenes
    to the cell, every carbon of every triazole ring bonded."""
    built = _build(catalog, tmp_path, "rtl",
                   f"0=tristriazolate_triptycene,1={KURATOWSKI}")

    assert built.net_agrees and built.joints == 24
    assert _p1_elements(built.structure) == Counter(
        {"Zn": 10, "Cl": 8, "N": 36, "C": 80, "H": 32})


@needs_database
@needs_builder
@needs_library
@needs_layers
@pytest.mark.parametrize("copper, chalcogen", [
    ("CuHTTP_CuS4", "S"),
    ("CuHOTP_CuO4", "O"),
])
def test_hhb_on_hcb_is_cu3_hhb_2(tmp_path, catalog, copper,
                                  chalcogen):
    """Two C6 cores and three Cu to the sheet, each Cu square planar
    on four chalcogens and each chalcogen on one carbon."""
    if copper not in {b.name for b in catalog.building_blocks()}:
        pytest.skip(f"{copper} is not in this checkout")
    built = _build(catalog, tmp_path, "hcb", "HHB_benzene_X3", copper)
    structure = built.structure

    assert built.net_agrees and built.joints == 12
    assert _p1_elements(structure) == Counter(
        {"C": 12, chalcogen: 12, "Cu": 3})
    neighbours = _neighbours(structure)
    element = [s.element for s in structure.sites]
    for i, symbol in enumerate(element):
        if symbol == "Cu":
            assert sorted(element[j] for j in neighbours[i]) == \
                [chalcogen] * 4
        if symbol == chalcogen:
            assert sorted(element[j] for j in neighbours[i]) == \
                ["C", "Cu"]


@needs_database
@needs_builder
@needs_library
@needs_layers
def test_the_six_connected_core_builds_on_hxl(tmp_path, catalog):
    """A point at every bidentate edge makes the core 6-c, and the
    6-c layer is hxl.  Each carbon is a member of two points, so it
    is bonded across two joints."""
    built = _build(catalog, tmp_path, "hxl", "HHB_benzene_X6",
                   "CuHTTP_CuS4")

    assert built.net_agrees and built.joints == 12
    assert _p1_elements(built.structure)["C"] == 6


@needs_database
@pytest.mark.slow
def test_every_pormake_net_is_three_periodic():
    """The fact :func:`xtal.mof.catalog._record_pormake_dimensions`
    records instead of asking, re-derived from the graphs.  If a
    PORMAKE net were a layer, the topology list would file it under
    3D and a spacing given for it would be refused."""
    layers = []
    for path in sorted((database_root() / "topologies").glob("*.cgd")):
        try:
            topology = read_topology(path)
        except Exception:                          # noqa: BLE001
            continue
        if topology.is_layer:
            layers.append(topology.name)
    assert layers == []


@needs_database
@needs_layers
def test_only_our_own_nets_are_filed_as_layers(catalog):
    layers = sorted(t.name for t in catalog.topologies() if t.is_layer)
    assert layers == ["hcb", "hxl", "kgm", "sql"]
