"""Fullerene face spirals and the shipped table: xtal.fullerene.spiral
and xtal.fullerene.catalogue."""

import importlib.util
from pathlib import Path

import pytest

from xtal.fullerene import catalogue, spiral
from xtal.fullerene.spiral import FullereneError

C60 = (1, 7, 9, 11, 13, 15, 18, 20, 22, 24, 26, 32)

#: The Atlas of Fullerenes' counts: every isomer to C40, IPR from C60.
ATLAS = {20: 1, 24: 1, 26: 1, 28: 2, 30: 3, 32: 6, 34: 6, 36: 15,
         38: 17, 40: 40, 60: 1, 70: 1, 72: 1, 74: 1, 76: 2, 78: 5,
         80: 7, 82: 9, 84: 24, 86: 19, 88: 35, 90: 46, 92: 86,
         94: 134, 96: 187, 98: 259, 100: 450}


def _script():
    path = Path(__file__).parents[1] / "scripts" / "fullerene_spirals.py"
    spec = importlib.util.spec_from_file_location("fullerene_spirals",
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_cage(n, places):
    rotation = spiral.wind(n, places)
    atoms, bonds = spiral.cage(rotation)
    assert len(atoms) == n
    assert len(bonds) == 3 * n // 2
    degree = [0] * n
    for a, b in bonds:
        degree[a] += 1
        degree[b] += 1
    assert set(degree) == {3}
    assert sorted(len(r) for r in spiral.rings(rotation, atoms)) \
        == [5] * 12 + [6] * (len(rotation) - 12)
    return rotation


def test_c60_winds_into_sixty_atoms_ninety_bonds_and_twelve_pentagons():
    """The spiral everybody quotes builds buckminsterfullerene; a
    windup that joined the wrong faces would give the wrong counts."""
    _check_cage(60, C60)


def test_the_canonical_spiral_of_c60_is_itself_and_its_group_has_120():
    """The count of starts giving the canonical spiral is the order of
    the point group, reflections included: Ih is 120.  An orientation
    that disagreed across an edge would read fewer."""
    assert spiral.canonical(spiral.wind(60, C60)) == (C60, 120)


def test_a_spiral_read_back_from_its_own_start_is_itself():
    """The windup and the reading agree on which way round: one sense
    from faces 0 and 1 retraces the spiral face for face."""
    rotation = spiral.wind(60, C60)
    orders = [spiral.spiral_from(rotation, 0, 1, sense)
              for sense in (1, -1)]
    assert list(range(32)) in orders


@pytest.mark.parametrize("n", [19, 21, 22, 10])
def test_a_size_no_fullerene_has_is_refused(n):
    with pytest.raises(FullereneError, match=f"no fullerene has {n}"):
        spiral.check_size(n)


def test_a_spiral_that_does_not_close_is_refused():
    """C72's spiral misremembered while planning this: it winds into
    a face with more neighbours than sides, and says which."""
    with pytest.raises(FullereneError, match="does not close"):
        spiral.wind(72, (1, 7, 9, 11, 14, 16, 23, 25, 32, 34, 36, 38))


def test_a_spiral_must_name_twelve_places_on_the_cage():
    with pytest.raises(FullereneError, match="twelve"):
        spiral.wind(60, C60[:11])
    with pytest.raises(FullereneError, match="face 1 to 32"):
        spiral.wind(60, C60[:11] + (33,))


def test_the_table_counts_match_the_atlas():
    """Every isomer to C40 and every IPR one from C60 to C100, each
    once: a canonical-spiral check that let a cage through twice, or
    dropped one, changes a count."""
    assert {n: len(catalogue.isomers(n)) for n in catalogue.sizes()} \
        == ATLAS


def test_every_named_group_has_the_order_of_its_isomer():
    """The names are by hand and the orders by count: a name on the
    wrong row of a size disagrees with the order there."""
    for n, named in catalogue.NAMED.items():
        for number, group in named.items():
            row = catalogue.isomer(n, number)
            assert row.order == catalogue.GROUP_ORDER[group], row.name


def test_the_defaults_are_the_cages_people_mean():
    names = {n: catalogue.default(n).name
             for n in (20, 28, 36, 40, 60, 70, 72, 76, 78, 80, 84)}
    assert names == {20: "C20-Ih", 28: "C28-Td", 36: "C36-D6h",
                     40: "C40-Td", 60: "C60-Ih", 70: "C70-D5h",
                     72: "C72-D6d", 76: "C76-D2", 78: "C78-D3",
                     80: "C80-Ih", 84: "C84-D2"}


def test_a_size_outside_the_table_is_refused_pointing_at_the_spiral():
    with pytest.raises(FullereneError, match="spiral can be typed"):
        catalogue.isomers(50)


def test_every_row_to_c80_closes_is_canonical_and_keeps_its_order():
    """Each row winds into a cage, is that cage's canonical spiral,
    and has the order written beside it."""
    for n in [s for s in catalogue.sizes() if s <= 80]:
        for row in catalogue.isomers(n):
            rotation = _check_cage(n, row.spiral)
            assert spiral.canonical(rotation) == (row.spiral, row.order)


def test_every_row_closes_and_the_ipr_rows_isolate_their_pentagons():
    """The whole table, C82 to C100 included: a row that does not
    wind would be a refusal in the form."""
    for n in catalogue.sizes():
        for row in catalogue.isomers(n):
            rotation = _check_cage(n, row.spiral)
            if row.ipr:
                assert all(len(rotation[g]) == 6
                           for around in rotation if len(around) == 5
                           for g in around)


@pytest.mark.slow
def test_the_script_regenerates_the_small_table():
    """The file is the script's: re-run for every isomer to C36 and
    IPR C60, it writes the same rows."""
    script = _script()
    for n, ipr in [(n, False) for n in range(20, 38, 2) if n != 22] \
            + [(60, True)]:
        rows = script.isomers(n, ipr)
        assert [(tuple(r["spiral"]), r["order"]) for r in rows] \
            == [(i.spiral, i.order) for i in catalogue.isomers(n)]
