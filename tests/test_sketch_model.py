"""A molecule as it is drawn (``xtal.build.sketch``), with no display.

The sketcher's canvas is a picture of one of these and every gesture
an edit of it, so what a drawing *is* -- and what string it writes --
is decided here, where it can be tested in milliseconds.
"""

from __future__ import annotations

import math

import pytest

from xtal.build import MISSING, chem, installed, library
from xtal.build.sketch import BOND, Sketch, symbol

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


def _chain(n: int, element: str = "C") -> Sketch:
    sketch = Sketch()
    sketch.add_atom(element)
    for k in range(n - 1):
        sketch.grow(k, element)
    return sketch


# ------------------------------------------------------------ editing

def test_a_chain_grows_a_bond_length_at_a_time_in_a_zigzag():
    sketch = _chain(4)
    lengths = [math.dist(sketch.point(b.a), sketch.point(b.b))
               for b in sketch.bonds]
    assert lengths == pytest.approx([BOND] * 3)
    # Atoms 0 and 2 are 120 degrees apart round atom 1, not in line.
    (x0, y0), (x1, y1), (x2, y2) = (sketch.point(k) for k in range(3))
    angle = math.degrees(math.atan2(y0 - y1, x0 - x1)
                         - math.atan2(y2 - y1, x2 - x1)) % 360
    assert min(angle, 360 - angle) == pytest.approx(120, abs=1e-6)


def test_setting_the_order_of_many_bonds_is_one_edit():
    """Select All, then Double: every bond selected, not the one under
    the cursor."""
    sketch = _chain(5)
    sketch.set_order(range(len(sketch.bonds)), "double")
    assert {b.order for b in sketch.bonds} == {"double"}


def test_deleting_an_atom_takes_its_bonds_and_renumbers():
    sketch = _chain(3)
    sketch.delete(atoms=[1])
    assert len(sketch) == 2
    assert sketch.bonds == []


def test_a_ring_fused_on_a_bond_shares_it():
    sketch = Sketch()
    sketch.add_ring(6)
    shared = sketch.bond_between(0, 1)
    ring = sketch.add_ring(5, bond=shared)
    assert ring[:2] == [0, 1]
    assert len(sketch) == 9
    assert len(sketch.bonds) == 10
    lengths = [math.dist(sketch.point(b.a), sketch.point(b.b))
               for b in sketch.bonds]
    assert lengths == pytest.approx([BOND] * 10)


def test_a_fused_ring_goes_on_the_far_side():
    """Drawn over the first ring, a naphthalene is two hexagons on top
    of each other; the second goes where nothing is."""
    sketch = Sketch()
    first = sketch.add_ring(6)
    sketch.add_ring(6, bond=sketch.bond_between(first[0], first[1]))
    for k in range(6, len(sketch)):
        others = [math.dist(sketch.point(k), sketch.point(j))
                  for j in first]
        assert min(others) > 0.5 * BOND


def test_element_names_are_read_strictly():
    assert symbol("cl") == "Cl"
    assert symbol("*") == "X"
    for wrong in ("Q", "Xx", "Kr2", ""):
        with pytest.raises(ValueError):
            symbol(wrong)


def test_a_head_is_one_point_only():
    sketch = Sketch()
    a = sketch.add_atom("X")
    b = sketch.add_atom("X")
    sketch.set_map_number(a, 1)
    sketch.set_map_number(b, 1)
    assert [atom.map_number for atom in sketch.atoms] == [0, 1]


# --------------------------------------------------- strings, both ways

@needs_rdkit
def test_a_smiles_survives_the_sketch_round_trip():
    """Every fragment the library ships: drawn from its string and
    written back, it is the same molecule."""
    for entry in library.entries():
        drawn = chem.sketch_from_smiles(entry.smiles)
        assert chem.sketch_smiles(drawn) == chem.canonical(entry.smiles), \
            entry.name


@needs_rdkit
def test_a_star_bonded_to_two_atoms_stays_one_point():
    drawn = chem.sketch_from_smiles("C1O*OC1")
    [point] = drawn.connection_points()
    assert len(drawn.neighbours(point)) == 2


@needs_rdkit
def test_head_and_tail_numbers_survive():
    text = chem.sketch_smiles(chem.sketch_from_smiles("[*:1]CC([*:2])C"))
    assert "[*:1]" in text and "[*:2]" in text


@needs_rdkit
def test_a_geometry_override_rides_in_the_cxsmiles():
    sketch = chem.sketch_from_smiles("Cl[Pt](Cl)([NH3])[NH3]")
    [pt] = [k for k, a in enumerate(sketch.atoms) if a.element == "Pt"]
    sketch.set_shape([pt], "tetrahedral")
    text = chem.sketch_smiles(sketch)
    back = chem.sketch_from_smiles(text)
    assert [a.shape for a in back.atoms if a.element == "Pt"] == \
        ["tetrahedral"]


@needs_rdkit
def test_a_metal_is_given_no_hydrogens_it_was_not_drawn_with():
    sketch = Sketch()
    zn = sketch.add_atom("Zn")
    sketch.grow(zn, "Cl")
    assert chem.sketch_smiles(sketch) == chem.canonical("Cl[Zn]")


@needs_rdkit
def test_a_dative_bond_keeps_the_donors_hydrogens():
    """An ammine is a dative bond; an ordinary bond to the metal is
    an amido, as drawn."""
    sketch = Sketch()
    pt = sketch.add_atom("Pt")
    n = sketch.grow(pt, "N")
    sketch.connect(n, pt, "dative")
    assert "[NH3]" in chem.sketch_smiles(sketch)
    sketch.set_order([0], "single")
    assert "[NH2]" in chem.sketch_smiles(sketch)


@needs_rdkit
def test_a_drawing_that_is_not_a_molecule_says_why():
    sketch = Sketch()
    c = sketch.add_atom("C")
    for _ in range(5):
        sketch.grow(c, "F")
    with pytest.raises(chem.BuildError, match="too many bonds"):
        chem.sketch_smiles(sketch)


def test_a_ring_on_a_bonded_atom_hangs_off_it():
    """A phenyl on a nitrogen: the ring through a new bond, and the
    nitrogen keeps its own bonds."""
    sketch = _chain(2)
    ring = sketch.add_ring(6, atom=1)
    assert 1 not in ring
    assert len(sketch) == 8
    assert sketch.bond_between(1, ring[0]) is not None
