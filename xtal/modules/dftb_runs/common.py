"""
xtal.modules.dftb_runs.common
=============================
What every DFTB+ run shares: the options, a folder, one invocation.
"""

from __future__ import annotations

import contextlib
import tempfile
from dataclasses import fields
from pathlib import Path

from xtal.core import p1
from xtal.ff.dftb import hsd
from xtal.ff.dftb.calculator import PROGRAM, DFTBOptions
from xtal.io.gen import gen_string
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess

GEOMETRY_NAME = "geo.gen"
INPUT_NAME = "dftb_in.hsd"


class RunFailed(Exception):
    """A run that cannot go on, carrying the result that says why."""

    def __init__(self, result: JobResult):
        super().__init__(result.message)
        self.result = result


def options_of(job) -> DFTBOptions:
    """The panel's Hamiltonian, from ``job.params["hamiltonian"]``.

    Unknown keys are dropped: a saved set of values outlives the field
    it was saved for, and refusing to run over one would be a run that
    cannot be repeated from its own record.
    """
    given = dict(job.param("hamiltonian", {}) or {})
    known = {f.name for f in fields(DFTBOptions)}
    return DFTBOptions(**{k: v for k, v in given.items() if k in known})


def symbols_of(structure) -> list[str]:
    return list(p1.expand(structure).elements)


def refuse(structure, options) -> None:
    """Raise :class:`RunFailed` before anything is written, when DFTB+
    or a parameter file is missing."""
    available = PROGRAM.availability()
    if not available:
        raise RunFailed(JobResult.failure(available.reason))
    refusal = hsd.check(symbols_of(structure),
                        options.parameter_directory)
    if refusal:
        raise RunFailed(JobResult.failure(refusal))


@contextlib.contextmanager
def folder(job):
    """The run folder, or a scratch one that goes away afterwards when
    there is no workspace -- the run still answers, and says nothing
    was kept."""
    if job.path is not None:
        job.path.mkdir(parents=True, exist_ok=True)
        yield job.path
        return
    with tempfile.TemporaryDirectory(prefix="xtal-dftb-") as scratch:
        yield Path(scratch)


def mesh(structure, options, spacing: float | None = None) -> tuple:
    spacing = options.k_spacing if spacing is None else spacing
    if spacing <= 0:
        return (1, 1, 1)
    return hsd.mesh_for(structure.lattice, spacing)


def invoke(job, directory: Path, structure, text: str,
           on_line=None) -> None:
    """Write ``geo.gen`` and ``dftb_in.hsd`` into ``directory`` and run
    DFTB+ there.  Raises :class:`RunFailed` when it did not finish."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / GEOMETRY_NAME).write_text(gen_string(structure),
                                           encoding="utf-8")
    (directory / INPUT_NAME).write_text(text, encoding="utf-8")
    process = ExternalProcess([PROGRAM.name], cwd=directory,
                              log=job.log, on_line=on_line)
    result = process.run(cancel=job.cancel, program=PROGRAM)
    if result.cancelled:
        raise RunFailed(JobResult.stopped("DFTB+ was stopped"))
    if not result.ok:
        raise RunFailed(JobResult.failure(
            f"DFTB+ exited with status {result.returncode}",
            detail=result.detail()))


def read(directory: Path, name: str) -> str:
    path = directory / name
    if not path.is_file():
        raise RunFailed(JobResult.failure(
            f"DFTB+ finished without writing {name}"))
    return path.read_text(encoding="utf-8", errors="replace")


def guarded(run):
    """A run callable whose :class:`RunFailed` is its result."""
    def wrapper(job):
        try:
            return run(job)
        except RunFailed as stop:
            return stop.result
    wrapper.__name__ = run.__name__
    wrapper.__doc__ = run.__doc__
    return wrapper
