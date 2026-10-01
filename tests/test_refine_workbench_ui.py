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

#: CI's test job does not install ``refine``: without it the Run
#: button names the extra and the plan notes, which are RietX's own
#: descriptions of its plans, are empty.
needs_rietx = pytest.mark.skipif(not powder.available(),
                                 reason="needs the refine extra")


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


@needs_rietx
def test_run_waits_for_a_pattern(bench):
    """Without RietX the tooltip names the extra instead, which is the
    test above."""
    assert not bench.run_button.isEnabled()
    assert "Load a pattern" in bench.run_button.toolTip()


def test_loading_an_xy_draws_the_observed_trace(bench, rutile_xy):
    assert bench.load_pattern(rutile_xy)
    assert "3000 points" in bench.pattern_label.text()
    if bench.plot.available:
        assert bench.plot.traces == ["observed"]
    assert bench.run_button.isEnabled()


@needs_rietx
def test_a_rasx_loads_without_being_exported_first(bench, tmp_path):
    from tests.conftest_patterns import TWO_THETA, write_rasx

    assert bench.load_pattern(write_rasx(tmp_path / "scan.rasx"))
    assert f"{len(TWO_THETA)} points" in bench.pattern_label.text()
    assert bench.status.text() == "loaded scan.rasx"


@needs_rietx
def test_loading_says_what_the_reader_chose_and_a_tube_it_disagrees_with(
        bench, tmp_path):
    """Scan 0 of 3, and Mo in a file the box says was Cu: both change
    what the fit means, so both are said, and neither is acted on."""
    from tests.conftest_patterns import write_rasx

    bench.data_form.set_values({"radiation": "cu"})
    assert bench.load_pattern(write_rasx(tmp_path / "three.rasx",
                                         scans=3, anode="Mo"))
    said = bench.status.text()
    assert "scan 0 of 3" in said
    assert "measured with Mo" in said
    assert bench.data_form.values()["radiation"] == "cu"


def test_a_file_that_is_not_a_pattern_is_refused_with_the_reason(
        bench, tmp_path):
    path = tmp_path / "notes.xy"
    path.write_text("hello\n", encoding="utf-8")
    assert not bench.load_pattern(path)
    assert "no two-column data" in bench.status.text()


def _flag(bench, name, on):
    """Tick or untick the Refine box of a row, or of a whole group, in
    the parameter table -- as a click does."""
    from xtalapp.refine.parameters import REFINE

    item = bench.parameter_table.item(name)
    assert item is not None, name
    item.setCheckState(REFINE, Qt.Checked if on else Qt.Unchecked)


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
    bench.step_forms["pawley"].set_values({"space_group": group})
    bench.cell_box.set_value(cell)
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
    monkeypatch.setattr(module.windows, "present", raised.append)
    bench.choose_pattern()
    assert raised == [bench]
    assert bench.data is not None


def test_the_forms_start_at_the_defaults_asked_for(bench):
    index, pawley = bench.values("index"), bench.values("pawley")
    assert index["zero_error"] == pytest.approx(0.3)
    assert bench.step_forms["index"].widgets["zero_error"] \
        .singleStep() == pytest.approx(0.1)
    assert index["longest_axis"] == 50.0
    assert pawley["hold"] == ""
    assert "background_terms" in bench.values("peaks")
    assert "positions" not in bench.step_forms["peaks"].widgets
    # the Refine column is what the boxes were: a box beside it would
    # be a second answer, never read
    for step in ("pawley", "rietveld"):
        for name in ("zero", "displacement", "size", "strain",
                     "positions", "biso", "background"):
            assert name not in bench.step_forms[step].widgets, name


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


# -- the cell, and what a fit refined ----------------------------------

def test_the_pawley_cell_offers_only_the_numbers_the_group_leaves_free(
        bench):
    """A cubic group takes one length and a monoclinic one three and
    an angle; the rest follow and have no switch of their own."""
    box = bench.cell_box
    bench.step_forms["pawley"].set_values({"space_group": "Fm-3m"})
    assert box.free() == ("a",)
    assert box.spins["a"].isEnabled()
    assert not box.spins["b"].isEnabled()
    assert box.boxes["b"].isHidden()
    box.spins["a"].setValue(5.64)
    assert bench.values("pawley")["cell"].split() == \
        ["5.64000", "5.64000", "5.64000", "90.000", "90.000", "90.000"]
    bench.step_forms["pawley"].set_values({"space_group": "P21/c"})
    assert box.free() == ("a", "b", "c", "beta")
    assert box.spins["beta"].isEnabled()
    assert not box.spins["alpha"].isEnabled()
    box.boxes["beta"].setChecked(False)
    assert bench.values("pawley")["hold"] == "beta"


def test_a_pawley_fit_writes_each_refined_number_beside_its_box(
        bench, qtbot, rutile_xy):
    """A cell number freed is its refined value -- beside the switch,
    not only in the summary; the rest are the parameter table's."""
    bench.load_pattern(rutile_xy)
    assert _run_pawley(bench, qtbot).ok
    assert bench.cell_box.notes["a"].text().startswith("4.59")
    assert bench.cell_box.notes["b"].text() == "= a"


# -- the plot ----------------------------------------------------------

def test_ticking_a_peak_in_or_out_keeps_the_zoom(bench, qtbot, rutile_xy):
    """A person zoomed into one peak to decide about it; unticking it
    must not throw them back out to the whole pattern."""
    if not bench.plot.available:
        pytest.skip("needs matplotlib")
    _run_peaks(bench, qtbot, rutile_xy)
    bench.plot.axes.set_xlim(27.0, 28.0)
    bench.plot.axes.set_ylim(50.0, 900.0)
    bench.table.item(0, 0).setCheckState(Qt.Unchecked)
    assert bench.plot.axes.get_xlim() == pytest.approx((27.0, 28.0))
    assert bench.plot.axes.get_ylim() == pytest.approx((50.0, 900.0))
    bench.table.item(0, 0).setCheckState(Qt.Checked)
    assert bench.plot.axes.get_ylim() == pytest.approx((50.0, 900.0))


def test_intensity_is_linear_square_root_or_logarithmic_and_the_difference_linear(  # noqa: E501
        bench, qtbot, rutile_xy):
    if not bench.plot.available:
        pytest.skip("needs matplotlib")
    _run_peaks(bench, qtbot, rutile_xy)
    plot = bench.plot
    plot.set_scale("log")
    assert plot.axes.get_yscale() == "log"
    assert plot.difference.get_yscale() == "linear"
    plot.set_scale("sqrt")
    assert plot.axes.get_yscale() == "function"
    assert plot.scale_box.currentData() == "sqrt"
    # the choice outlives a new fit being drawn
    bench._show_peaks()
    assert plot.axes.get_yscale() == "function"
    plot.scale_box.setCurrentIndex(plot.scale_box.findData("linear"))
    assert plot.axes.get_yscale() == "linear"


# -- Rietveld ----------------------------------------------------------

def _displaced_rutile_cif(tmp_path):
    """Rutile with its oxygen 0.06 A off where the pattern has it."""
    from xtal.core.lattice import Lattice
    from xtal.core.structure import Structure
    from xtal.io import write_cif

    structure = Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        ["Ti", "O"], [[0.0, 0.0, 0.0], [0.29, 0.29, 0.0]],
        space_group="P4_2/mnm")
    path = tmp_path / "displaced.cif"
    write_cif(structure, path)
    return str(path)


def _run_rietveld(bench, qtbot):
    bench.steps.setCurrentRow(3)
    assert bench.current_step == "rietveld"
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.run_step()
    return blocker.args[0]


def test_rietveld_waits_for_a_structure(bench, rutile_xy):
    bench.load_pattern(rutile_xy)
    bench.steps.setCurrentRow(3)
    assert not bench.run_button.isEnabled()
    assert "structure" in bench.run_button.toolTip()


def test_rietveld_frames_move_the_atoms_without_touching_the_undo_stack(
        window, qtbot, tmp_path, rutile_xy):
    window.settings.preview_interval = 0       # every accepted step
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    done = len(document.stack._done)
    seen = []
    document.previewChanged.connect(lambda: seen.append(
        (len(document.stack._done), document.modified,
         float(document.structure.sites[1].frac[0]))))
    assert _run_rietveld(bench, qtbot).ok
    assert seen
    assert all(n == done and not modified for n, modified, _x in seen)
    assert any(x != pytest.approx(0.29) for _n, _m, x in seen)


def test_a_finished_rietveld_is_one_undo_step_on_the_document_it_started_from(  # noqa: E501
        window, qtbot, tmp_path, rutile_xy, quartz_cif):
    """Opened over the displaced rutile, run with quartz in front:
    the rutile is refined and the quartz never touched."""
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    other = window.open_path(quartz_cif)
    assert window.current_document() is other
    quartz_before = other.structure.frac.copy()
    done = len(document.stack._done)
    result = _run_rietveld(bench, qtbot)
    assert result.ok, result.message
    assert len(document.stack._done) == done + 1
    assert document.undo_label == "Rietveld refinement"
    assert document.structure.sites[1].frac[0] == pytest.approx(0.3053,
                                                                abs=2e-3)
    assert len(document.structure.sites) == 2
    assert other.structure.frac == pytest.approx(quartz_before)
    assert bench.rietveld_label.text().startswith("Rwp")
    assert bench.parameters["scale"].esd
    # the committed structure's Biso is the fit's, esd and all
    oxygen = [row.name for row in bench.parameters.in_group("Atoms")
              if row.name.endswith("_biso")][1]
    assert bench.parameters[oxygen].esd
    assert oxygen in bench.parameter_table.moved
    assert bench.refined_table.rowCount() == len(bench.rietveld.refined)
    document.undo()
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)


def test_stopping_a_rietveld_run_puts_the_atoms_back(
        window, tmp_path, rutile_xy):
    """A frame moved the oxygen; a stopped run commits nothing and the
    atoms are where they were before it started."""
    import numpy as np

    from xtal.powder.rietveld import RietveldFrame

    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    structure = document.structure
    bench._running = "rietveld"
    bench._before = (structure.frac.copy(),
                     structure.lattice.matrix.copy())
    moved = structure.frac.copy()
    moved[1] = [0.31, 0.31, 0.0]
    x = bench.data.two_theta
    bench._on_frame(RietveldFrame("positions", x, bench.data.intensity,
                                  bench.data.intensity * 0.9, moved,
                                  structure.lattice.matrix.copy()))
    assert document.structure.sites[1].frac[0] == pytest.approx(0.31)
    done = len(document.stack._done)
    bench._running = ""
    bench._finish_rietveld(None)
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)
    assert len(document.stack._done) == done
    assert not document.modified
    assert np.isfinite(document.structure.frac).all()


def test_a_frame_before_the_scale_is_refined_leaves_the_axis_on_the_data(
        bench, rutile_xy):
    """RietX's first frame is at scale 1: 2.5 million counts against
    5000 on rutile.  The axis sized to it and kept that size for every
    later frame, which drew the measurement as a flat line."""
    bench.load_pattern(rutile_xy)
    x, y = bench.data.two_theta, bench.data.intensity
    bench.plot.show_fit(x, y, y * 500.0)
    assert bench.plot.axes.get_ylim()[1] < 2.0 * y.max()
    bench.plot.set_scale("sqrt")
    assert bench.plot.axes.get_ylim()[1] < 2.0 * y.max()
    bench.plot.set_scale("log")
    assert bench.plot.axes.get_ylim()[1] < 2.0 * y.max()


def test_each_rietveld_fit_joins_the_history_and_any_row_can_be_restored(
        window, qtbot, tmp_path, rutile_xy):
    """SHELXLE's walk back along the .res files: the start and every
    fit are rows, and restoring one is one undo step that puts back
    its atoms and its boxes -- the later rows stay."""
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    atoms = [row.name for row in bench.parameters.in_group("Atoms")
             if not row.name.endswith("_occ")]
    for name in atoms:
        _flag(bench, name, False)
    assert _run_rietveld(bench, qtbot).ok
    for name in atoms:
        _flag(bench, name, True)
    assert _run_rietveld(bench, qtbot).ok
    assert [e.fit is None for e in bench.history] == [True, False, False]
    assert bench.history_table.rowCount() == 3
    assert bench.history_table.item(0, 7).text() == "start"
    assert float(bench.history_table.item(2, 2).text()) \
        < float(bench.history_table.item(1, 2).text())
    refined = float(document.structure.sites[1].frac[0])
    assert refined == pytest.approx(0.3053, abs=2e-3)

    done = len(document.stack._done)
    assert bench.restore_history(1)
    assert len(document.stack._done) == done + 1
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)
    assert not any(bench.parameters[name].refine for name in atoms)
    assert bench.rietveld is bench.history[1].fit
    assert bench.history_table.rowCount() == 3
    assert bench.history_table.item(1, 0).font().bold()

    assert bench.restore_history(0)
    assert bench.rietveld is None
    document.undo()
    document.undo()
    assert document.structure.sites[1].frac[0] == pytest.approx(refined)


# -- the parameter table -----------------------------------------------

def test_switching_steps_shows_the_same_parameters(bench, rutile_xy):
    """One set for every fitting step, shown by one table moved into
    the step in front: a copy per step is how Rietveld used to start
    from the preset after a Pawley fit had found the peak shape."""
    bench.load_pattern(rutile_xy)
    table = bench.parameter_table
    shown = {}
    for row in (2, 3, 4, 5, 6):
        bench.steps.setCurrentRow(row)
        assert bench.forms.currentWidget().isAncestorOf(table), row
        shown[row] = table.item("W").text(1)
    assert len(set(shown.values())) == 1
    bench.steps.setCurrentRow(2)
    table.set_value("W", "0.0123")
    bench.steps.setCurrentRow(3)
    assert table.item("W").text(1) == "0.0123"
    for step in ("pawley", "rietveld", "energy", "pareto", "auto"):
        assert bench.values(step)["parameters"]["W"].value == 0.0123


def test_a_finished_fit_writes_its_values_and_esds_into_the_table(
        bench, qtbot, rutile_xy):
    """The table is where the numbers a fit reached are read, and
    where the next step starts from: a Pawley peak shape shown on
    Rietveld's page with its esd."""
    bench.load_pattern(rutile_xy)
    before = bench.parameters["W"].value
    assert _run_pawley(bench, qtbot).ok
    row = bench.parameters["W"]
    assert row.value != before and row.esd
    assert bench.pawley.parameters["W"].value == row.value
    assert "W" in bench.parameter_table.moved
    bench.steps.setCurrentRow(3)
    item = bench.parameter_table.item("W")
    assert item.text(2) and float(item.text(1)) == pytest.approx(
        row.value, rel=1e-3)
    assert item.font(1).bold()
    # a Pawley fit has no scale of its own to hand on
    assert not bench.parameters["scale"].esd


def test_reset_parameters_puts_the_profile_back_and_keeps_the_atoms(
        window, qtbot, tmp_path, rutile_xy):
    """For when the background or the size broadening has run away:
    the instrument and profile go back, the structure's numbers and
    what is flagged stay."""
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    start = bench.parameters.copy()
    assert _run_rietveld(bench, qtbot).ok
    assert bench.parameters["W"].value != start["W"].value
    biso = {row.name: row.value for row in bench.parameters.in_group(
        "Atoms")}
    _flag(bench, "zero_error", True)
    done = len(document.stack._done)
    bench.parameter_table.reset_button.click()
    assert bench.parameters["W"].value == start["W"].value
    assert bench.parameters["W"].esd is None
    assert bench.parameters["zero_error"].refine
    assert {row.name: row.value for row in bench.parameters.in_group(
        "Atoms")} == biso
    assert len(document.stack._done) == done


def test_paste_refuses_a_line_it_cannot_read_and_changes_nothing(
        bench, rutile_xy):
    """Half a paste is worse than none: the rows before the typo would
    change and nothing would say which."""
    bench.load_pattern(rutile_xy)
    table = bench.parameter_table
    before = bench.parameters.to_text()
    assert table.paste("W 0.02 Refine\nzero_eror 0.1 Refine\n") == 0
    assert "zero_eror" in bench.status.text()
    assert bench.parameters.to_text() == before
    assert table.paste("W 0.02 ± 0.001 NoRefine\n") == 1
    assert bench.parameters["W"].value == 0.02
    assert not bench.parameters["W"].refine
    assert table.item("W").text(2) == "0.0010"


def test_copy_puts_the_text_form_on_the_clipboard(bench, rutile_xy):
    from PySide6.QtWidgets import QApplication

    bench.load_pattern(rutile_xy)
    bench.parameter_table.copy_button.click()
    text = QApplication.clipboard().text()
    assert text == bench.parameters.to_text()
    assert bench.parameter_table.paste(text) == len([
        line for line in text.splitlines()
        if line and not line.startswith("#")])


def test_editing_a_biso_in_the_table_is_one_undo_step(
        window, rutile_cif, rutile_xy):
    """An atom's Biso is the site's: typing one here is an edit of the
    structure, undone by Ctrl+Z like any other, and two typed one after
    the other are two steps, not one merged edit."""
    document = window.open_path(rutile_cif)
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    name = next(row.name for row in bench.parameters.in_group("Atoms")
                if row.name.endswith("_biso"))
    done = len(document.stack._done)
    # as the editor commits it: from inside the tree's own signal,
    # which is where clearing the tree to redraw it crashed
    bench.parameter_table.item(name).setText(1, "1.25")
    assert len(document.stack._done) == done + 1
    assert bench.parameters[name].value == pytest.approx(1.25)
    assert document.structure.sites[0].u_iso == pytest.approx(
        1.25 / (8 * 3.141592653589793 ** 2))
    assert bench.parameter_table.set_value(name, "1.5")
    assert len(document.stack._done) == done + 2
    document.undo()
    assert bench.parameters[name].value == pytest.approx(1.25)
    assert not bench.parameter_table.set_value(name, "lots")
    assert len(document.stack._done) == done + 1


def test_restoring_a_history_row_restores_its_parameters(
        window, qtbot, tmp_path, rutile_xy):
    """A history row is a configuration: its atoms and the numbers the
    fit had.  Walking back to the start with the fit's peak shape
    left in the table would start the next run from neither."""
    window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    start = bench.parameters["W"].value
    assert _run_rietveld(bench, qtbot).ok
    fitted = bench.parameters["W"].value
    assert fitted != start
    assert bench.restore_history(0)
    assert bench.parameters["W"].value == start
    assert float(bench.parameter_table.item("W").text(1)) \
        == pytest.approx(start, rel=1e-4)
    assert bench.restore_history(1)
    assert bench.parameters["W"].value == fitted


def test_the_run_log_names_the_set_it_was_handed(
        bench, qtbot, rutile_xy):
    bench.load_pattern(rutile_xy)
    assert _run_pawley(bench, qtbot).ok
    log = next(bench._entry_for().path.rglob("*.log")).read_text()
    assert "parameters, " in log and "refined" in log
    assert "ParameterSet object" not in log


def test_loading_another_pattern_starts_a_new_history(bench, rutile_xy):
    bench.history.append(object())
    bench.load_pattern(rutile_xy)
    assert bench.history == []
    assert bench.history_table.rowCount() == 0
    assert not bench.restore_button.isEnabled()


@needs_rietx
def test_the_plan_note_says_what_the_chosen_plan_frees(
        window, rutile_cif):
    """Two of RietX's four plans move no atom, which a name like
    "lab Bragg-Brentano" does not say."""
    window.open_path(rutile_cif)
    bench = window.open_refine_workbench()
    form = bench.step_forms["rietveld"]
    assert "atom positions" in bench.plan_note.text()
    assert "The atoms move" in bench.plan_note.text()
    for row in bench.parameters.in_group("Atoms"):
        if row.name.endswith("_xyz"):
            _flag(bench, row.name, False)
    assert "atom positions" not in bench.plan_note.text()
    for plan, moves in (("mccusker_structural", True),
                        ("mccusker_default", False),
                        ("lab_bragg_brentano", False),
                        ("lab_sample_refine", False)):
        form.set_values({"plan": plan})
        text = bench.plan_note.text()
        assert text.startswith(("Standard", "Lab"))
        assert ("The atoms move" in text) is moves, plan


def test_run_and_stop_stay_in_sight_on_every_step(bench):
    """The form stack was as tall as Rietveld's page, which put Run
    below the bottom of the window on Peaks and Index; and Run lives
    outside the scrolling form, however long the form is."""
    from PySide6.QtWidgets import QApplication, QScrollArea

    bench.steps.setCurrentRow(0)
    QApplication.processEvents()
    tallest = max(bench.forms.widget(k).sizeHint().height()
                  for k in range(bench.forms.count()))
    assert bench.forms.sizeHint().height() \
        == bench.forms.widget(0).sizeHint().height() < tallest
    widget = bench.run_button
    while widget is not None:
        assert not isinstance(widget, QScrollArea)
        widget = widget.parentWidget()


@needs_rietx
def test_a_rietx_plan_greys_out_the_boxes_it_decides_for_itself(bench):
    """RietX's plans never read the flags, so a box left live beside
    one looked like a say over the fit that it did not have.  The
    range, the background's order and the values still count, and
    stay live -- a plan starts from the values shown."""
    from xtalapp.refine.parameters import REFINE

    bench.steps.setCurrentRow(3)
    form = bench.step_forms["rietveld"]
    form.set_values({"plan": "mccusker_default"})
    assert not form.widgets["preferred_axis"].isEnabled()
    zero = bench.parameter_table.item("zero_error")
    assert not zero.flags() & Qt.ItemIsUserCheckable
    assert zero.flags() & Qt.ItemIsEditable
    assert "plan" in zero.toolTip(REFINE)
    assert not bench.rietveld_cell.isEnabled()
    for name in ("start", "finish", "background_terms", "plan"):
        assert form.widgets[name].isEnabled(), name
    # a plan is the Rietveld step's: Pawley reads the flags
    bench.steps.setCurrentRow(2)
    assert bench.parameter_table.item("zero_error").flags() \
        & Qt.ItemIsUserCheckable
    bench.steps.setCurrentRow(3)
    form.set_values({"plan": ""})
    assert bench.parameter_table.item("zero_error").flags() \
        & Qt.ItemIsUserCheckable
    assert bench.rietveld_cell.isEnabled()


@needs_rietx
def test_a_plan_note_is_drawn_whole_however_narrow_the_column(
        bench, qtbot):
    """The page was measured with the boxes' one-line note and never
    again, so in a window too short to show the whole form the page
    was handed that height and a plan's four-sentence note was
    squeezed and cut off, and the rows below it with it."""
    from PySide6.QtWidgets import QApplication

    bench.resize(1000, 500)
    bench.show()
    bench.steps.setCurrentRow(3)
    QApplication.processEvents()
    bench.step_forms["rietveld"].set_values({"plan": "mccusker_default"})
    QApplication.processEvents()
    note = bench.plan_note
    assert note.minimumHeight() >= note.heightForWidth(note.width()) > 0
    page = bench.forms.currentWidget()
    assert bench.forms.sizeHint().height() \
        >= page.minimumSizeHint().height()


# -- automatic -------------------------------------------------------------

def _run_auto(bench, qtbot, **form):
    bench.steps.setCurrentRow(6)
    assert bench.current_step == "auto"
    bench.bravais.set_value("tP")
    bench.step_forms["index"].set_values(
        {"longest_axis": 6.0, "budget": 10.0, "zero_error": 0.0})
    bench.step_forms["auto"].set_values(
        {"cells": 1, "classes": 2, **form})
    with qtbot.waitSignal(bench.stepFinished, timeout=120000) as blocker:
        bench.run_step()
    return blocker.args[0]


def test_the_automatic_run_asks_every_steps_own_form(bench, rutile_xy):
    """One set of questions, asked once: the automatic run reads the
    lattices off Index and the broadening off Pawley, never a second
    copy of them that could disagree."""
    bench.load_pattern(rutile_xy)
    bench.bravais.set_value("tP")
    bench.step_forms["pawley"].set_values({"background_terms": 5})
    bench.step_forms["rietveld"].set_values({"plan": "mccusker_default"})
    _flag(bench, "strain_l", False)
    values = bench.values("auto")
    assert values["bravais"] == "tP"
    assert not values["parameters"]["strain_l"].refine
    assert "pawley_parameters" not in values
    assert "rietveld_parameters" not in values
    assert values["pawley_background_terms"] == 5
    assert values["rietveld_plan"] == "mccusker_default"
    assert "pawley_cell" not in values and "cell" not in values
    assert values["cells"] == 5 and values["continue_rietveld"] is False
    bench.steps.setCurrentRow(6)
    assert bench.run_button.text() == "Run all"


@pytest.mark.slow
def test_an_automatic_run_fills_every_steps_answer_and_ranks_the_fits(
        bench, qtbot, rutile_xy):
    """The peaks land on Peaks and the cells on Index, as if each step
    had been run; a row of the table is its own fit, and becomes the
    Pawley step's answer so Apply cell applies the one looked at."""
    bench.load_pattern(rutile_xy)
    result = _run_auto(bench, qtbot)
    assert result.ok, result.message
    assert bench.peaks is not None and bench.table.rowCount() > 5
    assert bench.cells is not None and bench.cell_table.rowCount()
    rows = bench.auto.rows
    assert bench.auto_table.rowCount() == len(rows) >= 1
    assert bench.pawley is rows[0].fit
    assert bench.auto_label.text().startswith("Best: row 1")
    if len(rows) > 1:
        bench.auto_table.selectRow(1)
        assert bench.pawley is rows[1].fit


@pytest.mark.slow
def test_continuing_to_rietveld_is_one_undo_step_on_the_structure(
        window, qtbot, tmp_path, rutile_xy):
    """Asked to go on, the run refines the structure the window was
    opened over in the Pawley cell, and the whole of it -- cell and
    atoms -- is one Ctrl+Z, and a row of the History."""
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    done = len(document.stack._done)
    result = _run_auto(bench, qtbot, continue_rietveld=True)
    assert result.ok, result.message
    assert bench.auto.rietveld is not None
    assert len(document.stack._done) == done + 1
    assert document.structure.sites[1].frac[0] == pytest.approx(0.3053,
                                                                abs=2e-3)
    assert [e.fit is None for e in bench.history] == [True, False]
    document.undo()
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)


# -- Rietveld with energy ------------------------------------------------

def _run_energy(bench, qtbot, weight=0.2):
    bench.steps.setCurrentRow(4)
    assert bench.current_step == "energy"
    bench.step_forms["energy"].set_values({"weight": weight})
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.run_step()
    return blocker.args[0]


def test_the_energy_engine_is_chosen_here_and_in_the_force_field_panel_at_once(  # noqa: E501
        bench, window):
    """Julius found it confusing to set the engine in another window.
    The box here shares the Force Field panel's model and choice, so
    choosing in either chooses in both and the two can never differ."""
    bench.steps.setCurrentRow(4)
    assert bench.run_button.text() == "Refine"
    assert "engine" not in bench.step_forms["energy"].widgets
    here, there = bench.engine_boxes["energy"], window.ff_dock.engine
    assert here.model() is there.model()
    assert here.currentData() == there.currentData() == "uff"
    values = bench.values("energy")
    assert values["engine"] == "uff"
    assert isinstance(values["engine_options"], dict)
    other = next(k for k in range(there.count())
                 if there.itemData(k) != "uff")
    there.setCurrentIndex(other)
    assert here.currentIndex() == other
    assert bench.engine_boxes["pareto"].currentIndex() == other
    assert bench.values("pareto")["engine"] == there.itemData(other)
    first = here.findData("uff")
    here.activated.emit(first)          # what a person choosing does
    assert there.currentData() == "uff"
    # the fit of everything but the atoms is the Rietveld step's boxes
    bench.step_forms["rietveld"].set_values({"background_terms": 6})
    assert bench.values("energy")["rietveld_background_terms"] == 6


def test_rietveld_with_energy_waits_for_a_structure(bench, rutile_xy):
    bench.load_pattern(rutile_xy)
    bench.steps.setCurrentRow(4)
    assert not bench.run_button.isEnabled()


def test_rietveld_with_energy_is_one_undo_step_and_joins_the_history(
        window, qtbot, tmp_path, rutile_xy):
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    done = len(document.stack._done)
    result = _run_energy(bench, qtbot, weight=0.2)
    assert result.ok, result.message
    assert len(document.stack._done) == done + 1
    assert document.undo_label == "Rietveld with energy"
    oxygen = document.structure.sites[1].frac
    assert oxygen[0] != pytest.approx(0.29)
    assert oxygen[0] == pytest.approx(oxygen[1])
    assert bench.energy is not None and bench.rietveld is None
    assert bench.energy_label.text().startswith("Rwp")
    assert bench.ends_table.rowCount() == 3
    assert bench.ends_table.item(2, 1).text() == "0.2"
    assert bench.history_table.rowCount() == 2
    assert bench.history_table.item(1, 5).text() == "with energy, w 0.2"
    document.undo()
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)


# -- Pareto ----------------------------------------------------------------

def _run_pareto(bench, qtbot, weights=""):
    bench.steps.setCurrentRow(5)
    assert bench.current_step == "pareto"
    if weights:
        bench.step_forms["pareto"].set_values({"weights": weights})
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.run_step()
    return blocker.args[0]


def test_a_pareto_sweep_leaves_the_structure_as_it_was(
        window, qtbot, tmp_path, rutile_xy):
    """A sweep returns no structure -- the points are files -- so the
    atoms it moved while running go back, and nothing is an undo
    step."""
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    done = len(document.stack._done)
    result = _run_pareto(bench, qtbot)
    assert result.ok, result.message
    assert len(document.stack._done) == done
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)
    assert bench.pareto_table.rowCount() == 12
    assert bench.history == []
    # drawn in this window too, against the weight and as the front
    drawn = bench.pareto_plots.series
    assert len(drawn["weight"]) == len(drawn["rwp"]) == 12
    assert drawn["weight"][0] == 0.0 and drawn["weight"][-1] == 1.0
    bench.pareto_plots.pointPicked.emit(3)
    assert bench.pareto_table.selectionModel().selectedRows()[0].row() \
        == 3


def test_the_suggested_weight_goes_to_the_with_energy_step(
        window, qtbot, tmp_path, rutile_xy):
    """Use this weight is the step from the sweep to refining at its
    answer: the weight is filled in and With energy is shown."""
    window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    _run_pareto(bench, qtbot)
    knee = bench.pareto.knee
    assert knee is not None
    assert bench.pareto_table.item(knee, 3).text() == "knee"
    # the knee's own fit is the one drawn and chosen
    assert bench.pareto_table.selectionModel().selectedRows()[0].row() \
        == knee
    assert bench.use_knee_button.isEnabled()
    bench.use_knee()
    assert bench.current_step == "energy"
    assert bench.step_forms["energy"].values()["weight"] == \
        pytest.approx(bench.pareto.points[knee].weight)


def test_a_pareto_point_opens_as_a_tab_of_its_own(
        window, qtbot, tmp_path, rutile_xy):
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    _run_pareto(bench, qtbot, weights="0, 1")
    opened = bench.open_pareto_point(0)
    assert opened is not None and opened is not document
    assert opened.structure.sites[1].frac[0] != pytest.approx(0.29)
    assert len(opened.structure.sites) == 2
    # the front in the Results panel, its points the same files
    shown = []
    window.results_dock.show_report = \
        lambda report, title="": shown.append(report)
    bench.show_front()
    assert shown[0].curves[0].path_at(0, 0).endswith(".cif")


def test_the_pawley_step_says_what_a_cell_is_for_and_what_range_to_fit(
        bench):
    """Two things Julius asked to be told in the window: a wider range
    is not a better cell, and how a cell becomes a structure here."""
    from xtalapp.refine import workbench

    texts = [label.text() for label in
             bench.forms.widget(2).findChildren(workbench.QLabel)]
    assert workbench.PAWLEY_RANGE_NOTE in texts
    assert workbench.CELL_TO_STRUCTURE_NOTE in texts
    assert "MOF builder" in workbench.CELL_TO_STRUCTURE_NOTE
    assert "slower" in bench.step_forms["pawley"].widgets["finish"] \
        .toolTip()


# -- Julius's fourth list ----------------------------------------------------

def test_the_pattern_is_drawn_logarithmic_to_start_with(bench):
    if not bench.plot.available:
        pytest.skip("needs matplotlib")
    assert bench.plot.scale == "log"


def test_the_plot_and_the_table_under_it_start_half_and_half(bench):
    from PySide6.QtWidgets import QApplication

    bench.show()
    QApplication.processEvents()
    top, bottom = bench.middle.sizes()
    assert abs(top - bottom) <= 2


def test_every_section_of_the_right_column_folds(bench):
    """Each step's column is folds of a few rows each -- range, what is
    refined, the result -- and a fold closed takes its rows with it."""
    from xtalapp.docks.columns import Collapsible

    for k in range(bench.forms.count()):
        folds = bench.forms.widget(k).findChildren(Collapsible)
        assert len(folds) >= 2, k
    peaks = bench.forms.widget(0).findChildren(Collapsible)[0]
    assert peaks.is_open()
    peaks.set_open(False)
    assert not peaks.body.isVisibleTo(bench)
    # the explanations are there, folded away until asked for
    about = [f for f in bench.forms.widget(2).findChildren(Collapsible)
             if f.title() == "About"]
    assert about and not about[0].is_open()


def test_the_index_time_budget_is_off_until_its_box_is_ticked(bench):
    spin = bench.step_forms["index"].widgets["budget"]
    assert not bench.budget_box.isChecked()
    assert not spin.isEnabled()
    assert bench.values("index")["budget"] == 0.0
    assert spin.text() == "no limit"
    bench.budget_box.setChecked(True)
    assert spin.isEnabled()
    assert bench.values("index")["budget"] == 60.0
    spin.setValue(25.0)
    bench.budget_box.setChecked(False)
    assert bench.values("index")["budget"] == 0.0
    bench.budget_box.setChecked(True)
    assert bench.values("index")["budget"] == 25.0


def test_a_rule_stands_between_the_row_boxes_and_the_lattices(bench):
    from xtalapp.refine.bravais import ROWS

    grid = bench.bravais.layout()
    row, column, rows, _columns = grid.getItemPosition(
        grid.indexOf(bench.bravais.rule))
    assert (row, column, rows) == (0, 2, len(ROWS))
    whole = grid.getItemPosition(grid.indexOf(bench.bravais.rows["Cubic"]))
    first = grid.getItemPosition(grid.indexOf(bench.bravais.boxes["cP"]))
    assert whole[1] < column < first[1]


def test_the_cell_tables_space_groups_are_not_cut_off(bench):
    """Stretched to what was left of the width, the last column cut a
    row's list of classes short."""
    header = bench.cell_table.horizontalHeader()
    assert not header.stretchLastSection()
    assert bench.cell_table.textElideMode() == Qt.ElideNone


def test_the_peaks_range_is_carried_on_until_a_step_is_given_its_own(
        bench, rutile_xy):
    bench.load_pattern(rutile_xy)
    bench.step_forms["peaks"].set_values({"start": 25.0, "finish": 60.0})
    for step in ("pawley", "rietveld", "energy", "pareto"):
        values = bench.step_forms[step].values()
        assert (values["start"], values["finish"]) == (25.0, 60.0), step
    bench.step_forms["pawley"].set_values({"start": 30.0})
    bench.step_forms["peaks"].set_values({"start": 27.0})
    assert bench.step_forms["pawley"].values()["start"] == 30.0
    assert bench.step_forms["rietveld"].values()["start"] == 27.0


def test_with_energy_and_pareto_fit_over_their_own_range(bench):
    bench.step_forms["rietveld"].set_values({"start": 22.0})
    bench.step_forms["pareto"].set_values({"start": 30.0, "finish": 50.0})
    values = bench.values("pareto")
    assert (values["rietveld_start"], values["rietveld_finish"]) == \
        (30.0, 50.0)
    assert "start" not in values
    assert bench.values("energy")["rietveld_start"] != 30.0


@needs_rietx
def test_with_energy_and_pareto_say_what_they_refine(bench):
    """The first stage is what the table flags beyond the atoms;
    without this nobody pressing Refine here could tell what it fits."""
    note = bench.refines_notes["pareto"]
    assert "background" in note.text()
    assert "atom positions" in note.text()
    assert "cell's free numbers" not in note.text()
    _flag(bench, "Background", False)
    assert "background" not in note.text()
    bench.step_forms["pareto"].set_values({"energy_cell": True})
    assert "cell's free numbers" in note.text()
    assert "cell's free numbers" not in bench.refines_notes["energy"].text()


def test_the_kbeta_flag_starts_off_and_le_bail_is_a_pawley_method(bench):
    assert bench.values("peaks")["flag_ghosts"] is False
    bench.steps.setCurrentRow(2)
    assert bench.run_button.text() == "Fit Pawley"
    bench.step_forms["pawley"].set_values({"method": "lebail"})
    assert bench.run_button.text() == "Fit Le Bail"
    assert bench.values("pawley")["method"] == "lebail"


def test_a_peak_can_be_moved_and_resized_by_hand_before_refining(
        bench, rutile_xy):
    """A better start for Refine peaks than the one found: the numbers
    typed into the table are the line's."""
    from PySide6.QtWidgets import QApplication

    bench.load_pattern(rutile_xy)
    bench.add_edit.setText("27.4, 36.1")
    bench.add_peaks()
    first = bench.table.item(0, 1)
    assert first.flags() & Qt.ItemIsEditable
    assert not bench.table.item(0, 3).flags() & Qt.ItemIsEditable
    first.setText("27.45")
    QApplication.processEvents()
    peak = bench.peaks.peaks[0]
    assert peak.two_theta == pytest.approx(27.45)
    assert "edited" in peak.flags
    bench.table.item(1, 4).setText("1234.5")
    QApplication.processEvents()
    assert bench.peaks.peaks[1].area == pytest.approx(1234.5)
    bench.table.item(1, 5).setText("wide")
    QApplication.processEvents()
    assert "not a number" in bench.status.text()
    assert bench.table.item(1, 5).text() != "wide"


def test_a_le_bail_fit_is_the_pawley_steps_answer(bench, qtbot, rutile_xy):
    bench.load_pattern(rutile_xy)
    bench.steps.setCurrentRow(2)
    bench.step_forms["pawley"].set_values(
        {"method": "lebail", "space_group": "P4_2/mnm"})
    bench.cell_box.set_value("4.59 4.59 2.96")
    with qtbot.waitSignal(bench.stepFinished, timeout=60000) as blocker:
        bench.run_step()
    result = blocker.args[0]
    assert result.ok, result.message
    assert result.message.startswith("Le Bail")
    assert bench.pawley.method == "lebail"
    assert bench.pawley_label.text().startswith("Le Bail")


# ------------------------------------------ the energy engine's options

@pytest.fixture
def options(window):
    """The workbench's Options... opened over UFF, the dialog it
    raised, and the panel it borrowed from."""
    dock = window.ff_dock
    dock.engine.setCurrentIndex(dock.engine.findData("uff"))
    bench = window.open_refine_workbench()
    bench.engine_option_buttons["energy"].click()
    return bench, bench.engine_options, dock


def test_options_opens_the_engines_options_over_the_workbench(options):
    """It raised the Force Field panel, which is in the main window
    behind the workbench, so the button looked as though it did
    nothing."""
    bench, dialog, dock = options
    assert dialog.isVisible()
    assert dialog.parent() is bench
    assert dialog.isAncestorOf(dock.uff_box)
    assert not dock.lent_note.isHidden()


def test_closing_the_options_puts_the_panels_controls_back(options):
    """Lent controls left in a closed window are a Force Field panel
    with no way to choose UFF4MOF."""
    _bench, dialog, dock = options
    dialog.close()
    assert dock.isAncestorOf(dock.uff_box)
    assert not dock.uff_box.isHidden()
    assert dock.lent_note.isHidden()


def test_closing_the_workbench_gives_the_controls_back(options):
    bench, _dialog, dock = options
    bench.close()
    assert dock.isAncestorOf(dock.uff_box)


def test_an_option_changed_in_the_dialog_is_what_the_run_is_handed(
        options):
    """One set of controls, so With energy and the panel can never be
    handed different options for the same engine."""
    bench, _dialog, dock = options
    box = dock.parameter_set
    box.setCurrentIndex(1 - box.currentIndex())
    handed = bench._energy_values({}, "energy")["engine_options"]
    assert handed["parameter_set"] == box.currentData()


def test_choosing_another_engine_swaps_the_controls_it_shows(options):
    """Otherwise the window names one engine and shows another's
    options, and UFF's never go home."""
    _bench, dialog, dock = options
    name = next(iter(dock.engine_forms))
    dock.engine.setCurrentIndex(dock.engine.findData(name))
    assert dialog.isAncestorOf(dock.engine_forms[name])
    assert not dock.engine_forms[name].isHidden()
    assert dock.isAncestorOf(dock.uff_box)



def test_zero_cycles_is_no_undo_step(window, qtbot, tmp_path, rutile_xy):
    """Max iterations 0 evaluates: the R values are shown and said to
    be an evaluation, and the atoms, the undo stack, the history and
    the table's numbers are all as they were."""
    document = window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    bench.step_forms["rietveld"].set_values({"max_iterations": 0})
    before = bench.parameters.to_text()
    done = len(document.stack._done)
    result = _run_rietveld(bench, qtbot)
    assert result.ok, result.message
    assert "0 cycles" in result.message
    assert len(document.stack._done) == done
    assert not document.modified
    assert document.structure.sites[1].frac[0] == pytest.approx(0.29)
    assert bench.rietveld.evaluated
    assert "0 cycles: evaluated at the values shown" in \
        bench.rietveld_label.text()
    assert len(bench.history) <= 1
    assert bench.parameters.to_text() == before


def test_the_pawley_step_hides_the_atoms_and_the_scale(
        window, tmp_path, rutile_xy):
    """A Pawley fit has neither, and their rows shown ticked beside it
    read as though it refined them.  They are hidden, not dropped:
    Rietveld shows them again, flags and all."""
    from xtal.powder import parameters as ps

    window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    table = bench.parameter_table
    bench.steps.setCurrentRow(2)
    assert table.item(ps.ATOMS).isHidden()
    assert table.item(ps.SCALE).isHidden()
    assert not table.item(ps.PROFILE).isHidden()
    assert table.unused_note.isVisibleTo(bench)
    assert "no atoms" in table.unused_note.text()
    bench.steps.setCurrentRow(3)
    assert not table.item(ps.ATOMS).isHidden()
    assert not table.item(ps.SCALE).isHidden()
    assert not table.unused_note.isVisibleTo(bench)
    assert bench.parameters["scale"].refine


def test_hovering_a_rietveld_tick_names_its_reflection(
        window, qtbot, tmp_path, rutile_xy):
    """Rutile's first line is (1 1 0), near 27.4°: the fit's own
    reflection list names it, at the primary line only."""
    from matplotlib.backend_bases import MouseEvent

    window.open_path(_displaced_rutile_cif(tmp_path))
    bench = window.open_refine_workbench()
    bench.load_pattern(rutile_xy)
    assert _run_rietveld(bench, qtbot).ok
    fit = bench.rietveld
    assert len(fit.reflections) == len(fit.ticks)
    first = min(fit.reflections, key=lambda r: r.two_theta)
    assert sorted(abs(v) for v in first.hkl) == [0, 1, 1]
    plot = bench.plot
    plot.canvas.draw()
    x, y = plot.strip.transData.transform((first.two_theta, 0.5))
    plot.canvas.callbacks.process("motion_notify_event", MouseEvent(
        "motion_notify_event", plot.canvas, x, y))
    assert plot.hovered.startswith("(")
    assert f"{first.two_theta:.2f}°" in plot.hovered
    assert "Å" in plot.hovered
