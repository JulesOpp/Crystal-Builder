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
    """pcu is 1 1 1 1 in Pm-3m, 221; mcm is two vertices and two edges."""
    pcu = _facts("pcu")
    assert (pcu.number, pcu.p, pcu.q) == (221, 1, 1)
    assert pcu.transitivity == (1, 1, 1, 1)
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


def test_faces_and_tiles_are_matched_where_the_rcsr_knows_them():
    """r and s are the natural tiling's, read from the RCSR's own data
    (scripts/rcsr_transitivity.py).  fcu is 1 1 1 2 -- one kind of face,
    and the octahedra and tetrahedra are two kinds of tile -- and sod
    1 1 2 1: squares and hexagons around one kind of cage."""
    assert _found(NetQuery.parse(transitivity="1 1 1 1"),
                  "pcu", "dia", "fcu", "sod") == ["pcu", "dia"]
    assert _found(NetQuery.parse(transitivity="1 1 1 2"),
                  "pcu", "fcu") == ["fcu"]
    assert _found(NetQuery.parse(transitivity="1 1 2 1"),
                  "fcu", "sod") == ["sod"]


def test_a_number_where_the_rcsr_knows_nothing_still_matches_nothing():
    """A layer has no tiles, and half the 3-D nets have no natural
    tiling on record (the RCSR writes 0 faces, 0 tiles).  Answering
    "one kind of tile" for those would be claiming knowledge nobody
    has."""
    assert _found(NetQuery.parse(transitivity="1 1 1 1"), "sql") == []
    aca = _facts("aca")
    assert aca.transitivity == (3, 2, None, None)
    assert not NetQuery.parse(transitivity="3 2 1 *").matches(aca)
    assert NetQuery.parse(transitivity="3 2 * *").matches(aca)


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



# ======================================================== the catalogue

@pytest.fixture(scope="module")
def catalog():
    from xtal.mof import Catalog, database_root

    if database_root() is None:
        pytest.skip("the vendored PORMAKE database is missing")
    return Catalog.default()


def _user_net(folder, name, edges):
    text = ["CRYSTAL", f"  NAME {name}", "  GROUP Pm-3m",
            "  CELL 1 1 1 90 90 90", "  NODE 1 6  0 0 0"]
    text += ["  EDGE  0 0 0   0 0 1"] * edges
    path = folder / f"{name}.cgd"
    path.write_text("\n".join(text + ["END"]) + "\n", encoding="utf-8")
    return path


def test_a_pormake_net_takes_p_and_q_from_the_rcsr_entry_of_its_name(
        catalog):
    """PORMAKE's tfm writes eleven EDGE lines where the RCSR writes
    two; counting lines would file it under q = 11 and a search for
    ``3 2`` would never find it."""
    tfm = catalog.topology("tfm")
    assert tfm.edge_lines == 11
    assert (tfm.facts().p, tfm.facts().q) == (3, 2)


def test_a_users_net_is_taken_at_its_word(tmp_path):
    """A file of the user's called pcu is not assumed to be the RCSR's
    pcu: its own lines are its transitivity."""
    from xtal.mof.catalog import read_topology

    facts = read_topology(_user_net(tmp_path, "pcu", 3)).facts()
    assert (facts.p, facts.q, facts.number) == (1, 3, 221)


def test_a_net_with_no_edge_lines_has_unknown_q(tmp_path):
    """Unknown, not zero: a search for ``* *`` still finds it and a
    search for ``1 1`` does not claim to know."""
    from xtal.mof.catalog import read_topology

    facts = read_topology(_user_net(tmp_path, "mine", 0)).facts()
    assert facts.q is None
    assert NetQuery.parse(transitivity="1 *").matches(facts)
    assert not NetQuery.parse(transitivity="1 1").matches(facts)


def test_an_unrecognised_group_symbol_has_no_number_and_is_still_listed(
        catalog):
    odd = catalog.topology("lcw_component_3")
    assert odd.group == "opm" and odd.facts().number is None
    assert NetQuery.parse(name="lcw_component").matches(odd.facts())
    assert not NetQuery.parse(number="1-230").matches(odd.facts())


def test_a_catalogue_layer_answers_to_its_plane_group(catalog):
    hcb = catalog.topology("hcb").facts()
    assert (hcb.dimension, hcb.number, hcb.p, hcb.q) == (2, 17, 1, 1)
    assert catalog.topology("hcb").summary() == \
        "3-c  ·  p6mm (17)  ·  [1 1 1]"


def test_facts_for_the_whole_catalogue_expand_no_net(catalog):
    """The list asks every row, so a fact that needed the graph would
    be ten seconds before the dialog opened."""
    for topology in catalog.topologies():
        topology.facts()
        assert "placement" not in topology._cache, topology.name


def test_q_is_the_kinds_of_edge_and_not_the_edge_lines():
    """The .cgd writes stz with nine EDGE lines for its six kinds of
    edge -- one of 18 nets where counting lines overstated q, so a
    search for "4 6" did not find it."""
    stz = _facts("stz")
    assert (stz.p, stz.q) == (4, 6)
    assert len(rcsr.nets()["stz"].edges) == 9


def test_a_net_the_rcsr_does_not_list_keeps_what_its_file_says(tmp_path):
    """A net of the user's, or one the RCSR has since dropped: p and q
    are its own NODE and EDGE lines, and nothing is known of r and s."""
    from xtal.io.cgd import read_cgd_string
    (entry,) = read_cgd_string(
        "CRYSTAL\n  NAME not-an-rcsr-net\n  GROUP Pm-3m\n"
        "  CELL 1 1 1 90 90 90\n  NODE 1 6 0 0 0\n"
        "  EDGE 0 0 0 1 0 0\nEND\n").entries
    facts = facts_of_entry(entry)
    assert facts.transitivity == (1, 1, None, None)


def test_the_transitivity_table_is_what_the_script_writes():
    """The two RCSR downloads are kept in tests/data/rcsr as they
    arrived; the shipped table must be what the script makes of them,
    and must cover every net the application can draw."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "rcsr_transitivity", root / "scripts" / "rcsr_transitivity.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    assert script.TABLE.read_bytes() == script._encoded(script.table())
    known = rcsr.transitivity()
    missing = [e.name for e in rcsr.nets() if e.name not in known]
    assert missing == ["elv"]           # dropped by the RCSR since 2019


def test_the_rcsr_record_is_read_the_way_the_rcsr_reads_it():
    """A net with no tiling writes 0 faces, 0 tiles and a blank tiling
    line, and the file ends with a record whose serial number is -1."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "rcsr_transitivity", root / "scripts" / "rcsr_transitivity.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    record = "\n".join([
        "start", "7", "abc", "1a",
        " 0  !number of other symbols", " 1  !number of names", "X",
        " 0  !number of other names", " 0  !number of keywords",
        " 0  !number of references", "Pm-3m   221",
        "  1.0  1.0  1.0  90.000  90.000  90.000",
        "2", "V1  6", "0 0 0", "0,0,0", "1 a", "m-3m", "48",
        "V2  6", "0.5 0.5 0.5", "1/2,1/2,1/2", "1 b", "m-3m", "48",
        "1", "E1  2", "0.5 0 0", "1/2,0,0", "3 c", "4/mmm",
        "0", "0", "0", "", "unk",
        "start", "-1", ""])
    assert script.read_3d(record) == {"abc": [2, 1, None, None]}
