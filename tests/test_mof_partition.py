"""Which partitioner fits which acs framework, by arithmetic.

The closed form is exact in the deposited pacs frameworks; what these
pin is that the blocks' own lengths feed it the right numbers.  If
they regress, the dialog offers a partitioner that cannot close the
cell, or refuses one that can.
"""

import math
from pathlib import Path

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
    assert all(not f.ok for f in fits[fits.index(tppb):])
    assert math.isinf(tppb.strain)


def test_a_target_pocket_height_asks_for_the_linker_that_gives_it(
        chromium):
    """Inverse design: the span returned, put back through the forward
    form, makes the partitioner layers the pocket apart."""
    tpt = partition.partitioner("tpt")
    wanted = partition.linker_requirement(chromium, tpt, pocket=9.0)
    fit = partition.predict(chromium, "made-up", wanted.value, tpt)
    assert fit.c / 2 == pytest.approx(9.0, abs=1e-9)


def test_the_linker_window_brackets_the_ideal_span(chromium):
    need = partition.linker_requirement(chromium,
                                        partition.partitioner("tpt"))
    assert need.low < need.value < need.high


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


def test_a_short_linker_none_of_the_classic_four_fit_is_offered_tpa(
        catalog):
    """E19 on a nickel trimer is too short for tpt, tpb, tripp and
    tppb alike; tri(4-pyridyl)amine's 4.2 A donor radius closes the
    cell, so a partitioner is still offered."""
    node = partition.node_geometry(catalog.building_block("N589"))
    span = partition.linker_span(catalog.building_block("E19"))
    fits = partition.rank(node, "E19", span)
    ok = [f.partitioner for f in fits if f.ok]
    assert ok == ["tpa"]
    assert {"tpt", "tpb", "tripp", "tppb"}.isdisjoint(ok)


@pytest.mark.skipif(not chem.installed(), reason="needs the build extra")
def test_every_stored_donor_radius_is_what_embedding_measures():
    """The radius is stored so ranking needs no RDKit; it must still be
    what the SMILES builds, or the ranker answers for another molecule."""
    for p in partition.PARTITIONERS:
        assert partition.measure(p.smiles) == pytest.approx(p.radius,
                                                            abs=0.01)


def test_the_compatible_nodes_are_the_open_trimers(catalog):
    """Every shipped open M3O trimer, and none with a terminal water or
    tetrahedral zinc -- and the agent skill names the same nine."""
    from pathlib import Path

    names = {n.name for n in partition.compatible_nodes(catalog)}
    assert names == {"N268", "N536", "N481", "N270", "N92", "N198",
                     "N589", "N433", "N287"}
    skill = Path("xtal/agent/skill/references/mof.md").read_text(
        encoding="utf-8")
    line = skill.split("Compatible nodes:")[1].split("--")[0]
    assert {w.strip(" ,\n") for w in line.split()
            if w.startswith("N")} == names


def _draw(folder, name, catalog):
    """tpt as the dialog saves a drawing: its block, in the
    workspace's partitioners folder."""
    target = folder / partition.DRAWN / f"{name}.xyz"
    target.parent.mkdir(parents=True)
    target.write_text(partition.drawn("tpt").text())
    return Catalog(catalog.topology_dirs, catalog.bb_dirs + (folder,))


@pytest.mark.skipif(not chem.installed(), reason="needs RDKit")
def test_a_partitioner_drawn_in_a_workspace_is_ranked_and_built_from(
        catalog, chromium, tmp_path):
    """Drawn into ``blocks/partitioners``, it is a candidate with the
    radius its nitrogens have, it is what its name builds, and the
    run copies its own file; it is never one of PORMAKE's blocks."""
    from xtal.mof.build import BuildRequest

    blocks = tmp_path / "blocks"
    wider = _draw(blocks, "my-tpt", catalog)
    drawn = partition.partitioner("my-tpt", wider)
    assert drawn.full_name == partition.DRAWN_NAME
    # The picture's embed is unrelaxed, a few hundredths smaller.
    assert drawn.radius == pytest.approx(
        partition.partitioner("tpt").radius, abs=0.1)
    names = [f.partitioner for f in partition.rank(
        chromium, *_bdc(catalog), partition.candidates(wider))]
    assert "my-tpt" in names
    with pytest.raises(KeyError):
        partition.partitioner("my-tpt", catalog)
    with pytest.raises(Exception):  # noqa: B017
        wider.building_block("my-tpt")

    request = BuildRequest.parse("acs", "N536", "E14",
                                 partition="my-tpt")
    rewritten, _, fit = partition.partitioned(request, wider,
                                              tmp_path / "run")
    assert fit.partitioner == "my-tpt"
    assert rewritten.nodes[1] == "pacs-my-tpt"
    copied = tmp_path / "run" / "blocks" / "pacs-my-tpt.xyz"
    assert copied.read_text() == (
        blocks / partition.DRAWN / "my-tpt.xyz").read_text()


def test_a_drawn_file_that_is_no_tritopic_pyridyl_is_not_listed(
        catalog, tmp_path):
    """Three points on carbons are an aryl node, not a partitioner."""
    folder = tmp_path / "blocks" / partition.DRAWN
    folder.mkdir(parents=True)
    (folder / "aryl.xyz").write_text(
        Path(catalog.building_block("N10").path).read_text())
    wider = Catalog(catalog.topology_dirs,
                    catalog.bb_dirs + (tmp_path / "blocks",))
    assert partition.drawn_partitioners(wider) == ()
