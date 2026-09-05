"""
xtal.io.xy
==========
A diffraction pattern as two columns: ``.xy``.

Whitespace-delimited 2-theta and intensity, one pair a line, with
``#`` comments -- which is what every diffractometer's export and
every plotting script already reads, and is the format the measured
patterns this application overlays arrive in.

**It is not in :data:`xtal.io.FORMATS`, and that is deliberate.**
Every entry in that registry reads and writes a
:class:`~xtal.core.structure.Structure`: ``File > Open`` builds its
filter from :meth:`~xtal.io.registry.FormatRegistry.readable` and
hands whatever comes back to a :class:`~xtalapp.document.Document`.
A pattern is not a structure, so registering it there would put
``.xy`` in the Open dialog and break the moment somebody chose one.
A second registry for measurements is worth adding when there is a
second measurement to put in it -- the same rule the report blocks and
the parameter kinds are held to -- and today there is one.

**Reading is deliberately forgiving and writing is not.**  Files in
the wild carry a header, blank lines, commas, and a third column of
errors that nothing here uses; refusing them would mean the user
editing a file before the application would look at it.  What is
written is two columns and a comment header naming what made it, so
that a pattern exported from here and read back is the same numbers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = ["EXTENSIONS", "read_xy", "write_xy", "xy_string"]

EXTENSIONS = (".xy", ".xye", ".dat")

#: What a line has to have before it is data.  Anything else is a
#: header, a comment or a blank -- not an error.
_COMMENT = "#!;/*"


def read_xy(path) -> tuple[np.ndarray, np.ndarray]:
    """``(two_theta, intensity)`` from a two-column file.

    A third column is an uncertainty in most of the files that have
    one, and is ignored rather than refused: a pattern that plots is
    what was asked for, and dropping the errors loses nothing this
    application does anything with.
    """
    path = Path(path)
    x: list[float] = []
    y: list[float] = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            row = line.strip()
            if not row or row[0] in _COMMENT:
                continue
            parts = row.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                first, second = float(parts[0]), float(parts[1])
            except ValueError:
                continue                # a header row of column names
            x.append(first)
            y.append(second)
    if not x:
        raise ValueError(
            f"no two-column data in {path.name} -- an .xy file is "
            f"2-theta and intensity, one pair a line")
    order = np.argsort(np.asarray(x, dtype=float))
    return (np.asarray(x, dtype=float)[order],
            np.asarray(y, dtype=float)[order])


def xy_string(x, y, header: str = "") -> str:
    """The file's text, for a test and for a clipboard."""
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    if len(x) != len(y):
        raise ValueError(
            f"got {len(x)} angles and {len(y)} intensities")
    lines = [f"# {line}" for line in (header or "").splitlines()
             if line.strip()]
    lines += [f"{a:.5f}  {b:.6g}" for a, b in zip(x, y, strict=True)]
    return "\n".join(lines) + "\n"


def write_xy(x, y, path, header: str = "") -> Path:
    """Write two columns, with a comment header saying what they are.

    The header is comments, so the file is still read by anything that
    reads ``.xy`` at all -- including :func:`read_xy`, which is the
    round trip a test asserts.
    """
    path = Path(path)
    path.write_text(xy_string(x, y, header), encoding="utf-8")
    return path
