"""Build the likely frameworks: the linker as a block, the plan, the
trial, and the module that strings them together.

The vote is :mod:`tests.test_synthesis`'s.  Here a forecast is written
by hand -- the shares are whatever the test says -- so what is checked
is how a forecast becomes candidates and builds, not what the table
happens to vote today.  The plan needs the catalogue and no RDKit; the
linker needs RDKit; a build needs the MOF builder.
"""

from __future__ import annotations

import pytest

from xtal import install
from xtal.build import MISSING, installed
from xtal.modules import Job, synthesis
from xtal.modules.registry import Availability
from xtal.mof import candidates, precedent
from xtal.mof.candidates import Attempt, Candidate, LinkerBlock, Trial
from xtal.mof.catalog import Catalog
from xtal.mof.catalog import installed as builder_installed
from xtal.mof.precedent import Forecast, Novelty, Query, Salt, Share

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)
needs_builder = pytest.mark.skipif(
    not builder_installed(), reason="the MOF builder is not installed")

#: Stand-ins for a typed linker that need no RDKit: E14 is the
#: catalogue's own phenylene, which is what BDC becomes.
DITOPIC = LinkerBlock("OC(=O)c1ccc(cc1)C(=O)O", "*c1ccc(*)cc1", 2,
                      "E14")
TRITOPIC = LinkerBlock("btc", "*c1cc(*)cc(*)c1", 3, "BTC-BLOCK")


@pytest.fixture(scope="module")
def catalog():
    return Catalog.default()


def forecast(nets, nodes, metal="Zr"):
    """A vote written by hand: ``[(value, share), ...]`` for each."""
    return Forecast(
        query=Query(Salt(metal, metal), (("x", frozenset()),)),
        nodes=tuple(Share(v, s, 1) for v, s in nodes),
        nets=tuple(Share(v, s, 1) for v, s in nets),
        interpenetrated=None, neighbours=(),
        novelty=Novelty(1.0, True, True, True, 1), source="by hand")


# ---------------------------------------------------------- the linker

@needs_rdkit
@pytest.mark.parametrize("text, star, topicity", [
    ("terephthalic acid", "*c1ccc(*)cc1", 2),
    ("[O-]C(=O)c1ccc(cc1)C(=O)[O-]", "*c1ccc(*)cc1", 2),
    ("trimesic acid", "*c1cc(*)cc(*)c1", 3),
    ("fumaric acid", "*/C=C/*", 2),             # trans, still
    ("OC(=O)/C=C\\C(=O)O", "*/C=C\\*", 2),     # maleic: cis
    ("NH2-BDC", "*c1ccc(*)c(N)c1", 2),
])
def test_a_carboxylic_acid_becomes_a_connection_point_on_its_carbon(
        text, star, topicity):
    """The carboxylate is the node's in this catalogue -- N16 is
    Zn4O(CO2)6 -- so the linker keeps the carbon it hung off and
    nothing more.  Kept, a second carboxylate would double every
    joint."""
    block = candidates.linker_block(text)

    assert block.starred == star
    assert block.topicity == topicity


@needs_rdkit
def test_the_acid_and_its_anion_are_one_block():
    """Same name, so typing either finds the block the other wrote."""
    acid = candidates.linker_block("terephthalic acid")
    anion = candidates.linker_block("[O-]C(=O)c1ccc(cc1)C(=O)[O-]")

    assert acid.name == anion.name


@needs_rdkit
@pytest.mark.parametrize("text", [
    "4,4'-bipyridine",                  # pyridyl donors
    "2-methylimidazole",                # an azolate
    "COC(=O)c1ccc(cc1)C(=O)OC",         # an ester is not a carboxylate
])
def test_a_linker_with_no_carboxylate_is_refused_by_name(text):
    with pytest.raises(candidates.CandidateError,
                       match="only carboxylate"):
        candidates.linker_block(text)


@needs_rdkit
def test_the_written_block_has_one_point_per_carboxylate(tmp_path):
    from xtal.mof.catalog import read_building_block

    block = candidates.linker_block("trimesic acid")
    path = candidates.write_linker(block, tmp_path)
    read = read_building_block(path)

    assert read.n_connections == 3
    assert read.composition == {"C": 6, "H": 3}


# ------------------------------------------------------------ the plan

def test_a_node_formula_is_read_into_metals():
    assert candidates.node_metals("Zr6") == {"Zr": 6}
    assert candidates.node_metals("CuZn2") == {"Cu": 1, "Zn": 2}


def test_only_plain_carboxylate_clusters_are_offered(catalog):
    """A zinc porphyrin (N2) has the metal and the four connections,
    and is not what a carboxylate linker makes; it came first for
    Zn + BDC before this."""
    offered = [b.name for b in candidates.node_blocks(catalog,
                                                      {"Zn": 1}, 4)]

    assert "N2" not in offered
    assert offered and all(
        catalog.building_block(n).composition.get("C") == 4
        for n in offered)


def test_a_ditopic_linker_goes_in_the_edges(catalog):
    found, _ = candidates.plan(
        forecast([("fcu", 0.9)], [("Zr6", 0.8)]), DITOPIC, catalog)

    assert found[0] == Candidate("fcu", ((0, "N419"),), "E14", "Zr6",
                                 0.72)


def test_a_tritopic_linker_is_a_node_beside_the_metal(catalog):
    """HKUST-1 is tbo: BTC is the 3-connected node and the Cu2
    paddlewheel the 4-connected one, joined with no linker between."""
    found, _ = candidates.plan(
        forecast([("tbo", 1.0)], [("Cu2", 1.0)], "Cu"), TRITOPIC,
        catalog)

    assert found[0].nodes == ((0, "BTC-BLOCK"), (1, "N17"))
    assert found[0].edge == ""


def test_candidates_come_best_scored_first(catalog):
    found, _ = candidates.plan(
        forecast([("pcu", 0.2), ("fcu", 0.8)], [("Zr6", 1.0)]),
        DITOPIC, catalog)

    assert [c.net for c in found][:1] == ["fcu"]
    assert [c.score for c in found] == sorted(
        (c.score for c in found), reverse=True)


def test_what_cannot_be_tried_is_said_once_each(catalog):
    """A net the builder does not have, a net with no slot for the
    linker, and a node with no cluster: each a row with its reason,
    and the node once however many nets wanted it."""
    _, skipped = candidates.plan(
        forecast([("no-such-net", 0.5), ("pcu", 0.3), ("fcu", 0.2)],
                 [("Zr6", 0.6), ("Pu9", 0.4)]),
        TRITOPIC, catalog)
    why = {s.what: s.why for s in skipped}

    assert why["no-such-net"] == "not in the builder's nets"
    assert "no 3-connected node" in why["pcu"]

    _, skipped = candidates.plan(
        forecast([("pcu", 0.5), ("fcu", 0.5)], [("Pu9", 1.0)]),
        DITOPIC, catalog)

    assert [s.what for s in skipped] == ["Pu9"]
    assert "pcu (6-c)" in skipped[0].why and "fcu (12-c)" in skipped[0].why


def test_a_candidate_spells_the_build_that_makes_it_again():
    """The report's rebuild column is parsed back into the request the
    trial built, so following it builds the same framework."""
    from xtal.mof.build import BuildRequest

    candidate = Candidate("tbo", ((0, "BTC-BLOCK"), (1, "N17")), "",
                          "Cu2", 1.0)
    params = dict(p.split("=", 1) for p in
                  candidate.spelled.replace("-p ", "").split())

    assert BuildRequest.parse(params["topology"], params["nodes"],
                              params.get("edges", "")) \
        == candidate.request()


# ----------------------------------------------------------- the trial

def test_the_best_build_is_the_net_asked_for_with_nothing_overlapping():
    def tried(net, confirmed, overlaps=0):
        return Attempt(Candidate(net, (), "", "", 0), built=True,
                       confirmed=confirmed, overlaps=overlaps)

    crowded, other, clean = (tried("a", True, 3), tried("b", False),
                             tried("c", True))

    assert Trial([crowded, other, clean], [], []).best is clean
    assert Trial([crowded, other], [], []).best is crowded
    assert Trial([other], [], []).best is None


@needs_builder
def test_a_candidate_that_fails_is_a_row_and_the_next_is_still_tried(
        catalog):
    """PORMAKE raises what it raises on a block that will not go; the
    trial is a list of candidates, and one bad one must not lose the
    rest."""
    wrong = Candidate("pcu", ((0, "N17"),), "E14", "Cu2", 0.9)   # 4-c
    right = Candidate("pcu", ((0, "N16"),), "E14", "Zn4", 0.5)
    attempts, untried = candidates.attempt([wrong, right], catalog)

    assert [a.status for a in attempts] == ["did not build", "built"]
    assert "4 connection point" in attempts[0].verdict
    assert attempts[1].structure is not None and untried == []


def test_an_assertion_inside_pormake_is_one_failed_row(monkeypatch):
    """PORMAKE's locator asserts, and indexes past the end, on a block
    it cannot place -- not a MofError, and not a ValueError either.
    Caught as one, the first such candidate ended the whole trial."""
    import importlib

    # By path: xtal.mof exports a function called build, which shadows
    # the module of that name in a `from xtal.mof import build`.
    build_module = importlib.import_module("xtal.mof.build")

    def build(request, directory, catalog):
        raise AssertionError

    monkeypatch.setattr(build_module, "build", build)
    two = [Candidate("pcu", ((0, "N16"),), "E14", "Zn4", 0.5),
           Candidate("pcu", ((0, "N197"),), "E14", "Zn4", 0.4)]
    attempts, _ = candidates.attempt(two, catalog=None)

    assert [a.status for a in attempts] == ["did not build"] * 2
    assert attempts[0].verdict == "AssertionError"


@needs_builder
def test_once_the_time_is_spent_the_rest_are_listed_untried(catalog):
    """At least one is always built -- a budget of nothing would
    otherwise answer nothing -- and the rest are said, not lost."""
    first = Candidate("pcu", ((0, "N16"),), "E14", "Zn4", 0.5)
    second = Candidate("pcu", ((0, "N197"),), "E14", "Zn4", 0.4)
    attempts, untried = candidates.attempt([first, second], catalog,
                                           budget=0.0)

    assert [a.candidate for a in attempts] == [first]
    assert untried == [second]


@needs_builder
def test_stop_leaves_the_rest_untried(catalog):
    first = Candidate("pcu", ((0, "N16"),), "E14", "Zn4", 0.5)
    second = Candidate("pcu", ((0, "N197"),), "E14", "Zn4", 0.4)
    _, untried = candidates.attempt([first, second], catalog,
                                    cancelled=lambda: True)

    assert untried == [second]


# ---------------------------------------------------------- the module

def test_the_build_entry_needs_the_mof_builder_too(monkeypatch):
    from xtal.modules import mof

    monkeypatch.setattr(synthesis, "installed", lambda: True)
    monkeypatch.setattr(mof, "available",
                        lambda: Availability(False, "needs ase"))
    action = synthesis.SYNTHESIS.action("build")

    assert not action.check()
    assert action.check().reason == "needs ase"


def test_without_rdkit_the_build_entry_names_the_extra(monkeypatch):
    monkeypatch.setattr(synthesis, "installed", lambda: False)
    available = synthesis.SYNTHESIS.action("build").check()

    assert not available
    assert install.command("build") in available.reason


@needs_rdkit
def test_a_linker_that_cannot_be_built_with_fails_before_any_vote():
    action = synthesis.SYNTHESIS.action("build")
    result = action.run(Job(params=action.coerce({
        "metal": "Zn", "linkers": "2-methylimidazole"})))

    assert not result.ok
    assert "only carboxylate" in result.message


@needs_rdkit
@needs_builder
@pytest.mark.slow
def test_uio_66_is_built_from_its_synthesis_into_the_workspace(tmp_path):
    """The whole of it, headless: the vote, the BDC block written into
    the workspace, fcu with the Zr6 cluster first, and the structure
    handed back to open."""
    from xtal.workspace import Workspace

    workspace = Workspace.create(tmp_path / "ws")
    entry = workspace.add_document("synthesis")
    action = synthesis.SYNTHESIS.action("build")
    result = action.run(Job(
        params=action.coerce({"metal": "ZrCl4", "linkers": "BDC",
                              "solvents": "DMF", "budget": 2.0}),
        folder=entry.next_run("synthesis", "build")))

    assert result.ok, result.message
    assert result.structure.meta["title"].startswith("fcu-N419-SYN-")
    assert result.message.startswith("Built fcu with N419")
    assert len(list(workspace.blocks.glob("SYN-*.xyz"))) == 1
    tried = result.report.tables[0]
    assert tried.title == "Frameworks tried"
    assert tried.rows[0].texts[4] == "built"


@needs_rdkit
@needs_builder
@pytest.mark.slow
def test_hkust_1_is_built_with_btc_as_the_three_connected_node():
    action = synthesis.SYNTHESIS.action("build")
    result = action.run(Job(params=action.coerce({
        "metal": "Cu(NO3)2·3H2O", "linkers": "trimesic acid",
        "solvents": "DMF, EtOH, water", "budget": 2.0})))

    assert result.ok, result.message
    assert result.structure.meta["title"].startswith("tbo-SYN-")
    assert "N17" in result.structure.meta["title"]


def test_a_query_that_only_reads_never_reaches_the_builder(monkeypatch):
    """The vote alone stays the quick entry: it must not import the
    candidate module, whose builds are the slow half."""
    import sys

    monkeypatch.delitem(sys.modules, "xtal.mof.candidates",
                        raising=False)
    action = synthesis.SYNTHESIS.action("forecast")
    action.run(Job(params=action.coerce({"metal": "", "linkers": ""})))

    assert "xtal.mof.candidates" not in sys.modules
    assert precedent.NEIGHBOURS == action.defaults()["neighbours"]
