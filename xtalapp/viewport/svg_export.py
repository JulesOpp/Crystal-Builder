"""
xtalapp.viewport.svg_export
===========================
The scene as vector artwork: one SVG element per drawn thing.

The point of exporting SVG is that the picture can be taken apart in
Illustrator -- recolour one atom, thicken the cell edges, delete the
disorder.  A screen grab wrapped in ``<svg>`` cannot do any of that,
which is what GL2PS produces here: VTK's OpenGL2 backend cannot fill
the feedback buffer GL2PS reads, so it embeds a PNG and emits only the
axis labels as text.  So the geometry is projected and written out
directly instead, and the exporter never touches the GPU.

**It works from the :class:`~xtalapp.viewport.scene.SceneModel`**, the
same flat arrays the renderer draws, plus a :class:`Projection` -- so
this module imports neither VTK nor Qt and a test can assert on the
markup with no window.  Everything the viewport shows is here except
the chrome that is not part of the crystal: the orientation axes, the
element legend and the scale bar are drawn in window coordinates by
VTK and stay behind.

**Depth is a painter's algorithm.**  Every shape is sorted back to
front by the depth of its centre and written in that order.  That is
exact for spheres and flat faces and approximate exactly where a
z-buffer differs from it -- a bond that passes through an atom is
drawn whole or not at all, never half-swallowed.  For ball-and-stick
and polyhedra, which is what anybody exports, it is the same picture.

**Every element carries an id and a class**, because that is what
makes the file editable: Illustrator shows an ``id`` as the object's
name in the Layers panel, and ``class`` is what "select all the bonds"
comes down to.  Atoms are named by their crystallographic label when
the caller passes one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from xtalapp.viewport.scene import (
    DASH_RADIUS,
    HIGHLIGHT_BOND_GROWTH,
    HIGHLIGHT_COLOR,
    HIGHLIGHT_GROWTH,
    HIGHLIGHT_OPACITY,
    split_by_order,
)

#: Below this many display pixels an atom is a dot and its gradient is
#: wasted markup.  Far cells in a large display range land here.
MIN_RADIUS = 0.35

#: The unit cell and the plane normals are drawn as thin lines by VTK,
#: which has no width in world units to project.  These are pixels.
CELL_WIDTH = 1.6
NORMAL_WIDTH = 2.0
WIREFRAME_WIDTH = 2.0

LABEL_FONT = 14

#: A lit sphere, faked: the fill is lightened towards white off-centre
#: and darkened at the rim.  One gradient per colour, shared by every
#: atom of that element, so a thousand-atom framework carries a
#: handful of them and recolouring an element is one edit.
GRADIENT_HIGHLIGHT = 0.55       # how far the lit side goes to white
GRADIENT_SHADOW = 0.55          # what fraction of the colour is left
GRADIENT_CENTRE = ("35%", "32%", "72%")     # cx, cy, r


@dataclass(frozen=True)
class Projection:
    """World coordinates to the picture, as plain arrays.

    ``matrix`` is the camera's composite world-to-clip transform, the
    4x4 VTK renders through, so a projection built from the live
    camera puts every atom exactly where the viewport has it --
    perspective, parallel scale and clipping range included.

    ``right`` is the camera's horizontal axis in world space, and is
    what turns a radius in Angstrom into a radius in pixels: an atom
    is measured by projecting a point one radius to the side of it,
    which foreshortens correctly under perspective and needs no
    assumption about the projection being parallel.

    ``direction`` is where the camera looks, and is used only to
    shade the flat faces -- a polyhedron whose faces are all one
    colour reads as a blob rather than as a solid.
    """

    matrix: np.ndarray
    right: np.ndarray
    size: tuple[int, int]
    direction: np.ndarray | None = None

    def to_display(self, points) -> tuple[np.ndarray, np.ndarray]:
        """``(xy, depth)`` for world points, in SVG pixels.

        Depth is normalised device z -- -1 at the near plane, +1 at the
        far one -- which is the order to paint in, largest first.
        """
        pts = np.asarray(points, dtype=float).reshape(-1, 3)
        if not len(pts):
            return np.zeros((0, 2)), np.zeros(0)
        homogeneous = np.column_stack([pts, np.ones(len(pts))])
        clip = homogeneous @ np.asarray(self.matrix, float).T
        w = clip[:, 3:4]
        # A point on the camera plane divides by zero; it is off the
        # picture either way, so it is nudged rather than dropped and
        # the arrays stay the same length as the model's.
        w = np.where(np.abs(w) < 1e-12, 1e-12, w)
        ndc = clip[:, :3] / w
        width, height = self.size
        # SVG's y runs down the page and clip space's runs up it.
        return (np.column_stack([(ndc[:, 0] + 1.0) * 0.5 * width,
                                 (1.0 - ndc[:, 1]) * 0.5 * height]),
                ndc[:, 2])

    def radii_at(self, centres, radii) -> np.ndarray:
        """World radii as display radii, at each centre's own depth."""
        centres = np.asarray(centres, dtype=float).reshape(-1, 3)
        radii = np.asarray(radii, dtype=float).reshape(-1)
        if not len(centres):
            return np.zeros(0)
        offset = centres + np.asarray(self.right, float) * radii[:, None]
        here, _ = self.to_display(centres)
        there, _ = self.to_display(offset)
        return np.linalg.norm(there - here, axis=1)

    def width_at(self, starts, ends, radius) -> np.ndarray:
        """A tube radius as a stroke width, one per segment.

        Measured at each segment's midpoint, so a bond running away
        from the camera gets the width it has where it is drawn rather
        than the width it would have at the near end.
        """
        starts = np.asarray(starts, dtype=float).reshape(-1, 3)
        ends = np.asarray(ends, dtype=float).reshape(-1, 3)
        if not len(starts):
            return np.zeros(0)
        middles = 0.5 * (starts + ends)
        return 2.0 * self.radii_at(
            middles, np.full(len(middles), float(radius)))


# -- markup ------------------------------------------------------------


def _hex(color) -> str:
    r, g, b = (int(round(float(c))) for c in color[:3])
    return f"#{max(0, min(255, r)):02x}" \
           f"{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _mix(color, other, amount: float):
    """``color`` moved ``amount`` of the way towards ``other``."""
    a = np.asarray(color, dtype=float)
    b = np.asarray(other, dtype=float)
    return a + (b - a) * float(amount)


def _n(value: float) -> str:
    """A number short enough to read in the file.

    Two decimals is a hundredth of a pixel, which is below anything
    that can be seen and keeps a large framework's file from being
    mostly trailing zeros.
    """
    return f"{float(value):.2f}".rstrip("0").rstrip(".") or "0"


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class _Gradients:
    """The sphere gradients used so far, one per colour."""

    def __init__(self):
        self._ids: dict[str, str] = {}

    def for_color(self, color) -> str:
        key = _hex(color)
        if key not in self._ids:
            self._ids[key] = f"sphere-{key[1:]}"
        return self._ids[key]

    def defs(self) -> list[str]:
        cx, cy, radius = GRADIENT_CENTRE
        out = []
        for key, name in self._ids.items():
            rgb = [int(key[i:i + 2], 16) for i in (1, 3, 5)]
            lit = _hex(_mix(rgb, (255, 255, 255), GRADIENT_HIGHLIGHT))
            dark = _hex(_mix(rgb, (0, 0, 0), 1.0 - GRADIENT_SHADOW))
            out.append(
                f'<radialGradient id="{name}" cx="{cx}" cy="{cy}" '
                f'r="{radius}">'
                f'<stop offset="0" stop-color="{lit}"/>'
                f'<stop offset="0.55" stop-color="{key}"/>'
                f'<stop offset="1" stop-color="{dark}"/>'
                f'</radialGradient>')
        return out


# -- the shapes --------------------------------------------------------


def _line(x1, y1, x2, y2, color, width, name, kind, opacity=1.0,
          cap="round") -> str:
    extra = "" if opacity >= 1.0 else \
        f' stroke-opacity="{_n(opacity)}"'
    return (f'<line id="{name}" class="{kind}" '
            f'x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
            f'stroke="{_hex(color)}" stroke-width="{_n(width)}" '
            f'stroke-linecap="{cap}"{extra}/>')


def _atom_shapes(model, projection, names, gradients, out) -> None:
    """A circle per atom, or an ellipse per displacement ellipsoid."""
    if not model.n_atoms:
        return
    centres, depth = projection.to_display(model.positions)
    radii = projection.radii_at(model.positions, model.radii)
    tensors = (np.asarray(model.atom_tensors, float)
               if len(model.atom_tensors) == model.n_atoms else None)
    selected = (np.asarray(model.selected, bool)
                if len(model.selected) == model.n_atoms
                else np.zeros(model.n_atoms, bool))
    for i in range(model.n_atoms):
        if radii[i] < MIN_RADIUS and tensors is None:
            continue
        name = _atom_name(i, model, names)
        fill = f'url(#{gradients.for_color(model.colors[i])})'
        common = (f'class="atom" fill="{fill}" '
                  f'stroke="{_hex(_mix(model.colors[i], (0, 0, 0), 0.45))}"'
                  f' stroke-width="{_n(max(radii[i] * 0.06, 0.3))}"')
        if tensors is not None:
            shape = _ellipse(centres[i], tensors[i], model.positions[i],
                             projection, name, common)
            if shape is None:
                continue
        else:
            shape = (f'<circle id="{name}" {common} '
                     f'cx="{_n(centres[i][0])}" cy="{_n(centres[i][1])}" '
                     f'r="{_n(radii[i])}"/>')
        if selected[i]:
            out.append((depth[i] + 1e-6, _halo(
                centres[i], radii[i] * HIGHLIGHT_GROWTH,
                f"halo-{name}")))
        out.append((depth[i], shape))


def _ellipse(centre, tensor, position, projection, name, common):
    """One displacement ellipsoid, as the ellipse it projects to.

    The tensor carries a unit sphere onto the ellipsoid, so the three
    columns projected into the picture are the 2x3 map whose image of
    the unit sphere is exactly the silhouette; its singular values are
    the semi-axes and its left singular vectors the tilt.
    """
    tips = np.asarray(position, float)[None, :] + np.asarray(tensor).T
    projected, _ = projection.to_display(tips)
    columns = (projected - np.asarray(centre)[None, :]).T   # (2, 3)
    if not np.all(np.isfinite(columns)):
        return None
    u, singular, _v = np.linalg.svd(columns)
    if singular[0] < MIN_RADIUS:
        return None
    angle = np.degrees(np.arctan2(u[1, 0], u[0, 0]))
    return (f'<ellipse id="{name}" {common} cx="0" cy="0" '
            f'rx="{_n(singular[0])}" ry="{_n(max(singular[1], 0.2))}" '
            f'transform="translate({_n(centre[0])},{_n(centre[1])}) '
            f'rotate({_n(angle)})"/>')


def _halo(centre, radius, name) -> str:
    return (f'<circle id="{name}" class="selection" '
            f'cx="{_n(centre[0])}" cy="{_n(centre[1])}" '
            f'r="{_n(radius)}" fill="{_hex(HIGHLIGHT_COLOR)}" '
            f'fill-opacity="{_n(HIGHLIGHT_OPACITY)}"/>')


def _atom_name(i: int, model, names) -> str:
    """``atom-Zn1`` where the caller knows the label, ``atom-7`` else.

    The index is the drawn atom's, not the site's: a display range
    puts the same site on screen many times and two objects sharing an
    id is a broken SVG.
    """
    if names is not None and len(model.atom_index):
        site = int(model.atom_index[i])
        if 0 <= site < len(names):
            return f"atom-{i}-{_escape(names[site])}"
    return f"atom-{i}"


def _bond_shapes(model, projection, out) -> None:
    """Every bond half, doubles and triples already split into lanes."""
    solid, dashed = split_by_order(model)
    wire = model.bond_render == "line"
    for kind, (starts, ends, colors), scale in (
            ("bond", solid, 1.0),
            ("bond-aromatic", dashed, DASH_RADIUS)):
        if not len(starts):
            continue
        a, depth_a = projection.to_display(starts)
        b, depth_b = projection.to_display(ends)
        widths = (np.full(len(starts), WIREFRAME_WIDTH) if wire else
                  projection.width_at(starts, ends,
                                      model.bond_radius * scale))
        for i in range(len(starts)):
            out.append((
                0.5 * (depth_a[i] + depth_b[i]),
                _line(a[i][0], a[i][1], b[i][0], b[i][1], colors[i],
                      max(widths[i], 0.4), f"{kind}-{i}", kind,
                      cap="butt" if not wire else "round")))
    _bond_halos(model, projection, out)


def _bond_halos(model, projection, out) -> None:
    chosen = (np.flatnonzero(np.asarray(model.selected_bonds, bool))
              if len(model.selected_bonds) == model.n_bond_halves
              else np.zeros(0, int))
    if not len(chosen):
        return
    starts = np.asarray(model.bond_starts, float)[chosen]
    ends = np.asarray(model.bond_ends, float)[chosen]
    a, depth_a = projection.to_display(starts)
    b, depth_b = projection.to_display(ends)
    widths = projection.width_at(
        starts, ends,
        model.bond_radius * HIGHLIGHT_GROWTH * HIGHLIGHT_BOND_GROWTH)
    for i in range(len(chosen)):
        out.append((0.5 * (depth_a[i] + depth_b[i]) + 1e-6,
                    _line(a[i][0], a[i][1], b[i][0], b[i][1],
                          HIGHLIGHT_COLOR, widths[i],
                          f"halo-bond-{int(chosen[i])}", "selection",
                          opacity=HIGHLIGHT_OPACITY)))


def _topology_shapes(model, projection, out) -> None:
    if not model.n_topology_edges:
        return
    starts = np.asarray(model.topology_starts, float)
    ends = np.asarray(model.topology_ends, float)
    a, depth_a = projection.to_display(starts)
    b, depth_b = projection.to_display(ends)
    widths = projection.width_at(starts, ends, model.topology_radius)
    selected = (np.asarray(model.topology_selected, bool)
                if len(model.topology_selected) == len(starts)
                else np.zeros(len(starts), bool))
    for i in range(len(starts)):
        color = (HIGHLIGHT_COLOR if selected[i]
                 else model.topology_color)
        out.append((0.5 * (depth_a[i] + depth_b[i]),
                    _line(a[i][0], a[i][1], b[i][0], b[i][1], color,
                          max(widths[i], 0.4), f"net-edge-{i}", "net",
                          opacity=model.topology_opacity)))


#: How dark a face turned edge-on to the camera goes.  The renderer
#: lights the hulls, and a set of faces all at one colour reads as a
#: flat blob rather than as a solid -- so each face is shaded by how
#: square it is to the view, which is the one term of a Lambert model
#: that a head-on light contributes.
FACE_SHADE = 0.45


def _shade(colors, points, faces, direction):
    """Each face's colour, darkened by how far it turns from the eye."""
    colors = np.asarray(colors, float)
    if direction is None or not len(faces):
        return colors
    points = np.asarray(points, float)
    corners = points[np.asarray(faces, int)]
    normals = np.cross(corners[:, 1] - corners[:, 0],
                       corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.where(lengths < 1e-12, 1.0, lengths)
    view = np.asarray(direction, float)
    view = view / max(np.linalg.norm(view), 1e-12)
    # A face is lit by how square it is to the camera, either way
    # round: which side of a hull's triangle faces out is the
    # builder's winding and not something to shade by.
    facing = np.abs(normals @ view)[:, None]
    return colors * (1.0 - FACE_SHADE + FACE_SHADE * facing)


def _face_shapes(points, faces, colors, opacity, projection, kind,
                 out) -> None:
    """Polyhedron or plane triangles, one flat-filled polygon each.

    A hairline stroke in the fill colour closes the seams between
    adjacent triangles of one hull, which otherwise show as pale
    cracks wherever the renderer's antialiasing used to hide them.
    """
    if not len(faces):
        return
    xy, depth = projection.to_display(points)
    faces = np.asarray(faces, int)
    shaded = _shade(colors, points, faces, projection.direction)
    for i, face in enumerate(faces):
        corners = " ".join(f"{_n(xy[v][0])},{_n(xy[v][1])}"
                           for v in face)
        color = _hex(shaded[i]) if len(shaded) > i else "#888888"
        out.append((float(depth[face].mean()),
                    f'<polygon id="{kind}-{i}" class="{kind}" '
                    f'points="{corners}" fill="{color}" '
                    f'fill-opacity="{_n(opacity)}" stroke="{color}" '
                    f'stroke-width="0.5" '
                    f'stroke-opacity="{_n(opacity)}"/>'))


def _cell_shapes(model, projection, out) -> None:
    if not model.n_cell_lines:
        return
    a, depth_a = projection.to_display(model.cell_starts)
    b, depth_b = projection.to_display(model.cell_ends)
    for i in range(model.n_cell_lines):
        out.append((0.5 * (depth_a[i] + depth_b[i]),
                    _line(a[i][0], a[i][1], b[i][0], b[i][1],
                          model.cell_colors[i], CELL_WIDTH,
                          f"cell-edge-{i}", "cell")))


def _normal_shapes(model, projection, out) -> None:
    if not model.n_planes:
        return
    a, depth_a = projection.to_display(model.normal_starts)
    b, depth_b = projection.to_display(model.normal_ends)
    for i in range(model.n_planes):
        out.append((0.5 * (depth_a[i] + depth_b[i]),
                    _line(a[i][0], a[i][1], b[i][0], b[i][1],
                          model.normal_colors[i], NORMAL_WIDTH,
                          f"plane-normal-{i}", "plane-normal")))


def _label_shapes(model, projection, out) -> None:
    if not model.labels:
        return
    positions = np.array([p for p, _text in model.labels], float)
    xy, depth = projection.to_display(positions)
    # The same rule the renderer uses: readable against the ground it
    # is drawn on, whichever that is.
    dark = sum(model.background) / 3 > 128
    color = "#000000" if dark else "#ffffff"
    for i, (_position, text) in enumerate(model.labels):
        out.append((
            depth[i] - 1e-3,            # labels sit in front of atoms
            f'<text id="label-{i}" class="label" '
            f'x="{_n(xy[i][0])}" y="{_n(xy[i][1])}" fill="{color}" '
            f'font-family="Helvetica, Arial, sans-serif" '
            f'font-size="{LABEL_FONT}" text-anchor="middle" '
            f'dominant-baseline="central">{_escape(text)}</text>'))


# -- the document ------------------------------------------------------


def render_svg(model, projection, names=None,
               transparent: bool = False) -> str:
    """The scene as an SVG document.

    ``names`` is the P1 cell's labels, used to name the atoms; the
    caller has them and this module has no business reading a
    structure.  Everything else comes off the model.
    """
    gradients = _Gradients()
    shapes: list[tuple[float, str]] = []
    _face_shapes(model.polyhedron_points, model.polyhedron_faces,
                 model.polyhedron_colors, model.polyhedron_opacity,
                 projection, "polyhedron", shapes)
    _face_shapes(model.plane_points, model.plane_faces,
                 model.plane_colors, model.plane_opacity, projection,
                 "plane", shapes)
    _normal_shapes(model, projection, shapes)
    _cell_shapes(model, projection, shapes)
    _topology_shapes(model, projection, shapes)
    _bond_shapes(model, projection, shapes)
    _atom_shapes(model, projection, names, gradients, shapes)
    _label_shapes(model, projection, shapes)

    # Farthest first.  Python's sort is stable, so shapes at equal
    # depth keep the order they were emitted in above -- which is what
    # puts a halo behind its atom and a label in front of everything.
    shapes.sort(key=lambda item: -item[0])

    width, height = projection.size
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<title>Crystal Builder</title>',
    ]
    defs = gradients.defs()
    if defs:
        lines.append("<defs>")
        lines.extend(defs)
        lines.append("</defs>")
    if not transparent:
        lines.append(f'<rect id="background" width="{width}" '
                     f'height="{height}" '
                     f'fill="{_hex(model.background)}"/>')
    lines.extend(markup for _depth, markup in shapes)
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_svg(model, projection, path, names=None,
              transparent: bool = False) -> Path:
    path = Path(path)
    path.write_text(render_svg(model, projection, names=names,
                               transparent=transparent),
                    encoding="utf-8")
    return path
