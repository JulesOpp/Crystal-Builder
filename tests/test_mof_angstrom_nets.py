"""A net drawn in Angstrom builds as it would at the RCSR's scale.

PORMAKE's scaler normalises its targets to about one but starts from
the file's cell, so a net exported from a crystal -- File > Export
net for Systre, sph-MOF-4's at 11.5 and 19.6 A edges -- started
hundreds of times off and settled with every cluster's edges
relabelled.  If this regresses, a 12-c cluster on such a net fits
1.12 A instead of 0.06 and its carboxylates point between the
linkers, with nothing but the RMSD to say so.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from xtal.io.cgd import read_cgd_string, write_cgd_string
from xtal.mof import catalog
from xtal.mof.catalog import Topology, installed

pytestmark = pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")

NET = Path(__file__).parent / "data" / "sph-mof-4.cgd"


def _topology(text: str) -> Topology:
    entry = read_cgd_string(text).entries[0]
    return Topology(entry.name, None, entry.group,
                    tuple(n.coordination for n in entry.nodes), text)


def _scaled(text: str, factor: float) -> str:
    entry = read_cgd_string(text).entries[0]
    cell = tuple(v * factor for v in entry.cell[:3]) + entry.cell[3:]
    return write_cgd_string([replace(entry, cell=cell)])


def test_a_net_drawn_in_angstrom_is_handed_over_at_a_unit_edge():
    net = _topology(NET.read_text())
    assert net.shortest_edge() == pytest.approx(11.53, abs=0.01)
    unit = _topology(net.unit_text())
    assert unit.shortest_edge() == pytest.approx(1.0)
    assert unit.unit_text() is None


def test_a_net_at_the_rcsr_scale_is_read_as_written():
    """Every shipped net has its shortest edge at one or below; one
    rescaled here would build differently from the file it names."""
    pcu = catalog.Catalog.default().topology("pcu")
    assert pcu.unit_text() is None
    small = _topology(_scaled(NET.read_text(), 1 / 11.53))
    assert small.unit_text() is None


@pytest.mark.slow
def test_a_cluster_on_a_net_drawn_in_angstrom_keeps_its_fit(tmp_path):
    """N419 fits the 12-c slot to 0.11 A as drawn; without the
    rescaling the scaler left it at 1.12."""
    from xtal.mof.build import BuildRequest, build

    folder = tmp_path / "nets"
    folder.mkdir()
    (folder / NET.name).write_text(NET.read_text())
    found = catalog.Catalog.default(topology_dir=str(folder))
    out = build(BuildRequest(topology="sph-mof-4",
                             nodes={0: "N419", 1: "N10", 2: "N386"},
                             orientation="as-found"),
                tmp_path, catalog=found)
    assert out.max_rmsd < 0.2
