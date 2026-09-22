"""
xtalapp.layout
==============
Which panels exist, what they are wired to, and where they sit.

This was the rest of the ``CONSTRUCTION`` half of
:mod:`xtalapp.mainwindow`.  It builds every dock, connects each one
back to the window method it reports to, groups them into the three
areas, and puts the Window menu together from the result.

**Free functions over a window**, for the same reason as
:mod:`xtalapp.menus`: there is no state here either.  The docks
themselves are set on the window -- ``window.sites_dock`` and the rest
-- because the refresh paths and the tests read them there and have
always done.

**The default arrangement is a default, not a rule.**
``build_docks`` calls :func:`apply_default_layout` on the way past,
and ``AppSettings.restore_window`` overrides it a moment later when
there is a saved layout.  ``Reset layout`` has to land on the same
arrangement or the menu item stops being a way back, which is why
there is one function and not two descriptions of the same thing.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QTabBar

from xtal.modules import MODULES
from xtalapp import external
from xtalapp.dialogs.run_progress import RunProgressDialog
from xtalapp.docks.ff_panel import ForceFieldDock
from xtalapp.docks.info import InfoDock
from xtalapp.docks.inspector import InspectorDock
from xtalapp.docks.logview import LogDock
from xtalapp.docks.measure import MeasureDock
from xtalapp.docks.modules import ModulesDock
from xtalapp.docks.move import MoveDock
from xtalapp.docks.net import NetDock
from xtalapp.docks.results import ResultsDock
from xtalapp.docks.sites import SitesDock
from xtalapp.docks.style_panel import StylePanelDock
from xtalapp.docks.trajectory import TrajectoryDock
from xtalapp.docks.workspace import WorkspaceDock
from xtalapp.settings import default_size, fit_to_screen


class _ScrollingDockTabs(QObject):
    """Give every tab bar of tabbed docks scroll arrows.

    A dock area is at least as wide as the tab bar under it, and a tab
    bar without scroll buttons is as wide as all of its tabs, elided.
    Eight panels tabbed on the right came to 397 px, so with them open
    the column would not drag narrower than that -- and which panels
    were open decided it, which is why the divider seemed to work only
    some of the time.  With scroll arrows the bar needs about 130 px.

    The bars are Qt's own, made and remade whenever docks are tabbed
    together -- by the default layout, by restoring a saved one, or by
    the user dropping one dock onto another -- so they are caught as
    they are polished rather than set once.
    """

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ChildPolished:
            child = event.child()
            if isinstance(child, QTabBar) and not child.usesScrollButtons():
                child.setUsesScrollButtons(True)
        return False


def build_docks(window):
    window._dock_tabs = _ScrollingDockTabs(window)
    window.installEventFilter(window._dock_tabs)
    window.file_dock = WorkspaceDock(window.settings.last_directory,
                                     window)
    window.file_dock.fileActivated.connect(window.open_path)
    window.file_dock.artifactActivated.connect(window.open_artifact)
    window.file_dock.workspaceRequested.connect(
        window._on_workspace_requested)
    window.file_dock.contextRequested.connect(window.show_workspace_menu)

    # What can be run, beside what it produced: the module tree
    # picks the calculation and the workspace tree shows its
    # folder appearing underneath the structure.  Those two panels
    # next to each other are the whole workflow.
    window.modules_dock = ModulesDock(MODULES, window)
    window.modules_dock.actionActivated.connect(
        window.run_module_action)
    window.modules_dock.stopRequested.connect(window.stop_module)
    window.modules_dock.setupRequested.connect(window.show_module_setup)

    window.inspector_dock = InspectorDock(window)
    window.inspector_dock.deleteRequested.connect(
        window.delete_selection)
    window.inspector_dock.reduceToP1Requested.connect(
        window.reduce_to_p1)

    window.info_dock = InfoDock(window)
    # What the net is called, beside what the structure is: they
    # are the two "what am I looking at" panels and they are read
    # one after the other.
    window.net_dock = NetDock(window)
    window.net_dock.statusMessage.connect(window.show_status)
    window.net_dock.exportRequested.connect(window.export_net)
    window.sites_dock = SitesDock(window)
    window.move_dock = MoveDock(window)
    window.move_dock.statusMessage.connect(window.show_status)
    window.style_dock = StylePanelDock(window)

    window.measure_dock = MeasureDock(window)
    window.measure_dock.targetChanged.connect(window._on_measure_target)
    window.measure_dock.statusMessage.connect(window.show_status)

    # MACE is listed with the force fields rather than given a dock
    # of its own: what earns DFTB+ a separate one is the parameter
    # directory it cannot run without, and an MLIP has no such thing.
    # This list is hand-written, so an engine registered and left out
    # of it is one nobody can choose -- see the test in
    # tests/test_ff_ui.py that holds the two lists together.
    window.ff_dock = ForceFieldDock(window, title="Force Field",
                                    object_name="ForceFieldDock",
                                    engines=["uff", "xtb", "mace"])
    window.dftb_dock = ForceFieldDock(window, title="DFTB+",
                                      object_name="DFTBDock",
                                      engines=["dftb"])
    for dock in (window.ff_dock, window.dftb_dock):
        # Connected to a method, not to the label: the docks are
        # built before the status bar exists.
        dock.statusMessage.connect(window.show_status)
        dock.previewIntervalChanged.connect(
            window.set_preview_interval)
        dock.set_preview_interval(window.settings.preview_interval)
        dock.set_parameter_directory(
            window.settings.path_setting(external.SLATER_KOSTER))
        # A run that has just started or just finished has changed
        # what is in the workspace, and the tree is read from the
        # directory -- so this is the whole of keeping it in step.
        dock.runStarted.connect(window._on_run_started)
        dock.runFinished.connect(window._on_run_finished)

    # A run that takes minutes needs to say so somewhere the user
    # is looking, which the footer of a panel that may be closed
    # is not.  It arms itself and appears only if the run is still
    # going a moment later, so a fast module never shows one.
    window.run_progress = RunProgressDialog(window)
    window.run_progress.stopRequested.connect(window.stop_module)

    # Where a module's tables and histograms land.  Beside the
    # log rather than beside the module tree: the numbers and the
    # output that produced them are read together, and a report
    # squeezed into the width of a tree is a report nobody reads.
    window.results_dock = ResultsDock(window)

    window.log_dock = LogDock(window)
    window.trajectory_dock = TrajectoryDock(window)
    window.trajectory_dock.statusMessage.connect(window.show_status)
    # The plot and the trajectory are the same run seen two ways:
    # clicking the trace jumps to that frame, and the frame being
    # played is marked on the trace.  Both engines' plots feed the
    # one transport bar -- only one of them is ever showing a run
    # at a time, so there is nothing to arbitrate between.
    # The viewport's tooltip says what the current view is about, and
    # the force field's reading of an atom is part of that only while
    # somebody is looking at the force field.  The dock is the only
    # thing that knows, so it says so.
    window.ff_dock.visibilityChanged.connect(window.show_atom_types)

    for dock in (window.ff_dock, window.dftb_dock):
        dock.plot.pointClicked.connect(window.trajectory_dock.show_step)
        window.trajectory_dock.frameShown.connect(dock.plot.set_marker)
    window.trajectory_dock.historyLoaded.connect(
        window._on_trajectory_history)

    # What the structure is and where it came from on the left, the
    # transport bar under the viewport, everything else tabbed on
    # the right in the order they are listed here.
    window.left_docks = (window.info_dock, window.file_dock,
                         window.modules_dock)
    window.bottom_docks = (window.trajectory_dock, window.log_dock,
                           window.results_dock)
    window.right_docks = (window.inspector_dock, window.net_dock,
                          window.sites_dock, window.move_dock,
                          window.style_dock, window.measure_dock,
                          window.ff_dock, window.dftb_dock)
    window.docks = (window.left_docks + window.right_docks
                    + window.bottom_docks)
    apply_default_layout(window)

    # Filled, not added.  :func:`xtalapp.menus.build_menus` creates
    # this menu in the place the menu bar should read it, because
    # this function runs after it and a menu added here would land
    # after Help -- which is exactly where the Window menu used to
    # be.  The docks do not exist until the lines above, so filling
    # it is still this function's job.
    for dock in window.docks:
        window.window_menu.addAction(dock.toggleViewAction())
    window.window_menu.addSeparator()
    window.window_menu.addAction(window.actions_["reset_layout"])


#: What a first run shows: what the structure is and what is on
#: disk, on the left, and the asymmetric unit on the right.  Those
#: are the three panels somebody editing a structure reads without
#: having been asked to open anything.  Every other panel is one
#: item away in the Window menu; seven of them tabbed on the right
#: take, between them, the width the viewport is there to use.
DEFAULT_VISIBLE = ("info_dock", "file_dock", "sites_dock")

#: The left column on a first run: wide enough for the longest line
#: the Structure panel writes, so the cell parameters are not clipped.
DEFAULT_LEFT_WIDTH = 380

#: The right column on a first run.  Left to the Sites table's size
#: hint it was 515 px -- eight columns at five significant figures --
#: and with the left column that gave the viewport 388 px of a
#: 1285 px window, and 133 px at 1024 wide.  This is a structure
#: viewer; the table scrolls sideways and the model does not.
DEFAULT_RIGHT_WIDTH = 300


def apply_default_layout(window) -> None:
    """Put every dock back where it starts: Structure over the two
    trees on the left, the rest tabbed on the right, and only three
    of them shown.

    Called once on construction -- ``restore_window`` overrides it
    when there is a saved layout -- and again by Reset layout.

    Nothing on the left is *tabbed*.  Structure says what the
    structure is, the workspace what is on disk and the module tree
    what can be run on it; tabbing any pair of those would mean
    never seeing both.
    """
    for dock in window.left_docks:
        window.addDockWidget(Qt.LeftDockWidgetArea, dock)
    for dock in window.right_docks:
        window.addDockWidget(Qt.RightDockWidgetArea, dock)
    for dock in window.bottom_docks:
        window.addDockWidget(Qt.BottomDockWidgetArea, dock)
    # The transport bar, the log and the report are three views of
    # one run and share the strip under the viewport.
    for previous, dock in zip(window.bottom_docks,
                              window.bottom_docks[1:], strict=False):
        window.tabifyDockWidget(previous, dock)
    for previous, dock in zip(window.right_docks,
                              window.right_docks[1:], strict=False):
        window.tabifyDockWidget(previous, dock)
    for previous, dock in zip(window.left_docks,
                              window.left_docks[1:], strict=False):
        window.splitDockWidget(previous, dock, Qt.Vertical)

    shown = {getattr(window, name) for name in DEFAULT_VISIBLE}
    for dock in window.docks:
        # Only the ones that are floating: Qt redoes a dock's window
        # state even when asked for the state it is in, and fourteen
        # of those were an eighth of building a window.
        if dock.isFloating():
            dock.setFloating(False)
        dock.setVisible(dock in shown)
    # Sites, and not whatever is first in the tuple: the asymmetric
    # unit is what the right-hand column is open for.
    window.sites_dock.raise_()
    # A starting width and nothing more.  It used to be each panel's
    # *minimum* -- 380 px on the Structure text -- which is also the
    # narrowest the column could ever be dragged.
    window.resizeDocks([window.info_dock, window.sites_dock],
                       [DEFAULT_LEFT_WIDTH, DEFAULT_RIGHT_WIDTH],
                       Qt.Horizontal)


def reset_layout(window) -> None:
    """Forget the saved layout and start again.

    Without this a window that once went wrong stays wrong: the bad
    geometry is what gets saved on quit and restored on start.
    """
    window.settings.clear_window()
    apply_default_layout(window)
    window.resize(*default_size(window))
    fit_to_screen(window)
    window.show_status("layout reset")
