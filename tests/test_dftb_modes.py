"""DFTB+ ▸ Vibrational modes, against stand-ins that write what DFTB+
24.1 and ``modes`` wrote for carbon dioxide."""

from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal import Lattice, Structure
from xtal.modules import MODULES, Job
from xtal.modules import process as process_module
from xtal.modules.dftb_runs import modes as modes_run
from xtal.modules.report import Modes

DATA = Path(__file__).resolve().parent / "data" / "dftb"

FAKE_DFTB = r'''
import pathlib, shutil
text = pathlib.Path("dftb_in.hsd").read_text()
if "SecondDerivatives" in text:
    pathlib.Path("seen.hsd").write_text(text)
    shutil.copy(DATA + "/co2_hessian.out", "hessian.out")
    # What the run leaves: the last displaced geometry's energy.
    pathlib.Path("detailed.out").write_text(
        "Total energy:  -8.2535808974 H  -224.5914 eV\n")
else:
    pathlib.Path("seen_reference.hsd").write_text(text)
    pathlib.Path("detailed.out").write_text(
        "Total energy:  -8.2535939638 H  -224.5917 eV\n")
'''

FAKE_MODES = r'''
import pathlib, shutil
pathlib.Path("seen_modes.hsd").write_text(
    pathlib.Path("modes_in.hsd").read_text())
shutil.copy(DATA + "/co2_vibrations.tag", "vibrations.tag")
'''


@pytest.fixture
def co2():
    return Structure.from_arrays(
        Lattice.cubic(12.0), ["C", "O", "O"],
        [[0.5, 0.5, 0.5], [0.5, 0.5, 0.5 + 1.17 / 12],
         [0.5, 0.5, 0.5 - 1.17 / 12]], space_group="P1")


@pytest.fixture
def parameters(tmp_path):
    directory = tmp_path / "skf"
    directory.mkdir()
    for a in ("C", "O"):
        for b in ("C", "O"):
            (directory / f"{a}-{b}.skf").write_text("1.0 10\n")
    return directory


@pytest.fixture
def fakes(tmp_path, monkeypatch, parameters):
    process_module.clear_hints()
    prefix = f"DATA = {str(DATA)!r}\n"
    monkeypatch.setenv("XTAL_DFTB", str(write_program(
        tmp_path, "dftb+", prefix + FAKE_DFTB)))
    monkeypatch.setenv("XTAL_MODES", str(write_program(
        tmp_path, "modes", prefix + FAKE_MODES)))
    monkeypatch.setenv("DFTB_PREFIX", str(parameters))
    yield
    process_module.clear_hints()


class _Folder:
    def __init__(self, path):
        self.path = Path(path)

    def log(self):
        return None


def _run(structure, run, parameters, **params):
    _module, action = MODULES.find("dftb.modes")
    values = action.coerce(params)
    values["hamiltonian"] = {"method": "scc",
                             "parameter_directory": str(parameters)}
    values["frozen"] = params.get("frozen", [])
    return action.run(Job(structure=structure, params=values,
                          folder=_Folder(run)))


def test_the_hessian_then_its_modes(fakes, co2, parameters, tmp_path):
    run = tmp_path / "run"
    result = _run(co2, run, parameters)
    assert result.ok, result.detail
    assert "Driver = SecondDerivatives {" in \
        (run / "seen.hsd").read_text()
    seen = (run / "seen_modes.hsd").read_text()
    assert "PlotModes = 1:-1" in seen
    assert 'Hessian = {\n  <<< "hessian.out"' in seen

    block = result.report.modes[0]
    assert block.n_modes == 9
    assert block.frequencies[-1] == pytest.approx(3129.08, abs=0.1)
    # The fixture's geometry was not relaxed, and the table says so.
    assert block.n_imaginary == 4
    assert "relax first" in result.message
    assert block.displacements.shape == (9, 3, 3)
    assert (run / "modes.dat").read_text().count("\n") == 10


def test_dftb_modes_report_carries_a_thermochemistry_table(
        fakes, co2, parameters, tmp_path):
    """G from DFTB+ reads as G from any other engine: the same Summary,
    curves and thermo.dat, E from a single point at the reference and
    not the last displaced geometry, and the rigid motions ``modes``
    leaves in projected out -- CO2 in a box is a linear molecule, so
    its two bends are what is imaginary, not five rotations and
    translations besides."""
    run = tmp_path / "run"
    result = _run(co2, run, parameters, temperature=300.0)
    assert result.ok, result.detail
    assert "Driver" not in (run / "seen_reference.hsd").read_text()
    table = result.report.tables[0]
    assert table.title == "Summary"
    rows = {row.texts[0]: row.texts for row in table.rows}
    assert rows["System"][1] == "molecule (ideal gas)"
    assert float(rows["E (electronic)"][1]) == pytest.approx(
        -8.2535939638 * 627.5094740631, abs=1e-3)
    assert "G(300 K)" in rows
    assert rows["Imaginary modes"][1] == "2"
    assert "DFTB+" in rows["Hessian"][1]
    assert len(result.report.curves) == 2
    assert (run / "thermo.dat").is_file()
    assert result.answer.g == pytest.approx(
        float(rows["G(300 K)"][1]), abs=1e-3)
    assert [code for code, _ in result.warnings] == ["IMAGINARY_MODES"]


def test_frozen_atoms_are_left_out_of_the_hessian(co2):
    co2.ensure_labels()
    job = Job(params={"freeze": True, "frozen": [co2.sites[0].label]})
    moved = modes_run.moved_atoms(co2, job)
    assert moved == (2, 3)
    assert "Atoms = 2:3" in modes_run.modes_input(moved)


def test_a_mode_plays_as_one_period_of_frames(co2):
    displacements = np.zeros((1, 3, 3))
    displacements[0, 0, 2] = 1.0
    block = Modes(frequencies=np.array([1000.0]),
                  displacements=displacements,
                  elements=("C", "O", "O"),
                  cart=np.asarray(co2.lattice.to_cart(co2.frac)),
                  lattice=np.asarray(co2.lattice.matrix))
    trajectory = modes_run.mode_trajectory(block, 0, amplitude=0.25,
                                           frames=8)
    assert trajectory.n_frames == 8
    moves = [f.cart[0, 2] - block.cart[0, 2] for f in trajectory]
    assert max(moves) == pytest.approx(0.25)
    assert min(moves) == pytest.approx(-0.25)
    assert all(np.allclose(f.cart[1:], block.cart[1:])
               for f in trajectory)


def test_translations_are_not_called_imaginary():
    block = Modes(frequencies=np.array([-39.4, -4.8, 413.2, -120.0]))
    assert block.n_imaginary == 1


# ------------------------------------------------------------ the GUI

@pytest.fixture
def window(qtbot, tmp_path):
    pytest.importorskip("pytestqt")
    from PySide6.QtWidgets import QWidget

    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    class _Stub(QWidget):
        def __init__(self, document, parent=None):
            super().__init__(parent)
            self.document = document

    settings = AppSettings("CrystalBuilderTest", f"Modes{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_animate_plays_the_selected_mode_in_the_transport_bar(
        window, qtbot, fakes, co2, parameters, monkeypatch):
    from xtalapp.dialogs.dftb_run import DftbRunDialog

    document = window.new_document()
    document.set_structure(co2, modified=False)
    monkeypatch.setattr(DftbRunDialog, "ask", staticmethod(
        lambda module, action, parent=None, initial=None: {
            "delta": 1e-4, "freeze": True, "frozen": [],
            "hamiltonian": {"method": "scc",
                            "parameter_directory": str(parameters)}}))
    window.run_module_action("dftb", "modes")
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    boxes = [b for b in window.results_dock._blocks
             if hasattr(b, "animate")]
    assert len(boxes) == 1
    box = boxes[0]
    assert box.view.selectionModel().selectedRows()[0].row() == 8
    box.animate.click()
    assert document.is_playing
    assert document.playback.n_frames == modes_run.FRAMES
