"""The refinement workbench: opening it, loading a pattern, running a
step and reading its answer back."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal import powder  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    """Stands in for the VTK viewport."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Wb{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def bench(window):
    window.actions_["refine_workbench"].trigger()
    return window._workbenches[id(window.current_document())]


def test_the_modules_menu_opens_one_workbench_per_document(window):
    """A second window over the same structure would file a second
    set of runs against it with nothing to say which is current."""
    window.actions_["refine_workbench"].trigger()
    first = window.open_refine_workbench()
    assert window.open_refine_workbench() is first
    assert first.isVisible()


def test_the_workbench_greys_out_naming_the_refine_extra(
        window, monkeypatch, rutile_xy):
    monkeypatch.setattr(powder, "available", lambda: False)
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    assert not bench.run_button.isEnabled()
    from xtal import install

    assert install.command("refine") in bench.run_button.toolTip()


def test_run_waits_for_a_pattern(bench):
    assert not bench.run_button.isEnabled()
    assert "Load a pattern" in bench.run_button.toolTip()


def test_loading_an_xy_draws_the_observed_trace(bench, rutile_xy):
    assert bench.load_pattern(rutile_xy)
    assert "3000 points" in bench.pattern_label.text()
    if bench.plot.available:
        assert bench.plot.traces == ["observed"]
    assert bench.run_button.isEnabled()


def test_a_file_that_is_not_a_pattern_is_refused_with_the_reason(
        bench, tmp_path):
    path = tmp_path / "notes.xy"
    path.write_text("hello\n", encoding="utf-8")
    assert not bench.load_pattern(path)
    assert "no two-column data" in bench.status.text()


def _run_peaks(bench, qtbot, rutile_xy):
    bench.load_pattern(rutile_xy)
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.run_step()
    return blocker.args[0]


def test_a_peak_run_fills_the_table_and_the_calculated_curve(
        bench, qtbot, rutile_xy):
    result = _run_peaks(bench, qtbot, rutile_xy)
    assert result.ok, result.message
    assert bench.table.rowCount() == len(bench.peaks.peaks) > 10
    if bench.plot.available:
        assert {"calculated", "difference", "observed"} <= \
            set(bench.plot.traces)
    assert bench.worker is None
    assert bench.run_button.isEnabled()


def test_unticking_a_peak_takes_it_out_of_use(bench, qtbot, rutile_xy):
    _run_peaks(bench, qtbot, rutile_xy)
    before = bench.peaks.n_used
    row = next(r for r, p in enumerate(bench.peaks.peaks) if p.use)
    bench.table.item(row, 0).setCheckState(Qt.Unchecked)
    assert bench.peaks.n_used == before - 1
    assert not bench.peaks.peaks[row].use


def test_a_run_is_filed_under_the_document_it_was_started_from(
        window, qtbot, rutile_cif, rutile_xy):
    document = window.open_path(rutile_cif)
    bench = window.open_refine_workbench()
    assert bench.document is document
    _run_peaks(bench, qtbot, rutile_xy)
    assert list(document.entry.path.rglob("peaks.csv"))


def test_double_clicking_a_pattern_in_the_workspace_opens_it_here(
        window, rutile_xy):
    window.open_artifact("pattern", str(rutile_xy))
    bench = window.open_refine_workbench()
    assert bench.data is not None
    assert bench.data.name == "rutile"


def test_the_wavelength_box_is_live_only_for_a_synchrotron(bench):
    """For a tube the wavelengths are the standard ones; a live box
    showing 0 Å reads as though that were what is used."""
    wavelength = bench.data_form.widgets["wavelength"]
    assert not wavelength.isEnabled()
    bench.data_form.set_values({"radiation": "synchrotron"})
    assert wavelength.isEnabled()
