"""
xtal.carbon.surface
===================
A smooth periodic sheet around a net: the shape a carbon framework is
laid on.

**A convolution surface, not a distance.**  The field is a sum of
Gaussians over beads every :data:`BEAD_SPACING` along the net's edges,
and the sheet is one of its level sets.  The distance to the nearest
edge would give tubes of exactly the right radius, but it has a crease
wherever two edges are equally near -- at every node -- and a crease in
the sheet is a row of carbons bent through a corner.  Summed Gaussians
are smooth everywhere and swell a little at a node, where four struts
add up, which is where a real framework is fuller too.

**The radius is the strut's**: the level is the field a distance ``R``
from an infinitely long straight edge (:func:`level_for`), so along an
edge the tube is ``R`` and at a node a little more.

**The surface is marched and then welded.**
:func:`xtal.analysis.isosurface.isosurface` shares no vertex between
two tetrahedra; every crossing lies on a grid edge, so two copies of
one are at the same place to rounding, and keyed by where they are
in the wrapped cell they become one vertex -- with the translation
each triangle uses it at.  A welded sheet round a net is closed, and
its Euler characteristic is twice the net's V - E per cell
(:func:`expected_euler`), which is the check that nothing was torn.

**The cell is solved, not chosen** (:func:`solve_scale`).  A sheet's
area grows as the square of the cell and the volume as the cube, so for
a given net, radius ratio and coverage there is one scale at which the
carbon it can hold, at graphene's 0.382 atoms per square Angstrom, is
the density asked for.  Distortions and layer spacings are in Angstrom
and do not scale, so it is a fixed point, and it settles in three or
four rounds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from xtal.analysis import isosurface, rcsr
from xtal.carbon.mesh import Mesh
from xtal.core.lattice import Lattice

#: Graphene's carbons per square Angstrom: two per hexagon of side
#: 1.42 A.  Also what an even triangulation at 2.46 A holds, one carbon
#: per triangle.
GRAPHENE_AREAL = 2.0 / (np.sqrt(3.0) / 2.0 * 2.46 ** 2)

#: Carbon atoms per cubic Angstrom in one g/cm3: 0.6022 / 12.011.
ATOMS_PER_GCC = 0.60221408 / 12.011

#: Along an edge, beads this far apart: well under the Gaussian's
#: width, so the tube is round rather than a string of pearls.
BEAD_SPACING = 0.3

#: The Gaussian's width as a fraction of the strut radius.  At a half,
#: four struts meeting swell the node to about 1.3 R: full enough to
#: join smoothly, not so full the node is a ball.
WIDTH_FRACTION = 0.5

#: Field points further than this many widths from a bead get nothing
#: from it: exp(-12.5) is 4e-6 of a bead's peak.
CUTOFF_WIDTHS = 5.0

#: The marching grid, as a fraction of the Gaussian's width, and never
#: finer than :data:`GRID_SPACING`.  The field has no detail finer than
#: the width, so this keeps the sheet's topology -- the welded chi is
#: the net's -- and the remesh makes the triangles what they should be,
#: so the grid does not need to.  Fixed in Angstrom, a cell solved to
#: 60 A marched 130 000 triangles a round.
GRID_WIDTHS = 0.6
GRID_SPACING = 1.0

#: Within this of a grid point, two crossings are one vertex: a
#: thousandth of the grid step, far below anything two distinct
#: crossings can be apart and far above rounding.
_WELD = 1000


class SurfaceError(ValueError):
    """A sheet that cannot be made, and why."""


@dataclass
class Skeleton:
    """The net, placed and distorted, in its cell: vertices in
    fractions, and every edge as a string of beads in Angstrom."""

    lattice: Lattice
    vertices: np.ndarray            # (V, 3) fractional
    edges: list                     # (i, j, image)
    beads: np.ndarray               # (B, 3) cartesian, in the cell
    edge_length: float              # mean, Angstrom

    @property
    def volume(self) -> float:
        return float(self.lattice.volume)


def net_of(name: str) -> tuple[Lattice, np.ndarray, list]:
    """An RCSR net's cell, vertices and edges, the cell scaled so the
    mean edge is one unit long."""
    try:
        entry = rcsr.nets()[name]
    except KeyError:
        raise SurfaceError(f"no net named {name!r} in the RCSR") from None
    if entry.dimension != 3 or not entry.cell:
        raise SurfaceError(
            f"{name} is not a 3-periodic net, and a carbon sheet "
            "around it would not percolate")
    net, frac = rcsr.placement(entry)
    lattice = Lattice.from_parameters(*entry.cell)
    edges = [(e.i, e.j, tuple(int(v) for v in e.image))
             for e in net.edges]
    lengths = [np.linalg.norm(lattice.to_cart(
        frac[j] + np.array(image) - frac[i])) for i, j, image in edges]
    scale = 1.0 / float(np.mean(lengths))
    return (Lattice(np.asarray(lattice.matrix) * scale),
            np.asarray(frac, float) % 1.0, edges)


def repeated(lattice: Lattice, vertices, edges, repeat):
    """The net over ``repeat`` cells: vertex ``v`` of cell ``t`` is
    ``v + V * index(t)``."""
    repeat = np.asarray(repeat, int)
    cells = np.array([(a, b, c) for a in range(repeat[0])
                      for b in range(repeat[1])
                      for c in range(repeat[2])], int)
    index = {tuple(t): k for k, t in enumerate(cells)}
    n = len(vertices)
    out_vertices = np.vstack([(vertices + t) / repeat for t in cells])
    out_edges = []
    for k, t in enumerate(cells):
        for i, j, image in edges:
            far = t + np.array(image)
            home = far % repeat
            out_edges.append((i + n * k, j + n * index[tuple(home)],
                              tuple(int(v) for v in
                                    (far - home) // repeat)))
    matrix = np.asarray(lattice.matrix) * repeat[:, None]
    return Lattice(matrix), out_vertices, out_edges


@dataclass
class Distortion:
    """Unit random draws for every vertex and edge, made once, so a
    scale can change without the net being redrawn."""

    vertex: np.ndarray              # (V, 3) standard normal
    edge: np.ndarray                # (E, 3) standard normal

    @classmethod
    def draw(cls, rng, n_vertices: int, n_edges: int) -> Distortion:
        return cls(rng.standard_normal((n_vertices, 3)),
                   rng.standard_normal((n_edges, 3)))


def skeleton(lattice: Lattice, vertices, edges, scale: float,
             distortion: Distortion | None = None,
             sigma_vertex: float = 0.0,
             sigma_edge: float = 0.0) -> Skeleton:
    """The net at ``scale`` (Angstrom per unit edge), each vertex moved
    by ``sigma_vertex`` and each edge bowed sideways at its middle by
    ``sigma_edge``, both in Angstrom.

    An edge is a quadratic curve through its two ends whose middle is
    off the straight line by the edge draw, taken perpendicular to the
    edge -- along it, the draw would only crowd the beads.
    """
    scaled = Lattice(np.asarray(lattice.matrix) * scale)
    frac = np.asarray(vertices, float).copy()
    if distortion is not None and sigma_vertex:
        frac = frac + scaled.to_frac(distortion.vertex * sigma_vertex)
    cart = scaled.to_cart(frac)
    matrix = np.asarray(scaled.matrix)
    beads, lengths = [], []
    for k, (i, j, image) in enumerate(edges):
        start = cart[i]
        end = cart[j] + np.asarray(image) @ matrix
        axis = end - start
        length = float(np.linalg.norm(axis))
        lengths.append(length)
        bow = np.zeros(3)
        if distortion is not None and sigma_edge and length > 0:
            draw = distortion.edge[k]
            unit = axis / length
            bow = (draw - (draw @ unit) * unit) * sigma_edge
        middle = (start + end) / 2.0 + 2.0 * bow
        n = max(2, int(np.ceil(length / BEAD_SPACING)) + 1)
        t = np.linspace(0.0, 1.0, n)[:-1, None]
        beads.append((1 - t) ** 2 * start + 2 * (1 - t) * t * middle
                     + t ** 2 * end)
    beads = np.vstack(beads) if beads else np.zeros((0, 3))
    beads = scaled.to_cart(scaled.to_frac(beads) % 1.0)
    return Skeleton(scaled, frac % 1.0, list(edges), beads,
                    float(np.mean(lengths)) if lengths else 0.0)


class Field:
    """The summed Gaussians of a skeleton's beads, and their gradient,
    anywhere in or around the cell."""

    def __init__(self, skeleton: Skeleton, width: float):
        self.lattice = skeleton.lattice
        self.width = float(width)
        shifts = np.array([(a, b, c) for a in (-1, 0, 1)
                           for b in (-1, 0, 1) for c in (-1, 0, 1)])
        matrix = np.asarray(self.lattice.matrix)
        images = (skeleton.beads[None, :, :]
                  + (shifts @ matrix)[:, None, :]).reshape(-1, 3)
        self.tree = cKDTree(images)
        self.points = images

    def __call__(self, cart) -> np.ndarray:
        return self.evaluate(cart)[0]

    def evaluate(self, cart, gradient: bool = False):
        """``(values, gradients)`` at ``cart`` (N, 3); points are
        wrapped into the cell first, so any image may be asked.

        A block of points at a time: every point and bead within the
        cutoff is a pair, about eighty a point, and a whole 2x2x2
        grid's pairs at once were gigabytes.
        """
        cart = np.atleast_2d(np.asarray(cart, float))
        frac = self.lattice.to_frac(cart)
        home = self.lattice.to_cart(frac - np.floor(frac))
        out = np.zeros(len(cart))
        grad = np.zeros((len(cart), 3)) if gradient else None
        for start in range(0, len(home), _POINT_BLOCK):
            block = home[start:start + _POINT_BLOCK]
            value, slope = self._block(block, gradient)
            out[start:start + len(block)] = value
            if gradient:
                grad[start:start + len(block)] = slope
        return out, grad

    def _block(self, home, gradient: bool):
        n = len(home)
        pairs = cKDTree(home).sparse_distance_matrix(
            self.tree, CUTOFF_WIDTHS * self.width,
            output_type="coo_matrix")
        rows, cols = pairs.row, pairs.col
        weight = np.exp(-pairs.data ** 2 / (2.0 * self.width ** 2))
        del pairs
        out = np.bincount(rows, weight, minlength=n)
        # A distance of exactly zero is not stored by the sparse
        # matrix, so a point sitting on a bead is added back.
        on_bead = self.tree.query(home, distance_upper_bound=1e-9)[0]
        out[np.isfinite(on_bead)] += 1.0
        if not gradient:
            return out, None
        scale = -weight / self.width ** 2
        grad = np.empty((n, 3))
        for axis in range(3):
            delta = home[rows, axis] - self.points[cols, axis]
            grad[:, axis] = np.bincount(rows, delta * scale,
                                        minlength=n)
        return out, grad


#: Field points per KD-tree query in :meth:`Field.evaluate`.
_POINT_BLOCK = 4096


def level_for(radius: float, width: float,
              spacing: float = BEAD_SPACING) -> float:
    """The field a distance ``radius`` from an endless straight row of
    beads ``spacing`` apart: the level whose sheet is a tube of that
    radius."""
    reach = int(np.ceil(CUTOFF_WIDTHS * width / spacing)) + 1
    along = np.arange(-reach, reach + 1) * spacing
    return float(np.exp(-(radius ** 2 + along ** 2)
                        / (2.0 * width ** 2)).sum())


def march(field: Field, level: float,
          spacing: float | None = None) -> Mesh:
    """The ``level`` sheet of ``field``, marched and welded."""
    if spacing is None:
        spacing = max(GRID_SPACING, GRID_WIDTHS * field.width)
    lattice = field.lattice
    lengths = np.linalg.norm(np.asarray(lattice.matrix), axis=1)
    shape = tuple(int(max(4, np.ceil(length / spacing)))
                  for length in lengths)
    axes = [np.arange(n) / n for n in shape]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"),
                    axis=-1).reshape(-1, 3)
    values = field(lattice.to_cart(grid)).reshape(shape)
    points, triangles = isosurface.isosurface(values, lattice, level)
    if not len(triangles):
        raise SurfaceError("the level is outside the field: no sheet")
    return weld(points, triangles, lattice, shape)


def weld(points, triangles, lattice, shape) -> Mesh:
    """One vertex per place on the wrapped cell, and the translation
    each triangle reaches it by.

    A triangle whose corners weld onto one vertex twice -- a crossing
    exactly at a grid point, which two of its sides then share -- has
    no area and is dropped.
    """
    scale = np.asarray(shape, np.int64) * _WELD
    q = np.round(np.asarray(points, float) * scale).astype(np.int64)
    wrapped = np.mod(q, scale)
    keys, index = np.unique(wrapped, axis=0, return_inverse=True)
    index = index.reshape(-1)
    shift = ((q - wrapped) // scale).astype(int)
    tri = index[triangles]
    corner_shift = shift[triangles]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    s = corner_shift
    same = (((a == b) & np.all(s[:, 0] == s[:, 1], axis=1))
            | ((b == c) & np.all(s[:, 1] == s[:, 2], axis=1))
            | ((a == c) & np.all(s[:, 0] == s[:, 2], axis=1)))
    mesh = Mesh(np.asarray(lattice.matrix, float), keys / scale,
                tri[~same], corner_shift[~same])
    return mesh.subset(np.ones(mesh.n_triangles, bool))


def expected_euler(n_vertices: int, n_edges: int) -> int:
    """The Euler characteristic of a closed sheet round a connected
    net with this many vertices and edges per cell: one handle per
    independent loop of the net, and a periodic net has E - V + 1 of
    them in the cell's quotient, so chi = 2 - 2(E - V + 1)."""
    return 2 * (n_vertices - n_edges)


def layer_offsets(layers: int, spacing: float) -> np.ndarray:
    """How far each layer is from the middle one, outwards positive:
    a bilayer is two sheets at plus and minus half a spacing."""
    return (np.arange(layers) - (layers - 1) / 2.0) * spacing


@dataclass
class Solved:
    """A net at the scale that holds the density asked for."""

    skeleton: Skeleton
    radius: float                   # the strut, Angstrom
    width: float                    # the Gaussian, Angstrom
    levels: np.ndarray              # one per layer
    meshes: list                    # one closed mesh per layer
    carbons: int                    # what the cell must hold

    @property
    def area(self) -> float:
        return float(sum(m.area() for m in self.meshes))


def solve_scale(lattice: Lattice, vertices, edges, *, density: float,
                radius_ratio: float, coverage: float, layers: int = 1,
                interlayer: float = 3.35,
                distortion: Distortion | None = None,
                sigma_vertex: float = 0.0, sigma_edge: float = 0.0,
                spacing: float | None = None, rounds: int = 6,
                scale: float = 10.0) -> Solved:
    """The scale at which ``coverage`` of the sheet, at graphene's
    density of carbon, is ``density`` g/cm3 of carbon in the cell.

    Each round marches the sheet at the current scale and corrects it
    by the ratio of carbon held to carbon wanted: for a pure change of
    scale that ratio goes as one over the scale, so the correction is
    exact but for what does not scale, and it is repeated until it
    stops mattering.  The innermost layer must keep room for a sheet
    of carbon (:data:`MIN_INNER_RADIUS`) or the build is refused.
    """
    if not 0.0 < coverage <= 1.0:
        raise SurfaceError("coverage is a fraction of the sheet, "
                           "above 0 and at most 1")
    if density <= 0.0:
        raise SurfaceError("the density must be above zero")
    offsets = layer_offsets(layers, interlayer)
    solved = None
    for _round in range(rounds):
        frame = skeleton(lattice, vertices, edges, scale, distortion,
                         sigma_vertex, sigma_edge)
        radius = radius_ratio * frame.edge_length
        width = WIDTH_FRACTION * radius
        field = Field(frame, width)
        levels = np.array([level_for(max(radius + o, 0.1 * radius),
                                     width) for o in offsets])
        try:
            meshes = [march(field, lv, spacing) for lv in levels]
        except SurfaceError:
            raise SurfaceError(
                "the outermost sheet merges with its neighbours into "
                "nothing: lower the radius ratio or use fewer layers"
                ) from None
        held = GRAPHENE_AREAL * coverage * sum(m.area() for m in meshes)
        wanted = density * ATOMS_PER_GCC * frame.volume
        solved = Solved(frame, radius, width, levels, meshes,
                        int(round(wanted)))
        ratio = held / wanted
        if abs(ratio - 1.0) < 5e-3:
            break
        scale *= ratio
    inner = solved.radius + offsets[0]
    if inner < MIN_INNER_RADIUS:
        # Judged at the scale the density settled on, not on the way
        # there: the first round's guess is anybody's.
        raise SurfaceError(
            f"the innermost sheet would be {inner:.2f} A from its "
            f"edge, under the {MIN_INNER_RADIUS} A a curved carbon "
            "sheet needs; raise the radius ratio or the coverage, "
            "lower the density, or use fewer layers")
    expected = expected_euler(len(vertices), len(edges))
    for k, mesh in enumerate(solved.meshes):
        if mesh.euler() != expected:
            # Fat enough struts merge across a pore and thin enough
            # ones pinch at a node; either is another sheet, and
            # Gauss-Bonnet would then count rings for a surface that
            # is not the net's.
            raise SurfaceError(
                f"layer {k + 1} is not a sheet round the net (its "
                f"Euler characteristic is {mesh.euler()}, the net's is "
                f"{expected}): its struts merge or pinch; change the "
                "radius ratio or the number of layers")
    return solved


#: The smallest radius a curved carbon sheet is given: a (5,5)
#: nanotube's is 3.4 A, and nothing in a templated carbon is tighter
#: than a buckybowl's few-Angstrom curvature.
MIN_INNER_RADIUS = 2.5
