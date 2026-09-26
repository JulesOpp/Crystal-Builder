"""Rietveld: a structure's own atoms fitted to a measured pattern, and
what may and may not come back changed."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rietx")

from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.structure import Bond, Structure  # noqa: E402
from xtal.modules.job import Cancellation, Job  # noqa: E402
from xtal.powder.data import (  # noqa: E402
    PowderData,
    PowderError,
    PowderStopped,
    Radiation,
)
from xtal.powder.rietveld import (  # noqa: E402
    RietveldOptions,
    parse_axis,
    rietveld,
)

#: Where the pattern put rutile's oxygen: 4f, (x, x, 0).
X_TRUE = 0.3053


def _rutile(x=0.29, dummy=False):
    """Rutile with its oxygen pulled 0.06 A along its free direction,
    a drawn Ti-O bond, and optionally a marker at a general position."""
    elements = ["Ti", "O"] + (["X"] if dummy else [])
    frac = [[0.0, 0.0, 0.0], [x, x, 0.0]] + (
        [[0.1, 0.2, 0.3]] if dummy else [])
    structure = Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        elements, frac, space_group="P4_2/mnm")
    structure.add_bond(Bond(0, 1))
    return structure


@pytest.fixture(scope="module")
def data(rutile_xy_shared):
    return PowderData.from_xy(rutile_xy_shared)


@pytest.fixture(scope="module")
def fitted(data):
    frames = []
    structure = _rutile(dummy=True)
    fit = rietveld(structure, data, Radiation("cu"), on_frame=frames.append,
                   frame_interval=0.0)
    return structure, fit, frames


def test_rietveld_on_a_displaced_rutile_returns_oxygen_to_its_site(fitted):
    structure, fit, _frames = fitted
    assert fit.converged
    assert fit.structure.sites[1].frac[0] == pytest.approx(X_TRUE,
                                                           abs=2e-3)
    # along the site's free direction only: still on (x, x, 0)
    assert fit.structure.sites[1].frac[0] == \
        pytest.approx(fit.structure.sites[1].frac[1])
    assert fit.structure.sites[1].frac[2] == 0.0
    assert fit.cell[0] == pytest.approx(4.5940, abs=3e-4)
    assert fit.gof < 1.5
    assert fit.moved == pytest.approx((X_TRUE - 0.29) * 4.594
                                      * np.sqrt(2), abs=0.02)


def test_a_rietveld_run_never_adds_removes_or_rebonds_atoms(fitted):
    structure, fit, _frames = fitted
    assert len(fit.structure.sites) == len(structure.sites)
    assert [s.element for s in fit.structure.sites] == \
        [s.element for s in structure.sites]
    assert fit.structure.bonds == structure.bonds
    # the structure given is not the one changed
    assert structure.sites[1].frac[0] == 0.29


def test_dummy_atoms_are_held_back_and_returned_unmoved(fitted):
    """A marker is not a scatterer: it never reaches RietX, and it
    comes back at the fractional coordinates it was left at."""
    structure, fit, _frames = fitted
    assert fit.structure.sites[2].element == "X"
    assert fit.structure.sites[2].frac == pytest.approx([0.1, 0.2, 0.3])
    assert len(fit.atom_labels) == 2


def test_frames_carry_every_site_and_end_where_the_fit_ends(fitted):
    """A frame goes straight to ``preview_positions``, so it has a row
    for every site; the last is within a step of the fit's answer,
    because a frame is the shadow model set to the free values the fit
    had reached.  Within a step and not at it: frames are throttled,
    and the final evaluation may fall between two."""
    structure, fit, frames = fitted
    assert frames
    last = frames[-1]
    assert last.frac.shape == (3, 3)
    assert last.frac[2] == pytest.approx([0.1, 0.2, 0.3])
    assert last.frac[1] == pytest.approx(fit.structure.sites[1].frac,
                                         abs=1e-3)
    assert last.y_calc == pytest.approx(fit.y_calc, rel=1e-2)
    # the atoms are seen moving: not every frame is the start
    assert frames[0].frac[1][0] != pytest.approx(last.frac[1][0])
    assert last.matrix.shape == (3, 3)


def test_stopping_a_rietveld_run_is_refused_as_a_result(data):
    """Half a refinement is not a structure: Stop raises, and putting
    the atoms back is the window's."""
    cancel = Cancellation()
    cancel.cancel()
    with pytest.raises(PowderStopped):
        rietveld(_rutile(), data, Radiation("cu"), cancel=cancel)


def test_a_held_cell_number_is_not_refined(data):
    fit = rietveld(_rutile(), data, Radiation("cu"),
                   RietveldOptions(hold_cell=("c",)))
    assert fit.cell[2] == 2.9590
    assert "phases.0.cell.c" not in fit.refined
    assert "phases.0.cell.a" in fit.refined


def test_one_of_rietxs_own_plans_can_stand_in_for_the_boxes(data):
    fit = rietveld(_rutile(), data, Radiation("cu"),
                   RietveldOptions(plan="mccusker_structural"))
    assert fit.structure.sites[1].frac[0] == pytest.approx(X_TRUE,
                                                           abs=2e-3)
    with pytest.raises(PowderError, match="nonsense"):
        rietveld(_rutile(), data, Radiation("cu"),
                 RietveldOptions(plan="nonsense"))


def test_a_preferred_orientation_axis_is_three_integers():
    assert parse_axis("") is None
    assert parse_axis("0 0 1") == (0, 0, 1)
    assert parse_axis("110") == (1, 1, 0)
    assert parse_axis("1, -1, 0") == (1, -1, 0)
    for bad in ("0 0 0", "a b c", "1 2"):
        with pytest.raises(PowderError):
            parse_axis(bad)


def test_xtal_run_rietveld_needs_a_structure_and_says_so(rutile_xy_shared):
    from xtal.modules.powder import run_rietveld

    result = run_rietveld(Job(structure=None,
                              params={"xy": str(rutile_xy_shared)}))
    assert not result.ok
    assert "structure" in result.message


def test_a_rietveld_step_writes_what_each_box_refined(rutile_xy_shared):
    from xtal.modules.powder import refined_notes, run_rietveld

    result = run_rietveld(Job(structure=_rutile(), params={
        "xy": str(rutile_xy_shared), "strain": True}))
    assert result.ok, result.message
    notes = refined_notes(result.answer)
    assert notes["biso"].startswith("Ti")
    assert notes["positions"].startswith("furthest")
    assert notes["strain"].startswith("L ")
    assert "U " in notes["profile"]


def test_every_plan_says_what_it_frees_and_whether_the_atoms_move():
    """Two of RietX's four plans move no atom, which "lab
    Bragg-Brentano" does not say by itself."""
    from xtal.powder.bridge import RIETVELD_PRESETS, plan_notes

    moves = {"mccusker_structural": True, "mccusker_default": False,
             "lab_bragg_brentano": False, "lab_sample_refine": False}
    for plan in RIETVELD_PRESETS:
        note = plan_notes(plan)
        assert "Stages: scale and background" in note
        assert ("The atoms move." in note) is moves[plan], plan
    boxes = plan_notes("", ("background", "cell", "positions"))
    assert "cell → atom positions" in boxes
    assert "peak shape" not in boxes
