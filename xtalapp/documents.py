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

import logging
import os
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from xtal.core.structure import Structure
from xtal.io import FORMATS
from xtal.workspace import resolved
from xtalapp import samples
from xtalapp.document import PROJECT_EXTENSION, Document
from xtalapp.viewport.view_settings import theme_background

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
        if not document.view_is_saved:
            # What Preferences > View defaults says a newly opened
            # structure starts as.  Not applied to a project, which
            # brings the view it was saved with -- and applied here,
            # before the viewport is built over it, so nothing is
            # drawn twice.
            default = self.window.settings.default_view()
            document.view.style = default["style"]
            follows = default["background_follows_theme"]
            document.view.background_follows_theme = follows
            document.view.background = (theme_background() if follows
                                        else default["background"])
        viewport = self.window._viewport_factory(document, self.tabs)
        if hasattr(viewport, "preview_interval_ms"):
            viewport.preview_interval_ms = \
                self.window.settings.preview_interval
        if hasattr(viewport, "show_types"):
            viewport.show_types = self.window._show_atom_types
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
        self.window.autosaver.watch(document)
        if hasattr(viewport, "statusMessage"):
            viewport.statusMessage.connect(
                lambda text: self.window.statusBar().showMessage(text, 4000))
        if hasattr(viewport, "contextRequested"):
            viewport.contextRequested.connect(self.window.show_context_menu)
        if hasattr(viewport, "modeChanged"):
            viewport.modeChanged.connect(self.window.sync_mode_action)
        self.tabs.setCurrentIndex(index)
        self.window._update_ui()
        self.window.workspace_shell.save_session()
        return index

    def new_document(self) -> Document:
        """An empty structure, in a folder of its own, straight away.

        A document with nowhere to be is one whose first run has
        nowhere to land and whose ``Ctrl+S`` opens a dialog in
        whichever directory was last used, which is how work made in
        this application ended up outside it.  So the folder is made
        now -- ``untitled``, numbered past whatever is already there --
        and the tab is over a real file from the first keystroke.  The
        entry is the structure's name here, so renaming is a workspace
        operation rather than a Save As.

        With no workspace the old pathless document is what opens.
        That is the folder-could-not-be-made path and nothing else;
        see :meth:`WorkspaceShell.restore_workspace`.
        """
        structure = Structure.empty()
        entry = path = None
        workspace = self.window.workspace
        if workspace is not None:
            try:
                entry = workspace.new_document("untitled")
                path = entry.path / f"{entry.name}.cif"
                FORMATS.write(structure, path)
            except (OSError, ValueError) as exc:
                self.window.show_message(
                    f"could not file the new structure: {exc}")
                entry = path = None
        document = Document(structure, path=path)
        self.add_document(document)
        if entry is not None:
            document.attach_workspace(entry)
            self.window.refresh_workspace()
        return document

    def open_dialog(self) -> None:
        filters = [f.filter_string() for f in FORMATS.readable()]
        filters.append("All files (*)")
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Open structure", self.window.settings.last_directory,
            ";;".join(filters))
        if path:
            self.open_path(path)

    def open_path(self, path, report: bool = True) -> Document | None:
        """Open a file, and say so in a dialog when it will not open.

        ``report=False`` is for the files nobody has just asked for --
        the tabs a workspace is being reopened with.  A launch that
        begins with a modal about a file the user deleted themselves
        is a launch that has to be dismissed before it has started.
        """
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
            # Compared by the name shown and not by path: the tab
            # follows the workspace's copy, so reopening the original
            # is a different path under the same name, and "already
            # open, as MOF-5.cif" read as though it were not.
            self.window.show_message(
                f"{path.name} is already open"
                if already.title == path.name else
                f"{path.name} is already open, as {already.title}")
            return already
        try:
            if not path.exists():
                # Before the reader, whose own answer is gemmi's C
                # library: "[Errno 2] unable to open() file ...".
                raise FileNotFoundError(
                    f"there is no file at {path.parent}")
            document = Document.load(path)
        except (ValueError, OSError, KeyError) as exc:
            # Logged as well as shown: the box is gone once it is
            # dismissed, and somebody who wants to send the parser's
            # line number to a colleague had to reproduce it first.
            # Help > Show Log is where this goes.
            logging.getLogger("xtalapp").warning(
                "could not open %s: %s", path, exc)
            if report:
                QMessageBox.warning(self.window,
                                    "Could not open the file",
                                    f"{path.name}\n\n{exc}")
            else:
                self.window.show_message(
                    f"could not reopen {path.name}: {exc}")
            return None
        self.add_document(document)
        self.window.settings.add_recent_file(path)
        self.window.settings.last_directory = str(path.parent)
        self.window._rebuild_recent_menu()
        self.window.place_in_workspace(document, path)
        self._announce_warnings(document)
        self.window.autosaver.offer(document)
        self._announce_agent(document)
        return document

    def _announce_agent(self, document) -> None:
        """Say so when the entry was built or edited by an AI assistant.

        The status line and not the notice bar: the bar may be asking
        about an autosave, and that question is worth more than this
        sentence.  The log itself is a file in the entry, which the
        Workspace panel shows.
        """
        from xtal.agent.session import LOG_NAME, summarise_log

        entry = getattr(document, "entry", None)
        if entry is None:
            return
        summary = summarise_log(entry.path / LOG_NAME)
        if not summary:
            return
        steps, warnings = summary
        said = (f"{entry.name} was worked on by an AI assistant: "
                f"{steps} step(s)")
        if warnings:
            said += f", {warnings} warning(s)"
        self.window.show_message(f"{said} -- {LOG_NAME} in the entry "
                                 f"lists them", 12000)

    def open_sample(self, name: str) -> Document | None:
        """Open one of the structures that ship with the application.

        **Copied into the workspace and then opened from there**, like
        any other file.  The shipped file lives inside the
        application's own folder -- a signed bundle on macOS, under
        ``Program Files`` on Windows -- so a document that adopted
        *that* path would answer ``Ctrl+S`` by writing there and the
        save would be refused or land somewhere nobody finds again.
        That is why this used to open a pathless document, and the
        copy answers it better: the sample becomes an ordinary
        structure of this workspace, editable, saveable, with runs of
        its own.

        Opening the same sample twice returns to the one entry,
        because ``add_structure`` compares the bytes.  Opening it
        again after editing and saving that entry does not: the bytes
        differ, so a pristine copy is made beside it, and what opens
        is what was clicked.

        With no workspace it falls back to the pathless document it
        always was -- the folder-could-not-be-made path.
        """
        sample = samples.get(name)
        path = sample.path
        if path is None:
            QMessageBox.warning(self.window, "No sample structures",
                                samples.MISSING)
            return None
        workspace = self.window.workspace
        if workspace is not None:
            try:
                entry = workspace.add_structure(
                    path, name=sample.entry_name)
            except OSError as exc:
                self.window.show_message(
                    f"could not copy the sample in: {exc}")
            else:
                return self.open_path(entry.path / path.name)
        try:
            structure = FORMATS.read(path)
        except (ValueError, OSError, KeyError) as exc:   # pragma: no cover
            QMessageBox.warning(self.window, "Could not open the sample",
                                f"{sample.label}\n\n{exc}")
            return None
        # The tab is named from here, because a pathless document
        # takes its title from the structure's, and these files carry
        # the data block name whoever exported them left behind.
        structure.meta["title"] = sample.entry_name
        document = Document(structure)
        self.add_document(document)
        self._announce_warnings(document)
        return document

    def _announce_warnings(self, document: Document) -> None:
        """Say a file opened with warnings, and say what they were.

        The status line used to read "opened with 1 warning(s)" for
        eight seconds, with no way to reach the sentence it was
        counting: the Log panel shows a *run* log, and Show Log opens
        a folder in Finder.  A count nobody can expand is the same as
        not having said it, so the warning says itself, and the
        application log keeps the whole of it.
        """
        if not document.warnings:
            return
        log = logging.getLogger("xtalapp")
        for warning in document.warnings:
            log.warning("%s: %s", document.title, warning)
        first = document.warnings[0]
        if len(first) > 110:
            first = first[:109].rsplit(" ", 1)[0] + "..."
        more = (f" (+{len(document.warnings) - 1} more)"
                if len(document.warnings) > 1 else "")
        self.window.statusBar().showMessage(first + more, 15000)

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
        wanted = resolved(path)
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
        out = {resolved(document.path)}
        entry = getattr(document, "entry", None)
        if entry is not None:
            out.add(resolved(entry.structure_path))
        # And the file it was read from, which the tab no longer
        # points at once the copy has been adopted -- opening that
        # same file a second time still has to find this tab.
        source = document.structure.meta.get("source")
        if source:
            out.add(resolved(source))
        out.discard(None)
        return out

    def save_document(self) -> None:
        """Save File: write this document, without asking where.

        Save and Save As write a **project**, always.  They used to
        dispatch on the extension the user typed, so the same command
        either kept a whole working session or threw most of it away
        depending on three characters after a dot.  Writing a file for
        another program is Export, which is one way and says so.

        **A document opened as a CIF converts on its first save.**  It
        gets the project of the same name beside it and becomes that
        file; the CIF it was read from is left exactly where it is.
        This is what stops ``Ctrl+S`` opening a dialog on a structure
        that plainly has somewhere to go -- the entry it is filed in --
        and it is a conversion rather than an overwrite because a CIF
        cannot hold a measurement, a plane, or the view it was being
        looked at in.

        Only a document with **no file at all** still asks, which
        outside the folder-could-not-be-made path no longer happens.
        """
        document = self.current_document()
        if document is None:
            return
        target = self._save_target(document)
        if target is None:
            self.save_document_as()
            return
        if not self._may_overwrite(target):
            return
        source = document.path
        try:
            written = document.save(target)
        except (ValueError, OSError) as exc:
            logging.getLogger("xtalapp").warning(
                "could not save %s: %s", target, exc)
            QMessageBox.warning(self.window, "Could not save", str(exc))
            return
        self.window.settings.add_recent_file(written)
        self.window._rebuild_recent_menu()
        self.window.show_message(f"saved {written.name}")
        self.window.refresh_workspace()
        if source is not None and source != written:
            self._explain_conversion(source, written)

    def _explain_conversion(self, source: Path, written: Path) -> None:
        """Say, once, that the CIF was left and a project made.

        Somebody who edits a CIF, saves, and mails "the CIF" to a
        collaborator mails the unedited one -- and the status line was
        all that told them otherwise, for six seconds.
        """
        settings = self.window.settings
        if settings.explained_conversion:
            return
        dont = "Don't Show Again"

        def answered(label):
            if label == dont:
                settings.explained_conversion = True

        self.window.notice.show_notice(
            f"Saved as {written.name}, which keeps the measurements, "
            f"planes and view that a CIF cannot hold. {source.name} "
            f"is unchanged; File ▸ Export writes a CIF.",
            buttons=(dont,), on_answer=answered)

    def _save_target(self, document) -> Path | None:
        """The project this document is, or becomes.  ``None`` to ask.

        Beside the file the tab is over rather than at the entry's own
        name, because those differ: two structures called MFU4l give
        entries ``MFU4l`` and ``MFU4l-2``, and both hold a file called
        ``MFU4l.cif``.  Naming the project after the *file* keeps the
        pair together and keeps a second save from finding a different
        answer than the first.
        """
        if document.path is None:
            return None
        return document.path.with_suffix(PROJECT_EXTENSION)

    def _may_overwrite(self, target: Path) -> bool:
        """Whether Save File may write over a file that is already there.

        Silently by default: the whole point of Save File is that it
        does not stop to ask where, and a box on every ``Ctrl+S`` is a
        box nobody reads by the third time.  Preferences turns it on
        for anybody who wants the pause, and it is only ever asked
        about a file that **exists** -- a first save is creating
        something and has nothing to confirm.
        """
        if not target.exists():
            return True
        if not self.window.settings.confirm_overwrite:
            return True
        answer = QMessageBox.question(
            self.window, "Save File",
            f"Overwrite {target.name}?\n\nIn: {target.parent}",
            QMessageBox.Yes | QMessageBox.No)
        return answer == QMessageBox.Yes

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
        if document.path is not None:
            # Beside the file the tab is over.  Asked of the entry
            # instead, this gives a different answer for a numbered
            # entry -- ``MFU4l-2/MFU4l.cif`` would be offered
            # ``MFU4l-2.xtalproj`` -- and Save File would then write
            # somewhere else again.
            return document.path.with_suffix(PROJECT_EXTENSION)
        if document.entry is not None:
            return document.entry.project_path
        base = Path(self.window.settings.last_directory) / \
            (document.structure.meta.get("title") or "structure")
        return Path(base).with_suffix(PROJECT_EXTENSION)

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
        """A picture of the view, in a format the user chose.

        The same shape as :meth:`export_dialog`, down to moving
        ``last_directory``, which the native save dialog this replaced
        never did.
        """
        viewport = self.current_viewport()
        # Most widget tests inject a bare QWidget in place of the VTK
        # viewport, and it can neither be measured nor grabbed.
        if viewport is None or not hasattr(viewport, "save_image") \
                or not hasattr(viewport, "image_size"):
            return
        document = self.current_document()
        stem = "view"
        if document is not None:
            stem = (document.path.stem if document.path is not None
                    else str(document.structure.meta.get("title")
                             or "view"))
        from xtalapp.dialogs.image_export import ImageExportDialog
        dialog = ImageExportDialog(
            self.window, directory=self.window.settings.last_directory,
            stem=stem, size=viewport.image_size())
        if dialog.exec() != QDialog.Accepted:
            return
        target = dialog.target()
        if target is None:                          # pragma: no cover
            return
        try:
            written = viewport.save_image(target, **dialog.options())
        except (KeyError, OSError) as exc:
            QMessageBox.warning(self.window, "Could not export image",
                                str(exc))
            return
        written = Path(written)
        self.window.settings.last_directory = str(written.parent)
        self.window.show_message(f"wrote {written.name}")

    def export_net(self) -> None:
        """The drawn net as ``.cgd``, for Systre to name.

        A plain save dialog rather than the Export one: the file holds
        a net and no structure, so none of that dialog's choices --
        format, selection only, what to clean -- mean anything for it.
        """
        document = self.current_document()
        if document is None:
            return
        if not document.has_net():
            self.window.show_message("no net has been drawn")
            return
        stem = (document.path.stem if document.path is not None
                else str(document.structure.meta.get("title") or "net"))
        suggested = Path(self.window.settings.last_directory) / \
            f"{stem}.cgd"
        chosen, _ = QFileDialog.getSaveFileName(
            self.window, "Export net for Systre", str(suggested),
            "Systre net (*.cgd)")
        if not chosen:
            return
        target = Path(chosen)
        if target.suffix.lower() != ".cgd":
            target = target.with_name(target.name + ".cgd")
        from xtal.io.cgd import CgdError
        try:
            written = document.export_net(target)
        except (CgdError, OSError) as exc:
            QMessageBox.warning(self.window, "Could not export net",
                                str(exc))
            return
        self.window.settings.last_directory = str(written.parent)
        self.window.show_message(
            f"wrote {written.name} -- run Systre on it for a second "
            f"opinion on the name")
        self.window.refresh_workspace()

    def close_current(self) -> None:
        if self.tabs.currentIndex() >= 0:
            self.close_document(self.tabs.currentIndex())

    def close_all(self, force: bool = False) -> bool:
        """Every tab, from the end.

        ``force`` skips the per-document question because the caller
        has already asked it once for the whole window -- changing
        workspace does, and the same question five times is not five
        questions.  Without it this is Close All and each modified
        document still gets its say; a refusal stops there and leaves
        what is left open, which is why this answers.
        """
        for index in range(len(self.documents) - 1, -1, -1):
            self.close_document(index, force=force)
        return not self.documents

    def close_document(self, index: int, force: bool = False) -> None:
        if not 0 <= index < len(self.documents):
            return
        document = self.documents[index]
        if document.modified and not force and not no_confirm_close():
            answer = QMessageBox.question(
                self.window, "Unsaved changes",
                f"{document.title} has unsaved changes. Close it?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        if document.modified:
            # Asked and answered, or forced by a caller that asked for
            # the whole window: its edits were thrown away on purpose.
            self.window.autosaver.forget(document)
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        del self.documents[index]
        widget.deleteLater()
        self.window._update_ui()
        self.window.workspace_shell.save_session()
