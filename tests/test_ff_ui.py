"""The force field through the application.

Two things run through all of it.  A calculation is not a change: a
single point, a typing, an unfinished run -- none of them may mark the
document modified or put anything on the undo stack.  And a finished
optimisation is exactly one change: one stack entry, and Ctrl+Z gives
back the structure the run started from.

The optimisation itself runs on a worker thread, so those tests wait on
signals rather than assuming the answer has arrived.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from dataclasses import replace  # noqa: E402

from tests.conftest_ff import water  # noqa: E402
from tests.conftest_program import write_program  # noqa: E402
from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.ff import optimize  # noqa: E402
from xtal.ff.xtb import calculator as xtb  # noqa: E402
from xtalapp.docks.ff_panel import COLUMNS  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.workers import OptimizationWorker  # noqa: E402

TIMEOUT = 20000
TYPE = COLUMNS.index("Type")
MEANS = COLUMNS.index("What it means")
SURE = COLUMNS.index("Sure?")
WHY = COLUMNS.index("Why")


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"FF{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def opened(window, rutile_cif):
    document = window.open_path(rutile_cif)
    return window, document


@pytest.fixture
def slow(window, rutile):
    """A document big enough that a run lasts long enough to watch.

    Water relaxes in well under a millisecond, so a test that tried to
    catch it mid-flight would be racing the optimiser and losing.  A
    72-site supercell at a tolerance nothing will reach takes seconds,
    and the run is paused deliberately rather than by hoping.
    """
    from xtal.core import supercell, symmetry
    big = symmetry.reduce_to_p1(supercell.supercell(rutile, 2, 2, 3))
    document = Document(big)
    window.add_document(document)
    dock = window.ff_dock
    dock.max_steps.setValue(9000)
    dock.tolerance.setValue(0.0001)
    dock.method.setCurrentIndex(dock.method.findData("fire"))
    return window, document, dock


def wait_for_the_run(qtbot, dock):
    qtbot.waitUntil(lambda: not dock.is_running, timeout=TIMEOUT)
    # The finished handler runs on the GUI thread after the signal.
    qtbot.waitUntil(lambda: dock.worker is None, timeout=TIMEOUT)


# --------------------------------------------------------- the panel

def test_the_panel_lists_a_row_per_site(opened):
    _window, document = opened
    dock = _window.ff_dock
    assert dock.table.rowCount() == document.structure.n_sites
    assert dock.table.item(0, TYPE).text() == "Ti6+4"
    assert "neighbours" in dock.table.item(0, WHY).text()


def test_filling_the_type_table_does_not_emit_a_signal_per_cell(
        window, rutile):
    """One layout change for the fill, not one per cell.

    Every setItem emits dataChanged, and the view answers each one by
    asking the header to size its columns to their contents -- which
    shapes the text of every sampled row again.  At two thousand cells
    that was twenty seconds of font shaping, and because Qt replays
    those signals from the event loop it was spent *after* an
    optimisation had finished: the run was instant and then the window
    stopped answering.  Counted rather than timed, because the cost is
    paid in a deferred repaint that a headless test never performs.
    """
    from xtal.core import supercell, symmetry

    big = symmetry.reduce_to_p1(supercell.supercell(rutile, 4, 4, 4))
    document = Document(big)
    window.add_document(document)
    dock = window.ff_dock
    assert dock.table.rowCount() == big.n_sites > 300

    changes = []
    layouts = []
    model = dock.table.model()
    model.dataChanged.connect(lambda *a: changes.append(a))
    model.layoutChanged.connect(lambda *a: layouts.append(a))

    dock.refresh()

    assert not changes, f"{len(changes)} dataChanged for one fill"
    assert len(layouts) == 1
    assert dock.table.item(big.n_sites - 1, TYPE).text()


def test_the_type_is_shown_in_words_beside_its_name(opened):
    """The one column the user is asked to check was written in a code
    the panel never explained."""
    _window, _document = opened
    dock = _window.ff_dock
    assert dock.table.item(0, TYPE).text() == "Ti6+4"
    assert dock.table.item(0, MEANS).text() == "octahedral Ti(IV)"
    assert dock.table.item(1, MEANS).text() == "sp3 oxygen"


def test_the_parameter_set_retypes_the_table_and_reaches_the_run(
        window, qtbot):
    """UFF4MOF was always on and invisible.  Choosing plain UFF has to
    change both what the table says and what the calculator is built
    with, or the table describes a run that is not the one made."""
    from xtal.io import read_cif
    document = Document(read_cif("resources/samples/MOF-5.cif"))
    window.add_document(document)
    dock = window.ff_dock
    types = {dock.table.item(r, TYPE).text()
             for r in range(dock.table.rowCount())}
    assert "Zn3f2" in types
    assert any("(UFF4MOF)" in dock.table.item(r, MEANS).text()
               for r in range(dock.table.rowCount()))

    dock.parameter_set.setCurrentIndex(
        dock.parameter_set.findData("uff"))
    types = {dock.table.item(r, TYPE).text()
             for r in range(dock.table.rowCount())}
    assert "Zn3f2" not in types and "Zn3+2" in types
    assert dock.options()["parameter_set"] == "uff"


def test_the_panel_shows_sites_and_not_cell_atoms(opened):
    """An override is stored on a site and applies to its whole orbit,
    so a per-atom table would offer edits it could not honour."""
    _window, document = opened
    dock = _window.ff_dock
    assert document.cell.n_atoms == 6
    assert dock.table.rowCount() == 2
    assert "x4" in dock.table.item(1, 0).text()     # the oxygen orbit


def test_the_panel_empties_when_there_is_no_document(window):
    assert window.ff_dock.table.rowCount() == 0
    assert not window.ff_dock.widget().isEnabled()


def test_a_single_point_fills_the_report_and_changes_nothing(opened):
    window, document = opened
    dock = window.ff_dock
    dock.single_point()
    text = dock.report.toPlainText()
    assert "bond" in text and "total" in text
    assert "max force" in text
    assert not document.modified
    assert not document.can_undo


def test_the_menu_reaches_the_panel(opened, qtbot):
    window, _document = opened
    window.actions_["single_point"].trigger()
    assert "total" in window.ff_dock.report.toPlainText()


def test_the_calculate_actions_need_a_document(window):
    for name in ("single_point", "optimize"):
        assert not window.actions_[name].isEnabled()


def test_the_force_field_lives_under_the_modules_menu(opened):
    """Calculate held three entries that were all UFF.  They are the
    three entries under Forcefield now, and Calculate is gone."""
    window, _document = opened
    titles = [a.text() for a in window.menuBar().actions()]
    assert "&Modules" in titles
    assert "Ca&lculate" not in titles


# ------------------------------------------------------- overriding

def test_overriding_a_type_is_undoable_and_shows_in_the_table(opened,
                                                              qtbot):
    window, document = opened
    dock = window.ff_dock
    assert document.set_atom_type([0], "Ti3+4")
    dock.refresh()
    assert dock.table.item(0, TYPE).text() == "Ti3+4"
    assert dock.table.item(0, MEANS).text() == "tetrahedral Ti(IV)"
    assert dock.table.item(0, SURE).text() == "set"
    assert document.modified

    document.undo()
    dock.refresh()
    assert dock.table.item(0, TYPE).text() == "Ti6+4"


def test_only_the_types_of_that_element_are_offered(opened,
                                                    monkeypatch):
    """There is no way to ask for a carbon parameter on an oxygen,
    which would not be a bold modelling choice but a silent
    nonsense."""
    window, _document = opened
    from PySide6.QtWidgets import QInputDialog

    seen = {}

    def fake(_parent, _title, _label, options, current, _editable):
        seen["options"] = options
        return options[current], False

    monkeypatch.setattr(QInputDialog, "getItem", fake)
    window.ff_dock._edit_type(0, 1)
    offered = "\n".join(seen["options"])
    assert "Ti6+4" in offered and "Ti3+4" in offered
    assert not any(o.startswith("O_") for o in seen["options"])


def test_the_override_dialog_says_what_each_type_means(opened,
                                                       monkeypatch):
    """Offered two strings, the user is being asked to choose between
    two strings; offered two shapes, they are being asked a question
    about their crystal."""
    window, document = opened
    from PySide6.QtWidgets import QInputDialog

    seen = {}

    def fake(_parent, _title, _label, options, current, _editable):
        seen["options"] = options
        seen["current"] = current
        return options[2], True          # "Ti6+4 -- octahedral Ti(IV)"

    monkeypatch.setattr(QInputDialog, "getItem", fake)
    window.ff_dock._edit_type(0, 1)
    assert "Ti3+4  --  tetrahedral Ti(IV)" in seen["options"]
    assert "Ti6+4  --  octahedral Ti(IV)" in seen["options"]
    # The type the site already has is the one the dialog opens on,
    # and what is stored is the five-character name alone.
    assert seen["options"][seen["current"]].startswith("Ti6+4")
    assert document.structure.sites[0].props["uff_type"] == "Ti6+4"


# ------------------------------------------------------ optimisation

def test_an_optimisation_lands_as_a_single_undo_step(qtbot, window,
                                                     tmp_path):
    document = Document(water(oh=1.15, angle=95.0))
    window.add_document(document)
    dock = window.ff_dock
    dock.tolerance.setValue(0.001)
    before = document.structure.frac.copy()

    dock.start()
    wait_for_the_run(qtbot, dock)

    assert document.can_undo
    assert document.stack.depth == 1
    assert not np.allclose(document.structure.frac, before)

    document.undo()
    assert np.allclose(document.structure.frac, before)


def test_relaxing_the_cell_changes_the_lattice_in_the_same_command(
        qtbot, window):
    """One command, or a Ctrl+Z would put the atoms back into a cell
    they were never relaxed in."""
    document = Document(water(oh=1.15, angle=95.0))
    window.add_document(document)
    dock = window.ff_dock
    dock.tolerance.setValue(0.01)
    dock.relax_cell.setChecked(True)
    before = document.structure.lattice.matrix.copy()

    dock.start()
    wait_for_the_run(qtbot, dock)

    assert document.stack.depth == 1
    assert not np.allclose(document.structure.lattice.matrix, before)
    document.undo()
    assert np.allclose(document.structure.lattice.matrix, before)


def test_every_optimiser_is_offered_by_name(opened):
    window, _document = opened
    dock = window.ff_dock
    offered = {dock.method.itemData(i)
               for i in range(dock.method.count())}
    assert offered == set(optimize.METHODS)
    assert all("_" not in dock.method.itemText(i)
               for i in range(dock.method.count()))


def test_the_optimiser_starts_on_smart(opened):
    """The same default the scan has.  L-BFGS as the first entry was
    the default by accident of dictionary order, and its first step
    from a hand-built geometry is the one that goes wild."""
    window, _document = opened

    assert window.ff_dock.method.currentData() == "smart"


def test_the_stress_tolerance_follows_the_cell_checkbox(opened):
    window, _document = opened
    dock = window.ff_dock
    assert not dock.stress_tolerance.isEnabled()
    dock.relax_cell.setChecked(True)
    assert dock.stress_tolerance.isEnabled()
    dock.relax_cell.setChecked(False)
    assert not dock.stress_tolerance.isEnabled()


def test_the_pressure_box_follows_the_cell_checkbox(opened):
    """A pressure is a term in the cell's energy, so offering one for
    a cell that cannot move would be offering a control that does
    nothing."""
    window, _document = opened
    dock = window.ff_dock
    assert not dock.relax_cell.isChecked()
    assert not dock.pressure.isEnabled()
    dock.relax_cell.setChecked(True)
    assert dock.pressure.isEnabled()
    assert "few percent out" in dock.notes.text()
    dock.relax_cell.setChecked(False)
    assert not dock.pressure.isEnabled()


def test_the_run_draws_itself_as_it_goes(qtbot, window):
    """Each step previews into the document so the viewport can draw
    it, and none of those previews reaches the undo stack.

    The previews travel on ``previewChanged`` and not on
    ``structureChanged``, which is what keeps them off every panel in
    the window that has nothing new to show.  Only the command at the
    end is a change to the structure.
    """
    document = Document(water(oh=1.15, angle=95.0))
    window.add_document(document)
    dock = window.ff_dock
    dock.tolerance.setValue(0.001)

    previews, changes = [], []
    document.previewChanged.connect(lambda: previews.append(1))
    document.structureChanged.connect(lambda _c: changes.append(1))
    dock.start()
    wait_for_the_run(qtbot, dock)

    assert len(previews) > 3                # one per step, at least
    assert len(changes) == 1                # the command at the end
    assert document.stack.depth == 1
    assert len(dock.plot.history) > 1


def test_stopping_a_run_leaves_the_document_where_it_started(
        qtbot, slow):
    """The promise cancelling has to keep: whatever the run had
    reached, the document is either untouched or one Ctrl+Z away from
    untouched.  Never a half-applied geometry.

    The worker is paused synchronously first so that it cannot reach
    the end before the test cancels it -- waiting for a step count
    would be racing an optimiser that sometimes converges in three.
    """
    _window, document, dock = slow
    before = document.structure.frac.copy()

    dock.start()
    dock.worker.pause()
    dock.stop()
    wait_for_the_run(qtbot, dock)

    assert "without converging" in dock.report.toPlainText()
    assert "stopped before converging" in dock.notes.text()
    assert document.stack.depth <= 1
    if document.can_undo:
        document.undo()
    assert np.allclose(document.structure.frac, before)


def test_a_finished_run_reports_convergence_and_the_breakdown(qtbot,
                                                              window):
    document = Document(water(oh=1.10, angle=100.0))
    window.add_document(document)
    dock = window.ff_dock
    dock.tolerance.setValue(0.001)
    dock.start()
    wait_for_the_run(qtbot, dock)
    text = dock.report.toPlainText()
    assert "converged" in text
    assert "bond" in text


def test_the_controls_lock_while_a_run_is_in_flight(qtbot, slow):
    _window, _document, dock = slow
    dock.start()
    # Paused synchronously, before the worker can reach the end: the
    # state under test is then held still rather than raced for.
    dock.worker.pause()
    assert dock.run_button.text() == "Stop"
    assert not dock.energy_button.isEnabled()
    assert not dock.method.isEnabled()
    assert dock.pause_button.isEnabled()

    dock.stop()
    wait_for_the_run(qtbot, dock)
    assert dock.run_button.text() == "Optimise"
    assert dock.energy_button.isEnabled()
    assert dock.method.isEnabled()


def test_pausing_and_resuming(qtbot, slow):
    _window, _document, dock = slow
    dock.start()
    dock.toggle_pause()
    assert dock.worker.is_paused
    assert dock.pause_button.text() == "Resume"

    dock.toggle_pause()
    assert not dock.worker.is_paused
    assert dock.pause_button.text() == "Pause"

    dock.stop()
    wait_for_the_run(qtbot, dock)


def test_freezing_everything_refuses_instead_of_running(qtbot,
                                                        window):
    document = Document(water(oh=1.15))
    window.add_document(document)
    document.select_all()
    dock = window.ff_dock
    dock.freeze.setChecked(True)
    dock.start()
    assert not dock.is_running
    assert "nothing to relax" in dock.notes.text()


# ---------------------------------------------------------- the worker

def test_the_worker_reports_every_step_then_finishes(qtbot):
    from xtal.ff import ENGINES

    structure = water(oh=1.15, angle=95.0)
    worker = OptimizationWorker(
        ENGINES.build("uff", structure.copy()), structure.copy(),
        max_steps=100, force_tolerance=1e-3)
    steps = []
    worker.stepped.connect(steps.append)
    with qtbot.waitSignal(worker.finished, timeout=TIMEOUT) as blocker:
        worker.run()
    assert len(steps) > 1
    assert blocker.args[0].converged


def test_recording_does_not_depend_on_how_often_anyone_draws(qtbot):
    """Phase I: the redraw rate is a property of the viewport and of
    nothing else.  ``OptimizationWorker`` has no notion of a preview
    interval at all -- it calls the recorder for every step it emits,
    which is the structural guarantee that a run watched as a moving
    crystal and a run watched as a plot (or not watched at all, with
    the viewport's redraw set to "Not while it runs") leave behind the
    identical trajectory.
    """
    from xtal.ff import ENGINES

    class CountingRecorder:
        def __init__(self):
            self.steps = 0

        def begin_steps(self):
            pass

        def step(self, _step):
            self.steps += 1

    structure = water(oh=1.15, angle=95.0)
    recorder = CountingRecorder()
    worker = OptimizationWorker(
        ENGINES.build("uff", structure.copy()), structure.copy(),
        max_steps=100, force_tolerance=1e-3, recorder=recorder)
    steps = []
    worker.stepped.connect(steps.append)
    with qtbot.waitSignal(worker.finished, timeout=TIMEOUT):
        worker.run()
    assert len(steps) > 1
    assert recorder.steps == len(steps)


def test_a_failing_worker_says_so_instead_of_taking_the_thread_down(
        qtbot):
    """An exception inside run() would otherwise leave the panel
    waiting for a result that never comes, which looks like a hang."""
    class Broken:
        n_atoms = 3

        def compute(self, *_a, **_k):
            raise RuntimeError("no parameters for unobtainium")

    worker = OptimizationWorker(Broken(), water(), max_steps=5)
    with qtbot.waitSignal(worker.failed, timeout=TIMEOUT) as blocker:
        worker.run()
    assert "unobtainium" in blocker.args[0]


def test_the_worker_can_be_cancelled_between_steps(qtbot):
    from xtal.ff import ENGINES

    structure = water(oh=1.30)
    worker = OptimizationWorker(
        ENGINES.build("uff", structure.copy()), structure.copy(),
        max_steps=5000, force_tolerance=1e-12)
    worker.stepped.connect(
        lambda step: worker.cancel() if step.iteration >= 2 else None)
    with qtbot.waitSignal(worker.finished, timeout=TIMEOUT) as blocker:
        worker.run()
    assert not blocker.args[0].converged
    assert blocker.args[0].steps <= 3



def test_one_stop_reaches_the_loop_and_the_engine(qtbot):
    """The worker kept a threading.Event for its loop and a
    Cancellation for the engine, set together and read apart.  One
    record now: a Stop ends the loop *and* fires what an external
    engine registered to kill its program with."""
    from xtal.ff import ENGINES

    structure = water(oh=1.30)
    worker = OptimizationWorker(
        ENGINES.build("uff", structure.copy()), structure.copy(),
        max_steps=5000, force_tolerance=1e-12)
    killed = []
    worker._stop.when_cancelled(lambda: killed.append(True))
    worker.stepped.connect(
        lambda step: worker.cancel() if step.iteration >= 1 else None)
    with qtbot.waitSignal(worker.finished, timeout=TIMEOUT) as blocker:
        worker.run()

    assert killed == [True]
    assert not blocker.args[0].converged



def test_the_panel_and_the_cli_offer_the_charge_sources_uff_declares(
        window, capsys):
    """Three copies, until a fourth source would have had to be
    added to each."""
    from xtal.cli import build_parser
    from xtal.ff.uff import calculator as uff

    declared = next(p for p in uff.OPTIONS if p.name == "charges")
    values = [value for value, _label in declared.choices]
    charges = window.ff_dock.charges

    assert [charges.itemData(i) for i in range(charges.count())] \
        == values
    parser = build_parser()
    for value in values:
        assert parser.parse_args(
            ["optimize", "x.cif", "--charges", value]).charges == value
    with pytest.raises(SystemExit):
        parser.parse_args(["optimize", "x.cif", "--charges", "bogus"])


# ------------------------------------------------ reading the panels

def test_the_dftb_run_and_the_scan_read_the_same_hamiltonian(window):
    """Two readers of the DFTB+ panel, one of them looking only at its
    form, and nothing tying their answers together."""
    from xtalapp.docks.ff_panel import panel_options

    form = window.dftb_dock.engine_forms["dftb"]
    form.set_values({"method": "scc", "dispersion": "d3"})

    read = panel_options(window, "dftb")

    assert read["method"] == "scc" and read["dispersion"] == "d3"
    assert read == form.values()


def test_the_selected_engine_is_read_from_its_own_controls(window):
    """UFF has hand-built controls rather than a form; reading a form
    for it would miss the parameter set the user chose."""
    from xtalapp.docks.ff_panel import panel_engine, panel_options

    dock = window.ff_dock
    dock.parameter_set.setCurrentIndex(
        dock.parameter_set.findData("uff"))

    assert panel_engine(window) == "uff"
    assert panel_options(window, "uff")["parameter_set"] == "uff"
    assert panel_options(window, "nonesuch") == {}


# ------------------------------------------------------------ the plot

def test_the_plot_says_so_before_there_is_anything_to_draw(qtbot):
    from xtalapp.plot import TracePlot

    plot = TracePlot()
    qtbot.addWidget(plot)
    plot.resize(300, 200)
    plot.grab()                             # must not raise
    plot.set_history([(0, -1.0, 5.0), (1, -2.0, 1.0),
                      (2, -2.5, 0.01)])
    plot.grab()
    assert len(plot.history) == 3
    plot.clear()
    assert plot.history == []


def test_the_plot_survives_a_flat_trace(qtbot):
    """Every value identical is a zero range, and a naive scaling
    divides by it."""
    from xtalapp.plot import TracePlot

    plot = TracePlot()
    qtbot.addWidget(plot)
    plot.resize(300, 200)
    plot.set_history([(0, 1.0, 0.5), (1, 1.0, 0.5)])
    plot.grab()


# ------------------------------------------------- more than one engine

def test_the_chooser_appears_once_there_is_something_to_choose(opened):
    """The dock hides its chooser when it is given one engine, which
    is what it was given until xTB was registered.  A second entry is
    the whole visible outcome of adding an engine, so it is worth a
    test of its own rather than being assumed from the layout."""
    window, _ = opened
    dock = window.ff_dock
    # isHidden rather than isVisible: nothing in a widget test is
    # shown, so isVisible is False for every widget in the window.
    assert not dock.engine.isHidden()
    assert [dock.engine.itemData(i) for i in range(dock.engine.count())] \
        == ["uff", "xtb", "mace", "orb", "mattersim"]


def test_choosing_xtb_hides_the_controls_that_are_uffs(opened):
    window, _ = opened
    dock = window.ff_dock
    dock.engine.setCurrentIndex(dock.engine.findData("xtb"))
    assert dock.coulomb.isHidden()
    assert not dock.engine_forms["xtb"].isHidden()


def test_choosing_uff_shows_the_controls_that_are_uffs(opened):
    """UFF declares its options so that the scan dialog can offer
    UFF4MOF without reaching into this panel, and the panel read that
    as "this engine draws its own form" and hid all five of UFF's
    controls -- with nothing generated to replace them, because UFF is
    left out of those by name.  The parameter set was unreachable and
    UFF4MOF could not be turned off."""
    window, _ = opened
    dock = window.ff_dock
    dock.engine.setCurrentIndex(dock.engine.findData("xtb"))
    dock.engine.setCurrentIndex(dock.engine.findData("uff"))
    assert "uff" not in dock.engine_forms
    for widget in dock.uff_rows:
        assert not widget.isHidden()
        label = dock.setup_form.labelForField(widget)
        assert label is None or not label.isHidden()


def test_a_method_the_machine_cannot_run_greys_out_as_it_is_chosen(
        opened, monkeypatch, tmp_path):
    """The availability of this engine is a function of what the form
    says: GFN-FF needs xtb and the other two do not, so the answer
    changes as the Method combo does.

    The panel used to re-ask only when the *engine* changed, which
    left Run enabled for a method with no binary behind it until
    something else happened to refresh the dock -- and then the
    failure arrived as a subprocess error after the button.

    tblite is a stand-in: the test is about the combo, and a runner
    without tblite installed otherwise greys GFN2 out as well.
    """
    monkeypatch.setenv("XTAL_TBLITE", str(
        write_program(tmp_path, "tblite", "raise SystemExit(0)\n")))
    monkeypatch.setenv("XTAL_XTB", "/nowhere/xtb")
    monkeypatch.setattr(xtb, "PROGRAMS", tuple(
        replace(p, name=f"{p.name}-not-installed")
        if p is xtb.XTB else p for p in xtb.PROGRAMS))

    window, _ = opened
    dock = window.ff_dock
    dock.engine.setCurrentIndex(dock.engine.findData("xtb"))
    method = dock.engine_forms["xtb"].widgets["method"]

    method.setCurrentIndex(method.findData("gfnff"))
    assert not dock.run_button.isEnabled()
    assert "xtb" in dock.engine_note.text().lower()

    method.setCurrentIndex(method.findData("gfn2"))
    assert dock.run_button.isEnabled()
    assert dock.engine_note.text() == ""


def test_every_engine_that_is_registered_can_be_chosen(window):
    """An engine the registry knows and no dock offers.

    MACE shipped like that: registered, tested, importable, and
    reachable from nowhere in the window, because the Force Field
    dock is handed a hand-written list of engine names and the new
    one was not added to it.  Nothing failed -- the panel drew two
    entries where there should have been three, and the only way to
    find out was to go looking for the third.

    Asserted as a partition rather than "mace is in ff_dock" so that
    the next engine cannot repeat it: every registered engine is
    offered by exactly one of the two docks.
    """
    from xtal.ff import ENGINES

    docks = (window.ff_dock, window.dftb_dock)
    offered = [engine.name for dock in docks for engine in dock.engines]
    assert sorted(offered) == sorted(ENGINES.names())
    assert len(offered) == len(set(offered))


# ------------------------------------------- an engine that is missing

def test_a_missing_engine_links_to_its_install_command(opened,
                                                       monkeypatch):
    """The command is a long path with nowhere to wrap: in the note it
    pushed the panel wider than its column, was cut off at the edge,
    and could not be copied from a label anyway.  The note links to
    Preferences > Engines, where it can."""
    import sys

    from xtal.ff.orb import calculator as orb
    from xtalapp.docks import MAXIMUM_MINIMUM

    monkeypatch.setattr(orb, "installed", lambda: False)
    window, _ = opened
    dock = window.ff_dock
    dock.engine.setCurrentIndex(dock.engine.findData("orb"))
    note = dock.engine_note

    assert not note.isHidden()
    assert "ORB is not installed" in note.text()
    assert 'href="engines"' in note.text()
    assert sys.executable not in note.text()
    assert note.minimumSizeHint().width() <= MAXIMUM_MINIMUM

    shown = []
    monkeypatch.setattr(window, "show_preferences",
                        lambda page="": shown.append(page))
    note.linkActivated.emit("engines")
    assert shown == ["Engines"]


# ------------------------------------------- where a method comes from

def _links(label):
    import re
    return re.findall(r'href="([^"]+)"', label.text())


def test_the_chosen_method_links_to_where_it_comes_from(window):
    """Right under the chooser, and following it: UFF4MOF cites its own
    papers as well as UFF's, plain UFF only Rappe's, an ML engine its
    preprint and its repository.  The links go to the browser."""
    dock = window.ff_dock
    source = dock.engine_source
    assert source.openExternalLinks()

    dock.parameter_set.setCurrentIndex(
        dock.parameter_set.findData("uff4mof"))
    assert "https://doi.org/10.1021/ct400952t" in _links(source)
    assert not source.isHidden()

    dock.parameter_set.setCurrentIndex(dock.parameter_set.findData("uff"))
    assert _links(source) == ["https://doi.org/10.1021/ja00051a040"]

    dock.engine.setCurrentIndex(dock.engine.findData("mattersim"))
    assert _links(source) == ["https://arxiv.org/abs/2405.04967",
                              "https://github.com/microsoft/mattersim"]


def test_the_charge_scheme_is_cited_once_it_is_doing_the_charges(
        window):
    dock = window.ff_dock
    eqeq = "https://doi.org/10.1021/jz3008485"
    dock.charges.setCurrentIndex(dock.charges.findData("eqeq"))
    assert eqeq not in _links(dock.engine_source)
    dock.coulomb.setChecked(True)
    assert eqeq in _links(dock.engine_source)


def test_the_dftb_panel_cites_the_hamiltonian_it_runs(window):
    """The DFTB+ dock has no chooser to sit under; the links head its
    Model box instead, and change with the form."""
    dock = window.dftb_dock
    form = dock.engine_forms["dftb"]
    form.set_values({"method": "scc", "dispersion": "d3"})
    links = _links(dock.engine_source)
    assert "https://doi.org/10.1103/PhysRevB.58.7260" in links
    assert "https://doi.org/10.1063/1.3382344" in links
    assert "https://github.com/dftbplus/dftbplus" in links
