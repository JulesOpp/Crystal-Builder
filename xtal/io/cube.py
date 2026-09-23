"""
xtal.io.cube
============
Gaussian cube files: a scalar field on a grid, with the atoms it is of.

What ``waveplot`` writes an orbital as, and what nearly every
electronic-structure code writes a density as.  The header is Bohr --
a *negative* voxel count would mean Angstrom, and is honoured -- and
the values run with the first axis slowest, which is C order.

Read only.  Nothing here writes one, and the field is not a structure:
it is marched into a surface (:mod:`xtal.analysis.isosurface`) and
drawn over the crystal it came from.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.io.text import read_text

BOHR = 0.52917721090380


@dataclass(frozen=True)
class Cube:
    """``values[i, j, k]`` at ``origin + i*axes[0] + j*axes[1] +
    k*axes[2]``, positions in Angstrom."""

    origin: np.ndarray
    axes: np.ndarray                    # (3, 3): one voxel step a row
    values: np.ndarray                  # (ni, nj, nk)
    numbers: np.ndarray                 # atomic numbers
    positions: np.ndarray               # (n, 3) Angstrom
    comment: str = ""

    @property
    def shape(self) -> tuple:
        return self.values.shape

    def points(self) -> np.ndarray:
        """Every grid point's position, C order, Angstrom."""
        index = np.indices(self.shape).reshape(3, -1).T
        return self.origin + index @ self.axes


def read_cube(path) -> Cube:
    return read_cube_string(read_text(path))


def read_cube_string(text: str) -> Cube:
    lines = text.splitlines()
    if len(lines) < 6:
        raise ValueError("a cube file needs two comment lines, the "
                         "origin and three axes")
    comment = " ".join(line.strip() for line in lines[:2]).strip()
    head = lines[2].split()
    n_atoms = abs(int(head[0]))
    origin = np.array([float(v) for v in head[1:4]])
    counts, axes, angstrom = [], [], []
    for row in lines[3:6]:
        parts = row.split()
        count = int(parts[0])
        counts.append(abs(count))
        axes.append([float(v) for v in parts[1:4]])
        angstrom.append(count < 0)
    if min(counts) <= 0:
        raise ValueError("a cube file's grid has no points along an "
                         "axis")
    scale = 1.0 if all(angstrom) else BOHR
    numbers, positions = [], []
    for row in lines[6:6 + n_atoms]:
        parts = row.split()
        numbers.append(int(float(parts[0])))
        positions.append([float(v) for v in parts[2:5]])
    data = np.array(" ".join(lines[6 + n_atoms:]).split(), dtype=float)
    size = int(np.prod(counts))
    if data.size < size:
        raise ValueError(f"the cube file holds {data.size} values for "
                         f"a {counts[0]}x{counts[1]}x{counts[2]} grid")
    return Cube(origin=origin * scale,
                axes=np.array(axes) * scale,
                values=data[:size].reshape(counts),
                numbers=np.array(numbers, dtype=int),
                positions=np.array(positions).reshape(-1, 3) * scale,
                comment=comment)
