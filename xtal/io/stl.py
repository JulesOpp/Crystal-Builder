"""Binary STL, one mesh to a file, for a print.

A two-color print is two STLs (or one 3MF, `xtal.io.threemf`) whose
meshes meet at a shared interface, so the coordinates are written as
float32 exactly as handed over and never re-centred or rescaled: a
slicer that loads both files has to see the interface vertices land on
each other bit for bit, or it reports two bodies that overlap or gap.

The normal stored with each triangle is worked out from its winding
(counter-clockwise seen from outside), because that is what every
slicer actually reads; a degenerate triangle gets a zero normal rather
than a NaN, which some readers refuse outright.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from xtal.io.atomic import replacing

_HEADER = 80
_RECORD = np.dtype([
    ("normal", "<f4", 3),
    ("vertices", "<f4", (3, 3)),
    ("attribute", "<u2"),
])


def _normals(corners: np.ndarray) -> np.ndarray:
    """Unit normals of ``(n, 3, 3)`` triangles, zero where degenerate."""
    cross = np.cross(corners[:, 1] - corners[:, 0],
                     corners[:, 2] - corners[:, 0])
    length = np.linalg.norm(cross, axis=1)
    out = np.zeros_like(cross)
    fine = length > 0
    out[fine] = cross[fine] / length[fine, None]
    return out


def write_stl(path, vertices, triangles, name: str = "") -> Path:
    """Write ``triangles`` (indices into ``vertices``) as binary STL.

    ``name`` goes into the 80-byte header after "Crystal Builder",
    so the header never starts with ``solid``: readers that sniff the
    first bytes would take the file for ASCII STL and read nothing.
    """
    path = Path(path)
    vertices = np.asarray(vertices, dtype=np.float32).reshape(-1, 3)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    corners = vertices[triangles]
    records = np.zeros(len(triangles), dtype=_RECORD)
    # The normal comes from the float32 corners that are written, so
    # it agrees with what a reader recomputes from them.
    records["normal"] = _normals(corners.astype(np.float64))
    records["vertices"] = corners
    label = f"Crystal Builder {name}".strip().encode("ascii", "replace")
    header = label[:_HEADER].ljust(_HEADER, b" ")
    with replacing(path) as partial, open(partial, "wb") as out:
        out.write(header)
        out.write(struct.pack("<I", len(records)))
        out.write(records.tobytes())
    return path


def read_stl(path) -> tuple[np.ndarray, np.ndarray]:
    """``(vertices, triangles)`` of a binary STL, corners welded where
    their float32 coordinates are identical -- no tolerance, because a
    tolerance would hide exactly the mismatch the tests look for."""
    data = Path(path).read_bytes()
    (count,) = struct.unpack_from("<I", data, _HEADER)
    records = np.frombuffer(data, dtype=_RECORD, count=count,
                            offset=_HEADER + 4)
    corners = records["vertices"].reshape(-1, 3)
    vertices, inverse = np.unique(corners, axis=0, return_inverse=True)
    return vertices, inverse.reshape(-1, 3)


__all__ = ["read_stl", "write_stl"]
