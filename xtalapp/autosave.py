"""
xtalapp.autosave
================
The modified tabs, written somewhere safe every couple of minutes.

A structure is usually twenty minutes of hand editing, and nothing
kept it but the user remembering Ctrl+S: a crash, a kill, a flat
battery lost every unsaved edit in every tab.

**An autosave is a side file, never the document.**  It goes to
``<workspace>/.autosave/``, mirroring the file's place in the
workspace (:meth:`xtal.workspace.Workspace.autosave_path`), and it is
written with ``Document.write_project``, which adopts no path.  The
tab's own file is only ever written by Save -- so "Save File converts"
and "overwriting is silent" still mean what they say, and the only
thing a timer can ever cost is a file in a dot-folder.

**Only what was edited, and only while it is unsaved.**  A tab is
written when its history has moved since the last write and it is
modified; it is deleted the moment the document is clean again -- a
save, or undoing back to the file -- and when a modified tab is
deliberately discarded (closed or quit with "yes, throw it away").
What is left in the folder is therefore exactly the work a person
did not choose to lose.

**It is offered back, not applied.**  When a file with a newer
autosave is opened, the window's notice bar says so and asks;
Restore is :meth:`xtalapp.document.Document.recover`, one undo step,
so Ctrl+Z is the file as saved.

A window with no workspace -- the degraded path -- has nowhere to
keep one and autosaves nothing.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

log = logging.getLogger("xtalapp")

RESTORE = "Restore"
DISCARD = "Discard"


class Autosaver(QObject):
    """One per window: a timer, and the tabs edited since it last ran."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._pending: set = set()
        self._offers: list = []
        self._asking = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.apply_interval()
        window.notice.answered.connect(self._resume)

    def _resume(self, _label: str) -> None:
        if not self._asking and self._offers:
            self._ask_next()

    def apply_interval(self) -> None:
        """Restart the timer from the preference; 0 stops it."""
        seconds = self.window.settings.autosave_interval
        self.timer.stop()
        if seconds > 0:
            self.timer.start(seconds * 1000)

    # -- following the documents ---------------------------------------

    def watch(self, document) -> None:
        """Called for every document the window takes on."""
        document.historyChanged.connect(
            lambda d=document: self._pending.add(d))
        document.modifiedChanged.connect(
            lambda modified, d=document: None if modified
            else self.forget(d))

    def path_for(self, document) -> Path | None:
        workspace = self.window.workspace
        if workspace is None or document.path is None:
            return None
        return workspace.autosave_path(document.path)

    # -- writing -------------------------------------------------------

    def tick(self) -> list[Path]:
        """Write every tab edited since the last tick.  What was written.

        Temp file then rename, so a crash mid-write leaves the last
        good autosave rather than half of a new one.
        """
        written = []
        pending, self._pending = self._pending, set()
        for document in pending:
            if document not in self.window.documents:
                continue
            if not document.modified:
                self.forget(document)
                continue
            target = self.path_for(document)
            if target is None:
                continue
            # ".partial" before the extension: the project writer puts
            # its own suffix on anything else.
            partial = target.with_name(target.stem + ".partial"
                                       + target.suffix)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(document.write_project(partial), target)
            except (OSError, ValueError) as error:
                # A full disk or a read-only workspace is no reason to
                # interrupt somebody editing; it is logged, and the
                # next tick tries again.
                log.warning("could not autosave %s: %s",
                            document.title, error)
                self._pending.add(document)
                continue
            written.append(target)
        return written

    def forget(self, document) -> None:
        """Drop a document's autosave: it was saved, or discarded."""
        self._pending.discard(document)
        target = self.path_for(document)
        if target is None:
            return
        try:
            target.unlink(missing_ok=True)
        except OSError:                             # pragma: no cover
            pass

    def forget_modified(self) -> None:
        """The whole window's unsaved work was deliberately discarded."""
        for document in list(self.window.documents):
            if document.modified:
                self.forget(document)

    # -- offering it back ----------------------------------------------

    def recovered(self, document) -> Path | None:
        """The autosave left for this document, if newer than its file."""
        target = self.path_for(document)
        if target is None or not target.is_file():
            return None
        try:
            if (document.path.is_file() and target.stat().st_mtime
                    <= document.path.stat().st_mtime):
                # Older than the file: the file was saved after it,
                # by this program or another, and it is stale.
                target.unlink(missing_ok=True)
                return None
        except OSError:                             # pragma: no cover
            return None
        return target

    def offer(self, document) -> bool:
        """Say that unsaved edits were kept, and ask what to do.

        Queued, one question at a time: a workspace reopening five
        tabs with five autosaves would otherwise put each notice over
        the last, and only the fifth would ever be answered.
        """
        target = self.recovered(document)
        if target is None:
            return False
        self._offers.append((document, target))
        if not self._asking:
            self._ask_next()
        return True

    def _ask_next(self) -> None:
        while self._offers:
            document, target = self._offers.pop(0)
            if document in self.window.documents and target.is_file():
                break
        else:
            self._asking = False
            return
        self._asking = True
        when = datetime.fromtimestamp(target.stat().st_mtime)

        def answered(label):
            if label is None:
                # Another notice took the bar; ask again when it is
                # answered (see __init__).
                self._offers.insert(0, (document, target))
                self._asking = False
                return
            if label == RESTORE:
                self.restore(document, target)
            elif label == DISCARD:
                target.unlink(missing_ok=True)
            # Closed without an answer: left, and asked next time the
            # file is opened.
            self._ask_next()

        self.window.notice.show_notice(
            f"Unsaved changes to {document.path.name} from "
            f"{when:%d %b %H:%M} were kept.",
            buttons=(RESTORE, DISCARD), on_answer=answered)

    def restore(self, document, target: Path) -> None:
        if document not in self.window.documents:
            return
        try:
            document.recover(target)
        except (OSError, ValueError, KeyError) as error:
            log.warning("could not restore %s: %s", target, error)
            self.window.show_message(
                f"could not restore the kept changes: {error}")
            return
        # Kept until the restored edits are saved or written again:
        # the document is modified, so the next tick replaces it.
        self._pending.add(document)
