"""File formats: CIF, extended XYZ, and the registry."""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1, properties, symmetry
from xtal.core.site import Site
from xtal.core.structure import TOPOLOGY, Bond
from xtal.io import (
    FORMATS,
    cif_string,
    for_export,
    read_cif,
    read_cif_all,
    read_cif_string,
    read_xyz_string,
    what_is_dropped,
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


# ------------------------------------------------- bonds, in the CIF

def test_a_cif_carries_the_bonds_it_was_written_with(rutile, tmp_path):
    """``_geom_bond_site_symmetry_2`` is ``n_pqr``: operation *n* of
    the symmetry loop, then a translation of (p-5, q-5, r-5).

    That is exactly what a ``Bond`` is, which is why the standard half
    of the loop carries the whole geometry -- another program reads
    the bonds this one drew.
    """
    rutile.bonds += [
        Bond(0, 1, (0, 0, 0), order=2.0, kind="explicit", stated=True),
        Bond(0, 1, (-1, 0, 0), kind=TOPOLOGY, op=3),
    ]
    write_cif(rutile, tmp_path / "bonded.cif")
    back = read_cif(tmp_path / "bonded.cif")

    assert [(b.i, b.j, b.image, b.order, b.kind, b.op, b.stated)
            for b in back.bonds] == [
        (0, 1, (0, 0, 0), 2.0, "explicit", 0, True),
        (0, 1, (-1, 0, 0), 1.0, TOPOLOGY, 3, False)]


def test_a_bond_further_out_than_the_symmetry_code_can_spell(rutile,
                                                             tmp_path):
    """``n_pqr`` is one digit per axis, so five cells has no spelling.

    ``_xtal_bond_image`` is written for every bond precisely so the
    answer never depends on that fitting.
    """
    rutile.bonds.append(Bond(0, 1, (0, 0, 7), kind=TOPOLOGY))
    text = cif_string(rutile)

    assert "  .   " in text or " . " in text
    assert read_cif_string(text).bonds[0].image == (0, 0, 7)


def test_a_foreign_geom_bond_loop_is_not_read_as_the_bonding(tmp_path):
    """It is nearly always a distance table from a refinement.

    Reading one in as the bond graph would hand the user a structure
    bonded by whoever prepared the file, silently, on open -- which is
    the one thing Recalculate Bonds exists to stay in charge of.
    """
    text = NO_SYMMETRY_CIF + """
loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
_geom_bond_distance
Na1 Na1 4.000
"""
    assert read_cif_string(text).bonds == []


def test_a_bond_loop_out_of_step_with_the_atoms_is_not_fatal():
    """A file to open without its bonds, not a file to refuse."""
    text = NO_SYMMETRY_CIF + """
loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
_geom_bond_site_symmetry_2
_xtal_bond_kind
Na1 nobody 1_555 explicit
Na1 Na1    1_555 explicit
Na1 Na1    1_655 explicit
"""
    # The first names an atom that is not there, the second is a site
    # bonded to itself in its own image, which cannot exist.
    kept = read_cif_string(text).bonds
    assert [(b.i, b.j, b.image) for b in kept] == [(0, 0, (1, 0, 0))]


def _stretched_mil53():
    from xtal.core import bonding

    mil53 = read_cif("resources/samples/MIL53.cif")
    held = len(bonding.perceive(mil53))
    parameters = list(mil53.lattice.parameters)
    parameters[0] *= 1.15
    mil53.set_lattice(Lattice.from_parameters(
        *mil53.space_group.cell_constraint.apply(parameters)))
    return mil53, held


def test_a_stored_perception_can_be_written_and_read_back(tmp_path):
    """A scan point's cell is wider than the one its bonds were
    perceived at.  Written without them, MIL-53 at +15% on *a* opens
    with 24 of its 126 bonds gone."""
    from xtal.core import bonding

    mil53, held = _stretched_mil53()
    assert len(bonding.perceive(mil53)) == held
    kept = read_cif(write_cif(mil53, tmp_path / "kept.cif",
                              perception=True))
    plain = read_cif(write_cif(mil53, tmp_path / "plain.cif"))
    assert len(bonding.perceive(kept)) == held
    assert len(bonding.perceive(plain)) < held


def test_a_perception_is_not_written_unless_asked_for(tmp_path):
    """Every other CIF this program writes is unchanged by it."""
    from xtal.core import bonding

    mil53, _held = _stretched_mil53()
    bonding.perceive(mil53)
    assert "_xtal_perceived" not in cif_string(mil53)


def test_a_read_perception_is_still_replaced_by_recalculating(tmp_path):
    """It is the answer perception gave, not a new rule about bonds:
    Recalculate Bonds still perceives at the geometry in front of it."""
    from xtal.core import bonding

    mil53, held = _stretched_mil53()
    kept = read_cif(write_cif(mil53, tmp_path / "kept.cif",
                              perception=True))
    kept.clear_perceived()
    assert len(bonding.perceive(kept)) < held


def test_a_perception_that_does_not_fit_the_atoms_is_ignored(tmp_path):
    """A file edited by hand opens the old way, perceived afresh,
    rather than bonded to atoms that are not the ones meant."""
    mil53, _held = _stretched_mil53()
    text = cif_string(mil53, perception=True)
    lines = text.splitlines()
    first = next(n for n, line in enumerate(lines)
                 if line.startswith("_xtal_perceived_bond_distance"))
    parts = lines[first + 1].split()
    parts[-1] = "9.9999"
    lines[first + 1] = " ".join(parts)
    assert read_cif_string("\n".join(lines)).perceived is None


# ------------------------------------------------- what leaves, clean

def test_an_export_keeps_the_chemistry_and_drops_the_markup(rutile):
    """A marker is not chemistry and a net edge is not a bond, so
    neither goes in a file for somebody else."""
    rutile.sites.append(Site("X", [0.25, 0.25, 0.25]))
    rutile.bonds += [
        Bond(0, 1, (0, 0, 0), kind="explicit"),
        Bond(0, 1, (1, 0, 0), kind=TOPOLOGY),
        Bond(0, 1, (0, 1, 0), kind="suppressed"),
        Bond(0, 2, (0, 0, 0), kind="explicit"),
    ]
    clean = for_export(rutile)

    assert [s.element for s in clean.sites] == ["Ti", "O"]
    assert [b.kind for b in clean.bonds] == ["explicit"]
    assert len(rutile.sites) == 3       # the original is untouched


def test_a_structure_with_nothing_to_clean_is_not_copied(rutile):
    """Every crystal anybody has ever opened, and it should not pay
    for a copy of itself on the way out."""
    assert for_export(rutile) is rutile


def test_what_is_dropped_says_so_in_one_sentence(rutile):
    assert what_is_dropped(rutile) == ""
    rutile.sites.append(Site("X", [0.25, 0.25, 0.25]))
    rutile.bonds.append(Bond(0, 1, (1, 0, 0), kind=TOPOLOGY))
    said = what_is_dropped(rutile)
    assert "1 dummy atom" in said and "1 net edge" in said


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
