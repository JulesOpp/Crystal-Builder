"""
xtalapp.viewport.label_atlas
============================
The Skeletal style's labels, as one texture.

Every label in a picture is one of a few strings -- ``Zn``, ``NH``,
``OH2`` -- so they are set once each, into one image, and every atom
that carries one is a quad pointing into it.  One actor for a
thousand labels: a :class:`vtkBillboardTextActor3D` each re-renders
2000 of them in 126 ms, which is a framework that stutters as it
turns.

**The box is the sketch's, and the letters are set into it.**  A
line stops short of a label at :func:`sketch.label_extents` plus the
pad, which is decided without a font; the cell drawn here is exactly
that box, filled with the background -- the knockout that interrupts
anything passing behind the label -- with the letters placed so the
atom's own sit on the vertex.  So the gap a line leaves and the
ground the label covers are one rectangle, and cannot disagree.

**The box is also transparent where there is no letter**: a fourth
channel carries the letters' coverage, so the window can draw the
letters alone and lay the box under them as a separate quad -- or
leave it out, and let a pore sphere behind a label show through.

The fade is baked, not shaded: each string is set at
:data:`LEVELS` steps from ink towards the background, and a label is
pointed at the step its depth asks for.  A textured quad's colour is
the texture's, so a shader would have had to take the colour apart
again; twelve steps of a grey no reader compares side by side cost
nothing to look at.

VTK's own FreeType renderer and not Qt's, because this module is
imported by ``vtk_scene``, whose render path runs without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache, lru_cache

import numpy as np
import vtkmodules.vtkRenderingFreeType  # noqa: F401
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkRenderingCore import vtkTextProperty, vtkTextRenderer

from xtalapp.viewport import sketch

#: The cap height the letters are set at, in texture pixels.  A label
#: is rarely more than 60 pixels tall on screen, and a texture set
#: larger than it is drawn stays sharp as it is minified.
CAP_PX = 48
#: How many steps of the fade each string is set at.
LEVELS = 12
#: How much lower a subscript's baseline is, in cap heights.
SUBSCRIPT_DROP = 0.25


@cache
def _renderer():
    return vtkTextRenderer()


def _property(size: int) -> vtkTextProperty:
    prop = vtkTextProperty()
    prop.SetFontFamilyToArial()
    prop.SetFontSize(int(size))
    prop.SetColor(1.0, 1.0, 1.0)
    prop.SetBackgroundOpacity(0.0)
    return prop


@lru_cache(maxsize=256)
def _run(text: str, size: int) -> np.ndarray:
    """Coverage of one run of ``text``, 0-1, row 0 at the top."""
    image = vtkImageData()
    dims = [0, 0]
    _renderer().RenderString(_property(size), text, image, dims, 72)
    width, height, _depth = image.GetDimensions()
    pixels = vtk_to_numpy(image.GetPointData().GetScalars())
    # VTK's rows run upwards and the image is padded to a power of
    # two above the text, so the text is the *last* rows once flipped.
    alpha = pixels.reshape(height, width, -1)[::-1, :, -1]
    return alpha[height - dims[1]:, :dims[0]].astype(np.float32) / 255.0


@lru_cache(maxsize=8)
def _metrics(size: int) -> tuple[int, int]:
    """``(baseline, cap)`` of a run set at ``size``: the row below
    the ink of a capital, counted from the image's foot, and the
    capital's height in pixels."""
    ink = np.flatnonzero(_run("H", size).max(axis=1) > 0.5)
    height = _run("H", size).shape[0]
    return height - 1 - int(ink.max()), int(ink.max() - ink.min() + 1)


@lru_cache(maxsize=4)
def _size_for_cap(cap: int) -> int:
    size = max(4, round(cap / 0.716))
    return max(4, round(size * cap / _metrics(size)[1]))


def _runs(text: str) -> list[tuple[str, bool]]:
    """``text`` as ``(run, subscript)`` pieces: digits are subscripts."""
    out: list[tuple[str, bool]] = []
    for char in text:
        sub = char.isdigit()
        if out and out[-1][1] == sub:
            out[-1] = (out[-1][0] + char, sub)
        else:
            out.append((char, sub))
    return out


@dataclass(frozen=True)
class Set:
    """One string's letters: coverage, and where its vertex is."""

    mask: np.ndarray        # (H, W) coverage, row 0 at the top
    anchor: tuple           # (x, y) of the atom's centre, in pixels
    cap: int                # a capital's height, in pixels


@lru_cache(maxsize=256)
def set_text(text: str, symbol: str, cap: int = CAP_PX) -> Set:
    """Set ``text`` with its digits subscripted, the atom's own
    letters centred on the vertex as :func:`sketch.label_extents`
    places them."""
    size = _size_for_cap(cap)
    small = max(4, round(size * sketch.SUBSCRIPT))
    drop = round(SUBSCRIPT_DROP * cap)
    pieces = [(_run(run, small if sub else size), sub)
              for run, sub in _runs(text)]
    base_big = _metrics(size)[0]
    base_small = _metrics(small)[0]
    # Every piece is placed by its baseline: a subscript's sits
    # ``drop`` below the letters'.
    above = max(p.shape[0] - (base_small if sub else base_big)
                + (-drop if sub else 0) for p, sub in pieces)
    below = max((base_small + drop) if sub else base_big
                for _p, sub in pieces)
    width = sum(p.shape[1] for p, _sub in pieces)
    mask = np.zeros((above + below, width), np.float32)
    x = 0
    for piece, sub in pieces:
        base = base_small if sub else base_big
        top = above - (piece.shape[0] - base) + (drop if sub else 0)
        region = mask[top:top + piece.shape[0], x:x + piece.shape[1]]
        np.maximum(region, piece, out=region)
        x += piece.shape[1]
    own = _run(symbol, size).shape[1] if symbol else 0
    if text.startswith(symbol):
        anchor_x = own / 2
    elif text.endswith(symbol):
        anchor_x = width - own / 2
    else:
        anchor_x = width / 2
    return Set(mask, (anchor_x, above - cap / 2), cap)


def cell(text: str, symbol: str, ink, background, height: float,
         pad: float, cap: int = CAP_PX) -> np.ndarray:
    """(H, W, 4) uint8: the label's box, ``pad`` included, in the
    background colour with the letters inked into it, and the letters'
    coverage as its alpha.  ``height`` and
    ``pad`` are the world sizes the box is drawn at; only their ratio
    matters here."""
    left, right, down, up = sketch.label_extents(text, symbol, height,
                                                 pad)
    scale = cap / height                        # pixels per Angstrom
    box_w = max(1, round((left + right) * scale))
    box_h = max(1, round((down + up) * scale))
    glyphs = set_text(text, symbol, cap)
    coverage = np.zeros((box_h, box_w), np.float32)
    # Where the glyphs' anchor lands in the box.
    ox = round(left * scale - glyphs.anchor[0])
    oy = round(up * scale - glyphs.anchor[1])
    h, w = glyphs.mask.shape
    y0, x0 = max(0, oy), max(0, ox)
    y1, x1 = min(box_h, oy + h), min(box_w, ox + w)
    if y1 > y0 and x1 > x0:
        coverage[y0:y1, x0:x1] = glyphs.mask[y0 - oy:y1 - oy,
                                             x0 - ox:x1 - ox]
    ink = np.asarray(ink, np.float32)
    ground = np.asarray(background, np.float32)
    rgb = ground + (ink - ground) * coverage[:, :, None]
    alpha = coverage[:, :, None] * 255.0
    return np.clip(np.round(np.concatenate([rgb, alpha], axis=2)),
                   0, 255).astype(np.uint8)


def level_colors(ink, background) -> np.ndarray:
    """(LEVELS, 3): ``ink`` at each step of the fade, the last all the
    way to the background."""
    ink = np.asarray(ink, float)
    ground = np.asarray(background, float)
    steps = np.linspace(0.0, 1.0, LEVELS)[:, None]
    return ink + (ground - ink) * steps


def level_of(fraction) -> np.ndarray:
    """The step nearest each fade fraction, 0 to 1."""
    f = np.clip(np.asarray(fraction, float), 0.0, 1.0)
    return np.rint(f * (LEVELS - 1)).astype(int)


@dataclass(frozen=True)
class Atlas:
    """Every label of a picture at every step of the fade, packed."""

    image: np.ndarray       # (H, W, 4) uint8, row 0 at the top
    #: ``(text, ink, level) -> (u0, v0, u1, v1)``, v measured upwards
    #: as a texture reads it.
    rects: dict


def build(entries, background, height: float, pad: float,
          cap: int = CAP_PX, width: int = 2048) -> Atlas:
    """Pack ``entries`` -- ``(text, symbol, ink)`` -- at every level.

    Shelf packing: cells in rows as wide as ``width``, each row as
    tall as its tallest.  A picture has tens of strings, so the atlas
    is a few hundred small cells and one texture.
    """
    cells = []
    for text, symbol, ink in dict.fromkeys(entries):
        for level, color in enumerate(level_colors(ink, background)):
            cells.append(((text, tuple(ink), level),
                          cell(text, symbol, color, background,
                               height, pad, cap)))
    placed, x, y, row = [], 0, 0, 0
    for key, image in cells:
        h, w = image.shape[:2]
        if x + w > width and x:
            x, y, row = 0, y + row + 1, 0
        placed.append((key, image, x, y))
        x += w + 1
        row = max(row, h)
    total_h = max(1, y + row)
    total_w = max(1, min(width, max((px + im.shape[1]
                                     for _k, im, px, _py in placed),
                                    default=1)))
    atlas = np.zeros((total_h, total_w, 4), np.uint8)
    atlas[:, :, :3] = np.asarray(background, np.uint8)
    rects = {}
    for key, image, px, py in placed:
        h, w = image.shape[:2]
        atlas[py:py + h, px:px + w] = image
        # Half a texel in from each edge, so linear filtering never
        # reaches a neighbouring cell.
        rects[key] = ((px + 0.5) / total_w,
                      1.0 - (py + h - 0.5) / total_h,
                      (px + w - 0.5) / total_w,
                      1.0 - (py + 0.5) / total_h)
    return Atlas(atlas, rects)
