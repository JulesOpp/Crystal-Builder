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

Periodic throughout: a guest near one face is tested against the
framework across the other, and against its own images when the cell
is small enough for it to meet them.  Qt-free, like everything in
:mod:`xtal.build`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from xtal.analysis import grid
from xtal.commands.clipboard import Fragment
from xtal.core import bonding, p1
from xtal.core import elements as el

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
class Placement:
    """Where each copy went -- ``(n_atoms, 3)`` cartesian arrays, whole
    molecules, centres inside the cell -- and how many were asked for."""

    guest: Fragment
    positions: tuple
    requested: int

    @property
    def placed(self) -> int:
        return len(self.positions)

    def message(self) -> str:
        formula = self.guest.formula
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
          radius_of=el.vdw_radius) -> Placement:
    """Put up to ``count`` copies of ``guest`` into ``host`` where
    each touches nothing.  Changes nothing; see :class:`Placement`.

    The same ``seed`` places the same molecules in the same places,
    which is what lets a dialog's preview and its OK agree, and a test
    say where something went.
    """
    count = max(0, int(count))
    if guest.is_empty or count == 0:
        return Placement(guest, (), count)
    rng = np.random.default_rng(seed)
    lattice = host.lattice
    scale = float(overlap_scale)
    guest_r = scale * np.array([radius_of(e) for e in guest.elements])

    cell = p1.expand(host)
    solid = [k for k, e in enumerate(cell.elements)
             if not el.is_dummy(e)]
    host_r = scale * np.array([radius_of(cell.elements[k])
                               for k in solid])
    reach = float(guest_r.max()) + float(host_r.max(initial=0.0))
    host_space = _Periodic(lattice, cell.frac[solid], host_r, reach)

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

    extent = 2.0 * float(np.linalg.norm(guest.cart, axis=1).max())
    self_images = _self_images(lattice, extent + 2.0 * guest_r.max())
    placed: list[np.ndarray] = []
    guests = None
    failures = 0
    while len(placed) < count and failures < max_attempts:
        pick = candidates[rng.integers(len(candidates))]
        frac = (pick + rng.random(3) - 0.5) / shape
        frac -= np.floor(frac)
        trial = (guest.cart @ _random_rotation(rng).T
                 + lattice.to_cart(frac))
        clear = (host_space.clear(trial, guest_r)
                 and (guests is None or guests.clear(trial, guest_r))
                 and _clear_of_itself(trial, guest_r, self_images))
        if not clear:
            failures += 1
            continue
        failures = 0
        placed.append(trial)
        every = np.concatenate(placed)
        guests = _Periodic(lattice, lattice.to_frac(every),
                           np.tile(guest_r, len(placed)),
                           2.0 * float(guest_r.max()))
    return Placement(guest, tuple(placed), count)


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
