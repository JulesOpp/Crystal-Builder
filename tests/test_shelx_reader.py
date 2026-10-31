"""SHELX ``.ins``/``.res`` files read as structures.

What breaks if these regress: a ``.res`` opens with the wrong group
(``SYMM`` lists neither the identity nor the centring nor a positive
``LATT``'s inversion), a site on a special position comes in at a
fraction of its occupancy (SHELXL's factor includes the site
symmetry), a free variable or a fixed ``10+x`` coordinate is taken
literally, a riding hydrogen gets a negative U, or the difference
peaks after ``HKLF`` become atoms.
"""

from pathlib import Path

import gemmi
import numpy as np
import pytest

from xtal.io import FORMATS, shelx
from xtal.io.shelx import PARTS_KEY, read_shelx_string

UIO67 = Path(__file__).resolve().parents[1] \
    / "resources/samples/cod/UiO-67.cif"

HALITE = """\
TITL halite
CELL 0.71073 5.64 5.64 5.64 90 90 90
LATT 4
SYMM -X,-Y,Z
SYMM -X,Y,-Z
SYMM X,-Y,-Z
SYMM Z,X,Y
SYMM Z,-X,-Y
SYMM -Z,-X,Y
SYMM -Z,X,-Y
SYMM Y,Z,X
SYMM -Y,Z,-X
SYMM Y,-Z,-X
SYMM -Y,-Z,X
SYMM Y,X,-Z
SYMM -Y,-X,-Z
SYMM Y,-X,Z
SYMM -Y,X,Z
SYMM X,Z,-Y
SYMM -X,Z,Y
SYMM -X,-Z,-Y
SYMM X,-Z,Y
SYMM Z,Y,-X
SYMM Z,-Y,X
SYMM -Z,Y,X
SYMM -Z,-Y,-X
SFAC NA CL
UNIT 4 4
FVAR 1.0
NA1 1 0.0 0.0 0.0 10.02083 0.01
CL1 2 10.5 10.5 10.5 10.02083 0.01
HKLF 4
END
Q1 1 0.25 0.25 0.25 11.0 0.05
"""

DISORDER = """\
TITL disorder
CELL 0.71073 10 11 12 90 100 90
LATT 1
SYMM -X,1/2+Y,1/2-Z
SFAC C H O
UNIT 4 8 4
FVAR 1.0 0.7
C1 1 0.1 0.2 0.3 11.0 0.01 0.02 0.03 0.0 0.001 0.0
AFIX 43
H1 2 0.15 0.25 0.35 11.0 -1.2
AFIX 0
PART 1
O1 3 0.4 0.4 0.4 21.0 0.05
PART 2
O2 3 0.45 0.4 0.4 -21.0 0.05
PART 0
HKLF 4
"""


def test_the_group_is_built_from_symm_latt_and_the_inversion():
    structure = read_shelx_string(HALITE)
    assert structure.space_group.short_name == "Fm-3m"
    structure = read_shelx_string(DISORDER)
    assert structure.space_group.short_name == "P21/c"


def test_a_special_position_has_its_chemical_occupancy():
    """``10.02083`` on Fm-3m's m-3m site is a whole atom."""
    structure = read_shelx_string(HALITE)
    assert [s.occupancy for s in structure.sites] == [1.0, 1.0]


def test_fixed_coordinates_and_elements_are_read_as_meant():
    sodium, chlorine = read_shelx_string(HALITE).sites
    assert np.allclose(chlorine.frac, 0.5)
    assert (sodium.element, chlorine.element) == ("Na", "Cl")


def test_nothing_after_hklf_is_an_atom():
    assert [s.label for s in read_shelx_string(HALITE).sites] \
        == ["NA1", "CL1"]


def test_free_variables_split_an_occupancy_between_parts():
    sites = {s.label: s for s in read_shelx_string(DISORDER).sites}
    assert sites["O1"].occupancy == pytest.approx(0.7)
    assert sites["O2"].occupancy == pytest.approx(0.3)


def test_a_riding_hydrogen_takes_its_parent_u_eq():
    sites = {s.label: s for s in read_shelx_string(DISORDER).sites}
    assert sites["C1"].u_aniso == (0.01, 0.02, 0.03, 0.0, 0.001, 0.0)
    assert sites["H1"].u_iso == pytest.approx(1.2 * 0.02)


def test_parts_are_recorded_for_the_window_as_a_cif_s_are():
    structure = read_shelx_string(DISORDER)
    assert structure.meta[PARTS_KEY] == [(1, [2]), (2, [3])]


def test_uio67_res_reads_as_its_own_cif_does():
    """The ``.res`` SHELXL embedded in the CIF gives the same sites,
    occupancies and PARTs as the CIF SHELXL wrote from it."""
    block = gemmi.cif.read(str(UIO67)).sole_block()
    res = read_shelx_string(shelx.instruction_text(block), "u.res")
    cif = FORMATS.read(UIO67)
    assert res.space_group == cif.space_group
    assert [s.label.upper() for s in res.sites] \
        == [s.label.upper() for s in cif.sites]
    for a, b in zip(res.sites, cif.sites, strict=True):
        assert a.element == b.element
        assert a.occupancy == pytest.approx(b.occupancy, abs=1e-3)
        assert np.allclose(a.frac, b.frac, atol=1e-3)
    assert res.meta[PARTS_KEY] == cif.meta[PARTS_KEY]


def test_ins_and_res_open_through_the_registry(tmp_path):
    for suffix in (".ins", ".res"):
        path = tmp_path / f"halite{suffix}"
        path.write_text(HALITE)
        structure = FORMATS.read(path)
        assert structure.meta["format"] == "shelx"
        assert structure.meta["title"] == "halite"


def test_a_zeopp_res_is_refused_by_name(tmp_path):
    """Zeo++ writes its pore diameters to a ``.res`` too."""
    path = tmp_path / "diameters.res"
    path.write_text("MOF.cssr 11.2 7.9 11.2\n")
    with pytest.raises(ValueError, match="no CELL"):
        FORMATS.read(path)
