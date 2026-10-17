"""
xtal.mof.rodbuild
=================
A rod MOF built: rods placed on a pattern (:mod:`xtal.mof.rodnet`), a
linker on every joint, the bonds stated, and the net of the points of
extension read back off the result and named.

**Every atom is placed by arithmetic, and nothing is perceived.**  The
placement says where each rod goes and which of its faces meets which
of a neighbour's.  A linker is put on each joint so that its ``X``
atoms land on the rods' -- by Kabsch where an end has two points
(dobdc's carboxylate and phenolate), and where it has one, along the
joint with the ring turned into the plane of the group it meets, in
closed form (the turn about a line through two points is the one
thing two points do not fix; :func:`xtal.mof.orient.align_edges` makes
the same choice for a framework's linkers).  Then every ``X`` goes,
and the atoms each stood for are bonded across the joint, paired by
distance.  The rods' bonds, the linkers' and the joints' are the
graph, stated, as every framework build's is.

**The net is read back, not assumed.**  A rod net's vertices are the
points of extension (Schoedel *et al.*, Chem. Rev. 2016, 116, 12466),
so each rod ``X`` is drawn as a vertex on the first atom it stood for,
its rod's stated shape as edges along the rod, and each linker as its
own skeleton -- pendants dropped, two-connected atoms folded -- so a
ditopic linker is one edge and dobdc keeps its four ring junctions.
The net is drawn on the framework as topology bonds and named by
:func:`xtal.mof.build.check_net`, as every build is held to its net.
Which net comes out is the rods' hands and the shape's business:
MIL-53 on sql reads sra and BTDD's helices etb with both hands and
eta with one, and the verdict says what was read rather than what was
hoped for.

Numpy and scipy; no Qt, no PORMAKE.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from itertools import permutations
from pathlib import Path

import numpy as np

from xtal.mof.rod import (
    SAVED,
    Rod,
    RodError,
    saved,
    shipped,
    shipped_linkers,
)
from xtal.mof.rodnet import (
    HANDS,
    PATTERNS,
    Placement,
    RodNetError,
    _about,
    conformers,
    ends_of,
    faces,
    placement,
    rod_net,
)

#: Each family's own linker, the one cut from the same crystal: what a
#: rod is built with when no linker is named.
OWN_LINKERS = {"MIL-53": "BDC", "MOF-74": "dobdc", "Ni2Cl2BTDD": "BTDD",
               "MOF-303": "pzdc"}


class RodBuildError(ValueError):
    """A rod build that cannot be set up or did not close, said in a
    sentence."""


# ================================================================ request


@dataclass(frozen=True)
class RodRequest:
    """A rod, a pattern for the rods, a linker between them, and how."""

    rod: str
    pattern: str
    linker: str = ""
    hands: str = "auto"
    angle: float | None = None
    repeat: tuple[int, int, int] = (1, 1, 1)

    @classmethod
    def parse(cls, rod: str, pattern: str, linker: str = "",
              hands: str = "", angle="", repeat: str = ""
              ) -> RodRequest:
        """The strings a parameter form and a command line hand over.

        No interpenetration: parallel rods joined on every side fill
        the plane across them, and no second framework threads
        through a rod MOF's channels."""
        from xtal.mof.build import MofError, _repeat

        rod, pattern = str(rod or "").strip(), str(pattern or "").strip()
        if not rod:
            raise RodBuildError("no rod named: one of "
                                + ", ".join(shipped()))
        if pattern not in PATTERNS:
            raise RodBuildError(f"the rods go on one of "
                                f"{', '.join(PATTERNS)}, not "
                                f"{pattern or 'nothing'}")
        hands = str(hands or "auto").strip()
        if hands not in HANDS:
            raise RodBuildError(f"hands is one of {', '.join(HANDS)}, "
                                f"not {hands}")
        text = str("" if angle is None else angle).strip()
        try:
            value = float(text) if text else None
        except ValueError:
            raise RodBuildError(f"an angle is a number of degrees, not "
                                f"{text}") from None
        try:
            tiles = _repeat(str(repeat or ""))
        except MofError as exc:
            raise RodBuildError(str(exc)) from None
        return cls(rod, pattern, str(linker or "").strip(), hands, value,
                   tiles)

    @property
    def linker_name(self) -> str:
        """The linker named, or the rod's own family's."""
        if self.linker:
            return self.linker
        own = OWN_LINKERS.get(Path(self.rod).stem.rsplit("_", 1)[0])
        if own is None:
            raise RodBuildError(f"{self.rod} has no linker of its own; "
                                f"name one")
        return own

    def resolved(self, folders=()) -> RodRequest:
        """The request with the linker a saved rod names filled in,
        when none was given (:func:`xtal.mof.rod.save_block`)."""
        if self.linker:
            return self
        named = load_rod(self.rod, folders).linker
        return replace(self, linker=named) if named else self

    def title(self) -> str:
        return (f"{Path(self.rod).stem}-{self.pattern}-"
                f"{Path(self.linker_name).stem}")


def load_rod(name: str, folders=()) -> Rod:
    """A shipped rod by name, one saved under ``folders`` (a
    workspace's blocks, :func:`xtal.mof.rod.save_block`), or a rod file
    by path."""
    found = shipped().get(name)
    for folder in folders:
        found = found or saved(folder).get(name)
    path = found or Path(name)
    if not path.is_file():
        raise RodBuildError(f"no rod called {name}; the shipped rods "
                            f"are {', '.join(shipped())}")
    try:
        return Rod.read(path)
    except (RodError, ValueError, IndexError) as exc:
        raise RodBuildError(f"{path.name} is not a rod: {exc}") from None


def load_linker(name: str, folders=()):
    """A linker by path, by name in the rod library, in ``folders``
    (a workspace's blocks), or among PORMAKE's blocks."""
    from xtal.mof import donors
    from xtal.mof.catalog import database_root
    from xtal.mof.trimer import Block

    candidates = [Path(name), shipped_linkers().get(name)]
    candidates += [Path(f) / SAVED / "linkers" / f"{name}.xyz"
                   for f in folders]
    candidates += [Path(f) / f"{name}.xyz" for f in folders]
    root = database_root()
    if root is not None:
        candidates.append(Path(root) / "bbs" / f"{name}.xyz")
    for path in candidates:
        if path is not None and path.is_file():
            try:
                return donors.as_linker(Block.read(path))
            except donors.DonorError as exc:
                raise RodBuildError(f"{path.stem}: {exc}") from None
    raise RodBuildError(f"no linker called {name}; the rods' own are "
                        f"{', '.join(shipped_linkers())}, and any "
                        f"two-ended block of PORMAKE's will do")


# ================================================================ outcome


@dataclass
class RodOutcome:
    """A rod framework and what is worth saying about it."""

    structure: object
    request: RodRequest
    placement: Placement
    n_atoms: int = 0
    #: How many rod-to-linker bonds the joints made, and the longest.
    joints: int = 0
    longest_joint: float = 0.0
    closest: float = float("inf")
    overlaps: tuple = ()
    #: What the RCSR calls the net of the points of extension.
    identified: object = None
    cif: Path | None = None
    #: One ``(node, hand, turn, rise)`` per rod of the cell.
    rods: tuple = ()

    @property
    def net_name(self) -> str:
        return self.identified.name if self.identified else ""

    def verdict(self) -> str:
        if not self.identified:
            head = "the net could not be read back off the framework"
        elif self.net_name:
            head = f"the points of extension make {self.net_name}"
            if self.identified.copies > 1:
                head = f"the framework is {self.identified.headline()}"
        else:
            head = (f"the points of extension make "
                    f"{self.identified.headline()}")
        said = [f"worst joint {self.placement.worst:.2f} A off"]
        if np.isfinite(self.closest):
            said.append(f"closest contact {self.closest:.2f} A")
        if self.joints:
            said.append(f"{self.joints} joint bond(s), the longest "
                        f"{self.longest_joint:.2f} A")
        if self.overlaps:
            said.append(f"{len(self.overlaps)} pair(s) of atoms "
                        f"overlapping")
        return head + " -- " + ", ".join(said)

    def warning(self) -> str:
        if not self.overlaps:
            return ""
        distance, first, second = self.overlaps[0]
        more = len(self.overlaps) - 1
        tail = f", and {more} more pair(s)" if more else ""
        return (f"atoms overlap in the built framework: {first} and "
                f"{second} are {distance:.2f} A apart{tail} -- try "
                f"another angle, the other hands, or a longer linker")


# ================================================================== build


def build(request: RodRequest, directory=None, log=None,
          folders=()) -> RodOutcome:
    """Build ``request``, and read back the net it makes."""
    from xtal.mof.build import OVERLAP, _contacts, check_net
    from xtal.mof.build import closest_contact as closest

    request = request.resolved(folders)
    rod = load_rod(request.rod, folders)
    linker = load_linker(request.linker_name, folders)
    try:
        net = rod_net(request.pattern, rod, request.hands)
        _say(log, f"placing {rod.name or request.rod} on "
                  f"{request.pattern}, hands {net.hands}")
        placed, atoms = _best(net, rod, linker, request.angle)
    except RodNetError as exc:
        raise RodBuildError(str(exc)) from None
    _say(log, placed.sentence())
    atoms = atoms.tiled(request.repeat)
    structure = atoms.structure(f"{request.title()}")
    outcome = RodOutcome(structure, request, placed,
                         n_atoms=structure.n_sites,
                         joints=atoms.joint_bonds,
                         longest_joint=atoms.longest_joint,
                         rods=atoms.rods)
    outcome.closest = closest(structure)
    outcome.overlaps = tuple(
        (d, atoms.name(i), atoms.name(j))
        for d, i, j in sorted(_contacts(structure, OVERLAP)))
    if outcome.overlaps:
        _say(log, outcome.warning())
        structure.meta.setdefault("warnings", []).append(
            outcome.warning())
    drawn = atoms.draw_net(structure)
    _say(log, f"drew {drawn} net edge(s); identifying what came out")
    outcome.identified = check_net(outcome.structure)
    if directory is not None:
        from xtal.io.cif_writer import write_cif
        from xtal.workspace import safe_name

        outcome.cif = Path(directory) / (
            safe_name(request.title(), "rods") + ".cif")
        write_cif(outcome.structure, outcome.cif, perception=True)
    _say(log, outcome.verdict())
    return outcome


def best_placement(net, rod, linker, angle=None) -> Placement:
    """The placement a build of these would use: for a linker that can
    turn about the bonds between its ends, the best of its poses."""
    return _best(net, rod, linker, angle)[0]


def _best(net, rod, linker, angle):
    """``(placement, atoms)``: each of the linker's poses placed and
    assembled (:data:`xtal.mof.rodnet.POSES`, none for a linker that
    cannot turn), the one whose joints miss and crowd least kept.

    Where the rods leave the twist free (one hand, a two-fold across
    the linker), the poses are spread over it instead
    (:data:`~xtal.mof.rodnet.FREE_TWISTS`), and the best refined
    :data:`~xtal.mof.rodnet.FREE_REFINE` either side."""
    from xtal.mof.rodnet import (
        FREE_REFINE,
        FREE_TWISTS,
        POSES,
        can_turn,
        wanted_twist,
    )

    best = None

    def keep(placed, twist=None):
        nonlocal best
        atoms = _assemble(placed, linker)
        if best is None or atoms.score < best[1].score - 1e-6:
            best = (placed, atoms, twist)

    if wanted_twist(net, rod) is None and can_turn(linker):
        for degrees in FREE_TWISTS:
            keep(placement(net, rod, linker, angle=angle,
                           twist=math.radians(degrees)), degrees)
        centre = best[2]
        for degrees in (centre - FREE_REFINE, centre + FREE_REFINE):
            if FREE_TWISTS[0] <= degrees <= FREE_TWISTS[-1]:
                keep(placement(net, rod, linker, angle=angle,
                               twist=math.radians(degrees)), degrees)
        return best[:2]
    for pose in range(POSES):
        placed = placement(net, rod, linker, angle=angle, pose=pose)
        if pose and placed.posed is None:
            break
        keep(placed)
        if placed.posed is None:
            break
    return best[:2]


# =============================================================== assembly


@dataclass
class _Atoms:
    """Atoms at unwrapped Cartesian positions in a cell of ``rows``.

    A bond or a net edge is ``(i, j, shift)``: ``j`` taken ``shift``
    cells from where it is written.
    """

    rows: np.ndarray
    symbols: list = field(default_factory=list)
    cart: list = field(default_factory=list)
    owner: list = field(default_factory=list)
    bonds: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    joint_bonds: int = 0
    longest_joint: float = 0.0
    rods: tuple = ()
    #: How far the linkers' joints miss, and crowd and stretch where
    #: the linker was turned: what :func:`_best` keeps the least of.
    score: float = 0.0

    def add(self, symbol, xyz, owner) -> int:
        self.symbols.append(symbol)
        self.cart.append(np.asarray(xyz, float))
        self.owner.append(owner)
        return len(self.symbols) - 1

    def at(self, atom, shift) -> np.ndarray:
        return self.cart[atom] + np.asarray(shift, float) @ self.rows

    def name(self, atom) -> str:
        return f"{self.symbols[atom]}{atom + 1} ({self.owner[atom]})"

    def tiled(self, repeat) -> _Atoms:
        """The same framework in a cell ``repeat`` times as large."""
        repeat = np.asarray(repeat, int)
        if np.all(repeat == 1):
            return self
        out = _Atoms(np.diag(repeat) @ self.rows,
                     joint_bonds=self.joint_bonds * int(np.prod(repeat)),
                     longest_joint=self.longest_joint, rods=self.rods)
        tiles = [np.array(t) for t in np.ndindex(*repeat)]
        index = {}
        for t in tiles:
            for k, s in enumerate(self.symbols):
                index[(k, tuple(t))] = out.add(
                    s, self.at(k, t), self.owner[k])

        def carry(links, into):
            for i, j, shift in links:
                for t in tiles:
                    to = t + np.asarray(shift, int)
                    home = np.mod(to, repeat)
                    into.append((index[(i, tuple(t))],
                                 index[(j, tuple(home))],
                                 tuple(int(v) for v in
                                       (to - home) // repeat)))

        carry(self.bonds, out.bonds)
        carry(self.edges, out.edges)
        return out

    def _images(self):
        frac = np.array(self.cart) @ np.linalg.inv(self.rows)
        whole = np.floor(frac + 1e-9)
        return frac - whole, whole.astype(int)

    def _image(self, whole, i, j, shift):
        return tuple(int(v) for v in np.asarray(shift) + whole[j]
                     - whole[i])

    def structure(self, title: str):
        """A P1 structure of the atoms, the bonds stated as its graph."""
        from xtal.core import p1
        from xtal.core.bonding import BondRules
        from xtal.core.lattice import Lattice
        from xtal.core.site import Site
        from xtal.core.structure import CellBond, Structure

        frac, whole = self._images()
        frac[frac >= 1.0] = 0.0
        sites = [Site(s, np.array(f)) for s, f in zip(self.symbols, frac,
                                                      strict=True)]
        for k, site in enumerate(sites):
            site.label = f"{site.element}{k + 1}"
        structure = Structure(lattice=Lattice(np.array(self.rows)),
                              sites=sites)
        structure.meta["title"] = title
        structure.meta["builder"] = "xtal.mof.rodbuild"
        cell = p1.expand(structure)
        found = {}
        for i, j, shift in self.bonds:
            image = self._image(whole, i, j, shift)
            gap = (cell.frac[j] + image - cell.frac[i]) @ self.rows
            a, b, img = CellBond(i, j, image, 0.0).key()
            found[(a, b, img)] = CellBond(a, b, img,
                                          float(np.linalg.norm(gap)))
        rules = BondRules.from_dict(structure.bond_rules)
        structure.set_perceived(sorted(found.values(),
                                       key=lambda b: (b.i, b.j, b.image)),
                                rules.signature(), cell)
        return structure

    def draw_net(self, structure) -> int:
        """The points of extension's net, as topology bonds."""
        from xtal.core.structure import TOPOLOGY, Bond

        _frac, whole = self._images()
        drawn = 0
        for i, j, shift in self.edges:
            image = self._image(whole, i, j, shift)
            if i == j and not any(image):
                continue
            if structure.add_bond(Bond(i=i, j=j, image=image,
                                       kind=TOPOLOGY)):
                drawn += 1
        return drawn


def _assemble(placed: Placement, linker) -> _Atoms:
    """Every rod of the cell, a linker on every joint, the ``X`` atoms
    gone and their atoms bonded across."""
    rows = placed.rows
    atoms = _Atoms(rows)
    p = placed.net.pattern
    if placed.posed is not None:
        linker = placed.posed
    ends = ends_of(linker)
    size = ends.size
    rod_faces = [faces(r, size) for r in placed.rods]

    # The rods.
    index, xyz = [], []                  # per node: rod atom -> ours
    rods = []
    for u, frac in enumerate(p.nodes):
        colour = placed.net.colours[u]
        rod = placed.rods[colour]
        turn = placed.turns[colour]
        centre = (frac[0] * rows[0] + frac[1] * rows[1]
                  + [0.0, 0.0, placed.rises[u]])
        where = _turned(rod.positions, turn) + centre
        mine = {}
        for k, s in enumerate(rod.symbols):
            if s != "X":
                mine[k] = atoms.add(s, where[k], f"rod {u + 1}")
        for i, j, _letter, shift in rod.bonds:
            if i in mine and j in mine:
                atoms.bonds.append((mine[i], mine[j], (0, 0, shift)))
        index.append(mine)
        xyz.append(where)
        rods.append((u + 1, rod.hand or "none", float(turn) % 360.0,
                     float(placed.rises[u]) % rod.repeat))
    atoms.rods = tuple(rods)

    def vertex(u, x, shift):
        """The atom a rod's ``X`` is drawn on, and its shift."""
        rod = placed.rods[placed.net.colours[u]]
        member, up = min(rod.members(x))
        return index[u][member], tuple(np.add(shift, (0, 0, up)))

    # Each rod's shape, along it.
    for u in range(len(p.nodes)):
        rod = placed.rods[placed.net.colours[u]]
        for a, b, shift in rod.edges:
            i, si = vertex(u, a, (0, 0, 0))
            j, sj = vertex(u, b, (0, 0, shift))
            atoms.edges.append((i, j, tuple(np.subtract(sj, si))))

    # The joints, once each.
    joints = {}
    used = defaultdict(int)
    for m in placed.matches:
        one = (m.node, m.face, m.other, m.partner, m.shift)
        other = (m.other, m.partner, m.node, m.face,
                 tuple(-v for v in m.shift))
        joints[min(one, other)] = True
    for u, f, v, g, _shift in joints:
        used[(u, f)] += 1
        used[(v, g)] += 1
    wrong = [k for k in ((u, f) for u in range(len(p.nodes))
                         for f in range(len(rod_faces[
                             placed.net.colours[u]])))
             if used[k] != 1]
    if wrong:
        u, f = wrong[0]
        raise RodBuildError(
            f"the joints did not pair up: face {f + 1} of rod {u + 1} "
            f"meets {used[(u, f)]} linkers, where every face meets one "
            f"-- the placement left joints {placed.worst:.2f} A off")

    skeleton = _skeleton(linker)
    places = _places(linker, ends)
    joined = []
    for u, f, v, g, shift in sorted(joints):
        sides = []
        for node, face, lattice in ((u, f, (0, 0, 0)), (v, g, shift)):
            colour = placed.net.colours[node]
            sides.append([
                (node, x, tuple(np.add(lattice, (0, 0, up))))
                for x, up in rod_faces[colour][face].members])
        targets = [(n, x, s, xyz[n][x] + np.asarray(s, float) @ rows)
                   for side in sides for n, x, s in side]
        kinds = [placed.rods[placed.net.colours[n]].kind(x)
                 for n, x, _s, _at in targets]
        joined.append((targets, kinds))

    def fitted(linker):
        fits = [(targets, _fits(linker, ends, targets, placed, index,
                                atoms, places, kinds))
                for targets, kinds in joined]
        pairing = _one_pairing([found for _targets, found in fits])
        return sum(found[pairing][0] for _t, found in fits), pairing, fits

    best = fitted(linker)
    turns = list(conformers(linker, ends)) if ends.size > 1 else []
    if turns:
        rods_at = np.array(atoms.cart)

        def scored(linker, tried):
            total, pairing, fits = tried
            chosen = [found[pairing] for _t, found in fits]
            targets = [t for t, _f in fits]
            score = total + CLASH_WEIGHT * (
                _crowding(linker, chosen, rows, rods_at)
                + _stretch(linker, chosen, targets, placed, index,
                           atoms))
            return score

        score = scored(linker, best)
        for turned in turns:
            tried = fitted(turned)
            mine = scored(turned, tried)
            if mine < score - 1e-6:
                best, linker, score = tried, turned, mine
        atoms.score = score
    else:
        atoms.score = best[0]
    _total, pairing, fits = best

    longest, count = 0.0, 0
    for k, (targets, found) in enumerate(fits):
        _miss, order, rotation, origin = found[pairing]
        owner = f"linker {k + 1}"
        placed_at = (linker.positions - linker.positions[
            list(linker.connections)].mean(axis=0)) @ rotation.T + origin
        mine = {}
        for a, s in enumerate(linker.symbols):
            if s != "X":
                mine[a] = atoms.add(s, placed_at[a], owner)
        for i, j, _letter in linker.bonds:
            if i in mine and j in mine:
                atoms.bonds.append((mine[i], mine[j], (0, 0, 0)))
        met = {}
        for x_linker, (n, x, s, _at) in zip(order, targets, strict=True):
            met[x_linker] = vertex(n, x, s)
            rod = placed.rods[placed.net.colours[n]]
            ours = [(index[n][m], tuple(np.add(s, (0, 0, up))))
                    for m, up in rod.members(x)]
            theirs = [mine[a] for a in linker.neighbours(x_linker)
                      if a in mine]
            for a, (b, sb), d in _pair(atoms, theirs, ours):
                atoms.bonds.append((a, b, sb))
                longest = max(longest, d)
                count += 1
        for a, b in skeleton:
            ia, sa = met.get(a, (mine.get(a), (0, 0, 0)))
            ib, sb = met.get(b, (mine.get(b), (0, 0, 0)))
            atoms.edges.append((ia, ib, tuple(np.subtract(sb, sa))))
    atoms.joint_bonds, atoms.longest_joint = count, longest
    return atoms


def _turned(m, turn) -> np.ndarray:
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    out = np.array(m, float)
    out[:, 0] = c * m[:, 0] - s * m[:, 1]
    out[:, 1] = s * m[:, 0] + c * m[:, 1]
    return out


def _places(linker, ends) -> dict[int, int]:
    """Each linker ``X``, numbered by where it sits in the linker's
    graph: how many bonds it is from each other ``X``.

    A biphenyl core's C4 point is 9 bonds from the far C4 one and its
    C3 point 7 from the far C3, which is all that tells dobpdc from
    pc-dobpdc when nothing names the donors.  Read off the bonds, not
    the geometry: both sit the same distance off the line through
    the ends' middles, and dobdc's two points, related by the ring's
    mirror, are rightly one place.
    """
    near = defaultdict(set)
    for i, j, _letter in linker.bonds:
        near[i].add(j)
        near[j].add(i)
    points = (*ends.ends[0], *ends.ends[1])

    def steps(x):
        seen, queue = {x: 0}, deque([x])
        while queue:
            a = queue.popleft()
            for n in near[a]:
                if n not in seen:
                    seen[n] = seen[a] + 1
                    queue.append(n)
        return tuple(sorted(seen.get(y, -1) for y in points if y != x))

    signatures = {x: steps(x) for x in points}
    numbered = {sig: k for k, sig in enumerate(sorted(set(
        signatures.values())))}
    return {x: numbered[signatures[x]] for x in points}


#: Atoms of different blocks nearer than this, A, crowd each other
#: when a linker's turn is chosen -- below any contact in the shipped
#: builds' crystals (2.05 A in MOF-74) yet above a clash.
CROWDED = 2.0

#: What a crowding of 1 A^2 costs against a joint's miss, A^2.
CLASH_WEIGHT = 10.0


#: A joint bond longer than this, A, is stretched when a linker's turn
#: is chosen: a C-C between rings is 1.48, a C-O 1.36.
STRETCHED = 1.6


def _stretch(linker, chosen, targets, placed, index, atoms) -> float:
    """How far the joints at ``chosen`` stretch: for each linker atom
    a joint bonds, (d - :data:`STRETCHED`)^2 to its nearest rod atom
    there, where d is over that.

    Contacts alone let a turn of pc-dobpdc buy 0.06 A of room with
    joints 2.05 A long."""
    xs = np.asarray(linker.positions, float)
    centre = xs[list(linker.connections)].mean(axis=0)
    total = 0.0
    for (_miss, order, rotation, origin), joint in zip(
            chosen, targets, strict=True):
        for x, (n, point, s, _at) in zip(order, joint, strict=True):
            rod = placed.rods[placed.net.colours[n]]
            ours = [atoms.at(index[n][m], np.add(s, (0, 0, up)))
                    for m, up in rod.members(point)]
            for a in linker.neighbours(x):
                if linker.symbols[a] == "X" or not ours:
                    continue
                at = (xs[a] - centre) @ rotation.T + origin
                d = min(float(np.linalg.norm(at - b)) for b in ours)
                total += max(0.0, d - STRETCHED) ** 2
    return total


def _crowding(linker, chosen, rows, rods_at) -> float:
    """How much the linkers placed at ``chosen`` -- each joint's
    ``(miss, order, rotation, origin)`` -- crowd the rods and one
    another: the sum of (:data:`CROWDED` - d)^2 over pairs closer than
    that, over the cell's neighbours.  The atoms a linker joins the
    rods by are left out, as their bonds put them close.
    """
    from scipy.spatial import cKDTree

    xs = np.asarray(linker.positions, float)
    centre = xs[list(linker.connections)].mean(axis=0)
    joining = {a for x in linker.connections
               for a in linker.neighbours(x)}
    body = [a for a, s in enumerate(linker.symbols)
            if s != "X" and a not in joining]
    placed = [(xs[body] - centre) @ rotation.T + origin
              for _miss, _order, rotation, origin in chosen]
    owners = np.concatenate([np.full(len(rods_at), -1)]
                            + [np.full(len(p), k)
                               for k, p in enumerate(placed)])
    every = np.vstack([rods_at, *placed])
    shifts = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1)
                       for k in (-1, 0, 1)], float) @ rows
    images = (every[None, :, :] + shifts[:, None, :]).reshape(-1, 3)
    tree = cKDTree(images)
    total = 0.0
    n = len(every)
    for k, block in enumerate(placed):
        hits = tree.query_ball_point(block, CROWDED)
        for a, found in enumerate(hits):
            for j in found:
                if owners[j % n] == k:
                    continue
                d = float(np.linalg.norm(images[j] - block[a]))
                total += (CROWDED - d) ** 2
    return total


def _one_pairing(fits):
    """The pairing every joint takes: the one whose misses, each joint
    at its best within it, sum least.

    A pairing is which place in the linker meets which kind of rod
    point, and only those with the fewest such pairs are considered:
    each place one kind wherever the linker has places enough.
    Chosen joint by joint, a biphenyl core went on as dobpdc at some
    joints and pc-dobpdc at others in one cell, and the two clashed
    where they met; left free within a joint, its two ends went on
    as one of each, which fits a twisted biphenyl better and is
    neither linker.
    """
    shared = set.intersection(*(set(found) for found in fits))
    fewest = min(len(key) for key in shared)
    return min((key for key in shared if len(key) == fewest),
               key=lambda key: (sum(f[key][0] for f in fits), key))


def _fits(linker, ends, targets, placed, index, atoms, places, kinds):
    """For each pairing, the joint's best ``(miss, order, rotation,
    origin)`` under it.  A linker ``X`` named by its donor goes only on
    a rod point of that kind; one drawn bare goes on any."""
    named = dict(zip(linker.connections, getattr(linker, "kinds", ()),
                     strict=False))
    best = {}
    for miss, order, rotation, origin in _candidates(
            linker, ends, targets, placed, index, atoms):
        if any(named.get(x) and named[x] != kind
               for x, kind in zip(order, kinds, strict=True)):
            continue
        key = tuple(sorted({(places[x], kind)
                            for x, kind in zip(order, kinds,
                                               strict=True)}))
        if key not in best or miss < best[key][0] - 1e-9:
            best[key] = (miss, order, rotation, origin)
    return best


def _candidates(linker, ends, targets, placed, index, atoms):
    """Every way the linker's ``X`` can go on ``targets``, with the
    rotation and origin that put them there and how far they miss:
    ``(miss, order, rotation, origin)``."""
    points = np.array([t[3] for t in targets])
    origin = points.mean(axis=0)
    xs = np.asarray(linker.positions, float)
    centre = xs[list(linker.connections)].mean(axis=0)
    for first, second in (ends.ends, ends.ends[::-1]):
        for a in permutations(first):
            for b in permutations(second):
                order = list(a) + list(b)
                source = xs[order] - centre
                rotation = _kabsch(source, points - origin)
                options = [rotation]
                if len(order) == 2:
                    rotation = _turn_into_plane(
                        rotation, linker, order, source, targets,
                        placed, index, atoms)
                    # A plane is the same plane half a turn on, and a
                    # bent linker is not the same linker: which half
                    # is where its atoms land against the rods'.
                    line = points[1] - points[0]
                    options = [rotation, _about(
                        line / np.linalg.norm(line), math.pi) @ rotation]
                for rotation in options:
                    miss = float(np.sum((source @ rotation.T + origin
                                         - points) ** 2))
                    miss += _reach_miss(linker, order, rotation, centre,
                                        origin, targets, placed, index,
                                        atoms)
                    yield miss, order, rotation, origin


def _reach_miss(linker, order, rotation, centre, origin, targets,
                placed, index, atoms) -> float:
    """How far the linker's atoms at each joint are from where the
    rod's bond, carried straight through its ``X``, would put them."""
    xs = np.asarray(linker.positions, float)
    total = 0.0
    for x_linker, (n, x, s, at) in zip(order, targets, strict=True):
        members = [a for a in linker.neighbours(x_linker)
                   if linker.symbols[a] != "X"]
        rod = placed.rods[placed.net.colours[n]]
        ours = [atoms.at(index[n][m], np.add(s, (0, 0, up)))
                for m, up in rod.members(x)]
        if not members or not ours:
            continue
        step = at - np.mean(ours, axis=0)
        ideal = at + 0.75 * step / np.linalg.norm(step)
        landed = (xs[members].mean(axis=0) - centre) @ rotation.T + origin
        total += float(np.sum((landed - ideal) ** 2))
    return total


def _kabsch(source, target) -> np.ndarray:
    """The rotation taking ``source`` onto ``target`` (both centred);
    for two points, the shortest turn from one line onto the other."""
    if len(source) == 2:
        return _align(source[1] - source[0], target[1] - target[0])
    h = source.T @ target
    u, _s, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    return vt.T @ np.diag([1.0, 1.0, d]) @ u.T


def _align(a, b) -> np.ndarray:
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        if c > 0:
            return np.eye(3)
        other = np.eye(3)[int(np.argmin(np.abs(a)))]
        axis = np.cross(a, other)
        return _about(axis / np.linalg.norm(axis), math.pi)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def _turn_into_plane(rotation, linker, order, source, targets, placed,
                     index, atoms):
    """``rotation`` turned about the joint so that each end's plane --
    the ring at the linker's ``X``, the group at the rod's -- lies in
    the other's, as near as one turn can make both."""
    axis = (source[1] - source[0]) @ rotation.T
    axis /= np.linalg.norm(axis)
    total = 0j
    for x_linker, (n, x, s, _at) in zip(order, targets, strict=True):
        ours = _linker_plane(linker, x_linker)
        theirs = _rod_plane(placed, n, x, s, index, atoms)
        if ours is None or theirs is None:
            continue
        a = ours @ rotation.T
        a, b = a - (a @ axis) * axis, theirs - (theirs @ axis) * axis
        if np.linalg.norm(a) < 1e-6 or np.linalg.norm(b) < 1e-6:
            continue
        angle = math.atan2(float(axis @ np.cross(a, b)), float(a @ b))
        total += complex(math.cos(2 * angle), math.sin(2 * angle))
    if abs(total) < 1e-9:
        return rotation
    return _about(axis, math.atan2(total.imag, total.real) / 2) @ rotation


def _normal(points) -> np.ndarray | None:
    points = np.asarray(points, float)
    if len(points) < 3:
        return None
    centred = points - points.mean(axis=0)
    _u, s, vt = np.linalg.svd(centred)
    if s[1] < 0.1 * s[0] or s[1] < 1e-3:
        return None
    return vt[2]


def _linker_plane(linker, x):
    members = [a for a in linker.neighbours(x) if linker.symbols[a] != "X"]
    near = set(members)
    for m in members:
        near |= {a for a in linker.neighbours(m)
                 if linker.symbols[a] != "X"}
    return _normal(np.asarray(linker.positions, float)[sorted(near)])


def _rod_plane(placed, node, x, shift, index, atoms):
    rod = placed.rods[placed.net.colours[node]]
    members = [(m, up) for m, up in rod.members(x)
               if rod.symbols[m] != "X"]
    near = set(members)
    for m, up in members:
        near |= {(j, up + k) for j, k in rod.neighbours(m)
                 if rod.symbols[j] != "X"}
    points = [atoms.at(index[node][m], np.add(shift, (0, 0, up)))
              for m, up in near]
    return _normal(points)


def _pair(atoms, theirs, ours):
    """Each of the linker's atoms at a joint bonded to one of the rod's,
    paired by distance so every atom of the smaller side is bonded, and
    any left on the larger side to its nearest: ``(a, (b, shift), d)``."""
    from scipy.optimize import linear_sum_assignment

    if not theirs or not ours:
        return []
    d = np.array([[np.linalg.norm(atoms.at(b, sb) - atoms.cart[a])
                   for b, sb in ours] for a in theirs])
    rows, cols = linear_sum_assignment(d)
    found = [(theirs[r], ours[c], float(d[r, c]))
             for r, c in zip(rows, cols, strict=True)]
    for r in set(range(len(theirs))) - set(rows):
        c = int(np.argmin(d[r]))
        found.append((theirs[r], ours[c], float(d[r, c])))
    for c in set(range(len(ours))) - set(cols):
        r = int(np.argmin(d[:, c]))
        found.append((theirs[r], ours[c], float(d[r, c])))
    return found


def _skeleton(linker) -> list[tuple[int, int]]:
    """The linker as its net: pendant atoms dropped, parallel paths
    merged and two-connected atoms folded, the ``X`` atoms kept, so a
    ditopic linker is one edge between its two ``X``.

    Whatever its core: two ends are one edge however they are joined,
    and BTDD's fused rings, folded, still leave 24 junctions between
    its two points (measured, E0)."""
    keep = {i for i, s in enumerate(linker.symbols) if s == "X"}
    if len(keep) == 2:
        return [tuple(sorted(keep))]
    edges = {tuple(sorted((i, j))) for i, j, _ in linker.bonds if i != j}
    alive = set(range(len(linker.symbols)))
    changed = True
    while changed:
        changed = False
        near = defaultdict(set)
        for a, b in edges:
            near[a].add(b)
            near[b].add(a)
        for v in sorted(alive - keep):
            if len(near[v]) <= 1:
                edges = {e for e in edges if v not in e}
            elif len(near[v]) == 2:
                a, b = sorted(near[v])
                edges = {e for e in edges if v not in e} | {(a, b)}
            else:
                continue
            alive.discard(v)
            changed = True
            break
    return sorted(edges)


def _say(log, text: str) -> None:
    if log is not None:
        log(text)


__all__ = ["OWN_LINKERS", "RodBuildError", "RodOutcome", "RodRequest",
           "build", "load_linker", "load_rod"]
