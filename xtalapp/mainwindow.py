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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QToolBar,
)

from xtal.commands.clipboard import Fragment
from xtal.core.structure import Change
from xtal.io import FORMATS
from xtal.workspace import NotAWorkspace, Workspace
from xtalapp.actions import ActionRegistry
from xtalapp.dialogs.add_atom import AddAtomDialog
from xtalapp.dialogs.bond_rules import BondRulesDialog
from xtalapp.dialogs.cell_edit import CellEditDialog
from xtalapp.dialogs.display_range import DisplayRangeDialog
from xtalapp.dialogs.find_symmetry import FindSymmetryDialog
from xtalapp.dialogs.spacegroup import SpaceGroupDialog
from xtalapp.dialogs.supercell import SupercellDialog
from xtalapp.docks.ff_panel import ForceFieldDock
from xtalapp.docks.info import InfoDock
from xtalapp.docks.inspector import InspectorDock
from xtalapp.docks.logview import LogDock
from xtalapp.docks.measure import MeasureDock
from xtalapp.docks.move import MoveDock
from xtalapp.docks.sites import SitesDock
from xtalapp.docks.style_panel import StylePanelDock
from xtalapp.docks.trajectory import TrajectoryDock
from xtalapp.docks.workspace import WorkspaceDock
from xtalapp.document import Document
from xtalapp.settings import AppSettings, default_size, fit_to_screen
from xtalapp.viewport import modes, styles
from xtalapp.viewport.view_settings import BACKGROUNDS

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
        self.documents: list[Document] = []
        self.clipboard_fragment = Fragment()
        # The workspace calculations land in, and the settings the
        # last export used -- which is what "Export again" repeats.
        self.workspace: Workspace | None = None
        self._last_export: tuple | None = None

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_document)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.actions_ = ActionRegistry(self)
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_docks()

        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)
        self.selection_label = QLabel("")
        self.statusBar().addPermanentWidget(self.selection_label)

        self.settings.restore_window(self)
        self.restore_workspace()
        self._update_ui()

        for path in paths or []:
            self.open_path(path)

    # ==================================================================
    #  CONSTRUCTION
    # ==================================================================

    def _build_actions(self):
        add = self.actions_.add
        add("new", "&New", self.new_document, "Ctrl+N")
        add("open", "&Open...", self.open_dialog, "Ctrl+O")
        add("save", "&Save", self.save_document, "Ctrl+S",
            tip="Save the session: the structure, the bonds you drew, "
                "the view, the selection and the measurements")
        add("save_as", "Save &As...", self.save_document_as,
            "Ctrl+Shift+S",
            tip="Save the session under another name")
        add("export", "&Export...", self.export_dialog,
            tip="Write a file for something else to read -- a CIF, an "
                "XYZ.  One way: it never becomes this document's file")
        add("export_again", "Export a&gain", self.export_again,
            tip="Export with the settings used last time")
        add("export_image", "Export &Image...", self.export_image)
        add("open_workspace", "&Open Workspace...",
            self.open_workspace_dialog,
            tip="A folder that structures and their calculations live "
                "in")
        add("new_workspace", "&New Workspace...",
            self.new_workspace_dialog)
        add("close_tab", "&Close", self.close_current, "Ctrl+W")
        add("quit", "&Quit", self.close, "Ctrl+Q")

        for name in styles.names():
            style = styles.get(name)
            add(f"style_{name}", style.label,
                lambda checked=False, s=name: self.set_style(s),
                checkable=True, checked=(name == "ball_stick"),
                tip=style.description, group="style")

        add("show_atoms", "Atoms",
            lambda v: self.set_view(show_atoms=v), checkable=True,
            checked=True)
        add("show_bonds", "Bonds",
            lambda v: self.set_view(show_bonds=v), checkable=True,
            checked=True)
        add("show_cell", "Unit cell",
            lambda v: self.set_view(show_cell=v), checkable=True,
            checked=True)
        add("show_legend", "Element legend",
            lambda v: self.set_view(show_legend=v), checkable=True)
        add("labels", "Labels",
            lambda v: self.set_view(
                label_mode="label" if v else "none"), checkable=True)
        add("orthographic", "Orthographic projection",
            lambda v: self.set_view(
                projection="orthographic" if v else "perspective"),
            checkable=True)
        add("boundary_bonded", "Complete bonds at the boundary",
            lambda v: self.set_view(
                boundary="bonded" if v else "in_range"),
            checkable=True)

        add("undo", "&Undo", self.undo, "Ctrl+Z")
        add("redo", "&Redo", self.redo, "Ctrl+Shift+Z")
        add("cut", "Cu&t", self.cut, "Ctrl+X")
        add("copy", "&Copy", self.copy, "Ctrl+C")
        add("paste", "&Paste", self.paste, "Ctrl+V")
        add("duplicate", "Du&plicate", self.duplicate, "Ctrl+D")
        add("add_atom_dialog", "&Add atom...", self.add_atom_dialog,
            "Ctrl+Shift+A")
        add("recompute_bonds", "&Recalculate bonds",
            self.recompute_bonds, "Ctrl+B",
            tip="Perceive the bonds again from the geometry as it is "
                "now.  Bonds do not change on their own when atoms "
                "move; this is what changes them.")
        add("bond_rules", "&Bond rules...", self.edit_bond_rules,
            tip="Which atoms bond, and how close they have to be")
        add("bonds_follow", "Bonds &follow the geometry",
            self.set_bonds_follow_geometry, checkable=True,
            checked=self.settings.bonds_follow_geometry,
            tip="Re-perceive the bonds after every edit that moves an "
                "atom, instead of only when you ask")

        for mode_name in modes.names():
            mode = modes.get(mode_name)
            add(f"mode_{mode_name}", mode.label,
                lambda checked=False, m=mode_name: self.set_mode(m),
                checkable=True, checked=(mode_name == "select"),
                tip=mode.hint, group="mode")

        add("select_all", "Select &All", self.select_all, "Ctrl+A")
        add("select_none", "Select &None", self.select_none, "Esc")
        add("invert_selection", "&Invert selection",
            self.invert_selection, "Ctrl+I")
        add("select_same", "Select same &element",
            self.select_same_element)
        add("expand_bonded", "Grow to &bonded neighbours",
            lambda: self.expand_selection("shell"), "Ctrl+G")
        add("expand_fragment", "Grow to whole &fragment",
            lambda: self.expand_selection("fragment"),
            "Ctrl+Shift+G")
        add("expand_orbit", "Grow to symmetry &orbit",
            lambda: self.expand_selection("orbit"))
        add("delete_selection", "&Delete", self.delete_selection,
            ["Del", "Backspace"],
            tip="Delete whichever is selected: the bonds if bonds "
                "are, otherwise the sites")
        add("delete_bond", "Delete &bond", self.delete_bonds,
            tip="Suppress the selected bonds, and their whole "
                "symmetry orbit")
        add("change_element", "Change &element...",
            self.change_element)
        add("reduce_p1", "Reduce to &P1", self.reduce_to_p1,
            tip="Expand every symmetry orbit into independent sites")

        add("find_symmetry", "&Find symmetry...", self.find_symmetry,
            "Ctrl+Shift+F",
            tip="Detect the space group at a tolerance and adopt it")
        add("set_space_group", "&Set space group...",
            self.set_space_group,
            tip="Choose a group and generate or impose it")
        add("standardize", "S&tandardise cell",
            lambda: self.standardize_cell(False),
            tip="Rebuild in the conventional setting of the detected "
                "group")
        add("primitive", "Reduce to pri&mitive cell",
            lambda: self.standardize_cell(True))
        add("wyckoff", "Assign &Wyckoff letters", self.assign_wyckoff)
        add("merge_duplicates", "Merge &duplicate sites",
            self.merge_duplicates,
            tip="Merge sites of the same element that sit on top of "
                "each other")

        add("supercell", "&Supercell...", self.supercell_dialog,
            tip="na x nb x nc, or a general integer transformation")
        add("edit_cell", "&Edit cell...", self.edit_cell,
            tip="Change the cell parameters, keeping fractional or "
                "cartesian coordinates")
        add("niggli", "&Niggli reduction",
            lambda: self.reduce_cell("niggli"),
            tip="The shortest, most orthogonal basis for this cell")
        add("delaunay", "&Delaunay reduction",
            lambda: self.reduce_cell("delaunay"))
        add("wrap_cell", "&Wrap atoms into the cell",
            self.wrap_into_cell)
        add("display_range", "Display &range...",
            self.display_range_dialog, "Ctrl+R",
            tip="How much of the crystal to draw")

        add("single_point", "&Single point energy",
            self.single_point_energy, "Ctrl+E",
            tip="Energy and per-term breakdown at this geometry")
        add("optimize", "&Optimise geometry", self.optimize_geometry,
            "Ctrl+Shift+E",
            tip="Relax the structure within its space group")
        add("show_ff", "&Force Field panel", self.show_force_field,
            tip="Atom types, electrostatics, and how the run is going")

        add("reset_layout", "Reset &layout", self.reset_layout,
            tip="Put the panels back where they started")
        add("reset_view", "&Reset view", self.reset_view, "Ctrl+0")
        add("view_a", "Along &a", lambda: self.look_along(0), "1")
        add("view_b", "Along &b", lambda: self.look_along(1), "2")
        add("view_c", "Along &c", lambda: self.look_along(2), "3")
        add("about", f"About {APP_NAME}", self.show_about)

    def _build_menus(self):
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self.actions_.fill_menu(file_menu, [
            "new", "open", None, "save", "save_as",
            None, "export", "export_again", "export_image",
            None, "new_workspace", "open_workspace",
            None, "close_tab"])
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.actions_["quit"])

        edit_menu = bar.addMenu("&Edit")
        self.actions_.fill_menu(edit_menu, [
            "undo", "redo", None, "cut", "copy", "paste", "duplicate",
            None, "delete_selection", "delete_bond",
            "change_element"])

        select_menu = bar.addMenu("&Select")
        self.actions_.fill_menu(select_menu, [
            "select_all", "select_none", "invert_selection", None,
            "select_same"])
        self.element_menu = select_menu.addMenu("By &element")
        grow_menu = select_menu.addMenu("&Grow")
        self.actions_.fill_menu(grow_menu, ["expand_bonded",
                                            "expand_fragment",
                                            "expand_orbit"])

        structure_menu = bar.addMenu("S&tructure")
        self.actions_.fill_menu(structure_menu, [
            "add_atom_dialog", None,
            "bond_rules", "recompute_bonds", "bonds_follow", None,
            *[f"mode_{n}" for n in modes.names()]])

        symmetry_menu = bar.addMenu("S&ymmetry")
        self.actions_.fill_menu(symmetry_menu, [
            "find_symmetry", "set_space_group", None,
            "standardize", "primitive", None,
            "wyckoff", "merge_duplicates", None, "reduce_p1"])

        cell_menu = bar.addMenu("&Cell")
        self.actions_.fill_menu(cell_menu, [
            "edit_cell", "supercell", None,
            "niggli", "delaunay", None, "wrap_cell"])

        calculate_menu = bar.addMenu("Ca&lculate")
        self.actions_.fill_menu(calculate_menu, [
            "single_point", "optimize", None, "show_ff"])

        view_menu = bar.addMenu("&View")
        style_menu = view_menu.addMenu("&Style")
        self.actions_.fill_menu(
            style_menu, [f"style_{n}" for n in styles.names()])
        show_menu = view_menu.addMenu("&Show")
        self.actions_.fill_menu(
            show_menu, ["show_atoms", "show_bonds", "show_cell",
                        "labels", "show_legend"])
        view_menu.addSeparator()
        background_menu = view_menu.addMenu("&Background")
        for name in BACKGROUNDS:
            background_menu.addAction(
                name.capitalize(),
                lambda checked=False, n=name: self.set_background(n))
        background_menu.addSeparator()
        background_menu.addAction("Custom...", self.choose_background)
        view_menu.addSeparator()
        self.actions_.fill_menu(view_menu, [
            "display_range", "boundary_bonded", None, "orthographic",
            None, "view_a", "view_b", "view_c", "reset_view"])

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.actions_["about"])

    def _build_toolbar(self):
        bar = QToolBar("Main")
        bar.setObjectName("MainToolBar")
        bar.setMovable(False)
        self.actions_.fill_menu(bar, ["open", "save", None, "undo",
                                      "redo", None, "reset_view"])
        bar.addSeparator()
        self.actions_.fill_menu(
            bar, [f"mode_{n}" for n in modes.names()])
        bar.addSeparator()
        bar.addAction(self.actions_["recompute_bonds"])
        self.element_combo = QComboBox()
        self.element_combo.setEditable(True)
        self.element_combo.addItems(
            ["H", "C", "N", "O", "F", "Na", "Si", "P", "S", "Cl",
             "Ca", "Ti", "Fe", "Co", "Ni", "Cu", "Zn", "Br", "I"])
        self.element_combo.setCurrentText("C")
        self.element_combo.setToolTip("Element placed by Add atom")
        self.element_combo.currentTextChanged.connect(
            self._on_element_changed)
        bar.addWidget(self.element_combo)
        bar.addSeparator()
        bar.addWidget(QLabel("  cells "))
        self.cell_spins = []
        for axis in "abc":
            spin = QSpinBox()
            spin.setRange(1, 20)
            spin.setValue(1)
            spin.setPrefix(f"{axis} ")
            spin.setToolTip(f"Unit cells shown along {axis}")
            spin.valueChanged.connect(self._on_cells_changed)
            bar.addWidget(spin)
            self.cell_spins.append(spin)
        bar.addSeparator()
        self.addToolBar(bar)
        self.toolbar = bar

    def _build_docks(self):
        self.file_dock = WorkspaceDock(self.settings.last_directory,
                                       self)
        self.file_dock.fileActivated.connect(self.open_path)
        self.file_dock.artifactActivated.connect(self.open_artifact)
        self.file_dock.workspaceRequested.connect(
            self._on_workspace_requested)

        self.inspector_dock = InspectorDock(self)
        self.inspector_dock.deleteRequested.connect(
            self.delete_selection)
        self.inspector_dock.reduceToP1Requested.connect(
            self.reduce_to_p1)

        self.info_dock = InfoDock(self)
        self.sites_dock = SitesDock(self)
        self.move_dock = MoveDock(self)
        self.style_dock = StylePanelDock(self)

        self.measure_dock = MeasureDock(self)
        self.measure_dock.targetChanged.connect(self._on_measure_target)

        self.ff_dock = ForceFieldDock(self)
        # Connected to a method, not to the label: the docks are built
        # before the status bar exists.
        self.ff_dock.statusMessage.connect(self.show_status)
        self.ff_dock.previewIntervalChanged.connect(
            self.set_preview_interval)
        self.ff_dock.set_preview_interval(
            self.settings.preview_interval)
        # A run that has just started or just finished has changed
        # what is in the workspace, and the tree is read from the
        # directory -- so this is the whole of keeping it in step.
        self.ff_dock.runStarted.connect(self._on_run_started)
        self.ff_dock.runFinished.connect(self._on_run_finished)

        self.log_dock = LogDock(self)
        self.trajectory_dock = TrajectoryDock(self)
        self.trajectory_dock.statusMessage.connect(self.show_status)
        # The plot and the trajectory are the same run seen two ways:
        # clicking the trace jumps to that frame, and the frame being
        # played is marked on the trace.
        self.ff_dock.plot.pointClicked.connect(
            self.trajectory_dock.show_step)
        self.trajectory_dock.frameShown.connect(
            self.ff_dock.plot.set_marker)
        self.trajectory_dock.historyLoaded.connect(
            self._on_trajectory_history)

        # The workspace on the left, the transport bar under the
        # viewport, everything else tabbed on the right in the order
        # they are listed here.
        self.left_docks = (self.file_dock,)
        self.bottom_docks = (self.trajectory_dock, self.log_dock)
        self.right_docks = (self.inspector_dock, self.info_dock,
                            self.sites_dock, self.move_dock,
                            self.style_dock, self.measure_dock,
                            self.ff_dock)
        self.docks = (self.left_docks + self.right_docks
                      + self.bottom_docks)
        self.apply_default_layout()

        window_menu = self.menuBar().addMenu("&Window")
        for dock in self.docks:
            window_menu.addAction(dock.toggleViewAction())
        window_menu.addSeparator()
        window_menu.addAction(self.actions_["reset_layout"])

    #: What a first run shows.  Every other panel is one item away in
    #: the Window menu; seven of them tabbed on the right hand side
    #: take, between them, the width the viewport is there to use.
    DEFAULT_VISIBLE = ("file_dock", "inspector_dock")

    def apply_default_layout(self) -> None:
        """Put every dock back where it starts: the tree on the left,
        the rest tabbed on the right, and only two of them shown.

        Called once on construction -- ``restore_window`` overrides it
        when there is a saved layout -- and again by Reset layout.
        """
        for dock in self.left_docks:
            self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        for dock in self.right_docks:
            self.addDockWidget(Qt.RightDockWidgetArea, dock)
        for dock in self.bottom_docks:
            self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        for previous, dock in zip(self.right_docks,
                                  self.right_docks[1:], strict=False):
            self.tabifyDockWidget(previous, dock)

        shown = {getattr(self, name) for name in self.DEFAULT_VISIBLE}
        for dock in self.docks:
            dock.setFloating(False)
            dock.setVisible(dock in shown)
        self.right_docks[0].raise_()

    def reset_layout(self) -> None:
        """Forget the saved layout and start again.

        Without this a window that once went wrong stays wrong: the bad
        geometry is what gets saved on quit and restored on start.
        """
        self.settings.clear_window()
        self.apply_default_layout()
        self.resize(*default_size(self))
        fit_to_screen(self)
        self.show_status("layout reset")

    # ==================================================================
    #  DOCUMENTS
    # ==================================================================

    def current_document(self) -> Document | None:
        index = self.tabs.currentIndex()
        if index < 0 or index >= len(self.documents):
            return None
        return self.documents[index]

    def current_viewport(self):
        widget = self.tabs.currentWidget()
        return widget

    def add_document(self, document: Document) -> int:
        document.bonds_follow_geometry = \
            self.settings.bonds_follow_geometry
        if not document.structure.bond_rules:
            # Only when the structure has none of its own: a project
            # carries the rules it was saved with, and a preference
            # must not overwrite them.
            document.structure.bond_rules = \
                self.settings.default_bond_rules()
        viewport = self._viewport_factory(document, self.tabs)
        if hasattr(viewport, "preview_interval_ms"):
            viewport.preview_interval_ms = self.settings.preview_interval
        self.documents.append(document)
        index = self.tabs.addTab(viewport, document.title)
        document.titleChanged.connect(
            lambda title, d=document: self._on_title_changed(d, title))
        document.structureChanged.connect(self._on_structure_changed)
        document.viewChanged.connect(self._on_view_changed)
        document.selectionChanged.connect(self._on_selection_changed)
        document.measurementsChanged.connect(
            self._on_measurements_changed)
        document.historyChanged.connect(self._update_history_actions)
        document.playbackChanged.connect(self._refresh_shell)
        if hasattr(viewport, "statusMessage"):
            viewport.statusMessage.connect(
                lambda text: self.statusBar().showMessage(text, 4000))
        if hasattr(viewport, "contextRequested"):
            viewport.contextRequested.connect(self.show_context_menu)
        self.tabs.setCurrentIndex(index)
        self._update_ui()
        return index

    def new_document(self) -> Document:
        document = Document()
        self.add_document(document)
        return document

    def open_dialog(self) -> None:
        filters = [f.filter_string() for f in FORMATS.readable()]
        filters.append("All files (*)")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open structure", self.settings.last_directory,
            ";;".join(filters))
        if path:
            self.open_path(path)

    def open_path(self, path) -> Document | None:
        path = Path(path)
        try:
            document = Document.load(path)
        except (ValueError, OSError, KeyError) as exc:
            QMessageBox.warning(self, "Could not open the file",
                                f"{path.name}\n\n{exc}")
            return None
        self.add_document(document)
        self.settings.add_recent_file(path)
        self.settings.last_directory = str(path.parent)
        self._rebuild_recent_menu()
        self.file_dock.set_root(path.parent)
        self.place_in_workspace(document, path)
        if document.warnings:
            self.statusBar().showMessage(
                f"opened with {len(document.warnings)} warning(s)", 8000)
        return document

    # ==================================================================
    #  THE WORKSPACE
    # ==================================================================

    def place_in_workspace(self, document, path) -> None:
        """Give a freshly opened structure somewhere to put its runs.

        The file is **copied** into the workspace rather than pointed
        at.  A workspace whose nodes are references to files the user
        then edits, renames or deletes is a tree of broken links; the
        copy costs kilobytes, and where the file came from is kept in
        ``structure.meta["source"]``.
        """
        path = Path(path)
        if document.entry is not None:
            # Already inside a workspace -- opened from the tree, or a
            # project that found its own by looking upwards.
            self.refresh_workspace()
            return
        workspace = self.workspace or self._offer_workspace(path)
        if workspace is None:
            return
        try:
            entry = workspace.add_structure(path)
        except OSError as exc:
            self.show_message(f"could not copy into the workspace: "
                              f"{exc}")
            return
        document.structure.meta.setdefault("source", str(path))
        document.attach_workspace(entry)
        self.refresh_workspace()
        self.file_dock.tree.select_path(entry.path)

    def _offer_workspace(self, path) -> Workspace | None:
        """What to do for a structure opened with no workspace open.

        Nothing, and say so.  The user picks the workspace and the
        application never guesses: a folder created behind somebody's
        back is one they find later and do not recognise, and a dialog
        on every file open is worse than the problem it solves.  So a
        structure with no workspace opens, runs, and leaves nothing
        behind -- which is exactly what this application did before
        there was anywhere to leave anything -- and the status bar
        says how to change that.
        """
        if not self.settings.auto_workspace:
            self.show_message(
                "no workspace open, so runs will not be kept -- "
                "File > New Workspace... gives them somewhere to go")
            return None
        return self.set_workspace(Path(path).parent / "Crystal Builder",
                                  create=True)

    def set_workspace(self, root, create: bool = False):
        """Open a workspace and show it in the tree."""
        try:
            workspace = (Workspace.create(root) if create
                         else Workspace.open(root))
        except (NotAWorkspace, OSError) as exc:
            self.show_message(f"could not open that workspace: {exc}")
            return None
        self.workspace = workspace
        self.settings.last_workspace = str(workspace.root)
        self.settings.add_recent_workspace(workspace.root)
        self.refresh_workspace()
        self.show_message(f"workspace: {workspace.root}")
        return workspace

    def restore_workspace(self) -> None:
        """Reopen the workspace that was open last, as the last
        directory is reopened."""
        last = self.settings.last_workspace
        if last and Workspace.is_workspace(last):
            self.workspace = Workspace(last)
        self.refresh_workspace()

    def refresh_workspace(self) -> None:
        self.file_dock.set_workspace(
            self.workspace, self.settings.recent_workspaces())

    def open_workspace_dialog(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Open workspace",
            self.settings.last_workspace or
            str(self.settings.default_workspace_root.parent))
        if chosen:
            self.set_workspace(chosen)

    def new_workspace_dialog(self) -> None:
        chosen = QFileDialog.getSaveFileName(
            self, "New workspace",
            str(self.settings.default_workspace_root))[0]
        if chosen:
            self.set_workspace(chosen, create=True)

    def _on_workspace_requested(self, what: str) -> None:
        """The tree's own switcher: open, new, or one of the recent."""
        if what == "open":
            self.open_workspace_dialog()
        elif what == "new":
            self.new_workspace_dialog()
        else:
            self.set_workspace(what)

    def _on_run_started(self, path: str) -> None:
        self.refresh_workspace()
        self.log_dock.show_file(Path(path) / "run.log")

    def _on_run_finished(self, path: str) -> None:
        self.refresh_workspace()
        self.log_dock.poll()

    def _on_trajectory_history(self, history) -> None:
        """A trajectory opened from the tree fills the energy plot.

        The plot and the trajectory are the same run seen two ways, so
        opening one has to populate the other -- otherwise clicking the
        trace to reach a frame only works for the run you just watched.
        """
        if history:
            self.ff_dock.plot.set_history(history)

    def open_artifact(self, kind: str, path: str) -> None:
        """Open a node of the workspace tree as what it *is*.

        Dispatch on the artefact's kind rather than on its extension:
        a ``.cif`` that is a run's output and a ``.cif`` that is the
        input want the same viewer and different labelling, which an
        extension cannot say.
        """
        target = Path(path)
        if kind == "log":
            self.log_dock.show_file(target)
        elif kind == "trajectory":
            self.trajectory_dock.set_document(self.current_document())
            self.trajectory_dock.open_path(target)
        elif kind in ("structure", "final", "project", "file"):
            self.open_path(target)

    def save_document(self) -> None:
        """Save the session.

        Save and Save As write a **project**, always.  They used to
        dispatch on the extension the user typed, so the same command
        either kept a whole working session or threw most of it away
        depending on three characters after a dot.  Writing a file for
        another program is Export, which is one way and says so.
        """
        document = self.current_document()
        if document is None:
            return
        if document.path is None or document.path.suffix != ".xtalproj":
            self.save_document_as()
            return
        try:
            document.save()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.show_message(f"saved {document.path.name}")
        self.refresh_workspace()

    def save_document_as(self) -> None:
        document = self.current_document()
        if document is None:
            return
        opened_a_structure = (document.path is not None
                              and document.path.suffix != ".xtalproj")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save project", str(self._suggested_project(document)),
            "Crystal Builder project (*.xtalproj)")
        if not path:
            return
        try:
            written = document.save(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.settings.add_recent_file(written)
        self._rebuild_recent_menu()
        document.attach_workspace()
        self.refresh_workspace()
        if opened_a_structure:
            # A behaviour change for anybody who has been opening a CIF
            # and pressing Ctrl+S, so it is made visible rather than
            # silent.
            self.show_message(
                f"wrote {written.name}; the file you opened has not "
                f"been touched -- File > Export writes one back")
        else:
            self.show_message(f"wrote {written.name}")

    def _suggested_project(self, document) -> Path:
        """Where Save As offers to put the project.

        Inside the workspace entry when there is one, because that is
        what lets a reopened project find its own workspace by looking
        upwards rather than by remembering a path that a moved folder
        would falsify.
        """
        if document.entry is not None:
            return document.entry.project_path
        base = document.path or Path(self.settings.last_directory) / \
            (document.structure.meta.get("title") or "structure")
        return Path(base).with_suffix(".xtalproj")

    def export_dialog(self) -> None:
        """One dialog for every writable format."""
        document = self.current_document()
        if document is None:
            return
        from xtalapp.dialogs.export import ExportDialog
        dialog = ExportDialog(document, self,
                              directory=self.settings.last_directory)
        if dialog.exec() != QDialog.Accepted:
            return
        target = dialog.target()
        if target is None:                          # pragma: no cover
            return
        self._export(document, target, dialog.options())

    def export_again(self) -> None:
        """Export where and how it was exported last.

        The one thing the Save/Export split costs is the quick round
        trip "open a CIF, nudge an atom, save the CIF"; this gives it
        back without blurring what Save means.
        """
        document = self.current_document()
        if document is None:
            return
        if not self._last_export:
            self.export_dialog()
            return
        path, options = self._last_export
        target = Path(path)
        if document.path is not None:
            target = target.with_name(
                document.path.stem + target.suffix)
        self._export(document, target, options)

    def _export(self, document, target, options) -> None:
        try:
            written = document.export(target, **options)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not export", str(exc))
            return
        self._last_export = (str(written), dict(options))
        self.settings.last_directory = str(written.parent)
        self.show_message(f"exported {written.name}")
        self.refresh_workspace()

    def export_image(self) -> None:
        viewport = self.current_viewport()
        if viewport is None or not hasattr(viewport, "save_image"):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export image", self.settings.last_directory,
            "PNG image (*.png)")
        if path:
            viewport.save_image(path)
            self.statusBar().showMessage(f"wrote {path}", 5000)

    def close_current(self) -> None:
        if self.tabs.currentIndex() >= 0:
            self.close_document(self.tabs.currentIndex())

    def close_document(self, index: int) -> None:
        if not 0 <= index < len(self.documents):
            return
        document = self.documents[index]
        if document.modified:
            answer = QMessageBox.question(
                self, "Unsaved changes",
                f"{document.title} has unsaved changes. Close it?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        del self.documents[index]
        widget.deleteLater()
        self._update_ui()

    # ==================================================================
    #  VIEW COMMANDS
    # ==================================================================

    def set_style(self, name: str) -> None:
        document = self.current_document()
        if document is not None:
            document.update_view(style=name)
            self.settings.set_default_view(style=name)

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

    def recompute_bonds(self) -> None:
        document = self.current_document()
        if document is not None:
            self.show_status(document.recompute_bonds())

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

    #: What a right click offers, by what was under it.  Every entry
    #: is a name in the action registry, so each one is already
    #: undoable, already has a keyboard shortcut and already appears in
    #: the menu bar -- and adding one costs a name in a list.
    CONTEXT_MENUS = {
        "atom": ["change_element", "delete_selection", None,
                 "expand_bonded", "expand_fragment", "expand_orbit",
                 "select_same", None, "copy", "cut", "duplicate", None,
                 "recompute_bonds"],
        "bond": ["delete_bond", None, "select_none", None,
                 "recompute_bonds"],
        "view": ["select_all", "select_none", None, "display_range",
                 "boundary_bonded", None, "orthographic",
                 "reset_view"],
    }

    #: The entries whose wording should say how much they will take.
    #: "Delete" and "Delete 14 atoms" are different promises, and a
    #: menu that makes the first while meaning the second is the one
    #: that loses somebody's work.
    COUNTED_ACTIONS = {"delete_selection": "Delete {n} {noun}",
                       "delete_bond": "Delete {n} {noun}"}

    def build_context_menu(self, kind: str):
        """The menu for whatever was right-clicked, or ``None``.

        Built here rather than in the viewport because the actions live
        in this window's registry -- which is what keeps a context-menu
        entry and a menu-bar entry the same object, enabled and
        disabled by the same rule.
        """
        from PySide6.QtWidgets import QMenu

        names = self.CONTEXT_MENUS.get(kind)
        if not names:
            return None
        count = self._selection_count(kind)
        noun = {"atom": "atoms", "bond": "bonds"}.get(kind, "")

        menu = QMenu(self)
        for name in names:
            if name is None:
                menu.addSeparator()
            elif name in self.COUNTED_ACTIONS and count > 1:
                self._add_counted(menu, name, count, noun)
            else:
                menu.addAction(self.actions_[name])
        if kind == "view":
            style = menu.addMenu("&Style")
            self.actions_.fill_menu(
                style, [f"style_{n}" for n in styles.names()])
        return menu

    def show_context_menu(self, kind: str, position) -> None:
        menu = self.build_context_menu(kind)
        if menu is not None:
            menu.exec(position)

    def _add_counted(self, menu, name: str, count: int, noun: str):
        """A menu entry that says what it will act on.

        A fresh action rather than the registry's own, because the
        registry's is the same object the menu bar shows: renaming it
        for one click would rename it for good.  This one carries the
        count and triggers the real thing.
        """
        action = self.actions_[name]
        entry = menu.addAction(
            self.COUNTED_ACTIONS[name].format(n=count, noun=noun))
        entry.setEnabled(action.isEnabled())
        entry.triggered.connect(action.trigger)
        return entry

    def _selection_count(self, kind: str) -> int:
        document = self.current_document()
        if document is None:
            return 0
        return {"atom": len(document.selection.atoms),
                "bond": len(document.selection.bonds)}.get(kind, 0)

    def set_mode(self, name: str) -> None:
        modes.get(name)                     # validate before switching
        viewport = self.current_viewport()
        if viewport is not None and hasattr(viewport, "set_mode"):
            viewport.set_mode(name)
        self.statusBar().showMessage(modes.get(name).hint, 6000)

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

    def delete_bonds(self) -> None:
        document = self.current_document()
        if document is not None and document.selection.bonds:
            self.show_status(document.delete_selected_bonds())

    def delete_selection(self) -> None:
        """Delete whatever is in hand.

        One key for both: bonds when bonds are what is selected, sites
        otherwise.  Clicking a bond and pressing delete should delete
        the bond, and the alternative -- a second key, or a mode -- is
        how the application ended up with deletion living inside a tool
        called Add Bond.
        """
        document = self.current_document()
        if document is None:
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
        self._run(lambda d: d.merge_duplicates())

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

    def show_force_field(self) -> None:
        self.ff_dock.show()
        self.ff_dock.raise_()

    def single_point_energy(self) -> None:
        self.show_force_field()
        self.ff_dock.single_point()

    def optimize_geometry(self) -> None:
        self.show_force_field()
        self.ff_dock.start()

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
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "copy", "cut",
             "duplicate", "select_same"],
            bool(document.selection.atoms or document.selection.bonds))
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "select_same",
             "expand_bonded", "expand_fragment", "expand_orbit",
             "copy", "cut", "duplicate"],
            bool(document.selection.atoms))

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

        if not positions_only:
            self.info_dock.show_document(document)
            self.style_dock.refresh()
            self.ff_dock.refresh()
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

    def _update_ui(self, *_args) -> None:
        document = self.current_document()
        self.info_dock.show_document(document)
        self.inspector_dock.set_document(document)
        self.sites_dock.set_document(document)
        self.move_dock.set_document(document)
        self.style_dock.set_document(document)
        self.measure_dock.set_document(document)
        self.ff_dock.set_document(document)
        self.trajectory_dock.set_document(document)
        self._rebuild_element_menu(document)
        self._refresh_shell()

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
            ["reduce_p1", "paste", "add_atom_dialog",
             "find_symmetry", "set_space_group", "standardize",
             "primitive", "wyckoff", "merge_duplicates", "supercell",
             "edit_cell", "niggli", "delaunay", "wrap_cell",
             "single_point", "optimize", "recompute_bonds"],
            editable)
        if document is None:
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
            ["delete_selection", "change_element", "cut", "duplicate"],
            has_selection and editable)
        self.status_label.setText(document.status_text())
        self.setWindowTitle(f"{document.title} — {APP_NAME}")
        name = f"style_{document.view.style}"
        if name in self.actions_:
            self.actions_[name].setChecked(True)
        for action, value in (("show_atoms", document.view.show_atoms),
                              ("show_bonds", document.view.show_bonds),
                              ("show_cell", document.view.show_cell),
                              ("show_legend",
                               document.view.show_legend)):
            widget = self.actions_[action]
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        viewport = self.current_viewport()
        mode = getattr(viewport, "mode", None)
        if mode is not None and f"mode_{mode.name}" in self.actions_:
            self.actions_[f"mode_{mode.name}"].setChecked(True)
        for spin, value in zip(self.cell_spins, document.view.cells,
                               strict=True):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

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
        for document in list(self.documents):
            if document.modified:
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
