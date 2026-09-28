"""DFTB+'s own stress against the numeric one, from the real binary.

The fake program in ``test_dftb.py`` covers the reading and the units;
only DFTB+ itself can say whether the tensor it prints is dE/de over
the volume or its negative.  That is the whole risk of taking it -- a
cell relaxed the wrong way that reports converging -- so it is asked
here, under a strain with every component different, against
:meth:`~xtal.ff.api.Calculator.numeric_stress` on the same calculator.

Skipped where DFTB+ is not installed or ``DFTB_PREFIX`` does not name a
Slater-Koster set with Na and Cl (3ob-3-1 does), which is CI.
"""

import numpy as np
import pytest

from xtal.core import p1
from xtal.ff.dftb import calculator as dftb
from xtal.ff.dftb import hsd


def _ready():
    directory = hsd.slater_koster_directory()
    return (dftb.PROGRAM.locate() is not None and directory is not None
            and (directory / "Na-Cl.skf").is_file())


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _ready(), reason="needs DFTB+ and 3ob"),
]


def test_dftbs_stress_is_the_negative_of_what_it_prints(halite):
    deform = np.array([[1.03, 0.02, 0.0],
                       [0.02, 0.99, -0.015],
                       [0.0, -0.015, 1.015]])
    matrix = halite.lattice.matrix @ deform
    positions = p1.expand(halite).frac @ matrix
    engine = dftb.build(halite)
    assert engine.provides_stress

    analytic = engine.compute(positions, matrix).stress
    numeric = engine.numeric_stress(positions, matrix)

    assert np.abs(numeric).max() > 1e-3        # a stress worth checking
    assert np.allclose(analytic, numeric,
                       atol=1e-4 * np.abs(numeric).max())
