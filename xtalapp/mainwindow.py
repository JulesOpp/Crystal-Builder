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
from xtal.io import FORMATS
from xtalapp.actions import ActionRegistry
from xtalapp.dialogs.add_atom import AddAtomDialog
from xtalapp.dialogs.cell_edit import CellEditDialog
from xtalapp.dialogs.display_range import DisplayRangeDialog
from xtalapp.dialogs.find_symmetry import FindSymmetryDialog
from xtalapp.dialogs.spacegroup import SpaceGroupDialog
from xtalapp.dialogs.supercell import SupercellDialog
from xtalapp.docks.ff_panel import ForceFieldDock
from xtalapp.docks.filetree import FileTreeDock
from xtalapp.docks.info import InfoDock
from xtalapp.docks.inspector import InspectorDock
from xtalapp.docks.measure import MeasureDock
from xtalapp.docks.move import MoveDock
from xtalapp.docks.sites import SitesDock
from xtalapp.docks.style_panel import StylePanelDock
from xtalapp.document import Document
from xtalapp.settings import AppSettings
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
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        self.settings = settings or AppSettings()
        self._viewport_factory = (viewport_factory
                                  or _default_viewport_factory)
        self.documents: list[Document] = []
        self.clipboard_fragment = Fragment()

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
        add("save", "&Save", self.save_document, "Ctrl+S")
        add("save_as", "Save &As...", self.save_document_as,
            "Ctrl+Shift+S")
        add("save_project", "Save &Project...", self.save_project,
            "Ctrl+Shift+P",
            tip="Save the structure together with how it is being "
                "viewed, what is selected and what you have measured")
        add("export_p1", "Export as P1 CIF...", self.export_p1)
        add("export_image", "Export &Image...", self.export_image)
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
            "Del", tip="Delete the selected sites")
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

        add("reset_view", "&Reset view", self.reset_view, "Ctrl+0")
        add("view_a", "Along &a", lambda: self.look_along(0), "1")
        add("view_b", "Along &b", lambda: self.look_along(1), "2")
        add("view_c", "Along &c", lambda: self.look_along(2), "3")
        add("about", f"About {APP_NAME}", self.show_about)

    def _build_menus(self):
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self.actions_.fill_menu(file_menu, [
            "new", "open", None, "save", "save_as", "save_project",
            None, "export_p1", "export_image", None, "close_tab"])
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.actions_["quit"])

        edit_menu = bar.addMenu("&Edit")
        self.actions_.fill_menu(edit_menu, [
            "undo", "redo", None, "cut", "copy", "paste", "duplicate",
            None, "delete_selection", "change_element"])

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
        self.file_dock = FileTreeDock(self.settings.last_directory,
                                      self)
        self.file_dock.fileActivated.connect(self.open_path)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.file_dock)

        self.inspector_dock = InspectorDock(self)
        self.inspector_dock.deleteRequested.connect(
            self.delete_selection)
        self.inspector_dock.reduceToP1Requested.connect(
            self.reduce_to_p1)
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspector_dock)

        self.info_dock = InfoDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)

        self.sites_dock = SitesDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.sites_dock)

        self.move_dock = MoveDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.move_dock)

        self.style_dock = StylePanelDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.style_dock)

        self.measure_dock = MeasureDock(self)
        self.measure_dock.targetChanged.connect(self._on_measure_target)
        self.addDockWidget(Qt.RightDockWidgetArea, self.measure_dock)

        self.ff_dock = ForceFieldDock(self)
        # Connected to a method, not to the label: the docks are built
        # before the status bar exists.
        self.ff_dock.statusMessage.connect(self.show_status)
        self.addDockWidget(Qt.RightDockWidgetArea, self.ff_dock)

        # Three panels compete for the right-hand side; tabbing them
        # keeps the viewport wide by default.
        self.tabifyDockWidget(self.inspector_dock, self.info_dock)
        self.tabifyDockWidget(self.info_dock, self.sites_dock)
        self.tabifyDockWidget(self.sites_dock, self.move_dock)
        self.tabifyDockWidget(self.move_dock, self.style_dock)
        self.tabifyDockWidget(self.style_dock, self.measure_dock)
        self.tabifyDockWidget(self.measure_dock, self.ff_dock)
        self.inspector_dock.raise_()

        window_menu = self.menuBar().addMenu("&Window")
        for dock in (self.file_dock, self.inspector_dock,
                     self.info_dock, self.sites_dock, self.move_dock,
                     self.style_dock, self.measure_dock,
                     self.ff_dock):
            window_menu.addAction(dock.toggleViewAction())

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
        viewport = self._viewport_factory(document, self.tabs)
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
        if hasattr(viewport, "statusMessage"):
            viewport.statusMessage.connect(
                lambda text: self.statusBar().showMessage(text, 4000))
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
        if document.warnings:
            self.statusBar().showMessage(
                f"opened with {len(document.warnings)} warning(s)", 8000)
        return document

    def save_document(self) -> None:
        document = self.current_document()
        if document is None:
            return
        if document.path is None:
            self.save_document_as()
            return
        try:
            document.save()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))

    def save_document_as(self) -> None:
        document = self.current_document()
        if document is None:
            return
        filters = [f.filter_string() for f in FORMATS.writable()]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save structure", self.settings.last_directory,
            ";;".join(filters))
        if not path:
            return
        try:
            document.save(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.settings.add_recent_file(path)
        self._rebuild_recent_menu()

    def save_project(self) -> None:
        """Write everything: the crystal, the view, the session.

        Saving as a CIF keeps the structure and drops the rest, which
        is the honest behaviour for an interchange format; this is the
        one that keeps a working session whole.
        """
        document = self.current_document()
        if document is None:
            return
        suggested = str((document.path or Path(self.settings
                                               .last_directory))
                        .with_suffix(".xtalproj"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save project", suggested,
            "Crystal Builder project (*.xtalproj)")
        if not path:
            return
        try:
            written = document.save_project(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.settings.add_recent_file(written)
        self._rebuild_recent_menu()
        self.statusBar().showMessage(f"wrote {written}", 5000)

    def export_p1(self) -> None:
        """Export with every symmetry-generated atom written out."""
        document = self.current_document()
        if document is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as P1 CIF", self.settings.last_directory,
            "Crystallographic Information File (*.cif)")
        if path:
            document.export(path, expand_to_p1=True)
            self.statusBar().showMessage(f"exported {path}", 5000)

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
        undo.setEnabled(document.can_undo)
        redo.setEnabled(document.can_redo)
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

    def delete_selection(self) -> None:
        """Delete the selected sites, asking first when symmetry means
        more atoms go than were selected."""
        document = self.current_document()
        if document is None or not document.selection.atoms:
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
        self.status_label.setText(text)

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

    def _on_structure_changed(self, _change: int = 0) -> None:
        """The crystal changed: the panels that show it must catch
        up.  The view panels must not -- rebuilding a site table
        because a spinbox moved is where a large structure loses its
        responsiveness."""
        document = self.current_document()
        if document is None:
            return
        self.info_dock.show_document(document)
        self.inspector_dock.refresh()
        self.sites_dock.refresh()
        self.move_dock.refresh()
        self.style_dock.refresh()
        self.ff_dock.refresh()
        self._rebuild_element_menu(document)
        self._update_ui()

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
        self._rebuild_element_menu(document)
        self._refresh_shell()

    def _refresh_shell(self) -> None:
        """Menus, toolbar and status bar for the current document."""
        document = self.current_document()
        has_document = document is not None
        self.actions_.set_enabled(
            ["save", "save_as", "save_project", "export_p1",
             "export_image", "close_tab", "reset_view", "view_a",
             "view_b", "view_c"],
            has_document)
        self._update_history_actions()
        self.actions_.set_enabled(
            ["select_all", "select_none", "invert_selection",
             "reduce_p1", "paste", "add_atom_dialog",
             "find_symmetry", "set_space_group", "standardize",
             "primitive", "wyckoff", "merge_duplicates", "supercell",
             "edit_cell", "niggli", "delaunay", "wrap_cell",
             "display_range", "single_point", "optimize"],
            has_document)
        if document is None:
            self.status_label.setText("No structure open")
            self.selection_label.setText("")
            self.setWindowTitle(APP_NAME)
            return
        self.selection_label.setText(document.selection_summary())
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "select_same",
             "expand_bonded", "expand_fragment", "expand_orbit",
             "copy", "cut", "duplicate"],
            bool(document.selection.atoms))
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
