"""
xtalapp.viewport.picking
========================
Turning a click into an atom or a bond.

The intersection maths is done on the CPU against the scene model's own
arrays rather than through VTK's hardware selector.  Three reasons:

* it is exact -- a hit means the ray really entered that sphere, not
  that a pixel happened to be that colour;
* it is deterministic and testable with no GPU, which is why picking
  has unit tests at all;
* it works the same in perspective and orthographic projection, and
  through glyph mappers, which the id-buffer approach does not do for
  free.

Only the ray construction needs VTK, and it is one small function kept
apart from the maths.
"""

from __future__ import annotations

import numpy as np

BOND_PICK_SLACK = 1.4       # bonds are easier to hit than they look


def ray_from_display(renderer, x: float, y: float):
    """(origin, unit direction) of the ray under a display pixel.

    ``x``/``y`` are VTK display coordinates, i.e. measured from the
    bottom-left of the render window -- Qt measures from the top, so
    the caller flips y.
    """
    renderer.SetDisplayPoint(float(x), float(y), 0.0)
    renderer.DisplayToWorld()
    near = np.array(renderer.GetWorldPoint())
    renderer.SetDisplayPoint(float(x), float(y), 1.0)
    renderer.DisplayToWorld()
    far = np.array(renderer.GetWorldPoint())
    near = near[:3] / (near[3] if near[3] else 1.0)
    far = far[:3] / (far[3] if far[3] else 1.0)
    direction = far - near
    length = np.linalg.norm(direction)
    if length < 1e-12:
        return near, np.array([0.0, 0.0, 1.0])
    return near, direction / length


def atom_hit(model, origin, direction):
    """(index, distance to the entry point) for the nearest atom the
    ray enters, or None.

    The distance is where the ray *enters the sphere*, not where the
    centre is.  Comparing centres would let a bond passing in front of
    a large atom lose to it, and a bond behind a small one win.
    """
    if model.n_atoms == 0:
        return None
    origin = np.asarray(origin, dtype=float)
    direction = np.asarray(direction, dtype=float)

    centres = model.positions.astype(float) - origin
    along = centres @ direction                    # distance to the
    perpendicular2 = (np.einsum("ij,ij->i", centres, centres)
                      - along ** 2)                #   closest approach
    radii = model.radii.astype(float)
    hit = (perpendicular2 <= radii ** 2) & (along > 0)
    if not np.any(hit):
        return None
    depth = np.where(hit,
                     along - np.sqrt(np.maximum(
                         radii ** 2 - perpendicular2, 0.0)),
                     np.inf)
    index = int(np.argmin(depth))
    return index, float(depth[index])


def pick_atom(model, origin, direction) -> int | None:
    """Index of the nearest atom the ray enters, or None."""
    found = atom_hit(model, origin, direction)
    return None if found is None else found[0]


def bond_hit(model, origin, direction):
    """(index, distance along the ray) for the nearest bond half the
    ray passes through, or None."""
    if model.n_bond_halves == 0:
        return None
    origin = np.asarray(origin, dtype=float)
    direction = np.asarray(direction, dtype=float)
    starts = model.bond_starts.astype(float)
    ends = model.bond_ends.astype(float)
    radius = float(model.bond_radius) * BOND_PICK_SLACK

    # Closest approach between the ray (origin + t * direction) and
    # each bond segment (start + s * segment), s clamped to [0, 1].
    # Naming follows the standard segment-segment formulation:
    #   u = segment, v = ray direction, w0 = start - origin
    u = ends - starts
    v = direction
    w0 = starts - origin
    a = np.einsum("ij,ij->i", u, u)         # |u|^2
    b = u @ v                               # u . v
    d = np.einsum("ij,ij->i", u, w0)        # u . w0
    e = w0 @ v                              # v . w0
    denominator = a - b * b                 # |v| is 1, so c = 1
    degenerate = np.abs(denominator) < 1e-12

    s = np.where(degenerate, 0.0,
                 (b * e - d) / np.where(degenerate, 1.0, denominator))
    s = np.clip(s, 0.0, 1.0)
    t = e + b * s
    closest_on_segment = starts + u * s[:, None]
    closest_on_ray = origin + direction * t[:, None]
    distance = np.linalg.norm(closest_on_segment - closest_on_ray,
                              axis=1)

    hit = (distance <= radius) & (t > 0)
    if not np.any(hit):
        return None
    depth = np.where(hit, t, np.inf)
    index = int(np.argmin(depth))
    return index, float(depth[index])


def pick_bond(model, origin, direction) -> int | None:
    """Index of the nearest bond half the ray passes through."""
    found = bond_hit(model, origin, direction)
    return None if found is None else found[0]


def pick(model, origin, direction):
    """(kind, index) for the nearest thing under the ray.

    ``kind`` is "atom", "bond" or None.  Whichever the ray reaches
    first wins, measured at the entry point; atoms win an exact tie,
    because a click on the join between an atom and the bond leaving it
    means the atom.
    """
    atom = atom_hit(model, origin, direction)
    bond = bond_hit(model, origin, direction)
    if atom is None and bond is None:
        return None, None
    if bond is None:
        return "atom", atom[0]
    if atom is None:
        return "bond", bond[0]
    return ("atom", atom[0]) if atom[1] <= bond[1] + 1e-9 \
        else ("bond", bond[0])
