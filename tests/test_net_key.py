"""The canonical key: the answer as a decision rather than a filter.

The coordination sequence and the point symbol name a net by
recognising it, and two nets can share both.  The key names it by
*writing it down*: the net reduced to the smallest cell it has and
described in the one way that does not depend on how it arrived, so
that two nets are the same net if and only if the strings match.

Everything here is a statement about that "if and only if".  A test
that only checks a net keys equal to itself checks nothing -- the
tests that matter are the ones that describe the same net in a
different cell, a different basis and a different order, and demand
the same string back.
"""

from itertools import product

import numpy as np
import pytest

from xtal.analysis import rcsr
from xtal.analysis.topology import Edge, Net, TopologyError

# ====================================================== nets to key


def pcu() -> Net:
    """Simple cubic, as RCSR writes it: one vertex, three edges."""
    return Net(1, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                   Edge(0, 0, (0, 0, 1))))


def doubled_pcu() -> Net:
    """The same net in a 2x2x2 cell: eight vertices, twenty-four
    edges, and not one thing about the net changed."""
    def number(x, y, z):
        return x * 4 + y * 2 + z

    edges = []
    for x, y, z in product(range(2), repeat=3):
        for axis in range(3):
            point, image = [x, y, z], [0, 0, 0]
            point[axis] += 1
            if point[axis] == 2:
                point[axis], image[axis] = 0, 1
            edges.append(Edge(number(x, y, z), number(*point),
                              tuple(image)))
    return Net(8, tuple(edges))


def dia() -> Net:
    """Diamond, in its primitive cell."""
    return Net(2, (Edge(0, 1, (0, 0, 0)), Edge(0, 1, (-1, 0, 0)),
                   Edge(0, 1, (0, -1, 0)), Edge(0, 1, (0, 0, -1))))


def rebased(net: Net, matrix) -> Net:
    """The same net in another basis -- a different cell for the same
    crystal, which is not a different net."""
    return Net(net.n_vertices, tuple(
        Edge(e.i, e.j, tuple(int(v) for v in
                             np.array(e.image) @ np.array(matrix)))
        for e in net.edges), net.labels, net.orbits)


def relabelled(net: Net, order) -> Net:
    """The same net with its vertices numbered differently."""
    where = {old: new for new, old in enumerate(order)}
    return Net(net.n_vertices, tuple(
        Edge(where[e.i], where[e.j], e.image) for e in net.edges))


# ============================================== the cell does not count

def test_the_same_net_in_a_bigger_cell_has_the_same_key():
    """The claim the whole of stage two rests on.  RCSR writes pcu
    with one vertex and three edges; nothing a user draws will be in
    that cell, and the key has to see through the difference."""
    assert doubled_pcu().key() == pcu().key()


def test_reducing_a_supercell_gives_back_the_cell_it_repeats():
    """Not just the same key -- the same net, eight vertices divided
    by the eight translations the cell did not know it had."""
    smallest = doubled_pcu().minimal()
    assert smallest.n_vertices == 1
    assert len(smallest.edges) == 3


def test_a_change_of_basis_does_not_change_the_key():
    """A net described in a sheared cell is the same net: the images
    are read in a different basis and the graph is untouched."""
    shear = [[1, 0, 0], [1, 1, 0], [0, 1, 1]]
    assert rebased(pcu(), shear).key() == pcu().key()
    assert rebased(dia(), shear).key() == dia().key()


def test_renumbering_the_vertices_does_not_change_the_key():
    assert relabelled(dia(), [1, 0]).key() == dia().key()


def test_a_net_described_in_a_cell_of_its_own_copies_keys_as_one():
    """A net whose cycles close on every second cell is two
    interpenetrating copies of a smaller net, and the *name* of a net
    has never included how many copies of it there are: the key is one
    chain's, and the copies are counted separately."""
    two = Net(1, (Edge(0, 0, (2, 0, 0)),))
    one = Net(1, (Edge(0, 0, (1, 0, 0)),))
    assert two.key() == one.key()
    assert two.multiplicity() == 2


# ================================================ different nets differ

def test_different_nets_have_different_keys():
    """The other half of if-and-only-if.  These three are
    4-coordinated, 6-coordinated and 8-coordinated and no two of them
    are the same net."""
    bcu = Net(1, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1)), Edge(0, 0, (1, 1, 1))))
    keys = {pcu().key(), dia().key(), bcu.key()}
    assert len(keys) == 3


def test_the_key_says_how_periodic_the_net_is():
    """A layer is keyed in two dimensions, in the cell of the layer --
    not in the three-dimensional cell it happened to be drawn in."""
    square = Net(1, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0))))
    assert square.key().startswith("2:1:")


def test_a_disconnected_quotient_graph_is_refused():
    """Two nets described in one cell have no smallest cell between
    them, and asking for one is a caller's mistake rather than an
    answer to give."""
    two = Net(2, (Edge(0, 0, (1, 0, 0)), Edge(1, 1, (1, 0, 0))))
    with pytest.raises(TopologyError):
        two.key()


# ==================================================== against the RCSR

def test_the_key_tells_apart_two_nets_the_invariants_cannot(
        rcsr_catalogue):
    """sxd and vng have the same coordination sequences and the same
    point symbols, which is why stage one reports both.  They are not
    the same net, and the key is what says so."""
    first, second = rcsr_catalogue["sxd"], rcsr_catalogue["vng"]
    if not (first.key and second.key):
        pytest.skip("the index was built without keys")
    assert first.fingerprint().token() == second.fingerprint().token()
    assert first.key != second.key


def test_every_name_the_invariants_share_is_separated_by_the_key(
        rcsr_catalogue):
    """The fourteen.

    Six groups of RCSR names have the same coordination sequences and
    the same point symbols as each other, which is the measured half a
    percent the fingerprint cannot resolve and the reason this stage
    exists.  Every one of them has to come out with a key of its own --
    "one of sxd, vng" is what stage two was for.
    """
    if not rcsr_catalogue.keyed:
        pytest.skip("the index was built without keys")
    for group in (("sin", "lcv-f"), ("fnh", "noz", "vma"),
                  ("sxd", "vng"), ("swc", "ska"), ("vcn", "vcq"),
                  ("vnc", "vne", "vnf")):
        entries = [rcsr_catalogue[name] for name in group]
        tokens = {e.fingerprint().token() for e in entries}
        assert len(tokens) == 1, group
        assert len({e.key for e in entries}) == len(group), group


def test_a_net_that_shares_pcus_invariants_is_named_by_its_key(
        rcsr_catalogue):
    """The fingerprint of the drawn net is looked up and so is its
    key, and where the second one answers it is the answer: one name,
    and the report says it was decided rather than merely matched."""
    found = rcsr.identify(pcu(), rcsr_catalogue)
    assert found.names == ("pcu",)
    assert found.key == pcu().key()
    if not rcsr_catalogue.keyed:
        pytest.skip("the index was built without keys")
    assert found.decided


def test_a_net_the_rcsr_does_not_have_is_a_fact_and_not_a_hint(
        rcsr_catalogue):
    """Simple cubic with a second-neighbour edge along a.  A key that
    matches nothing is a statement about the RCSR rather than about how
    hard the search tried -- and where a few catalogued nets have no
    key of their own, the statement says how many."""
    net = Net(1, (Edge(0, 0, (1, 0, 0)), Edge(0, 0, (0, 1, 0)),
                  Edge(0, 0, (0, 0, 1)), Edge(0, 0, (2, 0, 0))))
    found = rcsr.identify(net, rcsr_catalogue)
    if not rcsr_catalogue.keyed:
        pytest.skip("the index was built without keys")
    assert found.verdict == "unknown"
    assert found.decided
    assert "canonical form" in found.sentence()


def test_where_the_two_layers_disagree_the_report_says_both():
    """The one place the layers can contradict each other.

    A net whose invariants match a catalogued name and whose canonical
    form matches nothing is not that net -- it is a different net with
    the same coordination sequence and point symbol, which is exactly
    what the fourteen ambiguous names are.  The key decides it, and the
    name it ruled out is printed rather than quietly dropped, because a
    disagreement between two independent calculations is the most
    interesting thing on the page.
    """
    entry = rcsr.CatalogueEntry(
        "zzz", 3, pcu().fingerprint().sequences,
        pcu().fingerprint().symbols, "Pm-3m", 1, 3,
        key="3:1:not the key of pcu")
    found = rcsr.identify(pcu(), rcsr.Catalogue((entry,)))
    assert found.verdict == "unknown"
    assert found.decided
    assert found.looks_like == ("zzz",)
    assert "zzz" in found.caveat()
    assert "canonical form" in found.caveat()


def test_a_net_that_cannot_be_keyed_still_reports_its_invariants(
        monkeypatch, rcsr_catalogue):
    """The key is the second layer and not the only one: a net too
    large or too tangled to key is named by its invariants, exactly as
    it was before there was a key at all."""
    def refuse(self, budget=0):
        raise TopologyError("too large to key")

    monkeypatch.setattr(Net, "key", refuse)
    found = rcsr.identify(pcu(), rcsr_catalogue)
    assert found.names == ("pcu",)
    assert not found.decided
    assert found.key == ""


# ================================================ the index carries it

def test_an_index_written_and_read_back_keeps_its_keys(tmp_path):
    """The key has to survive the file, or the panel gets it from
    nowhere."""
    entry = rcsr.CatalogueEntry("zzz", 3, ((6, 18),), ("4^12.6^3",),
                                "Pm-3m", 1, 3, key=pcu().key())
    written = rcsr.write_index(rcsr.Catalogue((entry,), "test.cgd"),
                               tmp_path / "index.json.gz")
    import gzip
    import json
    payload = json.loads(gzip.open(written, "rt").read())
    assert payload["format"] == 2
    read = rcsr.CatalogueEntry.from_row(payload["nets"][0])
    assert read == entry


def test_an_index_written_before_the_key_still_opens():
    """An index built by the version before this one has seven fields
    to a row and no keys.  It is a net with no canonical form rather
    than a broken file: the invariants in it are as true as they were,
    and only the certainty is missing."""
    old = ["zzz", 3, [[6, 18]], ["4^12.6^3"], "Pm-3m", 1, 3]
    entry = rcsr.CatalogueEntry.from_row(old)
    assert entry.key == ""
    assert not rcsr.Catalogue((entry,)).keyed
    assert rcsr.Catalogue((entry,)).unkeyed == ("zzz",)


# ============================================== the index checks itself

@pytest.mark.slow
def test_the_index_has_no_two_names_with_one_key(rcsr_catalogue):
    """The check that says the canonicalisation is canonical.

    A key that is self-consistent but not canonical does not fail
    quietly -- it gives two descriptions of one net two different
    strings, and across a file of 2929 nets it collides names in bulk.
    Nothing here may share a key with anything else.
    """
    clashes = {key: names
               for key, names in rcsr_catalogue.by_key.items()
               if len(names) > 1}
    assert not clashes


def doubled(net: Net) -> Net:
    """The same net described in a 2x2x2 cell."""
    cells = list(product(range(2), repeat=3))
    where = {cell: k for k, cell in enumerate(cells)}
    edges = []
    for edge in net.edges:
        for cell in cells:
            target = [cell[c] + edge.image[c] for c in range(3)]
            edges.append(Edge(
                edge.i * 8 + where[cell],
                edge.j * 8 + where[tuple(v % 2 for v in target)],
                tuple(v // 2 for v in target)))
    return Net(net.n_vertices * 8, tuple(edges))


@pytest.mark.slow
def test_catalogued_nets_key_the_same_in_a_doubled_cell():
    """The check that says the key sees through a cell, run against
    real nets rather than the two written out above.

    A description in a doubled cell has eight times the vertices and
    eight times the edges and is the same net -- and a canonicalisation
    that is self-consistent but not canonical is exactly what fails
    here and nowhere else.  ``sql`` is in the list because a layer in a
    doubled cell falls into eight pieces that never touch, which is the
    case that has to be split before it is keyed.
    """
    from xtal.analysis.rcsr import expand, source_file
    from xtal.io.cgd import read_cgd

    path = source_file()
    if path is None:
        pytest.skip("the RCSR .cgd is not in this tree")
    file = read_cgd(path)
    for name in ("pcu", "dia", "nbo", "sod", "qtz", "bcu", "srs",
                 "sql"):
        net = expand(file[name])
        assert doubled(net).components()[0].key() == net.key(), name


@pytest.mark.slow
def test_every_key_in_the_index_agrees_with_its_invariants(
        rcsr_catalogue):
    """The two layers are computed independently, so they are each
    other's check: a net named by its key must be a net whose
    fingerprint matches too."""
    for entry in rcsr_catalogue.entries:
        if not entry.key:
            continue
        assert entry.name in rcsr_catalogue.lookup(entry.fingerprint())
