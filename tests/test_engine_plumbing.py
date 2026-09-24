"""What every engine shares: the door, the options, the two bases.

Each engine used to filter its own keywords three different ways, the
two external programs were one class written twice, and MACE's ASE
plumbing was MACE's alone.  These pin the shared version, so that the
next engine is its own part and nothing else.
"""

import numpy as np
import pytest

from tests.conftest_ff import water
from xtal.core import p1
from xtal.ff import ENGINES
from xtal.ff.registry import Engine


def test_an_unknown_option_is_dropped_at_the_door(rutile):
    """UFF, which filtered nothing, raised a TypeError here -- at the
    moment Optimise was pressed."""
    calculator = ENGINES.build("uff", rutile, nonesuch=1)

    assert calculator.options.parameter_set


def test_every_engine_is_handed_exactly_what_it_declares(rutile):
    """Filled, typed and filtered once, by the registry, for every
    engine that declares options."""
    seen = {}

    def build(structure, **options):
        seen.update(options)
        return ENGINES.build("uff", structure)

    for engine in ENGINES:
        if not engine.options:
            continue
        seen.clear()
        stand_in = Engine(name=engine.name, label=engine.label,
                          description="", build=build,
                          options=engine.options)
        stand_in(rutile, nonesuch=1)
        assert set(seen) == {p.name for p in engine.options}, \
            engine.name


def test_dftb_and_xtb_share_one_external_base():
    from xtal.ff.dftb.calculator import DFTBCalculator
    from xtal.ff.external import ExternalCalculator
    from xtal.ff.xtb.calculator import XTBCalculator

    assert issubclass(DFTBCalculator, ExternalCalculator)
    assert issubclass(XTBCalculator, ExternalCalculator)


# ------------------------------------------------ an engine is a loader

def test_an_ase_engine_is_its_loader_and_nothing_else():
    """What the next machine-learned potential will be: a
    ``load_model`` and a ``summary``.  Lennard-Jones stands in for the
    model, and the base does the rest -- the order, the cell, the
    units, and a stress that agrees with the numeric one."""
    pytest.importorskip("ase")
    from ase.calculators.lj import LennardJones

    from xtal.ff.ase_engine import KCAL_PER_EV, ASECalculator

    class Pairwise(ASECalculator):
        name = "lj"
        label = "Lennard-Jones"

        def load_model(self, options):
            return LennardJones(sigma=2.5, epsilon=0.01, rc=6.0)

        def summary(self) -> str:
            return "Lennard-Jones"

    structure = water()
    engine = Pairwise(structure, options=None)
    cell = p1.expand(structure)
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    result = engine.compute(cell.cart, matrix)
    assert engine.calls == 1

    reference = LennardJones(sigma=2.5, epsilon=0.01, rc=6.0)
    engine._atoms.calc = reference
    assert result.energy == pytest.approx(
        engine._atoms.get_potential_energy() * KCAL_PER_EV)
    assert np.allclose(result.stress,
                       engine.numeric_stress(cell.cart, matrix,
                                             strain=1e-5),
                       atol=1e-6)


def test_every_engine_says_where_its_method_comes_from():
    """The panel links these under the chooser; an engine registered
    without them is a method nobody can trace back to its paper."""
    from xtal.ff import ENGINES

    for engine in ENGINES:
        cited = engine.sources(**engine.defaults())
        assert cited, engine.name
        for reference in cited:
            assert reference.label
            assert reference.url.startswith((
                "https://doi.org/", "https://arxiv.org/abs/",
                "https://github.com/")), reference


def test_the_references_follow_the_options_that_choose_the_method():
    """UFF4MOF is not UFF's paper, GFN-FF is not GFN2's, and a charge
    scheme is cited only while it is doing the charges."""
    from xtal.ff import ENGINES

    def urls(name, **options):
        return {r.url for r in ENGINES.get(name).sources(**options)}

    uff = "https://doi.org/10.1021/ja00051a040"
    addicoat = "https://doi.org/10.1021/ct400952t"
    eqeq = "https://doi.org/10.1021/jz3008485"
    assert {uff, addicoat} <= urls("uff", parameter_set="uff4mof")
    assert urls("uff", parameter_set="uff") == {uff}
    assert eqeq not in urls("uff", coulomb=False, charges="eqeq")
    assert eqeq in urls("uff", coulomb=True, charges="eqeq")

    assert "https://github.com/grimme-lab/xtb" in urls(
        "xtb", method="gfnff")
    assert "https://github.com/tblite/tblite" in urls("xtb",
                                                      method="gfn2")
    assert "https://doi.org/10.1103/PhysRevB.58.7260" in urls(
        "dftb", method="scc")
    assert "https://doi.org/10.1063/1.3382344" in urls(
        "dftb", dispersion="d3")


def test_a_references_function_that_fails_costs_the_links_only():
    """They are drawn on every refresh of the panel, as availability
    is, and must not take the panel with them."""
    from xtal.ff.registry import Engine

    def broken(**_options):
        raise RuntimeError("no")

    engine = Engine("x", "X", "", build=lambda s: None,
                    references=broken)
    assert engine.sources() == ()
