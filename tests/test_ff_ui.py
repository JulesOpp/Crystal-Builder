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

from tests.conftest_ff import water  # noqa: E402
from tests.test_app_shell import StubViewport  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.workers import OptimizationWorker  # noqa: E402

TIMEOUT = 20000


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
    assert dock.table.item(0, 1).text() == "Ti6+4"
    assert "neighbours" in dock.table.item(0, 3).text()


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


def test_the_dock_has_a_window_menu_entry(opened):
    window, _document = opened
    titles = [a.text() for a in window.menuBar().actions()]
    assert "Ca&lculate" in titles


# ------------------------------------------------------- overriding

def test_overriding_a_type_is_undoable_and_shows_in_the_table(opened,
                                                              qtbot):
    window, document = opened
    dock = window.ff_dock
    assert document.set_atom_type([0], "Ti3+4")
    dock.refresh()
    assert dock.table.item(0, 1).text() == "Ti3+4"
    assert dock.table.item(0, 2).text() == "set"
    assert document.modified

    document.undo()
    dock.refresh()
    assert dock.table.item(0, 1).text() == "Ti6+4"


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
    assert "Ti6+4" in seen["options"] and "Ti3+4" in seen["options"]
    assert not any(o.startswith("O_") for o in seen["options"])


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


def test_the_run_draws_itself_as_it_goes(qtbot, window):
    """Each step previews into the document so the viewport can draw
    it, and none of those previews reaches the undo stack."""
    document = Document(water(oh=1.15, angle=95.0))
    window.add_document(document)
    dock = window.ff_dock
    dock.tolerance.setValue(0.001)

    seen = []
    document.structureChanged.connect(lambda _c: seen.append(1))
    dock.start()
    wait_for_the_run(qtbot, dock)

    assert len(seen) > 3                    # one per step, at least
    assert document.stack.depth == 1        # and one command at the end
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
