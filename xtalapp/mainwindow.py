"""
xtalapp.mainwindow
==================
The application shell: menus, toolbar, docks, document tabs, status bar.

The window owns documents and wires them to widgets; it holds no
crystallography of its own.  Anything it needs to know about a
structure it asks the Document, and anything it wants to change it asks
the Document to change -- which is what will let the whole menu bar
become undoable in phase 4 without touching this file's structure.

The viewport is injected (``viewport_factory``) so the shell can be
tested headless with a stub in place of the VTK widget.

Refreshing is split three ways on purpose.  ``_update_ui`` binds the
panels to a document and is for when the current document changes;
``_on_structure_changed`` refreshes what they show; ``_on_view_changed``
touches only the shell's own widgets.  Rebuilding a site table because
a display-range spinbox moved is where a large structure loses its
responsiveness.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QColorDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from xtal.build import MISSING as NO_RDKIT
from xtal.build import BuildError
from xtal.build import installed as rdkit_installed
from xtal.commands.bonds import BOND_TYPES
from xtal.commands.clipboard import Fragment
from xtal.core.structure import Change
from xtalapp import layout, menus
from xtalapp.actions import ActionRegistry
from xtalapp.dialogs.add_atom import AddAtomDialog
from xtalapp.dialogs.add_centroid import AddCentroidDialog
from xtalapp.dialogs.add_hydrogens import AddHydrogensDialog
from xtalapp.dialogs.bond_rules import BondRulesDialog
from xtalapp.dialogs.cell_edit import CellEditDialog
from xtalapp.dialogs.display_range import DisplayRangeDialog
from xtalapp.dialogs.find_symmetry import FindSymmetryDialog
from xtalapp.dialogs.merge_duplicates import MergeDuplicatesDialog
from xtalapp.dialogs.spacegroup import SpaceGroupDialog
from xtalapp.dialogs.subgroup import SubgroupDialog
from xtalapp.dialogs.supercell import SupercellDialog
from xtalapp.document import Document
from xtalapp.documents import (
    NO_CONFIRM_CLOSE_ENV,  # noqa: F401 -- the tests import it here
    DocumentSet,
    no_confirm_close,
)
from xtalapp.module_runner import ModuleRunner
from xtalapp.settings import AppSettings, default_size
from xtalapp.viewport import modes
from xtalapp.viewport.view_settings import (
    BACKGROUNDS,
    BOUNDARIES,
)
from xtalapp.workspace_shell import WorkspaceShell

APP_NAME = "Crystal Builder"

def _default_viewport_factory(document, parent=None):
    from xtalapp.viewport.widget import ViewportWidget
    return ViewportWidget(document, parent)


class MainWindow(QMainWindow):
    """The one window: file tree on the left, structures in the middle,
    information on the right."""

    def __init__(self, paths=None, viewport_factory=None,
                 settings=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        # Sized against the screen rather than to a fixed number of
        # pixels: 1280x820 is taller than a 1280x800 laptop display
        # before a single dock has asked for room.
        self.resize(*default_size(self))
        self.setAcceptDrops(True)

        self.settings = settings or AppSettings()
        self._viewport_factory = (viewport_factory
                                  or _default_viewport_factory)
        self.clipboard_fragment = Fragment()
        # What Insert molecule was last asked for.  Remembered
        # for the session and not in QSettings, the same rule
        # ModuleRunner keeps its parameters by: a SMILES string
        # is worth offering again while the work it belongs to is
        # open, and not six weeks later.
        self._insert_values: dict = {}
        # The workspace calculations land in.
        self.workspace_shell = WorkspaceShell(self)
        # What runs a module, and the run that may be going.  Built
        # before the docks it reports into, because _refresh_shell
        # asks it whether anything is running.
        self.module_runner = ModuleRunner(self)
        self._module_actions: list[tuple] = []
        self._module_submenus: dict = {}

        # Whether the viewport tooltip carries the force field's
        # reading of an atom.  Set before the docks are built, because
        # the Force Field dock reports its own visibility on the way
        # up and a new tab reads this to catch up.
        self._show_atom_types = False

        self.document_set = DocumentSet(self)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_document)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.actions_ = ActionRegistry(self)
        menus.build_actions(self)
        menus.build_menus(self)
        menus.build_toolbar(self)
        layout.build_docks(self)

        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)
        self.selection_label = QLabel("")
        self.statusBar().addPermanentWidget(self.selection_label)

        self.settings.restore_window(self)
        self.workspace_shell.restore_workspace()
        self._update_ui()

        for path in paths or []:
            self.open_path(path)

    # ==================================================================
    #  CONSTRUCTION
    # ==================================================================

    def _build_modules_menu(self) -> None:
        """Rebuild the Modules menu from the registry.

        A name of its own because a module registered after the window
        was built has to get into the menu somehow, which is what two
        tests do.
        """
        menus.build_modules_menu(self)

    def _refresh_module_availability(self) -> None:
        """Grey out what cannot run, with the reason as the tooltip.

        Connected to the Modules menu's ``aboutToShow``, so it stays a
        bound method of this window: that is what makes it a queued
        connection to the right thread and what keeps the menu from
        holding the slot alive by itself.
        """
        menus.refresh_module_availability(self)

    def apply_default_layout(self) -> None:
        """Put every dock back where it starts.

        Kept as a name on the window because that is what
        [docs/TODO.md](TODO.md) points at and what Reset layout is a
        way back to; the arrangement itself is
        :func:`xtalapp.layout.apply_default_layout`.
        """
        layout.apply_default_layout(self)

    def reset_layout(self) -> None:
        """Forget the saved layout and start again.

        An action slot, so it stays a bound method of this window.
        """
        layout.reset_layout(self)

    # ==================================================================
    #  DOCUMENTS
    # ==================================================================
    #
    # The documents and their tabs are :mod:`xtalapp.documents`.  What
    # is left here is the names the rest of the application reaches
    # them by: every one is an action slot, a signal receiver, or
    # something the tests and the run-app driver call on the window --
    # ``open_path`` alone in eighty places.

    @property
    def documents(self) -> list:
        """The open documents, in tab order.

        Read-only, and read from the document set rather than mirrored
        here: tab *i* shows document *i*, and two lists would be one
        too many.
        """
        return self.document_set.documents

    @property
    def _last_export(self):
        return self.document_set._last_export

    def current_document(self) -> Document | None:
        return self.document_set.current_document()

    def current_viewport(self):
        return self.document_set.current_viewport()

    def add_document(self, document: Document) -> int:
        return self.document_set.add_document(document)

    def new_document(self) -> Document:
        return self.document_set.new_document()

    def open_dialog(self) -> None:
        self.document_set.open_dialog()

    def open_path(self, path) -> Document | None:
        return self.document_set.open_path(path)

    def document_for(self, path) -> Document | None:
        return self.document_set.document_for(path)

    # ==================================================================
    #  THE WORKSPACE
    # ==================================================================
    #
    # The workspace itself is :mod:`xtalapp.workspace_shell`.  These
    # eleven names stay because something outside uses them: four are
    # connected to dock signals in :mod:`xtalapp.layout`, two are menu
    # actions, and ``refresh_workspace`` is reached by the module
    # runner, the document set and both force field docks whenever a
    # run leaves something on disk.

    @property
    def workspace(self):
        """The open workspace, or ``None``.

        Read-only, over the workspace shell's: one copy of which
        folder is open, not two.
        """
        return self.workspace_shell.workspace

    def place_in_workspace(self, document, path) -> None:
        self.workspace_shell.place_in_workspace(document, path)

    def set_workspace(self, root, create: bool = False):
        return self.workspace_shell.set_workspace(root, create)

    def refresh_workspace(self) -> None:
        self.workspace_shell.refresh_workspace()

    def open_workspace_dialog(self) -> None:
        self.workspace_shell.open_workspace_dialog()

    def new_workspace_dialog(self) -> None:
        self.workspace_shell.new_workspace_dialog()

    def _on_workspace_requested(self, what: str) -> None:
        self.workspace_shell._on_workspace_requested(what)

    def _on_run_started(self, path: str) -> None:
        self.workspace_shell._on_run_started(path)

    def _on_run_finished(self, path: str) -> None:
        self.workspace_shell._on_run_finished(path)

    def _on_trajectory_history(self, history) -> None:
        self.workspace_shell._on_trajectory_history(history)

    def open_artifact(self, kind: str, path: str) -> None:
        self.workspace_shell.open_artifact(kind, path)

    def save_document(self) -> None:
        self.document_set.save_document()

    def save_document_as(self) -> None:
        self.document_set.save_document_as()

    def _suggested_project(self, document) -> Path:
        return self.document_set._suggested_project(document)

    def export_dialog(self) -> None:
        self.document_set.export_dialog()

    def export_again(self) -> None:
        self.document_set.export_again()

    def export_image(self) -> None:
        self.document_set.export_image()

    def close_current(self) -> None:
        self.document_set.close_current()

    def close_document(self, index: int) -> None:
        self.document_set.close_document(index)

    # ==================================================================
    #  VIEW COMMANDS
    # ==================================================================

    def set_style(self, name: str) -> None:
        document = self.current_document()
        if document is not None:
            document.update_view(style=name)
            self.settings.set_default_view(style=name)
            self._report_ellipsoids(document, name)

    def _report_ellipsoids(self, document, style: str) -> None:
        """Say what the ellipsoids are made of when ORTEP is chosen.

        A drawing whose atoms are half of them fallbacks looks exactly
        like one whose atoms were all measured, and the difference is
        the whole value of the picture -- so it is said once, when the
        style is picked, rather than left to be discovered.
        """
        from xtalapp.viewport import styles
        if not styles.get(style).ellipsoids:
            return
        viewport = self.current_viewport()
        model = getattr(viewport, "model", None)
        report = model.thermal_report() if model is not None else ""
        if report:
            self.show_status(f"displacement ellipsoids: {report}")

    def set_view(self, **kwargs) -> None:
        document = self.current_document()
        if document is not None:
            document.update_view(**kwargs)

    def set_background(self, name: str) -> None:
        self.set_view(background=BACKGROUNDS[name])
        self.settings.set_default_view(background=BACKGROUNDS[name])

    def choose_background(self) -> None:
        document = self.current_document()
        if document is None:
            return
        current = QColor(*document.view.background)
        chosen = QColorDialog.getColor(current, self, "Background")
        if chosen.isValid():
            self.set_view(background=(chosen.red(), chosen.green(),
                                      chosen.blue()))

    def reset_view(self) -> None:
        viewport = self.current_viewport()
        if viewport is not None and hasattr(viewport, "reset_view"):
            viewport.reset_view()

    def look_along(self, axis: int) -> None:
        viewport = self.current_viewport()
        if viewport is not None and hasattr(viewport, "look_along_axis"):
            viewport.look_along_axis(axis)

    # ==================================================================
    #  SELECTION AND EDITING
    # ==================================================================

    def undo(self) -> None:
        document = self.current_document()
        if document is not None and document.can_undo:
            self.statusBar().showMessage(
                f"undid {document.undo()}", 4000)

    def redo(self) -> None:
        document = self.current_document()
        if document is not None and document.can_redo:
            self.statusBar().showMessage(
                f"redid {document.redo()}", 4000)

    def copy(self) -> None:
        """Copy the selection, to our own clipboard and the system's."""
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        self.clipboard_fragment = document.copy_selection()
        QGuiApplication.clipboard().setText(
            self.clipboard_fragment.to_xyz())
        self.statusBar().showMessage(
            f"copied {self.clipboard_fragment.n_atoms} atoms "
            f"({self.clipboard_fragment.formula})", 4000)

    def cut(self) -> None:
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        self.clipboard_fragment = document.cut_selection()
        QGuiApplication.clipboard().setText(
            self.clipboard_fragment.to_xyz())
        self.statusBar().showMessage(
            f"cut {self.clipboard_fragment.n_atoms} atoms", 4000)

    def paste(self) -> None:
        """Paste our fragment, or whatever XYZ is on the system
        clipboard -- so a fragment copied from another program lands
        here too."""
        document = self.current_document()
        if document is None:
            return
        fragment = self.clipboard_fragment
        text = QGuiApplication.clipboard().text()
        if text.strip():
            try:
                external = Fragment.from_xyz(text)
            except ValueError:
                external = None
            if external is not None and (
                    fragment.is_empty
                    or text.strip() != fragment.to_xyz().strip()):
                fragment = external
        if fragment.is_empty:
            self.statusBar().showMessage("nothing to paste", 4000)
            return
        self.statusBar().showMessage(document.paste(fragment), 6000)

    def duplicate(self) -> None:
        document = self.current_document()
        if document is not None and document.selection.atoms:
            self.statusBar().showMessage(
                document.duplicate_selection(), 6000)

    def add_atom_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        values = AddAtomDialog.ask(document.structure.lattice, self,
                                   self.element_combo.currentText())
        if values is None:
            return
        self.statusBar().showMessage(document.add_atom(**values), 4000)

    def insert_molecule_dialog(self) -> None:
        """Build a molecule from a string and paste it into this cell.

        A shell action rather than a module one, and
        :mod:`xtal.modules.build` gives the reason: a module's
        returned structure either replaces the open document or opens
        a tab of its own, and a paste is neither.  What it borrows
        from the registry is the parameter declaration and the dialog
        name, so the box that inserts and the box that builds a new
        document are one dialog with one set of parameters.
        """
        document = self.current_document()
        if document is None:
            return
        from xtal.modules.build import BUILD, INSERT, molecule_for
        from xtalapp.dialogs import module_dialog
        values = module_dialog(INSERT.dialog).ask(
            BUILD, INSERT, self, self._insert_values)
        if values is None:
            return
        self._insert_values = values
        try:
            molecule = molecule_for(values, connection_points=False)
        except BuildError as exc:
            self.show_message(str(exc))
            return
        self.show_status(document.paste(molecule.to_fragment(),
                                        self.paste_offset()))

    def paste_offset(self):
        """Where something dropped into the structure lands.

        The camera's focal point -- the middle of the picture -- or
        ``None``, which is what
        :meth:`xtal.commands.clipboard.Fragment.to_sites` already
        reads as the centre of the cell.

        Asked for defensively rather than assumed, because the
        viewport is injected: the stub the widget tests use is a bare
        ``QWidget`` with no camera and no intention of growing one,
        and a shell that needed it to would be a shell that cannot be
        tested without a GL context.  Both answers are real -- the
        cell centre is where a paste has always landed -- so a missing
        camera is not an error to report.
        """
        viewport = self.current_viewport()
        focal = getattr(viewport, "focal_point", None)
        if focal is None:
            return None
        try:
            return focal()
        except Exception:                           # noqa: BLE001
            # A tab whose render window has not been realised yet has
            # a renderer but nothing for it to look at.
            return None

    def add_centroid_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        values = AddCentroidDialog.ask(len(document.selection.atoms),
                                       self,
                                       self.element_combo.currentText())
        if values is None:
            return
        self.show_status(document.add_centroid(**values))

    def set_preview_interval(self, milliseconds: int) -> None:
        """How often a running calculation redraws the viewport.

        A setting rather than a constant because the right answer
        depends on the structure: every step is smooth on a molecule
        and is the slowest thing in the run on a framework.
        """
        self.settings.preview_interval = int(milliseconds)
        for index in range(self.tabs.count()):
            viewport = self.tabs.widget(index)
            if hasattr(viewport, "preview_interval_ms"):
                viewport.preview_interval_ms = int(milliseconds)

    def show_atom_types(self, showing: bool) -> None:
        """Put the force field's reading into the viewport tooltip, or
        take it out again.

        Driven by the Force Field dock's own visibility, so the
        tooltip follows what is on screen rather than a preference
        nobody set.  Every tab and not just the current one: a dock is
        the window's, and switching tabs must not change what a
        tooltip says.
        """
        self._show_atom_types = bool(showing)
        for index in range(self.tabs.count()):
            viewport = self.tabs.widget(index)
            if hasattr(viewport, "show_types"):
                viewport.show_types = self._show_atom_types

    def recompute_bonds(self) -> None:
        document = self.current_document()
        if document is not None:
            self.show_status(document.recompute_bonds())

    def reset_bonds(self) -> None:
        """Throw away the bond edits and perceive again.

        Separate from Recalculate because the two answer different
        questions: recalculating asks the geometry, resetting also
        withdraws every answer the user has given.  This is the one
        with the key on it -- see the note in :mod:`xtalapp.menus`.
        """
        document = self.current_document()
        if document is not None:
            self.show_status(document.reset_bonds())

    def edit_bond_rules(self) -> None:
        document = self.current_document()
        if document is None:
            return
        message = BondRulesDialog.ask(document, self, self.settings)
        if message:
            self.show_status(message)

    def set_bonds_follow_geometry(self, on: bool) -> None:
        """The preference, and every document already open.

        Applied to the open documents as well as saved, because a
        preference that only takes effect on the next file is one the
        user has to discover twice.
        """
        self.settings.bonds_follow_geometry = bool(on)
        for document in self.documents:
            document.bonds_follow_geometry = bool(on)
        self.show_status(
            "bonds now follow the geometry" if on else
            "bonds change when you recalculate them")

    #: A place in a context menu for the Set Bond Type submenu.  Not
    #: an action name, because the entry is a menu and not an action --
    #: the registry holds the five types inside it.
    BOND_TYPE_MENU = "@bond_type"

    #: The same, for the three boundary answers.
    BOUNDARY_MENU = "@boundary"

    #: The measurement the selected atoms admit, whichever it is.
    #: Built at click time because it depends on the count, and
    #: absent at a count that admits none.
    MEASURE_ENTRY = "@measure"

    #: What a right click offers, by what was under it.  Every entry
    #: is a name in the action registry, so each one is already
    #: undoable, already has a keyboard shortcut and already appears in
    #: the menu bar -- and adding one costs a name in a list.
    #: The cell is the one thing that is always under the cursor,
    #: whatever was clicked, so ``edit_cell`` and ``display_range``
    #: end all three lists rather than only the one for empty space.
    CONTEXT_MENUS = {
        "atom": ["change_element", "delete_selection", None,
                 "expand_bonded", "expand_fragment", "expand_orbit",
                 "select_same", None, "copy", "cut", "duplicate",
                 "add_centroid", MEASURE_ENTRY, None,
                 "recompute_bonds", None,
                 "edit_cell", "display_range"],
        "bond": ["delete_bond", BOND_TYPE_MENU, None, "select_none",
                 None, "recompute_bonds", None,
                 "edit_cell", "display_range"],
        "view": ["select_all", "select_none", None,
                 BOUNDARY_MENU, None, "orthographic",
                 "reset_view", None,
                 "edit_cell", "display_range"],
    }

    #: The entries whose wording should say how much they will take.
    #: "Delete" and "Delete 14 atoms" are different promises, and a
    #: menu that makes the first while meaning the second is the one
    #: that loses somebody's work.
    COUNTED_ACTIONS = {"delete_selection": "Delete {n} {noun}",
                       "delete_bond": "Delete {n} {noun}"}

    def build_context_menu(self, kind: str):
        """The menu for whatever was right-clicked, or ``None``.

        Built from this window's registry -- which is what keeps a
        context-menu entry and a menu-bar entry the same object,
        enabled and disabled by the same rule.  The building is
        :func:`xtalapp.menus.context_menu`; the name stays here
        because the viewport and five tests call it on the window.
        """
        return menus.context_menu(self, kind)

    def set_bond_type(self, order) -> None:
        """Call the selected bonds single, double, triple, aromatic --
        or nothing, and let the geometry decide again."""
        document = self.current_document()
        if document is not None and document.selection.bonds:
            self.show_status(document.set_selected_bond_type(order))

    def show_context_menu(self, kind: str, position) -> None:
        menu = self.build_context_menu(kind)
        if menu is not None:
            menu.exec(position)

    def set_mode(self, name: str) -> None:
        modes.get(name)                     # validate before switching
        viewport = self.current_viewport()
        if viewport is not None and hasattr(viewport, "set_mode"):
            # The viewport says what entering the mode means here and
            # now -- Add atom over a selected atom starts anchored --
            # through its own status signal, and saying the plain hint
            # afterwards would overwrite it.
            viewport.set_mode(name)
            return
        self.statusBar().showMessage(modes.get(name).hint, 6000)

    def cancel_gesture(self) -> None:
        """Escape, from wherever the focus happens to be.

        A window action rather than a key handler on the viewport,
        because a key event goes to the widget that has focus and the
        viewport almost never does: entering a mode means pressing a
        toolbar button, which leaves the focus on the toolbar.

        And an escalation, because Escape means "back out of whatever
        I am in the middle of" and there are three depths of that: a
        half-finished click gesture, a mode that is not Select, and a
        selection.  Each press goes up one rung, so the key never does
        nothing while there is still something to back out of -- and
        it still ends where it has always ended, clearing the
        selection.
        """
        viewport = self.current_viewport()
        if (viewport is not None
                and hasattr(viewport, "cancel_gesture")
                and viewport.cancel_gesture()):
            return
        self.select_none()

    def sync_mode_action(self, name: str) -> None:
        """Press the toolbar button for the mode the viewport is in.

        The viewport changes mode by itself when Escape leaves one, so
        the button cannot be the thing that decides which mode is
        current -- it has to follow.  ``setChecked`` and not
        ``trigger``: triggering would call back into
        :meth:`set_mode` and set the mode that is already set.
        """
        action = self.actions_.get(f"mode_{name}")
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def _on_measure_target(self, count: int) -> None:
        """The measurement chooser sets how many atoms a click run
        takes; the mode is where that lives."""
        mode = modes.get("measure")
        mode.target = int(count)
        mode.picked = []

    def _on_element_changed(self, text: str) -> None:
        from xtal.core import elements as el
        symbol = el.canonical_symbol(text)
        if symbol is not None:
            modes.get("add_atom").element = symbol

    def _update_history_actions(self) -> None:
        document = self.current_document()
        undo = self.actions_["undo"]
        redo = self.actions_["redo"]
        if document is None:
            undo.setEnabled(False)
            redo.setEnabled(False)
            undo.setText("&Undo")
            redo.setText("&Redo")
            return
        # A document playing a trajectory back is showing somebody
        # else's geometry, so undoing into it would be undoing under a
        # picture that is about to be replaced by the next frame.
        editable = not document.is_playing
        undo.setEnabled(document.can_undo and editable)
        redo.setEnabled(document.can_redo and editable)
        undo.setText(f"&Undo {document.undo_label}".rstrip())
        redo.setText(f"&Redo {document.redo_label}".rstrip())

    def select_all(self) -> None:
        document = self.current_document()
        if document is not None:
            document.select_all()

    def select_none(self) -> None:
        document = self.current_document()
        if document is not None:
            document.select_none()

    def invert_selection(self) -> None:
        document = self.current_document()
        if document is not None:
            document.invert_selection()

    def select_element(self, symbol: str) -> None:
        document = self.current_document()
        if document is not None:
            document.select_element(symbol)

    def select_same_element(self) -> None:
        """Grow a one-atom selection to every atom of that element."""
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        from xtal.core import selection as sel
        elements = {document.cell.elements[a]
                    for a in document.selection.atoms}
        atoms = set()
        for symbol in elements:
            atoms |= sel.by_element(document.cell, symbol)
        document.select(atoms, "set")

    def expand_selection(self, how: str) -> None:
        document = self.current_document()
        if document is not None:
            document.expand_selection(how)

    def define_plane(self) -> None:
        """A plane through the selected atoms."""
        document = self.current_document()
        if document is not None:
            self.show_status(document.define_plane())

    def measure_selection(self) -> None:
        """Measure the selected atoms, in the order they were picked.

        Two is a distance, three an angle about the middle one, four
        a torsion -- the same rule the measuring mode works to, taken
        over atoms that are already selected rather than making
        somebody click them a second time.
        """
        document = self.current_document()
        if document is None:
            return
        try:
            self.show_status(
                document.add_measurement(document.selection.order))
        except ValueError as exc:
            self.show_status(str(exc))

    def measure_plane_angles(self) -> None:
        """The angle between every pair of planes defined so far."""
        document = self.current_document()
        if document is not None:
            self.show_status(document.measure_plane_angles())

    def clear_planes(self) -> None:
        document = self.current_document()
        if document is not None:
            document.clear_planes()

    def clear_measurements(self) -> None:
        document = self.current_document()
        if document is not None:
            document.clear_measurements()

    def delete_bonds(self) -> None:
        document = self.current_document()
        if document is not None and document.selection.bonds:
            self.show_status(document.delete_selected_bonds())

    def delete_selection(self) -> None:
        """Delete whatever is in hand.

        One key for all three: net edges, then bonds, then sites --
        each when it is what is selected and nothing else is.  Clicking
        a bond and pressing delete should delete the bond, and the
        alternative -- a second key, or a mode -- is how the
        application ended up with deletion living inside a tool called
        Add Bond.
        """
        document = self.current_document()
        if document is None:
            return
        if document.selection.topology and not document.selection.atoms:
            self.show_status(document.delete_selected_topology())
            return
        if document.selection.bonds and not document.selection.atoms:
            self.delete_bonds()
            return
        if not document.selection.atoms:
            return
        if not document.selection_is_orbit_complete():
            answer = QMessageBox.question(
                self, "Symmetry",
                f"{document.selection_orbit_report()}.\n\n"
                f"Delete the whole orbit?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.statusBar().showMessage(document.delete_selection(), 5000)

    def change_element(self) -> None:
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        current = sorted({document.cell.elements[a]
                          for a in document.selection.atoms})[0]
        symbol, ok = QInputDialog.getText(
            self, "Change element", "New element:", text=current)
        if not ok or not symbol.strip():
            return
        from xtal.core import elements as el
        canonical = el.canonical_symbol(symbol)
        if canonical is None:
            QMessageBox.warning(
                self, "Unknown element",
                f"{symbol.strip()!r} is not an element symbol.")
            return
        symbol = canonical
        self.statusBar().showMessage(
            document.set_selection_element(symbol), 5000)

    def reduce_to_p1(self) -> None:
        document = self.current_document()
        if document is not None:
            self.statusBar().showMessage(document.reduce_to_p1(), 5000)

    # ==================================================================
    #  SYMMETRY AND CELL
    # ==================================================================
    #
    # The dialogs preview their own result, so everything reached from
    # here either opens one or is unambiguous enough not to need it.

    def find_symmetry(self) -> None:
        document = self.current_document()
        if document is not None:
            FindSymmetryDialog(document, self).exec()
            self._announce(document)

    def set_space_group(self) -> None:
        document = self.current_document()
        if document is not None:
            self._report(SpaceGroupDialog.ask(document, self))

    def standardize_cell(self, to_primitive: bool = False) -> None:
        self._run(lambda d: d.standardize_cell(
            to_primitive=to_primitive))

    def assign_wyckoff(self) -> None:
        self._run(lambda d: d.assign_wyckoff())

    def merge_duplicates(self) -> None:
        """Ask for the tolerance first.

        The count it would merge is flat over a wide range and then
        steps, and where it steps is a property of the file -- so the
        0.05 A default was as likely to be an order of magnitude too
        tight as it was to be right."""
        document = self.current_document()
        if document is not None:
            self._report(MergeDuplicatesDialog.ask(document, self))

    def descend_to_subgroup(self) -> None:
        """Descend, then reset the view.

        A descent can halve the cell or take three quarters of it, and
        can swap which axis is which -- so the camera that framed the
        old cell frames the new one badly or not at all.  Resetting is
        what every other operation that rebuilds the cell would want
        too; this is the one where it is never wrong, because the
        crystal has not moved and only the box around it has.
        """
        document = self.current_document()
        if document is None:
            return
        report = SubgroupDialog.ask(document, self)
        self._report(report)
        if report is not None and report.ok:
            self.reset_view()

    def invert_structure(self) -> None:
        """Swap the structure's hand, after saying what that means.

        Worth a confirmation and not worth a dialog of its own: the
        three answers a user needs -- nothing will change, the symbol
        will change, or the structure will change but the symbol will
        not -- are one sentence, and the command has already worked out
        which one it is.
        """
        document = self.current_document()
        if document is None:
            return
        report = document.preview_inversion()
        group = document.structure.space_group
        if group.is_centrosymmetric:
            QMessageBox.information(
                self, "Invert the structure",
                f"{group.short_name} is centrosymmetric, so inversion "
                f"is already one of its operations and the structure "
                f"you would get is the one you already have.")
            return
        answer = QMessageBox.question(
            self, "Invert the structure",
            f"{report.message}.\n\nThe cell is unchanged; the "
            f"coordinates and the space group both move. Continue?",
            QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._run(lambda d: d.invert_structure())

    def add_hydrogens_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        message = AddHydrogensDialog.ask(document, self)
        if message:
            self.statusBar().showMessage(message, 8000)

    def supercell_dialog(self) -> None:
        document = self.current_document()
        if document is not None:
            self._report(SupercellDialog.ask(document, self))

    def edit_cell(self) -> None:
        document = self.current_document()
        if document is not None:
            message = CellEditDialog.ask(document, self)
            if message:
                self.statusBar().showMessage(message, 6000)

    def reduce_cell(self, kind: str = "niggli") -> None:
        self._run(lambda d: d.reduce_cell(kind))

    def wrap_into_cell(self) -> None:
        self._run(lambda d: d.wrap_into_cell())

    # ==================================================================
    #  FORCE FIELD
    # ==================================================================
    #
    # Both menu entries drive the panel rather than duplicating it: a
    # single point run from the menu has to show the same breakdown,
    # and an optimisation has to be cancellable, so the panel is the
    # thing that runs them and the menu raises it first.

    def show_status(self, text: str) -> None:
        """Replace the permanent status line.

        This is where a panel says what it just computed, and it
        stands until the next refresh rewrites it from the document.
        """
        self.status_label.setText(text)

    def show_message(self, text: str, milliseconds: int = 6000) -> None:
        """Say something in passing, without taking over the line that
        describes the crystal."""
        self.statusBar().showMessage(text, milliseconds)

    # ==================================================================
    #  MODULES
    # ==================================================================
    #
    # The running of them is :mod:`xtalapp.module_runner`; what is left
    # here is the three names the rest of the application reaches it
    # by.  The modules dock, the run-progress dialog, ``closeEvent``
    # and the generated menu entries all call these, so they stay on
    # the window whatever the runner is called.

    @property
    def module_worker(self):
        """The run that is going, or ``None``.

        Read-only, and read from the runner rather than mirrored here:
        two copies of "is something running" is one copy too many, and
        the enabling of half the menu bar is decided by it.
        """
        return self.module_runner.module_worker

    def run_module_action(self, module_name: str,
                          action_name: str) -> None:
        self.module_runner.run_module_action(module_name, action_name)

    def stop_module(self) -> None:
        self.module_runner.stop_module()

    def show_force_field(self) -> None:
        self.ff_dock.show()
        self.ff_dock.raise_()

    def single_point_energy(self) -> None:
        self.show_force_field()
        self.ff_dock.single_point()

    def optimize_geometry(self) -> None:
        self.show_force_field()
        self.ff_dock.start()

    def show_dftb_panel(self) -> None:
        self.dftb_dock.show()
        self.dftb_dock.raise_()

    def dftb_single_point(self) -> None:
        self.show_dftb_panel()
        self.dftb_dock.single_point()

    def dftb_optimize(self) -> None:
        self.show_dftb_panel()
        self.dftb_dock.start()

    def display_range_dialog(self) -> None:
        document = self.current_document()
        if document is not None:
            DisplayRangeDialog.ask(document, self)

    def _run(self, operation) -> None:
        """Run a symmetry or cell operation on the current document and
        say what happened -- including when it declined to happen."""
        document = self.current_document()
        if document is None:
            return
        try:
            self._report(operation(document))
        except ValueError as exc:
            QMessageBox.warning(self, "The operation failed", str(exc))

    def _report(self, report) -> None:
        if report is None:
            return
        self.statusBar().showMessage(report.message, 8000)
        if report.warnings or not report.ok:
            QMessageBox.warning(
                self, "Symmetry",
                "\n\n".join([report.message] + list(report.warnings)))

    def _announce(self, document) -> None:
        self.statusBar().showMessage(document.status_text(), 5000)

    def _on_selection_changed(self) -> None:
        document = self.current_document()
        if document is None:
            return
        self.inspector_dock.refresh()
        self.sites_dock.sync_selection()
        self.move_dock.refresh()
        self.selection_label.setText(document.selection_summary())
        self.actions_.set_enabled(
            ["delete_bond"], bool(document.selection.bonds))
        self._sync_bond_type_actions(document)
        self._refresh_plane_actions()
        self.measure_dock.refresh_planes()
        # Delete acts on whichever of the three is held -- net edges,
        # then bonds, then sites -- so it is enabled by any of them.
        # It used to be listed here *and* in the atoms-only call
        # below, and the second call wins: with a bond selected and no
        # atom, Del was greyed out and the key did nothing.
        self.actions_.set_enabled(
            ["delete_selection"], bool(document.selection))
        self.actions_.set_enabled(
            ["change_element", "select_same", "expand_bonded",
             "expand_fragment", "expand_orbit", "copy", "cut",
             "duplicate"],
            bool(document.selection.atoms))
        # A centroid needs a middle, and one atom has none.
        self.actions_.set_enabled(
            ["add_centroid"], len(document.selection.atoms) > 1)

    def _sync_bond_type_actions(self, document) -> None:
        """Enable the bond types, and tick what the selection already
        is -- "" when the selected bonds are not all the same type, in
        which case none of them is ticked."""
        names = [f"bond_type_{n.lower()}" for n, _ in BOND_TYPES]
        selected = bool(document is not None
                        and not document.is_playing
                        and document.selection.bonds)
        self.actions_.set_enabled(names, selected)
        if hasattr(self, "bond_type_menu"):
            self.bond_type_menu.setEnabled(selected)
        current = document.selected_bond_type() if selected else ""
        for type_name, _order in BOND_TYPES:
            action = self.actions_[f"bond_type_{type_name.lower()}"]
            # Without this the group refuses to leave every entry
            # unticked, and a mixed selection would claim to be
            # whichever type happened to be ticked last.
            action.setChecked(type_name == current)

    def _refresh_plane_actions(self) -> None:
        """A plane needs three atoms, an angle needs two planes and a
        measurement needs two to four atoms, so none of these entries
        is offered before there is anything to do."""
        document = self.current_document()
        self.actions_.set_enabled(
            ["define_plane"],
            document is not None and len(document.selection.atoms) >= 3)
        self.actions_.set_enabled(
            ["measure_selection"],
            document is not None
            and len(document.selection.atoms) in menus.MEASURE_LABELS)
        self.actions_.set_enabled(
            ["plane_angle"],
            document is not None and len(document.planes) >= 2)
        self.actions_.set_enabled(
            ["clear_planes"],
            document is not None and bool(document.planes))
        self.actions_.set_enabled(
            ["clear_measurements"],
            document is not None and bool(document.measurements))

    def _rebuild_element_menu(self, document) -> None:
        self.element_menu.clear()
        if document is None:
            return
        for symbol in sorted(document.structure.elements):
            self.element_menu.addAction(
                symbol,
                lambda checked=False, s=symbol: self.select_element(s))

    def _on_cells_changed(self, _value=None) -> None:
        document = self.current_document()
        if document is None:
            return
        document.set_cells(*[s.value() for s in self.cell_spins])

    # ==================================================================
    #  HOUSEKEEPING
    # ==================================================================

    def _on_tab_changed(self, _index: int) -> None:
        self._update_ui()

    def _on_title_changed(self, document, title: str) -> None:
        if document in self.documents:
            self.tabs.setTabText(self.documents.index(document), title)

    def _on_structure_changed(self, change: int = 0) -> None:
        """The crystal changed: the panels that show it must catch up.

        Only the ones the change actually reached.  The formula, the
        density, the space group, the elements present and the force
        field's typing are all decided by *what* the atoms are, not by
        where they are -- so a geometry change refreshes the panels
        that show coordinates and leaves the rest alone.  Refreshing
        all of them on every drag of one atom is where a large
        structure loses its responsiveness.

        Previews do not arrive here at all; they travel on the
        document's ``previewChanged`` and reach the viewport only.
        """
        document = self.current_document()
        if document is None:
            return
        positions_only = bool(change) and not (
            change & ~int(Change.POSITIONS))

        # These show coordinates, so a move is news to them.
        self.inspector_dock.refresh()
        self.sites_dock.refresh()
        self.move_dock.refresh()

        # The net panel is the one expensive refresh here, so it is
        # given the flag and left to decide: identification walks ten
        # shells of an infinite graph, and a change that did not touch
        # a bond cannot have changed the answer.
        self.net_dock.on_structure_changed(change)

        if not positions_only:
            self.info_dock.show_document(document)
            self.style_dock.refresh()
            self.ff_dock.refresh()
            self.dftb_dock.refresh()
            self._rebuild_element_menu(document)
        # The shell, not _update_ui: that one *rebinds* every panel to
        # the document, which is for when the current document changes
        # and which would undo every skip above.
        self._refresh_shell()

    def _on_view_changed(self) -> None:
        """How it is drawn changed: the shell's own widgets and the
        style panel, which is the thing that shows view state."""
        self.style_dock.refresh()
        self._refresh_shell()

    def _on_measurements_changed(self) -> None:
        self.measure_dock.refresh()
        self._refresh_plane_actions()

    def _on_planes_changed(self) -> None:
        self.measure_dock.refresh_planes()
        self._refresh_plane_actions()

    def _update_ui(self, *_args) -> None:
        document = self.current_document()
        self.info_dock.show_document(document)
        self.net_dock.set_document(document)
        self.inspector_dock.set_document(document)
        self.sites_dock.set_document(document)
        self.move_dock.set_document(document)
        self.style_dock.set_document(document)
        self.measure_dock.set_document(document)
        self.ff_dock.set_document(document)
        self.dftb_dock.set_document(document)
        self.trajectory_dock.set_document(document)
        self._rebuild_element_menu(document)
        self._refresh_shell()

    def _refresh_insert_molecule(self, editable: bool) -> None:
        """Insert molecule, and the reason when it is off.

        Greyed with the sentence rather than absent.  RDKit is an
        optional extra, and an entry that is simply not there leaves
        somebody looking for a feature they have read about with
        nothing to find; one that is greyed and says ``pip install
        'crystal-builder[build]'`` in its tooltip tells them what to
        do.  The Modules tree greys its own entry from
        :func:`xtal.modules.build.available` and says the same thing.

        ``installed`` is ``find_spec``, which is why this can be
        called from every shell refresh.
        """
        action = self.actions_.get("insert_molecule")
        if action is None:                          # pragma: no cover
            return
        has_rdkit = rdkit_installed()
        action.setEnabled(editable and has_rdkit)
        tip = NO_RDKIT if not has_rdkit else menus.INSERT_MOLECULE_TIP
        action.setToolTip(tip)
        action.setStatusTip(tip)

    def _refresh_shell(self) -> None:
        """Menus, toolbar and status bar for the current document."""
        document = self.current_document()
        has_document = document is not None
        self.actions_.set_enabled(
            ["save", "save_as", "export", "export_again",
             "export_image", "close_tab", "reset_view", "view_a",
             "view_b", "view_c"],
            has_document)
        self._update_history_actions()
        self.actions_.set_enabled(
            ["select_all", "select_none", "invert_selection",
             "display_range", "bond_rules"],
            has_document)
        # Everything that changes the crystal is off while a
        # trajectory is being played: the atoms are showing a frame,
        # and an edit made against them would be wiped by the next one
        # without ever saying so.  ``Document.run`` refuses as well --
        # this is what stops the user reaching it.
        editable = has_document and not document.is_playing
        self.actions_.set_enabled(
            ["reduce_p1", "paste", "add_atom_dialog", "add_hydrogens",
             "find_symmetry", "set_space_group", "standardize",
             "primitive", "wyckoff", "merge_duplicates", "subgroup",
             "invert", "supercell",
             "edit_cell", "niggli", "delaunay", "wrap_cell",
             "single_point", "optimize", "dftb_single_point",
             "dftb_optimize", "recompute_bonds", "reset_bonds"],
            editable)
        if document is None:
            self._refresh_module_actions(False)
            self._refresh_insert_molecule(False)
            self._sync_bond_type_actions(None)
            self._refresh_plane_actions()
            self.status_label.setText("No structure open")
            self.selection_label.setText("")
            self.setWindowTitle(APP_NAME)
            return
        self.selection_label.setText(document.selection_summary())
        has_selection = bool(document.selection.atoms)
        self.actions_.set_enabled(
            ["select_same", "expand_bonded", "expand_fragment",
             "expand_orbit", "copy"],
            has_selection)
        self.actions_.set_enabled(
            ["change_element", "cut", "duplicate"],
            has_selection and editable)
        # A centroid needs a middle, and one atom has none.
        self.actions_.set_enabled(
            ["add_centroid"],
            len(document.selection.atoms) > 1 and editable)
        # Anything selected, not just atoms -- see _on_selection_changed.
        self.actions_.set_enabled(
            ["delete_selection"],
            bool(document.selection) and editable)
        self._refresh_module_actions(editable)
        self._refresh_insert_molecule(editable)
        self._sync_bond_type_actions(document)
        self._refresh_plane_actions()
        self.status_label.setText(document.status_text())
        self.setWindowTitle(f"{document.title} — {APP_NAME}")
        name = f"style_{document.view.style}"
        if name in self.actions_:
            self.actions_[name].setChecked(True)
        for action, value in (("show_atoms", document.view.show_atoms),
                              ("show_bonds", document.view.show_bonds),
                              ("show_bond_orders",
                               document.view.show_bond_orders),
                              ("show_cell", document.view.show_cell),
                              ("show_legend",
                               document.view.show_legend),
                              ("show_topology",
                               document.view.show_topology),
                              ("show_planes",
                               document.view.show_planes),
                              ("show_scale_bar",
                               document.view.show_scale_bar),
                              ("depth_cue", document.view.depth_cue)):
            widget = self.actions_[action]
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        # Set on each of the three and not just on the current one,
        # and without blocking signals: an exclusive QActionGroup
        # unticks the others *through* the signal it was blocked from
        # seeing, so blocking here left all three ticked at once.  The
        # slots hang off ``triggered``, which ``setChecked`` does not
        # emit -- see ``_sync_bond_type_actions``, which is the same
        # move for the same reason.
        for name in BOUNDARIES:
            action = self.actions_.get(f"boundary_{name}")
            if action is not None:
                action.setChecked(name == document.view.boundary)
        viewport = self.current_viewport()
        mode = getattr(viewport, "mode", None)
        if mode is not None and f"mode_{mode.name}" in self.actions_:
            self.actions_[f"mode_{mode.name}"].setChecked(True)
        for spin, value in zip(self.cell_spins, document.view.cells,
                               strict=True):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _refresh_module_actions(self, editable: bool) -> None:
        """Which module entries can be picked right now.

        Two reasons one cannot: there is nothing for it to run against
        -- no structure, or a trajectory being played, whose atoms are
        showing a frame -- or a module run is already going, because
        two at once would want two run folders and a Stop button that
        asks which.
        """
        idle = self.module_worker is None
        for name, needs_structure in self._module_actions:
            self.actions_.set_enabled(
                [name], idle and (editable or not needs_structure))

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self.settings.recent_files()
        for path in files:
            self.recent_menu.addAction(
                Path(path).name,
                lambda checked=False, p=path: self.open_path(p))
        if not files:
            empty = self.recent_menu.addAction("Nothing yet")
            empty.setEnabled(False)
        else:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction("Clear", self._clear_recent)

    def _clear_recent(self) -> None:
        self.settings.clear_recent_files()
        self._rebuild_recent_menu()

    def show_about(self) -> None:
        from xtal import __version__
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "Build, manipulate, analyse and export crystal "
            "structures.<br>"
            "Structure model and symmetry: gemmi and spglib. "
            "Rendering: VTK.")

    # -- drag and drop -------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file():
                self.open_path(path)

    def closeEvent(self, event):
        # A module run outlives the window that started it unless it
        # is stopped -- an external process especially, which would go
        # on writing into a run folder nobody is watching.
        self.stop_module()
        for document in list(self.documents):
            if document.modified and not no_confirm_close():
                answer = QMessageBox.question(
                    self, "Unsaved changes",
                    "Some structures have unsaved changes. Quit anyway?",
                    QMessageBox.Yes | QMessageBox.No)
                if answer != QMessageBox.Yes:
                    event.ignore()
                    return
                break
        self.settings.save_window(self)
        self.settings.sync()
        super().closeEvent(event)
