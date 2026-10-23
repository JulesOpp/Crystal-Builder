"""
xtalapp.viewport.colormaps
==========================
Turning a number per atom or per bond into a colour, for *Colour by*.

The maps are matplotlib's, sampled at nine points and interpolated
linearly between them: close enough to the originals to read the same,
and no import of matplotlib on the path that draws every frame.
Viridis and plasma are perceptually uniform, so equal steps in the
quantity look like equal steps; coolwarm is diverging, for a quantity
whose middle means something -- a bond as long as its ideal one.

**An undefined value is grey and off the scale**
(:data:`UNDEFINED`), never the scale's bottom colour: an atom with no
angle drawn as the smallest angle in the picture is a false minimum.
"""

from __future__ import annotations

import numpy as np

COLOR_MAPS = {
    "viridis": ((68, 1, 84), (71, 45, 123), (59, 82, 139),
                (44, 114, 142), (33, 145, 140), (40, 174, 128),
                (94, 201, 98), (173, 220, 48), (253, 231, 37)),
    "plasma": ((13, 8, 135), (76, 2, 161), (126, 3, 168),
               (169, 35, 149), (204, 71, 120), (229, 107, 93),
               (248, 149, 64), (253, 197, 39), (240, 249, 33)),
    "coolwarm": ((59, 76, 192), (98, 130, 234), (141, 176, 254),
                 (184, 208, 249), (221, 221, 221), (245, 196, 173),
                 (244, 154, 123), (222, 96, 77), (180, 4, 38)),
}

#: What a value with no meaning is drawn in.  A mid grey is in none of
#: the maps, so it cannot be read as a place on any of them.
UNDEFINED = (150, 150, 150)

#: Swatches in the colour bar, the two ends included.
BAR_STEPS = 6


def colors(found, lo: float, hi: float,
           name: str = "viridis") -> np.ndarray:
    """``(N, 3)`` uint8 for ``found`` placed between ``lo`` and ``hi``.

    Outside the range is clamped to its ends, so a range narrowed by
    hand still colours everything; NaN is :data:`UNDEFINED`.  A range
    of one value is the middle of the map.
    """
    found = np.asarray(found, float)
    anchors = np.array(COLOR_MAPS.get(name, COLOR_MAPS["viridis"]),
                       float)
    span = hi - lo
    t = (np.full(found.shape, 0.5) if not span > 0
         else np.clip((found - lo) / span, 0.0, 1.0))
    position = np.nan_to_num(t) * (len(anchors) - 1)
    k = np.minimum(position.astype(int), len(anchors) - 2)
    w = (position - k)[:, None]
    out = anchors[k] * (1.0 - w) + anchors[k + 1] * w
    out[~np.isfinite(found)] = UNDEFINED
    return np.round(out).astype(np.uint8)


def bar(label: str, lo: float, hi: float, name: str,
        integer: bool = False, undefined: bool = False) -> tuple:
    """The legend rows of a colour bar: a heading with no swatch, the
    top of the range down to the bottom, and *none* when anything
    drawn has no value -- a short word, because the column ends at
    the window's edge.

    Steps of whole numbers for a count, so a coordination bar reads
    2, 3, 4 and never 2.4.
    """
    if integer:
        steps = np.arange(np.ceil(lo), np.floor(hi) + 1)
        if len(steps) > BAR_STEPS + 2:
            steps = np.unique(np.round(
                np.linspace(lo, hi, BAR_STEPS)))
    else:
        steps = (np.array([lo]) if not hi > lo
                 else np.linspace(lo, hi, BAR_STEPS))
    swatches = colors(steps, lo, hi, name)
    rows = [(label, None)]
    for value, color in zip(steps[::-1], swatches[::-1], strict=True):
        rows.append((_number(value, integer, hi - lo),
                     tuple(int(c) for c in color)))
    if undefined:
        rows.append(("none", UNDEFINED))
    return tuple(rows)


def _number(value: float, integer: bool, span: float) -> str:
    if integer:
        return f"{value:.0f}"
    digits = 3 if span < 0.1 else 2 if span < 10 else 1
    return f"{value:.{digits}f}"
