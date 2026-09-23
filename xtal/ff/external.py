"""
xtal.ff.external
================
An energy engine that is somebody else's program.

DFTB+ and xTB both mean the same thing: write the geometry into a
scratch directory, launch a binary there, read an energy and forces
back.  They were written twice, 119 lines alike, including a ``_Log``
class that differed in one word of its docstring.  What they share is
here; what each keeps is its own input, its own command line and its
own reader, which is the part that is actually about the program.

A new engine of this kind subclasses :class:`ExternalCalculator`,
calls :meth:`~ExternalCalculator._prepare` and
:meth:`~ExternalCalculator._open_scratch` from its ``__init__``, and
in ``compute`` writes the geometry with :meth:`_write_geometry` and
runs its program with :meth:`_run`.
"""

from __future__ import annotations

import shutil
import tempfile
import weakref
from collections.abc import Callable
from pathlib import Path

import numpy as np

from xtal.core import p1
from xtal.ff.api import Calculator, CalculatorError, CalculatorStopped


class ProgramLog:
    """The tiny bit of :class:`xtal.workspace.RunLog` that
    :class:`~xtal.modules.process.ExternalProcess` uses.

    A calculator has no run folder -- the Force Field panel owns the
    one for the whole optimisation -- so the program's own output goes
    into the scratch directory, where a failure message can point at
    it.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._handle = self.path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        self._handle.write(f"{text}\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()


class ExternalCalculator(Calculator):
    """A calculator that runs a program over a structure's P1 cell."""

    #: Where the program's own output goes, in the scratch directory.
    log_name = "program.out"
    #: The geometry file :meth:`_write_geometry` writes, as ``.gen``.
    geometry_name = "geo.gen"
    #: The scratch directory's prefix, so one left behind by a crash
    #: says whose it was.
    scratch_prefix = "external-"

    def _prepare(self, structure, options) -> None:
        """The prologue every such engine starts with: the options,
        the P1 cell, and a refusal of a cell with nothing in it."""
        self.options = options
        self.structure = structure
        self.cell = p1.expand(structure)
        if self.cell.n_atoms == 0:
            raise CalculatorError(
                "there are no atoms to compute an energy for")
        self.symbols = tuple(self.cell.elements)
        self.warnings: list[str] = []
        self.calls = 0
        self.seconds = 0.0

    def _open_scratch(self) -> None:
        """A directory of this calculator's own for the program to run
        in.

        Cleaned when this object goes, not at interpreter exit: a long
        session doing twenty single points would otherwise keep twenty
        scratch directories of charges and outputs.
        """
        self.directory = Path(tempfile.mkdtemp(
            prefix=self.scratch_prefix))
        self._cleanup = weakref.finalize(
            self, shutil.rmtree, self.directory, True)

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    @property
    def log_path(self) -> Path:
        return self.directory / self.log_name

    def _write_geometry(self, positions, matrix) -> None:
        """These positions, in this cell, as the program's ``.gen``."""
        from xtal.core.lattice import Lattice
        from xtal.core.site import Site
        from xtal.core.spacegroup import SpaceGroup
        from xtal.core.structure import Structure
        from xtal.io.gen import gen_string

        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        matrix = np.asarray(matrix, dtype=float).reshape(3, 3)
        if len(positions) != self.n_atoms:
            raise CalculatorError(
                f"this calculator was built for {self.n_atoms} atoms "
                f"and was handed {len(positions)}")
        frac = positions @ np.linalg.inv(matrix)
        moved = Structure(
            lattice=Lattice(matrix),
            sites=[Site(symbol, f) for symbol, f
                   in zip(self.symbols, frac, strict=True)],
            space_group=SpaceGroup.p1())
        (self.directory / self.geometry_name).write_text(
            gen_string(moved), encoding="utf-8")

    def _run(self, argv: list[str], why: Callable[[object], str]):
        """Run the program once, in the scratch directory.

        Stop kills it (:class:`CalculatorStopped`) rather than waiting
        for an SCC cycle nobody wants; a failure is
        :class:`CalculatorError` with ``why(outcome)`` as the sentence,
        which is the part each program words for itself.
        """
        from xtal.modules.process import ExternalProcess

        log = ProgramLog(self.log_path)
        process = ExternalProcess(argv, cwd=self.directory, log=log)
        outcome = process.run(cancel=self.cancel)
        self.calls += 1
        self.seconds += outcome.seconds
        log.close()
        if outcome.cancelled:
            raise CalculatorStopped("stopped during an evaluation")
        if not outcome.ok:
            raise CalculatorError(why(outcome))
        return outcome
