"""DFTB+'s .gen: the simplest complete crystal format there is.

Three letters decide everything -- C is a cluster with no cell, S is a
supercell in cartesian coordinates, F is a supercell in fractional
ones -- and one thing can go quietly wrong: the species index is
one-based, and an off-by-one turns every carbon into a hydrogen
without failing.
"""

import numpy as np
import pytest

from xtal.core.p1 import expand
from xtal.io import FORMATS, gen_string, read_gen, read_gen_string, write_gen


def test_the_whole_cell_is_written(quartz):
    text = gen_string(quartz)
    assert text.splitlines()[0].split() == ["9", "F"]
    assert quartz.n_sites == 2


def test_the_species_line_is_the_distinct_elements_in_order(quartz):
    assert gen_string(quartz).splitlines()[1] == "Si O"


def test_atoms_name_their_species_by_one_based_index(quartz):
    lines = gen_string(quartz).splitlines()[2:11]
    kinds = [int(line.split()[1]) for line in lines]
    assert min(kinds) == 1
    assert kinds[:3] == [1, 1, 1]           # the three silicons
    assert kinds[3:] == [2] * 6             # the six oxygens


def test_the_lattice_is_the_last_three_lines_as_rows(quartz):
    rows = gen_string(quartz).strip().splitlines()[-3:]
    matrix = np.array([[float(v) for v in row.split()] for row in rows])
    assert np.allclose(matrix, quartz.lattice.matrix)


def test_a_round_trip_keeps_the_atoms(quartz, tmp_path):
    back = read_gen(write_gen(quartz, tmp_path / "q.gen"))
    assert expand(back).n_atoms == expand(quartz).n_atoms
    assert np.allclose(np.sort(expand(back).frac, axis=0),
                       np.sort(expand(quartz).frac, axis=0), atol=1e-9)
    assert np.allclose(back.lattice.matrix, quartz.lattice.matrix)


def test_cartesian_is_written_when_asked_and_read_back(quartz,
                                                       tmp_path):
    path = write_gen(quartz, tmp_path / "q.gen", fractional=False)
    assert path.read_text().splitlines()[0].split()[1] == "S"
    back = read_gen(path)
    assert np.allclose(np.sort(expand(back).frac, axis=0),
                       np.sort(expand(quartz).frac, axis=0), atol=1e-9)


def test_a_cluster_gets_a_padded_box_and_the_right_atoms():
    """There is no honest cell for one, so the box is made obvious
    rather than plausible -- the same rule as the XYZ reader's."""
    structure = read_gen_string(
        "2 C\nH O\n"
        "1 1 0.0 0.0 0.0\n"
        "2 2 0.0 0.0 1.0\n")
    assert [s.element for s in structure.sites] == ["H", "O"]
    assert structure.lattice.parameters[2] > 10.0


def test_comments_and_blank_lines_are_ignored():
    structure = read_gen_string(
        "# written by something else\n"
        "\n"
        "1 C\nH\n"
        "1 1 0.0 0.0 0.0   # the only atom\n")
    assert structure.n_sites == 1


def test_a_species_index_off_the_end_is_refused():
    """The one failure this format makes silent: an index that names
    nothing has to be caught, because an index that names the wrong
    element cannot be."""
    with pytest.raises(ValueError, match="names species"):
        read_gen_string("1 C\nH\n1 3 0.0 0.0 0.0\n")


def test_an_unknown_kind_is_refused():
    with pytest.raises(ValueError, match="geometry kind"):
        read_gen_string("1 X\nH\n1 1 0.0 0.0 0.0\n")


def test_a_periodic_file_without_a_lattice_is_refused():
    with pytest.raises(ValueError, match="lattice vectors"):
        read_gen_string("1 S\nH\n1 1 0.0 0.0 0.0\n")


def test_the_registry_knows_the_extension(rutile, tmp_path):
    path = tmp_path / "rutile.gen"
    FORMATS.write(rutile, path)
    assert FORMATS.read(path).n_sites == expand(rutile).n_atoms
