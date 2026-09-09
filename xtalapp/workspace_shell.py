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

from PySide6.QtWidgets import QFileDialog

from xtal.workspace import NotAWorkspace, Workspace


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
        """
        if not self.window.settings.auto_workspace:
            self.window.show_message(
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
            self.window.show_message(f"could not open that workspace: {exc}")
            return None
        self.workspace = workspace
        self.window.settings.last_workspace = str(workspace.root)
        self.window.settings.add_recent_workspace(workspace.root)
        self.refresh_workspace()
        self.window.show_message(f"workspace: {workspace.root}")
        return workspace

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
            return
        if self.set_workspace(
                self.window.settings.default_workspace_root,
                create=True) is None:
            self.refresh_workspace()

    def refresh_workspace(self) -> None:
        self.window.file_dock.set_workspace(
            self.workspace, self.window.settings.recent_workspaces())

    def open_workspace_dialog(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Open workspace",
            self.window.settings.last_workspace or
            str(self.window.settings.default_workspace_root.parent))
        if chosen:
            self.set_workspace(chosen)

    def new_workspace_dialog(self) -> None:
        chosen = QFileDialog.getSaveFileName(
            self.window, "New workspace",
            str(self.window.settings.default_workspace_root))[0]
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
