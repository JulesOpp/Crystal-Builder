"""UFF against numbers from outside this repository.

Everything else in the force-field tests checks that the code agrees
with itself: that the gradient matches the energy, that the topology
has the terms it should.  All of that would still pass if the whole
model were subtly wrong.

These check it against the literature -- bond lengths and force
constants the paper prints, the ethane rotation barrier, the geometry
UFF is known to give for water and benzene, and a Madelung constant
that has nothing to do with force fields at all.  When one of these
fails, the physics is wrong and not the plumbing.
"""

import numpy as np
import pytest

from tests.conftest_ff import benzene, ethane, methane, water
from xtal.ff import ENGINES, optimize
from xtal.ff.uff import terms

# Rappe et al. 1992, and reproduced by every implementation since.
ETHANE_BARRIER = 2.119          # the torsional term alone, kcal/mol
UFF_WATER_OH = 0.9903
UFF_WATER_ANGLE = 104.51
UFF_METHANE_CH = 1.1094
UFF_BENZENE_CC = 1.3793


def relax(structure, **kwargs):
    calculator = ENGINES.build("uff", structure)
    kwargs.setdefault("max_steps", 500)
    kwargs.setdefault("force_tolerance", 1e-4)
    return optimize.run(calculator, structure, **kwargs)


def cartesian(structure, result):
    return result.frac @ structure.lattice.matrix


def energy_of(structure) -> float:
    from xtal.core import p1
    calculator = ENGINES.build("uff", structure)
    return calculator.compute(p1.expand(structure).cart,
                              structure.lattice.matrix).energy


# ------------------------------------------------- relaxed geometries

def test_water_relaxes_to_the_published_uff_geometry():
    result = relax(water(oh=1.05, angle=100.0))
    cart = cartesian(water(), result)
    oh = np.linalg.norm(cart[1] - cart[0])
    angle = np.degrees(np.arccos(
        (cart[1] - cart[0]) @ (cart[2] - cart[0])
        / (oh * np.linalg.norm(cart[2] - cart[0]))))
    assert oh == pytest.approx(UFF_WATER_OH, abs=1e-3)
    assert angle == pytest.approx(UFF_WATER_ANGLE, abs=0.05)


def test_methane_relaxes_to_a_regular_tetrahedron():
    """The C-H length is UFF's, and every H-C-H angle is the
    tetrahedral one -- which is a check on the angle term's general
    cosine expansion, not just on the bond."""
    start = methane(ch=1.02)
    result = relax(start)
    cart = cartesian(start, result)
    lengths = [np.linalg.norm(cart[k] - cart[0]) for k in range(1, 5)]
    assert lengths == pytest.approx([UFF_METHANE_CH] * 4, abs=2e-3)

    angles = []
    for a in range(1, 5):
        for b in range(a + 1, 5):
            u, v = cart[a] - cart[0], cart[b] - cart[0]
            angles.append(np.degrees(np.arccos(
                u @ v / (np.linalg.norm(u) * np.linalg.norm(v)))))
    assert angles == pytest.approx([109.4712] * 6, abs=0.05)


def test_benzene_relaxes_to_a_flat_regular_hexagon():
    start = benzene(cc=1.45, ch=1.02)
    result = relax(start, force_tolerance=1e-3)
    cart = cartesian(start, result)
    ring = cart[:6]
    bonds = [np.linalg.norm(ring[k] - ring[(k + 1) % 6])
             for k in range(6)]
    assert bonds == pytest.approx([bonds[0]] * 6, abs=1e-4)
    assert bonds[0] == pytest.approx(UFF_BENZENE_CC, abs=0.02)
    assert np.abs(cart[:, 2]).max() < 1e-3      # still flat


# ------------------------------------------------------- the barriers

def test_the_ethane_rotation_barrier():
    """Eclipsed minus staggered.  UFF's threefold term contributes
    2.119 kcal/mol exactly, and the hydrogens crowding each other add
    the rest -- about 3 kcal/mol in total, against an experimental
    2.9."""
    staggered = energy_of(ethane(twist=60.0))
    eclipsed = energy_of(ethane(twist=0.0))
    barrier = eclipsed - staggered
    assert barrier == pytest.approx(3.05, abs=0.1)
    assert barrier > ETHANE_BARRIER          # van der Waals adds to it


def test_the_torsional_part_of_that_barrier_is_the_published_one():
    """Isolated from the van der Waals, the torsion term alone has to
    be the barrier the parameter table states."""
    from xtal.core import p1

    for twist, expected in ((60.0, 0.0), (0.0, ETHANE_BARRIER)):
        structure = ethane(twist=twist)
        calculator = ENGINES.build("uff", structure)
        result = calculator.compute(p1.expand(structure).cart,
                                    structure.lattice.matrix)
        assert result.terms["torsion"] == pytest.approx(expected,
                                                        abs=1e-6)


def test_the_barrier_is_split_between_the_torsions_around_the_bond():
    """Nine H-C-C-H dihedrals share one 2.119 kcal/mol barrier.  Not
    dividing it would make ethane's barrier nine times too large."""
    calculator = ENGINES.build("uff", ethane())
    torsions = calculator.topology.torsions
    assert len(torsions) == 9
    assert float(torsions.barrier.sum()) == pytest.approx(
        ETHANE_BARRIER, rel=1e-9)


# -------------------------------------------- the parameters that set
#                                               every organic geometry

@pytest.mark.parametrize(("a", "b", "order", "expected"), [
    ("C_3", "C_3", 1.0, 1.5140),
    ("C_3", "H_", 1.0, 1.1094),
    ("C_R", "C_R", 1.5, 1.3793),
    ("O_3", "H_", 1.0, 0.9903),
    ("N_3", "H_", 1.0, 1.0444),
])
def test_published_bond_lengths(a, b, order, expected):
    assert terms.natural_bond_length(a, b, order) == pytest.approx(
        expected, abs=5e-4)


def test_the_published_carbon_carbon_force_constant():
    r0 = terms.natural_bond_length("C_3", "C_3", 1.0)
    assert terms.bond_force_constant("C_3", "C_3", r0) == \
        pytest.approx(699.5, rel=2e-3)


# ------------------------------------------- a check from outside UFF

def test_the_electrostatics_reproduce_a_textbook_madelung_constant():
    """Nothing about this involves the force field's parameters, which
    is what makes it a good test of the lattice sum underneath them."""
    from xtal import Lattice
    from xtal.core import neighbors
    from xtal.ff import ewald

    a = 5.6402
    lattice = Lattice.cubic(a)
    frac = np.array([[0, 0, 0], [.5, .5, 0], [.5, 0, .5], [0, .5, .5],
                     [.5, .5, .5], [0, 0, .5], [0, .5, 0], [.5, 0, 0]])
    charges = np.array([1.0] * 4 + [-1.0] * 4)
    pairs = neighbors.neighbor_pairs(frac, lattice, 12.0)
    energy = ewald.madelung(
        lattice.to_cart(frac), lattice.matrix, charges,
        (pairs.i, pairs.j, pairs.image),
        setup_=ewald.setup(lattice.matrix, 12.0, accuracy=1e-10))
    assert -energy * (a / 2) / 4 == pytest.approx(1.7475646, abs=1e-6)


# -------------------------------------------- an optional cross-check

def test_against_ase_when_it_is_installed():
    """ASE is an optional dependency, and when it is there its cell
    and positions are another independent statement of the geometry --
    a cheap check that the P1 expansion the calculator works on is the
    crystal everyone else would recognise."""
    ase = pytest.importorskip("ase")
    from xtal.core import p1

    structure = benzene()
    cell = p1.expand(structure)
    atoms = ase.Atoms(
        symbols=list(cell.elements),
        positions=cell.cart,
        cell=structure.lattice.matrix,
        pbc=True)
    assert len(atoms) == cell.n_atoms
    assert np.allclose(atoms.get_positions(), cell.cart)
    assert atoms.get_chemical_formula() == "C6H6"
