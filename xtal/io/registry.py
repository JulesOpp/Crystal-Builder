"""
xtal.io.registry
================
The file-format registry: extension -> reader/writer.

Adding a format is registering a :class:`Format`.  Nothing else in the
application learns about it -- the open dialog, the save dialog, the
CLI and drag-and-drop all read their lists from here.  That is the
mechanism SHELX ``.res``, VASP ``POSCAR``, CHGCAR volumetric data and
anything else later plug into.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Format:
    """One file format the application can read and/or write."""

    name: str                       # "cif"
    description: str                # "Crystallographic Information File"
    extensions: tuple[str, ...]     # (".cif", ".mcif")
    read: Callable | None = None    # (path) -> Structure
    write: Callable | None = None   # (structure, path, **kw) -> None
    read_all: Callable | None = None  # (path) -> list[Structure]
    # What survives a round trip, for the export dialog to be honest
    # about: {"symmetry", "occupancy", "adp", "bonds", "charges"}
    keeps: frozenset = field(default_factory=frozenset)

    @property
    def can_read(self) -> bool:
        return self.read is not None

    @property
    def can_write(self) -> bool:
        return self.write is not None

    def filter_string(self) -> str:
        """Qt-style file filter, e.g. 'CIF (*.cif *.mcif)'."""
        globs = " ".join(f"*{e}" for e in self.extensions)
        return f"{self.description} ({globs})"


class FormatRegistry:
    """Extension -> Format, with dispatch helpers."""

    def __init__(self):
        self._formats: dict[str, Format] = {}

    def register(self, fmt: Format) -> Format:
        self._formats[fmt.name] = fmt
        return fmt

    def __contains__(self, name: str) -> bool:
        return name in self._formats

    def __iter__(self):
        return iter(self._formats.values())

    def get(self, name: str) -> Format:
        try:
            return self._formats[name]
        except KeyError:
            raise ValueError(f"unknown format: {name!r}") from None

    def by_extension(self, path) -> Format:
        suffix = Path(path).suffix.lower()
        for fmt in self._formats.values():
            if suffix in fmt.extensions:
                return fmt
        raise ValueError(
            f"no format is registered for {suffix or 'that file'!r}")

    def readable(self) -> list[Format]:
        return [f for f in self._formats.values() if f.can_read]

    def writable(self) -> list[Format]:
        return [f for f in self._formats.values() if f.can_write]

    # -- dispatch ------------------------------------------------------

    def read(self, path, fmt: str | None = None):
        """Read one structure from ``path``."""
        f = self.get(fmt) if fmt else self.by_extension(path)
        if not f.can_read:
            raise ValueError(f"{f.name} files cannot be read")
        return f.read(Path(path))

    def read_all(self, path, fmt: str | None = None) -> list:
        """Read every structure in a multi-block file."""
        f = self.get(fmt) if fmt else self.by_extension(path)
        if f.read_all is not None:
            return f.read_all(Path(path))
        return [self.read(path, fmt)]

    def write(self, structure, path, fmt: str | None = None, **kw):
        f = self.get(fmt) if fmt else self.by_extension(path)
        if not f.can_write:
            raise ValueError(f"{f.name} files cannot be written")
        return f.write(structure, Path(path), **kw)


FORMATS = FormatRegistry()
