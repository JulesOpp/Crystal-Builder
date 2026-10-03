"""Chains packed into a box: the amorphous model and what it reports."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import numpy as np
import pytest

from xtal.build import MISSING, installed
from xtal.core import bonding, elements, p1
from xtal.polymer import build, monomer, pack, pushoff
from xtal.polymer.sequence import Sequence

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


@pytest.fixture(scope="module")
def pe():
    if not installed():
        pytest.skip(MISSING)
    return monomer.from_library("Polyethylene")


@pytest.fixture(scope="module")
def bulk(pe):
    return build.build(pack.Recipe(monomers=(pe,), chains=3, length=10))


@pytest.fixture(scope="module")
def film(pe):
    return build.build(pack.Recipe(monomers=(pe,), chains=3, length=10,
                                   periodic="membrane", thickness=15.0,
                                   vacuum=10.0))


def _cart(structure) -> np.ndarray:
    cell = p1.expand(structure)
    return cell.lattice.to_cart(cell.frac)


def _stated(structure) -> list[tuple[int, int, float]]:
    return [(b.i, b.j, 1.0) for b in bonding.graph(structure).bonds]


def _box(structure) -> np.ndarray:
    return np.diag(structure.lattice.matrix).copy()


@needs_rdkit
def test_no_two_non_bonded_atoms_are_closer_than_the_overlap_scale(bulk):
    """Measured off the structure as written, with the bonds it states:
    a push-off that stopped short, or a bond lost on the way into the
    cell, leaves two atoms where one clash is all a person sees."""
    structure = bulk.structure
    fraction, distance = pushoff.contacts(
        [s.element for s in structure.sites], _cart(structure),
        _stated(structure), _box(structure))

    assert fraction >= pack.OVERLAP
    assert fraction == pytest.approx(bulk.closest, abs=1e-6)
    assert distance == pytest.approx(bulk.closest_distance, abs=1e-6)


@needs_rdkit
def test_a_bulk_build_reaches_its_target_density_or_says_so(bulk):
    """The density is the structure's own mass over its own cell, and
    the report names it beside the one asked for.  A box sized from
    the wrong mass is a model of another polymer."""
    structure = bulk.structure
    mass = sum(elements.mass(s.element) for s in structure.sites)
    density = mass / (structure.lattice.volume * pack.AVOGADRO)

    assert density == pytest.approx(bulk.density, rel=1e-9)
    assert density == pytest.approx(0.85, abs=0.02)
    text = "\n".join(bulk.lines())
    assert f"density {bulk.density:.3f} g/cm3 (asked 0.85)" in text
    assert "compressed to the target" in text


@needs_rdkit
def test_a_membrane_has_no_bond_across_c_and_vacuum_on_both_sides(film):
    """The surfaces are the chains' own: nothing grew across the film's
    faces, so no bond may reach the next film along c, and the atoms
    sit between the walls with the vacuum split either side."""
    structure = film.structure
    c = structure.lattice.parameters[2]
    z = _cart(structure)[:, 2]

    assert c == pytest.approx(25.0)
    assert all(b.image[2] == 0 for b in bonding.graph(structure).bonds)
    assert any(b.image[:2] != (0, 0)
               for b in bonding.graph(structure).bonds)
    assert z.min() > 3.0 and c - z.max() > 3.0
    assert z.max() - z.min() < 15.0 + 3.0


@needs_rdkit
def test_every_chain_has_the_monomers_asked_for_and_no_dummy_left(bulk):
    """Three chains of ten C2H4 with a hydrogen on each end: every X
    used up at a joint or capped, and every carbon with four
    neighbours from the stated graph."""
    structure = bulk.structure
    counts = Counter(s.element for s in structure.sites)
    coordination = bonding.graph(structure).coordination()

    assert counts == {"C": 3 * 10 * 2, "H": 3 * (10 * 4 + 2)}
    assert not any(s.element in elements.DUMMY_ELEMENTS
                   for s in structure.sites)
    assert all(len(chain.units) == 10 for chain in bulk.chains)
    carbons = [k for k, s in enumerate(structure.sites)
               if s.element == "C"]
    assert set(coordination[carbons]) == {4}


@needs_rdkit
def test_the_bonds_are_stated_and_never_perceived(bulk):
    """The graph the structure carries is the chains' own bonds,
    whatever distance perception would make of a squeezed box -- a
    compressed melt has hydrogens 2.1 A apart on different chains."""
    structure = bulk.structure
    stated = len(_stated(structure))
    expected = 3 * (10 * 6 - 1 + 2)   # C-C and C-H, joints, end caps

    assert stated == expected
    assert bonding.graph(structure).n_atoms == len(structure.sites)


@needs_rdkit
def test_the_same_seed_builds_the_same_model(pe):
    """A person who builds the same recipe twice gets the same atoms;
    another seed gets another model."""
    recipe = pack.Recipe(monomers=(pe,), chains=2, length=6, seed=7)
    one = _cart(build.build(recipe).structure)
    two = _cart(build.build(recipe).structure)
    other = _cart(build.build(replace(recipe, seed=8)).structure)

    np.testing.assert_array_equal(one, two)
    assert one.shape != other.shape or not np.allclose(one, other)


@needs_rdkit
def test_a_build_over_max_atoms_is_refused_before_growing(pe,
                                                          monkeypatch):
    """Refused with the count in the sentence, and before a single
    chain is seeded: a window of a hundred thousand atoms is found out
    by opening it, and by then the minutes are spent."""
    def never(*_args, **_kwargs):
        raise AssertionError("grew a recipe that should be refused")

    monkeypatch.setattr(pack, "grow", never)
    recipe = pack.Recipe(monomers=(pe,), chains=50, length=200,
                         max_atoms=20000)

    with pytest.raises(pack.PackError, match="over the 20000"):
        build.build(recipe)


@needs_rdkit
def test_stop_ends_a_build_without_a_structure(pe):
    """``check`` raising is how Stop arrives; it must come out of the
    build as itself, not as a model of whatever was placed by then."""
    class Stopped(Exception):
        pass

    calls = []

    def check():
        calls.append(None)
        if len(calls) > 20:
            raise Stopped

    with pytest.raises(Stopped):
        build.build(pack.Recipe(monomers=(pe,), chains=3, length=10),
                    check=check)


@needs_rdkit
def test_a_start_density_above_the_target_is_refused(pe):
    """A box is grown loose and compressed; the other way round would
    be an expansion nothing does."""
    with pytest.raises(pack.PackError, match="at most the target"):
        pack.Recipe(monomers=(pe,), density=0.85,
                    start_density=0.9).check()


@needs_rdkit
def test_a_monomer_without_a_stereocentre_reports_no_tacticity(bulk):
    """Polyethylene's mirror image is itself turned over, so "atactic,
    52 % meso" for it is a number about nothing."""
    first = bulk.lines()[0]

    assert not bulk.recipe.monomers[0].handed
    assert "tactic" not in first and "meso" not in first


@needs_rdkit
def test_an_atactic_polypropylene_reports_its_meso_dyads():
    """Where growth chose the hands, the report says what it chose."""
    pp = monomer.from_library("Polypropylene")
    built = build.build(pack.Recipe(
        monomers=(pp,), chains=2, length=8, density=0.85,
        sequence=Sequence(tacticity="atactic")))

    assert pp.handed
    assert built.meso is not None
    assert f"atactic ({built.meso:.0%} meso dyads)" in built.lines()[0]


@needs_rdkit
@pytest.mark.slow
def test_a_ladder_polymer_packs_and_says_how_it_was_compressed():
    """PIM-1 cannot turn about its joints, only flip: it is grown loose
    and squeezed, and the report says the literature's density comes
    from MD rather than from this."""
    pim = monomer.from_library("PIM-1")
    built = build.build(pack.Recipe(monomers=(pim,), chains=2, length=4,
                                    density=1.06))
    text = "\n".join(built.lines())

    assert built.density == pytest.approx(1.06, abs=0.02)
    assert built.closest >= pack.OVERLAP
    assert built.grown_at < 1.06
    assert "21-step protocol" in text
    assert not any(s.element in elements.DUMMY_ELEMENTS
                   for s in built.structure.sites)
