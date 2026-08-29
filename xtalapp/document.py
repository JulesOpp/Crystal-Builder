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
from xtal.core import bonding, p1, properties
from xtal.core import selection as sel
from xtal.core.selection import Selection
from xtal.core.structure import Change
from xtal.io import FORMATS
from xtalapp.viewport.view_settings import ViewSettings


class Document(QObject):
    """One open structure and its view state."""

    structureChanged = Signal(int)      # a Change flag
    selectionChanged = Signal()
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
        self.selection = Selection()
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
        self.selection.clear()
        if modified:
            self.set_modified(True)
        self.structureChanged.emit(int(change))
        self.selectionChanged.emit()
        self.titleChanged.emit(self.title)

    def apply(self, mutate, change: Change = Change.ALL) -> None:
        """Run ``mutate(structure)`` and announce the result.

        In phase 4 this becomes "push a Command"; every caller written
        against it now keeps working when it does.
        """
        mutate(self._structure)
        self.set_modified(True)
        if change & (Change.TOPOLOGY | Change.SYMMETRY | Change.CELL):
            self.selection.prune(self.cell.n_atoms)
            self.selectionChanged.emit()
        self.structureChanged.emit(int(change))

    # -- derived data --------------------------------------------------

    @property
    def cell(self):
        """The P1 expansion -- what is drawn, and what a click hits."""
        return p1.expand(self._structure)

    @property
    def graph(self):
        return bonding.graph(self._structure)

    # -- selection -----------------------------------------------------

    def select(self, atoms, mode: str = "set") -> None:
        """Select atoms of the P1 cell.  ``mode`` is set, add, toggle
        or remove."""
        atoms = [int(a) for a in atoms]
        if mode == "set":
            self.selection.set_atoms(atoms)
        elif mode == "add":
            self.selection.add_atoms(atoms)
        elif mode == "remove":
            self.selection.remove_atoms(atoms)
        elif mode == "toggle":
            for atom in atoms:
                self.selection.toggle_atom(atom)
        else:
            raise ValueError(f"unknown selection mode {mode!r}")
        self.selectionChanged.emit()

    def select_bond(self, key, mode: str = "set") -> None:
        if mode == "set":
            self.selection.bonds = {key}
        else:
            self.selection.toggle_bond(key)
        self.selectionChanged.emit()

    def select_none(self) -> None:
        self.selection.clear()
        self.selectionChanged.emit()

    def select_all(self) -> None:
        self.selection.set_atoms(range(self.cell.n_atoms))
        self.selectionChanged.emit()

    def invert_selection(self) -> None:
        self.selection.invert(self.cell.n_atoms)
        self.selectionChanged.emit()

    def select_element(self, symbol: str, mode: str = "set") -> None:
        self.select(sel.by_element(self.cell, symbol), mode)

    def select_site(self, site_index: int, mode: str = "set") -> None:
        """Select every image of one asymmetric-unit site."""
        self.select(sel.by_site(self.cell, site_index), mode)

    def expand_selection(self, how: str, value=1) -> None:
        """Grow the selection: 'shell', 'fragment', 'orbit' or
        'radius'."""
        atoms = set(self.selection.atoms)
        if not atoms:
            return
        if how == "shell":
            atoms = sel.expand_shell(self.graph, atoms, int(value))
        elif how == "fragment":
            atoms = sel.expand_fragment(self.graph, atoms)
        elif how == "orbit":
            atoms = sel.symmetry_orbit(self.cell, atoms)
        elif how == "radius":
            atoms = sel.within_radius(self.cell, self._structure.lattice,
                                      atoms, float(value))
        else:
            raise ValueError(f"unknown expansion {how!r}")
        self.select(atoms, "set")

    def selected_sites(self) -> set:
        return sel.sites_for(self.cell, self.selection.atoms)

    def selection_is_orbit_complete(self) -> bool:
        return sel.covers_whole_orbits(self.cell, self.selection.atoms)

    def selection_summary(self) -> str:
        return sel.describe(self._structure, self.cell, self.selection)

    def selection_orbit_report(self) -> str:
        return sel.orbit_report(self.cell, self.selection.atoms)

    # -- editing the selection -----------------------------------------

    def delete_selection(self) -> str:
        """Delete the sites behind the selected atoms.

        Symmetry ties images together, so this removes whole orbits:
        the caller is expected to have shown
        :meth:`selection_orbit_report` first.
        """
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing to delete"
        atoms = sum(self.cell.multiplicity(s) for s in sites)
        self.apply(lambda structure: structure.remove_sites(sites),
                   Change.TOPOLOGY)
        return f"deleted {len(sites)} site(s) ({atoms} atoms)"

    def set_selection_element(self, symbol: str) -> str:
        """Change the element of every selected atom's site."""
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"

        def mutate(structure):
            for index in sites:
                structure.sites[index].element = symbol
            structure.touch(Change.TOPOLOGY)

        self.apply(mutate, Change.TOPOLOGY)
        return f"changed {len(sites)} site(s) to {symbol}"

    def set_site_property(self, site_index: int, **values) -> None:
        """Edit one site's label, occupancy, Uiso, charge or
        coordinates."""
        change = (Change.POSITIONS if set(values) <= {"frac"}
                  else Change.TOPOLOGY)

        def mutate(structure):
            site = structure.sites[site_index]
            for key, value in values.items():
                setattr(site, key, value)
            structure.touch(change)

        self.apply(mutate, change)

    def reduce_to_p1(self) -> str:
        """Expand every orbit into explicit sites, so single atoms can
        be edited independently."""
        from xtal.core.symmetry import reduce_to_p1
        before = self._structure.space_group.short_name
        self.set_structure(reduce_to_p1(self._structure),
                           Change.SYMMETRY)
        return f"expanded {before} to P1"

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
