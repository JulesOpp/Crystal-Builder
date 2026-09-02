"""
xtal.ff.markers
===============
Keeping dummy atoms out of an energy.

A dummy atom is a marker and not chemistry -- see
:data:`xtal.core.elements.DUMMY_ELEMENTS`.  It has no force-field
type, no radius, no valence and no electrons; ``Add centroid`` puts
one in by an ordinary gesture, and until this module existed a single
one of them anywhere in the cell made every force field refuse the
whole structure by name.

Refusing was defensible while a marker was an exotic thing to have.
It is not, now that a centroid is a click: the user has a structure
they consider perfectly ordinary and a button that will not run on it,
and the remedy the message offers -- delete the marker -- throws away
the thing they added it for.

So the markers are **held back at the door** instead, which is the
same move :func:`xtal.modules.job.without_dummies` makes for a module
run and for the same reason.  The engine is built over a structure
that has none, so nothing inside it has to learn the word: no type is
assigned to a marker, no bond drawn to one spends a valence, no
coordination is counted through one, and no van der Waals pair list
looks for a radius it has not got.

What comes back out is :class:`WithoutMarkers`, which presents the
*whole* cell again -- because everything above a calculator is indexed
by the P1 cell of the structure the user is looking at.  The optimiser
maps orbits back onto sites, the panel reads the cell, the trajectory
writes it.  A marker in that picture feels no force and exerts none,
which is exactly what "the force field ignores it" has to mean: it
does not move, and nothing moves because of it.
"""

from __future__ import annotations

import numpy as np

from xtal.core import elements as el
from xtal.core import p1
from xtal.ff.api import Calculator, Result


def dummy_sites(structure) -> list[int]:
    """Which sites of ``structure`` are markers."""
    return [i for i, site in enumerate(structure.sites)
            if el.is_dummy(site.element)]


def hold_back(structure):
    """``(structure, kept)`` -- what an engine is handed, and which
    atoms of the original P1 cell it is about.

    ``kept`` is ``None`` when there was nothing to hold back, in which
    case the structure comes back untouched rather than copied -- that
    being every structure anybody has ever opened.

    Removing the marker *sites* removes exactly the marker atoms from
    the P1 cell and leaves the order of the rest alone, because a
    cell is expanded site by site in site order.  So the atoms that
    survive, in ascending order, are the mapping.
    """
    dummies = dummy_sites(structure)
    if not dummies:
        return structure, None
    cell = p1.expand(structure)
    kept = np.array([k for k in range(cell.n_atoms)
                     if not el.is_dummy(cell.elements[k])], dtype=int)
    clean = structure.copy()
    clean.remove_sites(dummies)
    return clean, kept


class WithoutMarkers(Calculator):
    """An engine's calculator, wearing the whole cell.

    A thin façade and deliberately not a subclass of anything: it
    wraps whatever the engine returned, so UFF, DFTB+ and an engine
    written next year all get this without knowing it happened.  Only
    the two things that are about *size* are overridden; everything
    else -- the summary, the warnings, the topology counts an engine
    hangs on itself -- is the engine's own and is passed through.

    The forces come back over the whole cell with zeros where the
    markers are, which is the honest answer and also the one that
    makes the optimiser do the right thing without being told: a site
    whose whole orbit feels nothing has no gradient, so it stays where
    the user put it.
    """

    def __init__(self, inner: Calculator, kept, n_atoms: int):
        self._inner = inner
        self._kept = np.asarray(kept, dtype=int)
        self._n_atoms = int(n_atoms)

    # -- the two things that are about size ----------------------------

    @property
    def n_atoms(self) -> int:
        return self._n_atoms

    def compute(self, positions, matrix) -> Result:
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        result = self._inner.compute(positions[self._kept], matrix)
        forces = np.zeros((self._n_atoms, 3))
        if len(result.forces):
            forces[self._kept] = result.forces
        return Result(result.energy, forces, dict(result.terms),
                      result.stress)

    # -- everything else is the engine's -------------------------------
    #
    # Spelled out rather than left to __getattr__, because these four
    # have defaults on Calculator: attribute lookup would find those
    # and never ask the engine.

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def label(self) -> str:
        return self._inner.label

    @property
    def provides_forces(self) -> bool:
        return self._inner.provides_forces

    @property
    def provides_stress(self) -> bool:
        return self._inner.provides_stress

    @property
    def warnings(self) -> list:
        return self._inner.warnings

    def summary(self) -> str:
        held = self._n_atoms - len(self._kept)
        note = (f"; {held} dummy atom{'' if held == 1 else 's'} left "
                f"out" if held else "")
        return f"{self._inner.summary()}{note}"

    def __getattr__(self, name: str):
        try:
            inner = self.__dict__["_inner"]
        except KeyError:                            # during __init__
            raise AttributeError(name) from None
        return getattr(inner, name)

    def __repr__(self) -> str:
        return (f"WithoutMarkers({self._inner!r}, "
                f"{self._n_atoms} atoms)")
