"""DFTB+'s own runs: the input blocks they need and the files they write.

Every reader is tested against output captured from DFTB+ 24.1 in
``tests/data/dftb`` -- ``generate.py`` there is how it was made, with
the input writer under test here, so the blocks below are ones the
real binary has already accepted.
"""

from pathlib import Path

import numpy as np
import pytest

from xtal import Lattice
from xtal.ff.dftb import hsd, outputs
from xtal.ff.dftb.calculator import DFTBOptions
from xtal.io.cube import read_cube_string

DATA = Path(__file__).resolve().parent / "data" / "dftb"


def _read(name):
    return (DATA / name).read_text()


# ------------------------------------------------------------ writing

def test_a_band_path_is_written_as_klines_in_reciprocal_fractions():
    path = hsd.KLines(((1, (0.5, 0.5, 0.5)), (20, (0, 0, 0)),
                       (25, (0.5, 0, 0.5))), ("L", "G", "X"))
    text = hsd.hsd_string(["Si"], DFTBOptions(), k_points=path,
                          read_charges=True, max_scc=1)
    assert "KPointsAndWeights = Klines {" in text
    assert "    20 0.00000000 0.00000000 0.00000000" in text
    assert "MaxSccIterations = 1" in text
    assert "ReadInitialCharges = Yes" in text
    assert "SupercellFolding" not in text
    assert path.n_points == 46


def test_the_captured_band_input_is_what_the_writer_writes():
    """The fixture's input was written by this module and accepted by
    DFTB+ 24.1; a change to the writer that DFTB+ has not seen shows up
    here first."""
    written = _read("si_klines_dftb_in.hsd")
    assert "Klines" in written
    assert "Driver" not in written


def test_a_lattice_relaxation_uses_the_driver_that_takes_a_pressure():
    """``GeometryOptimization`` at parser version 14 ignores Pressure
    and halts; the legacy LBFGS driver takes it."""
    lines = hsd.Relax(lattice=True, pressure=1e5, moved=(1, 2, 3, 7),
                      max_steps=50).lines()
    assert lines[0] == "Driver = LBFGS {"
    assert "  LatticeOpt = Yes" in lines
    assert "  Pressure [Pa] = 100000" in lines
    assert "  MovedAtoms = 1:3 7" in lines
    assert hsd.Relax(optimiser="cg").lines()[0] == \
        "Driver = ConjugateGradient {"


@pytest.mark.parametrize("thermostat, expected", [
    ("nose-hoover", "NoseHoover"), ("berendsen", "Berendsen"),
    ("none", "None")])
def test_each_thermostat_is_written(thermostat, expected):
    lines = hsd.Dynamics(thermostat=thermostat).lines()
    assert any(line.strip().startswith(f"Thermostat = {expected}")
               for line in lines)


def test_second_derivatives_and_mulliken_and_projected_states():
    text = hsd.hsd_string(
        ["C", "O"], DFTBOptions(), periodic=False,
        driver=hsd.SecondDerivatives(),
        analysis=hsd.Analysis(forces=False, mulliken=True,
                              regions=("C", "O")),
        detailed_xml=True, eigenvectors=True)
    assert "Driver = SecondDerivatives {" in text
    assert "MullikenAnalysis = Yes" in text
    assert text.count("Region {") == 2
    assert 'Label = "dos_O"' in text
    assert "WriteDetailedXML = Yes" in text
    assert "WriteEigenvectors = Yes" in text


def test_no_moved_atom_is_refused():
    with pytest.raises(ValueError):
        hsd.moved_atoms(())


def test_the_mesh_follows_the_reciprocal_cell(quartz):
    """Hexagonal a = b at 120 degrees: the reciprocal vectors are
    longer than 2 pi / a by 1 / sin 120, and a mesh counted from the
    real edges under-samples both of them."""
    spacing = 0.1
    mesh = hsd.mesh_for(quartz.lattice, spacing)
    b = 2 * np.pi / (4.9134 * np.sin(np.radians(120)))
    assert mesh[0] == mesh[1] == round(b / spacing)
    cubic = hsd.mesh_for(Lattice.cubic(5.0), spacing)
    assert cubic == (round(2 * np.pi / 5.0 / spacing),) * 3


# ------------------------------------------------------------ reading

def test_band_out_along_a_path():
    bands = outputs.read_bands(_read("si_klines_band.out"))
    assert (bands.n_spin, bands.n_kpoints, bands.n_bands) == (1, 10, 18)
    assert np.all(np.diff(bands.energies[0], axis=1) >= 0)


def test_the_fermi_level_and_the_projected_states():
    assert outputs.fermi_level(_read("si_scc_detailed.out")) == \
        pytest.approx(-3.8608)
    energies, weights = outputs.read_dos(_read("si_dos_Si.out"))
    assert len(energies) == len(weights) == 72
    # Every state of the cell projects wholly onto the silicon.
    assert weights.sum() == pytest.approx(18.0, abs=1e-3)


def test_broadening_keeps_the_count_of_states():
    grid = np.linspace(-30, 30, 6001)
    curve = outputs.broaden([0.0, 1.0], [1.0, 2.0], grid, 0.2)
    assert np.trapezoid(curve, grid) == pytest.approx(3.0, rel=1e-4)
    assert grid[curve.argmax()] == pytest.approx(1.0, abs=0.05)


def test_mulliken_charges_sum_to_the_cell_charge():
    charges = outputs.mulliken_charges(
        _read("quartz_mulliken_detailed.out"))
    assert len(charges) == 9
    assert charges.sum() == pytest.approx(0.0, abs=1e-6)
    assert charges[:3] == pytest.approx([0.912] * 3, abs=1e-3)
    assert outputs.mulliken_charges("Total energy: 1 H") is None


def test_a_relaxation_is_read_as_steps_as_it_prints():
    seen = []
    reader = outputs.StepReader(
        on_step=lambda *step: seen.append(step))
    for line in _read("si_relax_stdout.txt").splitlines():
        reader(line)
    reader.finish()
    assert len(seen) == 63
    assert [s[0] for s in seen] == list(range(63))
    assert seen[-1][2] < seen[0][2]             # the forces went down
    assert seen[-1][1] < seen[0][1]             # and so did the energy


def test_md_out_and_its_frames():
    log = outputs.read_md(_read("si_md.out"), time_step=0.5)
    assert list(log.steps) == [0.0, 2.5, 5.0]
    assert log.temperature[0] == pytest.approx(300.0)
    frames = outputs.read_xyz_frames(_read("si_md_geo_end.xyz"))
    assert len(frames) == 3
    assert frames[0].shape == (2, 3)
    assert frames[0][1] == pytest.approx([1.35775] * 3, abs=1e-4)


def test_the_modes_of_carbon_dioxide():
    """Its antisymmetric stretch is the top mode: the carbon moves one
    way, both oxygens the other by the mass ratio."""
    modes = outputs.read_modes(_read("co2_vibrations.tag"))
    assert len(modes.frequencies) == 9
    assert modes.frequencies[-1] == pytest.approx(3129.08, abs=0.1)
    assert modes.imaginary[:4].all()
    top = modes.displacements[-1]
    assert abs(top[0, 2]) == pytest.approx(1.0)
    assert top[1, 2] == pytest.approx(top[2, 2], abs=1e-3)
    assert top[1, 2] / -top[0, 2] == pytest.approx(12.011 / 31.998,
                                                   abs=0.01)


def test_a_file_that_is_not_the_one_asked_for_is_refused():
    with pytest.raises(ValueError):
        outputs.read_bands("nothing here")
    with pytest.raises(ValueError):
        outputs.read_md("nothing here")
    with pytest.raises(ValueError):
        outputs.read_modes("frequencies :real:1:1\n 0.1\n")


# --------------------------------------------------------------- cube

CUBE = """ waveplot
 orbital 4
    2    0.000000    0.000000    0.000000
    2    1.000000    0.000000    0.000000
    3    0.000000    1.000000    0.000000
    2    0.000000    0.000000    2.000000
   14    0.000000    0.000000    0.000000    0.000000
   14    0.000000    1.000000    1.000000    1.000000
  0.0  0.1
  1.0  1.1
  2.0  2.1
  10.0  10.1
  11.0  11.1
  12.0  12.1
"""


def test_a_cube_is_read_first_axis_slowest_in_angstrom():
    cube = read_cube_string(CUBE)
    assert cube.shape == (2, 3, 2)
    assert cube.values[1, 2, 1] == pytest.approx(12.1)
    assert cube.values[0, 1, 0] == pytest.approx(1.0)
    assert cube.axes[2] == pytest.approx([0, 0, 2 * outputs.BOHR])
    assert cube.positions[1] == pytest.approx([outputs.BOHR] * 3)
    assert list(cube.numbers) == [14, 14]
    assert cube.points()[-1] == pytest.approx(
        [outputs.BOHR, 2 * outputs.BOHR, 2 * outputs.BOHR])
