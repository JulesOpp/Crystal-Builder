"""Deuterium is hydrogen to every energy this application computes.

Every engine here -- UFF, EQeq, xTB, DFTB+ and the machine-learned
potentials -- returns a Born-Oppenheimer energy, and the surface an
atom moves on does not depend on the mass of its nucleus.  So a neutron
structure written with ``D`` has exactly the energy, forces and charges
of the same structure written with ``H``.  Refusing it, which every
engine did, sent a user with a deuterated MOF from the COD to rename
their atoms by hand.

What mass *does* change is vibration, and nothing that goes through the
engine door computes one: the DFTB+ modes run writes its own input and
still meets ``D`` as ``D``.
"""

import math

import numpy as np
import pytest

from tests.conftest_ff import isolated
from xtal import Structure
from xtal.core import p1
from xtal.core.site import Site
from xtal.ff.api import Calculator
from xtal.ff.registry import ENGINES
from xtal.ff.uff import typer


def _water(hydrogen: str) -> Structure:
    """One water in a box, off its minimum so the forces are not zero,
    with ``hydrogen`` for its H."""
    half = math.radians(110.0)
    return isolated(["O", hydrogen, hydrogen],
                    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                     [math.cos(half), math.sin(half), 0.0]])


def _evaluate(structure, **options):
    calculator = ENGINES.get("uff")(structure, **options)
    cell = p1.expand(structure)
    return calculator, calculator.compute(cell.cart,
                                          structure.lattice.matrix)


def test_heavy_water_has_the_energy_and_forces_of_water():
    _, light = _evaluate(_water("H"))
    _, heavy = _evaluate(_water("D"))

    assert heavy.energy == pytest.approx(light.energy, abs=1e-12)
    np.testing.assert_allclose(heavy.forces, light.forces, atol=1e-12)


def test_heavy_water_has_the_charges_of_water():
    """EQeq inside UFF: a D given its own ionisation energies would
    differ from H by about 4 meV (the reduced mass), and hydrogen's
    electron affinity is the method's -2 eV either way."""
    _, light = _evaluate(_water("H"), charges="eqeq",
                         coulomb=True)
    _, heavy = _evaluate(_water("D"), charges="eqeq",
                         coulomb=True)

    assert heavy.energy == pytest.approx(light.energy, abs=1e-12)


def test_the_run_says_deuterium_was_computed_as_hydrogen():
    calculator, _ = _evaluate(_water("D"))

    assert any("deuterium" in w.lower() for w in calculator.warnings)


def test_saying_so_does_not_touch_every_other_calculator():
    """``Calculator.warnings`` is a class attribute; appending to it
    would put the sentence on every run after this one."""
    _evaluate(_water("D"))
    plain, _ = _evaluate(_water("H"))

    assert Calculator.warnings == []
    assert not any("deuterium" in w.lower() for w in plain.warnings)


def test_the_structure_keeps_its_deuterium():
    """The engine is handed a copy; the document is the user's."""
    heavy = _water("D")
    _evaluate(heavy)

    assert [site.element for site in heavy.sites] == ["O", "D", "D"]


def test_the_atom_types_table_types_deuterium_as_hydrogen():
    """The table is typed outside the engine door, and has to agree
    with what the engine computed."""
    typing = typer.assign(_water("D"))

    assert [t.name for t in typing.types] == \
        [t.name for t in typer.assign(_water("H")).types]
    assert typing.types[1].name == "H_"


def test_deuterium_beside_a_marker_is_still_hydrogen():
    """The two things held at the door compose: the marker is taken
    out and the deuterium renamed, and the forces come back over the
    whole cell."""
    heavy = _water("D")
    heavy.sites.append(Site("X", np.array([0.1, 0.1, 0.1])))
    heavy.ensure_labels()
    heavy.touch()

    calculator, result = _evaluate(heavy)
    _, light = _evaluate(_water("H"))

    assert result.forces.shape == (4, 3)
    assert result.energy == pytest.approx(light.energy, abs=1e-12)
    assert any("deuterium" in w.lower() for w in calculator.warnings)
