"""Frequencies and thermochemistry as a run: ``forcefield.thermo``.

UFF throughout, on structures small enough that the Hessian is a
fraction of a second.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest_ff import water
from xtal.io import write_cif
from xtal.modules.job import Cancellation, Job
from xtal.modules.registry import MODULES
from xtal.modules.report import REPORT_NAME, Curve, Modes, Table, load
from xtal.workspace import Workspace


def _action():
    _module, action = MODULES.find("forcefield.thermo")
    return action


def _folder(tmp_path, structure, name="s"):
    source = tmp_path / f"{name}.cif"
    write_cif(structure, source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    return entry.next_run("forcefield", "thermo")


def _run(structure, folder=None, cancel=None, **params):
    from xtal.params import coerce

    action = _action()
    values = coerce(action.params, dict(
        engine="uff", t_min=100.0, t_max=400.0, t_step=100.0,
        **params))
    job = Job(structure=structure, folder=folder, params=values,
              cancel=cancel or Cancellation())
    job.on_progress = lambda _text: None
    return action.run(job)


def _summary(result) -> Table:
    return next(b for b in result.report.blocks
                if isinstance(b, Table) and b.title == "Summary")


def _row(table, name):
    """The row called ``name``, or ``name(298.15 K)``."""
    return next(r for r in table.rows if r.texts[0] == name
                or r.texts[0].startswith(name + "("))


def test_a_thermochemistry_run_returns_no_structure(rutile):
    """The tab is the crystal the numbers are of; a relaxed copy is a
    file to open, never an edit to it."""
    before = rutile.frac.copy()
    result = _run(rutile)
    assert result.ok, result.message
    assert result.structure is None
    assert np.array_equal(rutile.frac, before)


def test_relax_first_relaxes_a_copy_and_writes_it_beside_the_report(
        tmp_path, rutile):
    folder = _folder(tmp_path, rutile)
    result = _run(rutile, folder)
    assert result.ok, result.message
    relaxed = folder.path / "relaxed.cif"
    assert relaxed.exists()
    for name in ("thermo.dat", "modes.dat", "forces.npz", REPORT_NAME):
        assert (folder.path / name).exists(), name


def test_imaginary_modes_are_a_warning_in_the_summary_not_a_number_in_g(
        rutile):
    """Rutile squeezed and not relaxed has modes the energy falls
    along: they are counted, said, and left out of G."""
    squeezed = rutile.copy()
    squeezed.sites[1].frac = squeezed.sites[1].frac * 0.9
    result = _run(squeezed, relax_first=False)
    table = _summary(result)
    imaginary = _row(table, "Imaginary modes")
    assert int(imaginary.texts[1]) > 0
    assert "not a minimum" in imaginary.note
    assert "not a minimum" in table.warning
    assert "imaginary" in result.message
    assert np.isfinite(float(_row(table, "G").texts[1]))


def test_a_molecule_gets_the_ideal_gas_and_its_entropy():
    """Water alone in a box is proposed as a molecule, and S(298 K)
    is near the 45.1 cal/(mol K) of NIST whatever the engine: the
    rigid-body terms are most of it."""
    result = _run(water(), temperature=298.15)
    assert result.ok, result.message
    table = _summary(result)
    assert "molecule" in _row(table, "System").texts[1]
    # The Hessian is the relaxed water's: UFF's minimum is zero, and
    # the experimental geometry it started from is 1.2 kcal/mol above.
    assert float(_row(table, "E (electronic)").texts[1]) < 1e-3
    s = float(_row(table, "S").texts[1])
    assert s == pytest.approx(45.1, abs=0.5)
    assert _row(table, "Symmetry number").texts[1] == "2"


def test_the_report_has_curves_and_the_modes(rutile):
    result = _run(rutile)
    curves = [b for b in result.report.blocks if isinstance(b, Curve)]
    assert len(curves) == 2
    energy = next(c for c in curves if c.title.startswith("H, TS and G"))
    assert list(energy.x) == [100.0, 200.0, 300.0, 400.0]
    modes = [b for b in result.report.blocks if isinstance(b, Modes)]
    assert len(modes) == 1 and modes[0].n_modes == 18


def test_the_reopened_report_has_the_table_and_curves(tmp_path, rutile):
    """report.json leaves the modes out -- they are in modes.dat --
    and keeps everything else, so a closed run comes back."""
    folder = _folder(tmp_path, rutile)
    _run(rutile, folder)
    again = load(folder.path / REPORT_NAME)
    kinds = {type(b).__name__ for b in again.blocks}
    assert {"Table", "Curve"} <= kinds
    assert "Modes" not in kinds


def test_stop_during_the_hessian_keeps_the_forces_and_gives_no_g(
        tmp_path, rutile):
    folder = _folder(tmp_path, rutile)
    cancel = Cancellation()
    seen = []

    def progress(text):
        seen.append(text)
        if "displacement" in text:
            cancel.cancel()

    from xtal.params import coerce
    action = _action()
    job = Job(structure=rutile, folder=folder,
              params=coerce(action.params, {"engine": "uff",
                                            "relax_first": False}),
              cancel=cancel)
    job.on_progress = progress
    result = action.run(job)
    assert result.cancelled
    assert result.report is None
    assert (folder.path / "forces.npz").exists()
    assert not (folder.path / "thermo.dat").exists()


def test_frozen_sites_are_not_displaced(rutile):
    result = _run(rutile, freeze="0", relax_first=False)
    assert result.ok, result.message
    table = _summary(result)
    assert _row(table, "Displaced atoms").texts[1] == "4"


def test_xtal_run_forcefield_thermo_writes_thermo_dat(
        tmp_path, rutile, capsys):
    from xtal.cli import main

    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    root = tmp_path / "ws"
    assert main(["run", "forcefield.thermo", str(path), "--workspace",
                 str(root), "-p", "engine=uff", "-p",
                 "temperature=300"]) == 0
    written = list(root.rglob("thermo.dat"))
    assert len(written) == 1
    assert "G(300 K)" in capsys.readouterr().out


def test_the_ir_tick_adds_a_spectrum_from_the_same_hessian(
        tmp_path, rutile):
    """No second Hessian: the spectrum is the same modes contracted
    with a charge model, and the files are beside the others."""
    from xtal.modules.report import Spectrum

    folder = _folder(tmp_path, rutile)
    result = _run(rutile, folder, ir=True)
    spectra = [b for b in result.report.blocks
               if isinstance(b, Spectrum)]
    assert len(spectra) == 1
    assert "EQeq" in spectra[0].note or "UFF" in spectra[0].note
    for name in ("ir.dat", "ir_broadened.xy"):
        assert (folder.path / name).exists(), name
    assert any(isinstance(b, Spectrum)
               for b in load(folder.path / REPORT_NAME).blocks)


def test_the_ir_action_skips_the_thermochemistry():
    from xtal.params import coerce

    _module, action = MODULES.find("forcefield.infrared")
    names = {p.name for p in action.params}
    assert "temperature" not in names and "ir_charges" in names
    job = Job(structure=water(), params=coerce(
        action.params, {"engine": "uff"}), cancel=Cancellation())
    job.on_progress = lambda _text: None
    result = action.run(job)
    assert result.ok, result.message
    titles = [getattr(b, "title", "") for b in result.report.blocks]
    assert not any(t.startswith("H, TS and G") for t in titles)
    assert "IR spectrum" in titles
    assert "IR bands" in result.message


@pytest.mark.parametrize("action, extra", [
    ("forcefield.thermo", ["-p", "relax_first=false"]),
    ("scan.bulk_modulus", ["-p", "axis1_steps=5", "-p",
                           "relax_first=false"])])
def test_a_fresh_xtal_run_knows_the_engines(tmp_path, rutile, action,
                                            extra):
    """In a fresh interpreter the modules register while xtal.ff is
    still importing -- a DFTB+ calculator reaches xtal.modules.process
    -- so a choice list read off ENGINES then was empty, and every
    ``-p engine=uff`` was refused.  In this test process the engines
    are long registered, which is why it has to be a subprocess."""
    import subprocess
    import sys

    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    ran = subprocess.run(
        [sys.executable, "-c",
         "import sys; from xtal.cli import main; "
         "sys.exit(main(sys.argv[1:]))",
         "run", action, str(path), "--workspace", str(tmp_path / "ws"),
         "-p", "engine=uff", "-p", "max_steps=5", *extra, "-q"],
        capture_output=True, text=True, timeout=300)
    assert ran.returncode == 0, ran.stderr + ran.stdout


def test_analytic_is_refused_for_an_engine_without_one_before_relaxing(
        rutile):
    """Asked by name of UFF, the run fails with the reason before a
    step is taken -- never a quiet fall back to differences."""
    result = _run(rutile, method="analytic")
    assert not result.ok
    assert "no analytic Hessian" in result.message


def test_an_analytic_run_says_how_its_hessian_was_taken(
        rutile, monkeypatch):
    """An engine with second derivatives of its own: the summary and
    the log name the route, and nothing is displaced."""
    from tests.test_vibrations import _with_second_derivatives
    from xtal.ff.uff.calculator import UFFCalculator
    from xtal.modules import thermo as module

    monkeypatch.setattr(module, "has_analytic_hessian", lambda e: True)
    original = UFFCalculator.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        _with_second_derivatives(self, [])

    monkeypatch.setattr(UFFCalculator, "__init__", init)
    result = _run(rutile, method="analytic")
    assert result.ok, result.message
    said = _row(_summary(result), "Hessian").texts[1]
    assert "analytic" in said
    differences = _run(rutile, method="gamma")
    modes = [next(b for b in r.report.blocks if isinstance(b, Modes))
             for r in (result, differences)]
    assert modes[0].frequencies == pytest.approx(modes[1].frequencies,
                                                 abs=1.0)


def test_a_marker_does_not_change_the_formula_units():
    """One X made Z 1 and the per-formula-unit column the cell's: a
    marker is not chemistry, here as everywhere."""
    from xtal import Lattice, Structure

    structure = Structure.from_arrays(
        Lattice.from_parameters(4.594, 4.594, 2.959, 90, 90, 90),
        ["Ti", "O", "X"],
        [[0.0, 0.0, 0.0], [0.3053, 0.3053, 0.0], [0.5, 0.0, 0.25]],
        space_group="P4_2/mnm")
    result = _run(structure, relax_first=False, method="gamma")
    assert "Z = 2" in _summary(result).note
