"""Indexing: the lattices asked for, the cells found, the space groups
their absences allow, and what Stop leaves behind."""

from __future__ import annotations

import pytest

pytest.importorskip("rietx")

from xtal.modules.job import Cancellation  # noqa: E402
from xtal.powder.data import PowderData, PowderError, Radiation  # noqa: E402
from xtal.powder.index import (  # noqa: E402
    IndexOptions,
    _lattices,
    bravais_of_group,
    index,
    parse_bravais,
    parse_space_groups,
)
from xtal.powder.peaks import PeakOptions, fit_peaks  # noqa: E402

#: Rutile's cell is 4.594 x 2.959 A, so a 6 A bound on the search
#: holds it and costs seconds rather than the minutes 50 A does.  The
#: allowance is RietX's own measured one: the 1° default ranks a wrong
#: cell first on this pattern, from 0.5° up.
SMALL = dict(longest_axis=6.0, budget=20.0, zero_error=0.0)


def _peaks(path):
    data = PowderData.from_xy(path)
    fit = fit_peaks(data, Radiation("cu"), PeakOptions())
    window = data.window(fit.two_theta[0], fit.two_theta[-1])
    return fit.for_indexing(), window


def _index(path, **options):
    peak_list, window = _peaks(path)
    cancel = options.pop("cancel", None)
    say = options.pop("say", None)
    return index(peak_list, window, Radiation("cu"),
                 IndexOptions(**options), cancel=cancel, say=say)


@pytest.fixture(scope="module")
def tetragonal(rutile_xy_shared):
    return _index(rutile_xy_shared, bravais=frozenset({"tP", "tI"}),
                  rank_groups=1, **SMALL)


# -- asking ----------------------------------------------------------------

def test_a_bravais_selection_is_the_systems_and_centrings_searched():
    """hP is one of TOPAS's boxes and two of RietX's systems: the
    hexagonal and trigonal-P metrics are one lattice."""
    assert _lattices(parse_bravais("oC, hP tI"), ()) == {
        "orthorhombic": ["C"], "tetragonal": ["I"],
        "hexagonal": ["P"], "trigonal": ["P"]}
    assert len(parse_bravais("all")) == len(parse_bravais("")) == 14


def test_a_space_group_names_the_lattice_it_is_on():
    """An A-centred setting is C-centred on other axes, and C is the
    setting RietX searches."""
    names = "C2221, A 21 2 2, R-3m, P3121, Fm-3m, 136"
    assert [bravais_of_group(g) for g in parse_space_groups(names)] == \
        ["oC", "oC", "hR", "hP", "cF", "tP"]


def test_space_groups_narrow_the_search_to_their_lattices():
    groups = parse_space_groups("C2221, Ccc2")
    assert _lattices(parse_bravais("oP, oC, mP, mC"), groups) == \
        {"orthorhombic": ["C"]}


def test_a_space_group_on_no_ticked_lattice_is_refused_by_name():
    """Silently searching nothing would read as "no cell fits"."""
    with pytest.raises(PowderError, match="oC"):
        _lattices(parse_bravais("tP"), parse_space_groups("C2221"))


def test_an_unknown_lattice_or_group_is_refused_by_name():
    with pytest.raises(PowderError, match="'tX'"):
        parse_bravais("tP, tX")
    with pytest.raises(PowderError, match="'Q9'"):
        parse_space_groups("P1, Q9")


# -- searching -------------------------------------------------------------

@pytest.mark.slow
def test_rutile_indexes_first_as_primitive_tetragonal_at_its_own_cell(
        tetragonal):
    """The pattern was simulated from a = 4.594, c = 2.959.  RietX
    fits c 0.002 A short with a shift it had to assume, so a few
    thousandths is what the search can promise, not one."""
    top = tetragonal.rows[0]
    assert top.bravais == "tP"
    assert top.cell[0] == pytest.approx(4.5940, abs=0.002)
    assert top.cell[2] == pytest.approx(2.9590, abs=0.004)
    assert top.unindexed == 0


@pytest.mark.slow
def test_no_winner_is_invented_where_riet_x_names_none(tetragonal):
    """RietX withholds its best when the engines or the figures of
    merit disagree; a best of ours would be a confident guess."""
    if tetragonal.best is None:
        assert all(row.confidence != "high" for row in tetragonal.rows)
    else:
        assert tetragonal.rows[tetragonal.best].confidence == "high"
    assert all(row.caveats for row in tetragonal.rows
               if row.confidence != "high")


@pytest.mark.slow
def test_the_top_cells_extinction_classes_are_ranked_and_the_rest_not(
        tetragonal):
    top, rest = tetragonal.rows[0], tetragonal.rows[1:]
    assert top.classes
    assert top.space_groups
    assert all(row.classes is None for row in rest)


@pytest.mark.slow
def test_leaving_tetragonal_unticked_never_returns_a_tetragonal_cell(
        rutile_xy_shared):
    """Rutile is pseudo-orthorhombic too, so an orthorhombic search
    finds it -- and must not wander back into the lattice that was
    left unticked."""
    result = _index(rutile_xy_shared, bravais=frozenset({"oP"}),
                    rank_groups=0, longest_axis=6.0, budget=8.0,
                    zero_error=0.0)
    assert result.rows
    assert {row.system for row in result.rows} == {"orthorhombic"}
    assert result.systems_searched == ("orthorhombic",)


@pytest.mark.slow
def test_a_space_group_selection_ranks_only_classes_that_contain_it(
        rutile_xy_shared):
    """Rutile is P4_2/mnm, #136.  A class that cannot hold it is not
    an answer to the question asked."""
    import gemmi

    result = _index(rutile_xy_shared, bravais=frozenset({"tP", "tI"}),
                    space_groups="P42/mnm", rank_groups=1, **SMALL)
    top = result.rows[0]
    assert top.bravais == "tP"
    assert top.classes
    for group_class in top.classes:
        numbers = {gemmi.find_spacegroup_by_name(name).number
                   for name in group_class.space_groups}
        assert 136 in numbers
    assert "P 42/m n m" in top.space_groups


@pytest.mark.slow
def test_stop_returns_the_candidates_reached_so_far(rutile_xy_shared):
    """An indexing run is a minute; Stop is pressed when the list
    already looks right, and must not throw that list away."""
    cancel = Cancellation()

    def say(text):
        if "2 of" in text:              # the first engine has finished
            cancel.cancel()

    result = _index(rutile_xy_shared, bravais=frozenset({"tP"}),
                    rank_groups=3, cancel=cancel, say=say, **SMALL)
    assert result.stopped
    assert result.rows
    assert all(row.classes is None for row in result.rows)


@pytest.mark.slow
def test_the_index_step_runs_headless_and_leaves_its_table(
        rutile_xy_shared, tmp_path, capsys):
    """``xtal run pxrd.index`` fits its own peaks when no window hands
    it any."""
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "pxrd.index", "-p", f"xy={rutile_xy_shared}",
                 "-p", "bravais=tP", "-p", "longest_axis=6",
                 "-p", "budget=10", "-p", "rank_groups=0",
                 "-p", "zero_error=0",
                 "--workspace", str(workspace), "-q"]) == 0
    assert "Cells (" in capsys.readouterr().out
    cells = next(workspace.rglob("cells.csv")).read_text().splitlines()
    assert cells[0].startswith("rank,system,lattice,a,b,c")
    assert cells[1].split(",")[2] == "tP"


def test_cells_sort_by_gof_or_by_gof_over_the_unindexed_lines():
    """TOPAS's two orderings.  The one is so that a cell indexing
    every line is not a division by zero."""
    from xtal.modules.powder import sorted_rows
    from xtal.powder.index import IndexResult, IndexRow

    def row(rank, gof, unindexed):
        return IndexRow(rank=rank, system="cubic", centring="P",
                        cell=(5, 5, 5, 90, 90, 90), cell_esd=(0,) * 6,
                        volume=125, fom=("m20", gof), n_indexed=20,
                        n_lines=20 + unindexed, confidence="low",
                        caveats=(), lebail_rwp=None, found_by=())

    rows = [row(1, 10.0, 0), row(2, 30.0, 4), row(3, 20.0, 1)]
    result = IndexResult(rows=rows, best=None, stopped=False,
                         systems_searched=(), complete={}, wavelength=1.5,
                         two_theta_range=(5, 50))
    assert [r.rank for r in sorted_rows(result, "gof")] == [2, 3, 1]
    assert [r.rank for r in sorted_rows(result, "gof_unindexed")] == \
        [1, 3, 2]
    assert [r.rank for r in sorted_rows(result)] == [1, 2, 3]
    assert rows[1].gof_per_unindexed == pytest.approx(6.0)
