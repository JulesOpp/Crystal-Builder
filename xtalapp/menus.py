"""
xtalapp.menus
=============
Every command in the application, and the four places it appears.

This was the ``CONSTRUCTION`` half of :mod:`xtalapp.mainwindow`: the
action registry is filled once, and the menu bar, the toolbar, the
Modules menu and the context menus are all built by reading names back
out of it.  That is why a context-menu entry and a menu-bar entry are
the same object, enabled and disabled by the same rule and showing the
same tick.

**Free functions over a window, not a class**, because there is no
state here: every one of these did nothing but attach things to
``self``, and the things they attach -- ``window.actions_``,
``window.toolbar``, ``window.element_menu`` -- are read by the refresh
paths and by the tests where they have always been.  The dependency
runs one way: this module imports nothing from
:mod:`xtalapp.mainwindow`, and the window calls into it.

**The slots stay in the window.**  Every action here connects to a
bound method of ``MainWindow`` -- ``window.copy``,
``window.find_symmetry``, ``window.set_view(...)`` -- and those are
the shell's job.  What moved is the wiring, not what the wires do.

``CONTEXT_MENUS``, ``COUNTED_ACTIONS`` and ``BOND_TYPE_MENU`` stay
class attributes of ``MainWindow`` and are read off the window passed
in.  They are the table a later phase adds entries to, and moving them
would change how they are spelled without buying anything.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMenu,
    QSpinBox,
    QToolBar,
)

from xtal.commands.bonds import BOND_TYPES
from xtal.modules import MODULES
from xtalapp import external, samples
from xtalapp.viewport import modes, styles
from xtalapp.viewport.view_settings import BACKGROUNDS, ViewSettings

#: Which mouse mode the element combo belongs beside on the toolbar.
#: Named rather than positioned: the combo is the element *that* mode
#: places, so if the mode ever goes the combo has no reason to stay.
ELEMENT_MODE = "add_atom"

#: The three boundary answers, as menu entries.  In
#: :data:`xtalapp.viewport.view_settings.BOUNDARIES` order, which is
#: least drawn to most said.
BOUNDARY_ACTIONS = (
    ("in_range", "&Drop bonds at the boundary",
     "A bond whose far atom is outside the range is not drawn, so "
     "every atom on the surface of the picture is drawn "
     "under-coordinated"),
    ("bonded", "&Complete bonds at the boundary",
     "Draw the far atom as well.  The only way a coordination "
     "polyhedron at the cell edge stays whole, at the cost of a halo "
     "of extra atoms around the box"),
    ("half", "Draw &half bonds at the boundary",
     "Draw the near half and nothing on the end of it -- the usual "
     "notation for a bond that leaves the picture, and the only one "
     "that draws a six-coordinate net vertex with six edges"),
)


#: The tooltip on ``Insert molecule...`` when it is available.  Named
#: because the window puts :data:`xtal.build.MISSING` there instead
#: when RDKit is not installed, and has to be able to put this back.
INSERT_MOLECULE_TIP = (
    "Build a molecule from a SMILES string and paste it into this "
    "structure.  It arrives with the bonds the builder gave it and "
    "no others, and pasting into a group with symmetry multiplies it "
    "-- the dialog says by how much before you press the button.")


def build_actions(window):
    # The one name in here that lives in the module importing this
    # one, wanted for a single menu entry.  At the top it would be a
    # cycle -- mainwindow defines APP_NAME below its own imports, so
    # the partly-executed module has no such attribute yet.
    from xtalapp.mainwindow import APP_NAME

    add = window.actions_.add
    add("new", "&New", window.new_document, "Ctrl+N")
    add("open", "&Open...", window.open_dialog, "Ctrl+O")
    add("save", "&Save File", window.save_document, "Ctrl+S",
        tip="Save the session -- the structure, the bonds you drew, "
            "the view, the selection and the measurements -- over "
            "the file this is, without asking where")
    add("save_as", "Save &As...", window.save_document_as,
        "Ctrl+Shift+S",
        tip="Save the session under another name")
    add("export", "&Export...", window.export_dialog,
        tip="Write a file for something else to read -- a CIF, an "
            "XYZ.  One way: it never becomes this document's file")
    add("export_image", "Export &Image...", window.export_image)
    add("open_workspace", "&Open Workspace...",
        window.open_workspace_dialog,
        tip="A folder that structures and their calculations live "
            "in")
    add("new_workspace", "&New Workspace...",
        window.new_workspace_dialog)
    add("close_tab", "&Close", window.close_current, "Ctrl+W")
    add("close_all_tabs", "Close A&ll", window.close_all_documents,
        "Ctrl+Shift+W",
        tip="Every open structure.  Each modified one still asks")
    add("preferences", "&Preferences...", window.show_preferences,
        "Ctrl+,", role=QAction.MenuRole.PreferencesRole,
        tip="Everything this application remembers between sessions "
            "-- where new workspaces go, and what a newly opened "
            "structure is drawn as")
    # QuitRole and AboutRole, said rather than guessed: macOS moves
    # both of these into the application menu, and left to itself Qt
    # decides which entries those are by reading their English text.
    # See ``ActionRegistry.add``.
    # ``request_quit`` and not ``close``: Quit is reached from over a
    # dialog as often as from the window, and the question about
    # unsaved work has to be asked in front of it.  See
    # ``MainWindow.confirm_quit``.
    add("quit", "&Quit", window.request_quit, "Ctrl+Q",
        role=QAction.MenuRole.QuitRole)

    # One per structure shipped in ``resources/samples``.  Registered
    # whether or not the file is there, so that the run-app driver and
    # the tests have a name to type either way; the menu is what
    # decides which of them can be pressed.
    for sample in samples.SAMPLES:
        add(f"sample_{sample.name}", sample.label,
            lambda checked=False, n=sample.name: window.open_sample(n),
            tip=sample.description)

    for name in styles.names():
        style = styles.get(name)
        add(f"style_{name}", style.label,
            lambda checked=False, s=name: window.set_style(s),
            checkable=True, checked=(name == "ball_stick"),
            tip=style.description, group="style")

    add("show_atoms", "Atoms",
        lambda v: window.set_view(show_atoms=v), checkable=True,
        checked=True)
    add("show_bonds", "Bonds",
        lambda v: window.set_view(show_bonds=v), checkable=True,
        checked=True)
    add("show_cell", "Unit cell",
        lambda v: window.set_view(show_cell=v), checkable=True,
        checked=True)
    add("show_legend", "Element legend",
        lambda v: window.set_view(show_legend=v), checkable=True)
    add("show_bond_orders", "Bond orders",
        lambda v: window.set_view(show_bond_orders=v),
        checkable=True, checked=True,
        tip="Draw a double bond as two tubes and a triple as "
            "three, with an inner dashed line for an aromatic "
            "one")
    add("labels", "Labels",
        lambda v: window.set_view(
            label_mode="label" if v else "none"), checkable=True)
    add("show_topology", "Net (topology bonds)",
        lambda v: window.set_view(show_topology=v), checkable=True,
        checked=True,
        tip="Draw the net a chemist marked out over the framework "
            "-- thicker and translucent, over the real bonds "
            "rather than in place of them")
    add("depth_cue", "Depth cueing",
        lambda v: window.set_view(depth_cue=v), checkable=True,
        tip="Fade distant atoms towards the background, so a "
            "thick slab reads as having depth instead of as a "
            "flat mat of spheres")
    add("orthographic", "Orthographic projection",
        lambda v: window.set_view(
            projection="orthographic" if v else "perspective"),
        checkable=True)
    # Three answers to one question -- what happens to a bond whose
    # far atom is outside the display range -- so an exclusive group
    # and not three checkboxes.  ``boundary_bonded`` keeps its name:
    # it is in a context menu, in the View menu and in the tests, and
    # renaming it would be a rename and nothing else.
    for name, label, tip in BOUNDARY_ACTIONS:
        add(f"boundary_{name}", label,
            lambda checked=False, b=name: (
                window.set_view(boundary=b) if checked else None),
            checkable=True,
            checked=(name == ViewSettings.boundary),
            group="boundary", tip=tip)
    add("show_planes", "Planes",
        lambda v: window.set_view(show_planes=v), checkable=True,
        checked=True,
        tip="Draw a translucent quad at every plane in the Measure "
            "panel, with its normal on it -- choose rows in that "
            "list to draw only those")
    add("show_scale_bar", "Scale bar",
        lambda v: window.set_view(show_scale_bar=v), checkable=True,
        tip="A ruler in the corner, in Angstrom.  It measures the "
            "camera and not the crystal, so a cell that contracts "
            "during a relaxation is seen to contract against it")

    add("undo", "&Undo", window.undo, "Ctrl+Z")
    add("redo", "&Redo", window.redo, "Ctrl+Shift+Z")
    add("cut", "Cu&t", window.cut, "Ctrl+X")
    add("copy", "&Copy", window.copy, "Ctrl+C")
    add("paste", "&Paste", window.paste, "Ctrl+V")
    add("duplicate", "Du&plicate", window.duplicate, "Ctrl+D")
    add("add_atom_dialog", "&Add atom...", window.add_atom_dialog,
        "Ctrl+Shift+A")
    add("add_centroid", "Add &centroid...",
        window.add_centroid_dialog,
        tip="Put an atom at the middle of the selected atoms -- a "
            "dummy atom, which bonds to nothing and is what net "
            "edges and measurements are drawn to, or an element")
    add("add_hydrogens", "Add &hydrogens...",
        window.add_hydrogens_dialog,
        tip="Complete every main-group coordination with the "
            "hydrogens an X-ray structure never had")
    add("insert_molecule", "&Insert molecule...",
        window.insert_molecule_dialog, tip=INSERT_MOLECULE_TIP)
    add("save_building_block", "Save as a &building block...",
        window.save_building_block,
        tip="Write this molecule into the folder the MOF builder "
            "reads, so it appears in the block picker beside the 867 "
            "PORMAKE ships.  It needs connection points on it -- the "
            "dialog says what is missing.")
    add("mark_connection_points", "&Mark connection points",
        window.mark_connection_points,
        tip="Turn each selected atom that has exactly one bond into "
            "a connection point: a dummy 0.75 A along that bond, "
            "which is what a PORMAKE building block is joined by.  "
            "There is no unmark -- an X does not remember what it "
            "was, so the way back is Ctrl+Z.")
    add("recompute_bonds", "&Recalculate bonds",
        window.recompute_bonds,
        tip="Perceive the bonds again from the geometry as it is "
            "now.  Bonds do not change on their own when atoms "
            "move; this is what changes them.")
    # Ctrl+B is the reset and not the recalculation, because the two
    # are reached differently: recalculating after moving atoms is
    # rare -- bonds do not follow the geometry in the first place --
    # and the one worth a key is the way back to a clean answer after
    # an afternoon of editing.  It throws bond edits away, which is
    # answered by ResetBonds being a single command: Ctrl+Z is exactly
    # one press.  The toolbar button stays Recalculate; a button is
    # pressed by aim rather than by memory, and the destructive one of
    # a pair is the wrong thing to leave under the cursor.
    add("reset_bonds", "Reset bonds to a&utomatic",
        window.reset_bonds, "Ctrl+B",
        tip="Drop the bonds you drew and the ones you deleted, "
            "and take what the distance criteria give.  The only "
            "way back from a deleted bond once the undo stack has "
            "gone, because a deletion is saved with the project.")
    add("bond_rules", "&Bond rules...", window.edit_bond_rules,
        tip="Which atoms bond, and how close they have to be")
    # One action per bond type, in an exclusive group: the menu
    # shows what the selected bonds already are, and picking a
    # different one is the edit.  Automatic is in the same group
    # because "no stated order" is a state a bond can be in, not
    # the absence of one.
    for type_name, order in BOND_TYPES:
        add(f"bond_type_{type_name.lower()}", f"&{type_name}",
            lambda checked=False, o=order: window.set_bond_type(o),
            checkable=True, group="bond_type",
            tip=("Let the geometry decide this bond's order again"
                 if order is None else
                 f"Call the selected bonds {type_name.lower()}, "
                 f"and their whole symmetry orbit with them"))
    add("bonds_follow", "Bonds &follow the geometry",
        window.set_bonds_follow_geometry, checkable=True,
        checked=window.settings.bonds_follow_geometry,
        tip="Re-perceive the bonds after every edit that moves an "
            "atom, instead of only when you ask")

    for mode_name in modes.names():
        mode = modes.get(mode_name)
        add(f"mode_{mode_name}", mode.label,
            lambda checked=False, m=mode_name: window.set_mode(m),
            checkable=True, checked=(mode_name == "select"),
            tip=mode.hint, group="mode")

    # Escape has no menu entry -- there is nothing to click -- so the
    # window is handed the action directly, which is what makes a
    # shortcut live.  It has to be a window action and not a key
    # handler on the viewport: a key event goes to the widget with
    # focus, and the gesture being cancelled was started by pressing a
    # toolbar button, so the focus is on the toolbar and the viewport
    # never sees the key at all.
    window.addAction(
        add("cancel_gesture", "Cancel the current gesture",
            window.cancel_gesture, "Esc",
            tip="Put down a half-finished click gesture -- an "
                "add-atom chain, the first end of a bond, the atoms "
                "of a measurement.  Again to leave the mode."))

    add("measure_selection", "&Measure selection",
        window.measure_selection, "Ctrl+M",
        tip="Measure the selected atoms in the order they were "
            "picked: two a distance, three an angle about the "
            "middle one, four a torsion -- or the length of every "
            "selected bond")
    add("define_plane", "Define &plane from selection",
        window.define_plane, "Ctrl+Shift+P",
        tip="Fit a plane through the selected atoms: exactly "
            "through three, least-squares through more")
    add("plane_angle", "&Angle between planes",
        window.measure_plane_angles,
        tip="Measure the angle between the planes defined so far "
            "-- one measurement per pair")
    add("clear_planes", "Clear pl&anes", window.clear_planes)
    add("clear_measurements", "Clear &measurements",
        window.clear_measurements)

    add("select_all", "Select &All", window.select_all, "Ctrl+A")
    # No key of its own: Escape is one action, and clearing the
    # selection is its last rung -- see MainWindow.cancel_gesture.
    # Two actions on the same key is an "ambiguous shortcut overload",
    # which is Qt for neither of them firing.
    add("select_none", "Select &None", window.select_none,
        tip="Escape, when there is no gesture or mode to leave first")
    add("invert_selection", "&Invert selection",
        window.invert_selection, "Ctrl+I")
    add("select_same", "Select same &element",
        window.select_same_element)
    add("expand_bonded", "Grow to &bonded neighbours",
        lambda: window.expand_selection("shell"), "Ctrl+G")
    add("expand_fragment", "Grow to whole &fragment",
        lambda: window.expand_selection("fragment"),
        "Ctrl+Shift+G")
    add("expand_orbit", "Grow to symmetry &orbit",
        lambda: window.expand_selection("orbit"))
    add("delete_selection", "&Delete", window.delete_selection,
        ["Del", "Backspace"],
        tip="Delete whichever is selected: the bonds if bonds "
            "are, otherwise the sites")
    add("delete_bond", "Delete &bond", window.delete_bonds,
        tip="Suppress the selected bonds, and their whole "
            "symmetry orbit")
    add("change_element", "Change &element...",
        window.change_element)
    add("reduce_p1", "Reduce to &P1", window.reduce_to_p1,
        tip="Expand every symmetry orbit into independent sites")

    add("find_symmetry", "&Find symmetry...", window.find_symmetry,
        "Ctrl+Shift+F",
        tip="Detect the space group at a tolerance and adopt it")
    add("set_space_group", "&Set space group...",
        window.set_space_group,
        tip="Choose a group and generate or impose it")
    add("standardize", "S&tandardise cell",
        lambda: window.standardize_cell(False),
        tip="Rebuild in the conventional setting of the detected "
            "group")
    add("primitive", "Reduce to pri&mitive cell",
        lambda: window.standardize_cell(True))
    add("wyckoff", "Assign &Wyckoff letters", window.assign_wyckoff)
    add("subgroup", "&Descend to a subgroup...",
        window.descend_to_subgroup,
        tip="Drop to a maximal subgroup so that an orbit splits "
            "and its atoms become independent")
    add("invert", "&Invert the structure", window.invert_structure,
        tip="The same crystal in the other hand: the coordinates "
            "and the space group together")
    add("merge_duplicates", "Merge &duplicate sites...",
        window.merge_duplicates,
        tip="Merge sites of the same element that are the same "
            "atom, symmetry images included")

    add("supercell", "&Supercell...", window.supercell_dialog,
        tip="na x nb x nc, or a general integer transformation")
    add("edit_cell", "&Edit cell...", window.edit_cell,
        tip="Change the cell parameters, keeping fractional or "
            "cartesian coordinates")
    add("niggli", "&Niggli reduction",
        lambda: window.reduce_cell("niggli"),
        tip="The shortest, most orthogonal basis for this cell")
    add("delaunay", "&Delaunay reduction",
        lambda: window.reduce_cell("delaunay"))
    add("wrap_cell", "&Wrap atoms into the cell",
        window.wrap_into_cell)
    add("display_range", "Display &range...",
        window.display_range_dialog, "Ctrl+R",
        tip="How much of the crystal to draw")

    add("single_point", "&Single point energy",
        window.single_point_energy, "Ctrl+E",
        tip="Energy and per-term breakdown at this geometry")
    add("optimize", "&Optimise geometry", window.optimize_geometry,
        "Ctrl+Shift+E",
        tip="Relax the structure within its space group")
    add("show_ff", "&Force Field panel", window.show_force_field,
        tip="Atom types, electrostatics, and how the run is going")

    # DFTB+'s own three, the same shape as UFF's above and kept
    # deliberately unshortcut'd: Ctrl+E and Ctrl+Shift+E already
    # mean "run UFF", and a DFTB+ run is launched from its own
    # panel or the Modules menu rather than a reflex keystroke.
    add("dftb_single_point", "DFTB+: &Single point energy",
        window.dftb_single_point,
        tip="Energy and per-term breakdown at this geometry, "
            "through DFTB+")
    add("dftb_optimize", "DFTB+: &Optimise geometry",
        window.dftb_optimize,
        tip="Relax the structure within its space group, "
            "through DFTB+")
    add("show_dftb", "DFTB&+ panel", window.show_dftb_panel,
        tip="Hamiltonian, parameter set, dispersion, and how the "
            "run is going")

    add("reset_layout", "Reset &layout", window.reset_layout,
        tip="Put the panels back where they started")
    # All four are on the toolbar now, where a button with no tooltip
    # is a button nobody presses twice.
    add("reset_view", "&Reset view", window.reset_view, "Ctrl+0",
        tip="Frame the whole of what is drawn again")
    add("view_a", "Along &a", lambda: window.look_along(0), "1",
        tip="Look down the a axis")
    add("view_b", "Along &b", lambda: window.look_along(1), "2",
        tip="Look down the b axis")
    add("view_c", "Along &c", lambda: window.look_along(2), "3",
        tip="Look down the c axis")
    add("about", f"About {APP_NAME}", window.show_about,
        role=QAction.MenuRole.AboutRole)
    add("show_log", "Show &Log", window.show_log,
        tip="Reveal the file this application writes its warnings "
            "and its crashes to")
    add("help_contents", f"{APP_NAME} &Help", window.show_help,
        QKeySequence.StandardKey.HelpContents,
        tip="Every command and every module setting, generated from "
            "the application itself")

def build_menus(window):
    bar = window.menuBar()

    file_menu = bar.addMenu("&File")
    window.actions_.fill_menu(file_menu, ["new", "open"])
    # The three ways to open something, together.  Recent was below
    # Close, at the far end of a menu whose top is where somebody
    # opening a file is looking.
    window.recent_menu = file_menu.addMenu("Open &Recent")
    window._rebuild_recent_menu()
    window.sample_menu = file_menu.addMenu("Open Sa&mple")
    build_sample_menu(window)
    window.actions_.fill_menu(file_menu, [
        None, "save", "save_as",
        None, "export", "export_image",
        "save_building_block",
        None, "new_workspace", "open_workspace",
        None, "close_tab", "close_all_tabs"])
    file_menu.addSeparator()
    # Both of these are drawn here on Windows and Linux and are moved
    # into the application menu on macOS, by the roles they carry.
    window.actions_.fill_menu(file_menu, ["preferences", None, "quit"])

    edit_menu = bar.addMenu("&Edit")
    window.actions_.fill_menu(edit_menu, [
        "undo", "redo", None, "cut", "copy", "paste", "duplicate",
        None, "delete_selection", "delete_bond",
        "change_element"])

    select_menu = bar.addMenu("&Select")
    window.actions_.fill_menu(select_menu, [
        "select_all", "select_none", "invert_selection", None,
        "select_same"])
    window.element_menu = select_menu.addMenu("By &element")
    grow_menu = select_menu.addMenu("&Grow")
    window.actions_.fill_menu(grow_menu, ["expand_bonded",
                                        "expand_fragment",
                                        "expand_orbit"])

    structure_menu = bar.addMenu("S&tructure")
    window.actions_.fill_menu(structure_menu, [
        "add_atom_dialog", "add_centroid", "add_hydrogens",
        "insert_molecule", "mark_connection_points", None,
        "bond_rules", "recompute_bonds", "reset_bonds",
        "bonds_follow"])
    window.bond_type_menu = add_bond_type_menu(window,
                                              structure_menu)
    structure_menu.addSeparator()
    # A submenu and not six flat entries: these are what the *mouse*
    # does, and under the bond commands they made the bottom of
    # Structure read as though a mode were an edit.
    window.mode_menu = structure_menu.addMenu("Mouse &mode")
    window.actions_.fill_menu(window.mode_menu,
                            [f"mode_{n}" for n in modes.names()])

    symmetry_menu = bar.addMenu("S&ymmetry")
    window.actions_.fill_menu(symmetry_menu, [
        "find_symmetry", "set_space_group", "subgroup", None,
        "standardize", "primitive", None,
        "wyckoff", "merge_duplicates", "invert",
        None, "reduce_p1"])

    cell_menu = bar.addMenu("&Cell")
    window.actions_.fill_menu(cell_menu, [
        "edit_cell", "supercell", None,
        "niggli", "delaunay", None, "wrap_cell"])

    measure_menu = bar.addMenu("&Measure")
    window.actions_.fill_menu(measure_menu, [
        "measure_selection", None,
        "define_plane", "plane_angle", None,
        "clear_planes", "clear_measurements"])

    view_menu = bar.addMenu("&View")
    style_menu = view_menu.addMenu("&Style")
    window.actions_.fill_menu(
        style_menu, [f"style_{n}" for n in styles.names()])
    show_menu = view_menu.addMenu("&Show")
    window.actions_.fill_menu(
        show_menu, ["show_atoms", "show_bonds", "show_bond_orders",
                    "show_topology", "show_cell", "show_planes",
                    "labels", "show_legend", "show_scale_bar"])
    view_menu.addSeparator()
    background_menu = view_menu.addMenu("&Background")
    for name in BACKGROUNDS:
        background_menu.addAction(
            name.capitalize(),
            lambda checked=False, n=name: window.set_background(n))
    background_menu.addSeparator()
    background_menu.addAction("Custom...", window.choose_background)
    view_menu.addSeparator()
    window.actions_.fill_menu(view_menu, ["display_range"])
    add_boundary_menu(window, view_menu)
    window.actions_.fill_menu(view_menu, [
        None, "orthographic", "depth_cue",
        None, "view_a", "view_b", "view_c", "reset_view"])

    window.modules_menu = bar.addMenu("&Modules")
    build_modules_menu(window)

    # Created here and filled by :func:`xtalapp.layout.build_docks`,
    # which is where the docks it lists come from.  It used to add a
    # menu of its own, and because that runs after this function the
    # Window menu landed after Help -- the menu bar's order was a
    # property of two files' call order rather than of either file's
    # contents, which is how it could be wrong with no line looking
    # wrong.  The whole order is here now, and it reads as it reads.
    window.window_menu = bar.addMenu("&Window")

    help_menu = bar.addMenu("&Help")
    window.actions_.fill_menu(help_menu, ["help_contents", None,
                                          "show_log", None, "about"])

def build_sample_menu(window) -> None:
    """The structures that ship with the application, as one submenu.

    Built once and never refreshed, unlike the Modules menu: a
    module's binary can be installed while the window is open, and
    these files cannot -- they are part of the installation itself.

    A copy that has not got them is a real state rather than a broken
    one: ``resources/`` is not package data, so a wheel install has no
    samples exactly as it has no bundled Zeo++.  That gets a disabled
    menu carrying the reason, which is the same answer a module with
    no binary gives, and not seven entries that each raise a dialog.
    """
    menu = window.sample_menu
    menu.clear()
    present = samples.installed()
    menu.setEnabled(bool(present))
    menu.setToolTip("" if present else samples.MISSING)
    for sample in samples.SAMPLES:
        action = window.actions_[f"sample_{sample.name}"]
        action.setEnabled(sample.path is not None)
        menu.addAction(action)

def build_modules_menu(window) -> None:
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
    menu = window.modules_menu
    menu.clear()
    window._module_actions = []
    window._module_submenus = {}
    for module in MODULES:
        submenu = menu.addMenu(module.label)
        window._module_submenus[module.name] = submenu
        for action in module.actions:
            submenu.addAction(module_action(window, module,
                                            action))
    if not MODULES.names():                     # pragma: no cover
        menu.addAction("Nothing registered").setEnabled(False)
    menu.aboutToShow.connect(window._refresh_module_availability)
    refresh_module_availability(window)

def refresh_module_availability(window) -> None:
    """Grey out what cannot run, with the reason as the tooltip.

    An external tool that is missing is the most common state it
    will be in, so the answer belongs where the module is rather
    than in the failure after clicking it.  ``Module.check`` is a
    ``shutil.which`` and there are a handful of modules, so asking
    again on every open costs nothing worth caching.

    The paths from Preferences are pushed into :mod:`xtal`'s lookup
    first, which is what makes a module whose binary was named there
    stop being greyed out without a restart -- and what keeps that
    true for a plugin's module, which this file has never heard of.
    """
    external.apply_hints(window.settings)
    for name, submenu in window._module_submenus.items():
        if name not in MODULES:                 # pragma: no cover
            continue
        module = MODULES.get(name)
        available = module.availability()
        submenu.setEnabled(bool(available))
        submenu.setToolTip(module.description if available
                           else available.reason)

def module_action(window, module, action):
    """The QAction for one module entry, made once and reused.

    An entry with a ``shell`` name is performed by the window
    action of that name -- which is how the three Force Field
    entries moved into this menu unchanged, keeping Ctrl+E and
    Ctrl+Shift+E and the panel behind them.  Everything else gets
    an action of its own, named ``module.<module>.<action>`` so
    that a keyboard shortcut, a test and the CLI all spell it the
    same way.
    """
    if action.shell and action.shell in window.actions_:
        return window.actions_[action.shell]
    name = f"module.{module.name}.{action.name}"
    window._module_actions.append((name, action.needs_structure))
    if name not in window.actions_:
        window.actions_.add(
            name, action.label,
            lambda checked=False, m=module.name, a=action.name:
                window.run_module_action(m, a),
            shortcut=action.shortcut, tip=action.tip)
    return window.actions_[name]

def build_toolbar(window):
    """The toolbar, in three groups: the file and the undo stack, what
    the mouse does, and what is being looked at.

    Two things sat in the wrong group before ``docs/MENUS.md``.  The
    element combo is *the element Add atom places* -- its own tooltip
    says so -- and it stood two controls away from that button on the
    far side of a separator, beside Recalculate bonds, which it has
    nothing to do with.  Reset view was grouped with Undo and Redo,
    which reads as though it undid something.
    """
    bar = QToolBar("Main")
    bar.setObjectName("MainToolBar")
    bar.setMovable(False)
    window.actions_.fill_menu(bar, ["open", "save", None, "undo",
                                  "redo"])
    bar.addSeparator()

    window.element_combo = QComboBox()
    window.element_combo.setEditable(True)
    window.element_combo.addItems(
        ["H", "C", "N", "O", "F", "Na", "Si", "P", "S", "Cl",
         "Ca", "Ti", "Fe", "Co", "Ni", "Cu", "Zn", "Br", "I"])
    window.element_combo.setCurrentText("C")
    window.element_combo.setToolTip("Element placed by Add atom")
    window.element_combo.currentTextChanged.connect(
        window._on_element_changed)
    for name in modes.names():
        bar.addAction(window.actions_[f"mode_{name}"])
        if name == ELEMENT_MODE:
            bar.addWidget(window.element_combo)
    bar.addSeparator()
    bar.addAction(window.actions_["recompute_bonds"])
    bar.addSeparator()
    bar.addWidget(QLabel("  cells "))
    window.cell_spins = []
    for axis in "abc":
        spin = QSpinBox()
        spin.setRange(1, 20)
        spin.setValue(1)
        spin.setToolTip(f"Unit cells shown along {axis}")
        spin.valueChanged.connect(window._on_cells_changed)
        # The axis letter is a label beside the box, not the
        # spinbox's prefix.  A prefix is drawn *inside* the field, so
        # the box read "a 1" -- the letter sitting where the number
        # is, in the space the user clicks into to type one.
        bar.addWidget(QLabel(f" {axis} "))
        bar.addWidget(spin)
        window.cell_spins.append(spin)
    bar.addSeparator()

    # The axis views are as often pressed as Reset view and were on no
    # toolbar at all.  They are labelled by their letter here and stay
    # "Along a" in the View menu: a toolbar button shows the action's
    # *icon text*, which is the one place a shorter spelling belongs.
    # The word before them is what keeps three bare letters from being
    # read as more cell counts.
    bar.addAction(window.actions_["reset_view"])
    bar.addWidget(QLabel("  along "))
    for axis, name in zip("abc", ["view_a", "view_b", "view_c"],
                          strict=True):
        action = window.actions_[name]
        action.setIconText(axis)
        bar.addAction(action)
    window.addToolBar(bar)
    window.toolbar = bar

def context_menu(window, kind: str):
    """The menu for whatever was right-clicked, or ``None``.

    Built here rather than in the viewport because the actions live
    in this window's registry -- which is what keeps a context-menu
    entry and a menu-bar entry the same object, enabled and
    disabled by the same rule.
    """
    names = window.CONTEXT_MENUS.get(kind)
    if not names:
        return None
    count = selection_count(window, kind)
    noun = {"atom": "atoms", "bond": "bonds"}.get(kind, "")

    menu = QMenu(window)
    for name in names:
        if name is None:
            menu.addSeparator()
        elif name == window.BOND_TYPE_MENU:
            add_bond_type_menu(window, menu)
        elif name == window.BOUNDARY_MENU:
            add_boundary_menu(window, menu)
        elif name == window.MEASURE_ENTRY:
            add_measure(window, menu, count, kind)
        elif name in window.COUNTED_ACTIONS and count > 1:
            add_counted(window, menu, name, count, noun)
        else:
            menu.addAction(window.actions_[name])
    if kind == "view":
        style = menu.addMenu("&Style")
        window.actions_.fill_menu(
            style, [f"style_{n}" for n in styles.names()])
    return menu

def add_boundary_menu(window, menu):
    """The three boundary answers, wherever they are wanted.

    Parented to the menu it is added to, for the reason spelled out
    in :func:`add_bond_type_menu`: a submenu built by ``addMenu(title)``
    alone is owned by Python and is collected the moment this returns.
    """
    submenu = QMenu("Bonds at the &boundary", menu)
    menu.addMenu(submenu)
    window.actions_.fill_menu(
        submenu, [f"boundary_{n}" for n, _l, _t in BOUNDARY_ACTIONS])


def add_bond_type_menu(window, menu):
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
    submenu.setEnabled(window.actions_["bond_type_single"].isEnabled())
    window.actions_.fill_menu(
        submenu, [f"bond_type_{n.lower()}" for n, _ in BOND_TYPES])
    return submenu

#: What each number of selected atoms admits.  One entry and not
#: three, and *absent* at any other count rather than greyed out:
#: "Measure" over one atom is not something that would happen if
#: only the right thing were enabled.
MEASURE_LABELS = {2: "&Measure distance", 3: "&Measure angle",
                  4: "&Measure dihedral"}


def bond_measure_label(count: int) -> str | None:
    """What measuring this many selected bonds is called.

    A bond admits exactly one measurement whatever the count -- it is
    a pair of atoms and the answer is a length -- so the count changes
    the wording rather than the question.  It is said for the reason
    :data:`MainWindow.COUNTED_ACTIONS` exists: a box drawn round a
    linker selects eleven bonds, and "Measure bond length" over
    eleven of them promises one row and delivers eleven.
    """
    if count < 1:
        return None
    if count == 1:
        return "&Measure bond length"
    return f"&Measure {count} bond lengths"


def add_measure(window, menu, count: int, kind: str = "atom"):
    """The one measurement this selection admits, or nothing at all.

    A fresh action rather than the registry's own, for the reason
    given in :func:`add_counted`: the registry's is the object the
    menu bar shows, and renaming it here would rename it there.
    """
    label = (bond_measure_label(count) if kind == "bond"
             else MEASURE_LABELS.get(count))
    if label is None:
        return None
    action = window.actions_["measure_selection"]
    entry = menu.addAction(label)
    entry.setEnabled(action.isEnabled())
    entry.triggered.connect(action.trigger)
    return entry


def add_counted(window, menu, name: str, count: int, noun: str):
    """A menu entry that says what it will act on.

    A fresh action rather than the registry's own, because the
    registry's is the same object the menu bar shows: renaming it
    for one click would rename it for good.  This one carries the
    count and triggers the real thing.
    """
    action = window.actions_[name]
    entry = menu.addAction(
        window.COUNTED_ACTIONS[name].format(n=count, noun=noun))
    entry.setEnabled(action.isEnabled())
    entry.triggered.connect(action.trigger)
    return entry

def selection_count(window, kind: str) -> int:
    document = window.current_document()
    if document is None:
        return 0
    return {"atom": len(document.selection.atoms),
            "bond": len(document.selection.bonds)}.get(kind, 0)
