"""
xtalapp.documents
=================
The open structures, the tabs they sit in, and the files they came
from.

This was the ``DOCUMENTS`` half of :mod:`xtalapp.mainwindow`, plus
save, export and close.  One object owns the tab widget's contents and
the list beside it, because those two are the same fact written twice
-- tab *i* shows document *i* -- and keeping them in step is most of
what this code does.

**A document is a structure in a tab; a workspace is a directory that
runs land in.**  They meet at exactly one call --
``place_in_workspace``, when a file is opened -- which is why the
workspace is a separate module and not the rest of this one.

**Not a QObject**, and unlike :class:`xtalapp.module_runner.ModuleRunner`
that is safe here: nothing connects a signal to a method of this
class.  The tab widget's own signals go to the window's
``close_document`` and ``_on_tab_changed``, and every per-document
signal raised in :meth:`DocumentSet.add_document` lands on a window
method.  Nothing here is reached from another thread.

``no_confirm_close`` and ``_resolved`` came along because their callers
did; ``mainwindow`` imports the first back for ``closeEvent``, which is
the one use left outside.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from xtal.io import FORMATS
from xtalapp.document import Document

#: The environment variable that turns the unsaved-changes prompt off.
NO_CONFIRM_CLOSE_ENV = "XTAL_NO_CONFIRM_CLOSE"


def no_confirm_close() -> bool:
    """Whether closing may discard unsaved work without asking.

    An automated launch -- a screenshot run, a smoke test, an agent
    driving the GUI -- has nobody to answer the question, and a modal
    nothing will dismiss hangs the run until it is killed.  Off by
    default, so an interactive user is still warned before losing
    edits.  Read on each close rather than at import so a test can set
    it.  Parsed like XTAL_STUB_MODULE: "0"/"false"/"no"/"off" are off.
    """
    return os.environ.get(NO_CONFIRM_CLOSE_ENV, "").strip().lower() not in (
        "", "0", "false", "no", "off")


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


class DocumentSet:
    """Every open document, and the tabs showing them.

    Holds the window it is part of, because opening a file touches the
    recent list, the workspace tree and every panel, and closing one
    tears down a viewport widget.  Those are the shell's business;
    naming the dependency is what this split buys.
    """

    def __init__(self, window):
        self.window = window
        self.documents: list[Document] = []
        # Where the last export went and how, which is what "Export
        # again" repeats.
        self._last_export: tuple | None = None

    @property
    def tabs(self):
        """The tab widget, which the window owns as its central widget.

        Read through here so that ``self.tabs`` in the methods below
        means what it has always meant.
        """
        return self.window.tabs

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
            self.window.settings.bonds_follow_geometry
        if not document.structure.bond_rules:
            # Only when the structure has none of its own: a project
            # carries the rules it was saved with, and a preference
            # must not overwrite them.
            document.structure.bond_rules = \
                self.window.settings.default_bond_rules()
        viewport = self.window._viewport_factory(document, self.tabs)
        if hasattr(viewport, "preview_interval_ms"):
            viewport.preview_interval_ms = \
                self.window.settings.preview_interval
        self.documents.append(document)
        index = self.tabs.addTab(viewport, document.title)
        document.titleChanged.connect(
            lambda title, d=document: self.window._on_title_changed(d, title))
        document.structureChanged.connect(self.window._on_structure_changed)
        document.viewChanged.connect(self.window._on_view_changed)
        document.selectionChanged.connect(self.window._on_selection_changed)
        document.measurementsChanged.connect(
            self.window._on_measurements_changed)
        document.planesChanged.connect(self.window._on_planes_changed)
        document.historyChanged.connect(self.window._update_history_actions)
        document.playbackChanged.connect(self.window._refresh_shell)
        if hasattr(viewport, "statusMessage"):
            viewport.statusMessage.connect(
                lambda text: self.window.statusBar().showMessage(text, 4000))
        if hasattr(viewport, "contextRequested"):
            viewport.contextRequested.connect(self.window.show_context_menu)
        self.tabs.setCurrentIndex(index)
        self.window._update_ui()
        return index

    def new_document(self) -> Document:
        document = Document()
        self.add_document(document)
        return document

    def open_dialog(self) -> None:
        filters = [f.filter_string() for f in FORMATS.readable()]
        filters.append("All files (*)")
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Open structure", self.window.settings.last_directory,
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
            # Named when the tab is not spelled the way the thing that
            # was clicked is -- the workspace's copy of a structure,
            # or a session saved beside it.  "MOF-5.cif is already
            # open" over a tab called MOF-5.xtalproj reads as a bug.
            same = _resolved(already.path) == _resolved(path)
            self.window.show_message(
                f"{path.name} is already open" if same else
                f"{path.name} is already open, as {already.title}")
            return already
        try:
            document = Document.load(path)
        except (ValueError, OSError, KeyError) as exc:
            QMessageBox.warning(self.window, "Could not open the file",
                                f"{path.name}\n\n{exc}")
            return None
        self.add_document(document)
        self.window.settings.add_recent_file(path)
        self.window.settings.last_directory = str(path.parent)
        self.window._rebuild_recent_menu()
        self.window.file_dock.set_root(path.parent)
        self.window.place_in_workspace(document, path)
        if document.warnings:
            self.window.statusBar().showMessage(
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
            if wanted in self._paths_naming(document):
                return document
        return None

    @staticmethod
    def _paths_naming(document) -> set:
        """Every path on disk that names this document's structure.

        Its own path, and -- the part that is not obvious -- the copy
        the workspace made of it.  Opening a structure from outside a
        workspace copies it in (:meth:`place_in_workspace`), so the
        file the user opened and the file the tree shows underneath it
        are two paths to one crystal.  Comparing ``document.path``
        alone made double-clicking that node open a *second* document
        over the same atoms, with a second undo stack and a second
        viewport -- which is the duplicate-tab failure this whole
        method exists to prevent, arriving through the one route that
        was not checked for it.

        Only the entry's **structure** file counts, never everything
        inside the entry: ``final.cif`` from a run is a different
        geometry that has earned a tab of its own.
        """
        out = {_resolved(document.path)}
        entry = getattr(document, "entry", None)
        if entry is not None:
            out.add(_resolved(entry.structure_path))
        out.discard(None)
        return out

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
            QMessageBox.warning(self.window, "Could not save", str(exc))
            return
        self.window.show_message(f"saved {document.path.name}")
        self.window.refresh_workspace()

    def save_document_as(self) -> None:
        document = self.current_document()
        if document is None:
            return
        opened_a_structure = (document.path is not None
                              and document.path.suffix != ".xtalproj")
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Save project",
            str(self._suggested_project(document)),
            "Crystal Builder project (*.xtalproj)")
        if not path:
            return
        try:
            written = document.save(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self.window, "Could not save", str(exc))
            return
        self.window.settings.add_recent_file(written)
        self.window._rebuild_recent_menu()
        document.attach_workspace()
        self.window.refresh_workspace()
        if opened_a_structure:
            # A behaviour change for anybody who has been opening a CIF
            # and pressing Ctrl+S, so it is made visible rather than
            # silent.
            self.window.show_message(
                f"wrote {written.name}; the file you opened has not "
                f"been touched -- File > Export writes one back")
        else:
            self.window.show_message(f"wrote {written.name}")

    def _suggested_project(self, document) -> Path:
        """Where Save As offers to put the project.

        Inside the workspace entry when there is one, because that is
        what lets a reopened project find its own workspace by looking
        upwards rather than by remembering a path that a moved folder
        would falsify.
        """
        if document.entry is not None:
            return document.entry.project_path
        base = document.path or Path(self.window.settings.last_directory) / \
            (document.structure.meta.get("title") or "structure")
        return Path(base).with_suffix(".xtalproj")

    def export_dialog(self) -> None:
        """One dialog for every writable format."""
        document = self.current_document()
        if document is None:
            return
        from xtalapp.dialogs.export import ExportDialog
        dialog = ExportDialog(document, self.window,
                              directory=self.window.settings.last_directory)
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
            QMessageBox.warning(self.window, "Could not export", str(exc))
            return
        self._last_export = (str(written), dict(options))
        self.window.settings.last_directory = str(written.parent)
        self.window.show_message(f"exported {written.name}")
        self.window.refresh_workspace()

    def export_image(self) -> None:
        viewport = self.current_viewport()
        if viewport is None or not hasattr(viewport, "save_image"):
            return
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Export image", self.window.settings.last_directory,
            "PNG image (*.png)")
        if path:
            viewport.save_image(path)
            self.window.statusBar().showMessage(f"wrote {path}", 5000)

    def close_current(self) -> None:
        if self.tabs.currentIndex() >= 0:
            self.close_document(self.tabs.currentIndex())

    def close_document(self, index: int) -> None:
        if not 0 <= index < len(self.documents):
            return
        document = self.documents[index]
        if document.modified and not no_confirm_close():
            answer = QMessageBox.question(
                self.window, "Unsaved changes",
                f"{document.title} has unsaved changes. Close it?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        del self.documents[index]
        widget.deleteLater()
        self.window._update_ui()
