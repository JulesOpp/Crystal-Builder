"""The grid's own surface-area and volume runs, without Zeo++.

These are the "(faster)" twins of the Zeo++ entries.  What is pinned
here is what the run adds to :mod:`xtal.analysis.voids`: the report is
Zeo++'s shape with the grid's note, a borderline window is said above
the numbers, the radii are the ones asked for (a file read rather than
refused), and a disordered crystal never reaches the grid.  The numbers
themselves are pinned against Zeo++ in ``test_voids.py``.
"""

from pathlib import Path

import pytest

from xtal.analysis import porosity
from xtal.io.cif_reader import read_cif
from xtal.modules import Job, poregrid

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


def run(entry, structure, **params):
    return entry(Job(structure=structure, params=params, label="test"))


def sample(name):
    return read_cif(SAMPLES / f"{name}.cif")


def test_the_faster_area_comes_back_in_the_zeopp_report_shape():
    result = run(poregrid.surface_area, sample("MOF-5"))
    assert result.ok
    table = result.report.tables[0]
    asa = next(r for r in table.rows if r.symbol == "ASA")
    # Zeo++: 3644 m^2/g.
    assert float(asa.value) == pytest.approx(3644, rel=0.02)
    assert "grid" in table.note
    assert "Monte Carlo" not in table.note
    assert "Nitrogen" in result.message


def test_the_faster_volume_is_the_occupiable_one_by_default_and_draws():
    result = run(poregrid.volume, sample("MOF-5"))
    rows = result.report.tables[0].rows
    assert rows[0].symbol == "POAV"
    assert "-volpo" in result.report.tables[0].note
    assert result.overlay is not None
    assert result.overlay.n_surface_faces > 1000


def test_the_centre_s_volume_says_so_and_can_skip_the_drawing():
    result = run(poregrid.volume, sample("MOF-5"), occupiable=False,
                 draw=False)
    assert result.report.tables[0].rows[0].symbol == "AV"
    assert result.overlay is None


def test_a_borderline_window_is_said_above_the_numbers():
    """UiO-66 on a 0.3 A grid cannot tell whether its windows are open;
    a table that quoted a volume without saying so would be quoting
    the grid's luck."""
    result = run(poregrid.volume, sample("UIO66"), spacing=0.3,
                 draw=False)
    first = result.report.tables[0].rows[0]
    assert first.label == "Resolution"
    assert "Pore diameters" in first.note


def test_a_clear_answer_carries_no_warning():
    result = run(poregrid.volume, sample("MOF-5"), draw=False)
    assert all(r.label != "Resolution"
               for r in result.report.tables[0].rows)


def test_a_radii_file_is_read_rather_than_refused(tmp_path, rutile):
    """Zeo++'s entries draw no surface from a radii file, because the
    grid could not match Zeo++'s reading of it.  Here the grid is the
    whole calculation, so the file is simply the table."""
    table = tmp_path / "mine.rad"
    table.write_text("# small atoms\nTi 0.5\n\nO 0.5\n")
    small = run(poregrid.volume, rutile, radii_file=str(table),
                gas="custom", probe_radius=0.5, draw=False)
    usual = run(poregrid.volume, rutile, gas="custom", probe_radius=0.5,
                draw=False)
    assert "mine.rad" in small.report.note
    assert (small.report.tables[0].rows[1].value
            != usual.report.tables[0].rows[1].value)


def test_a_radii_file_missing_an_element_is_refused_by_name(tmp_path,
                                                            rutile):
    table = tmp_path / "mine.rad"
    table.write_text("Ti 1.0\n")
    with pytest.raises(ValueError, match="no radius for O"):
        run(poregrid.surface_area, rutile, radii_file=str(table))


def test_a_radii_file_line_that_is_not_two_columns_is_refused():
    with pytest.raises(ValueError, match="line 2"):
        poregrid.read_radii("Ti 1.0\nO\n")


def test_a_disordered_structure_never_reaches_the_grid(rutile,
                                                       monkeypatch):
    rutile.sites[1].occupancy = 0.5
    from xtal.analysis import grid
    monkeypatch.setattr(grid, "distance_grid", pytest.fail)
    with pytest.raises(ValueError, match="partially occupied"):
        run(poregrid.surface_area, rutile)


def test_the_radii_are_the_ones_asked_for(rutile):
    assert poregrid._radii(Job(structure=rutile, params={}))[0] \
        is porosity.zeo_radius
