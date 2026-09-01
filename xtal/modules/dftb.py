"""
xtal.modules.dftb
==================
DFTB+, as a registry entry of its own.

Reached as an *engine* under ``Forcefield`` since Phase H, sharing its
panel with UFF behind an engine chooser -- which meant that panel had
to hold both UFF's controls and DFTB+'s generated form (eight fields:
Hamiltonian, parameter directory, dispersion, charge, temperature,
k-point spacing, SCC tolerance, angular momentum overrides) at once,
and it grew taller than a laptop screen the day DFTB+ arrived.

Phase I splits it out: its own module, its own dock, its own entry in
the Modules tree, so a user who has never touched DFTB+ never sees a
form for it, and a user who has does not have to find it inside
Forcefield first.

The three entries and the ``shell`` mechanism are exactly what
:mod:`xtal.modules.forcefield` already does for UFF -- see that
module's docstring for why ``Action.shell`` exists at all.
"""

from __future__ import annotations

from xtal.modules.registry import MODULES, Action, Availability, Module


def _available() -> Availability:
    """The binary and a parameter set, both looked for -- the same
    check the panel itself uses, so the tree and the panel never
    disagree about whether a run is possible."""
    from xtal.ff import ENGINES
    if "dftb" not in ENGINES:
        return Availability(                        # pragma: no cover
            False, "the DFTB+ engine is not registered")
    return ENGINES.get("dftb").availability()


DFTB = Module(
    name="dftb",
    label="DFTB+",
    description="Density-functional tight binding: atom types have "
                "no place in it, but the energy, the forces and the "
                "geometry optimisation are asked for the same way.",
    order=11,
    check=_available,
    provides=frozenset({"energy", "forces", "structure",
                        "trajectory"}),
    actions=(
        Action(name="setup", label="Setup and parameters...",
               tip="Hamiltonian, parameter directory, dispersion, and "
                   "how the run is going",
               shell="show_dftb", writes_run_folder=False),
        Action(name="single-point", label="Single point energy",
               tip="Energy and per-term breakdown at this geometry",
               shell="dftb_single_point", kind="single-point"),
        Action(name="optimise", label="Optimise geometry",
               tip="Relax the structure within its space group",
               shell="dftb_optimize", kind="optimise"),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(DFTB)
