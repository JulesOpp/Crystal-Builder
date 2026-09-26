"""Rietveld with energies: the pattern and a force field weighed
against each other, and what each end of the weight must reproduce."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("rietx")

from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.structure import Bond, Structure  # noqa: E402
from xtal.ff import optimize  # noqa: E402
from xtal.ff.registry import ENGINES  # noqa: E402
from xtal.modules.job import Cancellation, Job  # noqa: E402
from xtal.powder import bridge  # noqa: E402
from xtal.powder.data import (  # noqa: E402
    PowderData,
    PowderError,
    PowderStopped,
    Radiation,
)
from xtal.powder.energy import (  # noqa: E402
    EnergyOptions,
    rietveld_with_energy,
)
from xtal.powder.rietveld import RietveldOptions, rietveld  # noqa: E402

CU = Radiation("cu")


def _uff(structure):
    return ENGINES.build("uff", structure)


def _quartz():
    """alpha-quartz as the conftest fixture has it: Si on the two-fold
    axis (x, 0, 2/3), O on a general position."""
    return Structure.from_arrays(
        Lattice.from_parameters(4.9134, 4.9134, 5.4052, 90, 90, 120),
        ["Si", "O"], [[0.4697, 0.0, 2 / 3], [0.4135, 0.2669, 0.7857]],
        space_group="P3221")


def _rutile(x=0.29, dummy=False):
    elements = ["Ti", "O"] + (["X"] if dummy else [])
    frac = [[0.0, 0.0, 0.0], [x, x, 0.0]] + (
        [[0.1, 0.2, 0.3]] if dummy else [])
    structure = Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        elements, frac, space_group="P4_2/mnm")
    structure.add_bond(Bond(0, 1))
    return structure


def _pattern(structure) -> PowderData:
    two_theta = np.arange(15.0, 80.0, 0.02)
    y = bridge.predict(structure, CU, two_theta)
    counts = np.random.default_rng(0).poisson(y / y.max() * 5000 + 100)
    return PowderData(two_theta=two_theta, intensity=counts.astype(float))


@pytest.fixture(scope="module")
def quartz_data():
    return _pattern(_quartz())


@pytest.fixture(scope="module")
def rutile_data(rutile_xy_shared):
    return PowderData.from_xy(rutile_xy_shared)


def test_weight_zero_matches_a_plain_rietveld_position_fit(rutile_data):
    """At w = 0 the energy has no say, and the answer is RietX's own
    position fit: the oxygen back at 0.3053 from 0.29."""
    plain = rietveld(_rutile(), rutile_data, CU,
                     RietveldOptions(cell=False))
    fit = rietveld_with_energy(_rutile(), rutile_data, CU, _uff,
                               EnergyOptions(weight=0.0))
    assert fit.converged
    assert fit.structure.sites[1].frac[0] == pytest.approx(
        plain.structure.sites[1].frac[0], abs=5e-4)
    assert fit.rwp == pytest.approx(plain.rwp, rel=0.01)
    # the relaxation is only needed to scale the energy against
    assert np.isnan(fit.scale.relaxed)


def test_weight_one_matches_a_force_field_relaxation_at_fixed_cell(
        quartz_data):
    """At w = 1 the pattern has no say: the atoms go where the Force
    Field panel's own optimiser puts them, the cell held."""
    structure = _quartz()
    alone = optimize.run(_uff(structure), structure, method="lbfgs",
                         force_tolerance=1e-4, max_steps=2000)
    fit = rietveld_with_energy(structure, quartz_data, CU, _uff,
                               EnergyOptions(weight=1.0))
    assert fit.converged
    assert fit.energy == pytest.approx(alone.energy, abs=1e-3)
    assert fit.structure.frac == pytest.approx(alone.frac, abs=1e-3)
    assert fit.cell[:3] == pytest.approx((4.9134, 4.9134, 5.4052))
    assert fit.scale.relaxed == pytest.approx(fit.energy)


def test_a_weight_between_lands_between_the_two_ends(quartz_data):
    fit = rietveld_with_energy(_quartz(), quartz_data, CU, _uff,
                               EnergyOptions(weight=0.5))
    scale = fit.scale
    assert fit.converged
    assert scale.relaxed <= fit.energy < scale.energy
    assert fit.rwp < scale.relaxed_rwp


def test_the_pattern_gradient_matches_central_differences(rutile_data):
    """Breaks if RietX's private residual or Jacobian changes meaning:
    the gradient R+E descends is 2 J^T r, read off them."""
    term, *_rest = bridge.pattern_term(
        _rutile(), rutile_data, CU, free=("background", "profile"),
        cell=True)
    assert term.paths == ["phases.0.cell.a", "phases.0.cell.c",
                          "phases.0.atoms.1.dof.0"]
    theta = term.theta0 + 1e-3
    _chi2, gradient = term(theta)
    step = 1e-6
    numeric = [(term(theta + h)[0] - term(theta - h)[0]) / (2 * step)
               for h in np.eye(len(theta)) * step]
    assert gradient == pytest.approx(numeric, rel=1e-5)


def test_the_energy_gradient_matches_central_differences(quartz_data):
    """The engine's forces, carried over each orbit onto the site's
    allowed directions -- and its stress onto the cell's numbers."""
    from xtal.powder.energy import _Energy

    structure = _quartz()
    term, _result, indices, _refinement = bridge.pattern_term(
        structure, quartz_data, CU, free=("background",), cell=True)
    energy = _Energy(_uff(structure), structure, indices, term)
    theta = term.theta0 + 2e-3
    _e, gradient = energy(theta, cell=True)
    step = 1e-5
    numeric = []
    for h in np.eye(len(theta)) * step:
        up = energy(theta + h, cell=True)[0]
        down = energy(theta - h, cell=True)[0]
        numeric.append((up - down) / (2 * step))
    assert gradient == pytest.approx(numeric, rel=1e-3, abs=1e-3)


def test_an_energy_term_never_moves_a_site_off_its_special_position(
        quartz_data):
    """Si on quartz's two-fold axis and Ti at rutile's origin have
    fewer directions than three, and the energy is only ever read
    along the ones they have."""
    fit = rietveld_with_energy(_quartz(), quartz_data, CU, _uff,
                               EnergyOptions(weight=0.5, cell=True))
    silicon = fit.structure.sites[0].frac
    assert silicon[1] == pytest.approx(0.0, abs=1e-12)
    assert silicon[2] == pytest.approx(2 / 3, abs=1e-12)
    assert fit.structure.sites[0].frac[0] != pytest.approx(0.4697,
                                                           abs=1e-4)
    a, b, _c, alpha, beta, gamma = fit.cell
    assert (a, alpha, beta, gamma) == pytest.approx((b, 90, 90, 120))

    rutile = rietveld_with_energy(_rutile(), _pattern(_rutile(0.3053)),
                                  CU, _uff, EnergyOptions(weight=0.5))
    titanium, oxygen = (s.frac for s in rutile.structure.sites)
    assert titanium == pytest.approx([0.0, 0.0, 0.0], abs=1e-12)
    assert oxygen[0] == pytest.approx(oxygen[1], abs=1e-12)
    assert oxygen[2] == pytest.approx(0.0, abs=1e-12)


def test_the_cell_moves_only_when_asked(quartz_data):
    held = rietveld_with_energy(_quartz(), quartz_data, CU, _uff,
                                EnergyOptions(weight=1.0))
    free = rietveld_with_energy(_quartz(), quartz_data, CU, _uff,
                                EnergyOptions(weight=1.0, cell=True))
    assert held.structure.lattice.parameters[:3] == pytest.approx(
        (4.9134, 4.9134, 5.4052))
    assert free.cell[0] != pytest.approx(4.9134, abs=1e-3)
    assert free.energy < held.energy


def test_a_marker_is_held_back_and_never_moves(rutile_data):
    structure = _rutile(dummy=True)
    fit = rietveld_with_energy(structure, rutile_data, CU, _uff,
                               EnergyOptions(weight=0.3))
    assert len(fit.structure.sites) == 3
    assert fit.structure.sites[2].frac == pytest.approx([0.1, 0.2, 0.3])
    assert fit.structure.bonds == structure.bonds
    assert structure.sites[1].frac[0] == 0.29


def test_a_weight_outside_zero_to_one_is_refused(rutile_data):
    with pytest.raises(PowderError, match="weight"):
        rietveld_with_energy(_rutile(), rutile_data, CU, _uff,
                             EnergyOptions(weight=1.5))


def test_stop_raises_rather_than_returning_half_a_fit(rutile_data):
    cancel = Cancellation()
    frames = []

    def on_frame(frame):
        frames.append(frame)
        cancel.cancel()

    with pytest.raises(PowderStopped):
        rietveld_with_energy(_rutile(), rutile_data, CU, _uff,
                             EnergyOptions(weight=0.3), on_frame=on_frame,
                             frame_interval=0.0, cancel=cancel)
    assert frames


def test_the_step_runs_headless_and_leaves_its_files(tmp_path,
                                                     rutile_xy_shared):
    from xtal.io import write_cif
    from xtal.modules import MODULES
    from xtal.modules import record as module_record
    from xtal.workspace import Workspace

    source = tmp_path / "rutile.cif"
    write_cif(_rutile(), source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    module = MODULES.get("pxrd")
    action = module.action("energy")
    params = {"xy": str(rutile_xy_shared), "weight": 0.2,
              "engine": "uff", "frame_interval": -1}
    folder = module_record.open_run(entry, module, action, params,
                                    _rutile())
    result = action.run(Job(structure=_rutile(), folder=folder,
                            params=params))
    assert result.ok, result.message
    assert "w 0.2" in result.message
    for name in ("fit.xy", "refined.cif", "ends.csv"):
        assert (folder.path / name).exists()
    ends = (folder.path / "ends.csv").read_text().splitlines()
    assert [line.split(",")[0] for line in ends[1:]] == \
        ["As given", "Energy alone", "This fit"]


def test_an_engine_that_cannot_run_is_named_before_anything_runs(
        rutile_xy_shared):
    from xtal.modules import MODULES

    module = MODULES.get("pxrd")
    job = Job(structure=_rutile(),
              params={"xy": str(rutile_xy_shared), "engine": "nothing"})
    result = module.action("energy").run(job)
    assert not result.ok
    assert "nothing" in result.message


def test_the_note_says_what_each_stage_of_a_run_with_energy_refines():
    """The first stage is the Rietveld step's boxes, which live on
    another page; the note names them, and what moves after."""
    from xtal.modules.powder import energy_refines_note

    note = energy_refines_note({"rietveld_background": True,
                                "rietveld_profile": True,
                                "rietveld_biso": False,
                                "rietveld_positions": True})
    first, then = note.split("<b>Then</b>")
    assert "scale" in first and "background" in first
    assert "peak shape" in first
    assert "displacement parameters" not in first
    # the boxes an energy run never frees in its first stage
    assert "positions" not in first
    assert "atom positions" in then and "cell" not in then
    assert "cell's free numbers" in energy_refines_note(
        {"energy_cell": True})
