"""
xtalapp.viewport.scene
======================
The render model: flat numpy arrays describing what to draw.

This is the boundary between crystallography and graphics.  Above it,
the builder knows about symmetry, bonds and display ranges; below it,
VTK knows only points, radii, colours and line segments.  Because a
SceneModel is plain arrays, it can be built and asserted on in a test
with no GPU, no window and no VTK at all -- which is where the
rendering regressions get caught.

Every drawn atom carries its provenance (which atom of the P1 cell it
is, and which lattice translation put it there), and so does every bond
half, so a pick in the viewport can be turned back into a site or a
bond of the asymmetric unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _empty(n_cols: int = 3, dtype=np.float32) -> np.ndarray:
    return np.zeros((0, n_cols), dtype=dtype)


@dataclass(frozen=True)
class SceneModel:
    """Everything the viewport draws, as arrays."""

    # atoms
    positions: np.ndarray = field(default_factory=_empty)      # (M,3)
    radii: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.float32))       # (M,)
    colors: np.ndarray = field(
        default_factory=lambda: _empty(3, np.uint8))           # (M,3)
    atom_index: np.ndarray = field(
        default_factory=lambda: np.zeros(0, int))   # into the P1 cell
    atom_cell: np.ndarray = field(
        default_factory=lambda: _empty(3, int))     # lattice shift
    selected: np.ndarray = field(
        default_factory=lambda: np.zeros(0, bool))  # (M,) highlight

    # bonds, already split in half so each end takes its atom's colour
    bond_starts: np.ndarray = field(default_factory=_empty)    # (K,3)
    bond_ends: np.ndarray = field(default_factory=_empty)      # (K,3)
    bond_colors: np.ndarray = field(
        default_factory=lambda: _empty(3, np.uint8))           # (K,3)
    bond_radius: float = 0.15
    bond_render: str = "tube"                                  # tube|line
    selected_bonds: np.ndarray = field(
        default_factory=lambda: np.zeros(0, bool))             # (K,)
    # (K,5): which bond of the P1 cell each half belongs to, as
    # (i, j, image) flattened.  Carrying it here is what lets a click
    # on a bond name the two atoms it really joins, images included,
    # instead of guessing from the geometry.
    bond_keys: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 5), int))

    # unit cell wireframe
    cell_starts: np.ndarray = field(default_factory=_empty)    # (L,3)
    cell_ends: np.ndarray = field(default_factory=_empty)      # (L,3)
    cell_colors: np.ndarray = field(
        default_factory=lambda: _empty(3, np.uint8))           # (L,3)

    labels: tuple = ()                  # ((x, y, z), "text"), ...
    background: tuple = (255, 255, 255)

    @property
    def n_atoms(self) -> int:
        return len(self.positions)

    @property
    def n_bond_halves(self) -> int:
        return len(self.bond_starts)

    @property
    def n_cell_lines(self) -> int:
        return len(self.cell_starts)

    @property
    def is_empty(self) -> bool:
        return (self.n_atoms == 0 and self.n_bond_halves == 0
                and self.n_cell_lines == 0)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """(min, max) cartesian corner of everything drawn."""
        chunks = [c for c in (self.positions, self.bond_starts,
                              self.bond_ends, self.cell_starts,
                              self.cell_ends) if len(c)]
        if not chunks:
            return np.zeros(3), np.zeros(3)
        stacked = np.vstack(chunks)
        pad = float(self.radii.max()) if len(self.radii) else 0.0
        return stacked.min(axis=0) - pad, stacked.max(axis=0) + pad

    def center(self) -> np.ndarray:
        lo, hi = self.bounds()
        return (lo + hi) / 2.0

    @property
    def n_selected(self) -> int:
        return int(self.selected.sum()) if len(self.selected) else 0

    def instance(self, i: int) -> tuple[int, tuple[int, int, int]]:
        """Provenance of drawn atom ``i``: (P1 atom index, cell)."""
        return int(self.atom_index[i]), tuple(self.atom_cell[i])

    def bond_key(self, half: int) -> tuple:
        """Provenance of bond half ``half``: the (i, j, image) key of
        the P1-cell bond it draws."""
        row = self.bond_keys[half]
        return (int(row[0]), int(row[1]),
                (int(row[2]), int(row[3]), int(row[4])))
