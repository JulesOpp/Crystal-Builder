"""
xtal.modules.forcefield
=======================
UFF, as a registry entry.

The three things the ``Calculate`` menu held are the three entries
under ``Forcefield``, and nothing about UFF changed to put them there.
That is the point of the step: the menu became a registry, and the
first module in it is the one that was already working, moved rather
than rewritten.

DFTB+ was an *engine* under this same module until Phase I, sharing
one panel with UFF behind an engine chooser.  The two have nothing in
common that a user cares about -- one is in-process and instant, the
other launches a binary and can take minutes -- and stacking DFTB+'s
generated form (Hamiltonian, parameter directory, dispersion, charge,
temperature, k-point spacing, SCC tolerance, angular momentum
overrides) on top of the shared Optimisation controls in one panel is
what made that panel too tall for a laptop screen.  Splitting them
into two modules -- this one and :mod:`xtal.modules.dftb` -- with a
dock apiece is the fix, and it also makes DFTB+ discoverable as its
own thing in the Modules tree rather than a setting to find inside
Forcefield.

They are the one place :attr:`~xtal.modules.registry.Action.shell` is
used.  The Force Field panel does three things a generic runner cannot
-- it draws the geometry as it moves, it plots the energy as it
arrives, and it lands the whole run on the undo stack as a single
command -- and rewriting it to fit a form-and-worker shape would have
been Phase D spending its budget on the one module that did not need
it.  So the registry names the window action that performs each entry,
and the shell obliges.

A module written after this one has ``run`` instead, gets its form
generated and its thread managed, and touches no existing file.  That
is the asymmetry the ``shell`` field records honestly rather than
hides.
"""

from __future__ import annotations

from xtal.modules.registry import MODULES, Action, Availability, Module


def _available() -> Availability:
    """UFF is native NumPy and in-process, so it is available whenever
    it is registered -- which is always, unlike DFTB+, which needs a
    binary and a parameter set found on this machine."""
    from xtal.ff import ENGINES
    if "uff" in ENGINES:
        return Availability(True)
    return Availability(                            # pragma: no cover
        False, "the UFF engine is not registered")


FORCEFIELD = Module(
    name="forcefield",
    label="Forcefield",
    description="Universal Force Field: atom types, energies and "
                "geometry optimisation, under the space group.",
    order=10,
    check=_available,
    provides=frozenset({"energy", "forces", "structure",
                        "trajectory"}),
    actions=(
        Action(name="setup", label="Setup and atom types...",
               tip="Atom types, electrostatics, and how the run is "
                   "going",
               shell="show_ff", writes_run_folder=False),
        Action(name="single-point", label="Single point energy",
               tip="Energy and per-term breakdown at this geometry",
               shell="single_point", kind="single-point"),
        Action(name="optimise", label="Optimise geometry",
               tip="Relax the structure within its space group",
               shell="optimize", kind="optimise"),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(FORCEFIELD)
