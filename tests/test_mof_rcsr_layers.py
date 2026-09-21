"""The RCSR's layer nets, in the MOF builder's catalogue.

Until 2026-09-21 the builder's layers were four hand-written files in
``xtal/mof/library/nets``; now they are every 2-periodic net the RCSR
has that PORMAKE can build on, 196 of 200, held as text and written
flat in their layer groups by :func:`xtal.analysis.rcsr.as_layer`.
What breaks if these regress is a layered MOF built on the wrong
cell, or a net in the list that no build can ever succeed on.
"""

import pytest

from tests.test_mof_builder import needs_builder, needs_database
from xtal.analysis import rcsr
from xtal.analysis.rcsr import LAYER_C
from xtal.io.cgd import read_cgd_string, write_cgd_string
from xtal.mof import Catalog
from xtal.mof.catalog import (
    PORMAKE_REJECTS,
    RCSR_LAYERS,
    Topology,
    rcsr_layers,
)

#: ``xtal/mof/library/nets/hcb.cgd`` as it was, which the Ni3(HITP)2
#: target was pinned against.
OLD_HCB = """CRYSTAL
  NAME hcb
  GROUP P6/mmm
  CELL 1.73205 1.73205 10.00000 90.0000 90.0000 120.0000
  NODE 1 3  0.33333 0.66667 0.00000
  EDGE  0.33333 0.66667 0.00000   0.66667 0.33333 0.00000
END
"""


@pytest.fixture(scope="module")
def layers():
    return {t.name: t for t in rcsr_layers()}


def _two_d():
    return [e for e in rcsr.nets() if e.dimension == 2 and e.cell]


def test_every_buildable_rcsr_layer_is_offered(layers):
    """All 200 but the four PORMAKE refuses, and the four that used
    to be files among them."""
    assert len(_two_d()) == 200
    assert set(layers) == {e.name for e in _two_d()} - PORMAKE_REJECTS
    assert len(layers) == 196
    assert {"hcb", "hxl", "kgm", "sql"} <= set(layers)


def test_hcb_from_the_rcsr_is_the_file_it_replaced(layers):
    """Group, cell, node and edge, value for value.  If this moves,
    so does every framework built on hcb -- Ni3(HITP)2 first."""
    old = read_cgd_string(OLD_HCB).entries[0]
    new = layers["hcb"].entry()
    assert (new.name, new.group) == (old.name, old.group)
    assert new.cell == pytest.approx(old.cell)
    assert [n.coordination for n in new.nodes] == [3]
    assert new.nodes[0].frac == pytest.approx(old.nodes[0].frac)
    assert [*new.edges[0][0], *new.edges[0][1]] == pytest.approx(
        [*old.edges[0][0], *old.edges[0][1]])


def test_a_layer_keeps_its_plane_group_and_is_known_to_be_a_layer(
        layers):
    """The group the net is in, not the one it is spelled in for
    PORMAKE; and told it is a layer rather than expanded to ask."""
    kgm = layers["kgm"]
    assert kgm.group == "p6mm" and kgm.path is None
    assert kgm._cache["layer"] is True
    assert kgm.entry().group == "P6/mmm"
    assert kgm.entry().cell[2] == LAYER_C


def test_a_layer_ends_on_its_end_line(layers):
    """PORMAKE reads ``readlines()[1:-1]`` -- it drops the last line
    unread, taking it to be ``END``.  A trailing blank line would
    leave ``END`` in the body, to be parsed as a node."""
    for topology in layers.values():
        assert topology.text.endswith("\nEND\n"), topology.name


def test_the_default_catalogue_reads_the_layers_between_pormake_and_yours():
    """A folder after the layers still wins, as every later folder
    does; the layers still win over anything before them."""
    catalog = Catalog.default(topology_dir="/nonexistent")
    dirs = catalog.topology_dirs
    assert RCSR_LAYERS in dirs
    assert dirs.index(RCSR_LAYERS) == len(dirs) - 2


def test_a_users_net_still_replaces_an_rcsr_layer_of_the_same_name(
        tmp_path):
    (tmp_path / "hcb.cgd").write_text(
        OLD_HCB.replace("1.73205 1.73205", "2.00000 2.00000"),
        encoding="utf-8")
    catalog = Catalog((RCSR_LAYERS, tmp_path), ())
    hcb = catalog.topology("hcb")
    assert hcb.path == tmp_path / "hcb.cgd"
    assert hcb.entry().cell[0] == pytest.approx(2.0)


def test_a_missing_rcsr_file_is_a_failure_named_not_a_crash(
        monkeypatch):
    def gone():
        raise rcsr.RcsrError("the RCSR nets are missing")

    monkeypatch.setattr(rcsr, "nets", gone)
    catalog = Catalog((RCSR_LAYERS,), ())
    assert catalog.topologies() == ()
    assert any("layer nets" in f for f in catalog.failures)


@needs_database
@needs_builder
@pytest.mark.slow
def test_every_rcsr_layer_is_recorded_as_a_layer_and_is_one(layers):
    """What :func:`rcsr_layers` tells each topology instead of asking,
    asked: every one builds through PORMAKE, and its graph is free
    along c.  The four rejects are what PORMAKE refuses."""
    from xtal.mof.build import import_pormake
    from xtal.mof.layers import stacking_axis_is_free

    pormake = import_pormake()
    for name, topology in layers.items():
        topology.expanded()
        assert stacking_axis_is_free(topology.net()), name

    for entry in _two_d():
        if entry.name not in PORMAKE_REJECTS:
            continue
        text = write_cgd_string([rcsr.as_layer(entry)]).rstrip() + "\n"
        reject = Topology(entry.name, None, entry.group, (), text)
        with pytest.raises(Exception, match="Invalid cgd"):
            reject._pormake(pormake)
