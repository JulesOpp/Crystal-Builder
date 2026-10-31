"""The thermochemistry and IR results in the window."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import Qt

from xtal.modules.report import Modes, Report, Spectrum
from xtalapp.docks.results import ResultsDock, select_mode
from xtalapp.widgets.choices import choice_enabled


@pytest.fixture
def dock(qtbot):
    widget = ResultsDock()
    qtbot.addWidget(widget)
    return widget


def _report():
    frequencies = np.array([0.0, 0.0, 0.0, 1600.0, 3650.0, 3750.0])
    modes = Modes(title="Vibrational modes", frequencies=frequencies,
                  displacements=np.zeros((6, 3, 3)),
                  elements=("O", "H", "H"), cart=np.zeros((3, 3)))
    spectrum = Spectrum(title="IR spectrum",
                        frequencies=frequencies[3:],
                        intensities=np.array([60.0, 5.0, 40.0]),
                        modes=(3, 4, 5))
    return Report(title="IR", blocks=(modes, spectrum))


def test_clicking_a_stick_selects_its_mode(dock):
    """A peak is chosen on the spectrum and watched from the mode
    table: the click has to land on the row of the stick nearest it,
    in the table's own numbering, rigid modes and all."""
    report = _report()
    dock.show_report(report)
    spectrum = report.spectra[0]
    assert select_mode(spectrum, dock, 3700.0) == 4
    view = next(w.view for w in dock._blocks if hasattr(w, "animate"))
    assert view.selectionModel().selectedRows()[0].row() == 4
    assert select_mode(spectrum, dock, 1500.0) == 3


def test_the_band_is_redrawn_at_the_width_asked(dock):
    report = _report()
    dock.show_report(report)
    widget = next(w for w in dock._blocks if hasattr(w, "fwhm"))
    narrow = widget.plot.curve.y.max()
    widget.fwhm.setValue(40.0)
    assert widget.plot.curve.y.max() < narrow
    # Drawn as IR is: wavenumber falling from left to right.
    assert widget.plot.curve.x[0] > widget.plot.curve.x[-1]


# ----------------------------------------------------------------------
#  The dialog and the panel's button
# ----------------------------------------------------------------------

@pytest.fixture
def window(qtbot, tmp_path):
    from PySide6.QtWidgets import QWidget

    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    class Viewport(QWidget):
        def __init__(self, document, parent=None):
            super().__init__(parent)
            self.document = document

    settings = AppSettings("CrystalBuilderTest", f"Thermo{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=Viewport, settings=settings)
    qtbot.addWidget(win)
    return win


def _open(window, tmp_path, structure, name="s"):
    from xtal.io import write_cif

    path = tmp_path / f"{name}.cif"
    write_cif(structure, path)
    window.open_path(path)


def _dialog(qtbot, window, action="thermo"):
    from xtal.modules.registry import MODULES
    from xtalapp.dialogs.thermo import ThermoDialog

    module, found = MODULES.find(f"forcefield.{action}")
    dialog = ThermoDialog(module, found, window)
    qtbot.addWidget(dialog)
    return dialog


def test_the_dialog_is_what_the_actions_ask_for():
    """Registered by name, so the frozen app collects it."""
    from xtal.modules.registry import MODULES
    from xtalapp.dialogs import module_dialog

    for name in ("thermo", "infrared"):
        _module, action = MODULES.find(f"forcefield.{name}")
        assert action.dialog == "thermo"
    assert module_dialog("thermo").__name__ == "ThermoDialog"


def test_the_dialog_opens_on_the_panels_engine_and_options(
        qtbot, window, tmp_path, rutile):
    _open(window, tmp_path, rutile)
    panel = window.ff_dock
    dialog = _dialog(qtbot, window)
    values = dialog.values()
    assert values["engine"] == panel.engine_name()
    assert values["engine_options"] == panel.options_for(
        panel.engine_name())


def test_a_molecule_in_a_box_is_offered_as_a_molecule(
        qtbot, window, tmp_path, rutile):
    from tests.conftest_ff import water

    _open(window, tmp_path, water(), "water")
    dialog = _dialog(qtbot, window)
    assert dialog.values()["system"] == "molecule"
    assert dialog.form.widgets["sigma"].isVisibleTo(dialog)
    _open(window, tmp_path, rutile, "rutile")
    crystal = _dialog(qtbot, window)
    assert crystal.system() == "crystal"
    assert not crystal.form.widgets["sigma"].isVisibleTo(crystal)


def test_the_estimate_counts_the_evaluations_and_times_one(
        qtbot, window, tmp_path, rutile):
    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    dialog.form.set_values({"method": "gamma"})
    dialog.time_one_evaluation()
    qtbot.waitUntil(lambda: " x " in dialog.estimate.text(),
                    timeout=20000)
    text = dialog.estimate.text()
    assert "37 evaluations x" in text
    assert "Gamma only" in text


def test_choosing_another_engine_times_that_one_off_the_gui_thread(
        qtbot, window, tmp_path, rutile, monkeypatch):
    """Timed once at open, the line read "timing one..." for good
    after the engine changed; and timed on the GUI thread, a model
    not yet downloaded froze the dialog for the download."""
    import threading

    from xtal.ff.registry import ENGINES

    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    qtbot.waitUntil(lambda: " x " in dialog.estimate.text(),
                    timeout=20000)
    threads, real = [], ENGINES.build

    def build(name, *args, **kwargs):
        threads.append(threading.get_ident())
        return real(name, *args, **kwargs)

    monkeypatch.setattr(ENGINES, "build", build)
    form = dialog.engine_forms["uff"]
    form.set_values({"parameter_set": "uff"})
    qtbot.waitUntil(lambda: dialog._engine_key() in dialog._seconds,
                    timeout=20000)
    assert threads and threading.get_ident() not in threads
    assert " x " in dialog.estimate.text()


def test_the_estimate_counts_the_charge_flux_solves(
        qtbot, window, tmp_path, rutile, monkeypatch):
    from xtalapp.dialogs.thermo import ThermoDialog

    monkeypatch.setattr(ThermoDialog, "time_one_evaluation",
                        lambda self: None)
    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    dialog.form.set_values({"ir": True, "ir_charges": "flux"})
    assert "36 EQeq solves" in dialog.estimate.text()


def test_with_phonopy_the_estimate_counts_its_displacements(
        qtbot, window, tmp_path, rutile):
    """Rutile's four evaluations (three displacements and the
    reference) in a 3x3x4 supercell; the estimate saying 37 would
    put somebody off the route that is ten times cheaper."""
    pytest.importorskip("phonopy")
    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    dialog.form.set_values({"method": "phonopy"})
    dialog.time_one_evaluation()
    qtbot.waitUntil(lambda: " x " in dialog.estimate.text(),
                    timeout=20000)
    text = dialog.estimate.text()
    assert "4 evaluations x" in text
    assert "phonopy, supercell 3x3x4" in text
    assert dialog.form.widgets["supercell"].isVisibleTo(dialog)
    dialog.form.set_values({"method": "gamma"})
    assert not dialog.form.widgets["supercell"].isVisibleTo(dialog)


def test_a_supercell_over_the_limit_is_said_and_run_is_disabled(
        qtbot, window, tmp_path, rutile):
    pytest.importorskip("phonopy")
    from PySide6.QtWidgets import QDialogButtonBox

    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    dialog.form.set_values({"method": "phonopy",
                            "supercell": "30 30 30"})
    assert "phonon supercell would have" in dialog.estimate.text()
    assert not dialog.buttons.button(
        QDialogButtonBox.Ok).isEnabled()


def test_without_phonopy_the_phonopy_rows_are_greyed_and_name_the_extra(
        qtbot, window, tmp_path, rutile, monkeypatch):
    from xtal.ff import phonons

    monkeypatch.setattr(phonons, "installed", lambda: False)
    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    method = dialog.form.widgets["method"]
    assert not choice_enabled(method, method.findData("phonopy"))
    assert not dialog.form.widgets["supercell"].isEnabled()
    assert dialog.phonopy_note.isVisibleTo(dialog)
    assert "phonons extra" in dialog.phonopy_note.text()
    assert "Preferences &gt; Engines" in dialog.phonopy_note.text()
    assert dialog.method() == "gamma"


def test_the_panel_button_is_disabled_during_an_optimisation(window):
    panel = window.ff_dock
    assert panel.thermo_button.text() == "Thermochemistry..."
    panel._set_running(True)
    assert not panel.thermo_button.isEnabled()
    panel._set_running(False)


def test_the_panel_button_runs_the_module_action(
        window, monkeypatch, tmp_path, rutile):
    _open(window, tmp_path, rutile)
    calls = []
    monkeypatch.setattr(window, "run_module_action",
                        lambda m, a: calls.append((m, a)))
    window.ff_dock.thermo_button.click()
    assert calls == [("forcefield", "thermo")]


def test_a_landed_run_is_summed_up_in_the_panel(window):
    """The one line in the panel; the rest is in the Results panel."""
    from xtal.modules.job import JobResult

    window.ff_dock.thermo_landed(JobResult(
        message="G(298.15 K) = -12.000 kcal/mol per formula unit"))
    assert "G(298.15 K)" in window.ff_dock.report.toPlainText()


def test_the_modes_of_a_thermo_run_animate_in_the_transport_bar(
        qtbot, window, tmp_path, rutile):
    from tests.test_thermo_module import _run

    _open(window, tmp_path, rutile)
    result = _run(rutile)
    window.results_dock.show_report(result.report)
    modes = next(w for w in window.results_dock._blocks
                 if hasattr(w, "animate"))
    opened = []
    transport = window.trajectory_dock
    original = transport.open_trajectory
    transport.open_trajectory = lambda t: opened.append(t) or True
    try:
        modes.animate.click()
    finally:
        transport.open_trajectory = original
    assert len(opened) == 1
    assert opened[0].n_frames > 1


def test_a_run_from_the_button_lands_in_both_panels(
        qtbot, window, tmp_path, rutile, monkeypatch):
    """The whole path a person takes: the button, the dialog's values,
    a worker, and the run's line in the Force Field panel as well as
    its tables in the Results panel."""
    from xtal.modules.registry import MODULES
    from xtal.params import coerce
    from xtalapp.dialogs.thermo import ThermoDialog

    _open(window, tmp_path, rutile)
    _module, action = MODULES.find("forcefield.thermo")
    values = coerce(action.params, {"engine": "uff"})
    monkeypatch.setattr(ThermoDialog, "ask",
                        classmethod(lambda cls, *a, **k: values))
    window.ff_dock.thermo_button.click()
    qtbot.waitUntil(
        lambda: window.module_runner.module_worker is None,
        timeout=60000)
    assert "G(298.15 K)" in window.ff_dock.report.toPlainText()
    assert window.results_dock._blocks


def test_analytic_is_offered_only_for_an_engine_with_a_hessian(
        qtbot, window, tmp_path, rutile, monkeypatch):
    """Greyed under UFF, offered under MACE, and the line then says
    the memory as well as the rows -- memory is what the route costs.
    Nothing is evaluated: MACE never loads into the test process,
    and CI has no mace, so it is declared available here -- unavailable,
    the dialog says why instead of the cost."""
    from xtalapp.dialogs import thermo as thermo_dialog
    from xtalapp.dialogs.thermo import ThermoDialog

    monkeypatch.setattr(ThermoDialog, "time_one_evaluation",
                        lambda self: None)
    monkeypatch.setattr(thermo_dialog, "_unavailable",
                        lambda name, values: "")
    _open(window, tmp_path, rutile)
    dialog = _dialog(qtbot, window)
    method = dialog.form.widgets["method"]
    analytic = method.findData("analytic")
    dialog._select(dialog.engine, "uff")
    assert not choice_enabled(method, analytic)
    assert "no second derivatives" in method.itemData(
        analytic, Qt.ToolTipRole)
    dialog._select(dialog.engine, "mace")
    assert choice_enabled(method, analytic)
    assert not method.itemData(analytic, Qt.ToolTipRole)
    dialog.form.set_values({"method": "analytic"})
    assert dialog.method() == "analytic"
    text = dialog.estimate.text()
    assert "18 rows" in text and "GB beside the model" in text
    dialog._select(dialog.engine, "uff")
    assert method.currentData() == "auto"
