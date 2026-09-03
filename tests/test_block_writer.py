"""Writing a building block, and reading it back with PORMAKE's own
conventions.

The reader in :mod:`xtal.mof.catalog` is the other direction and is
tested against the 867 shipped files; this is the writer, tested
against that reader, against the format facts the shipped files
established, and -- once -- against PORMAKE itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.build import MISSING as NO_RDKIT
from xtal.build import from_smiles
from xtal.build import installed as rdkit_installed
from xtal.core import bonding, p1
from xtal.core.lattice import Lattice
from xtal.core.structure import Bond, Structure
from xtal.mof import database_root
from xtal.mof import installed as pormake_installed
from xtal.mof.block import (
    CONNECTION_DISTANCE,
    BlockError,
    block_string,
    problems,
    write_building_block,
)
from xtal.mof.catalog import read_building_block

needs_rdkit = pytest.mark.skipif(not rdkit_installed(),
                                 reason=NO_RDKIT)
needs_pormake = pytest.mark.skipif(
    not pormake_installed() or database_root() is None,
    reason="PORMAKE is not installed; pip install "
           "'crystal-builder[mof]'")


@pytest.fixture
def linker():
    """Para-phenylene with a connection point at each end: the shape
    of every linker in PORMAKE's ``bbs/``."""
    if not rdkit_installed():
        pytest.skip(NO_RDKIT)
    return from_smiles("[*:1]c1ccc([*:2])cc1",
                       name="phenylene").to_structure()


def written(structure, tmp_path, name="U01"):
    return read_building_block(
        write_building_block(structure, tmp_path / f"{name}.xyz"))


# ------------------------------------------------------- the format

@needs_rdkit
def test_a_block_reads_back_as_the_molecule_that_was_written(
        linker, tmp_path):
    block = written(linker, tmp_path)

    assert block.n_connections == 2
    assert block.formula == "C6H4"
    assert block.name == "U01"


@needs_rdkit
def test_the_connection_points_are_written_both_ways(linker,
                                                     tmp_path):
    """PORMAKE identifies them by the symbol and never reads the index
    line; this application's own reader takes the index line first.  A
    file with only one of the two is read correctly by exactly one of
    the two readers."""
    text = block_string(linker)
    lines = text.splitlines()
    listed = [int(t) for t in lines[1].split()]
    symbols = [line.split()[0] for line in lines[2:2 + 12]]

    assert listed == [10, 11]
    assert [i for i, s in enumerate(symbols) if s == "X"] == listed


@needs_rdkit
def test_the_connection_points_come_last(linker, tmp_path):
    """866 of the 867 shipped blocks are laid out that way, so a
    reader that assumes it is a reader that works on the database."""
    lines = block_string(linker).splitlines()
    symbols = [line.split()[0] for line in lines[2:2 + 12]]

    assert symbols[-2:] == ["X", "X"]
    assert "X" not in symbols[:-2]


@needs_rdkit
def test_a_connection_point_is_written_at_0_75_angstrom(linker,
                                                        tmp_path):
    """Not at a bond length.  A block written at 1.4 A builds a
    framework with every linker bond roughly twice too long and
    nothing anywhere reports it."""
    block = written(linker, tmp_path)
    body = [i for i in range(len(block.symbols))
            if i not in block.connections]

    for point in block.connections:
        near = min(np.linalg.norm(block.positions[point]
                                  - block.positions[j]) for j in body)
        assert near == pytest.approx(CONNECTION_DISTANCE, abs=1e-3)


@needs_rdkit
def test_the_bond_block_carries_the_orders(linker):
    """The fourth section, which is how a molecule's bond orders
    survive into the built framework's CIF."""
    lines = block_string(linker).splitlines()
    bonds = [line.split() for line in lines[2 + 12:]]

    assert len(bonds) == 12                 # six ring, four C-H, two X
    assert {b[2] for b in bonds} == {"A", "S"}
    assert sum(1 for b in bonds if b[2] == "A") == 6


@needs_rdkit
def test_every_bond_names_two_atoms_that_are_in_the_file(linker):
    lines = block_string(linker).splitlines()
    count = int(lines[0])
    for line in lines[2 + count:]:
        i, j, letter = line.split()
        assert 0 <= int(i) < count and 0 <= int(j) < count
        assert letter in ("S", "D", "T", "A")


@needs_rdkit
def test_writing_makes_the_folder_it_was_pointed_at(linker, tmp_path):
    path = write_building_block(linker, tmp_path / "mine" / "U01.xyz")
    assert path.exists()


# ----------------------------------------------------- the refusals

def test_a_structure_with_no_connection_points_says_so(dry_ice):
    found = problems(dry_ice)
    assert found and "nothing marks where this joins" in found[0]


@needs_rdkit
def test_a_cell_with_two_molecules_in_it_is_two_blocks(linker):
    """PORMAKE would build a framework out of whichever of them the
    alignment happened to favour and report nothing."""
    two = linker.copy()
    for site in linker.sites:
        moved = site.copy()
        moved.frac = site.frac + np.array([0.35, 0.0, 0.0])
        moved.label = ""
        two.add_sites([moved])
    for bond in linker.bonds:
        two.add_bond(Bond(bond.i + linker.n_sites,
                          bond.j + linker.n_sites, bond.image,
                          bond.order))

    found = problems(two)
    assert any("separate pieces" in line for line in found)
    with pytest.raises(BlockError, match="separate pieces"):
        block_string(two)


@needs_rdkit
def test_a_connection_point_with_two_bonds_is_named(linker):
    """It has no direction to be placed along, so it is refused rather
    than placed along one of the two."""
    crowded = linker.copy()
    cell = p1.expand(crowded)
    marked = [i for i in range(cell.n_atoms)
              if cell.elements[i] == "X"][0]
    other = [i for i in range(cell.n_atoms)
             if cell.elements[i] == "C"][3]
    crowded.add_bond(bonding.bond_between(crowded, cell, marked,
                                          other))

    found = problems(crowded)
    assert any("2 bond(s)" in line for line in found)


def test_a_framework_is_not_a_building_block():
    """A chain that closes onto the next cell has no outside for a
    connection point to point into, however well marked it is."""
    lattice = Lattice.from_parameters(3.0, 15.0, 15.0, 90, 90, 90)
    chain = Structure.from_arrays(
        lattice, ["C", "C", "X"],
        [[0.0, 0.5, 0.5], [0.5, 0.5, 0.5], [0.0, 0.55, 0.5]],
        space_group="P1")
    chain.add_bond(Bond(0, 1, (0, 0, 0), 1.0))
    chain.add_bond(Bond(1, 0, (1, 0, 0), 1.0))
    chain.add_bond(Bond(0, 2, (0, 0, 0), 1.0))

    found = problems(chain)
    assert found and any("framework" in line for line in found)
    with pytest.raises(BlockError, match="framework"):
        block_string(chain)


# ---------------------------------------------------- the whole way

@needs_pormake
@needs_rdkit
@pytest.mark.slow
def test_pormake_builds_pcu_from_a_block_this_application_wrote(
        linker, tmp_path):
    """The acceptance test for the whole writer.

    A linker built here from a SMILES string, written into a folder of
    the user's own, picked up by the catalogue beside the 867 that
    ship, put on the edges of pcu against a shipped node -- and the
    net read back off the framework still names itself pcu.  Anything
    wrong with the connection distance, the index line, the symbols or
    the bond block shows up as a framework that is not pcu, or as no
    framework at all.
    """
    from xtal.mof import Catalog
    from xtal.mof.build import BuildRequest, build

    blocks = tmp_path / "bbs"
    write_building_block(linker, blocks / "UPhenylene.xyz")
    catalog = Catalog.default("", str(blocks))
    assert "UPhenylene" in [b.name for b in
                            catalog.building_blocks()]

    outcome = build(BuildRequest.parse("pcu", "N59", "UPhenylene"),
                    tmp_path, catalog)

    assert outcome.net_name == "pcu"
    assert outcome.net_agrees
    assert outcome.n_atoms > 0


def test_an_empty_structure_is_refused_rather_than_written():
    empty = Structure.empty(Lattice.cubic(10.0))
    with pytest.raises(BlockError):
        block_string(empty)
