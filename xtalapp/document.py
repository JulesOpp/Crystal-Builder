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

from contextlib import nullcontext
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from xtal import Structure
from xtal.analysis import overlays, porosity, rcsr, topology
from xtal.build import fill
from xtal.commands import CommandStack, ReplaceStructure, SnapshotEdit
from xtal.commands import atoms as atom_commands
from xtal.commands import bonds as bond_commands
from xtal.commands import cell as cell_commands
from xtal.commands import connections as connection_commands
from xtal.commands import interpenetrate as interpenetrate_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.commands.base import Command
from xtal.commands.clipboard import (
    Fragment,
    InsertMolecules,
    PasteFragment,
)
from xtal.core import bonding, measure, p1, properties, symmetry
from xtal.core import selection as sel
from xtal.core.selection import Selection
from xtal.core.structure import CHEMISTRY, TOPOLOGY, Change
from xtal.io import (
    FORMATS,
    for_export,
    is_project,
    read_project,
    write_project,
)
from xtal.io.project import EXTENSION as PROJECT_EXTENSION
from xtal.workspace import Workspace
from xtalapp import playback
from xtalapp.busy import busy
from xtalapp.viewport.view_settings import ViewSettings


class PlaybackActive(RuntimeError):
    """An edit was attempted while a trajectory was being played."""


def _busy_unless_gesture(command):
    """The wait cursor for a command, unless it is one of a gesture's.

    A command that merges with the next is one that arrives several
    times a second -- a drag, a spinbox held down -- and a cursor that
    flickers to *wait* at every step of a drag is worse than none.
    Everything else is a click, and some clicks take seconds.
    """
    if type(command).merge_with is not Command.merge_with:
        return nullcontext()
    return busy()


class Document(QObject):
    """One open structure, its view state, and its history."""

    structureChanged = Signal(int)      # a Change flag
    previewChanged = Signal()           # a geometry shown, not committed
    selectionChanged = Signal()
    measurementsChanged = Signal()
    planesChanged = Signal()            # a plane defined or dropped
    poresChanged = Signal()             # a pore network drawn or dropped
    overlayChanged = Signal()           # charges or an orbital, likewise
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
        # The planes the user has defined, in the order they defined
        # them.  Like measurements they are notes rather than edits --
        # nothing here is undoable -- but unlike a measurement a plane
        # is a thing other measurements are taken *between*, so it is
        # kept in its own list and named.
        self.planes: list = []
        # The pore network a porosity run came back with, or None.
        # Neither structure nor note: it is a *measurement of* the
        # crystal made by an external program, so it is not undoable,
        # does not mark the document modified, and is thrown away the
        # moment the crystal it describes is replaced.
        self.pores = None
        # The other two things a run can draw over the crystal -- see
        # `xtal.analysis.overlays` -- under the same rules as the pores.
        self.charges = None
        self.orbital = None
        # Which rows of that list the picture draws, or () for all of
        # them.  View state and not a note: it follows what is
        # selected in the Planes list, it is not written into the
        # project, and "none chosen means all of them" is the same
        # convention ``measure_plane_angles`` already works to.
        self.shown_planes: tuple = ()
        # Whether ``view`` came out of a saved project.  A project
        # carries the view it was saved with and the preference for
        # what a *new* document looks like must not overwrite it --
        # the same rule the default bond rules follow, and the reason
        # it has to be a flag is that a project whose style happens to
        # equal the built-in one is indistinguishable from a fresh
        # document by looking at the values.
        self.view_is_saved = False
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
            document.view_is_saved = True
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

    def adopt(self, path) -> None:
        """Point this document at the file it now lives in.

        A structure opened from outside is *copied* into the workspace
        and the tab has to follow the copy: the original belongs to
        whoever the user got it from, and editing it in place is not
        what opening it here meant.  Where it came from is kept in
        ``structure.meta["source"]``, and that is what still names
        this document if the same file is opened again.

        Not :meth:`save` -- nothing has been written and nothing is
        clean.  Only the file this document *is* has changed.
        """
        path = Path(path)
        if self._path == path:
            return
        self._path = path
        self.titleChanged.emit(self.title)

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
            "planes": [p.to_dict() for p in self.planes],
            **({"pores": self.pores.to_dict()}
               if self.pores is not None else {}),
            **({"charges": self.charges.to_dict()}
               if self.charges is not None else {}),
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
        for record in session.get("planes", []):
            try:
                atoms = [int(a) for a in record["atoms"]]
                if atoms and max(atoms) < cell.n_atoms:
                    color = record.get("color")
                    self.planes.append(measure.plane(
                        cell, self._structure.lattice, atoms,
                        name=record.get("name", ""),
                        color=None if color is None else tuple(color)))
            except (KeyError, TypeError, ValueError):
                continue
        for record in session.get("measurements", []):
            try:
                saved = measure.Measurement.from_dict(record)
                if max(saved.atoms) < cell.n_atoms:
                    self.measurements.append(self._recomputed(
                        saved, cell, self._structure.lattice))
            except (KeyError, TypeError, ValueError):
                continue
        # The pore network needs no check against the structure: it is
        # stored in fractional coordinates of the cell it was measured
        # in, and it names no atoms, so nothing in it can point at one
        # that has gone.
        if session.get("pores"):
            try:
                self.pores = porosity.PoreNetwork.from_dict(
                    session["pores"])
            except (KeyError, TypeError, ValueError):
                self.pores = None
        if session.get("charges"):
            charges = overlays.AtomCharges.from_dict(session["charges"])
            # A charge per atom of a cell that no longer has that many
            # atoms is a charge on somebody else's atom.
            self.charges = (charges if charges.n_atoms == self.cell.n_atoms
                            else None)

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

    def recover(self, path) -> str:
        """Put an autosave's edits back, as **one undo step**.

        The structure comes back through :meth:`replace_structure`, so
        Ctrl+Z returns to the file as it was saved and the document is
        modified -- which it is: the file does not have these edits.
        The bonds are the project's own, so nothing is perceived.  The
        view, the measurements and the planes come back the way a
        project brings them on open; they were never on the undo stack
        and are not put there now.
        """
        structure, view, session = read_project(Path(path))
        label = self.replace_structure(structure,
                                       "Restore unsaved changes")
        self.view = ViewSettings.from_dict(view)
        self.view_is_saved = True
        self.selection.clear()
        self.measurements = []
        self.planes = []
        self._restore_session(session)
        self.viewChanged.emit()
        self.selectionChanged.emit()
        self.measurementsChanged.emit()
        self.planesChanged.emit()
        return label

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
        """What an export would write.

        Cleaned, which is the other half of the workspace keeping
        everything in the CIF: the file this document *is* carries the
        markers the user placed and the net drawn over a framework,
        and the file somebody else opens carries neither.  See
        :func:`xtal.io.export.for_export` for why each goes.
        """
        if not selection_only:
            return for_export(self._structure)
        return for_export(sel.substructure(
            self._structure, self.cell, self.selection.atoms))

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
        self.planes = []
        self.shown_planes = ()
        self.pores = None
        self.charges = None
        self.orbital = None
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
        with _busy_unless_gesture(command):
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
        with busy():
            command = self.stack.undo(self)
            if command is None:
                return ""
            self._after_change(command.change)
        return command.label

    def redo(self) -> str:
        with busy():
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
            # A move can change how many atoms the cell holds all the
            # same: an atom taken off a special position splits its
            # orbit, and one moved onto one merges it.  The selection
            # then names atoms that are no longer there, and would
            # light up whichever atoms inherited their indices.
            n_atoms = self.cell.n_atoms
            if self.selection.names_beyond(n_atoms):
                self.selection.prune(n_atoms)
                self.selectionChanged.emit()
            self._remeasure()
        self._stale_pores(change)
        self._announce_modified()
        self.structureChanged.emit(int(change))
        self.historyChanged.emit()

    def _stale_pores(self, change: Change) -> None:
        """Drop the pore network when the crystal it measured changes.

        Not pruned and not refitted, because there is nothing to fit
        it to: unlike a plane, which is defined by atoms and can be
        put back through them, this is a Voronoi decomposition of a
        particular arrangement of a particular set of atoms.  Move one
        and it is a picture of where the channels *were* -- which is
        the worst kind of wrong, because it still looks like an
        answer.  Zeo++ is a second away; guessing is not.

        A change that is only how the crystal is *drawn* or *named*
        leaves it alone, which is why this reads the flags rather than
        dropping on every signal.
        """
        if not change & (CHEMISTRY | Change.POSITIONS):
            return
        if self.pores is not None:
            self.pores = None
            self.poresChanged.emit()
        if self.charges is not None or self.orbital is not None:
            self.charges = self.orbital = None
            self.overlayChanged.emit()

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

    def select(self, atoms, mode: str = "set",
               with_bonds: bool = False) -> None:
        """Select atoms, and optionally the bonds between them.

        ``with_bonds`` takes every bond whose *both* ends are in the
        selection -- the only bonds a selection of atoms can be said to
        contain.

        It is set by the commands that name a *region*: Select All, the
        box, Invert, and the three Grow commands.  A region contains
        the bonds inside it, which is what makes "select the linker,
        set the bond type" one gesture instead of eleven clicks.  The
        commands that name *atoms* -- a click, Select same element, a
        row in a table -- leave the bonds alone, because there the user
        is talking about atoms and a bond that quietly joined the
        selection would be edited by the next command without ever
        having been asked for.
        """
        atoms = [int(a) for a in atoms]
        if mode == "set":
            # "Set" replaces the whole selection and not merely the
            # atoms in it.  A bond or a net edge left behind by the
            # previous click is what the *next* command acts on --
            # Delete looks at the net first and the bonds second, so a
            # stale edge means Del takes the edge the user stopped
            # pointing at three clicks ago.  ``with_bonds`` below
            # decides what a region brings with it; it does not decide
            # whether the last selection survives this one.
            self.selection.bonds.clear()
            self.selection.topology.clear()
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
        if with_bonds:
            self._take_the_bonds_between(mode)
        self.selectionChanged.emit()

    def _take_the_bonds_between(self, mode: str = "set") -> None:
        """Bring the selected bonds into line with the selected atoms.

        A bond with one end outside the selection is not in it, which
        is what each of these three says in its own way: replacing the
        selection replaces its bonds, adding to it keeps whatever was
        already held, and removing atoms drops the bonds that are now
        only half held.  Without the last one a bond stays selected
        long after the atom it hangs off has gone, and the next Set
        Bond Type quietly acts on it.
        """
        inside = sel.bonds_within(self.graph, self.selection.atoms)
        if mode == "add":
            self.selection.bonds |= inside
        elif mode == "remove":
            self.selection.bonds &= inside
        else:
            self.selection.bonds = inside

    def select_bond(self, key, mode: str = "set") -> None:
        """Select one bond, replacing the selection or adding to it.

        Clicking a bond and pressing Del must delete *that bond*, and
        it did not: ``delete_selection`` acts on the atoms when there
        are any, so an atom left selected from the click before meant
        Del deleted the atom -- and its whole symmetry orbit with it,
        which is why it looked like atoms at random around the cell.
        """
        if mode == "set":
            self.selection.set_atoms(())
            self.selection.topology.clear()
            self.selection.bonds = {key}
        else:
            self.selection.toggle_bond(key)
        self.selectionChanged.emit()

    def select_none(self) -> None:
        self.selection.clear()
        self.selectionChanged.emit()

    def select_all(self) -> None:
        """Everything: the atoms, and the bonds between them.

        Not the net edges.  A topology bond is a statement about which
        parts of a framework are nodes rather than a bond, and Delete
        acts on the net before it acts on anything else -- so taking
        the edges here would make Select All followed by Delete take
        the net apart instead of the crystal.
        """
        self.selection.set_atoms(range(self.cell.n_atoms))
        self.selection.bonds = {b.key() for b in self.graph.bonds}
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
        # The bonds are re-derived rather than inverted: they follow
        # the atoms, so the inverse of "everything" is nothing at all
        # and not "no atoms, every bond".
        self._take_the_bonds_between()
        self.selectionChanged.emit()

    def select_element(self, symbol: str, mode: str = "set") -> None:
        self.select(sel.by_element(self.cell, symbol), mode)

    def select_site(self, site_index: int, mode: str = "set") -> None:
        self.select(sel.by_site(self.cell, site_index), mode)

    def select_bonds_between(self, first: str,
                             second: str | None = None) -> str:
        """Select every bond joining two elements, and nothing else.

        The atoms are let go on purpose.  Delete acts on the sites
        whenever any atom is held, so a selection of Zn-O bonds that
        kept the atoms it was chosen from would delete the zinc; with
        bonds alone, Delete and Bond type act on exactly these.
        ``second`` of ``None`` is every bond ``first`` makes.
        """
        keys = sel.bonds_between_elements(self.graph, self.cell,
                                          first, second)
        self.selection.set_atoms(())
        self.selection.topology.clear()
        self.selection.bonds = keys
        self.selectionChanged.emit()
        name = f"{first}-{second}" if second else f"{first}-any"
        if not keys:
            return f"no {name} bonds"
        return f"selected {len(keys)} {name} bond(s)"

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
        self.select(atoms, "set", with_bonds=True)

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
        """Place one atom where the user said, and bond it to nothing.

        Perception is not run over it: bonds change when the user asks
        them to, and an atom appearing already bonded to whatever it
        happens to be near is that rule being broken by the one
        operation nobody would expect to break it.  *Recalculate
        bonds* is how the new atom joins the graph.
        """
        site = atom_commands.new_site(element, frac, occupancy, label)
        self.run(atom_commands.AddSites([site], perceive=False))
        return f"added {element}"

    def add_bonded_atom(self, element: str, frac, anchor: int,
                        anchor_image=(0, 0, 0),
                        label: str = "") -> tuple[str, tuple]:
        """Add an atom bonded to one that is already in the cell.

        What a click on an existing atom in Add-atom mode means: the
        user has said what the new atom is bonded to, so the bond is
        created with it, explicitly, in the same undo step.

        Returns the message *and* where the atom landed, as ``(P1
        atom, translation)``.  The caller cannot work the second out
        for itself -- the site is wrapped into the cell and its orbit
        generated -- and the gesture that placed it carries on from
        it.
        """
        name = self.cell.labels[anchor] or self.cell.elements[anchor]
        site = atom_commands.new_site(element, frac, label=label)
        command = self.run(
            atom_commands.AddBondedSite(site, anchor, anchor_image))
        return f"added {element}, bonded to {name}", command.placed

    def add_centroid(self, element: str = "X", label: str = "") -> str:
        """Put an atom at the middle of the selected atoms.

        A **dummy atom** by default, because that is what a centroid
        usually is: a position somebody wants named -- the centre of a
        ring, the vertex of a net -- rather than a piece of chemistry.
        A dummy bonds to nothing by perception (see
        ``bonding.DUMMY_ELEMENTS``), and net edges and measurements
        take it like any other atom, which is what it is for.  Naming
        a real element instead builds with it, and that is a different
        thing the same gesture does.

        The new atom is left selected: a centroid lands inside the
        ring it was taken from, where an unhighlighted new atom is
        genuinely hard to find.
        """
        atoms = sorted(self.selection.atoms)
        if len(atoms) < 2:
            return "select at least two atoms to put a centroid between"
        point = measure.centroid(self.cell, self._structure.lattice,
                                 atoms)
        frac = self._structure.lattice.to_frac(point)
        site = atom_commands.new_site(element, frac, label=label)
        self.run(atom_commands.AddSites([site], label="Add centroid",
                                        perceive=False))
        placed = self._structure.n_sites - 1
        self.select(self.cell.indices_of_site(placed).tolist())
        return (f"centroid of {len(atoms)} atoms added as "
                f"{self._structure.sites[placed].label}")

    def merge_atoms(self) -> str:
        """Replace the selected atoms with one at their middle.

        What two half-occupied positions of a disordered atom, or a
        cluster somebody wants reduced to a node, are collapsed into.
        The merged atom keeps the element when every atom going into it
        shares one, and is a dummy otherwise: a carbon and an oxygen
        averaged are not either of them, and guessing would quietly
        change what the crystal means.

        One undo step, and the add goes first.  A site appended last
        renumbers nothing, so the delete that follows still names the
        sites it was asked to; the other way round, the centroid would
        have to be measured over atoms that are already gone.  Like
        Delete it removes whole orbits, and like Add centroid the new
        atom is bonded to nothing and left selected.
        """
        atoms = sorted(self.selection.atoms)
        if len(atoms) < 2:
            return "select at least two atoms to merge"
        symbols = {self.cell.elements[a] for a in atoms}
        element = symbols.pop() if len(symbols) == 1 else "X"
        point = measure.centroid(self.cell, self._structure.lattice,
                                 atoms)
        frac = self._structure.lattice.to_frac(point)
        sites = sorted(self.selected_sites())
        with self.transaction("Merge atoms"):
            self.run(atom_commands.AddSites(
                [atom_commands.new_site(element, frac)],
                label="Merge atoms", perceive=False))
            self.run(atom_commands.DeleteSites(sites))
        placed = self._structure.n_sites - 1
        self.select(self.cell.indices_of_site(placed).tolist())
        return (f"merged {len(atoms)} atoms into "
                f"{self._structure.sites[placed].label}")

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

    def mark_connection_points(self) -> str:
        """Turn the selected atoms into a building block's connection
        points -- see :mod:`xtal.commands.connections`, including why
        there is no way back except Ctrl+Z.

        Planned before it is run so that a selection nothing in which
        can be marked is a sentence in the status bar rather than an
        undo step that changed nothing.
        """
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"
        planned = connection_commands.plan(self._structure, sites)
        if not planned[0]:
            return "; ".join(planned[2]) or "nothing to mark"
        command = connection_commands.MarkConnectionPoints(
            sites, plan_for=planned)
        self.run(command)
        return command.summary()

    def mark_one_connection_point(self) -> str:
        """Collapse the selected atoms into a single connection point.

        The gesture for a chelate: two atoms that meet the next block
        together are one joint, and marking them separately gives a
        block with twice the coordination number it has.  See
        :class:`~xtal.commands.connections.MarkOneConnectionPoint`,
        including why there is still no way back except Ctrl+Z.

        Planned before it is run, like Mark connection points, so a
        selection nothing can be done with is a sentence in the status
        bar rather than an undo step that changed nothing.
        """
        atoms = sorted(self.selection.atoms)
        if len(atoms) < 2:
            return "select at least two atoms"
        planned = connection_commands.plan_one(self._structure, atoms)
        if planned[0] is None:
            return "; ".join(planned[2]) or "nothing to mark"
        command = connection_commands.MarkOneConnectionPoint(
            atoms, sorted(self.selected_sites()), plan_for=planned)
        self.run(command)
        # Left selected, like Merge atoms and Add centroid: the atom
        # that was just made is the one the next gesture is about.
        self.select(self.cell.indices_of_site(command.placed).tolist())
        return command.summary()

    def move_selection(self, delta, cartesian: bool = False) -> str:
        """Translate the selected sites."""
        sites = sorted(self.selected_sites())
        if not sites:
            return "nothing selected"
        maker = (atom_commands.MoveSites.by_cartesian_delta if cartesian
                 else atom_commands.MoveSites.by_delta)
        self.run(maker(self._structure, sites, delta))
        return f"moved {len(sites)} site(s)"

    def drag_selection(self, delta) -> str:
        """Move the selection by a cartesian delta, as the *drawn*
        atoms see it.

        What a drag means: the copy under the cursor follows the
        cursor, and its symmetry mates follow the operation that made
        them.  :meth:`move_selection` displaces the parent sites
        instead, which is right for a number typed into the Move dock
        and wrong for a hand on an atom -- see
        :meth:`~xtal.commands.atoms.MoveSites.by_image_delta`.

        Nothing here touches the bonding: a moved atom keeps the bonds
        it had, whatever the new distances say, until Recalculate
        Bonds is asked for.
        """
        atoms = sorted(self.selection.atoms)
        if not atoms:
            return "nothing selected"
        command = atom_commands.MoveSites.by_image_delta(
            self._structure, self.cell, atoms, delta)
        self.run(command)
        return f"moved {len(command.targets)} site(s)"

    def drag_rotation(self, axis, angle_degrees: float, centre) -> str:
        """Turn the selection about ``centre``, as the drawn atoms see
        it.

        The rotating half of :meth:`drag_selection`, and the same
        distinction: the images are what turn, and the sites follow.
        ``centre`` is cartesian and comes from the caller because it
        has to be the pivot the gesture started at -- recomputing the
        centroid while the atoms move drags the fragment away from it.
        """
        atoms = sorted(self.selection.atoms)
        if not atoms:
            return "nothing selected"
        command = atom_commands.MoveSites.by_image_rotation(
            self._structure, self.cell, atoms, axis, angle_degrees,
            centre)
        self.run(command)
        return f"turned {len(command.targets)} site(s)"

    def selection_pivot(self):
        """``(centre, radius)`` of the selected atoms as they are drawn
        -- the middle of what is being turned, and how big it is.

        The P1 cell rather than the scene: a selected atom drawn in
        nine cells at once would otherwise pull the centroid towards
        whichever corner of the display range it was repeated into.
        """
        atoms = sorted(self.selection.atoms)
        if not atoms:
            return None, 0.0
        points = self.cell.cart[atoms]
        centre = points.mean(axis=0)
        radius = float(np.linalg.norm(points - centre, axis=1).max())
        return centre, radius

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

        What it does **not** do is undo the user's own bond edits: a
        bond they drew stays drawn and a bond they deleted stays
        suppressed, because both are information perception cannot
        produce.  That is also the reason this looked like a button
        that did nothing -- somebody who deletes a bond and then
        recalculates gets the identical graph and no explanation.  So
        the overrides are counted and said out loud, and
        :meth:`reset_bonds` is named as the way past them.
        """
        before = {b.key() for b in bonding.perceive(self._structure)}
        self.run(bond_commands.RecomputeBonds())
        after = {b.key() for b in bonding.perceive(self._structure)}

        added, removed = len(after - before), len(before - after)
        if not added and not removed:
            head = f"bonds recalculated, unchanged: {len(after)} bonds"
        else:
            # The difference, not the total: a recalculation that
            # swapped one bond for another has the same count as one
            # that did nothing, and they are not the same event.
            head = (f"bonds recalculated: {added} added, "
                    f"{removed} removed -- {len(after)} bonds")
        held = self.bond_overrides()
        return head if not held else f"{head} ({held})"

    def bond_overrides(self) -> str:
        """The user's bond edits, counted -- or "" when there are none.

        Said after every recalculation, because they are what a
        recalculation deliberately leaves in place, and an unexplained
        no-op is indistinguishable from a broken button.
        """
        drawn = sum(1 for b in self._structure.bonds
                    if b.kind == "explicit")
        cut = sum(1 for b in self._structure.bonds
                  if b.kind == "suppressed")
        parts = []
        if drawn:
            parts.append(f"{drawn} you drew")
        if cut:
            parts.append(f"{cut} you deleted")
        if not parts:
            return ""
        return (f"kept {' and '.join(parts)}; "
                f"Reset bonds is what drops them")

    def reset_bonds(self) -> str:
        """Drop the bond edits and take the automatic answer.

        The way back from a suppression, which is otherwise permanent:
        it is stored so that perception cannot undo it and it is saved
        with the project, so once the undo stack is gone there is
        nothing else that can.
        """
        held = self.bond_overrides()
        if not held:
            # Nothing to drop, so this is a recalculation and should
            # say so rather than claiming to have reset something.
            return self.recompute_bonds()
        self.run(bond_commands.ResetBonds())
        return (f"bonds reset to automatic: "
                f"{len(bonding.perceive(self._structure))} bonds, "
                f"and the edits you had made to them are gone -- "
                f"Ctrl+Z brings them back")

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
        if command.replaced is not None:
            # Worth saying: the click both drew a bond and withdrew a
            # deletion, and the deletion was the invisible half.
            return "bond added, over the one you had deleted"
        if not command.added:
            return "those atoms are already bonded"
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
        command = bond_commands.AddTopologyBond.between_atoms(
            self._structure, self.cell, atom_a, atom_b,
            image_a, image_b)
        self.run(command)
        edges = len(bonding.topology_graph(self._structure).bonds)
        if not command._added:
            # Symmetry had already put an edge here.  Saying "drawn"
            # would be a lie, and the honest answer is also the useful
            # one: the net already says this.
            return f"already a net edge -- {edges} in the cell"
        return f"net edge drawn -- {edges} in the cell"

    def select_topology(self, key, mode: str = "set") -> None:
        """Select one net edge, replacing the selection or adding to it.

        Replaces the atoms and bonds for the same reason
        :meth:`select_bond` does: *Draw net* says "click an edge to
        select it, Del removes it", and the first vertex of a
        half-finished edge is an atom that would be deleted instead.
        """
        if mode == "set":
            self.selection.set_atoms(())
            self.selection.bonds.clear()
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
        # Which record *draws* this edge, rather than what a click on
        # it would store.  Those are different questions the moment a
        # site is on a special position -- see
        # :func:`~xtal.core.bonding.record_drawing` -- and asking the
        # second one deleted nothing unless the user happened to click
        # the copy they had drawn.
        records = []
        for key in keys:
            for found in bonding.records_drawing(
                    self._structure, self.cell,
                    (int(key[0]), int(key[1]),
                     tuple(int(v) for v in key[2]))):
                if found not in records:
                    records.append(found)
        if not records:
            return "removed 0 net edge(s)"
        with self.transaction(f"Delete {len(keys)} net edge(s)"):
            for record in records:
                self.run(bond_commands.RemoveTopologyBond(record))
        gone = before - len(bonding.topology_graph(self._structure).bonds)
        self.selection.topology.clear()
        self.selectionChanged.emit()
        return f"removed {gone} net edge(s)"

    def net(self) -> topology.Net:
        """The net drawn on this structure, as a periodic graph."""
        return topology.net_of(self._structure)

    def net_identification(self) -> rcsr.NetReport:
        """Which net this is, looked up in the RCSR.

        Cached against the structure, because identification is not
        free -- the coordination sequences are a walk over ten shells
        of an infinite graph -- and because nothing but a change to the
        bonds can change the answer.  A cell edit, a relaxation and a
        change of setting all leave it alone, which is exactly what
        makes a net worth naming.
        """
        return self._structure.cached(
            "net_identification",
            lambda: rcsr.describe(self.net()),
            invalidated_by=CHEMISTRY)

    def net_report(self, atom: int | None = None) -> str:
        """What the net drawn on this structure actually is, in a line.

        The coordination sequence and the point symbol are how RCSR
        names a net, and they are the reason for drawing one rather
        than printing it: **pcu** is 6, 18, 38, 66 and 4^12.6^3, and
        nothing else is.  Now that the catalogue is here the name comes
        first and the numbers it rests on follow, because the name is
        what was wanted and the numbers are the evidence for it.
        """
        del atom                        # the net is not an atom's
        return self.net_identification().sentence()

    def has_net(self) -> bool:
        """Whether anything has been drawn, without drawing it.

        Asked on every refresh of the shell, a drag included, so it
        reads the stored records rather than expanding the net.
        """
        return any(b.kind == TOPOLOGY for b in self._structure.bonds)

    def export_net(self, path) -> Path:
        """Write the drawn net as ``.cgd``, for Systre to name.

        The block is named after the file, because the name is the
        one thing Systre prints back and the file is what the user
        chose to call it.  One way, like :meth:`export`: nothing about
        the document changes.
        """
        from xtal.io.cgd import entry_of, write_cgd

        path = Path(path)
        return write_cgd(path, [entry_of(self._structure, path.stem)])

    def delete_selected_bonds(self) -> str:
        """Suppress every selected bond, as one undo step.

        One command for the whole selection, for the reason
        :meth:`set_selected_bond_type` gives.

        Reported in orbit terms, because that is what happens: a bond
        is stored against the asymmetric unit, so suppressing one
        suppresses every bond the symmetry says is the same bond.
        "removed 4 Ti-O bonds" is the honest message where "bond
        removed" is not.
        """
        bonds, _refused = self._selected_bonds_as_sites()
        if bonds is None:
            return "no bonds are selected"
        selected = len(self.selection.bonds)
        before = len(self.graph.bonds)
        if bonds:
            self.run(bond_commands.SuppressBonds(bonds))
        gone = before - len(self.graph.bonds)
        self.selection.bonds.clear()
        self.selectionChanged.emit()
        if gone == selected:
            return f"removed {gone} bond(s)"
        return (f"removed {gone} bonds -- {selected} were selected, "
                f"and symmetry carried it to the rest of the orbit")

    def set_selected_bond_type(self, order) -> str:
        """State the order of every selected bond, as one undo step.

        One command for the whole selection, not one per bond: the
        structure is touched once, the cell is expanded once and the
        viewport redraws once.  Select All on a framework selects eight
        hundred bonds, and the version of this that ran a command each
        made the application stop for a quarter of a minute drawing
        pictures nobody asked to see.

        Reported in orbit terms for the same reason deletion is: the
        statement is stored against the asymmetric unit, so calling one
        C-O of an acetate double calls the other one double as well,
        and a message that said "1 bond" would be describing a
        different edit from the one that happened.
        """
        bonds, refused = self._selected_bonds_as_sites()
        if bonds is None:
            return "no bonds are selected"
        name = bond_commands.bond_type_name(order)
        if bonds:
            self.run(bond_commands.SetBondTypes(bonds, order))
        changed = self.count_bonds_of_order(order)
        selected = len(self.selection.bonds)
        if refused:
            return (f"set {changed} bond(s) to {name.lower()}; "
                    f"{refused} could not be expressed in "
                    f"{self._structure.space_group.short_name} and "
                    f"were left alone")
        if order is None:
            return f"{selected} bond(s) back to the inferred order"
        if changed > selected:
            return (f"set {changed} bonds to {name.lower()} -- "
                    f"{selected} were selected, and symmetry carried "
                    f"it to the rest of the orbit")
        return f"set {changed} bond(s) to {name.lower()}"

    def _selected_bonds_as_sites(self):
        """``(the selected bonds in site space, how many were refused)``.

        ``None`` for the bonds when nothing is selected.  A bond the
        space group cannot express is counted rather than raised: one
        such bond in a selection of eight hundred must not throw the
        other 799 away.
        """
        keys = sorted(self.selection.bonds)
        if not keys:
            return None, 0
        # Read the expansion once.  Nothing in this loop moves an atom,
        # so the cell it starts with is the cell it ends with -- and
        # asking the document for it again per bond is what made this
        # quadratic.
        cell = self.cell
        bonds, refused = [], 0
        for i, j, image in keys:
            try:
                bonds.append(bonding.bond_between(
                    self._structure, cell, int(i), int(j),
                    (0, 0, 0), tuple(int(v) for v in image)))
            except ValueError:
                refused += 1
        return bonds, refused

    def count_bonds_of_order(self, order) -> int:
        """How many drawn bonds now carry ``order``."""
        if order is None:
            return 0
        orders = bonding.orders(self._structure)
        return int(sum(1 for value in orders
                       if abs(float(value) - float(order)) < 1e-9))

    def selected_bond_type(self) -> str:
        """What the selected bonds are called, or "" when they differ.

        Read off the drawn graph, which already carries both halves of
        the answer: the order, and whether anybody stated it.  A bond
        whose order was inferred is *Automatic* even when the inference
        made it double, and one the user set is what they set.

        The menu asks this on every selection change, so it is a
        dictionary and a lookup rather than a walk back into site
        space per bond -- which on a framework with everything selected
        was a third of a second every time anything was clicked.
        """
        keys = self.selection.bonds
        if not keys:
            return ""
        drawn = {bond.key(): bond for bond in self.graph.bonds}
        names = set()
        for key in keys:
            bond = drawn.get(tuple(key))
            if bond is None:
                return ""               # selected but no longer drawn
            names.add(bond_commands.bond_type_name(bond.order,
                                                   bond.stated))
            if len(names) > 1:
                return ""
        return names.pop() if names else ""

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

    def merge_duplicates(self,
                         tol: float = symmetry.DEFAULT_MERGE_TOL):
        return self.operate(symmetry_commands.MergeDuplicates(tol))

    def preview_merge(self, tol: float = symmetry.DEFAULT_MERGE_TOL):
        """What merging duplicates at this tolerance would do.

        The tolerance dialog asks this as the spinbox moves; the right
        tolerance is a property of the file, so the count has to travel
        with the number."""
        return symmetry.preview_merge(self._structure, tol)

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
        """The subgroups of the current group that need no new cell,
        one per conjugacy class.  Cached on the group, so a dialog may
        ask freely."""
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

    def interpenetration_candidates(self, n: int):
        """Where ``n`` copies of this framework could go, best first.

        Read-only, so the dialog can follow the fold spinbox.  Raises
        :class:`~xtal.analysis.interpenetrate.InterpenetrationError`
        for a structure with nothing periodic to interpenetrate.
        """
        from xtal.analysis import interpenetrate
        return interpenetrate.candidates(self._structure, n)

    def interpenetrate(self, placement):
        """Add the copies a placement names, as one undo step; returns
        the report, which is ``ok=False`` with the reason when the
        placement collides."""
        return self.operate(
            interpenetrate_commands.Interpenetrate(placement))

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

    def atom_types(self, parameter_set: str | None = None):
        """The force field's reading of every atom, with reasons.

        Memoised on the structure, so the panel may call it whenever it
        redraws.
        """
        from xtal.ff.uff import params, typer
        return typer.assign(
            self._structure,
            parameter_set=parameter_set or params.DEFAULT_PARAMETER_SET)

    def site_types(self, parameter_set: str | None = None) -> list:
        """One ``(site index, AtomType, multiplicity)`` per site.

        The table shows sites rather than cell atoms because an
        override is stored on a site and applies to its whole orbit --
        a per-atom table would offer edits it could not honour.
        """
        typing = self.atom_types(parameter_set)
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

    def preview_positions(self, frac, matrix=None) -> None:
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

        ``matrix`` is the cell at this step of a variable-cell run.
        Without it the atoms of a shrinking cell were drawn contracting
        inside the box they started in, and the fractional coordinates
        -- which a strain leaves alone -- showed no relaxation at all.
        """
        for site, coordinates in zip(self._structure.sites, frac,
                                     strict=True):
            site.frac = np.array(coordinates, dtype=float)
        change = Change.POSITIONS
        if matrix is not None and not np.array_equal(
                matrix, self._structure.lattice.matrix):
            from xtal.core.lattice import Lattice
            self._structure.lattice = Lattice(
                np.asarray(matrix, dtype=float))
            change |= Change.CELL
        self._structure.touch(change)
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

    def add_bond_measurements(self, keys) -> str:
        """Measure the selected bonds -- one distance each.

        A bond already names its two atoms, so "how long is that?" is
        one click on it rather than two clicks on its ends.  What gets
        stored is the pair of atoms and not the bond: a measurement
        follows the crystal by being taken again over its atoms
        (:meth:`_remeasure`), and a bond that recalculation removes
        would take an honest number off the table with it.

        The distance is the **minimum image** one, like every other
        measurement, which is the same number as the bond's own for
        every bond perception draws.  A bond the user drew to a
        further image reports the near one, and says so by being a
        distance rather than claiming to be that bond.

        Duplicates collapse: two bonds between the same pair in
        different images recompute to one number, so listing it twice
        would be two rows that can never disagree.

        Taken in one batch and announced once -- a box drawn round a
        linker selects eleven bonds, and eleven separate signals is
        what made Select All slow enough to notice.
        """
        pairs = sorted({(int(i), int(j)) for i, j, _image in keys
                        if int(i) != int(j)})
        if not pairs:
            raise ValueError(
                "a bond from an atom to its own periodic image joins "
                "one atom, and has no distance to report")
        cell, lattice = self.cell, self._structure.lattice
        taken = [measure.measure(cell, lattice, pair)
                 for pair in pairs]
        self.measurements.extend(taken)
        self.measurementsChanged.emit()
        if len(taken) == 1:
            return taken[0].text()
        return f"measured {len(taken)} bonds"

    # -- planes --------------------------------------------------------
    #
    # A plane is defined by atoms and re-fitted from them whenever they
    # move, which is the only way an interplanar angle can be trusted
    # after an optimisation: a plane stored as four numbers would go on
    # reporting the angle the molecule used to have.

    def define_plane(self, atoms=None, name: str = "") -> str:
        """Fit a plane through three or more atoms -- the selection by
        default.

        Exactly three atoms determine a plane; more are fitted by least
        squares, which is what makes "select the ring, define the
        plane" the gesture it should be rather than an error message
        about having picked six atoms.
        """
        indices = (sorted(self.selection.atoms) if atoms is None
                   else [int(a) for a in atoms])
        if len(indices) < 3:
            return "a plane needs at least three atoms"
        result = measure.plane(
            self.cell, self._structure.lattice, indices,
            name=name or self._next_plane_name())
        self.planes.append(result)
        self.planesChanged.emit()
        return result.text()

    def _next_plane_name(self) -> str:
        """The lowest unused ``Plane n``.

        Counting the list would reuse a name as soon as one is removed,
        and an interplanar angle already on the table would then be
        labelled with somebody else's plane.
        """
        taken = {p.name for p in self.planes}
        n = 1
        while f"Plane {n}" in taken:
            n += 1
        return f"Plane {n}"

    def remove_plane(self, index: int) -> None:
        if 0 <= index < len(self.planes):
            del self.planes[index]
            self.shown_planes = ()
            self.planesChanged.emit()

    def set_plane_color(self, rows, color) -> None:
        """Colour these planes, or put them back on the default.

        ``color`` of ``None`` clears the override rather than storing
        the default, so a plane nobody has coloured still follows the
        Planes swatch in the style panel when that is changed.
        """
        color = None if color is None else tuple(int(c) for c in color)
        changed = False
        for row in {int(r) for r in rows}:
            if 0 <= row < len(self.planes) \
                    and self.planes[row].color != color:
                self.planes[row].color = color
                changed = True
        if changed:
            self.planesChanged.emit()

    def clear_planes(self) -> None:
        if self.planes:
            self.planes = []
            self.shown_planes = ()
            self.planesChanged.emit()

    def set_shown_planes(self, rows) -> None:
        """Draw only these rows of the plane list, or all of them when
        the list is given nothing.

        Choosing none and meaning all is the useful default here for
        the same reason it is in :meth:`measure_plane_angles`: one
        plane is defined and looked at, and having to select the row
        as well before it appears would make the button look broken.
        """
        rows = tuple(sorted({int(r) for r in rows}))
        if rows != self.shown_planes:
            self.shown_planes = rows
            self.planesChanged.emit()

    def planes_to_draw(self) -> list:
        """The planes the viewport is to draw, in list order."""
        if not self.shown_planes:
            return list(self.planes)
        return [self.planes[r] for r in self.shown_planes
                if 0 <= r < len(self.planes)]

    # -- the pore network ---------------------------------------------
    #
    # What a porosity run came back with, drawn over the crystal the
    # way a plane is.  Unlike a plane it is not something the user
    # defined and not something this application worked out: it is an
    # external program's measurement of a particular arrangement of a
    # particular set of atoms.  So there is nothing to edit -- it is
    # put there by a run, hidden with View > Pore network, and dropped
    # by ``_stale_pores`` the moment that arrangement changes.

    def set_overlay(self, overlay) -> None:
        """Draw whatever a run found: a pore network, charges, or an
        orbital.  Each replaces its own kind and leaves the others."""
        if isinstance(overlay, overlays.AtomCharges):
            self.charges = overlay
            self.overlayChanged.emit()
        elif isinstance(overlay, overlays.OrbitalSurface):
            self.orbital = overlay
            self.overlayChanged.emit()
        else:
            self.set_pores(overlay)

    def clear_overlays(self) -> None:
        """Take the charges and the orbital off the picture."""
        if self.charges is None and self.orbital is None:
            return
        self.charges = self.orbital = None
        self.overlayChanged.emit()

    def set_pores(self, network) -> None:
        """Draw this pore network over the crystal.

        Not a command and not an edit.  Where the pores are is a fact
        about the structure that was already there -- finding it out
        changes nothing, so it must not land on the undo stack and
        must not mark the document modified.
        """
        self.pores = network
        self.poresChanged.emit()

    def measure_plane_angles(self, indices=None) -> str:
        """The angle between planes -- every pair of them.

        Two planes give one angle.  More than two give one angle per
        pair, because there is no such thing as "the" angle between
        three planes and picking one pair of the three for the user
        would be choosing for them.
        """
        chosen = (list(range(len(self.planes))) if indices is None
                  else [int(i) for i in indices])
        chosen = [i for i in chosen if 0 <= i < len(self.planes)]
        if len(chosen) < 2:
            return "define at least two planes to measure between them"
        added = 0
        for position, first in enumerate(chosen):
            for second in chosen[position + 1:]:
                self.measurements.append(measure.interplanar_angle(
                    self.planes[first], self.planes[second]))
                added += 1
        self.measurementsChanged.emit()
        if added == 1:
            return self.measurements[-1].text()
        return f"measured {added} interplanar angles"

    def remove_measurement(self, index: int) -> None:
        if 0 <= index < len(self.measurements):
            del self.measurements[index]
            self.measurementsChanged.emit()

    def clear_measurements(self) -> None:
        if self.measurements:
            self.measurements = []
            self.measurementsChanged.emit()

    def _remeasure(self) -> None:
        """Recompute every measurement and re-fit every plane after the
        atoms moved."""
        cell, lattice = self.cell, self._structure.lattice
        if self.planes:
            self.planes = [
                measure.plane(cell, lattice, p.atoms, name=p.name,
                              color=p.color)
                for p in self.planes if max(p.atoms) < cell.n_atoms]
            self.planesChanged.emit()
        if not self.measurements:
            return
        self.measurements = [
            self._recomputed(m, cell, lattice)
            for m in self.measurements
            if max(m.atoms) < cell.n_atoms]
        self.measurementsChanged.emit()

    def _recomputed(self, m, cell, lattice):
        """One measurement, taken again over the atoms as they are now.

        An interplanar angle is re-fitted from its two atom groups
        rather than from the planes in the list, so a measurement
        survives the plane it was taken from being removed -- what it
        records is the two sets of atoms, and those are still there.
        """
        if not m.planes:
            return measure.measure(cell, lattice, m.atoms)
        first, second = (
            measure.plane(cell, lattice, group, name=name)
            for group, name in zip(m.planes, m.labels, strict=False))
        return measure.interplanar_angle(first, second)

    def _prune_measurements(self) -> None:
        """Drop the measurements and planes whose atoms no longer
        exist."""
        n_atoms = self.cell.n_atoms
        planes = [p for p in self.planes if max(p.atoms) < n_atoms]
        if len(planes) != len(self.planes):
            self.planes = planes
            self.shown_planes = ()      # the rows have renumbered
            self.planesChanged.emit()
        keep = [m for m in self.measurements
                if max(m.atoms) < n_atoms]
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

    def fill_pores(self, guest: Fragment, count: int,
                   overlap_scale: float = fill.DEFAULT_OVERLAP_SCALE,
                   seed: int | None = None) -> str:
        """Put up to ``count`` copies of ``guest`` into the empty space.

        One undo step, the reduction to P1 a symmetric host needs
        included, and the new molecules left selected so that what
        arrived can be seen.  Nothing placed is nothing pushed: an
        empty entry on the stack makes Ctrl+Z lie.  Bonds are not
        recalculated -- see :class:`InsertMolecules`.
        """
        placement = fill.place(self._structure, guest, count,
                               overlap_scale=overlap_scale, seed=seed)
        if not placement.placed:
            return (f"no room was found for {guest.formula}"
                    if count else "nothing to place")
        command = InsertMolecules(guest, placement.positions)
        self.run(command)
        self.select(_atoms_of_sites(self.cell, command.indices))
        return placement.message()

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

    def set_cells(self, na: float, nb: float, nc: float) -> None:
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
