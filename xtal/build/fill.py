"""
xtal.build.fill
===============
Guest molecules into the empty space of a host: solvent in a pore.

Two questions and nothing else.  *What is the guest* --
:func:`guest_molecules` lifts every discrete molecule out of a
structure, which is how a solvent somebody drew in a box of its own
becomes a thing that can be put somewhere.  *Where does each copy go*
-- :func:`place` throws them in at random and keeps the ones that
touch nothing.  Committing the answer is
:class:`xtal.commands.clipboard.InsertMolecules`, and bonding it is
nobody's business here: a guest arrives with the bonds it was drawn
with and none to the framework it is sitting a contact away from.

**Random insertion, not packing.**  A trial centre is drawn from the
grid points :func:`xtal.analysis.grid.distance_grid` says are clear of
the host, the molecule is turned by a uniformly random rotation, and
the trial is kept when no atom of it is inside any other atom.  It is
what a first Monte Carlo step does, and it stops being able to add
anything well short of a liquid's density: :func:`capacity` is the
upper bound it is quoted against, not a promise.

**Contact means van der Waals radii, scaled.**  Two atoms clash when
they are closer than ``overlap_scale`` times the sum of their radii.
At 1.0 nothing touches anything, which leaves a real solvent visibly
too sparse -- molecules in a liquid sit inside each other's van der
Waals spheres -- so 0.8 is the default and the dialog offers the rest.

**Or at a point somebody chose** -- :func:`at_point`, one copy with
its centroid on given fractional coordinates, which is the question
of a guest the user knows the place of: the template in its cage,
the molecule a diffraction study located.  A clash there is
*reported*, never refused: the point was chosen, and the closest
contact is said by name so the user can judge it.  The molecule is
put as it was drawn unless it is asked to turn, and then the turn
that leaves the most room is kept -- which is never tighter than as
drawn, because as drawn is the first one tried.  Kept in its space
group, the host's operations copy the molecule; at a special position
those copies land on each other, and that is said too, from the atom
count the expansion actually makes.

Periodic throughout: a guest near one face is tested against the
framework across the other, and against its own images when the cell
is small enough for it to meet them.  Qt-free, like everything in
:mod:`xtal.build`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.spatial import cKDTree

from xtal.analysis import grid
from xtal.commands.clipboard import (
    Fragment,
    InsertMolecules,
    PasteFragment,
)
from xtal.core import bonding, p1
from xtal.core import elements as el
from xtal.core.structure import Structure

DEFAULT_OVERLAP_SCALE = 0.8

#: Consecutive rejected trials before a molecule is given up on, and
#: with it the rest.  Five hundred is a second or so on MOF-5 and
#: enough that a pore with room in it is not declared full; a pore
#: without room does not get any fuller from being asked longer.
DEFAULT_ATTEMPTS = 500

#: Grid spacing for finding the free space.  Coarser than the pore
#: surface's: this only chooses where to *try*, and every trial is
#: then tested exactly.
SPACING = 0.5

#: Where a copy put beside an atom goes: its centre this far from the
#: atom, in Angstrom.  The inner edge is past a contact -- Na and O at
#: the default overlap scale touch at 3.0 A -- and the outer is still
#: the atom's neighbourhood rather than the next pore over.
NEAR = (3.5, 5.0)

#: Orientations tried when a molecule put at a point is turned for
#: room: 15 ms on HKUST-1, so the dialog's preview can afford it.
TURNS = 500

#: How far from the point the host is looked at for contacts, beyond
#: the molecule's own reach.  Anything further is no contact anybody
#: needs named.
LOOK = 8.0


def guest_molecules(structure) -> list[Fragment]:
    """Every distinct discrete molecule in ``structure``.

    A framework is not one -- it never closes -- and nor is a lone
    marker.  Markers are taken off what is left
    (:meth:`Fragment.without_dummies`), because a centroid somebody
    placed on the solvent they drew is not part of the solvent.

    One per formula, the first found.  Dry ice is four CO2 molecules,
    and offering "CO2" four times over is asking somebody to choose
    between answers that are the same.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    out: dict[str, Fragment] = {}
    for part in graph.fragments():
        if part.periodic:
            continue
        guest = Fragment.from_selection(structure, cell, part.atoms,
                                        graph).without_dummies()
        if guest.is_empty or guest.formula in out:
            continue
        out[guest.formula] = guest
    return list(out.values())


@dataclass(frozen=True)
class Contact:
    """The closest approach of a molecule put at a point: which of its
    atoms, to what, how far, and what fraction of the two atoms' van
    der Waals contact that is -- the number a clash is judged by."""

    atom: str
    other: str
    distance: float
    ratio: float
    #: What ``other`` belongs to: ``"host"``, ``"copy"`` (another copy
    #: the group made) or ``"image"`` (the molecule a cell over).
    of: str = "host"

    def sentence(self) -> str:
        whose = {"host": "", "copy": " of another copy",
                 "image": " of its own image a cell over"}[self.of]
        return (f"{self.atom} is {self.distance:.2f} A from "
                f"{self.other}{whose}, {self.ratio:.2f} of their van "
                f"der Waals contact")


@dataclass(frozen=True)
class Placement:
    """Where each copy went -- ``(n_atoms, 3)`` cartesian arrays, whole
    molecules, centres inside the cell -- and how many were asked for."""

    guest: Fragment
    positions: tuple
    requested: int
    #: With anchors, the ones no copy could be put beside, by label --
    #: named rather than counted, because which atom is left without
    #: its counter-ion is the thing somebody goes and looks at.
    missed: tuple = ()
    #: Whether each copy was put beside an atom rather than anywhere.
    beside: bool = False
    #: Put at a point (:func:`at_point`): its fractional coordinates.
    point: tuple | None = None
    #: The point's closest contact, and the overlap scale it is judged
    #: against -- what makes it a warning rather than a remark.
    contact: Contact | None = None
    overlap_scale: float = DEFAULT_OVERLAP_SCALE
    #: Kept in the host's space group: the group's order, and how many
    #: atoms its expansion makes of the molecule.  Fewer than the
    #: molecule's atoms times the order is a special position.
    keep_group: bool = False
    order: int = 1
    atoms_made: int = 0

    @property
    def placed(self) -> int:
        return len(self.positions)

    @property
    def crowded(self) -> bool:
        """Closer to something than the overlap scale lets two atoms
        come -- what random filling would have refused."""
        return (self.contact is not None
                and self.contact.ratio < self.overlap_scale)

    @property
    def special(self) -> bool:
        """Kept in its group, and some of the copies fell on each
        other: fewer atoms than the molecule times the order."""
        return (self.keep_group
                and self.atoms_made < self.guest.n_atoms * self.order)

    def warnings(self) -> list[str]:
        """What a molecule put at a point owes the user: it was placed
        anyway, because the point was theirs."""
        out = []
        if self.special:
            out.append(
                f"The point is a special position: the group makes "
                f"{self.atoms_made} atoms of {self.guest.formula}, not "
                f"{self.guest.n_atoms} x {self.order}, so copies of the "
                f"molecule fall on each other.  Undo, and insert it "
                f"without keeping the group or at another point.")
        if self.crowded:
            out.append(f"Crowded: {self.contact.sentence()}.")
        return out

    def message(self) -> str:
        formula = self.guest.formula
        if self.point is not None:
            where = ", ".join(f"{x:.4f}" for x in self.point)
            head = f"placed {formula} at ({where})"
            if self.keep_group and self.order > 1:
                head += (f", copied by the group to "
                         f"{self.atoms_made} atoms")
            return head
        if self.beside:
            head = (f"placed {self.placed} {formula}, one beside each "
                    f"of {self.requested} atom(s)")
            if not self.missed:
                return head
            names = ", ".join(self.missed[:8])
            more = (f" and {len(self.missed) - 8} more"
                    if len(self.missed) > 8 else "")
            return (f"placed {self.placed} of {self.requested} "
                    f"{formula}: no room beside {names}{more}")
        if self.placed == self.requested:
            return f"placed {self.placed} {formula}"
        return (f"placed {self.placed} of {self.requested} {formula}: "
                f"no room was found for the rest")


def capacity(host, guest: Fragment,
             overlap_scale: float = DEFAULT_OVERLAP_SCALE,
             radius_of=el.vdw_radius) -> int:
    """About how many copies of ``guest`` the free volume could hold.

    The host's free volume -- grid points outside every scaled van der
    Waals sphere -- over the volume the guest's own scaled spheres
    enclose.  An upper bound: no arrangement of real molecules fills
    space, and random insertion stops a long way short of one that
    tries.  It is there so that "fill with 500" into a pore with room
    for 50 is seen to be hopeless before anything runs.
    """
    if guest.is_empty:
        return 0
    field = _free_space(host, overlap_scale, radius_of)
    free = float(np.count_nonzero(field > 0.0)) / field.size
    volume = free * abs(float(np.linalg.det(host.lattice.matrix)))
    own = _enclosed_volume(guest, overlap_scale, radius_of)
    return int(volume // own) if own > 0 else 0


def place(host, guest: Fragment, count: int, *,
          overlap_scale: float = DEFAULT_OVERLAP_SCALE,
          seed: int | None = None,
          max_attempts: int = DEFAULT_ATTEMPTS,
          radius_of=el.vdw_radius,
          anchors=None, near=NEAR) -> Placement:
    """Put up to ``count`` copies of ``guest`` into ``host`` where
    each touches nothing.  Changes nothing; see :class:`Placement`.

    The same ``seed`` places the same molecules in the same places,
    which is what lets a dialog's preview and its OK agree, and a test
    say where something went.

    ``anchors`` -- atoms of the P1 cell -- asks a different question:
    one copy *beside each*, its centre between ``near[0]`` and
    ``near[1]`` Angstrom from the atom, and ``count`` is then how many
    anchors there are.  It is what putting a counter-ion by every
    charged site of a framework is: the cations of an anionic MOF sit
    by its carboxylates, not anywhere there is room.  Every copy is
    tested exactly as a pore's solvent is, against the host, the
    copies already placed and its own images, so an ion is never put
    on the one beside the next anchor.  An anchor with no room is
    named (:attr:`Placement.missed`) and the rest still get theirs.
    """
    if anchors is not None:
        return _beside(host, guest, [int(a) for a in anchors], near,
                       overlap_scale, seed, max_attempts, radius_of)
    count = max(0, int(count))
    if guest.is_empty or count == 0:
        return Placement(guest, (), count)
    rng = np.random.default_rng(seed)
    lattice = host.lattice
    scale = float(overlap_scale)
    guest_r, host_space, self_images = _spaces(host, guest, scale,
                                               radius_of)

    field = _free_space(host, scale, radius_of)
    # Every atom of the guest has to clear the host, and none is
    # further from the centre than it is; so the centre itself has to
    # clear by at least the most any one atom needs, less the most a
    # trial can stray from its grid point.  Only where to try -- a
    # trial is then tested exactly.
    centre_clearance = float(np.max(
        guest_r - np.linalg.norm(guest.cart, axis=1))) - SPACING
    shape = np.array(field.shape)
    candidates = np.argwhere(field > centre_clearance)
    if not len(candidates):
        return Placement(guest, (), count)

    placed: list[np.ndarray] = []
    guests = None
    failures = 0
    while len(placed) < count and failures < max_attempts:
        pick = candidates[rng.integers(len(candidates))]
        frac = (pick + rng.random(3) - 0.5) / shape
        frac -= np.floor(frac)
        trial = (guest.cart @ _random_rotation(rng).T
                 + lattice.to_cart(frac))
        if not _fits(trial, guest_r, host_space, guests, self_images):
            failures += 1
            continue
        failures = 0
        placed.append(trial)
        guests = _placed(lattice, placed, guest_r)
    return Placement(guest, tuple(placed), count)


def _beside(host, guest: Fragment, anchors, near, overlap_scale, seed,
            max_attempts, radius_of) -> Placement:
    """:func:`place` with anchors: one copy in a shell around each."""
    if guest.is_empty or not anchors:
        return Placement(guest, (), len(anchors), beside=True)
    inner, outer = sorted(float(r) for r in near)
    rng = np.random.default_rng(seed)
    lattice = host.lattice
    guest_r, host_space, self_images = _spaces(host, guest,
                                               float(overlap_scale),
                                               radius_of)
    cell = p1.expand(host)
    placed: list[np.ndarray] = []
    missed: list[str] = []
    guests = None
    for anchor in anchors:
        centre = lattice.to_cart(cell.frac[anchor])
        for _attempt in range(max(1, int(max_attempts))):
            direction = rng.normal(size=3)
            direction /= float(np.linalg.norm(direction)) or 1.0
            # Uniform in the shell's volume, not in its radius: drawn
            # by radius the inner surface would be tried as often as
            # the outer, which is three times the area.
            radius = np.cbrt(rng.uniform(inner ** 3, outer ** 3))
            trial = (guest.cart @ _random_rotation(rng).T
                     + centre + radius * direction)
            if _fits(trial, guest_r, host_space, guests, self_images):
                # Whole, with its centre in the cell, as a pore's
                # solvent is placed: the atom may sit on a face.
                middle = lattice.to_frac(trial.mean(axis=0))
                trial = trial - lattice.to_cart(np.floor(middle))
                placed.append(trial)
                guests = _placed(lattice, placed, guest_r)
                break
        else:
            missed.append(cell.labels[anchor] or cell.elements[anchor])
    return Placement(guest, tuple(placed), len(anchors),
                     missed=tuple(missed), beside=True)


def at_point(host, guest: Fragment, frac, *, turn: bool = False,
             keep_group: bool = False,
             overlap_scale: float = DEFAULT_OVERLAP_SCALE,
             seed: int | None = None, turns: int = TURNS,
             radius_of=el.vdw_radius) -> Placement:
    """One copy of ``guest`` with its centroid at fractional ``frac``.
    Changes nothing; :func:`insert_command` is what commits it.

    As drawn -- the source's own cartesian frame -- unless ``turn``,
    and then the best of ``turns`` seeded orientations by closest
    contact, as drawn among them, so turning never leaves less room.
    ``keep_group`` measures the copies the host's operations will
    make as well, and counts the atoms they come to.  A clash is put
    in :attr:`Placement.contact` and never stops the placing.
    """
    frac = np.asarray(frac, dtype=float).reshape(3)
    point = tuple(float(x) for x in frac)
    if guest.is_empty:
        return Placement(guest, (), 1, point=point,
                         overlap_scale=overlap_scale,
                         keep_group=keep_group)
    lattice = host.lattice
    centre = lattice.to_cart(frac)
    body = guest.cart - guest.cart.mean(axis=0)
    ops = (host.space_group.operations if keep_group else ())
    room = _Room(host, guest, frac, ops, radius_of)

    best = body
    score, found = room.measure(body)
    if turn:
        rng = np.random.default_rng(seed)
        for _ in range(max(0, int(turns))):
            trial = body @ _random_rotation(rng).T
            trial_score, trial_found = room.measure(trial)
            if trial_score > score:
                best, score, found = trial, trial_score, trial_found
    placed = replace(guest, cart=best)
    order = len(ops) if keep_group else 1
    made = guest.n_atoms
    if keep_group:
        alone = Structure.from_arrays(
            lattice, list(guest.elements),
            lattice.to_frac(best + centre),
            space_group=host.space_group)
        made = p1.expand(alone).n_atoms
    return Placement(placed, (best + centre,), 1, point=point,
                     contact=room.contact(found),
                     overlap_scale=float(overlap_scale),
                     keep_group=keep_group, order=order,
                     atoms_made=made)


def insert_command(placement: Placement, label: str | None = None):
    """The undoable edit that puts :func:`at_point`'s molecule in:
    pasted into the asymmetric unit when the group is kept, so the
    group copies it, and otherwise one copy into the P1 cell
    :class:`InsertMolecules` reduces to."""
    if label is None:
        where = ", ".join(f"{x:.4g}" for x in placement.point)
        label = f"Insert {placement.guest.formula} at ({where})"
    if placement.keep_group:
        centre = placement.positions[0].mean(axis=0)
        return PasteFragment(placement.guest, centre, label)
    return InsertMolecules(placement.guest, placement.positions, label)


class _Room:
    """What a molecule at one point is measured against, built once
    and asked once per orientation.

    The host is its atoms near the point, every lattice image of them
    that could matter, in one tree.  The molecule's own copies -- a
    cell over, and with the group kept every operation's -- are a
    fixed set of affine maps, because the centroid does not move when
    the molecule turns: which copies come near is decided once.
    """

    def __init__(self, host, guest: Fragment, frac, ops, radius_of):
        lattice = host.lattice
        self.lattice = lattice
        self.frac = frac
        centre = lattice.to_cart(frac)
        self.radii = np.array([radius_of(e) for e in guest.elements])
        self.labels = [label or f"{symbol}{k + 1}" for k, (symbol, label)
                       in enumerate(zip(guest.elements, guest.labels
                                        or [""] * guest.n_atoms,
                                        strict=True))]
        extent = float(np.linalg.norm(guest.cart - guest.cart.mean(0),
                                      axis=1).max())

        cell = p1.expand(host)
        solid = [k for k, e in enumerate(cell.elements)
                 if not el.is_dummy(e)]
        reach = extent + LOOK
        points, radii, names = [], [], []
        if solid:
            near = cell.frac[solid] - np.round(cell.frac[solid] - frac)
            # Far enough to hold the nearest atom whatever it is: the
            # middle of a big pore is more than LOOK from anything,
            # and "nothing near" is not the closest contact.
            nearest = float(np.linalg.norm(
                lattice.to_cart(near) - centre, axis=1).min())
            reach = max(reach, nearest + 1.0)
            shells = _shells(lattice, reach)
            for shift in _grid(shells):
                cart = lattice.to_cart(near + shift)
                keep = np.linalg.norm(cart - centre, axis=1) <= reach
                points.append(cart[keep])
                radii.extend(radius_of(cell.elements[solid[k]])
                             for k in np.nonzero(keep)[0])
                names.extend(cell.labels[solid[k]]
                             or cell.elements[solid[k]]
                             for k in np.nonzero(keep)[0])
        self.host = np.concatenate(points) if points else np.zeros((0, 3))
        self.host_r = np.array(radii)
        self.host_names = names
        self.tree = cKDTree(self.host) if len(self.host) else None

        # The copies: every operation, wrapped to put its centroid by
        # the point, then every lattice image near enough to touch.
        if not ops:
            rots, trans = [np.eye(3)], [np.zeros(3)]
        else:
            rots = [np.asarray(op.rot, float) for op in ops]
            trans = [np.asarray(op.trans, float) for op in ops]
        touch = 2.0 * extent + 2.0 * float(self.radii.max())
        maps, kinds = [], []
        shells = _shells(lattice, touch)
        for rot, tr in zip(rots, trans, strict=True):
            image = rot @ frac + tr
            pull = -np.round(image - frac)
            identity = (np.allclose(rot, np.eye(3))
                        and np.allclose(tr, np.round(tr)))
            for shift in _grid(shells):
                moved = pull + shift
                if identity and np.allclose(image + moved, frac):
                    continue
                gap = np.linalg.norm(lattice.to_cart(image + moved - frac))
                if gap <= touch:
                    maps.append((rot, tr + moved))
                    kinds.append("image" if identity else "copy")
        self.maps = maps
        self.kinds = kinds
        self.centre = centre

    def measure(self, body):
        """``(smallest contact ratio, where it was)`` for the molecule
        turned to ``body`` (centred cartesian)."""
        cart = body + self.centre
        best, where = np.inf, None
        if self.tree is not None:
            k = min(8, len(self.host))
            distance, index = self.tree.query(cart, k=k)
            distance = distance.reshape(len(cart), -1)
            index = index.reshape(len(cart), -1)
            ratio = distance / (self.radii[:, None] + self.host_r[index])
            a, b = np.unravel_index(np.argmin(ratio), ratio.shape)
            best = float(ratio[a, b])
            where = ("host", int(a), int(index[a, b]), float(distance[a, b]))
        if self.maps:
            frac = self.lattice.to_frac(cart)
            copies = np.concatenate([frac @ rot.T + tr
                                     for rot, tr in self.maps])
            others = self.lattice.to_cart(copies)
            distance = np.linalg.norm(cart[:, None, :] - others[None],
                                      axis=2)
            n = len(cart)
            ratio = distance / (self.radii[:, None]
                                + np.tile(self.radii, len(self.maps)))
            a, b = np.unravel_index(np.argmin(ratio), ratio.shape)
            if ratio[a, b] < best:
                best = float(ratio[a, b])
                where = (self.kinds[b // n], int(a), int(b % n),
                         float(distance[a, b]))
        return best, where

    def contact(self, where) -> Contact | None:
        if where is None:
            return None
        kind, atom, other, distance = where
        name = (self.host_names[other] if kind == "host"
                else self.labels[other])
        pair = self.radii[atom] + (self.host_r[other] if kind == "host"
                                   else self.radii[other])
        return Contact(self.labels[atom], name, distance,
                       distance / pair, kind)


def _grid(shells):
    """Every lattice translation within ``shells`` cells each way."""
    a, b, c = (range(-int(n), int(n) + 1) for n in shells)
    return [np.array([i, j, k], dtype=float)
            for i in a for j in b for k in c]


def _spaces(host, guest: Fragment, scale: float, radius_of):
    """``(guest radii, the host as a periodic obstacle, the lattice
    vectors a copy could meet itself along)`` -- what either kind of
    placing tests a trial against."""
    lattice = host.lattice
    guest_r = scale * np.array([radius_of(e) for e in guest.elements])
    cell = p1.expand(host)
    solid = [k for k, e in enumerate(cell.elements)
             if not el.is_dummy(e)]
    host_r = scale * np.array([radius_of(cell.elements[k])
                               for k in solid])
    reach = float(guest_r.max()) + float(host_r.max(initial=0.0))
    host_space = _Periodic(lattice, cell.frac[solid], host_r, reach)
    extent = 2.0 * float(np.linalg.norm(guest.cart, axis=1).max())
    self_images = _self_images(lattice, extent + 2.0 * guest_r.max())
    return guest_r, host_space, self_images


def _fits(trial, guest_r, host_space, guests, self_images) -> bool:
    return (host_space.clear(trial, guest_r)
            and (guests is None or guests.clear(trial, guest_r))
            and _clear_of_itself(trial, guest_r, self_images))


def _placed(lattice, placed, guest_r):
    """The copies placed so far, as the next trial's obstacle."""
    every = np.concatenate(placed)
    return _Periodic(lattice, lattice.to_frac(every),
                     np.tile(guest_r, len(placed)),
                     2.0 * float(guest_r.max()))


# ----------------------------------------------------------------------

class _Periodic:
    """Atoms of a periodic cell, asked whether a set of spheres fits.

    Every atom is wrapped into the cell and copied into as many
    neighbouring cells as ``reach`` needs, and every question is asked
    of wrapped points -- so a point near a face finds the atom across
    it.  As many shells as the reach needs and not a fixed 27, because
    a guest two contacts long in a five-Angstrom cell meets the cell
    after next.
    """

    def __init__(self, lattice, frac, radii, reach: float):
        self.lattice = lattice
        self.radii = np.asarray(radii, dtype=float)
        frac = np.asarray(frac, dtype=float).reshape(-1, 3)
        frac = frac - np.floor(frac)
        shells = _shells(lattice, reach)
        shifts = np.array([[a, b, c]
                           for a in range(-shells[0], shells[0] + 1)
                           for b in range(-shells[1], shells[1] + 1)
                           for c in range(-shells[2], shells[2] + 1)],
                          dtype=float)
        self.centres = lattice.to_cart(
            (frac[None, :, :] + shifts[:, None, :]).reshape(-1, 3))
        self.index = np.tile(np.arange(len(frac)), len(shifts))
        self.tree = cKDTree(self.centres) if len(self.centres) else None
        self.largest = float(self.radii.max(initial=0.0))

    def clear(self, cart, radii) -> bool:
        if self.tree is None:
            return True
        frac = self.lattice.to_frac(cart)
        wrapped = self.lattice.to_cart(frac - np.floor(frac))
        hits = self.tree.query_ball_point(wrapped,
                                          np.asarray(radii) + self.largest)
        for k, near in enumerate(hits):
            if not near:
                continue
            near = np.asarray(near)
            gap = np.linalg.norm(self.centres[near] - wrapped[k], axis=1)
            if np.any(gap < radii[k] + self.radii[self.index[near]]):
                return False
        return True


def _shells(lattice, reach: float) -> np.ndarray:
    """Neighbouring cells to copy along each axis to cover ``reach``.

    The distance between opposite faces, not the edge length, decides
    it: a sheared cell is thinner than its edges.
    """
    matrix = np.asarray(lattice.matrix, dtype=float)
    volume = abs(float(np.linalg.det(matrix)))
    widths = np.array([
        volume / np.linalg.norm(np.cross(matrix[(k + 1) % 3],
                                         matrix[(k + 2) % 3]))
        for k in range(3)])
    return np.maximum(1, np.ceil(reach / widths)).astype(int)


def _self_images(lattice, reach: float) -> np.ndarray:
    """The lattice vectors a molecule might meet a copy of itself along.

    Empty in any cell wider than the molecule and a contact, which is
    every framework -- the test is then skipped rather than run.
    """
    shells = _shells(lattice, reach)
    matrix = np.asarray(lattice.matrix, dtype=float)
    out = [np.array([a, b, c]) @ matrix
           for a in range(-shells[0], shells[0] + 1)
           for b in range(-shells[1], shells[1] + 1)
           for c in range(-shells[2], shells[2] + 1)
           if (a, b, c) != (0, 0, 0)]
    out = [v for v in out if np.linalg.norm(v) < reach]
    return np.array(out).reshape(-1, 3)


def _clear_of_itself(cart, radii, images) -> bool:
    if not len(images):
        return True
    contact = radii[:, None] + radii[None, :]
    for shift in images:
        gap = np.linalg.norm(cart[:, None, :] + shift - cart[None, :, :],
                             axis=2)
        if np.any(gap < contact):
            return False
    return True


def _free_space(host, scale: float, radius_of) -> np.ndarray:
    """Distance from each grid point to the nearest *scaled* host
    surface.  A marker occupies no space, so it is given none."""
    def scaled(symbol):
        if el.is_dummy(symbol):
            return -np.inf
        return scale * radius_of(symbol)
    return grid.distance_grid(host, scaled, spacing=SPACING)


def _enclosed_volume(guest: Fragment, scale: float, radius_of,
                     spacing: float = 0.2) -> float:
    """The volume inside the union of a molecule's scaled spheres.

    Counted on a grid rather than summed, because a molecule's spheres
    overlap by most of their volume -- CO2's three sum to nearly twice
    what they enclose.
    """
    radii = scale * np.array([radius_of(e) for e in guest.elements])
    lo = (guest.cart - radii[:, None]).min(axis=0)
    hi = (guest.cart + radii[:, None]).max(axis=0)
    axes = [np.arange(a, b + spacing, spacing) for a, b in zip(lo, hi,
                                                              strict=True)]
    points = np.stack(np.meshgrid(*axes, indexing="ij"),
                      axis=-1).reshape(-1, 3)
    distance, index = cKDTree(guest.cart).query(
        points, k=min(len(radii), 8))
    distance = distance.reshape(len(points), -1)
    index = index.reshape(len(points), -1)
    inside = np.any(distance < radii[index], axis=1)
    return float(np.count_nonzero(inside)) * spacing ** 3


def _random_rotation(rng) -> np.ndarray:
    """A rotation drawn uniformly: a normalised four-dimensional
    Gaussian is a uniformly random unit quaternion."""
    q = rng.normal(size=4)
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z),
         2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z),
         2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x),
         1 - 2 * (x * x + y * y)]])
