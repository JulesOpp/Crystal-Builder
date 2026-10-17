"""Linkers by what they span: the inverse-design engine.

A requirement is a number and a range; the answer is the catalogue's
blocks and a generated isoreticular series, nearest first.  If this
regresses the builder suggests molecules that do not fit, or the
stored series drifts from the SMILES that are supposed to build it.
"""

import pytest

from xtal.build import chem
from xtal.mof import linkers, partition
from xtal.mof.catalog import Catalog

needs_rdkit = pytest.mark.skipif(not chem.installed(),
                                 reason="needs the build extra")


@pytest.fixture(scope="module")
def catalog():
    return Catalog.default()


@pytest.fixture(scope="module")
def nickel(catalog):
    return partition.node_geometry(catalog.building_block("N589"))


def test_a_requirement_finds_bdc_for_the_span_tpt_asks_for(catalog,
                                                           nickel):
    """BDC's ring (E14) and its generated twin both answer what tpt on
    a Ni trimer asks of a linker."""
    need = partition.linker_requirement(nickel,
                                        partition.partitioner("tpt"))
    names = [s.candidate.name for s in
             linkers.suggest(need, catalog, n=1000)]
    assert "E14" in names
    assert "L-P-aryl" in names


def test_a_suggestion_says_how_far_it_is_from_the_requirement(catalog,
                                                              nickel):
    need = partition.linker_requirement(nickel,
                                        partition.partitioner("tpt"))
    found = linkers.suggest(need, catalog, n=5)
    assert found
    misses = [abs(s.miss) for s in found]
    assert misses == sorted(misses)
    assert all(need.low <= s.candidate.value <= need.high
               for s in found)
    assert "from" in found[0].sentence(need)


def test_the_series_holds_the_partitioners_it_was_checked_against():
    """The generated tritopic pyridyls include tpt, tpb, tripp and
    tppb, at the radii the partitioner catalogue stores."""
    stored = {c.name: c for c in linkers.stored()}
    for name, series in (("tpt", "T-triazine-0-py"),
                         ("tpb", "T-benzene-0-py"),
                         ("tripp", "T-pyridine-0-py"),
                         ("tppb", "T-benzene-P-py")):
        assert stored[series].value == pytest.approx(
            partition.partitioner(name).radius, abs=0.01)


def test_a_linker_asks_for_the_partitioner_that_fits_it(catalog,
                                                        nickel):
    """The other reverse: BDC asks for a donor radius tpt has."""
    span = partition.linker_span(catalog.building_block("E14"))
    need = partition.partitioner_requirement(nickel, span)
    names = [s.candidate.name for s in linkers.suggest(need, None)]
    assert "T-triazine-0-py" in names


def test_nothing_in_range_still_names_the_nearest_misses():
    need = linkers.Requirement(2, 1.0, 0.9, 1.1)
    assert linkers.suggest(need, None) == []
    near = linkers.nearest_misses(need, None)
    assert near and near[0].miss > 0


def test_a_metal_block_is_never_a_linker(catalog):
    """CuHTTP's CuS4 has two points and a metal: it is a node."""
    assert linkers.profile(catalog.building_block("CuHTTP_CuS4")) is None
    assert linkers.profile(catalog.building_block("E14")).donor == "aryl"


@needs_rdkit
def test_a_generated_linker_is_written_as_a_block_the_catalogue_reads(
        tmp_path):
    made = next(c for c in linkers.stored() if c.name == "L-PP-aryl")
    linkers.write_block(made, tmp_path)
    block = Catalog.default(bb_dir=str(tmp_path)).building_block(
        "L-PP-aryl")
    assert len(block.connections) == 2
    assert partition.linker_span(block) == pytest.approx(made.value,
                                                         abs=0.01)


@needs_rdkit
@pytest.mark.slow
def test_every_stored_series_value_is_what_its_smiles_embeds():
    """The table is stored so asking needs no RDKit; it must still be
    what the SMILES build.  Re-run scripts/linker_series.py if not."""
    generated = {name: smiles for name, _t, _d, smiles
                 in linkers.series()}
    for c in linkers.stored():
        assert generated[c.name] == c.smiles
        value, formula = linkers.measure_smiles(c.smiles)
        # Relaxed to convergence the table is the same to 0.007 A
        # under RDKit 2026.03 and 2026.09; unconverged, it was 2 A.
        assert value == pytest.approx(c.value, abs=0.05), c.name
        assert formula == c.formula
