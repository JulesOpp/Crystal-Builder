"""
xtal.mof.rodnet
===============
Rods side by side: a 2D pattern of parallel rod axes, which hand each
rod is, and where each sits.

**Parallel rods, four patterns.**  The rod axes of nearly every rod MOF
cut a plane across them in one of four invariant patterns -- sql, hxl,
hcb, kgm -- with only two known exceptions (Schoedel *et al.*, Chem.
Rev. 2016, 116, 12466).  They are written here by hand, two lines each,
and a test holds each to the RCSR's own layer of that name.

**A hand is a colouring.**  A chiral rod placed on a pattern is either
the same hand everywhere or alternates, and which changes the net: 3_1
helices of one hand joined in threes are **eta**, alternating **etb**.
Alternating needs the pattern 2-coloured.  sql and hcb can be, and hxl
and kgm cannot -- each has triangles -- which is refused by name and
never approximated.  sql's colouring is a checkerboard that its
one-node cell cannot show, so the colouring carries the supercell it
needs (:func:`colouring`).  An achiral rod (MOF-303, MIL-53; see
:attr:`xtal.mof.rod.Rod.hand`) has no hand to alternate, and asking for
one is refused rather than ignored.

**The cell comes from the blocks.**  A rod's X atoms are grouped into
*faces*, as many to a face as the linker has points at each end, and a
face's reach is how far its middle is from the axis.  Neighbouring rods
are the reach of each, plus the linker's span, apart: a straight joint
with both X coincident, as every build here joins.  *c* is the rod's own
repeat.  Then each colour's turn about its axis and rise along it are
fitted so that every face looks along an edge of the pattern at a
partner the span away (:func:`placement`) -- along the joint for a
straight linker, and off it by the linker's own bend for a bent one
(:attr:`Ends.bend`): pzdc's carboxylates splay 13.6 degrees, and asked
to be straight, MOF-303 closed nowhere.  The rhombus of sql is
**the breathing coordinate** (MIL-53 opens and closes on it), so its
angle is a parameter: given, it is used; not given, it is solved from
where the rod's faces point, and the placement says which.  It is never
a default fixed without saying so.

Numpy and scipy; no Qt, no PORMAKE.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace

import numpy as np

from xtal.mof.rod import Rod


class RodNetError(ValueError):
    """A rod net that cannot be made as asked, said in a sentence."""


# ================================================================ patterns


@dataclass(frozen=True)
class Pattern:
    """Rod axes in a plane: nodes in a 2D cell, and the edges between
    neighbouring rods.

    ``spacing`` is the node-to-node distance in the pattern's own
    primitive cell with *a* = 1, and ``gamma`` that cell's angle;
    ``free`` says whether the angle may be chosen -- sql's rhombus --
    rather than fixed by the pattern's symmetry.  ``cell`` is the
    supercell the nodes are written in, rows in the primitive cell's
    terms: a checkerboard of a rhombus has unequal sides, so the
    supercell is kept as integers over the primitive cell rather than
    as a side and an angle of its own.
    """

    name: str
    nodes: tuple[tuple[float, float], ...]
    edges: tuple[tuple[int, int, tuple[int, int]], ...]
    gamma: float
    spacing: float
    free: bool = False
    colours: tuple[int, ...] = ()
    cell: tuple[tuple[int, int], tuple[int, int]] = ((1, 0), (0, 1))

    @property
    def degree(self) -> int:
        count = [0] * len(self.nodes)
        for u, v, _ in self.edges:
            count[u] += 1
            count[v] += 1
        return count[0]

    def matrix(self, a: float, gamma: float | None = None) -> np.ndarray:
        """The 2D cell the nodes are written in, rows *a* and *b*, for
        a primitive cell of side ``a`` and angle ``gamma``."""
        g = math.radians(self.gamma if gamma is None else gamma)
        primitive = a * np.array([[1.0, 0.0], [math.cos(g), math.sin(g)]])
        return np.array(self.cell, float) @ primitive


_S3 = math.sqrt(3.0)

PATTERNS = {
    "sql": Pattern("sql", ((0.0, 0.0),),
                   ((0, 0, (1, 0)), (0, 0, (0, 1))), 90.0, 1.0, True),
    "hxl": Pattern("hxl", ((0.0, 0.0),),
                   ((0, 0, (1, 0)), (0, 0, (0, 1)), (0, 0, (1, 1))),
                   120.0, 1.0),
    "hcb": Pattern("hcb", ((1 / 3, 2 / 3), (2 / 3, 1 / 3)),
                   ((0, 1, (0, 0)), (0, 1, (-1, 0)), (0, 1, (0, 1))),
                   120.0, 1 / _S3),
    "kgm": Pattern("kgm", ((0.5, 0.0), (0.0, 0.5), (0.5, 0.5)),
                   ((0, 1, (0, 0)), (0, 1, (1, -1)), (0, 2, (0, 0)),
                    (0, 2, (0, -1)), (1, 2, (0, 0)), (1, 2, (-1, 0))),
                   120.0, 0.5),
}


def pattern(name: str) -> Pattern:
    try:
        return PATTERNS[name]
    except KeyError:
        raise RodNetError(f"no rod pattern called {name}; the patterns "
                          f"are {', '.join(PATTERNS)}") from None


def as_net(p: Pattern):
    """The pattern as a 2-periodic :class:`~xtal.analysis.topology.Net`,
    to be named against the RCSR's layers."""
    from xtal.analysis.topology import Edge, Net

    return Net(len(p.nodes), tuple(Edge(u, v, (i, j, 0))
                                   for u, v, (i, j) in p.edges))


def colouring(p: Pattern) -> tuple[np.ndarray, tuple[int, ...]] | None:
    """A 2-colouring of the pattern, or ``None`` when it has odd rings.

    Returned as the supercell it needs (rows in the pattern's own cell)
    and a colour for each node of the pattern: a node's colour in cell
    *n* is its colour plus ``k . n``, and the supercell is the lattice
    on which that sum is even.  hcb is coloured in its own cell
    (``k = 0``); sql needs the checkerboard, ``k = (1, 1)``.
    """
    for k in ((0, 0), (1, 0), (0, 1), (1, 1)):
        colours = _two_colour(p, np.array(k))
        if colours is not None:
            return _parity_cell(k), colours
    return None


def _two_colour(p, k):
    colours = {0: 0}
    queue = deque([0])
    adjacent = [[] for _ in p.nodes]
    for u, v, image in p.edges:
        adjacent[u].append((v, np.array(image)))
        adjacent[v].append((u, -np.array(image)))
    while queue:
        u = queue.popleft()
        for v, image in adjacent[u]:
            want = (colours[u] + 1 + int(k @ image)) % 2
            if v not in colours:
                colours[v] = want
                queue.append(v)
            elif colours[v] != want:
                return None
    return tuple(colours[i] for i in range(len(p.nodes)))


def _parity_cell(k) -> np.ndarray:
    return {(0, 0): np.eye(2, dtype=int),
            (1, 0): np.array([[2, 0], [0, 1]]),
            (0, 1): np.array([[1, 0], [0, 2]]),
            (1, 1): np.array([[1, -1], [1, 1]])}[tuple(k)]


def supercell(p: Pattern, cell: np.ndarray,
              colours: tuple[int, ...] = ()) -> Pattern:
    """``p`` in the supercell whose rows are ``cell``, each node's
    colour carried (and flipped in the cells the parity says)."""
    cell = np.asarray(cell, int)
    det = int(round(abs(np.linalg.det(cell))))
    inverse = np.linalg.inv(cell)
    corners = np.array([[0, 0], cell[0], cell[1], cell[0] + cell[1]])
    lo, hi = corners.min(axis=0), corners.max(axis=0)
    shifts = []
    for i in range(lo[0], hi[0] + 1):
        for j in range(lo[1], hi[1] + 1):
            f = np.array([i, j]) @ inverse
            if np.all(f > -1e-9) and np.all(f < 1 - 1e-9):
                shifts.append((i, j))
    if len(shifts) != det:
        raise RodNetError("the supercell could not be enumerated")
    parity = None
    if colours:
        for k in ((0, 0), (1, 0), (0, 1), (1, 1)):
            if _two_colour(p, np.array(k)) == tuple(colours):
                parity = np.array(k)
                break
    nodes, index, new_colours = [], {}, []
    for s in shifts:
        for n, (x, y) in enumerate(p.nodes):
            f = (np.array([x, y]) + s) @ inverse
            index[(n, s)] = len(nodes)
            nodes.append(tuple(float(v) % 1.0 for v in f))
            if parity is not None:
                new_colours.append((colours[n] + int(parity @ s)) % 2)
    edges = []
    for s in shifts:
        for u, v, image in p.edges:
            target = np.array(s) + image
            f = target @ inverse
            whole = np.floor(f + 1e-9).astype(int)
            home = tuple(int(t) for t in target - whole @ cell)
            edges.append((index[(u, s)], index[(v, home)],
                          tuple(int(w) for w in whole)))
    return Pattern(p.name, tuple(nodes), tuple(edges), p.gamma,
                   p.spacing, p.free, tuple(new_colours),
                   tuple(tuple(int(v) for v in row)
                         for row in cell @ np.array(p.cell, int)))


# =================================================================== hands

HANDS = ("auto", "same", "alternating")


@dataclass(frozen=True)
class RodNet:
    """A pattern with a hand for every node's rod."""

    pattern: Pattern
    hands: str
    #: 0 for the rod as given, 1 for its mirror image (or, for an
    #: achiral rod, the same rod turned on its own).
    colours: tuple[int, ...]

    @property
    def nodes(self) -> int:
        return len(self.pattern.nodes)


def rod_net(name: str, rod: Rod, hands: str = "auto") -> RodNet:
    """The rods of ``rod`` on pattern ``name``, handed as asked.

    ``auto`` alternates a chiral rod where the pattern allows -- both
    chiral rods shipped alternate in their crystals (E0: MOF-74 and
    Ni2Cl2BTDD on hcb) -- and is "same" otherwise.
    """
    if hands not in HANDS:
        raise RodNetError(f"hands is one of {', '.join(HANDS)}, not "
                          f"{hands}")
    p = pattern(name)
    chiral = rod.hand is not None
    if hands == "alternating" and not chiral:
        raise RodNetError(f"{rod.name or 'this rod'} has no hand -- a "
                          f"mirror, inversion or glide of its own maps "
                          f"it onto its mirror image -- so its rods "
                          f"cannot alternate hands")
    found = colouring(p)
    if hands == "alternating" and found is None:
        raise RodNetError(f"{name} has odd rings (triangles), so its "
                          f"rods cannot alternate hands; choose same")
    if hands == "auto":
        hands = "alternating" if chiral and found is not None else "same"
    if hands == "same":
        return RodNet(p, "same", (0,) * len(p.nodes))
    cell, colours = found
    p = supercell(p, cell, colours)
    return RodNet(p, "alternating", p.colours)


# =============================================================== placement


@dataclass(frozen=True)
class Face:
    """Points of extension that meet one end of one linker."""

    members: tuple[tuple[int, int], ...]     # X atom and its shift
    middle: np.ndarray                       # in the rod's frame
    #: Which way a linker leaves: the bond onto each X, from the atoms
    #: it hangs off, averaged.  Not the radial line -- a carboxylate's
    #: C-C leaves MIL-53's rod well off it.
    outward: np.ndarray = None

    @property
    def reach(self) -> float:
        return float(np.linalg.norm(self.middle[:2]))

    @property
    def azimuth(self) -> float:
        return math.degrees(math.atan2(self.middle[1], self.middle[0]))


@dataclass(frozen=True)
class Ends:
    """A linker as its two ends: the X atoms at each, and the span
    between the ends' middles.

    ``bend`` is how far, in radians, the bond into the linker at an end
    leaves the line between the ends -- 0 for BDC, 0.24 (13.6 degrees)
    for pzdc, whose carboxylates splay from a five-ring -- the mean of
    the two ends, since a joint is met from either.  ``twist`` is the angle
    between the two ends' bonds seen along that line: 0 where both
    bend the same way, as a flat bent linker does.
    """

    positions: np.ndarray
    ends: tuple[tuple[int, ...], tuple[int, ...]]
    bend: float = 0.0
    twist: float = 0.0

    @property
    def size(self) -> int:
        return len(self.ends[0])

    @property
    def span(self) -> float:
        a = self.positions[list(self.ends[0])].mean(axis=0)
        b = self.positions[list(self.ends[1])].mean(axis=0)
        return float(np.linalg.norm(b - a))


def ends_of(block) -> Ends:
    """``block`` (anything with ``positions`` and ``connections``) split
    into two ends along its longest axis."""
    points = list(block.connections)
    if len(points) < 2 or len(points) % 2:
        raise RodNetError(f"a linker between two rods needs an even "
                          f"number of points, not {len(points)}")
    xyz = np.asarray(block.positions, float)[points]
    centred = xyz - xyz.mean(axis=0)
    axis = np.linalg.svd(centred)[2][0]
    order = np.argsort(centred @ axis)
    half = len(points) // 2
    ends = (tuple(points[i] for i in sorted(order[:half])),
            tuple(points[i] for i in sorted(order[half:])))
    positions = np.asarray(block.positions, float)
    if not hasattr(block, "neighbours"):
        return Ends(positions, ends)
    middles = [positions[list(e)].mean(axis=0) for e in ends]
    line = middles[1] - middles[0]
    line /= np.linalg.norm(line)
    into = []
    for end, middle in zip(ends, middles, strict=True):
        members = [a for x in end for a in block.neighbours(x)
                   if block.symbols[a] != "X"]
        if not members:
            return Ends(positions, ends)
        step = positions[members].mean(axis=0) - middle
        into.append(step / np.linalg.norm(step))
    bend = (_angle(into[0], line) + _angle(into[1], -line)) / 2
    return Ends(positions, ends, bend, _twist(into[0], into[1], line))


def _angle(a, b) -> float:
    return float(np.arccos(np.clip(a @ b, -1.0, 1.0)))


def _twist(a, b, line) -> float:
    """The unsigned angle between ``a`` and ``b`` seen along ``line``,
    0 when either is along it."""
    a, b = a - (a @ line) * line, b - (b @ line) * line
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return _angle(a / na, b / nb)


def linker_points(rod: Rod) -> int:
    """How many points a linker for ``rod`` has: one face at each end."""
    return 2 * rod.face


def mismatch(rod: Rod, linker, size: int) -> str:
    """Why ``linker``, ``size`` points at each end, does not fit
    ``rod``, said by name.

    Without it a two-point linker on MOF-74 was paired with one X of a
    chelate each and failed at the joints, 2 A off, naming neither.
    """
    name = getattr(linker, "name", "") or "the linker"
    each = "point" if rod.face == 1 else "points"
    why = (" (a chelate: the rod holds the donors, so the linker's X "
           "atoms go where they join it)" if rod.face > 1 else "")
    return (f"{rod.name or 'the rod'} meets each end of a linker at "
            f"{rod.face} {each}{why}, so its linker has "
            f"{linker_points(rod)} in all; {name} has {size} at each "
            f"end, {2 * size} in all")


def unmet_kinds(rod: Rod, linker, ends: Ends, rod_faces) -> str:
    """Why ``linker``'s named points cannot meet ``rod``'s, or ``""``.

    An end's points named by their donor (:mod:`xtal.mof.donors`) must
    each find a rod point of that kind in every face; a point drawn
    bare finds any.  Said before anything is fitted, since a joint
    with no pairing left has nothing to say for itself.
    """
    from xtal.mof import donors

    named = dict(zip(getattr(linker, "connections", ()),
                     getattr(linker, "kinds", ()), strict=False))
    if not any(named.values()):
        return ""
    for face in rod_faces:
        have = [rod.kind(x) for x, _up in face.members]
        for end in ends.ends:
            want = [named.get(x, "") for x in end]
            spare = list(have)
            for kind in want:
                if not kind:
                    continue
                if kind not in spare:
                    name = getattr(linker, "name", "") or "the linker"
                    return (f"{name} brings {donors.described(want)} to "
                            f"each end, where {rod.name or 'the rod'} "
                            f"has {donors.described(have)}")
                spare.remove(kind)
    return ""


def faces(rod: Rod, size: int) -> list[Face]:
    """The rod's X atoms in faces of ``size``, nearest together first.

    One X is one face.  Two (dobdc's carboxylate and phenolate) are
    paired greedily by distance, the next repeat counted, so that each
    X is in exactly one face.
    """
    points = rod.connections
    if len(points) % size:
        raise RodNetError(f"{rod.name or 'the rod'} has {len(points)} "
                          f"points a repeat, which do not make faces of "
                          f"{size}")
    rise = np.array([0.0, 0.0, rod.repeat])
    if size == 1:
        return [Face(((x, 0),), rod.positions[x], _leaving(rod, [x]))
                for x in points]
    if size != 2:
        raise RodNetError("faces of more than two points are not made")
    pairs = []
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            for k in (-1, 0, 1):
                gap = np.linalg.norm(rod.positions[b] + k * rise
                                     - rod.positions[a])
                pairs.append((float(gap), a, b, k))
    pairs.sort()
    used, found = set(), []
    for _gap, a, b, k in pairs:
        if a in used or b in used:
            continue
        used |= {a, b}
        middle = (rod.positions[a] + rod.positions[b] + k * rise) / 2
        found.append(Face(((a, 0), (b, k)), middle,
                          _leaving(rod, [a, b])))
    return found


def _leaving(rod: Rod, points) -> np.ndarray:
    """The unit direction a linker leaves ``points`` along."""
    rise = np.array([0.0, 0.0, rod.repeat])
    total = np.zeros(3)
    for x in points:
        members = rod.members(x)
        hung = np.mean([rod.positions[m] + k * rise for m, k in members],
                       axis=0)
        step = rod.positions[x] - hung
        total += step / np.linalg.norm(step)
    return total / np.linalg.norm(total)


@dataclass(frozen=True)
class Match:
    """Face ``face`` of node ``node``'s rod meets face ``partner`` of
    node ``other``'s, that rod moved by ``shift``: whole cells along
    *a* and *b* of the pattern's cell, and whole repeats along *c*."""

    node: int
    face: int
    other: int
    partner: int
    shift: tuple[int, int, int]


@dataclass
class Placement:
    """Where every rod of a :class:`RodNet` goes, and the cell.

    The in-plane rows of the cell rise along *c* as well
    (``shears``): rods a translation apart need not be at one height,
    and in MIL-53 (I-centred) they are half a repeat apart, in MOF-74
    (R-centred) a third.  Each node's rod has its own rise on top.
    """

    net: RodNet
    rods: tuple[Rod, Rod]                 # colour 0 and colour 1
    linker: Ends
    a: float                              # the primitive pattern's side
    c: float
    gamma: float                          # and its angle
    angle_from: str
    turns: tuple[float, float]            # degrees, by colour
    rises: tuple[float, ...]              # A, by node
    shears: tuple[float, float]           # A, rise of rows a and b
    cost: float
    reach: float
    joints: list = field(default_factory=list)
    #: Whether the second colour's rod is turned over (a half turn
    #: across its axis) as well as turned about it.
    turned_over: bool = False
    #: Which face meets which, one :class:`Match` per face of every
    #: node, so each joint is here twice -- once from either end.
    matches: list = field(default_factory=list)
    #: The linker turned about the bonds between its ends as it was
    #: placed (:func:`poses`), or ``None`` for as drawn.
    posed: object = None

    @property
    def spacing(self) -> float:
        return self.a * self.net.pattern.spacing

    @property
    def rows(self) -> np.ndarray:
        """The cell, rows *a*, *b*, *c*, Cartesian, *c* along *z*."""
        flat = self.net.pattern.matrix(self.a, self.gamma)
        return np.array([[*flat[0], self.shears[0]],
                         [*flat[1], self.shears[1]],
                         [0.0, 0.0, self.c]])

    @property
    def cell(self) -> tuple[float, ...]:
        """``(a, b, c, alpha, beta, gamma)``."""
        a, b, c = self.rows
        n = [float(np.linalg.norm(v)) for v in (a, b, c)]

        def angle(u, v, nu, nv):
            return math.degrees(math.acos(float(u @ v) / nu / nv))

        return (n[0], n[1], n[2], angle(b, c, n[1], n[2]),
                angle(a, c, n[0], n[2]), angle(a, b, n[0], n[1]))

    @property
    def worst(self) -> float:
        return max((j[2] for j in self.joints), default=0.0)

    def sentence(self) -> str:
        p = self.net.pattern
        a, b, c, al, be, ga = self.cell
        return (f"{p.name}, {self.net.nodes} rod"
                f"{'s' if self.net.nodes != 1 else ''} a cell, hands "
                f"{self.net.hands}"
                f"{', every other turned over' if self.turned_over else ''}"
                f": a {a:.3f} b {b:.3f} c {c:.3f} A, "
                f"{al:.1f} {be:.1f} {ga:.1f} degrees, rows rising "
                f"{self.shears[0] / self.c:.2f} and "
                f"{self.shears[1] / self.c:.2f} of c; the pattern's "
                f"angle {self.gamma:.1f} ({self.angle_from}); rods "
                f"{self.spacing:.3f} A apart, for a reach of "
                f"{self.reach:.2f} and a span of {self.linker.span:.2f}"
                f"; worst joint {self.worst:.2f} A off")


#: Turns tried for each colour before refining, degrees.
_TURN_STEP = 10.0
#: Rises and shears tried, as fractions of the repeat.
_RISE_STEPS = 4
#: Angles a free pattern is started from, degrees.
_ANGLES = (60.0, 75.0, 90.0, 105.0, 120.0)
#: A placement whose cost is below this closes every joint, A^2; the
#: rest of the options are not tried.
CLOSED = 1e-4
#: How many of the best starting points are refined.
_STARTS = 5
#: How many starts are costed in one batch of arrays.
_CHUNK = 4096
#: The range a free angle stays in, degrees.
FREE_ANGLES = (45.0, 135.0)
#: Placements whose costs are within this, A^2, are a tie, and the
#: smaller angle wins it.  A rhombus is the same at 75 degrees and at
#: 105 from its other corner, and a 1e-4 A rounding in BDC's file
#: was enough to send MIL-53 from one description to the other.
TIE = 5e-5


#: The turns about a bond between a linker's ends that are tried, in
#: degrees: every :data:`TURN_STEP` round, the drawing's own first.
TURN_STEP = 10

#: The finer step :func:`poses` turns by, degrees.
POSE_STEP = 5

#: How many turns nearest the symmetry's twist are placed and built,
#: the best kept.  Placement is sensitive near it: pc-dobpdc posed at
#: 179.5 degrees put a ring hydrogen 0.95 A from a rod oxygen, and at
#: 178.7 built with joints of 1.47 A.
POSES = 3

#: The twists, degrees, tried first where the rods' symmetry leaves a
#: linker's twist free (:func:`wanted_twist` is ``None``), then
#: :data:`FREE_REFINE` either side of the best.  Zn2(dobpdc)'s twist
#: is 128 degrees, and a twist of 0 built it 6 % small.
FREE_TWISTS = (0, 45, 90, 135, 180)
FREE_REFINE = 15

#: Two atoms of a turned linker three or more bonds apart may come no
#: closer than this, A; a planar biphenyl's ortho hydrogens are 2.0.
TURN_CLEAR = 1.5


def _turning_bonds(linker, ends) -> list[tuple[int, int]]:
    """The single bonds on the path between the linker's two ends
    that are in no ring: what a drawn linker may be turned about
    (dobpdc's biaryl bond).  Each is ``(a, b)`` with ``b`` on the side
    of the second end."""
    near = defaultdict(set)
    for i, j, _letter in linker.bonds:
        near[i].add(j)
        near[j].add(i)
    start, goal = ends.ends[0][0], set(ends.ends[1])
    back, queue = {start: None}, deque([start])
    while queue:
        a = queue.popleft()
        for n in near[a]:
            if n not in back:
                back[n] = a
                queue.append(n)
    end = next((x for x in ends.ends[1] if x in back), None)
    if end is None:
        return []
    path = [end]
    while back[path[-1]] is not None:
        path.append(back[path[-1]])
    path.reverse()
    single = {tuple(sorted((i, j))) for i, j, letter in linker.bonds
              if letter == "S"}
    found = []
    for a, b in zip(path, path[1:], strict=False):
        if tuple(sorted((a, b))) not in single:
            continue
        if len(near[a]) < 2 or len(near[b]) < 2:
            continue
        side = _side(near, b, a)
        if goal <= side and not (side & set(ends.ends[0])):
            found.append((a, b))
    return found


def can_turn(linker) -> bool:
    """Whether :func:`poses` can turn ``linker``: points at each end
    more than one, and a bond between the ends to turn about."""
    if not hasattr(linker, "bonds"):
        return False
    ends = ends_of(linker)
    return ends.size > 1 and bool(_turning_bonds(linker, ends))


def _side(near, start, cut) -> set[int]:
    """The atoms reached from ``start`` without crossing to ``cut``;
    ``cut`` among them means the bond is in a ring."""
    seen, queue = {start}, deque([start])
    while queue:
        a = queue.popleft()
        for n in near[a]:
            if n not in seen and not (a == start and n == cut):
                seen.add(n)
                queue.append(n)
    return seen


def conformers(linker, ends, step: int = TURN_STEP):
    """The linker turned about each bond of :func:`_turning_bonds`, one
    bond at a time, every ``step`` degrees, leaving out any
    turn that brings two of its atoms within :data:`TURN_CLEAR`.

    A drawing's turn is the embedder's, not the crystal's: RDKit
    left dobpdc's rings 32 degrees apart and pc-dobpdc's donors on one
    side.  :func:`poses` picks those placement starts from, and the
    build refines it against the joints.
    """
    near = defaultdict(set)
    for i, j, _letter in linker.bonds:
        near[i].add(j)
        near[j].add(i)
    xyz = np.asarray(linker.positions, float)
    far = _far_pairs(near, len(xyz))
    for a, b in _turning_bonds(linker, ends):
        side = sorted(_side(near, b, a))
        axis = xyz[b] - xyz[a]
        axis /= np.linalg.norm(axis)
        for degrees in range(step, 360, step):
            moved = xyz.copy()
            turn = _about(axis, math.radians(degrees))
            moved[side] = (xyz[side] - xyz[b]) @ turn.T + xyz[b]
            gaps = np.linalg.norm(moved[far[:, 0]] - moved[far[:, 1]],
                                  axis=1)
            if len(gaps) and gaps.min() < TURN_CLEAR:
                continue
            yield replace(linker, positions=moved)


def _far_pairs(near, n) -> np.ndarray:
    """Every pair of atoms three or more bonds apart, ``X`` included."""
    pairs = []
    for a in range(n):
        seen, frontier = {a}, {a}
        for _ in range(2):
            frontier = {m for f in frontier for m in near[f]} - seen
            seen |= frontier
        pairs.extend((a, b) for b in range(a + 1, n) if b not in seen)
    return np.array(pairs, dtype=int).reshape(-1, 2)



def _about(axis, angle) -> np.ndarray:
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]],
                  [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k



def poses(linker, ends: Ends, twist: float) -> list:
    """Up to :data:`POSES` conformers of ``linker`` -- turned about the
    bonds between its ends, :data:`POSE_STEP` apart -- whose ends'
    :attr:`Ends.twist` is nearest ``twist`` (radians), nearest first,
    each with its ``Ends``; empty when it cannot turn.

    The turn decides the placement through the twist, and the
    placement the net: dobpdc as RDKit drew it, 34 degrees, read msg
    with joints of 2.28 A, and turned to 177 degrees, 1.43 A; pc-dobpdc
    as drawn, 94 degrees, read a net that is not in the RCSR.  Placing
    every turn costs 1.5 s each, so the turns tried are the ones the
    joined rods' symmetry asks for (:func:`placement`).
    """
    found = [(_gap(its.twist, twist), k, turned, its)
             for k, (turned, its) in enumerate(
                 (t, ends_of(t)) for t in conformers(linker, ends,
                                                       POSE_STEP))]
    found.append((_gap(ends.twist, twist), -1, linker, ends))
    found.sort(key=lambda row: (row[0], row[1]))
    return [(turned, its) for _gap_, _k, turned, its in found[:POSES]]


def wanted_twist(net, rod: Rod) -> float | None:
    """The twist between a linker's ends that the rods it joins ask
    for, or ``None`` where they leave it free.

    The linker sits on what relates them.  An inversion centre, where
    neighbours alternate hands (MOF-74, R-3), takes each end's bond
    onto the other's reversed: the ends a half turn apart, exactly.  A
    two-fold axis across the line between the ends, where they are one
    hand (Zn2(dobpdc), P3_121), takes it onto the other's turned about
    that axis, and the axis may point any way round the line: any
    twist.  It was 0 here, which built Zn2(dobpdc) with a 20.35 A cell
    for the crystal's 21.66; its linker's twist is 128 degrees.
    """
    if net.hands == "same" and rod.hand is not None:
        return None
    return math.pi


def _gap(a: float, b: float) -> float:
    return abs(math.remainder(a - b, 2 * math.pi))



def placement(net: RodNet, rod: Rod, linker, *,
              angle: float | None = None, pose: int = 0,
              twist: float | None = None) -> Placement:
    """Solve the cell, and each rod's turn and rise, for ``rod`` on
    ``net`` joined by ``linker`` (a block, or :class:`Ends`).

    ``angle`` is sql's rhombus angle.  Given, it is used; ``None``, it
    is the one the rod's faces fit best, and :attr:`Placement.angle_from`
    says which.  For a pattern whose angle is fixed by symmetry, giving
    one is refused.  ``pose`` is which of :func:`poses` a linker that
    can turn about the bonds between its ends is placed in, the
    nearest the rods' symmetry first; :func:`xtal.mof.rodbuild.
    best_placement` tries each.  ``twist`` (radians) is the twist the
    poses are nearest instead of the symmetry's -- needed where
    :func:`wanted_twist` leaves it free, which is otherwise taken as
    the first of :data:`FREE_TWISTS`.
    """
    ends = linker if isinstance(linker, Ends) else ends_of(linker)
    if ends.size != rod.face:
        raise RodNetError(mismatch(rod, linker, ends.size))
    posed = None
    if not isinstance(linker, Ends) and ends.size > 1:
        if twist is None:
            twist = wanted_twist(net, rod)
        if twist is None:
            twist = math.radians(FREE_TWISTS[0])
        found = poses(linker, ends, twist)
        if pose < len(found) and found[pose][0] is not linker:
            posed, ends = found[pose]
    p = net.pattern
    rod_faces = faces(rod, ends.size)
    unmet = unmet_kinds(rod, linker, ends, rod_faces)
    if unmet:
        raise RodNetError(unmet)
    degree = PATTERNS[p.name].degree
    if len(rod_faces) % degree:
        raise RodNetError(
            f"{rod.name or 'the rod'} has {len(rod_faces)} faces a "
            f"repeat and {p.name} gives each rod {degree} neighbours: "
            f"they must divide")
    if angle is not None and not p.free:
        raise RodNetError(f"{p.name}'s angle is fixed by its symmetry "
                          f"at {PATTERNS[p.name].gamma:g} degrees")
    if angle is not None and not FREE_ANGLES[0] <= angle <= FREE_ANGLES[1]:
        raise RodNetError(f"a rhombus angle is between {FREE_ANGLES[0]:g}"
                          f" and {FREE_ANGLES[1]:g} degrees")
    reach = float(np.mean([f.reach for f in rod_faces]))
    a = (2 * reach + ends.span) / p.spacing
    second = rod.mirror() if net.hands == "alternating" else rod
    # The second colour may be the rod turned over as well as turned:
    # same-handed 3_1 helices on hcb are eta only so, a two-fold axis
    # across the rods relating neighbours (P6_222).
    options = [second]
    if len(set(net.colours)) > 1:
        options.append(second.turned_over())
    elif net.hands == "same" and colouring(p) is not None:
        options.append(rod.turned_over())
    if angle is not None:
        said, free = "given", False
        gammas = (float(angle),)
    elif p.free:
        said, free = "from the rod's faces", True
        gammas = _ANGLES
    else:
        said, free = "fixed by the pattern", False
        gammas = (p.gamma,)
    best = None
    for k, option in enumerate(options):
        if best is not None and best[0] < CLOSED:
            break
        trial_net = net
        if len(set(net.colours)) == 1 and k > 0:
            cell, colours = colouring(p)
            trial_net = RodNet(supercell(p, cell, colours), net.hands,
                               supercell(p, cell, colours).colours)
        model = _Model(trial_net.pattern, trial_net.colours,
                       (rod_faces, faces(option, ends.size)),
                       rod.repeat, ends.span, a, ends.bend, ends.twist)
        x, gamma, cost = model.fit(gammas, free)
        if best is None or cost < best[0] - CLOSED:
            best = (cost, x, gamma, model, trial_net, option, k > 0)
    cost, x, gamma, model, net, second, over = best
    turns, rises, shears, a = model.unpack(x)
    return Placement(net, (rod, second), ends, a, rod.repeat, gamma,
                     said, turns, rises, shears, cost, reach,
                     model.joints(x, gamma), over,
                     model.matches(x, gamma), posed)


def _better(found, best) -> bool:
    """Whether placement ``found`` beats ``best``, each ``(cost, x,
    gamma)``: cheaper, but between two angles that tie on cost
    (:data:`TIE`) the smaller."""
    if abs(found[2] - best[2]) < 1e-6 or abs(found[0] - best[0]) > TIE:
        return found[0] < best[0]
    return found[2] < best[2]


class _Model:
    """The cost of a placement and its search.

    ``x`` is the colours' two turns, a rise for every node but the
    first, and the two shears; a free angle rides at the end of it.
    """

    def __init__(self, p, colours, sets, repeat, span, a, bend=0.0,
                 twist=0.0):
        self.p, self.colours, self.repeat = p, colours, repeat
        self.span, self.a = span, a
        self.bend, self.twist = bend, twist
        self.middles = [np.array([f.middle for f in s]) for s in sets]
        self.outwards = [np.array([f.outward for f in s]) for s in sets]
        self.n = len(p.nodes)
        self.edges = [[] for _ in p.nodes]
        for u, v, image in p.edges:
            self.edges[u].append((v, np.array(image, float)))
            self.edges[v].append((u, -np.array(image, float)))
        self.frac = np.array(p.nodes, float)

    def unpack(self, x):
        """``(turns, rises, shears, a)``: ``x`` ends with how far the
        side has been stretched from where the reaches put it."""
        turns = (float(x[0]), float(x[1]))
        rises = (0.0, *(float(v) for v in x[2:2 + self.n - 1]))
        shears = (float(x[1 + self.n]), float(x[2 + self.n]))
        return turns, rises, shears, self.a * (1.0 + float(x[3 + self.n]))

    @staticmethod
    def _turn(m, turn):
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        out = np.empty_like(m)
        out[:, 0] = c * m[:, 0] - s * m[:, 1]
        out[:, 1] = s * m[:, 0] + c * m[:, 1]
        out[:, 2] = m[:, 2]
        return out

    def pairs(self, x, gamma):
        """Each face and the partner face it meets, positions and
        outward directions, as four arrays."""
        return self._pairs(x, gamma)[:4]

    def matches(self, x, gamma) -> list[Match]:
        """Which face meets which: the identities behind
        :meth:`pairs`, in the same order."""
        return self._pairs(x, gamma, identify=True)[4]

    def _pairs(self, x, gamma, identify=False):
        # Called a hundred thousand times by the search, so a match is
        # only named when asked for.  Taking a rod's faces together,
        # edge by edge, was measured slower: there are four to eight.
        turns, rises, shears, a = self.unpack(x)
        flat = self.p.matrix(a, gamma)
        rows = np.array([[*flat[0], shears[0]], [*flat[1], shears[1]]])
        placed = [self._turn(self.middles[k], turns[k]) for k in (0, 1)]
        leaving = [self._turn(self.outwards[k], turns[k]) for k in (0, 1)]
        here_all, out_all, there_all, back_all = [], [], [], []
        found = []
        for u in range(self.n):
            centre = self.frac[u] @ rows
            centre = centre + [0.0, 0.0, rises[u]]
            mine = placed[self.colours[u]] + centre
            outward = leaving[self.colours[u]]
            level = outward[:, :2] / np.linalg.norm(outward[:, :2],
                                                    axis=1)[:, None]
            gaps = np.array([(self.frac[v] + image - self.frac[u]) @ rows
                             + [0.0, 0.0, rises[v] - rises[u]]
                             for v, image in self.edges[u]])
            flat_gaps = gaps[:, :2] / np.linalg.norm(gaps[:, :2],
                                                     axis=1)[:, None]
            chosen = np.argmax(level @ flat_gaps.T, axis=1)
            for f, e in enumerate(chosen):
                v, image = self.edges[u][e]
                other = centre + gaps[e]
                theirs = placed[self.colours[v]] + other
                dz = theirs[:, 2] - mine[f, 2]
                up = np.round(dz / self.repeat)
                theirs[:, 2] -= self.repeat * up
                d = np.linalg.norm(theirs - mine[f], axis=1)
                g = int(np.argmin(d))
                if identify:
                    found.append(Match(u, f, v, g, (int(round(image[0])),
                                                    int(round(image[1])),
                                                    -int(up[g]))))
                here_all.append(mine[f])
                out_all.append(outward[f])
                there_all.append(theirs[g])
                back_all.append(leaving[self.colours[v]][g])
        return (np.array(here_all), np.array(out_all),
                np.array(there_all), np.array(back_all), found)

    def cost(self, x, gamma):
        return float(self._score(*self.pairs(x, gamma)))

    def costs(self, xs, gamma) -> np.ndarray:
        """:meth:`cost` of every row of ``xs`` at once.

        The search's grid is a hundred thousand starts for a cell of
        two rods (MOF-303: 36 turns, 12 of the other colour's, 4^3 rises
        and shears, five angles), and one call each was 40 s; as arrays
        it is a fraction of a second.  A test holds the two equal.
        """
        return self._score(*self._batch(np.asarray(xs, float), gamma))

    def _score(self, here, outward, there, back):
        """The cost of faces and their partners, ``(..., faces, 3)``
        arrays, summed over the faces."""
        joint = there - here
        length = np.linalg.norm(joint, axis=-1)
        unit = joint / np.maximum(length, 1e-9)[..., None]
        along = np.clip(np.sum(outward * unit, axis=-1), -1.0, 1.0)
        against = np.clip(np.sum(back * unit, axis=-1), -1.0, 1.0)
        # Each face's bond is to leave the joint's line at the linker's
        # own bend: 1 - cos of the miss, which for a straight linker is
        # 1 - along, the cost a straight joint always had.
        miss = ((1 - np.cos(np.arccos(along) - self.bend))
                + (1 - np.cos(np.arccos(-against) - self.bend)))
        if self.bend > 1e-3:
            a = outward - along[..., None] * unit
            b = back - against[..., None] * unit
            na = np.maximum(np.linalg.norm(a, axis=-1), 1e-9)
            nb = np.maximum(np.linalg.norm(b, axis=-1), 1e-9)
            seen = np.arccos(np.clip(np.sum(a * b, axis=-1) / na / nb,
                                     -1.0, 1.0))
            miss = miss + math.sin(self.bend) ** 2 * (
                1 - np.cos(seen - self.twist))
        return (np.sum((length - self.span) ** 2, axis=-1)
                + self.span ** 2 * np.sum(miss, axis=-1))

    def _batch(self, xs, gamma):
        """:meth:`pairs` for every row of ``xs``: four ``(rows, faces,
        3)`` arrays, the faces in the order :meth:`pairs` gives them."""
        b = len(xs)
        n = self.n
        turns = xs[:, :2]
        rises = np.concatenate([np.zeros((b, 1)), xs[:, 2:1 + n]], axis=1)
        shears = xs[:, 1 + n:3 + n]
        a = self.a * (1.0 + xs[:, 3 + n])
        unit_flat = self.p.matrix(1.0, gamma)
        rows = np.empty((b, 2, 3))
        rows[:, :, :2] = a[:, None, None] * unit_flat
        rows[:, :, 2] = shears

        def turned(m, turn):
            c = np.cos(np.radians(turn))[:, None]
            s_ = np.sin(np.radians(turn))[:, None]
            out = np.empty((b, *m.shape))
            out[..., 0] = c * m[:, 0] - s_ * m[:, 1]
            out[..., 1] = s_ * m[:, 0] + c * m[:, 1]
            out[..., 2] = m[:, 2]
            return out

        placed = [turned(self.middles[k], turns[:, k]) for k in (0, 1)]
        leaving = [turned(self.outwards[k], turns[:, k]) for k in (0, 1)]
        everyone = np.arange(b)
        here_all, out_all, there_all, back_all = [], [], [], []
        for u in range(n):
            colour = self.colours[u]
            centre = np.einsum("j,bjk->bk", self.frac[u], rows)
            centre[:, 2] += rises[:, u]
            mine = placed[colour] + centre[:, None, :]
            outward = leaving[colour]
            level = outward[..., :2] / np.linalg.norm(
                outward[..., :2], axis=-1)[..., None]
            vs = [v for v, _ in self.edges[u]]
            steps = np.array([self.frac[v] + image - self.frac[u]
                              for v, image in self.edges[u]])
            gaps = np.einsum("ej,bjk->bek", steps, rows)
            gaps[:, :, 2] += rises[:, vs] - rises[:, u][:, None]
            flat = gaps[..., :2] / np.linalg.norm(
                gaps[..., :2], axis=-1)[..., None]
            chosen = np.argmax(np.einsum("bfk,bek->bfe", level, flat),
                               axis=2)                       # (b, f)
            # Every edge's partner rod, then each face's own.
            theirs = np.stack([placed[self.colours[v]] for v in vs],
                              axis=1) \
                + (centre[:, None, :] + gaps)[:, :, None, :]  # b e g 3
            backs = np.stack([leaving[self.colours[v]] for v in vs],
                             axis=1)
            picked = theirs[everyone[:, None], chosen]       # b f g 3
            picked_back = backs[everyone[:, None], chosen]
            dz = picked[..., 2] - mine[:, :, None, 2]
            picked = picked.copy()
            picked[..., 2] -= self.repeat * np.round(dz / self.repeat)
            d = np.linalg.norm(picked - mine[:, :, None, :], axis=-1)
            g = np.argmin(d, axis=2)                         # (b, f)
            faces_ = np.arange(mine.shape[1])[None, :]
            here_all.append(mine)
            out_all.append(outward)
            there_all.append(picked[everyone[:, None], faces_, g])
            back_all.append(picked_back[everyone[:, None], faces_, g])
        return (np.concatenate(here_all, axis=1),
                np.concatenate(out_all, axis=1),
                np.concatenate(there_all, axis=1),
                np.concatenate(back_all, axis=1))

    def fit(self, gammas, free):
        from itertools import product

        from scipy.optimize import minimize

        two = len(set(self.colours)) > 1
        turns = np.arange(-180.0, 180.0, _TURN_STEP)
        others = (np.arange(-180.0, 180.0, 3 * _TURN_STEP) if two
                  else [0.0])
        steps = np.arange(_RISE_STEPS) * self.repeat / _RISE_STEPS
        grid = np.array([[t0, t1, *lifts, 0.0]
                         for t0, t1 in product(turns, others)
                         for lifts in product(steps, repeat=self.n + 1)])
        starts = []
        for gamma in gammas:
            for chunk in range(0, len(grid), _CHUNK):
                xs = grid[chunk:chunk + _CHUNK]
                starts.extend(zip(self.costs(xs, gamma),
                                  [gamma] * len(xs), xs, strict=True))
        starts.sort(key=lambda s: s[0])
        best = None
        for _c, gamma, x in starts[:_STARTS]:
            if free:
                def cost(y):
                    g = y[-1]
                    if not FREE_ANGLES[0] <= g <= FREE_ANGLES[1]:
                        return 1e9
                    return self.cost(y[:-1], g)
                y0 = np.array([*x, gamma])
            else:
                def cost(y, gamma=gamma):
                    return self.cost(y, gamma)
                y0 = x
            result = minimize(cost, y0, method="Nelder-Mead",
                              options={"xatol": 1e-4, "fatol": 1e-8,
                                       "maxiter": 6000, "maxfev": 6000})
            y = result.x
            found = (float(result.fun), y[:-1] if free else y,
                     float(y[-1]) if free else gamma)
            if best is None or _better(found, best):
                best = found
        cost, x, gamma = best
        return x, gamma, cost

    def joints(self, x, gamma):
        """Each joint as ``(face, partner, how far off)``: how far the
        partner's middle is from where a straight linker of the span,
        along the face's outward line, would put it."""
        here, outward, there, _back = self.pairs(x, gamma)
        found = []
        for h, o, t in zip(here, outward, there, strict=True):
            # Along the face's bond, bent off it by the linker's bend
            # towards where the partner is.
            side = (t - h) - ((t - h) @ o) * o
            norm = np.linalg.norm(side)
            side = side / norm if norm > 1e-9 else np.zeros(3)
            way = math.cos(self.bend) * o + math.sin(self.bend) * side
            ideal = h + self.span * way
            found.append((h, t, float(np.linalg.norm(t - ideal))))
        return found


# =========================================================== inverse design


#: How far a linker may be from the span asked of it and still build,
#: as a fraction: PORMAKE's scaler takes up a few per cent.
SPAN_SLACK = 0.04


def requirement(rod: Rod, name: str, a: float):
    """What linker gives rods of ``rod`` on pattern ``name`` the cell
    side ``a``: a :class:`~xtal.mof.linkers.Requirement` on span."""
    from xtal.mof.linkers import Requirement, within

    p = pattern(name)
    reach = float(np.mean([f.reach for f in faces(rod, 1)]))
    span = a * p.spacing - 2 * reach
    if span <= 0:
        raise RodNetError(f"rods of {rod.name or 'this rod'} reach "
                          f"{reach:.2f} A each, so on {name} a cell of "
                          f"{a:.2f} A leaves no room for a linker")
    low, high = within(span, span * SPAN_SLACK)
    return Requirement(2, span, low, high, "aryl",
                       f"{rod.name or 'the rod'} on {name} at a = "
                       f"{a:.2f} A: rods {a * p.spacing:.2f} A apart, "
                       f"less twice its reach of {reach:.2f}")


def rods_for(span: float, name: str, a: float,
             rods: dict[str, Rod] | None = None) -> list[tuple[str, float]]:
    """Shipped rods a linker of ``span`` asks for, to make a cell of
    side ``a`` on pattern ``name``: ``(name, miss)`` in A of reach,
    nearest first, where a miss is how much farther each rod reaches
    than the one asked for."""
    from xtal.mof.rod import shipped

    if rods is None:
        rods = {n: Rod.read(path) for n, path in shipped().items()}
    p = pattern(name)
    wanted = (a * p.spacing - span) / 2
    found = []
    for n, r in rods.items():
        reach = float(np.mean([f.reach for f in faces(r, 1)]))
        found.append((n, reach - wanted))
    return sorted(found, key=lambda f: abs(f[1]))


__all__ = ["CLOSED", "FREE_ANGLES", "HANDS", "PATTERNS", "SPAN_SLACK", "Ends",
           "Face", "Match", "Pattern", "Placement", "RodNet", "RodNetError",
           "as_net", "colouring", "ends_of", "faces", "pattern",
           "placement", "requirement", "rod_net", "rods_for",
           "supercell"]
