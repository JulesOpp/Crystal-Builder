"""
xtalapp.viewport.builder
========================
Structure + ViewSettings -> SceneModel.

The three jobs here are the ones that make a crystal viewer look like a
crystal viewer rather than a molecule viewer:

**Display range.**  A crystal is infinite; the picture is not.  Atoms
are emitted for every lattice translation that lands them inside the
requested fractional range, which is inclusive at both ends -- so the
atom at x = 0 also appears at x = 1 and the cell looks closed instead
of gnawed.

**Bonds across boundaries.**  A bond is (i, j, translation).  Both ends
have to be drawn instances for the bond to appear; with
``boundary="bonded"`` the missing partner is drawn as well, so
coordination polyhedra at the cell edge stay whole.

**Half-bonds.**  Each bond is split at its midpoint into two segments
that take their own atom's colour, which is how every crystallography
program has drawn two-tone bonds since the 1980s.

No Qt, no VTK: this module is tested headless.
"""

from __future__ import annotations

import itertools

import numpy as np

from xtal.core import bonding, p1
from xtalapp.viewport import styles
from xtalapp.viewport.scene import SceneModel

RANGE_TOL = 1e-6

# The a, b, c edges meeting at the origin are drawn in the traditional
# red / green / blue; the other nine edges take a neutral colour.
AXIS_COLORS = ((220, 60, 60), (60, 170, 60), (60, 100, 220))
CELL_COLOR = (120, 120, 130)


def build_scene(structure, settings, bond_rules=None) -> SceneModel:
    """Build the render model for one structure."""
    style = styles.get(settings.style)
    cell = p1.expand(structure)
    lattice = structure.lattice

    instances, index_of = _emit_atoms(cell, settings, style)
    bond_halves = []
    if settings.show_bonds and style.draw_bonds and cell.n_atoms:
        graph = bonding.graph(structure, bond_rules)
        bond_halves = _emit_bonds(graph, cell, instances, index_of,
                                  settings, style)

    positions = np.array([i["frac"] for i in instances],
                         dtype=float).reshape(-1, 3)
    cart = (lattice.to_cart(positions).astype(np.float32)
            if len(positions) else np.zeros((0, 3), np.float32))

    starts, ends, bond_colors = _bond_arrays(bond_halves, lattice)
    cell_starts, cell_ends, cell_colors = (
        _cell_lines(structure, settings) if settings.show_cell
        else (np.zeros((0, 3), np.float32),) * 2
        + (np.zeros((0, 3), np.uint8),))

    show_atoms = settings.show_atoms and style.radius_factor > 0
    return SceneModel(
        positions=cart if show_atoms else np.zeros((0, 3), np.float32),
        radii=(np.array([i["radius"] for i in instances],
                        dtype=np.float32) if show_atoms
               else np.zeros(0, np.float32)),
        colors=(np.array([i["color"] for i in instances],
                         dtype=np.uint8).reshape(-1, 3) if show_atoms
                else np.zeros((0, 3), np.uint8)),
        atom_index=(np.array([i["atom"] for i in instances], dtype=int)
                    if show_atoms else np.zeros(0, int)),
        atom_cell=(np.array([i["cell"] for i in instances],
                            dtype=int).reshape(-1, 3) if show_atoms
                   else np.zeros((0, 3), int)),
        bond_starts=starts,
        bond_ends=ends,
        bond_colors=bond_colors,
        bond_radius=settings.bond_radius,
        bond_render=style.bond_render,
        cell_starts=cell_starts,
        cell_ends=cell_ends,
        cell_colors=cell_colors,
        labels=_labels(instances, cell, lattice, settings),
        background=tuple(settings.background),
    )


# ======================================================================
#  ATOMS
# ======================================================================

def _translations(settings) -> list[tuple[int, int, int]]:
    """Lattice translations that can place an atom in the range."""
    spans = []
    for lo, hi in settings.ranges:
        spans.append(range(int(np.floor(lo)) - 1, int(np.ceil(hi)) + 1))
    return list(itertools.product(*spans))


def _in_range(frac, settings) -> bool:
    for value, (lo, hi) in zip(frac, settings.ranges, strict=True):
        if not (lo - RANGE_TOL <= value <= hi + RANGE_TOL):
            return False
    return True


def _emit_atoms(cell, settings, style):
    """One entry per drawn atom, plus a lookup from (atom, cell) to its
    index so bonds can find their endpoints."""
    instances = []
    index_of: dict[tuple, int] = {}
    for shift in _translations(settings):
        offset = np.array(shift, dtype=float)
        for k in range(cell.n_atoms):
            frac = cell.frac[k] + offset
            if not _in_range(frac, settings):
                continue
            element = cell.elements[k]
            index_of[(k, shift)] = len(instances)
            instances.append({
                "frac": frac,
                "atom": k,
                "cell": shift,
                "element": element,
                "radius": style.atom_radius(element, settings),
                "color": settings.color_for(element),
            })
    return instances, index_of


def _add_ghost(instances, index_of, cell, key, settings, style):
    """Draw an atom outside the display range because a bond needs it."""
    k, shift = key
    element = cell.elements[k]
    index_of[key] = len(instances)
    instances.append({
        "frac": cell.frac[k] + np.array(shift, dtype=float),
        "atom": k,
        "cell": shift,
        "element": element,
        "radius": style.atom_radius(element, settings),
        "color": settings.color_for(element),
    })
    return index_of[key]


# ======================================================================
#  BONDS
# ======================================================================

def _emit_bonds(graph, cell, instances, index_of, settings, style):
    """Half-bonds as (start_frac, end_frac, colour) triples."""
    halves = []
    for bond in graph.bonds:
        image = np.array(bond.image, dtype=int)
        for (k, shift), start_index in list(index_of.items()):
            if k == bond.i:
                other_key = (bond.j, tuple(np.array(shift) + image))
            elif k == bond.j:
                other_key = (bond.i, tuple(np.array(shift) - image))
            else:
                continue
            end_index = index_of.get(other_key)
            if end_index is None:
                if settings.boundary != "bonded":
                    continue
                end_index = _add_ghost(instances, index_of, cell,
                                       other_key, settings, style)
            if end_index < start_index:
                continue                # drawn from the other side
            a, b = instances[start_index], instances[end_index]
            middle = (a["frac"] + b["frac"]) / 2.0
            halves.append((a["frac"], middle, a["color"]))
            halves.append((b["frac"], middle, b["color"]))
    return halves


def _bond_arrays(halves, lattice):
    if not halves:
        return (np.zeros((0, 3), np.float32),
                np.zeros((0, 3), np.float32),
                np.zeros((0, 3), np.uint8))
    starts = lattice.to_cart(np.array([h[0] for h in halves]))
    ends = lattice.to_cart(np.array([h[1] for h in halves]))
    colors = np.array([h[2] for h in halves], dtype=np.uint8)
    return (starts.astype(np.float32), ends.astype(np.float32),
            colors.reshape(-1, 3))


# ======================================================================
#  CELL AND LABELS
# ======================================================================

# The 12 edges of a unit cube, as pairs of corner indices.
_CUBE_CORNERS = np.array(list(itertools.product((0, 1), repeat=3)),
                         dtype=float)
_CUBE_EDGES = [(i, j) for i in range(8) for j in range(i + 1, 8)
               if np.sum(np.abs(_CUBE_CORNERS[i] - _CUBE_CORNERS[j])) == 1]


def _cell_lines(structure, settings):
    """One box per whole cell in the display range, with the three
    edges at the origin coloured a, b, c."""
    lattice = structure.lattice
    starts, ends, colors = [], [], []
    spans = []
    for lo, hi in settings.ranges:
        spans.append(range(int(np.floor(lo)), max(
            int(np.floor(lo)) + 1, int(np.ceil(hi)))))
    for shift in itertools.product(*spans):
        origin = np.array(shift, dtype=float)
        corners = _CUBE_CORNERS + origin
        for i, j in _CUBE_EDGES:
            a, b = corners[i], corners[j]
            color = CELL_COLOR
            if np.allclose(a, origin) and shift == (0, 0, 0):
                axis = int(np.argmax(np.abs(b - a)))
                color = AXIS_COLORS[axis]
            starts.append(a)
            ends.append(b)
            colors.append(color)
    return (lattice.to_cart(np.array(starts)).astype(np.float32),
            lattice.to_cart(np.array(ends)).astype(np.float32),
            np.array(colors, dtype=np.uint8).reshape(-1, 3))


def _labels(instances, cell, lattice, settings):
    mode = settings.label_mode
    if mode == "none" or not instances:
        return ()
    out = []
    for i in instances:
        if mode == "element":
            text = i["element"]
        elif mode == "label":
            text = cell.labels[i["atom"]] or i["element"]
        elif mode == "index":
            text = str(i["atom"])
        else:
            continue
        out.append((tuple(lattice.to_cart(i["frac"])), text))
    return tuple(out)
