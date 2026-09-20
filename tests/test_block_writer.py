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
from xtal.core.structure import Bond, Site, Structure
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
def test_two_bonds_on_one_point_are_a_bidentate_attachment(linker):
    """Two bonds used to be a refusal, on the grounds that there was
    no single direction to place the point along.  There is one: the
    direction from the two atoms' middle, which is how MFU-4l's
    kernel meets a triazolate.  Refusing it was what made that
    crystal unbuildable."""
    crowded = linker.copy()
    cell = p1.expand(crowded)
    marked = [i for i in range(cell.n_atoms)
              if cell.elements[i] == "X"][0]
    # A ring carbon on the same end as that X, so the pair is a bite
    # across the ring rather than a span of the whole molecule.
    near = sorted((i for i in range(cell.n_atoms)
                   if cell.elements[i] == "C"),
                  key=lambda i: np.linalg.norm(cell.cart[i]
                                               - cell.cart[marked]))[1]
    crowded.add_bond(bonding.bond_between(crowded, cell, marked,
                                          near))

    assert problems(crowded) == []


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


# ------------------------------------ a point that stands for several

def molecule(symbols, cart, bonds):
    """A molecule in a 20 A box with its bonds stated, not perceived.

    Explicit coordinates rather than a SMILES string: these tests are
    about distances of a tenth of an Angstrom either side of a named
    constant, and an embedding that moves between RDKit versions
    cannot pin one.
    """
    lattice = Lattice.cubic(20.0)
    structure = Structure.from_arrays(
        lattice, list(symbols),
        lattice.to_frac(np.asarray(cart, dtype=float) + 10.0),
        space_group="P1")
    for i, j, order in bonds:
        structure.add_bond(Bond(i, j, (0, 0, 0), order))
    return structure


@pytest.fixture
def chelate():
    """A connection point bridging two carbons 1.40 A apart.

    The shape of every attachment this work was built for: MFU-4l's
    kernel meets a triazolate through two ring atoms, Ni3(HITP)2's
    nickel meets an imine through two nitrogens.
    """
    return molecule(
        ["C", "C", "X", "C", "C"],
        [[-0.70, 0.0, 0.0], [0.70, 0.0, 0.0], [0.0, 1.50, 0.0],
         [-1.40, -1.21, 0.0], [1.40, -1.21, 0.0]],
        [(0, 1, 1.0), (0, 2, 1.0), (1, 2, 1.0),
         (0, 3, 1.0), (1, 4, 1.0)])


@pytest.fixture
def ethyne():
    """One point per atom, which is what every block was until now."""
    return molecule(
        ["X", "C", "C", "X"],
        [[-2.10, 0.0, 0.0], [-0.70, 0.0, 0.0],
         [0.70, 0.0, 0.0], [2.10, 0.0, 0.0]],
        [(0, 1, 1.0), (1, 2, 3.0), (2, 3, 1.0)])


def test_a_connection_point_may_stand_for_two_atoms(chelate,
                                                    tmp_path):
    """Written, read back, and still bidentate -- the bond block is
    the only record of which atoms a point stands for, and it is the
    one PORMAKE has always written and always read."""
    block = written(chelate, tmp_path)
    point, = block.connections

    assert block.is_polydentate
    assert len(block.members[point]) == 2
    assert {block.symbols[m] for m in block.members[point]} == {"C"}


def test_a_bridging_connection_point_sits_above_their_middle(
        chelate, tmp_path):
    """0.75 A from the *centroid* of its members, which is further
    than 0.75 from either of them.  It is where the next block's own
    point has to land for the two ends to meet, and a point pulled in
    to one of the two atoms would meet it half a bite away."""
    block = written(chelate, tmp_path)
    point, = block.connections
    members = list(block.members[point])
    middle = block.positions[members].mean(axis=0)

    assert np.linalg.norm(block.positions[point]
                          - middle) == pytest.approx(
        CONNECTION_DISTANCE, abs=1e-3)
    for member in members:
        assert np.linalg.norm(block.positions[point]
                              - block.positions[member]) > 1.0


def test_a_single_point_block_is_written_byte_for_byte_as_before(
        ethyne):
    """The guarantee the whole phase rests on.  A centroid over one
    atom is that atom, so nothing about a monodentate block goes
    through new arithmetic -- and this pins the bytes rather than
    arguing it."""
    assert block_string(ethyne) == (
        "4\n"
        "    2    3\n"
        "C    -0.7000 0.0000 0.0000\n"
        "C    0.7000 0.0000 0.0000\n"
        "X    -1.4500 0.0000 0.0000\n"
        "X    1.4500 0.0000 0.0000\n"
        "   0    1 T\n"
        "   1    3 S\n"
        "   2    0 S\n")


def test_two_points_may_share_one_member_atom():
    """Explicitly not a refusal: a single-metal node is two
    connection points on the same metal, and that is most of what
    PORMAKE's own N-series is made of."""
    node = molecule(
        ["Ni", "X", "X", "N", "N"],
        [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [-1.5, 0.0, 0.0],
         [0.0, 1.9, 0.0], [0.0, -1.9, 0.0]],
        [(0, 1, 1.0), (0, 2, 1.0), (0, 3, 1.0), (0, 4, 1.0)])

    assert problems(node) == []


# --------------------------------------- what a group can get wrong

def test_a_connection_point_with_no_bonds_is_still_refused(chelate):
    """The refusal that survives the loosening.  One bond is a
    direction and two are a frame; none is nothing."""
    lonely = chelate.copy()
    lonely.add_sites([Site("X", np.array([0.9, 0.9, 0.9]))])

    found = problems(lonely)
    assert any("no bonds" in line and "at least one" in line
               for line in found)


def test_a_point_bonded_to_another_point_is_refused(chelate):
    """A connection point stands for the atoms of this block.  Two of
    them standing for each other describe a joint to nowhere, and the
    fit would place a block against a marker."""
    doubled = chelate.copy()
    doubled.add_sites([Site("X", doubled.lattice.to_frac(
        np.array([0.0, 2.8, 0.0]) + 10.0))])
    doubled.add_bond(Bond(2, 5, (0, 0, 0), 1.0))

    found = problems(doubled)
    assert any("both of them are connection points" in line
               for line in found)
    # And not also told it has no bonds: it has one, to the other
    # marker, which is exactly what the sentence above is about.
    assert not any("no bonds" in line for line in found)


def test_an_attachment_wider_than_a_chelate_is_refused():
    """Two atoms 6 A apart are two ends of a molecule, not one
    chelating group -- the mis-click MAX_ATTACHMENT_SPAN exists for.
    The widest real attachment measured is 2.861 A."""
    wide = molecule(
        ["C", "C", "X", "H", "H"],
        [[-3.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 2.0, 0.0],
         [-3.0, -1.09, 0.0], [3.0, -1.09, 0.0]],
        [(0, 2, 1.0), (1, 2, 1.0), (0, 3, 1.0), (1, 4, 1.0)])

    found = problems(wide)
    assert any("6.00 A apart" in line for line in found)


def test_an_attachment_pointing_into_the_molecule_is_refused(chelate):
    """Judged against the atoms one bond further in and never against
    the block's middle: a node's arms are concave, so 77 of the 4256
    shipped connection points point toward their own block's centroid
    and every one of them is right."""
    inward = chelate.copy()
    inward.sites[2].frac = inward.lattice.to_frac(
        np.array([0.0, -1.5, 0.0]) + 10.0)

    found = problems(inward)
    assert any("points back into the molecule" in line
               for line in found)


def test_a_point_on_a_molecule_that_goes_no_further_is_left_alone():
    """Two atoms and a marker: there is no atom one bond further in,
    so there is nothing to say which way is out and the refusal keeps
    quiet rather than guessing."""
    small = molecule(["C", "X"], [[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                     [(0, 1, 1.0)])

    assert problems(small) == []


@needs_pormake
def test_pormake_reads_a_bidentate_point_this_application_wrote(
        chelate, tmp_path):
    """The premise the whole phase rests on: nothing new enters the
    format, so the vendored reader takes a polydentate block without
    being told about one.  It has always read the bond block, and the
    bond block has always been what says which atoms a point stands
    for."""
    from xtal.mof.pormake import BuildingBlock

    path = write_building_block(chelate, tmp_path / "U01.xyz")
    block = BuildingBlock(str(path))
    point, = block.connection_point_indices
    records = [r for r in block.bonds if point in r]

    assert len(records) == 2
    assert block.n_connection_points == 1


def pormake_says(path) -> str:
    """What PORMAKE logs while it reads this block.

    Through a handler on its own logger and not through ``caplog`` or
    ``capsys``: ``pormake/log.py`` sets ``propagate = False`` and
    binds a console handler to whatever ``sys.stderr`` was at import,
    so a capture of either sees nothing -- or sees it only when this
    test happens to run first.
    """
    import io
    import logging

    from xtal.mof.pormake import BuildingBlock

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("unique_logger")
    logger.addHandler(handler)
    try:
        BuildingBlock(str(path)).check_bonds()
    finally:
        logger.removeHandler(handler)
    return stream.getvalue()


@needs_pormake
def test_pormake_finds_nothing_to_warn_about_in_a_bidentate_block(
        chelate, tmp_path):
    """``check_bonds`` runs at construction and warns about an atom
    that is in no bond.  A point standing for two atoms is in two, so
    it has nothing to say -- which is what makes this a block the
    vendored code builds with rather than one it merely reads.

    The second half is what proves the first half is not vacuous.
    """
    written_here = write_building_block(chelate, tmp_path / "U01.xyz")
    dangling = tmp_path / "U02.xyz"
    dangling.write_text(
        "3\n    2\nC 0.0 0.0 0.0\nH 5.0 0.0 0.0\nX 0.75 0.0 0.0\n"
        "   0    2 S\n", encoding="utf-8")

    assert "without bond" not in pormake_says(written_here)
    assert "without bond" in pormake_says(dangling)
