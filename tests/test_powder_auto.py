"""The automatic run: peaks, indexing, a Pawley fit of every leading
(cell, class), the ranked table, and Rietveld only when the structure
is the crystal the table found."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

pytest.importorskip("rietx")

from xtal.core.lattice import Lattice  # noqa: E402
from xtal.powder.auto import (  # noqa: E402
    AutoOptions,
    AutoRow,
    auto,
    ranked,
    rietveld_match,
)
from xtal.powder.data import PowderData, Radiation  # noqa: E402
from xtal.powder.index import GroupClass, IndexOptions  # noqa: E402

#: Rutile's cell in seconds rather than minutes: the tetragonal
#: primitive lattice only, a 6 A search, the measured zero -- the
#: same bounds the indexing tests use, and why.
SMALL = IndexOptions(bravais=frozenset({"tP"}), longest_axis=6.0,
                     budget=20.0, zero_error=0.0)


def _run(path, structure=None, folder=None, **options):
    return auto(PowderData.from_xy(path), Radiation("cu"),
                AutoOptions(index=SMALL, cells=2, classes=2, **options),
                structure=structure, folder=folder)


@pytest.fixture(scope="module")
def table(rutile_xy_shared, tmp_path_factory):
    folder = tmp_path_factory.mktemp("auto")
    return _run(rutile_xy_shared, folder=folder), folder


def _stretched(structure, factor):
    out = structure.copy()
    a, b, c, *angles = out.lattice.parameters
    out.set_lattice(Lattice.from_parameters(a, b, c * factor, *angles))
    return out


# -- the table -------------------------------------------------------------

@pytest.mark.slow
def test_auto_ranks_rutiles_true_cell_first(table):
    """The pattern was simulated from a = 4.594, c = 2.959 in
    P4_2/mnm; the whole-pattern fit closes indexing's 0.002 A on c."""
    result, _folder = table
    top = result.rows[0]
    assert top.rank == 1 and top.cell_rank == 1
    assert top.bravais == "tP"
    assert top.fit.cell[0] == pytest.approx(4.5940, abs=5e-4)
    assert top.fit.cell[2] == pytest.approx(2.9590, abs=5e-4)
    assert [row.rank for row in result.rows] == \
        list(range(1, len(result.rows) + 1))
    rwps = [row.rwp for row in result.rows]
    assert all(r2 >= r1 * 0.99 for r1, r2 in zip(rwps, rwps[1:],
                                                   strict=False))


@pytest.mark.slow
def test_every_pawley_fit_is_a_row_with_a_folder_of_its_own(table):
    """A row opens the fit it was ranked by; two fits in one folder
    would leave the second's files over the first's."""
    result, folder = table
    folders = [row.folder for row in result.rows]
    assert len(set(folders)) == len(folders) >= 2
    assert all(f.parent == folder for f in folders)
    assert result.peaks is not None and result.cells.rows


@pytest.mark.slow
def test_auto_stops_at_the_pawley_table_unless_asked_to_continue(
        table, rutile_xy_shared, rutile):
    """A table is an answer a person reads; a Rietveld fit is an edit
    to their structure, and is not made without being asked for."""
    result, _folder = table
    assert result.rietveld is None and not result.rietveld_refused
    asked = _run(rutile_xy_shared, structure=rutile, rietveld=True)
    assert asked.rietveld is not None
    assert asked.rietveld_row is asked.rows[0]
    assert asked.rietveld.gof < 1.5
    assert len(asked.rietveld.structure.sites) == len(rutile.sites)


@pytest.mark.slow
def test_auto_does_not_rietveld_a_structure_whose_cell_does_not_match(
        rutile_xy_shared, rutile):
    """3 % on c is the same lattice and another compound more often
    than it is a thermal expansion, and atoms refined against the
    wrong pattern converge somewhere plausible and wrong."""
    result = _run(rutile_xy_shared, structure=_stretched(rutile, 1.03),
                  rietveld=True)
    assert result.rows
    assert result.rietveld is None
    assert "matches no row" in result.rietveld_refused
    assert "c is" in result.rietveld_refused


# -- ranking and matching, without a fit -----------------------------------

def _row(cell_rank, class_rank, rwp, cell=(4.594, 4.594, 2.959, 90, 90,
                                           90), group="P42/mnm",
         classes=()):
    fit = SimpleNamespace(rwp=rwp, gof=1.0, cell=cell, space_group=group,
                          volume=62.4)
    return AutoRow(cell_rank=cell_rank, class_rank=class_rank,
                   bravais="tP", cell=cell, space_group=group,
                   class_symbol="P - - -", groups=(), fit=fit,
                   cell_classes=tuple(classes))


def test_fits_within_a_percent_of_each_other_keep_indexings_order():
    """Rutile's tP cell and the oP one with a and c swapped both fit
    at 9.49 %; ordering them by the fifth digit is ordering by noise."""
    rows = ranked([_row(2, 1, 0.09490), _row(1, 2, 0.09495),
                   _row(1, 1, 0.09499), _row(3, 1, 0.11780),
                   dataclasses.replace(_row(4, 1, 0.0), fit=None,
                                       error="RietX refused")])
    assert [(r.cell_rank, r.class_rank) for r in rows] == \
        [(1, 1), (1, 2), (2, 1), (3, 1), (4, 1)]
    assert [r.rank for r in rows] == [1, 2, 3, 4, 5]


def test_a_class_the_pattern_refutes_keeps_the_structure_out(rutile):
    """The row's own group need not be the structure's -- a pattern
    that shows no absences ranks the class without them first -- but a
    class the screen refuted is ruled out."""
    alive = GroupClass("P - n -", ("P 42 n m", "P 42/m n m"), 500.0,
                       refuted=False)
    row, why = rietveld_match([_row(1, 1, 0.09, group="P4/mmm",
                                    classes=[alive])], rutile)
    assert row is not None and why == ""
    refuted = dataclasses.replace(alive, refuted=True)
    row, why = rietveld_match([_row(1, 1, 0.09, group="P4/mmm",
                                    classes=[refuted])], rutile)
    assert row is None
    assert "refutes" in why and "P - n -" in why


@pytest.mark.slow
def test_the_automatic_step_runs_headless_and_leaves_its_table(
        rutile_xy_shared, tmp_path, capsys):
    """``xtal run pxrd.auto`` takes the Pawley step's questions under
    ``pawley_`` and leaves the ranked table beside a folder per fit."""
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "pxrd.auto", "-p", f"xy={rutile_xy_shared}",
                 "-p", "bravais=tP", "-p", "longest_axis=6",
                 "-p", "budget=10", "-p", "zero_error=0",
                 "-p", "cells=1", "-p", "classes=1",
                 "-p", "pawley_strain=false",
                 "--workspace", str(workspace), "-q"]) == 0
    assert "Pawley fits (" in capsys.readouterr().out
    ranked_csv = next(workspace.rglob("ranked.csv"))
    lines = ranked_csv.read_text().splitlines()
    assert lines[0].startswith("rank,cell_rank,lattice,space_group")
    assert lines[1].split(",")[2] == "tP"
    assert (ranked_csv.parent / "pawley-01").is_dir()
