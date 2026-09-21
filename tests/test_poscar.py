"""VASP's POSCAR and CONTCAR: a format with no tags in it.

Everything is positional, so every test here is really about counting
lines correctly, and the two that are not are about the things the
format leaves out: the species names, which live in a file that is not
this one, and the symmetry, which is not written at all.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1
from xtal.io import FORMATS

BODY = """  4.0 0.0 0.0
  0.0 4.0 0.0
  0.0 0.0 4.0
"""


def _poscar(tmp_path, text, name="POSCAR"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("name", ["POSCAR", "CONTCAR"])
def test_a_file_named_poscar_is_found_without_a_suffix(tmp_path, name):
    """Path("POSCAR").suffix is "", so matching on the suffix alone
    could never find one. The registry matches the whole name first."""
    assert FORMATS.by_extension(tmp_path / name).name == "poscar"


def test_a_suffix_still_wins_over_a_stem(tmp_path):
    """POSCAR.cif is a CIF whatever its stem says."""
    assert FORMATS.by_extension(tmp_path / "POSCAR.cif").name == "cif"


def test_direct_coordinates_are_read_as_fractional(tmp_path):
    path = _poscar(tmp_path, "t\n1.0\n" + BODY + " Na Cl\n 1 1\nDirect\n"
                   " 0.0 0.0 0.0\n 0.5 0.5 0.5\n")
    structure = FORMATS.read(path)
    assert [s.element for s in structure.sites] == ["Na", "Cl"]
    assert np.allclose(structure.sites[1].frac, [0.5, 0.5, 0.5])


def test_cartesian_coordinates_are_converted(tmp_path):
    """The same crystal, written the other way the format allows."""
    path = _poscar(tmp_path, "t\n1.0\n" + BODY + " Na Cl\n 1 1\n"
                   "Cartesian\n 0.0 0.0 0.0\n 2.0 2.0 2.0\n")
    assert np.allclose(FORMATS.read(path).sites[1].frac, [0.5, 0.5, 0.5])


def test_a_negative_scale_is_a_volume_and_not_a_length(tmp_path):
    """VASP reads it as the cell volume in cubic angstroms. A reader
    that took it for a length would give a cell 64 times too small
    here, and nothing in the file would say so."""
    path = _poscar(tmp_path, "t\n-27.0\n" + BODY + " Na\n 1\nDirect\n"
                   " 0.0 0.0 0.0\n")
    assert FORMATS.read(path).lattice.volume == pytest.approx(27.0)


def test_selective_dynamics_does_not_shift_every_atom_by_a_line(
        tmp_path):
    """One optional word between the counts and the coordinates, and
    every position after it is read from the wrong line."""
    path = _poscar(tmp_path, "t\n1.0\n" + BODY + " Na Cl\n 1 1\n"
                   "Selective dynamics\nDirect\n"
                   " 0.0 0.0 0.0  T T T\n 0.5 0.5 0.5  F F F\n")
    structure = FORMATS.read(path)
    assert len(structure.sites) == 2
    assert np.allclose(structure.sites[1].frac, [0.5, 0.5, 0.5])


def test_a_file_with_no_species_is_refused_and_says_why(tmp_path):
    """VASP 4 wrote the counts alone and took the names from the
    POTCAR beside it. Reading those atoms as X would be worse than
    refusing: X here is a marker, not an element, and every force
    field holds one back at the door -- a whole crystal would arrive
    as dummy atoms and quietly weigh nothing."""
    path = _poscar(tmp_path, "t\n1.0\n" + BODY + " 1 1\nDirect\n"
                   " 0.0 0.0 0.0\n 0.5 0.5 0.5\n")
    with pytest.raises(ValueError, match="no species"):
        FORMATS.read(path)


def test_a_potcar_style_species_name_is_read_down_to_the_element(
        tmp_path):
    """Fe_pv and Zn2+ are both iron and zinc to everything here."""
    path = _poscar(tmp_path, "t\n1.0\n" + BODY + " Fe_pv Zn2+\n 1 1\n"
                   "Direct\n 0.0 0.0 0.0\n 0.5 0.5 0.5\n")
    assert [s.element for s in FORMATS.read(path).sites] == ["Fe", "Zn"]


def test_a_crystal_survives_the_round_trip(tmp_path):
    """Written in P1, because the format has nowhere to put a group."""
    original = Structure.from_arrays(
        Lattice.from_parameters(4.6, 4.6, 3.0, 90, 90, 90),
        ["Ti", "O"], [[0, 0, 0], [0.305, 0.305, 0.0]],
        space_group="P4_2/mnm")
    path = tmp_path / "out.POSCAR"
    FORMATS.write(original, path, fmt="poscar")
    back = FORMATS.read(path)
    before = p1.expand(original)
    assert len(back.sites) == before.n_atoms
    assert np.allclose(original.lattice.matrix, back.lattice.matrix)
    assert sorted(set(before.elements)) == \
        sorted({s.element for s in back.sites})


def test_the_format_says_it_keeps_no_symmetry(tmp_path):
    """The export dialog is honest about what a format drops, and a
    POSCAR drops the group."""
    assert not FORMATS.get("poscar").keeps


def test_species_and_counts_that_disagree_are_refused(tmp_path):
    """zip would have stopped at the shorter of the two and read a
    crystal with some of its atoms missing, without saying so."""
    path = _poscar(tmp_path, "t\n1.0\n" + BODY + " Na Cl K\n 1 1\n"
                   "Direct\n 0.0 0.0 0.0\n 0.5 0.5 0.5\n")
    with pytest.raises(ValueError, match="3 species"):
        FORMATS.read(path)
