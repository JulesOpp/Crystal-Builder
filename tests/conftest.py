"""Shared fixtures: four real structures, chosen to cover the cases
that break crystallography code.

* rutile   -- tetragonal, two Wyckoff sites, a framework
* quartz   -- trigonal, non-orthogonal cell, an atom on a special
              position (Si is 3a, so its multiplicity is half the
              general one)
* halite   -- face-centred cubic, so centring translations matter
* dry ice  -- cubic but molecular: four discrete CO2 molecules
"""

import pytest

from xtal import Lattice, Structure

# Reference values from the literature, for tests that check we get
# real numbers out and not just self-consistent ones.
RUTILE_DENSITY = 4.25       # g/cm^3
QUARTZ_DENSITY = 2.65
QUARTZ_SI_O = 1.61          # Angstrom


@pytest.fixture
def rutile() -> Structure:
    """TiO2, P4_2/mnm (#136).  Ti on 2a, O on 4f."""
    return Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        ["Ti", "O"],
        [[0.0, 0.0, 0.0], [0.30530, 0.30530, 0.0]],
        space_group="P4_2/mnm")


@pytest.fixture
def quartz() -> Structure:
    """alpha-SiO2, P3_221 (#154).  Si sits on the 3a special position
    (x, 0, 2/3) -- the multiplicity is 3, not 6."""
    return Structure.from_arrays(
        Lattice.from_parameters(4.9134, 4.9134, 5.4052, 90, 90, 120),
        ["Si", "O"],
        [[0.4697, 0.0, 2 / 3], [0.4135, 0.2669, 0.7857]],
        space_group="P3221")


@pytest.fixture
def halite() -> Structure:
    """NaCl, Fm-3m (#225).  192 operations, F centring."""
    return Structure.from_arrays(
        Lattice.cubic(5.6402), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="Fm-3m")


@pytest.fixture
def dry_ice() -> Structure:
    """CO2, Pa-3 (#205): four discrete molecules in the cell."""
    return Structure.from_arrays(
        Lattice.cubic(5.624), ["C", "O"],
        [[0.0, 0.0, 0.0], [0.118, 0.118, 0.118]], space_group="Pa-3")


@pytest.fixture
def rutile_cif(tmp_path, rutile) -> str:
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    return str(path)
