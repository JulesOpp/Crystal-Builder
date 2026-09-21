"""Searching nets by name, coordination, group number and transitivity.

The query is what both net lists -- the MOF builder's and the Net
builder's -- filter with, so a regression here is a wrong list in
both.  The facts are taken from the RCSR file itself, not invented:
a query that matches a made-up row proves nothing about the rows it
will meet.
"""

from fractions import Fraction

import gemmi
import numpy as np
import pytest

from xtal.analysis import rcsr
from xtal.analysis.netsearch import (
    NetQuery,
    NetQueryError,
    facts_of_entry,
    space_group_number,
)
from xtal.analysis.rcsr import (
    LAYER_C,
    LAYER_GROUPS,
    PLANE_GROUPS,
    as_layer,
    plane_group_number,
    plane_group_operations,
)


def _facts(name):
    return facts_of_entry(rcsr.nets()[name])


def _found(query, *names):
    return [n for n in names if query.matches(_facts(n))]


# ================================================================ facts

def test_an_rcsr_entry_gives_its_group_number_and_transitivity():
    """pcu is 1 1 in Pm-3m, 221; mcm is two vertices and two edges."""
    pcu = _facts("pcu")
    assert (pcu.number, pcu.p, pcu.q) == (221, 1, 1)
    assert pcu.coordinations == (6,)
    mcm = _facts("mcm")
    assert (mcm.dimension, mcm.p, mcm.q) == (2, 2, 2)
    assert sorted(mcm.coordinations) == [3, 4]


def test_a_layer_answers_to_its_plane_group_number():
    """hcb is 17, not the 191 of P6/mmm it is built in -- the number
    the RCSR prints beside it."""
    assert _facts("hcb").number == 17
    assert _found(NetQuery.parse(number="17"), "hcb") == ["hcb"]
    assert _found(NetQuery.parse(number="191"), "hcb") == []


def test_an_origin_choice_does_not_change_the_group_number():
    assert space_group_number("I41/amd:2") == 141
    assert space_group_number("opm") is None


def test_plane_groups_are_numbered_as_the_international_tables_do():
    assert plane_group_number("p1") == 1
    assert plane_group_number("pg") == 4
    assert plane_group_number("c2mm") == 9
    assert plane_group_number("p3m1") == 14
    assert plane_group_number("p6mm") == 17
    assert plane_group_number("P6/mmm") is None


# ================================================================ query

def test_an_empty_query_matches_everything():
    query = NetQuery.parse()
    assert query.empty
    assert _found(query, "pcu", "hcb", "mcm") == ["pcu", "hcb", "mcm"]


def test_a_name_matches_as_a_substring_ignoring_case():
    """``pc`` finds pcu, as the old one-box filter did."""
    assert _found(NetQuery.parse(name="PC"), "pcu", "dia") == ["pcu"]


def test_coordination_without_exclusive_needs_every_number_listed():
    """3,6 finds pyr (3,6) and not hcb (3 alone)."""
    query = NetQuery.parse(coordination="3,6")
    assert _found(query, "pyr", "hcb", "pcu") == ["pyr"]
    assert _found(NetQuery.parse(coordination="3"),
                  "pyr", "hcb", "pcu") == ["pyr", "hcb"]


def test_exclusive_coordination_rejects_a_net_with_a_third_kind():
    """3 exclusive is the 3-c nets only; pyr has a 6 as well."""
    query = NetQuery.parse(coordination="3", exclusive=True)
    assert _found(query, "pyr", "hcb", "srs") == ["hcb", "srs"]


def test_the_rcsr_spelling_of_coordination_is_read():
    assert NetQuery.parse(coordination="3,6-c").coordinations == {3, 6}
    assert NetQuery.parse(coordination="4-c").coordinations == {4}


def test_a_space_group_range_includes_both_ends():
    query = NetQuery.parse(number="221-225")
    assert _found(query, "pcu", "fcu", "dia") == ["pcu", "fcu"]
    listed = NetQuery.parse(number="221, 227")
    assert _found(listed, "pcu", "fcu", "dia") == ["pcu", "dia"]


def test_a_star_in_transitivity_matches_anything():
    query = NetQuery.parse(transitivity="1 1 * *")
    assert _found(query, "pcu", "sql", "mcm") == ["pcu", "sql"]
    assert _found(NetQuery.parse(transitivity="* 2"),
                  "pcu", "mcm") == ["mcm"]


def test_a_number_for_faces_matches_nothing_because_faces_are_unknown():
    """r and s belong to the natural tiling, which nothing here has.
    Matching them anyway would answer "one kind of face" with every
    net in the list."""
    query = NetQuery.parse(transitivity="1 1 1 1")
    assert _found(query, "pcu", "sql") == []


def test_packed_and_spaced_transitivity_are_the_same_query():
    spaced = NetQuery.parse(transitivity="1 2 * *").transitivity
    assert NetQuery.parse(transitivity="12**").transitivity == spaced
    assert NetQuery.parse(transitivity="[1,2]").transitivity == spaced
    assert NetQuery.parse(transitivity="1 2").transitivity == spaced


def test_a_transitivity_over_nine_is_written_with_spaces():
    assert NetQuery.parse(transitivity="1 11").transitivity == \
        (1, 11, None, None)


@pytest.mark.parametrize("field, given", [
    ("coordination", {"coordination": "3,x"}),
    ("number", {"number": "231"}),
    ("number", {"number": "230-221"}),
    ("transitivity", {"transitivity": "1 1 1 1 1"}),
    ("transitivity", {"transitivity": "1 a"}),
])
def test_an_unreadable_field_is_named_in_the_error(field, given):
    """The dialog reddens the field the error names; naming the wrong
    one points somebody at a box they typed correctly."""
    with pytest.raises(NetQueryError) as raised:
        NetQuery.parse(**given)
    assert raised.value.field == field


# =============================================================== layers

def _three_d(plane_op, z):
    rot, trans = plane_op
    out = []
    for i in range(3):
        row = [int(round(rot[i][j])) if i < 2 and j < 2 else 0
               for j in range(3)]
        if i == 2:
            row[2] = z
        term = "".join(f"{'+' if c > 0 else '-'}{'xyz'[j]}"
                       for j, c in enumerate(row) if c)
        shift = Fraction(float(trans[i]) if i < 2 else 0.0
                         ).limit_denominator(24)
        if shift:
            term += f"+{shift}"
        out.append(term.lstrip("+"))
    return gemmi.Op(",".join(out))


@pytest.mark.parametrize("plane", list(PLANE_GROUPS))
def test_every_plane_group_maps_to_the_layer_group_its_operations_make(
        plane):
    """The table is derived here, not trusted: the plane group's
    operations plus z -> -z, looked up by gemmi.  If this regresses a
    layer is built in the wrong group, and ``pg`` is the one it would
    be -- its setting is not one anybody checks by eye."""
    ops = gemmi.GroupOps([_three_d(op, z)
                          for op in plane_group_operations(plane)
                          for z in (1, -1)])
    found = gemmi.find_spacegroup_by_ops(ops)
    assert found is not None
    assert gemmi.SpaceGroup(LAYER_GROUPS[plane]).xhm() == found.xhm()


def test_a_layer_is_written_flat_at_z_zero_with_the_stated_c():
    layer = as_layer(rcsr.nets()["kgm"])
    assert layer.dimension == 3 and layer.group == "P6/mmm"
    assert layer.cell == (2.0, 2.0, LAYER_C, 90.0, 90.0, 120.0)
    assert all(node.frac[2] == 0.0 for node in layer.nodes)
    assert all(p[2] == 0.0 == q[2] for p, q in layer.edges)


def test_a_three_periodic_entry_is_not_rewritten():
    pcu = rcsr.nets()["pcu"]
    assert as_layer(pcu) is pcu


def test_every_layer_expands_to_the_net_its_plane_group_makes():
    """The mirror fixes the sheet, so it adds no vertex and no edge.
    If it did, a layer would build with its vertices doubled."""
    for entry in rcsr.nets():
        if entry.dimension != 2 or not entry.cell:
            continue
        flat = rcsr.expand(entry)
        built = rcsr.expand(as_layer(entry))
        assert len(built.orbits) == len(flat.orbits), entry.name
        assert len(built.edges) == len(flat.edges), entry.name
        assert np.array_equal(np.sort(built.orbits),
                              np.sort(flat.orbits)), entry.name

