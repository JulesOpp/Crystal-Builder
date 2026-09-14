"""
xtalapp.workspace_shell
=======================
The folder that structures and their calculations live in, as the
window sees it.

:mod:`xtal.workspace` is the workspace itself -- directories, entries,
run folders, headless.  This is the half that needs a window: opening
one, remembering it, copying a structure into it, and turning a node
of the tree into whatever that node actually is.

**Separate from :mod:`xtalapp.documents`, though they are adjacent in
the file this came from.**  A workspace is a directory that runs land
in; a document is a structure in a tab.  They meet at one call --
``place_in_workspace``, when a file is opened -- and that call is a
better boundary than the blank line that used to separate them.

**There is always a workspace**, made on a first run if there is not
one to reopen -- see :meth:`WorkspaceShell.restore_workspace` for why
that reverses the rule this file used to hold.  A window whose
workspace could not be created still opens and still runs and leaves
nothing behind, which is the old behaviour kept as the failure path
rather than as the default.
"""

from __future__ import annotations

from pathlib import Path

from xtal.workspace import NotAWorkspace, Workspace
from xtalapp.dialogs.workspace_chooser import (
    ask_for_existing,
    ask_for_new,
)


class WorkspaceShell:
    """The open workspace, and the window showing it.

    Not a QObject: everything the docks emit -- the tree's switcher,
    the run-started and run-finished signals, a trajectory loaded from
    a node -- is connected to the window's method of that name and
    arrives on the thread that emitted it, which is the one this
    window is on.

    ``workspace`` is the whole of the state.  The window keeps a
    read-only property over it, because the test that a workspace is
    reopened in the next session asks the window for it.
    """

    def __init__(self, window):
        self.window = window
        self.workspace: Workspace | None = None
        # The session is written whenever the tabs change, and there
        # are two stretches where the tabs change without the user
        # having changed anything: reopening a workspace's tabs, and
        # closing them all on the way out of one.  Recorded, the first
        # writes a session half-restored and the second writes an
        # empty one over the session it is leaving behind.
        self._holding = False

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
            self.window.show_message(f"could not copy into the workspace: "
                                     f"{exc}")
            return
        document.structure.meta.setdefault("source", str(path))
        document.attach_workspace(entry)
        # The tab follows the copy.  A document still pointing at the
        # file it was read from is one whose work is only half in the
        # workspace -- and one the workspace cannot remember, because
        # what it remembers is paths inside itself.
        document.adopt(entry.path / path.name)
        self.refresh_workspace()
        self.window.file_dock.tree.select_path(entry.path)

    def _offer_workspace(self, path) -> Workspace | None:
        """What to do for a structure opened with no workspace open.

        Which now means: opened in a window whose default workspace
        could not be made, because :meth:`restore_workspace` makes one
        on a first run.  So this is the failure path rather than the
        ordinary one, and what it does there is nothing, and says so:
        a second attempt at a folder the first attempt could not
        create, on every file the user opens, is a status bar that
        says nothing else all session.

        There was a preference to make one beside the file instead.
        It was off by default and reachable only here, on the path
        where making a folder had just failed, and it is gone.
        """
        self.window.show_message(
            "no workspace open, so runs will not be kept -- "
            "File > New Workspace... gives them somewhere to go")
        return None

    def set_workspace(self, root, create: bool = False):
        """Open a workspace and show it in the tree.

        The swap on its own, closing nothing.  This is the path
        construction takes, when there are no tabs to close yet.
        Everything a *user* reaches goes through
        :meth:`switch_workspace` instead.
        """
        workspace = self._open(root, create)
        if workspace is not None:
            self._adopt(workspace)
        return workspace

    def switch_workspace(self, root, create: bool = False):
        """Leave the workspace that is open, and enter another.

        **Everything open closes.**  A tab is a structure *of* the
        workspace it was opened in -- its runs are filed in that
        folder and its session is saved beside it -- so a tab carried
        across a switch is a document whose entry points into a
        directory the user has walked away from, and the next run it
        starts is filed there.  That was the behaviour, and it was a
        bug rather than a convenience.

        The new workspace is opened **first**.  A folder that turns
        out not to be one, or that cannot be created, must not already
        have cost somebody the tabs they had.
        """
        workspace = self._open(root, create)
        if workspace is None:
            return None
        if workspace == self.workspace:
            self.refresh_workspace()
            return workspace
        if not self.window.may_discard_unsaved(
                "Some structures have unsaved changes. Leave this "
                "workspace anyway?"):
            return None
        self.save_session()
        self._holding = True
        try:
            self.window.close_all_documents(force=True)
        finally:
            self._holding = False
        self._adopt(workspace)
        self.restore_session()
        return workspace

    def _open(self, root, create: bool):
        try:
            return (Workspace.create(root) if create
                    else Workspace.open(root))
        except (NotAWorkspace, OSError) as exc:
            self.window.show_message(f"could not open that workspace: {exc}")
            return None

    def _adopt(self, workspace) -> None:
        self.workspace = workspace
        self.window.settings.last_workspace = str(workspace.root)
        self.window.settings.add_recent_workspace(workspace.root)
        self.refresh_workspace()
        self.window.refresh_title()
        self.window.show_message(f"workspace: {workspace.root}")

    # -- the tabs a workspace was left with --------------------------

    def save_session(self) -> None:
        """Remember what is open, so entering here again brings it back.

        Written whenever the tabs change rather than at quit alone: a
        crash, a force-quit or a machine that goes to sleep and never
        comes back are the three ways a session kept only in memory is
        lost, and it is a few hundred bytes.
        """
        if self._holding or self.workspace is None:
            return
        documents = self.window.documents
        paths = [d.path for d in documents if d.path is not None]
        active, current = 0, self.window.tabs.currentIndex()
        if 0 <= current < len(documents):
            path = documents[current].path
            if path in paths:
                active = paths.index(path)
        self.workspace.set_session(paths, active)

    def restore_session(self) -> None:
        """Reopen the tabs this workspace was last left with.

        A remembered file that has since been deleted is skipped
        rather than reported: the workspace is being *entered*, and a
        dialog about a file the user threw away themselves is not the
        first thing it should say.
        """
        if self.workspace is None:
            return
        remembered = self.workspace.session_paths()
        if not remembered:
            return
        active = self.workspace.session["active"]
        self._holding = True
        try:
            for path in remembered:
                self.window.open_path(path, report=False)
        finally:
            self._holding = False
        if 0 <= active < self.window.tabs.count():
            self.window.tabs.setCurrentIndex(active)
        self.save_session()

    def enter_workspace(self, workspace=None) -> None:
        """The workspace this window opens in, at construction.

        With one already chosen -- the chooser in
        :func:`xtalapp.main.main` -- it is simply adopted, and the
        tabs it was left with come back.  With none, the last one is
        reopened or the default is made, which is what this did
        before anybody was asked and is still what a window built by
        hand does.
        """
        if workspace is None:
            self.restore_workspace()
            return
        self._adopt(workspace)
        self.restore_session()

    def restore_workspace(self) -> None:
        """Reopen the workspace that was open last, or make one.

        **The application does not work without a workspace.**  It
        used to, and the reason was good: a folder created behind
        somebody's back is one they find later and do not recognise.
        What that traded away turned out to be worse.  A structure
        with no workspace opened, ran, and left nothing behind -- so
        the framework somebody had just built, or the run they had
        just watched finish, had been kept nowhere at all, and the
        status bar sentence saying so is not something anybody reads
        before the tab is closed.

        So a first run *makes* the default workspace, in the folder
        Preferences names, and says where it put it.  That folder is
        an ordinary directory in the home folder rather than a hidden
        one under Application Support precisely so that the thing
        created behind somebody's back is one they can find.

        It falls back to no workspace when the folder cannot be made,
        because a window that will not open is worse than a window
        with nowhere to put its runs -- so every ``workspace is None``
        branch downstream is still reachable and still means what it
        said.
        """
        last = self.window.settings.last_workspace
        if last and Workspace.is_workspace(last):
            self.workspace = Workspace(last)
            self.refresh_workspace()
            self.window.refresh_title()
            self.restore_session()
            return
        if self.set_workspace(
                self.window.settings.default_workspace_root,
                create=True) is None:
            self.refresh_workspace()
        else:
            self.restore_session()

    def refresh_workspace(self) -> None:
        self.window.file_dock.set_workspace(
            self.workspace, self.window.settings.recent_workspaces())

    def open_workspace_dialog(self) -> None:
        chosen = ask_for_existing(self.window, self.window.settings)
        if chosen:
            self.switch_workspace(chosen)

    def new_workspace_dialog(self) -> None:
        chosen = ask_for_new(self.window, self.window.settings)
        if chosen:
            self.switch_workspace(chosen, create=True)

    def _on_workspace_requested(self, what: str) -> None:
        """The tree's own switcher: open, new, or one of the recent."""
        if what == "open":
            self.open_workspace_dialog()
        elif what == "new":
            self.new_workspace_dialog()
        else:
            self.switch_workspace(what)

    def _on_run_started(self, path: str) -> None:
        self.refresh_workspace()
        self.window.log_dock.show_file(Path(path) / "run.log")

    def _on_run_finished(self, path: str) -> None:
        self.refresh_workspace()
        self.window.log_dock.poll()

    def _on_trajectory_history(self, history) -> None:
        """A trajectory opened from the tree fills the energy plot.

        The plot and the trajectory are the same run seen two ways, so
        opening one has to populate the other -- otherwise clicking the
        trace to reach a frame only works for the run you just watched.
        """
        if history:
            # Which engine produced this run is not carried this far,
            # so both plots take it -- only the one behind the dock
            # the user actually opens is looked at, and a stale trace
            # in the other is harmless.
            self.window.ff_dock.plot.set_history(history)
            self.window.dftb_dock.plot.set_history(history)

    def open_artifact(self, kind: str, path: str) -> None:
        """Open a node of the workspace tree as what it *is*.

        Dispatch on the artefact's kind rather than on its extension:
        a ``.cif`` that is a run's output and a ``.cif`` that is the
        input want the same viewer and different labelling, which an
        extension cannot say.
        """
        target = Path(path)
        if kind == "log":
            self.window.log_dock.show_file(target)
        elif kind == "trajectory":
            self.window.trajectory_dock.set_document(
                self.window.current_document())
            self.window.trajectory_dock.open_path(target)
        elif kind == "image":
            # A plot a run left behind.  Handed to whatever the
            # desktop opens PNGs with, because a picture viewer is not
            # something this application should be growing.
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            if not QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(target))):
                self.window.show_message(                  # pragma: no cover
                    f"could not open {target.name}")
        elif kind in ("structure", "final", "project", "file"):
            self.window.open_path(target)
