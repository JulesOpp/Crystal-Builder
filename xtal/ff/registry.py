"""
xtal.ff.registry
================
Name -> calculator, the same shape as the file-format and draw-style
registries.

The Force Field panel builds its chooser from here, the CLI takes
``--engine`` from here, and neither of them knows that UFF is the only
entry.  Adding GULP or an MLIP later is a module plus a
:func:`register` call, which is the whole point of the exercise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from xtal.params import Availability, Param, coerce, defaults


@dataclass(frozen=True)
class Engine:
    """One energy engine the application can offer."""

    name: str                       # "uff"
    label: str                      # "Universal Force Field"
    description: str
    build: Callable                 # (structure, **options) -> Calculator
    # What it can do, for the UI to grey out honestly:
    # {"forces", "stress", "charges", "periodic", "types"}
    provides: frozenset = field(default_factory=frozenset)
    #: What it needs asked before it can run, declared the way a
    #: module's parameters are (:mod:`xtal.params`).  UFF declares
    #: none and keeps the two hand-built controls it has always had;
    #: an engine that declares these gets a generated form instead --
    #: which is what let DFTB+, with its Hamiltonian, its parameter
    #: set, its k-point mesh and its filling temperature, arrive
    #: without the panel learning any of those words.
    options: tuple[Param, ...] = ()
    #: Whether it can run at all -- typically that a binary is
    #: installed and that its parameter files have been found.  Called
    #: every time the panel is refreshed, so it has to be cheap.
    #:
    #: It is handed the options, because for an external engine half
    #: the answer is in them: DFTB+ without a Slater-Koster directory
    #: cannot run, and *which* directory is a field in the form.  A
    #: check that ignored them would tell a user their engine was
    #: unavailable while they were looking at the box that makes it
    #: available.
    check: Callable[..., Availability] | None = None
    #: Where it sits in the chooser.  UFF is 10 because it is the one
    #: that was there before there was a chooser, and the one that is
    #: always installed.
    order: int = 100

    def availability(self, **options) -> Availability:
        if self.check is None:
            return Availability(True)
        try:
            return self.check(**self.coerce(options))
        except Exception as exc:                    # noqa: BLE001
            # A broken check must not take the chooser with it.
            return Availability(False, str(exc))

    def defaults(self) -> dict:
        return defaults(self.options)

    def coerce(self, values: dict | None) -> dict:
        return coerce(self.options, values)

    def __call__(self, structure, **options):
        """Build a calculator, with the markers held at the door.

        This and not :attr:`build` is what everything should call.
        ``build`` is the engine's own factory and knows nothing about
        dummy atoms; asking it directly hands one a structure with
        markers in it, which is how a centroid used to make every
        force field refuse the crystal it was added to.  Doing it here
        rather than in each engine is the same argument
        :mod:`xtal.ff.markers` makes: an engine written next year
        would have to remember, and would not.
        """
        from xtal.core import p1
        from xtal.ff import markers

        clean, kept = markers.hold_back(structure)
        calculator = self.build(clean, **options)
        if kept is None:
            return calculator
        return markers.WithoutMarkers(calculator, kept,
                                      p1.expand(structure).n_atoms)


class EngineRegistry:
    def __init__(self):
        self._engines: dict[str, Engine] = {}

    def register(self, engine: Engine) -> Engine:
        self._engines[engine.name] = engine
        return engine

    def __contains__(self, name: str) -> bool:
        return name in self._engines

    def __iter__(self):
        return iter(sorted(self._engines.values(),
                           key=lambda e: (e.order, e.label)))

    def __len__(self) -> int:
        return len(self._engines)

    def get(self, name: str) -> Engine:
        try:
            return self._engines[name]
        except KeyError:
            raise ValueError(
                f"unknown force field: {name!r}; "
                f"have {', '.join(sorted(self._engines)) or 'none'}"
            ) from None

    def names(self) -> list[str]:
        return list(self._engines)

    def build(self, name: str, structure, **options):
        return self.get(name)(structure, **options)


ENGINES = EngineRegistry()
