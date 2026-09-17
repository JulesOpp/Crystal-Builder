"""
xtal.io.trajectory
==================
Many frames of one structure: multi-frame extended XYZ.

A relaxation is two hundred geometries and one of them is the answer.
The other hundred and ninety-nine are how it got there, which is what
anybody asks for when the answer is surprising -- so they are written
down as they arrive rather than held in memory and dropped when the run
ends.

**Extended XYZ, and not an invented format.**  Concatenated XYZ frames
with ``Lattice="..."`` on each comment line is what ASE, OVITO and VMD
already read, so a trajectory written here opens in all three without a
converter; and a trajectory written by any of them opens here.  That is
most of what a trajectory is for.  Everything else on the comment line
is ``key=value``, which is the same convention, so the energy of a
frame travels with it and an unknown key is carried rather than lost.

**Writing is streaming.**  :class:`TrajectoryWriter` appends a frame
and flushes it: 5184 sites is 124 kB a frame and 200 steps is 25 MB,
which is fine on disk and not fine in a signal queue.  A run that is
killed halfway leaves a trajectory that is short, not one that is
broken.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.core.lattice import Lattice

EXTENSION = ".extxyz"
PROPERTIES = "species:S:1:pos:R:3"

# key="quoted value" | key=bare_value, which is the extxyz comment-line
# convention every reader of the format implements.
_INFO_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'
                      r'(?:"([^"]*)"|(\S+))')


def parse_info(comment: str) -> dict:
    """The ``key=value`` pairs of an extended XYZ comment line.

    Values are left as strings apart from the ones with an agreed
    meaning: ``Lattice`` is nine numbers and anything that parses as a
    number is a number.  A comment line that is prose rather than
    key-value pairs simply yields nothing, which is how a plain XYZ
    file reads.
    """
    info: dict = {}
    for key, quoted, bare in _INFO_RE.findall(comment or ""):
        text = quoted if quoted else bare
        info[key] = _value(key, text)
    return info


def _value(key: str, text: str):
    if key == "Lattice":
        try:
            values = [float(v) for v in text.split()]
        except ValueError:
            return text
        return np.array(values).reshape(3, 3) if len(values) == 9 \
            else text
    if key == "Properties":
        return text
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def format_info(info: dict) -> str:
    """The inverse of :func:`parse_info`, in a stable order."""
    parts = []
    for key, value in info.items():
        if value is None:
            continue
        if isinstance(value, np.ndarray):
            text = " ".join(f"{v:.8f}" for v in np.asarray(
                value, dtype=float).ravel())
            parts.append(f'{key}="{text}"')
        elif isinstance(value, str):
            parts.append(f'{key}="{value}"' if " " in value
                         else f"{key}={value}")
        elif isinstance(value, bool):
            parts.append(f"{key}={'T' if value else 'F'}")
        elif isinstance(value, int | np.integer):
            parts.append(f"{key}={int(value)}")
        else:
            parts.append(f"{key}={float(value):.8f}")
    return " ".join(parts)


# ======================================================================
#  ONE FRAME
# ======================================================================

@dataclass(frozen=True)
class Frame:
    """One geometry: the atoms, the cell, and what was known about it.

    The coordinates are cartesian and of the **P1 cell**, because that
    is what the format holds and what another program will read.  A
    frame is not a :class:`~xtal.core.structure.Structure` and does not
    pretend to be one: it has no space group, no asymmetric unit and no
    bonds, and turning it back into a structure is a decision the
    caller makes (:meth:`to_structure`), not something that happens on
    the way in.
    """

    elements: tuple[str, ...]
    cart: np.ndarray                        # (N, 3)
    lattice: Lattice | None = None
    info: dict = field(default_factory=dict)

    @property
    def n_atoms(self) -> int:
        return len(self.elements)

    @property
    def energy(self) -> float | None:
        value = self.info.get("energy")
        return None if value is None else float(value)

    @property
    def step(self) -> int | None:
        value = self.info.get("step")
        return None if value is None else int(value)

    def frac(self, lattice: Lattice | None = None) -> np.ndarray:
        """Fractional coordinates, in the frame's cell or another one.

        Playing a trajectory back against an open structure asks for
        the second: the frame carries the cell it was written with, and
        the document has its own, and where a run held the cell fixed
        they are the same cell.
        """
        cell = lattice or self.lattice
        if cell is None:
            raise ValueError("the frame has no cell to be fractional "
                             "in")
        if not self.n_atoms:
            return np.zeros((0, 3))
        return cell.to_frac(self.cart)

    def to_structure(self, space_group=None):
        """A P1 structure with these atoms in this cell."""
        from xtal.core.site import Site
        from xtal.core.spacegroup import SpaceGroup
        from xtal.core.structure import Structure

        if self.lattice is None:
            raise ValueError("a frame with no cell cannot become a "
                             "structure; read it through xtal.io.xyz, "
                             "which pads a box around it")
        frac = self.frac()
        structure = Structure(
            lattice=self.lattice,
            sites=[Site(symbol, f) for symbol, f
                   in zip(self.elements, frac, strict=True)],
            space_group=space_group or SpaceGroup.p1())
        structure.ensure_labels()
        return structure

    def text(self) -> str:
        """This frame as it is written to a file."""
        info = dict(self.info)
        if self.lattice is not None:
            info = {"Lattice": self.lattice.matrix,
                    "Properties": PROPERTIES, **info}
        lines = [str(self.n_atoms), format_info(info)]
        for symbol, (x, y, z) in zip(self.elements, self.cart,
                                     strict=True):
            lines.append(f"{symbol:<4s} {x: 14.8f} {y: 14.8f} "
                         f"{z: 14.8f}")
        lines.append("")
        return "\n".join(lines)


def frame_of(structure, **info) -> Frame:
    """The P1 cell of ``structure`` as a frame.

    Every extra keyword lands on the comment line, so
    ``frame_of(s, energy=e, step=n)`` is the whole of what an optimiser
    has to say about an iteration.
    """
    from xtal.core import p1

    cell = p1.expand(structure)
    return Frame(elements=tuple(cell.elements), cart=cell.cart,
                 lattice=structure.lattice, info=dict(info))


# ======================================================================
#  MANY FRAMES
# ======================================================================

@dataclass
class Trajectory:
    """The frames of one run, in the order they were written."""

    frames: list[Frame] = field(default_factory=list)
    path: Path | None = None

    def __len__(self) -> int:
        return len(self.frames)

    def __iter__(self) -> Iterator[Frame]:
        return iter(self.frames)

    def __getitem__(self, index) -> Frame:
        return self.frames[index]

    @property
    def n_frames(self) -> int:
        return len(self.frames)

    @property
    def n_atoms(self) -> int:
        return self.frames[0].n_atoms if self.frames else 0

    @property
    def elements(self) -> tuple[str, ...]:
        return self.frames[0].elements if self.frames else ()

    @property
    def lattice(self) -> Lattice | None:
        return self.frames[0].lattice if self.frames else None

    @property
    def is_fixed_cell(self) -> bool:
        """Did every frame share one cell?

        A fixed-cell run can be played back against the open structure
        without touching its lattice, which is the common case and the
        cheap one.
        """
        first = self.lattice
        if first is None:
            return False
        return all(f.lattice is not None
                   and np.allclose(f.lattice.matrix, first.matrix)
                   for f in self.frames)

    @property
    def energies(self) -> np.ndarray:
        """One energy per frame; NaN where a frame did not carry one."""
        return np.array([np.nan if f.energy is None else f.energy
                         for f in self.frames], dtype=float)

    @property
    def steps(self) -> list:
        """The step number of each frame, falling back to its index --
        so a trajectory from somewhere else, which carries no step
        numbers, still has an x axis."""
        return [i if f.step is None else f.step
                for i, f in enumerate(self.frames)]

    def is_compatible(self, structure) -> bool:
        """Could this trajectory be played against that structure?

        The test is the elements of the P1 cell, in order.  Atom counts
        alone would let a trajectory of one crystal drive another with
        the same number of atoms, which would be nonsense drawn
        convincingly.
        """
        from xtal.core import p1

        if not self.frames:
            return False
        return tuple(p1.expand(structure).elements) == self.elements

    def text(self) -> str:
        return "".join(frame.text() for frame in self.frames)


# ======================================================================
#  READING AND WRITING
# ======================================================================

def read_frames(text: str) -> list[Frame]:
    """Every frame in a concatenated XYZ document."""
    lines = text.splitlines()
    frames, cursor = [], 0
    while cursor < len(lines):
        if not lines[cursor].strip():           # blank between frames
            cursor += 1
            continue
        frame, cursor = _read_frame(lines, cursor)
        frames.append(frame)
    return frames


def _read_frame(lines: list[str], start: int) -> tuple[Frame, int]:
    try:
        n_atoms = int(lines[start].split()[0])
    except (ValueError, IndexError):
        raise ValueError(
            f"line {start + 1} should be an atom count, and is "
            f"{lines[start]!r}") from None
    if n_atoms < 0:
        raise ValueError(f"negative atom count on line {start + 1}")
    body = lines[start + 2:start + 2 + n_atoms]
    if len(body) < n_atoms:
        raise ValueError(
            f"the frame at line {start + 1} claims {n_atoms} atoms and "
            f"the file ends after {len(body)}")

    info = parse_info(lines[start + 1] if start + 1 < len(lines) else "")
    symbols, coordinates = [], []
    for offset, line in enumerate(body):
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(
                f"malformed XYZ line {start + 3 + offset}: {line!r}")
        symbols.append(parts[0])
        coordinates.extend(parts[1:4])
    cart = (np.array(coordinates, dtype=float).reshape(n_atoms, 3)
            if n_atoms else np.zeros((0, 3)))

    matrix = info.pop("Lattice", None)
    info.pop("Properties", None)
    lattice = (Lattice(np.asarray(matrix, dtype=float))
               if isinstance(matrix, np.ndarray) else None)
    return Frame(tuple(symbols), cart, lattice, info), \
        start + 2 + n_atoms


def read_trajectory(path) -> Trajectory:
    """Read a multi-frame file whole.

    Whole, and not lazily: a trajectory is scrubbed backwards as often
    as forwards, and a run of a few hundred frames is a few tens of
    megabytes.  A file too large for that is a reason to write a
    windowed reader, not a reason to make every playback seek.
    """
    path = Path(path)
    return Trajectory(read_frames(path.read_text(encoding="utf-8")), path=path)


def write_trajectory(frames: Iterable[Frame], path) -> Path:
    path = Path(path)
    with TrajectoryWriter(path) as writer:
        for frame in frames:
            writer.append_frame(frame)
    return path


class TrajectoryWriter:
    """Append frames to a file, one at a time, flushing each.

    A run that is cancelled, crashes or is killed has still written
    every frame it reported, which is the whole reason the frames go to
    disk as they arrive rather than being collected and written at the
    end.
    """

    def __init__(self, path, append: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a" if append else "w",
                                      encoding="utf-8")
        self.n_frames = 0

    def append_frame(self, frame: Frame) -> None:
        self._handle.write(frame.text())
        self._handle.flush()
        self.n_frames += 1

    def append(self, structure, **info) -> None:
        """Write the P1 cell of ``structure`` as the next frame."""
        self.append_frame(frame_of(structure, **info))

    def close(self) -> None:
        if self._handle is not None and not self._handle.closed:
            self._handle.close()

    @property
    def closed(self) -> bool:
        return self._handle is None or self._handle.closed

    def __enter__(self) -> TrajectoryWriter:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
