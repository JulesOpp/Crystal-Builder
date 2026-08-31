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
    "P3221": (4, [2, 3, 3, 3]),
    "Pa-3": (6, [2, 3, 4, 4, 4, 4]),
    "Fm-3m": (10, [2, 2, 2, 3, 3, 3, 4, 4, 4, 4]),
}

# ... and how many rows those become once conjugates share one.
EXPECTED_CLASSES = {
    "P4_2/mnm": 7,          # all of them normal: index 2 always is
    "P3221": 2,             # P3_2, and the three C2 as one
    "Pa-3": 3,              # P2_13, Pbca, and the four R-3 as one
    "Fm-3m": 5,             # three at index 2, one I4/mmm, one R-3m
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
        ops = subgroups._expand(indices, reps, centrings)
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
    assert len(everything) == 32
    assert len(maximal) == 5
    assert all(s.maximal for s in maximal)
    assert {s.symbol for s in maximal} <= {s.symbol for s in everything}
    # the deepest descent of all: keep the lattice, drop every rotation
    assert min(s.index for s in everything) == 2
    assert max(s.index for s in everything) == 48


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
        assert len(sub.ops) * sub.index == parent.order
        # The name and the transformation have to agree.  A group's
        # operation count belongs to its *conventional* cell, so the
        # count found in the parent's cell only matches after the
        # change of cell is allowed for: rutile's Cmmm has eight
        # operations in rutile's cell and sixteen in the doubled one it
        # is named in.
        assert sub.group.order == pytest.approx(
            len(sub.ops) * sub.volume_ratio)


def test_subgroups_are_proper_subsets_of_the_parent():
    parent = SpaceGroup.from_name("P4_2/mnm")
    parent_ops = {op.triplet for op in parent.operations}
    for sub in subgroups.maximal_subgroups(parent):
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


def _find(structure, symbol):
    for sub in subgroups.maximal_subgroups(structure.space_group):
        if sub.group is not None and sub.group.short_name == symbol:
            return sub
    raise AssertionError(f"{symbol} is not a maximal subgroup here")
