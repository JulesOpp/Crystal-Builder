"""DFTB+ ▸ Density of states, against a stand-in that writes the
projected files DFTB+ 24.1 wrote for silicon."""

from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal import Lattice, Structure
from xtal.modules import MODULES, Job
from xtal.modules import process as process_module
from xtal.modules.dftb_runs import dos as dos_run

DATA = Path(__file__).resolve().parent / "data" / "dftb"
A = 5.431

FAKE = r'''
import pathlib, re
text = pathlib.Path("dftb_in.hsd").read_text()
pathlib.Path("dftb_in.copy").write_text(text)
source = pathlib.Path(SOURCE).read_text()
shells = "ShellResolved = Yes" in text
for label in re.findall(r'Label = "([^"]+)"', text):
    if shells:
        for shell in (1, 2, 3):
            pathlib.Path(f"{label}.{shell}.out").write_text(source)
    else:
        pathlib.Path(f"{label}.out").write_text(source)
pathlib.Path("detailed.out").write_text(
    "Fermi level:  -0.1418822000 H  -3.8608 eV\n")
'''


@pytest.fixture
def silicon():
    matrix = np.array([[0, A / 2, A / 2], [A / 2, 0, A / 2],
                       [A / 2, A / 2, 0]])
    return Structure.from_arrays(Lattice(matrix), ["Si", "Si"],
                                 [[0, 0, 0], [0.25, 0.25, 0.25]],
                                 space_group="P1")


@pytest.fixture
def parameters(tmp_path):
    directory = tmp_path / "skf"
    directory.mkdir()
    (directory / "Si-Si.skf").write_text("1.0 10\n")
    return directory


@pytest.fixture
def fake_dftb(tmp_path, monkeypatch):
    process_module.clear_hints()
    body = f"SOURCE = {str(DATA / 'si_dos_Si.out')!r}\n" + FAKE
    monkeypatch.setenv("XTAL_DFTB",
                       str(write_program(tmp_path, "dftb+", body)))
    yield
    process_module.clear_hints()


class _Folder:
    def __init__(self, path):
        self.path = Path(path)

    def log(self):
        return None


def _run(structure, run, parameters, **params):
    _module, action = MODULES.find("dftb.dos")
    values = {"spacing": 0.5, "sigma": 0.1, "shells": False,
              "hamiltonian": {"method": "scc",
                              "parameter_directory": str(parameters)}}
    values.update(params)
    return action.run(Job(structure=structure, params=values,
                          folder=_Folder(run)))


def test_every_element_is_a_region_and_the_curve_counts_electrons(
        fake_dftb, silicon, parameters, tmp_path):
    """Silicon's two atoms hold eight valence electrons, and the
    broadened curve below the Fermi level integrates to them -- the
    check a reader makes of any density of states."""
    run = tmp_path / "run"
    result = _run(silicon, run, parameters)
    assert result.ok, result.detail
    written = (run / "dftb_in.hsd").read_text()
    assert 'Label = "dos_Si"' in written
    assert "ShellResolved = No" in written

    block = result.report.doses[0]
    assert [label for label, _y in block.partial] == ["Si"]
    below = block.energies <= 0.0
    assert np.trapezoid(block.total[below], block.energies[below]) == \
        pytest.approx(8.0, abs=0.05)
    assert (run / "dos.dat").read_text().startswith("# E-E_F(eV)")


def test_shells_are_labelled_s_p_d(fake_dftb, silicon, parameters,
                                   tmp_path):
    result = _run(silicon, tmp_path / "run", parameters, shells=True)
    assert result.ok, result.detail
    labels = [label for label, _y in result.report.doses[0].partial]
    assert labels == ["Si s", "Si p", "Si d"]


def test_broadening_is_a_gaussian_of_the_width_asked_for(tmp_path):
    (tmp_path / "dos_Si.out").write_text(
        " KPT 1 SPIN 1 KWEIGHT 1.0\n   0.000  1.000\n")
    narrow = dos_run.projected(tmp_path, ["Si"], 0.0, 0.05)
    wide = dos_run.projected(tmp_path, ["Si"], 0.0, 0.4)
    assert narrow.total.max() > 4 * wide.total.max()
    for block in (narrow, wide):
        assert np.trapezoid(block.total, block.energies) == \
            pytest.approx(2.0, rel=1e-3)


# ------------------------------------------------------------ the GUI

@pytest.fixture
def dock(qtbot):
    pytest.importorskip("pytestqt")
    from xtalapp.docks.results import ResultsDock
    widget = ResultsDock()
    qtbot.addWidget(widget)
    return widget


def _blocks():
    from xtal.modules.report import Bands, Dos
    energies = np.linspace(-5, 5, 101)
    bands = Bands(x=np.linspace(0, 1, 4),
                  energies=np.array([[[-1.0, 1.0]] * 4]),
                  ticks=((0.0, "G"), (1.0, "X")))
    density = Dos(energies=energies, total=np.exp(-energies ** 2),
                  partial=(("Si", np.exp(-energies ** 2)),))
    return bands, density


def test_a_dos_from_the_same_run_stands_beside_the_bands(dock):
    from xtal.modules.report import Report
    bands, density = _blocks()
    dock.show_report(Report(blocks=(bands, density)))
    boxes = [b for b in dock._blocks if hasattr(b, "plot")]
    assert len(boxes) == 1                      # not a second block
    box = boxes[0]
    assert box.dos is not None
    box.low.setValue(-2.0)
    assert box.dos.energy_window[0] == -2.0
    assert box.plot.energy_window[0] == -2.0


def test_a_dos_alone_is_a_block_of_its_own(dock):
    from xtal.modules.report import Report
    _bands, density = _blocks()
    dock.show_report(Report(blocks=(density,)))
    boxes = [b for b in dock._blocks if hasattr(b, "plot")]
    assert len(boxes) == 1
    assert boxes[0].plot.dos is density
