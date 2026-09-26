"""Peak fitting: the lines, the curve drawn over them, and which of
them indexing reads."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rietx")

from xtal.modules import MODULES  # noqa: E402
from xtal.powder.data import PowderData, Radiation  # noqa: E402
from xtal.powder.peaks import PeakOptions, fit_peaks  # noqa: E402

CU_KA1 = 1.5405929


def _rutile_lines(rutile, top=60.0):
    """Where Bragg puts rutile's first reflections, at Cu Kα1."""
    a, _b, c = rutile.lattice.parameters[:3]
    out = []
    for h, k, m in [(1, 1, 0), (1, 0, 1), (2, 0, 0), (1, 1, 1),
                    (2, 1, 0), (2, 1, 1), (2, 2, 0)]:
        d = 1.0 / np.sqrt((h * h + k * k) / a ** 2 + m * m / c ** 2)
        two_theta = 2.0 * np.degrees(np.arcsin(CU_KA1 / (2.0 * d)))
        if two_theta < top:
            out.append(two_theta)
    return out


@pytest.fixture
def fit(rutile_xy):
    return fit_peaks(PowderData.from_xy(rutile_xy), Radiation("cu"),
                     PeakOptions(finish=60.0))


def test_every_strong_rutile_line_is_found_within_a_hundredth_of_a_degree(
        fit, rutile):
    """The positions are what indexing solves from; one a hundredth
    out is a cell a part in a thousand wrong."""
    used = np.array([p.two_theta for p in fit.peaks if p.use])
    for expected in _rutile_lines(rutile):
        assert np.min(np.abs(used - expected)) < 0.01, expected


def test_a_line_fitted_twice_is_counted_once(fit):
    """RietX's windows overlap at rutile's 101 and both fit it.
    Counted twice, indexing weights that d-spacing double and the
    curve draws the line twice as tall as it is."""
    near = [p for p in fit.peaks if abs(p.two_theta - 36.08) < 0.02
            and p.area > 10]
    assert sum(p.use for p in near) == 1
    assert any("duplicate" in p.flags for p in near)


def test_the_calculated_curve_follows_the_data(fit):
    """What the workbench draws over the pattern.  It is rebuilt from
    the fitted lines with the Kα2 put back, which RietX's own windows
    can cut off."""
    residual = fit.y_obs - fit.y_calc
    assert np.sqrt(np.mean(residual ** 2)) < 0.01 * fit.y_obs.max()


def test_excluding_a_peak_keeps_it_out_of_the_indexing_list(fit):
    """TOPAS's "comment out a peak".  RietX's own ``usable`` is what
    every indexing engine reads, so the untick has to arrive as its
    ``excluded`` flag, not as a row missing from a copy."""
    before = len(fit.for_indexing().usable())
    strongest = max((p for p in fit.peaks if p.use),
                    key=lambda p: p.area)
    strongest.use = False
    lines = fit.for_indexing().usable()
    assert len(lines) == before - 1
    assert all(abs(line.two_theta - strongest.two_theta) > 1e-6
               for line in lines)


def test_fitting_at_named_positions_fits_exactly_those(rutile_xy):
    data = PowderData.from_xy(rutile_xy)
    fit = fit_peaks(data, Radiation("cu"),
                    PeakOptions(positions=(27.44, 54.32)))
    assert [round(p.two_theta, 1) for p in fit.peaks] == [27.4, 54.3]


def test_the_peak_step_runs_headless_and_leaves_its_files(
        rutile_xy, tmp_path, capsys):
    """``xtal run pxrd.peaks`` is the proof the step needs no window:
    the table, peaks.csv and fit.xy, filed in a workspace."""
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "pxrd.peaks", "-p", f"xy={rutile_xy}",
                 "-p", "finish=60", "--workspace", str(workspace),
                 "-q"]) == 0
    assert "Peaks (" in capsys.readouterr().out
    assert list(workspace.rglob("peaks.csv"))
    fitted = next(workspace.rglob("fit.xy"))
    assert np.loadtxt(fitted).shape[1] == 5


def test_the_steps_stay_out_of_the_modules_menu():
    """A step's input is the step before it, which a form in a menu
    cannot hand it; the workbench is the listed way in."""
    pxrd = MODULES.get("pxrd")
    assert [a.name for a in pxrd.actions if a.listed] == \
        ["simulate", "refine"]
    assert not pxrd.action("peaks").listed
    assert pxrd.action("refine").shell == "refine_workbench"


# -- refining ------------------------------------------------------------

def test_refining_keeps_only_the_lines_in_use_and_fits_the_pattern(
        fit, rutile_xy, rutile):
    """Refine is what a person does once the list is the list: an
    unticked line is one they have said is not there."""
    from xtal.powder.peaks import refine_peaks

    weakest = min((p for p in fit.peaks if p.use), key=lambda p: p.area)
    weakest.use = False
    refined = refine_peaks(PowderData.from_xy(rutile_xy), Radiation("cu"),
                           fit, background_terms=6)
    assert len(refined.peaks) == fit.n_used
    assert all(abs(p.two_theta - weakest.two_theta) > 1e-3
               for p in refined.peaks)
    residual = refined.y_obs - refined.y_calc
    assert np.sqrt(np.mean(residual ** 2)) < 0.01 * refined.y_obs.max()
    assert refined.rwp < 0.12
    used = np.array([p.two_theta for p in refined.peaks])
    for expected in _rutile_lines(rutile):
        assert np.min(np.abs(used - expected)) < 0.005, expected
    assert all(0 < p.two_theta_esd < 0.05 for p in refined.peaks
               if p.area > 50)


def test_a_line_added_by_hand_is_fitted_and_reaches_indexing(
        fit, rutile_xy):
    """Where Find missed a line, a person places it; Refine fits it,
    and indexing is told it was placed by hand."""
    from xtal.powder.peaks import refine_peaks

    data = PowderData.from_xy(rutile_xy)
    strongest = max(fit.peaks, key=lambda p: p.area)
    strongest.use = False
    without = refine_peaks(data, Radiation("cu"), fit)
    assert all(abs(p.two_theta - 27.434) > 0.05 for p in without.peaks)
    (placed,) = without.add([27.40], data)
    assert placed.use and placed.origin == "manual"
    refined = refine_peaks(data, Radiation("cu"), without)
    again = min(refined.peaks, key=lambda p: abs(p.two_theta - 27.434))
    assert again.two_theta == pytest.approx(27.434, abs=0.003)
    assert again.origin == "manual"
    line = next(line for line in refined.for_indexing().peaks
                if abs(line.two_theta - again.two_theta) < 1e-9)
    assert line.origin == "manual"


def test_a_line_placed_outside_the_range_is_refused(fit, rutile_xy):
    from xtal.powder.data import PowderError

    with pytest.raises(PowderError, match="outside"):
        fit.add([95.0], PowderData.from_xy(rutile_xy))


def test_each_line_is_drawn_alone_and_one_out_of_use_not_at_all(
        fit, rutile_xy):
    """The overlay: the lines in use sum, over the background, to the
    calculated curve; an unticked line has no curve to draw."""
    from xtal.powder.peaks import refine_peaks

    refined = refine_peaks(PowderData.from_xy(rutile_xy), Radiation("cu"),
                           fit)
    curves = refined.curves()
    # the fit evaluates each line out to 15 widths, the overlay the
    # whole range: the tails beyond differ by less than the noise
    summed = refined.y_background + np.sum(curves, axis=0)
    assert np.max(np.abs(summed - refined.y_calc)) < \
        1e-3 * refined.y_calc.max()
    refined.peaks[0].use = False
    assert refined.curves()[0] is None


def test_refining_with_no_line_in_use_is_refused(fit, rutile_xy):
    from xtal.powder.data import PowderError
    from xtal.powder.peaks import refine_peaks

    for peak in fit.peaks:
        peak.use = False
    with pytest.raises(PowderError, match="tick at least one"):
        refine_peaks(PowderData.from_xy(rutile_xy), Radiation("cu"), fit)


def test_peak_refinement_runs_headless(rutile_xy, tmp_path, capsys):
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "pxrd.refine_peaks", "-p", f"xy={rutile_xy}",
                 "-p", "background_terms=5", "--workspace",
                 str(workspace), "-q"]) == 0
    assert "Rwp" in capsys.readouterr().out
    assert list(workspace.rglob("peaks.csv"))
