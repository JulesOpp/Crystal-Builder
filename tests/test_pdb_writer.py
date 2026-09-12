"""One cell cut out of a crystal, and written as PDB for Blender."""

import numpy as np
import pytest

from xtal.commands import CommandStack, Host
from xtal.commands.bonds import AddTopologyBond, SuppressBond
from xtal.core import bonding, cellcut, p1
from xtal.core.site import Site
from xtal.io.pdb import pdb_text


def _conect_pairs(text):
    pairs = set()
    for line in text.splitlines():
        if not line.startswith("CONECT"):
            continue
        numbers = [int(line[k:k + 5]) for k in range(6, len(line), 5)]
        first, rest = numbers[0], numbers[1:]
        assert len(rest) <= 4
        pairs |= {(min(first, n), max(first, n)) for n in rest}
    return pairs


def _atoms(text):
    return [line for line in text.splitlines()
            if line.startswith("HETATM")]


# ----------------------------------------------------------------- cut

def test_a_centred_cell_has_its_face_and_corner_atoms(halite):
    """Eight corners and six faces of sodium, twelve edges and the
    centre of chlorine: the cell as it is drawn and as it is printed."""
    cut = cellcut.cut_cell(halite)
    assert cut.elements.count("Na") == 14
    assert cut.elements.count("Cl") == 13
    frac = halite.lattice.to_frac(cut.cart)
    assert frac.min() >= -1e-9 and frac.max() <= 1 + 1e-9


def test_no_bond_in_the_cut_is_longer_than_a_bond(halite):
    cut = cellcut.cut_cell(halite)
    lengths = [np.linalg.norm(cut.cart[i] - cut.cart[j])
               for i, j, _order in cut.bonds]
    assert lengths
    assert max(lengths) == pytest.approx(5.6402 / 2)


def test_a_molecule_across_a_face_keeps_only_what_is_inside(dry_ice):
    """Every CO2 in dry ice has an oxygen over a face.  Cut plainly,
    that oxygen is left behind with its bond; with partners it is
    brought in, and the molecule prints whole."""
    plain = cellcut.cut_cell(dry_ice)
    whole = cellcut.cut_cell(dry_ice, bonded_partners=True)
    assert whole.n_atoms > plain.n_atoms
    assert len(whole.bonds) > len(plain.bonds)
    carbons = [k for k, e in enumerate(whole.elements) if e == "C"]
    for carbon in carbons:
        assert sum(carbon in (i, j) for i, j, _o in whole.bonds) == 2
    for i, j, _order in whole.bonds:
        assert np.linalg.norm(whole.cart[i] - whole.cart[j]) < 1.3


def test_a_suppressed_bond_is_not_cut(quartz):
    host = Host(quartz)
    cell = p1.expand(quartz)
    bond = bonding.graph(quartz).bonds[0]
    before = len(cellcut.cut_cell(quartz).bonds)
    CommandStack().push(SuppressBond.between_atoms(
        quartz, cell, bond.i, bond.j, image_b=bond.image), host)
    assert len(cellcut.cut_cell(host.structure).bonds) < before


def test_markers_and_net_edges_are_not_cut(quartz):
    """A dummy atom is not an atom and a net edge is not a bond."""
    host = Host(quartz)
    stack = CommandStack()
    cell = p1.expand(quartz)
    silicon = [k for k, e in enumerate(cell.elements) if e == "Si"]
    before = cellcut.cut_cell(quartz)
    stack.push(AddTopologyBond.between_atoms(
        quartz, cell, silicon[0], silicon[1]), host)
    host.structure.add_sites([Site("X", [0.5, 0.5, 0.5])])
    after = cellcut.cut_cell(host.structure)
    assert "X" not in after.elements
    assert after.n_atoms == before.n_atoms
    assert after.bonds == before.bonds


# ----------------------------------------------------------------- PDB

def test_every_atom_is_a_hetatm_in_the_standard_columns(halite):
    cut = cellcut.cut_cell(halite)
    atoms = _atoms(pdb_text(cut))
    assert len(atoms) == cut.n_atoms
    for serial, line in enumerate(atoms, start=1):
        assert int(line[6:11]) == serial
        assert line[76:78].strip() == line[12:14].strip()
        xyz = [float(line[30:38]), float(line[38:46]),
               float(line[46:54])]
        assert xyz == pytest.approx(cut.cart[serial - 1], abs=1e-3)
    assert "CRYST1" not in pdb_text(cut)


def test_conect_names_every_bond_and_no_missing_atom(dry_ice):
    cut = cellcut.cut_cell(dry_ice, bonded_partners=True)
    text = pdb_text(cut)
    pairs = _conect_pairs(text)
    assert pairs == {(i + 1, j + 1) for i, j, _o in cut.bonds}
    assert max(max(p) for p in pairs) <= len(_atoms(text))


def test_a_busy_atom_continues_on_another_conect_line(halite):
    """Six neighbours is more than one CONECT line holds."""
    text = pdb_text(cellcut.cut_cell(halite))
    centre = [line for line in text.splitlines()
              if line.startswith("CONECT")]
    serials = [int(line[6:11]) for line in centre]
    assert any(serials.count(s) == 2 for s in serials)


def test_nothing_in_the_file_reads_as_the_end_of_a_chain(halite):
    """Atomic Blender takes a line with TER anywhere in it as the end
    of a chain, and renumbers every atom after it."""
    text = pdb_text(cellcut.cut_cell(halite))
    assert not any("TER" in line for line in text.splitlines())
