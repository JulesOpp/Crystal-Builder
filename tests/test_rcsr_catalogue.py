"""The catalogue: expanding the RCSR file, and what it can tell apart.

The index that ships is generated, so these are the tests that say the
generator was right.  Two of them are the file checking the code rather
than the other way round -- every ``NODE`` declares its own
coordination number, and every edge endpoint has to land on a node
orbit -- and those are what make a hand-written table of 17 plane
groups safe to rely on.
"""

import pytest

from xtal.analysis import rcsr
from xtal.analysis.rcsr import PLANE_GROUPS, expand, plane_group_operations
from xtal.io.cgd import read_cgd

#: Nets whose invariants RCSR publishes and everyone in the field
#: knows.  Wrong here means wrong everywhere.
KNOWN = {
    "pcu": ((6, 18, 38, 66, 102), "4^12.6^3"),
    "dia": ((4, 12, 24, 42, 64), "6^6"),
    "srs": ((3, 6, 12, 24, 35), "10^3"),
    "nbo": ((4, 12, 28, 50, 76), "6^4.8^2"),
    "sod": ((4, 10, 20, 34, 52), "4^2.6^4"),
    "sql": ((4, 8, 12, 16, 20), "4^4.6^2"),
    "hcb": ((3, 6, 9, 12, 15), "6^3"),
}

#: How many plane-group operations each group has.  The table is
#: generated from generators, so an order that is wrong is a
#: generator that is wrong.
ORDERS = {"p1": 1, "p2": 2, "pm": 2, "pg": 2, "cm": 4, "p2mm": 4,
          "p2mg": 4, "p2gg": 4, "c2mm": 8, "p4": 4, "p4mm": 8,
          "p4gm": 8, "p3": 3, "p3m1": 6, "p31m": 6, "p6": 6,
          "p6mm": 12}


# ========================================================= plane groups

def test_all_seventeen_plane_groups_are_there():
    assert set(PLANE_GROUPS) == set(ORDERS)


@pytest.mark.parametrize("symbol", sorted(ORDERS))
def test_a_plane_group_has_the_order_it_should(symbol):
    assert len(plane_group_operations(symbol)) == ORDERS[symbol]


def test_a_group_that_is_not_a_plane_group_is_refused():
    with pytest.raises(rcsr.RcsrError):
        plane_group_operations("p5mm")


# ====================================================== known net values

@pytest.mark.parametrize("name", sorted(KNOWN))
def test_a_net_expands_to_the_invariants_rcsr_publishes(name, rcsr_path):
    """Not a round trip: these numbers are from the literature, and
    agreeing with them is the only evidence that the expansion means
    anything."""
    sequence, symbol = KNOWN[name]
    net = expand(read_cgd(rcsr_path)[name])
    fingerprint = net.fingerprint()
    assert fingerprint.sequences[0][:5] == sequence
    assert fingerprint.symbols == (symbol,)


def test_a_layer_net_is_two_periodic(rcsr_path):
    """``sql`` is written in ``p4mm`` and is a layer.  Its images come
    out of the plane-group table two-dimensional and are padded, and
    the periodicity is what says the padding was right."""
    assert expand(read_cgd(rcsr_path)["sql"]).periodicity() == 2


def test_an_unstated_origin_choice_is_recovered(rcsr_path):
    """``thz`` is written ``I41/amd`` and is in the second setting.  In
    the first its edges point at nothing -- which is a hard failure and
    not a silent one, so retrying the other setting is safe."""
    assert expand(read_cgd(rcsr_path)["thz"]).n_vertices == 96


# ================================================= the shipped catalogue

def test_the_index_is_there_and_holds_the_file(rcsr_catalogue):
    assert len(rcsr_catalogue) > 2900
    assert "2019-06-01" in rcsr_catalogue.source


def test_the_catalogue_holds_two_and_three_periodic_nets(rcsr_catalogue):
    periodicities = {e.periodicity for e in rcsr_catalogue.entries}
    assert periodicities == {2, 3}
    two = sum(1 for e in rcsr_catalogue.entries if e.periodicity == 2)
    assert two == 200


def test_the_famous_nets_are_in_it(rcsr_catalogue):
    for name in KNOWN:
        assert rcsr_catalogue[name].name == name


def test_the_fingerprint_names_all_but_a_handful(rcsr_catalogue):
    """The measurement the whole design rests on.

    Over the 2931 nets in the file the coordination sequence alone
    leaves 122 names in 54 groups it cannot separate -- **pcu** among
    them, with **tfs**, **smd**, **sxd** and **vng** -- and adding the
    point symbol takes that to 68 names in 33 groups, naming 2863
    uniquely.  If this number grows, something in the invariants has
    been weakened and the panel has started guessing.
    """
    clashing = {t: names for t, names
                in rcsr_catalogue.by_token.items() if len(names) > 1}
    involved = sum(len(n) for n in clashing.values())
    assert involved <= 68, sorted(clashing.values())
    assert len(rcsr_catalogue) - involved >= 2863


def test_the_point_symbol_earns_its_place(rcsr_catalogue):
    """Without it the ambiguity nearly doubles, and pcu is inside it.

    A first version built on the coordination sequence alone would
    answer the commonest question in the field with a list of five
    names, which is the reason the expensive invariant is computed.
    """
    from collections import defaultdict

    walks = defaultdict(list)
    for entry in rcsr_catalogue.entries:
        walks[(entry.periodicity, entry.sequences)].append(entry.name)
    ambiguous = [n for v in walks.values() if len(v) > 1 for n in v]
    assert len(ambiguous) > 100
    assert "pcu" in ambiguous


def test_no_two_layer_nets_share_a_fingerprint(rcsr_catalogue):
    """All 33 ambiguous groups are 3-periodic: the 200 layer nets are
    each named uniquely, which is a second check on the plane-group
    table -- a wrong operation there would merge two of them."""
    layers = [e for e in rcsr_catalogue.entries if e.periodicity == 2]
    tokens = [e.fingerprint().token() for e in layers]
    assert len(set(tokens)) == len(layers) == 200


def test_pcu_is_not_one_of_the_ambiguous_ones(rcsr_catalogue):
    """It shares its coordination sequence with four other nets and is
    separated by its point symbol.  The commonest net in the field
    being ambiguous would make the feature useless on the day it
    shipped."""
    entry = rcsr_catalogue["pcu"]
    assert rcsr_catalogue.lookup(entry.fingerprint()) == ("pcu",)
    others = [e.name for e in rcsr_catalogue.entries
              if e.sequences == entry.sequences]
    assert set(others) == {"pcu", "tfs", "smd", "sxd", "vng"}


def test_the_catalogue_is_read_once(rcsr_catalogue):
    assert rcsr.catalogue() is rcsr.catalogue()


def test_a_near_miss_is_offered_when_nothing_matches(rcsr_catalogue):
    """A fingerprint with pcu's walk and a symbol nothing has: the
    four nets that walk the same way are what to look at."""
    from xtal.analysis.topology import Fingerprint

    pcu = rcsr_catalogue["pcu"]
    invented = Fingerprint(3, pcu.sequences, ("9^99",))
    assert rcsr_catalogue.lookup(invented) == ()
    reason, names = rcsr_catalogue.nearest(invented)
    assert reason == "coordination sequence"
    assert set(names) == {"pcu", "tfs", "smd", "sxd", "vng"}


# ============================================ the build, against the file

@pytest.mark.slow
def test_every_entry_agrees_with_its_own_declared_coordination(
        rcsr_path):
    """The check that makes the expansion trustworthy, run over the
    whole file rather than over the index built from it.

    A vertex whose degree is not the coordination number its own NODE
    line declares means the symmetry expansion produced the wrong
    orbit, and it is refused at build time rather than catalogued.

    The same sweep checks that no two NODE lines are one orbit, which
    is what lets the net search read vertex transitivity p off the
    NODE count (:func:`xtal.analysis.netsearch.facts_of_entry`):
    expanding the file twice to ask the two questions apart would be
    ten seconds for nothing.
    """
    read = read_cgd(rcsr_path)
    refused, merged = [], []
    for entry in read:
        try:
            net = expand(entry)
        except rcsr.RcsrError as exc:
            refused.append((entry.name, str(exc)))
            continue
        if len(set(net.orbits)) != len(entry.nodes):
            merged.append(entry.name)
    assert len(refused) <= 2, refused
    assert merged == []
    assert len(read) - len(refused) > 2900
