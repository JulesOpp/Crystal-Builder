"""Disorder components of a CIF's embedded SHELX file as atom groups.

What breaks if these regress: a CIF refined with PART 1 / PART 2 opens
with its components mixed together and no way to look at one alone,
an instruction such as ``UNIT`` is taken for an atom, a group comes
back on a project that already has its own, or the two disagree with
the CIF's own ``_atom_site_disorder_group``.
"""

from pathlib import Path

from xtal.io import FORMATS, read_cif_string
from xtal.io.shelx import PARTS_KEY, atom_parts, site_parts

UIO67 = Path(__file__).resolve().parents[1] \
    / "resources/samples/cod/UiO-67.cif"

RES = """\
TITL test
CELL 0.71073 10 10 10 90 90 90
SFAC C O
UNIT 4 8
REM PART 7
FVAR 1.0 0.6
C1 1 0.1 0.1 0.1 11.0 0.05
PART 1 21
O1 2 0.2 0.2 0.2 21.0 0.05 0.05 =
     0.05 0 0 0
PART 2 -21
O2 2 0.3 0.3 0.3 -21.0 0.05
PART 0
HKLF 4
REM  after the end
Q1 1 0.4 0.4 0.4 11.0 0.05 1.2
"""


def test_atom_parts_reads_part_numbers_and_skips_instructions_and_peaks():
    """``UNIT 4 8`` has the shape of no atom, but ``UNIT 4 8 2 2 3``
    would; ``REM`` hides a PART; nothing after ``HKLF`` is an atom,
    and a continued line is still one atom."""
    parts = atom_parts(RES + "UNIT 4 8 2 2 3\n")
    assert parts == {"C1": 0, "O1": 1, "O2": 2}


def test_an_atom_in_a_residue_is_found_by_its_cif_name_too():
    parts = atom_parts("RESI 3 TOL\nPART 1\nC1 1 0 0 0 11 0.05\n")
    assert parts["C1"] == 1 and parts["C1_3"] == 1


def test_site_parts_matches_labels_without_regard_to_case_and_skips_part_0():
    """SHELX writes ``ZR1`` for the CIF's ``Zr1``."""
    parts = {"ZR1": 0, "O1": 1, "O2": 2, "H2": 2}
    assert site_parts(["Zr1", "O1", "O2", "H2"], parts) \
        == [(1, [1]), (2, [2, 3])]


def test_uio67_parts_agree_with_its_disorder_group_column():
    structure = FORMATS.read(UIO67)
    parts = dict(structure.meta[PARTS_KEY])
    assert set(parts) == {1, 2, -1}
    for part, sites in parts.items():
        for index in sites:
            assert str(structure.sites[index].props["disorder_group"]) \
                == str(part)


def test_a_cif_without_an_instruction_file_records_no_parts(rutile):
    assert PARTS_KEY not in rutile.meta


def _cif(res: str) -> str:
    return f"""data_t
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P 1'
_shelx_res_file
;
{res}
;
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.1 0.1 0.1
O1 O 0.2 0.2 0.2
O2 O 0.3 0.3 0.3
"""


def test_a_cif_read_from_text_records_its_parts_by_site():
    structure = read_cif_string(_cif(RES))
    assert structure.meta[PARTS_KEY] == [(1, [1]), (2, [2])]
