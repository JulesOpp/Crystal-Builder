"""Supertetrahedral decoration: any 4-c net as an ST-MOF net.

If these regress, a zeolitic MOF is built on a net PORMAKE has read
as some other graph -- faces bonded to faces -- or the catalogue
cannot find ``sod-st`` at all, or a net whose vertices cannot be
tetrahedral is decorated into four faces at one point.
"""

import numpy as np
import pytest

from xtal.analysis import rcsr
from xtal.mof import decorate
from xtal.mof.catalog import (
    Catalog,
    CatalogError,
    database_root,
    installed,
)

#: The zeolites the RCSR draws with a square-planar vertex: on a
#: centre of symmetry (asv, ptt) or flat in a mirror (ssf).
FLAT = ("asv", "ptt", "ssf")


def test_supertetrahedral_mtn_is_the_mil_100_net():
    """MIL-100 is supertetrahedra on mtn, and the RCSR calls its net
    moo: four kinds of trimer for mtn's four kinds of edge, six of
    face.  Named by its invariants, which pick out moo alone; moo's
    canonical form is a minute to compute and says nothing more."""
    topology = decorate.supertetrahedral("mtn")
    assert topology.name == "mtn-st"
    assert sorted(topology.coordinations) == [3] * 6 + [6] * 4
    fingerprint = topology.net().fingerprint()
    assert rcsr.catalogue().lookup(fingerprint) == ("moo",)


def test_a_decorated_net_is_written_in_its_parents_setting():
    """PORMAKE expands what the file says and does not retry, so
    mtn's second origin choice has to be written down."""
    assert decorate.decoration("mtn").group == "Fd-3m:2"
    assert decorate.decoration("sod").group == "Im-3m"


@pytest.mark.slow
def test_every_rcsr_zeolite_decorates_to_a_periodic_net():
    """One connected 3-periodic net each, with a trimer for every
    parent edge and four faces at every vertex -- every zeolite but
    the three whose vertices the RCSR draws flat."""
    for entry in decorate.zeolites():
        if entry.name in FLAT:
            continue
        decorated = decorate.decoration(entry)
        net = rcsr.expand(decorated.entry())
        parent = decorated.parent_net
        assert net.periodicity() == 3, entry.name
        assert len(net.components()) == 1, entry.name
        assert net.n_vertices == (len(parent.edges)
                                  + 4 * parent.n_vertices), entry.name
        assert decorated.margin >= decorate.MIN_MARGIN, entry.name


def test_every_zeolite_code_is_a_four_connected_rcsr_net():
    """A code that is the RCSR's name for some other net (bct, ton)
    must not be offered as a zeolite."""
    for entry in decorate.zeolites():
        assert {node.coordination for node in entry.nodes} == {4}, (
            entry.name)


def test_a_vertex_held_square_planar_is_refused_by_name():
    """On a centre of symmetry a 4-c vertex is flat in its group;
    drawn flat, its four faces fall on one point.  Each is a sentence
    naming the node, never a file PORMAKE reads as something else."""
    for name, said in (("asv", "centre of symmetry"),
                       ("ptt", "centre of symmetry"),
                       ("ssf", "in a plane")):
        with pytest.raises(decorate.DecorationError, match=said):
            decorate.decoration(name)


def test_a_net_that_is_not_four_connected_is_refused():
    with pytest.raises(decorate.DecorationError,
                       match="6-connected"):
        decorate.decoration("pcu")


def test_a_face_sits_on_the_normal_through_its_trimers_circumcentre():
    """Its three edges are equal by construction, so the scaler
    starts from a face the blocks can sit on."""
    decorated = decorate.decoration("lta")
    from xtal.core.lattice import Lattice

    lattice = np.asarray(Lattice.from_parameters(
        *rcsr.nets()["lta"].cell).matrix)
    for face in decorated.faces[:24]:
        here = np.asarray(face.frac) @ lattice
        lengths = [np.linalg.norm(
            (decorated.trimers[k] + np.asarray(s)) @ lattice - here)
            for k, s in face.trimers]
        assert max(lengths) - min(lengths) < 1e-9


@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_pormake_reads_a_decorated_net_by_distance_alone():
    """Every edge shorter than every non-edge: the distance reading
    validates without the nearest-two fallback, on the net that sits
    closest to the margin as well as on sod."""
    from xtal.mof.build import import_pormake
    from xtal.mof.pormake.neighbor_list import NeighborList

    pormake = import_pormake()
    for name in ("sod", "uov"):
        topology = decorate.supertetrahedral(name)
        read = topology._pormake(pormake)
        read.neighbor_list = NeighborList(read.atoms, method="distance")
        assert read.check_validity(), name
        parent = decorate.decoration(name).parent_net
        assert read.n_nodes == (len(parent.edges)
                                + 4 * parent.n_vertices), name


@pytest.mark.skipif(database_root() is None,
                    reason="the vendored PORMAKE database is missing")
def test_the_catalogue_finds_a_decorated_net_by_name():
    """``sod-st`` is asked for by a request, a saved set or an agent,
    so the catalogue makes it -- once -- and lists it nowhere."""
    catalog = Catalog.default()
    made = catalog.topology("sod-st")
    assert made is catalog.topology("sod-st")
    assert made.coordinations == (6, 3)
    assert "sod-st" not in {t.name for t in catalog.topologies()}
    with pytest.raises(CatalogError, match="centre of symmetry"):
        catalog.topology("asv-st")


@pytest.mark.slow
@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_a_supertetrahedral_sod_builds_and_reads_back_as_asked(tmp_path):
    """A Cr trimer at every edge of sod and a triazine on every face:
    the RCSR has no name for the net, so the build is held to the
    decoration's canonical form, and says it is what was asked."""
    from xtal.mof.build import BuildRequest, build

    outcome = build(BuildRequest.parse("sod-st", "0=N536,1=N19", ""),
                    tmp_path, Catalog.default())
    assert outcome.net_agrees
    assert "sod-st, as asked" in outcome.verdict()
    assert outcome.max_rmsd < 0.2
    assert not outcome.overlaps
