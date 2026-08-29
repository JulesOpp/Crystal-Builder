"""Formula, Z, mass, density, charge balance."""

import pytest

from tests.conftest import QUARTZ_DENSITY, RUTILE_DENSITY
from xtal import Lattice, Structure
from xtal.core import properties
from xtal.core.site import Site


def test_rutile_matches_the_literature(rutile):
    assert properties.density(rutile) == pytest.approx(
        RUTILE_DENSITY, abs=0.02)
    assert properties.formula(rutile) == ("TiO2", 2)
    assert properties.cell_contents(rutile) == {"Ti": 2.0, "O": 4.0}


def test_quartz_matches_the_literature(quartz):
    assert properties.density(quartz) == pytest.approx(
        QUARTZ_DENSITY, abs=0.02)
    assert properties.formula(quartz) == ("SiO2", 3)


def test_halite(halite):
    assert properties.formula(halite) == ("NaCl", 4)
    assert properties.density(halite) == pytest.approx(2.16, abs=0.02)


def test_cell_contents_counts_the_cell_not_the_asymmetric_unit(rutile):
    assert rutile.composition() == {"Ti": 1.0, "O": 1.0}
    assert properties.cell_contents(rutile) == {"Ti": 2.0, "O": 4.0}


def test_formula_ordering_conventions():
    def formula_of(symbols):
        frac = [[0.05 * i, 0.05 * i, 0.05 * i]
                for i in range(len(symbols))]
        s = Structure.from_arrays(Lattice.cubic(30.0), symbols, frac)
        return properties.formula(s, reduce=False)[0]

    assert formula_of(["Si", "O", "O"]) == "SiO2"       # not O2Si
    assert formula_of(["Ca", "C", "O", "O", "O"]) == "CaCO3"
    assert formula_of(["O", "H", "H"]) == "H2O"
    assert formula_of(["C"] * 6 + ["H"] * 6) == "C6H6"  # Hill for
    assert formula_of(["Fe"] + ["C"] * 5 + ["H"] * 5) == "C5H5Fe"


def test_partial_occupancy_defeats_reduction():
    s = Structure.from_arrays(
        Lattice.cubic(4.0), ["Na", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]],
        occupancies=[0.5, 1.0])
    formula, z = properties.formula(s)
    assert z == 1
    assert "0.5" in formula


def test_mass_and_density_scale_together(rutile):
    from xtal.core import supercell
    big = supercell.supercell(rutile, 2, 2, 2)
    assert properties.cell_mass(big) == pytest.approx(
        8 * properties.cell_mass(rutile))
    assert properties.density(big) == pytest.approx(
        properties.density(rutile))


def test_charge_balance():
    assert properties.charge_balance(
        Structure.from_arrays(Lattice.cubic(4.0), ["Na"],
                              [[0, 0, 0]])) is None
    charged = Structure(Lattice.cubic(4.0), [
        Site("Na", [0, 0, 0], charge=1.0),
        Site("Cl", [0.5, 0.5, 0.5], charge=-1.0)])
    assert properties.charge_balance(charged) == pytest.approx(0.0)

    unbalanced = Structure(Lattice.cubic(4.0), [
        Site("Na", [0, 0, 0], charge=1.0)])
    assert properties.charge_balance(unbalanced) == pytest.approx(1.0)


def test_info_gathers_everything(quartz):
    info = properties.info(quartz)
    assert info.formula == "SiO2" and info.z == 3
    assert info.n_sites == 2 and info.n_atoms == 9
    assert info.space_group == "P3221"
    assert info.crystal_system == "trigonal"
    text = info.text()
    for expected in ("formula", "space group", "density", "volume"):
        assert expected in text


def test_empty_structure_reports_nothing_rather_than_crashing():
    empty = Structure.empty()
    assert properties.formula(empty) == ("", 0)
    assert properties.cell_mass(empty) == 0.0
    assert properties.density(empty) == 0.0
