"""
xtal.modules.probe
==================
Ask a program whether it runs, and read its answer the way that
program gives one.

"Found at /opt/anaconda3/bin/dftb+" says a file is there.  It does not
say the file runs: a binary built for the other architecture, a
conda environment whose libraries moved, a Blender whose add-on
broke -- each is found, and each fails the first time a module is
started, with a traceback about a missing ``.dylib``.  Running the
thing for a moment is the only way to know, and Preferences > Engines
has a Test button per row that does.

**No two programs are asked the same way**, which is why this is a
table and not ``--version``.  Measured on the programs this
application runs:

* ``tblite --version`` and ``xtb --version`` exit 0 at once.
* ``dftb+``, ``waveplot`` and ``modes`` take no ``--version``.  Run in
  an empty directory each prints its banner -- ``DFTB+ release 24.1``,
  ``DFTB+ (WAVEPLOT 0.3)``, ``DFTB+ (MODES 0.03)`` -- and then **exits
  1**, because there is no input file.  The banner is the answer; the
  exit code is not.  The empty directory is so that a ``dftb_in.hsd``
  lying in the working directory is never run by a Test button.
* ``network`` with no arguments prints its usage and exits 0.
* ``Blender --version`` exits 0 in about **three seconds**, which is
  why a probe has a timeout of its own and why the dialog runs one
  without waiting for it.
* A Python package is an ``import`` in a fresh interpreter (a third of
  a second for RDKit and matplotlib), so that a broken package cannot
  take the application down with it.  A frozen build has no
  interpreter to hand that line to, so it is asked of the application
  itself: :data:`IMPORT_FLAG`.

Nothing here imports Qt.  :func:`run` is the synchronous version, for
tests and scripts; the dialog starts the same argv with ``QProcess``
and hands what came back to :func:`summarise`.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

#: The flag a frozen build answers with one import and its version.
#: See :func:`xtalapp.selftest.import_one`.
IMPORT_FLAG = "--selftest-import"

#: How long a probe may take before it is called unanswered.  Blender
#: took 3.2 s on the machine this was measured on, so its own is more.
DEFAULT_TIMEOUT = 5.0
BLENDER_TIMEOUT = 15.0

#: The line every program in the DFTB+ distribution opens with: the
#: engine names its release, and each tool names itself and a version.
DFTB_BANNER = re.compile(r"DFTB\+ (?:release \S+|\([A-Z]+ [\d.]+\))")

#: How many lines of output are shown under a Test button.
SHOWN_LINES = 2


def _exits_zero(code: int, _output: str) -> bool:
    return code == 0


def _dftb_banner(_code: int, output: str) -> bool:
    return DFTB_BANNER.search(output) is not None


def _network_usage(code: int, output: str) -> bool:
    return code == 0 and "invocation syntax" in output


def _blender_version(code: int, output: str) -> bool:
    return code == 0 and "Blender" in output


@dataclass(frozen=True)
class Probe:
    """One way of asking one program whether it runs."""

    argv: tuple
    #: Whether ``(exit code, output)`` is the answer of a program that
    #: runs.
    ok: Callable[[int, str], bool] = _exits_zero
    #: Run in a new empty directory rather than wherever we are.
    empty_cwd: bool = False
    timeout: float = DEFAULT_TIMEOUT
    #: Picks the line worth showing out of the output, when there is
    #: one line that says it better than the first two do.
    headline: re.Pattern | None = field(default=None)

    @property
    def name(self) -> str:
        return Path(str(self.argv[0])).name


def _program_argv(key: str, path) -> Probe | None:
    path = str(path)
    if key in ("tools/tblite", "tools/xtb"):
        return Probe((path, "--version"))
    if key in ("tools/dftb", "tools/waveplot", "tools/modes"):
        return Probe((path,), ok=_dftb_banner, empty_cwd=True,
                     headline=DFTB_BANNER)
    if key == "tools/zeopp":
        return Probe((path,), ok=_network_usage)
    if key == "tools/blender":
        return Probe((path, "--version"), ok=_blender_version,
                     timeout=BLENDER_TIMEOUT)
    return None


def probe_for(key: str, path) -> Probe | None:
    """How to ask the program a preference names, found at ``path``.

    ``None`` for a preference that is not a program -- a folder of
    parameters or of building blocks has nothing to run.
    """
    return _program_argv(key, path)


def probe_for_package(package: str, frozen: bool = False,
                      executable: str | None = None,
                      timeout: float = 0.0, prepend=()) -> Probe:
    """How to ask whether a Python package imports.

    In a fresh interpreter, never this one: a package whose compiled
    half is broken can abort the process that imports it, and the
    process must not be the application.  A frozen build is asked
    through its own executable, since ``sys.executable`` *is* the
    application there and takes no ``-c``.

    ``package`` may be a module inside one (``mace.calculators``),
    where importing the top alone would prove nothing; the version
    printed is the top's, since a submodule has none.

    ``prepend`` is what the application put ahead of the interpreter's
    own import path -- its packages folder -- so that the fresh
    interpreter finds the copy the application would load, and not
    another one or none.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", package):
        raise ValueError(f"not a package name: {package!r}")
    executable = executable or sys.executable
    timeout = timeout or DEFAULT_TIMEOUT
    if frozen:
        return Probe((executable, IMPORT_FLAG, package),
                     timeout=timeout)
    top = package.split(".")[0]
    line = (f"import {package}; import {top}; "
            f"print({top!r}, getattr({top}, '__version__', ''))")
    if prepend:
        line = f"import sys; sys.path[:0] = {list(map(str, prepend))!r}; " \
            + line
    # The line this prints, found wherever it is: torch-based packages
    # warn on import, and the first two lines were a UserWarning about
    # ``torch.load`` where the version should have been.
    return Probe((executable, "-c", line), timeout=timeout,
                 headline=re.compile(rf"^{re.escape(top)} .*$", re.M))


# -- reading the answer ------------------------------------------------

def useful_lines(output: str) -> list[str]:
    """The lines that say something, without a banner's box drawing.

    DFTB+ frames its banner in ``|`` and ``=``, and the first two lines
    of its output are a rule and an empty bar.
    """
    lines = []
    for raw in output.splitlines():
        line = raw.strip().lstrip("|").strip()
        if line and not re.fullmatch(r"[=\-_*|+ ]+", line):
            lines.append(line)
    return lines


def summarise(probe: Probe, code: int | None, output: str,
              timed_out: bool = False,
              error: str = "") -> tuple[bool, str]:
    """Whether the program ran, and what to show under its button.

    ``code`` is ``None`` for a program that never started, and
    ``error`` then says why.
    """
    if timed_out:
        return False, (f"{probe.name} did not answer within "
                       f"{probe.timeout:g} s, so it was stopped.")
    if code is None:
        return False, f"{probe.name} could not be started: {error}"
    lines = useful_lines(output)
    if probe.headline is not None:
        found = probe.headline.search(output)
        if found is not None:
            lines = [found.group(0)]
    shown = "\n".join(lines[:SHOWN_LINES])
    if probe.ok(code, output):
        return True, shown or f"{probe.name} ran, and printed nothing."
    if "Traceback (most recent call last):" in lines:
        # A Python failure says what went wrong on its last line, and
        # its first two are the word Traceback and a file name.
        shown = lines[-1]
    said = f"\n{shown}" if shown else "  It printed nothing."
    return False, (f"{probe.name} ran but did not answer the way it "
                   f"should (exit code {code}).{said}")


def run(probe: Probe) -> tuple[bool, str]:
    """Ask, and wait for the answer.  For tests and scripts; a dialog
    must not block on a program that takes seconds."""
    with tempfile.TemporaryDirectory(prefix="xtal-probe-") as empty:
        try:
            done = subprocess.run(
                [str(a) for a in probe.argv],
                cwd=empty if probe.empty_cwd else None,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=probe.timeout,
                check=False)
        except subprocess.TimeoutExpired:
            return summarise(probe, None, "", timed_out=True)
        except FileNotFoundError:
            return summarise(probe, None, "",
                             error=f"{probe.argv[0]} was not found")
        except OSError as exc:
            return summarise(probe, None, "", error=str(exc))
    output = done.stdout.decode("utf-8", errors="replace")
    return summarise(probe, done.returncode, output)
