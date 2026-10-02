"""The disordered-carbon builder's defaults against the ZTC they aim at.

The example is a fluorinated zeolite-templated carbon a ZTC group sent,
``JulesWork/ZTC-II+OFacch.cif``: private, never committed, so this is
skipped wherever it is absent -- CI, and every machine but one.  What
it measured set the defaults (2026-10-02): dia, as FAU's supercages
are, 2 x 2 x 2 of a 23.8 A cell, 0.418 g/cm3 of carbon, H/C 0.07,
F/C 0.29, O/C 0.044, 43 % edge carbon, rings 55 % hexagons.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from xtal.analysis import grid
from xtal.analysis.porosity import zeo_radius
from xtal.carbon import build as cb
from xtal.carbon import surface as sf
from xtal.core import p1, rings

EXAMPLE = Path(__file__).resolve().parent.parent / "JulesWork" / \
    "ZTC-II+OFacch.cif"

pytestmark = pytest.mark.skipif(not EXAMPLE.exists(),
                                reason="the example ZTC is private")


def pore_size_peak(structure, spacing: float = 0.7) -> float:
    """The peak of the volume-weighted geometric pore size
    distribution: every void grid point given the diameter of the
    largest maximal sphere containing it.  A histogram of the local
    maxima alone is a few hundred numbers and moved by two Angstrom
    between relaxations that left the pores alone."""
    field = grid.distance_grid(structure, zeo_radius, spacing=spacing)
    shape = np.array(field.shape)
    peak = (field == ndimage.maximum_filter(field, size=3, mode="wrap")) \
        & (field > 1.0)
    centres, radii = np.argwhere(peak) / shape, field[peak]
    void = np.argwhere(field > 0) / shape
    matrix = structure.lattice.matrix
    best = np.zeros(len(void))
    for centre, radius in sorted(zip(centres, radii, strict=True),
                                 key=lambda pair: pair[1]):
        delta = void - centre
        delta -= np.round(delta)
        delta = delta @ matrix
        best[np.einsum("ij,ij->i", delta, delta) <= radius ** 2] = \
            2 * radius
    counts, edges = np.histogram(best[best > 0],
                                 bins=np.arange(0.0, 30.0, 0.5))
    return float(edges[np.argmax(counts)] + 0.25)


def _measured(structure):
    cell = p1.expand(structure)
    count = Counter(cell.elements)
    census = rings.census(structure, max_size=10)
    return {
        "density": count["C"] / structure.lattice.volume
        / sf.ATOMS_PER_GCC,
        "H/C": count["H"] / count["C"], "O/C": count["O"] / count["C"],
        "hexagons": census.get(6, 0) / sum(census.values()),
    }


@pytest.mark.slow
def test_the_ztc_defaults_match_the_example():
    """The default recipe, relaxed a little, against the example: the
    carbon density within 3 %, H/C and O/C within 0.01, the share of
    hexagons within 0.1, one piece through the cell, and the pore size
    peak within 1 A.  Thirty seconds of building, so the relaxation is
    150 steps: the peak is the example's from there on."""
    from xtal.io.cif_reader import read_cif

    example = read_cif(EXAMPLE)
    built = cb.build(cb.Recipe(relax_steps=150))
    want, got = _measured(example), _measured(built.structure)
    assert got["density"] == pytest.approx(want["density"], rel=0.03)
    assert got["H/C"] == pytest.approx(want["H/C"], abs=0.01)
    assert got["O/C"] == pytest.approx(want["O/C"], abs=0.01)
    assert got["hexagons"] == pytest.approx(want["hexagons"], abs=0.1)
    assert built.pieces == 1 and built.periodicity == 3
    assert pore_size_peak(built.structure) == pytest.approx(
        pore_size_peak(example), abs=1.0)
