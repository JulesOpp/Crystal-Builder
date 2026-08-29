"""File formats: CIF, extended XYZ, and the registry."""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1, properties, symmetry
from xtal.io import (
    FORMATS,
    cif_string,
    read_cif,
    read_cif_all,
    read_cif_string,
    read_xyz_string,
    write_cif,
    write_xyz,
    xyz_string,
)

NO_SYMMETRY_CIF = """
data_mystery
_cell_length_a 4.0
_cell_length_b 4.0
_cell_length_c 4.0
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_atom_site_label
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 0.0 0.0 0.0
Cl1 0.5 0.5 0.5
"""

OPS_ONLY_CIF = """
data_ops
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_space_group_symop_operation_xyz
'x,y,z'
'-x,-y,-z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.1 0.2 0.3
"""

TWO_BLOCK_CIF = NO_SYMMETRY_CIF + """
data_second
_cell_length_a 6.0
_cell_length_b 6.0
_cell_length_c 6.0
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_atom_site_label
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
K1 0.0 0.0 0.0
"""


# ---------------------------------------------------------------- CIF

def test_cif_round_trip_is_exact(rutile, tmp_path):
    rutile.ensure_labels()
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    back = read_cif(path)
    assert back == rutile
    assert back.space_group == rutile.space_group
    assert back.lattice.almost_equal(rutile.lattice)


@pytest.mark.parametrize("name", ["rutile", "quartz", "halite",
                                  "dry_ice"])
def test_every_fixture_survives_a_cif_round_trip(name, request,
                                                 tmp_path):
    structure = request.getfixturevalue(name)
    structure.ensure_labels()
    path = tmp_path / f"{name}.cif"
    write_cif(structure, path)
    back = read_cif(path)
    assert back.space_group == structure.space_group
    assert p1.expand(back).n_atoms == p1.expand(structure).n_atoms
    assert properties.density(back) == pytest.approx(
        properties.density(structure))


def test_export_says_where_it_came_from(rutile):
    text = cif_string(rutile)
    assert "Crystal Builder" in text
    assert "_audit_creation_method" in text
    assert "_audit_creation_date" in text


def test_export_carries_structure_and_nothing_else(rutile):
    """Cell, symmetry, atoms, provenance -- no invented refinement
    metadata."""
    text = cif_string(rutile)
    for tag in ("_cell_length_a", "_space_group_name_H-M_alt",
                "_space_group_name_Hall", "_space_group_IT_number",
                "_space_group_symop_operation_xyz",
                "_atom_site_fract_x", "_atom_site_occupancy"):
        assert tag in text
    for absent in ("_refine_", "_diffrn_", "_exptl_crystal_",
                   "_publ_"):
        assert absent not in text


def test_p1_export_expands_the_cell(rutile, tmp_path):
    path = tmp_path / "flat.cif"
    write_cif(rutile, path, expand_to_p1=True)
    back = read_cif(path)
    assert back.is_p1
    assert back.n_sites == 6
    assert properties.density(back) == pytest.approx(
        properties.density(rutile))


def test_occupancy_uiso_and_charge_survive(tmp_path):
    from xtal.core.site import Site
    s = Structure(Lattice.cubic(5.0), [
        Site("Fe", [0, 0, 0], occupancy=0.75, u_iso=0.013,
             charge=3.0, label="Fe1"),
        Site("O", [0.5, 0.5, 0.5], u_iso=0.02, charge=-2.0,
             label="O1")])
    back = read_cif_string(cif_string(s))
    assert back.sites[0].occupancy == pytest.approx(0.75)
    assert back.sites[0].u_iso == pytest.approx(0.013)
    assert back.sites[0].charge == pytest.approx(3.0)
    assert back.sites[1].charge == pytest.approx(-2.0)


def test_missing_symmetry_reads_as_p1_with_a_warning():
    s = read_cif_string(NO_SYMMETRY_CIF)
    assert s.is_p1
    assert s.n_sites == 2
    assert s.elements == ["Na", "Cl"]        # elements from labels
    assert any("assuming P1" in w for w in s.meta["warnings"])


def test_symmetry_operations_alone_are_enough():
    s = read_cif_string(OPS_ONLY_CIF)
    assert s.space_group.number == 2          # P-1
    assert p1.expand(s).n_atoms == 2


def test_nonstandard_setting_survives_the_round_trip(tmp_path):
    """A number alone cannot express origin choice 2; the Hall symbol
    can, and that is what we write."""
    s = Structure.from_arrays(
        Lattice.cubic(8.0), ["Si"], [[0.0, 0.0, 0.0]],
        space_group="Fd-3m:2")
    back = read_cif_string(cif_string(s))
    assert back.space_group.setting == "2"
    assert back.space_group == s.space_group


def test_multi_block_files(tmp_path):
    path = tmp_path / "two.cif"
    path.write_text(TWO_BLOCK_CIF)
    everything = read_cif_all(path)
    assert len(everything) == 2
    assert everything[0].n_sites == 2
    assert everything[1].elements == ["K"]
    assert read_cif(path).n_sites == 2        # first block by default
    assert len(FORMATS.read_all(path)) == 2


def test_metadata_is_kept(rutile_cif):
    s = read_cif(rutile_cif)
    assert s.meta["format"] == "cif"
    assert s.meta["source"].endswith("rutile.cif")
    assert s.meta["title"]


def test_reading_a_file_with_no_structure_raises(tmp_path):
    path = tmp_path / "empty.cif"
    path.write_text("data_nothing\n_cell_length_a 4.0\n")
    with pytest.raises(ValueError):
        read_cif(path)
    with pytest.raises(ValueError):
        read_cif_string("data_nothing\n")


# ---------------------------------------------------------------- XYZ

def test_xyz_round_trip_keeps_the_cell(quartz, tmp_path):
    path = tmp_path / "quartz.xyz"
    write_xyz(quartz, path)
    back = FORMATS.read(path)
    assert back.lattice.almost_equal(quartz.lattice)
    assert back.n_sites == p1.expand(quartz).n_atoms
    assert properties.density(back) == pytest.approx(
        properties.density(quartz))


def test_xyz_writes_the_expanded_cell(rutile):
    text = xyz_string(rutile)
    assert text.splitlines()[0] == "6"        # not the 2 asymmetric
    assert 'Lattice="' in text


def test_xyz_without_a_lattice_gets_a_padded_box():
    text = "2\nwater-ish\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\n"
    s = read_xyz_string(text)
    assert s.n_sites == 2
    assert s.is_p1
    assert s.lattice.lengths[0] > 0.96        # padded, not degenerate
    assert any("padded box" in w for w in s.meta["warnings"])
    cart = s.lattice.to_cart(s.frac)
    assert np.linalg.norm(cart[1] - cart[0]) == pytest.approx(0.96)


@pytest.mark.parametrize("bad", ["", "not a number\n", "3\nc\nH 0 0 0\n",
                                 "1\nc\nH 0 0\n"])
def test_malformed_xyz_raises(bad):
    with pytest.raises(ValueError):
        read_xyz_string(bad)


# ----------------------------------------------------------- registry

def test_registry_dispatches_on_extension(rutile, tmp_path):
    for suffix in (".cif", ".xyz"):
        path = tmp_path / f"out{suffix}"
        FORMATS.write(rutile, path)
        assert path.exists()
        assert FORMATS.read(path).n_sites > 0


def test_registry_lookups_and_errors(tmp_path):
    assert FORMATS.get("cif").can_read and FORMATS.get("cif").can_write
    assert "cif" in FORMATS
    assert {f.name for f in FORMATS.readable()} >= {"cif", "xyz"}
    assert "*.cif" in FORMATS.get("cif").filter_string()
    with pytest.raises(ValueError):
        FORMATS.get("nope")
    with pytest.raises(ValueError):
        FORMATS.read(tmp_path / "structure.unknown")


def test_formats_declare_what_they_preserve():
    assert "symmetry" in FORMATS.get("cif").keeps
    assert "symmetry" not in FORMATS.get("xyz").keeps


def test_cif_export_of_a_structure_built_from_scratch(tmp_path):
    """The path a user actually takes: build something, set a group,
    export it, read it back somewhere else."""
    s = Structure.from_arrays(
        Lattice.cubic(5.64), ["Na", "Cl"],
        [[0, 0, 0], [0.5, 0.5, 0.5]], space_group="Fm-3m")
    path = tmp_path / "built.cif"
    write_cif(s, path)
    back = read_cif(path)
    assert symmetry.detect(back).number == 225
    assert properties.formula(back) == ("NaCl", 4)
