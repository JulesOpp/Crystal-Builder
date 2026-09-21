"""Naming the net: the drawn graph, looked up in the RCSR.

The application could already say *6-coordinated, 6, 18, 38, 66,
4^12.6^3*.  What it could not say was **pcu**, which is the word the
user came for, and these are the tests that it now does.

**Only the connectivity matters.**  Everything here rests on that: the
same net in a bigger cell, in a different setting, drawn on a linker
rather than on a bond, has to come back with the same name.  A test
that passes only in the cell the net was written in is testing the
cell.
"""

from itertools import product

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.analysis import rcsr
from xtal.analysis.topology import Edge, Net, net_of
from xtal.core.structure import TOPOLOGY, Bond

# ====================================================== nets to draw on


def pcu_net(a=5.0) -> Structure:
    """One vertex, three edges along a, b and c: simple cubic."""
    structure = Structure.from_arrays(Lattice.cubic(a), ["Zn"],
                                      [[0.0, 0.0, 0.0]],
                                      space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        structure.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    structure.touch()
    return structure


def diamond() -> Structure:
    """Carbon in the diamond structure, in P1.

    Written out rather than expanded from Fd-3m so that the net under
    test is not built by the same code that built the catalogue entry
    it is matched against.
    """
    corners = [[0.0, 0.0, 0.0], [0.0, 0.5, 0.5],
               [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]
    frac = corners + [[c + 0.25 for c in point] for point in corners]
    return Structure.from_arrays(Lattice.cubic(3.567), ["C"] * 8, frac,
                                 space_group="P1")


def net_from_bonds(structure) -> Structure:
    """Turn every perceived bond into a net edge.

    The net of a structure whose atoms *are* its vertices is its own
    bond graph, and going through perception means the edges come from
    the geometry rather than from anything this module wrote down.
    """
    from xtal.core import bonding

    for bond in bonding.graph(structure).bonds:
        structure.bonds.append(
            Bond(bond.i, bond.j, bond.image, kind=TOPOLOGY))
    structure.touch()
    return structure


# ============================================================ the names

def test_a_simple_cubic_net_is_pcu(rcsr_catalogue):
    report = rcsr.describe(net_of(pcu_net()), rcsr_catalogue)
    assert report.name == "pcu"
    assert report.headline() == "pcu"


def test_diamond_is_dia(rcsr_catalogue):
    """Four-coordinated, 4, 12, 24, 42 and 6^6.  Built from the
    geometry of a real diamond cell, not from RCSR's own entry."""
    net = net_of(net_from_bonds(diamond()))
    assert rcsr.describe(net, rcsr_catalogue).name == "dia"


def test_a_square_layer_is_sql_and_a_honeycomb_is_hcb(rcsr_catalogue):
    """The 2-periodic half, which is also the test that the
    hand-written plane-group table is right: these two nets are
    catalogued in ``p4mm`` and ``p6mm`` and gemmi has neither."""
    square = Structure.from_arrays(
        Lattice.from_parameters(4.0, 4.0, 20.0, 90, 90, 90),
        ["Zn"], [[0.0, 0.0, 0.0]], space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0)):
        square.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    square.touch()
    assert rcsr.describe(net_of(square), rcsr_catalogue).name == "sql"

    honeycomb = Structure.from_arrays(
        Lattice.from_parameters(4.0, 4.0, 20.0, 90, 90, 120),
        ["C", "C"], [[1 / 3, 2 / 3, 0.0], [2 / 3, 1 / 3, 0.0]],
        space_group="P1")
    for image in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
        honeycomb.bonds.append(Bond(0, 1, image, kind=TOPOLOGY))
    honeycomb.touch()
    assert rcsr.describe(net_of(honeycomb),
                         rcsr_catalogue).name == "hcb"


def test_a_two_periodic_net_is_named_two_periodic(rcsr_catalogue):
    """The dimension is the *net's*, not the crystal's: sql is drawn
    in a three-dimensional cell and is a layer."""
    square = Structure.from_arrays(
        Lattice.cubic(4.0), ["Zn"], [[0.0, 0.0, 0.0]],
        space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0)):
        square.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    square.touch()
    report = rcsr.describe(net_of(square), rcsr_catalogue)
    assert report.name == "sql"
    assert "2-periodic" in report.sentence()


# =============================================== the cell does not count

def test_the_same_net_in_a_bigger_cell_is_the_same_net(rcsr_catalogue):
    """A 2x2x2 description of pcu: eight vertices, twenty-four edges,
    and still pcu.  This is the property the whole lookup rests on --
    RCSR writes pcu with one vertex and three edges, and nothing a
    user draws will be in that cell."""
    def index(x, y, z):
        return x * 4 + y * 2 + z

    edges = []
    for x, y, z in product(range(2), repeat=3):
        for axis in range(3):
            point, image = [x, y, z], [0, 0, 0]
            point[axis] += 1
            if point[axis] == 2:
                point[axis], image[axis] = 0, 1
            edges.append(Edge(index(x, y, z), index(*point),
                              tuple(image)))
    doubled = Net(8, tuple(edges))
    assert doubled.n_vertices == 8
    assert len(doubled.edges) == 24
    assert rcsr.describe(doubled, rcsr_catalogue).name == "pcu"


def test_a_net_drawn_over_a_linker_is_named_from_the_net(rcsr_catalogue):
    """The point of the feature.  The net edge runs node to node
    straight through a three-atom linker, and the linker's atoms are
    not vertices of anything -- counting them would make every
    invariant, and so the name, wrong."""
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

    net = net_of(structure)
    assert net.n_vertices == 1              # the ten linker atoms are not
    assert rcsr.describe(net, rcsr_catalogue).name == "pcu"


# ====================================================== the honest cases

def test_adding_the_body_diagonal_to_pcu_gives_bcu(rcsr_catalogue):
    """The check that the naming is right and not merely consistent.

    Simple cubic with the body diagonal added is body-centred cubic,
    which is a fact about crystals and not about this code -- and the
    catalogue has to agree with it.
    """
    net = Net(1, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1)), Edge(0, 0, (1, 1, 1))))
    assert rcsr.describe(net, rcsr_catalogue).name == "bcu"


def test_a_net_the_rcsr_does_not_have_says_so(rcsr_catalogue):
    """Simple cubic with a *second*-neighbour edge along a: an
    8-coordinated net nobody has catalogued.  Not finding it is a
    result, and the invariants and the near misses are what make it
    one."""
    net = Net(1, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1)), Edge(0, 0, (2, 0, 0))))
    found = rcsr.identify(net, rcsr_catalogue)
    if found.names:                         # pragma: no cover
        pytest.skip(f"this net is catalogued after all: {found.names}")
    assert found.verdict == "unknown"
    assert found.headline() == "not in the RCSR"
    assert found.fingerprint.periodicity == 3
    # It walks like nothing catalogued, so the near misses are offered
    # on the weaker ground and the sentence says which.
    assert found.nearest_by == "coordination number"
    assert "bcu" in found.nearest
    assert "nearest by coordination number" in found.sentence()


def test_a_one_periodic_net_is_not_looked_up(rcsr_catalogue):
    """A chain has no entry to find: the RCSR net file holds 2- and
    3-periodic nets only, and rod packings are a separate publication.
    Saying "not found" would blame the net for the catalogue."""
    chain = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                  [[0.0, 0.0, 0.0]], space_group="P1")
    chain.bonds.append(Bond(0, 0, (1, 0, 0), kind=TOPOLOGY))
    chain.touch()
    found = rcsr.identify(net_of(chain), rcsr_catalogue)
    assert found.verdict == "uncatalogued"
    assert "2- and 3-periodic" in found.sentence()


def test_nothing_drawn_is_not_an_answer(rcsr_catalogue):
    plain = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                  [[0.0, 0.0, 0.0]], space_group="P1")
    report = rcsr.describe(net_of(plain), rcsr_catalogue)
    assert not report
    assert report.sentence() == "no net has been drawn"


def test_two_nets_that_share_both_invariants_are_told_apart(
        rcsr_catalogue):
    """Fourteen names in the file cannot be told apart by these two
    invariants: sxd and vng have the same coordination sequences and
    the same point symbols and are not the same net.

    Which is what the canonical key is for.  The invariants still
    match both -- that is a fact about the invariants and is unchanged
    -- and the answer is one name, decided rather than matched.
    """
    entry = rcsr_catalogue["sxd"]
    net = _as_net(entry)
    assert set(rcsr_catalogue.lookup(net.fingerprint())) == {"sxd",
                                                             "vng"}
    found = rcsr.identify(net, rcsr_catalogue)
    if not found.decided:
        pytest.skip("the index was built without canonical keys")
    assert found.names == ("sxd",)
    assert found.verdict == "named"


def _as_net(entry) -> Net:
    """A stand-in with an entry's fingerprint, for the cases where
    building the real net would just be re-running the index."""
    from xtal.analysis.rcsr import expand, source_file
    from xtal.io.cgd import read_cgd

    path = source_file()
    if path is None:
        pytest.skip("the RCSR .cgd is not in this tree")
    return expand(read_cgd(path)[entry.name])


# =========================================== interpenetration and pieces

def test_a_net_described_in_a_doubled_cell_is_not_two_nets():
    """One vertex joined to its own image two cells along is one
    component of the quotient graph and two separate chains in the
    crystal.  Miss that and every net in an even supercell is reported
    as one copy of itself."""
    net = Net(1, (Edge(0, 0, (2, 0, 0)),))
    assert net.periodicity() == 1
    assert net.multiplicity() == 2


def test_two_separate_nets_are_reported_separately(rcsr_catalogue):
    """Two pcu nets that never touch: interpenetration, which is the
    normal case in this field and not an error."""
    net = Net(2, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1)), Edge(1, 1, (1, 0, 0)),
                  Edge(1, 1, (0, 1, 0)), Edge(1, 1, (0, 0, 1))))
    report = rcsr.describe(net, rcsr_catalogue)
    assert len(report.parts) == 2
    assert report.name == "pcu"
    assert report.copies == 2
    assert "2-fold interpenetrated pcu" in report.sentence()


def test_an_isolated_vertex_is_not_a_component(rcsr_catalogue):
    """An atom with a net edge deleted from under it is not a net."""
    net = Net(2, (Edge(0, 0, (1, 0, 0)),))
    assert len(net.components()) == 1


# ================================================= the flagship, MOF-5

@pytest.mark.slow
def test_mof5_with_one_bond_between_its_oxygens_is_pcu(rcsr_catalogue):
    """The scenario the feature exists for, end to end.

    Read MOF-5, find its symmetry (Fm-3m), draw one net edge between
    the O1 at (1/4,1/4,1/4) and the one at (1/4,1/4,3/4), and let the
    space group draw the other five.  That is eight vertices and
    twenty-four edges in the conventional cell against RCSR's one and
    three, and it is pcu.
    """
    from pathlib import Path

    from xtal.core import bonding, p1, symmetry
    from xtal.io import read_cif

    source = (Path(__file__).resolve().parent.parent
              / "resources" / "samples" / "MOF-5.cif")
    if not source.is_file():
        pytest.skip("resources/samples/MOF-5.cif is not in this tree")

    structure, _report = symmetry.asymmetrize(read_cif(source))
    assert structure.space_group.number == 225

    cell = p1.expand(structure)

    def atom_at(target):
        delta = cell.frac - np.array(target)
        delta -= np.round(delta)
        distance = np.linalg.norm(delta @ structure.lattice.matrix,
                                  axis=1)
        return int(np.argmin(distance))

    first = atom_at([0.25, 0.25, 0.25])
    second = atom_at([0.25, 0.25, 0.75])
    assert cell.elements[first] == cell.elements[second] == "O"

    bond = bonding.bond_between(structure, cell, first, second,
                                (0, 0, 0), (0, 0, 0))
    structure.add_bond(Bond(bond.i, bond.j, bond.image, op=bond.op,
                            kind=TOPOLOGY))
    structure.touch()

    net = net_of(structure)
    assert (net.n_vertices, len(net.edges)) == (8, 24)
    report = rcsr.describe(net, rcsr_catalogue)
    assert report.name == "pcu"
    assert "6, 18, 38, 66" in report.sentence()
    assert "4^12.6^3" in report.sentence()


# ==================================== interpenetration, from the bonds

def test_a_crystal_is_asked_about_its_own_bonds_not_a_drawn_net():
    """net_of answers about a net somebody drew by hand. Asking the
    same question of the chemistry is what makes interpenetration
    something the application can answer without being told where the
    nodes are."""
    import pathlib

    from xtal.analysis.topology import interpenetration
    from xtal.io import FORMATS
    sample = (pathlib.Path(__file__).resolve().parent.parent
              / "resources" / "samples" / "MOF-5.cif")
    if not sample.exists():
        pytest.skip("sample structure not present")
    answer = interpenetration(FORMATS.read(sample))
    assert answer.fold == 1
    assert answer.frameworks == 1
    assert answer.text() == "not interpenetrated"


def test_two_frameworks_that_never_touch_are_two_fold():
    """The obvious half: a second framework disconnected from the
    first is another component."""
    from xtal.analysis.topology import Interpenetration
    net = Net(2, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1)), Edge(1, 1, (1, 0, 0)),
                  Edge(1, 1, (0, 1, 0)), Edge(1, 1, (0, 0, 1))))
    parts = [c for c in net.components() if c.periodicity() == 3]
    answer = Interpenetration(sum(c.multiplicity() for c in parts),
                              len(parts), 0)
    assert answer.fold == 2
    assert answer.text() == "2-fold interpenetrated"


def test_a_framework_doubled_inside_one_component_is_still_two():
    """The half a component count gets wrong, and the common one in
    deposited files: a net whose cycles close on every second cell is
    two copies described in one component."""
    net = Net(1, (Edge(0, 0, (2, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1))))
    assert net.periodicity() == 3
    assert len(net.components()) == 1, "one component"
    assert net.multiplicity() == 2, "and two copies in it"


def test_solvent_in_the_pores_is_not_a_second_framework():
    """Ni2Cl2BTDD carries eighteen molecules in its channels. Counting
    components alone would call it a nineteen-fold framework; only the
    3-periodic ones are frameworks."""
    import pathlib

    from xtal.analysis.topology import interpenetration
    from xtal.core import symmetry
    from xtal.io import FORMATS
    sample = (pathlib.Path(__file__).resolve().parent.parent
              / "resources" / "samples" / "Ni2Cl2BTDD.cif")
    if not sample.exists():
        pytest.skip("sample structure not present")
    merged, _ = symmetry.merge_duplicates(FORMATS.read(sample))
    answer = interpenetration(merged)
    assert answer.fold == 1
    assert answer.frameworks == 1
    assert answer.other == 18
