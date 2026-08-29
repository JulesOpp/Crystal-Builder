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
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QToolBar,
)

from xtal.io import FORMATS
from xtalapp.actions import ActionRegistry
from xtalapp.docks.filetree import FileTreeDock
from xtalapp.docks.info import InfoDock
from xtalapp.docks.inspector import InspectorDock
from xtalapp.docks.sites import SitesDock
from xtalapp.document import Document
from xtalapp.settings import AppSettings
from xtalapp.viewport import styles
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

        add("reset_view", "&Reset view", self.reset_view, "Ctrl+0")
        add("view_a", "Along &a", lambda: self.look_along(0), "1")
        add("view_b", "Along &b", lambda: self.look_along(1), "2")
        add("view_c", "Along &c", lambda: self.look_along(2), "3")
        add("about", f"About {APP_NAME}", self.show_about)

    def _build_menus(self):
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self.actions_.fill_menu(file_menu, [
            "new", "open", None, "save", "save_as", None,
            "export_p1", "export_image", None, "close_tab"])
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.actions_["quit"])

        edit_menu = bar.addMenu("&Edit")
        self.actions_.fill_menu(edit_menu,
                                ["delete_selection", "change_element"])

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
        self.actions_.fill_menu(structure_menu, ["reduce_p1"])

        view_menu = bar.addMenu("&View")
        style_menu = view_menu.addMenu("&Style")
        self.actions_.fill_menu(
            style_menu, [f"style_{n}" for n in styles.names()])
        show_menu = view_menu.addMenu("&Show")
        self.actions_.fill_menu(
            show_menu, ["show_atoms", "show_bonds", "show_cell",
                        "labels"])
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
            "orthographic", "boundary_bonded", None,
            "view_a", "view_b", "view_c", "reset_view"])

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.actions_["about"])

    def _build_toolbar(self):
        bar = QToolBar("Main")
        bar.setObjectName("MainToolBar")
        bar.setMovable(False)
        self.actions_.fill_menu(bar, ["open", "save", None,
                                      "reset_view"])
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

        # Three panels compete for the right-hand side; tabbing them
        # keeps the viewport wide by default.
        self.tabifyDockWidget(self.inspector_dock, self.info_dock)
        self.tabifyDockWidget(self.info_dock, self.sites_dock)
        self.inspector_dock.raise_()

        window_menu = self.menuBar().addMenu("&Window")
        for dock in (self.file_dock, self.inspector_dock,
                     self.info_dock, self.sites_dock):
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
        document.structureChanged.connect(self._update_ui)
        document.viewChanged.connect(self._update_ui)
        document.selectionChanged.connect(self._on_selection_changed)
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
        except (ValueError, OSError) as exc:
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

    def _on_selection_changed(self) -> None:
        document = self.current_document()
        if document is None:
            return
        self.inspector_dock.refresh()
        self.sites_dock.sync_selection()
        self.selection_label.setText(document.selection_summary())
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "select_same",
             "expand_bonded", "expand_fragment", "expand_orbit"],
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

    def _update_ui(self, *_args) -> None:
        document = self.current_document()
        has_document = document is not None
        self.actions_.set_enabled(
            ["save", "save_as", "export_p1", "export_image",
             "close_tab", "reset_view", "view_a", "view_b", "view_c"],
            has_document)
        self.info_dock.show_document(document)
        self.inspector_dock.set_document(document)
        self.sites_dock.set_document(document)
        self._rebuild_element_menu(document)
        self.actions_.set_enabled(
            ["select_all", "select_none", "invert_selection",
             "reduce_p1"], has_document)
        if document is None:
            self.status_label.setText("No structure open")
            self.selection_label.setText("")
            self.setWindowTitle(APP_NAME)
            return
        self.selection_label.setText(document.selection_summary())
        self.actions_.set_enabled(
            ["delete_selection", "change_element", "select_same",
             "expand_bonded", "expand_fragment", "expand_orbit"],
            bool(document.selection.atoms))
        self.status_label.setText(document.status_text())
        self.setWindowTitle(f"{document.title} — {APP_NAME}")
        name = f"style_{document.view.style}"
        if name in self.actions_:
            self.actions_[name].setChecked(True)
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
