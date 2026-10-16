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


# ---------------------------------------------------------------- windows

def _blocks():
    from xtal.mof.partition import node_geometry

    catalog = Catalog.default()
    return (catalog, node_geometry(catalog.building_block("N536")),
            catalog.building_block("N19"))


def test_sod_has_four_and_six_ring_windows_with_their_site_polygons():
    """Six 4-rings and eight 6-rings a cell -- a truncated
    octahedron's faces -- each flat, with every trimer round it able
    to turn an open site to its centre."""
    kinds = decorate.windows(decorate.decoration("sod"))
    assert [(k.size, k.count) for k in kinds] == [(4, 6), (6, 8)]
    for kind in kinds:
        assert kind.inward == kind.size
        assert kind.pucker < 1e-6
    assert kinds[1].radius > kinds[0].radius


@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_a_window_asks_for_a_pyridyl_with_a_donor_on_every_site():
    """sod's 6-ring on a Cr trimer asks for a hexatopic pyridyl, and
    hexa(4-pyridyl)benzene from the series is what answers -- the one
    sod-st-f6 builds with, Cr-N within 0.1 A of the dative length."""
    from xtal.mof import linkers

    catalog, node, face = _blocks()
    decorated = decorate.decoration("sod")
    placed = decorate.trial(decorated, decorate.plain_blocks(
        decorated.topology(), catalog.building_block("N536"), face))
    six = decorate.windows(decorated)[1]
    wanted = decorate.requirement(decorated, six, node, placed)
    assert (wanted.topicity, wanted.donor) == (6, "pyridyl")
    found = [s.candidate.name for s in linkers.suggest(wanted, catalog)]
    assert "H-benzene-0-py" in found
    said = decorate.sentence(decorated, six, node, placed)
    assert said.startswith("6-ring, 6 sites (6 facing in)")


@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_sod_windows_on_btc_ask_what_the_csda_paper_derives():
    """The cSDA paper's closed forms for sod on regular
    supertetrahedra (Nat. Synth. 3, 33, SI section 3), with In's own
    oxide-to-nitrogen reach for their 4 A: L_T = L_ST / sqrt 2 - C2
    and L_E = L_ST - C2, L_ST = sqrt 3 (L_A + 2.5).  Held to their own
    0.5 A on BTC, the In-sod-ZMOF-102 linker."""
    from xtal.mof.partition import node_geometry

    catalog = Catalog.default()
    trimer, face = catalog.building_block("N92"), catalog.building_block(
        "N10")
    node = node_geometry(trimer)
    decorated = decorate.decoration("sod")
    placed = decorate.trial(decorated, decorate.plain_blocks(
        decorated.topology(), trimer, face))
    reach = node.radius + node.dative
    edge = np.sqrt(3) * (decorate.face_reach(face) + 0.75 + 2.5)
    four, six = decorate.windows(decorated)
    assert abs(decorate.requirement(decorated, four, node, placed).value
               - (edge / np.sqrt(2) - reach)) < 0.5
    assert abs(decorate.requirement(decorated, six, node, placed).value
               - (edge - reach)) < 0.5


@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_sod_st_builds_at_the_cell_of_the_in_sod_zmof():
    """In-sod-ZMOF-102 is In3O trimers and BTC on sod, a = 33.748 A
    (CCDC 2261737); the trial pass, unrelaxed, comes within 1 %.  Its
    supertetrahedra come out regular, which bends T-O-T to 165 degrees,
    where sod's silica analogue stops."""
    catalog = Catalog.default()
    decorated = decorate.decoration("sod")
    placed = decorate.trial(decorated, decorate.plain_blocks(
        decorated.topology(), catalog.building_block("N92"),
        catalog.building_block("N10")))
    a = np.linalg.norm(placed.lattice, axis=1)
    assert np.allclose(a, 33.748, rtol=0.01)
    assert np.all(abs(placed.tot(decorated) - 165) < 3)
    assert np.all(decorate.on_net(decorated).tot(decorated) > 179.9)


def test_filling_both_sod_windows_makes_every_trimer_nine_connected():
    """One site to its 4-ring and two to its 6-rings: the trimer of a
    filled sod is the nine-connected twin S1 makes."""
    decorated = decorate.decoration("sod")
    filled = decorate.filled(decorated, [(4, 1), (6, 1)])
    assert filled.name == "sod-st-f4-f6"
    assert filled.topology().coordinations == (9, 3, 4, 6)
    assert decorate.filled(decorated, [(4, 1)]).topology(
        ).coordinations == (7, 3, 4)


def test_a_filler_on_every_other_site_that_symmetry_relates_is_refused():
    """sod's 4-ring sits on a fourfold axis, which turns the two sites
    a ditopic filler would take onto the two it leaves; written in
    Im-3m it would bond to all four."""
    with pytest.raises(decorate.DecorationError, match="symmetry"):
        decorate.filled(decorate.decoration("sod"), [(4, 2)])


def test_a_window_too_wide_for_pormake_to_read_is_refused():
    """lta's 8-ring filler edges are longer than the faces beside them
    are far: no cutoff tells the two apart, so it is said, not
    written."""
    with pytest.raises(decorate.DecorationError,
                       match="every edge shorter"):
        decorate.filled(decorate.decoration("lta"), [(8, 1)])


def test_a_net_without_that_window_says_which_it_has():
    with pytest.raises(decorate.DecorationError,
                       match="no 8-ring windows"):
        decorate.filled(decorate.decoration("sod"), [(8, 1)])


@pytest.mark.skipif(database_root() is None,
                    reason="the vendored PORMAKE database is missing")
def test_the_catalogue_finds_a_filled_net_by_name():
    made = Catalog.default().topology("sod-st-f6")
    assert made.coordinations == (8, 3, 6)
    assert decorate.parse("sod-st-f4-f6e3") == ("sod", [(4, 1), (6, 3)])
    assert decorate.parse("nia-d") is None


@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_a_filler_that_cannot_span_a_window_is_refused(tmp_path):
    """Tetra(4-pyridyl)ethylene is three times what sod's 4-ring asks
    for on this trimer; built, it put a nitrogen 0.6 A from a
    chromium.  Refused before the build, with both numbers."""
    from xtal.mof.build import BuildRequest, MofError, build

    request = BuildRequest.parse("sod-st-f4", "0=N536,1=N19,"
                                 "2=Q-ethylene-0-py", "")
    with pytest.raises(MofError, match=r"donor radius of 4\.69 A.*"
                                       r"4-rings of sod-st"):
        build(request, tmp_path, Catalog.default())


@pytest.mark.slow
@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_a_filled_sod_states_its_metal_nitrogen_bonds_at_the_dative_length(
        tmp_path):
    """sod's 6-rings filled with hexa(4-pyridyl)benzene on the 8-c twin
    of a Cr trimer: the net read back is the one asked for, every
    filler nitrogen is bonded to a chromium, and none of those bonds is
    far from 2.10 A."""
    from xtal.mof.attach import DATIVE_MN
    from xtal.mof.build import BuildRequest, build
    from xtal.mof.partition import measured_dative

    outcome = build(BuildRequest.parse(
        "sod-st-f6", "0=N536,1=N19,2=H-benzene-0-py", ""),
        tmp_path, Catalog.default())
    assert outcome.net_agrees
    bonds = measured_dative(outcome.structure)
    assert len(bonds) == 6 * 8
    assert max(abs(b - DATIVE_MN["Cr"]) for b in bonds) < 0.15
    assert not outcome.overlaps


def _with_tatb(tmp_path):
    """The catalogue, with TATB written from the series: the tritopic
    face of In-sod-ZMOF-320."""
    from xtal.build import chem
    from xtal.mof import linkers

    if not chem.installed():
        pytest.skip("embedding TATB needs the 'build' extra (RDKit)")
    tatb = next(c for c in linkers.stored()
                if c.name == "T-triazine-P-ar")
    linkers.write_block(tatb, tmp_path / "blocks")
    base = Catalog.default()
    return Catalog(base.topology_dirs, base.bb_dirs + (tmp_path / "blocks",))


@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_the_porphyrin_of_in_sod_zmof_320_is_what_its_four_ring_asks_for(
        tmp_path):
    """In-sod-ZMOF-320 is In3O, TATB and TPyP in every 4-ring
    (CCDC 2261744): the window on an In trimer and TATB suggests the
    porphyrin, and nothing a third of its size."""
    from xtal.mof import linkers
    from xtal.mof.partition import node_geometry

    catalog = _with_tatb(tmp_path)
    trimer = catalog.building_block("N92")
    decorated = decorate.decoration("sod")
    placed = decorate.trial(decorated, decorate.plain_blocks(
        decorated.topology(), trimer,
        catalog.building_block("T-triazine-P-ar")))
    four = decorate.windows(decorated)[0]
    wanted = decorate.requirement(decorated, four, node_geometry(trimer),
                                  placed)
    found = {s.candidate.name for s in linkers.suggest(wanted, catalog)}
    assert "Q-porphyrin-0-py" in found
    assert "Q-ethylene-0-py" not in found


@pytest.mark.slow
@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_tpyp_in_the_four_rings_opens_tot_and_says_to_relax(tmp_path):
    """Measured, not assumed: TPyP widens sod's 4-ring, so T-O-T opens
    from 165 to 172 degrees and the cell comes within 1 % of
    In-sod-ZMOF-320's 57.31 A.  Its rigid placement leaves In-N 0.8 A
    short, and the build says to relax rather than calling it done."""
    from xtal.mof.build import BuildRequest, build

    catalog = _with_tatb(tmp_path)
    outcome = build(BuildRequest.parse(
        "sod-st-f4", "0=N92,1=T-triazine-P-ar,2=Q-porphyrin-0-py", ""),
        tmp_path, catalog)
    assert outcome.net_agrees
    a = np.linalg.norm(outcome.structure.lattice.matrix, axis=1)
    assert np.allclose(a, 57.312, rtol=0.015)
    said = outcome.decoration
    assert "T-O-T as built 17" in said.lines[0]
    assert "relax" in said.warning
    assert said.warning in outcome.structure.meta["warnings"]
