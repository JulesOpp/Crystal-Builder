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


# ----------------------------------------------------------------------
#  the parameter set: where a run starts, and where it leaves the next
# ----------------------------------------------------------------------

def test_a_second_rietveld_run_starts_where_the_first_ended(fitted, data):
    """Run again from the first run's parameters with only the scale
    flagged: the Rwp and every other number stay where they were.
    Without it every run starts from RietX's preset again, and a
    profile fitted on one tab is thrown away on the next."""
    _structure, first, _frames = fitted
    again = first.parameters.copy()
    for row in again:
        again.set_refine(row.name, row.name == "scale")
    fit = rietveld(first.structure, data, Radiation("cu"),
                   RietveldOptions(cell=False), parameters=again)
    assert fit.converged
    assert fit.rwp == pytest.approx(first.rwp, rel=1e-4)
    for before in first.parameters:
        after = fit.parameters[before.name]
        if before.value is not None:
            assert after.value == pytest.approx(
                before.value, rel=1e-4, abs=1e-9), before.name


def test_a_row_not_flagged_does_not_move(data):
    """W typed in and left unflagged is the W the fit ends with, and
    has no esd; the rest of the peak shape still refines.  Without it
    a person's held number is quietly refitted."""
    from xtal.powder import bridge

    start = bridge.starting_parameters(Radiation("cu"), data=data,
                                       structure=_rutile())
    start.set_value("W", 0.002)
    start.set_refine("W", False)
    fit = rietveld(_rutile(), data, Radiation("cu"), parameters=start)
    assert fit.parameters["W"].value == 0.002
    assert fit.parameters["W"].esd is None
    assert "instrument.profile.w" not in fit.refined
    assert fit.parameters["U"].esd


def test_a_position_its_site_fixes_is_held_and_says_why(fitted):
    """Rutile's Ti at 0,0,0 has no direction to move in; its glob
    matches nothing in RietX, which does not refuse it, so only the
    set says so.  Without it the table offers a Refine flag that does
    nothing."""
    _structure, fit, _frames = fitted
    assert fit.parameters["Ti1_xyz"].held == "fixed by symmetry"
    assert fit.parameters["O2_xyz"].held == ""


def test_nothing_flagged_is_refused_rather_than_run(data):
    from xtal.powder import bridge

    start = bridge.starting_parameters(Radiation("cu"), data=data,
                                       structure=_rutile())
    for row in start:
        start.set_refine(row.name, False)
    with pytest.raises(PowderError, match="nothing is flagged"):
        rietveld(_rutile(), data, Radiation("cu"),
                 RietveldOptions(cell=False), parameters=start)


def test_xtal_run_starts_from_a_parameter_file_and_leaves_where_it_ended(
        tmp_path, rutile_xy_shared):
    """``parameters=FILE`` is read in the text form Copy writes, its
    flags in place of the boxes, and the run's folder keeps the set it
    started from and the one it ended with.  Without it a script
    cannot carry numbers from one run to the next."""
    from xtal.io import write_cif
    from xtal.modules import MODULES
    from xtal.modules import record as module_record
    from xtal.powder.parameters import ParameterSet
    from xtal.workspace import Workspace

    source = tmp_path / "rutile.cif"
    write_cif(_rutile(), source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    given = tmp_path / "start.txt"
    given.write_text("W 0.0015 NoRefine\nstrain_l 0 Refine\n"
                     "bkg_c9 0 Refine\n", encoding="utf-8")
    module = MODULES.get("pxrd")
    action = module.action("rietveld")
    params = {"xy": str(rutile_xy_shared), "parameters": str(given),
              "strain": False, "frame_interval": -1}
    folder = module_record.open_run(entry, module, action, params,
                                    _rutile())
    result = action.run(Job(structure=_rutile(), folder=folder,
                            params=params))
    assert result.ok, result.message
    started = folder.path / "parameters-start.txt"
    ended = folder.path / "parameters.txt"
    assert "W 0.0015 NoRefine" in started.read_text()
    after = ParameterSet(result.answer.parameters)
    after.paste(ended.read_text())
    assert after["W"].value == 0.0015
    # the file's flag, not the box's
    assert "phases.0.lor_strain" in result.answer.refined
    # a coefficient the file names grows the series past the box's 8
    assert after.background_terms == 10


def test_a_parameter_file_that_cannot_be_read_names_its_line(
        tmp_path, rutile_xy_shared):
    from xtal.modules.powder import run_rietveld

    given = tmp_path / "start.txt"
    given.write_text("W 0.0015 NoRefine\nwidth 3 Refine\n",
                     encoding="utf-8")
    result = run_rietveld(Job(structure=_rutile(), params={
        "xy": str(rutile_xy_shared), "parameters": str(given)}))
    assert not result.ok
    assert "start.txt, line 2" in result.message
