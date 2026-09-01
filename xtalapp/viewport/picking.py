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

Only the ray construction and the projection need VTK, and they are two
small functions kept apart from the maths.
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


def project_to_display(renderer, points) -> np.ndarray:
    """(M, 2) display coordinates of world ``points``.

    One matrix multiply for the whole array rather than a call into VTK
    per point: a box drag over a supercell projects tens of thousands
    of atoms and has to do it while the mouse is still moving.

    Points behind the camera come back as NaN.  A perspective divide by
    a negative w folds them round to the *front* of the picture, and a
    rectangle test would then take atoms from behind the viewer -- so
    they are marked unusable rather than quietly wrong, and every
    comparison against NaN is False, which is the answer wanted.
    """
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if not len(points):
        return np.zeros((0, 2))
    width, height = (int(v) for v in renderer.GetSize())
    camera = renderer.GetActiveCamera()
    matrix = camera.GetCompositeProjectionTransformMatrix(
        width / max(height, 1), -1.0, 1.0)
    transform = np.array([[matrix.GetElement(r, c) for c in range(4)]
                          for r in range(4)])

    clip = np.column_stack([points, np.ones(len(points))]) @ transform.T
    w = clip[:, 3]
    normalised = clip[:, :2] / np.where(np.abs(w) < 1e-12, 1.0, w)[:, None]
    origin = renderer.GetOrigin()
    display = np.column_stack([
        (normalised[:, 0] + 1.0) * 0.5 * width + origin[0],
        (normalised[:, 1] + 1.0) * 0.5 * height + origin[1]])
    display[w <= 0] = np.nan
    return display


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
    return _segment_hit(model.bond_starts, model.bond_ends,
                        float(model.bond_radius) * BOND_PICK_SLACK,
                        origin, direction)


def topology_hit(model, origin, direction):
    """The same, for the net drawn over the bonds.

    Its own test rather than a wider radius on the bond one: a net edge
    is thicker and runs *over* the chemistry, so a click that lands on
    both has to be able to prefer it.
    """
    return _segment_hit(model.topology_starts, model.topology_ends,
                        float(model.topology_radius), origin,
                        direction)


def _segment_hit(starts, ends, radius, origin, direction):
    if len(starts) == 0:
        return None
    origin = np.asarray(origin, dtype=float)
    direction = np.asarray(direction, dtype=float)
    starts = np.asarray(starts, dtype=float)
    ends = np.asarray(ends, dtype=float)

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


def pick(model, origin, direction, prefer_topology: bool = False):
    """(kind, index) for the nearest thing under the ray.

    ``kind`` is "atom", "bond", "topology" or None.  Whichever the ray
    reaches first wins, measured at the entry point; atoms win an exact
    tie, because a click on the join between an atom and the bond
    leaving it means the atom.

    A net edge is drawn *over* the bonds and is thicker than they are,
    so on depth alone it would win every click near a framework edge
    and there would be no way to select the bond underneath.  It is
    therefore offered only when it is asked for -- which is what the
    topology mode does -- and ignored otherwise.

    **An edge does not hide its own ends.**  A net edge runs centre to
    centre, so the two atoms it joins are inside it -- and an edge that
    won every click would swallow them both, which means the second
    edge of a net could never be started from where the first one
    ended.  Draw net stopped after one edge.  So an endpoint in front
    of its own edge is picked as the atom it is; every other atom the
    edge covers, a linker's among them, still belongs to the edge,
    because running straight through those atoms is what a net edge is
    for.
    """
    candidates = [("atom", atom_hit(model, origin, direction)),
                  ("bond", bond_hit(model, origin, direction))]
    if prefer_topology:
        found = topology_hit(model, origin, direction)
        if found is not None:
            near = candidates[0][1]
            if near is not None and near[1] <= found[1]:
                atom, _cell = model.instance(near[0])
                i, j, _image = model.topology_key(found[0])
                if atom in (i, j):
                    return "atom", near[0]
            return "topology", found[0]
    live = [(kind, hit) for kind, hit in candidates if hit is not None]
    if not live:
        return None, None
    kind, hit = min(live, key=lambda pair: (
        pair[1][1] + (0.0 if pair[0] == "atom" else 1e-9)))
    return kind, hit[0]
