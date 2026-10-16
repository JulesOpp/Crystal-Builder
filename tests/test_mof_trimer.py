"""An M3O trimer with its open sites as connection points.

The nine-connected twin is what a pore-space-partitioned framework is
built from: six carboxylates and three open sites, the last of which a
pyridyl partitioner takes.  If these regress, a pacs build either has
nowhere to put the partitioner or puts it 1.5 A from the metal.
"""

import numpy as np
import pytest

from xtal.mof.attach import DATIVE_MN
from xtal.mof.block import CONNECTION_DISTANCE
from xtal.mof.catalog import Catalog, database_root
from xtal.mof.trimer import (
    Block,
    TrimerError,
    open_site,
    trimers,
    twin_name,
    with_axial_points,
    write_twin,
)

#: Every shipped M3O(CO2)6 trimer with nothing on its open sites.
OPEN_TRIMERS = ("N536", "N481", "N270", "N433", "N92", "N198",
                "N268", "N589")


def _block(name):
    return Block.read(database_root() / "bbs" / f"{name}.xyz")


def test_a_trimer_gains_three_axial_points_on_its_open_site_lines():
    """The three new points are where a pyridyl goes: on the line from
    the oxide through each metal, outward."""
    block = _block("N536")
    twin = with_axial_points(block)
    core = trimers(twin)[0]
    assert len(twin.connections) == 9
    for metal, point in zip(core.metals, twin.connections[-3:],
                            strict=True):
        out = twin.positions[point] - twin.positions[metal]
        out /= np.linalg.norm(out)
        assert out @ open_site(twin, core, metal) > 0.9999
        assert (metal, point, "S") in twin.bonds


def test_an_axial_point_is_the_metals_dative_length_less_the_ligands():
    """A joint's bond is the sum of its two ends' distances, so the
    metal's point sits at M-N less the pyridyl's 0.75 A; at 0.75 the
    metal-nitrogen bond would be built 1.5 A long."""
    for name in ("N536", "N481", "N92"):
        twin = with_axial_points(_block(name))
        core = trimers(twin)[0]
        for metal, point in zip(core.metals, twin.connections[-3:],
                                strict=True):
            reach = np.linalg.norm(twin.positions[point]
                                   - twin.positions[metal])
            expected = DATIVE_MN[twin.symbols[metal]] - CONNECTION_DISTANCE
            assert reach == pytest.approx(expected, abs=1e-6)


def test_every_shipped_open_trimer_has_a_nine_connected_twin(tmp_path):
    """Each twin is read back by the catalogue as a 9-c node, the same
    cluster to the bit with three points more."""
    for name in OPEN_TRIMERS:
        write_twin(database_root() / "bbs" / f"{name}.xyz", tmp_path)
    catalog = Catalog.default(bb_dir=str(tmp_path))
    for name in OPEN_TRIMERS:
        twin = catalog.building_block(twin_name(name))
        original = catalog.building_block(name)
        assert twin.n_connections == 9
        body = [i for i, s in enumerate(original.symbols) if s != "X"]
        assert np.array_equal(twin.positions[body],
                              original.positions[body])


def test_a_trimer_with_a_terminal_ligand_is_refused_unless_stripped():
    """N9's terminal oxygens are part of the cluster it says it is;
    dropping them unasked would build a different chemistry."""
    block = _block("N9")
    with pytest.raises(TrimerError, match="already filled"):
        with_axial_points(block)
    twin = with_axial_points(block, strip=True)
    assert len(twin.connections) == 9
    assert twin.symbols.count("O") == block.symbols.count("O") - 3


def test_a_cluster_whose_own_carboxylate_sits_on_the_site_is_refused():
    """N86's carboxylate leans onto the line opposite the oxide; there
    is no open site, and stripping would cut the cluster."""
    with pytest.raises(TrimerError, match="no open site"):
        with_axial_points(_block("N86"), strip=True)


def test_a_block_without_an_m3o_core_is_refused():
    with pytest.raises(TrimerError, match="no M3O"):
        with_axial_points(_block("N16"))
