"""The calculator: what it decides to add up, and whether its forces
are the gradient of its energy.

Two kinds of test.  The topology ones check that the right terms exist
-- that a metal oxide has no torsions, that geminal pairs are kept out
of the van der Waals sum, that a bond across a cell boundary is one
bond and not two.  The gradient ones check the whole assembled thing
against a finite difference, which is what catches a term that is
individually correct but wired up with the wrong sign or the wrong
lattice translation.

Everything is run on real crystals as well as molecules.  A force
field that works in a big empty box and not under periodic boundary
conditions is no use in a crystal builder.
"""

import numpy as np
import pytest

from tests.conftest_ff import (
    benzene,
    carbon_dioxide,
    ethane,
    isolated,
    salt,
    water,
)
from xtal import Structure
from xtal.core import p1
from xtal.ff import ENGINES, CalculatorError
from xtal.ff.uff.calculator import UFFCalculator, UFFOptions, _pair_key


def build(structure, **options) -> UFFCalculator:
    return ENGINES.build("uff", structure, **options)


def evaluate(structure, **options):
    calculator = build(structure, **options)
    cell = p1.expand(structure)
    return calculator, calculator.compute(cell.cart,
                                          structure.lattice.matrix)


def assert_forces_are_the_gradient(structure, scatter=0.05, **options):
    """Displace off the ideal geometry so every term is active, then
    compare."""
    calculator = build(structure, **options)
    matrix = structure.lattice.matrix
    rng = np.random.default_rng(11)
    positions = p1.expand(structure).cart.copy()
    positions += rng.normal(scale=scatter, size=positions.shape)

    result = calculator.compute(positions, matrix)
    analytic = -result.forces
    numeric = np.zeros_like(positions)
    h = 1e-6
    for atom in range(len(positions)):
        for axis in range(3):
            up = positions.copy()
            up[atom, axis] += h
            down = positions.copy()
            down[atom, axis] -= h
            numeric[atom, axis] = (
                calculator.compute(up, matrix).energy
                - calculator.compute(down, matrix).energy) / (2 * h)
    scale = max(1.0, float(np.abs(numeric).max()))
    assert np.abs(analytic - numeric).max() / scale < 1e-6
    return result


# --------------------------------------------------------- the engine

def test_the_registry_offers_uff():
    assert "uff" in ENGINES
    engine = ENGINES.get("uff")
    assert "forces" in engine.provides and "periodic" in engine.provides


def test_an_unknown_engine_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown force field"):
        ENGINES.get("dft-please")


def test_an_empty_structure_has_no_energy():
    with pytest.raises(CalculatorError, match="no atoms"):
        build(Structure.empty())


def test_the_wrong_number_of_positions_is_refused():
    calculator = build(water())
    with pytest.raises(CalculatorError, match="expected 3"):
        calculator.compute(np.zeros((5, 3)), np.eye(3) * 30)


# ------------------------------------------------------- the topology

def test_ethane_has_the_terms_ethane_should_have():
    calculator = build(ethane())
    counts = calculator.topology.counts()
    assert counts["bonds"] == 7               # one C-C, six C-H
    assert counts["angles"] == 12             # six per carbon
    assert counts["torsions"] == 9            # three H against three
    assert counts["inversions"] == 0          # nothing is sp2


def test_benzene_has_an_inversion_at_every_ring_carbon():
    """Three per centre, one for each neighbour taken out of the
    plane."""
    calculator = build(benzene())
    assert calculator.topology.counts()["inversions"] == 18


def test_a_metal_oxide_has_no_torsions(rutile):
    """UFF gives a torsion only when both central atoms are sp2 or
    sp3.  Building them anyway around a six-coordinate metal would
    enumerate hundreds of thousands of dihedrals, every one worth
    zero."""
    calculator = build(rutile)
    assert calculator.topology.counts()["torsions"] == 0
    assert calculator.topology.counts()["angles"] > 0


def test_bonded_and_geminal_pairs_are_kept_out_of_the_pair_sum():
    """Water's only non-bonded pair would be its two hydrogens, and
    they are geminal -- so its van der Waals energy is exactly
    zero."""
    _calculator, result = evaluate(water())
    assert result.terms["van der Waals"] == 0.0


def test_the_exclusion_key_names_a_pair_the_same_way_from_either_end():
    """Exclusions are built from the bond graph and matched against
    the neighbour search; if the two disagree about how to name a
    pair, bonded atoms get a van der Waals term as well."""
    assert _pair_key(3, 1, [1, 0, -1]) == _pair_key(1, 3, [-1, 0, 1])
    assert _pair_key(2, 2, [0, 0, -1]) == _pair_key(2, 2, [0, 0, 1])


def test_a_bond_across_a_boundary_is_one_bond(quartz):
    """Quartz's silicons each have four oxygens and most of them are
    in the next cell along."""
    calculator = build(quartz)
    assert calculator.topology.counts()["bonds"] == 12
    assert calculator.n_atoms == 9


# --------------------------------------------------------- the forces

@pytest.mark.parametrize("name", ["water", "ethane", "benzene",
                                  "carbon_dioxide"])
def test_forces_are_the_gradient_for_molecules(name):
    maker = {"water": water, "ethane": ethane, "benzene": benzene,
             "carbon_dioxide": carbon_dioxide}[name]
    assert_forces_are_the_gradient(maker())


def test_forces_are_the_gradient_for_rutile(rutile):
    assert_forces_are_the_gradient(rutile)


def test_forces_are_the_gradient_in_a_non_orthogonal_cell(quartz):
    assert_forces_are_the_gradient(quartz)


def test_forces_are_the_gradient_for_a_molecular_crystal(dry_ice):
    assert_forces_are_the_gradient(dry_ice)


def test_forces_are_the_gradient_with_electrostatics(quartz):
    assert_forces_are_the_gradient(quartz, coulomb=True,
                                   charges="qeq")


def test_forces_are_the_gradient_with_charges_from_the_sites():
    assert_forces_are_the_gradient(salt(), scatter=0.08,
                                   coulomb=True, charges="site")


# --------------------------------------------------------- the answer

def test_the_breakdown_adds_up_to_the_total():
    _calculator, result = evaluate(benzene())
    assert sum(result.terms.values()) == pytest.approx(result.energy)
    assert "bond" in result.breakdown()
    assert "total" in result.breakdown()


def test_an_ideal_molecule_sits_at_the_bottom_of_its_bonded_terms():
    """Built at UFF's own equilibrium geometry, the bonded terms are
    zero -- which is a check on the parameters and the expressions at
    the same time."""
    ideal = water(oh=0.99030, angle=104.51)
    _calculator, result = evaluate(ideal)
    assert result.terms["bond"] == pytest.approx(0.0, abs=1e-4)
    assert result.terms["angle"] == pytest.approx(0.0, abs=1e-4)


def test_a_flat_benzene_has_no_torsion_or_inversion_energy():
    _calculator, result = evaluate(benzene())
    assert result.terms["torsion"] == pytest.approx(0.0, abs=1e-9)
    assert result.terms["inversion"] == pytest.approx(0.0, abs=1e-9)


def test_stretching_a_bond_costs_energy_and_pulls_back():
    short = evaluate(water(oh=0.9903))[1]
    long_ = evaluate(water(oh=1.30))[1]
    assert long_.energy > short.energy
    assert long_.max_force > 10.0


# ----------------------------------------------------------- warnings

def test_an_uncertain_typing_is_reported_before_any_number_is():
    """An octahedral zinc, which UFF only has a tetrahedral type
    for."""
    positions = [[0, 0, 0]]
    for axis in range(3):
        for sign in (1, -1):
            point = [0.0, 0.0, 0.0]
            point[axis] = sign * 2.0
            positions.append(point)
    calculator = build(isolated(["Zn"] + ["O"] * 6, positions))
    assert any("not sure of" in w for w in calculator.warnings)


def test_a_well_understood_crystal_raises_no_typing_warning(rutile):
    """Titanium with six neighbours and an octahedral titanium type is
    a good assignment; warning about it would put a warning on almost
    every structure and leave nothing to notice."""
    assert not any("not sure of" in w for w in build(rutile).warnings)


def test_electrostatics_with_no_charges_says_so():
    calculator = build(water(), coulomb=True, charges="site")
    assert any("zero" in w for w in calculator.warnings)


def test_a_net_charged_cell_is_reported_rather_than_refused():
    charged = salt()
    charged.sites[1].charge = -0.5
    calculator = build(charged, coulomb=True, charges="site")
    assert any("net charge" in w for w in calculator.warnings)


# ----------------------------------------------------- the pair list

def test_the_pair_list_survives_the_atoms_moving():
    """It is built with a skin and rebuilt when an atom outruns it.
    The energy has to be the same either way, or an optimiser sees a
    step where there is none."""
    structure = benzene()
    calculator = build(structure)
    matrix = structure.lattice.matrix
    positions = p1.expand(structure).cart.copy()
    before = calculator.compute(positions, matrix).energy

    far = positions + 5.0                       # a rigid translation
    after = calculator.compute(far, matrix).energy
    assert after == pytest.approx(before, rel=1e-9)


def test_options_round_trip_as_a_dictionary():
    options = UFFOptions(coulomb=True, charges="qeq")
    assert options.to_dict()["charges"] == "qeq"


# ------------------------------------------------------------- stress

def test_numeric_stress_is_symmetric_and_finite(quartz):
    calculator = build(quartz)
    cell = p1.expand(quartz)
    stress = calculator.numeric_stress(cell.cart,
                                       quartz.lattice.matrix)
    assert stress.shape == (3, 3)
    assert np.allclose(stress, stress.T)
    assert np.all(np.isfinite(stress))


def test_a_structure_with_no_bonds_still_has_an_energy():
    """Two argon atoms in a box: no bonds, no angles, and a perfectly
    good van der Waals energy."""
    gas = isolated(["Ar", "Ar"], [[0, 0, 0], [4.0, 0, 0]])
    calculator, result = evaluate(gas)
    assert calculator.topology.counts()["bonds"] == 0
    assert result.energy < 0.0                  # attracting
    assert any("no bonds" in w for w in calculator.warnings)


def test_the_summary_says_what_it_built(quartz):
    text = build(quartz).summary()
    assert "9 atoms" in text and "bonds" in text
