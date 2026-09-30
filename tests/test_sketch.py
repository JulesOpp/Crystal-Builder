"""The Skeletal style's drawing, as arrays: labels, gaps and wedges,
asserted without a render window."""

import math
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, p1
from xtal.io.cif_reader import read_cif
from xtalapp.viewport import sketch

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"

# Straight down -z, with +y up the screen and so +x to the right.
DOWN = dict(direction=(0, 0, -1), view_up=(0, 1, 0))


def _box(symbols, cart, edge=12.0):
    lattice = Lattice.cubic(edge)
    frac = np.asarray(cart, float) / edge + 0.5
    return Structure.from_arrays(lattice, symbols, frac)


@pytest.fixture
def methylamine():
    """CH3-NH2 in a box of its own: a carbon with three hydrogens and
    a nitrogen with two."""
    return _box(
        ["C", "N", "H", "H", "H", "H", "H"],
        [[0.0, 0.0, 0.0], [1.47, 0.0, 0.0],
         [-0.36, 1.03, 0.0], [-0.36, -0.51, 0.89],
         [-0.36, -0.51, -0.89],
         [1.81, -0.47, 0.82], [1.81, -0.47, -0.82]])


def _fold(structure, explicit_carbon=False):
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    ends = [(b.i, b.j) for b in graph.bonds]
    return cell, graph, sketch.fold(cell.elements, ends, explicit_carbon)


def test_an_nh2_nitrogen_is_labelled_nh2_and_its_hydrogens_are_not_drawn(
        methylamine):
    """Folding regressed would draw every N-H as a line to an H."""
    cell, _graph, folding = _fold(methylamine)
    n = list(cell.elements).index("N")
    assert folding.text[n] == "NH2"
    assert folding.hydrogens[n] == 2
    hydrogens = [k for k, s in enumerate(cell.elements) if s == "H"]
    assert folding.hidden[hydrogens].all()
    assert all(folding.text[h] == "" for h in hydrogens)


def test_implicit_carbon_hides_the_label_and_its_hydrogens(methylamine):
    cell, _graph, folding = _fold(methylamine)
    c = list(cell.elements).index("C")
    assert folding.text[c] == ""
    assert folding.degree[c] == 1           # the C-N bond, and no C-H


def test_explicit_carbon_writes_its_hydrogens(methylamine):
    cell, _graph, folding = _fold(methylamine, explicit_carbon=True)
    assert folding.text[list(cell.elements).index("C")] == "CH3"


def test_a_carbon_with_no_bonds_keeps_its_label_when_carbon_is_implicit():
    """Methane: an implicit vertex with no lines to it is not in the
    picture at all, so it is written out."""
    folding = sketch.fold(["C", "H", "H", "H", "H"],
                          [(0, 1), (0, 2), (0, 3), (0, 4)])
    assert folding.text[0] == "CH4"


def test_a_free_water_is_written_h2o_and_a_bound_one_oh2():
    free = sketch.fold(["O", "H", "H"], [(0, 1), (0, 2)])
    assert free.text[0] == "H2O"
    bound = sketch.fold(["Zn", "O", "H", "H"], [(0, 1), (1, 2), (1, 3)])
    assert bound.text[1] == "OH2"
    assert bound.text[0] == "Zn"


def test_a_hydrogen_on_a_metal_or_a_marker_is_drawn_as_itself():
    """A hydride is chemistry a label cannot say, and a marker is not
    an atom that can carry one."""
    folding = sketch.fold(["Fe", "H", "X", "H"], [(0, 1), (2, 3)])
    assert not folding.hidden.any()
    assert folding.text == ("Fe", "H", "X", "H")


def test_a_bridging_hydrogen_is_not_folded():
    folding = sketch.fold(["B", "H", "B"], [(0, 1), (1, 2)])
    assert not folding.hidden.any()
    assert folding.text[1] == "H"


def test_folding_leaves_the_structure_and_its_graph_unchanged(
        methylamine):
    before = [(b.i, b.j, tuple(b.image))
              for b in bonding.graph(methylamine).bonds]
    sites = len(methylamine.sites)
    _fold(methylamine)
    after = [(b.i, b.j, tuple(b.image))
             for b in bonding.graph(methylamine).bonds]
    assert after == before and len(methylamine.sites) == sites


def test_mof5_with_implicit_carbon_labels_only_its_zinc_and_oxygen():
    """Every hydrogen of MOF-5 is on a ring carbon, so with carbon
    implicit the labels are the metal and the oxygens."""
    structure = read_cif(SAMPLES / "MOF-5.cif")
    cell, _graph, folding = _fold(structure)
    labelled = Counter(t for t in folding.text if t)
    assert set(labelled) == {"Zn", "O"}
    assert folding.hidden.sum() == list(cell.elements).count("H")


def test_a_metal_is_the_centre_of_its_bonds():
    """Zn-O: the zinc has four bonds and the carboxylate oxygen two,
    and a tie would still go to the metal."""
    first = sketch.centres(["O", "Zn"], [2, 4], [(0, 1)])
    assert not first[0]
    tie = sketch.centres(["O", "Zn"], [2, 2], [(0, 1)])
    assert not tie[0]
    busier = sketch.centres(["C", "O"], [3, 1], [(0, 1)])
    assert busier[0]


def test_a_label_sits_its_own_letters_on_the_vertex():
    """NH2's hydrogens trail off to the right, so a bond leaving to
    the right has further to go before it clears the label."""
    left, right, down, up = sketch.label_extents("NH2", "N", 0.5)
    assert right > 2 * left
    assert down > up                        # the subscript descends
    assert sketch.label_extents("", "C", 0.5) == (0, 0, 0, 0)


def _one_half(direction, extents=(0.2, 0.2, 0.2, 0.2), from_centre=True,
              order=1.0):
    start = np.zeros((1, 3))
    end = np.asarray(direction, float).reshape(1, 3)
    return sketch.sketch_bonds(
        start, end, [extents], [from_centre], [order], [(0, 1, 0)],
        scale=1.5, **DOWN)


@pytest.mark.parametrize("tilt", [0.0, 15.0, 25.0])
def test_a_bond_stops_short_of_a_label_by_the_gap_on_screen(tilt):
    """The cut is measured on screen: a foreshortened bond loses more
    of its world length to the same label."""
    angle = math.radians(tilt)
    half = 0.75 * np.array([math.cos(angle), 0.0, math.sin(angle)])
    ink = _one_half(half)
    assert len(ink.line_starts) == 1
    assert ink.line_starts[0, 0] == pytest.approx(0.2)
    assert ink.line_ends[0] == pytest.approx(half)


def test_an_implicit_vertex_is_not_cut():
    ink = _one_half((0.75, 0, 0), extents=(0, 0, 0, 0))
    assert ink.line_starts[0] == pytest.approx((0, 0, 0))


def test_a_bond_seen_end_on_is_not_drawn_inverted():
    """Down its own axis a half is inside its label, and is left out
    rather than drawn from the far side of its atom."""
    ink = _one_half((0.01, 0, 0.75))
    assert not len(ink.line_starts) and not len(ink.wedge_quads)
    assert not len(ink.hash_starts)


def test_a_bond_towards_the_viewer_from_its_centre_is_a_solid_wedge():
    """The camera looks down -z, so +z is towards it.  The wedge is
    narrow at the centre and widens outwards."""
    ink = _one_half((0.5, 0, 0.5), extents=(0, 0, 0, 0))
    assert len(ink.wedge_quads) == 1 and not len(ink.line_starts)
    quad = ink.wedge_quads[0]
    narrow = np.linalg.norm(quad[1] - quad[0])
    wide = np.linalg.norm(quad[2] - quad[3])
    assert narrow == pytest.approx(0.0, abs=1e-9)
    assert wide == pytest.approx(1.5 * sketch.WEDGE_WIDTH / 2)


def test_a_bond_away_from_its_centre_is_hashed():
    ink = _one_half((0.5, 0, -0.5), extents=(0, 0, 0, 0))
    assert not len(ink.wedge_quads) and not len(ink.line_starts)
    assert len(ink.hash_starts) >= 2
    widths = np.linalg.norm(ink.hash_ends - ink.hash_starts, axis=1)
    assert np.all(np.diff(widths) >= -1e-12)    # widening outwards


def test_the_far_half_of_a_wedge_continues_the_near_one():
    """The half from the far atom is wide where the near one ended,
    so the two halves make one wedge."""
    near = _one_half((0.5, 0, 0.5), extents=(0, 0, 0, 0))
    far = _one_half((-0.5, 0, -0.5), extents=(0, 0, 0, 0),
                    from_centre=False)
    assert len(far.wedge_quads) == 1
    mid_near = np.linalg.norm(near.wedge_quads[0][2]
                              - near.wedge_quads[0][3])
    mid_far = np.linalg.norm(far.wedge_quads[0][2]
                             - far.wedge_quads[0][3])
    assert mid_near == pytest.approx(mid_far)


def test_a_double_bond_is_two_lines_and_never_a_wedge():
    ink = _one_half((0.5, 0, 0.5), extents=(0, 0, 0, 0), order=2.0)
    assert len(ink.line_starts) == 2 and not len(ink.wedge_quads)


def test_the_bond_scale_is_the_median_bond():
    starts = np.zeros((3, 3))
    ends = np.array([[0.5, 0, 0], [0.7, 0, 0], [2.0, 0, 0]])
    assert sketch.bond_scale(starts, ends) == pytest.approx(1.4)
