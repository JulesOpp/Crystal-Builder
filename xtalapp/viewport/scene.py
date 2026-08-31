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


# What an atom's ellipsoid rests on.  Ordered by how much is known.
UNMEASURED = 0
NON_POSITIVE = 1
ISOTROPIC = 2
ANISOTROPIC = 3

THERMAL_NAMES = {
    UNMEASURED: "no displacement parameters",
    NON_POSITIVE: "non-positive-definite",
    ISOTROPIC: "isotropic only",
    ANISOTROPIC: "anisotropic",
}


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
    # ORTEP.  (M,3,3) transforms carrying a unit sphere onto each
    # atom's displacement ellipsoid, empty when the atoms are spheres.
    atom_tensors: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3, 3), np.float32))
    # (M,) what each ellipsoid is really made of: ANISOTROPIC for a
    # measured tensor, ISOTROPIC for a U_iso blown up into a sphere,
    # UNMEASURED for an atom the refinement said nothing about, and
    # NON_POSITIVE for one whose tensor has no ellipsoid at all.  The
    # picture has to distinguish them or it claims measurements that
    # were never made.
    atom_thermal: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.uint8))

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
    # (K,) how many electron pairs each half draws -- 1, 1.5, 2, 3 --
    # and (K,3) the unit direction to offset the extra tubes along.
    # The direction is the builder's business and not the renderer's:
    # it is the local pi plane, and getting it from anywhere else makes
    # the second tube of every double bond flip as the camera turns.
    bond_orders: np.ndarray = field(
        default_factory=lambda: np.zeros(0, np.float32))       # (K,)
    bond_offsets: np.ndarray = field(default_factory=_empty)   # (K,3)

    # topology bonds: the net, drawn over the chemistry rather than in
    # place of it.  One segment per edge and not two halves, because it
    # takes one flat colour -- a net edge belongs to neither of the
    # atoms it joins.
    topology_starts: np.ndarray = field(default_factory=_empty)   # (T,3)
    topology_ends: np.ndarray = field(default_factory=_empty)     # (T,3)
    topology_keys: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 5), int))
    topology_selected: np.ndarray = field(
        default_factory=lambda: np.zeros(0, bool))
    topology_radius: float = 0.35
    topology_color: tuple = (124, 96, 200)
    topology_opacity: float = 0.55

    # coordination polyhedra: triangles over a shared vertex list
    polyhedron_points: np.ndarray = field(default_factory=_empty)
    polyhedron_faces: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), int))          # (F,3)
    polyhedron_colors: np.ndarray = field(
        default_factory=lambda: _empty(3, np.uint8))            # (F,3)
    polyhedron_opacity: float = 0.75

    # unit cell wireframe
    cell_starts: np.ndarray = field(default_factory=_empty)    # (L,3)
    cell_ends: np.ndarray = field(default_factory=_empty)      # (L,3)
    cell_colors: np.ndarray = field(
        default_factory=lambda: _empty(3, np.uint8))           # (L,3)

    # Depth cueing: a fade towards the background with distance from
    # the camera.  Carried on the model like the background and the
    # polyhedron opacity, so everything the renderer needs arrives in
    # one object and an offscreen render behaves like the viewport.
    depth_cue: bool = False
    depth_cue_strength: float = 0.7

    labels: tuple = ()                  # ((x, y, z), "text"), ...
    legend: tuple = ()                  # (("Fe", (r, g, b)), ...)
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
    def n_topology_edges(self) -> int:
        return len(self.topology_starts)

    def topology_key(self, edge: int) -> tuple:
        """Provenance of net edge ``edge``: the (i, j, image) key of the
        P1-cell bond it draws."""
        row = self.topology_keys[edge]
        return (int(row[0]), int(row[1]),
                (int(row[2]), int(row[3]), int(row[4])))

    @property
    def n_polyhedron_faces(self) -> int:
        return len(self.polyhedron_faces)

    @property
    def is_empty(self) -> bool:
        return (self.n_atoms == 0 and self.n_bond_halves == 0
                and self.n_cell_lines == 0
                and self.n_topology_edges == 0
                and self.n_polyhedron_faces == 0)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """(min, max) cartesian corner of everything drawn."""
        chunks = [c for c in (self.positions, self.bond_starts,
                              self.bond_ends, self.cell_starts,
                              self.cell_ends, self.polyhedron_points,
                              self.topology_starts,
                              self.topology_ends)
                  if len(c)]
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

    @property
    def draws_ellipsoids(self) -> bool:
        return bool(len(self.atom_tensors))

    def thermal_report(self) -> str:
        """What the ellipsoids in this picture are actually made of.

        Worth saying out loud.  An ORTEP drawing whose atoms are half
        of them fallbacks looks exactly like one whose atoms were all
        measured, and the difference is the whole value of the
        picture.
        """
        if not len(self.atom_thermal):
            return ""
        counts: dict[int, int] = {}
        for kind in self.atom_thermal.tolist():
            counts[kind] = counts.get(kind, 0) + 1
        parts = [f"{counts[k]} {THERMAL_NAMES[k]}"
                 for k in sorted(counts, reverse=True) if k in counts]
        return ", ".join(parts)

    @property
    def has_multiple_bonds(self) -> bool:
        """Is anything here drawn as more than one tube?"""
        return bool(len(self.bond_orders)
                    and np.any(self.bond_orders > SINGLE_MAX))

    def bond_key(self, half: int) -> tuple:
        """Provenance of bond half ``half``: the (i, j, image) key of
        the P1-cell bond it draws."""
        row = self.bond_keys[half]
        return (int(row[0]), int(row[1]),
                (int(row[2]), int(row[3]), int(row[4])))


# ======================================================================
#  BOND ORDER, AS GEOMETRY
# ======================================================================
#
# A double bond is two tubes and a triple is three, offset along the
# direction the builder worked out from the local pi plane.  An
# aromatic bond is one tube with a dashed line inside it, which is the
# convention every chemistry program uses and the only one that stays
# readable when every bond in the ring has the same order.

SINGLE_MAX = 1.25           # up to here, one tube and nothing else
AROMATIC_MAX = 1.75         # up to here, a tube plus a dashed line
DOUBLE_MAX = 2.5            # up to here, two tubes; beyond it, three

#: Distance between adjacent tube centres, in bond radii.  Wide enough
#: that two tubes read as two at a glance, narrow enough that a double
#: bond still reads as one bond.
ORDER_SEPARATION = 2.4
#: How thin the aromatic inner line is, relative to the bond.
DASH_RADIUS = 0.45
DASHES_PER_HALF = 3
DASH_DUTY = 0.55            # fraction of each dash slot that is drawn


def split_by_order(model) -> tuple[tuple, tuple]:
    """``(solid, dashed)`` line sets for the bonds this model draws.

    Each is ``(starts, ends, colors)``.  The solid set is what gets
    tubes at the bond radius: one line for a single bond, two for a
    double, three for a triple.  The dashed set is the thin inner line
    that marks an aromatic bond, already broken into dashes, and is
    empty whenever nothing is aromatic.

    A model with no orders on it -- which is what the builder produces
    when the user has turned bond orders off -- comes back as its own
    lines and nothing else, so the caller needs no special case.
    """
    starts = np.asarray(model.bond_starts, dtype=np.float32)
    ends = np.asarray(model.bond_ends, dtype=np.float32)
    colors = np.asarray(model.bond_colors, dtype=np.uint8)
    empty = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32),
             np.zeros((0, 3), np.uint8))
    if not len(starts) or len(model.bond_orders) != len(starts):
        return (starts, ends, colors), empty

    orders = np.asarray(model.bond_orders, dtype=float)
    offsets = (np.asarray(model.bond_offsets, dtype=np.float32)
               * (float(model.bond_radius) * ORDER_SEPARATION))

    single = orders <= SINGLE_MAX
    aromatic = (~single) & (orders <= AROMATIC_MAX)
    double = (orders > AROMATIC_MAX) & (orders <= DOUBLE_MAX)
    triple = orders > DOUBLE_MAX

    # The centre line is drawn for everything except a double bond,
    # which straddles the axis instead of sitting on it.
    lanes = [(~double, np.zeros_like(offsets)),
             (double, offsets * 0.5), (double, offsets * -0.5),
             (triple, offsets), (triple, -offsets)]
    solid = _gather(lanes, starts, ends, colors)

    dashed = empty
    if np.any(aromatic):
        shifted = _gather([(aromatic, offsets)], starts, ends, colors)
        dashed = _dash(*shifted)
    return solid, dashed


def _gather(lanes, starts, ends, colors):
    """Stack the selected half-bonds, each displaced by its lane."""
    picked = [(np.flatnonzero(mask), shift) for mask, shift in lanes]
    picked = [(rows, shift) for rows, shift in picked if len(rows)]
    if not picked:
        return (np.zeros((0, 3), np.float32),
                np.zeros((0, 3), np.float32),
                np.zeros((0, 3), np.uint8))
    return (np.vstack([starts[r] + shift[r] for r, shift in picked]),
            np.vstack([ends[r] + shift[r] for r, shift in picked]),
            np.vstack([colors[r] for r, _shift in picked]))


def _dash(starts, ends, colors):
    """Break each line into evenly spaced dashes.

    VTK's OpenGL2 backend has no line stipple, and a tube filter draws
    whatever segments it is given -- so a dashed line is simply several
    short lines, which is also the only spelling that survives being
    turned into geometry for a screenshot.
    """
    if not len(starts):
        return starts, ends, colors
    direction = ends - starts
    slot = 1.0 / DASHES_PER_HALF
    lo, hi, tint = [], [], []
    for d in range(DASHES_PER_HALF):
        a = d * slot
        b = a + slot * DASH_DUTY
        lo.append(starts + direction * a)
        hi.append(starts + direction * b)
        tint.append(colors)
    return (np.vstack(lo).astype(np.float32),
            np.vstack(hi).astype(np.float32),
            np.vstack(tint).astype(np.uint8))
