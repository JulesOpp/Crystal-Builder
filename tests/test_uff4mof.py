"""UFF4MOF: the metal nodes UFF was never given.

UFF has one tetrahedral zinc and no square-planar copper at all, so
the framework this application exists to build is the structure its
own force field is worst at.  UFF4MOF (2014) and UFF4MOF-II (2016) add
ninety-one rows for exactly those environments, and the rows are the
easy half -- ``params.py``'s docstring has always said a type name is
data.

The hard half is that they are *alternatives*.  ``Zn3+2`` and
``Zn3f2`` are both a tetrahedral Zn(II) and nothing geometric tells
them apart, so a merged table means the typer has to decide, and every
test below is about that decision: that a framework gets the fitted
row, that a plain oxide does not, that the shape is measured rather
than inferred from a coordination number two characters share, and
that what is left genuinely ambiguous is reported rather than settled
by which row happens to come first.
"""

import numpy as np

from xtal.core import bonding, p1
from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure
from xtal.ff import ENGINES, optimize
from xtal.ff.uff import params, typer
from xtal.io import read_cif

#: The Zn-O distances of MOF-5's node, measured off the crystal
#: structure that ships in resources/samples.  These are the numbers
#: UFF4MOF exists to reproduce and UFF does not.
MOF5_ZN_O_OXIDE = 1.9429
MOF5_ZN_O_CARBOXYLATE = 1.9408


def types_of(structure) -> dict[str, set[str]]:
    """Element -> the set of types the typer gave it."""
    cell = p1.expand(structure)
    out: dict[str, set[str]] = {}
    for element, name in zip(cell.elements, typer.assign(structure).names,
                             strict=True):
        out.setdefault(element, set()).add(name)
    return out


def sample(name):
    return read_cif(f"resources/samples/{name}.cif")


def molecule(symbols, positions, box=20.0):
    """Atoms in a box big enough that nothing sees its own image."""
    lattice = Lattice.from_parameters(box, box, box, 90.0, 90.0, 90.0)
    frac = np.asarray(positions, dtype=float) / box + 0.5
    return Structure(lattice=lattice,
                     sites=[Site(s, f) for s, f
                            in zip(symbols, frac, strict=True)],
                     space_group=SpaceGroup.p1())


# ----------------------------------------------------------- the table

def test_the_fitted_rows_are_reachable_and_describe_themselves():
    """A fitted row spells the oxidation state with an ``f`` where UFF
    spells it with a sign, so the positional parsing that reads
    ``Fe6+2`` has to be taught it -- or every one of them loses its
    oxidation state and reads as a bare element in the override
    dropdown."""
    assert params.get("Zn3f2").oxidation_state == 2
    assert params.get("Cr6f3").oxidation_state == 3
    assert params.get("Zn3f2").is_fitted
    assert not params.get("Zn3+2").is_fitted
    assert params.get("Zn3f2").description == \
        "tetrahedral Zn(II), framework-fitted"


def test_the_eight_coordinate_geometry_character_is_understood():
    """UFF stops at six.  UFF4MOF-II's Zr8f4 and the lanthanide rows
    use ``8``, and a character the table does not know makes
    ``coordination`` None -- which the fallback then treats as
    zero-coordinate and prefers for a terminal atom."""
    assert params.get("Zr8f4").coordination == 8
    assert params.get("Zr8f4").shape == "cubic"


def test_a_linear_type_expects_two_neighbours_and_not_one():
    """``1`` is a shape, and a linear centre has two neighbours.  It
    read as one until UFF4MOF-II brought seven linear metals with it,
    and then it decided which row they got."""
    assert params.get("Ag1+1").coordination == 2
    assert params.get("Ag1f1").coordination == 2


# ------------------------------------------------------- the framework

def test_mof5_gets_the_node_uff4mof_was_written_for():
    """MOF-5 is the structure the 2014 paper is about: a Zn4O node,
    four tetrahedral zincs around one oxygen that bridges all of them,
    with carboxylates from there out.  All three types are UFF4MOF's
    and none of them existed in UFF."""
    types = types_of(sample("MOF-5"))
    assert types["Zn"] == {"Zn3f2"}
    assert "O_3_f" in types["O"]


def test_plain_uff_types_mof5_without_a_single_uff4mof_row():
    """The parameter set is how somebody checks a UFF4MOF number
    against the field it extends.  If one fitted row slipped through
    -- the node oxide, which a hand-written rule and not the table
    hands out, is the likely one -- the comparison would be between
    two answers that are both UFF4MOF."""
    structure = sample("MOF-5")
    names = set(typer.assign(structure, parameter_set="uff").names)
    assert not names & params.UFF4MOF_TYPES
    cell = p1.expand(structure)
    zinc = {n for e, n in zip(cell.elements, typer.assign(
        structure, parameter_set="uff").names, strict=True) if e == "Zn"}
    assert zinc == {"Zn3+2"}


def test_plain_uff_costs_a_paddlewheel_its_square_planar_copper():
    """``Cu4+2`` has no ``f`` in its name and is UFF4MOF's all the
    same, so a filter on ``is_fitted`` alone would have kept it."""
    structure = sample("HKUST1")
    cell = p1.expand(structure)
    names = typer.assign(structure, parameter_set="uff").names
    assert {n for e, n in zip(cell.elements, names, strict=True)
            if e == "Cu"} == {"Cu3+1"}


def test_the_calculator_types_with_the_set_it_was_given():
    from xtal.ff.uff.calculator import UFFCalculator, UFFOptions
    structure = sample("MOF-5")
    plain = UFFCalculator(structure, UFFOptions(parameter_set="uff"))
    assert "Zn3f2" not in plain.types
    assert "Zn3f2" in UFFCalculator(structure).types
    assert plain.options.to_dict()["parameter_set"] == "uff"


def test_the_hkust1_paddlewheel_copper_is_square_planar():
    """UFF gives copper one type, ``Cu3+1``, and it is tetrahedral.
    The paddlewheel is not, and taking the tetrahedral row for it is
    the silent wrong answer this phase exists to stop -- ``Cu4+2`` is
    the row UFF4MOF added and the angles are what choose it."""
    types = types_of(sample("HKUST1"))
    assert types["Cu"] == {"Cu4+2"}


def test_zif8_zinc_is_a_framework_node_through_nitrogen():
    """The linker is an imidazolate and the donor is N rather than O,
    which the rule has to accept or every ZIF types as ordinary
    zinc."""
    assert types_of(sample("ZIF-8"))["Zn"] == {"Zn3f2"}


def test_mfu4l_says_so_where_it_cannot_tell():
    """MFU-4l has two kinds of zinc: four tetrahedral ones that take
    the fitted row, and a central octahedral one that neither paper
    has a type for at all.  The second must come back uncertain -- it
    is a real answer with a real caveat, and the panel's warning is
    the only place that caveat exists."""
    structure = sample("MFU4l")
    typing = typer.assign(structure)
    assert types_of(structure)["Zn"] == {"Zn3f2", "Zn3+2"}
    cell = p1.expand(structure)
    unsure = {cell.elements[i] for i in typing.unsure()}
    assert unsure == {"Zn"}


# --------------------------------------------------- and where it must not

def test_rutile_titanium_is_not_a_framework_node(rutile):
    """Every neighbour a metal and every neighbour bridged: an oxide
    looks like a node from close up.  What it has not got is carbon,
    and that is what *metal-organic* means."""
    types = types_of(rutile)
    assert types["Ti"] == {"Ti6+4"}
    assert types["O"] == {"O_3"}


def test_quartz_keeps_the_zeolite_oxygen(quartz):
    """The rule that came before this one still gets there first."""
    assert types_of(quartz)["O"] == {"O_3_z"}


def test_a_zinc_that_is_not_in_a_framework_keeps_rappes_row():
    """Four waters on a zinc is a tetrahedral Zn(II) and is not a
    framework node.  Nothing about the metal says which row it should
    have; the linker does, and there is no linker here."""
    d = 2.0
    positions = [(0, 0, 0)]
    for x, y, z in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)):
        n = np.array([x, y, z], dtype=float)
        positions.append(tuple(d * n / np.linalg.norm(n)))
        positions.append(tuple((d + 0.96) * n / np.linalg.norm(n)))
    symbols = ["Zn"] + ["O", "H"] * 4
    assert types_of(molecule(symbols, positions))["Zn"] == {"Zn3+2"}


# ------------------------------------------- and whether it is better

def zinc_oxygen(structure, frac=None):
    """``(mu4 oxide, carboxylate)`` mean Zn-O distance, in Angstrom.

    Split by what the oxygen is bonded to rather than by index, so it
    reads the same off the crystal structure and off a relaxation of
    it.
    """
    cell = p1.expand(structure)
    geo = bonding.geometry(structure)
    graph = bonding.graph(structure)
    matrix = structure.lattice.matrix
    cart = cell.cart if frac is None else frac @ matrix
    oxide, carboxylate = [], []
    for i, element in enumerate(cell.elements):
        if element != "Zn":
            continue
        for j, shift in graph.neighbors_with_images(i):
            if cell.elements[j] != "O":
                continue
            d = float(np.linalg.norm(
                cart[j] + shift @ matrix - cart[i]))
            bucket = (oxide if all(cell.elements[k] == "Zn"
                                   for k in geo.partners(j))
                      else carboxylate)
            bucket.append(d)
    return float(np.mean(oxide)), float(np.mean(carboxylate))


def relaxed(structure):
    calculator = ENGINES.build("uff", structure)
    result = optimize.run(calculator, structure, max_steps=200,
                          force_tolerance=1e-3)
    return zinc_oxygen(structure, result.frac)


def test_the_node_comes_out_closer_than_uff_alone(monkeypatch):
    """The claim the whole phase rests on, measured rather than
    assumed.

    Everything else here checks that the right row is chosen; this
    checks that choosing it was worth doing.  MOF-5 is relaxed twice
    over the same bond graph -- once as the typer types it now, and
    once with the fitted rows suppressed so it falls back to Rappe's
    -- and the node is compared against the crystal structure both
    times.

    It is not a large improvement and it is not claimed to be one.
    UFF4MOF is a force field fitted to a class of solids, not a
    refinement: what it buys is a node that is wrong by 0.08 A rather
    than 0.10, and a Zn-O that no longer needs an octahedral zinc's
    parameters to describe a tetrahedral one.
    """
    structure = sample("MOF-5")
    with_fitted = relaxed(structure)

    monkeypatch.setattr(typer, "_framework_node",
                        lambda *args, **kwargs: False)
    structure = sample("MOF-5")
    without = relaxed(structure)

    target = np.array([MOF5_ZN_O_OXIDE, MOF5_ZN_O_CARBOXYLATE])
    better = np.abs(np.array(with_fitted) - target)
    worse = np.abs(np.array(without) - target)
    assert better.mean() < worse.mean()
