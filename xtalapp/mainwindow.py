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
    QMenu,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QToolBar,
)

from xtal.commands.bonds import BOND_TYPES
from xtal.commands.clipboard import Fragment
from xtal.core.structure import Change
from xtal.io import FORMATS
from xtal.modules import MODULES, Job, ModuleError
from xtal.modules import record as module_record
from xtal.workspace import NotAWorkspace, Workspace, safe_name
from xtalapp.actions import ActionRegistry
from xtalapp.dialogs.add_atom import AddAtomDialog
from xtalapp.dialogs.add_hydrogens import AddHydrogensDialog
from xtalapp.dialogs.bond_rules import BondRulesDialog
from xtalapp.dialogs.cell_edit import CellEditDialog
from xtalapp.dialogs.display_range import DisplayRangeDialog
from xtalapp.dialogs.find_symmetry import FindSymmetryDialog
from xtalapp.dialogs.module_form import ModuleDialog
from xtalapp.dialogs.run_progress import RunProgressDialog
from xtalapp.dialogs.spacegroup import SpaceGroupDialog
from xtalapp.dialogs.subgroup import SubgroupDialog
from xtalapp.dialogs.supercell import SupercellDialog
from xtalapp.docks.ff_panel import ForceFieldDock
from xtalapp.docks.info import InfoDock
from xtalapp.docks.inspector import InspectorDock
from xtalapp.docks.logview import LogDock
from xtalapp.docks.measure import MeasureDock
from xtalapp.docks.modules import ModulesDock
from xtalapp.docks.move import MoveDock
from xtalapp.docks.results import ResultsDock
from xtalapp.docks.sites import SitesDock
from xtalapp.docks.style_panel import StylePanelDock
from xtalapp.docks.trajectory import TrajectoryDock
from xtalapp.docks.workspace import WorkspaceDock
from xtalapp.document import Document
from xtalapp.histogram import save_histogram
from xtalapp.settings import AppSettings, default_size, fit_to_screen
from xtalapp.viewport import modes, styles
from xtalapp.viewport.view_settings import BACKGROUNDS
from xtalapp.workers import ModuleWorker, start_in_thread

APP_NAME = "Crystal Builder"


def _resolved(path):
    """A path as the filesystem knows it, or ``None``.

    ``None`` for a document that has never been saved, and for a path
    that cannot be resolved at all -- a volume that went away, a
    permission that was withdrawn.  Both are "not the file you are
    asking about", which is the answer the caller wants.
    """
    if path is None:
        return None
    try:
        return Path(path).resolve()
    except OSError:                                 # pragma: no cover
        return None


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
        # The one module run that may be going, and what each action
        # was last run with.  Remembered in the window rather than in
        # QSettings: a parameter set is worth offering again in the
        # session that chose it, and not worth restoring six weeks
        # later against a different structure.
        self.module_worker: ModuleWorker | None = None
        self._module_thread = None
        self._module_params: dict = {}
        self._module_actions: list[tuple] = []
        self._module_submenus: dict = {}

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
        add("show_bond_orders", "Bond orders",
            lambda v: self.set_view(show_bond_orders=v),
            checkable=True, checked=True,
            tip="Draw a double bond as two tubes and a triple as "
                "three, with an inner dashed line for an aromatic "
                "one")
        add("labels", "Labels",
            lambda v: self.set_view(
                label_mode="label" if v else "none"), checkable=True)
        add("show_topology", "Net (topology bonds)",
            lambda v: self.set_view(show_topology=v), checkable=True,
            checked=True,
            tip="Draw the net a chemist marked out over the framework "
                "-- thicker and translucent, over the real bonds "
                "rather than in place of them")
        add("depth_cue", "Depth cueing",
            lambda v: self.set_view(depth_cue=v), checkable=True,
            tip="Fade distant atoms towards the background, so a "
                "thick slab reads as having depth instead of as a "
                "flat mat of spheres")
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
        add("add_hydrogens", "Add &hydrogens...",
            self.add_hydrogens_dialog,
            tip="Complete every main-group coordination with the "
                "hydrogens an X-ray structure never had")
        add("recompute_bonds", "&Recalculate bonds",
            self.recompute_bonds, "Ctrl+B",
            tip="Perceive the bonds again from the geometry as it is "
                "now.  Bonds do not change on their own when atoms "
                "move; this is what changes them.")
        add("reset_bonds", "Reset bonds to a&utomatic",
            self.reset_bonds,
            tip="Drop the bonds you drew and the ones you deleted, "
                "and take what the distance criteria give.  The only "
                "way back from a deleted bond once the undo stack has "
                "gone, because a deletion is saved with the project.")
        add("bond_rules", "&Bond rules...", self.edit_bond_rules,
            tip="Which atoms bond, and how close they have to be")
        # One action per bond type, in an exclusive group: the menu
        # shows what the selected bonds already are, and picking a
        # different one is the edit.  Automatic is in the same group
        # because "no stated order" is a state a bond can be in, not
        # the absence of one.
        for type_name, order in BOND_TYPES:
            add(f"bond_type_{type_name.lower()}", f"&{type_name}",
                lambda checked=False, o=order: self.set_bond_type(o),
                checkable=True, group="bond_type",
                tip=("Let the geometry decide this bond's order again"
                     if order is None else
                     f"Call the selected bonds {type_name.lower()}, "
                     f"and their whole symmetry orbit with them"))
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

        add("define_plane", "Define &plane from selection",
            self.define_plane, "Ctrl+Shift+P",
            tip="Fit a plane through the selected atoms: exactly "
                "through three, least-squares through more")
        add("plane_angle", "&Angle between planes",
            self.measure_plane_angles,
            tip="Measure the angle between the planes defined so far "
                "-- one measurement per pair")
        add("clear_planes", "Clear pl&anes", self.clear_planes)
        add("clear_measurements", "Clear &measurements",
            self.clear_measurements)

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
        add("subgroup", "&Descend to a subgroup...",
            self.descend_to_subgroup,
            tip="Drop to a maximal subgroup so that an orbit splits "
                "and its atoms become independent")
        add("invert", "&Invert the structure", self.invert_structure,
            tip="The same crystal in the other hand: the coordinates "
                "and the space group together")
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
            "add_atom_dialog", "add_hydrogens", None,
            "bond_rules", "recompute_bonds", "reset_bonds",
            "bonds_follow"])
        self.bond_type_menu = self._add_bond_type_menu(structure_menu)
        structure_menu.addSeparator()
        self.actions_.fill_menu(structure_menu,
                                [f"mode_{n}" for n in modes.names()])

        measure_menu = bar.addMenu("&Measure")
        self.actions_.fill_menu(measure_menu, [
            "define_plane", "plane_angle", None,
            "clear_planes", "clear_measurements"])

        symmetry_menu = bar.addMenu("S&ymmetry")
        self.actions_.fill_menu(symmetry_menu, [
            "find_symmetry", "set_space_group", "subgroup", None,
            "standardize", "primitive", None,
            "wyckoff", "merge_duplicates", "invert",
            None, "reduce_p1"])

        cell_menu = bar.addMenu("&Cell")
        self.actions_.fill_menu(cell_menu, [
            "edit_cell", "supercell", None,
            "niggli", "delaunay", None, "wrap_cell"])

        self.modules_menu = bar.addMenu("&Modules")
        self._build_modules_menu()

        view_menu = bar.addMenu("&View")
        style_menu = view_menu.addMenu("&Style")
        self.actions_.fill_menu(
            style_menu, [f"style_{n}" for n in styles.names()])
        show_menu = view_menu.addMenu("&Show")
        self.actions_.fill_menu(
            show_menu, ["show_atoms", "show_bonds", "show_bond_orders",
                        "show_topology", "show_cell", "labels",
                        "show_legend"])
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
            "depth_cue",
            None, "view_a", "view_b", "view_c", "reset_view"])

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.actions_["about"])

    def _build_modules_menu(self) -> None:
        """The Modules menu, built from the registry and nothing else.

        ``Calculate`` held a single point, an optimisation and a panel
        toggle -- three entries that were all UFF, in a menu whose name
        promised everything that computes.  This one has a submenu per
        module and knows the name of none of them, so a module
        installed as a plugin appears here without this file changing.

        The structure is built once; whether each module *can* run is
        asked again every time the menu opens
        (:meth:`_refresh_module_availability`), because an engine whose
        binary was installed while the window was open should stop
        being greyed out, and a menu that cached the answer would go on
        saying it is missing.
        """
        menu = self.modules_menu
        menu.clear()
        self._module_actions = []
        self._module_submenus = {}
        for module in MODULES:
            submenu = menu.addMenu(module.label)
            self._module_submenus[module.name] = submenu
            for action in module.actions:
                submenu.addAction(self._module_action(module, action))
        if not MODULES.names():                     # pragma: no cover
            menu.addAction("Nothing registered").setEnabled(False)
        menu.aboutToShow.connect(self._refresh_module_availability)
        self._refresh_module_availability()

    def _refresh_module_availability(self) -> None:
        """Grey out what cannot run, with the reason as the tooltip.

        An external tool that is missing is the most common state it
        will be in, so the answer belongs where the module is rather
        than in the failure after clicking it.  ``Module.check`` is a
        ``shutil.which`` and there are a handful of modules, so asking
        again on every open costs nothing worth caching.
        """
        for name, submenu in self._module_submenus.items():
            if name not in MODULES:                 # pragma: no cover
                continue
            module = MODULES.get(name)
            available = module.availability()
            submenu.setEnabled(bool(available))
            submenu.setToolTip(module.description if available
                               else available.reason)

    def _module_action(self, module, action):
        """The QAction for one module entry, made once and reused.

        An entry with a ``shell`` name is performed by the window
        action of that name -- which is how the three Force Field
        entries moved into this menu unchanged, keeping Ctrl+E and
        Ctrl+Shift+E and the panel behind them.  Everything else gets
        an action of its own, named ``module.<module>.<action>`` so
        that a keyboard shortcut, a test and the CLI all spell it the
        same way.
        """
        if action.shell and action.shell in self.actions_:
            return self.actions_[action.shell]
        name = f"module.{module.name}.{action.name}"
        self._module_actions.append((name, action.needs_structure))
        if name not in self.actions_:
            self.actions_.add(
                name, action.label,
                lambda checked=False, m=module.name, a=action.name:
                    self.run_module_action(m, a),
                shortcut=action.shortcut, tip=action.tip)
        return self.actions_[name]

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

        # What can be run, beside what it produced: the module tree
        # picks the calculation and the workspace tree shows its
        # folder appearing underneath the structure.  Those two panels
        # next to each other are the whole workflow.
        self.modules_dock = ModulesDock(MODULES, self)
        self.modules_dock.actionActivated.connect(
            self.run_module_action)
        self.modules_dock.stopRequested.connect(self.stop_module)

        self.inspector_dock = InspectorDock(self)
        self.inspector_dock.deleteRequested.connect(
            self.delete_selection)
        self.inspector_dock.reduceToP1Requested.connect(
            self.reduce_to_p1)

        self.info_dock = InfoDock(self)
        self.sites_dock = SitesDock(self)
        self.move_dock = MoveDock(self)
        self.move_dock.statusMessage.connect(self.show_status)
        self.style_dock = StylePanelDock(self)

        self.measure_dock = MeasureDock(self)
        self.measure_dock.targetChanged.connect(self._on_measure_target)
        self.measure_dock.statusMessage.connect(self.show_status)

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

        # A run that takes minutes needs to say so somewhere the user
        # is looking, which the footer of a panel that may be closed
        # is not.  It arms itself and appears only if the run is still
        # going a moment later, so a fast module never shows one.
        self.run_progress = RunProgressDialog(self)
        self.run_progress.stopRequested.connect(self.stop_module)

        # Where a module's tables and histograms land.  Beside the
        # log rather than beside the module tree: the numbers and the
        # output that produced them are read together, and a report
        # squeezed into the width of a tree is a report nobody reads.
        self.results_dock = ResultsDock(self)

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
        self.left_docks = (self.file_dock, self.modules_dock)
        self.bottom_docks = (self.trajectory_dock, self.log_dock,
                             self.results_dock)
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

    #: What a first run shows: what can be run and what it produced,
    #: on the left, and the inspector on the right.  Every other panel
    #: is one item away in the Window menu; seven of them tabbed on
    #: the right take, between them, the width the viewport is there
    #: to use.
    DEFAULT_VISIBLE = ("file_dock", "modules_dock", "inspector_dock")

    def apply_default_layout(self) -> None:
        """Put every dock back where it starts: the two trees on the
        left, the rest tabbed on the right, and only three of them
        shown.

        Called once on construction -- ``restore_window`` overrides it
        when there is a saved layout -- and again by Reset layout.

        The workspace and the module tree are *split* rather than
        tabbed: they answer the two halves of one question -- what can
        I run, and what did it produce -- and tabbing them would mean
        never seeing both.
        """
        for dock in self.left_docks:
            self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        for dock in self.right_docks:
            self.addDockWidget(Qt.RightDockWidgetArea, dock)
        for dock in self.bottom_docks:
            self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        # The transport bar, the log and the report are three views of
        # one run and share the strip under the viewport.
        for previous, dock in zip(self.bottom_docks,
                                  self.bottom_docks[1:], strict=False):
            self.tabifyDockWidget(previous, dock)
        for previous, dock in zip(self.right_docks,
                                  self.right_docks[1:], strict=False):
            self.tabifyDockWidget(previous, dock)
        self.splitDockWidget(self.file_dock, self.modules_dock,
                             Qt.Vertical)

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
        document.planesChanged.connect(self._on_planes_changed)
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
        already = self.document_for(path)
        if already is not None:
            # Not a dialog and not a refusal: the user asked to see
            # that file, and showing it to them is the answer.  A
            # second tab over the same bytes would be two documents
            # with two undo stacks editing what the user thinks is one
            # structure, and whichever was saved last would win.
            self.tabs.setCurrentIndex(self.documents.index(already))
            self.show_message(f"{path.name} is already open")
            return already
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

    def document_for(self, path) -> Document | None:
        """The open document that came from this file, or ``None``.

        The test is the **resolved** path -- same location and same
        name -- and not the file name alone: ``data/a/MFU4l.cif`` and
        ``data/b/MFU4l.cif`` are two different crystals that happen to
        share a name, and treating the second as the first would be
        worse than the bug this exists to fix.  Resolving also settles
        the symlink and the ``/var`` versus ``/private/var`` cases,
        which are one file spelled two ways.

        Asked here rather than in each caller because
        :meth:`open_path` is the one door every route in goes through:
        the Open dialog, the recent list, the workspace tree, drag and
        drop and the command line.
        """
        wanted = _resolved(path)
        if wanted is None:
            return None
        for document in self.documents:
            if _resolved(document.path) == wanted:
                return document
        return None

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
        elif kind == "image":
            # A plot a run left behind.  Handed to whatever the
            # desktop opens PNGs with, because a picture viewer is not
            # something this application should be growing.
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            if not QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(target))):
                self.show_message(                  # pragma: no cover
                    f"could not open {target.name}")
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

    def reset_bonds(self) -> None:
        """Throw away the bond edits and perceive again.

        Separate from Recalculate because the two answer different
        questions: recalculating asks the geometry, resetting also
        withdraws every answer the user has given -- which is why it
        is a menu entry and not what Ctrl+B quietly does.
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

    #: What a right click offers, by what was under it.  Every entry
    #: is a name in the action registry, so each one is already
    #: undoable, already has a keyboard shortcut and already appears in
    #: the menu bar -- and adding one costs a name in a list.
    CONTEXT_MENUS = {
        "atom": ["change_element", "delete_selection", None,
                 "expand_bonded", "expand_fragment", "expand_orbit",
                 "select_same", None, "copy", "cut", "duplicate", None,
                 "recompute_bonds"],
        "bond": ["delete_bond", BOND_TYPE_MENU, None, "select_none",
                 None, "recompute_bonds"],
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
        names = self.CONTEXT_MENUS.get(kind)
        if not names:
            return None
        count = self._selection_count(kind)
        noun = {"atom": "atoms", "bond": "bonds"}.get(kind, "")

        menu = QMenu(self)
        for name in names:
            if name is None:
                menu.addSeparator()
            elif name == self.BOND_TYPE_MENU:
                self._add_bond_type_menu(menu)
            elif name in self.COUNTED_ACTIONS and count > 1:
                self._add_counted(menu, name, count, noun)
            else:
                menu.addAction(self.actions_[name])
        if kind == "view":
            style = menu.addMenu("&Style")
            self.actions_.fill_menu(
                style, [f"style_{n}" for n in styles.names()])
        return menu

    def _add_bond_type_menu(self, menu):
        """The Set Bond Type submenu, wherever it is wanted.

        The same five actions in both places, so the context menu and
        the menu bar are enabled by the same rule and show the same
        tick -- which is the whole reason the actions live in the
        registry rather than being built where they are shown.
        """
        # Parented to the menu it is added to, so the menu owns it:
        # a submenu built by ``addMenu(title)`` alone is owned by
        # Python, and the one in a context menu is collected the moment
        # this method returns.
        submenu = QMenu("Set Bond &Type", menu)
        menu.addMenu(submenu)
        submenu.setEnabled(self.actions_["bond_type_single"].isEnabled())
        self.actions_.fill_menu(
            submenu, [f"bond_type_{n.lower()}" for n, _ in BOND_TYPES])
        return submenu

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

    def define_plane(self) -> None:
        """A plane through the selected atoms."""
        document = self.current_document()
        if document is not None:
            self.show_status(document.define_plane())

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
        self._run(lambda d: d.merge_duplicates())

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
    # One run at a time, on a worker thread, into a run folder, with a
    # Stop button that reaches whatever is actually running -- a loop
    # in this process or a binary in another.  Nothing here names a
    # module: everything it needs comes off the registry entry, which
    # is what "adding an engine touches no existing file" means.

    def run_module_action(self, module_name: str,
                          action_name: str) -> None:
        """Run one entry of one module.

        Ask for the parameters, open a run folder under the structure
        the run belongs to, and start a thread.  The three Force Field
        entries divert to the panel that has always performed them --
        see :mod:`xtal.modules.forcefield` for why that is the one
        exception rather than the pattern.
        """
        try:
            module, action = MODULES.find(
                f"{module_name}.{action_name}")
        except ModuleError as exc:
            self.show_message(str(exc))
            return
        if action.shell:
            shell_action = self.actions_.get(action.shell)
            if shell_action is None:                # pragma: no cover
                self.show_message(
                    f"{module.label} cannot do that here")
            elif not shell_action.isEnabled():
                self.show_message(
                    f"{action.label} is not available right now")
            else:
                shell_action.trigger()
            return
        if self.module_worker is not None:
            self.show_message(
                "a module is already running -- stop it first")
            return
        available = module.availability()
        if not available:
            self.show_message(available.reason)
            return
        document = self.current_document()
        if action.needs_structure and document is None:
            self.show_message(
                f"{action.label} needs a structure open")
            return
        if document is not None and document.is_playing:
            # The atoms are showing a frame of a trajectory, so the
            # geometry a module would be handed is not the document's.
            # The menu entries are already disabled; this is what
            # stops the tree reaching it.
            self.show_message(
                "close the trajectory first -- these atoms are a "
                "frame being played, not the structure")
            return
        key = f"{module.name}.{action.name}"
        values = ModuleDialog.ask(module, action, self,
                                  self._module_params.get(key))
        if values is None:                          # cancelled
            return
        self._module_params[key] = values
        self._start_module(module, action, values, document)

    def _start_module(self, module, action, values, document) -> None:
        folder = None
        if action.writes_run_folder and document is not None:
            try:
                folder = module_record.open_run(
                    document.entry, module, action, values,
                    document.structure)
            except OSError as exc:
                self.show_message(
                    f"could not write into the workspace: {exc}")
                return
        if folder is None and action.writes_run_folder:
            # Same rule as the Force Field panel: a structure with no
            # workspace still runs, it just leaves nothing behind, and
            # the status bar says so once rather than putting up a
            # dialog.
            self.show_message(
                "no workspace open, so this run will not be kept -- "
                "File > New Workspace... gives it somewhere to go")
        # The worker gets a copy of the structure.  It reads it, caches
        # on it and may move it, while the window goes on redrawing the
        # one the user can see; sharing them would be a data race in
        # the most literal sense.
        job = Job(structure=document.structure.copy()
                  if document is not None else None,
                  params=values, folder=folder,
                  label=f"{module.name}.{action.name}")
        worker = ModuleWorker(module, action, job)
        worker.progressed.connect(self.modules_dock.set_progress)
        worker.progressed.connect(self.run_progress.set_progress)
        worker.finished.connect(self._on_module_finished)
        worker.failed.connect(self._on_module_failed)
        self.module_worker = worker
        self.modules_dock.set_running(worker.label)
        self.run_progress.start(worker.label)
        self._refresh_shell()
        if folder is not None:
            self.refresh_workspace()
            self.log_dock.show_file(folder.path / "run.log")
        # Parented to the window, so the thread outlives this
        # method's reference to it whatever Python does with the
        # attribute below.
        self._module_thread = start_in_thread(worker, self)

    def stop_module(self) -> None:
        """Stop whatever the module tree started.

        For an in-process job this is a flag it looks at between units
        of work; for an external one it is a signal to the process.
        The button does not have to know which.
        """
        if self.module_worker is not None:
            self.module_worker.cancel()
            self.show_message("stopping...")

    def _on_module_finished(self, result) -> None:
        worker, job = self._finish_module()
        # The pictures are written before the log is closed, so the
        # log can name them the way it names every other artefact.
        self._save_report_images(job, result)
        module_record.close_run(job.folder if job else None, result)
        self._show_report(worker, result)
        if result.structure is not None:
            self._adopt_module_structure(worker, result)
        self.run_progress.finish()
        self.modules_dock.set_idle(result.summary())
        self._refresh_shell()
        self.show_status(result.summary())
        if result.detail:
            self.show_message(result.detail.splitlines()[0])
        self._after_module_run(job)

    def _on_module_failed(self, message: str) -> None:
        """A module that raised.

        Reported where the run was started from and written into the
        log that is already open, rather than into a dialog that has
        to be dismissed before the log can be read.
        """
        _worker, job = self._finish_module()
        module_record.close_run(job.folder if job else None,
                                error=message)
        # The previous run's numbers must not sit there under this
        # run's heading, which is the one way this panel could be
        # worse than no panel.
        self.run_progress.finish()
        self.results_dock.clear()
        self.modules_dock.set_idle(f"failed: {message}")
        self._refresh_shell()
        self.show_status(f"the module failed: {message}")
        self._after_module_run(job)

    def _show_report(self, worker, result) -> None:
        """Put a module's tables and histograms where they can be read.

        Raised only when there is something in it.  A panel that
        appears after every run -- including the ones whose whole
        answer is a sentence -- is one people learn to close, and then
        the one run that had a histogram in it goes unseen.
        """
        report = getattr(result, "report", None)
        label = worker.label if worker is not None else ""
        self.results_dock.show_report(report, label)
        if report:
            self.results_dock.show()
            self.results_dock.raise_()

    def _save_report_images(self, job, result) -> None:
        """Write a run's histograms into its folder as PNGs.

        The picture is the answer for a pore size distribution, and a
        run folder holding four columns of numbers and no plot is one
        somebody has to reopen the application to look at.  Drawn here
        rather than by the module because the drawing is Qt's and the
        module is headless -- and a failure to write one must never
        cost the run, which has already succeeded.
        """
        report = getattr(result, "report", None)
        if job is None or job.folder is None or not report:
            return
        written = []
        for index, histogram in enumerate(report.histograms):
            name = safe_name(histogram.title or f"plot-{index + 1}",
                             f"plot-{index + 1}").lower()
            try:
                written.append(save_histogram(
                    histogram, job.folder.path / f"{name}.png"))
            except Exception as exc:                # noqa: BLE001
                self.show_message(f"could not write the plot: {exc}")
                return
        if written:
            result.artifacts = tuple(result.artifacts) + tuple(written)

    def _finish_module(self):
        """Let go of the run, but not of the thread it was on.

        The worker signals ``finished`` from inside ``run``, so at
        this point the thread has not stopped yet.  It is parented to
        the window and Qt deletes it when it has -- nothing here may
        touch its lifetime, because destroying a ``QThread`` that is
        still running aborts the process rather than raising anything
        catchable.
        """
        worker = self.module_worker
        job = worker.job if worker is not None else None
        self.module_worker = None
        return worker, job

    def _after_module_run(self, job) -> None:
        """The workspace has changed and the log has stopped growing.

        The tree is read from the directory on every refresh, so this
        is the whole of keeping it in step with what just happened.
        """
        if job is not None and job.folder is not None:
            self.refresh_workspace()
            self.log_dock.poll()
        self.modules_dock.refresh()

    def _adopt_module_structure(self, worker, result) -> None:
        """Take a geometry a module produced, as one undoable edit.

        The module worked on a copy, so this is the only point at
        which anything it did reaches the document -- and it reaches
        it as a single command, so Ctrl+Z afterwards gives back the
        structure the run started from.
        """
        document = self.current_document()
        if document is None or document.is_playing:
            self.show_message(
                "the module produced a structure, and it was not "
                "adopted because the document it ran against is no "
                "longer in front")
            return
        label = f"{worker.module.label}: {worker.action.label}" \
            if worker is not None else "Module result"
        document.replace_structure(result.structure,
                                   label.rstrip("."), Change.ALL)

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
        self._sync_bond_type_actions(document)
        self._refresh_plane_actions()
        self.measure_dock.refresh_planes()
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "copy", "cut",
             "duplicate", "select_same"],
            bool(document.selection.atoms or document.selection.bonds))
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "select_same",
             "expand_bonded", "expand_fragment", "expand_orbit",
             "copy", "cut", "duplicate"],
            bool(document.selection.atoms))

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
        """A plane needs three atoms and an angle needs two planes, so
        neither entry is offered before there is anything to do."""
        document = self.current_document()
        self.actions_.set_enabled(
            ["define_plane"],
            document is not None and len(document.selection.atoms) >= 3)
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
        self._refresh_plane_actions()

    def _on_planes_changed(self) -> None:
        self.measure_dock.refresh_planes()
        self._refresh_plane_actions()

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
            ["reduce_p1", "paste", "add_atom_dialog", "add_hydrogens",
             "find_symmetry", "set_space_group", "standardize",
             "primitive", "wyckoff", "merge_duplicates", "subgroup",
             "invert", "supercell",
             "edit_cell", "niggli", "delaunay", "wrap_cell",
             "single_point", "optimize", "recompute_bonds",
             "reset_bonds"],
            editable)
        if document is None:
            self._refresh_module_actions(False)
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
            ["delete_selection", "change_element", "cut", "duplicate"],
            has_selection and editable)
        self._refresh_module_actions(editable)
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
                              ("depth_cue", document.view.depth_cue)):
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
