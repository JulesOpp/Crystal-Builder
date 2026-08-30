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


@dataclass(frozen=True)
class Engine:
    """One energy engine the application can offer."""

    name: str                       # "uff"
    label: str                      # "Universal Force Field"
    description: str
    build: Callable                 # (structure, **options) -> Calculator
    # What it can do, for the UI to grey out honestly:
    # {"forces", "stress", "charges", "periodic"}
    provides: frozenset = field(default_factory=frozenset)

    def __call__(self, structure, **options):
        return self.build(structure, **options)


class EngineRegistry:
    def __init__(self):
        self._engines: dict[str, Engine] = {}

    def register(self, engine: Engine) -> Engine:
        self._engines[engine.name] = engine
        return engine

    def __contains__(self, name: str) -> bool:
        return name in self._engines

    def __iter__(self):
        return iter(self._engines.values())

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
        return self.get(name).build(structure, **options)


ENGINES = EngineRegistry()
