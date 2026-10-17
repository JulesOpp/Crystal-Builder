"""PORMAKE's reading of a net, with the midpoint reading behind it.

PORMAKE pairs edge centres with nodes by distance, which fails on a
net whose edges differ in length -- a merged net.  If this regresses,
180 of the paper's merged nets and 14 RCSR nets drop out of the
builder again, or a net that always read by distance reads otherwise.
"""

import pytest

from xtal.analysis import rcsr
from xtal.io.cgd import write_cgd_string
from xtal.mof import merged_nets
from xtal.mof.catalog import Topology, installed

pytestmark = pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")


def _topology(entry):
    entry = rcsr.as_net(entry)
    return Topology(entry.name, None, entry.group,
                    tuple(n.coordination for n in entry.nodes),
                    write_cgd_string([entry]).rstrip() + "\n")


def _pormake():
    from xtal.mof.build import import_pormake

    return import_pormake()


def test_a_merged_net_pormake_refused_by_distance_reads_by_midpoints():
    """tam (pcu + she) was an RCSR reject: its two edges are too
    different for one cutoff.  Read now, with every vertex at its
    declared coordination."""
    pormake = _pormake()
    entry = rcsr.nets()["tam"]
    read = _topology(entry)._pormake(pormake)
    plain = type(read).__mro__[2]
    assert plain is pormake.Topology
    with pytest.raises(Exception, match="Invalid cgd"):
        _plain_read(pormake, entry)
    assert read.n_node_types == len(entry.nodes)


def _plain_read(pormake, entry):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "net.cgd"
        path.write_text(write_cgd_string([rcsr.as_net(entry)]))
        return pormake.Topology(str(path))


def test_a_net_that_read_by_distance_reads_exactly_as_it_did():
    pormake = _pormake()
    entry = rcsr.nets()["pcu"]
    ours = _topology(entry)._pormake(pormake)
    theirs = _plain_read(pormake, entry)
    assert [sorted(n.index for n in ns) for ns in ours.neighbor_list] \
        == [sorted(n.index for n in ns) for ns in theirs.neighbor_list]


@pytest.mark.skipif(not merged_nets.table(), reason="no merged nets")
def test_edges_crossing_at_one_midpoint_are_still_refused():
    """thw's 10-c rods along a and c cross at one point, which
    PORMAKE's file holds as one centre: no reading can rescue it."""
    pormake = _pormake()
    assert "thw" in merged_nets.REJECTS
    with pytest.raises(Exception, match="Invalid cgd"):
        _topology(merged_nets.entry("thw"))._pormake(pormake)
