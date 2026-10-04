"""The CIF reader says what it assumed, and refuses what it cannot.

Each of these was a guess made in silence: a file that lost a cell
length opened as a 1 A cube, a repeated label sent every bond to the
last site holding it, and operations matching no tabulated setting
were dropped without a word.
"""

import pytest

from xtal.core.structure import Bond
from xtal.io import project
from xtal.io.cif_reader import read_cif, read_cif_string
from xtal.io.cif_writer import cif_string

CELL = """_cell_length_a 5
_cell_length_b 5
_cell_length_c 5
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
"""

SITES = """loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
{rows}
"""


def cif(extra="", rows="Zr1 Zr 0 0 0", cell=CELL):
    return f"data_t\n{cell}{extra}\n{SITES.format(rows=rows)}"


def test_duplicate_labels_are_renamed_and_said():
    """A P1 export can call 24 sites Zr1, and a bond is read by label:
    every bond to a Zr1 went to the last one."""
    structure = read_cif_string(cif(
        "_symmetry_space_group_name_H-M 'P 1'",
        "Zr1 Zr 0 0 0\nZr1 Zr 0.5 0.5 0.5\nZr1 Zr 0.5 0 0\n"
        "Zr1_2 Zr 0 0.5 0"))

    labels = [site.label for site in structure.sites]
    assert labels == ["Zr1", "Zr1_3", "Zr1_4", "Zr1_2"]
    assert len(set(labels)) == 4
    assert any("renamed 2 duplicate labels" in w
               for w in structure.meta["warnings"])


def test_a_file_with_unique_labels_is_read_as_it_was_written():
    """Renaming must touch nothing in an ordinary file."""
    original = read_cif("resources/samples/MFU4l.cif")
    back = read_cif_string(cif_string(original))

    assert [s.label for s in back.sites] == \
        [s.label for s in original.sites]
    for structure in (original, back):
        assert not any("renamed" in w
                       for w in structure.meta.get("warnings", []))


def test_uio66_bonds_survive_a_project_round_trip_unchanged(tmp_path):
    """UiO-66 ships with seven labels for 432 sites.  A bond to the
    30th site came back on the last O1, and the project then held it
    twice: once from its own record, once from the CIF part."""
    structure = read_cif("resources/samples/UIO66.cif")
    structure.add_bond(Bond(i=0, j=30, image=(0, 0, 0),
                            kind="explicit"))

    back, _view, _session = project.read_project(
        project.write_project(structure, tmp_path / "u.xtalproj"))
    plain = read_cif_string(cif_string(structure))

    assert [(b.i, b.j, b.kind) for b in back.bonds] == \
        [(0, 30, "explicit")]
    assert [(b.i, b.j) for b in plain.bonds] == [(0, 30)]


@pytest.mark.parametrize("value", [None, "?"])
def test_a_cell_with_a_missing_length_is_refused_by_name(value):
    """gemmi fills a missing length with 1 A, and the crystal opened as
    a cube with its atoms piled on each other."""
    cell = CELL.replace("_cell_length_b 5\n", "" if value is None
                        else f"_cell_length_b {value}\n")

    with pytest.raises(ValueError, match="_cell_length_b"):
        read_cif_string(cif(cell=cell))


def test_a_series_skips_the_block_with_no_cell_and_says_so(tmp_path):
    """One broken block of a series is that block, not the file."""
    broken = cif(cell=CELL.replace("_cell_angle_beta 90\n", ""))
    path = tmp_path / "series.cif"
    path.write_text(cif() + "\n" + broken.replace("data_t", "data_u"))

    structure = read_cif(path)

    assert any("skipped" in w and "_cell_angle_beta" in w
               for w in structure.meta["warnings"])


@pytest.mark.parametrize("unknown", ["?", "."])
def test_an_unknown_space_group_number_still_opens(unknown):
    """``?`` was unquoted to an empty string, which gemmi then refused
    as "not an integer" -- the file would not open at all."""
    structure = read_cif_string(cif(
        f"_space_group_IT_number {unknown}\n"
        "_symmetry_space_group_name_H-M 'P m -3 m'\n"
        "_space_group_name_Hall ?"))

    assert structure.space_group.number == 221
    assert not structure.meta.get("warnings")


def test_operations_matching_no_setting_are_said_to_be_unused():
    """Building the group from the file's own operations is owed;
    until then the file must not appear to have been read by them."""
    structure = read_cif_string(cif(
        "_space_group_name_H-M_alt 'P 21'\nloop_\n"
        "_space_group_symop_operation_xyz\nx,y,z\n-x+1/3,y+1/2,-z",
        "Zr1 Zr 0.1 0.2 0.3"))

    warning, = structure.meta["warnings"]
    assert "2 symmetry operations" in warning
    assert "P21 was used instead" in warning


def test_a_disorder_group_survives_writing_and_reading(rutile):
    """Prepare orders disorder by these groups; a save that dropped
    them left it nothing to order by on the next open."""
    structure = rutile.copy()
    structure.sites[1].props["disorder_group"] = 2

    back = read_cif_string(cif_string(structure))

    assert back.sites[1].props.get("disorder_group") == 2
    assert "disorder_group" not in back.sites[0].props


def test_a_computed_charge_goes_through_a_cif_and_an_oxidation_state_stays_in_the_symbol(  # noqa: E501
        rutile):
    """EQeq's charges were dropped on save -- a fractional charge had
    no column -- so they could not reach RASPA or Zeo++, which read
    ``_atom_site_charge``.  A whole-number charge is still written as
    the type symbol (Ti4+), and a file without the column reads as it
    did."""
    computed = rutile.copy()
    for site, q in zip(computed.sites, (1.2875, -0.64375), strict=False):
        site.charge = q
    text = cif_string(computed)
    assert "_atom_site_charge" in text
    back = read_cif_string(text)
    assert [s.charge for s in back.sites] == pytest.approx(
        [1.2875, -0.64375])

    formal = rutile.copy()
    formal.sites[0].charge = 4.0
    formal.sites[1].charge = -2.0
    text = cif_string(formal)
    assert "_atom_site_charge" not in text
    assert "Ti4+" in text
    assert [s.charge for s in read_cif_string(text).sites] == [4.0, -2.0]
