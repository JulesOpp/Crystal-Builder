"""
xtalapp.module_runner
=====================
One run at a time, on a worker thread, into a run folder, with a Stop
button that reaches whatever is actually running -- a loop in this
process or a binary in another.  Nothing here names a module:
everything it needs comes off the registry entry, which is what
"adding an engine touches no existing file" means.

This was the ``MODULES`` section of :mod:`xtalapp.mainwindow` and is
the same code; it is here because it is the one part of the shell with
a lifetime of its own.  A run outlives the click that started it, owns
a thread and a folder, and has to be findable by the Stop button and
by whatever the window is doing when the thread comes back -- which is
state, and the window has enough.

**It holds the window rather than the pieces it uses**, and looks each
one up when it needs it.  The docks it reports into are built after
this object is, and a runner that captured them at construction would
have to be constructed later than the state it owns.  The dependency
is real either way: a module runner needs a shell to run in, and
naming it in a constructor argument is the whole of the improvement
over reading it off ``self``.
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from xtal.core.structure import Change
from xtal.modules import MODULES, Job, ModuleError
from xtal.modules import record as module_record
from xtal.modules.job import restore_dummies, without_dummies
from xtal.workspace import safe_name
from xtalapp.curve import save_curve
from xtalapp.dialogs import module_dialog
from xtalapp.dialogs.module_form import ModuleDialog
from xtalapp.document import Document
from xtalapp.histogram import save_histogram
from xtalapp.workers import ModuleWorker, start_in_thread


class ModuleRunner(QObject):
    """The one module run that may be going, and what each action was
    last run with.

    The parameters are remembered here rather than in ``QSettings``: a
    parameter set is worth offering again in the session that chose
    it, and not worth restoring six weeks later against a different
    structure.

    **A QObject, parented to the window, and that is not decoration.**
    It owns no signals; it *receives* two, and a worker emits them
    from inside its own thread.  Qt decides where a slot runs from the
    receiver's thread affinity, which a plain Python object does not
    have -- so the finished handler would run on the worker thread,
    and the first thing it does is refresh the menu bar.  Reaching a
    widget from another thread does not raise, it aborts the process.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.module_worker: ModuleWorker | None = None
        self._module_thread = None
        self._module_params: dict = {}
        # The dummy atoms kept out of the run in progress, so they can
        # be put back into a geometry it hands over.  See
        # `xtal.modules.job.without_dummies`.
        self._held_dummies = None

    def run_module_action(self, module_name: str,
                          action_name: str) -> None:
        """Run one entry of one module.

        Ask for the parameters, open a run folder under the structure
        the run belongs to, and start a thread.  The three Force Field
        entries divert to the panel that has always performed them --
        see :mod:`xtal.modules.forcefield` for why that is the one
        exception rather than the pattern.
        """
        try:
            module, action = MODULES.find(
                f"{module_name}.{action_name}")
        except ModuleError as exc:
            self.window.show_message(str(exc))
            return
        if action.shell:
            shell_action = self.window.actions_.get(action.shell)
            if shell_action is None:                # pragma: no cover
                self.window.show_message(
                    f"{module.label} cannot do that here")
            elif not shell_action.isEnabled():
                self.window.show_message(
                    f"{action.label} is not available right now")
            else:
                shell_action.trigger()
            return
        if self.module_worker is not None:
            self.window.show_message(
                "a module is already running -- stop it first")
            return
        available = module.availability()
        if not available:
            self.window.show_message(available.reason)
            return
        document = self.window.current_document()
        if not action.needs_structure:
            # It makes its own structure, so whatever is in front is
            # not what it runs against and must not be handed to it.
            # A trajectory being played is not in its way either.
            document = None
        elif document is None:
            self.window.show_message(
                f"{action.label} needs a structure open")
            return
        elif document.is_playing:
            # The atoms are showing a frame of a trajectory, so the
            # geometry a module would be handed is not the document's.
            # The menu entries are already disabled; this is what
            # stops the tree reaching it.
            self.window.show_message(
                "close the trajectory first -- these atoms are a "
                "frame being played, not the structure")
            return
        key = f"{module.name}.{action.name}"
        values = self._ask(module, action,
                           self._module_params.get(key))
        if values is None:                          # cancelled
            return
        self._module_params[key] = values
        self._start_module(module, action, values, document)

    def _ask(self, module, action, initial) -> dict | None:
        """The parameters to run with, or ``None`` if it was cancelled.

        The generated form, unless the action named a dialog of its
        own.  ``Action.dialog`` substitutes the *collection* of the
        parameters and nothing else -- the values come back in the
        same dict, and ``run`` never learns which asked for them --
        because PORMAKE's parameters are decided by the topology that
        was picked and a flat static form cannot ask that question.
        See :class:`xtal.modules.registry.Action`.
        """
        chosen = module_dialog(action.dialog)
        if chosen is None:
            return ModuleDialog.ask(module, action, self.window,
                                    initial)
        return chosen.ask(module, action, self.window, initial)

    def _start_module(self, module, action, values, document) -> None:
        folder = None
        if action.writes_run_folder:
            try:
                folder = module_record.open_run(
                    self._entry_for(module, document), module, action,
                    values,
                    document.structure if document is not None
                    else None)
            except OSError as exc:
                self.window.show_message(
                    f"could not write into the workspace: {exc}")
                return
        if folder is None and action.writes_run_folder:
            # Same rule as the Force Field panel: a structure with no
            # workspace still runs, it just leaves nothing behind, and
            # the status bar says so once rather than putting up a
            # dialog.
            self.window.show_message(
                "no workspace open, so this run will not be kept -- "
                "File > New Workspace... gives it somewhere to go")
        # The worker gets a copy of the structure.  It reads it, caches
        # on it and may move it, while the window goes on redrawing the
        # one the user can see; sharing them would be a data race in
        # the most literal sense.
        #
        # And a copy with the dummy atoms taken out -- see
        # `xtal.modules.job.without_dummies`.  A marker has no
        # force-field type and no radius a porosity code knows, and
        # one in the cell is enough to fail a Zeo++ run outright.
        # They are put back if the module hands a geometry back.
        structure, self._held_dummies = (
            without_dummies(document.structure.copy())
            if document is not None else (None, None))
        job = Job(structure=structure,
                  params=values, folder=folder,
                  label=f"{module.name}.{action.name}")
        if self._held_dummies is not None:
            self.window.show_message(
                f"{len(self._held_dummies[0])} dummy atom(s) left out "
                f"of this run -- a marker is not chemistry")
        worker = ModuleWorker(module, action, job)
        worker.progressed.connect(self.window.modules_dock.set_progress)
        worker.progressed.connect(self.window.run_progress.set_progress)
        worker.finished.connect(self._on_module_finished)
        worker.failed.connect(self._on_module_failed)
        self.module_worker = worker
        self.window.modules_dock.set_running(worker.label)
        self.window.run_progress.start(worker.label)
        self.window._refresh_shell()
        if folder is not None:
            self.window.refresh_workspace()
            self.window.log_dock.show_file(folder.path / "run.log")
        # Parented to the window, so the thread outlives this
        # method's reference to it whatever Python does with the
        # attribute below.
        self._module_thread = start_in_thread(worker, self.window)

    def _entry_for(self, module, document):
        """Which workspace entry this run's folder goes under.

        The document's, when the run is about a document.  A module
        that builds its own structure has none, so its runs go under
        an entry named for the module -- ``add_document`` exists for
        exactly that, and the alternative is putting a framework built
        from nothing into the folder of whichever crystal happened to
        be in front, which is a filing error a person would then have
        to undo.
        """
        if document is not None:
            return document.entry
        workspace = self.window.workspace
        if workspace is None:
            return None
        try:
            return workspace.add_document(module.label)
        except OSError as exc:
            self.window.show_message(
                f"could not write into the workspace: {exc}")
            return None

    def stop_module(self) -> None:
        """Stop whatever the module tree started.

        For an in-process job this is a flag it looks at between units
        of work; for an external one it is a signal to the process.
        The button does not have to know which.
        """
        if self.module_worker is not None:
            self.module_worker.cancel()
            self.window.show_message("stopping...")

    def _on_module_finished(self, result) -> None:
        worker, job = self._finish_module()
        # The pictures are written before the log is closed, so the
        # log can name them the way it names every other artefact.
        self._save_report_images(job, result)
        module_record.close_run(job.folder if job else None, result)
        self._show_report(worker, result)
        if result.structure is not None:
            self._adopt_module_structure(worker, result)
        self.window.run_progress.finish()
        self.window.modules_dock.set_idle(result.summary())
        self.window._refresh_shell()
        self.window.show_status(result.summary())
        if result.detail:
            self.window.show_message(result.detail.splitlines()[0])
        self._after_module_run(job)

    def _on_module_failed(self, message: str) -> None:
        """A module that raised.

        Reported where the run was started from and written into the
        log that is already open, rather than into a dialog that has
        to be dismissed before the log can be read.
        """
        _worker, job = self._finish_module()
        module_record.close_run(job.folder if job else None,
                                error=message)
        # The previous run's numbers must not sit there under this
        # run's heading, which is the one way this panel could be
        # worse than no panel.
        self.window.run_progress.finish()
        self.window.results_dock.clear()
        self.window.modules_dock.set_idle(f"failed: {message}")
        self.window._refresh_shell()
        self.window.show_status(f"the module failed: {message}")
        self._after_module_run(job)

    def _show_report(self, worker, result) -> None:
        """Put a module's tables and histograms where they can be read.

        Raised only when there is something in it.  A panel that
        appears after every run -- including the ones whose whole
        answer is a sentence -- is one people learn to close, and then
        the one run that had a histogram in it goes unseen.
        """
        report = getattr(result, "report", None)
        label = worker.label if worker is not None else ""
        self.window.results_dock.show_report(report, label)
        if report:
            self.window.results_dock.show()
            self.window.results_dock.raise_()

    def _save_report_images(self, job, result) -> None:
        """Write a run's histograms and curves into its folder as PNGs.

        The picture is the answer for a pore size distribution, and a
        run folder holding four columns of numbers and no plot is one
        somebody has to reopen the application to look at.  Drawn here
        rather than by the module because the drawing is Qt's and the
        module is headless -- and a failure to write one must never
        cost the run, which has already succeeded.
        """
        report = getattr(result, "report", None)
        if job is None or job.folder is None or not report:
            return
        written = []
        plots = ([(h, save_histogram) for h in report.histograms]
                 + [(c, save_curve) for c in report.curves])
        for index, (block, draw) in enumerate(plots):
            name = safe_name(block.title or f"plot-{index + 1}",
                             f"plot-{index + 1}").lower()
            try:
                written.append(draw(
                    block, job.folder.path / f"{name}.png"))
            except Exception as exc:                # noqa: BLE001
                self.window.show_message(f"could not write the plot: {exc}")
                return
        if written:
            result.artifacts = tuple(result.artifacts) + tuple(written)

    def _finish_module(self):
        """Let go of the run, but not of the thread it was on.

        The worker signals ``finished`` from inside ``run``, so at
        this point the thread has not stopped yet.  It is parented to
        the window and Qt deletes it when it has -- nothing here may
        touch its lifetime, because destroying a ``QThread`` that is
        still running aborts the process rather than raising anything
        catchable.
        """
        worker = self.module_worker
        job = worker.job if worker is not None else None
        self.module_worker = None
        return worker, job

    def _after_module_run(self, job) -> None:
        """The workspace has changed and the log has stopped growing.

        The tree is read from the directory on every refresh, so this
        is the whole of keeping it in step with what just happened.
        """
        if job is not None and job.folder is not None:
            self.window.refresh_workspace()
            self.window.log_dock.poll()
        self.window.modules_dock.refresh()

    def _adopt_module_structure(self, worker, result) -> None:
        """Take a geometry a module produced, as one undoable edit.

        The module worked on a copy, so this is the only point at
        which anything it did reaches the document -- and it reaches
        it as a single command, so Ctrl+Z afterwards gives back the
        structure the run started from.

        Unless it did not start from one.  A module that declared
        ``needs_structure = False`` was handed no document and built
        what it returned out of nothing, so there is no edit to make
        and nothing to undo -- it opens in a tab of its own instead.
        """
        action = worker.action if worker is not None else None
        if action is not None and not action.needs_structure:
            self._open_module_structure(worker, result)
            return
        document = self.window.current_document()
        if document is None or document.is_playing:
            self.window.show_message(
                "the module produced a structure, and it was not "
                "adopted because the document it ran against is no "
                "longer in front")
            return
        label = f"{worker.module.label}: {worker.action.label}" \
            if worker is not None else "Module result"
        adopted, restored = restore_dummies(result.structure,
                                            self._held_dummies)
        if not restored:
            self.window.show_message(
                "the dummy atoms were not put back: this run returned "
                "different atoms from the ones it was given, so there "
                "is nowhere they belong in it")
        document.replace_structure(adopted, label.rstrip("."),
                                   Change.ALL)

    def _open_module_structure(self, worker, result) -> None:
        """A structure a module built from nothing, in a new tab.

        Not into the current document, which is the rule this branch
        exists to break: ``_adopt_module_structure`` replaces the
        structure that is in front, so a build with something open
        would have destroyed it and a build with nothing open would
        have silently thrown away what it had just made.

        The document has no path.  It is named after the structure
        rather than after a file, and File > Save As is what gives it
        one -- the run folder already holds the CIF it was read back
        from, so nothing is lost if the tab is closed without saving.
        """
        document = Document(result.structure)
        self.window.add_document(document)
        self.window.show_message(
            f"{document.title} opened in a new tab")
