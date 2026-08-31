"""CSSR: the format Zeo++ reads.

The tests that matter here are not about the columns.  They are about
the two things a wrong CSSR would quietly get wrong: that the whole
cell is written and not the asymmetric unit -- Zeo++ ignores the space
group field and would compute the porosity of two atoms in a box --
and that the eight connectivity zeros are present, because without
them the charge lands in a field that means something else.
"""

import numpy as np
import pytest

from xtal.core.p1 import expand
from xtal.io import FORMATS, cssr_string, read_cssr, write_cssr


def header(text: str) -> list[str]:
    return text.splitlines()[:4]


def atom_lines(text: str) -> list[str]:
    return [line for line in text.splitlines()[4:] if line.strip()]


def test_the_whole_cell_is_written_not_the_asymmetric_unit(quartz):
    """Quartz is two sites and nine atoms.  Zeo++ reads what it is
    given as the whole crystal, so writing two would not be a lossy
    export -- it would be a different structure."""
    text = cssr_string(quartz)
    assert quartz.n_sites == 2
    assert len(atom_lines(text)) == expand(quartz).n_atoms == 9


def test_the_cell_is_the_first_two_lines(quartz):
    lines = header(cssr_string(quartz))
    a, b, c = (float(v) for v in lines[0].split())
    alpha, beta, gamma = (float(v) for v in lines[1].split()[:3])
    assert (a, b, c) == pytest.approx(quartz.lattice.parameters[:3],
                                      abs=1e-4)
    assert (alpha, beta, gamma) == pytest.approx(
        quartz.lattice.parameters[3:], abs=1e-3)


def test_it_says_P1_whatever_the_group_was(quartz):
    """Because that is what the file now contains."""
    assert "SPGR =  1 P 1" in cssr_string(quartz)


def test_the_atom_count_line_carries_the_cartesian_flag(rutile):
    """The reader takes two tokens off this line whatever they are, so
    a missing flag shifts every field after it."""
    count, flag = header(cssr_string(rutile))[2].split()[:2]
    assert int(count) == expand(rutile).n_atoms
    assert flag == "0"


def test_the_name_is_a_line_of_its_own(rutile):
    """It is read with getline, so a newline in it would shift every
    atom by one line."""
    assert header(cssr_string(rutile, "some name"))[3] == "0 some name"
    assert header(cssr_string(rutile, "two\nlines"))[3] == "0 two lines"


def test_every_atom_line_has_the_eight_connectivity_slots(rutile):
    for line in atom_lines(cssr_string(rutile)):
        parts = line.split()
        assert len(parts) == 14                 # id, type, xyz, 8, charge
        assert parts[5:13] == ["0"] * 8


def test_fractions_are_inside_the_cell(quartz):
    for line in atom_lines(cssr_string(quartz)):
        for value in (float(v) for v in line.split()[2:5]):
            assert 0.0 <= value < 1.0


def test_a_charge_survives(rutile):
    rutile.sites[0].charge = 2.4
    line = atom_lines(cssr_string(rutile))[0]
    assert float(line.split()[-1]) == pytest.approx(2.4)


# ------------------------------------------------------------- reading

def test_a_round_trip_keeps_the_atoms(quartz, tmp_path):
    path = write_cssr(quartz, tmp_path / "quartz.cssr")
    back = read_cssr(path)

    assert expand(back).n_atoms == expand(quartz).n_atoms
    assert np.allclose(np.sort(expand(back).frac, axis=0),
                       np.sort(expand(quartz).frac, axis=0), atol=1e-4)
    assert back.lattice.parameters == pytest.approx(
        quartz.lattice.parameters, abs=1e-3)


def test_it_reads_back_as_P1(quartz, tmp_path):
    """Not because the symmetry is unknowable, but because it is not
    in the file: claiming P3_221 would be inventing it."""
    back = read_cssr(write_cssr(quartz, tmp_path / "q.cssr"))
    assert len(back.space_group.operations) == 1


def test_the_registry_knows_the_extension(rutile, tmp_path):
    path = tmp_path / "rutile.cssr"
    FORMATS.write(rutile, path)
    assert FORMATS.read(path).n_sites == expand(rutile).n_atoms


def test_cartesian_coordinates_are_read(rutile, tmp_path):
    """Zeo++ writes them itself, so a file we get back may have
    them."""
    a = rutile.lattice.parameters[0]
    path = tmp_path / "cart.cssr"
    path.write_text(
        f"\t\t\t\t{a} {a} 3.0\n"
        f"\t\t90 90 90  SPGR =  1 P 1\t\t OPT = 1\n"
        f"1   1\n"
        f"0 cartesian\n"
        f" 1 Ti {a / 2:.4f} 0.0000 0.0000 "
        f" 0 0 0 0 0 0 0 0   0.0000\n")
    back = read_cssr(path)
    assert back.sites[0].frac == pytest.approx([0.5, 0.0, 0.0],
                                               abs=1e-6)


def test_a_file_with_no_cell_is_refused(tmp_path):
    path = tmp_path / "bad.cssr"
    path.write_text("not\na\ncssr\nfile\n")
    with pytest.raises(ValueError, match="cell"):
        read_cssr(path)


def test_a_file_that_is_too_short_is_refused(tmp_path):
    path = tmp_path / "short.cssr"
    path.write_text("10 10 10\n90 90 90\n")
    with pytest.raises(ValueError, match="four header lines"):
        read_cssr(path)
