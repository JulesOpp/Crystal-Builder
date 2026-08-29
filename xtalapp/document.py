"""
xtalapp.document
================
A Document is one open structure: the crystal, how it is being viewed,
where it came from, and whether it has unsaved changes.

Widgets never hold a Structure of their own -- they hold a Document and
listen to its signals.  The signals carry a *change hint*
(``xtal.core.structure.Change``) so the viewport can tell "an atom
moved" from "the topology changed" and pick the cheap redraw over the
expensive one.

The undo stack lands here in phase 4; the API is already shaped for it,
which is why every mutation goes through :meth:`apply` rather than
letting callers poke at ``document.structure``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from xtal import Structure
from xtal.core import properties
from xtal.core.structure import Change
from xtal.io import FORMATS
from xtalapp.viewport.view_settings import ViewSettings


class Document(QObject):
    """One open structure and its view state."""

    structureChanged = Signal(int)      # a Change flag
    viewChanged = Signal()
    modifiedChanged = Signal(bool)
    titleChanged = Signal(str)

    def __init__(self, structure: Structure | None = None,
                 path=None, parent=None):
        super().__init__(parent)
        self._structure = structure or Structure.empty()
        self._path = Path(path) if path else None
        self._modified = False
        self.view = ViewSettings()
        self.warnings: list[str] = list(
            self._structure.meta.get("warnings", []))

    # -- loading and saving --------------------------------------------

    @classmethod
    def load(cls, path) -> Document:
        """Read a structure file into a new document."""
        structure = FORMATS.read(path)
        return cls(structure, path=path)

    def save(self, path=None) -> Path:
        """Write the structure back out.  Saving clears the modified
        flag; exporting (a different format, or P1) does not."""
        target = Path(path) if path else self._path
        if target is None:
            raise ValueError("no path to save to")
        FORMATS.write(self._structure, target)
        self._path = target
        self.set_modified(False)
        self.titleChanged.emit(self.title)
        return target

    def export(self, path, **kwargs) -> Path:
        """Write a copy somewhere without adopting it as the
        document's own file."""
        FORMATS.write(self._structure, Path(path), **kwargs)
        return Path(path)

    # -- structure -----------------------------------------------------

    @property
    def structure(self) -> Structure:
        return self._structure

    def set_structure(self, structure: Structure,
                      change: Change = Change.ALL,
                      modified: bool = True) -> None:
        """Replace the structure wholesale (open, supercell, P1, ...)."""
        self._structure = structure
        self.warnings = list(structure.meta.get("warnings", []))
        if modified:
            self.set_modified(True)
        self.structureChanged.emit(int(change))
        self.titleChanged.emit(self.title)

    def apply(self, mutate, change: Change = Change.ALL) -> None:
        """Run ``mutate(structure)`` and announce the result.

        In phase 4 this becomes "push a Command"; every caller written
        against it now keeps working when it does.
        """
        mutate(self._structure)
        self.set_modified(True)
        self.structureChanged.emit(int(change))

    # -- view ----------------------------------------------------------

    def update_view(self, **kwargs) -> None:
        """Change view settings; never marks the document modified,
        because how a crystal is drawn is not part of the crystal."""
        for key, value in kwargs.items():
            if not hasattr(self.view, key):
                raise AttributeError(f"no view setting {key!r}")
            setattr(self.view, key, value)
        self.viewChanged.emit()

    def set_cells(self, na: int, nb: int, nc: int) -> None:
        self.view.set_cells(na, nb, nc)
        self.viewChanged.emit()

    # -- state ---------------------------------------------------------

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def modified(self) -> bool:
        return self._modified

    def set_modified(self, value: bool) -> None:
        if value != self._modified:
            self._modified = value
            self.modifiedChanged.emit(value)
            self.titleChanged.emit(self.title)

    @property
    def title(self) -> str:
        if self._path is not None:
            name = self._path.name
        else:
            name = str(self._structure.meta.get("title") or "Untitled")
        return f"{name}*" if self._modified else name

    def info(self):
        return properties.info(self._structure)

    def status_text(self) -> str:
        """The one-line summary for the status bar."""
        if not self._structure.n_sites:
            return "empty cell"
        info = self.info()
        return (f"{info.formula}  ·  Z = {info.z}  ·  "
                f"{info.space_group} (#{info.space_group_number})  ·  "
                f"{info.n_sites} sites / {info.n_atoms} atoms  ·  "
                f"V = {info.volume:.2f} A^3  ·  "
                f"{info.density:.3f} g/cm^3")

    def __repr__(self) -> str:
        return f"Document({self.title}, {self._structure!r})"
