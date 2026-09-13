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

from xtal.modules.registry import (
    MODULES,
    Action,
    Availability,
    Module,
    Param,
)

#: The runs themselves import the DFTB+ engine, and the engine imports
#: this package on its way in -- so they are reached through these
#: functions at run time, and this module declares their parameters
#: without importing them.

BAND_PARAMS = (
    Param("path", "Path", kind="text", default="",
          help="The corners to visit, as ASE names them: "
               "'GXWKGLUWLK,UX'.  A comma is a jump.  Empty is ASE's "
               "recommended path for this cell"),
    Param("density", "Points per 1/A", kind="float", default=40.0,
          minimum=2.0, maximum=500.0, step=5.0, decimals=0,
          help="How finely each segment is sampled"),
    Param("dos", "Density of states beside it", kind="bool",
          default=True,
          help="Projected onto each element, from the run on the mesh "
               "that converges the charges -- no extra invocation, and "
               "as fine as that mesh"),
    Param("sigma", "DOS broadening", kind="float", default=0.1,
          minimum=0.005, maximum=2.0, step=0.05, decimals=3,
          suffix=" eV"),
)

DOS_PARAMS = (
    Param("spacing", "K-point spacing", kind="float", default=0.1,
          minimum=0.01, maximum=1.0, step=0.02, decimals=3,
          suffix=" 1/A",
          help="Denser than the charges need: a density of states is "
               "an integral over the zone"),
    Param("sigma", "Broadening", kind="float", default=0.1,
          minimum=0.005, maximum=2.0, step=0.05, decimals=3,
          suffix=" eV",
          help="DFTB+ does not broaden; this Gaussian width is ours"),
    Param("shells", "Resolve s, p and d", kind="bool", default=False),
)


def _dos(job):
    from xtal.modules.dftb_runs import dos
    return dos.density_of_states(job)


def _ase() -> Availability:
    from xtal.analysis import kpath
    return Availability(kpath.installed(),
                        "" if kpath.installed() else kpath.MISSING)


def _band_structure(job):
    from xtal.modules.dftb_runs import bands
    return bands.band_structure(job)


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
        Action(name="band-structure", label="Band structure...",
               tip="Eigenvalues along a path through the Brillouin "
                   "zone, from charges converged on a mesh",
               params=BAND_PARAMS, run=_band_structure,
               dialog="band-structure", kind="bands", check=_ase),
        Action(name="dos", label="Density of states...",
               tip="Total and projected onto each element, on a dense "
                   "mesh",
               params=DOS_PARAMS, run=_dos, dialog="dftb-run",
               kind="dos"),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(DFTB)
