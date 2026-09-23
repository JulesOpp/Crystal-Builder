"""Building a framework: the catalogue, the request, and the check.

Two halves.  Everything down to :class:`BuildRequest` reads files and
is tested unconditionally, because the whole point of
:mod:`xtal.mof.catalog` is that it works without importing PORMAKE.
The builds themselves are marked slow.

**Nothing here is skipped for a missing PORMAKE any more.**  It is
vendored, at :mod:`xtal.mof.pormake`, so the only thing that can be
absent is the database of nets and blocks beside it -- which is a
broken installation rather than a choice, and is what
``needs_database`` now says.  ``tests/test_mof_vendored.py`` is where
the vendored copy is diffed against a real upstream one.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from xtal.mof import Catalog, MofError, database_root, installed
from xtal.mof.build import (
    BuildOutcome,
    BuildRequest,
    build,
    closest_contact,
)
from xtal.mof.catalog import (
    BuildingBlock,
    CatalogError,
    matches_composition,
    matches_search,
    read_building_block,
)

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="the vendored PORMAKE database of nets and blocks is "
           "missing from this installation")

#: Building needs one thing more than listing does.  The vendored
#: PORMAKE is written over ``ase``, which stays an extra so that
#: ``pip install crystal-builder`` keeps working with four packages --
#: so a checkout without it can read the whole catalogue and cannot
#: build, and the two halves of this file skip separately.
needs_builder = pytest.mark.skipif(
    not installed(),
    reason="the MOF builder needs ase -- pip install "
           "'crystal-builder[ase]'")


@pytest.fixture(scope="module")
def catalog():
    if database_root() is None:
        pytest.skip("the vendored PORMAKE database is missing")
    return Catalog.default()


# ------------------------------------------- what a run can build with

@needs_database
def test_a_block_in_the_workspace_is_what_the_run_builds_with(tmp_path):
    """A block drawn on a slot row is written into the workspace, and
    the run has to read it there.  It did not, so Build on the block
    you had just drawn failed with "no building block called ..." --
    the one folder the answer was certain to be in."""
    from xtal.modules.job import Job
    from xtal.modules.mof import catalog_for
    from xtal.workspace import Workspace

    workspace = Workspace.create(tmp_path / "ws")
    workspace.blocks.mkdir(parents=True)
    (workspace.blocks / "mine.xyz").write_text(
        "2\n0 1\nX 0.0 0.0 0.0\nX 1.5 0.0 0.0\n")
    entry = workspace.add_document("framework")
    run = tmp_path / "ws" / entry.path.name / "runs" / "mof-build-001"
    run.mkdir(parents=True)
    job = Job(params={}, folder=SimpleNamespace(path=run))
    assert catalog_for(job).building_block("mine").n_connections == 2


def test_a_run_outside_a_workspace_still_has_a_catalogue():
    """The no-workspace path is reachable and must not look upwards
    from a folder that is not there."""
    from xtal.modules.job import Job
    from xtal.modules.mof import catalog_for

    assert catalog_for(Job(params={})) is not None


def test_atoms_copied_from_a_structure_are_not_read_as_a_smiles():
    """The clipboard's XYZ in the SMILES box was quoted back as "not a
    SMILES string RDKit can read" -- three lines of atoms and no
    advice, when the user already has the atoms."""
    from xtal.build import BuildError, installed
    from xtal.build.molecule import from_smiles

    if not installed():
        pytest.skip("the molecule builder needs rdkit")
    pasted = ("1\ncopied from Crystal Builder UIO66\n"
              "O        0.000000     0.000000     0.000000\n")
    for text in (pasted, " ".join(pasted.split())):
        with pytest.raises(BuildError) as raised:
            from_smiles(text)
        assert "copied from a structure" in str(raised.value)
        assert "building block" in str(raised.value)


# ----------------------------------------------------- the catalogue

@needs_database
def test_the_catalogue_is_read_without_importing_pormake(catalog):
    """The dialog opens instantly because of this.

    Importing PORMAKE used to bring jax and pymatgen with it and take
    ten seconds.  Vendoring took both away, and the claim still
    matters: everything the picker shows is in the .cgd and .xyz files
    themselves, and a catalogue that imported a builder to list files
    would put that import on every rebuild of the Modules tree.

    In a subprocess because the claim is about a fresh interpreter:
    any earlier test that actually built a framework has PORMAKE in
    ``sys.modules`` already, and this would then pass or fail on the
    order the files happened to run in.
    """
    assert catalog.topologies()
    assert catalog.building_blocks()

    import subprocess
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; from xtal.mof import Catalog; "
         "read = Catalog.default(); "
         "print(bool(read.topologies()), "
         "'xtal.mof.pormake' in sys.modules)"],
        capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["True", "False"]


@needs_database
def test_the_whole_database_reads_without_a_failure(catalog):
    """2399 nets and 867 blocks, and nothing in the shipped database
    that this reader chokes on."""
    assert len(catalog.topologies()) > 2000
    assert len(catalog.building_blocks()) > 800
    assert catalog.failures == ()


@needs_database
def test_a_topology_states_its_node_types_in_pormakes_order(catalog):
    """Node type 0 is the first NODE line of the .cgd.

    Not a convention invented here: PORMAKE tags each expanded site
    with the index of the NODE line it came from and calls that the
    node type, so this is what ``build_by_type`` is keyed on.  Getting
    it backwards would put the metal node on the linker's slots.
    """
    tbo = catalog.topology("tbo")
    assert tbo.coordinations == (3, 4)
    assert tbo.group == "Fm-3m"


@needs_database
def test_the_slots_of_a_net_are_its_nodes_and_the_pairs_they_join(
        catalog):
    slots = catalog.topology("tbo").slots()
    assert [(s.kind, s.key, s.coordination) for s in slots] == [
        ("node", 0, 3), ("node", 1, 4), ("edge", (0, 1), 2)]
    assert [s.token for s in slots] == ["0", "1", "0-1"]


@needs_database
def test_a_one_node_net_has_one_node_slot_and_one_edge_slot(catalog):
    slots = catalog.topology("pcu").slots()
    assert [s.token for s in slots] == ["0", "0-0"]
    assert slots[0].coordination == 6


@needs_database
def test_a_building_block_knows_where_it_connects(catalog):
    block = catalog.building_block("N59")
    assert block.n_connections == 6
    assert block.has_metal
    assert "Cd" in block.formula


@needs_database
def test_only_blocks_of_the_right_coordination_fit_a_slot(catalog):
    fitting = catalog.fitting(6)
    assert fitting
    assert all(b.n_connections == 6 for b in fitting)
    assert "N59" in {b.name for b in fitting}


@needs_database
def test_composition_search_finds_the_exact_counts_asked_for(
        catalog):
    """N59 is C6Cd2O12 -- exactly 6 carbons, 2 cadmiums, 12 oxygens,
    nothing else."""
    n59 = catalog.building_block("N59")
    assert matches_composition(n59, "6C 2Cd 12O")
    assert not matches_composition(n59, "6C 2Cd 11O")
    assert not matches_composition(n59, "5C 2Cd 12O")


@needs_database
def test_composition_search_by_bare_element_wants_only_presence(
        catalog):
    """No count on a token means "contains this", however many --
    the same query that finds C6Cd2O12 also finds C18H12."""
    n59 = catalog.building_block("N59")
    e1 = catalog.building_block("E1")
    assert matches_composition(n59, "C O")
    assert matches_composition(e1, "C")
    assert not matches_composition(e1, "Cd")


def test_composition_search_mixes_exact_counts_and_presence():
    """"6C N" -- exactly six carbons, and nitrogen in any amount --
    is the shape the two building-block examples in the request are:
    a full formula and a bare-element search, in one query."""
    from xtal.mof.catalog import BuildingBlock

    block = BuildingBlock("test", None, ("C",) * 6 + ("N",) * 3,
                          None, ())
    assert matches_composition(block, "6C N")
    assert not matches_composition(block, "6C O")
    assert not matches_composition(block, "7C N")


def test_a_block_search_word_that_is_no_element_is_a_name():
    """"N59" is not a composition, so it is looked for in the name;
    "N" is nitrogen, and as a name fragment would be in every one of
    PORMAKE's node names."""
    from xtal.mof.catalog import BuildingBlock

    block = BuildingBlock("N59", None, ("C",) * 6 + ("Cd",) * 2,
                          None, ())
    other = BuildingBlock("N60", None, ("C",) * 6 + ("N",), None, ())
    assert matches_search(block, "N59")
    assert matches_search(block, "n59 6C")
    assert not matches_search(block, "N59 N")
    assert not matches_search(other, "N59")
    assert matches_search(other, "N")
    assert not matches_search(block, "N")


def test_an_empty_composition_query_matches_everything():
    from xtal.mof.catalog import BuildingBlock

    block = BuildingBlock("test", None, ("C", "H"), None, ())
    assert matches_composition(block, "")
    assert matches_composition(block, "   ")


def test_composition_search_ignores_a_token_it_cannot_read():
    """A query still being typed -- "3Z" before the rest of "Zn" --
    is dropped rather than refused, and a query of nothing readable
    matches everything, the same as a blank box."""
    from xtal.mof.catalog import BuildingBlock

    block = BuildingBlock("test", None, ("C", "H"), None, ())
    assert matches_composition(block, "3Z")
    assert matches_composition(block, "not an element either")


@needs_database
def test_a_name_that_is_in_neither_folder_says_where_it_looked(
        catalog):
    with pytest.raises(CatalogError) as raised:
        catalog.topology("not-a-net")
    assert "not-a-net" in str(raised.value)
    assert "topologies" in str(raised.value)


def test_a_users_own_folder_is_read_beside_pormakes(tmp_path):
    """"A user's own building block is a folder, not a code change."

    The extra directory is what makes that true, and a name in it
    replaces one of PORMAKE's -- which is what lets somebody correct a
    block rather than only add one.
    """
    (tmp_path / "MINE.xyz").write_text(
        "3\n   1   2\nC 0.0 0.0 0.0\nX 1.5 0.0 0.0\nX -1.5 0.0 0.0\n")
    catalog = Catalog(bb_dirs=(tmp_path,))
    assert [b.name for b in catalog.building_blocks()] == ["MINE"]
    assert catalog.building_block("MINE").n_connections == 2


def test_a_block_written_with_x_atoms_reads_the_same(tmp_path):
    """Both spellings, because both are in the wild: PORMAKE's own
    files list connection points by index and its documentation marks
    them as X atoms."""
    path = tmp_path / "X.xyz"
    path.write_text(
        "3\nno indices here\nC 0.0 0.0 0.0\nX 1.5 0.0 0.0\n"
        "X -1.5 0.0 0.0\n")
    assert read_building_block(path).connections == (1, 2)


def test_a_block_with_no_connection_points_at_all_is_refused(tmp_path):
    """It cannot be placed on anything, and one read as having none
    would be built in as a lump of unbonded atoms."""
    path = tmp_path / "flat.xyz"
    path.write_text("2\n\nC 0.0 0.0 0.0\nC 1.5 0.0 0.0\n")
    with pytest.raises(CatalogError):
        read_building_block(path)


# ------------------------------------------------------- the request

def test_a_block_named_without_a_slot_fills_every_slot_of_its_kind():
    """``nodes="N59"`` means what it obviously means.

    Nearly every net people build on has one kind of node and one kind
    of edge, and making those spell a slot they cannot get wrong is
    ceremony.
    """
    request = BuildRequest.parse("pcu", "N59", "E32")
    from xtal.mof.catalog import Slot
    assert request.block_for(Slot("node", 0, 6)) == "N59"
    assert request.block_for(Slot("edge", (0, 0), 2)) == "E32"


def test_a_block_can_be_named_against_the_slot_it_goes_in():
    from xtal.mof.catalog import Slot
    request = BuildRequest.parse("tbo", "0=N19,1=N59", "0-1=E32")
    assert request.block_for(Slot("node", 0, 3)) == "N19"
    assert request.block_for(Slot("node", 1, 4)) == "N59"
    assert request.block_for(Slot("edge", (0, 1), 2)) == "E32"


def test_a_request_comes_back_spelled_the_way_it_was_written():
    """The log records the run that happened.

    Rewriting ``N59`` as ``0=N59`` would make the parameters in a run
    folder stop matching the command that produced them.
    """
    assert BuildRequest.parse("pcu", "N59", "E32").spelled() == (
        "pcu", "N59", "E32")
    assert BuildRequest.parse("tbo", "0=N19,1=N59", "").spelled() == (
        "tbo", "0=N19,1=N59", "")


def test_the_framework_is_named_after_what_it_was_built_from():
    assert BuildRequest.parse("pcu", "N59", "E32").title() == \
        "pcu-N59-E32"


def test_a_build_with_no_topology_is_refused_before_anything_else():
    with pytest.raises(MofError):
        BuildRequest.parse("", "N59", "E32")


def test_the_two_spellings_may_not_be_mixed():
    """``"N19,1=N59"`` is a typo with two readings and no way to pick
    between them."""
    with pytest.raises(MofError):
        BuildRequest.parse("tbo", "N19,1=N59", "")


def test_something_that_does_not_name_a_slot_says_how_to_write_one():
    with pytest.raises(MofError) as raised:
        BuildRequest.parse("tbo", "left=N19", "")
    assert "0=N59" in str(raised.value)


def test_a_stacking_offset_is_read_as_the_fractions_it_was_written_in():
    """``1/3`` is a third and ``0.3333`` is not: a slip written the
    way stackings are named must not arrive 0.0003 of a cell off."""
    request = BuildRequest.parse("hcb", "N1", "E1", spacing="3.24 A",
                                 offset="1/3, 2/3")
    assert request.spacing == 3.24
    assert request.offset == (1 / 3, 2 / 3)
    assert BuildRequest.parse("hcb", "N1", "E1").spacing is None
    assert BuildRequest.parse("hcb", "N1", "E1").offset is None


def test_a_spacing_or_offset_that_says_nothing_is_refused_by_name():
    for spacing, offset in (("0", ""), ("-3", ""), ("wide", ""),
                            ("", "1/3"), ("", "a, b"), ("", "1/0, 0")):
        with pytest.raises(MofError):
            BuildRequest.parse("hcb", "N1", "E1", spacing=spacing,
                               offset=offset)


@needs_database
def test_a_block_that_does_not_fit_its_slot_names_both(tmp_path,
                                                       catalog):
    """PORMAKE's own refusal is an assertion inside a locator.

    This is the sentence a user can act on, and it is raised before
    PORMAKE is imported at all.
    """
    request = BuildRequest.parse("tbo", "0=N59,1=N59", "")
    with pytest.raises(MofError) as raised:
        build(request, tmp_path, catalog)
    assert "N59" in str(raised.value)
    assert "6 connection point" in str(raised.value)


@needs_database
def test_a_node_slot_left_empty_is_refused(tmp_path, catalog):
    """A net has to have something on every node.  An empty edge is a
    framework with no linker; an empty node is nothing at all."""
    with pytest.raises(MofError):
        build(BuildRequest.parse("tbo", "0=N19", ""), tmp_path,
              catalog)


# --------------------------------------------------------- the build

@needs_builder
@pytest.mark.slow
def test_a_build_produces_the_net_it_was_asked_for(tmp_path, catalog):
    """The check the whole phase is for.

    The net is read back off the *structure* with the same two
    functions the Net panel uses, so this is a statement about the
    bonds that ended up in the file rather than about anything PORMAKE
    said while writing it.
    """
    outcome = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)
    assert outcome.asked == "pcu"
    assert outcome.net_name == "pcu"
    assert outcome.net_agrees
    assert "as asked" in outcome.verdict()


@needs_builder
@needs_builder
@pytest.mark.slow
def test_every_joint_the_builder_made_arrives_bonded(tmp_path,
                                                     catalog):
    """The bonds inside a block arrive at a chemical length and
    perception finds them; the joins between blocks do not have to, and
    a framework whose linkers float unbonded beside their nodes is one
    nobody would think to draw the missing bond in by hand.

    pcu has three edges in its cell, so a linker on each is six joins
    and a bare node-to-node net is three -- and those three are a node
    to its own periodic image, which is why they cannot be found by
    looking for bonds between two different blocks."""
    outcome = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)
    explicit = [b for b in outcome.structure.bonds
                if b.kind == "explicit"]
    assert outcome.joints == 6
    assert len(explicit) == 6
    assert any(b.image != (0, 0, 0) for b in explicit)

    bare = build(BuildRequest.parse("pcu", "N59", ""), tmp_path,
                 catalog)
    assert bare.joints == 3
    assert len([b for b in bare.structure.bonds
                if b.kind == "explicit"]) == 3


@needs_builder
@pytest.mark.slow
def test_a_joint_stays_bonded_however_long_it_is(tmp_path, catalog):
    """The point of storing them.  A joint is the user's own bond, so
    it is drawn whatever the distance criteria would have said -- which
    is what a carboxylate onto a metal, or a block written a little
    long, needs."""
    from xtal.core import bonding

    outcome = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)
    structure = outcome.structure
    joints = {tuple(sorted((b.i, b.j)))
              for b in structure.bonds if b.kind == "explicit"}
    # Criteria that bond nothing at all: the joints are still there.
    drawn = bonding.perceive(structure,
                             bonding.BondRules(scale=0.1))
    assert joints <= {tuple(sorted((b.i, b.j))) for b in drawn}


@pytest.mark.slow
def test_the_framework_arrives_with_its_net_already_drawn(tmp_path,
                                                          catalog):
    """So the Net panel names it the moment the tab opens.

    Nothing else in this application draws a net for the user: PORMAKE
    knows exactly which atoms are one node, and throwing that away
    would leave a framework somebody has to redraw a net on to find
    out what they built.
    """
    from xtal.core import bonding

    outcome = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)
    graph = bonding.topology_graph(outcome.structure)
    assert len(graph.bonds) == 3        # pcu has three edges per cell
    assert outcome.structure.meta["title"] == "pcu-N59-E32"


@needs_builder
@pytest.mark.slow
def test_the_cif_is_written_where_the_run_folder_is(tmp_path, catalog):
    outcome = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)
    assert outcome.cif.parent == tmp_path
    assert outcome.cif.is_file()
    assert outcome.n_atoms == 98


@needs_builder
@pytest.mark.slow
def test_a_net_with_two_node_types_builds_on_both(tmp_path, catalog):
    """tbo is 3-c and 4-c, and putting the wrong block on either slot
    would produce a framework that is not tbo -- which is exactly what
    the check would then say."""
    three = next(b.name for b in catalog.fitting(3) if b.has_metal)
    four = next(b.name for b in catalog.fitting(4) if b.has_metal)
    outcome = build(
        BuildRequest.parse("tbo", f"0={three},1={four}", "E32"),
        tmp_path, catalog)
    assert outcome.net_agrees
    assert outcome.net_name == "tbo"


@needs_builder
@pytest.mark.slow
def test_a_net_built_with_no_linker_at_all_still_gets_its_net(
        tmp_path, catalog):
    """An empty edge is a real framework -- the nodes bond directly --
    and it is the case that broke drawing the net.

    PORMAKE consumes the connection points to make those bonds, so the
    block's own centroid, which is the mean of them, is gone by the
    time the vertex atom has to be chosen.  The slot decides instead.
    """
    outcome = build(BuildRequest.parse("pcu", "N59", ""), tmp_path,
                    catalog)
    assert outcome.net_agrees
    assert outcome.n_atoms == 20


@needs_builder
@pytest.mark.slow
def test_importing_pormake_does_not_write_into_the_working_directory(
        tmp_path, catalog, monkeypatch):
    """Upstream PORMAKE opens ``runtime.log`` in the current
    directory, in mode "w", at import time.

    That is whatever folder the application was launched from, and a
    file of the user's with that name would be truncated by an import
    they never asked for.  This used to be contained by swapping
    ``logging.FileHandler`` out for the duration of the import;
    vendoring let it be fixed where it happens, in
    ``xtal/mof/pormake/log.py``.  The guarantee is unchanged and so is
    this test, which is the point of keeping it.
    """
    monkeypatch.chdir(tmp_path)
    build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path, catalog)
    assert not (tmp_path / "runtime.log").exists()


# ------------------------------------------- what the verdict claims

def test_a_verdict_never_claims_a_shape_the_net_does_not_have():
    """A topology is combinatorial; the metric cell is free.

    The review this work came out of proposed reporting "the relaxed
    cell is triclinic where pcu is cubic".  That would be a false
    alarm on real materials -- DMOF-1 is tetragonal **pcu** and
    MIL-53 monoclinic -- so the verdict says nothing about the shape
    of the cell, and this is the test that keeps it that way.
    """
    outcome = BuildOutcome(
        structure=None, cif=None, request=BuildRequest.parse("pcu", "N59", ""),
        asked="pcu", max_rmsd=0.5, closest=1.2,
        identified=SimpleNamespace(name="pcu", headline=lambda: "pcu"))
    said = outcome.verdict()
    assert outcome.net_agrees
    for word in ("cubic", "triclinic", "monoclinic", "tetragonal",
                 "orthorhombic", "hexagonal", "trigonal"):
        assert word not in said


def test_a_verdict_carries_the_numbers_it_was_judged_on():
    """The net half alone reads like a pass however bad the geometry.

    "the framework is pcu, as asked" was the whole sentence, and it
    was true of a build with none of MFU-4l's chlorides and a fifth of
    its atoms.  What says whether a build is any good is the fit and
    the contacts, so the sentence carries them.
    """
    outcome = BuildOutcome(
        structure=None, cif=None, request=BuildRequest.parse("pcu", "N59", ""),
        asked="pcu", max_rmsd=0.2710, closest=1.662, joints=6,
        identified=SimpleNamespace(name="pcu", headline=lambda: "pcu"))
    said = outcome.verdict()
    assert "as asked" in said
    assert "0.271" in said
    assert "1.66" in said
    assert "6 joint(s)" in said


def test_a_verdict_with_nothing_measured_still_reads():
    """A contact that was never measured is ``inf``, not 0.0 -- 0.000 A
    is a real answer and ``CFA1.cif`` gives it -- so the clause is left
    out rather than printed as a number nobody measured."""
    outcome = BuildOutcome(
        structure=None, cif=None, request=BuildRequest.parse("pcu", "N59", ""),
        asked="pcu",
        identified=SimpleNamespace(name="tbo", headline=lambda: "tbo"))
    said = outcome.verdict()
    assert "different nets" in said
    assert "inf" not in said
    assert "contact" not in said


@needs_database
def test_the_closest_contact_is_the_shortest_one_that_is_not_a_bond():
    """The shortest distance of any kind is the C-H bond every time.

    ``MFU4l.cif``'s own refinement puts it at 0.930 A, and so does a
    framework built out of blocks cut from it, so the plain minimum
    tells a person nothing.  The unbonded minimum does: every
    framework in ``resources/samples`` sits between 1.996 and 2.170 A.
    """
    from xtal.io import FORMATS

    structure = FORMATS.read("resources/samples/MFU4l.cif")
    assert 1.9 < closest_contact(structure) < 2.2


@needs_database
def test_the_closest_contact_holds_connection_points_back():
    """An ``X`` sits 0.75 A from the atom it hangs off, so a structure
    that carries one would answer 0.75 A to this question every time,
    whatever else is in it."""
    from xtal.core.structure import Bond, Lattice, Structure
    from xtal.io import FORMATS

    plain = FORMATS.read("resources/samples/MFU4l.cif")
    before = closest_contact(plain)
    marked = Structure.from_arrays(
        Lattice.from_parameters(10.0, 10.0, 10.0, 90, 90, 90),
        ["C", "C", "X"],
        [[0.0, 0.0, 0.0], [0.25, 0.0, 0.0], [0.075, 0.0, 0.0]],
        space_group="P1")
    marked.add_bond(Bond(0, 2, (0, 0, 0), 1.0))
    # 2.5 A apart and not bonded; the X is 0.75 A from atom 0.
    assert abs(closest_contact(marked) - 2.5) < 1e-6
    assert before > 1.9


# ------------------------------------------- what a point stands for

def block_file(tmp_path, text: str, name: str = "U01"):
    path = tmp_path / f"{name}.xyz"
    path.write_text(text, encoding="utf-8")
    return read_building_block(path)


def test_members_are_the_distinct_partners_and_not_the_bond_count():
    """54 of the 4256 shipped connection points carry more than one
    bond *record* and 52 of those name the same partner twice, across
    26 blocks.  A reader that counted records would take 26 shipped
    blocks down the polydentate path, where none of them belongs."""
    from xtal.mof.catalog import BuildingBlock

    block = BuildingBlock("test", None, ("C", "H", "X"), None, (2,),
                          ((0, 2, "S"), (2, 0, "S")))

    assert block.members == {2: (0,)}
    assert not block.is_polydentate


def test_a_block_with_no_bond_block_says_nothing_about_its_members(
        tmp_path):
    """Not "this point has no members".  A file that never wrote its
    bonds cannot be asked which atom a point hangs off, and guessing
    the nearest one is how a block is built along a direction nobody
    wrote down."""
    block = block_file(tmp_path,
                       "2\n    1\nC 0.0 0.0 0.0\nX 0.75 0.0 0.0\n")

    assert block.bonds == ()
    assert block.members == {1: ()}
    assert not block.is_polydentate


def test_a_line_that_is_not_a_bond_is_skipped_the_way_pormake_skips_it(
        tmp_path):
    """There is no header to tell a bond block from anything else --
    everything after the atoms is read as a bond -- so a line that is
    not one is dropped in silence.  Refusing would make a file
    PORMAKE reads one this application does not."""
    block = block_file(
        tmp_path,
        "3\n    2\nC 0.0 0.0 0.0\nH -1.0 0.0 0.0\nX 0.75 0.0 0.0\n"
        "   0    2 S\n"
        "\n"
        "a comment somebody left\n"
        "   0    9 S\n"
        "   x    2 S\n")

    assert block.bonds == ((0, 2, "S"),)
    assert block.members == {2: (0,)}


@needs_database
def test_only_two_vendored_blocks_read_as_bidentate_and_both_wrong():
    """Pinned rather than tolerated by a threshold.

    ``N484``'s connection point is bonded to a **hydrogen**, and
    ``N684``'s sits 1.201 and 0.613 A from its two partners against a
    CONNECTION_DISTANCE of 0.75.  Both are upstream data errors and
    both genuinely read as bidentate.  No geometric tolerance
    separates them from ours -- N684 sits 0.703 A from its members'
    centroid against our 0.750 -- so tuning one to 0.047 A would be
    fitting a constant to two broken files.  They are named here
    instead, and a third name appearing is a change in the database
    rather than a change in the rules.

    PORMAKE's ``bbs/`` alone, and that is the point of the test
    rather than a detail of it: the four this application now ships
    of its own are polydentate *deliberately*, so asking the default
    catalogue would measure our library and call an upstream data
    error a feature.
    """
    catalog = Catalog((), (database_root() / "bbs",))

    names = sorted(block.name for block in catalog.building_blocks()
                   if block.is_polydentate)

    assert names == ["N484", "N684"]


# -------------------------------------------- the attachment's frame

def attachment(offsets):
    from xtal.mof.attach import Attachment

    offsets = np.asarray(offsets, dtype=float)
    return Attachment(0, tuple(range(1, len(offsets) + 1)), offsets)


def test_a_monodentate_attachment_s_axis_is_the_bond_direction():
    """What the single-point path has always used, which is why a
    catalogue of them reaches none of the new arithmetic."""
    single = attachment([[0.0, 0.0, -1.5]])

    assert single.denticity == 1
    assert not single.is_polydentate
    assert single.span == 0.0
    assert single.axis == pytest.approx([0.0, 0.0, 1.0])


def test_a_bidentate_attachment_points_out_of_its_members_middle():
    pair = attachment([[1.4, 0.0, -1.0], [-1.4, 0.0, -1.0]])

    assert pair.is_polydentate
    assert pair.span == pytest.approx(2.8)
    assert pair.axis == pytest.approx([0.0, 0.0, 1.0])


def test_two_ends_that_agree_cost_nothing_and_a_right_angle_costs_two():
    """Measured on MFU-4l before any of this was built: the crystal's
    own orientation scores exactly 0.000000 and a 90-degree twist
    exactly 2.000000."""
    from xtal.mof.attach import pair_cost

    axis = [0.0, 0.0, 1.0]
    node = attachment([[1.405, 0.0, -1.0], [-1.405, 0.0, -1.0]])
    aligned = attachment([[2.861, 0.0, 1.0], [-2.861, 0.0, 1.0]])
    twisted = attachment([[0.0, 2.861, 1.0], [0.0, -2.861, 1.0]])

    assert pair_cost(node, aligned, axis) == pytest.approx(0.0,
                                                           abs=1e-12)
    assert pair_cost(node, twisted, axis) == pytest.approx(2.0,
                                                           abs=1e-12)


def test_the_two_ends_different_spans_do_not_show_up_in_the_cost():
    """Comparing the offsets themselves leaves a floor of 0.53 A^2
    that is the span difference and nothing else -- MFU-4l's node
    members are 1.405 A apart and its linker's 2.861.  The laterals
    are compared as directions for exactly that reason."""
    from xtal.mof.attach import pair_cost

    axis = [0.0, 0.0, 1.0]
    narrow = attachment([[0.1, 0.0, -1.0], [-0.1, 0.0, -1.0]])
    wide = attachment([[4.0, 0.0, 1.0], [-4.0, 0.0, 1.0]])

    assert pair_cost(narrow, wide, axis) == pytest.approx(0.0,
                                                          abs=1e-12)


def test_a_joint_with_a_monodentate_end_has_no_twist_to_prefer():
    """One member has no lateral to disagree about.  This is what
    makes the tie-break inert for every block shipped before this
    work, rather than a thing that has to be switched off."""
    from xtal.mof.attach import pair_cost

    axis = [0.0, 0.0, 1.0]
    single = attachment([[0.0, 0.0, -1.5]])
    pair = attachment([[1.4, 0.0, 1.0], [-1.4, 0.0, 1.0]])

    assert pair_cost(single, pair, axis) == 0.0


@needs_database
def test_a_shipped_block_s_attachments_are_one_per_connection_point(
        catalog):
    """Read off the file and not counted: ``attachments_of`` is what
    the orientation work will be written against."""
    from xtal.mof.attach import attachments_of

    block = catalog.building_block("N484")
    found = attachments_of(block)

    assert len(found) == block.n_connections
    assert sum(a.denticity for a in found) == 4
    assert [a.point for a in found] == sorted(block.connections)


# ------------------------------------- the joints an attachment makes

#: Six directions, each with a perpendicular for the two atoms of a
#: bidentate attachment to straddle.  Octahedral, so the node below
#: goes on ``pcu``.
_AXES = [((1, 0, 0), (0, 1, 0)), ((-1, 0, 0), (0, 1, 0)),
         ((0, 1, 0), (0, 0, 1)), ((0, -1, 0), (0, 0, 1)),
         ((0, 0, 1), (1, 0, 0)), ((0, 0, -1), (1, 0, 0))]


def bidentate_node() -> str:
    """A 6-connected node whose every point stands for two atoms.

    Synthetic and not one of the four real ones, because a test about
    how many bonds a joint makes should not also depend on a crystal
    being cut up correctly -- and because the real blocks are Phase 7's
    to ship.
    """
    symbols, positions, bonds = ["Zn"], [(0.0, 0.0, 0.0)], []
    for k, (axis, across) in enumerate(_AXES):
        axis, across = np.array(axis, float), np.array(across, float)
        symbols += ["C", "C"]
        positions += [tuple(1.4 * axis + 0.7 * across),
                      tuple(1.4 * axis - 0.7 * across)]
        bonds += [(0, 1 + 2 * k), (0, 2 + 2 * k)]
    for k, (axis, _across) in enumerate(_AXES):
        symbols.append("X")
        positions.append(tuple(2.15 * np.array(axis, float)))
        bonds += [(13 + k, 1 + 2 * k), (13 + k, 2 + 2 * k)]
    return _block_text(symbols, positions, bonds)


def bidentate_linker() -> str:
    """A 2-connected linker that meets each node through two atoms."""
    return _block_text(
        ["C", "C", "C", "C", "X", "X"],
        [(0.7, 0.0, 2.0), (-0.7, 0.0, 2.0),
         (0.7, 0.0, -2.0), (-0.7, 0.0, -2.0),
         (0.0, 0.0, 2.75), (0.0, 0.0, -2.75)],
        [(0, 1), (2, 3), (0, 2), (1, 3),
         (4, 0), (4, 1), (5, 2), (5, 3)])


def single_point_linker() -> str:
    """A 2-connected linker of the shape every shipped block has:
    one atom per connection point."""
    return _block_text(
        ["C", "C", "X", "X"],
        [(0.0, 0.0, 2.0), (0.0, 0.0, -2.0),
         (0.0, 0.0, 2.75), (0.0, 0.0, -2.75)],
        [(0, 1), (2, 0), (3, 1)])


def _block_text(symbols, positions, bonds) -> str:
    marked = [i for i, s in enumerate(symbols) if s == "X"]
    lines = [str(len(symbols)), "".join(f"{i:5d}" for i in marked)]
    lines += [f"{s:<4s} {x:.4f} {y:.4f} {z:.4f}"
              for s, (x, y, z) in zip(symbols, positions, strict=True)]
    lines += [f"{i:4d} {j:4d} S" for i, j in bonds]
    return "\n".join(lines) + "\n"


@pytest.fixture
def synthetic(tmp_path):
    """A catalogue with the three blocks above in it."""
    folder = tmp_path / "blocks"
    folder.mkdir()
    for name, text in (("SNODE", bidentate_node()),
                       ("SLINK", bidentate_linker()),
                       ("SSTICK", single_point_linker())):
        (folder / f"{name}.xyz").write_text(text, encoding="utf-8")
    return Catalog.default(also_blocks=[folder])


def joints_of(outcome):
    return {tuple(sorted((b.i, b.j))) for b in outcome.structure.bonds
            if b.kind == "explicit"}


@needs_builder
@pytest.mark.slow
def test_a_bidentate_end_arrives_with_two_bonds(tmp_path, synthetic):
    """The defect this phase exists for.  ``builder.py:644-658`` keeps
    one partner per connection point -- a scalar assigned into a
    list-valued map -- so a bidentate joint comes back with half its
    bonds, and pcu's three edges give six joints where twelve are
    needed."""
    outcome = build(BuildRequest.parse("pcu", "SNODE", "SLINK"),
                    tmp_path, synthetic)

    assert outcome.joints == 12
    assert len(joints_of(outcome)) == 12
    assert outcome.longest_joint > 0.0


@needs_builder
@pytest.mark.slow
def test_the_two_ends_of_a_joint_are_paired_not_crossed(tmp_path,
                                                        synthetic):
    """Each joint takes the cheaper of its two pairings, and every
    attachment atom ends up in exactly one bond.

    PORMAKE's own choice is whichever partner it saw last -- three of
    MFU-4l's six joints on pcu come back crossed that way -- which is
    why an enumerated joint replaces what the builder made of it
    instead of being added to it.

    The lengths are pinned because they say which pairing was taken.
    All twelve are the same here and that is the settled geometry:
    this node presents a different face on each pair of axes, so the
    fit left the twelve in three groups of four -- 1.5, 1.544, and a
    *square* at 1.797, all four of its distances equal, which is a
    quarter turn with nothing in the fit to prefer either way round.
    :func:`xtal.mof.orient.align_edges` turns each linker about its
    own axis until both its ends face the nodes they meet, and on a
    cubic net whose edges are all alike that is one length twelve
    times.  ``test_a_planar_linker_lands_coplanar_with_both_ends``
    is where that turn is measured; here it is the floor the pairing
    is read against.
    """
    outcome = build(BuildRequest.parse("pcu", "SNODE", "SLINK"),
                    tmp_path, synthetic)
    lattice = outcome.structure.lattice
    frac = np.asarray(outcome.structure.frac, dtype=float)

    lengths, ends = [], []
    for bond in outcome.structure.bonds:
        if bond.kind != "explicit":
            continue
        offset = frac[bond.i] - frac[bond.j] - np.asarray(bond.image)
        lengths.append(float(np.linalg.norm(lattice.to_cart(offset))))
        ends += [bond.i, bond.j]

    assert sorted(round(v, 3) for v in lengths) == [1.5] * 12
    # Twenty-four attachment atoms, each in one joint and no more:
    # a crossed joint would double one of them and drop another.
    assert len(ends) == len(set(ends)) == 24


@needs_builder
@pytest.mark.slow
def test_a_joint_between_unequal_denticities_bonds_every_member(
        tmp_path, synthetic):
    """A bidentate node meeting a single-point linker is a real joint,
    and leaving half of it floating would be the same defect one size
    down.  The assignment covers the smaller end and the larger end's
    leftovers take their nearest partner."""
    outcome = build(BuildRequest.parse("pcu", "SNODE", "SSTICK"),
                    tmp_path, synthetic)
    bonded = {atom for pair in joints_of(outcome) for atom in pair}
    elements = [str(s.element) for s in outcome.structure.sites]

    assert outcome.joints == 12
    # Every one of the node's twelve attachment atoms, not six.
    assert sum(1 for a in bonded if elements[a] == "C") >= 12


@needs_builder
@pytest.mark.slow
def test_a_net_with_no_linker_still_joins_a_bidentate_node(
        tmp_path, synthetic):
    """Node to its own periodic image, and twice per joint.

    This is the one case where the located block comes back without
    its connection points -- upstream deletes them from the framework's
    atoms, which with a single filled slot is the same object -- so it
    is the case that says :func:`_placed_atoms` reads each block's
    extent off its own bond list.
    """
    outcome = build(BuildRequest.parse("pcu", "SNODE", ""), tmp_path,
                    synthetic)

    assert outcome.joints == 6              # three edges, two each
    assert len(joints_of(outcome)) == 6


@needs_builder
@pytest.mark.slow
def test_a_single_point_build_makes_exactly_the_bonds_it_always_made(
        tmp_path, synthetic, catalog):
    """The guarantee.  No shipped block is polydentate, so the whole
    of the new path is behind a guard none of them opens, and a build
    of them makes the bonds it made before any of this was written --
    one per joint, and the length not measured because there is
    nothing to choose between."""
    shipped = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)

    assert shipped.joints == 6
    assert shipped.longest_joint == 0.0
    assert "longest joint" not in shipped.verdict()


# ------------------------------------------- the bonds a block is drawn with

def test_a_block_is_drawn_with_the_bonds_it_is_built_with(catalog):
    """The picker once bonded by its own distance rule: 9401 bonds
    the shipped blocks do not have, 74 missing that they do."""
    for block in catalog.building_blocks():
        own = {(min(int(i), int(j)), max(int(i), int(j)))
               for i, j, *_ in block.bonds}
        assert set(block.bond_pairs()) == own, block.name


def test_a_block_with_no_bonds_is_drawn_by_the_applications_rule():
    """No bond section: perception over the atoms, which refuses a
    metal-metal pair, and each connection point on a stalk to its
    nearest atom."""
    block = BuildingBlock(
        name="bare", path=Path("bare.xyz"),
        symbols=("Zn", "Zn", "O", "X"),
        positions=np.array([[0.0, 0, 0], [2.6, 0, 0], [1.3, 1.2, 0],
                            [1.3, 2.6, 0]]),
        connections=(3,))

    pairs = block.bond_pairs()

    assert (0, 1) not in pairs                  # never Zn-Zn
    assert (0, 2) in pairs and (1, 2) in pairs
    assert (2, 3) in pairs                      # the point's stalk
