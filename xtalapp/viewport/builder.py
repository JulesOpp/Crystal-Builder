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

Speed is a feature here, not a nicety: this function runs on every view
change, and a few hundred atoms drawn 2x2x2 is a hundred thousand
candidate pairs if the bond loop is written the obvious way.  The atoms
are emitted in one vectorised pass, and each bond looks only at the
drawn images of its own two ends.

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


def build_scene(structure, settings, selection=None,
                bond_rules=None) -> SceneModel:
    """Build the render model for one structure.

    ``selection`` is a :class:`xtal.core.selection.Selection` over P1
    atom indices; the atoms and bonds it names come back flagged so the
    viewport can highlight them without a second pass over the
    structure.
    """
    style = styles.get(settings.style)
    cell = p1.expand(structure)
    lattice = structure.lattice

    drawn = _emit_atoms(cell, settings, style)
    halves = _Halves()
    if settings.show_bonds and style.draw_bonds and cell.n_atoms:
        graph = bonding.graph(structure, bond_rules)
        _emit_bonds(graph, cell, drawn, halves, settings, style,
                    selection)
    drawn.finish()

    cart = (lattice.to_cart(drawn.frac).astype(np.float32)
            if drawn.count else np.zeros((0, 3), np.float32))
    starts, ends, bond_colors, bond_flags, bond_keys = halves.arrays(
        drawn, lattice)
    flags = _atom_flags(drawn.atom, selection)

    cell_starts, cell_ends, cell_colors = (
        _cell_lines(structure, settings) if settings.show_cell
        else (np.zeros((0, 3), np.float32),) * 2
        + (np.zeros((0, 3), np.uint8),))

    show_atoms = settings.show_atoms and style.radius_factor > 0
    return SceneModel(
        positions=cart if show_atoms else np.zeros((0, 3), np.float32),
        radii=drawn.radius if show_atoms else np.zeros(0, np.float32),
        colors=drawn.color if show_atoms else np.zeros((0, 3), np.uint8),
        atom_index=drawn.atom if show_atoms else np.zeros(0, int),
        atom_cell=drawn.cell if show_atoms else np.zeros((0, 3), int),
        selected=flags if show_atoms else np.zeros(0, bool),
        bond_starts=starts,
        bond_ends=ends,
        bond_colors=bond_colors,
        selected_bonds=bond_flags,
        bond_keys=bond_keys,
        bond_radius=settings.bond_radius,
        bond_render=style.bond_render,
        cell_starts=cell_starts,
        cell_ends=cell_ends,
        cell_colors=cell_colors,
        labels=_labels(drawn, cell, lattice, settings),
        background=tuple(settings.background),
    )


def selection_flags(model, selection):
    """(atom flags, bond flags) for an existing scene.

    Changing what is selected changes nothing about the geometry, so
    the viewport recomputes these two arrays and swaps them in rather
    than rebuilding the scene -- the difference between a click that
    feels instant and one that does not.
    """
    atoms = _atom_flags(model.atom_index, selection)
    bonds = np.zeros(model.n_bond_halves, bool)
    chosen = set() if selection is None else set(selection.bonds)
    if chosen and model.n_bond_halves:
        bonds = np.array([model.bond_key(k) in chosen
                          for k in range(model.n_bond_halves)],
                         dtype=bool)
    return atoms, bonds


def _atom_flags(atom_index, selection):
    picked = set() if selection is None else set(selection.atoms)
    if not picked or not len(atom_index):
        return np.zeros(len(atom_index), bool)
    return np.isin(atom_index,
                   np.fromiter(picked, int, len(picked)))


# ======================================================================
#  ATOMS
# ======================================================================

class _Drawn:
    """The drawn atoms, as parallel arrays.

    The atoms inside the display range are emitted in one vectorised
    pass; the ghosts that complete a bond at the boundary are appended
    one at a time and folded in by :meth:`finish`, so no array is ever
    reallocated per ghost.
    """

    def __init__(self, frac, atom, cell, radius, color, n_cell_atoms):
        self.frac = np.asarray(frac, float).reshape(-1, 3)
        self.atom = np.asarray(atom, int)
        self.cell = np.asarray(cell, int).reshape(-1, 3)
        self.radius = np.asarray(radius, np.float32)
        self.color = np.asarray(color, np.uint8).reshape(-1, 3)
        self.count = len(self.atom)
        # The translation of each instance as a plain int tuple: the
        # bond loop does this arithmetic once per candidate pair, and
        # numpy is the slow way to add three small integers.
        self.shift: list = []
        self._extra: list[tuple] = []
        self.index_of: dict[tuple, int] = {}
        self.by_atom: list = [[] for _ in range(n_cell_atoms)]

    # -- growth --------------------------------------------------------

    def add(self, atom: int, shift: tuple, frac, radius,
            color) -> int:
        """Append one atom outside the display range; returns its
        index."""
        index = self.count
        self._extra.append((frac, atom, shift, radius, color))
        self.shift.append(shift)
        self.index_of[(atom, shift)] = index
        self.by_atom[atom].append(index)
        self.count += 1
        return index

    def finish(self) -> None:
        """Fold the ghosts into the arrays, once."""
        if not self._extra:
            return
        extra = self._extra
        self._extra = []
        self.frac = np.vstack(
            [self.frac, np.array([e[0] for e in extra],
                                 float).reshape(-1, 3)])
        self.atom = np.concatenate(
            [self.atom, np.array([e[1] for e in extra], int)])
        self.cell = np.vstack(
            [self.cell, np.array([e[2] for e in extra],
                                 int).reshape(-1, 3)])
        self.radius = np.concatenate(
            [self.radius, np.array([e[3] for e in extra],
                                   np.float32)])
        self.color = np.vstack(
            [self.color, np.array([e[4] for e in extra],
                                  np.uint8).reshape(-1, 3)])


def _translations(settings) -> np.ndarray:
    """Lattice translations that can place an atom in the range."""
    spans = []
    for lo, hi in settings.ranges:
        spans.append(range(int(np.floor(lo)) - 1, int(np.ceil(hi)) + 1))
    return np.array(list(itertools.product(*spans)), dtype=int)


def _emit_atoms(cell, settings, style) -> _Drawn:
    """Every atom of the P1 cell, at every lattice translation that
    puts it inside the display range."""
    shifts = _translations(settings)
    if cell.n_atoms == 0 or not len(shifts):
        return _Drawn(np.zeros((0, 3)), np.zeros(0, int),
                      np.zeros((0, 3), int), np.zeros(0, np.float32),
                      np.zeros((0, 3), np.uint8), cell.n_atoms)

    # (T, N, 3): every atom under every candidate translation.  The
    # survivors come out translation-major, atom-minor, which is the
    # order the nested loop this replaced produced.
    frac = cell.frac[None, :, :] + shifts[:, None, :].astype(float)
    lo = np.array([r[0] for r in settings.ranges]) - RANGE_TOL
    hi = np.array([r[1] for r in settings.ranges]) + RANGE_TOL
    inside = np.all((frac >= lo) & (frac <= hi), axis=2)
    where, atom = np.nonzero(inside)

    radius_of, color_of = _appearance(cell, settings, style)
    drawn = _Drawn(frac[where, atom], atom, shifts[where],
                   radius_of[atom], color_of[atom], cell.n_atoms)

    # The two lookups the bond matcher lives on: "where is atom k at
    # translation s" and "where is every image of atom k".  Built from
    # plain Python lists, because that is what they are read as.
    atoms = atom.tolist()
    drawn.shift = [tuple(s) for s in shifts[where].tolist()]
    drawn.index_of = dict(zip(zip(atoms, drawn.shift, strict=True),
                              range(len(atoms)), strict=True))
    for index, a in enumerate(atoms):
        drawn.by_atom[a].append(index)
    return drawn


def _appearance(cell, settings, style):
    """Radius and colour per *P1 atom*, looked up once per element
    rather than once per drawn instance."""
    radii, colors = {}, {}
    for element in set(cell.elements):
        radii[element] = style.atom_radius(element, settings)
        colors[element] = settings.color_for(element)
    radius = np.array([radii[e] for e in cell.elements],
                      dtype=np.float32)
    color = np.array([colors[e] for e in cell.elements],
                     dtype=np.uint8).reshape(-1, 3)
    return radius, color


# ======================================================================
#  BONDS
# ======================================================================

class _Halves:
    """Half-bonds, collected as pairs of drawn-atom indices.

    Nothing is turned into geometry while the bonds are being matched:
    the pairs are resolved to coordinates and colours in one vectorised
    pass at the end, which is most of what makes a large picture cheap
    to rebuild.
    """

    def __init__(self):
        self.near: list = []
        self.far: list = []
        self.flags: list = []
        self.keys: list = []

    def add(self, near: int, far: int, key, selected) -> None:
        self.near.append(near)
        self.far.append(far)
        self.flags.append(selected)
        self.keys.append(key)

    def arrays(self, drawn, lattice):
        """(starts, ends, colours, flags, keys), two halves per bond.

        Each half runs from its own atom to the midpoint and takes that
        atom's colour; the two halves of a bond stay adjacent, which is
        what the viewport and the tests rely on.
        """
        if not self.near:
            return (np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.uint8),
                    np.zeros(0, bool),
                    np.zeros((0, 5), int))
        near = np.array(self.near, dtype=int)
        far = np.array(self.far, dtype=int)
        ends_of_half = np.empty(2 * len(near), dtype=int)
        ends_of_half[0::2] = near
        ends_of_half[1::2] = far

        start_frac = drawn.frac[ends_of_half]
        middle = (drawn.frac[near] + drawn.frac[far]) / 2.0
        starts = lattice.to_cart(start_frac).astype(np.float32)
        ends = lattice.to_cart(np.repeat(middle, 2, axis=0)
                               ).astype(np.float32)
        return (starts, ends, drawn.color[ends_of_half],
                np.repeat(np.array(self.flags, bool), 2),
                np.repeat(np.array(self.keys, int).reshape(-1, 5), 2,
                          axis=0))


def _emit_bonds(graph, cell, drawn, halves, settings, style,
                selection=None):
    """Match every bond of the graph to the drawn images of its ends.

    A bond joins atom ``i`` to atom ``j`` displaced by ``image``, so
    the image of ``i`` at translation ``s`` pairs with the image of
    ``j`` at ``s + image``.  Each pair is offered from both ends and
    drawn from the lower index, which is how it gets drawn exactly
    once.
    """
    chosen = set() if selection is None else set(selection.bonds)
    complete = settings.boundary == "bonded"
    radius_of, color_of = _appearance(cell, settings, style)
    shift_of, index_of = drawn.shift, drawn.index_of

    for bond in graph.bonds:
        key = _key_row(bond.key())
        selected = bond.key() in chosen
        u, v, w = (int(n) for n in bond.image)
        # Snapshotted, because completing a bond at the boundary
        # appends to these very lists.
        sides = ((bond.j, (u, v, w), list(drawn.by_atom[bond.i])),
                 (bond.i, (-u, -v, -w), list(drawn.by_atom[bond.j])))
        for far_atom, (du, dv, dw), group in sides:
            for start in group:
                s = shift_of[start]
                far_shift = (s[0] + du, s[1] + dv, s[2] + dw)
                end = index_of.get((far_atom, far_shift))
                if end is None:
                    if not complete:
                        continue
                    end = drawn.add(
                        far_atom, far_shift,
                        cell.frac[far_atom] + np.asarray(far_shift,
                                                         float),
                        radius_of[far_atom], color_of[far_atom])
                elif end < start:
                    continue            # drawn from the other side
                halves.add(start, end, key, selected)


def _key_row(key) -> tuple:
    """A graph bond key flattened to five integers, so it can live in
    an array on the scene model."""
    i, j, image = key
    return (int(i), int(j), *(int(v) for v in image))


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


def _labels(drawn, cell, lattice, settings):
    mode = settings.label_mode
    if mode == "none" or not drawn.count:
        return ()
    if mode == "element":
        text_of = list(cell.elements)
    elif mode == "label":
        text_of = [cell.labels[k] or cell.elements[k]
                   for k in range(cell.n_atoms)]
    elif mode == "index":
        text_of = [str(k) for k in range(cell.n_atoms)]
    else:
        return ()
    cart = lattice.to_cart(drawn.frac)
    return tuple((tuple(cart[i]), text_of[int(drawn.atom[i])])
                 for i in range(drawn.count))
