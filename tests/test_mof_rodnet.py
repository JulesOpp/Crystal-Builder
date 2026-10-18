"""Rod nets: parallel rods on sql, hxl, hcb or kgm, their hands, and
where each sits."""

from collections import deque
from pathlib import Path

import numpy as np
import pytest

from xtal.analysis import rcsr
from xtal.core import bonding, p1
from xtal.io import read_cif
from xtal.mof import rodnet
from xtal.mof.rod import Rod, shipped
from xtal.mof.rodnet import Ends, RodNetError
from xtal.mof.trimer import Block

ROOT = Path(__file__).resolve().parents[1]
BTDD = ROOT / "xtal" / "mof" / "library" / "blocks" / "MFU4l_BTDD.xyz"


def rod(name) -> Rod:
    return Rod.read(shipped()[name])


def straight(span) -> Ends:
    return Ends(np.array([[0.0, 0.0, 0.0], [span, 0.0, 0.0]]),
                ((0,), (1,)))


@pytest.fixture(scope="module")
def bdc_span():
    """BDC's X-to-X span as MIL-53's crystal has it: the ring's para
    carbons, and a connection point 0.75 A beyond each.  PORMAKE's E14
    is drawn with 1.54 A ring bonds, 0.3 A longer across."""
    s = read_cif(ROOT / "resources" / "samples" / "prepared" / "MIL-53.cif")
    cell = p1.expand(s)
    graph = bonding.graph(s)
    elements = cell.elements
    near = {}
    for b in graph.bonds:
        near.setdefault(b.i, []).append((b.j, np.array(b.image)))
        near.setdefault(b.j, []).append((b.i, -np.array(b.image)))
    carboxyl = {i for i, e in enumerate(elements) if e == "C"
                and sum(elements[j] == "O" for j, _ in near[i]) == 2}
    first, image = next((j, im) for j, im in near[min(carboxyl)]
                        if elements[j] == "C")

    def cart(f):
        return np.asarray(cell.lattice.to_cart(np.asarray(f, float)))

    where = {first: cart(cell.frac[first] + image)}
    depth = {first: 0}
    queue = deque([first])
    while queue:
        a = queue.popleft()
        for j, im in near[a]:
            if elements[j] == "C" and j not in depth and j not in carboxyl:
                depth[j] = depth[a] + 1
                where[j] = where[a] + cart(cell.frac[j] + im) \
                    - cart(cell.frac[a])
                queue.append(j)
    para = next(j for j, d in depth.items() if d == 3)
    return float(np.linalg.norm(where[para] - where[first])) + 1.5


def radial_rod(reach=3.0, repeat=5.0) -> Rod:
    """A metal on the axis and four points straight out from it."""
    symbols = ["Cr"]
    positions = [[0.0, 0.0, 0.0]]
    bonds = []
    for k in range(4):
        u = np.array([np.cos(k * np.pi / 2), np.sin(k * np.pi / 2), 0.0])
        symbols.append("C")
        positions.append(list((reach - 0.75) * u))
        bonds.append((0, len(symbols) - 1, "S", 0))
    for k in range(4):
        u = np.array([np.cos(k * np.pi / 2), np.sin(k * np.pi / 2), 0.0])
        symbols.append("X")
        positions.append(list(reach * u))
        bonds.append((1 + k, len(symbols) - 1, "S", 0))
    return Rod(symbols, np.array(positions), repeat, bonds, [],
               "radial")


def test_the_four_patterns_are_the_rcsrs_layers_of_their_names():
    for name, pattern in rodnet.PATTERNS.items():
        assert rcsr.identify(rodnet.as_net(pattern)).name == name


def test_alternating_hands_are_refused_on_a_pattern_with_odd_rings():
    """hxl and kgm have triangles: around one, two rods of three are
    the same hand whatever is done, so "alternating" is not a thing
    that can be built, and saying so beats building something else."""
    btdd = rod("Ni2Cl2BTDD_Ni")
    for name in ("hxl", "kgm"):
        with pytest.raises(RodNetError, match="odd rings"):
            rodnet.rod_net(name, btdd, "alternating")
        assert rodnet.rod_net(name, btdd).hands == "same"


def test_an_achiral_rod_has_no_hands_to_alternate():
    with pytest.raises(RodNetError, match="no hand"):
        rodnet.rod_net("hcb", rod("MOF-303_Al"), "alternating")
    assert rodnet.rod_net("sql", rod("MIL-53_Cr")).hands == "same"


def test_auto_hands_are_the_rods_own_crystals():
    """Co(BDP)'s helices are all one hand, so auto keeps them so on
    sql, where it could alternate; MOF-74's alternate as theirs do.  A
    rod that says nothing (one saved from a structure) alternates
    where the pattern allows, as auto always did."""
    from dataclasses import replace

    assert rodnet.rod_net("sql", rod("MBDP_Zn")).hands == "same"
    assert rodnet.rod_net("sql", rod("MBDP_Zn"), "alternating").hands \
        == "alternating"
    assert rodnet.rod_net("hcb", rod("MOF-74_Zn")).hands == "alternating"
    unsaid = replace(rod("MBDP_Zn"), hands="")
    assert rodnet.rod_net("sql", unsaid).hands == "alternating"


def test_sqls_checkerboard_is_coloured_in_a_supercell_of_two():
    """One rod a cell cannot alternate with itself, so alternating on
    sql doubles the cell -- and the doubled pattern is still sql."""
    net = rodnet.rod_net("sql", rod("Ni2Cl2BTDD_Ni"), "alternating")
    assert len(net.pattern.nodes) == 2
    assert sorted(net.colours) == [0, 1]
    assert rcsr.identify(rodnet.as_net(net.pattern)).name == "sql"
    assert rodnet.rod_net("hcb", rod("MOF-74_Zn")).colours == (0, 1)


def test_the_cell_is_twice_the_rods_reach_plus_the_linkers_span():
    """Points straight out from the axis, a straight linker between
    them: the rods are one reach, a span and a reach apart."""
    r = radial_rod(reach=3.0)
    placed = rodnet.placement(rodnet.rod_net("sql", r), r, straight(5.0),
                              angle=90.0)
    assert placed.spacing == pytest.approx(3.0 + 5.0 + 3.0, abs=1e-3)
    assert placed.worst == pytest.approx(0.0, abs=1e-3)
    assert placed.cell[2] == pytest.approx(5.0)


@pytest.mark.slow
def test_a_rhombus_angle_is_a_parameter_never_a_default_silently_fixed(
        bdc_span):
    """MIL-53 breathes on its rhombus.  Not given, the angle is solved
    from where the rod's faces point and the placement says so; given,
    it is used, and joints it bends are reported, not hidden."""
    r = rod("MIL-53_Cr")
    net = rodnet.rod_net("sql", r)
    solved = rodnet.placement(net, r, straight(bdc_span))
    assert solved.angle_from == "from the rod's faces"
    assert "from the rod's faces" in solved.sentence()
    forced = rodnet.placement(net, r, straight(bdc_span), angle=60.0)
    assert forced.gamma == pytest.approx(60.0)
    assert forced.angle_from == "given"
    assert forced.worst > 0.5
    with pytest.raises(RodNetError, match="fixed by its symmetry"):
        rodnet.placement(rodnet.rod_net("hcb", rod("Ni2Cl2BTDD_Ni")),
                         rod("Ni2Cl2BTDD_Ni"), Block.read(BTDD),
                         angle=100.0)


def test_mil_53_on_sql_lands_on_its_crystals_cell(bdc_span):
    """The prepared crystal: rods 10.65 A apart in a 76.3 degree
    rhombus, every other one half a repeat up (Imma is I-centred)."""
    r = rod("MIL-53_Cr")
    placed = rodnet.placement(rodnet.rod_net("sql", r), r,
                              straight(bdc_span))
    assert placed.spacing == pytest.approx(10.65, rel=0.01)
    rhombus = min(placed.gamma, 180.0 - placed.gamma)
    assert rhombus == pytest.approx(76.3, abs=1.5)
    assert np.abs(np.array(placed.shears)) / r.repeat == \
        pytest.approx([0.5, 0.5], abs=0.02)
    assert placed.worst < 0.05


@pytest.mark.slow
def test_three_fold_helices_on_hcb_close_with_either_hand():
    """Alternating 3_1 helices joined in threes are etb, and the joints
    close with the rows rising a third of a repeat (R-centred, as the
    crystal is); one hand throughout is eta, and closes only with every
    other rod turned over -- P6_222's two-fold axes across the rods."""
    r = rod("Ni2Cl2BTDD_Ni")
    btdd = Block.read(BTDD)
    alternating = rodnet.placement(rodnet.rod_net("hcb", r), r, btdd)
    assert alternating.net.hands == "alternating"
    assert alternating.worst < 0.05
    rising = sorted(abs(s) / r.repeat % 1.0 for s in alternating.shears)
    assert all(min(v, 1 - v) == pytest.approx(1 / 3, abs=0.02)
               for v in rising)
    same = rodnet.placement(rodnet.rod_net("hcb", r, "same"), r, btdd)
    assert same.turned_over
    assert same.worst < 0.05


def test_a_rod_turned_over_keeps_its_hand():
    r = rod("MOF-74_Zn")
    assert r.turned_over().hand == r.hand
    assert r.mirror().turned_over().hand != r.hand


def test_points_that_do_not_divide_among_the_neighbours_are_refused():
    """MIL-53's four points a repeat cannot each face one of hcb's
    three neighbours an equal number of times."""
    r = rod("MIL-53_Cr")
    with pytest.raises(RodNetError, match="must divide"):
        rodnet.placement(rodnet.rod_net("hcb", r), r, straight(4.3))


def test_the_linker_a_rod_asks_for_spans_the_gap_its_reach_leaves():
    """The inverse: a cell asked for is a span asked of the linker, and
    a span is a reach asked of the rod."""
    r = radial_rod(reach=3.0)
    asked = rodnet.requirement(r, "sql", 14.0)
    assert asked.topicity == 2
    assert asked.value == pytest.approx(14.0 - 2 * 3.0)
    assert asked.low < asked.value < asked.high
    with pytest.raises(RodNetError, match="no room"):
        rodnet.requirement(r, "sql", 5.0)
    ranked = rodnet.rods_for(8.0, "sql", 14.0,
                             {"radial": r, "wide": radial_rod(4.0)})
    assert ranked[0] == ("radial", pytest.approx(0.0, abs=1e-9))


def test_the_searchs_batched_cost_is_the_cost():
    """The grid of starts is costed as arrays and the refinement one
    point at a time; if the two drifted apart the search would start
    from the wrong places and nothing would say so."""
    r = rod("MOF-303_Al")
    net = rodnet.rod_net("sql", r)
    cell, colours = rodnet.colouring(net.pattern)
    p = rodnet.supercell(net.pattern, cell, colours)
    bent = Ends(np.array([[0.0, 0.0, 0.0], [3.5, 0.0, 0.0],
                          [0.6, 0.6, 0.0], [2.9, 0.6, 0.0]]), ((0,), (1,)),
                0.24, 0.0)
    for linker in (straight(3.6), bent):
        model = rodnet._Model(p, p.colours,
                              (rodnet.faces(r, 1),
                               rodnet.faces(r.turned_over(), 1)),
                              r.repeat, linker.span, 14.0, linker.bend,
                              linker.twist)
        rng = np.random.default_rng(7)
        xs = np.column_stack([rng.uniform(-180, 180, (50, 2)),
                              rng.uniform(0, r.repeat, (50, 3)),
                              rng.uniform(-0.1, 0.1, 50)])
        one = [model.cost(x, 85.0) for x in xs]
        assert model.costs(xs, 85.0) == pytest.approx(one, rel=1e-9)


def test_a_rhombus_that_fits_either_way_is_given_by_its_acute_angle():
    """MIL-53's rhombus closes at 75 degrees and, from its other corner,
    at 105: a tie, and a 1e-4 A rounding in BDC's file decided it.  The
    smaller angle wins, so the dialog's best fit stays 75."""
    from xtal.mof.rodbuild import load_linker, load_rod
    from xtal.mof.rodnet import placement, rod_net

    rod = load_rod("MIL-53_Cr")
    placed = placement(rod_net("sql", rod, "auto"), rod, load_linker("BDC"))
    assert 70 < placed.gamma < 80
