"""Quasi-harmonic F(V, T): the arithmetic on synthetic crystals whose
answer is known, then the run on a real one."""

import numpy as np
import pytest

from xtal.ff import qha, thermo

V0 = 100.0
#: kcal/mol/A^6: a few hundred GPa A^3 of curvature, a stiff crystal.
K = 0.05
TEMPERATURES = np.arange(10.0, 810.0, 10.0)
BASE = np.array([150.0, 300.0, 450.0, 600.0, 900.0, 1200.0])


def _crystal(gamma=0.0, volumes=None, energy=lambda v: K * (v - V0) ** 2,
             base=BASE):
    """Volumes round V0 with frequencies nu (V / V0) ** -gamma."""
    volumes = np.linspace(94.0, 106.0, 9) if volumes is None else volumes
    return [qha.judge(v, energy(v), base * (v / V0) ** -gamma)
            for v in volumes]


def test_a_harmonic_crystal_has_no_thermal_expansion():
    """Frequencies that do not move with the volume add the same F_vib
    to every point, so the minimum stays where E's is: expansion comes
    from the frequencies' volume dependence and nothing else."""
    result = qha.analyse(_crystal(gamma=0.0), TEMPERATURES)
    (well,) = result.wells
    v = well.series("volume")
    assert np.allclose(v, V0, atol=1e-3)
    alpha = well.expansion
    assert np.nanmax(np.abs(alpha)) < 1e-7


def test_softening_frequencies_with_volume_expand_the_cell_with_temperature():
    """A positive Grueneisen parameter: modes soften as the cell grows,
    so F_vib falls with V faster the hotter it is, and V(T) rises --
    slowly at first, while only the zero point acts."""
    result = qha.analyse(_crystal(gamma=1.5), TEMPERATURES)
    (well,) = result.wells
    v = well.series("volume")
    assert np.isfinite(v).all()
    assert v[0] > V0                        # the zero point already
    assert (np.diff(v) > -1e-9).all()
    assert v[-1] - v[0] > 0.1
    alpha = well.expansion
    assert np.nanmin(alpha[1:-1]) >= 0
    assert alpha[-2] > alpha[1]
    assert (well.series("b") > 0).all()


def test_a_volume_with_imaginary_modes_is_a_hole_not_a_free_energy():
    points = _crystal(gamma=1.0)
    broken = np.append(BASE, -120.0)
    points[2] = qha.judge(points[2].volume, points[2].energy, broken)
    points[6] = qha.judge(points[6].volume, points[6].energy, BASE,
                          converged=False)
    assert points[2].hole and "1 imaginary mode" in points[2].note
    assert points[6].hole and "converge" in points[6].note
    result = qha.analyse(points, TEMPERATURES)
    assert np.isnan(result.free[2]).all()
    assert np.isnan(result.free[6]).all()
    assert len(result.holes) == 2
    # Seven points are left, still enough for the equation of state.
    (well,) = result.wells
    assert well.form == "Birch-Murnaghan"
    assert np.isfinite(well.series("g")).all()


def test_two_wells_are_fitted_apart_and_their_crossing_found():
    """MIL-53's case: a dense well lower in energy and stiffer, an open
    one higher and softer.  Fitted as one curve the minimum would sit
    on the barrier; apart, the open well wins once T S pays for its
    energy, and the crossing is the transition temperature."""
    volumes = np.linspace(80.0, 120.0, 17)

    def energy(v):
        return 0.02 * (v - 88.0) ** 2 * (v - 112.0) ** 2 / 50.0 \
            + 0.15 * (v - 88.0)

    def frequencies(v):
        return BASE * (1.0 if v < 100.0 else 0.6)

    points = [qha.judge(v, energy(v), frequencies(v)) for v in volumes]
    result = qha.analyse(points, TEMPERATURES)
    assert len(result.wells) == 2
    dense, open_ = result.wells
    assert np.nanmax(dense.series("volume")) < 100.0
    assert np.nanmin(open_.series("volume")) > 100.0
    assert len(result.crossings) == 1
    crossing = result.crossings[0]
    assert (crossing.below, crossing.above) == (0, 1)
    gap = dense.series("g") - open_.series("g")
    j = int(np.searchsorted(TEMPERATURES, crossing.temperature))
    assert gap[j - 1] < 0 < gap[j]


def test_a_well_too_small_for_an_equation_of_state_is_a_parabola():
    points = _crystal(gamma=1.0, volumes=np.linspace(97.0, 103.0, 4))
    (well,) = qha.analyse(points, TEMPERATURES).wells
    assert well.form == "parabola"
    assert np.isfinite(well.series("volume")).all()


def test_pressure_compresses_the_minimum():
    low = qha.analyse(_crystal(gamma=1.0), [300.0]).wells[0]
    high = qha.analyse(_crystal(gamma=1.0), [300.0],
                       pressure=1.0).wells[0]
    assert high.series("volume")[0] < low.series("volume")[0]


def test_free_energy_is_e_plus_the_harmonic_f_vib():
    (point,) = _crystal(volumes=[V0])
    f = qha.free_energies([point], [300.0])
    expected = thermo.harmonic(BASE, temperature=300.0).f_vib
    assert f[0, 0] == pytest.approx(expected)


# ------------------------------------------------------------ the run

def _qha_run(structure, tmp_path, cancel=None, **params):
    """``scan.qha`` on ``structure`` under UFF, filed in a workspace:
    ``(result, run folder)``."""
    from xtal.io import write_cif
    from xtal.modules.job import Cancellation, Job
    from xtal.modules.registry import MODULES
    from xtal.params import coerce
    from xtal.workspace import Workspace

    source = tmp_path / "s.cif"
    write_cif(structure, source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    folder = entry.next_run("scan", "qha")
    _module, action = MODULES.find("scan.qha")
    values = coerce(action.params, {
        "engine": "uff", "hessian": "gamma", "axis1_steps": 5,
        "span": 3.0, "t_step": 100.0, **params})
    # Not ``cancel or ...``: a Cancellation is false until it is set.
    job = Job(structure=structure, folder=folder, params=values,
              cancel=Cancellation() if cancel is None else cancel)
    job.on_progress = lambda _text: None
    return action.run(job), folder.path


def test_quartz_expands_with_temperature_and_its_report_reopens(
        tmp_path, quartz):
    """A real crystal end to end: every volume summed, V rising with
    T, the files a person opens, and the report back from disk."""
    from xtal.modules.report import REPORT_NAME, load

    result, run = _qha_run(quartz, tmp_path)
    assert result.ok, result.message
    assert result.structure is None
    (well,) = result.answer.wells
    v = well.series("volume")
    assert np.isfinite(v).all() and v[-1] > v[0]
    for name in ("qha.csv", "scan.csv", "free_energy.dat",
                 "minima.dat", "forward-00-frequencies.txt"):
        assert (run / name).is_file(), name
    reopened = load(run / REPORT_NAME)
    assert [t.title for t in reopened.tables] == ["Volumes", "Minimum"]
    assert len(reopened.curves) == 3


def test_every_qha_point_is_on_disk_before_the_next_starts(
        tmp_path, quartz, monkeypatch):
    """Each Hessian starts only once every volume before it has its
    row in qha.csv, its frequencies and its column of F: a run stopped
    or crashed at the seventh volume keeps six."""
    from xtal.modules import qha as qha_run

    real, seen = qha_run._vibrations, []

    def counting(job, structure, *args):
        run = job.folder.path
        rows = (run / "qha.csv").read_text().count("\n") - 1 \
            if (run / "qha.csv").exists() else 0
        written = len(list(run.glob("*-frequencies.txt")))
        free = run / "free_energy.dat"
        columns = free.read_text().count("\n") - 1 if free.exists() \
            else 0
        seen.append((rows, written, columns))
        return real(job, structure, *args)

    monkeypatch.setattr(qha_run, "_vibrations", counting)
    result, _run = _qha_run(quartz, tmp_path)
    assert result.ok
    assert seen == [(k, k, k) for k in range(5)]


def test_stop_during_a_hessian_keeps_the_volumes_before_it(
        tmp_path, quartz, monkeypatch):
    from xtal.modules import qha as qha_run
    from xtal.modules.job import Cancellation

    cancel = Cancellation()
    real, calls = qha_run._vibrations, []

    def stopping(job, structure, *args):
        calls.append(1)
        if len(calls) == 3:
            cancel.cancel()
        return real(job, structure, *args)

    monkeypatch.setattr(qha_run, "_vibrations", stopping)
    result, run = _qha_run(quartz, tmp_path, cancel=cancel)
    assert result.cancelled
    assert "volume 3" in result.message
    assert (run / "qha.csv").read_text().count("\n") == 3   # head + 2
    assert len(result.answer.points) == 2


def test_a_phonopy_supercell_over_the_limit_is_refused_before_relaxing(
        tmp_path, quartz, monkeypatch):
    pytest.importorskip("phonopy")
    from xtal.ff import optimize

    monkeypatch.setattr(optimize, "run", lambda *a, **k: pytest.fail(
        "relaxed before refusing"))
    result, _run = _qha_run(quartz, tmp_path, hessian="phonopy",
                            supercell="20 20 20")
    assert not result.ok
    assert [code for code, _ in result.warnings] == ["SIZE_LIMIT"]


def test_a_crystal_with_an_imaginary_mode_at_every_volume_fits_nothing(
        tmp_path, rutile):
    """Rutile under UFF has a mode at -340 cm-1 however it is relaxed:
    not a minimum at any volume, so every volume is a hole and the run
    says so rather than fitting free energies of nothing."""
    result, _run = _qha_run(rutile, tmp_path)
    assert result.ok
    assert result.answer.wells == ()
    assert "nothing to fit" in result.message
    assert [code for code, _ in result.warnings] == ["IMAGINARY_MODES"]


def test_every_volume_is_sampled_with_the_same_supercell_and_q_mesh(
        tmp_path, quartz, monkeypatch):
    """``auto`` asked of each volume's own cell changes with the volume
    -- MIL-53 is 2x2x1 open and 2x2x2 a few percent smaller -- and a
    change of sampling is a step in F(V) that is not the crystal's.
    The supercell is the relaxed start's and the mesh the first
    volume's, for every volume."""
    pytest.importorskip("phonopy")
    from xtal.ff import phonons

    real, asked = phonons.phonopy_vibrations, []

    def recording(build, structure, **kwargs):
        asked.append((kwargs["supercell"], kwargs["mesh"]))
        return real(build, structure, **kwargs)

    monkeypatch.setattr(phonons, "phonopy_vibrations", recording)
    result, _run = _qha_run(quartz, tmp_path, hessian="phonopy",
                            axis1_steps=3)
    assert result.ok, result.message
    supercells = {s for s, _ in asked}
    assert len(supercells) == 1 and isinstance(supercells.pop(), tuple)
    meshes = [m for _, m in asked]
    assert np.ndim(meshes[0]) == 0                  # a length, once
    assert all(m == meshes[1] for m in meshes[1:])
    assert np.ndim(meshes[1]) == 1                  # then held
    assert "at every volume" in result.report.title


def test_a_volume_whose_hessian_fails_is_a_hole_not_the_end_of_the_run(
        tmp_path, quartz, monkeypatch):
    from xtal.ff.api import CalculatorError
    from xtal.modules import qha as qha_run

    real, calls = qha_run._vibrations, []

    def failing(*args):
        calls.append(1)
        if len(calls) == 2:
            raise CalculatorError("the engine refused this geometry")
        return real(*args)

    monkeypatch.setattr(qha_run, "_vibrations", failing)
    result, _run = _qha_run(quartz, tmp_path)
    assert result.ok
    (hole,) = result.answer.holes
    assert "the engine refused" in hole.note
    (well,) = result.answer.wells
    assert len(well.indices) == 4 and well.form == "parabola"
