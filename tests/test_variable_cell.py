"""Relaxing the cell as well as the atoms.

The one thing that has to be true and is invisible when it is not: the
strain is **symmetry-adapted**.  A cubic cell has one free strain and
not six, and an optimiser that gave it six would leave the crystal
system on the first step -- with nothing complaining, and with a
lattice "constant" that is three different numbers.  So most of what is
tested here is that a cell comes back the shape it went in.

The other half is units.  An energy in kcal/mol, a volume in Angstrom
cubed and a pressure in GPa meet in one term, and that is exactly the
kind of place a factor goes missing without changing anything visible
except the answer.
"""

import numpy as np
import pytest

from tests.conftest_ff import salt
from xtal import Lattice, Structure
from xtal.commands.base import CommandStack, Host
from xtal.commands.ff import ApplyOptimizedGeometry
from xtal.core import p1
from xtal.ff import ENGINES, optimize


def hexagonal() -> Structure:
    """One site in a hexagonal cell -- the shape is the subject.

    It used to be written as two, at (1/3, 2/3, 1/4) and (2/3, 1/3,
    3/4), which P6_3/mmc generates from each other: the cell held four
    atoms where it holds two, in coincident pairs. Harmless while the
    subject was the lattice, and refused now that a force field will
    not compute an energy for a cell with two atoms in one place.
    """
    return Structure.from_arrays(
        Lattice.from_parameters(4.0, 4.0, 6.5, 90, 90, 120),
        ["C"], [[1 / 3, 2 / 3, 0.25]],
        space_group="P6_3/mmc")


def tetragonal() -> Structure:
    return Structure.from_arrays(
        Lattice.from_parameters(4.6, 4.6, 3.0, 90, 90, 90),
        ["Ti", "O"], [[0, 0, 0], [0.305, 0.305, 0.0]],
        space_group="P4_2/mnm")


def _rebuilt(structure, frac, matrix) -> Structure:
    """The same crystal, at these coordinates in this cell."""
    return Structure.from_arrays(
        Lattice(matrix), [s.element for s in structure.sites], frac,
        space_group=structure.space_group)


def _energy_of(structure, frac, matrix) -> float:
    """The energy of the *cell*, which is what has one."""
    moved = _rebuilt(structure, frac, matrix)
    return ENGINES.build("uff", moved).compute(
        p1.expand(moved).cart, matrix).energy


def relaxed(structure, **kwargs):
    calculator = ENGINES.build("uff", structure)
    return optimize.run(calculator, structure, method="lbfgs",
                        relax_cell=True, **kwargs)


# ----------------------------------------------- the strain subspace

def free_strains(structure) -> int:
    """How many independent strains this group allows.

    The rank of the projector, which is the honest count: it needs no
    table of crystal systems and it is the number the optimiser really
    has to play with.
    """
    dof = optimize.SymmetryDOF(structure, relax_cell=True)
    basis = []
    for k in range(6):
        voigt = np.zeros(6)
        voigt[k] = 1.0
        basis.append(dof.project_strain(
            optimize._from_voigt(voigt)).reshape(9))
    return int(np.linalg.matrix_rank(np.array(basis), tol=1e-8))


def test_the_number_of_free_strains_is_the_crystal_system():
    """Cubic one, hexagonal and tetragonal two, triclinic all six --
    read off the operations, not off a lookup table."""
    triclinic = Structure.from_arrays(
        Lattice.from_parameters(4, 5, 6, 80, 85, 95), ["C"],
        [[0, 0, 0]], space_group="P1")
    assert free_strains(salt()) == 1
    assert free_strains(hexagonal()) == 2
    assert free_strains(tetragonal()) == 2
    assert free_strains(triclinic) == 6


def test_a_cubic_cell_stays_cubic_across_a_whole_relaxation():
    result = relaxed(salt(), max_steps=40)
    cell = Lattice(result.matrix)
    a, b, c, alpha, beta, gamma = cell.parameters
    assert b == pytest.approx(a, abs=1e-9)
    assert c == pytest.approx(a, abs=1e-9)
    assert (alpha, beta, gamma) == (pytest.approx(90.0, abs=1e-9),) * 3
    assert a != pytest.approx(5.6402, abs=1e-3)     # it did move


def test_a_hexagonal_cell_stays_hexagonal():
    result = relaxed(hexagonal(), max_steps=40)
    a, b, c, alpha, beta, gamma = Lattice(result.matrix).parameters
    assert b == pytest.approx(a, abs=1e-9)
    assert (alpha, beta) == (pytest.approx(90.0, abs=1e-9),) * 2
    assert gamma == pytest.approx(120.0, abs=1e-9)
    assert c != pytest.approx(a)         # c is free and independent


def test_a_tetragonal_cell_keeps_its_right_angles():
    result = relaxed(tetragonal(), max_steps=30)
    a, b, c, alpha, beta, gamma = Lattice(result.matrix).parameters
    assert b == pytest.approx(a, abs=1e-9)
    assert (alpha, beta, gamma) == (pytest.approx(90.0, abs=1e-9),) * 3


# ------------------------------------------------------- is it right

def test_the_relaxed_cell_is_a_minimum_and_not_just_a_stop():
    """Scale it either way and the energy goes up.  Convergence says
    the gradient is small; this says it is a minimum of the thing the
    gradient was of."""
    structure = salt()
    result = relaxed(structure, max_steps=40)
    assert result.converged

    def energy(matrix):
        return _energy_of(structure, result.frac, matrix)

    here = energy(result.matrix)
    assert energy(result.matrix * 1.01) > here
    assert energy(result.matrix * 0.99) > here


def test_a_pure_strain_leaves_the_fractional_coordinates_alone():
    """Which is why a step reports them whether the cell is a variable
    or not, and why a relaxation in P4_2/mnm still writes back into
    P4_2/mnm."""
    structure = tetragonal()
    dof = optimize.SymmetryDOF(structure, relax_cell=True)
    x = dof.start.copy()
    x[dof.n_sites] = [0.3, 0.3, 0.1]        # some strain
    assert np.allclose(dof.to_frac(x), structure.frac)
    # ...and the atoms really did move, in cartesian space.
    assert not np.allclose(dof.positions(x), dof.positions(dof.start))


def test_the_strain_gradient_agrees_with_finite_differences():
    """The chain rule through F, checked against the energy it is the
    derivative of -- at a strained configuration, because that is
    where the two ways of writing a strain (added to F, or applied to
    the cell F already made) come apart.  Getting that backwards is a
    few percent, converges, and lands on the wrong cell."""
    structure = tetragonal()
    problem = optimize._Problem(
        ENGINES.build("uff", structure),
        optimize.SymmetryDOF(structure, relax_cell=True))
    x = problem.dof.start.copy()
    x[problem.dof.n_sites] = [0.01, 0.01, -0.02]
    _energy, gradient = problem(x)

    h = 1e-5
    for row in (problem.dof.n_sites, problem.dof.n_sites + 1):
        for column in range(3):
            up, down = x.copy(), x.copy()
            up[row, column] += h
            down[row, column] -= h
            numeric = (problem(up)[0] - problem(down)[0]) / (2 * h)
            assert numeric == pytest.approx(
                gradient[row, column],
                abs=1e-4 * max(1.0, abs(numeric)))


# -------------------------------------------------------- pressure

def test_one_kcal_per_mol_per_cubic_angstrom_is_seven_gigapascal():
    """The conversion, on its own, because it is the one place a
    factor goes missing without anything looking wrong."""
    assert 1.0 / optimize.GPA == pytest.approx(6.9477, abs=1e-3)


def test_pressure_squeezes_the_cell():
    free = relaxed(salt(), max_steps=40)
    squeezed = relaxed(salt(), pressure=10.0, max_steps=40)
    assert squeezed.converged
    assert (abs(np.linalg.det(squeezed.matrix))
            < abs(np.linalg.det(free.matrix)))


def test_at_the_relaxed_cell_the_internal_stress_balances_the_applied():
    """What a P V term *means*: at the answer, the crystal is pushing
    back exactly as hard as it is being pushed.  This is the units
    check with teeth -- a wrong conversion factor still converges, to
    the wrong cell."""
    pressure = 5.0
    structure = salt()
    result = relaxed(structure, pressure=pressure, max_steps=60)
    assert result.converged

    at_rest = _rebuilt(structure, result.frac, result.matrix)
    cell = p1.expand(at_rest)
    stress = ENGINES.build("uff", at_rest).numeric_stress(
        cell.cart, result.matrix)
    mean = float(np.trace(stress) / 3.0) / optimize.GPA
    assert mean == pytest.approx(-pressure, abs=0.2)


def test_a_converged_cell_is_one_whose_stress_is_below_the_tolerance():
    """The cell's half of convergence is the residual stress, in GPa.
    It was the strain gradient per atom, which let a framework call
    itself relaxed under a fifth of a GPa."""
    result = relaxed(salt(), max_steps=80, stress_tolerance=0.01)
    assert result.converged
    assert 0.0 < result.stress <= 0.01 or result.stress == 0.0


def test_a_tight_stress_tolerance_keeps_a_run_going():
    """Same forces, same cell -- only the stress tolerance differs, and
    the run that asks for less stress takes more steps."""
    loose = relaxed(salt(), max_steps=200, stress_tolerance=1.0)
    tight = relaxed(salt(), max_steps=200, stress_tolerance=1e-4)
    assert tight.steps >= loose.steps
    assert tight.stress <= loose.stress + 1e-12


def test_a_run_that_stopped_says_which_half_is_not_relaxed():
    result = relaxed(salt(), max_steps=1, force_tolerance=1e-9,
                     stress_tolerance=1e-9)
    assert not result.converged
    phrase = optimize.unconverged(result, 1e-9, 1e-9)
    assert "the cell" in phrase


def test_the_ewald_sum_follows_a_cell_the_pair_list_was_not_built_for():
    """The reciprocal vectors and the volume belong to the cell.  They
    were chosen once, at the first pair list, and a strain too small to
    rebuild it left the Coulomb energy that of the cell the run
    started from -- a numeric stress then differentiated the wrong
    function."""
    from xtal.ff.uff.calculator import UFFCalculator, UFFOptions
    structure = salt()
    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    options = UFFOptions(coulomb=True, charges="site")
    kept = UFFCalculator(structure, options)
    kept.compute(cell.cart, matrix)
    strain = np.eye(3) * 1.02
    fresh = UFFCalculator(structure, options)
    assert kept.compute(cell.cart @ strain, matrix @ strain).energy \
        == pytest.approx(fresh.compute(cell.cart @ strain,
                                       matrix @ strain).energy,
                         abs=1e-4)


def test_a_strained_ewald_setup_keeps_its_vectors_and_moves_them():
    """The same k-vectors, carried -- a vector that crossed the cutoff
    between two strains of 1e-4 would be a step in the energy a
    numeric stress divides by 1e-4."""
    from xtal.ff import ewald
    matrix = salt().lattice.matrix
    conf = ewald.setup(matrix)
    moved = ewald.strained(conf, matrix * 1.03)
    assert moved.n_k == conf.n_k
    assert moved.volume == pytest.approx(conf.volume * 1.03 ** 3)
    assert np.allclose(moved.k_vectors, conf.k_vectors / 1.03)
    assert ewald.strained(conf, matrix) is conf


def test_pressure_does_nothing_when_the_cell_is_fixed():
    """It is a term in the cell's energy and there is no cell
    variable, so a pressure with no ``relax_cell`` must not quietly
    change the atoms."""
    calculator = ENGINES.build("uff", salt())
    fixed = optimize.run(calculator, salt(), max_steps=5)
    pressed = optimize.run(calculator, salt(), pressure=50.0,
                           max_steps=5)
    assert fixed.matrix is None and pressed.matrix is None
    assert np.allclose(fixed.frac, pressed.frac)


# ------------------------------------------- what comes back out

def test_a_fixed_cell_run_says_so_by_carrying_no_matrix():
    result = optimize.run(ENGINES.build("uff", salt()), salt(),
                          max_steps=3)
    assert result.matrix is None
    assert result.volume_change == 0.0
    assert "cell" not in result.summary()


def test_every_step_carries_the_cell_it_was_computed_in():
    structure = salt()
    seen = [step.matrix for step in optimize.steps(
        ENGINES.build("uff", structure), structure, relax_cell=True,
        max_steps=3)]
    assert all(m is not None for m in seen)
    assert not np.allclose(seen[0], seen[-1])       # it moved
    assert np.allclose(seen[0], structure.lattice.matrix)


def test_the_result_reports_the_volume_change():
    result = relaxed(salt(), max_steps=40)
    assert result.volume_change != 0.0
    assert "% by volume" in result.summary()


def test_the_cell_travels_with_the_coordinates_in_one_command():
    """Two commands would mean a Ctrl+Z that put the atoms back into a
    cell they were never relaxed in."""
    structure = salt()
    before = structure.lattice.matrix.copy()
    result = relaxed(structure, max_steps=40)

    host = Host(structure)
    stack = CommandStack()
    stack.push(ApplyOptimizedGeometry.from_result(result), host)
    assert np.allclose(host.structure.lattice.matrix, result.matrix)
    assert not np.allclose(host.structure.lattice.matrix, before)

    stack.undo(host)
    assert np.allclose(host.structure.lattice.matrix, before)
    stack.redo(host)
    assert np.allclose(host.structure.lattice.matrix, result.matrix)


def test_the_trajectory_frames_carry_the_relaxed_cell(tmp_path):
    """A trajectory whose cell never changed would show the atoms of a
    variable-cell run rattling inside a box they were not relaxed
    in."""
    from xtal.ff.record import RunRecorder
    from xtal.io import write_cif
    from xtal.io.trajectory import read_trajectory
    from xtal.workspace import Workspace

    structure = salt()
    path = tmp_path / "salt.cif"
    write_cif(structure, path)
    entry = Workspace.create(tmp_path / "ws").add_structure(path)
    calculator = ENGINES.build("uff", structure)
    with RunRecorder(entry.next_run("uff", "optimise"), structure,
                     calculator, engine="uff") as recorder:
        for step in optimize.steps(calculator, structure,
                                   relax_cell=True, max_steps=5):
            recorder.step(step)

    frames = read_trajectory(entry.runs()[0].trajectory_path)
    assert frames.n_frames >= 2
    first = frames[0].lattice.matrix
    last = frames[-1].lattice.matrix
    assert not np.allclose(first, last)
    assert np.allclose(first, structure.lattice.matrix)
