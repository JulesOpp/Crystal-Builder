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
def test_the_default_rule_builds_exactly_what_it_built_before(
        tmp_path, synthetic):
    """``as-found`` is the default and it is today's behaviour, so a
    build that does not ask for a rule never reaches any of this.

    Pinned against the numbers ``test_the_two_ends_of_a_joint_are_
    paired_not_crossed`` fixed in the phase before: twelve joints and
    a longest of 1.797 A, which is the square -- the quarter turn
    between a node and its linker that only a *continuous* turn of the
    linker can undo.
    """
    request = BuildRequest.parse("pcu", "SNODE", "SLINK")
    assert request.orientation == "as-found"

    built = build(request, _fresh(tmp_path / "a"), synthetic)
    named = build(BuildRequest.parse("pcu", "SNODE", "SLINK", "",
                                     "as-found"),
                  _fresh(tmp_path / "b"), synthetic)

    assert built.joints == 12
    assert round(built.longest_joint, 3) == 1.797
    assert named.cif.read_text() == built.cif.read_text()


@needs_builder
@pytest.mark.slow
def test_consistent_orientations_put_opposite_nodes_on_every_edge(
        tmp_path, synthetic):
    """**acs** joins two node slots to each other, and with no linker
    between them the two ends of every edge are the joint.

    So this is where the discrete choice is the whole answer rather
    than half of it: the fit leaves the two nodes a quarter turn
    apart and the joint comes back 2.766 A long, and turning one of
    them brings it to 1.884.  Neither number is a bond length -- these
    are synthetic blocks -- but the second is the shorter, and no
    continuous rotation of anything could have found it.
    """
    as_found = build(BuildRequest.parse("acs", "SNODE", "", "",
                                        "as-found"),
                     _fresh(tmp_path / "a"), synthetic)
    consistent = build(BuildRequest.parse("acs", "SNODE", "", "",
                                          "consistent"),
                       _fresh(tmp_path / "b"), synthetic)

    assert as_found.joints == consistent.joints == 12
    assert round(as_found.longest_joint, 3) == 2.766
    assert round(consistent.longest_joint, 3) == 1.884
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


@needs_builder
def test_a_rule_with_nothing_to_score_refuses_by_name(synthetic):
    """No shipped block is polydentate: every connection point stands
    for exactly one atom, which presents no face, so every joint in
    such a build costs zero however the nodes are turned.

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
            str(synthetic.building_block("N59").path))

    with pytest.raises(MofError, match="consistent"):
        orient.choose_permutations(topology, blocks, "consistent")


@needs_builder
@pytest.mark.slow
def test_a_build_with_nothing_to_score_keeps_the_fit(tmp_path,
                                                     synthetic):
    """And the build itself does not refuse.  Asking for consistent
    orientations of blocks that have no faces is a preference with
    nothing to apply it to, and the framework is the one the fit
    made."""
    asked = build(BuildRequest.parse("pcu", "N59", "E32", "",
                                     "consistent"),
                  _fresh(tmp_path / "a"), synthetic)
    plain = build(BuildRequest.parse("pcu", "N59", "E32"),
                  _fresh(tmp_path / "b"), synthetic)

    assert asked.cif.read_text() == plain.cif.read_text()


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
