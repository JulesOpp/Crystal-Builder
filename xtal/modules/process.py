"""
xtal.modules.process
====================
Running somebody else's binary, once, carefully.

DFTB+ and Zeo++ are both external programs, and everything that is
hard about running one is the same for both -- which is the argument
for writing this once, as part of the module registry, rather than
twice as part of two engines.  Four things are what make it hard.

**A missing binary has to be found before launching, not inside a
subprocess failure.**  ``FileNotFoundError: [Errno 2] No such file or
directory: 'dftb+'`` is a stack trace, not a sentence, and it arrives
after the run folder has been created and the log opened.  So
:class:`Program` resolves first and raises :class:`MissingProgram`,
which knows the name, where it looked and where to get it -- and the
same call answers the module registry's ``check``, so the tree can grey
the module out and say why before anybody clicks.

**The log has to be live.**  A DFTB+ run is minutes to hours, and a
log written at the end of a run that never ended is empty.  Every line
of the child's output is written and flushed as it arrives, which is
also what lets the log viewer tail it while it runs.

**Cancel has to reach the process.**  Abandoning the reading thread
leaves the binary running: still on the CPU, still writing into the
run folder, and still there when the next run starts.  So Stop
terminates, waits a moment for the program to put itself away, and
kills what is left -- and it terminates the *group*, because a program
launched through a wrapper script is a child of a child.

**The exit status has to become a sentence.**  ``returncode 1`` tells a
user nothing; the last few lines of what the program printed usually
tell them everything, so those are kept and put in the message.

stderr is merged into stdout rather than captured separately.  Two
streams into one log interleave by arrival and not by content, which
makes the error and the line that caused it end up pages apart; one
stream keeps them adjacent, which is how anybody reads a log.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from xtal.modules.registry import Availability

#: How long a terminated program is given to put itself away before it
#: is killed.  Long enough for a solver to close its output files,
#: short enough that Stop feels like a button and not a request.
GRACE_SECONDS = 5.0

#: How much of the output is kept in memory for the failure message.
#: The whole thing is in the log; this is only what the status bar and
#: the dialog quote.
TAIL_LINES = 20

WINDOWS = sys.platform == "win32"


#: Paths the caller has been told to use, by ``Program.setting``.
#:
#: This is how a preference reaches a lookup in a package that must
#: never read one.  :mod:`xtal` imports no Qt and has no idea what a
#: QSettings is; the GUI resolves its own preference and puts the
#: answer here, exactly as a shell puts one in an environment
#: variable.  Nothing in this package writes to it.
_HINTS: dict[str, str] = {}


def set_hint(setting: str, path) -> None:
    """Say where a program is, for every later lookup of it.

    An empty path forgets it rather than storing an empty string: a
    stored blank would have to be told apart from "never set" at every
    place that reads one.
    """
    if not setting:
        return
    text = str(path or "").strip()
    if text:
        _HINTS[setting] = text
    else:
        _HINTS.pop(setting, None)


def hint_for(setting: str) -> str:
    """The path set for that preference, or ``""``."""
    return _HINTS.get(setting, "") if setting else ""


def clear_hints() -> None:
    """Forget every one.  For the suite, and for a session that has
    just had its preferences reset."""
    _HINTS.clear()


class MissingProgram(RuntimeError):
    """The binary is not installed, or not where we were told.

    Carries what a user needs to fix it rather than what Python needs
    to raise it: the name, every place that was looked, and the
    setting that would say where it is.
    """

    def __init__(self, program: str, searched=(), hint: str = "",
                 url: str = ""):
        self.program = program
        self.searched = tuple(searched)
        self.hint = hint
        self.url = url
        parts = [f"{program} was not found"]
        if hint:
            parts.append(f"(looked at {hint}, which was set for it)")
        parts.append("on PATH")
        message = " ".join(parts)
        if url:
            message += f".  It is at {url}"
        super().__init__(message)


@dataclass(frozen=True)
class Program:
    """An external binary the application knows how to look for.

    Three places, in the order somebody would expect: an explicit path
    the caller was given (a preference), the environment variable that
    names it, and then PATH.
    """

    name: str                       # the executable: "dftb+"
    label: str = ""                 # "DFTB+"
    env_var: str = ""               # "XTAL_DFTB"
    url: str = ""                   # where to get it
    setting: str = ""               # the preference that names a path

    @property
    def title(self) -> str:
        return self.label or self.name

    def locate(self, hint=None) -> Path | None:
        """Where it is, or ``None``."""
        for candidate in self._candidates(hint):
            found = _executable(candidate)
            if found is not None:
                return found
        return None

    def hint(self, given=None) -> str:
        """The path this lookup should try first.

        What the caller passed, or what was set for this program's
        preference.  **Ahead of the environment variable**, which is
        the decision worth recording: a variable is what a shell sets
        and a preference is what a person set on purpose, and a
        packaged application has no shell to set the first one in.
        """
        return str(given) if given else hint_for(self.setting)

    def _candidates(self, hint=None):
        hint = self.hint(hint)
        if hint:
            yield hint
        if self.env_var and os.environ.get(self.env_var):
            yield os.environ[self.env_var]
        yield self.name

    def search(self, hint=None) -> tuple:
        """Every place that would be looked, and what is there.

        ``(source, candidate, found)`` per place, in order, where
        ``source`` is ``"preference"``, the environment variable's
        name, or ``"PATH"``.  Unlike :meth:`locate` this does not stop
        at the first answer, because it exists for the status line
        that has to say *what was tried* -- "not found, and
        XTAL_ZEOPP is not set" is the sentence that saves somebody an
        afternoon, and a bare red field is what makes them conclude
        the feature is broken.
        """
        out = []
        hint = self.hint(hint)
        if hint:
            out.append(("preference", hint, _executable(hint)))
        if self.env_var:
            value = os.environ.get(self.env_var, "")
            out.append((self.env_var, value,
                        _executable(value) if value else None))
        out.append(("PATH", self.name, _executable(self.name)))
        return tuple(out)

    def resolve(self, hint=None) -> Path:
        """Where it is, or a :class:`MissingProgram` saying where we
        looked."""
        found = self.locate(hint)
        if found is None:
            raise MissingProgram(
                self.title, searched=tuple(self._candidates(hint)),
                hint=self.hint(hint) or
                (self.env_var and os.environ.get(self.env_var, "")),
                url=self.url)
        return found

    def found(self, hint=None) -> bool:
        return self.locate(hint) is not None

    def availability(self, hint=None) -> Availability:
        """The registry's answer, for a module whose binary may be
        missing -- which is the state it will usually be in."""
        found = self.locate(hint)
        if found is not None:
            return Availability(True, str(found))
        # Every place that was named and is wrong, because a path
        # that was set and is a typo looks exactly like one that was
        # never set, and only one of the two is five seconds from
        # working.
        given = self.hint(hint)
        from_env = os.environ.get(self.env_var, "") if self.env_var \
            else ""
        parts = []
        if given:
            parts.append(f"not at {given}, which is set for it")
        if from_env:
            parts.append(f"not at {from_env}, which {self.env_var} "
                         f"names")
        elif self.env_var:
            parts.append(f"{self.env_var} is not set")
        where = f" ({'; '.join(parts)})" if parts else ""
        tail = f".  It is at {self.url}" if self.url else ""
        return Availability(
            False,
            f"{self.title} is not installed, or not on PATH{where}"
            f"{tail}")


def _executable(candidate) -> Path | None:
    """A path to something runnable, from a name or a path.

    ``shutil.which`` handles both, including the ``.exe`` a Windows
    caller will not have typed -- but it says yes to a directory on
    some versions, so the answer is checked.
    """
    text = str(candidate)
    found = shutil.which(text)
    if found is None and os.sep in text:
        path = Path(text).expanduser()
        found = str(path) if path.is_file() and \
            os.access(path, os.X_OK) else None
    if found is None:
        return None
    path = Path(found)
    return path if path.is_file() else None


# ======================================================================
#  ONE RUN OF ONE PROGRAM
# ======================================================================

@dataclass
class ProcessResult:
    """How it ended, in terms somebody can act on."""

    argv: tuple = ()
    cwd: Path | None = None
    returncode: int | None = None
    cancelled: bool = False
    lines: tuple = ()               # the tail of the output
    seconds: float = 0.0
    log_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.cancelled

    @property
    def program(self) -> str:
        return Path(self.argv[0]).name if self.argv else "the program"

    def message(self) -> str:
        """One sentence for the status bar."""
        if self.cancelled:
            return f"{self.program} was stopped"
        if self.ok:
            return f"{self.program} finished in {self.seconds:.1f} s"
        return (f"{self.program} exited with status "
                f"{self.returncode}")

    def detail(self) -> str:
        """The message, and the last thing the program printed.

        Which is nearly always what actually went wrong, and nearly
        never the exit status.
        """
        parts = [self.message()]
        if not self.ok and self.lines:
            parts.append("its last output was:")
            parts.extend(f"    {line}" for line in self.lines)
        if self.log_path is not None:
            parts.append(f"the whole log is in {self.log_path.name}")
        return "\n".join(parts)


class ExternalProcess:
    """One child process, streamed into a log and stoppable.

    Not reusable: one instance runs one program once, so that
    ``returncode`` and ``cancelled`` mean something unambiguous
    afterwards.
    """

    def __init__(self, argv, cwd, log=None, on_line=None, env=None,
                 grace: float = GRACE_SECONDS,
                 tail: int = TAIL_LINES):
        if not argv:
            raise ValueError("a process needs a program to run")
        self.argv = [str(a) for a in argv]
        self.cwd = Path(cwd)
        self.log = log
        self.on_line = on_line
        self.env = env
        self.grace = float(grace)
        self._tail: deque = deque(maxlen=int(tail))
        self._process: subprocess.Popen | None = None
        self._cancelled = False
        self._returncode: int | None = None

    # -- before anything is launched -----------------------------------

    def resolve(self, program: Program | None = None, hint=None) -> str:
        """Find the binary, and say so before the run folder is
        touched."""
        if program is not None:
            return str(program.resolve(hint))
        found = _executable(self.argv[0])
        if found is None:
            raise MissingProgram(self.argv[0],
                                 searched=(self.argv[0],))
        return str(found)

    # -- the run -------------------------------------------------------

    def run(self, cancel=None, program: Program | None = None,
            hint=None) -> ProcessResult:
        """Launch, stream until it ends, and say how it ended.

        Blocking, and meant to be: it is called on a worker thread,
        and the thing that makes it stoppable is ``cancel`` rather
        than a timeout.
        """
        self.argv[0] = self.resolve(program, hint)
        self.cwd.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        self._write(f"$ {_command_line(self.argv)}")
        self._write(f"  in {self.cwd}")
        if cancel is not None:
            cancel.when_cancelled(self.cancel)
            if cancel.requested:
                # Stop was pressed between opening the run folder and
                # getting here.  Launching now and killing it a
                # millisecond later would still have launched it --
                # and a program with a start-up cost would have paid
                # it -- so the honest answer is not to start.
                cancel.forget(self.cancel)
                self._cancelled = True
                result = ProcessResult(
                    argv=tuple(self.argv), cwd=self.cwd,
                    cancelled=True, seconds=0.0,
                    log_path=getattr(self.log, "path", None))
                self._write(result.message())
                return result
        try:
            self._process = subprocess.Popen(       # noqa: S603
                self.argv, cwd=str(self.cwd), env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True, bufsize=1, errors="replace",
                **_isolation())
        except OSError as exc:
            # The binary was there when we resolved it and is not
            # runnable now -- a broken symlink, a wrong architecture,
            # a permission bit.
            if cancel is not None:
                cancel.forget(self.cancel)
            raise MissingProgram(
                Path(self.argv[0]).name,
                searched=(self.argv[0],)) from exc
        try:
            # And once more, for the gap between that check and the
            # process existing: the callback fired into a None and had
            # nothing to terminate.
            if cancel is not None and cancel.requested:
                self.cancel()
            self._stream()
            self._returncode = self._process.wait()
        finally:
            if cancel is not None:
                cancel.forget(self.cancel)
            self._close()
        result = ProcessResult(
            argv=tuple(self.argv), cwd=self.cwd,
            returncode=self._returncode, cancelled=self._cancelled,
            lines=tuple(self._tail),
            seconds=time.monotonic() - started,
            log_path=getattr(self.log, "path", None))
        self._write(result.message())
        return result

    def _stream(self) -> None:
        """Every line the child prints, as it prints it.

        Iterating the pipe blocks until a line arrives or the pipe
        closes -- and cancelling closes it, because cancelling kills
        the writer.  That is why Stop does not need this loop to poll
        anything.
        """
        stream = self._process.stdout
        if stream is None:                          # pragma: no cover
            return
        for line in stream:
            text = line.rstrip("\n")
            self._tail.append(text)
            self._write(text)

    def _write(self, text: str) -> None:
        if self.log is not None:
            self.log.write(text)
        if self.on_line is not None:
            self.on_line(text)

    def _close(self) -> None:
        stream = getattr(self._process, "stdout", None)
        if stream is not None and not stream.closed:
            stream.close()

    # -- stopping it ---------------------------------------------------

    def cancel(self) -> None:
        """Terminate the process group, then kill what survives.

        Called from the GUI thread while the worker sits in
        :meth:`_stream`; killing the writer is what wakes that loop
        up.  Safe before the process exists and after it has gone.
        """
        self._cancelled = True
        process = self._process
        if process is None or process.poll() is not None:
            return
        _terminate(process)
        try:
            process.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            _kill(process)

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def running(self) -> bool:
        return (self._process is not None
                and self._process.poll() is None)


# ======================================================================
#  PLATFORM
# ======================================================================

def _isolation() -> dict:
    """Put the child in a group of its own, so the whole tree can be
    signalled.

    A program launched through a wrapper script is a child of a child,
    and terminating only what we launched leaves the one doing the
    work behind.
    """
    if WINDOWS:                                     # pragma: no cover
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate(process) -> None:
    if WINDOWS:                                     # pragma: no cover
        _quietly(process.terminate)
        return
    _quietly(lambda: os.killpg(os.getpgid(process.pid),
                               signal.SIGTERM))


def _kill(process) -> None:
    if WINDOWS:                                     # pragma: no cover
        _quietly(process.kill)
        return
    _quietly(lambda: os.killpg(os.getpgid(process.pid),
                              signal.SIGKILL))


def _quietly(action) -> None:
    """A process that exited between the poll and the signal is not an
    error -- it is the outcome we wanted."""
    try:
        action()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _command_line(argv) -> str:
    """The command as somebody would retype it, for the top of the
    log.  A run folder with the exact command in it is a run that can
    be reproduced by hand."""
    import shlex
    if WINDOWS:                                     # pragma: no cover
        return subprocess.list2cmdline(argv)
    return shlex.join(str(a) for a in argv)
