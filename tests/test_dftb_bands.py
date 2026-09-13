"""DFTB+ ▸ Band structure, against a stand-in for DFTB+.

The stand-in reads the input it was given the way DFTB+ would: a mesh
run leaves charges and a Fermi level, a Klines run leaves one KPT block
per point of the path.  So what is tested is our side -- the two
invocations, the charges carried between them, the energies made
relative, the files and the report -- and the real binary's side is in
``tests/data/dftb``.
"""

import re
from pathlib import Path

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal import Lattice, Structure
from xtal.analysis import kpath
from xtal.modules import MODULES, Job
from xtal.modules import process as process_module

pytestmark = pytest.mark.skipif(not kpath.installed(),
                                reason="the band path needs ASE")

A = 5.431

FAKE = r'''
import pathlib, re, sys
text = pathlib.Path("dftb_in.hsd").read_text()
pathlib.Path("inputs.log").open("a").write(text + "\n=====\n")
if "Klines" in text:
    if "ReadInitialCharges = Yes" in text and \
            not pathlib.Path("charges.bin").exists():
        print("ERROR: no charges.bin", flush=True)
        sys.exit(1)
    block = text.split("Klines {")[1].split("}")[0]
    count = sum(int(line.split()[0]) for line in block.splitlines()
                if line.strip())
    out = []
    for k in range(count):
        out.append(f" KPT {k + 1} SPIN 1 KWEIGHT 1.0")
        for n, (e, occ) in enumerate([(-9.0 + 0.01 * k, 2.0),
                                      (-4.0, 2.0), (-2.5, 0.0),
                                      (1.0, 0.0)]):
            out.append(f"  {n + 1}  {e:.3f}  {occ:.5f}")
        out.append("")
    pathlib.Path("band.out").write_text("\n".join(out))
else:
    pathlib.Path("charges.bin").write_bytes(b"charges")
    for label in re.findall(r'Label = "([^"]+)"', text):
        pathlib.Path(f"{label}.out").write_text(
            " KPT 1 SPIN 1 KWEIGHT 1.0\n  -4.0  1.0\n  -2.5  1.0\n")
    pathlib.Path("detailed.out").write_text(
        "Fermi level:  -0.1250000000 H  -3.4014 eV\n")
print("DFTB+ done", flush=True)
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
    script = write_program(tmp_path, "dftb+", FAKE)
    monkeypatch.setenv("XTAL_DFTB", str(script))
    yield script
    process_module.clear_hints()


class _Folder:
    def __init__(self, path):
        self.path = Path(path)

    def log(self):
        return None


def _run(structure, folder, parameters, **params):
    _module, action = MODULES.find("dftb.band-structure")
    values = {"path": "", "density": 10.0,
              "hamiltonian": {"method": "scc",
                              "parameter_directory": str(parameters)}}
    values.update(params)
    return action.run(Job(structure=structure, params=values,
                          folder=folder))


def test_charges_on_a_mesh_then_eigenvalues_along_the_path(
        fake_dftb, silicon, parameters, tmp_path):
    run = tmp_path / "run"
    result = _run(silicon, _Folder(run), parameters)
    assert result.ok, result.detail

    mesh = (run / "scc" / "dftb_in.hsd").read_text()
    path = (run / "bands" / "dftb_in.hsd").read_text()
    assert "SupercellFolding" in mesh
    assert "Klines" in path
    assert "ReadInitialCharges = Yes" in path
    assert re.search(r"MaxSccIterations = 1\b", path)

    bands = result.report.bands[0]
    assert bands.fermi == pytest.approx(-3.4014)
    # Relative to the Fermi level: the highest occupied band was -4.0.
    assert bands.energies[0, 0, 1] == pytest.approx(-4.0 + 3.4014)
    assert len(bands.x) == bands.energies.shape[1]
    assert [label for _x, label in bands.ticks][0] == "Γ"
    assert bands.gap() == pytest.approx((-0.5986, 0.9014), abs=1e-4)
    assert (run / "bands.dat").read_text().startswith("# x(1/A)")
    assert (run / "bands.csv").is_file()
    assert result.report.zones[0].runs == \
        kpath.band_path(silicon.lattice).runs


def test_a_path_typed_by_the_user_is_the_one_run(fake_dftb, silicon,
                                                 parameters, tmp_path):
    result = _run(silicon, _Folder(tmp_path / "run"), parameters,
                  path="LGX")
    assert result.ok, result.detail
    ticks = [label for _x, label in result.report.bands[0].ticks]
    assert ticks == ["L", "Γ", "X"]


def test_a_path_through_a_point_the_cell_does_not_have_is_refused(
        fake_dftb, silicon, parameters, tmp_path):
    run = tmp_path / "run"
    result = _run(silicon, _Folder(run), parameters, path="GQ")
    assert not result.ok
    assert "not a point" in result.message
    assert not (run / "scc").exists()


def test_non_scc_skips_the_mesh(fake_dftb, silicon, parameters,
                                tmp_path):
    run = tmp_path / "run"
    result = _run(silicon, _Folder(run), parameters,
                  hamiltonian={"method": "non-scc",
                               "parameter_directory": str(parameters)})
    assert result.ok, result.detail
    assert not (run / "scc").exists()
    assert "ReadInitialCharges" not in \
        (run / "bands" / "dftb_in.hsd").read_text()
    # Mid-gap, between -4.0 and -2.5.
    assert result.report.bands[0].fermi == pytest.approx(-3.25)


def test_missing_parameters_are_a_sentence_before_anything_runs(
        fake_dftb, silicon, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    run = tmp_path / "run"
    result = _run(silicon, _Folder(run), empty)
    assert not result.ok
    assert "Si-Si.skf" in result.message
    assert not run.exists()


def test_without_a_workspace_it_still_answers(fake_dftb, silicon,
                                              parameters):
    result = _run(silicon, None, parameters)
    assert result.ok, result.detail
    assert result.report.bands


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

    settings = AppSettings("CrystalBuilderTest", f"Bands{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_the_dialog_draws_the_path_and_carries_the_panels_hamiltonian(
        window, qtbot, silicon, parameters):
    from PySide6.QtWidgets import QDialogButtonBox

    from xtalapp.dialogs import module_dialog
    document = window.new_document()
    document.set_structure(silicon, modified=False)
    window.dftb_dock.engine_forms["dftb"].set_values(
        {"method": "scc", "parameter_directory": str(parameters)})
    module, action = MODULES.find("dftb.band-structure")
    dialog = module_dialog(action.dialog)(module, action, window)
    qtbot.addWidget(dialog)

    assert dialog.path_edit.text() == "GXWKGLUWLK,UX"
    assert dialog.view.zone is not None
    assert dialog.view.runs == kpath.band_path(silicon.lattice).runs
    assert "SCC-DFTB" in dialog.summary.text()
    values = dialog.values()
    assert values["hamiltonian"]["method"] == "scc"
    assert values["hamiltonian"]["parameter_directory"] == \
        str(parameters)

    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    dialog.path_edit.setText("GQ")
    assert not ok.isEnabled()
    assert "not a point" in dialog.status.text()
    dialog.path_edit.setText("LGX")
    assert ok.isEnabled()
    assert dialog.view.runs == (("L", "G", "X"),)


def test_the_results_show_the_bands_and_the_zone_and_save_both(
        window, qtbot, fake_dftb, silicon, parameters, tmp_path,
        monkeypatch):
    from xtalapp.dialogs.dftb_run import BandStructureDialog

    document = window.new_document()
    document.set_structure(silicon, modified=False)

    def answer(module, action, parent=None, initial=None):
        return {"path": "", "density": 10.0,
                "hamiltonian": {"method": "scc",
                                "parameter_directory": str(parameters)}}
    monkeypatch.setattr(BandStructureDialog, "ask", staticmethod(answer))
    window.run_module_action("dftb", "band-structure")
    qtbot.waitUntil(lambda: window.module_worker is None, timeout=20000)

    dock = window.results_dock
    boxes = [b for b in dock._blocks if hasattr(b, "plot")]
    assert len(boxes) == 1
    box = boxes[0]
    box.low.setValue(-2.0)
    box.high.setValue(3.0)
    assert box.plot.energy_window == (-2.0, 3.0)
    assert any(hasattr(b, "view") for b in dock._blocks)
    written = {p.name for p in document.entry.path.rglob("*.png")}
    assert {"band_structure.png", "brillouin_zone.png"} <= written


def test_the_band_structure_exports_as_numbers_and_as_a_figure(
        tmp_path):
    from xtal.modules.report import Bands
    from xtalapp.bands import export_figure
    bands = Bands(x=np.linspace(0, 1, 5),
                  energies=np.array([[[-1.0, 1.0]] * 5]),
                  ticks=((0.0, "Γ"), (1.0, "X")))
    assert export_figure(bands, tmp_path / "b.dat").read_text() \
        .count("\n") == 7
    assert export_figure(bands, tmp_path / "b.csv").is_file()
    pytest.importorskip("matplotlib")
    figure = export_figure(bands, tmp_path / "b.svg", (-2.0, 2.0))
    assert "<svg" in figure.read_text()
