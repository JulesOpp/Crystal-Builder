"""Pawley: a cell and a space group fitted to the whole pattern, and
whether that cell belongs on a structure."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

pytest.importorskip("rietx")

from xtal.powder.data import PowderData, PowderError, Radiation  # noqa: E402
from xtal.powder.pawley import (  # noqa: E402
    PawleyOptions,
    cell_fits_structure,
    parse_cell,
    pawley,
)

#: Where indexing put rutile (a 0.001 A, c 0.002 A out): what a
#: Pawley fit is handed in practice.
INDEXED = "4.5948 4.5948 2.9572"


@pytest.fixture(scope="module")
def fit(rutile_xy_shared):
    return pawley(PowderData.from_xy(rutile_xy_shared), Radiation("cu"),
                  INDEXED, "P42/mnm")


def test_pawley_on_rutile_recovers_the_cell_it_was_simulated_from(fit):
    """a = 4.5940, c = 2.9590.  Indexing was a part in a thousand out
    on c; the whole pattern is what closes that."""
    assert fit.converged
    assert fit.cell[0] == pytest.approx(4.5940, abs=3e-4)
    assert fit.cell[1] == fit.cell[0]
    assert fit.cell[2] == pytest.approx(2.9590, abs=3e-4)
    assert fit.cell[3:] == (90.0, 90.0, 90.0)
    assert 0 < fit.cell_esd[0] < 1e-3
    assert fit.gof < 1.5


def test_the_curves_are_the_fit_and_the_ticks_its_reflections(fit):
    residual = fit.y_obs - fit.y_calc
    assert np.sqrt(np.mean(residual ** 2)) < 0.02 * fit.y_obs.max()
    assert len(fit.ticks) == len(fit.reflections) > 10


def test_every_reflection_is_one_the_group_allows(fit):
    """P4_2/mnm forbids 0kl with k + l odd: 100 and 001 are absent, and
    fitting an intensity there would let noise into the list."""
    hkls = {r.hkl for r in fit.reflections}
    assert (1, 1, 0) in hkls
    assert (1, 0, 0) not in hkls
    assert (0, 0, 1) not in hkls


def test_a_cell_is_three_lengths_or_six_numbers():
    assert parse_cell("4.59 4.59 2.96") == (4.59, 4.59, 2.96, 90, 90, 90)
    assert parse_cell("5, 6, 7, 90, 101.5, 90")[4] == 101.5
    for bad in ("4.59 4.59", "a b c", "4 4 4 90 90 190", "0 1 1"):
        with pytest.raises(PowderError):
            parse_cell(bad)


def test_a_space_group_nobody_knows_is_refused(rutile_xy_shared):
    with pytest.raises(PowderError, match="'Q42'"):
        pawley(PowderData.from_xy(rutile_xy_shared), Radiation("cu"),
               INDEXED, "Q42")


def test_a_capillary_never_frees_specimen_displacement():
    """Displacement is a flat plate standing proud of the goniometer
    axis; a capillary has none, and freeing it would only trade with
    the zero error."""
    options = PawleyOptions(displacement=True)
    assert "displacement" in options.free(Radiation("cu"))
    assert "displacement" not in options.free(
        Radiation("synchrotron", wavelength=0.8))


def test_the_cell_fits_a_structure_only_in_the_same_setting(
        fit, rutile, quartz):
    """Coordinates are kept when a cell is applied, so the axes must
    be the structure's own: a cell indexed with c first passes every
    figure of merit and would shear the atoms."""
    assert cell_fits_structure(fit, rutile) == ""
    assert "hexagonal" in cell_fits_structure(fit, quartz) or \
        "trigonal" in cell_fits_structure(fit, quartz)
    turned = dataclasses.replace(
        fit, cell=(fit.cell[2], fit.cell[0], fit.cell[1], 90, 90, 90))
    assert "a is" in cell_fits_structure(turned, rutile)


def test_the_pawley_step_runs_headless_and_leaves_its_reflections(
        rutile_xy_shared, tmp_path, capsys):
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "pxrd.pawley", "-p", f"xy={rutile_xy_shared}",
                 "-p", f"cell={INDEXED}", "-p", "space_group=136",
                 "--workspace", str(workspace), "-q"]) == 0
    assert "Reflections (" in capsys.readouterr().out
    lines = next(workspace.rglob("reflections.csv")).read_text() \
        .splitlines()
    assert lines[0] == "h,k,l,d,two_theta,multiplicity,intensity"
    assert lines[1].startswith("1,1,0,")
    assert np.loadtxt(next(workspace.rglob("fit.xy"))).shape[1] == 5


def test_a_pawley_step_with_no_cell_says_what_it_needs(rutile_xy_shared):
    from xtal.modules import powder as steps
    from xtal.modules.job import Job

    result = steps.run_pawley(Job(params={"xy": str(rutile_xy_shared)}))
    assert not result.ok
    assert "cell and a space group" in result.message


def test_a_held_cell_number_stays_where_it_was_given(rutile_xy_shared):
    """TOPAS's ``c 2.9572`` beside ``a @ 4.5948``: c is held, a still
    refines."""
    from xtal.modules.powder import refined_notes

    fit = pawley(PowderData.from_xy(rutile_xy_shared), Radiation("cu"),
                 INDEXED, "P42/mnm", PawleyOptions(hold_cell=("c",)))
    assert fit.cell[2] == pytest.approx(2.9572, abs=1e-9)
    assert fit.cell[0] == pytest.approx(4.5940, abs=1e-3)
    notes = refined_notes(fit)
    assert "a" in notes and "c" not in notes


def test_holding_reads_the_greek_letters_and_the_whole_cell():
    from xtal.powder.pawley import parse_hold

    assert parse_hold("") == ()
    assert parse_hold("a, β") == ("a", "beta")
    assert parse_hold("cell") == ("a", "b", "c", "alpha", "beta",
                                  "gamma")
    with pytest.raises(PowderError, match="'d'"):
        parse_hold("d")


def test_a_fit_lists_the_numbers_each_box_refined(fit):
    """Strain broadening freed is a Lorentzian and a Gaussian term;
    both are written beside the box, with their esds."""
    from xtal.modules.powder import refined_notes

    notes = refined_notes(fit)
    assert notes["strain"].startswith("L ") and " G " in notes["strain"]
    assert notes["size"].startswith("L ")
    assert "mm" in notes["displacement"]
    assert "zero" not in notes                  # held by default
    assert notes["a"].startswith("4.59")


def test_le_bail_over_the_same_plan_recovers_the_same_cell(
        rutile_xy_shared):
    """Le Bail is the Pawley step's other method: the intensities
    shared out from the observed counts rather than refined, the cell
    and the boxes the same."""
    fit = pawley(PowderData.from_xy(rutile_xy_shared), Radiation("cu"),
                 INDEXED, "P42/mnm", PawleyOptions(method="lebail"))
    assert fit.method == "lebail" and fit.method_name == "Le Bail"
    assert fit.cell[0] == pytest.approx(4.5940, abs=5e-4)
    assert fit.cell[2] == pytest.approx(2.9590, abs=5e-4)
    assert fit.rwp < 0.2


def test_a_method_that_is_neither_is_refused(rutile_xy_shared):
    with pytest.raises(PowderError, match="not a method"):
        pawley(PowderData.from_xy(rutile_xy_shared), Radiation("cu"),
               INDEXED, "P42/mnm", PawleyOptions(method="rietveld"))
