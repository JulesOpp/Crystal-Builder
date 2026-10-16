"""Which partitioner fits which acs framework, by arithmetic.

The closed form is exact in the deposited pacs frameworks; what these
pin is that the blocks' own lengths feed it the right numbers.  If
they regress, the dialog offers a partitioner that cannot close the
cell, or refuses one that can.
"""

import math

import pytest

from xtal.build import chem
from xtal.mof import partition
from xtal.mof.catalog import Catalog

#: COD 4134054 (JACS 2020, 10.1021/jacs.9b12924): tpt with BDC on an
#: Mg2V trimer, P6_3/mmc.
REFERENCE_A, REFERENCE_C = 16.790, 14.840


@pytest.fixture(scope="module")
def catalog():
    return Catalog.default()


@pytest.fixture(scope="module")
def chromium(catalog):
    return partition.node_geometry(catalog.building_block("N536"))


def _bdc(catalog):
    block = catalog.building_block("E14")
    return "E14", partition.linker_span(block)


def test_tpt_with_bdc_on_a_trimer_predicts_the_reference_cell(
        catalog, chromium):
    """Cr against a Mg2V crystal, so within 3 % rather than exact: Cr-N
    is 0.15 A shorter than Mg-N."""
    fit = partition.predict(chromium, *_bdc(catalog),
                            partition.partitioner("tpt"))
    assert fit.ok
    assert fit.a == pytest.approx(REFERENCE_A, rel=0.03)
    assert fit.c == pytest.approx(REFERENCE_C, rel=0.03)
    assert partition.PHI_WINDOW[0] < fit.phi < partition.PHI_WINDOW[1]


def test_a_partitioner_too_large_for_the_linker_is_refused_by_name(
        catalog, chromium):
    """tppb pushes the trimers 14 A off the axis and BDC reaches 12:
    the cell cannot close, and the reason says which linker."""
    fits = partition.rank(chromium, *_bdc(catalog))
    tppb = next(f for f in fits if f.partitioner == "tppb")
    assert not tppb.ok
    assert "E14" in tppb.reason
    assert fits[-1] is tppb
    assert math.isinf(tppb.strain)


def test_a_target_pocket_height_asks_for_the_linker_that_gives_it(
        chromium):
    """Inverse design: the span returned, put back through the forward
    form, makes the partitioner layers the pocket apart."""
    tpt = partition.partitioner("tpt")
    wanted = partition.linker_requirement(chromium, tpt, pocket=9.0)
    fit = partition.predict(chromium, "made-up", wanted.span, tpt)
    assert fit.c / 2 == pytest.approx(9.0, abs=1e-9)


def test_the_linker_window_brackets_the_ideal_span(chromium):
    need = partition.linker_requirement(chromium,
                                        partition.partitioner("tpt"))
    assert need.low < need.span < need.high


def test_ranking_linkers_finds_bdc_and_leaves_metal_blocks_out(
        catalog, chromium):
    two = [b for b in catalog.building_blocks()
           if len(b.connections) == 2]
    fits = partition.rank_linkers(chromium,
                                  partition.partitioner("tpt"), two)
    names = [f.linker for f in fits]
    assert "E14" in names
    assert not any(catalog.building_block(n).has_metal for n in names)
    assert all(f.ok for f in fits[:10])


@pytest.mark.skipif(not chem.installed(), reason="needs the build extra")
def test_every_stored_donor_radius_is_what_embedding_measures():
    """The radius is stored so ranking needs no RDKit; it must still be
    what the SMILES builds, or the ranker answers for another molecule."""
    for p in partition.PARTITIONERS:
        assert partition.measure(p.smiles) == pytest.approx(p.radius,
                                                            abs=0.01)
