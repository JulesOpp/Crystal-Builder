"""Reading CGD: the format RCSR publishes its nets in.

The file is not as uniform as its first page, and every case here is
one the RCSR's own 2929 blocks actually contain rather than one the
reader was designed for in advance.  A quirk that stops being handled
does not produce an error -- it produces a net with an edge missing,
which is a *different net* and would be named as one.
"""

import pytest

from xtal.io.cgd import CgdError, read_cgd, read_cgd_string

PCU = """
CRYSTAL
  NAME pcu
  GROUP Pm-3m
  CELL 1.00000 1.00000 1.00000 90.0000 90.0000 90.0000
  NODE 1 6  0.00000 0.00000 0.00000
  EDGE  0.00000 0.00000 0.00000   0.00000 0.00000 1.00000
# EDGE_CENTER  0.00000 0.00000 0.50000
END
"""


def test_a_block_reads_to_a_node_and_an_edge():
    entry = read_cgd_string(PCU)["pcu"]
    assert entry.group == "Pm-3m"
    assert entry.dimension == 3
    assert [n.coordination for n in entry.nodes] == [6]
    assert entry.edges == (((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),)


def test_the_edge_center_comment_is_not_an_edge():
    """It is the midpoint of the edge above it.  Read as an edge it
    would halve every bond length and double every vertex."""
    assert len(read_cgd_string(PCU)["pcu"].edges) == 1


def test_a_two_dimensional_entry_is_two_dimensional():
    """``CELL a b gamma`` and two coordinates per node.  The dimension
    comes from the node, because four blocks have no cell at all."""
    entry = read_cgd_string("""
CRYSTAL
  NAME sql
  GROUP p4mm
  CELL 1.00000 1.00000 90.0000
  NODE 1 4  0.00000 0.00000
  EDGE  0.00000 0.00000   0.00000 1.00000
END
""")["sql"]
    assert entry.dimension == 2
    assert entry.edges == (((0.0, 0.0), (0.0, 1.0)),)


def test_the_other_dialect_gives_a_neighbour_and_not_a_pair():
    """``EDGE 1  x y z`` is one *neighbour position* of node 1, not two
    points.  Four numbers in three dimensions is the tell, which is why
    the nodes have to be read before the edges."""
    entry = read_cgd_string("""
CRYSTAL
GROUP Fm-3m
NAME nts
ATOM 1 4 0.3333  0.1667  0.5000
ATOM 2 6 0.1668  0.1668  0.6668
EDGE 1   0.1668  0.1668  0.3332
END
""")["nts"]
    assert entry.edges == (((0.3333, 0.1667, 0.5),
                            (0.1668, 0.1668, 0.3332)),)


def test_a_keyword_may_stand_alone_with_its_rows_beneath_it():
    entry = read_cgd_string("""
crystal
group R-3
NAME llw-z
atom 1 4  0.3333  0.6667  0.4626
edge
1  0.0833  0.6667  0.4625
1  0.3333  0.4167  0.4625
end
""")["llw-z"]
    assert len(entry.nodes) == 1
    assert len(entry.edges) == 2
    assert entry.edges[0][0] == (0.3333, 0.6667, 0.4626)


def test_keywords_are_read_in_either_case():
    assert read_cgd_string(PCU.lower().replace("pm-3m", "Pm-3m"))


def test_a_missing_cell_is_not_a_missing_net():
    """Four entries have no CELL.  The identity of a net is its
    connectivity and the cell is never read, so refusing them would
    lose four nets over a number nothing looks at."""
    entry = read_cgd_string("""
CRYSTAL
GROUP P4332
NAME cys
ATOM 1 3 0.5000  0.5000  0.5000
ATOM 2 6 0.3750  0.8750  0.6250
EDGE 1   0.3750  0.8750  0.6250
END
""")["cys"]
    assert entry.cell is None
    assert entry.dimension == 3


def test_a_block_with_no_edges_is_refused_by_name():
    """``moo-a`` in the RCSR file declares 22 atoms and no edges."""
    read = read_cgd_string("""
CRYSTAL
name broken
group P1
atom 1 4 0.0 0.0 0.0
END
""")
    assert len(read) == 0
    assert len(read.problems) == 1
    assert "broken" in read.problems[0]


def test_one_broken_block_does_not_lose_the_others():
    """A file of 2929 nets that will not open because one of them is
    incomplete is worse than 2928 nets and a sentence saying so."""
    read = read_cgd_string(PCU + """
CRYSTAL
  NAME broken
  GROUP P1
  NODE 1 4  0.0 0.0 0.0
END
""" + PCU.replace("pcu", "pcu2"))
    assert [e.name for e in read] == ["pcu", "pcu2"]
    assert len(read.problems) == 1


def test_an_edge_of_the_wrong_length_is_refused_and_not_dropped():
    read = read_cgd_string("""
CRYSTAL
  NAME odd
  GROUP P1
  NODE 1 4  0.0 0.0 0.0
  EDGE  0.0 0.0
END
""")
    assert len(read) == 0
    assert "neither a pair" in read.problems[0]


def test_an_edge_at_a_node_that_was_never_declared_is_refused():
    read = read_cgd_string("""
CRYSTAL
  NAME odd
  GROUP P1
  ATOM 1 4  0.0 0.0 0.0
  EDGE 7   0.1 0.1 0.1
END
""")
    assert "never declares" in read.problems[0]


def test_a_block_with_no_name_is_refused():
    read = read_cgd_string("""
CRYSTAL
  GROUP P1
  NODE 1 4  0.0 0.0 0.0
  EDGE  0.0 0.0 0.0  1.0 0.0 0.0
END
""")
    assert "no NAME" in read.problems[0]


def test_a_name_that_is_not_there_raises():
    with pytest.raises(KeyError):
        read_cgd_string(PCU)["dia"]


def test_a_file_that_is_not_cgd_is_a_file_with_no_nets():
    assert len(read_cgd_string("hello\nworld\n")) == 0


def test_a_live_edge_center_keyword_is_read_and_ignored():
    """PORMAKE's topology database writes four of its 2403 nets with
    ``EDGE_CENTER`` as a keyword rather than as the ``#`` comment the
    RCSR file uses.

    Without the word in the keyword set those lines are read as rows
    belonging to the ``NODE`` above them, and the read dies on a
    coordinate where a coordination number was expected -- taking the
    whole catalogue with it rather than one net.  A midpoint says
    nothing a pair of endpoints has not, so an entry that has only
    midpoints comes back as a net with no edges, which is a refusal
    the caller can report.
    """
    read = read_cgd_string("""
CRYSTAL
  NAME bcu-b
  GROUP Pm-3m
  CELL 1.1547 1.1547 1.1547 90.0 90.0 90.0
  NODE 1 8  0.0 0.0 0.0
  NODE 2 8  0.5 0.5 0.5
  EDGE_CENTER  0.25 0.25 0.25
END
""")
    assert read.entries == ()
    assert "bcu-b has no edges" in read.problems[0]


def test_an_edge_center_beside_real_edges_changes_nothing():
    """The RCSR file writes them as comments and this reader has
    always dropped them; naming the keyword must not start reading
    them."""
    read = read_cgd_string("""
CRYSTAL
  NAME pcu
  GROUP Pm-3m
  NODE 1 6  0.0 0.0 0.0
  EDGE  0.0 0.0 0.0   0.0 0.0 1.0
  EDGE_CENTER  0.0 0.0 0.5
  EDGE  0.0 0.0 0.0   0.0 1.0 0.0
  EDGE  0.0 0.0 0.0   1.0 0.0 0.0
END
""")
    assert len(read["pcu"].edges) == 3


# ============================================== against the real file

def test_the_rcsr_file_reads(rcsr_path):
    """2931 nets, one refusal, and the refusal is ``moo-a``."""
    read = read_cgd(rcsr_path)
    assert len(read) > 2900
    assert [p.split()[2] for p in read.problems] == ["moo-a"]
    assert sum(1 for e in read if e.dimension == 2) == 200


def test_the_reader_does_not_need_a_cgd_error_to_be_caught(rcsr_path):
    """Nothing in the RCSR file raises out of the reader; everything
    it cannot use comes back in ``problems``."""
    try:
        read_cgd(rcsr_path)
    except CgdError as exc:                 # pragma: no cover
        pytest.fail(f"the reader raised instead of collecting: {exc}")


# ============================================================ writing

def _pcu(a=5.0):
    from xtal import Lattice, Structure
    from xtal.core.structure import TOPOLOGY, Bond

    structure = Structure.from_arrays(Lattice.cubic(a), ["Zn"],
                                      [[0.0, 0.0, 0.0]],
                                      space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        structure.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    structure.touch()
    return structure


def _net_from_bonds(structure):
    """Every perceived bond as a net edge, so that the edges come from
    the geometry rather than from anything the writer was told."""
    from dataclasses import replace

    from xtal.core import bonding, p1
    from xtal.core.structure import TOPOLOGY

    cell = p1.expand(structure)
    for bond in bonding.graph(structure).bonds:
        record = bonding.bond_between(structure, cell, bond.i, bond.j,
                                      image_b=bond.image)
        structure.bonds.append(replace(record, kind=TOPOLOGY))
    structure.touch()
    return structure


def _written_and_read_back(structure, name="net"):
    from xtal.io.cgd import entry_of, write_cgd_string

    text = write_cgd_string([entry_of(structure, name)])
    read = read_cgd_string(text)
    assert not read.problems, read.problems
    return read[name]


def test_a_drawn_net_is_written_as_one_p1_block():
    entry = _written_and_read_back(_pcu(), "pcu")
    assert entry.group == "P1"
    assert len(entry.nodes) == 1
    assert len(entry.edges) == 3
    assert entry.cell == pytest.approx((5.0, 5.0, 5.0, 90.0, 90.0, 90.0))


def test_an_edge_to_its_own_image_counts_twice_at_the_vertex():
    """pcu has one vertex and three edges and is six-coordinated.
    Declaring three would be refused by every reader that expands the
    file and counts, Systre and this application's own among them."""
    entry = _written_and_read_back(_pcu())
    assert entry.nodes[0].coordination == 6


@pytest.mark.parametrize("which", ["pcu", "diamond", "rutile"])
def test_a_written_net_reads_back_as_the_same_net(which, rutile):
    """The whole point of the file: what Systre reads is the net the
    Net panel named.  Compared by canonical key, which is equal if and
    only if the nets are -- so an edge landing on the wrong vertex, a
    lost lattice image or a miscounted coordination all fail here.
    Rutile is drawn over a space group, so the expansion is tested
    and not only a net that was already in P1."""
    from xtal import Lattice, Structure
    from xtal.analysis import rcsr
    from xtal.analysis.topology import net_of

    if which == "pcu":
        structure = _pcu()
    elif which == "diamond":
        corners = [[0.0, 0.0, 0.0], [0.0, 0.5, 0.5],
                   [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]
        frac = corners + [[c + 0.25 for c in p] for p in corners]
        structure = _net_from_bonds(Structure.from_arrays(
            Lattice.cubic(3.567), ["C"] * 8, frac, space_group="P1"))
    else:
        structure = _net_from_bonds(rutile)

    drawn = net_of(structure)
    read = rcsr.expand(_written_and_read_back(structure))
    assert read.n_vertices == drawn.n_vertices
    assert len(read.edges) == len(drawn.edges)
    assert read.key() == drawn.key()


def test_an_edge_across_a_cell_face_is_written_at_its_real_length():
    """The second endpoint carries the lattice image.  Written without
    it, every edge that crosses a face runs back across the whole
    cell, which is still a valid file and is a different net."""
    import numpy as np

    from xtal import Lattice, Structure

    corners = [[0.0, 0.0, 0.0], [0.0, 0.5, 0.5],
               [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]
    frac = corners + [[c + 0.25 for c in p] for p in corners]
    lattice = Lattice.cubic(3.567)
    structure = _net_from_bonds(Structure.from_arrays(
        lattice, ["C"] * 8, frac, space_group="P1"))
    entry = _written_and_read_back(structure)
    lengths = [np.linalg.norm(lattice.to_cart(np.subtract(b, a)))
               for a, b in entry.edges]
    assert lengths == pytest.approx([3.567 * 3 ** 0.5 / 4] * 16)


def test_a_net_over_a_linker_writes_only_the_nodes():
    """The linker's atoms are not vertices of anything, and a file
    that listed them would give Systre isolated points to refuse."""
    from xtal import Lattice, Structure
    from xtal.core.structure import TOPOLOGY, Bond
    from xtal.io.cgd import entry_of

    elements, frac = ["Zn"], [[0.0, 0.0, 0.0]]
    for axis in range(3):
        for t in (0.25, 0.5, 0.75):
            point = [0.0, 0.0, 0.0]
            point[axis] = t
            elements.append("C" if t == 0.5 else "O")
            frac.append(point)
    structure = Structure.from_arrays(Lattice.cubic(8.0), elements,
                                      frac, space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        structure.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    structure.touch()
    assert len(entry_of(structure).nodes) == 1


def test_nothing_drawn_is_refused_rather_than_written_empty():
    from xtal import Lattice, Structure
    from xtal.io.cgd import entry_of

    structure = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                      [[0.0, 0.0, 0.0]],
                                      space_group="P1")
    with pytest.raises(CgdError, match="no net"):
        entry_of(structure)


def test_two_vertices_in_one_place_are_refused():
    """An endpoint is matched to a node by position, so two nodes a
    hair apart make every edge at either of them a guess -- and the
    file would describe whichever net the guess made."""
    from xtal import Lattice, Structure
    from xtal.core.structure import TOPOLOGY, Bond
    from xtal.io.cgd import entry_of

    structure = Structure.from_arrays(
        Lattice.cubic(5.0), ["Zn", "X"],
        [[0.0, 0.0, 0.0], [0.9985, 0.0, 0.0]], space_group="P1")
    structure.bonds.append(Bond(0, 0, (1, 0, 0), kind=TOPOLOGY))
    structure.bonds.append(Bond(1, 1, (0, 1, 0), kind=TOPOLOGY))
    structure.touch()
    with pytest.raises(CgdError, match="same place"):
        entry_of(structure)


def test_a_title_with_spaces_is_written_as_one_word():
    """A name is one token to every reader; ``MOF 5`` would come back
    as ``MOF``."""
    structure = _pcu()
    structure.meta["title"] = "MOF 5 net"
    from xtal.io.cgd import entry_of, write_cgd_string

    text = write_cgd_string([entry_of(structure)])
    assert read_cgd_string(text).entries[0].name == "MOF_5_net"


def test_a_coordinate_just_below_zero_is_not_written_negative():
    from xtal.io.cgd import CgdEntry, CgdNode, write_cgd_string

    entry = CgdEntry("x", "P1", (CgdNode("1", 2, (-1e-9, 0.0, 0.5)),),
                     (((0.0, 0.0, 0.5), (1.0, 0.0, 0.5)),))
    assert "-0.000000" not in write_cgd_string([entry])


def test_the_writer_saves_to_a_file(tmp_path):
    from xtal.io.cgd import entry_of, write_cgd

    written = write_cgd(tmp_path / "pcu.cgd", [entry_of(_pcu(), "pcu")])
    assert len(read_cgd(written)["pcu"].edges) == 3
