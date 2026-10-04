"""
xtal.build.coordination
=======================
The shape a metal's neighbours take round it, for a drawn molecule.

ETKDG knows organic chemistry and no coordination chemistry: asked for
cisplatin it gave Cl-Pt-Cl angles of 97-120 degrees, and Fe(OH)6 came
out with angles of 65 to 151, with nothing to say either was wrong.
So the metal and the atoms bonded to it are put on an ideal polyhedron
first and the rest of the molecule is grown round them
(:func:`xtal.build.chem.embed`).

**The shape is the coordination number's, unless somebody chose.**  A
drawn metal with four neighbours is square planar if it is one of the
metals that are -- the d8 ions UFF types square planar only (Ni, Pd,
Pt, Au), Rh and Ir with them, and copper, whose Cu(II) is the case a
MOF chemist draws -- and tetrahedral otherwise.  Five neighbours one of
which is a metal is a square pyramid with the metal at the apex, which
is a paddlewheel; five otherwise is a trigonal bipyramid.  Right-click
a metal in the sketcher to say otherwise (``SketchAtom.shape``).

**Which neighbour goes on which vertex is chosen, not taken in order.**
A chelate's two donors must be cis -- en spanning a trans pair of an
octahedron is a ring that cannot close -- and a paddlewheel's metal
must be at the apex.  :func:`assign` tries every arrangement (at most
8! of them) and keeps the one that puts each chelate's donors closest
together.
"""

from __future__ import annotations

import itertools
import math

import numpy as np

from xtal.core import elements as el


def _unit(rows) -> np.ndarray:
    v = np.array(rows, dtype=float)
    return v / np.linalg.norm(v, axis=1)[:, None]


_T = 1.0 / math.sqrt(3.0)
_ANTI = math.radians(59.27)             # square antiprism's polar angle

#: Every shape a metal may be given: its name, what the menu says, and
#: the unit vectors of its vertices.  The first vertex of a square
#: pyramid is its apex.
SHAPES: dict[str, tuple[str, np.ndarray]] = {
    "linear": ("Linear", _unit([[1, 0, 0], [-1, 0, 0]])),
    "trigonal_planar": ("Trigonal planar", _unit(
        [[1, 0, 0], [-0.5, math.sqrt(3) / 2, 0],
         [-0.5, -math.sqrt(3) / 2, 0]])),
    "tetrahedral": ("Tetrahedral", _unit(
        [[_T, _T, _T], [_T, -_T, -_T], [-_T, _T, -_T], [-_T, -_T, _T]])),
    "square_planar": ("Square planar", _unit(
        [[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]])),
    "trigonal_bipyramidal": ("Trigonal bipyramidal", _unit(
        [[0, 0, 1], [0, 0, -1], [1, 0, 0],
         [-0.5, math.sqrt(3) / 2, 0], [-0.5, -math.sqrt(3) / 2, 0]])),
    "square_pyramidal": ("Square pyramidal", _unit(
        [[0, 0, 1], [1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]])),
    "octahedral": ("Octahedral", _unit(
        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
         [0, 0, 1], [0, 0, -1]])),
    "pentagonal_bipyramidal": ("Pentagonal bipyramidal", _unit(
        [[0, 0, 1], [0, 0, -1]]
        + [[math.cos(2 * math.pi * k / 5), math.sin(2 * math.pi * k / 5),
            0] for k in range(5)])),
    "square_antiprismatic": ("Square antiprismatic", _unit(
        [[math.sin(_ANTI) * math.cos(math.pi / 2 * k),
          math.sin(_ANTI) * math.sin(math.pi / 2 * k), math.cos(_ANTI)]
         for k in range(4)]
        + [[math.sin(_ANTI) * math.cos(math.pi / 2 * k + math.pi / 4),
            math.sin(_ANTI) * math.sin(math.pi / 2 * k + math.pi / 4),
            -math.cos(_ANTI)] for k in range(4)])),
    "cubic": ("Cubic", _unit(list(itertools.product((1, -1), repeat=3)))),
}

#: The shapes that have an apex, which a metal neighbour should take.
APEX = {"square_pyramidal": 0}

#: The metals with four neighbours drawn square planar by default.
SQUARE_PLANAR = frozenset({"Ni", "Pd", "Pt", "Au", "Rh", "Ir", "Cu"})

_DEFAULT = {2: "linear", 3: "trigonal_planar", 6: "octahedral",
            7: "pentagonal_bipyramidal", 8: "square_antiprismatic"}


def shapes_for(n_neighbours: int) -> list[str]:
    """The shapes a metal with this many neighbours could take."""
    return [name for name, (_label, v) in SHAPES.items()
            if len(v) == n_neighbours]


def default_shape(element: str, n_neighbours: int,
                  metal_neighbours: int = 0) -> str | None:
    """The shape a drawn metal is given when nobody chose one, or
    ``None`` for a count no polyhedron here has (a metal bonded to
    every carbon of two rings, which is a sandwich, not a shape)."""
    if n_neighbours == 4:
        return ("square_planar" if element in SQUARE_PLANAR
                else "tetrahedral")
    if n_neighbours == 5:
        return ("square_pyramidal" if metal_neighbours
                else "trigonal_bipyramidal")
    return _DEFAULT.get(n_neighbours)


def bond_length(metal: str, ligand: str) -> float:
    """Where a donor is put: the sum of the covalent radii, which the
    relax afterwards leaves alone (the donors are held), and which is
    within 0.1 A of Pt-Cl, Cu-N and Fe-O as crystals have them."""
    return el.covalent_radius(metal) + el.covalent_radius(ligand)


def assign(shape: str, chelated, apex_wanted=(),
           wanted=None) -> list[int]:
    """Which vertex each neighbour goes on: ``result[k]`` is the
    vertex of neighbour ``k``.

    ``chelated`` is pairs of neighbour indices joined through the
    ligand (a ring closes through the metal), which want the smallest
    angle the shape has between them; ``apex_wanted`` the neighbours
    that want its apex; ``wanted`` maps a pair to the cosine it should
    have -- what its partners across a bridge have on a metal placed
    already, which is what keeps a paddlewheel's two ends from
    twisting against each other.  Every arrangement is tried -- 40 320
    at most,
    for eight neighbours -- and the cheapest kept, the first of equals,
    so the answer is the same every time.
    """
    vectors = SHAPES[shape][1]
    n = len(vectors)
    cosines = vectors @ vectors.T
    apex = APEX.get(shape)
    chelated = [tuple(pair) for pair in chelated]
    wanted = dict(wanted or {})
    if not chelated and not wanted and (apex is None or not apex_wanted):
        return list(range(n))
    best, best_cost = list(range(n)), math.inf
    for order in itertools.permutations(range(n)):
        # A chelate's donors as close as the shape allows: the larger
        # the cosine between their vertices, the smaller the angle.
        cost = -sum(cosines[order[i], order[j]] for i, j in chelated)
        if apex is not None:
            cost += 10.0 * sum(order[k] != apex for k in apex_wanted)
        cost += 4.0 * sum((cosines[order[i], order[j]] - c) ** 2
                          for (i, j), c in wanted.items())
        if cost < best_cost - 1e-9:
            best, best_cost = list(order), cost
    return best


def angle_error(cart, metal: int, neighbours, shape: str,
                vertex_of) -> float:
    """The largest difference, in degrees, between a neighbour-metal-
    neighbour angle and the shape's -- how a build checks itself."""
    vectors = SHAPES[shape][1]
    centre = np.asarray(cart[metal], float)
    worst = 0.0
    for a, b in itertools.combinations(range(len(neighbours)), 2):
        u = np.asarray(cart[neighbours[a]], float) - centre
        v = np.asarray(cart[neighbours[b]], float) - centre
        cos = float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)))
        got = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
        ideal = math.degrees(math.acos(max(-1.0, min(1.0, float(
            vectors[vertex_of[a]] @ vectors[vertex_of[b]])))))
        worst = max(worst, abs(got - ideal))
    return worst
