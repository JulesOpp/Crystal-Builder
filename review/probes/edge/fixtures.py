"""Copies of the four conftest fixtures, as plain functions."""
from xtal.core.lattice import Lattice
from xtal.core.structure import Structure


def rutile():
    return Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        ["Ti", "O"],
        [[0.0, 0.0, 0.0], [0.30530, 0.30530, 0.0]],
        space_group="P4_2/mnm")


def quartz():
    return Structure.from_arrays(
        Lattice.from_parameters(4.9134, 4.9134, 5.4052, 90, 90, 120),
        ["Si", "O"],
        [[0.4697, 0.0, 2 / 3], [0.4135, 0.2669, 0.7857]],
        space_group="P3221")


def halite():
    return Structure.from_arrays(
        Lattice.cubic(5.6402), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="Fm-3m")


def dry_ice():
    return Structure.from_arrays(
        Lattice.cubic(5.624), ["C", "O"],
        [[0.0, 0.0, 0.0], [0.118, 0.118, 0.118]], space_group="Pa-3")


ALL = {"rutile": rutile, "quartz": quartz, "halite": halite,
       "dry_ice": dry_ice}
