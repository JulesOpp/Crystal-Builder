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
coordination polyhedra at the cell edge stay whole, and with
``boundary="half"`` the near half is drawn with nothing on the end of
it, which says "there is more here" without drawing what is not.

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

from xtal.core import bonding, measure, p1, transforms
from xtalapp.viewport import scene as scene_model
from xtalapp.viewport import styles, view_settings
from xtalapp.viewport.scene import SceneModel

RANGE_TOL = 1e-6

# The a, b, c edges meeting at the origin are drawn in the traditional
# red / green / blue; the other nine edges take a neutral colour.
AXIS_COLORS = ((220, 60, 60), (60, 170, 60), (60, 100, 220))
CELL_COLOR = (120, 120, 130)

# The net is drawn over the chemistry rather than in place of it, so it
# has to be distinguishable at a glance from every bond underneath:
# thicker than a bond, and translucent enough to see the framework
# through.  Its colour is the user's -- ``settings.topology_color`` --
# because a flat colour that is nobody's element on a white background
# is somebody's element on a black one.
TOPOLOGY_RADIUS_FACTOR = 2.4
TOPOLOGY_OPACITY = 0.55

#: The empty part of a partly occupied site.  A neutral grey and not
#: the background: a vacancy is something the refinement measured, and
#: a wedge the colour of the paper reads as a hole in the picture.
VACANCY_COLOR = (170, 172, 178)
#: How much bigger than the largest sphere it stands on an occupancy
#: pie is drawn.  It has to cover them, and a wedge sagging inside the
#: sphere underneath z-fights -- the same arithmetic the ORTEP octants
#: in ``vtk_scene`` document, at this tessellation.
PIE_MARGIN = 1.02
PIE_MERIDIANS = 28              # over the whole circle, before cutting
PIE_PARALLELS = 18
#: How far from 1 an occupancy has to be before a site is drawn as
#: partly empty.  Refinements write 0.9999 and mean full.
OCCUPANCY_TOL = 1e-3


def build_scene(structure, settings, selection=None,
                bond_rules=None, view_direction=None,
                planes=()) -> SceneModel:
    """Build the render model for one structure.

    ``selection`` is a :class:`xtal.core.selection.Selection` over P1
    atom indices; the atoms and bonds it names come back flagged so the
    viewport can highlight them without a second pass over the
    structure.

    ``planes`` are :class:`xtal.core.measure.Plane` objects to draw as
    translucent quads.  They are passed in rather than read off the
    structure because they are not on it: a plane is a note the user
    made about the crystal, it lives on the document beside the
    measurements, and which of them are being shown is the user's
    choice made in the Planes list.

    ``view_direction`` is the camera's direction of projection, and is
    used for one thing only: laying the second tube of a bond that has
    no pi plane of its own into the plane of the screen.  Everything
    else here is camera-free, and has to be -- a picture that depended
    on where the camera was would have to be rebuilt on every orbit.
    """
    style = styles.get(settings.style)
    cell = p1.expand(structure)
    lattice = structure.lattice

    drawn = _emit_atoms(cell, settings, style)
    halves = _Halves()
    hulls = _Hulls()
    orders = frames = None
    if cell.n_atoms and (style.draw_polyhedra
                         or (settings.show_bonds and style.draw_bonds)):
        graph = bonding.graph(structure, bond_rules)
        # Polyhedra first, because what they consume the bonds must
        # not draw again: the edges from a centre to its own vertices
        # *are* the polyhedron, and drawing them as well leaves a cage
        # of sticks inside every hull.
        hull_edges = (_emit_polyhedra(graph, cell, drawn, hulls,
                                      settings, style)
                      if style.draw_polyhedra else frozenset())
        if settings.show_bonds and style.draw_bonds:
            _emit_bonds(graph, cell, drawn, halves, settings, style,
                        selection, skip=hull_edges)
            if settings.show_bond_orders:
                orders = bonding.orders(structure, bond_rules)
                frames = _bond_frames(graph, cell, orders,
                                      view_direction)
    drawn.finish()

    cart = (lattice.to_cart(drawn.frac).astype(np.float32)
            if drawn.count else np.zeros((0, 3), np.float32))
    (starts, ends, bond_colors, bond_flags, bond_keys,
     bond_orders, bond_offsets) = halves.arrays(drawn, cell, lattice,
                                                orders, frames)
    if style.bond_color is not None and len(bond_colors):
        # A report figure draws its bonds in ink, so the two-tone rule
        # is overridden here rather than in the halves: they are what
        # a bond *is*, and both ends still carry their own atom's
        # provenance and selection flag.
        bond_colors = np.tile(
            np.array(style.bond_color, np.uint8), (len(bond_colors), 1))
    flags = _atom_flags(drawn.atom, selection)

    cell_starts, cell_ends, cell_colors = (
        _cell_lines(structure, settings) if settings.show_cell
        else (np.zeros((0, 3), np.float32),) * 2
        + (np.zeros((0, 3), np.uint8),))

    net = (_emit_topology(structure, cell, drawn, lattice, settings,
                          selection)
           if settings.show_topology
           else _Segments().arrays())
    faces = (_emit_planes(planes, cell, lattice, settings)
             if settings.show_planes else _no_planes())

    show_atoms = settings.show_atoms and style.radius_factor > 0
    pies = (_emit_pies(cell, drawn, cart)
            if show_atoms and style.occupancy_pies else _no_pies())
    tensors, thermal = (
        _emit_ellipsoids(cell, drawn, structure, settings)
        if show_atoms and style.ellipsoids
        else (np.zeros((0, 3, 3), np.float32), np.zeros(0, np.uint8)))
    return SceneModel(
        positions=cart if show_atoms else np.zeros((0, 3), np.float32),
        radii=drawn.radius if show_atoms else np.zeros(0, np.float32),
        colors=drawn.color if show_atoms else np.zeros((0, 3), np.uint8),
        atom_index=drawn.atom if show_atoms else np.zeros(0, int),
        atom_cell=drawn.cell if show_atoms else np.zeros((0, 3), int),
        selected=flags if show_atoms else np.zeros(0, bool),
        atom_tensors=tensors,
        atom_thermal=thermal,
        ellipsoid_octants=bool(settings.ellipsoid_octants),
        bond_starts=starts,
        bond_ends=ends,
        bond_colors=bond_colors,
        selected_bonds=bond_flags,
        bond_keys=bond_keys,
        bond_orders=bond_orders,
        bond_offsets=bond_offsets,
        bond_radius=settings.bond_radius * style.bond_factor,
        bond_render=style.bond_render,
        shading=style.shading,
        outline=style.outline,
        outline_color=tuple(style.outline_color),
        polyhedron_points=hulls.points(lattice),
        polyhedron_faces=hulls.faces(),
        polyhedron_colors=hulls.colors(),
        polyhedron_opacity=settings.polyhedron_opacity,
        pie_local=pies[0],
        pie_centres=pies[1],
        pie_faces=pies[2],
        pie_colors=pies[3],
        pie_normals=pies[4],
        depth_cue=settings.depth_cue,
        depth_cue_strength=settings.depth_cue_strength,
        depth_cue_start=settings.depth_cue_start,
        depth_cue_gradient=settings.depth_cue_gradient,
        topology_starts=net[0],
        topology_ends=net[1],
        topology_keys=net[2],
        topology_selected=net[3],
        topology_radius=settings.bond_radius * TOPOLOGY_RADIUS_FACTOR,
        topology_color=tuple(settings.topology_color),
        topology_opacity=TOPOLOGY_OPACITY,
        plane_points=faces[0],
        plane_faces=faces[1],
        plane_colors=faces[2],
        normal_starts=faces[3],
        normal_ends=faces[4],
        normal_colors=faces[5],
        scale_bar=settings.show_scale_bar,
        cell_starts=cell_starts,
        cell_ends=cell_ends,
        cell_colors=cell_colors,
        labels=_labels(drawn, cell, lattice, settings),
        legend=_legend(drawn, cell, settings, style),
        background=tuple(settings.background),
    )


def selection_flags(model, selection):
    """(atom flags, bond flags, net flags) for an existing scene.

    Changing what is selected changes nothing about the geometry, so
    the viewport recomputes these arrays and swaps them in rather
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
    net = np.zeros(model.n_topology_edges, bool)
    picked = set() if selection is None else set(
        getattr(selection, "topology", ()))
    if picked and model.n_topology_edges:
        net = np.array([model.topology_key(k) in picked
                        for k in range(model.n_topology_edges)],
                       dtype=bool)
    return atoms, bonds, net


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
        # How many are inside the display range.  Ghosts are appended
        # past this point, so anything that must not draw outside the
        # range -- a coordination polyhedron, say -- stops here.
        self.in_range = self.count
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
        colors[element] = style.atom_color(element, settings)
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

    A bond that runs out of the picture is a **stub**: one half, from
    its own atom to where the midpoint would be, and no sphere on the
    end of it.  Stubs are kept in lists of their own rather than as a
    drawn atom of radius zero, and that is the whole of the decision.
    Every array in the scene model is indexed by drawn atom -- the
    radii, the colours, the labels, the ellipsoids, the legend, the
    selection flags and the picking all read them by that index -- so
    a radius-zero entry is a fictional atom that seven other things
    would each have to learn to skip, and the first one that forgot
    would put a label in mid-air or an element in the legend that is
    not in the picture.

    The far end is named by (atom, translation) and not by a position,
    because the matching loop is integer arithmetic on purpose and a
    numpy add per candidate pair is what this module is written to
    avoid.
    """

    def __init__(self):
        self.near: list = []
        self.far: list = []
        self.flags: list = []
        self.keys: list = []
        self.of_bond: list = []         # index into graph.bonds
        # the stubs, in the same shape but one half each
        self.stub_near: list = []
        self.stub_atom: list = []
        self.stub_shift: list = []
        self.stub_flags: list = []
        self.stub_keys: list = []
        self.stub_of_bond: list = []

    def add(self, near: int, far: int, key, selected,
            bond: int) -> None:
        self.near.append(near)
        self.far.append(far)
        self.flags.append(selected)
        self.keys.append(key)
        self.of_bond.append(bond)

    def add_stub(self, near: int, far_atom: int, far_shift, key,
                 selected, bond: int) -> None:
        """One half of a bond whose far atom is not drawn."""
        self.stub_near.append(near)
        self.stub_atom.append(far_atom)
        self.stub_shift.append(far_shift)
        self.stub_flags.append(selected)
        self.stub_keys.append(key)
        self.stub_of_bond.append(bond)

    def arrays(self, drawn, cell, lattice, orders=None, offsets=None):
        """(starts, ends, colours, flags, keys, orders, offsets).

        Each half runs from its own atom to the midpoint and takes that
        atom's colour.  The two halves of a whole bond stay adjacent,
        which is what the viewport and the tests rely on, and the
        stubs -- one half each, with nothing to be adjacent to --
        follow them.
        """
        starts, ends, colors = [], [], []
        flags, keys, of_bond = [], [], []
        if self.near:
            near = np.array(self.near, dtype=int)
            far = np.array(self.far, dtype=int)
            ends_of_half = np.empty(2 * len(near), dtype=int)
            ends_of_half[0::2] = near
            ends_of_half[1::2] = far
            middle = (drawn.frac[near] + drawn.frac[far]) / 2.0
            starts.append(drawn.frac[ends_of_half])
            ends.append(np.repeat(middle, 2, axis=0))
            colors.append(drawn.color[ends_of_half])
            flags.append(np.repeat(np.array(self.flags, bool), 2))
            keys.append(np.repeat(
                np.array(self.keys, int).reshape(-1, 5), 2, axis=0))
            of_bond.append(np.repeat(np.array(self.of_bond, int), 2))
        if self.stub_near:
            near = np.array(self.stub_near, dtype=int)
            away = (cell.frac[np.array(self.stub_atom, dtype=int)]
                    + np.array(self.stub_shift, dtype=float))
            starts.append(drawn.frac[near])
            ends.append((drawn.frac[near] + away) / 2.0)
            colors.append(drawn.color[near])
            flags.append(np.array(self.stub_flags, bool))
            keys.append(np.array(self.stub_keys, int).reshape(-1, 5))
            of_bond.append(np.array(self.stub_of_bond, int))
        if not starts:
            return (np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.uint8),
                    np.zeros(0, bool),
                    np.zeros((0, 5), int),
                    np.zeros(0, np.float32),
                    np.zeros((0, 3), np.float32))
        # Both halves of a bond carry the same order and the same
        # offset direction, so the two tubes of a double bond meet at
        # the midpoint instead of crossing it.
        if orders is None or offsets is None:
            per_half_order = np.zeros(0, np.float32)
            per_half_offset = np.zeros((0, 3), np.float32)
        else:
            rows = np.concatenate(of_bond)
            per_half_order = np.asarray(orders, np.float32)[rows]
            per_half_offset = np.asarray(offsets, np.float32)[rows]
        return (lattice.to_cart(np.vstack(starts)).astype(np.float32),
                lattice.to_cart(np.vstack(ends)).astype(np.float32),
                np.vstack(colors),
                np.concatenate(flags),
                np.vstack(keys),
                per_half_order, per_half_offset)


def _emit_bonds(graph, cell, drawn, halves, settings, style,
                selection=None, skip=frozenset()):
    """Match every bond of the graph to the drawn images of its ends.

    A bond joins atom ``i`` to atom ``j`` displaced by ``image``, so
    the image of ``i`` at translation ``s`` pairs with the image of
    ``j`` at ``s + image``.  Each pair is offered from both ends and
    drawn from the lower index, which is how it gets drawn exactly
    once.

    ``skip`` names the bonds a polyhedron has already drawn as its own
    edges, which is what makes a picture that is polyhedral at the
    nodes and molecular at the linkers.

    When the far image is not drawn, ``settings.boundary`` decides
    between the three answers: drop the bond, draw the far atom too,
    or draw the near half and stop.
    """
    chosen = set() if selection is None else set(selection.bonds)
    complete = settings.boundary == "bonded"
    stub = settings.boundary == "half"
    radius_of, color_of = _appearance(cell, settings, style)
    shift_of, index_of = drawn.shift, drawn.index_of

    for index, bond in enumerate(graph.bonds):
        if bond.key() in skip:
            continue                    # this one is a polyhedron edge
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
                    if stub:
                        halves.add_stub(start, far_atom, far_shift,
                                        key, selected, index)
                        continue
                    if not complete:
                        continue
                    end = drawn.add(
                        far_atom, far_shift,
                        cell.frac[far_atom] + np.asarray(far_shift,
                                                         float),
                        radius_of[far_atom], color_of[far_atom])
                elif end < start:
                    continue            # drawn from the other side
                halves.add(start, end, key, selected, index)


# ----------------------------------------------------------------------
#  WHERE THE SECOND TUBE GOES
# ----------------------------------------------------------------------
#
# Two parallel tubes need a plane to lie in, and an arbitrary
# perpendicular to the bond is not one: it turns with the camera, and
# the picture flickers on every orbit.  The plane that does not move is
# the molecule's own -- the atoms around the sp2 centre -- so the
# offset direction is the in-plane perpendicular to the bond, which is
# the normal of that plane crossed with the bond axis.
#
# It is also pointed *at* the substituents rather than away from them,
# which is what puts an aromatic ring's inner line inside the ring.


def _bond_frames(graph, cell, orders, view=None) -> np.ndarray:
    """A unit offset direction per bond of the graph.

    Only worked out for the bonds that need one; a single bond is one
    tube down the axis and never asks.
    """
    out = np.zeros((len(graph.bonds), 3))
    if not len(graph.bonds):
        return out
    matrix = cell.lattice.matrix
    cart = cell.cart
    for k, bond in enumerate(graph.bonds):
        if orders[k] <= scene_model.SINGLE_MAX:
            continue
        far = cart[bond.j] + np.asarray(bond.image) @ matrix \
            - cart[bond.i]
        length = float(np.linalg.norm(far))
        if length < 1e-9:                       # pragma: no cover
            continue
        out[k] = _offset_direction(
            far / length, far, _substituents(graph, cart, matrix, bond),
            view)
    return out


def _substituents(graph, cart, matrix, bond) -> np.ndarray:
    """Everything bonded to either end of ``bond`` except each other,
    in a frame with atom ``i`` at the origin.

    Both ends contribute, and they have to: the plane of an amide or a
    carboxylate is set by the atoms around the carbon, and a terminal
    oxygen at the other end of the double bond has none of its own.
    """
    image = np.asarray(bond.image, dtype=int)
    far = cart[bond.j] + image @ matrix - cart[bond.i]
    points = [cart[n] + t @ matrix - cart[bond.i]
              for n, t in graph.neighbors_with_images(bond.i)
              if not (n == bond.j and np.array_equal(t, image))]
    points += [far + cart[n] + t @ matrix - cart[bond.j]
               for n, t in graph.neighbors_with_images(bond.j)
               if not (n == bond.i and np.array_equal(t, -image))]
    return np.array(points) if points else np.zeros((0, 3))


def _offset_direction(axis, far, others, view=None) -> np.ndarray:
    """The in-plane perpendicular to a bond, or the best guess when
    there is no plane.

    A bare diatomic -- an isolated O2, a nitrogen sitting in a pore --
    has no substituents and so no pi plane to be consistent with.
    There the tubes are laid into the plane of the *screen*, which is
    the only way a lone double bond reads as double instead of as one
    fat tube seen edge-on.  It is fixed when the scene is built and not
    while the camera turns, so orbiting the structure does not make the
    picture flicker; it is re-chosen on the next rebuild.

    There is nothing for that to be inconsistent with, which is why it
    is allowed here and nowhere else.
    """
    if not len(others):
        return _view_perpendicular(axis, view)
    cloud = np.vstack([np.zeros(3), far, others])
    _centroid, normal = transforms.best_fit_plane(cloud)
    direction = np.cross(normal, axis)
    length = float(np.linalg.norm(direction))
    if length < 1e-6:                           # pragma: no cover
        return _view_perpendicular(axis, view)
    direction = direction / length
    if direction @ (others.mean(axis=0) - far / 2.0) < 0:
        direction = -direction                  # point it inwards
    return direction


def _view_perpendicular(axis, view) -> np.ndarray:
    """A perpendicular lying in the plane of the screen, when there is
    a camera to ask; otherwise any perpendicular at all."""
    if view is not None:
        direction = np.cross(axis, np.asarray(view, dtype=float))
        length = float(np.linalg.norm(direction))
        if length > 1e-6:
            return direction / length
        # The bond points straight at the camera: it is a dot on the
        # screen and no offset would be visible anyway.
    return _any_perpendicular(axis)


def _any_perpendicular(axis) -> np.ndarray:
    """Some unit vector at right angles to ``axis``.

    Crossed with the cartesian direction the axis leans on *least*,
    which is never within 55 degrees of parallel -- so the cross
    product is never near zero, which is what a fixed choice of trial
    axis gets wrong for exactly the bonds that lie along it.
    """
    trial = np.zeros(3)
    trial[int(np.argmin(np.abs(axis)))] = 1.0
    direction = np.cross(axis, trial)
    return direction / np.linalg.norm(direction)


def _key_row(key) -> tuple:
    """A graph bond key flattened to five integers, so it can live in
    an array on the scene model."""
    i, j, image = key
    return (int(i), int(j), *(int(v) for v in image))


# ======================================================================
#  POLYHEDRA
# ======================================================================

class _Hulls:
    """Coordination polyhedra, as triangles over a shared vertex
    list."""

    def __init__(self):
        self._points: list = []
        self._faces: list = []
        self._colors: list = []

    def add(self, vertices, triangles, color) -> None:
        base = len(self._points)
        self._points.extend(vertices)
        for triangle in triangles:
            self._faces.append([base + int(v) for v in triangle])
            self._colors.append(color)

    def points(self, lattice) -> np.ndarray:
        if not self._points:
            return np.zeros((0, 3), np.float32)
        return lattice.to_cart(
            np.array(self._points, dtype=float)).astype(np.float32)

    def faces(self) -> np.ndarray:
        if not self._faces:
            return np.zeros((0, 3), int)
        return np.array(self._faces, dtype=int).reshape(-1, 3)

    def colors(self) -> np.ndarray:
        if not self._colors:
            return np.zeros((0, 3), np.uint8)
        return np.array(self._colors, dtype=np.uint8).reshape(-1, 3)


def _emit_polyhedra(graph, cell, drawn, hulls, settings,
                    style) -> frozenset:
    """One convex hull per drawn atom with enough neighbours.

    The vertices are the *neighbours*, each in the periodic image the
    bond actually points at -- four of an octahedron's six are usually
    in the next cell along, and taking the copy inside the cell instead
    gives a shape that is not the coordination sphere of anything.

    A polyhedron is drawn once per drawn centre, so it follows the
    display range like everything else.

    Returns the keys of the bonds the hulls used as edges, so a style
    that draws both does not draw those twice.
    """
    try:
        from scipy.spatial import ConvexHull, QhullError
    except ImportError:                             # pragma: no cover
        return frozenset()

    consumed: set = set()
    minimum = max(4, int(settings.polyhedron_min_vertices))
    centres = style.centres(cell.elements, settings)
    for index in range(drawn.in_range):
        centre = int(drawn.atom[index])
        element = cell.elements[centre]
        if element not in centres:
            continue
        partners = graph.neighbors_with_images(centre)
        if len(partners) < minimum:
            continue
        shift = np.asarray(drawn.shift[index], dtype=float)
        vertices = np.array(
            [cell.frac[j] + image + shift for j, image in partners])
        # The hull has to be built in real space: the convex hull of
        # fractional coordinates in a non-orthogonal cell is the hull
        # of a sheared shape, which is a different polyhedron.
        try:
            hull = ConvexHull(cell.lattice.to_cart(vertices))
        except (QhullError, ValueError):
            continue                    # coplanar: no volume, no shape
        hulls.add(vertices, hull.simplices,
                  settings.color_for(element))
        consumed.update(b.key() for b in graph.bonds_of(centre))
    return frozenset(consumed)


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


def _legend(drawn, cell, settings, style) -> tuple:
    """One entry per element actually in the picture, in the order the
    periodic table puts them.

    Built from what is *drawn*, not from what the structure contains:
    a legend that lists an element the display range has cut away is
    telling the reader about a different picture.  The swatch is the
    style's colour and not the palette's for the same reason -- under
    a style that draws pale atoms, a saturated swatch names a colour
    that is nowhere on the screen.
    """
    if not settings.show_legend or not drawn.count:
        return ()
    from xtal.core import elements as el

    present = {cell.elements[int(k)] for k in drawn.atom}
    return tuple((symbol, style.atom_color(symbol, settings))
                 for symbol in sorted(present, key=el.atomic_number))


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


# ======================================================================
#  OCCUPANCY PIES
# ======================================================================

def _no_pies():
    return (np.zeros((0, 3), np.float32),
            np.zeros((0, 3), np.float32),
            np.zeros((0, 3), int),
            np.zeros((0, 3), np.uint8),
            np.zeros((0, 3), np.float32))


def _emit_pies(cell, drawn, cart):
    """VESTA's occupancy spheres: one wedge per occupant of a site.

    A site two things share, or one that is partly empty, is the case
    every other style draws as a lie -- two spheres exactly on top of
    each other, of which the reader sees whichever happens to be
    larger, with nothing on screen to say the other is there.

    **What comes out of here is in a frame of its own**, with the
    wedges cut about +z and the first one starting at +x -- and the
    renderer turns that frame to face the camera, so the pie reads as
    a pie from every angle instead of as stripes from most of them.
    That is the one thing in this module a camera gets a say in, and
    it is kept out of here on purpose: a scene rebuilt on every orbit
    is what the display range and the bond matching exist to avoid, so
    the vertices are emitted once as offsets from their own centre and
    :meth:`~xtalapp.viewport.scene.SceneModel.pie_geometry` turns them
    per frame -- a 3x3 matrix multiply over a few thousand points, and
    only for the sites that have a pie at all.

    **The spheres underneath are still drawn.**  Every array in the
    scene model is indexed by drawn atom -- the labels, the legend,
    the selection flags, the picking -- so dropping the occupants of a
    shared site would put four other things out of step to save
    geometry that is hidden anyway.  The pie is drawn a whisker
    outside the largest of them instead.

    An occupancy over 1 is somebody's refinement and not this
    module's to correct: the wedges are scaled to fit the circle and
    no vacancy is drawn, which shows the site full rather than
    silently dropping the excess.
    """
    occupancy = np.asarray(cell.occupancy, float)[drawn.atom]
    # Sites are shared when they are at the same place, and a CIF
    # writes the same place as the same digits.  Rounding rather than
    # clustering on purpose: a split site at 0.245 and 0.255 is two
    # sites and VESTA draws it as two, so a tolerance wide enough to
    # merge them would be wrong about a real structure.
    _where, group = np.unique(np.round(drawn.frac, 3), axis=0,
                              return_inverse=True)
    members: dict[int, list[int]] = {}
    for index, key in enumerate(group.ravel().tolist()):
        members.setdefault(key, []).append(index)

    local, centres, faces, colors, normals = [], [], [], [], []
    for rows in members.values():
        shares = occupancy[rows]
        total = float(shares.sum())
        if len(rows) == 1 and total > 1.0 - OCCUPANCY_TOL:
            continue
        radius = float(drawn.radius[rows].max()) * PIE_MARGIN
        if radius <= 0.0:
            continue
        scale = max(total, 1.0)
        # Biggest share first, so which colour a site opens with does
        # not depend on the order the sites were written in.
        order = sorted(range(len(rows)),
                       key=lambda k: (-shares[k], rows[k]))
        wedges = []
        start = 0.0
        for k in order:
            end = start + float(shares[k]) / scale
            wedges.append((start, end, tuple(drawn.color[rows[k]])))
            start = end
        if start < 1.0 - OCCUPANCY_TOL:
            wedges.append((start, 1.0, VACANCY_COLOR))
        for lo, hi, color in wedges:
            _wedge(cart[rows[0]], radius, lo, hi,
                   local, centres, faces, colors, normals, color)

    if not faces:
        return _no_pies()
    return (np.concatenate(local).astype(np.float32),
            np.concatenate(centres).astype(np.float32),
            np.concatenate(faces).astype(int),
            np.concatenate(colors).astype(np.uint8),
            np.concatenate(normals).astype(np.float32))


def _wedge(centre, radius, lo, hi, local, centres, faces, colors,
           normals, color):
    """One slice of a sphere, from fraction ``lo`` round to ``hi``.

    In the pie's own frame: the slice runs round the +z axis and the
    centre it belongs to is carried beside it, because where the +z
    axis ends up pointing is the camera's business and not this
    function's.
    """
    meridians = max(2, int(np.ceil((hi - lo) * PIE_MERIDIANS)))
    phi = np.linspace(lo, hi, meridians + 1) * 2.0 * np.pi
    theta = np.linspace(0.0, np.pi, PIE_PARALLELS + 1)
    sin_t, cos_t = np.sin(theta), np.cos(theta)
    verts = np.stack(
        [np.outer(sin_t, np.cos(phi)),
         np.outer(sin_t, np.sin(phi)),
         np.repeat(cos_t[:, None], meridians + 1, axis=1)],
        axis=-1).reshape(-1, 3)

    base = sum(len(block) for block in local)
    local.append(verts * radius)
    centres.append(np.tile(np.asarray(centre, float), (len(verts), 1)))
    normals.append(verts)

    row, column = np.meshgrid(np.arange(PIE_PARALLELS),
                              np.arange(meridians), indexing="ij")
    a = (row * (meridians + 1) + column).ravel() + base
    b, c, d = a + 1, a + meridians + 1, a + meridians + 2
    quads = np.concatenate([np.stack([a, c, b], axis=1),
                            np.stack([b, c, d], axis=1)])
    faces.append(quads)
    colors.append(np.tile(np.asarray(color, np.uint8),
                          (len(quads), 1)))


# ======================================================================
#  THERMAL ELLIPSOIDS
# ======================================================================

def _emit_ellipsoids(cell, drawn, structure, settings):
    """``(transforms, provenance)`` for the ORTEP style.

    A transform per *drawn* atom, worked out once per site of the
    asymmetric unit: every image of a site is the same ellipsoid turned
    by the symmetry operation that placed it, and turning the tensor is
    the whole of that.

    Three fallbacks, and each one has to look like itself:

    * a site refined anisotropically gets its ellipsoid;
    * a site with only ``u_iso`` gets a sphere of the equivalent
      radius -- which is what an isotropic refinement *is*, and reads
      as one because it has no orientation;
    * a site with neither gets a small fixed sphere that does not grow
      when the probability level is raised.  Everything measured swells
      and it stands still, which is the tell.

    An atom whose tensor is not positive definite is the fourth case
    and the most important one: it has no ellipsoid, it is what an
    ORTEP picture is drawn to reveal, and it is reported rather than
    quietly rounded up to something drawable.
    """
    from xtal.core import transforms as tf

    probability = float(settings.ellipsoid_probability)
    lattice = structure.lattice
    per_site: dict[int, tuple] = {}
    for index, site in enumerate(structure.sites):
        per_site[index] = _site_ellipsoid(site, lattice, probability,
                                          settings, tf)

    rotations = [op.rot for op in structure.space_group.operations]
    cart_rot = _cartesian_rotations(rotations, lattice)

    tensors = np.zeros((drawn.count, 3, 3), dtype=np.float32)
    thermal = np.zeros(drawn.count, dtype=np.uint8)
    for k in range(drawn.count):
        atom = int(drawn.atom[k])
        matrix, kind = per_site[int(cell.site_idx[atom])]
        rotation = cart_rot[int(cell.op_idx[atom])]
        tensors[k] = rotation @ matrix
        thermal[k] = kind
    return tensors, thermal


def _site_ellipsoid(site, lattice, probability, settings, tf):
    """One site's unit-sphere transform, and what it rests on."""
    u = site.u_cartesian(lattice)
    if u is not None:
        kind = (scene_model.NON_POSITIVE
                if tf.is_non_positive_definite(u)
                else scene_model.ANISOTROPIC)
        return tf.ellipsoid_transform(u, probability), kind
    if site.u_iso is not None and site.u_iso > 0:
        radius = max(tf.MIN_ELLIPSOID_AXIS,
                     tf.probability_scale(probability)
                     * float(np.sqrt(site.u_iso)))
        return np.eye(3) * radius, scene_model.ISOTROPIC
    fallback = settings.base_radius(site.element, "covalent") * 0.25
    return np.eye(3) * fallback, scene_model.UNMEASURED


def _cartesian_rotations(rotations, lattice):
    """Each symmetry rotation, expressed in cartesian axes.

    A rotation acts on fractional coordinates, and an ellipsoid lives
    in cartesian ones.  Conjugating by the lattice is what carries one
    to the other -- and skipping it draws every symmetry image of an
    atom with the ellipsoid of the site it came from, unturned, which
    in anything below cubic is visibly wrong.
    """
    matrix = np.asarray(lattice.matrix, dtype=float).T
    inverse = np.linalg.inv(matrix)
    return [matrix @ np.asarray(r, dtype=float) @ inverse
            for r in rotations]


# ======================================================================
#  TOPOLOGY
# ======================================================================

class _Segments:
    """Whole edges, not half-bonds.

    A net edge takes one flat colour and belongs to neither of the
    atoms it joins, so it is not split at the midpoint the way a
    chemical bond is -- except when the far vertex is not drawn, where
    the half *is* the edge there is room for.
    """

    def __init__(self):
        self.near: list = []
        self.far: list = []
        self.keys: list = []
        self.flags: list = []
        self.stub_near: list = []
        self.stub_frac: list = []
        self.stub_keys: list = []
        self.stub_flags: list = []

    def add(self, near, far, key, selected) -> None:
        self.near.append(near)
        self.far.append(far)
        self.keys.append(key)
        self.flags.append(selected)

    def add_stub(self, near, far_frac, key, selected) -> None:
        self.stub_near.append(near)
        self.stub_frac.append(far_frac)
        self.stub_keys.append(key)
        self.stub_flags.append(selected)

    def arrays(self, drawn=None, lattice=None):
        starts, ends, keys, flags = [], [], [], []
        if self.near:
            near = np.array(self.near, dtype=int)
            far = np.array(self.far, dtype=int)
            starts.append(drawn.frac[near])
            ends.append(drawn.frac[far])
            keys.append(np.array(self.keys, int).reshape(-1, 5))
            flags.append(np.array(self.flags, bool))
        if self.stub_near:
            near = np.array(self.stub_near, dtype=int)
            away = np.array(self.stub_frac, dtype=float).reshape(-1, 3)
            starts.append(drawn.frac[near])
            ends.append((drawn.frac[near] + away) / 2.0)
            keys.append(np.array(self.stub_keys, int).reshape(-1, 5))
            flags.append(np.array(self.stub_flags, bool))
        if not starts:
            return (np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.float32),
                    np.zeros((0, 5), int),
                    np.zeros(0, bool))
        return (lattice.to_cart(np.vstack(starts)).astype(np.float32),
                lattice.to_cart(np.vstack(ends)).astype(np.float32),
                np.vstack(keys),
                np.concatenate(flags))


def _emit_topology(structure, cell, drawn, lattice, settings,
                   selection):
    """The net, matched to the drawn images of its vertices.

    The same pairing as :func:`_emit_bonds`, with one difference that
    matters: a net edge never completes itself at the boundary.  Its
    two ends are often whole cells apart -- that is what makes it a net
    edge rather than a bond -- and drawing the missing vertex would
    scatter ghost atoms across the picture wherever the box was cut.
    So ``boundary="bonded"`` does nothing here, and the half edge is
    what the net wanted all along: without it a net drawn on one cell
    of **pcu** shows three edges at a six-coordinate vertex, which is
    a wrong picture rather than a missing feature.
    """
    net = bonding.topology_graph(structure)
    segments = _Segments()
    if not net.bonds or not drawn.count:
        return segments.arrays()

    stub = settings.boundary == "half"
    chosen = set() if selection is None else set(
        getattr(selection, "topology", ()))
    shift_of, index_of = drawn.shift, drawn.index_of
    for bond in net.bonds:
        key = _key_row(bond.key())
        selected = bond.key() in chosen
        u, v, w = (int(n) for n in bond.image)
        # Offered from both ends, but drawn whole only from the i
        # side: a stub is anchored to the drawn vertex it starts at,
        # so the j side has stubs of its own to contribute and no
        # whole edge that the i side has not already given.  The flag
        # says which side this is, rather than comparing the atoms --
        # a net edge from a vertex to its own image has i == j.
        for whole, far_atom, (du, dv, dw), group in (
                (True, bond.j, (u, v, w), drawn.by_atom[bond.i]),
                (False, bond.i, (-u, -v, -w), drawn.by_atom[bond.j])):
            if not whole and not stub:
                continue
            for start in group:
                s = shift_of[start]
                far_shift = (s[0] + du, s[1] + dv, s[2] + dw)
                end = index_of.get((far_atom, far_shift))
                if end is None:
                    if stub:
                        segments.add_stub(
                            start,
                            cell.frac[far_atom] + np.asarray(far_shift,
                                                             float),
                            key, selected)
                elif whole:
                    segments.add(start, end, key, selected)
    return segments.arrays(drawn, lattice)


# ======================================================================
#  PLANES
# ======================================================================

def _no_planes():
    return (np.zeros((0, 3), np.float32),
            np.zeros((0, 3), int),
            np.zeros((0, 3), np.uint8),
            np.zeros((0, 3), np.float32),
            np.zeros((0, 3), np.float32),
            np.zeros((0, 3), np.uint8))


def _emit_planes(planes, cell, lattice, settings):
    """A translucent quad at each plane, with its normal on it.

    Two triangles and a line, which is why this borrows the polyhedron
    machinery rather than growing any of its own: the renderer already
    takes triangles with a colour per face and lines with a colour per
    segment, and a quad is two of the first.

    A plane whose atoms are no longer in the cell is skipped rather
    than drawn wrong.  The document prunes those, but it prunes them
    on a signal, and a picture built between the edit and the signal
    must not index off the end of the cell.

    **Each plane's own colour wins over the settings' default.**  The
    reason for drawing a quad at all is to see where two planes cross,
    and two quads in one colour is the picture that cannot be read --
    so the colour belongs to the plane, and the setting is what a
    plane nobody has coloured falls back to.
    """
    default = tuple(settings.plane_color)
    points, faces, colors = [], [], []
    starts, ends, normal_colors = [], [], []
    for plane in planes:
        if not plane.atoms or max(plane.atoms) >= cell.n_atoms:
            continue
        color = default if plane.color is None else tuple(plane.color)
        corners, tip = measure.plane_quad(plane, cell, lattice)
        base = len(points)
        points.extend(corners)
        faces.extend([[base, base + 1, base + 2],
                      [base, base + 2, base + 3]])
        colors.extend([color, color])
        starts.append(plane.centroid)
        ends.append(tip)
        normal_colors.append(view_settings.normal_of(color))
    if not faces:
        return _no_planes()
    return (np.array(points, np.float32).reshape(-1, 3),
            np.array(faces, int).reshape(-1, 3),
            np.array(colors, np.uint8).reshape(-1, 3),
            np.array(starts, np.float32).reshape(-1, 3),
            np.array(ends, np.float32).reshape(-1, 3),
            np.array(normal_colors, np.uint8).reshape(-1, 3))
