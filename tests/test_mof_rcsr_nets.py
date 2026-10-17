"""The RCSR's 3-periodic nets that PORMAKE never shipped.

sph, the merged nets and 341 others are buildable only because the
catalogue offers them from the RCSR file.  If these regress, a merged
net is not there to build on, or a net is offered twice under one
name, or PORMAKE is handed a file in the wrong origin setting and
draws another graph.
"""

import pytest

from xtal.analysis import rcsr
from xtal.io.cgd import write_cgd_string
from xtal.mof.catalog import (
    RCSR_NETS,
    RCSR_REJECTS,
    Catalog,
    Topology,
    database_root,
    installed,
    rcsr_nets,
)

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="the vendored PORMAKE database is missing")


@pytest.fixture(scope="module")
def offered():
    return {t.name: t for t in rcsr_nets()}


@needs_database
def test_sph_is_buildable_and_its_graph_is_the_rcsr_entry(offered):
    """In the catalogue, with its three kinds of node, written in the
    setting its edges resolve in, and its graph the RCSR's own."""
    sph = Catalog.default().topology("sph")
    assert sph.coordinations == (6, 3, 12)
    assert sph.group == "Fd-3m:2"
    assert not sph.is_layer
    fingerprint = sph.net().fingerprint()
    assert "sph" in rcsr.catalogue().lookup(fingerprint)


@needs_database
def test_an_rcsr_net_pormake_ships_is_not_offered_twice(offered):
    """A name in both catalogues is one net; PORMAKE's file is the one
    kept, and pacs, our own, is not shadowed by anything."""
    pormake = {p.stem for p in (database_root() / "topologies").glob(
        "*.cgd")}
    assert not set(offered) & pormake
    assert "pacs" not in offered
    catalog = Catalog.default()
    assert catalog.topology("pcu").path is not None
    assert RCSR_NETS in catalog.topology_dirs


def test_every_offered_net_is_three_periodic_and_said_to_be(offered):
    assert len(offered) == 341
    assert not set(offered) & RCSR_REJECTS
    for topology in offered.values():
        assert topology._cache["layer"] is False
        assert topology.text.rstrip().endswith("END")


def test_a_net_in_a_group_with_one_origin_is_written_as_it_was():
    """Only groups with two origin choices are expanded to find which
    one the RCSR wrote; the rest are taken at their word."""
    entry = rcsr.nets()["pcu"]
    assert rcsr.as_net(entry) is entry


@pytest.mark.slow
@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_the_rejects_are_still_refused_and_sph_is_read(offered):
    """What ``scripts/rcsr_net_rejects.py`` measured, asked again: each
    reject fails PORMAKE's own validity check as the RCSR embeds it,
    and sph -- in the second origin setting -- does not."""
    from xtal.mof.build import import_pormake

    pormake = import_pormake()
    assert offered["sph"]._pormake(pormake).n_node_types == 3
    for name in sorted(RCSR_REJECTS):
        entry = rcsr.as_net(rcsr.nets()[name])
        text = write_cgd_string([entry]).rstrip() + "\n"
        reject = Topology(name, None, entry.group, (), text)
        with pytest.raises(Exception, match="Invalid cgd"):
            reject._pormake(pormake)


@needs_database
def test_a_fresh_catalogue_keeps_what_its_nets_were_told_and_expands_none(
        monkeypatch):
    """Every MOF builder dialog makes a catalogue, and the picker asks
    every row whether it is a layer.  The RCSR's nets and the merged
    nets are told the answer when they are made; a catalogue's copy
    that dropped it expanded 823 nets on every open -- 5.5 s."""
    Catalog.default().topologies()          # made once, as a dialog's

    def expand(*_args, **_kw):
        raise AssertionError("a net was expanded to ask if it is a layer")

    monkeypatch.setattr(rcsr, "placement", expand)
    fresh = Catalog.default()
    told = [t for t in fresh.topologies() if t.text]
    assert len(told) > 800
    layers = sum(t.is_layer for t in told)
    assert 0 < layers < len(told)
