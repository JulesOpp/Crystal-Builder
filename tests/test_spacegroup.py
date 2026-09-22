"""Space groups: identity, settings, and operations."""

import numpy as np
import pytest

from xtal.core.spacegroup import SpaceGroup

# (spec, number, order)  -- order is the general-position multiplicity
GROUPS = [
    ("P 1", 1, 1),
    ("P -1", 2, 2),
    ("P21/c", 14, 4),
    ("C2/c", 15, 8),
    ("Pnma", 62, 8),
    ("R-3c", 167, 36),        # hexagonal axes: 12 ops x 3 centrings
    ("Fm-3m", 225, 192),
]


@pytest.mark.parametrize("spec,number,order", GROUPS)
def test_lookup_by_name(spec, number, order):
    sg = SpaceGroup.from_name(spec)
    assert sg.number == number
    assert sg.order == order
    assert len(sg.operations) == order
    assert len(sg.triplets) == order


def test_lookup_by_number_name_and_hall_agree():
    by_name = SpaceGroup.from_name("P21/c")
    assert by_name.hall == "-P 2ybc"
    assert SpaceGroup.from_hall("-P 2ybc") == by_name
    assert SpaceGroup.from_number(14) == by_name
    assert SpaceGroup.from_any(14) == by_name
    assert SpaceGroup.from_any(by_name) is by_name


def test_from_any_accepts_none_as_p1():
    assert SpaceGroup.from_any(None).is_p1


def test_settings_of_the_same_number_are_different_groups():
    origin1 = SpaceGroup.from_name("Fd-3m:1")
    origin2 = SpaceGroup.from_name("Fd-3m:2")
    assert origin1.number == origin2.number == 227
    assert origin1 != origin2                 # this is the whole point
    assert origin1.hall != origin2.hall
    assert set(origin1.triplets) != set(origin2.triplets)
    assert origin2.setting == "2"


def test_rhombohedral_and_hexagonal_axes_differ():
    hexagonal = SpaceGroup.from_name("R-3c:H")
    rhombo = SpaceGroup.from_name("R-3c:R")
    assert hexagonal.order == 36 and rhombo.order == 12
    assert hexagonal.centring == "R" and rhombo.centring == "P"


def test_identity_is_first_and_operations_are_read_only():
    sg = SpaceGroup.from_name("P21/c")
    assert sg.operations[0].is_identity()
    assert sg.triplets[0] == "x,y,z"
    with pytest.raises(ValueError):
        sg.operations[1].rot[0, 0] = 5.0


def test_operations_of_p21_over_c():
    sg = SpaceGroup.from_name("P21/c")
    assert sg.triplets == ["x,y,z", "-x,y+1/2,-z+1/2", "-x,-y,-z",
                           "x,-y+1/2,z+1/2"]
    got = sg.apply_all([0.1, 0.2, 0.3])
    assert np.allclose(got, [[0.1, 0.2, 0.3], [-0.1, 0.7, 0.2],
                             [-0.1, -0.2, -0.3], [0.1, 0.3, 0.8]])


@pytest.mark.parametrize("spec,_n,_o", GROUPS)
def test_operations_form_a_closed_group(spec, _n, _o):
    """Composing any two operations lands on another operation of the
    group, modulo a lattice translation."""
    ops = SpaceGroup.from_name(spec).operations
    known = {(tuple(op.rot.ravel()),
              tuple(np.round(np.mod(op.trans, 1.0), 6))) for op in ops}
    for a in ops:
        for b in ops:
            rot = a.rot @ b.rot
            trans = np.mod(a.rot @ b.trans + a.trans, 1.0)
            key = (tuple(rot.ravel()), tuple(np.round(trans, 6)))
            assert key in known, f"{a.triplet} * {b.triplet} escaped"


def test_group_flags():
    assert SpaceGroup.p1().is_p1
    assert not SpaceGroup.from_name("P21/c").is_p1
    assert SpaceGroup.from_name("P21/c").is_centrosymmetric
    assert not SpaceGroup.from_name("P212121").is_centrosymmetric
    assert SpaceGroup.from_name("P212121").is_chiral
    assert SpaceGroup.from_name("Fm-3m").centring == "F"
    assert SpaceGroup.from_name("Fm-3m").crystal_system == "cubic"


def test_dict_round_trip_preserves_the_setting():
    for spec in ("Fd-3m:1", "Fd-3m:2", "R-3c:R", "P21/c"):
        sg = SpaceGroup.from_name(spec)
        assert SpaceGroup.from_dict(sg.to_dict()) == sg


def test_bad_lookups_raise():
    with pytest.raises(ValueError):
        SpaceGroup.from_name("P 42/nonsense")
    with pytest.raises(ValueError):
        SpaceGroup.from_number(231)
    with pytest.raises(ValueError):
        SpaceGroup.from_number(0)
    with pytest.raises(ValueError):
        SpaceGroup.from_hall("not a hall symbol")
    with pytest.raises(TypeError):
        SpaceGroup.from_any(3.7)


def test_every_operation_undoes_to_a_lattice_translation():
    """``inverse_of`` over every setting gemmi knows: the op it names
    composed with the op it inverts is the identity plus the integer
    shift it reports.  A wrong entry names a bond from its far end as
    a different bond, and every stored bond then counts twice."""
    from xtal.core.spacegroup import table
    for sg in table():
        ops = sg.operations
        for k, op in enumerate(ops):
            m, shift = sg.inverse_of(k)
            back = ops[m]
            assert np.array_equal(back.rot @ op.rot, np.eye(3)), sg.hm
            assert np.allclose(back.rot @ op.trans + back.trans, shift,
                               atol=1e-9), sg.hm


def test_a_second_instance_of_a_group_reuses_its_inverse_table():
    """The table belongs to the group and not the object: a fresh
    ``SpaceGroup`` is made on every CIF read and Reduce to P1, and
    rebuilding Fm-3m's table each time was 0.2 s of every one."""
    first = SpaceGroup.from_number(225)
    first.inverse_of(0)
    second = SpaceGroup.from_hall(first.hall)
    assert second is not first
    assert second.inverse_of(5)[1] is first.inverse_of(5)[1]


def test_an_inverse_shift_cannot_be_edited_by_its_caller():
    """The shift is shared by every caller of the group, so one caller
    writing into it would corrupt every later bond reversal."""
    _m, shift = SpaceGroup.from_name("Fm-3m").inverse_of(7)
    with pytest.raises(ValueError):
        shift[0] = 3
