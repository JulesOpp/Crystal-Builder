"""phonopy's route to the modes: symmetry, a supercell and a q-mesh.

UFF throughout.  Skipped without the ``phonons`` extra, except for
what the run decides when phonopy is not there.
"""

from __future__ import annotations

import importlib.util
from functools import partial

import numpy as np
import pytest

from tests.conftest_ff import water
from xtal.core import bonding, limits, p1
from xtal.core.lattice import Lattice
from xtal.core.structure import Structure
from xtal.ff import phonons, thermo, vibrations
from xtal.ff.registry import ENGINES
from xtal.io import FORMATS
from xtal.modules.thermo import choose_method
from xtal.params import ParamError

needs_phonopy = pytest.mark.skipif(
    importlib.util.find_spec("phonopy") is None,
    reason="the phonons extra is not installed")

PREPARED = "resources/samples/prepared"

uff = partial(ENGINES.build, "uff")


def _lithium_hydride(isotope="H") -> Structure:
    return Structure.from_arrays(
        Lattice.from_parameters(4.08, 4.08, 4.08, 90, 90, 90),
        ["Li", isotope], [[0, 0, 0], [0.5, 0.5, 0.5]],
        space_group="Fm-3m")


@needs_phonopy
def test_mof5_needs_nineteen_displacements_not_six_hundred():
    """The measured count, and the reason for the extra: MACE takes
    nine minutes over every atom of MOF-5 and seventeen seconds over
    these."""
    mof5 = FORMATS.read(f"{PREPARED}/MOF-5.cif")
    plan = phonons.plan(mof5)
    assert plan.supercell == (1, 1, 1)
    assert plan.displacements == 19
    assert vibrations.evaluations(mof5) == 6 * 106 + 1


@needs_phonopy
def test_gamma_frequencies_agree_with_the_numpy_hessian(rutile):
    """Both are finite differences of the same forces, one column per
    displaced atom or one per displacement and the rest by symmetry:
    they are one Hessian, or the symmetry was applied wrongly."""
    every = vibrations.hessian(uff(rutile), rutile)
    found = phonons.phonopy_vibrations(uff, rutile, supercell="1 1 1")
    assert found.evaluations == 4
    assert np.abs(found.frequencies - every.frequencies).max() < 1.0
    assert found.energy == pytest.approx(every.energy)
    assert found.method == "phonopy"
    assert found.mesh_frequencies is None


@needs_phonopy
@pytest.mark.slow
def test_uio66s_gamma_frequencies_agree_with_the_numpy_hessian():
    """114 atoms and Zr6 clusters, 35 evaluations against 685; within
    a wavenumber, measured at 0.34."""
    uio = FORMATS.read(f"{PREPARED}/UiO-66.cif")
    every = vibrations.hessian(uff(uio), uio)
    found = phonons.phonopy_vibrations(uff, uio, supercell="1 1 1")
    assert found.evaluations == 35
    assert np.abs(found.frequencies - every.frequencies).max() < 1.0


def test_a_small_cell_is_given_a_supercell_at_least_ten_angstrom_wide(
        rutile):
    """Rutile is 4.6 x 4.6 x 3.0 A: Gamma alone misses every branch
    across the zone, which is what S is made of."""
    repeats = phonons.supercell_of(rutile, "auto")
    assert repeats == (3, 3, 4)
    widths = np.array([4.594, 4.594, 2.959]) * repeats
    assert widths.min() >= phonons.MIN_WIDTH
    assert phonons.supercell_of(rutile, "gamma") == (1, 1, 1)
    assert phonons.supercell_of(rutile, "2x2x1") == (2, 2, 1)
    with pytest.raises(ValueError):
        phonons.parse_supercell("2 2")


def test_a_supercell_over_the_hard_limit_is_refused_with_the_largest_that_fits(  # noqa: E501
        rutile):
    """In the core, so the CLI and an agent meet it as the dialog
    does; the sentence says what would fit."""
    verdict = limits.check_phonons(6, (30, 30, 30))
    assert verdict.refused
    assert "is the largest that fits" in verdict.sentence
    plan = phonons.plan(rutile, "30 30 30")
    assert plan.verdict.refused and plan.displacements == 0
    with pytest.raises(ValueError, match="phonon supercell would have"):
        phonons.phonopy_vibrations(uff, rutile, supercell="30 30 30")


def test_the_supercell_carries_the_graph_and_the_energy(rutile):
    """UFF types every atom by its bonds, so a supercell perceived
    afresh could be another molecule; carried, it is the same one,
    and its energy is the cell's times the repeats."""
    big = phonons._supercell_with_graph(rutile, (2, 2, 3))
    one = bonding.flat_with_graph(rutile)
    assert len(big.perceived.bonds) == 12 * len(one.perceived.bonds)
    cell = ENGINES.build("uff", rutile)
    e_one = cell.compute(p1.expand(rutile).cart,
                         rutile.lattice.matrix).energy
    e_big = ENGINES.build("uff", big).compute(
        p1.expand(big).cart, big.lattice.matrix).energy
    assert e_big == pytest.approx(12 * e_one, rel=1e-6)


@needs_phonopy
def test_a_q_mesh_is_one_cell_of_modes(rutile):
    """Each branch's weights sum to one over the mesh, so H, S and G
    stay per cell and Z still divides them."""
    found = phonons.phonopy_vibrations(uff, rutile)
    assert found.supercell == (3, 3, 4)
    assert found.q_mesh is not None
    frequencies, weights = found.sampled()
    assert weights.sum() == pytest.approx(len(found.frequencies))
    assert len(frequencies) % len(found.frequencies) == 0
    at_gamma = thermo.harmonic(found.frequencies, found.weights,
                               temperature=298.15)
    over = thermo.harmonic(frequencies, weights, temperature=298.15)
    # The acoustic branches away from Gamma are entropy Gamma never
    # sees: zero there, and most of a low-frequency solid's S.
    assert over.s_vib > at_gamma.s_vib


@needs_phonopy
@pytest.mark.slow
def test_deuterium_is_its_own_mass_and_the_mesh_is_not_reduced_by_it():
    """The force constants are hydrogen's -- the surface is the same
    -- and the masses deuterium's, which is the whole of the
    difference a deuterated crystal makes."""
    hydride = phonons.phonopy_vibrations(uff, _lithium_hydride("H"),
                                         mesh=20.0)
    deuteride = phonons.phonopy_vibrations(uff, _lithium_hydride("D"),
                                           mesh=20.0)
    ratio = deuteride.frequencies.max() / hydride.frequencies.max()
    assert 1 / np.sqrt(2) < ratio < 0.9
    assert not phonons._symmetric_masses(
        phonons._real_cell(_lithium_hydride("D"))[0])
    assert phonons._symmetric_masses(
        phonons._real_cell(_lithium_hydride("H"))[0])


@needs_phonopy
def test_stop_raises_between_displacements(rutile):
    from xtal.ff.api import CalculatorStopped
    from xtal.modules.job import Cancellation

    cancel = Cancellation()
    seen = []

    def progress(done, total):
        seen.append(done)
        cancel.cancel()

    with pytest.raises(CalculatorStopped):
        phonons.phonopy_vibrations(uff, rutile, cancel=cancel,
                                   progress=progress)
    assert seen == [1]


# -- what the run chooses ----------------------------------------------

def test_a_molecule_always_takes_the_gamma_path():
    assert choose_method("phonopy", "molecule")[0] == "gamma"
    assert choose_method("auto", "molecule") == ("gamma", "")


def test_frozen_atoms_with_phonopy_named_are_refused_and_point_at_gamma():
    with pytest.raises(ParamError, match="Gamma only"):
        choose_method("phonopy", "crystal", frozen=[0])
    assert choose_method("auto", "crystal", frozen=[0])[0] == "gamma"


def test_without_phonopy_automatic_is_gamma_and_says_what_it_would_buy(
        monkeypatch):
    monkeypatch.setattr(phonons, "installed", lambda: False)
    method, why = choose_method("auto", "crystal")
    assert method == "gamma"
    assert "phonons extra" in why
    with pytest.raises(ParamError, match="not installed"):
        choose_method("phonopy", "crystal")


@needs_phonopy
def test_a_phonopy_run_says_so_and_leaves_phonopys_own_file(
        tmp_path, rutile):
    from tests.test_thermo_module import _folder, _row, _run, _summary

    folder = _folder(tmp_path, rutile)
    result = _run(rutile, folder=folder, relax_first=False,
                  method="phonopy")
    assert result.ok, result.message
    table = _summary(result)
    assert _row(table, "Hessian").texts[1].startswith(
        "phonopy, supercell 3x3x4, q-mesh")
    assert "q-mesh" in _row(table, "Modes summed").note
    assert (folder.path / "phonopy_params.yaml").exists()
    assert (folder.path / "forces.npz").exists()
    modes = next(b for b in result.report.blocks
                 if type(b).__name__ == "Modes")
    assert len(modes.frequencies) == 18


def test_a_molecule_run_asked_for_phonopy_is_a_gamma_run():
    from tests.test_thermo_module import _row, _run, _summary

    result = _run(water(), method="phonopy", relax_first=False)
    assert result.ok, result.message
    assert _row(_summary(result), "Hessian").texts[1] == \
        "Gamma only, finite differences"


@needs_phonopy
def test_a_spectrum_alone_takes_phonopy_without_a_supercell(rutile):
    """Gamma's modes are the cell's force constants summed over
    images, which a 1x1x1 cell measures exactly; a 3x3x4 supercell
    would be 36 times the work for the same spectrum."""
    from xtal.modules.job import Cancellation, Job
    from xtal.modules.registry import MODULES
    from xtal.params import coerce

    _module, action = MODULES.find("forcefield.infrared")
    job = Job(structure=rutile, folder=None, cancel=Cancellation(),
              params=coerce(action.params, {
                  "engine": "uff", "method": "phonopy",
                  "relax_first": False}))
    job.on_progress = lambda _text: None
    result = action.run(job)
    assert result.ok, result.message
    summary = result.report.blocks[0]
    hessian = next(r for r in summary.rows if r.texts[0] == "Hessian")
    assert hessian.texts[1] == "phonopy, Gamma only (supercell 1x1x1)"
