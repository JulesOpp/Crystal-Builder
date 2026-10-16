"""The merged nets of Jiang et al. (Science 2024), as a table.

Every row names two parents, and the table also records what each set
of its edge kinds spans, worked out by decomposing the paper's own
file.  If this regresses, a transcription slip ships, the explorer
draws a net with its parents mixed up, or the builder offers a net
twice.
"""

import random

import pytest

from xtal.mof import merged_nets
from xtal.mof.catalog import Catalog, taken_names

needs_table = pytest.mark.skipif(not merged_nets.table(),
                                 reason="the merged-net table is missing")


@needs_table
def test_the_table_has_every_net_the_paper_gives_a_file_for():
    """353 nets in Data S1; sht (3p-3p) alone has no .cgd in Data
    S6."""
    rows = merged_nets.table()
    assert len(rows) == 352
    assert len({r.name for r in rows}) == 352
    counts = {t: sum(r.type == t for r in rows) for t in merged_nets.TYPES}
    assert counts == {"3p-3p": 142, "3p-2p": 135, "3p-1p": 8,
                      "3p-0p": 67}
    assert set(merged_nets.texts()) == {r.name for r in rows}


@needs_table
def test_every_merged_net_row_decomposes_into_its_listed_parents():
    """The recorded parts of every row hold its parents: by name for
    a 3-periodic parent, by what the other edges span for a layer,
    rod or polyhedron."""
    wrong = {r.name: r.held() for r in merged_nets.table() if r.held()}
    assert wrong == {}


@needs_table
def test_sph_is_spn_and_hxg_with_the_papers_ratio_and_its_mof():
    sph = merged_nets.row("sph")
    assert sph.parents == ("spn", "hxg")
    assert sph.type == "3p-3p"
    assert sph.coordination == (3, 6, 12)
    assert sph.merged_cn == 12
    assert sph.ratio == ("0.577", "0.577")
    assert "Tb-sph-MOF-6" in sph.made
    assert [name for name, _kinds in sph.components()] == ["spn", "hxg"]


@needs_table
def test_a_layer_split_into_two_kinds_of_edge_is_still_its_parent():
    """bok's kgm layer is two symmetry classes of edge, and they span
    it beside bor."""
    bok = merged_nets.row("bok")
    assert bok.held() == []
    (first, one), (second, two) = bok.components()
    assert (first, second) == ("bor", "kgm")
    assert len(two) == 2 and not set(one) & set(two)


@needs_table
def test_a_polyhedron_parent_is_held_by_its_shape():
    nam = merged_nets.row("nam")
    assert nam.parents == ("nbo", "tet")
    assert nam.held() == []
    rest = nam.components()[1][1]
    part = next(p for p in nam.parts if p.kinds == rest)
    assert part.shape == (4, (3,))


@needs_table
def test_the_explorer_filters_by_cluster_connectivity():
    twelve = [r.name for r in merged_nets.table() if r.merged_cn == 12]
    assert "sph" in twelve and "pch" in twelve
    assert all(merged_nets.row(n).merged_cn == 12 for n in twelve)


@needs_table
def test_a_merged_net_the_rcsr_has_is_offered_once_under_its_name():
    """sph is the RCSR's in the catalogue; a net only the paper has
    comes from the paper's file, and none is offered twice."""
    catalog = Catalog.default()
    names = [t.name for t in catalog.topologies()]
    assert len(names) == len(set(names))
    offered = {t.name for t in merged_nets.topologies(taken_names())}
    assert "sph" not in offered and "sph" in names
    new = next(r.name for r in merged_nets.table()
               if r.name not in taken_names()
               and r.name not in merged_nets.REJECTS)
    assert new in offered and new in names


@needs_table
def test_a_drawn_merged_net_carries_one_group_per_parent():
    """The merged vertex is in neither group, so hiding one parent
    leaves the other whole."""
    structure = merged_nets.drawn("sph")
    groups = structure.meta[merged_nets.GROUPS_KEY]
    assert [g[0] for g in groups] == ["spn", "hxg"]
    first, second = (set(g[2]) for g in groups)
    assert first and second and not first & second
    twelve = [n for n, s in enumerate(structure.sites)
              if s.label == "H1"]
    assert twelve and not set(twelve) & (first | second)


@pytest.mark.slow
@needs_table
def test_a_sample_of_rows_decomposes_again_as_recorded():
    """The record is the script's; this re-derives a seeded sample
    (and the paper's six made nets) from the shipped files."""
    from xtal.analysis import components

    rows = list(merged_nets.table())
    sample = random.Random(7).sample(rows, 6) + [
        merged_nets.row(n) for n in ("sph", "pch", "thw", "nam")]
    for r in sample:
        net, kinds = components.entry_kinds(merged_nets.entry(r.name))
        found = {c.kinds: c.name for c in components.components(
            net, kinds)}
        for part in r.parts:
            if part.name:
                assert found[part.kinds] == part.name, r.name
