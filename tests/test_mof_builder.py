"""Building a framework: the catalogue, the request, and the check.

Two halves.  Everything down to :class:`BuildRequest` reads files and
is tested unconditionally, because the whole point of
:mod:`xtal.mof.catalog` is that it works without PORMAKE.  The builds
themselves are skipped when PORMAKE is not installed and marked slow
when it is -- ``import pormake`` is ten seconds on its own.
"""

import sys

import pytest

from xtal.mof import Catalog, MofError, database_root, installed
from xtal.mof.build import BuildRequest, build
from xtal.mof.catalog import CatalogError, read_building_block

needs_pormake = pytest.mark.skipif(
    not installed() or database_root() is None,
    reason="PORMAKE is not installed; pip install "
           "'crystal-builder[mof]'")


@pytest.fixture(scope="module")
def catalog():
    if database_root() is None:
        pytest.skip("PORMAKE's database is not installed")
    return Catalog.default()


# ----------------------------------------------------- the catalogue

@needs_pormake
def test_the_catalogue_is_read_without_importing_pormake(catalog):
    """The dialog opens instantly because of this.

    ``import pormake`` brings jax and pymatgen with it and takes ten
    seconds; everything the picker shows is in the .cgd and .xyz files
    themselves.  If this ever fails, opening the Modules tree freezes
    the window.

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
         "'pormake' in sys.modules)"],
        capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["True", "False"]


@needs_pormake
def test_the_whole_database_reads_without_a_failure(catalog):
    """2399 nets and 867 blocks, and nothing in the shipped database
    that this reader chokes on."""
    assert len(catalog.topologies()) > 2000
    assert len(catalog.building_blocks()) > 800
    assert catalog.failures == ()


@needs_pormake
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


@needs_pormake
def test_the_slots_of_a_net_are_its_nodes_and_the_pairs_they_join(
        catalog):
    slots = catalog.topology("tbo").slots()
    assert [(s.kind, s.key, s.coordination) for s in slots] == [
        ("node", 0, 3), ("node", 1, 4), ("edge", (0, 1), 2)]
    assert [s.token for s in slots] == ["0", "1", "0-1"]


@needs_pormake
def test_a_one_node_net_has_one_node_slot_and_one_edge_slot(catalog):
    slots = catalog.topology("pcu").slots()
    assert [s.token for s in slots] == ["0", "0-0"]
    assert slots[0].coordination == 6


@needs_pormake
def test_a_building_block_knows_where_it_connects(catalog):
    block = catalog.building_block("N59")
    assert block.n_connections == 6
    assert block.has_metal
    assert "Cd" in block.formula


@needs_pormake
def test_only_blocks_of_the_right_coordination_fit_a_slot(catalog):
    fitting = catalog.fitting(6)
    assert fitting
    assert all(b.n_connections == 6 for b in fitting)
    assert "N59" in {b.name for b in fitting}


@needs_pormake
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


@needs_pormake
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


@needs_pormake
def test_a_node_slot_left_empty_is_refused(tmp_path, catalog):
    """A net has to have something on every node.  An empty edge is a
    framework with no linker; an empty node is nothing at all."""
    with pytest.raises(MofError):
        build(BuildRequest.parse("tbo", "0=N19", ""), tmp_path,
              catalog)


# --------------------------------------------------------- the build

@needs_pormake
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


@needs_pormake
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


@needs_pormake
@pytest.mark.slow
def test_the_cif_is_written_where_the_run_folder_is(tmp_path, catalog):
    outcome = build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path,
                    catalog)
    assert outcome.cif.parent == tmp_path
    assert outcome.cif.is_file()
    assert outcome.n_atoms == 98


@needs_pormake
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


@needs_pormake
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


@needs_pormake
@pytest.mark.slow
def test_importing_pormake_does_not_write_into_the_working_directory(
        tmp_path, catalog, monkeypatch):
    """PORMAKE opens ``runtime.log`` in the current directory, in mode
    "w", at import time.

    That is whatever folder the application was launched from, and a
    file of the user's with that name would be truncated by an import
    they never asked for.  The import is contained; this is what says
    so.
    """
    monkeypatch.chdir(tmp_path)
    build(BuildRequest.parse("pcu", "N59", "E32"), tmp_path, catalog)
    assert not (tmp_path / "runtime.log").exists()
