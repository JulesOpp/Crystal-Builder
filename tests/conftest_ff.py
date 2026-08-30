"""Molecules for the force-field tests.

Built from ideal internal coordinates rather than read from files, so
that a test that says "ethane's barrier is 3 kcal/mol" is starting from
an ethane and not from whatever a file happened to contain.  Everything
sits alone in a box large enough that no atom sees a periodic image of
itself, which is how a molecular test is run in a periodic code.
"""

from __future__ import annotations

import math

import numpy as np

from xtal import Lattice, Structure

BOX = 30.0


def isolated(symbols, cartesian, box: float = BOX) -> Structure:
    """One molecule in a big P1 box."""
    lattice = Lattice.cubic(box)
    return Structure.from_arrays(
        lattice, symbols, lattice.to_frac(np.asarray(cartesian,
                                                     dtype=float)),
        space_group="P1")


def water(oh: float = 0.9572, angle: float = 104.52) -> Structure:
    half = math.radians(angle)
    return isolated(["O", "H", "H"],
                    [[0.0, 0.0, 0.0],
                     [oh, 0.0, 0.0],
                     [oh * math.cos(half), oh * math.sin(half), 0.0]])


def ethane(cc: float = 1.526, ch: float = 1.09,
           twist: float = 60.0) -> Structure:
    """Two carbons up the z axis; ``twist`` is the H-C-C-H dihedral,
    60 for staggered and 0 for eclipsed."""
    cz = math.cos(math.radians(109.47))
    sz = math.sin(math.radians(109.47))
    symbols = ["C", "C"]
    positions = [[0.0, 0.0, 0.0], [0.0, 0.0, cc]]
    for k in range(3):
        a = math.radians(120 * k)
        positions.append([ch * sz * math.cos(a),
                          ch * sz * math.sin(a), ch * cz])
        symbols.append("H")
    for k in range(3):
        a = math.radians(120 * k + twist)
        positions.append([ch * sz * math.cos(a),
                          ch * sz * math.sin(a), cc - ch * cz])
        symbols.append("H")
    return isolated(symbols, positions)


def benzene(cc: float = 1.39, ch: float = 1.08,
            with_hydrogen: bool = True) -> Structure:
    """A flat, regular hexagon -- the geometry UFF should leave
    alone."""
    symbols, positions = [], []
    for k in range(6):
        angle = math.radians(60 * k)
        symbols.append("C")
        positions.append([cc * math.cos(angle), cc * math.sin(angle),
                          0.0])
    if with_hydrogen:
        for k in range(6):
            angle = math.radians(60 * k)
            symbols.append("H")
            positions.append([(cc + ch) * math.cos(angle),
                              (cc + ch) * math.sin(angle), 0.0])
    return isolated(symbols, positions)


def carbon_dioxide(co: float = 1.16) -> Structure:
    return isolated(["O", "C", "O"],
                    [[-co, 0, 0], [0, 0, 0], [co, 0, 0]])


def butadiene() -> Structure:
    """The carbon skeleton of s-trans butadiene, with no hydrogens --
    the shape an X-ray structure of it would have."""
    short, long_ = 1.34, 1.47
    a = math.radians(60)
    c0 = [0.0, 0.0, 0.0]
    c1 = [short, 0.0, 0.0]
    c2 = [short + long_ * math.cos(a), long_ * math.sin(a), 0.0]
    c3 = [c2[0] + short, c2[1], 0.0]
    return isolated(["C"] * 4, [c0, c1, c2, c3])


def methane(ch: float = 1.09) -> Structure:
    d = ch / math.sqrt(3.0)
    return isolated(["C", "H", "H", "H", "H"],
                    [[0, 0, 0], [d, d, d], [d, -d, -d],
                     [-d, d, -d], [-d, -d, d]])


def salt(a: float = 5.6402) -> Structure:
    """Rock salt, with formal charges set on the two sites."""
    structure = Structure.from_arrays(
        Lattice.cubic(a), ["Na", "Cl"],
        [[0, 0, 0], [0.5, 0.5, 0.5]], space_group="Fm-3m")
    structure.sites[0].charge = 1.0
    structure.sites[1].charge = -1.0
    return structure
