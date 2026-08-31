"""DFTB+ behind the Calculator interface.

DFTB+ is a binary and a set of parameter files, neither of which a
test machine can be assumed to have, so what runs here is a stand-in:
a Python script named by ``XTAL_DFTB`` that writes the
``detailed.out`` DFTB+ would have written, and a directory of empty
``.skf`` files.  That covers everything this application is
responsible for -- what it writes, what it checks before launching,
what it reads back, and the unit conversions -- and none of what
DFTB+ is responsible for.

The unit conversion is the part worth being careful about: DFTB+
answers in Hartree and Hartree/Bohr, everything above the calculator
is kcal/mol and kcal/mol/Angstrom, and a factor of 0.529 in the forces
is an optimisation that converges to the wrong geometry rather than
one that fails.
"""

import sys
from itertools import product

import numpy as np
import pytest

from xtal.ff import ENGINES
from xtal.ff.api import CalculatorError
from xtal.ff.dftb import calculator as dftb
from xtal.ff.dftb import hsd, params

#: One energy and two forces, in the layout DFTB+ writes them.
DETAILED = """
 Total Electronic energy:      -4.2000000000 H     -114.2879 eV
 Repulsive energy:              0.1220092015 H        3.3200 eV
 Total energy:                 -4.0779907985 H     -110.9678 eV
 Extrapolated to 0K:           -4.0779907985 H     -110.9678 eV
 Total Mermin free energy:     -4.0779907985 H     -110.9678 eV

 Total Forces
    1    0.000000000000    0.000000000000    0.010000000000
    2    0.000000000000    0.000000000000   -0.010000000000
"""

FAKE = '''import pathlib
pathlib.Path("detailed.out").write_text(OUTPUT)
print("DFTB+ running", flush=True)
'''


@pytest.fixture
def parameters(tmp_path):
    """A parameter directory with every pair a two-element structure
    needs."""
    directory = tmp_path / "3ob"
    directory.mkdir()
    for a, b in product(("Ti", "O", "Si", "H"), repeat=2):
        (directory / f"{a}-{b}.skf").write_text("1.0 10\n")
    return directory


@pytest.fixture
def fake_dftb(tmp_path, monkeypatch):
    script = tmp_path / "dftb+"
    script.write_text(f"#!{sys.executable}\nOUTPUT = {DETAILED!r}\n"
                      + FAKE)
    script.chmod(0o755)
    monkeypatch.setenv("XTAL_DFTB", str(script))
    return script


@pytest.fixture
def two_atoms():
    """Two atoms in a big box, so there is one force pair to check."""
    from xtal import Lattice, Structure
    return Structure.from_arrays(
        Lattice.cubic(10.0), ["Si", "H"],
        [[0.0, 0.0, 0.0], [0.0, 0.0, 0.15]], space_group="P1")


def build(structure, parameters, **options):
    return dftb.build(structure,
                      parameter_directory=str(parameters), **options)


# ------------------------------------------------- before it is launched

def test_a_missing_parameter_directory_is_a_sentence(fake_dftb,
                                                     two_atoms,
                                                     monkeypatch):
    monkeypatch.delenv(hsd.ENV_VAR, raising=False)
    with pytest.raises(CalculatorError, match="dftb.org"):
        dftb.build(two_atoms)


def test_a_missing_element_pair_is_named_before_launching(
        fake_dftb, two_atoms, tmp_path):
    """DFTB+ would fail several seconds in, naming a file rather than
    a problem."""
    thin = tmp_path / "thin"
    thin.mkdir()
    (thin / "Si-Si.skf").write_text("")

    with pytest.raises(CalculatorError) as raised:
        build(two_atoms, thin)
    assert "Si-H.skf" in str(raised.value)
    assert "element pairs" in str(raised.value)


def test_missing_parameters_checks_both_orders(tmp_path):
    directory = tmp_path / "half"
    directory.mkdir()
    for name in ("C-C.skf", "C-H.skf", "H-H.skf"):
        (directory / name).write_text("")
    assert hsd.missing_parameters(["C", "H"], directory) == ["H-C.skf"]


def nowhere(monkeypatch):
    """Point the whole search at a binary that is not installed."""
    from dataclasses import replace
    monkeypatch.setenv("XTAL_DFTB", "/nowhere/dftb+")
    monkeypatch.setattr(
        dftb, "PROGRAM",
        replace(dftb.PROGRAM, name="dftb+-that-is-not-installed"))


def test_a_missing_binary_says_how_to_install_it(two_atoms,
                                                 parameters,
                                                 monkeypatch):
    nowhere(monkeypatch)
    with pytest.raises(CalculatorError, match="conda"):
        build(two_atoms, parameters)


def test_the_engine_reports_why_it_cannot_run(monkeypatch, parameters):
    """The state an external engine will usually be in, and the one
    the panel says before the button rather than after it."""
    nowhere(monkeypatch)
    available = ENGINES.get("dftb").availability()
    assert not available
    assert "dftbplus.org" in available.reason


# ------------------------------------------------------------ the input

def test_the_input_names_every_element(two_atoms, parameters,
                                       fake_dftb):
    engine = build(two_atoms, parameters)
    text = hsd.hsd_string(engine.symbols, engine.options)
    assert 'Si = "d"' in text
    assert 'H = "s"' in text


def test_dftb3_adds_third_order_and_hubbard_derivatives(rutile,
                                                        parameters,
                                                        fake_dftb):
    engine = build(rutile, parameters, method="dftb3")
    text = hsd.hsd_string(engine.symbols, engine.options)
    assert "ThirdOrderFull = Yes" in text
    assert "HubbardDerivs" in text


def test_non_scc_says_so_and_asks_for_no_tolerance(rutile, parameters,
                                                   fake_dftb):
    engine = build(rutile, parameters, method="non-scc")
    text = hsd.hsd_string(engine.symbols, engine.options)
    assert "Scc = No" in text
    assert "SccTolerance" not in text


def test_forces_are_always_asked_for(rutile, parameters, fake_dftb):
    """The optimiser needs them, and an input without the Analysis
    block gets an energy and nothing else."""
    engine = build(rutile, parameters)
    text = hsd.hsd_string(engine.symbols, engine.options)
    assert f"{hsd.forces_keyword()} = Yes" in text


def test_the_forces_keyword_follows_the_parser_version():
    """``CalculateForces`` became ``PrintForces`` at parser 14, and a
    parser reading at 14 does not accept the old spelling quietly --
    it reports an ignored node and halts.  So the two have to move
    together, and lowering the version for an older DFTB+ has to be
    the only change that needs making."""
    assert hsd.forces_keyword(14) == "PrintForces"
    assert hsd.forces_keyword(13) == "CalculateForces"
    assert f"ParserVersion = {hsd.PARSER_VERSION}" in hsd.hsd_string(
        ("H",), dftb.DFTBOptions())


def test_an_angular_momentum_override_wins(rutile, parameters,
                                           fake_dftb):
    engine = build(rutile, parameters, angular_momentum="O=d")
    text = hsd.hsd_string(engine.symbols, engine.options)
    assert 'O = "d"' in text


def test_a_nonsense_override_is_refused():
    with pytest.raises(ValueError, match="not a shell"):
        params.parse_overrides("Cl=q")


def test_dispersion_is_off_unless_asked_for(rutile, parameters,
                                            fake_dftb):
    plain = build(rutile, parameters)
    assert "Dispersion" not in hsd.hsd_string(plain.symbols,
                                              plain.options)
    with_d3 = build(rutile, parameters, dispersion="d3")
    assert "DftD3" in hsd.hsd_string(with_d3.symbols, with_d3.options)


# -------------------------------------------------------- the k-points

def test_a_small_cell_gets_more_k_points_than_a_large_one():
    from xtal.core.lattice import Lattice
    small = hsd.mesh_for(Lattice.cubic(4.0))
    large = hsd.mesh_for(Lattice.cubic(40.0))
    assert small > large
    assert large == (1, 1, 1)


def test_an_even_mesh_is_shifted_and_an_odd_one_is_not():
    """An odd mesh already contains Gamma and must not be shifted off
    it."""
    even = "\n".join(hsd._k_points((2, 2, 2)))
    odd = "\n".join(hsd._k_points((3, 3, 3)))
    assert "0.5 0.5 0.5" in even
    assert "0.0 0.0 0.0" in odd


def test_zero_spacing_is_the_gamma_point_alone(rutile, parameters,
                                               fake_dftb):
    assert build(rutile, parameters, k_spacing=0.0).k_points == (1, 1, 1)


# ------------------------------------------------------------ the answer

def test_an_energy_comes_back_in_kcal_per_mole(two_atoms, parameters,
                                               fake_dftb):
    engine = build(two_atoms, parameters)
    result = engine.compute(engine.cell.cart,
                            two_atoms.lattice.matrix)
    assert result.energy == pytest.approx(-4.0779907985 * dftb.HARTREE)


def test_the_mermin_free_energy_is_the_one_taken():
    """It is the one whose gradient the forces are, and at a finite
    electronic temperature it is not the same number."""
    text = DETAILED.replace("Total Mermin free energy:     -4.0779907985",
                            "Total Mermin free energy:     -4.5000000000")
    assert dftb.parse_energy(text) == pytest.approx(-4.5)


def test_forces_come_back_in_kcal_per_mole_per_angstrom(
        two_atoms, parameters, fake_dftb):
    """A factor of 0.529 here is an optimisation that converges to the
    wrong geometry rather than one that fails."""
    engine = build(two_atoms, parameters)
    result = engine.compute(engine.cell.cart,
                            two_atoms.lattice.matrix)

    expected = 0.01 * dftb.HARTREE / dftb.BOHR
    assert result.forces.shape == (2, 3)
    assert result.forces[0, 2] == pytest.approx(expected)
    assert result.forces[1, 2] == pytest.approx(-expected)


def test_forces_are_read_for_every_atom():
    assert dftb.parse_forces(DETAILED, 2).shape == (2, 3)
    assert dftb.parse_forces(DETAILED, 3) is None


def test_a_second_evaluation_reuses_the_charges(two_atoms, parameters,
                                                fake_dftb):
    """Most of the cost of an SCC cycle, and the reason a DFTB+
    optimisation is affordable at all."""
    engine = build(two_atoms, parameters)
    positions, matrix = engine.cell.cart, two_atoms.lattice.matrix

    engine.compute(positions, matrix)
    assert "ReadInitialCharges" not in \
        (engine.directory / dftb.INPUT_NAME).read_text()

    engine.compute(positions, matrix)
    assert "ReadInitialCharges = Yes" in \
        (engine.directory / dftb.INPUT_NAME).read_text()


def test_the_geometry_it_is_handed_is_the_geometry_it_writes(
        two_atoms, parameters, fake_dftb):
    engine = build(two_atoms, parameters)
    moved = engine.cell.cart.copy()
    moved[1, 2] += 0.5

    engine.compute(moved, two_atoms.lattice.matrix)

    from xtal.io import read_gen
    written = read_gen(engine.directory / dftb.GEOMETRY_NAME)
    assert written.lattice.to_cart(written.frac)[1, 2] == \
        pytest.approx(moved[1, 2], abs=1e-6)


def test_the_wrong_number_of_atoms_is_refused(two_atoms, parameters,
                                              fake_dftb):
    engine = build(two_atoms, parameters)
    with pytest.raises(CalculatorError, match="built for 2 atoms"):
        engine.compute(np.zeros((3, 3)), two_atoms.lattice.matrix)


# ---------------------------------------------------- when it goes wrong

def test_a_run_that_writes_nothing_says_where_to_look(
        two_atoms, parameters, tmp_path, monkeypatch):
    silent = tmp_path / "dftb+"
    silent.write_text(f"#!{sys.executable}\nprint('nothing to say')\n")
    silent.chmod(0o755)
    monkeypatch.setenv("XTAL_DFTB", str(silent))

    engine = build(two_atoms, parameters)
    with pytest.raises(CalculatorError, match="without writing"):
        engine.compute(engine.cell.cart, two_atoms.lattice.matrix)


def test_an_unconverged_scc_is_named_as_one(two_atoms, parameters,
                                            tmp_path, monkeypatch):
    """DFTB+ writes a detailed.out with no total energy in it, which
    is not an obvious thing to read out of a file."""
    stubborn = tmp_path / "dftb+"
    stubborn.write_text(
        f"#!{sys.executable}\nimport pathlib\n"
        "pathlib.Path('detailed.out').write_text('nothing useful')\n")
    stubborn.chmod(0o755)
    monkeypatch.setenv("XTAL_DFTB", str(stubborn))

    engine = build(two_atoms, parameters)
    with pytest.raises(CalculatorError, match="SCC cycle"):
        engine.compute(engine.cell.cart, two_atoms.lattice.matrix)


def test_a_failing_binary_quotes_what_it_said(two_atoms, parameters,
                                              tmp_path, monkeypatch):
    broken = tmp_path / "dftb+"
    broken.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "print('Geometry step exceeded')\nsys.exit(1)\n")
    broken.chmod(0o755)
    monkeypatch.setenv("XTAL_DFTB", str(broken))

    engine = build(two_atoms, parameters)
    with pytest.raises(CalculatorError, match="Geometry step exceeded"):
        engine.compute(engine.cell.cart, two_atoms.lattice.matrix)


# ------------------------------------------------ what it had to assume

def test_a_guessed_angular_momentum_is_a_warning(parameters,
                                                 fake_dftb, tmp_path):
    """It does not fail -- DFTB+ takes what it is given and returns a
    plausible number -- so it has to be visible."""
    from xtal import Lattice, Structure

    for name in ("Fr-Fr.skf",):
        (parameters / name).write_text("")
    exotic = Structure.from_arrays(Lattice.cubic(10.0), ["Fr"],
                                   [[0.0, 0.0, 0.0]], space_group="P1")
    engine = build(exotic, parameters)
    assert any("angular momentum" in w for w in engine.warnings)


def test_dftb3_without_a_hubbard_derivative_is_a_warning(
        rutile, parameters, fake_dftb):
    """3ob publishes none for titanium, and second order is a
    different model rather than a coarser one."""
    engine = build(rutile, parameters, method="dftb3")
    assert any("Hubbard" in w for w in engine.warnings)


def test_scc_dftb_does_not_warn_about_hubbard_derivatives(
        rutile, parameters, fake_dftb):
    engine = build(rutile, parameters, method="scc")
    assert not any("Hubbard" in w for w in engine.warnings)


# ------------------------------------------------------------ the engine

def test_it_is_in_the_registry_with_its_options():
    engine = ENGINES.get("dftb")
    assert engine.label == "DFTB+"
    declared = engine.defaults()
    assert declared["method"] == "dftb3"
    assert "parameter_directory" in declared


def test_every_declared_option_reaches_the_calculation():
    """A field that exists in the form and not in the options is a
    control that does nothing."""
    from dataclasses import fields
    known = {f.name for f in fields(dftb.DFTBOptions)}
    for param in dftb.OPTIONS:
        assert param.name in known


def test_it_does_not_claim_an_analytic_stress():
    """DFTB+ prints one and its conventions are not something to
    guess at: a stress with the wrong sign relaxes a cell in the
    wrong direction and reports converging while it does it."""
    assert dftb.DFTBCalculator.provides_stress is False


def test_the_summary_names_the_parameter_set(two_atoms, parameters,
                                             fake_dftb):
    summary = build(two_atoms, parameters).summary()
    assert "3ob" in summary
    assert "k-points" in summary
