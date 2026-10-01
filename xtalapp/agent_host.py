"""
xtalapp.agent_host
==================
The window as a host for the agent's tools: one session per open tab.

:mod:`xtal.agent.tools` acts on whatever :class:`~xtal.agent.tools.Host`
it is given.  Headless that is a dict of :class:`~xtal.agent.Session`
objects; here it is the window, and each session is a
:class:`WindowSession` over one tab's :class:`~xtalapp.document.Document`
-- so an assistant's ``add_atom`` is the command a person's click
pushes, on that tab's stack, and the person's Ctrl+Z takes it back.

**Every verb is served on the GUI thread.**  The tools are called on
the server's thread, and a command run there would race the viewport
drawing the same structure -- the data race :mod:`xtalapp.workers`
copies the structure to avoid.  So a verb crosses to the GUI thread
through :class:`Bridge` whole, reading as well as pushing: a site
index is checked against the structure it will be applied to, and
nothing caches derived data on the document's structure from another
thread.  The calculations (``energy``, ``optimize``, ``run``) are the
exception, as they are for the Force Field panel: they copy the
structure on the GUI thread, compute over the copy on the calling
thread, and cross back only to apply.

**The gates.**  A verb is refused with ``WINDOW_BUSY`` while the tab
plays a trajectory (its atoms are a frame, and ``Document.run`` would
refuse) or while a calculation runs (whose result is applied over
whatever is there when it finishes).  An agent calculation registers
itself as an :class:`AgentCalculation` so the window counts it too.
A relaxation whose tab was edited while it ran is not applied:
``DOCUMENT_CHANGED``, and ``RESULT_NOT_APPLIED`` names the run folder
that keeps it.

The GUI thread never waits on another thread here: :meth:`Bridge.call`
from the GUI thread calls straight through, and only the server's
thread blocks.  Whatever stops the server must not wait for it from
the GUI thread while a call may be pending -- that is a deadlock.
"""

from __future__ import annotations

import functools
import inspect as pyinspect
import threading
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Slot

from xtal.agent.answers import VerbResult
from xtal.agent.capabilities import VERBS
from xtal.agent.diagnostics import Diagnostic
from xtal.agent.session import Session
from xtal.agent.tools import HOST_VERBS, NO_SESSION, Host

#: Verbs that change nothing, and so may run while the window is busy:
#: an assistant waiting for a calculation can still look.
READ_ONLY = ("inspect", "select")

#: Verbs that compute over a copy, off the GUI thread.
CALCULATIONS = ("energy", "optimize", "run")

#: Why a call from the server's thread is refused once it is stopping.
CLOSING = "the window is closing"
#: Why a call begun under a server since stopped is refused, though
#: another has started: its client has gone, and nobody would be told
#: what it did.
STOPPED = "the window stopped serving"


class BridgeClosed(RuntimeError):
    """A call from the server's thread the window will not take."""


def on_gui_thread(obj: QObject) -> bool:
    return QThread.currentThread() is obj.thread()


class Bridge(QObject):
    """Runs a callable on the GUI thread and hands back what it
    returned, or raises what it raised, on the caller's thread.

    One call at a time: the callable and its outcome are held here
    under a lock for the length of the crossing.

    ``closing`` is set when the server stops: a call already waiting
    is still answered (stopping turns the event loop while it waits),
    and a new one from another thread raises rather than queueing on a
    GUI thread that may never turn again.  ``generation`` counts the
    server's starts: a call carries the one it began under, and is
    refused once another start has made it stale -- a relaxation left
    computing past a stop must not apply under the next server.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._pending = None
        self._outcome = None
        self.closing = False
        self.generation = 0
        self._lock_posted = threading.Lock()
        self._posted = []

    def call(self, fn, generation: int | None = None):
        """``fn()`` on the GUI thread.  From another thread,
        :class:`BridgeClosed` when the server is stopping or the call
        belongs to a server since replaced (``generation``, read when
        the work it is part of began; now, if not given)."""
        if on_gui_thread(self):
            return fn()
        if generation is None:
            generation = self.generation
        with self._lock:
            # Inside the lock: a call that waited for it while the
            # server stopped must not go through after the stop.
            self._refuse(generation)
            self._pending, self._outcome = (fn, generation), None
            try:
                QMetaObject.invokeMethod(self, "_invoke",
                                         Qt.BlockingQueuedConnection)
                outcome = self._outcome
            finally:
                self._pending = self._outcome = None
        if outcome is None:
            raise RuntimeError("the window did not answer")
        ok, value = outcome
        if not ok:
            raise value
        return value

    def _refuse(self, generation: int) -> None:
        if self.closing:
            raise BridgeClosed(CLOSING)
        if generation != self.generation:
            raise BridgeClosed(STOPPED)

    @Slot()
    def _invoke(self) -> None:
        fn, generation = self._pending
        try:
            # Queued under one server and reached under the next.
            if generation != self.generation:
                raise BridgeClosed(STOPPED)
            self._outcome = (True, fn())
        except BaseException as exc:    # noqa: BLE001 -- re-raised
            self._outcome = (False, exc)

    def post(self, fn) -> None:
        """``fn`` on the GUI thread when it next turns, not waited for:
        what a stopping server still owes the window, such as taking
        its calculation off the count."""
        if on_gui_thread(self):
            fn()
            return
        with self._lock_posted:
            self._posted.append(fn)
        QMetaObject.invokeMethod(self, "_run_posted",
                                 Qt.QueuedConnection)

    @Slot()
    def _run_posted(self) -> None:
        with self._lock_posted:
            posted, self._posted = self._posted, []
        for fn in posted:
            fn()


class AgentCalculation:
    """An assistant's calculation, counted by the window while it runs.

    ``window.has_running_calculation()`` is what quitting asks and what
    the gates read, and the hazard is the panel's: an edit made during
    the run is overwritten when the run applies.  The status bar says
    what is running, because the person cannot otherwise tell why the
    window refuses the assistant -- or what it is waiting for.
    """

    def __init__(self, window, verb: str):
        self.window = window
        self.message = f"AI assistant: {verb} running"
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self.window.agent_host.bridge.call(self._register)

    def stop(self) -> None:
        if self._started:
            self._started = False
            bridge = self.window.agent_host.bridge
            try:
                bridge.call(self._unregister)
            except BridgeClosed:
                # Off the count all the same, when the window next
                # turns: the calculation has stopped either way.
                bridge.post(self._unregister)

    def _register(self) -> None:
        self.window.agent_calculations.add(self)
        self.window.show_message(self.message, 0)

    def _unregister(self) -> None:
        self.window.agent_calculations.discard(self)
        bar = self.window.statusBar()
        if bar.currentMessage() == self.message:
            bar.clearMessage()

    def __enter__(self) -> AgentCalculation:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


def _served(method, gated: bool = True):
    """``method`` run whole on the GUI thread, refused first with
    ``WINDOW_BUSY`` when ``gated`` and the window is busy.

    At the door and not in ``_push``: a verb that adds to its answer
    after pushing (``recalculate_bonds`` counts the bonds again) would
    otherwise dress a refusal as a success.
    """
    names = [p for p in pyinspect.signature(method).parameters][1:]

    @functools.wraps(method)
    def verb(self, *args, **kwargs):
        def serve():
            if gated:
                busy = self._busy(method.__name__,
                                  {**dict(zip(names, args, strict=False)),
                                   **kwargs})
                if busy is not None:
                    return busy
            return method(self, *args, **kwargs)
        try:
            return self._bridge.call(serve)
        except BridgeClosed as exc:
            return _closing(method.__name__, exc)

    return verb


def _closing(verb: str, exc: BridgeClosed) -> VerbResult:
    """The refusal a stopping server gives, made off the GUI thread:
    nothing is read from the tab and nothing is logged."""
    return VerbResult(verb, False, str(exc),
                      diagnostics=[Diagnostic("WINDOW_BUSY", str(exc))])


class WindowSession(Session):
    """A :class:`~xtal.agent.Session` over one tab's document.

    The structure, path and entry are the document's, read live, so a
    Save As or a reload in the tab is what the next verb sees.  Pushes
    go through ``Document.run``; the log is the entry's, as headless.
    """

    def __init__(self, document, window):
        # Not Session.__init__: the structure, its stack and its file
        # are the document's, and there is nothing to read.
        self.document = document
        self.window = window
        self._bridge = window.agent_host.bridge
        self.log: list[dict] = []
        self._view = {}
        self._project_session = {}
        self.opened: VerbResult | None = None
        # Counts every change the tab announces -- the person's, a
        # reload's, the assistant's own.  The stack's depth is not
        # enough: a held arrow merges into the step before it and
        # an undo then an edit leave the depth where it was.
        self._revision = 0
        document.structureChanged.connect(self._changed)

    def _changed(self, _change) -> None:
        self._revision += 1

    @property
    def structure(self):
        return self.document.structure

    @property
    def path(self) -> Path | None:
        return self.document.path

    @property
    def entry(self):
        return self.document.entry

    @property
    def stack(self):
        """The tab's stack, for reading: pushes go through
        ``Document.run``, which announces them."""
        return self.document.stack

    @property
    def cell(self):
        return self._bridge.call(lambda: self.document.cell)

    def history(self) -> list[str]:
        return self._bridge.call(lambda: Session.history(self))

    def _record(self, verb, args, answer: VerbResult) -> None:
        Session._record(self, verb, args, answer)
        self._announce(verb, answer)

    def _announce(self, verb, answer: VerbResult) -> None:
        """The answer in the status bar, while the window is serving:
        the person is watching, and this is where the window says
        what it did itself.  Emitted on the GUI thread, whichever
        thread recorded it -- a calculation's answer is recorded on
        the server's."""
        server = getattr(self.window, "agent_server", None)
        if server is not None and server.running:
            said = f"{verb}: {answer.message}"
            self._bridge.post(lambda: server.verbLanded.emit(said))

    # -- the gate --------------------------------------------------------

    def _gate(self) -> str:
        """Why the window cannot take a verb now, or ``""``."""
        if self.document.is_playing:
            return ("this tab is playing a trajectory back; nothing was "
                    "changed")
        if self.window.has_running_calculation():
            return "a calculation is running in the window"
        return ""

    def _busy(self, verb, args) -> VerbResult | None:
        reason = self._gate()
        if not reason:
            return None
        return self._answer_refused(verb, args,
                                    Diagnostic("WINDOW_BUSY", reason))

    # -- the plumbing ----------------------------------------------------

    def _push(self, verb, command, message, args, notes=(),
              data=None) -> VerbResult:
        return self._bridge.call(lambda: self._land(
            verb, command, message, args, notes, data))

    def _land(self, verb, command, message, args, notes,
              data) -> VerbResult:
        before = self.n_atoms
        self.document.run(command)
        answer = VerbResult(verb, True, message, undo_label=command.label,
                            atoms_before=before, atoms_after=self.n_atoms,
                            data=dict(data or {}),
                            diagnostics=list(notes))
        self._record(verb, args, answer)
        return answer

    @_served
    def undo(self) -> VerbResult:
        before = self.n_atoms
        label = self.document.undo()
        answer = VerbResult(
            "undo", bool(label),
            f"undid {label}" if label else "nothing to undo",
            atoms_before=before, atoms_after=self.n_atoms)
        self._record("undo", {}, answer)
        return answer

    @_served
    def redo(self) -> VerbResult:
        before = self.n_atoms
        label = self.document.redo()
        answer = VerbResult(
            "redo", bool(label),
            f"redid {label}" if label else "nothing to redo",
            atoms_before=before, atoms_after=self.n_atoms)
        self._record("redo", {}, answer)
        return answer

    @_served
    def save(self, path=None) -> Path:
        """Save the tab as its project -- the person's Save, view,
        measurements and all."""
        target = self.document.save(path)
        self.window.refresh_workspace()
        self._record("save", {"path": str(target)},
                     VerbResult("save", True, f"saved {target.name}",
                                atoms_after=self.n_atoms))
        return target

    @_served
    def render(self, path, view="diagonal", size=(800, 600),
               style: str = "ball_stick", highlight=(),
               show_cell: bool = True) -> VerbResult:
        """The tab's viewport, drawn to a PNG: the person's view, in
        the tab's style and size.  ``view`` other than ``"diagonal"``
        turns the camera for the picture and back after it."""
        from xtal.agent.render import VIEWS

        path = Path(path)
        if path.suffix.lower() != ".png":
            raise ValueError(f"render writes a .png, not {path.name}")
        if isinstance(view, str) and view not in VIEWS:
            raise ValueError(f"view is one of {', '.join(VIEWS)} or a "
                             f"lattice direction [u, v, w], not {view!r}")
        args = {"path": str(path),
                "view": view if isinstance(view, str)
                else [float(x) for x in view]}
        viewport = self.window.tabs.widget(
            self.window.documents.index(self.document))
        if not hasattr(viewport, "save_image"):
            return self._answer_refused("render", args, Diagnostic(
                "RENDER_UNAVAILABLE", "this tab has no viewport to draw"))
        # Gone first, so a picture left by an earlier call is not taken
        # for this one's.
        path.unlink(missing_ok=True)
        with _turned(viewport, self.structure.lattice, view):
            viewport.save_image(path, magnification=1)
        if not path.exists():
            return self._answer_refused("render", args, Diagnostic(
                "RENDER_UNAVAILABLE", "the viewport wrote no picture"))
        n = self.n_atoms
        # The size, style and highlight asked for are the tab's own
        # here; said in the answer rather than left to be guessed.
        answer = VerbResult("render", True, f"wrote {path}",
                            atoms_before=n, atoms_after=n,
                            data={**args, "honoured": ["path", "view"]})
        self._record("render", {"path": str(path), "view": view},
                     answer)
        return answer

    # -- calculations ------------------------------------------------

    def energy(self, engine: str = "uff", **options) -> VerbResult:
        return self._calculate("energy", {"engine": engine, **options},
                               lambda over: over.energy(engine, **options))

    def run(self, action: str, **params) -> VerbResult:
        return self._calculate(action, params,
                               lambda over: over.run(action, **params))

    def _calculate(self, verb, args, compute) -> VerbResult:
        started = self._start(verb, args)
        if isinstance(started, VerbResult):
            return started
        calculation, _revision, generation, over = started
        with calculation:
            answer = compute(over)
        # Recorded by the copy's session, which is not this one; and
        # not said under a server that is not the one asked.
        if generation == self._bridge.generation:
            self._announce(verb, answer)
        return answer

    def _start(self, verb, args):
        try:
            return self._bridge.call(lambda: self._begin(verb, args))
        except BridgeClosed as exc:
            return _closing(verb, exc)

    def _begin(self, verb, args):
        """On the GUI thread, in one go so nothing slips between them:
        the gate, the calculation registered, and a session over a
        copy of the structure that logs to this one's entry -- and
        the server generation the work began under."""
        busy = self._busy(verb, args)
        if busy is not None:
            return busy
        calculation = AgentCalculation(self.window, verb)
        calculation.start()
        over = Session(self.document.structure.copy(), self.path,
                       self.entry)
        over.log = self.log
        return calculation, self._revision, self._bridge.generation, over

    def _relax(self, args, options):
        started = self._start("optimize", args)
        if isinstance(started, VerbResult):
            return started
        calculation, revision, generation, over = started
        with calculation:
            relaxed = over._relax(args, options)
        if isinstance(relaxed, VerbResult):
            return relaxed
        return _Pending(relaxed, revision, generation, over)

    def _apply_relaxation(self, pending, args) -> VerbResult:
        try:
            outcome = self._bridge.call(
                lambda: self._apply_unless_changed(pending, args),
                generation=pending.generation)
        except BridgeClosed as exc:
            # Nobody is waiting for this answer, so nothing of the tab
            # is read for it off the GUI thread.
            answer = _closing("optimize", exc)
            notes, run = self._kept(pending)
            answer.diagnostics.extend(notes)
            if run:
                answer.data["run"] = run
            return answer
        if isinstance(outcome, VerbResult):
            return outcome
        return self._not_applied(pending, args, outcome)

    def _apply_unless_changed(self, pending, args):
        """On the GUI thread, the check and the apply in one crossing:
        an edit the person made between two would be put back by the
        relaxation, with nobody told.  The answer, or the refusal's
        diagnostic."""
        refused = self._unless_changed(pending)
        if refused is not None:
            return refused
        try:
            return Session._apply_relaxation(self, pending.relaxed, args)
        except ValueError as exc:
            # The geometry no longer fits -- sites added or removed
            # behind the revision's back.  Both places it is raised
            # (measuring the move, and the command's own check) come
            # before anything is pushed.
            return Diagnostic(
                "DOCUMENT_CHANGED", f"the structure in the tab no longer "
                f"matches the relaxed one ({exc}); the result was not "
                f"applied")

    def _unless_changed(self, pending) -> Diagnostic | None:
        if self._revision != pending.revision:
            return Diagnostic(
                "DOCUMENT_CHANGED", "the structure in the tab was edited "
                "while optimize ran; the result was not applied")
        if self.document.is_playing:
            return Diagnostic(
                "WINDOW_BUSY", "the tab began playing a trajectory while "
                "optimize ran; the result was not applied")
        if self.window.has_running_calculation():
            # Started by the person while this one ran (this one has
            # stopped counting by now): it would apply over ours.
            return Diagnostic(
                "WINDOW_BUSY", "a calculation began in the window while "
                "optimize ran; the result was not applied")
        return None

    def _not_applied(self, pending, args, refused) -> VerbResult:
        """The run folder keeps the relaxed geometry -- the copy takes
        it, for ``final.cif`` -- and the answer says where."""
        notes, run = self._kept(pending)
        answer = self._answer_refused("optimize", args, refused,
                                      notes=notes)
        if run:
            answer.data["run"] = run
        return answer

    @staticmethod
    def _kept(pending) -> tuple[list, str]:
        """The relaxed geometry written to its run folder, through the
        copy; the note saying where, and the folder."""
        from xtal.ff import record as ff_record

        relaxed, over = pending.relaxed, pending.over
        over.stack.push(relaxed.command(), over)
        ff_record.close_run(relaxed.recorder, relaxed.result,
                            final=over.structure)
        if relaxed.recorder is None:
            return [], ""
        run = str(relaxed.recorder.folder.path)
        return [Diagnostic("RESULT_NOT_APPLIED", "the relaxed geometry "
                           "is in the run folder", where=run)], run


class _Pending:
    """A relaxation computed over a copy, the tab's revision when the
    copy was taken, and the server generation it began under."""

    def __init__(self, relaxed, revision, generation, over):
        self.relaxed = relaxed
        self.revision = revision
        self.generation = generation
        self.over = over


# Every other verb a session has, served whole on the GUI thread and
# gated unless it only reads: one written here would be one a new verb
# could be added without.
for _verb in VERBS:
    if (_verb in HOST_VERBS or _verb in CALCULATIONS
            or _verb in vars(WindowSession)):
        continue
    setattr(WindowSession, _verb, _served(getattr(Session, _verb),
                                          gated=_verb not in READ_ONLY))
del _verb


class _turned:
    """The camera along ``view`` for one picture, and back after.

    A stub viewport, which has no scene, is drawn as it is.
    """

    def __init__(self, viewport, lattice, view):
        self.viewport = viewport
        self.lattice = lattice
        self.view = view
        self.saved = None

    def __enter__(self):
        scene = getattr(self.viewport, "scene", None)
        if scene is None or self.view == "diagonal":
            return self
        camera = scene.renderer.GetActiveCamera()
        self.saved = (camera, camera.GetPosition(),
                      camera.GetFocalPoint(), camera.GetViewUp(),
                      camera.GetParallelScale(), camera.GetViewAngle())
        if isinstance(self.view, str):
            self.viewport.look_along_axis("abc".index(self.view))
        else:
            scene.look_along(self.lattice.to_cart(
                [float(x) for x in self.view]))
            scene.reset_camera()
        return self

    def __exit__(self, *exc) -> None:
        if self.saved is None:
            return
        camera, position, focal, up, scale, angle = self.saved
        camera.SetPosition(*position)
        camera.SetFocalPoint(*focal)
        camera.SetViewUp(*up)
        camera.SetParallelScale(scale)
        camera.SetViewAngle(angle)
        self.viewport.scene.renderer.ResetCameraClippingRange()
        self.viewport._safe_render()


class WindowHost(Host):
    """The window's tabs as the tools' sessions.

    A session is made the first time a tab is asked for and dropped
    once its tab has closed; asking twice gives the same one, which is
    how ``open`` tells an assistant a file is already open.  Every
    method does its work on the GUI thread.
    """

    #: The bridge takes one call at a time, and a calculation computes
    #: outside it, so the tools need no lock of their own: a look or a
    #: refusal is answered while a relaxation runs.
    serialises = True

    def __init__(self, window):
        if not on_gui_thread(window):
            raise RuntimeError("the agent host is made on the GUI thread")
        self.window = window
        self.bridge = Bridge(window)
        self._sessions: list[WindowSession] = []
        # The path each was opened from, as the headless host keys
        # them: an assistant opens again what it opened before.
        self._opened_from: dict[int, Path] = {}

    def current(self) -> WindowSession:
        return self.bridge.call(self._current)

    def open(self, path, workspace=None) -> WindowSession:
        return self.bridge.call(lambda: self._open(Path(path)))

    def sessions(self) -> list[WindowSession]:
        return self.bridge.call(
            lambda: [self._session(d) for d in self.window.documents])

    def switch(self, path) -> WindowSession:
        return self.bridge.call(lambda: self._switch(Path(path)))

    # -- on the GUI thread -------------------------------------------

    def _current(self) -> WindowSession:
        document = self.window.current_document()
        if document is None:
            raise LookupError(NO_SESSION)
        return self._session(document)

    def _open(self, path: Path) -> WindowSession:
        held = self._held(path)
        if held is not None:
            self._raise(held)
            return held
        if not path.exists():
            raise FileNotFoundError(f"no such file: {path}")
        document = self.window.open_path(path, report=False)
        if document is None:
            raise ValueError(self.window.statusBar().currentMessage()
                             or f"could not open {path}")
        session = self._session(document)
        self._opened_from[id(session)] = path.resolve()
        session.opened = VerbResult(
            "open", True, f"opened {document.path.name}",
            atoms_after=session.n_atoms)
        session._record("open", {"path": str(path)}, session.opened)
        return session

    def _switch(self, path: Path) -> WindowSession:
        held = self._held(path)
        if held is None:
            raise LookupError(f"{path} is not open")
        self._raise(held)
        return held

    def _raise(self, session: WindowSession) -> None:
        self.window.tabs.setCurrentIndex(
            self.window.documents.index(session.document))

    def _held(self, path: Path) -> WindowSession | None:
        """The session over ``path``: the tab the window says that file
        is (its own path, the workspace's copy, the file it came
        from), or the one an assistant opened from it."""
        document = self.window.document_for(path)
        if document is not None:
            return self._session(document)
        wanted = path.resolve()
        for session in self._live():
            if self._opened_from.get(id(session)) == wanted:
                return session
        return None

    def _session(self, document) -> WindowSession:
        for session in self._live():
            if session.document is document:
                return session
        session = WindowSession(document, self.window)
        self._sessions.append(session)
        return session

    def _live(self) -> list[WindowSession]:
        """The sessions whose tab is still open, the others dropped."""
        open_now = self.window.documents
        kept = [s for s in self._sessions
                if any(s.document is d for d in open_now)]
        for gone in self._sessions:
            if gone not in kept:
                self._opened_from.pop(id(gone), None)
        self._sessions = kept
        return kept
