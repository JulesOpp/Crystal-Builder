"""
render_framing
==============
Where the camera goes so that the whole structure is in the picture.

Julius's scene puts a 40 mm camera at one fixed place, which frames
one structure of one size.  This keeps the camera's *direction* and
moves it along that direction until every corner of the imported
objects' bounding box is inside the frustum, then sets the render
region to where those corners land.

It is standard library only and imports nothing of this package, for
two readers: Blender runs ``render_scene.py`` beside it with its own
Python, which has no ``xtal`` on its path, and the tests import it
through :mod:`xtal.modules.blender` with no Blender at all.  Two
copies of the arithmetic would be two answers to where the camera is.

Blender's camera looks down its own -Z with +X to the right and +Y up,
and ``sensor_fit`` AUTO puts the sensor width across the longer side
of the image -- which is what :func:`half_angles` assumes.
"""

from __future__ import annotations

import math

#: Blender's default sensor width, the one AUTO fit spreads across the
#: longer side of the image.
SENSOR_WIDTH = 36.0

#: How much room is left around the structure, as a fraction of the
#: frame's half-width.
MARGIN = 0.05


def rotation(degrees) -> tuple[tuple[float, ...], ...]:
    """The matrix of Blender's XYZ Euler angles, given in degrees."""
    x, y, z = (math.radians(d) for d in degrees)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    # R = Rz @ Ry @ Rx: XYZ order applies X first.
    return ((cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
            (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
            (-sy, cy * sx, cy * cx))


def half_angles(focal: float, width: int, height: int,
                sensor: float = SENSOR_WIDTH) -> tuple[float, float]:
    """tan of the half field of view across and up the image."""
    wide = (sensor / 2.0) / focal
    if width >= height:
        return wide, wide * height / width
    return wide * width / height, wide


def corners(low, high) -> list[tuple[float, float, float]]:
    return [(x, y, z) for x in (low[0], high[0])
            for y in (low[1], high[1]) for z in (low[2], high[2])]


def _to_camera(matrix, vector):
    """``R^T v``: a world vector in the camera's own axes."""
    return tuple(sum(matrix[r][c] * vector[r] for r in range(3))
                 for c in range(3))


def forward(matrix) -> tuple[float, float, float]:
    """The way the camera looks, in world axes: its own -Z."""
    return tuple(-matrix[r][2] for r in range(3))


def middle(points) -> tuple[float, float, float]:
    """The middle of the box around ``points``."""
    return tuple((min(p[axis] for p in points)
                  + max(p[axis] for p in points)) / 2.0
                 for axis in range(3))


def frame(points, degrees, focal: float, width: int, height: int,
          margin: float = MARGIN) -> tuple[float, float, float]:
    """The camera's place: turned by ``degrees``, aimed at the middle of
    ``points``, and as close as it can be with every one of them in the
    picture.

    In the camera's axes a point is at ``(a, b, c)`` from the middle,
    and a camera ``t`` back along the view axis sees it at depth
    ``t - c``; it is in the frame when ``|a| <= k_x (t - c)`` and
    likewise for ``b``.  So the distance is a maximum over the points,
    in closed form -- no search.  The points are the corners of what
    is drawn rather than of one box around it all: seen obliquely a
    box's corners are mostly empty space, and framing them leaves the
    structure small and off to one side.
    """
    matrix = rotation(degrees)
    tan_x, tan_y = half_angles(focal, width, height)
    k_x, k_y = tan_x / (1.0 + margin), tan_y / (1.0 + margin)
    centre = middle(points)
    distance = 0.0
    for point in points:
        a, b, c = _to_camera(
            matrix, tuple(p - m for p, m in zip(point, centre,
                                                 strict=True)))
        distance = max(distance, c + abs(a) / k_x, c + abs(b) / k_y)
    look = forward(matrix)
    return tuple(m - distance * f
                 for m, f in zip(centre, look, strict=True))


def project(point, location, degrees, focal: float, width: int,
            height: int) -> tuple[float, float] | None:
    """Where ``point`` lands in the image, 0..1 left to right and
    bottom to top as Blender's render region counts; None when it is
    behind the camera."""
    matrix = rotation(degrees)
    tan_x, tan_y = half_angles(focal, width, height)
    a, b, c = _to_camera(
        matrix, tuple(p - q for p, q in zip(point, location,
                                            strict=True)))
    depth = -c
    if depth <= 0.0:
        return None
    return (0.5 + a / (2.0 * tan_x * depth),
            0.5 + b / (2.0 * tan_y * depth))


def region(points, location, degrees, focal: float, width: int,
           height: int, pad: float = 0.02) -> tuple[float, ...]:
    """The render region, ``(min_x, max_x, min_y, max_y)`` in 0..1,
    around where ``points`` land and clipped to the image.  The whole
    image when one is behind the camera, since then the outline is not
    where the points land."""
    landed = [project(point, location, degrees, focal, width, height)
              for point in points]
    if not landed or any(point is None for point in landed):
        return 0.0, 1.0, 0.0, 1.0
    xs = [point[0] for point in landed]
    ys = [point[1] for point in landed]

    def clip(value):
        return min(1.0, max(0.0, value))
    return (clip(min(xs) - pad), clip(max(xs) + pad),
            clip(min(ys) - pad), clip(max(ys) + pad))
