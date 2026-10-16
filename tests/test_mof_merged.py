"""Linker sets for a merged net: one cluster, two kinds of edge.

sph joins a 12-c cluster to a tritopic and a hexatopic, and a set fits
only where both edges close at one scale with every block's shape on
its vertex.  If this regresses the builder suggests pairs that open a
joint or collide, or builds on the RCSR's file, whose 3-c vertex is a
pyramid no flat linker fits.  Numbers are held to Jiang et al.,
Science 386, 659 (2024): sph's edge ratio is 1/sqrt(3) (table S9),
and Tb-sph-MOF-6 is a = 46.10 A on a benzotrithiophene tritopic.
"""

import numpy as np
import pytest

from xtal.build import chem
from xtal.mof import linkers, merged
from xtal.mof.catalog import Catalog, CatalogError, database_root, installed

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="the vendored PORMAKE database is missing")


@pytest.fixture(scope="module")
def catalog():
    return Catalog.default()


@pytest.fixture(scope="module")
def sph(catalog):
    return catalog.topology("sph")


@pytest.fixture(scope="module")
def cluster(catalog):
    # Zr6 stands for a rare-earth hexamer: the same 12-c
    # cuboctahedron of carboxylates, a few tenths of an A smaller.
    return catalog.building_block("N419")


@pytest.fixture(scope="module")
def scanned(sph, cluster):
    return merged.scan(sph, 2, cluster)


@needs_database
def test_flat_linkers_fit_sph_at_the_edge_ratio_the_merged_net_paper_gives(
        scanned):
    """The RCSR draws sph's 3-c vertex as a pyramid; flat, the 12-3
    edge is 1/sqrt(3) of the 12-6, the ratio Systre's model has, and
    the least the shapes allow -- bent, the cluster stops fitting."""
    low, high = scanned.ratio_range(1, 0)
    assert low == pytest.approx(1 / np.sqrt(3), abs=1e-3)
    assert high - low < 0.03
    best = scanned.best
    assert best.lengths[1] / best.lengths[0] == pytest.approx(
        1 / np.sqrt(3), abs=0.01)
    assert best.fits and best.u != (0.0,)


@needs_database
def test_the_rcsr_embedding_of_sph_does_not_take_a_flat_tritopic(sph):
    """What made the re-embedding necessary: at the file's own
    coordinates a triangle is far from the 3-c vertex."""
    free = merged.freedom(sph.entry())
    assert free.dimension == 1
    from xtal.analysis import rcsr

    net, frac = rcsr.placement(free.moved((0.0,)))
    lattice = free.lattice
    vertex = list(net.orbits).index(1)
    steps = [(frac[e.j] + np.asarray(e.image) - frac[e.i]) @ lattice
             if e.i == vertex else
             (frac[e.i] - np.asarray(e.image) - frac[e.j]) @ lattice
             for e in net.edges if vertex in (e.i, e.j)]
    flat = merged.ideal_shapes(3)[0]
    assert merged.shape_rmsd(np.array(steps), flat) > 0.5


@needs_database
def test_sph_asks_for_a_tritopic_and_hexatopic_pair_of_matching_span(
        sph, cluster, catalog, scanned):
    """Anchored on benzotrithiophene (N110, Tb-sph-MOF-6's core), the
    hexatopic asked for is the generated hexakis(biphenyl)benzene; and
    anchored on that, the tritopic asked for takes N110 back."""
    n110 = catalog.building_block("N110")
    asked = merged.edge_requirements(
        sph, 2, cluster, given={1: merged.block_reach(n110)},
        scanned=scanned)
    hexa = asked[0]
    assert hexa.topicity == 6 and hexa.donor == "aryl"
    names = [s.candidate.name for s in linkers.suggest(hexa, catalog)]
    assert "H-benzene-PP-ar" in names
    generated = next(c for c in linkers.stored()
                     if c.name == "H-benzene-PP-ar")
    from xtal.mof.block import CONNECTION_DISTANCE

    back = merged.edge_requirements(
        sph, 2, cluster,
        given={0: generated.value + CONNECTION_DISTANCE},
        scanned=scanned)[1]
    assert back.admits(linkers.profile(n110))


@needs_database
def test_with_nothing_given_a_requirement_starts_where_clusters_part(
        sph, cluster, scanned):
    """sph puts two clusters one 12-6 edge apart, so the smallest set
    is set by room, and nothing is asked below it."""
    asked = merged.edge_requirements(sph, 2, cluster, scanned=scanned)
    floor = scanned.best.floor(cluster)
    rc = merged.block_reach(cluster)
    assert asked[0].high == float("inf")
    assert asked[0].value + 0.75 + rc == pytest.approx(
        floor * scanned.best.lengths[0], rel=1e-6)
    assert "smallest with room" in asked[0].why


@needs_database
def test_a_linker_pair_outside_the_nets_ratio_range_is_refused(
        sph, cluster, catalog):
    """Benzene hexa- and tritopic make both edges alike, where sph
    needs one 1.7 times the other."""
    with pytest.raises(merged.SetError, match=r"allows 1\.\d\d-1\.\d\d"):
        merged.check_set(sph, 2, cluster,
                         {0: catalog.building_block("N5"),
                          1: catalog.building_block("N10")})


@needs_database
def test_a_hexatopic_that_is_not_flat_is_refused_by_its_shape(
        sph, cluster, catalog):
    """N604's six points are a prism, and sph's 6-c vertex a flat
    hexagon wherever its free coordinate goes."""
    with pytest.raises(merged.SetError, match="from the blocks' shapes"):
        merged.check_set(sph, 2, cluster,
                         {0: catalog.building_block("N604"),
                          1: catalog.building_block("N110")})


@pytest.mark.slow
@needs_database
def test_suggested_sets_close_both_edges_and_fit_their_vertices(
        sph, cluster, catalog):
    sets = merged.suggest_sets(sph, 2, cluster, catalog, n=3)
    assert sets
    for found in sets:
        assert found.strain <= merged.SCALE_SLACK
        assert found.worst_fit <= merged.SHAPE_FIT
        assert found.scale >= found.sample.floor(cluster)


@needs_database
def test_a_net_with_one_kind_of_edge_has_no_set_to_work_out(catalog):
    pcu = catalog.topology("pcu")
    six = next(b for b in catalog.fitting(6) if b.has_metal)
    with pytest.raises(merged.SetError, match="one kind of edge"):
        merged.scan(pcu, 0, six)


@needs_database
def test_a_reembedded_net_is_found_by_its_name_and_is_the_same_graph(
        catalog, sph):
    name = merged.spelled("sph", (-0.125,))
    assert name == "sph@-0.1250"
    assert merged.parse(name) == ("sph", (-0.125,))
    moved = catalog.topology(name)
    assert moved.name == name
    assert moved.net().fingerprint() == sph.net().fingerprint()
    assert moved.entry().nodes[1].frac != sph.entry().nodes[1].frac
    assert merged.parse("sod-st-f4") is None


@needs_database
def test_a_move_that_has_the_wrong_count_is_refused_by_name(catalog):
    with pytest.raises(CatalogError, match="free coordinate"):
        catalog.topology("sph@0.1_0.2")


@pytest.mark.slow
@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
@pytest.mark.skipif(not chem.installed(), reason="needs the build extra")
def test_an_sph_build_on_a_hexanuclear_cluster_closes_both_edges(
        tmp_path):
    """The set the requirement found, built where it fits: every
    block on its vertex, nothing overlapping, the net read back as
    sph, and the cell within 5 % of Tb-sph-MOF-6's (Zr6 is smaller
    than Tb6, which is most of the 3 %)."""
    from xtal.mof.build import BuildRequest, build

    blocks = tmp_path / "blocks"
    generated = next(c for c in linkers.stored()
                     if c.name == "H-benzene-PP-ar")
    linkers.write_block(generated, blocks)
    catalog = Catalog.default(also_blocks=[blocks])
    sph = catalog.topology("sph")
    cluster = catalog.building_block("N419")
    found = merged.check_set(
        sph, 2, cluster,
        {0: catalog.building_block("H-benzene-PP-ar"),
         1: catalog.building_block("N110")})
    name = merged.spelled("sph", found.sample.u)
    outcome = build(BuildRequest.parse(
        name, "0=H-benzene-PP-ar,1=N110,2=N419", ""),
        tmp_path, catalog)
    assert outcome.net_agrees
    assert outcome.rcsr_asked == "sph"
    assert not outcome.overlaps
    assert outcome.max_rmsd < 0.1
    a = np.mean(outcome.structure.lattice.parameters[:3])
    assert a == pytest.approx(46.10, rel=0.05)
    assert a == pytest.approx(found.scale * 3.0267, rel=0.02)
