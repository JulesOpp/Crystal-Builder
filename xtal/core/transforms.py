"""
xtal.core.transforms
====================
Geometry over a bare set of cartesian points.

Free functions, with no notion of a site, a symmetry operation or an
undo stack: the commands in :mod:`xtal.commands.atoms` wrap them, and a
test here can hand one four coordinates and check the answer.

The displacement ellipsoid of a refined atom is here too.  It is the
same kind of object -- a quadratic form turned into a shape -- and it
has to be worked out somewhere no force field and no renderer owns.

Everything is cartesian, on purpose.  A rotation is only rigid in
cartesian space, and so is a projection onto a plane -- doing either in
fractional coordinates shears the fragment in any cell that is not
orthogonal, which is most of them.
"""

from __future__ import annotations

import math

import numpy as np


def best_fit_plane(points) -> tuple[np.ndarray, np.ndarray]:
    """``(centroid, unit normal)`` of the least-squares plane through
    ``points``.

    The singular value decomposition of the mean-centred coordinates
    orders the directions by how much the points vary along them, so
    the last right singular vector is the direction they vary along
    *least* -- which is the plane's normal.

    Fewer than three points do not determine a plane, and are refused
    rather than handed an arbitrary one.
    """
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(points) < 3:
        raise ValueError("a plane needs at least three points")
    centroid = points.mean(axis=0)
    normal = np.linalg.svd(points - centroid)[2][-1]
    return centroid, normal / np.linalg.norm(normal)


def plane_deviation(points) -> float:
    """RMS distance of ``points`` from their own best-fit plane.

    Three points are always coplanar and so is anything smaller, and
    the answer for them is zero rather than an error: this is asked as
    a *question about flatness*, and a triangle is flat.
    """
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(points) < 4:
        return 0.0
    centroid, normal = best_fit_plane(points)
    return float(np.sqrt(np.mean(((points - centroid) @ normal) ** 2)))


def planarize(points) -> tuple[np.ndarray, float]:
    """``(flattened points, largest displacement)``.

    Every point slides along the plane normal and no further, which is
    the smallest move that makes the set coplanar -- and the reason the
    largest of those moves is worth reporting: it is the difference
    between straightening a ring that was nearly flat already and
    silently rebuilding one that was not.
    """
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    centroid, normal = best_fit_plane(points)
    offsets = (points - centroid) @ normal
    moved = points - offsets[:, None] * normal
    return moved, float(np.abs(offsets).max())


# ======================================================================
#  DISPLACEMENT ELLIPSOIDS
# ======================================================================

#: Probability levels an ORTEP picture is normally drawn at.
ELLIPSOID_LEVELS = (0.50, 0.90, 0.99)
MIN_ELLIPSOID_AXIS = 0.02       # Angstrom: below this it is a dot


def probability_scale(probability: float) -> float:
    """How many RMS displacements enclose ``probability`` of the
    density.

    An atom's displacement is a three-dimensional Gaussian, so the
    surface enclosing a given probability is the one at a fixed value
    of chi-squared with three degrees of freedom.  Its cumulative
    distribution has a closed form,

        P(c) = erf(c / sqrt(2)) - sqrt(2/pi) c exp(-c^2 / 2),

    which is solved here by bisection rather than by table lookup, so
    that any probability the user asks for is answered exactly and not
    rounded to the nearest of the three anybody publishes.  The famous
    ones come out at 1.5382 for 50% and 2.5003 for 90%.

    The number matters: an ellipsoid drawn at one RMS displacement
    encloses only 20% of the density and looks far too small for a
    refinement that is actually fine.
    """
    p = float(probability)
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be between 0 and 1, "
                         f"got {probability!r}")

    def enclosed(c: float) -> float:
        return (math.erf(c / math.sqrt(2.0))
                - math.sqrt(2.0 / math.pi) * c * math.exp(-c * c / 2.0))

    low, high = 0.0, 12.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if enclosed(mid) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def ellipsoid_transform(u_cartesian, probability: float = 0.5):
    """The 3x3 matrix carrying a unit sphere onto the displacement
    ellipsoid.

    ``u_cartesian`` is the displacement tensor in cartesian axes -- see
    :meth:`xtal.core.site.Site.u_cartesian`, which is where the CIF's
    U values have to be converted before they get here.

    The tensor is a covariance, so its eigenvectors are the ellipsoid's
    principal axes and the square roots of its eigenvalues are the RMS
    displacements along them.  The result is ``R diag(s)`` with ``R``
    a proper rotation, which is the form a renderer can split back into
    an orientation and three scales.

    A refinement that has gone wrong produces a *non-positive-definite*
    tensor -- the famous "NPD" atom, which has no ellipsoid at all
    because the density it describes is not a peak in every direction.
    The negative axes are clamped to a visible minimum rather than
    producing a NaN, and :func:`is_non_positive_definite` is how a
    caller finds out it happened and says so.
    """
    u = np.asarray(u_cartesian, dtype=float).reshape(3, 3)
    values, vectors = np.linalg.eigh((u + u.T) / 2.0)
    axes = probability_scale(probability) * np.sqrt(
        np.maximum(values, 0.0))
    axes = np.maximum(axes, MIN_ELLIPSOID_AXIS)
    if np.linalg.det(vectors) < 0:
        vectors = vectors.copy()
        vectors[:, 0] = -vectors[:, 0]      # keep it a rotation
    return vectors @ np.diag(axes)


def is_non_positive_definite(u_cartesian, tol: float = 0.0) -> bool:
    """Has this atom refined to a tensor with no ellipsoid?

    Worth asking separately from drawing it: an NPD atom is the single
    most useful thing an ORTEP picture can tell you, and a viewer that
    quietly drew it as a small sphere would be hiding exactly the
    result the picture exists to show.
    """
    u = np.asarray(u_cartesian, dtype=float).reshape(3, 3)
    return bool(np.linalg.eigvalsh((u + u.T) / 2.0).min() <= tol)
