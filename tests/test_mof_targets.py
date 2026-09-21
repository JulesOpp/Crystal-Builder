"""MFU-4l and Ni3(HITP)2, built out of the blocks this application
ships of its own.

Everything the four phases before this one added is exercised here at
once, on a real material rather than on a synthetic block: a
connection point standing for two atoms
(:mod:`xtal.mof.attach`), every member of a polydentate end arriving
bonded (:func:`xtal.mof.build.bond_joints`), the discrete choice of
which way round a node goes (:mod:`xtal.mof.orient`), and the
continuous angle a linker is left at.

The blocks are the shipped ones -- ``xtal/mof/library/blocks`` --
because that is the other half of what this file is for.  A test that
cut them out of ``MFU4l.cif`` for itself would pass in a checkout
whose package data never reached the ``.dmg``; asking
:meth:`Catalog.default` for them by name is what says they are where
a packaged user will find them.

One node and three linkers make **Zn5Cl4N18C36O6H12**, which is the
crystal's own formula for one Kuratowski unit -- so the composition
is not an arbitrary pin but the statement that nothing was lost at a
cut and nothing counted twice.

Ni3(HITP)2 is the second target and the first **layer**: ``hcb`` is
one of the three 2-periodic nets in ``xtal/mof/library/nets``, and
the spacing between its sheets is set after the build by
:mod:`xtal.mof.layers`.  Two triphenylenes and three NiN4H4 make
**C36H24N12Ni3**, the CIF's own ``_chemical_formula_sum``.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from tests.test_mof_builder import needs_builder, needs_database
from xtal.core.structure import TOPOLOGY
from xtal.io import FORMATS
from xtal.mof import (
    CONNECTION_DISTANCE,
    Catalog,
    MofError,
    library_nets,
    library_root,
)
from xtal.mof.attach import MAX_ATTACHMENT_SPAN
from xtal.mof.build import BuildRequest, build
from xtal.mof.layers import DEFAULT_SPACING

#: The four are package data, so a checkout can have the code and not
#: the blocks in exactly the way a bundle can.  Skipped rather than
#: failed for the same reason the database is: it is an installation
#: that is short, not a rule that is broken.
needs_library = pytest.mark.skipif(
    library_root() is None,
    reason="the four polydentate blocks are missing from this "
           "installation")

#: The layer nets are package data as well, and a separate glob.
needs_layers = pytest.mark.skipif(
    library_nets() is None,
    reason="the layer nets are missing from this installation")

NODE = "MFU4l_Kuratowski"
LINKER = "MFU4l_BTDD"

HITP = "NiHITP_triphenylene"
NICKEL = "NiHITP_NiN4"
SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"
#: Ni3(HITP)2's own c, which is its interlayer spacing: one sheet to
#: a cell, eclipsed.
HITP_SPACING = 3.23835


@pytest.fixture(scope="module")
def catalog():
    return Catalog.default()


@pytest.fixture(scope="module")
def mfu4l(tmp_path_factory, catalog):
    """MFU-4l on **pcu**, built once for the four tests below.

    Module-scoped because a build is a second and none of these tests
    changes what it looks at.  ``as-found`` is the default and is
    deliberately not overridden: on the single cell every edge joins a
    node to an image of itself, so the discrete rule has nothing to
    choose between and the framework must be the one a user who asked
    for nothing gets.
    """
    folder = tmp_path_factory.mktemp("mfu4l")
    return build(BuildRequest.parse("pcu", NODE, LINKER), folder,
                 catalog)


# ------------------------------------------------ what is shipped

@needs_database
@needs_library
def test_all_four_shipped_blocks_are_bidentate_at_every_point():
    """The recipe's whole output, pinned: four blocks, every
    connection point of every one standing for exactly two atoms.

    An ``X`` does not remember what it was, so a block cut one atom
    at a time is indistinguishable in the file from one cut two at a
    time -- until it is built, where it comes out with twice the
    coordination number it has and fits no net in the catalogue.
    That is the failure MFU-4l and Ni3(HITP)2 were stuck on, and it
    is invisible to every other check: the file parses, the block
    lists, the picker draws it.  So the count is asserted here rather
    than left to a build to discover.

    The grouping is the structure's own bonds and never new state on
    a marker, which is why ``members`` can be asked of a block read
    back off disk at all.

    Each point is also checked to be
    :data:`~xtal.mof.block.CONNECTION_DISTANCE` from the centroid of
    the two atoms it stands for -- the middle of the chelate's bite,
    which is where the next block's point has to land.  A block
    written at a bond length instead builds a framework with every
    linker bond twice too long and nothing reports it, and these four
    were cut by a script rather than by the writer in
    :mod:`xtal.mof.block`, so it is worth saying that they agree.
    """
    catalog = Catalog.default()

    ours = {name: catalog.building_block(name)
            for name in (NODE, LINKER, "NiHITP_triphenylene",
                         "NiHITP_NiN4")}

    assert [b.n_connections for b in ours.values()] == [6, 2, 3, 2]
    assert [b.formula for b in ours.values()] == [
        "C12Cl4N18Zn5", "C8H4O2", "C18H6", "H4N4Ni"]
    for name, block in ours.items():
        assert block.is_polydentate, name
        assert sorted(len(m) for m in block.members.values()) == \
            [2] * block.n_connections, name
        for point, members in block.members.items():
            held = block.positions[list(members)]
            reach = np.linalg.norm(block.positions[point]
                                   - held.mean(axis=0))
            assert round(float(reach), 6) == CONNECTION_DISTANCE, name
            bite = np.linalg.norm(held[0] - held[1])
            assert float(bite) < MAX_ATTACHMENT_SPAN, name


# ------------------------------------------------ what came out

@needs_database
@needs_builder
@needs_library
def test_the_built_framework_is_still_pcu(mfu4l):
    """The net is read back off the bonds of what was built, never
    repeated from the request.

    Which is the whole reason it is worth asserting on a polydentate
    build: twelve joints and six edges are different numbers, and a
    framework whose extra bonds had been drawn between the wrong
    atoms would identify as something other than **pcu** -- or as
    nothing at all.
    """
    assert mfu4l.asked == "pcu"
    assert mfu4l.net_name == "pcu"
    assert mfu4l.net_agrees


@needs_database
@needs_builder
@needs_library
def test_the_built_framework_keeps_its_chlorides(mfu4l):
    """One Cl on each of the four peripheral zincs, and the central
    one bare.

    A chloride is the atom this application has lost before: MFU-4l's
    Cl1 is written 0.0006 A off its three-fold axis, and at the old
    tolerance an operation that should have mapped it onto itself
    generated three of it instead.  Nothing in a build goes near
    symmetry generation, so the assertion here is the plainer one --
    four chlorides, each 2.07 A from a zinc of its own -- and it is
    worth making because a chloride is also what a marker held back at
    the door could quietly have taken with it.
    """
    structure = mfu4l.structure
    counts = Counter(site.element for site in structure.sites)

    assert counts == {"C": 36, "N": 18, "H": 12, "O": 6,
                      "Zn": 5, "Cl": 4}

    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    frac = np.array([site.frac for site in structure.sites])
    zinc = [i for i, s in enumerate(structure.sites)
            if s.element == "Zn"]
    partners = []
    for i, site in enumerate(structure.sites):
        if site.element != "Cl":
            continue
        offsets = frac[zinc] - frac[i]
        lengths = np.linalg.norm(
            (offsets - np.round(offsets)) @ matrix, axis=1)
        partners.append(zinc[int(np.argmin(lengths))])
        assert round(float(lengths.min()), 2) == 2.07

    assert len(set(partners)) == 4


@needs_database
@needs_builder
@needs_library
def test_every_triazolate_end_binds_through_two_carbons(mfu4l):
    """Twelve bonds across six joins, and no two of them on one atom.

    This is Phase 4's rule on a real material: a joint is as many
    bonds as the two ends have members, so the node's six triazolate
    arms -- two carbons each, one connection point -- meet three
    linkers through **twelve** C-C bonds and not six.  Six would mean
    each arm had been fused through a single carbon and the other
    left dangling, which is what PORMAKE writing one bond per joint
    gives and what no amount of later perception recovers: the
    surviving carbons are 1.5 A apart with nothing between them.

    The two carbons of one arm must also reach two *different*
    linker carbons.  Both landing on one is a pairing that crossed,
    and it is a real failure mode rather than a hypothetical -- it is
    the square that ``test_the_two_ends_of_a_joint_are_paired_not_
    crossed`` pins on the synthetic blocks.
    """
    structure = mfu4l.structure
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    frac = np.array([site.frac for site in structure.sites])
    element = [site.element for site in structure.sites]

    def apart(i, j):
        offset = frac[j] - frac[i]
        return float(np.linalg.norm((offset - np.round(offset))
                                    @ matrix))

    # A triazolate carbon is the one with a ring nitrogen beside it;
    # every other carbon in the framework belongs to a linker.
    triazolate = {i for i, symbol in enumerate(element)
                  if symbol == "C"
                  and any(element[j] == "N" and apart(i, j) < 1.6
                          for j in range(len(element)))}
    assert len(triazolate) == 12

    joints = [b for b in structure.bonds
              if element[b.i] == "C" and element[b.j] == "C"]
    assert len(joints) == 12
    assert mfu4l.joints == 12

    reached = {}
    for bond in joints:
        near, far = ((bond.i, bond.j) if bond.i in triazolate
                     else (bond.j, bond.i))
        assert near in triazolate and far not in triazolate
        assert near not in reached
        reached[near] = far

    # Six arms, by the C-C bond of each triazolate ring, and each arm
    # reaching two linker carbons rather than the same one twice.
    arms = []
    for i in sorted(triazolate):
        mates = [j for j in triazolate if j != i and apart(i, j) < 1.6]
        assert len(mates) == 1
        if i < mates[0]:
            arms.append((i, mates[0]))
    assert len(arms) == 6
    for near, mate in arms:
        assert reached[near] != reached[mate]


@needs_database
@needs_builder
@needs_library
@pytest.mark.slow
def test_mfu4l_builds_with_its_nodes_alternating(tmp_path, catalog):
    """The Kuratowski cluster's tetrahedron points two ways, and on a
    2x2x2 cell ``consistent`` uses both.

    Every edge of **pcu** joins a node to an image of itself, so on
    the single cell there is nothing for the discrete rule to choose
    between and the two orientations cannot both appear.  Repeat the
    net first and they can: the eight slots are eight independent
    choices, and the rule takes seven of them off what the fit found.

    The measurement is the one MOF-5's own file gives -- the signed
    volume of the four zinc directions out of the cluster's centre,
    ``+0.770`` for one tetrahedron of the cube and ``-0.770`` for the
    other.  ``as-found`` builds all eight the same way round;
    ``consistent`` comes back **four and four**, and the longest joint
    falls from 1.838 A to 1.667 with the blocks sitting on their slots
    exactly as well as before.
    """
    plain = build(BuildRequest.parse("pcu", NODE, LINKER, "2x2x2"),
                  _fresh(tmp_path / "as-found"), catalog)
    turned = build(
        BuildRequest.parse("pcu", NODE, LINKER, "2x2x2", "consistent"),
        _fresh(tmp_path / "consistent"), catalog)

    assert plain.n_atoms == turned.n_atoms == 648
    assert plain.joints == turned.joints == 96
    assert round(plain.longest_joint, 3) == 1.838
    assert round(turned.longest_joint, 3) == 1.667

    assert sorted(_handedness(plain.structure)) == [-0.77] * 8
    assert sorted(_handedness(turned.structure)) == \
        [-0.77] * 4 + [0.77] * 4


# ------------------------------------------------ Ni3(HITP)2

@pytest.fixture(scope="module")
def nihitp(tmp_path_factory, catalog):
    """Ni3(HITP)2 on **hcb**, stacked at the crystal's own c."""
    folder = tmp_path_factory.mktemp("nihitp")
    return build(BuildRequest.parse("hcb", HITP, NICKEL,
                                    spacing=str(HITP_SPACING)),
                 folder, catalog)


@needs_database
@needs_builder
@needs_library
@needs_layers
def test_nihitp_builds_with_the_cell_the_crystal_has(nihitp):
    """The crystal's formula, its hexagonal cell, its c to the digit,
    and **hcb** read back off the bonds.

    *a* is not the crystal's, and the difference is pinned rather
    than tolerated because it has one cause and the cause is known.
    Ni-N comes out at the crystal's 1.838 A; the N-C bond at the cut
    comes out at **1.606 A against 1.294**, because a connection
    point is 0.75 A from the centroid of the atoms it stands for and
    so two ends meet with their centroids 1.5 A apart -- where a
    chelate's, whose bonds lean inwards, are 1.16 A.  Two joints on
    every path from one triphenylene to the next make that the
    **+5.5 %** on *a*.  A change to the joint geometry moves this
    number and must say why.
    """
    structure = nihitp.structure
    crystal = p1_elements(FORMATS.read(SAMPLES / "NiHITP.cif"))

    assert Counter(site.element for site in structure.sites) == \
        crystal == {"C": 36, "H": 24, "N": 12, "Ni": 3}
    a, b, c, alpha, beta, gamma = structure.lattice.parameters
    assert (round(alpha, 6), round(beta, 6), round(gamma, 6)) == \
        (90.0, 90.0, 120.0)
    assert round(a, 3) == round(b, 3) == 22.731
    # To the 0.001 A PORMAKE's writer puts a cell length in the file.
    assert round(c, 3) == round(HITP_SPACING, 3)
    assert nihitp.net_name == "hcb" and nihitp.net_agrees
    assert round(nihitp.longest_joint, 3) == 1.606


@needs_database
@needs_builder
@needs_library
@needs_layers
def test_every_diimine_end_binds_two_nitrogen(nihitp):
    """Twelve N-C bonds across six joints, one per nitrogen.

    Each arm of a triphenylene is an *o*-diimine: two carbons, one
    connection point, and a nickel's two nitrogens on the other side.
    Six bonds would be PORMAKE's one-per-joint and would leave every
    nickel bound to its linkers through one nitrogen of each pair,
    which nothing afterwards recovers.  Every nitrogen must also end
    up bonded to a carbon of its *own* -- two nitrogens on one carbon
    is a pairing that crossed.
    """
    structure = nihitp.structure
    element = [site.element for site in structure.sites]
    joints = [b for b in structure.bonds if b.kind != TOPOLOGY
              and {element[b.i], element[b.j]} == {"N", "C"}]

    assert nihitp.joints == 12
    assert len(joints) == 12
    nitrogen = [b.i if element[b.i] == "N" else b.j for b in joints]
    carbon = [b.j if element[b.i] == "N" else b.i for b in joints]
    assert sorted(Counter(nitrogen).values()) == [1] * 12
    assert sorted(Counter(carbon).values()) == [1] * 12


@needs_database
@needs_builder
@needs_library
@needs_layers
def test_the_nickel_lands_square_planar_in_the_layer(nihitp):
    """Four nitrogens at 1.84 A, at right angles and straight across,
    all in the plane of the sheet.

    The NiN4H4 block is a two-connected *linker* here, so its angle
    about the axis through its two connection points is the one
    Phase 6 settles; a nickel turned out of the layer would still be
    square planar in itself and would put two of its NH groups into
    the sheet above.  88.2 and 91.8 degrees are the crystal's own
    bite angle, not a distortion of the build.
    """
    structure = nihitp.structure
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    frac = np.array([site.frac for site in structure.sites])
    element = [site.element for site in structure.sites]
    normal = np.cross(matrix[0], matrix[1])
    normal /= np.linalg.norm(normal)

    nickels = [i for i, e in enumerate(element) if e == "Ni"]
    assert len(nickels) == 3
    for ni in nickels:
        offsets = frac - frac[ni]
        arms = (offsets - np.round(offsets)) @ matrix
        near = [j for j, e in enumerate(element) if e == "N"
                and np.linalg.norm(arms[j]) < 2.3]
        assert len(near) == 4
        lengths = np.linalg.norm(arms[near], axis=1)
        # The crystal's 1.838, to what one block cut from a real
        # crystal holds: it is square planar to a few thousandths.
        assert np.allclose(lengths, 1.838, atol=0.003)
        assert np.allclose(arms[near] @ normal, 0.0, atol=1e-4)
        unit = arms[near] / lengths[:, None]
        angles = sorted(round(float(np.degrees(np.arccos(
            np.clip(unit[p] @ unit[q], -1, 1)))), 1)
            for p in range(4) for q in range(p + 1, 4))
        assert np.allclose(angles, [88.2, 88.2, 91.8, 91.8,
                                    180.0, 180.0], atol=0.15)


# ------------------------------------------------ layer nets

@needs_database
@needs_layers
def test_the_three_layer_nets_are_layers_and_pcu_is_not(catalog):
    """Read off the graph, not off the folder: a net whose own
    lattice has rank two and no cycle along *c*.

    ``pcu`` is the other half of the assertion because a spacing is
    refused on a net that is not a layer, and a test that only ever
    asked the question of layers would pass a rule that called
    everything one.
    """
    assert [catalog.topology(n).is_layer
            for n in ("hcb", "sql", "kgm", "pcu", "tbo")] == \
        [True, True, True, False, False]


@needs_database
@needs_builder
@needs_library
@needs_layers
def test_a_layer_net_keeps_the_spacing_it_was_given(tmp_path,
                                                     catalog):
    """The spacing along the normal, the offset in the plane, and
    nothing inside a sheet moved to make room for either.

    PORMAKE's scaler hands back ``hcb`` with *c* = 107 A, because it
    scales the whole cell by one factor chosen for the in-plane
    edges.  What comes out here must be the stacking that was asked
    for: 3.5 A between sheets, each slipped a third of *a* and two
    thirds of *b* over the last -- and the sheet itself atom for atom
    the one the eclipsed build made, because a restack is a
    translation of whole layers and nothing else.
    """
    plain = build(BuildRequest.parse("hcb", HITP, NICKEL),
                  _fresh(tmp_path / "plain"), catalog)
    slipped = build(BuildRequest.parse("hcb", HITP, NICKEL,
                                       spacing="3.5",
                                       offset="1/3, 2/3"),
                    _fresh(tmp_path / "slipped"), catalog)

    assert round(plain.structure.lattice.parameters[2], 6) == \
        DEFAULT_SPACING
    matrix = np.asarray(slipped.structure.lattice.matrix, dtype=float)
    normal = np.cross(matrix[0], matrix[1])
    normal /= np.linalg.norm(normal)
    # The file holds a cell to 0.001 A and 0.001 degrees, and a
    # slipped cell is written as lengths and angles -- so this is as
    # close as the stacking can be read back, not as it was made.
    assert round(float(matrix[2] @ normal), 3) == 3.5
    in_plane = matrix[2] - (matrix[2] @ normal) * normal
    assert np.allclose(in_plane, matrix[0] / 3 + 2 * matrix[1] / 3,
                       atol=2e-3)
    assert np.allclose(
        np.asarray(plain.structure.lattice.matrix)[:2], matrix[:2])

    assert _in_plane(plain.structure) == _in_plane(slipped.structure)
    assert slipped.net_name == "hcb" and slipped.joints == 12


@needs_database
@needs_builder
@needs_library
@needs_layers
def test_a_layer_net_repeated_along_c_is_that_many_sheets(tmp_path,
                                                          catalog):
    """``1x1x2`` is two sheets to a cell, each the spacing from the
    next -- not one sheet in a cell twice as tall."""
    stacked = build(BuildRequest.parse("hcb", HITP, NICKEL, "1x1x2",
                                       spacing="3.3"),
                    _fresh(tmp_path / "two"), catalog)

    structure = stacked.structure
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    assert stacked.n_atoms == 150
    assert round(structure.lattice.parameters[2], 6) == 6.6
    heights = (np.array([s.frac for s in structure.sites])
               @ matrix)[:, 2] % 6.6
    assert sorted(set(np.round(heights - heights.min(), 2))) == \
        [0.0, 3.3]


@needs_database
def test_a_spacing_on_a_three_periodic_net_is_refused(tmp_path,
                                                      catalog):
    """Ignoring it would build exactly the framework somebody asked
    for with one of their numbers quietly dropped -- the kind of
    silence a command-line run never notices."""
    for extra in ({"spacing": "3.4"}, {"offset": "0.5, 0"}):
        with pytest.raises(MofError, match="no layers to stack"):
            build(BuildRequest.parse("pcu", "N59", "E32", **extra),
                  tmp_path, catalog)


# ------------------------------------------------ helpers

def p1_elements(structure) -> Counter:
    """What a symmetric structure's full cell is made of."""
    from xtal.core import p1

    return Counter(p1.expand(structure).elements)


def _in_plane(structure) -> list:
    """Each atom's position in its sheet, and its height off it.

    In Cartesian terms along *a*, *b* and the normal, so that two
    cells stacked differently compare equal when the sheet is the
    same sheet.
    """
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    normal = np.cross(matrix[0], matrix[1])
    normal /= np.linalg.norm(normal)
    frac = np.array([site.frac for site in structure.sites])
    cart = frac @ matrix
    height = cart @ normal
    layer = np.round(height / (matrix[2] @ normal))
    flat = cart - np.outer(layer, matrix[2])
    ab = flat @ np.linalg.pinv(matrix[:2])
    ab -= np.floor(ab + 1e-6)
    return [(site.element, round(float(x), 3), round(float(y), 3),
             round(float(z), 3)) for site, (x, y), z
            in zip(structure.sites, ab, flat @ normal, strict=True)]


# ------------------------------------------------ helpers (MFU-4l)

def _fresh(path):
    """A directory for one build's CIF, made rather than assumed."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _handedness(structure) -> list[float]:
    """The signed volume of each Zn5 cluster's four zinc directions.

    The central zinc is the one with four zincs around it: 3.64 A to
    each of the peripheral four, where those are 5.95 A from one
    another, so any cutoff between the two finds the same clusters.

    The directions are put in a canonical order before the
    determinant is taken -- sorted on their rounded coordinates --
    because a signed volume is otherwise a fact about the order the
    atoms happened to be written in.  Under one order the two
    tetrahedra of a cube are mirror images and come back with
    opposite signs, which is exactly the thing being counted.
    """
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    zinc = [i for i, s in enumerate(structure.sites)
            if s.element == "Zn"]
    frac = np.array([structure.sites[i].frac for i in zinc])

    def offset(a, b):
        delta = frac[b] - frac[a]
        return (delta - np.round(delta)) @ matrix

    out = []
    for a in range(len(zinc)):
        near = [b for b in range(len(zinc))
                if b != a and np.linalg.norm(offset(a, b)) < 4.5]
        if len(near) != 4:
            continue
        arms = np.array([offset(a, b) for b in near])
        arms /= np.linalg.norm(arms, axis=1)[:, None]
        arms = arms[np.lexsort(np.round(arms, 3).T[::-1])]
        out.append(round(float(np.linalg.det(arms[:3])), 2))
    return out
