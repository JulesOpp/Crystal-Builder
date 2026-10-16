"""An acs framework built partitioned: the pacs frameworks.

The build is a request on ``acs`` rewritten onto our ``pacs`` net (the
``nia-d`` graph PORMAKE can read): the trimer's nine-connected twin,
the partitioner from its SMILES, and a dative joint between them.  If
this regresses, a partitioned build either lands on the wrong net,
leaves open sites bare, or bonds the pyridyl 1.5 A from the metal.
"""

import pytest

from xtal.build import chem
from xtal.core import bonding, p1
from xtal.mof import partition
from xtal.mof.build import BuildRequest, MofError, build
from xtal.mof.catalog import Catalog

needs_rdkit = pytest.mark.skipif(not chem.installed(),
                                 reason="needs the build extra")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    request = BuildRequest.parse("acs", "N589", "E14",
                                 partition=partition.AUTO)
    return build(request, tmp_path_factory.mktemp("pacs"),
                 Catalog.default())


def _neighbours(structure, element):
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    return {i: [cell.elements[j] for j in graph.neighbors(i)]
            for i in range(cell.n_atoms) if cell.elements[i] == element}


@needs_rdkit
@pytest.mark.slow
def test_acs_with_a_partitioner_builds_on_nia_d_with_every_axial_site_bonded(
        built):
    assert built.net_name == "nia-d"
    assert built.net_agrees
    assert "pacs (the nia-d net), as asked" in built.verdict()
    nickel = _neighbours(built.structure, "Ni")
    assert len(nickel) == 6
    assert all(around.count("N") == 1 for around in nickel.values())
    assert "X" not in p1.expand(built.structure).elements


@needs_rdkit
@pytest.mark.slow
def test_a_partitioned_build_bonds_its_metal_nitrogens_at_the_dative_length(
        built):
    """Within the spread a rigid-block build leaves (1.9-2.1 on Ni,
    target 2.10), and nowhere near the 1.5 A two 0.75 A points make."""
    lengths = partition.measured_dative(built.structure)
    assert len(lengths) == 6
    assert min(lengths) > 1.85
    assert max(lengths) < 2.35


@needs_rdkit
@pytest.mark.slow
def test_auto_partition_takes_the_rankers_first_choice(built):
    catalog = Catalog.default()
    node = partition.node_geometry(catalog.building_block("N589"))
    span = partition.linker_span(catalog.building_block("E14"))
    first = partition.rank(node, "E14", span)[0]
    assert built.partition.partitioner == first.partitioner == "tpt"
    assert built.request.partition == "tpt"
    a = built.structure.lattice.parameters[0]
    assert a == pytest.approx(first.a, rel=0.03)


def test_a_partition_on_a_net_other_than_acs_is_refused(tmp_path):
    request = BuildRequest.parse("pcu", "N589", "E14", partition="tpt")
    with pytest.raises(MofError, match="acs framework"):
        build(request, tmp_path, Catalog.default())


def test_a_partitioner_the_arithmetic_refuses_is_not_built(tmp_path):
    """Refused by the ranker's own sentence, before PORMAKE is asked."""
    request = BuildRequest.parse("acs", "N589", "E14", partition="tppb")
    with pytest.raises(MofError, match="too wide for E14"):
        build(request, tmp_path, Catalog.default())


def test_a_trimer_with_no_open_site_cannot_be_partitioned(tmp_path):
    request = BuildRequest.parse("acs", "N86", "E14", partition="tpt")
    with pytest.raises(MofError, match="no open site"):
        build(request, tmp_path, Catalog.default())


def test_the_pacs_net_is_nia_d_under_another_embedding():
    """Read back under the RCSR's name, so the verdict can say so."""
    topology = Catalog.default().topology("pacs")
    assert topology.identify().name == "nia-d"
    assert [s.coordination for s in topology.slots()] == [9, 3, 2, 2]


def test_a_framework_with_no_partitioner_has_no_dative_lengths():
    """MIL-88B's open sites hold waters: nothing to report, and no
    error for asking."""
    from xtal.io.cif_reader import read_cif

    mil88 = read_cif("resources/samples/prepared/MIL-88B.cif")
    assert partition.measured_dative(mil88) == []
