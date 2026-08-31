"""
xtalapp.document
================
A Document is one open structure: the crystal, how it is being viewed,
what is selected, and its undo history.

Widgets never hold a Structure of their own and never mutate one --
they hold a Document, listen to its signals, and change it by running
Commands through :meth:`Document.run`.  That single funnel is what
makes every edit in the application undoable, scriptable and testable
without a window.

Signals carry a *change hint* (``xtal.core.structure.Change``) so the
viewport can tell "an atom moved" from "the topology changed" and pick
the cheap redraw over the expensive one.

"Modified" is derived from the undo stack rather than being a flag that
edits set: undo back to the point you last saved and the document is
clean again, exactly as in any other editor.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from xtal import Structure
from xtal.commands import CommandStack, ReplaceStructure, SnapshotEdit
from xtal.commands import atoms as atom_commands
from xtal.commands import bonds as bond_commands
from xtal.commands import cell as cell_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.commands.clipboard import Fragment, PasteFragment
from xtal.core import bonding, measure, p1, properties
from xtal.core import selection as sel
from xtal.core.selection import Selection
from xtal.core.structure import CHEMISTRY, Change
from xtal.io import FORMATS, is_project, read_project, write_project
from xtal.io.project import EXTENSION as PROJECT_EXTENSION
from xtal.workspace import Workspace
from xtalapp import playback
from xtalapp.viewport.view_settings import ViewSettings


class PlaybackActive(RuntimeError):
    """An edit was attempted while a trajectory was being played."""


class Document(QObject):
    """One open structure, its view state, and its history."""

    structureChanged = Signal(int)      # a Change flag
    previewChanged = Signal()           # a geometry shown, not committed
    selectionChanged = Signal()
    measurementsChanged = Signal()
    viewChanged = Signal()
    historyChanged = Signal()
    modifiedChanged = Signal(bool)
    titleChanged = Signal(str)
    workspaceChanged = Signal()         # the entry this document is in
    playbackChanged = Signal()          # a trajectory opened or closed

    def __init__(self, structure: Structure | None = None,
                 path=None, parent=None):
        super().__init__(parent)
        # `is None`, not `or`: a Structure is falsy when it has no
        # sites, so `or` silently replaces a cell you set up before
        # adding any atoms with the default 10 A one.
        self._structure = (Structure.empty() if structure is None
                           else structure)
        self._path = Path(path) if path else None
        self._was_modified = False
        self.stack = CommandStack()
        self.view = ViewSettings()
        self.selection = Selection()
        # Measurements are neither structure nor view: they are notes
        # about the crystal, so they live here, are saved with a
        # project, and never land on the undo stack.
        self.measurements: list = []
        self.warnings: list[str] = list(
            self._structure.meta.get("warnings", []))
        # Off, and a preference rather than a rule -- see
        # ``AppSettings.bonds_follow_geometry``.  The window sets it
        # from the preference on every document it opens.
        self.bonds_follow_geometry = False
        # The workspace entry this document's calculations land in,
        # and the trajectory currently being played back.  Both are
        # None until something puts one there; a document with neither
        # is exactly the document this application had before.
        self.entry = None
        self.playback: playback.Playback | None = None

    # ==================================================================
    #  LOADING AND SAVING
    # ==================================================================

    @classmethod
    def load(cls, path) -> Document:
        """Open a file.  A project brings its view and session with
        it; anything else brings only the crystal, which is the honest
        behaviour for an interchange format."""
        path = Path(path)
        if is_project(path):
            structure, view, session = read_project(path)
            document = cls(structure, path=path)
            document.view = ViewSettings.from_dict(view)
            document._restore_session(session)
        else:
            document = cls(FORMATS.read(path), path=path)
        document.attach_workspace()
        return document

    def attach_workspace(self, entry=None) -> object | None:
        """Bind this document to the workspace entry it lives in.

        Found by looking *upwards* from the file rather than by
        reading a path out of the project.  A workspace that was
        moved, renamed or copied to another machine still answers, and
        a stored absolute path would confidently be wrong -- which is
        also why saving a project inside its own entry folder is what
        the window offers.
        """
        if entry is not None:
            self.entry = entry
        elif self._path is not None:
            workspace = Workspace.find(self._path)
            self.entry = (workspace.entry_for(self._path)
                          if workspace is not None else None)
        self.workspaceChanged.emit()
        return self.entry

    def write_project(self, path) -> Path:
        """Write the structure, the view and the session as one file,
        without adopting the path.  :meth:`save` is the one that
        adopts."""
        return write_project(self._structure, Path(path),
                             view=self.view.to_dict(),
                             session=self.session())

    # ``Save Project...`` used to be a third thing beside Save and
    # Save As.  It is what Save now is, and the old name is kept
    # pointing at the same behaviour so nothing that called it is
    # silently writing a different file.
    save_project = write_project

    def session(self) -> dict:
        """What is selected and what has been measured."""
        return {
            "selection": sorted(self.selection.atoms),
            "bonds": [list(k) if not isinstance(k, tuple) else
                      [k[0], k[1], list(k[2])]
                      for k in sorted(self.selection.bonds)],
            "measurements": [m.to_dict() for m in self.measurements],
        }

    def _restore_session(self, session: dict) -> None:
        """Put a saved selection and measurement list back.

        Anything that no longer fits the structure is dropped rather
        than restored wrong -- a project is a convenience, and a
        measurement pointing at an atom that is not there would be a
        lie about the crystal.
        """
        cell = self.cell
        atoms = [int(a) for a in session.get("selection", [])
                 if 0 <= int(a) < cell.n_atoms]
        if atoms:
            self.selection.set_atoms(atoms)
        for record in session.get("bonds", []):
            try:
                i, j, image = record
                self.selection.bonds.add(
                    (int(i), int(j), tuple(int(v) for v in image)))
            except (TypeError, ValueError):
                continue
        for record in session.get("measurements", []):
            try:
                saved = measure.Measurement.from_dict(record)
                if max(saved.atoms) < cell.n_atoms:
                    self.measurements.append(measure.measure(
                        cell, self._structure.lattice, saved.atoms))
            except (KeyError, TypeError, ValueError):
                continue

    def save(self, path=None) -> Path:
        """Save the session.  Always a project, never an export.

        Save and Save As are about the *project*: the structure, the
        bonds drawn by hand, the view, the selection, the measurements
        and the atom-type overrides.  The extension is not a choice,
        because the same command writing a whole session or throwing
        most of it away depending on three characters after a dot is
        not a command anybody can predict.  Writing a file for another
        program is :meth:`export`, which never adopts a path and never
        pretends to keep what a format cannot hold.
        """
        target = Path(path) if path else self._path
        if target is None:
            raise ValueError("no path to save to")
        target = Path(target).with_suffix(PROJECT_EXTENSION)
        self.write_project(target)
        self._path = target
        self.stack.mark_clean()
        self._announce_modified()
        self.titleChanged.emit(self.title)
        return target

    def export(self, path, selection_only: bool = False,
               **kwargs) -> Path:
        """Write a copy for something else to read.

        One way, always: it never becomes the document's path, never
        clears the modified flag, and never pretends the format kept
        what it has nowhere to put.
        """
        FORMATS.write(self.exportable(selection_only), Path(path),
                      **kwargs)
        return Path(path)

    def exportable(self, selection_only: bool = False) -> Structure:
        """What an export would write."""
        if not selection_only:
            return self._structure
        return sel.substructure(self._structure, self.cell,
                                self.selection.atoms)

    # ==================================================================
    #  STRUCTURE
    # ==================================================================

    @property
    def structure(self) -> Structure:
        return self._structure

    @structure.setter
    def structure(self, value: Structure) -> None:
        """Assignment point for ReplaceStructure; emits nothing on its
        own, because the command runner announces the change."""
        self._structure = value

    def set_structure(self, structure: Structure,
                      change: Change = Change.ALL,
                      modified: bool = True) -> None:
        """Adopt a structure outside the undo history (opening a file,
        or starting again).  Clears the stack -- there is nothing
        sensible to undo *into*."""
        self._structure = structure
        self.warnings = list(structure.meta.get("warnings", []))
        self.selection.clear()
        self.measurements = []
        self.stack.clear()
        if not modified:
            self.stack.mark_clean()
        self._announce_modified()
        self.structureChanged.emit(int(change))
        self.selectionChanged.emit()
        self.historyChanged.emit()
        self.titleChanged.emit(self.title)

    # ==================================================================
    #  PLAYBACK
    # ==================================================================
    #
    # A trajectory open against this document puts it into a preview
    # state: the atoms show a frame, the history is untouched, and
    # edits are refused rather than silently lost at the next frame.

    @property
    def is_playing(self) -> bool:
        return self.playback is not None

    def open_trajectory(self, trajectory, path=None):
        """Start playing a trajectory against this structure."""
        self.playback = playback.open_playback(self._structure,
                                               trajectory, path)
        self.playbackChanged.emit()
        self.show_frame(0)
        return self.playback

    def show_frame(self, index: int):
        """Draw one frame.  A preview, and nothing more."""
        if self.playback is None:
            return None
        self.playback.index = self.playback.clamp(index)
        self.preview_positions(
            self.playback.frac_at(self.playback.index,
                                  self._structure.lattice))
        return self.playback.frame

    def close_playback(self, restore: bool = True) -> None:
        """Leave playback, putting the atoms back where they were.

        ``restore=False`` is for the caller that has just adopted a
        frame: the geometry on screen is then the one it committed,
        and putting the old one back would undo the command that was
        the whole point of the gesture.
        """
        if self.playback is None:
            return
        before = self.playback.before
        self.playback = None
        if restore and before is not None:
            self.preview_positions(before)
        self.playbackChanged.emit()

    def adopt_frame(self) -> str:
        """Keep the frame on screen, as one undoable edit.

        The way out of playback that keeps something.  It pushes the
        same command an optimisation pushes, so undo afterwards gives
        back the geometry the user was on before they started
        watching -- not the previous frame.
        """
        if self.playback is None:
            raise ValueError("no trajectory is open")
        from xtal.commands import ff as ff_commands
        frame = self.playback.index + 1
        frac = self.playback.frac_at(self.playback.index,
                                     self._structure.lattice)
        before = self.playback.before
        self.close_playback(restore=False)
        command = ff_commands.ApplyOptimizedGeometry(
            frac, label=f"Adopt frame {frame}", before=before)
        moved = command.displacement(self._structure)
        if moved < 1e-9:
            return "that frame is the geometry you already had"
        self.run(command)
        return (f"adopted frame {frame}; the furthest atom moved "
                f"{moved:.3f} A")

    # ==================================================================
    #  COMMANDS
    # ==================================================================

    def run(self, command) -> object:
        """Run a command and announce what it changed.

        This is the only way the application changes a structure.

        A document playing a trajectory back refuses: the atoms are
        showing a frame, so an edit made against them would be an edit
        of somebody else's geometry, and it would be wiped by the next
        frame.  The window disables the editing actions while a
        trajectory is open, and this is the backstop that makes that a
        rule rather than a habit.
        """
        if self.playback is not None:
            raise PlaybackActive(
                "this document is playing a trajectory back; adopt "
                "the frame or close the trajectory before editing")
        self.stack.push(command, self)
        self._after_change(command.change)
        return command

    def apply(self, mutate, change: Change = Change.ALL,
              label: str = "Edit") -> object:
        """Run an arbitrary mutation, undoably, by keeping a copy.

        Convenient from the console and from tests; a real command is
        cheaper and should be preferred for anything the UI does often.
        """
        return self.run(SnapshotEdit(mutate, label, change))

    def transaction(self, label: str):
        """Group several commands into one undo step:

            with document.transaction("Build water"):
                document.run(...)
        """
        return _Transaction(self, label)

    def break_merge(self) -> None:
        """End the current gesture, so the next edit is its own undo
        step.

        Held arrows and dragged spinboxes merge while they run; this is
        what tells the stack the gesture is over.  Without it the next
        nudge merges into the same step, and Ctrl+Z undoes more than
        the user did.
        """
        self.stack.break_merge()

    def undo(self) -> str:
        command = self.stack.undo(self)
        if command is None:
            return ""
        self._after_change(command.change)
        return command.label

    def redo(self) -> str:
        command = self.stack.redo(self)
        if command is None:
            return ""
        self._after_change(command.change)
        return command.label

    @property
    def can_undo(self) -> bool:
        return self.stack.can_undo

    @property
    def can_redo(self) -> bool:
        return self.stack.can_redo

    @property
    def undo_label(self) -> str:
        return self.stack.undo_label

    @property
    def redo_label(self) -> str:
        return self.stack.redo_label

    def _after_change(self, change: Change) -> None:
        self.warnings = list(self._structure.meta.get("warnings", []))
        if (self.bonds_follow_geometry and change & Change.POSITIONS
                and not change & CHEMISTRY):
            # The preference, applied.  Not a command and not on the
            # stack: undoing the edit that moved the atom has to undo
            # the perception that followed it, and it does, because
            # what is dropped here is re-derived from the geometry the
            # undo puts back.
            self._structure.clear_perceived()
            self._structure.drop_cache("bonds:")
            self._structure.drop_cache("uff-typing")
        if change & (Change.TOPOLOGY | Change.SYMMETRY | Change.CELL):
            self.selection.prune(self.cell.n_atoms)
            self.selectionChanged.emit()
            self._prune_measurements()
        elif change & Change.POSITIONS:
            self._remeasure()
        self._announce_modified()
        self.structureChanged.emit(int(change))
        self.historyChanged.emit()

    def _announce_modified(self) -> None:
        now = self.modified
        if now != self._was_modified:
            self._was_modified = now
            self.modifiedChanged.emit(now)
        self.titleChanged.emit(self.title)

    # ==================================================================
    #  DERIVED DATA
    # ==================================================================

    @property
    def cell(self):
        """The P1 expansion -- what is drawn, and what a click hits."""
        return p1.expand(self._structure)

    @property
    def graph(self):
        return bonding.graph(self._structure)

    # ==================================================================
    #  SELECTION
    # ==================================================================

    def select(self, atoms, mode: str = "set") -> None:
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
        """Invert over whole symmetry orbits, not over atoms.

        Every *edit* acts on whole orbits, so inverting a partial orbit
        atom-by-atom hands back a selection that overlaps the one it
        came from: the atoms you had are still, in effect, selected,
        because their orbit-mates are.  Growing to the orbit first
        makes the complement mean what it says.  The core predicate
        stays orbit-blind and the Document is the thing that knows
        about symmetry, which is how delete and move already work.  In
        P1 this is a no-op, which is the right way for it to degrade.
        """
        atoms = self.selection.atoms
        if atoms:
            self.selection.set_atoms(sel.symmetry_orbit(self.cell,
                                                        atoms))
        self.selection.invert(self.cell.n_atoms)
        self.selectionChanged.emit()

    def select_element(self, symbol: str, mode: str = "set") -> None:
        self.select(sel.by_element(self.cell, symbol), mode)

    def select_site(self, site_index: int, mode: str = "set") -> None:
        self.select(sel.by_site(self.cell, site_index), mode)

    def expand_selection(self, how: str, value=1) -> None:
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
            atoms = sel.within_radius(self.cell,
                                      self._structure.lattice, atoms,
                                      float(value))
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

    # ==================================================================
    #  EDITING
    # ==================================================================

    def add_atom(self, element: str, frac, occupancy: float = 1.0,
                 label: str = "") -> str:
        site = atom_commands.new_site(element, frac, occupancy, label)
        self.run(atom_commands.AddSites([site]))
        return f"added {element}"

    def delete_selection(self) -> str:
        """Delete the sites behind the selected atoms.  Symmetry ties
        images together, so this removes whole orbits."""
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing to delete"
        atoms = sum(self.cell.multiplicity(s) for s in sites)
        self.run(atom_commands.DeleteSites(sites))
        return f"deleted {len(sites)} site(s) ({atoms} atoms)"

    def set_selection_element(self, symbol: str) -> str:
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"
        self.run(atom_commands.SetElement(sites, symbol))
        return f"changed {len(sites)} site(s) to {symbol}"

    def set_site_property(self, site_index: int, **values) -> None:
        self.run(atom_commands.SetSiteProperties(site_index, **values))

    def move_selection(self, delta, cartesian: bool = False) -> str:
        """Translate the selected sites."""
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"
        maker = (atom_commands.MoveSites.by_cartesian_delta if cartesian
                 else atom_commands.MoveSites.by_delta)
        self.run(maker(self._structure, sites, delta))
        return f"moved {len(sites)} site(s)"

    def rotate_selection(self, axis, angle_degrees: float,
                         centre=None) -> str:
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"
        self.run(atom_commands.TransformSites.rotation(
            sites, axis, angle_degrees, centre))
        return f"rotated {len(sites)} site(s) by {angle_degrees:g}"

    def mirror_selection(self, normal, centre=None) -> str:
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"
        self.run(atom_commands.TransformSites.mirror(sites, normal,
                                                     centre))
        return f"mirrored {len(sites)} site(s)"

    def planarize_selection(self) -> str:
        """Flatten the selected sites onto their best-fit plane.

        Says how far the furthest atom had to move, because that is the
        whole of the difference between straightening a ring that was
        nearly flat and quietly rebuilding one that was not.
        """
        sites = sorted(self.selected_sites())
        if len(sites) < 3:
            return "a plane needs at least three atoms"
        command = atom_commands.PlanarizeSites(sites)
        self.run(command)
        return (f"planarised {len(sites)} site(s), moved by up to "
                f"{command.displacement:.3f} A")

    def recompute_bonds(self) -> str:
        """Perceive the bonds again, over the geometry as it now is.

        Perception does not follow atoms as they move -- see
        :data:`xtal.core.structure.CHEMISTRY` -- so a bond does not
        appear because two atoms drifted together, or vanish because
        one was dragged away.  It changes when it is asked to, which is
        here.

        The graph is stored on the structure and saved with the
        project, so replacing it is a change like any other and goes on
        the undo stack -- including when the bonds come back the same,
        because their lengths did not.
        """
        before = {b.key() for b in bonding.perceive(self._structure)}
        self.run(bond_commands.RecomputeBonds())
        after = {b.key() for b in bonding.perceive(self._structure)}

        added, removed = len(after - before), len(before - after)
        if not added and not removed:
            return f"bonds recalculated, unchanged: {len(after)} bonds"
        # The difference, not the total: a recalculation that swapped
        # one bond for another has the same count as one that did
        # nothing, and they are not the same event.
        return (f"bonds recalculated: {added} added, {removed} removed "
                f"-- {len(after)} bonds")

    def add_bond_between(self, atom_a: int, atom_b: int,
                         image_a=(0, 0, 0), image_b=(0, 0, 0)) -> str:
        """Bond two atoms of the P1 cell, as picked in the viewport.

        The images are the lattice translations the two atoms were
        drawn at: in a multi-cell view the same P1 atom appears many
        times, and which copy was clicked decides which bond is meant.
        """
        command = bond_commands.AddBond.between_atoms(
            self._structure, self.cell, atom_a, atom_b,
            image_a, image_b)
        self.run(command)
        return "bond added"

    def remove_bond_between(self, atom_a: int, atom_b: int,
                            image_a=(0, 0, 0),
                            image_b=(0, 0, 0)) -> str:
        command = bond_commands.SuppressBond.between_atoms(
            self._structure, self.cell, atom_a, atom_b,
            image_a, image_b)
        self.run(command)
        return "bond removed"

    def add_topology_bond_between(self, atom_a: int, atom_b: int,
                                  image_a=(0, 0, 0),
                                  image_b=(0, 0, 0)) -> str:
        """Draw an edge of the underlying net between two drawn atoms.

        It expands over the symmetry orbit like every other bond, which
        is what makes drawing one edge of a **pcu** net draw all six.
        """
        self.run(bond_commands.AddTopologyBond.between_atoms(
            self._structure, self.cell, atom_a, atom_b,
            image_a, image_b))
        edges = len(bonding.topology_graph(self._structure).bonds)
        return f"net edge drawn -- {edges} in the cell"

    def select_topology(self, key, mode: str = "set") -> None:
        if mode == "set":
            self.selection.topology = {key}
        else:
            self.selection.toggle_topology(key)
        self.selectionChanged.emit()

    def delete_selected_topology(self) -> str:
        """Remove every selected net edge, as one undo step.

        A plain removal rather than a suppression: nothing perceives a
        topology bond, so nothing will put it back.
        """
        keys = sorted(self.selection.topology)
        if not keys:
            return "no net edges are selected"
        before = len(bonding.topology_graph(self._structure).bonds)
        with self.transaction(f"Delete {len(keys)} net edge(s)"):
            for i, j, image in keys:
                self.run(
                    bond_commands.RemoveTopologyBond.between_atoms(
                        self._structure, self.cell, int(i), int(j),
                        (0, 0, 0), tuple(int(v) for v in image)))
        gone = before - len(bonding.topology_graph(self._structure).bonds)
        self.selection.topology.clear()
        self.selectionChanged.emit()
        return f"removed {gone} net edge(s)"

    def net_report(self, atom: int | None = None) -> str:
        """What the net drawn on this structure actually is.

        The coordination sequence and the point symbol are how RCSR
        names a net, and they are the reason for drawing one rather
        than printing it: **pcu** is 6, 18, 38, 66 and 4^12.6^3, and
        nothing else is.
        """
        net = bonding.topology_graph(self._structure)
        if not net.bonds:
            return "no net has been drawn"
        vertices = [i for i in range(net.n_atoms)
                    if net.neighbors(i)]
        if atom is None:
            atom = (self.selection.focus if
                    self.selection.focus in vertices else vertices[0])
        sequence = bonding.coordination_sequence(net, atom, depth=5)
        symbol = bonding.point_symbol(net, atom)
        cell = self.cell
        label = cell.labels[atom] or cell.elements[atom]
        return (f"{label}: {len(net.neighbors(atom))}-coordinated, "
                f"coordination sequence "
                f"{', '.join(str(n) for n in sequence)}, "
                f"point symbol {symbol}")

    def delete_selected_bonds(self) -> str:
        """Suppress every selected bond, as one undo step.

        Reported in orbit terms, because that is what happens: a bond
        is stored against the asymmetric unit, so suppressing one
        suppresses every bond the symmetry says is the same bond.
        "removed 4 Ti-O bonds" is the honest message where "bond
        removed" is not.
        """
        keys = sorted(self.selection.bonds)
        if not keys:
            return "no bonds are selected"
        before = len(self.graph.bonds)
        with self.transaction(f"Delete {len(keys)} bond(s)"):
            for i, j, image in keys:
                self.run(bond_commands.SuppressBond.between_atoms(
                    self._structure, self.cell, int(i), int(j),
                    (0, 0, 0), tuple(int(v) for v in image)))
        gone = before - len(self.graph.bonds)
        self.selection.bonds.clear()
        self.selectionChanged.emit()
        if gone == len(keys):
            return f"removed {gone} bond(s)"
        return (f"removed {gone} bonds -- {len(keys)} were selected, "
                f"and symmetry carried it to the rest of the orbit")

    def replace_structure(self, structure: Structure, label: str,
                          change: Change = Change.ALL) -> str:
        """Undoable wholesale replacement (P1, supercell, symmetry)."""
        self.run(ReplaceStructure(structure, label, change))
        return label

    # ==================================================================
    #  SYMMETRY AND CELL
    # ==================================================================
    #
    # Every one of these is a StructureOperation, which means the
    # dialog above it can ask what would happen -- how many atoms, what
    # group, what warnings -- before anything is committed, and then
    # commit the very same result.

    def operate(self, command):
        """Run a symmetry or cell operation and hand back its report.

        A failed operation (``report.ok`` false) is not pushed: there
        is nothing to undo, and leaving a no-op on the stack would make
        Ctrl+Z lie.
        """
        _new, report = command.preview(self._structure)
        if report is not None and not report.ok:
            return report
        self.run(command)
        return command.report

    def detect_symmetry(self, symprec: float = 1e-5):
        """What group these coordinates have at this tolerance.

        Read-only, so the Find Symmetry dialog can follow the spinbox
        without touching the structure.
        """
        from xtal.core.symmetry import detect
        return detect(self._structure, symprec)

    def reduce_to_p1(self) -> str:
        return self.operate(symmetry_commands.ReduceToP1()).message

    def find_symmetry(self, symprec: float = 1e-5,
                      standardize_cell: bool = False):
        return self.operate(symmetry_commands.FindSymmetry(
            symprec, standardize_cell))

    def set_space_group(self, group, mode: str = "reinterpret"):
        return self.operate(symmetry_commands.SetSpaceGroup(
            group, mode))

    def standardize_cell(self, symprec: float = 1e-5,
                         to_primitive: bool = False,
                         idealize: bool = True):
        return self.operate(symmetry_commands.Standardize(
            symprec, to_primitive, idealize))

    def assign_wyckoff(self, symprec: float = 1e-5):
        return self.operate(symmetry_commands.AssignWyckoff(symprec))

    def merge_duplicates(self, tol: float = 0.05):
        return self.operate(symmetry_commands.MergeDuplicates(tol))

    def invert_structure(self):
        """Swap the hand of the structure, group included."""
        return self.operate(symmetry_commands.Invert())

    def preview_inversion(self):
        """What inverting would do, without doing it.  The dialog says
        so before the user commits, because for a centrosymmetric group
        the answer is 'nothing'."""
        _new, report = symmetry_commands.Invert().preview(
            self._structure)
        return report

    def hand(self) -> str:
        """Which hand this structure's group is, in one line."""
        from xtal.core.symmetry import hand_description
        return hand_description(self._structure.space_group)

    def subgroups(self):
        """The translationengleiche subgroups of the current group, one
        per conjugacy class.  Cached on the group, so a dialog may ask
        freely."""
        from xtal.core import subgroups
        return subgroups.subgroups_of(self._structure.space_group)

    def maximal_subgroups(self):
        """Only the one-step descents."""
        from xtal.core import subgroups
        return subgroups.maximal_subgroups(self._structure.space_group)

    def subgroup_split(self, subgroup):
        """What descending to ``subgroup`` would do to the sites."""
        from xtal.core import subgroups
        return subgroups.describe_split(self._structure, subgroup)

    def descend_to_subgroup(self, subgroup):
        return self.operate(
            symmetry_commands.DescendToSubgroup(subgroup))

    def make_supercell(self, na: int, nb: int, nc: int):
        return self.operate(cell_commands.Supercell(na, nb, nc))

    def transform_cell(self, p_matrix):
        return self.operate(cell_commands.TransformCell(p_matrix))

    def reduce_cell(self, kind: str = "niggli"):
        return self.operate(cell_commands.ReduceCell(kind))

    def shift_origin(self, shift):
        return self.operate(cell_commands.ShiftOrigin(shift))

    def wrap_into_cell(self):
        return self.operate(cell_commands.WrapIntoCell())

    def set_lattice(self, lattice, keep: str = "fractional") -> str:
        """Change the cell parameters, keeping either the fractional or
        the cartesian coordinates -- never both, and never a guess."""
        self.run(cell_commands.SetLattice(lattice, keep))
        a, b, c, al, be, ga = lattice.parameters
        return (f"cell {a:.4f} {b:.4f} {c:.4f} "
                f"{al:.3f} {be:.3f} {ga:.3f} ({keep} kept)")

    # ==================================================================
    #  FORCE FIELD
    # ==================================================================
    #
    # The document owns none of the physics -- it builds calculators
    # over its structure and turns their answers into commands, and
    # every one of these is callable with no window, which is what
    # keeps the Force Field panel a set of widgets and nothing more.

    def atom_types(self):
        """The force field's reading of every atom, with reasons.

        Memoised on the structure, so the panel may call it whenever it
        redraws.
        """
        from xtal.ff.uff import typer
        return typer.assign(self._structure)

    def site_types(self) -> list:
        """One ``(site index, AtomType, multiplicity)`` per site.

        The table shows sites rather than cell atoms because an
        override is stored on a site and applies to its whole orbit --
        a per-atom table would offer edits it could not honour.
        """
        typing = self.atom_types()
        cell = self.cell
        out = []
        for index in range(self._structure.n_sites):
            atoms = cell.indices_of_site(index)
            if not len(atoms):
                continue
            out.append((index, typing.types[int(atoms[0])],
                        len(atoms)))
        return out

    def plan_hydrogens(self, xray: bool = False):
        """Where the missing hydrogens would go, changing nothing.

        Read-only, so the dialog can show the count -- and every
        assumption behind it -- while the user is still deciding.
        """
        from xtal.commands.ff import AddHydrogens
        return AddHydrogens(xray=xray).preview(self._structure)

    def add_hydrogens(self, xray: bool = False) -> str:
        """Complete every main-group coordination with hydrogens.

        One command for the lot, so Ctrl+Z takes all of them back
        together.  A plan that would add nothing is not pushed: there
        would be nothing to undo, and an empty entry on the stack makes
        Ctrl+Z lie.
        """
        from xtal.commands.ff import AddHydrogens
        command = AddHydrogens(xray=xray)
        plan = command.preview(self._structure)
        if not plan:
            return plan.message()
        self.run(command)
        return plan.message()

    def force_field(self, engine: str = "uff", **options):
        """Build a calculator over this structure."""
        from xtal.ff import ENGINES
        return ENGINES.build(engine, self._structure, **options)

    def single_point(self, engine: str = "uff", **options):
        """``(result, calculator)`` at the current geometry."""
        calculator = self.force_field(engine, **options)
        result = calculator.compute(self.cell.cart,
                                    self._structure.lattice.matrix)
        return result, calculator

    def set_atom_type(self, site_indices, type_name) -> str:
        """Override -- or, with ``None``, stop overriding -- the type
        of some sites."""
        from xtal.commands import ff as ff_commands
        indices = sorted({int(i) for i in site_indices})
        if not indices:
            return "no sites"
        self.run(ff_commands.SetAtomTypes(indices, type_name))
        return (f"set {len(indices)} site(s) to {type_name}"
                if type_name else
                f"cleared the type of {len(indices)} site(s)")

    def frozen_sites(self) -> set:
        """The sites the selection says to hold still."""
        return self.selected_sites()

    def preview_positions(self, frac) -> None:
        """Show a geometry without committing to it.

        The optimiser produces two hundred of these and only the last
        one is a change the user made; putting each on the undo stack
        would bury everything before it, and marking the document
        modified at step one would be a lie about a run that can still
        be cancelled.  So this moves the atoms and tells the viewport,
        and touches neither the history nor the modified flag.

        **It announces itself on its own signal**, and that is the
        point of it.  ``structureChanged`` reaches every panel in the
        window -- the site table, the formula, the force field's type
        table -- and none of them are showing anything a preview
        changed.  Two hundred previews down that signal cost more time
        than the optimisation they were previewing.  ``previewChanged``
        reaches the viewport, which is the only thing that has
        something new to draw.
        """
        for site, coordinates in zip(self._structure.sites, frac,
                                     strict=True):
            site.frac = np.array(coordinates, dtype=float)
        self._structure.touch(Change.POSITIONS)
        self._remeasure()
        self.previewChanged.emit()

    def apply_optimization(self, result, before=None) -> str:
        """Commit an optimisation as one undoable step.

        ``before`` is where the atoms were when the run started, which
        the caller has to supply if it has been previewing: by then the
        structure holds the last previewed geometry, and a command that
        read its undo data from the structure would undo to that
        instead of to where the user began.
        """
        from xtal.commands import ff as ff_commands
        command = ff_commands.ApplyOptimizedGeometry(
            result.frac, before=before,
            matrix=getattr(result, "matrix", None))
        moved = command.displacement(self._structure)
        if moved < 1e-9:
            # A run cancelled before it took a step, or one that
            # started at the minimum.  Pushing this would put an entry
            # on the stack that undoes to itself, and Ctrl+Z would
            # appear to do nothing.
            return f"{result.summary()}; nothing moved"
        self.run(command)
        return (f"{result.summary()}; the furthest atom moved "
                f"{moved:.3f} A")

    def apply_charges(self, charges) -> str:
        from xtal.commands import ff as ff_commands
        self.run(ff_commands.SetCharges(charges))
        return f"set charges on {len(charges)} site(s)"

    # ==================================================================
    #  MEASUREMENTS
    # ==================================================================
    #
    # A measurement is a note about the crystal, not a change to it, so
    # none of this is undoable.  It does have to follow the crystal
    # though: move an atom and the number must change, delete one and
    # the measurement has to go.

    def add_measurement(self, atoms, kind=None) -> str:
        """Measure between 2, 3 or 4 atoms of the P1 cell."""
        result = measure.measure(self.cell, self._structure.lattice,
                                 atoms)
        if kind is not None and result.kind != kind:
            raise ValueError(
                f"a {kind} needs a different number of atoms")
        self.measurements.append(result)
        self.measurementsChanged.emit()
        return result.text()

    def remove_measurement(self, index: int) -> None:
        if 0 <= index < len(self.measurements):
            del self.measurements[index]
            self.measurementsChanged.emit()

    def clear_measurements(self) -> None:
        if self.measurements:
            self.measurements = []
            self.measurementsChanged.emit()

    def _remeasure(self) -> None:
        """Recompute every measurement after the atoms moved."""
        if not self.measurements:
            return
        cell, lattice = self.cell, self._structure.lattice
        self.measurements = [
            measure.measure(cell, lattice, m.atoms)
            for m in self.measurements
            if max(m.atoms) < cell.n_atoms]
        self.measurementsChanged.emit()

    def _prune_measurements(self) -> None:
        """Drop the measurements whose atoms no longer exist."""
        keep = [m for m in self.measurements
                if max(m.atoms) < self.cell.n_atoms]
        if len(keep) != len(self.measurements):
            self.measurements = keep
            self.measurementsChanged.emit()
            return
        self._remeasure()

    # ==================================================================
    #  CLIPBOARD
    # ==================================================================

    def copy_selection(self) -> Fragment:
        """Lift the selection out as a cell-free fragment."""
        return Fragment.from_selection(
            self._structure, self.cell, self.selection.atoms,
            self.graph)

    def cut_selection(self) -> Fragment:
        fragment = self.copy_selection()
        if not fragment.is_empty:
            with self.transaction("Cut"):
                self.delete_selection()
        return fragment

    def paste(self, fragment: Fragment, offset=None) -> str:
        """Add a fragment; returns what it did, symmetry included."""
        if fragment.is_empty:
            return "nothing to paste"
        command = PasteFragment(fragment, offset)
        message = command.describe(self._structure)
        self.run(command)
        self.select(_atoms_of_sites(self.cell, command.indices))
        return message

    def duplicate_selection(self, offset=None) -> str:
        fragment = self.copy_selection()
        if fragment.is_empty:
            return "nothing selected"
        if offset is None:
            offset = self._structure.lattice.to_cart(
                self.cell.frac[sorted(self.selection.atoms)]
            ).mean(axis=0) + np.array([1.0, 0.0, 0.0])
        return self.paste(fragment, offset)

    # ==================================================================
    #  VIEW AND STATE
    # ==================================================================

    def update_view(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if not hasattr(self.view, key):
                raise AttributeError(f"no view setting {key!r}")
            setattr(self.view, key, value)
        self.viewChanged.emit()

    def set_cells(self, na: int, nb: int, nc: int) -> None:
        self.view.set_cells(na, nb, nc)
        self.viewChanged.emit()

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def modified(self) -> bool:
        return not self.stack.is_clean

    @property
    def title(self) -> str:
        if self._path is not None:
            name = self._path.name
        else:
            name = str(self._structure.meta.get("title") or "Untitled")
        return f"{name}*" if self.modified else name

    def info(self):
        return properties.info(self._structure)

    def status_text(self) -> str:
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


class _Transaction:
    """Context manager grouping commands into one undo step."""

    def __init__(self, document: Document, label: str):
        self.document = document
        self.label = label
        self._context = None

    def __enter__(self):
        self._context = self.document.stack.transaction(
            self.label, self.document)
        return self._context.__enter__()

    def __exit__(self, *exc):
        result = self._context.__exit__(*exc)
        self.document.historyChanged.emit()
        return result


def _atoms_of_sites(cell, site_indices) -> set:
    atoms = set()
    for index in site_indices:
        atoms |= {int(k) for k in cell.indices_of_site(index)}
    return atoms
