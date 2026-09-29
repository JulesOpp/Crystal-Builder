"""The LAMMPS data file: box, atoms, molecules, charges and bonds.

The geometry was checked once against ASE's reader and LAMMPS's own
``read_data`` on every sample (distances to 1e-10 A); what is here
holds the parts of it that can break without either noticing.
"""

import numpy as np
import pytest

from xtal.core import bonding, p1
from xtal.core.site import Site
from xtal.core.structure import Bond
from xtal.core.supercell import supercell
from xtal.io import FORMATS, for_export
from xtal.io.lammps import lammps_box, lammps_data_string


def _section(text, name):
    """The rows of one section, as lists of words; none when the
    section is not there, which is how a file with no bonds says so."""
    lines = text.splitlines()
    start = next((n for n, line in enumerate(lines)
                  if line.split("#")[0].strip() == name), None)
    if start is None:
        return []
    rows = []
    for line in lines[start + 2:]:
        if not line.strip():
            break
        rows.append(line.split("#")[0].split())
    return rows


def _header(text, word):
    for line in text.splitlines():
        parts = line.split("#")[0].split()
        if parts[-len(word.split()):] == word.split():
            return parts
    return None


def _positions(text):
    return np.array([[float(v) for v in row[4:7]]
                     for row in _section(text, "Atoms")])


def _box(text):
    lx = float(_header(text, "xlo xhi")[1])
    ly = float(_header(text, "ylo yhi")[1])
    lz = float(_header(text, "zlo zhi")[1])
    tilt = _header(text, "xy xz yz")
    xy, xz, yz = (map(float, tilt[:3]) if tilt else (0.0, 0.0, 0.0))
    return np.array([[lx, 0, 0], [xy, ly, 0], [xz, yz, lz]])


def _distances(cart, box):
    """Every minimum-image distance, the long way round."""
    frac = cart @ np.linalg.inv(box)
    delta = frac[:, None, :] - frac[None, :, :]
    shifts = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1)
                       for k in (-1, 0, 1)], float)
    moved = (delta - np.round(delta))[:, :, None, :] + shifts
    return np.linalg.norm(moved @ box, axis=-1).min(axis=-1)


def test_a_triclinic_box_puts_every_atom_where_the_cell_had_it(quartz):
    text = lammps_data_string(quartz)
    written = _distances(_positions(text), _box(text))
    cell = p1.expand(quartz)
    matrix = np.asarray(quartz.lattice.matrix, float)
    original = _distances(cell.frac @ matrix, matrix)
    assert np.allclose(written, original, atol=1e-6)
    assert _header(text, "xy xz yz") is not None


def test_an_orthogonal_cell_writes_no_tilt_line(dry_ice):
    assert _header(lammps_data_string(dry_ice), "xy xz yz") is None


def test_a_large_tilt_is_folded_without_moving_an_atom():
    """LAMMPS asks for tilts within half the box.  Folding is a change
    of basis: the lattice, and so every distance, is the same."""
    matrix = np.array([[5.0, 0, 0], [9.0, 4.0, 0], [7.0, -6.0, 3.0]])
    box, rotation = lammps_box(matrix)
    assert abs(box[1, 0]) <= box[0, 0] / 2 + 1e-9
    assert abs(box[2, 0]) <= box[0, 0] / 2 + 1e-9
    assert abs(box[2, 1]) <= box[1, 1] / 2 + 1e-9
    assert abs(np.linalg.det(box)) == pytest.approx(
        abs(np.linalg.det(matrix)))
    # Both bases span one lattice: each is an integer combination of
    # the other's vectors, once the rotation is applied.
    change = (matrix @ rotation) @ np.linalg.inv(box)
    assert np.allclose(change, np.round(change), atol=1e-9)
    assert np.allclose(rotation @ rotation.T, np.eye(3))
    assert np.linalg.det(rotation) == pytest.approx(1.0)


def test_a_left_handed_cell_is_not_written_as_its_mirror_image():
    """A reflection would write the other enantiomer of a chiral
    crystal, which reads back as a perfectly good structure."""
    matrix = np.array([[5.0, 0, 0], [0, 6.0, 0], [0, 0, -7.0]])
    _box_, rotation = lammps_box(matrix)
    assert np.linalg.det(rotation) == pytest.approx(1.0)


def test_bonds_are_the_drawn_graph_and_a_suppressed_bond_stays_out(
        dry_ice):
    """Handed the cleaned copy, the writer would perceive the graph
    again and every bond the user took away would be in the file."""
    before = len(_section(lammps_data_string(dry_ice), "Bonds"))
    dry_ice.add_bond(Bond(0, 1, kind="suppressed"))
    drawn = len(bonding.graph(dry_ice).bonds)
    assert drawn < before
    assert len(_section(lammps_data_string(dry_ice), "Bonds")) == drawn
    assert len(bonding.graph(for_export(dry_ice)).bonds) == before


def test_the_format_is_handed_the_uncleaned_structure(dry_ice,
                                                      tmp_path):
    from xtal.agent.session import Session

    assert FORMATS.get("lammps-data").settles_bonds
    assert not FORMATS.get("cif").settles_bonds
    dry_ice.add_bond(Bond(0, 1, kind="suppressed"))
    drawn = len(bonding.graph(dry_ice).bonds)
    session = Session(dry_ice)
    path = session.export(tmp_path / "out.data")
    assert len(_section(path.read_text(), "Bonds")) == drawn


def test_a_dummy_atom_and_its_net_edges_are_not_written(dry_ice):
    before = lammps_data_string(dry_ice)
    marked = dry_ice.copy()
    marked.sites.append(Site("X", (0.5, 0.5, 0.5), label="X1"))
    marked.add_bond(Bond(0, len(marked.sites) - 1, kind="explicit"))
    text = lammps_data_string(marked)
    assert len(_section(text, "Atoms")) == len(_section(before, "Atoms"))
    assert len(_section(text, "Bonds")) == len(_section(before, "Bonds"))
    assert "# X" not in text


def test_charges_are_written_when_set_and_zero_is_said_when_not(
        dry_ice):
    text = lammps_data_string(dry_ice)
    assert "No charges were set" in text
    charged = dry_ice.copy()
    for site in charged.sites:
        site.charge = 0.65 if site.element == "C" else -0.325
    text = lammps_data_string(charged)
    assert "No charges were set" not in text
    charges = [float(row[3]) for row in _section(text, "Atoms")]
    assert sum(charges) == pytest.approx(0.0, abs=1e-9)
    assert max(charges) == pytest.approx(0.65)


def test_a_bond_to_an_ambiguous_image_is_refused(rutile):
    """Rutile's equatorial oxygen is bonded to its Ti through two
    images the same distance away along c = 2.96 A; LAMMPS would bond
    one of them twice.  A supercell along c makes the file writable."""
    with pytest.raises(ValueError, match="supercell"):
        lammps_data_string(rutile)
    text = lammps_data_string(supercell(rutile, 1, 1, 2))
    assert len(_section(text, "Bonds")) == 2 * len(
        bonding.graph(rutile).bonds)


def test_molecules_get_their_own_molecule_ids(dry_ice):
    """Four CO2 in the cell: four molecule IDs of three atoms each."""
    rows = _section(lammps_data_string(dry_ice), "Atoms")
    ids = [row[1] for row in rows]
    assert sorted(ids.count(i) for i in set(ids)) == [3, 3, 3, 3]


def test_every_bond_type_is_named(dry_ice):
    text = lammps_data_string(dry_ice)
    assert "# bond type 1: C-O" in text
    assert {row[1] for row in _section(text, "Bonds")} == {"1"}
