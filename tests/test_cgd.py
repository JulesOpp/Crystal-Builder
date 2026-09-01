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
