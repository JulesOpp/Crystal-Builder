"""
xtalapp.feedback
================
Help ▸ Send Feedback: a report composed here, sent by the person's own
mail client.

Nothing leaves the application on its own.  The report is a
``mailto:`` link the desktop hands to whatever mail client it has, so
there is no server, no account and no credential anywhere in it, and
the person presses Send or does not.

**A link carries no attachment.**  ``mailto:`` has no field for one,
and Apple Mail, Outlook and Gmail all ignore the unofficial
``attach=``.  So the log goes *in the body*: its last lines, with the
home folder written ``~`` because the log names every file opened
and most of those paths contain the account's name.

**A link has a length.**  On Windows the hand-off to Outlook cuts a
``mailto:`` near 2 000 characters, and what arrives is a body that
stops mid-line with nothing saying so.  The log is trimmed from its
oldest line until the link fits :data:`URL_BUDGET`, then a crash's
traceback from its outermost frame; what the person wrote is never
trimmed.  The dialog shows the body exactly as it will arrive, and
offers it on the clipboard for when it still does not fit.

No Qt here, so all of it is tested headless; the dialog is
:mod:`xtalapp.dialogs.feedback`.
"""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import quote

ADDRESS = "juliuso@princeton.edu"
APP = "Crystal Builder"

BUG = "Bug"
FEATURE = "Feature suggestion"
UI = "UI suggestion"
KINDS = (BUG, FEATURE, UI)

#: How long the whole ``mailto:`` link may be.  Windows' is where
#: Outlook truncates; elsewhere Apple Mail and xdg-email take far
#: more, and 8 000 keeps a body short enough to read.
URL_BUDGET = {"win32": 1900}
DEFAULT_BUDGET = 8000

#: Lines of the log offered before any trimming.
LOG_LINES = 150
#: Read no more than this off the end of a log that may be a megabyte.
_TAIL_BYTES = 64 * 1024
#: A hard crash's stack is from an earlier session -- faulthandler
#: writes it as the process dies -- so a recent one is worth sending.
FAULT_AGE = 7 * 24 * 3600
SUBJECT_LENGTH = 60


@dataclass(frozen=True)
class Report:
    subject: str
    body: str
    url: str
    #: Log and traceback lines left out so the link fits.
    dropped: int = 0
    #: True when it is over budget even with nothing left to trim.
    too_long: bool = False

    def as_text(self) -> str:
        """For the clipboard: what to paste into an email by hand."""
        return f"To: {ADDRESS}\nSubject: {self.subject}\n\n{self.body}"


def budget(platform_name: str | None = None) -> int:
    return URL_BUDGET.get(platform_name or sys.platform, DEFAULT_BUDGET)


def _version_of(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not installed"


def environment() -> str:
    """The lines that say which build, on what, without being asked."""
    from xtal import __version__
    build = ("packaged build" if getattr(sys, "frozen", False)
             else "from source")
    return "\n".join([
        f"{APP} {__version__} ({build})",
        f"Python {platform.python_version()}, "
        f"PySide6 {_version_of('PySide6')}, VTK {_version_of('vtk')}",
        f"{platform.platform()} ({platform.machine()})",
    ])


def _home_as_tilde(text: str) -> str:
    home = str(Path.home())
    return text.replace(home, "~") if home not in ("", "/") else text


def _tail_text(path: Path) -> str:
    with open(path, "rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - _TAIL_BYTES))
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    if size > _TAIL_BYTES:
        # The first line is whatever the seek landed in the middle of.
        text = text.partition("\n")[2]
    return text


def log_tail(path, lines: int = LOG_LINES) -> list[str]:
    """The last ``lines`` lines of ``path``, home folder hidden;
    empty when there is no such file."""
    if path is None or not Path(path).is_file():
        return []
    text = _home_as_tilde(_tail_text(Path(path)))
    return text.splitlines()[-lines:]


def last_fault(path, now: float | None = None) -> list[str]:
    """The last stack ``faulthandler`` wrote to ``path``, if recent.

    Each crash appends a block beginning ``Fatal Python error`` (or
    ``Timeout`` for a hang's dump), so the last such line is where
    the most recent one starts -- ``Current thread`` is inside one.
    """
    if path is None or not Path(path).is_file():
        return []
    path = Path(path)
    now = time.time() if now is None else now
    if now - path.stat().st_mtime > FAULT_AGE:
        return []
    lines = _home_as_tilde(_tail_text(path)).splitlines()
    starts = [i for i, line in enumerate(lines)
              if line.startswith(("Fatal Python error", "Timeout ("))]
    return lines[starts[-1]:] if starts else []


def subject(kind: str, text: str) -> str:
    first = next((line.strip() for line in text.splitlines()
                  if line.strip()), "")
    line = f"[{APP}] {kind}" + (f": {first}" if first else "")
    if len(line) > SUBJECT_LENGTH:
        line = line[:SUBJECT_LENGTH - 3].rstrip() + "..."
    return line


def mailto(subject_line: str, body: str) -> str:
    return (f"mailto:{ADDRESS}?subject={quote(subject_line, safe='')}"
            f"&body={quote(body, safe='')}")


def _body(text, kind, env, traceback_lines, log_lines, fault_lines,
          log_note) -> str:
    parts = [text.strip() or "(nothing written)", "",
             f"-- {kind} --", env]
    if traceback_lines:
        parts += ["", "-- Error --", *traceback_lines]
    if fault_lines:
        parts += ["", "-- Last hard crash (faults.log) --", *fault_lines]
    if log_note:
        parts += ["", log_note]
    if log_lines:
        parts += ["", f"-- Last {len(log_lines)} lines of the log --",
                  *log_lines]
    return "\n".join(parts) + "\n"


def compose(kind: str, text: str, *, include_log: bool = False,
            log=None, faults=None, details: str = "",
            limit: int | None = None, env: str | None = None) -> Report:
    """The report, trimmed to fit ``limit`` (the platform's budget).

    ``log`` and ``faults`` are paths, ``None`` when nothing is being
    logged; ``details`` is a crash's traceback.  Trimmed in this
    order: the log's oldest line, the hard crash's outermost frame,
    the traceback's outermost frame -- its first line and the last,
    which names the exception, are kept.
    """
    limit = budget() if limit is None else limit
    env = environment() if env is None else env
    subject_line = subject(kind, text)
    log_lines, fault_lines, log_note = [], [], ""
    if include_log:
        if log is None:
            log_note = ("(No log: this window was not started by the "
                        "application.)")
        else:
            log_lines = log_tail(log)
            fault_lines = last_fault(faults)
    tb_lines = _home_as_tilde(details.strip()).splitlines()

    dropped = 0

    def build():
        body = _body(text, kind, env, tb_lines, log_lines, fault_lines,
                     log_note)
        return body, mailto(subject_line, body)

    body, url = build()
    # (lines, which to drop, how many to keep).  faulthandler writes
    # the innermost call first and Python's traceback last, so the
    # outermost frame is at opposite ends; the traceback keeps its
    # header and the line naming the exception.  At most a few
    # hundred lines, so one at a time is cheaper than being clever.
    for lines, at, keep in ((log_lines, 0, 0), (fault_lines, -1, 1),
                            (tb_lines, 1, 2)):
        while len(url) > limit and len(lines) > keep:
            del lines[at]
            dropped += 1
            body, url = build()
    return Report(subject_line, body, url, dropped,
                  too_long=len(url) > limit)
