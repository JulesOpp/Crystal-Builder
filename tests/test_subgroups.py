"""Descending to a maximal subgroup.

Two halves are tested separately because they fail separately: the
*enumeration* is a group-theory question with a known answer, and the
*naming* is the part that was expensive and is the reason the feature
is usable at all.

The counts below are not self-consistency checks -- they are what the
four fixture structures' groups actually have, and a change in any of
them means the enumeration has started finding subgroups that are not
maximal or missing ones that are.
"""

import numpy as np
import pytest

from xtal.core import p1, subgroups
from xtal.core.spacegroup import SpaceGroup

# group -> (maximal subgroups counted individually, and the indices
#           they come at).  Conjugate subgroups are counted separately
#           here: this is the enumeration's own oracle and it has to
#           keep finding every one of them, whether or not the list
#           shown to a user collapses them.
EXPECTED = {
    "P4_2/mnm": (7, [2] * 7),
    "P3221": (7, [2, 2, 2, 3, 3, 3, 3]),
    "Pa-3": (6, [2, 3, 4, 4, 4, 4]),
    "Fm-3m": (18, [2, 2, 2, 3, 3, 3] + [4] * 12),
}

# ... and how many rows those become once conjugates share one.
EXPECTED_CLASSES = {
    "P4_2/mnm": 7,          # all of them normal: index 2 always is
    "P3221": 5,             # P3_2, the three C2 as one, and three
                            # more that double or triple the cell
    "Pa-3": 3,              # P2_13, Pbca, and the four R-3 as one
    "Fm-3m": 7,             # three at index 2, one I4/mmm, one R-3m,
                            # and the two that drop the F centring
}


@pytest.mark.parametrize("name,expected", list(EXPECTED.items()))
def test_maximal_subgroup_counts(name, expected):
    count, indices = expected
    found = subgroups.maximal_subgroups(name)
    assert sum(s.n_conjugates for s in found) == count
    assert sorted(i for s in found for i in [s.index] * s.n_conjugates) \
        == indices


@pytest.mark.parametrize("name,classes",
                         list(EXPECTED_CLASSES.items()))
def test_conjugate_subgroups_share_one_row(name, classes):
    """Fm-3m's three tetragonal subgroups keep three different cubic
    axes and are carried onto each other by the parent's own three-fold
    -- so they are one choice, not three."""
    found = subgroups.maximal_subgroups(name)
    assert len(found) == classes


def _distance_fingerprint(structure):
    """Every minimum-image interatomic distance, sorted.

    A fingerprint that does not care where the origin is or which way
    the axes point, which is exactly what has to be ignored when asking
    whether two descents gave the same crystal.
    """
    import numpy as np

    cell = p1.expand(structure)
    frac = cell.frac
    out = []
    for i in range(cell.n_atoms):
        d = frac[i + 1:] - frac[i]
        d -= np.round(d)
        out.extend(np.linalg.norm(d @ structure.lattice.matrix, axis=1))
    return np.sort(np.array(out))


def test_conjugates_give_the_same_crystal(quartz):
    """The justification for collapsing them, checked rather than
    asserted.

    Quartz's three maximal C2 subgroups are conjugate, and descending
    to any of them gives the same group, the same cell and a congruent
    crystal.  It does *not* give the same coordinate list: the three
    results are related by an operation of the parent, so they sit at
    different origins and on different axes within the same cell -- an
    equivalent setting, not an identical one.  That is why the test is
    on a fingerprint that ignores the setting rather than on the
    coordinates, and it is the honest form of the claim the dialog
    makes when it shows one row instead of three.

    Reaches into the enumeration for the conjugates the public list no
    longer shows, because what is being tested is exactly the claim
    that not showing them costs nothing.
    """
    import numpy as np

    group = quartz.space_group
    reps, centrings = subgroups._reduced(group)
    table = subgroups._multiplication_table(reps, centrings)
    lattice = subgroups._probe_lattice(group)
    everything = subgroups._all_subgroups(reps, table)
    maximal = {h for h in everything
               if not any(h < k for k in everything)}

    twofolds = [h for h in maximal if len(h) == 2]
    assert len(twofolds) == 3               # the conjugate C2 class

    results = []
    for indices in twofolds:
        ops = subgroups._ops_from_full(indices, reps, centrings)
        child_group, p_matrix, p_shift = subgroups._name(lattice, ops)
        basis = subgroups._tidy(np.linalg.inv(p_matrix).T)
        shift = np.mod(subgroups._tidy(
            -np.linalg.solve(p_matrix, p_shift)), 1.0)
        sub = subgroups.Subgroup(
            index=len(reps) // len(indices),
            ops=subgroups._to_symops(ops), group=child_group,
            basis=basis, origin_shift=subgroups._tidy(shift))
        child, report = subgroups.descend(quartz, sub)
        assert report.ok
        results.append(child)

    first = results[0]
    reference = _distance_fingerprint(first)
    for other in results[1:]:
        assert other.space_group == first.space_group
        assert other.n_sites == first.n_sites
        assert np.allclose(other.lattice.parameters,
                           first.lattice.parameters, atol=1e-9)
        assert np.allclose(_distance_fingerprint(other), reference,
                           atol=1e-9)
        # ... and each still has the symmetry it was descended from,
        # because nothing moved.
        from xtal.core import symmetry
        assert (symmetry.detect(other, 1e-5).international
                == symmetry.detect(first, 1e-5).international)


def test_every_subgroup_is_offered_not_only_the_maximal_ones():
    """An ordering model usually knows the group it is heading for, and
    reaching it only through three dialogs is the subgroup lattice done
    by hand."""
    everything = subgroups.subgroups_of("Fm-3m")
    maximal = subgroups.maximal_subgroups("Fm-3m")
    assert len(everything) == 237
    assert len(maximal) == 7
    assert all(s.maximal for s in maximal)
    assert {s.symbol for s in maximal} <= {s.symbol for s in everything}
    # the deepest descent of all: drop every rotation *and* the whole
    # centring, which is P1 in the parent's own cubic cell
    assert min(s.index for s in everything) == 2
    assert max(s.index for s in everything) == 192


def test_a_non_maximal_subgroup_still_descends(quartz):
    """Descending straight to a non-maximal group has to give what
    descending through the groups between would."""
    everything = subgroups.subgroups_of(quartz.space_group)
    deep = [s for s in everything if not s.maximal]
    assert deep
    for sub in deep:
        child, report = subgroups.descend(quartz, sub)
        assert report.ok, f"{sub}: {report.message}"
        assert (p1.expand(child).n_atoms
                == round(p1.expand(quartz).n_atoms * sub.volume_ratio))


@pytest.mark.parametrize("name", list(EXPECTED))
def test_every_subgroup_is_named(name):
    """The naming is the hard half.  Asking gemmi to recognise the raw
    operations names 11 of these 27; going through a probe crystal
    names all of them, and an unnamed subgroup is one nobody can
    choose from."""
    for sub in subgroups.maximal_subgroups(name):
        assert sub.named, f"{name}: index {sub.index} came out unnamed"


@pytest.mark.parametrize("name", list(EXPECTED))
def test_subgroup_order_matches_its_index(name):
    parent = SpaceGroup.from_name(name)
    for sub in subgroups.maximal_subgroups(name):
        if sub.sublattice is None:
            assert len(sub.ops) * sub.index == parent.order
        else:
            # Counted in the larger cell instead, where the parent has
            # its own operations again for every translation it is
            # about to lose.  The point group is kept whole, so what is
            # left of the index is all translations.
            assert sub.t_index == 1
            assert sub.k_index == sub.index
            assert len(sub.ops) * len(_centrings_of(parent)) \
                == parent.order
        # The name and the transformation have to agree.  A group's
        # operation count belongs to its *conventional* cell, so the
        # count found in the cell the operations are held in only
        # matches after the change of cell is allowed for: rutile's
        # Cmmm has eight operations in rutile's cell and sixteen in the
        # doubled one it is named in.
        assert sub.group.order == pytest.approx(
            len(sub.ops) * sub.cell_ratio)


def test_subgroups_are_proper_subsets_of_the_parent():
    parent = SpaceGroup.from_name("P4_2/mnm")
    parent_ops = {op.triplet for op in parent.operations}
    for sub in subgroups.maximal_subgroups(parent):
        if sub.sublattice is not None:
            continue          # written in its own cell, not this one
        found = {op.triplet for op in sub.ops}
        assert found < parent_ops


def test_p1_has_no_subgroups():
    assert subgroups.maximal_subgroups("P1") == []


def test_subgroups_are_closed_under_composition():
    for sub in subgroups.maximal_subgroups("Pa-3"):
        ops = list(sub.ops)
        keys = {_key(op.rot, op.trans) for op in ops}
        for a in ops:
            for b in ops:
                rot = a.rot @ b.rot
                trans = a.rot @ b.trans + a.trans
                assert _key(rot, trans) in keys


def _key(rot, trans):
    return (tuple(np.round(np.asarray(rot).reshape(9)).astype(int)),
            tuple(np.round(np.mod(trans, 1.0) * 24).astype(int) % 24))


# ======================================================================
#  GIVING UP THE CENTRING
# ======================================================================
#
#  The klassengleiche half, in the same cell.  A subgroup here keeps
#  rotations and drops translations rather than the other way round,
#  and the translations it can drop are the centring ones -- which is
#  why every one of these tests is about a centred group and why the
#  primitive fixtures must come out of this change untouched.


@pytest.mark.parametrize("name", ["P4_2/mnm", "P3221", "Pa-3"])
def test_a_primitive_group_has_nothing_to_give_up_but_rotations(name):
    """A same-cell klassengleiche descent gives up part of the
    centring, and a primitive group has no centring to give up.  Its
    list is therefore exactly the list it always was, which is the
    guard that says the reduction is still in place."""
    found = [s for s in subgroups.subgroups_of(name)
             if s.sublattice is None]
    assert found
    assert all(s.k_index == 1 and s.kind == "t" for s in found)


def test_fm3m_contains_pm3m_in_the_same_cell():
    """The descent that was missing.  Index 4, not one rotation lost,
    the whole F centring given up, and no cell transformation at all --
    which is what makes it cost nothing to apply."""
    pm3m = next(s for s in subgroups.maximal_subgroups("Fm-3m")
                if s.symbol == "Pm-3m")
    assert (pm3m.index, pm3m.k_index, pm3m.t_index) == (4, 4, 1)
    assert pm3m.kind == "k"
    assert pm3m.keeps_the_cell
    assert subgroups.basis_description(pm3m) == "same axes, same origin"


def test_fm3m_has_exactly_two_maximal_klassengleiche_subgroups():
    """International Tables gives Fm-3m two of them, Pm-3m and Pn-3m,
    and not the other two primitive m-3m groups: Pm-3n and Pn-3n need
    glides a symmorphic parent does not contain.  Four here would mean
    the lift is being offered without being closed."""
    maximal = subgroups.maximal_subgroups("Fm-3m")
    lost_centring = [s for s in maximal if s.kind == "k"]
    assert {s.symbol for s in lost_centring} == {"Pm-3m", "Pn-3m"}
    assert all(s.index == 4 for s in lost_centring)


def test_a_lifted_subgroup_is_closed_under_composition():
    """A klassengleiche subgroup is assembled by choosing, for each
    generator of the point group, which of the centring translations to
    keep it with.  Most choices do not close, and one offered without
    that check is a list of operations rather than a symmetry."""
    for sub in subgroups.maximal_subgroups("Fm-3m"):
        ops = list(sub.ops)
        keys = {_key(op.rot, op.trans) for op in ops}
        for a in ops:
            for b in ops:
                assert _key(a.rot @ b.rot,
                            a.rot @ b.trans + a.trans) in keys


def test_the_index_is_the_two_halves_multiplied():
    """``index`` is the whole descent and ``k_index`` the part of it
    that is translations.  Both are shown, and a row whose numbers do
    not multiply out is a row nobody can read."""
    for sub in subgroups.subgroups_of("Fm-3m"):
        assert sub.t_index * sub.k_index == sub.index
        assert sub.kind == ("t" if sub.k_index == 1 else
                            "k" if sub.t_index == 1 else "t + k")


def test_rock_salt_splits_only_once_the_centring_goes(halite):
    """Halite was the one fixture where no descent split anything, and
    the reason was that the half of the subgroup lattice that splits it
    was not offered.  Fm-3m to Pm-3m puts sodium on 1a and 3c and
    chlorine on 1b and 3d, which is the cation-ordering model."""
    for sub in subgroups.maximal_subgroups(halite.space_group):
        if sub.kind == "t":
            assert not subgroups.describe_split(halite, sub).splits

    split = subgroups.describe_split(halite, _find(halite, "Pm-3m"))
    assert (split.before, split.after) == (2, 4)
    assert [pieces for _l, _e, _m, pieces in split.per_site] == [2, 2]


def test_a_lost_centring_moves_no_atom(halite):
    """The cheapest descent there is: same lattice, same coordinates,
    fewer operations.  An atom that moves means the lift was named in a
    setting it is not actually in."""
    pm3m = _find(halite, "Pm-3m")
    child, report = subgroups.descend(halite, pm3m)
    assert report.ok
    assert child.lattice.almost_equal(halite.lattice)
    assert np.allclose(np.sort(p1.expand(halite).frac, axis=0),
                       np.sort(p1.expand(child).frac, axis=0))


def test_the_deepest_descent_of_a_centred_group_keeps_its_cell(halite):
    """Dropping every rotation but keeping the centring is P1 in the
    *primitive* cell, with two atoms.  Dropping the centring as well is
    P1 in the cubic cell the structure was written in, with all eight
    atoms independent -- and it is the deeper of the two."""
    found = subgroups.subgroups_of(halite.space_group)
    deepest = max(found, key=lambda s: s.index)
    assert (deepest.symbol, deepest.index, deepest.k_index) == \
        ("P1", 192, 4)
    child, report = subgroups.descend(halite, deepest)
    assert report.ok
    assert child.n_sites == 8
    assert child.lattice.almost_equal(halite.lattice)


def test_a_descent_in_the_same_cell_still_has_the_parents_symmetry(
        halite):
    """Nothing moved, so Find symmetry must still answer Fm-3m.  This
    is the strongest check available that a lift closed into a real
    group: a set of operations that merely looks like one produces a
    child whose expansion is not the crystal."""
    from xtal.core import symmetry
    for sub in subgroups.maximal_subgroups(halite.space_group):
        child, report = subgroups.descend(halite, sub)
        assert report.ok
        assert symmetry.detect(child).space_group.short_name == "Fm-3m"


# ======================================================================
#  A LARGER CELL
# ======================================================================
#
#  The klassengleiche subgroups that do not fit in the parent's cell.
#  These are the superstructures, and the counts below are what
#  International Tables lists for the groups they name.


def test_pm3m_doubles_its_cell_the_way_the_tables_say():
    """P m -3 m's maximal subgroups on a larger cell: Fm-3m and Fm-3c
    at index 2 and Im-3m at index 4, all on the doubled cubic cell.
    This is the one place the answers can be checked against a table
    rather than against the code that produced them."""
    bigger = [s for s in subgroups.maximal_subgroups("Pm-3m")
              if s.enlarges_the_lattice]
    assert {(s.symbol, s.index) for s in bigger} == {
        ("Fm-3m", 2), ("Fm-3c", 2), ("Im-3m", 4)}
    for sub in bigger:
        assert subgroups.basis_description(sub).startswith(
            "a' = 2a, b' = 2b, c' = 2c")
        assert sub.volume_ratio == pytest.approx(8.0)


def test_p4mmm_gives_the_tables_eight_superstructures():
    """P4/mmm's are the textbook list: the c-doubling ones, the
    root-two ones in the plane, and the two body-centred ones that do
    both."""
    bigger = {s.symbol for s in subgroups.maximal_subgroups("P4/mmm")
              if s.enlarges_the_lattice}
    assert bigger == {"P4/mcc", "P4/nbm", "P4/mbm", "P4/nmm",
                      "P42/mmc", "P42/mcm", "I4/mmm", "I4/mcm"}


def test_the_isomorphic_superstructures_are_not_offered():
    """A subgroup of the same group on a larger cell exists at every
    prime index for most lattices, so the family is infinite and
    cannot be a list.  P1 is the whole family and nothing else, which
    is why P1 still has no subgroups at all."""
    assert subgroups.subgroups_of("P1") == []
    for name in ("P3221", "Pm-3m", "P4/mmm", "Cmcm"):
        parent = SpaceGroup.from_name(name)
        for sub in subgroups.subgroups_of(name):
            if sub.enlarges_the_lattice:
                assert sub.group.number != parent.number


def test_a_superstructure_keeps_the_whole_point_group():
    """Enlarging the cell is the klassengleiche half in its pure form:
    every rotation survives and the translations are what is lost.  A
    row here with a t index above one would mean the two kinds had been
    mixed up in one pass."""
    for name in ("P3221", "Pm-3m", "P4/mmm", "P6_3/mmc"):
        for sub in subgroups.subgroups_of(name):
            if sub.enlarges_the_lattice:
                assert sub.t_index == 1
                assert sub.k_index == sub.index
                assert sub.kind == "k"
                assert not sub.keeps_the_cell


def test_a_superstructure_descent_conserves_the_crystal():
    """The cell grows by the index and so does the atom count, every
    atom keeps its place, and the symmetry that is still there is the
    parent's -- because nothing moved.  That round trip is the only
    check here that does not come from the code being tested."""
    from xtal import Lattice, Structure
    from xtal.core import properties, symmetry

    perovskite = Structure.from_arrays(
        Lattice.cubic(3.905), ["Sr", "Ti", "O"],
        [[0, 0, 0], [.5, .5, .5], [.5, .5, 0]], space_group="Pm-3m")
    before = p1.expand(perovskite).n_atoms
    bigger = [s for s in subgroups.subgroups_of("Pm-3m")
              if s.enlarges_the_lattice]
    assert bigger
    for sub in bigger:
        child, report = subgroups.descend(perovskite, sub)
        assert report.ok, f"{sub}: {report.message}"
        assert p1.expand(child).n_atoms == round(
            before * sub.volume_ratio)
        assert properties.density(child) == pytest.approx(
            properties.density(perovskite))
        assert symmetry.detect(child).space_group.short_name == "Pm-3m"


def test_ordering_the_b_site_of_a_perovskite():
    """What the half is for.  SrTiO3 in Pm-3m has one titanium; on the
    doubled cell in Fm-3m it has two, which is the rock-salt ordering
    a double perovskite needs and which no descent in the parent's own
    cell can produce."""
    from xtal import Lattice, Structure

    perovskite = Structure.from_arrays(
        Lattice.cubic(3.905), ["Sr", "Ti", "O"],
        [[0, 0, 0], [.5, .5, .5], [.5, .5, 0]], space_group="Pm-3m")
    ordering = [s for s in subgroups.subgroups_of("Pm-3m")
                if s.symbol == "Fm-3m"]
    splits = [subgroups.describe_split(perovskite, s) for s in ordering]
    assert any(pieces > 1 for split in splits
               for label, _el, _mult, pieces in split.per_site
               if label == "Ti")
    child, report = subgroups.descend(perovskite, ordering[0])
    assert report.ok
    assert child.lattice.lengths == pytest.approx((7.81, 7.81, 7.81))


def test_one_atom_of_the_parent_is_several_of_a_larger_child():
    """The split count has to be worked out over the *whole* child
    cell.  A parent atom of multiplicity one is eight atoms of a cell
    eight times the size, and matching only the copy the parent cell
    holds finds one of them and reports that nothing split -- which
    made every superstructure look like it did nothing."""
    from xtal import Lattice, Structure

    perovskite = Structure.from_arrays(
        Lattice.cubic(3.905), ["Sr", "Ti", "O"],
        [[0, 0, 0], [.5, .5, .5], [.5, .5, 0]], space_group="Pm-3m")
    for sub in subgroups.subgroups_of("Pm-3m"):
        if not sub.enlarges_the_lattice:
            continue
        split = subgroups.describe_split(perovskite, sub)
        assert split.after == sum(
            1 for _l, _e, _m, pieces in split.per_site for _ in
            range(pieces)), subgroups.basis_description(sub)


# ======================================================================
#  WHAT A DESCENT DOES TO A STRUCTURE
# ======================================================================

def test_quartz_splits_its_oxygen(quartz):
    """The case the feature exists for: quartz's one oxygen of
    multiplicity 6 becomes two independent oxygens of multiplicity 3
    in P3_2, and no atom moves."""
    sub = _find(quartz, "P32")
    split = subgroups.describe_split(quartz, sub)
    assert split.before == 2 and split.after == 3
    assert split.splits
    child, report = subgroups.descend(quartz, sub)
    assert report.ok
    assert child.space_group.short_name == "P32"
    assert p1.expand(child).n_atoms == p1.expand(quartz).n_atoms


def test_rutile_only_splits_under_the_one_gemmi_could_not_name(rutile):
    """Six of rutile's seven maximal subgroups leave both sites whole.
    The seventh -- Cmmm, in a basis gemmi cannot name from the
    operations alone -- splits both, which is the argument for solving
    the naming rather than shipping the easy subgroups."""
    splitting = [s for s in subgroups.maximal_subgroups(rutile.space_group)
                 if subgroups.describe_split(rutile, s).splits]
    assert len(splitting) == 1
    assert splitting[0].group.short_name == "Cmmm"
    assert not splitting[0].keeps_the_cell


def test_a_descent_never_loses_an_atom(rutile, quartz, halite,
                                       dry_ice):
    """The whole-cell contents are conserved: what changes is how many
    of them are independent, and -- when the subgroup's conventional
    cell is a different multiple of the primitive one -- how many
    cells' worth the new cell holds."""
    for structure in (rutile, quartz, halite, dry_ice):
        before = p1.expand(structure).n_atoms
        for sub in subgroups.maximal_subgroups(structure.space_group):
            child, report = subgroups.descend(structure, sub)
            assert report.ok, f"{sub}: {report.message}"
            assert (p1.expand(child).n_atoms
                    == round(before * sub.volume_ratio))


def test_a_descent_that_keeps_the_cell_moves_no_atom(dry_ice):
    sub = _find(dry_ice, "P213")
    assert sub.keeps_the_cell
    child, _report = subgroups.descend(dry_ice, sub)
    assert np.allclose(child.lattice.matrix, dry_ice.lattice.matrix)
    before = np.sort(p1.expand(dry_ice).frac, axis=0)
    after = np.sort(p1.expand(child).frac, axis=0)
    assert np.allclose(before, after, atol=1e-6)


def test_a_new_setting_keeps_the_crystal(dry_ice):
    """The rhombohedral descents re-express the cubic cell on
    hexagonal axes.  The axes move, the crystal does not -- so every
    atom of the new cell lands on an atom of the old one once the
    difference between the two cells is divided out."""
    sub = next(s for s in subgroups.maximal_subgroups(dry_ice.space_group)
               if s.volume_ratio > 1.5)
    child, report = subgroups.descend(dry_ice, sub)
    assert report.ok
    assert child.lattice.volume == pytest.approx(
        dry_ice.lattice.volume * sub.volume_ratio, rel=1e-9)

    parent_cell = p1.expand(dry_ice)
    # child coordinates back in the parent's basis, wrapped into the
    # parent's cell: the same points, or the descent moved an atom.
    back = np.mod(p1.expand(child).frac @ sub.basis + sub.origin_shift,
                  1.0)
    for point in back:
        d = parent_cell.frac - point
        d -= np.round(d)
        assert np.linalg.norm(d @ dry_ice.lattice.matrix,
                              axis=1).min() < 1e-6


def test_a_descent_leaves_the_symmetry_that_is_actually_there(quartz):
    """Descending changes which operations are *enforced*, not where
    the atoms are.  Nothing has moved yet, so the coordinates still
    have the parent's full symmetry and spglib still finds it -- which
    is the difference between this and an edit."""
    sub = _find(quartz, "P32")
    child, _report = subgroups.descend(quartz, sub)
    from xtal.core import symmetry
    assert symmetry.detect(child, 1e-5).international == "P3_221"


def test_descending_is_undoable_through_a_command(quartz):
    from xtal.commands.symmetry import DescendToSubgroup
    sub = _find(quartz, "P32")
    command = DescendToSubgroup(sub)
    new, report = command.preview(quartz)
    assert report.ok
    assert "P3221 -> P32" in report.message
    assert new.space_group.short_name == "P32"
    # the preview is the very thing that gets applied
    assert command.preview(quartz)[0] is new


def test_an_unnamed_subgroup_refuses_rather_than_guessing(quartz):
    sub = _find(quartz, "P32")
    nameless = subgroups.Subgroup(
        index=sub.index, ops=sub.ops, group=None,
        basis=sub.basis, origin_shift=sub.origin_shift)
    assert not nameless.named
    with pytest.raises(ValueError, match="no name"):
        subgroups.descend(quartz, nameless)


def test_a_row_says_how_many_subgroups_it_stands_for():
    """Collapsing conjugates must not hide them: the count is what says
    the orientation was the parent's choice and not a missing row."""
    tetragonal = [s for s in subgroups.maximal_subgroups("Fm-3m")
                  if s.group.number == 139]
    assert len(tetragonal) == 1
    assert tetragonal[0].n_conjugates == 3
    rhombohedral = [s for s in subgroups.maximal_subgroups("Fm-3m")
                    if s.group.number == 166]
    assert len(rhombohedral) == 1
    assert rhombohedral[0].n_conjugates == 4


def test_distinct_rows_are_distinguishable():
    """Whatever survives the collapsing has to be tellable apart: same
    symbol, same index, different axes."""
    rows = subgroups.subgroups_of("Fm-3m")
    described = {(s.symbol, s.index,
                  subgroups.basis_description(s)) for s in rows}
    assert len(described) == len(rows)


def _centrings_of(group):
    return subgroups._reduced(group)[1]


def _find(structure, symbol):
    for sub in subgroups.maximal_subgroups(structure.space_group):
        if sub.group is not None and sub.group.short_name == symbol:
            return sub
    raise AssertionError(f"{symbol} is not a maximal subgroup here")
