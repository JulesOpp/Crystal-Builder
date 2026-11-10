"""From a synthesis: reading a salt, the vote, and the module.

The vote is :mod:`xtal.mof.precedent` and the entry is
:mod:`xtal.modules.synthesis`.  Most of these run on a small table
written here, through the :class:`~xtal.mof.precedent.Source` seam,
so they need no RDKit and say exactly what the vote should do; the
few that read the shipped table check that it still answers the
syntheses everybody knows the answer to.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

from xtal import install
from xtal.build import MISSING, installed
from xtal.modules import MODULES, Job, synthesis
from xtal.mof import precedent
from xtal.mof.precedent import Precedent, Query, Salt

ROOT = Path(__file__).resolve().parent.parent
needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)

BDC = ("bdc", frozenset({1, 2, 3, 4}))
BTC = ("btc", frozenset({1, 2, 5, 6}))
IMIDAZOLE = ("im", frozenset({7, 8}))


@dataclass
class Table:
    """A source of precedents written by hand."""

    rows: tuple
    name: str = "a table written for the test"

    def records(self):
        return self.rows

    def linker_bits(self):
        return (BDC, BTC, IMIDAZOLE)


def made(refcode, metal, linker, net, solvents=None, temperature=None,
         anions=None, node=None, interpenetrated=False):
    return Precedent(refcode, (metal,), (node or f"[{metal}]",),
                     (linker,), net, interpenetrated, anions, solvents,
                     temperature)


def query(metal="Zr", linkers=(BDC,), solvents=(), temperature=None,
          anions=()):
    return Query(Salt(metal, metal, anions), linkers, solvents, (),
                 temperature)


# ----------------------------------------------------------- reading

@pytest.mark.parametrize("text, metal, anions", [
    ("zinc nitrate hexahydrate", "Zn", ("NO3",)),
    ("Zn(NO3)2·6H2O", "Zn", ("NO3",)),
    ("ZrCl4", "Zr", ("Cl",)),
    ("ZrOCl2·8H2O", "Zr", ("O", "Cl")),
    ("Co(CH3COO)2·4H2O", "Co", ("OAc",)),
    ("Cu(ClO4)2", "Cu", ("ClO4",)),
    ("cobalt(II) hydroxide", "Co", ("OH",)),
    ("zirconium oxychloride octahydrate", "Zr", ("O", "Cl")),
    ("FeCl3·6H2O", "Fe", ("Cl",)),
    ("Al(NO3)3·9H2O", "Al", ("NO3",)),
    ("In(NO3)3·xH2O", "In", ("NO3",)),
    ("Cu(NO3)2.2.5H2O", "Cu", ("NO3",)),
    ("Zn(OAc)2·2H2O", "Zn", ("OAc",)),
    ("Co(acac)2", "Co", ("acac",)),
    ("Cu(BF4)2", "Cu", ("BF4",)),
    ("nickel(II) chloride hexahydrate", "Ni", ("Cl",)),
    ("lead nitrate", "Pb", ("NO3",)),
    ("Zr", "Zr", ()),
    ("zinc", "Zn", ()),
])
def test_a_salt_is_read_by_name_or_formula(text, metal, anions):
    """Perchlorate read as chloride and oxide, or a hydroxide read as
    an oxide, would compare the wrong counter-ion with every
    precedent."""
    salt = precedent.read_salt(text)

    assert salt.metal == metal
    assert set(salt.anions) == set(anions)


def test_a_roman_numeral_is_the_oxidation_state():
    assert precedent.read_salt("copper(II) acetate").oxidation == 2


def test_a_source_with_no_metal_is_refused_by_name():
    with pytest.raises(precedent.PrecedentError, match="carbon"):
        precedent.read_salt("carbon black")


def test_a_solvent_not_known_is_handed_back_rather_than_guessed():
    """A solvent dropped in silence moves the vote, so the answer has
    to be able to say which ones it left out."""
    read, unread = precedent.read_solvents(
        ["DMF", "EtOH", "water", "CID 31275", "ionic liquid"])

    assert read == (6228, 702, 962, 31275)
    assert unread == ("ionic liquid",)


def test_a_comma_inside_a_name_does_not_split_it():
    assert synthesis.split("DMF, 1,4-dioxane; water") == [
        "DMF", "1,4-dioxane", "water"]
    assert synthesis.split("BDC, 4,4'-bipyridine") == [
        "BDC", "4,4'-bipyridine"]


@needs_rdkit
def test_a_linker_is_the_same_as_acid_or_anion():
    """The table's linkers are MOFid's carboxylates, written as
    anions, and a person types the acid; compared as written they
    would never match."""
    acid = precedent.linker_key("terephthalic acid")
    anion = precedent.linker_key("[O-]C(=O)c1ccc(cc1)C(=O)[O-]")

    assert acid == anion


# -------------------------------------------------------- similarity

def test_the_same_synthesis_scores_one():
    p = made("A", "Zr", 0, "fcu", solvents=(6228,), temperature=120,
             anions=("Cl",))
    q = query(solvents=(6228,), temperature=120, anions=("Cl",))

    assert precedent.similarity(q, p, Table(()).linker_bits()) \
        == pytest.approx(1.0)


def test_an_unknown_condition_ranks_between_agreeing_and_not():
    """Most of the table records no conditions.  Scored as a
    disagreement, those would never vote; scored as agreement, they
    would outvote the syntheses that were done the same way."""
    bits = Table(()).linker_bits()
    q = query(solvents=(6228,))
    same = made("A", "Zr", 0, "fcu", solvents=(6228,))
    unknown = made("B", "Zr", 0, "fcu")
    other = made("C", "Zr", 0, "fcu", solvents=(962,))

    assert precedent.similarity(q, same, bits) \
        > precedent.similarity(q, unknown, bits) \
        > precedent.similarity(q, other, bits)


def test_an_analogous_metal_scores_half():
    assert precedent.metal_score("Hf", ("Zr",)) == 0.5
    assert precedent.metal_score("Zr", ("Zr",)) == 1.0
    assert precedent.metal_score("Zr", ("Cu",)) == 0.0


# --------------------------------------------------------------- vote

def test_the_nearest_precedents_outvote_the_rest():
    table = Table((
        made("UIO", "Zr", 0, "fcu"),
        made("UIO2", "Zr", 0, "fcu"),
        made("HKUST", "Cu", 1, "tbo"),
        made("ZIF", "Zn", 2, "sod"),
    ))
    answer = precedent.forecast(query(), table, neighbours=2)

    assert [s.value for s in answer.nets] == ["fcu"]
    assert {n.precedent.refcode for n in answer.neighbours} \
        == {"UIO", "UIO2"}


def test_a_precedent_with_no_net_votes_on_the_node_only():
    """Shares of the nets are out of the weight that named one --
    otherwise every share shrinks with the records MOFid could not
    name, and an answer of 40 % would mean nothing."""
    table = Table((
        made("A", "Zr", 0, "fcu", node="[Zr][Zr]"),
        made("B", "Zr", 0, None, node="[Zr][Zr]"),
    ))
    answer = precedent.forecast(query(), table)

    assert answer.nets[0].value == "fcu"
    assert answer.nets[0].share == pytest.approx(1.0)
    assert answer.nodes[0].support == 2


def test_one_node_written_two_ways_is_one_node():
    """Two papers write one Zr6 cluster with its oxygens in different
    places; as SMILES they would split the vote."""
    table = Table((
        made("A", "Zr", 0, "fcu", node="[Zr]1[Zr][Zr][Zr][Zr][Zr]1"),
        made("B", "Zr", 0, "fcu", node="[O][Zr]1[Zr][Zr][Zr][Zr][Zr]1"),
    ))
    answer = precedent.forecast(query(), table)

    assert [(s.value, s.support) for s in answer.nodes] == [("Zr6", 2)]


def test_the_answer_says_when_metal_and_linker_were_never_made_together():
    table = Table((made("A", "Zr", 1, "fcu"), made("B", "Cu", 0, "pcu")))
    novelty = precedent.forecast(query(), table).novelty

    assert novelty.metal_seen and novelty.linker_seen
    assert not novelty.metal_with_linker_seen
    assert "never together" in novelty.sentence()


def test_an_empty_source_is_an_error_not_an_empty_answer():
    with pytest.raises(precedent.PrecedentError, match="no precedents"):
        precedent.forecast(query(), Table(()))


# --------------------------------------------------- the shipped table

def test_the_shipped_table_says_where_it_came_from():
    """CC-BY needs the attribution to travel with the data."""
    source = precedent.BundledSource()

    assert any("CoRE MOF 2024" in s for s in source.citations())
    assert any("SynMOF" in s for s in source.citations())
    assert all(r.metals for r in source.records())


def test_a_refcode_family_is_one_precedent():
    """UiO-66's eleven re-determinations were eleven votes for one
    paper's fcu before the script folded them together."""
    refcodes = [r.refcode for r in precedent.BundledSource().records()]

    assert len(refcodes) == len(set(refcodes))
    assert "WIZMAV" in refcodes
    assert not any(c.startswith("WIZMAV") and c != "WIZMAV"
                   for c in refcodes)


@needs_rdkit
@pytest.mark.parametrize("salt, linker, net", [
    ("ZrCl4", "terephthalic acid", "fcu"),         # UiO-66
    ("Cu(NO3)2·3H2O", "trimesic acid", "tbo"),     # HKUST-1
])
def test_the_syntheses_everybody_knows_come_out_first(salt, linker, net):
    answer = precedent.forecast(Query.read(salt, [linker], ["DMF"]))

    assert answer.nets[0].value == net
    assert answer.novelty.metal_with_linker_seen


# ------------------------------------------------------------ module

def test_the_entry_is_registered_and_needs_no_document():
    module, action = MODULES.find("synthesis.forecast")

    assert module is synthesis.SYNTHESIS
    assert action.needs_structure is False
    assert action.writes_run_folder is False


def test_without_rdkit_the_entry_greys_out_naming_the_extra(monkeypatch):
    monkeypatch.setattr(synthesis, "installed", lambda: False)
    available = synthesis.SYNTHESIS.availability()

    assert not available
    assert install.command("build") in available.reason


@needs_rdkit
def test_a_run_reports_and_builds_nothing():
    """It is a vote about what forms; building one is the MOF
    builder's, and a structure here would open a tab nobody asked
    for."""
    action = synthesis.SYNTHESIS.action("forecast")
    result = action.run(Job(params=action.coerce({
        "metal": "ZrCl4", "linkers": "BDC",
        "solvents": "DMF, ionic liquid", "temperature": "120"})))

    assert result.ok and result.structure is None
    titles = [t.title for t in result.report.tables]
    assert "Nets the nearest precedents formed" in titles
    read = result.report.tables[0]
    assert "ionic liquid" in read.rows[2].value
    assert "fcu" in result.message


@needs_rdkit
@pytest.mark.parametrize("params, words", [
    ({"metal": "", "linkers": "BDC"}, "metal"),
    ({"metal": "Zr", "linkers": ""}, "linker"),
    ({"metal": "Zr", "linkers": "BDC", "temperature": "hot"}, "hot"),
    ({"metal": "Zr", "linkers": "not-a-linker"}, "not-a-linker"),
])
def test_a_query_that_cannot_be_read_fails_the_run_by_name(params,
                                                            words):
    action = synthesis.SYNTHESIS.action("forecast")
    result = action.run(Job(params=action.coerce(params)))

    assert not result.ok
    assert words in result.message


# ------------------------------------------------------------ script

def _script():
    spec = importlib.util.spec_from_file_location(
        "synthesis_precedents", ROOT / "scripts" /
        "synthesis_precedents.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_a_mofid_is_read_into_nodes_linkers_and_net():
    nodes, linkers, net, cat = _script().read_mofid(
        "[Cu][Cu].[O-]C(=O)c1ccc(cc1)C(=O)[O-] MOFid-v1.nbo,fof.cat1;"
        "X_ASR_pacman")

    assert nodes == ["[Cu][Cu]"]
    assert linkers == ["[O-]C(=O)c1ccc(cc1)C(=O)[O-]"]
    assert net == "nbo"
    assert cat is True


@pytest.mark.parametrize("word", ["UNKNOWN", "ERROR", "MISMATCH",
                                  "TIMEOUT"])
def test_what_mofid_writes_for_no_net_is_not_a_net(word):
    """Each of these was a vote for a net called TIMEOUT."""
    *_, net, _ = _script().read_mofid(
        f"[Zn].c1ncc[n-]1 MOFid-v1.{word}.cat0;X")

    assert net is None


def test_a_redetermination_is_its_compounds_refcode():
    script = _script()

    assert script.refcode("WIZMAV07_ASR_pacman") == "WIZMAV"
    assert script.refcode("OFODET_clean") == "OFODET"
    assert script.refcode("ja507947d_si_001_ASR_pacman") \
        == "ja507947d_si_001_ASR_pacman"


# ------------------------------------------------------ more of the vote

def test_every_share_is_out_of_one():
    """A share is a fraction of the weight that voted, so the shares
    of one question add up to one -- a record with two nodes splits
    its weight between them rather than counting twice."""
    table = Table((
        made("A", "Zr", 0, "fcu", node="[Zr][Zr]"),
        Precedent("B", ("Zr", "Cu"), ("[Zr]", "[Cu][Cu]"), (0,), "pcu",
                  True),
        made("C", "Zr", 1, "bcu"),
    ))
    answer = precedent.forecast(query(), table)

    assert sum(s.share for s in answer.nets) == pytest.approx(1, abs=0.01)
    assert sum(s.share for s in answer.nodes) \
        == pytest.approx(1, abs=0.01)


def test_the_same_question_gets_the_same_answer():
    """Ties in similarity are broken by refcode, never by the order
    the table happened to be read in."""
    rows = tuple(made(c, "Zr", 0, net) for c, net in
                 (("D", "pcu"), ("A", "fcu"), ("C", "bcu"), ("B", "fcu")))
    first = precedent.forecast(query(), Table(rows), neighbours=2)
    again = precedent.forecast(query(), Table(rows[::-1]), neighbours=2)

    assert first == again
    assert [n.precedent.refcode for n in first.neighbours] == ["A", "B"]


def test_interpenetration_is_out_of_those_that_say():
    table = Table((
        made("A", "Zn", 0, "pcu", interpenetrated=True),
        made("B", "Zn", 0, "pcu", interpenetrated=False),
        made("C", "Zn", 0, "pcu", interpenetrated=None),
    ))
    share = precedent.forecast(query("Zn"), table).interpenetrated

    assert share.share == pytest.approx(0.5)
    assert share.support == 1


def test_a_metal_nobody_has_used_is_said_to_be_a_guess():
    table = Table((made("A", "Zr", 0, "fcu"),))
    novelty = precedent.forecast(query("Pu"), table).novelty

    assert not novelty.metal_seen
    assert "analogy only" in novelty.sentence()


def test_a_closer_temperature_is_a_closer_synthesis():
    bits = Table(()).linker_bits()
    q = query(temperature=120)
    near = made("A", "Zr", 0, "fcu", temperature=125)
    far = made("B", "Zr", 0, "fcu", temperature=25)

    assert precedent.similarity(q, near, bits) \
        > precedent.similarity(q, far, bits)


def test_a_linker_nothing_like_the_precedents_lowers_the_score():
    bits = Table(()).linker_bits()
    p = made("A", "Zr", 0, "fcu")

    assert precedent.similarity(query(linkers=(IMIDAZOLE,)), p, bits) \
        < precedent.similarity(query(linkers=(BDC,)), p, bits)


@pytest.mark.parametrize("linkers, words", [
    ((), "At least one"),
    (("a", "b", "c", "d"), "At most three"),
])
def test_a_query_needs_one_to_three_linkers(linkers, words):
    with pytest.raises(precedent.PrecedentError, match=words):
        Query.read("Zr", linkers)


def test_a_temperature_outside_the_oven_is_refused():
    with pytest.raises(precedent.PrecedentError, match="500"):
        Query.read("Zr", ["c1ccccc1"], temperature=500)


# --------------------------------------------- the shipped table, whole

def test_the_shipped_table_holds_together():
    """What the script writes and the vote assumes: a linker index
    that points nowhere is an IndexError in the middle of a run, and
    a net in upper case is one of MOFid's words for no net."""
    source = precedent.BundledSource()
    records, linkers = source.records(), source.linker_bits()

    assert len(records) > 7000
    assert sum(r.has_conditions for r in records) > 300
    assert all(0 <= i < len(linkers) for r in records for i in r.linkers)
    assert all(0 <= b < precedent.FP_BITS for _, bits in linkers
               for b in bits)
    assert all(r.net == r.net.lower() for r in records if r.net)
    assert all(m not in precedent.NONMETALS for r in records
               for m in r.metals)
    assert all(isinstance(c, int) for r in records if r.solvents
               for c in r.solvents)


@needs_rdkit
def test_the_shipped_linker_bits_are_what_a_typed_linker_gets_today():
    """The table's bits were made once; a typed linker's are made now.
    A new RDKit, or a changed radius or length, would compare the two
    and every answer would drift with nothing failing -- this is what
    fails instead.  Re-run scripts/synthesis_precedents.py."""
    linkers = precedent.BundledSource().linker_bits()
    for smiles, bits in linkers[::97]:
        assert precedent.linker_key(smiles) == (smiles, bits)


@needs_rdkit
@pytest.mark.slow
def test_the_held_out_accuracy_is_what_the_answer_quotes():
    """BASIS tells every person who runs it how often the net that
    formed comes out in the first five.  Re-measured here, so the
    number cannot go stale when the table or the vote changes."""
    n, first, five = _script().held_out(precedent.BundledSource())

    assert f"{five:.0%}".replace("%", " %") in precedent.BASIS
    assert f"{first:.0%}".replace("%", " %") in precedent.BASIS
    assert f"of {n}" in precedent.BASIS
    assert five > 0.5


@needs_rdkit
def test_a_vote_over_the_whole_table_takes_under_a_second():
    """Every precedent is scored on every run; at seconds the form
    would feel broken and the held-out check would take an hour."""
    import time

    q = Query.read("ZrCl4", ["BDC"], ["DMF"], 120)
    precedent.forecast(q)                       # the load, once
    start = time.perf_counter()
    precedent.forecast(q)

    assert time.perf_counter() - start < 1.0


# ------------------------------------------- the script, on a few rows

ZR6 = "[Zr]1[Zr][Zr][Zr][Zr][Zr]1"
BDC_ANION = "[O-]C(=O)c1ccc(cc1)C(=O)[O-]"
BTC_ANION = "[O-]C(=O)c1cc(cc(c1)C(=O)[O-])C(=O)[O-]"


def _core_row(cifname, smiles, net, cat="cat0"):
    return f'{cifname},"{smiles} MOFid-v1.{net}.{cat};{cifname}"'


CORE = "\n".join((
    "cifname,mofid",
    _core_row("WIZMAV02_ASR_pacman", f"{ZR6}.{BDC_ANION}", "UNKNOWN"),
    _core_row("WIZMAV07_ASR_pacman", f"{ZR6}.{BDC_ANION}", "fcu"),
    _core_row("FIQCEN_ASR_pacman", f"[Cu][Cu].{BTC_ANION}", "tbo"),
    'BROKEN_ASR_pacman,"nothing a MOFid would write"',
)) + "\n"

SYNMOF = "\n".join((
    "filename,metal_ele1,counterions1,solvent1,solvent2,"
    "temperature_Celsius",
    "FIQCEN_clean,Cu,NO3,6228,962,85",
    "NOTINCORE_clean,Zn,CH3COO,6228,,120",
)) + "\n"


@needs_rdkit
def test_the_script_joins_the_two_tables_by_refcode_family(tmp_path):
    core = tmp_path / "core.csv"
    synmof = tmp_path / "synmof.csv"
    core.write_text(CORE, encoding="utf-8")
    synmof.write_text(SYNMOF, encoding="utf-8")

    table = _script().build(core, synmof)
    by_code = {r["refcode"]: r for r in table["records"]}

    # UiO-66 twice is one precedent, and the one with a net is kept.
    assert sorted(by_code) == ["FIQCEN", "WIZMAV"]
    assert by_code["WIZMAV"]["net"] == "fcu"
    assert by_code["WIZMAV"]["conditions"] is None
    # HKUST-1's conditions came across, CIDs as numbers.
    assert by_code["FIQCEN"]["conditions"] == {
        "anions": ["NO3"], "solvents": [6228, 962], "temperature": 85.0}
    assert by_code["FIQCEN"]["metals"] == ["Cu"]
    # Both linkers stored once each, uncharged, and found by index.
    smiles = [row["smiles"] for row in table["linkers"]]
    assert len(smiles) == 2 and all("-" not in s for s in smiles)
    assert table["sources"] == list(_script().SOURCES)


def test_a_synmof_counter_ion_is_read_into_the_vote_s_spelling():
    _, conditions = _script().read_conditions({
        "filename": "ABCDEF_clean", "counterions1": "CH3COO|H2O",
        "solvent1": "6228.0", "temperature_Celsius": "not given"})

    assert conditions["anions"] == ["OAc"]
    assert conditions["solvents"] == [6228]
    assert conditions["temperature"] is None


# --------------------------------------------------------------- CLI

@needs_rdkit
@pytest.mark.slow
def test_xtal_run_answers_from_the_command_line():
    """The CLI is the module's own run, start to finish, in a process
    of its own -- the path an agent or a script takes."""
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-m", "xtal.cli", "run", "synthesis.forecast",
         "-p", "metal=Cu(NO3)2·3H2O", "-p", "linkers=BTC",
         "-p", "solvents=DMF, EtOH, water"],
        capture_output=True, text=True, timeout=120, cwd=ROOT)

    assert done.returncode == 0, done.stderr
    assert "Likeliest net tbo" in done.stdout
    assert "The precedents that voted" in done.stdout
