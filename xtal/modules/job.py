"""
xtal.modules.job
================
What a module is handed when it runs, and what it hands back.

A module's ``run`` callable gets one argument.  That is deliberate:
every extra positional argument is a signature every future module has
to match, and a :class:`Job` can grow a field without breaking one that
was written before the field existed.

The interesting part is cancellation, because there are two very
different things to cancel and only one button.

An **in-process** job -- a loop, a solver, a numpy grid -- can only be
stopped by asking it to look.  It polls :attr:`Cancellation.requested`
between units of work, and sleeps with :meth:`Cancellation.wait` so
that a job resting for ten seconds still stops in milliseconds.

An **external process** cannot be asked anything.  Abandoning the
thread that is reading its output leaves the binary running: it keeps
the CPU, keeps writing into the run folder, and is still there when
the user starts the next run.  So cancelling has to reach the process
itself, and :meth:`Cancellation.when_cancelled` is how it does --
:class:`~xtal.modules.process.ExternalProcess` registers its
terminator, the GUI thread sets the cancellation, and the binary gets
a signal rather than being forgotten about.

One :class:`Cancellation` covers both, so the Stop button does not
have to know which kind of job it is stopping.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xtal.core import elements as el


class Cancelled(Exception):
    """Raised by :meth:`Cancellation.check` when Stop was pressed.

    A module may raise it, return a cancelled result, or simply stop
    early -- the runner treats all three the same.  Cancelling is not
    a failure and never reaches the user as one.
    """


class Cancellation:
    """Set from the GUI thread; noticed on the worker's.

    Setting it twice is not an error and neither is registering a
    callback after it has already been set -- that callback fires
    immediately, which is what makes a race between "Stop" and "the
    process has just started" harmless in either order.
    """

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        with self._lock:
            already = self._event.is_set()
            self._event.set()
            callbacks = list(self._callbacks)
        if already:
            return
        for callback in callbacks:
            _safely(callback)

    def when_cancelled(self, callback: Callable[[], None]) -> None:
        """Do this the moment Stop is pressed -- or now, if it has
        been already."""
        with self._lock:
            if not self._event.is_set():
                self._callbacks.append(callback)
                return
        _safely(callback)

    def forget(self, callback: Callable[[], None]) -> None:
        """Stop calling a callback -- a process that has finished has
        nothing left to terminate."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def wait(self, seconds: float) -> bool:
        """Sleep, and return True if Stop was pressed while we did."""
        return self._event.wait(max(0.0, float(seconds)))

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled("stopped")

    def __bool__(self) -> bool:                     # pragma: no cover
        return self._event.is_set()


def _safely(callback) -> None:
    """A callback that raises must not stop the others firing: one of
    them is the thing that kills the subprocess."""
    try:
        callback()
    except Exception:                               # noqa: BLE001, S110
        pass


# ======================================================================
#  THE JOB
# ======================================================================

@dataclass
class Job:
    """One run of one action, and everything it is allowed to touch.

    **The structure is the job's own copy.**  The window keeps
    redrawing the one the user can see while this one is read, cached
    on and sometimes moved; sharing them between the two threads would
    be a data race in the most literal sense.

    ``folder`` is ``None`` when there is no workspace open, and every
    method here is a no-op in that case.  That is not an error state:
    a structure with no workspace still runs and simply leaves nothing
    behind, which is what this application did before there was
    anywhere to leave anything.
    """

    structure: Any = None
    params: dict = field(default_factory=dict)
    folder: Any = None                  # xtal.workspace.RunFolder | None
    cancel: Cancellation = field(default_factory=Cancellation)
    #: A line for the status bar.  Called on the worker thread, so the
    #: shell's implementation must be a signal emission and nothing
    #: heavier.
    on_progress: Callable[[str], None] | None = None
    label: str = ""                     # "stub: count", for messages

    # -- where it writes -----------------------------------------------

    @property
    def log(self):
        """The run log, or ``None`` with no workspace open."""
        return self.folder.log() if self.folder is not None else None

    @property
    def path(self) -> Path | None:
        return self.folder.path if self.folder is not None else None

    def file(self, name: str) -> Path:
        """A path inside the run folder, for an artefact of its own.

        Raises with no workspace, because a module that has got as far
        as naming an output file has to be told there is nowhere to
        put it rather than writing it into the current directory.
        """
        if self.folder is None:
            raise RuntimeError(
                "there is no workspace open, so this run has nowhere "
                "to write its files")
        return self.folder.path / name

    # -- what it says --------------------------------------------------

    def say(self, text: str) -> None:
        """One line, into the log and onto the status bar.

        Both or neither: a module should not have to write the same
        sentence twice, and a line that reached only the status bar
        lasted four seconds and is gone.
        """
        log = self.log
        if log is not None:
            log.write(text)
        if self.on_progress is not None:
            self.on_progress(text)

    def note(self, text: str) -> None:
        """Into the log only -- for the detail a status bar cannot
        carry."""
        log = self.log
        if log is not None:
            log.write(text)

    # -- cancellation, forwarded so a module needs one object ----------

    @property
    def cancelled(self) -> bool:
        return self.cancel.requested

    def sleep(self, seconds: float) -> bool:
        """Rest, and answer whether Stop was pressed while resting."""
        return self.cancel.wait(seconds)

    def check(self) -> None:
        self.cancel.check()

    def param(self, name: str, default=None):
        return self.params.get(name, default)


# ======================================================================
#  THE RESULT
# ======================================================================

@dataclass
class JobResult:
    """What a run produced, kept as small as three modules can justify.

    A message the status bar can show, optionally a geometry to adopt,
    the flags that say how it ended, and -- since Zeo++, which was the
    first module with an answer a sentence could not carry -- a
    :class:`~xtal.modules.report.Report` of the tables and histograms
    worth looking at.  See that module for why the shape is as small
    as it is.
    """

    message: str = ""
    ok: bool = True
    cancelled: bool = False
    #: A new geometry for the document to adopt, as one undoable
    #: command.  ``None`` from anything that only measured.
    structure: Any = None
    #: Anything worth naming that the run wrote.  The tree reads the
    #: folder rather than this, so it is for messages, not for the
    #: tree.
    artifacts: tuple = ()
    detail: str = ""
    #: What to show: tables and histograms, in the order to show them.
    #: ``None`` from a module whose whole answer is its message, which
    #: is most of them.
    report: Any = None

    @classmethod
    def stopped(cls, message: str = "stopped") -> JobResult:
        return cls(message=message, ok=True, cancelled=True)

    @classmethod
    def failure(cls, message: str, detail: str = "") -> JobResult:
        return cls(message=message, ok=False, detail=detail)

    def summary(self) -> str:
        return self.message or ("stopped" if self.cancelled
                                else "finished")


# ======================================================================
#  WHAT A MODULE IS NOT HANDED
# ======================================================================
#
# A dummy atom is a marker and not chemistry -- see
# :data:`xtal.core.elements.DUMMY_ELEMENTS`.  It has no force-field
# type, no radius a porosity code would recognise, and no business in
# a pore-size histogram; handing one to an external binary is how
# Zeo++ comes back with an error on a structure the user considers
# perfectly ordinary.  So the markers are held back at the door, which
# is here, rather than in each module -- a module written next year
# would have to remember, and would not.


def without_dummies(structure):
    """``(structure, held)`` -- what a module is handed, and what was
    kept back from it.

    ``held`` is what :func:`restore_dummies` needs to put them back,
    and is ``None`` when there were none -- in which case the
    structure comes back untouched rather than copied, because that is
    every run on every structure anybody has ever opened.
    """
    dummies = [i for i, site in enumerate(structure.sites)
               if el.is_dummy(site.element)]
    if not dummies:
        return structure, None
    clean = structure.copy()
    held = (tuple((i, clean.sites[i].copy()) for i in dummies),
            list(clean.bonds), len(clean.sites) - len(dummies))
    clean.remove_sites(dummies)
    return clean, held


def restore_dummies(structure, held):
    """Put the markers back into a structure a module handed back.

    The sites go in at the indices they had and the bond list that
    named them is restored whole -- the same move
    ``DeleteSites.undo`` makes, and for the same reason: taking a site
    out renumbers every bond after it, so putting the site back is not
    enough on its own.  A user-drawn bond to a dummy, and a net edge
    to one, both survive the round trip because of it.

    Only when the module gave back the same atoms it was given, which
    is the only case this can be right about.  A module that returned
    a different structure -- a supercell, a framework built from
    nothing -- did not return one the old markers have positions in,
    and it comes back unchanged with ``False`` to say so.
    """
    if held is None:
        return structure, True
    sites, bonds, expected = held
    if len(structure.sites) != expected:
        return structure, False
    for index, site in sites:                       # ascending
        structure.sites.insert(index, site.copy())
    structure.set_bonds(bonds)
    return structure, True
