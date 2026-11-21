"""
xtal.printing.primitives
========================
A cut cell as balls and sticks, each in color 1 or color 2.

A ball per atom at Atomic Blender's radius times the ball scale (a
hydrogen times the hydrogen scale again), and a flat-ended stick per
bond from centre to centre -- the model the one-color export prints.

**A half-and-half bond changes color at the middle of the part of it
that shows**, halfway between the two ball surfaces rather than the two
nuclei: a zinc's ball would otherwise swallow most of its half, and the
printed bond would look as if it belonged to the oxygen.  Where two
balls overlap past that point it is clamped inside the bond.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.printing import radii

#: How a bond is colored.
BONDS = ("1", "2", "half")

BALL, STICK = 0, 1


@dataclass(frozen=True)
class Primitives:
    """``kind`` ball or stick; a ball is at ``a`` (``b`` the same), a
    stick runs ``a`` to ``b``; ``radius`` and ``color`` (1 or 2)."""

    kind: np.ndarray
    a: np.ndarray
    b: np.ndarray
    radius: np.ndarray
    color: np.ndarray

    def __len__(self) -> int:
        return len(self.kind)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """The corners of the box every primitive fits in."""
        r = self.radius[:, None]
        lo = np.minimum(self.a, self.b) - r
        hi = np.maximum(self.a, self.b) + r
        return lo, hi

    def area(self) -> float:
        """An upper bound on the surface, for sizing the grid: every
        ball and stick whole, as if nothing overlapped."""
        r = self.radius
        balls = self.kind == BALL
        length = np.linalg.norm(self.b - self.a, axis=1)
        return float(np.sum(4 * np.pi * r[balls] ** 2)
                     + np.sum(2 * np.pi * r[~balls] * length[~balls]))


def ball_radius(symbol: str, ball_scale: float, h_scale: float) -> float:
    scale = ball_scale * (h_scale if symbol in ("H", "D") else 1.0)
    return radii.radius(symbol) * scale


def visible_middle(a, b, ra: float, rb: float):
    """Halfway between the surfaces of balls ``ra`` at ``a`` and ``rb``
    at ``b``, along the bond."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = float(np.linalg.norm(b - a))
    along = (d + ra - rb) / 2
    along = min(max(along, 0.05 * d), 0.95 * d)
    return a + (b - a) * (along / d)


def build(cut, colors, bonds: str = "half", ball_scale: float = 0.8,
          h_scale: float = 2.0, stick_radius: float = 0.4) -> Primitives:
    """The balls and sticks of ``cut``; ``colors[k]`` is image ``k``'s
    color, 1 or 2, and ``bonds`` one of :data:`BONDS`."""
    if bonds not in BONDS:
        raise ValueError(f"bonds must be one of {BONDS}, not {bonds!r}")
    colors = np.asarray(colors, dtype=int)
    cart = np.asarray(cut.cart, dtype=float).reshape(-1, 3)
    ball = np.array([ball_radius(s, ball_scale, h_scale)
                     for s in cut.elements], dtype=float)
    kind = [BALL] * len(cart)
    a, b = list(cart), list(cart)
    radius, color = list(ball), list(colors)
    for i, j, _order in cut.bonds:
        if np.linalg.norm(cart[j] - cart[i]) < 1e-6:
            continue
        if bonds == "half":
            middle = visible_middle(cart[i], cart[j], ball[i], ball[j])
            pieces = ((cart[i], middle, colors[i]),
                      (middle, cart[j], colors[j]))
        else:
            pieces = ((cart[i], cart[j], int(bonds)),)
        for start, end, c in pieces:
            kind.append(STICK)
            a.append(start)
            b.append(end)
            radius.append(stick_radius)
            color.append(c)
    return Primitives(
        kind=np.asarray(kind, dtype=int),
        a=np.asarray(a, dtype=float).reshape(-1, 3),
        b=np.asarray(b, dtype=float).reshape(-1, 3),
        radius=np.asarray(radius, dtype=float),
        color=np.asarray(color, dtype=int))
