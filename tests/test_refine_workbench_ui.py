"""The refinement workbench: opening it, loading a pattern, running a
step and reading its answer back."""

from __future__ import annotations

import dataclasses

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


# -- indexing -----------------------------------------------------------

def test_the_bravais_boxes_are_the_fourteen_lattices(bench):
    from xtal.powder.index import BRAVAIS

    assert list(bench.bravais.boxes) == [s for s, _l in BRAVAIS]
    assert bench.values("index")["bravais"] == "all"
    for symbol in ("aP", "mP", "mC"):
        bench.bravais.boxes[symbol].setChecked(False)
    assert "aP" not in bench.values("index")["bravais"]
    assert "oC" in bench.values("index")["bravais"]


def test_unticking_every_lattice_is_refused_not_read_as_all(bench):
    """Empty is what ``xtal run`` reads as every lattice; a search of
    everything is the opposite of what unticking all of them meant."""
    from xtal.modules import powder as steps
    from xtal.powder.data import PowderError
    from xtal.powder.index import _lattices

    for box in bench.bravais.boxes.values():
        box.setChecked(False)
    options = steps.index_options(bench.values("index"))
    with pytest.raises(PowderError, match="tick at least one"):
        _lattices(options.bravais, ())


def test_indexing_is_handed_the_peaks_as_they_are_ticked(
        bench, qtbot, rutile_xy):
    """TOPAS's "comment out a peak" reaches the search -- and a copy
    of it, so an untick made while the search runs is the next run's."""
    _run_peaks(bench, qtbot, rutile_xy)
    row = next(r for r, p in enumerate(bench.peaks.peaks) if p.use)
    bench.table.item(row, 0).setCheckState(Qt.Unchecked)
    given = bench._given("index")
    assert not given.peaks[row].use
    assert len(given.for_indexing().usable()) == bench.peaks.n_used
    bench.table.item(row, 0).setCheckState(Qt.Checked)
    assert not given.peaks[row].use
    assert bench._given("peaks") is None


@pytest.mark.slow
def test_an_index_run_fills_the_cell_table_and_draws_the_chosen_cell(
        bench, qtbot, rutile_xy):
    _run_peaks(bench, qtbot, rutile_xy)
    bench.steps.setCurrentRow(1)
    assert bench.current_step == "index"
    assert bench.tables.currentWidget() is bench.cell_table
    for symbol, box in bench.bravais.boxes.items():
        box.setChecked(symbol == "tP")
    bench.step_forms["index"].set_values(
        {"longest_axis": 6.0, "budget": 10.0, "rank_groups": 0,
         "zero_error": 0.0})
    with qtbot.waitSignal(bench.stepFinished, timeout=120000) as blocker:
        bench.run_step()
    result = blocker.args[0]
    assert result.ok, result.message
    assert bench.cell_table.rowCount() == len(bench.cells.rows) > 0
    assert bench.cell_table.item(0, 2).text() == "tP"
    assert bench.cell_table.selectionModel().selectedRows()[0].row() == 0
    if bench.plot.available:
        assert "reflections" in bench.plot.traces
    # the peaks survive an index run: the next search reads them again
    assert bench.peaks is not None


# -- Pawley -------------------------------------------------------------

def _run_pawley(bench, qtbot, cell="4.5948 4.5948 2.9572",
                group="P42/mnm"):
    bench.steps.setCurrentRow(2)
    assert bench.current_step == "pawley"
    bench.step_forms["pawley"].set_values({"cell": cell,
                                           "space_group": group})
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.run_step()
    return blocker.args[0]


def test_choosing_a_cell_fills_the_pawley_form(bench, rutile_xy):
    """Indexing's table is the Pawley step's input: the chosen row's
    cell, fitted in its best class's group -- or its lattice's own
    when no class was ranked."""
    from xtal.powder.index import GroupClass, IndexResult, IndexRow

    bench.load_pattern(rutile_xy)
    row = IndexRow(rank=1, system="tetragonal", centring="P",
                   cell=(4.5948, 4.5948, 2.9572, 90, 90, 90),
                   cell_esd=(0,) * 6, volume=62.4, fom=None, n_indexed=15,
                   n_lines=15, confidence="medium", caveats=(),
                   lebail_rwp=None, found_by=(),
                   lattice_group="P 4/m m m")
    other = dataclasses.replace(row, rank=2, classes=[GroupClass(
        "P 42/- n m", ("P 42/m n m",), 0.0, False,
        representative="P 42/m n m")])
    bench.cells = IndexResult(rows=[row, other], best=None, stopped=False,
                              systems_searched=("tetragonal",),
                              complete={}, wavelength=1.5406,
                              two_theta_range=(20.0, 80.0))
    bench._fill_cells()
    values = bench.values("pawley")
    assert values["cell"].split()[:3] == ["4.59480", "4.59480", "2.95720"]
    assert values["space_group"] == "P 4/m m m"
    bench.cell_table.selectRow(1)
    assert bench.values("pawley")["space_group"] == "P 42/m n m"


def test_the_pawley_form_starts_from_the_open_structure(window,
                                                        rutile_cif):
    """Refining a known phase's cell against a new measurement needs
    no indexing."""
    window.open_path(rutile_cif)
    bench = window.open_refine_workbench()
    values = bench.values("pawley")
    assert values["cell"].split()[0] == "4.59400"
    assert "42" in values["space_group"]


def test_a_pawley_fit_fills_the_result_and_the_reflection_list(
        bench, qtbot, rutile_xy):
    bench.load_pattern(rutile_xy)
    result = _run_pawley(bench, qtbot)
    assert result.ok, result.message
    assert bench.tables.currentWidget() is bench.reflection_table
    assert bench.reflection_table.rowCount() == \
        len(bench.pawley.reflections) > 10
    assert "GoF" in bench.pawley_label.text()
    assert "a 4.5939" in bench.pawley_label.text()
    # no structure open: nothing to apply to, but a new one can start
    assert not bench.apply_button.isEnabled()
    assert "No structure" in bench.apply_button.toolTip()
    assert bench.new_button.isEnabled()


def test_applying_a_pawley_cell_is_one_undo_step(
        window, qtbot, rutile_cif, rutile_xy):
    """On the document the workbench was opened for, fractional
    coordinates kept, and undone in one Ctrl+Z."""
    document = window.open_path(rutile_cif)
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    before = document.structure.lattice.parameters
    fracs = [site.frac.copy() for site in document.structure.sites]
    steps_before = len(document.stack._done)
    assert _run_pawley(bench, qtbot).ok
    assert bench.apply_button.isEnabled(), bench.apply_button.toolTip()
    bench.apply_cell()
    assert len(document.stack._done) == steps_before + 1
    assert document.undo_label == "Apply Pawley cell"
    after = document.structure.lattice.parameters
    assert after[0] == pytest.approx(bench.pawley.cell[0])
    for site, frac in zip(document.structure.sites, fracs, strict=True):
        assert site.frac == pytest.approx(frac)
    document.undo()
    assert document.structure.lattice.parameters == pytest.approx(before)


def test_a_cell_of_another_lattice_is_not_offered_to_the_structure(
        window, qtbot, quartz_cif, rutile_xy):
    window.open_path(quartz_cif)
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    assert _run_pawley(bench, qtbot).ok
    assert not bench.apply_button.isEnabled()
    assert "Not this structure's cell" in bench.apply_button.toolTip()


def test_a_new_structure_from_the_cell_opens_in_a_tab_of_its_own(
        bench, window, qtbot, rutile_xy):
    bench.load_pattern(rutile_xy)
    assert _run_pawley(bench, qtbot).ok
    tabs = window.tabs.count()
    document = bench.new_structure()
    assert window.tabs.count() == tabs + 1
    structure = document.structure
    assert not structure.sites
    assert structure.space_group.number == 136
    assert structure.lattice.parameters[2] == \
        pytest.approx(bench.pawley.cell[2])
    assert document.entry is not None
    assert document.entry.name.startswith("rutile-pawley")


# -- asked for 2026-09-25 ------------------------------------------------

def test_loading_a_pattern_sets_the_fit_ranges_to_the_data(bench,
                                                           rutile_xy):
    bench.load_pattern(rutile_xy)
    for step in ("peaks", "pawley"):
        values = bench.values(step)
        assert values["start"] == pytest.approx(20.0)
        assert values["finish"] == pytest.approx(79.98)


def test_loading_through_the_dialog_keeps_the_workbench_in_front(
        bench, rutile_xy, monkeypatch):
    """A native file dialog handed activation back to the main window,
    which then stood in front as though the workbench had closed."""
    from xtalapp.refine import workbench as module

    monkeypatch.setattr(module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(rutile_xy), "")))
    raised = []
    monkeypatch.setattr(bench, "raise_", lambda: raised.append(True))
    bench.choose_pattern()
    assert raised
    assert bench.data is not None


def test_the_forms_start_at_the_defaults_asked_for(bench):
    index, pawley = bench.values("index"), bench.values("pawley")
    assert index["zero_error"] == 1.0
    assert bench.step_forms["index"].widgets["zero_error"] \
        .singleStep() == pytest.approx(0.1)
    assert index["longest_axis"] == 50.0
    assert (pawley["zero"], pawley["displacement"], pawley["refine_cell"],
            pawley["size"], pawley["strain"]) == \
        (False, True, True, True, True)
    assert "background_terms" in bench.values("peaks")
    assert "positions" not in bench.step_forms["peaks"].widgets


def test_the_run_button_says_what_the_step_does(bench):
    assert bench.run_button.text() == "Find peaks"
    bench.steps.setCurrentRow(1)
    assert bench.run_button.text() == "Index"
    bench.steps.setCurrentRow(2)
    assert bench.run_button.text() == "Fit Pawley"


def test_a_crystal_system_box_ticks_or_unticks_its_whole_row(bench):
    rows, boxes = bench.bravais.rows, bench.bravais.boxes
    assert rows["Cubic"].checkState() == Qt.Checked
    rows["Cubic"].click()
    assert not any(boxes[s].isChecked() for s in ("cP", "cI", "cF"))
    assert rows["Cubic"].checkState() == Qt.Unchecked
    boxes["cI"].setChecked(True)
    assert rows["Cubic"].checkState() == Qt.PartiallyChecked
    rows["Cubic"].click()               # partly ticked goes to all
    assert all(boxes[s].isChecked() for s in ("cP", "cI", "cF"))
    assert "cF" in bench.values("index")["bravais"] or \
        bench.values("index")["bravais"] == "all"


def test_refine_peaks_keeps_the_lines_in_use_and_draws_each_one(
        bench, qtbot, rutile_xy):
    _run_peaks(bench, qtbot, rutile_xy)
    if bench.plot.available:
        drawn = len(bench.plot._lines["components"].get_segments())
        assert drawn == bench.peaks.n_used
    row = next(r for r, p in enumerate(bench.peaks.peaks) if p.use)
    bench.table.item(row, 0).setCheckState(Qt.Unchecked)
    if bench.plot.available:
        assert len(bench.plot._lines["components"].get_segments()) == \
            drawn - 1
    kept = bench.peaks.n_used
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.refine_button.click()
    assert blocker.args[0].ok, blocker.args[0].message
    assert len(bench.peaks.peaks) == kept == bench.table.rowCount()
    assert bench.peaks.rwp is not None
    bench.components_box.setChecked(False)
    if bench.plot.available:
        assert not bench.plot._lines["components"].get_visible()


def test_a_peak_added_by_hand_joins_the_table_before_it_is_fitted(
        bench, qtbot, rutile_xy):
    _run_peaks(bench, qtbot, rutile_xy)
    before = len(bench.peaks.peaks)
    bench.add_edit.setText("45.1, 47.3")
    bench.add_button.click()
    assert len(bench.peaks.peaks) == before + 2
    assert bench.table.rowCount() == before + 2
    assert "manual" in {bench.table.item(r, 6).text()
                        for r in range(bench.table.rowCount())}
    assert bench.add_edit.text() == ""


def test_peaks_can_be_placed_by_hand_with_nothing_found_first(
        bench, qtbot, rutile_xy):
    bench.load_pattern(rutile_xy)
    bench.add_edit.setText("27.43, 36.08, 54.32")
    bench.add_button.click()
    assert len(bench.peaks.peaks) == 3
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.refine_button.click()
    assert blocker.args[0].ok, blocker.args[0].message
    positions = sorted(p.two_theta for p in bench.peaks.peaks)
    assert positions[0] == pytest.approx(27.434, abs=0.005)


def test_sorting_the_cells_reorders_the_table_and_the_choice_follows(
        bench, rutile_xy):
    from xtal.powder.index import IndexResult, IndexRow

    bench.load_pattern(rutile_xy)

    def row(rank, gof, c):
        return IndexRow(rank=rank, system="tetragonal", centring="P",
                        cell=(4.5948, 4.5948, c, 90, 90, 90),
                        cell_esd=(0,) * 6, volume=62.4, fom=("m20", gof),
                        n_indexed=15, n_lines=15, confidence="low",
                        caveats=(), lebail_rwp=None, found_by=(),
                        lattice_group="P 4/m m m")

    bench.cells = IndexResult(
        rows=[row(1, 5.0, 2.9572), row(2, 50.0, 5.9144)], best=None,
        stopped=False, systems_searched=("tetragonal",), complete={},
        wavelength=1.5406, two_theta_range=(20.0, 80.0))
    bench._fill_cells()
    assert bench.cell_table.item(0, 0).text() == "1"
    bench.sort_box.setCurrentIndex(
        bench.sort_box.findData("gof"))
    assert bench.cell_table.item(0, 0).text() == "2"
    assert bench.values("pawley")["cell"].split()[2] == "5.91440"
