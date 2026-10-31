"""
xtal.graphene.twist
===================
Commensurate twists of two honeycomb layers: which angles close into a
cell, how many atoms that cell holds, and the two layers' integer
cells in it.

**A twist is commensurate only at angles (m, r) name** (Lopes dos
Santos, Peres and Castro Neto 2007): a lattice vector ``w`` of the
lower layer turned onto another of the same length ``v``, in the
60-degree basis ``w = (m + r, m)`` and ``v = (m, m + r)``, so

    cos t = (3m^2 + 3mr + r^2/2) / (3m^2 + 3mr + r^2),

and with gcd(m, r) = 1 and r not a multiple of three the cell they
span with their 60-degree turns is the whole coincidence lattice:
3m^2 + 3mr + r^2 of the sheet's cells a layer, 4(3m^2 + 3mr + r^2)
atoms a bilayer.  (1, 1) is 21.79 degrees and 28 atoms; (30, 1) is
the magic angle, 1.08 degrees and 11 164.  r a multiple of three is
a cell a third the size and is not built here: its angles are 60
degrees less the simple family's, so nothing near the small angles
anybody asks for is missing.

**An angle is read to the precision it was written at**, as a site's
coordinates are: "1.08" is any commensurate angle within 0.005 of
it, and the smallest cell among those is the one built -- the
angles are dense, so "nearest" alone would be a cell of millions.
Never coarser than two decimals, or "2" would be 2.45.  An angle is
spelled back (:func:`spelled`) with as many decimals as it takes to
come back to the same cell, which is what the form's list writes.

Nothing here lays atoms out; :func:`xtal.graphene.build.build` does,
from :func:`matrices`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

__all__ = ["Twist", "TwistError", "MAX_ATOMS", "matrices", "angle_of",
           "table", "nearest", "written", "read", "spelled"]

#: The largest bilayer the table enumerates: past every size
#: profile's hard limit but Warn only's, and 34 000 twists.
MAX_ATOMS = 1_000_000

#: The coarsest an angle is read at, degrees: half the second place.
COARSEST = 0.005


class TwistError(ValueError):
    """An angle no commensurate cell is close enough to."""


@dataclass(frozen=True)
class Twist:
    """One commensurate twist."""

    m: int
    r: int

    @property
    def cells(self) -> int:
        """The sheet's cells in one layer of the twisted cell."""
        return 3 * self.m ** 2 + 3 * self.m * self.r + self.r ** 2

    @property
    def atoms(self) -> int:
        """Atoms in one bilayer of the twisted cell."""
        return 4 * self.cells

    @property
    def angle(self) -> float:
        return angle_of(self.m, self.r)

    @property
    def label(self) -> str:
        return (f"{spelled(self)}°, (m, r) = ({self.m}, {self.r}): "
                f"{_count(self.atoms)} atoms a bilayer")


def angle_of(m: int, r: int) -> float:
    """The twist (m, r) names, degrees."""
    n = 3 * m * m + 3 * m * r + r * r
    # 1 - cos, not cos: at (30, 1) cos is 0.99982 and acos of it has
    # lost four of its digits.
    return math.degrees(2.0 * math.asin(math.sqrt(r * r / (4.0 * n))))


def matrices(twist: Twist) -> tuple[np.ndarray, np.ndarray]:
    """The twisted cell in each layer's own hexagonal cell (rows, the
    120-degree basis :mod:`xtal.graphene.build` uses): the lower
    layer's and the upper's, turned by ``twist.angle`` counterclockwise
    about the origin.  The same two vectors, so each layer is whole in
    the cell; the second is t2 - t1, 120 degrees from the first."""
    m, r = twist.m, twist.r
    # 60-degree basis, where a turn by 60 is (i, j) -> (-j, i + j).
    lower = ((m, m + r), (-(m + r), 2 * m + r))
    upper = ((m + r, m), (-m, 2 * m + r))

    def hexagonal(rows):
        # (i, j) in the 60-degree basis is i a1 + j (a1 + a2), and
        # t2 - t1 makes the pair 120 degrees apart.
        (i1, j1), (i2, j2) = rows
        t1 = np.array([i1 + j1, j1])
        t2 = np.array([i2 + j2, j2])
        return np.array([t1, t2 - t1])
    return hexagonal(lower), hexagonal(upper)


@lru_cache(maxsize=1)
def table() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every simple commensurate twist up to :data:`MAX_ATOMS`:
    angles, m and r, sorted by angle.  A tenth of a second, once."""
    limit = MAX_ATOMS // 4
    angles, ms, rs = [], [], []
    r = 1
    while 3 + 3 * r + r * r <= limit:
        if r % 3:
            # 3m^2 + 3mr + r^2 <= limit, solved for m.
            top = int((-3 * r + math.sqrt(9 * r * r - 12 * (r * r - limit)))
                      / 6.0)
            m = np.arange(1, top + 1)
            m = m[(np.gcd(m, r) == 1)
                  & (3 * m * m + 3 * m * r + r * r <= limit)]
            n = 3 * m * m + 3 * m * r + r * r
            angles.append(np.degrees(2 * np.arcsin(np.sqrt(
                r * r / (4.0 * n)))))
            ms.append(m)
            rs.append(np.full_like(m, r))
        r += 1
    angles = np.concatenate(angles)
    order = np.argsort(angles, kind="stable")
    return (angles[order], np.concatenate(ms)[order],
            np.concatenate(rs)[order])


def _count(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _cells(m, r):
    return 3 * m * m + 3 * m * r + r * r


def nearest(angle: float, count: int = 8,
            max_atoms: int = MAX_ATOMS) -> list[Twist]:
    """The ``count`` commensurate twists closest to ``angle`` among
    cells of up to ``max_atoms`` atoms a bilayer, closest first."""
    angles, ms, rs = table()
    keep = 4 * _cells(ms, rs) <= max_atoms
    angles, ms, rs = angles[keep], ms[keep], rs[keep]
    if not len(angles):
        return []
    at = int(np.searchsorted(angles, angle))
    low, high = max(at - count, 0), min(at + count, len(angles))
    near = sorted(range(low, high), key=lambda k: abs(angles[k] - angle))
    return [Twist(int(ms[k]), int(rs[k])) for k in near[:count]]


def tolerance(text: str) -> float:
    """Half a unit in the last place ``text`` was written to, and
    never more than :data:`COARSEST`."""
    text = text.strip().lower()
    mantissa = text.split("e")[0]
    places = len(mantissa.split(".")[1]) if "." in mantissa else 0
    return min(0.5 * 10.0 ** -places, COARSEST)


def written(text) -> tuple[float, str]:
    """The angle ``text`` writes, degrees, and the number as written
    (whose places are its precision), with any ``°`` or ``deg``
    taken off.  The form's list of nearby angles reads the box through
    this too, so whatever builds also lists."""
    text = str(text).strip().rstrip("°").strip()
    if text.lower().endswith("deg"):
        text = text[:-3].strip()
    try:
        return float(text), text
    except ValueError:
        raise TwistError(f"the twist must be an angle in degrees, not "
                         f"{text!r}") from None


def read(text) -> Twist:
    """The smallest commensurate cell whose angle is the one written,
    to the precision it was written at."""
    angle, text = written(text)
    if not 0.0 < angle < 60.0:
        raise TwistError(f"the twist must be between 0 and 60 degrees, "
                         f"not {text}")
    within = tolerance(text)
    angles, ms, rs = table()
    low = int(np.searchsorted(angles, angle - within, side="left"))
    high = int(np.searchsorted(angles, angle + within, side="right"))
    if low == high:
        near = nearest(angle, 1)[0]
        raise TwistError(
            f"no commensurate twist of up to {_count(MAX_ATOMS)} atoms "
            f"is within {within:g} degrees of {text}; the nearest is "
            f"{spelled(near)} ({_count(near.atoms)} atoms)")
    cells = _cells(ms[low:high], rs[low:high])
    k = low + int(np.argmin(cells))
    return Twist(int(ms[k]), int(rs[k]))


def spelled(twist: Twist) -> str:
    """``twist``'s angle with as few decimals as read back to it: two
    at least, six at most."""
    for places in range(2, 7):
        text = f"{twist.angle:.{places}f}"
        try:
            if read(text) == twist:
                return text
        except TwistError:
            pass
    return f"{twist.angle:.6f}"
