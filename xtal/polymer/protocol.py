"""
xtal.polymer.protocol
=====================
How a packed model would be equilibrated, held as data, and the seam
an equilibrator plugs into.

**Nothing here runs.**  The builder makes a packed starting model and
says so (:mod:`xtal.polymer.build`); relaxing the chains at their own
scale is molecular dynamics, and neither an external LAMMPS module nor
an in-process integrator exists yet.  What does exist is the
question's shape, so that whichever arrives first answers it and
nothing upstream changes: a :class:`Protocol` of stages, and an
:class:`Equilibrator` that runs one over a structure with an engine.

**The 21-step scheme is a table, not a procedure.**  Larsen, Lin and
Colina (*Macromolecules* 2011, 44, 6944) compress and decompress a
packed glass by alternating hot NVT, cool NVT and NPT at fractions of
a maximum pressure, finishing with a long NPT at the target.  Its
pressures are written as fractions of ``p_max`` and its temperatures
as ``t_max`` or ``t_final``, because those three numbers are what a
user changes (PIMs are often run at a lower ``t_max``) and the
pattern is what makes it the 21-step.  Durations are times, not step
counts: the step is the engine's to choose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol as _Interface

#: The ensembles a stage can ask for.
NVT, NPT = "NVT", "NPT"


@dataclass(frozen=True)
class Stage:
    """One stage: an ensemble at a temperature, and a pressure for
    NPT, held for a time."""

    ensemble: str
    temperature: float              # K
    duration: float                 # ps
    pressure: float | None = None   # bar; NPT only

    def __post_init__(self):
        if self.ensemble not in (NVT, NPT):
            raise ValueError(f"no ensemble {self.ensemble!r}; a stage "
                             f"is {NVT} or {NPT}")
        if (self.pressure is None) != (self.ensemble == NVT):
            raise ValueError("an NPT stage needs a pressure and an NVT "
                             "stage has none")
        if self.temperature <= 0 or self.duration <= 0:
            raise ValueError("a stage needs a temperature and a "
                             "duration above zero")


@dataclass(frozen=True)
class Protocol:
    """Stages in order, with a name to report them by."""

    name: str
    stages: tuple[Stage, ...]

    @property
    def duration(self) -> float:
        """The whole of it, in ps."""
        return sum(stage.duration for stage in self.stages)


# (ensemble, temperature, fraction of p_max or None, ps); the last
# stage's pressure is p_final, marked by -1.
_TWENTY_ONE = (
    (NVT, "max", None, 50.0), (NVT, "final", None, 50.0),
    (NPT, "final", 0.02, 50.0),
    (NVT, "max", None, 50.0), (NVT, "final", None, 100.0),
    (NPT, "final", 0.6, 50.0),
    (NVT, "max", None, 50.0), (NVT, "final", None, 100.0),
    (NPT, "final", 1.0, 50.0),
    (NVT, "max", None, 50.0), (NVT, "final", None, 100.0),
    (NPT, "final", 0.5, 5.0),
    (NVT, "max", None, 5.0), (NVT, "final", None, 10.0),
    (NPT, "final", 0.1, 5.0),
    (NVT, "max", None, 5.0), (NVT, "final", None, 10.0),
    (NPT, "final", 0.01, 5.0),
    (NVT, "max", None, 5.0), (NVT, "final", None, 10.0),
    (NPT, "final", -1, 800.0),
)


def twenty_one_step(t_max: float = 600.0, t_final: float = 300.0,
                    p_max: float = 5.0e4,
                    p_final: float = 1.0) -> Protocol:
    """Larsen, Lin and Colina's 21-step compression and decompression,
    at the temperatures and pressures given (K and bar)."""
    stages = []
    for ensemble, hot, fraction, ps in _TWENTY_ONE:
        temperature = t_max if hot == "max" else t_final
        pressure = (None if fraction is None
                    else p_final if fraction < 0 else fraction * p_max)
        stages.append(Stage(ensemble, temperature, ps, pressure))
    return Protocol("21-step", tuple(stages))


#: The scheme at its published defaults: 600 K, 300 K, 5e4 bar, 1 bar.
TWENTY_ONE_STEP = twenty_one_step()


class Equilibrator(_Interface):
    """What runs a :class:`Protocol` -- an external LAMMPS module or an
    in-process integrator over :class:`xtal.ff.api.Calculator`.

    It moves atoms and the cell and never adds, removes or bonds them,
    as every force field here does; ``say`` takes a line for the run's
    log and ``check`` raises when Stop is pressed.  Returns the
    structure at the end of the last stage.
    """

    def run(self, structure, protocol: Protocol, engine, say,
            check):                                 # pragma: no cover
        ...
