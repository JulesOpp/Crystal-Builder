"""The GFN family behind the Calculator interface.

Two binaries and neither of them assumable on a test machine, so what
runs here is a pair of stand-ins: a Python script named by
``XTAL_TBLITE`` that writes the ``tblite.json`` tblite would have
written, and one named by ``XTAL_XTB`` that writes the ``.engrad``
xtb would have.  That covers what this application is responsible for
-- which program it picks, what it puts on the command line, what it
reads back, and the unit conversions -- and none of what either
program is responsible for.

Two things here are not shaped like the DFTB+ tests, and both are
about there being two programs behind one entry.  Availability is
answered *per method*: GFN-FF on a machine with only tblite is
unavailable while GFN2 on the same machine is not, so the check takes
the options and a test that ignored them would pass while the panel
greyed out the wrong row.  And the reason GFN2 cannot go through xtb
is not that xtb lacks it -- it is that its periodic code does, which
this application only ever finds out the hard way, after the geometry
is written and the process launched.
"""

import json
from dataclasses import fields, replace

import numpy as np
import pytest

from tests.conftest_program import write_program
from xtal.core import p1
from xtal.ff import ENGINES
from xtal.ff.api import CalculatorError
from xtal.ff.xtb import calculator as xtb

#: One energy and two atoms' worth of gradient, in Hartree and
#: Hartree/Bohr, in tblite's own JSON layout.
TBLITE_JSON = {
    "version": "0.7.0",
    "energy": -4.0779907985,
    "gradient": [0.0, 0.0, 0.01, 0.0, 0.0, -0.01],
    "virial": [0.0] * 9,
}

FAKE_TBLITE = '''import json, pathlib, sys
pathlib.Path("argv.txt").write_text(" ".join(sys.argv[1:]))
pathlib.Path("tblite.json").write_text(json.dumps(OUTPUT))
print("tblite running", flush=True)
'''

#: The same numbers in xtb's ``.engrad``: a comment, the atom count, a
#: comment, the energy, a comment, then 3N components one per line.
ENGRAD = """#
# Number of atoms
#
         2
#
# The current total energy in Eh
#
     -4.0779907985
#
# The current gradient in Eh/bohr
#
       0.000000000000
       0.000000000000
       0.010000000000
       0.000000000000
       0.000000000000
      -0.010000000000
#
# The atomic numbers and current coordinates in Bohr
#
   8     0.0000000    0.0000000    0.0000000
   8     0.0000000    0.0000000    3.7794520
"""

FAKE_XTB = '''import pathlib, sys
pathlib.Path("argv.txt").write_text(" ".join(sys.argv[1:]))
pathlib.Path("geo.engrad").write_text(OUTPUT)
print("xtb running", flush=True)
'''


@pytest.fixture
def fake_tblite(tmp_path, monkeypatch):
    script = write_program(tmp_path, "tblite",
                           f"OUTPUT = {TBLITE_JSON!r}\n" + FAKE_TBLITE)
    monkeypatch.setenv("XTAL_TBLITE", str(script))
    return script


@pytest.fixture
def fake_xtb(tmp_path, monkeypatch):
    script = write_program(tmp_path, "xtb",
                           f"OUTPUT = {ENGRAD!r}\n" + FAKE_XTB)
    monkeypatch.setenv("XTAL_XTB", str(script))
    return script


@pytest.fixture
def two_atoms():
    """Two atoms in a big box, so there is one force pair to check."""
    from xtal.core.lattice import Lattice
    from xtal.core.site import Site
    from xtal.core.spacegroup import SpaceGroup
    from xtal.core.structure import Structure
    lattice = Lattice.from_parameters(20.0, 20.0, 20.0, 90.0, 90.0, 90.0)
    return Structure(
        lattice=lattice,
        sites=[Site("O", (0.5, 0.5, 0.5)), Site("O", (0.5, 0.5, 0.6))],
        space_group=SpaceGroup.p1())


def nowhere(monkeypatch, *keys: str):
    """Make the named programs -- or all of them -- unfindable.

    The name has to be replaced as well as the variable unset: a
    developer's machine may well have tblite or xtb on PATH, and a
    test that only pointed the environment somewhere empty would then
    quietly assert nothing on the one machine that has the real
    thing.
    """
    keys = keys or tuple(p.setting.rsplit("/", 1)[-1]
                         for p in xtb.PROGRAMS)
    replaced = []
    for program in xtb.PROGRAMS:
        key = program.setting.rsplit("/", 1)[-1]
        if key not in keys:
            replaced.append(program)
            continue
        monkeypatch.setenv(program.env_var, f"/nowhere/{key}")
        replaced.append(
            replace(program, name=f"{program.name}-not-installed"))
    monkeypatch.setattr(xtb, "PROGRAMS", tuple(replaced))


def run(structure, **options):
    calculator = ENGINES.build("xtb", structure, **options)
    cell = p1.expand(structure)
    return calculator, calculator.compute(cell.cart,
                                          structure.lattice.matrix)


# ------------------------------------------------------ which program

def test_gfnff_is_xtbs_alone_and_says_so(fake_tblite, monkeypatch):
    """tblite is the tight-binding half of the family and has no
    force field in it, so a machine with tblite and no xtb can run two
    of the three methods.  The panel greys out the third naming what
    is missing, and that sentence is this."""
    nowhere(monkeypatch, "xtb")
    engine = ENGINES.get("xtb")
    assert engine.availability(method="gfn2")
    assert engine.availability(method="gfn1")
    unavailable = engine.availability(method="gfnff")
    assert not unavailable
    assert "xtb" in unavailable.reason.lower()


def test_the_method_decides_which_binary_runs(fake_tblite, fake_xtb,
                                              two_atoms):
    """One program per method, so there is no control offering the
    choice -- it could only ever narrow it to nothing.

    Both of the tight-binding methods are tblite's: xtb has GFN2 and
    its periodic code does not, stopping with "Multipoles not
    available with PBC", and xtb's periodic GFN1 fails to diagonalise
    a two-atom silicon cell and segfaults on MOF-5 after reporting
    its own SCC converged.  GFN-FF is xtb's, because tblite has no
    force field.
    """
    for method in ("gfn1", "gfn2"):
        calculator, _ = run(two_atoms, method=method)
        assert calculator.program is xtb.TBLITE
        assert "tblite" in calculator.summary()
    calculator, _ = run(two_atoms, method="gfnff")
    assert calculator.program is xtb.XTB


def test_a_missing_binary_says_how_to_install_it(monkeypatch,
                                                 two_atoms):
    nowhere(monkeypatch)
    with pytest.raises(CalculatorError, match="conda"):
        run(two_atoms, method="gfn2")


def test_the_engine_reports_why_it_cannot_run(monkeypatch):
    """The state an external engine will usually be in, and the one
    the panel says before the button rather than after it."""
    nowhere(monkeypatch)
    available = ENGINES.get("xtb").availability(method="gfn2")
    assert not available
    assert "github.com/tblite" in available.reason


# ------------------------------------------------------- what it sends

def test_the_command_line_carries_the_method(fake_tblite, two_atoms):
    calculator, _ = run(two_atoms, method="gfn1", charge=-1.0)
    argv = (calculator.directory / "argv.txt").read_text()
    assert "--method gfn1" in argv
    assert "--charge -1" in argv
    assert "--json" in argv and "--grad" in argv


def test_xtb_gets_its_own_spelling_of_the_method(fake_xtb, two_atoms):
    """``--gfnff`` is not ``--method gfnff``; the two programs agree
    about almost nothing on the command line."""
    calculator, _ = run(two_atoms, method="gfnff")
    argv = (calculator.directory / "argv.txt").read_text()
    assert "--gfnff" in argv
    assert "--grad" in argv


def test_the_geometry_is_written_where_the_program_will_find_it(
        fake_tblite, two_atoms):
    calculator, _ = run(two_atoms, method="gfn2")
    written = (calculator.directory / "geo.gen").read_text()
    assert written.split()[0] == "2"
    assert "O" in written


# ------------------------------------------------------ what it reads

def test_the_units_come_back_in_kcal(fake_tblite, two_atoms):
    """Hartree and Hartree/Bohr in, kcal/mol and kcal/mol/Angstrom
    out.  A missing factor of 0.529 in the forces is an optimisation
    that converges to the wrong geometry rather than one that
    fails."""
    _, result = run(two_atoms, method="gfn2")
    assert result.energy == pytest.approx(-4.0779907985 * xtb.HARTREE)
    expected = 0.01 * xtb.HARTREE / xtb.BOHR
    assert result.forces[0, 2] == pytest.approx(-expected)
    assert result.forces[1, 2] == pytest.approx(expected)


def test_both_formats_are_read_as_the_same_numbers(tmp_path):
    """Two formats, one quantity.  The two canned outputs above hold
    the same energy and the same gradient, so a difference here is a
    parser and not a program -- and the methods no longer share a
    binary, so nothing else would compare them."""
    (tmp_path / "tblite.json").write_text(json.dumps(TBLITE_JSON))
    (tmp_path / "geo.engrad").write_text(ENGRAD)
    from_json = xtb.read_tblite_json(tmp_path / "tblite.json", 2)
    from_engrad = xtb.read_engrad(tmp_path / "geo.engrad", 2)
    assert from_json[0] == pytest.approx(from_engrad[0])
    assert np.allclose(from_json[1], from_engrad[1])


def test_no_stress_is_claimed(fake_tblite, two_atoms):
    """tblite writes a virial and the obvious conversion of it
    disagrees with a numeric stress by ten per cent on quartz.  Until
    that is understood the twelve extra evaluations are the honest
    price -- see the module docstring."""
    calculator, result = run(two_atoms, method="gfn2")
    assert not calculator.provides_stress
    assert result.stress is None


def test_an_energy_without_a_gradient_is_a_sentence(tmp_path):
    path = tmp_path / "tblite.json"
    path.write_text(json.dumps({"energy": -1.0}))
    with pytest.raises(CalculatorError, match="no gradient"):
        xtb.read_tblite_json(path, 2)


def test_a_run_that_wrote_nothing_points_at_its_own_log(tmp_path):
    with pytest.raises(CalculatorError, match="xtb.out"):
        xtb.read_tblite_json(tmp_path / "tblite.json", 2)


def test_an_engrad_for_the_wrong_number_of_atoms_is_refused(tmp_path):
    path = tmp_path / "geo.engrad"
    path.write_text(ENGRAD)
    with pytest.raises(CalculatorError, match="answered for 2 atoms"):
        xtb.read_engrad(path, 3)


# ------------------------------------------------- against the real thing

def installed(key: str):
    """The real binary, if this machine has it."""
    for program in xtb.PROGRAMS:
        if program.setting.endswith(key):
            return program.locate()
    return None                                     # pragma: no cover


@pytest.mark.slow
@pytest.mark.parametrize("method,program", [
    ("gfn2", "tblite"), ("gfn1", "tblite"), ("gfnff", "xtb")])
def test_a_real_run_accepts_the_command_line_we_send(method, program,
                                                     two_atoms):
    """The stand-ins above take any flags at all, which is the one
    thing they cannot check.  ``--gfn2`` instead of ``--method gfn2``
    is a spelling neither program complains about until it is run, and
    then it fails with a Fortran backtrace rather than a sentence.

    Skipped where the binary is not installed, which is most machines
    and all of CI.
    """
    if installed(program) is None:
        pytest.skip(f"{program} is not installed")
    _, result = run(two_atoms, method=method)
    assert np.isfinite(result.energy)
    assert result.forces.shape == (2, 3)
    assert np.all(np.isfinite(result.forces))
    # Two atoms and nothing else: the forces are equal and opposite,
    # whatever the method thinks the energy is.  GFN-FF's is positive
    # here -- it is a force field and its zero is a reference state,
    # not a bare nucleus.
    assert np.allclose(result.forces[0], -result.forces[1], atol=1e-6)


def test_a_crash_is_told_apart_from_a_refusal(tmp_path, monkeypatch):
    """"exited with status -11" is a sentence only somebody who
    already knows Python's signal convention can read, and the
    difference matters: a non-zero status is the program rejecting
    what it was given and a signal is the program falling over.  Only
    one of those is worth changing an option over.

    tblite 0.6.0 does exactly this on a periodic GFN2 cell, on two
    atoms as readily as on four hundred.

    The stand-in dies of SIGKILL rather than the SIGSEGV tblite gives:
    a real segmentation fault makes macOS write a crash report and put
    a "Python quit unexpectedly" window in front of whoever ran the
    suite, every run.  The path through ``_how_it_died`` is the same
    for any signal, and the SIGSEGV spelling is checked directly below.
    """
    script = write_program(
        tmp_path, "tblite",
        "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n")
    monkeypatch.setenv("XTAL_TBLITE", str(script))
    from xtal.core.lattice import Lattice
    from xtal.core.site import Site
    from xtal.core.spacegroup import SpaceGroup
    from xtal.core.structure import Structure
    structure = Structure(
        lattice=Lattice.from_parameters(9.0, 9.0, 9.0, 90.0, 90.0, 90.0),
        sites=[Site("O", (0.0, 0.0, 0.0))],
        space_group=SpaceGroup.p1())
    with pytest.raises(CalculatorError, match="killed by SIGKILL"):
        run(structure, method="gfn2")


def test_a_segmentation_fault_is_named_as_one():
    """-11 is what Python reports for the SIGSEGV tblite 0.6.0 dies of;
    the sentence has to say so without a real crash to produce it."""
    from xtal.ff.xtb.calculator import _how_it_died
    assert _how_it_died(-11) == "was killed by SIGSEGV"
    assert _how_it_died(1) == "exited with status 1"


# --------------------------------------------------------- the registry

def test_the_engine_is_registered_and_offers_its_options():
    engine = ENGINES.get("xtb")
    assert engine.label == "xTB (GFN)"
    assert engine.defaults()["method"] == "gfn2"
    assert "types" not in engine.provides


def test_every_field_in_the_form_is_one_the_calculation_reads():
    """A field in the form that is not in the options is a control
    that does nothing."""
    known = {f.name for f in fields(xtb.XTBOptions)}
    assert {p.name for p in xtb.OPTIONS} <= known
