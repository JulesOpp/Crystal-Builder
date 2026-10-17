"""A net broken into the nets its kinds of edge span.

If these regress, the merged-net explorer lists parents a net does
not have -- or misses the ones it does -- and a transcription slip in
the merged-net table is held to the wrong answer.
"""

import pytest

from xtal.analysis import components as C
from xtal.analysis import rcsr
from xtal.analysis.topology import Edge, Net


def _named(name):
    net, kinds = C.entry_kinds(rcsr.nets()[name])
    return {c.kinds: c for c in C.components(net, kinds)}


def test_sph_breaks_into_spn_and_hxg():
    """sph is Eddaoudi's merged net of spn and hxg: its 12-to-3 edges
    span one and its 12-to-6 edges the other, and both kinds together
    are sph again."""
    found = _named("sph")
    assert {c.name for c in found.values()} == {"spn", "hxg", "sph"}
    assert found[(0, 1)].name == "sph"


def test_an_edge_transitive_net_has_only_itself_as_a_component():
    found = _named("pcu")
    assert [c.name for c in found.values()] == ["pcu"]


def test_a_component_that_is_not_periodic_is_reported_not_named():
    """nia-d is acs with a partitioner on every channel: the trimer-to-
    trimer edges are acs, and the trimer-to-partitioner ones only join
    each layer's three trimers -- a layer, said, never named."""
    found = _named("nia-d")
    names = {kinds: c.name for kinds, c in found.items()}
    assert "acs" in names.values()
    layer = next(c for c in found.values() if not c.periodic)
    assert layer.periodicity == 2
    assert layer.name == ""
    assert "not a net to name" in layer.sentence()


def test_kinds_from_the_graph_never_split_an_orbit():
    """Without a file, kinds are the colours of an edge's ends: sph's
    two kinds of edge join different kinds of vertex, so the graph
    alone finds both."""
    net, from_file = C.entry_kinds(rcsr.nets()["sph"])
    from_graph = C.edge_kinds(net)
    pairs = set(zip(from_file, from_graph, strict=True))
    assert len(pairs) == len(set(from_file)) == len(set(from_graph))


def test_a_two_connected_vertex_is_folded_into_its_edge():
    """A square with a point on every edge is still sql."""
    edges = (Edge(0, 1, (0, 0, 0)), Edge(1, 0, (1, 0, 0)),
             Edge(0, 2, (0, 0, 0)), Edge(2, 0, (0, 1, 0)))
    net = Net(3, edges)
    folded, count = C._fold(net)
    assert count == 2
    assert folded.n_vertices == 1
    assert sorted(e.image for e in folded.edges) == [(0, 1, 0), (1, 0, 0)]


def test_kinds_must_match_the_edges():
    net, kinds = C.entry_kinds(rcsr.nets()["pcu"])
    with pytest.raises(ValueError, match="kinds for"):
        C.components(net, kinds[:-1])


@pytest.mark.slow
def test_a_built_framework_breaks_into_the_nets_of_its_drawn_edges(
        tmp_path):
    """A pacs build is P1, so its drawn net carries no orbits; the
    graph's own kinds still find acs under the partitioners, as they
    do on the nia-d file."""
    from xtal.mof import installed
    from xtal.mof.build import BuildRequest, build
    from xtal.mof.catalog import Catalog

    if not installed():
        pytest.skip("PORMAKE needs ase")
    outcome = build(BuildRequest.parse("acs", "0=N589", "0-0=E14",
                                       partition="tpt"),
                    tmp_path, Catalog.default())
    net, kinds = C.drawn_kinds(outcome.structure)
    names = {c.name for c in C.components(net, kinds)}
    assert {"acs", "nia-d"} <= names
