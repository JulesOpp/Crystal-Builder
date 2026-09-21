"""Which way round a node goes, and how big a net to put it on.

The tie a symmetric node leaves behind, and the two things that may
break it: a rule the user picks, and a net repeated before anything is
placed on it.

The blocks are the **synthetic** ones ``tests/test_mof_builder.py``
writes, for the reason stated there: a test about which face a node
presents should not also depend on a crystal having been cut up
correctly, and the real four are Phase 7's to ship.  One more is added
here -- a trigonal planar node -- because a planar block is the case
three connection directions cannot describe at all, and that is what
decided how the rotation group is enumerated.

The second half of the file is the *continuous* freedom, which is a
different lever on the same cost: a two-connected block turns about
the line through its own two connection points, that line moves
neither of them, and the angle is solved rather than searched.

**Which orientation the primary fit returns is not the same on every
machine, and nothing here may assert that it is.**  ``locate`` walks
an Euler grid and takes the first orientation below its threshold
(``locator.py:189-190``, and
``test_two_runs_of_the_same_build_choose_the_same_orientations``
says so), and scipy says out loud that the Kabsch step underneath is
"not uniquely or poorly defined" for these vectors -- the tie this
whole file is about.  Which member of that tie a build starts from
therefore depends on the last bit of a float, and it differed between
an arm64 Mac, an Intel Mac and Windows in one CI run: the same three
tests came back 2.766 against 1.884, 1.667 against 1.668, and a
different linker already right.

Every number in a docstring here is the one this machine measured and
is worth keeping as a record.  What is *asserted* is the property the
rule exists to produce -- a shorter joint than the fit found, at the
same RMSD, with every pair coplanar afterwards -- because that holds
wherever the tie falls.
"""

import numpy as np
import pytest

from tests.test_mof_builder import (
    bidentate_linker,
    bidentate_node,
    needs_builder,
    needs_database,
    single_point_linker,
)
from xtal.mof import Catalog, MofError, database_root
from xtal.mof.build import BuildRequest, build


@pytest.fixture(scope="module")
def catalog():
    if database_root() is None:
        pytest.skip("the vendored PORMAKE database is missing")
    return Catalog.default()


def trigonal_node() -> str:
    """A 3-connected node, flat, whose every point stands for two
    atoms.

    Ni3(HITP)2's nickel meets each imine through two nitrogens and
    the whole node is planar, which is the shape a layer net is built
    out of.  Synthetic for the same reason the others are.
    """
    symbols, positions, bonds = ["Ni"], [(0.0, 0.0, 0.0)], []
    arms = [np.array([np.cos(a), np.sin(a), 0.0])
            for a in np.radians([0.0, 120.0, 240.0])]
    across = np.array([0.0, 0.0, 1.0])
    for k, arm in enumerate(arms):
        symbols += ["N", "N"]
        positions += [tuple(1.4 * arm + 0.6 * across),
                      tuple(1.4 * arm - 0.6 * across)]
        bonds += [(0, 1 + 2 * k), (0, 2 + 2 * k)]
    for k, arm in enumerate(arms):
        symbols.append("X")
        positions.append(tuple(2.1 * arm))
        bonds += [(7 + k, 1 + 2 * k), (7 + k, 2 + 2 * k)]
    return _block_text(symbols, positions, bonds)


def settled(catalog, *spelled):
    """A framework as the builder leaves it, before anything settles.

    ``build`` settles it on the way past, which is the point -- so a
    test that wants to watch the turn happen has to stand between the
    two, and this is that seam.
    """
    from xtal.mof.build import _build, _resolve

    request = BuildRequest.parse(*spelled)
    topology, nodes, edges = _resolve(request, catalog)
    return _build(topology, nodes, edges, None, request.repeat,
                  request.orientation)


def disagreement(framework):
    """How badly the two ends of each joint disagree about their face.

    :func:`xtal.mof.attach.pair_cost` per joint, which is 0.000000
    when the two frames coincide and 2.000000 at a quarter turn --
    the same number the discrete rule above minimises, so the two
    halves of this file are scored on one scale.
    """
    from xtal.mof import orient
    from xtal.mof.attach import pair_cost

    blocks = framework.info["located_bbs"]
    out = []
    for here, there in orient.fused_points(
            framework.info["topology"], blocks,
            framework.info["permutations"]):
        mine = orient._attachment_at(blocks, *here)
        theirs = orient._attachment_at(blocks, *there)
        if mine is not None and theirs is not None:
            out.append(round(pair_cost(mine, theirs, mine.axis), 6))
    return sorted(out)


def positions_of(framework):
    """Every placed block's atoms, slot by slot, before wrapping."""
    return {slot: np.asarray(block.atoms.get_positions(), dtype=float)
            for slot, block in
            enumerate(framework.info["located_bbs"])
            if block is not None}


def _fresh(path):
    """A directory for one build's CIF, made rather than assumed."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _block_text(symbols, positions, bonds) -> str:
    marked = [i for i, s in enumerate(symbols) if s == "X"]
    lines = [str(len(symbols)), "".join(f"{i:5d}" for i in marked)]
    lines += [f"{s:<4s} {x:.4f} {y:.4f} {z:.4f}"
              for s, (x, y, z) in zip(symbols, positions, strict=True)]
    lines += [f"{i:4d} {j:4d} S" for i, j in bonds]
    return "\n".join(lines) + "\n"


@pytest.fixture
def synthetic(tmp_path):
    """A catalogue with the five synthetic blocks in it."""
    folder = tmp_path / "blocks"
    folder.mkdir()
    for name, text in (("SNODE", bidentate_node()),
                       ("SLINK", bidentate_linker()),
                       ("SSTICK", single_point_linker()),
                       ("STRIG", trigonal_node())):
        (folder / f"{name}.xyz").write_text(text, encoding="utf-8")
    return Catalog.default(also_blocks=[folder])


def placed(topology, block, fits):
    """One placement per fit, as the set of its body positions.

    Rounded and sorted as a *set of atoms* rather than column by
    column: sorting each coordinate on its own would destroy the atom
    correspondence and make every symmetry-related placement look
    identical, which is the opposite of what is being counted.
    """
    from xtal.mof import orient

    locator = orient._locator()
    points = set(block.connection_point_indices)
    body = [i for i in range(block.n_atoms) if i not in points]
    out = set()
    for fit in fits:
        located, _rmsd = locator.locate_with_permutation(
            topology.local_structure(fit.slot), block,
            np.asarray(fit.permutation))
        out.add(tuple(sorted(
            tuple(np.round(row, 2))
            for row in located.atoms.positions[body])))
    return out


# ------------------------------------------------ a net, repeated

@needs_builder
def test_a_net_repeated_twice_has_eight_times_the_slots(catalog):
    """``Topology.expanded`` is ``Topology.__mul__``, which tiles the
    net's atoms and rebuilds its neighbour lists.  Every slot of the
    net becomes eight, nodes and edges alike, which is what makes a
    framework on it the same material in a larger cell."""
    net = catalog.topology("pcu")

    once = net.expanded()
    twice = net.expanded(2, 2, 2)

    assert twice.n_slots == 8 * once.n_slots
    assert len(twice.node_indices) == 8 * len(once.node_indices)
    assert len(twice.edge_indices) == 8 * len(once.edge_indices)


@needs_builder
def test_a_repeat_of_one_builds_exactly_what_it_built_before(
        tmp_path, catalog):
    """A repeat of one does not multiply anything -- it hands back the
    net itself -- so the build it produces is the build it always
    produced, file for file, and the framework is not renamed."""
    plain = build(BuildRequest.parse("pcu", "N59", "E32"),
                  _fresh(tmp_path / "a"), catalog)
    spelled = build(BuildRequest.parse("pcu", "N59", "E32", "1x1x1"),
                    _fresh(tmp_path / "b"), catalog)

    assert plain.request.repeat == (1, 1, 1)
    assert plain.request.title() == "pcu-N59-E32"
    assert spelled.request.title() == "pcu-N59-E32"
    assert spelled.cif.read_text() == plain.cif.read_text()


def test_a_repeat_is_written_into_the_name_and_only_when_there_is_one():
    """The name says what the framework is made of, and a supercell of
    it is a different file of the same material -- so the repeat is in
    the name, and a repeat of one is not, or every framework built
    before repeats existed would be renamed."""
    assert BuildRequest.parse("pcu", "N59", "E32", "2x2x2").title() \
        == "pcu-2x2x2-N59-E32"
    assert BuildRequest.parse("pcu", "N59", "E32", "2").repeat \
        == (2, 2, 2)
    assert BuildRequest.parse("pcu", "N59", "E32", "3,1,1").repeat \
        == (3, 1, 1)
    with pytest.raises(MofError, match="2x2x2"):
        BuildRequest.parse("pcu", "N59", "E32", "twice")


# ------------------------------------------------- the tie itself

@needs_builder
def test_an_octahedral_block_has_twenty_four_tied_fits(synthetic):
    """The whole reason this phase exists.  An octahedral node fits a
    six-connected slot 24 ways and the primary fit takes whichever its
    Euler grid reached first -- so which face the node presents to its
    neighbour is, without this, an accident.

    24 out of 720 permutations, found from 24 ordered pairs rather
    than by trying the 720.
    """
    from xtal.mof import orient

    pormake = orient.import_pormake()
    topology = synthetic.topology("pcu").expanded()
    block = pormake.BuildingBlock(
        str(synthetic.building_block("SNODE").path))

    group = orient.rotation_group(block)
    fits = orient.tie_set(topology, int(topology.node_indices[0]),
                          block)

    assert len(group) == 24
    assert len(fits) == 24
    assert len({fit.permutation for fit in fits}) == 24


@needs_builder
def test_every_tied_permutation_has_the_same_rmsd_to_six_places(
        synthetic):
    """A tie is a tie, and what makes it one is measured by placing
    every candidate rather than derived from the group: the 24 are
    validated through the same ``locate_with_permutation`` the builder
    will call, so the fit scored is the fit produced.

    The gap this has to find is five orders of magnitude wide --
    4.2e-08 against 8.2e-01 -- which is why the criterion is a factor
    and never an epsilon.
    """
    from xtal.mof import orient

    pormake = orient.import_pormake()
    topology = synthetic.topology("pcu").expanded()
    block = pormake.BuildingBlock(
        str(synthetic.building_block("SNODE").path))

    fits = orient.tie_set(topology, int(topology.node_indices[0]),
                          block)

    assert len({round(fit.rmsd, 6) for fit in fits}) == 1
    assert max(fit.rmsd for fit in fits) < 1e-6


@needs_builder
def test_a_kuratowski_block_reaches_exactly_two_body_orientations(
        synthetic):
    """24 fits, two placements.  The node's own body is invariant
    under half the octahedron's rotations -- the twelve of the
    tetrahedral group -- so the 24 collapse to exactly 2 distinct
    orientations of the block, which is the same count the Kuratowski
    Zn5Cl4 node of MFU-4l gives and is what makes this a *choice*
    rather than a search."""
    from xtal.mof import orient

    pormake = orient.import_pormake()
    topology = synthetic.topology("pcu").expanded()
    block = pormake.BuildingBlock(
        str(synthetic.building_block("SNODE").path))
    fits = orient.tie_set(topology, int(topology.node_indices[0]),
                          block)

    assert len(placed(topology, block, fits)) == 2


@needs_builder
def test_a_trigonal_linker_has_one_orientation_only(synthetic):
    """A flat three-connected node fits its slot all six ways and
    every one of them is the same block in the same place.

    This is the block that decided how the group is enumerated.  Three
    coplanar directions never span a volume, so a search over ordered
    *triples* can name no rotation of this block at all and returns
    the identity alone -- one tied fit where there are six.  A pair
    and the normal of its plane has no such blind spot.
    """
    from xtal.mof import orient

    pormake = orient.import_pormake()
    topology = synthetic.topology("pbz").expanded()
    block = pormake.BuildingBlock(
        str(synthetic.building_block("STRIG").path))

    fits = orient.tie_set(topology, int(topology.node_indices[0]),
                          block)

    assert len(fits) == 6
    assert len(placed(topology, block, fits)) == 1


# --------------------------------------------- choosing between them

@needs_builder
@pytest.mark.slow
def test_as_found_builds_exactly_what_it_built_before(
        tmp_path, synthetic):
    """``as-found`` is the fit's own choice, so a build that asks for
    it never reaches any of the discrete choice above.  It was the
    default until ``consistent`` took over; the pins are the ones it
    had then.

    It does reach the *continuous* one, and that is not a hole in the
    guarantee.  A node's fit decides which of its own rotations was
    applied and ``as-found`` is faithful to that decision; a linker's
    fit leaves the angle about its own axis **undetermined**, so
    there is no decision there to be faithful to and
    :func:`xtal.mof.orient.align_edges` runs whatever the rule is.
    The square that ``test_the_two_ends_of_a_joint_are_paired_not_
    crossed`` used to pin at 1.797 A is what it undoes; what no
    continuous turn can undo is two nodes a quarter turn apart, and
    that is what the rule below is for.
    """
    built = build(BuildRequest.parse("pcu", "SNODE", "SLINK", "",
                                     "as-found"),
                  _fresh(tmp_path / "a"), synthetic)

    assert built.joints == 12
    assert round(built.longest_joint, 3) == 1.500
    assert built.twist is None


@needs_builder
@pytest.mark.slow
def test_a_build_that_names_no_rule_is_built_consistent(tmp_path,
                                                         synthetic):
    """``consistent`` is the default: it is what builds MOF-5 with its
    clusters alternating, and Phase 1 of the face rule is what made it
    safe to be -- it starts from the fit, leaves it only for something
    strictly cheaper, and throws away a rebuild that fits worse."""
    request = BuildRequest.parse("acs", "SNODE", "")
    assert request.orientation == "consistent"

    unnamed = build(request, _fresh(tmp_path / "a"), synthetic)
    named = build(BuildRequest.parse("acs", "SNODE", "", "",
                                     "consistent"),
                  _fresh(tmp_path / "b"), synthetic)

    assert unnamed.cif.read_text() == named.cif.read_text()
    assert unnamed.twist is not None


@needs_builder
@pytest.mark.slow
def test_consistent_orientations_put_opposite_nodes_on_every_edge(
        tmp_path, synthetic):
    """**acs** joins two node slots to each other, and with no linker
    between them the two ends of every edge are the joint.

    So this is where the discrete choice is the whole answer rather
    than half of it: the fit leaves the two nodes a quarter turn
    apart and the joint comes back 2.766 A long, and turning them
    brings it to 1.931.  Neither number is a bond length -- these are
    synthetic blocks -- but the second is the shorter, and no
    continuous rotation of anything could have found it.

    It was 1.884 until the search started from the fit.  The fit's own
    permutation is in neither slot's tie set here, and the search used
    to start both slots at their lowest permutation instead, logging
    *that* as "as found" at 2.602 -- the real fit costs 9.693 -- and
    then kept it for a 1e-5 improvement.  Started honestly it reaches
    2.191, cheaper on the cost the rule minimises.
    """
    as_found = build(BuildRequest.parse("acs", "SNODE", "", "",
                                        "as-found"),
                     _fresh(tmp_path / "a"), synthetic)
    consistent = build(BuildRequest.parse("acs", "SNODE", "", "",
                                          "consistent"),
                       _fresh(tmp_path / "b"), synthetic)

    assert as_found.joints == consistent.joints == 12
    # The numbers in the docstring are this machine's. Which
    # orientation the *primary* fit returns is not portable -- see the
    # note at the top of this file -- so what is asserted is the
    # relationship the rule exists to produce, which is.
    assert consistent.longest_joint < as_found.longest_joint
    # The fit is not touched: what changed is which way round the
    # block went, not how well it sits on its slot.
    assert round(consistent.max_rmsd, 3) == round(as_found.max_rmsd, 3)


@needs_builder
@pytest.mark.slow
def test_two_runs_of_the_same_build_choose_the_same_orientations(
        tmp_path, synthetic):
    """``locate``'s early exit at ``locator.py:189-190`` stops at the
    first orientation on its Euler grid that is good enough, so the
    primary fit -- and every permutation composed with it -- depends
    on the order that grid was walked in.  The tie set is therefore
    ordered by the permutation itself and every tie below it is broken
    by the lowest one, which is what stops two runs of one build
    differing."""
    first = build(BuildRequest.parse("acs", "SNODE", "", "",
                                     "consistent"),
                  _fresh(tmp_path / "a"), synthetic)
    second = build(BuildRequest.parse("acs", "SNODE", "", "",
                                      "consistent"),
                   _fresh(tmp_path / "b"), synthetic)

    assert second.cif.read_text() == first.cif.read_text()


def _acs_nodes(synthetic):
    """acs, and the synthetic bidentate node on both its node slots."""
    from xtal.mof import orient

    pormake = orient.import_pormake()
    topology = synthetic.topology("acs").expanded()
    blocks = [None] * topology.n_slots
    for slot in topology.node_indices:
        blocks[int(slot)] = pormake.BuildingBlock(
            str(synthetic.building_block("SNODE").path))
    return topology, blocks


@needs_builder
def test_the_fit_s_own_orientation_is_always_a_candidate(synthetic):
    """The tie set is located afresh, and ``locate`` stops at the
    first good-enough orientation on its grid, so the builder's own
    fit need not be in it -- on ``cds`` with N307 it was not, and the
    search started that slot elsewhere and rebuilt the framework at
    the same cost, a joint going from 3.49 A to 2.54 for nothing.
    So the fit is admitted and started from, and like every other
    start it is left only for something strictly cheaper."""
    import itertools

    from xtal.mof import orient

    topology, blocks = _acs_nodes(synthetic)
    nodes = [int(s) for s in topology.node_indices]
    ties = {slot: orient.tie_set(topology, slot, blocks[slot])
            for slot in nodes}
    allowed = {fit.permutation for fit in ties[nodes[0]]}
    foreign = next(p for p in itertools.permutations(
        range(len(ties[nodes[0]][0].permutation))) if p not in allowed)
    baseline = {nodes[0]: foreign,
                nodes[1]: ties[nodes[1]][0].permutation}

    admitted = orient._admit(nodes, ties, baseline)

    assert foreign in {fit.permutation for fit in admitted[nodes[0]]}
    assert len(admitted[nodes[1]]) == len(ties[nodes[1]])
    assert orient._start(nodes, admitted, baseline)[nodes[0]] == foreign


@needs_builder
@pytest.mark.slow
def test_a_second_pass_that_fits_worse_is_thrown_away(
        tmp_path, synthetic, monkeypatch):
    """Pass 2 relaxes the cell again around the turned nodes, and the
    choice never looked at how well they would sit afterwards.
    ``nbo`` on N466 and E14, turned, fitted 0.973 A against 0.562 as
    found; a default rule cannot hand that back.  Here pass 2 -- the
    only call that pins permutations -- is made to report a worse
    fit, and the framework that comes back is pass 1's."""
    from xtal.mof import orient

    builder = orient.import_pormake().Builder
    real = builder.build

    def worse(self, topology, bbs, permutations=None, **kwargs):
        framework = real(self, topology, bbs, permutations, **kwargs)
        if permutations:
            framework.info["max_rmsd"] = (
                float(framework.info["max_rmsd"]) + 0.5)
        return framework

    monkeypatch.setattr(builder, "build", worse)
    said = []
    turned = build(BuildRequest.parse("acs", "SNODE", "", "",
                                      "consistent"),
                   _fresh(tmp_path / "a"), synthetic, log=said.append)
    plain = build(BuildRequest.parse("acs", "SNODE", "", "",
                                     "as-found"),
                  _fresh(tmp_path / "b"), synthetic)

    # Pass 1's framework either way, which is the whole claim.
    assert turned.cif.read_text() == plain.cif.read_text()
    if not any("moved" in line or "turned" in line for line in said):
        pytest.skip("the rule found nothing to turn on this machine, "
                    "so there was no second pass to throw away -- see "
                    "the note at the top of this file")
    assert any("fit their slots worse" in line for line in said)


@needs_builder
@pytest.mark.slow
def test_a_second_pass_that_moves_the_cell_is_thrown_away(tmp_path,
                                                          catalog):
    """A tie does not move where connection points go, so it cannot
    move the cell.  ``dia`` on N623 and E14, turned, relaxed to a cell
    with *b* = 0.007 A: every block fitted to 1e-4 because there was
    no room left to misfit in, the closest contact was 0.01 A, and
    writing the CIF took five minutes.  The fit's framework comes
    back instead, and says why."""
    said = []
    turned = build(BuildRequest.parse("dia", "N623", "E14"),
                   _fresh(tmp_path / "a"), catalog, log=said.append)
    plain = build(BuildRequest.parse("dia", "N623", "E14", "",
                                     "as-found"),
                  _fresh(tmp_path / "b"), catalog)

    assert any("relaxed to another cell" in line for line in said)
    assert round(turned.max_rmsd, 6) == round(plain.max_rmsd, 6)
    assert turned.closest > 1.0
    assert (turned.structure.lattice.parameters[:3]
            == pytest.approx(plain.structure.lattice.parameters[:3]))


@needs_builder
def test_a_joint_is_scored_once_however_often_the_search_asks(
        synthetic, monkeypatch):
    """The search asks for the same joint under the same pair of
    orientations over and over: 15 096 scorings for 1736 distinct
    answers on MFU-4l's pcu x 2x2x2, and 54 of 72 seconds on a
    2x2x2 ``dia``.  Each is scored once."""
    from xtal.mof import orient

    seen = []
    real = orient.pair_cost

    def counted(a, b, axis):
        seen.append((a.point, a.offsets.tobytes(), b.point,
                     b.offsets.tobytes(), np.asarray(axis).tobytes()))
        return real(a, b, axis)

    monkeypatch.setattr(orient, "pair_cost", counted)
    topology, blocks = _acs_nodes(synthetic)
    orient.choose_permutations(topology, blocks, "consistent")

    assert seen
    assert len(seen) == len(set(seen))


@needs_builder
def test_a_rule_with_nothing_to_score_refuses_by_name(synthetic):
    """N6 is a B12 icosahedron: every connection point stands for one
    boron, and a boron with five neighbours besides it presents no
    plane -- so every joint in such a build costs zero however the
    nodes are turned.  N59 was this test's block until a carboxylate
    became a face.

    The refusal is the function's and not the build's.  A build asks
    only after it has found a polydentate block, and one that has not
    keeps the fit and says so -- failing a whole framework because a
    preference had nothing to do would be the wrong end of the same
    stick.
    """
    from xtal.mof import orient

    pormake = orient.import_pormake()
    topology = synthetic.topology("pcu").expanded()
    blocks = [None] * topology.n_slots
    for slot in topology.node_indices:
        blocks[int(slot)] = pormake.BuildingBlock(
            str(synthetic.building_block("N6").path))

    with pytest.raises(MofError, match="consistent"):
        orient.choose_permutations(topology, blocks, "consistent")


@needs_builder
@pytest.mark.slow
def test_a_build_with_nothing_to_score_keeps_the_fit(tmp_path,
                                                     synthetic):
    """And the build itself does not refuse.  Asking for consistent
    orientations of blocks that have no faces is a preference with
    nothing to apply it to, and the framework is the one the fit
    made.  N6's borons have five neighbours each and E32's points
    hang off alkyne carbons, so neither presents a plane."""
    asked = build(BuildRequest.parse("pcu", "N6", "E32", "",
                                     "consistent"),
                  _fresh(tmp_path / "a"), synthetic)
    plain = build(BuildRequest.parse("pcu", "N6", "E32"),
                  _fresh(tmp_path / "b"), synthetic)

    assert asked.cif.read_text() == plain.cif.read_text()


@needs_builder
@pytest.mark.slow
def test_nodes_with_nothing_to_score_between_linkers_with_faces_keep_the_fit(
        tmp_path, synthetic):
    """The build asked whether *any* block had a frame, and the rule
    asks only of the nodes -- so N6 between E14 rings reached the rule
    with nothing it could score and failed the whole build.  ``cds``
    on N307 and E3 did, in the shipped database.  The nodes keep the
    fit; the linkers still turn."""
    asked = build(BuildRequest.parse("pcu", "N6", "E14", "",
                                     "consistent"),
                  _fresh(tmp_path / "a"), synthetic)
    plain = build(BuildRequest.parse("pcu", "N6", "E14", "",
                                     "as-found"),
                  _fresh(tmp_path / "b"), synthetic)

    assert asked.n_atoms == plain.n_atoms
    assert round(asked.max_rmsd, 6) == round(plain.max_rmsd, 6)


@needs_builder
def test_a_rule_nobody_has_written_is_refused_by_name(synthetic):
    """``xtal run`` takes the rule as a string, so a typo reaches
    here; the sentence names what there is instead of failing on a
    lookup."""
    from xtal.mof import orient

    with pytest.raises(MofError, match="as-found"):
        orient.choose_permutations(None, [], "sensible")


@needs_builder
def test_a_block_mirrored_in_the_first_pass_stays_mirrored_in_the_second(
        synthetic):
    """The hazard of running two passes, and it runs the opposite way
    to the obvious one.

    A pinned permutation ``continue``s at ``builder.py:266``, before
    the chiral retries at ``:298`` and ``:311`` and before
    ``make_chiral_building_block`` at ``:313`` -- so it never fights
    the fallback.  What it does is *skip* it: if the first pass
    quietly substituted a mirrored block, the second would place the
    un-mirrored one, come out worse, and say nothing.  A mirror flips
    the sign of the volume three connection directions span, and that
    is how it is caught.
    """
    from types import SimpleNamespace

    from xtal.mof import orient

    pormake = orient.import_pormake()
    path = str(synthetic.building_block("SNODE").path)
    blocks = [pormake.BuildingBlock(path),
              pormake.BuildingBlock(path)]
    framework = SimpleNamespace(info={"located_bbs": [
        blocks[0].make_chiral_building_block(),
        pormake.BuildingBlock(path)]})

    changed, unchecked = orient.substitute_mirrored(blocks, framework)

    assert changed == [0] and unchecked == []
    assert orient.handedness(blocks[0]) * orient.handedness(
        pormake.BuildingBlock(path)) < 0
    assert orient.handedness(blocks[1]) * orient.handedness(
        pormake.BuildingBlock(path)) > 0


@needs_database
def test_a_flat_block_has_no_handedness_to_carry_over(synthetic):
    """A planar block's mirror image is one of its own rotations, so
    there is no substitution to detect and nothing to carry into the
    second pass.  Saying that with a zero rather than with a guess is
    what keeps :func:`mirrored` from firing on rounding."""
    from xtal.mof import orient

    pormake = orient.import_pormake()
    flat = pormake.BuildingBlock(
        str(synthetic.building_block("STRIG").path))

    assert orient.handedness(flat) == 0.0
    assert not orient.mirrored(flat,
                               flat.make_chiral_building_block())


# ------------------------------------- the angle about its own axis

@needs_builder
@pytest.mark.slow
def test_a_planar_linker_lands_coplanar_with_both_ends(synthetic):
    """The freedom the primary fit does not decide, and so is not
    overriding when this decides it.

    Placing a two-connected block is Kabsch on two vectors, which
    scipy itself warns is "not uniquely defined": the angle about the
    line through the block's own two points is left where the grid
    happened to leave it.  On ``pcu`` this node presents a different
    face on each pair of axes, so the fit leaves one linker already
    right, one a third of the way out, and one at **2.000000** -- a
    dead quarter turn, which is the square
    ``test_the_two_ends_of_a_joint_are_paired_not_crossed`` sees as
    four equal distances.

    Every one of them comes back at zero, which is what "coplanar
    with both ends" is in a number: the two ends' unit laterals
    coincide, so the joint's four atoms and its axis are in one
    plane.
    """
    from xtal.mof import orient

    framework = settled(synthetic, "pcu", "SNODE", "SLINK")
    before = disagreement(framework)
    assert len(before) == 6
    # One cost per joint, and a linker owns two of them, so a sorted
    # disagreement comes in adjacent pairs and turning one linker
    # clears both. Asserted rather than assumed: if that stops being
    # true the arithmetic below would hide it.
    assert before[0::2] == before[1::2]
    # *How many* the fit left wrong is this machine's business -- see
    # the note at the top of this file. That each of them comes back
    # at zero, and that nothing already right was touched, is not.
    crooked = sum(1 for cost in before[0::2] if cost > 1e-6)

    turned = orient.align_edges(framework)

    # Only the ones that needed it: a linker the fit had already put
    # right is left alone rather than turned by its own rounding.
    assert turned == crooked
    assert disagreement(framework) == [0.0] * 6


@needs_builder
@pytest.mark.slow
def test_settling_moves_no_connection_point(synthetic):
    """Why this is a refinement of the fit and not a second one.

    The axis is the line through the block's own two connection
    points, so both of them are *on* it and a turn about it leaves
    them exactly where the builder fused them.  The RMSD the fit
    reported, the cell the scaler relaxed and every X-to-X
    coincidence therefore go on being true of the framework that is
    written out, which is what makes turning it legal at all.
    """
    from xtal.mof import orient

    framework = settled(synthetic, "pcu", "SNODE", "SLINK")
    blocks = framework.info["located_bbs"]
    before = {slot: np.asarray(
        blocks[slot].atoms.get_positions(), dtype=float)[
            list(blocks[slot].connection_point_indices)]
        for slot in orient._turnable(blocks)}

    orient.align_edges(framework)

    for slot, points in before.items():
        moved = np.asarray(blocks[slot].atoms.get_positions(),
                           dtype=float)[
            list(blocks[slot].connection_point_indices)]
        assert float(np.abs(moved - points).max()) < 1e-9


@needs_builder
@pytest.mark.slow
def test_settling_moves_no_atom_between_blocks(synthetic):
    """A turn is one block's own and reaches nothing else.

    Nothing is added, nothing is removed and nothing changes hands:
    the framework comes back with the same atoms in the same order,
    every block that was not turned exactly where it was placed, and
    only the bodies of the ones that were anywhere else.  A test
    worth having because the write-back is index arithmetic over
    ``_framework_indices``, and the way that arithmetic fails is by
    moving the wrong atoms rather than by raising.
    """
    from xtal.mof import orient

    framework = settled(synthetic, "pcu", "SNODE", "SLINK")
    before = positions_of(framework)
    symbols = list(framework.atoms.symbols)
    turnable = set(orient._turnable(framework.info["located_bbs"]))

    orient.align_edges(framework)
    after = positions_of(framework)

    assert list(framework.atoms.symbols) == symbols
    assert set(after) == set(before)
    still = [slot for slot in before
             if float(np.abs(after[slot] - before[slot]).max()) > 1e-9]
    assert set(still) <= turnable
    # And the node slot is one of the ones that did not move: it is
    # six-connected, so it has no axis of its own to turn about.
    assert 0 in before and 0 not in still


@needs_builder
@pytest.mark.slow
def test_a_linker_with_no_members_is_left_where_it_was_placed(
        tmp_path, synthetic, catalog):
    """A connection point standing for one atom presents no face, so
    no angle is better than any other and there is nothing to settle.

    That is the whole of the guarantee for the 867 shipped blocks --
    not a rule they are exempt from but a list they are not on -- and
    it is checked twice here: once on the framework, which comes back
    atom for atom as it was placed, and once through ``build``, where
    a shipped net on shipped blocks writes the CIF it always wrote.
    """
    from xtal.mof import orient

    framework = settled(synthetic, "pcu", "SNODE", "SSTICK")
    before = positions_of(framework)

    assert orient._turnable(framework.info["located_bbs"]) == []
    assert orient.align_edges(framework) == 0
    assert all(np.array_equal(after, before[slot])
               for slot, after in positions_of(framework).items())

    shipped = build(BuildRequest.parse("pcu", "N59", "E32"),
                    _fresh(tmp_path / "a"), catalog)
    assert shipped.joints == 6
    assert shipped.longest_joint == 0.0


@needs_builder
def test_a_two_connected_node_turns_like_a_linker(synthetic):
    """The same freedom, and it is not an edge slot's.

    Ni3(HITP)2's NiN4H4 is two-connected and bidentate and sits on a
    *node* slot of ``hcb``; its angle about its own axis is as
    undetermined as any linker's and matters for the same reason.  So
    what is asked is the block -- two connection points, and a face
    at one of them -- and never which kind of slot it landed on,
    which is what covers both without naming either.
    """
    from xtal.mof import orient

    pormake = orient.import_pormake()
    node = pormake.BuildingBlock(
        str(synthetic.building_block("SNODE").path))
    linker = pormake.BuildingBlock(
        str(synthetic.building_block("SLINK").path))
    stick = pormake.BuildingBlock(
        str(synthetic.building_block("SSTICK").path))

    # The two-connected block in a node slot and the six-connected
    # one in an edge slot: the answer follows the block.
    assert orient._turnable([linker, node, None, stick]) == [0]


# ------------------------------------------------ faces

def _carboxylate(tilt=0.0):
    """C with two neighbours in the xy plane and a point along +y,
    lifted ``tilt`` A out of that plane.  ``(connections, bonds,
    positions)`` in the shape a block hands :mod:`xtal.mof.attach`."""
    positions = [(0.0, 0.0, 0.0), (1.08, -0.62, 0.0),
                 (-1.08, -0.62, 0.0), (0.0, 0.75, tilt)]
    bonds = [(0, 1), (0, 2), (3, 0)]
    return (3,), bonds, np.array(positions)


def test_a_face_is_the_plane_of_the_atom_and_its_two_neighbours():
    """The carboxylate is in the xy plane and the joint runs along y,
    so what it presents across the joint is +-x: a line in its own
    plane, and nothing along z."""
    from xtal.mof.attach import face_of, unit_laterals

    face = face_of(*_carboxylate(), 3)
    laterals = unit_laterals(face, [0.0, 1.0, 0.0])

    assert face.members == (1, 2)
    assert np.allclose(np.abs(laterals), [[1, 0, 0], [1, 0, 0]])
    assert np.allclose(laterals.sum(axis=0), 0.0)
    assert np.allclose(face.axis, [0.0, 1.0, 0.0])


def test_a_face_does_not_care_where_its_x_was_written():
    """2045 of the 3899 faces the shipped blocks present have their X
    more than 0.1 off the plane -- E102's is 0.65.  Tilted by half an
    Angstrom, the carboxylate still presents +-x across the joint."""
    from xtal.mof.attach import face_of, unit_laterals

    upright = face_of(*_carboxylate(), 3)
    tilted = face_of(*_carboxylate(tilt=0.5), 3)
    axis = [0.0, 1.0, 0.0]

    # To the hair `face_of` keeps along the bond for `axis`'s sake,
    # a millionth of a radian; at 0.5 A of tilt the old construction
    # leaned by 0.43.
    assert np.allclose(unit_laterals(tilted, axis),
                       unit_laterals(upright, axis), atol=1e-5)


def test_a_linear_or_tetrahedral_point_presents_no_face():
    """One other neighbour is a line and has no plane; three is a
    free rotor with no preferred angle.  Neither is a face, and a
    point standing for several atoms has its members instead."""
    from xtal.mof.attach import face_of

    linear = [(0.0, 0.0, 0.0), (0.0, -1.2, 0.0), (0.0, 0.75, 0.0)]
    assert face_of((2,), [(0, 1), (2, 0)], linear, 2) is None

    rotor = [(0.0, 0.0, 0.0), (1.0, -0.4, 0.0), (-0.5, -0.4, 0.87),
             (-0.5, -0.4, -0.87), (0.0, 0.75, 0.0)]
    assert face_of((4,), [(0, 1), (0, 2), (0, 3), (4, 0)], rotor,
                   4) is None

    chelate = [(0.7, 0.0, 0.0), (-0.7, 0.0, 0.0), (0.0, 0.75, 0.0)]
    assert face_of((2,), [(0, 2), (1, 2)], chelate, 2) is None


def test_a_face_is_never_a_member():
    """``members_of`` owns joints and bonding, so the two oxygens a
    carboxylate's face is taken from must never be read as atoms that
    join the next block."""
    from xtal.mof.attach import members_of, presents_face

    connections, bonds, positions = _carboxylate()

    assert members_of(connections, bonds) == {3: (0,)}
    assert presents_face(connections, bonds, positions)
