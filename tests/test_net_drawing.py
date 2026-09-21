"""Drawing a named RCSR net as a structure.

The 2728 files this replaces were generated once by
``resources/topo/Top2Cif.py`` and committed, and the two things it got
wrong were invisible in a picture and are not invisible here: a bead
placed on top of a node, and the beads either side of an edge's
midpoint being the same atom twice.  Both are asserted below, because
a duplicate atom inside a structure is a wrong structure even when the
picture looks right.

The declared coordination is the check that matters.  RCSR states how
many edges meet at each vertex, and a net drawn with an edge missing
or an edge too many is a *different net* -- which is exactly the
failure mode that would otherwise reach the Net panel and be named.
"""

import numpy as np
import pytest

from xtal.analysis import rcsr
from xtal.build import topology
from xtal.core import bonding, p1

#: Five nets with nothing in common but being drawable: a hexagonal
#: one, the two textbook cubic ones, a chiral one and a zeolite.
NETS = ("acs", "pcu", "dia", "srs", "sod")


@pytest.fixture(scope="module")
def nets():
    return rcsr.nets()


@pytest.mark.parametrize("name", NETS)
def test_every_node_has_the_coordination_rcsr_declares(name, nets):
    """A vertex short of an edge is a different net, and the Net panel
    would name it as one."""
    entry = nets[name]
    structure = topology.structure_for(entry)
    cell = p1.expand(structure)
    coordination = bonding.graph(structure).coordination()
    drawn = {int(c) for c, element
             in zip(coordination, cell.elements, strict=True)
             if element == topology.NODE_ELEMENT}
    assert drawn == {node.coordination for node in entry.nodes}


@pytest.mark.parametrize("name", NETS)
def test_every_bead_joins_exactly_two_others(name, nets):
    """A bead is an interior point of one edge, so it has the atom
    before it and the atom after it and nothing else.  Three means two
    edges have been run together."""
    structure = topology.structure_for(nets[name])
    cell = p1.expand(structure)
    coordination = bonding.graph(structure).coordination()
    assert {int(c) for c, element
            in zip(coordination, cell.elements, strict=True)
            if element == topology.EDGE_ELEMENT} == {2}


@pytest.mark.parametrize("name", NETS)
def test_no_two_atoms_land_on_top_of_each_other(name, nets):
    """``Top2Cif.py`` placed a bead at each of ``n/beads`` for ``n`` up
    to and including ``beads``, so the last one sat exactly on the far
    node -- in the ``acs.cif`` it wrote, ``He8`` is a symmetry image of
    ``H0``.  The beads either side of an edge's midpoint are a second
    source of the same thing, and merging duplicates is what answers
    it."""
    cell = p1.expand(topology.structure_for(nets[name]))
    distance = np.linalg.norm(
        cell.cart[:, None] - cell.cart[None, :], axis=-1)
    np.fill_diagonal(distance, np.inf)
    assert distance.min() > 0.5


def test_the_beads_sit_about_a_bond_length_apart(nets):
    """The scale exists for this and nothing else: the ``.cgd`` cells
    are normalised so an edge is about one unit long, and eight times
    that with eight beads is a picture whose rods read as rods."""
    cell = p1.expand(topology.structure_for(nets["pcu"]))
    distance = np.linalg.norm(
        cell.cart[:, None] - cell.cart[None, :], axis=-1)
    np.fill_diagonal(distance, np.inf)
    assert distance.min() == pytest.approx(1.0, abs=0.05)


def test_a_net_arrives_with_its_bonds_already_drawn(nets):
    """Perception on the defaults finds none of them -- a hydrogen and
    a helium bond inside 0.68 A and the beads are at 1.0 -- so a net
    that relied on it would open as loose spheres."""
    structure = topology.structure_for(nets["pcu"])
    assert structure.bonds
    assert not bonding.perceive(structure, bonding.BondRules(),
                                include_explicit=False)


def test_no_distance_rule_could_have_found_these_edges():
    """The reason the bonds are written rather than perceived, as a
    fact about the nets rather than an assertion in a docstring: in
    **rht** two beads on different edges are closer together than two
    beads on the same one, so a cutoff that keeps every edge keeps
    those too, and one that excludes them cuts real edges elsewhere."""
    structure = topology.by_name("rht")
    cell = p1.expand(structure)
    bonded = {(min(b.i, b.j), max(b.i, b.j))
              for b in bonding.graph(structure).bonds}
    separation = np.linalg.norm(
        cell.cart[:, None] - cell.cart[None, :], axis=-1)

    along = max(separation[i, j] for i, j in bonded)
    across = min(separation[i, j]
                 for i in range(len(separation))
                 for j in range(i + 1, len(separation))
                 if (i, j) not in bonded)
    assert across < along


def test_a_net_whose_edges_do_not_land_on_it_is_refused(nets):
    """**thz** writes one endpoint a whole bond length from where its
    own symmetry puts it -- :mod:`xtal.analysis.rcsr` notes the same
    file being loose about this.  It is the only one of the 2727 that
    will not draw, and it says which it is."""
    with pytest.raises(topology.NetDrawingError, match="thz"):
        topology.by_name("thz")


def test_a_layer_is_drawn_flat_in_its_layer_group(nets):
    """200 of the 2931 entries are 2-periodic.  They are drawn as the
    MOF builder builds them, in the plane group's layer group with
    every atom at z = 0 -- a sheet with a tilt or a second copy would
    be a picture of a different net."""
    from xtal.core import p1

    kgm = topology.structure_for(nets["kgm"])
    assert kgm.space_group.number == 191
    assert kgm.lattice.parameters[2] == pytest.approx(
        rcsr.LAYER_C * topology.SCALE)
    cell = p1.expand(kgm)
    assert {round(f[2] % 1.0, 6) for f in cell.frac} == {0.0}
    nodes = [e for e in cell.elements if e == topology.NODE_ELEMENT]
    assert len(nodes) == 3
    assert "kgm" in topology.names() and "hcb" in topology.names()


def test_a_net_with_no_cell_is_refused_by_name(nets):
    """Four of them: llw-z, nts, ssp and cys.  The reader reads CELL
    only to ignore it, so their absence surfaces here."""
    with pytest.raises(topology.NetDrawingError, match="nts"):
        topology.structure_for(nets["nts"])
    assert "nts" not in topology.names()


def test_a_name_that_is_not_a_net_says_so():
    with pytest.raises(topology.NetDrawingError, match="conquistador"):
        topology.by_name("conquistador")


def test_the_structure_remembers_which_net_it_is(nets):
    """So that a tab has a title and a saved file says what it was."""
    structure = topology.by_name("pcu")
    assert structure.meta["topology"] == "pcu"
    assert structure.meta["title"] == "pcu"


def test_the_nets_ship_with_the_package():
    """The index that ships beside them holds invariants and a key and
    no coordinates, so it names a net and cannot draw one."""
    assert rcsr.NETS.is_file()
    assert len(topology.names()) > 2500
