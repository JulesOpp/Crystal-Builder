"""EQeq charges.

The numbers that can be checked against something outside this code
are MOF-5's: the authors' own program, run on IRMOF-1, gives zinc
+1.211, the central oxygen -0.968 and the carboxylate oxygens -0.483;
and the same program, run on the shipped COD MOF-5, gives the charges
in ``tests/data/eqeq/mof5_cod_authors_program.json``.
Everything else here pins a piece of the method that a plausible
answer would not reveal was missing -- a charge centre not moved back,
hydrogen's affinity left at the measured value, a table drifted from
its sources.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from xtal.core import p1
from xtal.ff import ewald
from xtal.ff.charges import eqeq

ROOT = Path(__file__).resolve().parents[1]


def _mof5_cell():
    from xtal.io import read_cif
    return p1.expand(read_cif(ROOT / "resources" / "samples"
                              / "MOF-5.cif"))


def _by_element(cell, charges):
    elements = np.array(cell.elements)
    return {e: charges[elements == e] for e in set(cell.elements)}


def test_eqeq_charges_sum_to_the_structure_charge(halite, quartz):
    for structure in (halite, quartz):
        cell = p1.expand(structure)
        for total in (0.0, 1.0):
            charges, _note = eqeq.equilibrate(cell, total_charge=total)
            assert charges.sum() == pytest.approx(total, abs=1e-9)


def test_the_authors_program_gives_the_same_charges_on_the_same_cell():
    """The check that can tell a small error from none.  The authors'
    own program, compiled and run on the shipped COD MOF-5 (see
    ``about`` in the data file), against this code on the same atoms:
    measured to agree within 0.00016 e everywhere.  A thousandth
    leaves room for the NIST table being newer than theirs and for
    their truncated Ewald sum, and fails anything that matters."""
    import json

    reference = json.loads((ROOT / "tests" / "data" / "eqeq"
                            / "mof5_cod_authors_program.json")
                           .read_text())["charges"]
    cell = _cod_cell("MOF-5.cif")
    charges, _note = eqeq.equilibrate(cell)

    assert len(charges) == len(reference)
    assert charges == pytest.approx(np.array(reference), abs=1e-3)


def test_mof5_zinc_comes_out_positive_and_near_the_published_charge():
    """Against the paper's published numbers, which are for the
    authors' IRMOF-1 geometry and not this file's.  The 0.05 is that
    difference in geometry -- on the same cell the program and this
    code agree to 0.0002 (the test above) -- so this one pins sign and
    size, and the one above pins the method."""
    cell = _mof5_cell()
    charges, _note = eqeq.equilibrate(cell)
    by = _by_element(cell, charges)

    assert by["Zn"] == pytest.approx(1.211, abs=0.05)
    assert np.ptp(by["Zn"]) < 1e-6
    oxygen = np.sort(np.unique(np.round(by["O"], 4)))
    assert oxygen[0] == pytest.approx(-0.968, abs=0.05)
    assert oxygen[-1] == pytest.approx(-0.483, abs=0.05)
    assert np.all(by["H"] > 0)


def test_the_charges_do_not_depend_on_the_ewald_split(quartz):
    cell = p1.expand(quartz)
    matrix = cell.lattice.matrix
    answers = [
        eqeq.equilibrate(cell, setup_=ewald.setup(
            matrix, real_cutoff=cutoff, accuracy=1e-10))[0]
        for cutoff in (8.0, 14.0)]
    np.testing.assert_allclose(*answers, atol=1e-7)


def test_a_charge_centre_is_expanded_about_and_moved_back_to_neutral():
    """Zinc about +2: chi and J from its second and third ionisation
    energies, then chi shifted by 2 J so that the solver's Q = 0 is
    the neutral atom again."""
    table = eqeq.table()["Zn"]
    ie2, ie3 = table[2], table[3]
    chi, hardness = eqeq.parameters("Zn")
    assert hardness == pytest.approx(ie3 - ie2)
    assert chi == pytest.approx((ie3 + ie2) / 2 - 2 * (ie3 - ie2))


def test_hydrogen_uses_the_papers_affinity_and_not_the_measured_one():
    """With the measured 0.754 eV every hydrogen in a framework takes
    far too much charge."""
    chi, hardness = eqeq.parameters("H")
    ie1 = eqeq.table()["H"][1]
    assert hardness == pytest.approx(ie1 - eqeq.HYDROGEN_AFFINITY)
    assert chi == pytest.approx((ie1 + eqeq.HYDROGEN_AFFINITY) / 2)


def test_an_anion_that_is_not_bound_reads_as_zero_affinity():
    """Nitrogen's blank in the table is not missing data; its anion
    does not hold the electron."""
    assert eqeq.table()["N"][0] == 0.0
    chi, hardness = eqeq.parameters("N")
    assert hardness == pytest.approx(eqeq.table()["N"][1])


def test_two_atoms_on_top_of_each_other_meet_at_their_hardness():
    """The overlap term is what keeps 1/r finite as two atoms merge,
    at lambda sqrt(J_i J_j) rather than infinity.  MOF-5's charges
    barely notice it -- its atoms are bonded, not merging -- so
    without this nothing would say it had gone."""
    from xtal import Lattice

    matrix = Lattice.cubic(30.0).matrix
    hardness = np.array([eqeq.parameters(e)[1] for e in ("C", "O")])
    a = np.sqrt(hardness.prod()) / eqeq.qeq.COULOMB_EV
    for r in (1e-3, 0.3):
        cart = np.array([[5.0, 5.0, 5.0], [5.0, 5.0, 5.0 + r]])
        overlap = eqeq._overlap(cart, matrix, hardness)[0, 1]
        exact = np.exp(-(a * r) ** 2) * (2 * a - a * a * r - 1 / r)
        assert overlap == pytest.approx(exact, rel=1e-9)
    assert 1 / 1e-3 + eqeq._overlap(
        np.array([[5.0, 5, 5], [5, 5, 5.001]]), matrix,
        hardness)[0, 1] == pytest.approx(2 * a, rel=1e-2)


def test_a_dummy_atom_is_refused_by_name():
    with pytest.raises(ValueError, match="'X'"):
        eqeq.parameters("X")


def test_the_uff_calculator_takes_its_charges_from_eqeq(halite):
    from xtal.ff.uff.calculator import UFFCalculator, UFFOptions

    calculator = UFFCalculator(
        halite, UFFOptions(coulomb=True, charges="eqeq"))
    elements = np.array(calculator.cell.elements)
    assert np.all(calculator.charges[elements == "Na"] > 0.5)
    assert calculator.charges.sum() == pytest.approx(0.0, abs=1e-9)
    assert any("EQeq" in w for w in calculator.warnings)


def test_the_ionisation_table_is_what_the_script_writes():
    """The table ships in the package and the two downloads it was
    written from are kept in tests/data; if someone edits the table
    by hand, or refreshes one without the other, this is what
    says so."""
    spec = importlib.util.spec_from_file_location(
        "eqeq_table", ROOT / "scripts" / "eqeq_table.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    shipped = (ROOT / "xtal" / "ff" / "charges" / "data"
               / "ionization.csv").read_text(encoding="utf-8")
    assert script.written() == shipped


# ------------------------------------------------------ charge centres
#
# The centre is the charge a metal is expanded about, and it decides
# the answer: Ongari et al. (J. Chem. Theory Comput. 2019, 15, 382)
# found EQeq "heavily affected" by it over 2338 MOFs, and the choice
# "mandatory" for alkali metals.  A metal left at 0 is expanded about
# the neutral atom, where its curve is soft, and runs away.

def _cod_cell(name):
    from xtal.io import read_cif
    return p1.expand(read_cif(ROOT / "resources" / "samples" / "cod"
                              / name))


def test_aluminium_is_expanded_about_three_and_stays_possible():
    """Al-soc-MOF-1, one of the shipped COD frameworks.  With only the
    paper's seven metals given a centre, aluminium came out at +6.33 --
    more than the three electrons it has to lose -- and its oxygens at
    -3.57."""
    cell = _cod_cell("Al-soc-MOF-1.cif")
    charges, note = eqeq.equilibrate(cell)
    by = _by_element(cell, charges)

    assert eqeq.CHARGE_CENTRES["Al"] == 3
    assert 0 < by["Al"].max() <= 3
    assert by["O"].min() >= -2
    assert "beyond" not in note


def test_every_metal_has_a_centre_and_the_papers_seven_are_its_own():
    """Every metal the table has energies for is expanded about its
    common oxidation state.  The seven the paper gave are kept as it
    gave them -- vanadium at +4, where Open Babel has +3 -- so the
    charges of every framework that already worked do not move."""
    paper = {"Mg": 2, "V": 4, "Co": 2, "Ni": 2, "Cu": 2, "Zn": 2,
             "Zr": 4}
    for element, centre in paper.items():
        assert eqeq.CHARGE_CENTRES[element] == centre
    for element in ("Na", "K", "Ca", "Al", "Ti", "Cr", "Mn", "Fe",
                    "Cd", "In", "Eu", "La", "Ce", "Hf", "Pb", "Bi"):
        assert eqeq.CHARGE_CENTRES.get(element, 0) > 0, element
    for element in ("H", "C", "N", "O", "F", "Cl", "S", "P", "Si"):
        assert eqeq.CHARGE_CENTRES.get(element, 0) == 0, element


def test_a_centre_can_be_set_for_the_framework_in_hand():
    """The table is a common oxidation state and a framework need not
    be common: MIL-88B is chromium(III), and the table's +2 is the
    usual one.  The method leaves the choice to the user -- the
    authors list guessing it as a feature they did not write -- so it
    can be given, and it changes the answer."""
    cell = _cod_cell("MIL-88B.cif")
    usual, _ = eqeq.equilibrate(cell)
    as_is, note = eqeq.equilibrate(cell, centres={"Cr": 3})
    chromium = np.array(cell.elements) == "Cr"

    assert not np.allclose(usual[chromium], as_is[chromium])
    assert "Cr +3" in note


def test_a_centre_the_table_cannot_expand_about_is_refused():
    with pytest.raises(ValueError, match="Zn"):
        eqeq.parameters("Zn", centre=40)


def test_a_charge_no_atom_could_carry_is_said(quartz):
    """Silicon has no centre in any EQeq table -- it is not a metal --
    and in quartz it runs away the same way aluminium did, to more
    than the four electrons it has.  Nothing can fix that inside the
    method; what must not happen is showing the number as though it
    meant something."""
    cell = p1.expand(quartz)
    charges, note = eqeq.equilibrate(cell)

    silicon = charges[np.array(cell.elements) == "Si"]
    assert silicon.max() > 4                    # the case, still there
    assert "Si +5.69 (at most +4)" in note
    assert "expand Si about" in note           # the cause, not the O
    assert "expand O" not in note


def test_the_possible_range_is_the_nearest_closed_shells():
    """An atom cannot lose more than the electrons outside the
    noble-gas core beneath it, nor gain more than the next one holds."""
    assert eqeq.possible_charges("Na") == (-7, 1)
    assert eqeq.possible_charges("Al") == (-5, 3)
    assert eqeq.possible_charges("O") == (-2, 6)
    assert eqeq.possible_charges("H") == (-1, 1)
    assert eqeq.possible_charges("Fe") == (-10, 8)
