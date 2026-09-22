"""The pair search and the long UFF terms, a block at a time.

Evaluated all at once, the van der Waals pairs of a 5184-atom
framework held 66 MB of temporaries every step, and the pair search
behind them held 1.1 million hits to keep half.  Both now run in
blocks.  The block size is a memory knob and nothing else: these tests
shrink it until every block boundary falls somewhere awkward and ask
for the answer the single pass gave.
"""

import numpy as np
import pytest

from xtal.core import neighbors, p1
from xtal.ff.registry import ENGINES
from xtal.ff.uff import terms
from xtal.io import FORMATS


def sorted_pairs(pairs):
    order = np.lexsort((pairs.image[:, 2], pairs.image[:, 1],
                        pairs.image[:, 0], pairs.j, pairs.i))
    return (pairs.i[order], pairs.j[order], pairs.image[order],
            pairs.distance[order], pairs.vector[order])


@pytest.mark.parametrize("subset", [None, [0, 3, 4]])
def test_a_pair_search_in_blocks_finds_the_pairs_of_one_pass(
        quartz, monkeypatch, subset):
    """Every pair once, from both halves of the tie-break, with and
    without a subset.  A pair dropped at a block edge is a contact the
    force field never sees; one kept twice is counted double."""
    cell = p1.expand(quartz)
    whole = sorted_pairs(neighbors.neighbor_pairs(
        cell.frac, quartz.lattice, 6.0, subset=subset))
    monkeypatch.setattr(neighbors, "_SEARCH_BLOCK", 2)
    blocked = sorted_pairs(neighbors.neighbor_pairs(
        cell.frac, quartz.lattice, 6.0, subset=subset))
    for a, b in zip(whole, blocked, strict=True):
        assert np.array_equal(a, b)


def test_uff_in_blocks_gives_the_energy_and_forces_of_one_pass(
        monkeypatch):
    """MFU-4l's torsions and van der Waals pairs, seven terms at a
    time.  Only the order of the sums changes, so the answer may move
    in its last digits and nowhere else."""
    structure = FORMATS.read("resources/samples/MFU4l.cif")
    positions = p1.expand(structure).cart
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    whole = ENGINES.build("uff", structure).compute(positions, matrix)
    monkeypatch.setattr(terms, "_TERM_BLOCK", 7)
    blocked = ENGINES.build("uff", structure).compute(positions, matrix)
    assert blocked.energy == pytest.approx(whole.energy, rel=1e-12)
    assert np.allclose(blocked.forces, whole.forces,
                       rtol=1e-10, atol=1e-10)


def test_no_block_is_empty_and_none_is_missed():
    for n in (0, 1, 7, terms._TERM_BLOCK, terms._TERM_BLOCK + 1):
        covered = [i for part in terms._blocks(n)
                   for i in range(n)[part]]
        assert covered == list(range(n))
        assert all(part.stop > part.start for part in terms._blocks(n))
