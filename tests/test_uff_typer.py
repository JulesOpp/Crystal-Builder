"""Atom typing -- the part that decides whether an energy means
anything.

The tests are chemistry, not code: benzene's carbons are aromatic,
carbon dioxide's is sp, quartz's oxygens are framework oxygens, and an
octahedral zinc gets flagged because UFF has no octahedral zinc.  A
typer that agreed with itself but called a carbonyl an ether would pass
any test that only checked shapes.

Missing hydrogens run through all of it.  Every X-ray structure has
none, so the rules have to survive a benzene ring with no H on it and
say what they assumed when they cannot.
"""

import numpy as np
import pytest

from tests.conftest_ff import (
    benzene,
    butadiene,
    carbon_dioxide,
    ethane,
    isolated,
    methane,
    water,
)
from xtal import Lattice, Structure
from xtal.core import p1
from xtal.ff.uff import typer


def names(structure) -> list[str]:
    return list(typer.assign(structure).names)


def type_of(structure, index: int) -> typer.AtomType:
    return typer.assign(structure).types[index]


# ------------------------------------------------------------ organics

def test_benzene_is_aromatic():
    assert names(benzene())[:6] == ["C_R"] * 6
    assert all(t == "H_" for t in names(benzene())[6:])


def test_benzene_is_still_aromatic_without_its_hydrogens():
    """Which is how it arrives from an X-ray refinement: the ring is
    flat and six-membered, and that is what aromaticity is here."""
    assert names(benzene(with_hydrogen=False)) == ["C_R"] * 6


def test_a_puckered_six_ring_is_not_aromatic():
    """Cyclohexane in its chair: same ring size, same element, and
    sp3 throughout.  Flatness is what separates them."""
    ring = []
    for k in range(6):
        angle = np.radians(60 * k)
        ring.append([1.54 * np.cos(angle), 1.54 * np.sin(angle),
                     0.25 * (-1) ** k])
    chair = isolated(["C"] * 6, ring)
    assert "C_R" not in names(chair)


def test_ethane_is_two_sp3_carbons():
    assert names(ethane())[:2] == ["C_3", "C_3"]


def test_methane_and_water_and_carbon_dioxide():
    assert names(methane()) == ["C_3"] + ["H_"] * 4
    assert names(water()) == ["O_3", "H_", "H_"]
    assert names(carbon_dioxide()) == ["O_2", "C_1", "O_2"]


def test_a_linear_carbon_is_recognised_by_its_angle():
    """The rule that separates carbon dioxide from an ether, and the
    reason the angle has to be looked at and not just the count."""
    assert type_of(carbon_dioxide(), 1).name == "C_1"
    assert "180" in type_of(carbon_dioxide(), 1).reason


# -------------------------------------------------------- bond orders

def test_carbon_dioxide_gets_two_double_bonds():
    """An sp carbon has two pi bonds to place.  Pairing atoms off one
    at a time gives O=C-O, which is wrong and stiffens one bond by a
    third."""
    typing = typer.assign(carbon_dioxide())
    assert sorted(typing.bond_orders) == [2.0, 2.0]


def test_butadiene_gets_double_single_double():
    """All four carbons are sp2, so the assignment has to come from
    the lengths: the short bonds are the double ones."""
    structure = butadiene()
    typing = typer.assign(structure)
    from xtal.core import bonding
    graph = bonding.graph(structure)
    orders = {tuple(sorted((b.i, b.j))): typing.bond_orders[k]
              for k, b in enumerate(graph.bonds)}
    assert orders[(0, 1)] == 2.0
    assert orders[(1, 2)] == 1.0
    assert orders[(2, 3)] == 2.0


def test_aromatic_bonds_are_one_and_a_half():
    typing = typer.assign(benzene(with_hydrogen=False))
    assert list(typing.bond_orders) == [1.5] * 6


def test_a_single_bond_is_the_default():
    typing = typer.assign(ethane())
    assert set(typing.bond_orders) == {1.0}


# ------------------------------------------------------------ crystals

def test_quartz_oxygens_are_framework_oxygens(quartz):
    """UFF has a separate oxygen for a wide Si-O-Si bridge, and using
    the ordinary one gives every zeolite a badly wrong angle."""
    assigned = names(quartz)
    assert set(assigned) == {"Si3", "O_3_z"}
    oxygen = next(t for t in typer.assign(quartz).types
                  if t.name == "O_3_z")
    assert "framework" in oxygen.reason


def test_rutile_titanium_is_octahedral(rutile):
    assert names(rutile)[:2] == ["Ti6+4", "Ti6+4"]


def test_halite_is_typed_without_bonds(halite):
    """Sodium and chlorine have one type each, so no geometry is
    needed -- and none is available, because the bond rules do not
    perceive an ionic contact."""
    assert set(names(halite)) == {"Na", "Cl"}


def test_dry_ice_is_carbon_dioxide_in_a_box(dry_ice):
    assigned = set(names(dry_ice))
    assert assigned == {"C_1", "O_2"}


def test_a_ring_that_only_closes_through_a_cell_boundary_is_not_a_ring(
        quartz):
    """Walking Si-O-Si along an axis comes back to the atom it started
    from, one cell along.  That is the lattice repeating, and calling
    it a ring would make every framework aromatic."""
    assert typer.assign(quartz).rings == ()


# --------------------------------------------------------- confidence

def test_an_octahedral_zinc_is_flagged_because_uff_has_no_such_type():
    """The footgun the plan names: UFF fits zinc as tetrahedral, and a
    six-coordinate zinc still gets a number.  It should not get a
    confident one."""
    lattice = Lattice.cubic(12.0)
    positions = [[0, 0, 0]]
    for axis in range(3):
        for sign in (1, -1):
            point = [0.0, 0.0, 0.0]
            point[axis] = sign * 2.0
            positions.append(point)
    octahedral = Structure.from_arrays(
        lattice, ["Zn"] + ["O"] * 6, lattice.to_frac(positions))
    zinc = type_of(octahedral, 0)
    assert zinc.name == "Zn3+2"
    assert not zinc.is_sure
    assert "6" in zinc.reason


def test_a_lone_carbon_says_it_could_not_tell():
    lonely = isolated(["C"], [[0, 0, 0]])
    assert type_of(lonely, 0).confidence == typer.UNCERTAIN


def test_a_confident_typing_reports_nothing_to_check(rutile):
    assert typer.assign(benzene()).unsure() == []


def test_the_summary_counts_what_it_found():
    text = typer.assign(benzene()).summary()
    assert "C_Rx6" in text and "H_x6" in text


# ---------------------------------------------------------- overrides

def test_an_override_wins_and_says_so(rutile):
    rutile.sites[0].props["uff_type"] = "Ti3+4"
    rutile.touch()
    assigned = type_of(rutile, 0)
    assert assigned.name == "Ti3+4"
    assert assigned.overridden and assigned.is_sure


def test_an_override_applies_to_the_whole_orbit(rutile):
    """Two atoms related by symmetry are one atom seen twice; typing
    them differently would make the energy depend on which copy was
    clicked."""
    rutile.sites[1].props["uff_type"] = "O_2"
    rutile.touch()
    cell = p1.expand(rutile)
    typing = typer.assign(rutile)
    oxygens = cell.indices_of_site(1)
    assert len(oxygens) == 4
    assert {typing.types[int(i)].name for i in oxygens} == {"O_2"}


def test_a_nonsense_override_is_ignored_with_a_warning(rutile):
    rutile.sites[0].props["uff_type"] = "Unobtainium"
    rutile.touch()
    assert type_of(rutile, 0).name == "Ti6+4"
    assert any("Unobtainium" in w
               for w in rutile.meta.get("warnings", []))


# ------------------------------------------------------------ refusal

def test_an_element_uff_has_no_parameters_for_is_refused():
    """Better than substituting something similar and returning a
    number that looks like an answer."""
    lattice = Lattice.cubic(10.0)
    exotic = Structure.from_arrays(lattice, ["Og"], [[0, 0, 0]])
    with pytest.raises(typer.TypingError, match="Og"):
        typer.assign(exotic)


def test_an_empty_structure_types_to_nothing():
    empty = Structure.empty()
    typing = typer.assign(empty)
    assert len(typing) == 0
    assert typing.names == ()
