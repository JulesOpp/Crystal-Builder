"""
xtalapp.viewport.sketch
=======================
The Skeletal style's drawing, as arrays: what a chemist would write
at each atom, and where the ink goes between them.

Two halves, and the split is the camera.  **What an atom is called**
-- ``NH2``, an implicit carbon, which end of a bond a wedge grows from
-- is a question about the bond graph and is answered once per
structure (:func:`fold`, :func:`centres`).  **Where a line stops and
whether it is a wedge** is a question about the camera: a label is
cut out of the lines *on screen*, so the length taken off a bond in
the world depends on how foreshortened it is, and a bond seen tilted
towards the viewer is a wedge only from where the viewer stands.  That
half (:func:`sketch_bonds`) is one numpy pass over the half-bonds the
scene model already carries, run again whenever the camera turns.

Folding hides a hydrogen from the picture, never from the structure:
nothing here changes a site or a bond.  The graph it reads is the
stored one -- no bond is perceived to decide what an atom is called.

No Qt, no VTK: the SVG export draws from exactly these arrays, and
the tests hold them without a render window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from xtal.core import elements as el
from xtalapp.viewport import scene as scene_model
from xtalapp.viewport.scene import (
    AROMATIC_MAX,
    DASH_DUTY,
    DASHES_PER_HALF,
    DOUBLE_MAX,
    SINGLE_MAX,
)

# Every length below is a fraction of the structure's median bond,
# which is ChemDraw's unit too: its labels, wedges and hashes are in
# proportion to the bond, so a sketch of a framework and one of a
# molecule read the same at the size each is drawn at.

#: A label's cap height.
LABEL_HEIGHT = 0.35
#: The clear space round a label, beyond its letters.  ChemDraw's
#: "margin width"; without it a line runs into the ink of the letter.
LABEL_PAD = 0.08
#: The wide end of a wedge.
WEDGE_WIDTH = 0.18
#: The narrowest hash, so the one beside the centre is still a mark.
HASH_MIN = 0.03
#: Screen distance between the lines of a hashed wedge.
HASH_SPACING = 0.12
#: Distance between the lines of a double bond.
LINE_SEPARATION = 0.16
#: How far towards the background the back of a skeletal drawing
#: goes when the depth cue is off -- the grey the style is drawn with.
#: The depth cue's own settings take over when it is on.
BACK_GREY = 0.6
#: Line weight on screen, in pixels.
LINE_WIDTH = 1.6
#: How far from a carbon left implicit a click still takes it.
VERTEX_PICK = 0.12
#: A bond tilted less than this out of the screen is a plain line.
#: Every bond in a crystal tilts somewhat, and one wedged at 5 degrees
#: claims a depth the reader cannot see.
WEDGE_TILT = math.radians(30.0)

#: Where a free molecule writes its hydrogens first: H2O and HCl, but
#: NH3 and CH4 -- the order chemists write them in.
_HYDROGEN_FIRST = frozenset({"O", "S", "Se", "Te", "F", "Cl", "Br", "I"})

# Arial's advance widths in em -- Helvetica's, to the thousandth --
# so the box a line stops short of is the box the letters are set in
# (``label_atlas`` renders Arial into exactly this box).
CAP_HEIGHT = 0.716             # of the em
_ADVANCE = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    (0.667, 0.667, 0.722, 0.722, 0.667, 0.611, 0.778, 0.722, 0.278,
     0.500, 0.667, 0.556, 0.833, 0.722, 0.778, 0.667, 0.778, 0.722,
     0.667, 0.611, 0.722, 0.667, 0.944, 0.667, 0.667, 0.611),
    strict=True))
_ADVANCE.update(zip(
    "abcdefghijklmnopqrstuvwxyz",
    (0.556, 0.556, 0.500, 0.556, 0.556, 0.278, 0.556, 0.556, 0.222,
     0.222, 0.500, 0.222, 0.833, 0.556, 0.556, 0.556, 0.556, 0.333,
     0.500, 0.278, 0.556, 0.500, 0.722, 0.500, 0.500, 0.500),
    strict=True))
_DESCENDERS = frozenset("gjpqy")
#: A subscript's size, relative to the letters it follows.
SUBSCRIPT = 0.7


@dataclass(frozen=True)
class Folding:
    """What each atom of the P1 cell is drawn as."""

    #: (N,) atoms not drawn at all: hydrogens written into a label.
    hidden: np.ndarray
    #: (N,) hydrogens written into each atom's label.
    hydrogens: np.ndarray
    #: (N,) bonds to atoms that are drawn.
    degree: np.ndarray
    #: The label, ``""`` for a carbon left implicit.  Digits are
    #: subscripts; the text carries them as plain characters and the
    #: renderer sets them.
    text: tuple


def fold(elements, ends, explicit_carbon: bool = False) -> Folding:
    """Fold hydrogens into labels and decide every atom's text.

    ``elements`` is one symbol per P1 atom and ``ends`` the graph's
    bonds as ``(i, j)`` rows -- images do not matter to a count.  A
    hydrogen is folded when it has exactly one bond and that bond is
    to a non-metal that is neither a hydrogen nor a marker: a hydride
    on a metal or a bridging hydrogen is chemistry a label cannot
    say, and a marker is not an atom that can carry one.
    """
    elements = [str(s) for s in elements]
    n = len(elements)
    ends = np.asarray(ends, dtype=int).reshape(-1, 2)
    full = np.bincount(ends.ravel(), minlength=n)

    hydrogen = np.array([s == "H" for s in elements], bool)
    carrier = np.array([not (s == "H" or el.is_dummy(s)
                             or el.element(s).is_metal)
                        for s in elements], bool)
    hidden = np.zeros(n, bool)
    hydrogens = np.zeros(n, int)
    for i, j in ends:
        for h, heavy in ((i, j), (j, i)):
            if (h != heavy and hydrogen[h] and full[h] == 1
                    and carrier[heavy]):
                hidden[h] = True
                hydrogens[heavy] += 1

    kept = ~(hidden[ends[:, 0]] | hidden[ends[:, 1]])
    degree = np.bincount(ends[kept].ravel(), minlength=n)
    text = tuple(
        "" if hidden[k] else _text(elements[k], int(hydrogens[k]),
                                   int(degree[k]), explicit_carbon)
        for k in range(n))
    return Folding(hidden, hydrogens, degree, text)


def _text(symbol: str, n_h: int, degree: int,
          explicit_carbon: bool) -> str:
    # A carbon with nothing drawn to it keeps its label either way:
    # an implicit vertex is where lines meet, and with no lines it is
    # not in the picture at all.
    if symbol == "C" and not explicit_carbon and degree:
        return ""
    if not n_h:
        return symbol
    h = "H" if n_h == 1 else f"H{n_h}"
    if not degree and symbol in _HYDROGEN_FIRST:
        return h + symbol
    return symbol + h


def centres(elements, degree, ends) -> np.ndarray:
    """(B,) true where a bond's first atom is the end its wedge grows
    from.

    ChemDraw's narrow end is the stereocentre, and a crystal has none,
    so the centre is the busier atom: more drawn bonds, then a metal,
    then the heavier, then the lower index.  So a metal's ligands
    wedge out from the metal, and a ring's substituents from the ring.
    """
    ends = np.asarray(ends, dtype=int).reshape(-1, 2)
    degree = np.asarray(degree, dtype=int)
    metal = np.array([el.element(s).is_metal and not el.is_dummy(s)
                      for s in elements], int)
    z = np.array([0 if el.is_dummy(s) else el.atomic_number(s)
                  for s in elements], int)
    i, j = ends[:, 0], ends[:, 1]
    first = np.stack([degree[i], metal[i], z[i], -i], axis=1)
    second = np.stack([degree[j], metal[j], z[j], -j], axis=1)
    out = np.ones(len(ends), bool)
    undecided = np.ones(len(ends), bool)
    for column in range(first.shape[1]):
        a, b = first[:, column], second[:, column]
        out[undecided & (a < b)] = False
        undecided &= a == b
    return out


def _advance(char: str) -> float:
    if char.isdigit():
        return 0.556 * SUBSCRIPT
    return _ADVANCE.get(char, 0.667)


def text_width(text: str, height: float) -> float:
    """How wide ``text`` is, set at cap height ``height``."""
    em = height / CAP_HEIGHT
    return em * sum(_advance(c) for c in text)


def label_extents(text: str, symbol: str, height: float,
                  pad: float = 0.0) -> tuple[float, float, float, float]:
    """``(left, right, down, up)`` of a label about its atom's centre.

    The atom's own letters sit on the vertex and the hydrogens trail
    off to one side, as ChemDraw sets ``NH2`` -- so the extents are not
    symmetric, and a bond leaving to the right of an ``NH2`` stops
    further out than one leaving to the left.  ``""`` is an implicit
    vertex and has no extent: lines meet at it.
    """
    if not text:
        return (0.0, 0.0, 0.0, 0.0)
    total = text_width(text, height)
    own = text_width(symbol, height)
    if text.startswith(symbol):
        left, right = own / 2, total - own / 2
    elif text.endswith(symbol):
        left, right = total - own / 2, own / 2
    else:
        left = right = total / 2
    # Below the letters: a subscript's drop, or the tail of a g or a
    # y (Mg, Hg, Dy), whichever reaches further.
    down = height / 2 + max(
        0.25 * height if any(c.isdigit() for c in text) else 0.0,
        0.30 * height if any(c in _DESCENDERS for c in text) else 0.0)
    return (left + pad, right + pad, down + pad, height / 2 + pad)


def symbol_of(text: str) -> str:
    """The element a label is written for: the first symbol in it
    that is not a folded hydrogen -- ``N`` of ``NH2``, ``O`` of
    ``H2O`` -- or ``H`` for a hydrogen drawn as itself."""
    symbols, k = [], 0
    while k < len(text):
        if text[k].isupper():
            end = k + 1
            while end < len(text) and text[end].islower():
                end += 1
            symbols.append(text[k:end])
            k = end
        else:
            k += 1
    heavy = [s for s in symbols if s != "H"]
    return heavy[0] if heavy else (symbols[0] if symbols else "")


def bond_scale(starts, ends) -> float:
    """The median bond length of a set of half-bonds, which is the
    unit every length of the sketch is a fraction of."""
    starts = np.asarray(starts, float).reshape(-1, 3)
    ends = np.asarray(ends, float).reshape(-1, 3)
    if not len(starts):
        return 1.5
    lengths = 2.0 * np.linalg.norm(ends - starts, axis=1)
    lengths = lengths[lengths > 1e-6]
    return float(np.median(lengths)) if len(lengths) else 1.5


@dataclass(frozen=True)
class SketchBonds:
    """The ink for one camera.  Each row names the half-bond it came
    from, so the renderer can fade it by depth and highlight it with
    its selection."""

    line_starts: np.ndarray             # (L,3)
    line_ends: np.ndarray               # (L,3)
    line_half: np.ndarray               # (L,)
    wedge_quads: np.ndarray             # (W,4,3) solid wedges, per half
    wedge_half: np.ndarray              # (W,)
    hash_starts: np.ndarray             # (H,3) the rungs of hashed ones
    hash_ends: np.ndarray               # (H,3)
    hash_half: np.ndarray               # (H,)


def camera_axes(direction, view_up) -> tuple[np.ndarray, np.ndarray,
                                             np.ndarray]:
    """``(direction, right, up)``, orthonormal, from a camera."""
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    up = np.asarray(view_up, float)
    up = up - (up @ d) * d
    up = up / np.linalg.norm(up)
    right = np.cross(d, up)
    return d, right, up


def sketch_bonds(starts, ends, extents, from_centre, orders, offsets,
                 *, direction, view_up, eye=None,
                 scale: float = 1.5) -> SketchBonds:
    """Cut, wedge and hash every half-bond for one camera.

    ``starts``/``ends`` are the scene model's halves: a half runs from
    its own atom to the bond's midpoint (or where it would be, for a
    stub).  ``extents`` is ``(left, right, down, up)`` of the label at
    each half's own atom, in the world, pad included -- zeros for an
    implicit vertex.  ``from_centre`` says whether that atom is the
    bond's centre (:func:`centres`).  ``orders`` and ``offsets`` are
    the model's, and may be empty.  ``scale`` is :func:`bond_scale`.

    ``eye`` makes a perspective camera: each half's tilt is then read
    along its own line of sight.  The gap is measured in the screen's
    own axes either way, because the label is drawn facing the screen.
    """
    starts = np.asarray(starts, float).reshape(-1, 3)
    ends = np.asarray(ends, float).reshape(-1, 3)
    n = len(starts)
    extents = np.asarray(extents, float).reshape(-1, 4)
    from_centre = np.asarray(from_centre, bool).reshape(-1)
    d, right, up = camera_axes(direction, view_up)

    v = ends - starts
    vx, vy = v @ right, v @ up
    projected = np.hypot(vx, vy)
    safe = np.where(projected > 1e-9, projected, 1.0)
    dx, dy = vx / safe, vy / safe
    with np.errstate(divide="ignore", invalid="ignore"):
        tx = np.where(dx > 1e-9, extents[:, 1] / dx,
                      np.where(dx < -1e-9, extents[:, 0] / -dx, np.inf))
        ty = np.where(dy > 1e-9, extents[:, 3] / dy,
                      np.where(dy < -1e-9, extents[:, 2] / -dy, np.inf))
    gap = np.minimum(tx, ty)
    gap[~np.any(extents > 0, axis=1)] = 0.0
    # The fraction of the half the label takes.  A half seen end on,
    # or shorter than its own label, is inside the label: not drawn,
    # rather than drawn from the far side of its atom.
    cut = np.where(projected > 1e-9, gap / safe, np.inf)
    cut[gap == 0.0] = 0.0
    visible = cut < 1.0
    cut = np.minimum(cut, 1.0)

    if eye is None:
        sight = np.tile(d, (n, 1))
    else:
        sight = starts - np.asarray(eye, float)
        sight /= np.maximum(np.linalg.norm(sight, axis=1), 1e-12)[:, None]

    orders = np.asarray(orders, float).reshape(-1)
    if len(orders) != n:
        orders = np.ones(n)
    offsets = np.asarray(offsets, float).reshape(-1, 3)
    if len(offsets) != n:
        offsets = np.zeros((n, 3))

    # From the centre outwards, whichever end this half starts at.
    outward = np.where(from_centre[:, None], v, -v)
    length = np.maximum(np.linalg.norm(v, axis=1), 1e-12)
    along = np.einsum("ij,ij->i", outward, sight) / length
    tilted = np.abs(along) >= math.sin(WEDGE_TILT)
    single = orders <= SINGLE_MAX
    wedged = visible & single & tilted
    solid = wedged & (along < 0)            # towards the eye
    hashed = wedged & ~solid

    lines = _lines(starts, v, cut, visible & ~wedged, orders, offsets,
                   scale * LINE_SEPARATION)

    lateral = np.cross(v, sight)
    lateral /= np.maximum(np.linalg.norm(lateral, axis=1), 1e-12)[:, None]
    # Where along the whole bond, from its centre, each end of the
    # half is: 0 at the centre, 1 at the far atom, the midpoint at 1/2.
    u0 = np.where(from_centre, 0.0, 1.0)
    u1 = np.full(n, 0.5)
    u_cut = u0 + (u1 - u0) * cut
    width = scale * WEDGE_WIDTH

    rows = np.flatnonzero(solid)
    a = starts[rows] + v[rows] * cut[rows, None]
    b = ends[rows]
    wa = (width * u_cut[rows] / 2)[:, None] * lateral[rows]
    wb = (width * u1[rows] / 2)[:, None] * lateral[rows]
    quads = np.stack([a - wa, a + wa, b + wb, b - wb], axis=1)

    rungs = _rungs(starts, v, u0, u_cut, u1, projected, lateral,
                   np.flatnonzero(hashed), scale)
    return SketchBonds(
        lines[0], lines[1], lines[2],
        quads.reshape(-1, 4, 3), rows,
        rungs[0], rungs[1], rungs[2])


def _lines(starts, v, cut, mask, orders, offsets, separation):
    """The plain lines: one per lane, doubles straddling the axis,
    and an aromatic bond's inner line dashed."""
    rows = np.flatnonzero(mask)
    a = starts[rows] + v[rows] * cut[rows, None]
    b = starts[rows] + v[rows]
    order = orders[rows]
    shift = offsets[rows] * separation
    double = (order > AROMATIC_MAX) & (order <= DOUBLE_MAX)
    triple = order > DOUBLE_MAX
    aromatic = (order > SINGLE_MAX) & (order <= AROMATIC_MAX)
    lanes = [(~double, 0.0), (double, 0.5), (double, -0.5),
             (triple, 1.0), (triple, -1.0)]
    out_a, out_b, out_half = [], [], []
    for keep, k in lanes:
        out_a.append(a[keep] + k * shift[keep])
        out_b.append(b[keep] + k * shift[keep])
        out_half.append(rows[keep])
    if np.any(aromatic):
        lo, hi = a[aromatic] + shift[aromatic], b[aromatic] + shift[aromatic]
        slot = 1.0 / DASHES_PER_HALF
        for dash in range(DASHES_PER_HALF):
            f0, f1 = dash * slot, dash * slot + slot * DASH_DUTY
            out_a.append(lo + (hi - lo) * f0)
            out_b.append(lo + (hi - lo) * f1)
            out_half.append(rows[aromatic])
    return (np.vstack(out_a).reshape(-1, 3),
            np.vstack(out_b).reshape(-1, 3),
            np.concatenate(out_half).astype(int))


def _rungs(starts, v, u0, u_cut, u1, projected, lateral, rows, scale):
    """A hashed wedge's rungs, spaced along the whole bond so the two
    halves' rungs keep one rhythm across the midpoint."""
    out_a, out_b, out_half = [], [], []
    width = scale * WEDGE_WIDTH
    for r in rows:
        # The whole bond is twice the half, on screen as in the world.
        count = max(2, int(round(2 * projected[r]
                                 / (scale * HASH_SPACING))))
        u = np.arange(1, count + 1) / count
        lo, hi = sorted((u_cut[r], u1[r]))
        u = u[(u > lo + 1e-9) & (u <= hi + 1e-9)]
        if not len(u):
            continue
        # u is the whole bond's, from its centre; back to this half.
        t = (u - u0[r]) / (u1[r] - u0[r])
        centre = starts[r] + t[:, None] * v[r]
        half_width = np.maximum(width * u, scale * HASH_MIN) / 2
        out_a.append(centre - half_width[:, None] * lateral[r])
        out_b.append(centre + half_width[:, None] * lateral[r])
        out_half.append(np.full(len(u), r))
    if not out_a:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, int)
    return (np.vstack(out_a), np.vstack(out_b),
            np.concatenate(out_half).astype(int))


def fade(positions, radii, points, eye, direction,
         cue=None) -> np.ndarray:
    """How far towards the background each of ``points`` is drawn.

    ``cue`` is the depth cue's ``(start, end, strength)`` when it is
    on; ``None`` is the style's own grey, :data:`BACK_GREY` over the
    whole depth of the atoms.  The screen and the SVG both ask here,
    so an exported sketch is grey where the window was.
    """
    start, end, strength = cue if cue is not None else (
        0.0, 1.0, BACK_GREY)
    eye = np.asarray(eye, float)
    direction = np.asarray(direction, float)
    near, far = scene_model.cue_depth_range(
        positions, radii, eye, direction, start, end)
    return scene_model.cue_fraction(
        (np.asarray(points, float).reshape(-1, 3) - eye) @ direction,
        near, far, strength)


def model_cue(model):
    """The model's depth cue as :func:`fade` takes it."""
    if not model.depth_cue:
        return None
    start, end = scene_model.cue_ends(model.depth_cue_start,
                                      model.depth_cue_end)
    return start, end, float(model.depth_cue_strength)


def sketch_model(model, direction, view_up, eye=None) -> SketchBonds:
    """:func:`sketch_bonds` over a scene model's own half-bonds."""
    n = model.n_bond_halves
    gaps = (model.bond_gaps if len(model.bond_gaps) == n
            else np.zeros((n, 4)))
    from_centre = (model.bond_from_centre
                   if len(model.bond_from_centre) == n
                   else np.ones(n, bool))
    return sketch_bonds(
        model.bond_starts, model.bond_ends, gaps, from_centre,
        model.bond_orders, model.bond_offsets,
        direction=direction, view_up=view_up, eye=eye,
        scale=model.sketch_scale)
