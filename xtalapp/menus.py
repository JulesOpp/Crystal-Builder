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

import os
import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QMenu,
    QToolBar,
    QToolButton,
)

from xtal.commands.bonds import BOND_TYPES
from xtal.modules import MODULES
from xtalapp import external, samples
from xtalapp.viewport import modes, styles
from xtalapp.viewport.view_settings import (
    BACKGROUNDS,
    DEFAULT_STYLE,
    FOLLOW_THE_SYSTEM,
    ViewSettings,
)
from xtalapp.widgets.periodic_table import PeriodicTableToolButton

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


#: What "show it in the file browser" is called where the user is.
#: Qt has no name for it, and "Reveal in Finder" on Windows reads as
#: a different program.
REVEAL_LABEL = ("&Reveal in Finder" if sys.platform == "darwin"
                else "Show in &Explorer" if os.name == "nt"
                else "Show in &File Manager")


#: The tooltip on ``Insert molecule...`` when it is available.  Named
#: because the window puts :data:`xtal.build.MISSING` there instead
#: when RDKit is not installed, and has to be able to put this back.
MOVE_ORIGIN_TIP = (
    "Put the cell's corner somewhere else, so that a cluster cut in "
    "two by a face comes out whole: every atom moves and is folded "
    "back into the cell, its bonds with it.  P1 only.")
#: Why Move origin is greyed: the group's operations are written about
#: the origin, and the group at a new one cannot be named.
MOVE_ORIGIN_NEEDS_P1 = (
    "Moving the origin needs P1: the space group's operations are "
    "written about this origin.  Symmetry > Reduce to P1 first.")

INSERT_MOLECULE_TIP = (
    "Build a molecule from a SMILES string and paste it into this "
    "structure.  It arrives with the bonds the builder gave it and "
    "no others, and pasting into a group with symmetry multiplies it "
    "-- the dialog says by how much before you press the button.")
#: Save as a monomer: on when there are two connection points, and
#: otherwise greyed with :data:`SAVE_MONOMER_NEEDS_TWO`.
SAVE_MONOMER_TIP = (
    "Write this molecule into the workspace's monomers, so the polymer "
    "builder lists it beside its own.  Its two connection points are "
    "the head and the tail, and the dialog asks which is which.")
SAVE_MONOMER_NEEDS_TWO = (
    "A monomer needs exactly two connection points, a head and a tail "
    "-- this has {count}.  Building blocks > Mark connection points "
    "makes them; for a ladder, Mark as one connection point.")


def submenu(parent, title: str) -> QMenu:
    """A menu under *parent* -- a menu bar or a menu -- that it owns.

    ``parent.addMenu(title)`` is the obvious spelling and it hands
    back a wrapper that PySide6 can invalidate while the C++ menu
    goes on living: the wrapper is tied to the temporary ``QAction``
    the walk over ``parent.actions()`` produced, and dies with it.
    Nothing looks wrong afterwards -- the menu still drops down and
    still lists its entries -- but every handle stored on the window
    raises ``Internal C++ object already deleted`` the next time it
    is read.  Generating the help pages walks the whole menu bar,
    which is how opening Help once made the next edit to a structure
    crash in ``_rebuild_element_menu``.

    Constructing the menu with its parent and adding it as an object
    ties the wrapper to the parent menu instead, which outlives every
    walk.  Every submenu in this module goes through here, stored on
    the window or not: the ones that are only ever shown are as easy
    to store later as they are to leave alone now.
    """
    menu = QMenu(title, parent)
    parent.addMenu(menu)
    return menu

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
    add("export_net", "Export &net for Systre...", window.export_net,
        tip="The net drawn on this structure as a .cgd file, for "
            "Systre to name -- a second opinion on the Net panel that "
            "does not come from the code that gave the first")
    add("export_stl", "Export as S&TL...", window.export_stl,
        tip="One unit cell with its bonds, as a mesh a 3D printer can "
            "take.  Blender does the meshing, so it has to be "
            "installed -- see Preferences > Engines")
    add("render_blender", "Render in &Blender...", window.render_in_blender,
        tip="One unit cell with its bonds, lit and rendered by "
            "Blender, the scene kept beside the picture.  Blender has "
            "to be installed -- see Preferences > Engines")
    add("open_workspace", "&Open workspace...",
        window.open_workspace_dialog,
        tip="A folder that structures and their calculations live "
            "in")
    add("new_workspace", "&New workspace...",
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
            checkable=True, checked=(name == DEFAULT_STYLE),
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
    add("show_axes", "Cell axes (a, b, c)",
        lambda v: window.set_view(show_axes=v), checkable=True,
        checked=True,
        tip="The triad in the corner of the view: which way a, b "
            "and c point as the structure turns")
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
    add("show_pores", "Pore network",
        lambda v: window.set_view(show_pores=v), checkable=True,
        checked=True,
        tip="Draw the channel skeleton and the surface a porosity "
            "run found.  The pore sphere is its own box in the Style "
            "panel.  Nothing is drawn until Modules > Zeo++ has "
            "answered")
    add("show_only_selected", "Show &only selected",
        window.show_only_selected,
        tip="Draw the selected atoms and nothing else -- every phenol, "
            "say, to see what a substitution did to them.  Only the "
            "picture changes: the hidden atoms are still in the "
            "structure, and in every calculation and every save")
    add("show_all", "Show a&ll", window.show_all,
        tip="Draw every atom again after Show only selected, and "
            "tick every hidden atom group")
    add("group_selected", "&Group selected atoms...",
        window.group_selected, "Ctrl+G",
        tip="Name the selected atoms as an atom group, listed in the "
            "Style panel, where it can be coloured, hidden and "
            "selected again.  Only the picture changes")
    add("color_selected", "&Colour selected atoms...",
        window.color_selected,
        tip="Draw the selected atoms, and their halves of each bond, "
            "in a colour of your choosing -- a new atom group in the "
            "Style panel.  The elements and every save are untouched")
    add("hide_selected", "&Hide selected", window.hide_selected,
        tip="Leave the selected atoms out of the picture as a hidden "
            "atom group; its tick in the Style panel shows them "
            "again.  They stay in the structure and every calculation")
    add("clear_overlays", "Clear c&harges and orbital",
        window.clear_overlays,
        tip="Take a DFTB+ run's atom colouring and orbital lobes off "
            "the picture.  They go by themselves when the atoms move")
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
    add("merge_atoms", "Mer&ge atoms", window.merge_atoms,
        tip="Replace the selected atoms with one at their middle -- "
            "of their element when they share one, a dummy atom when "
            "they do not.  Whole orbits go, as with Delete, and the "
            "new atom is bonded to nothing")
    add("add_hydrogens", "Add &hydrogens...",
        window.add_hydrogens_dialog,
        tip="Complete every main-group coordination with the "
            "hydrogens an X-ray structure never had")
    add("substitute_rings", "Su&bstitute hydrogens...",
        window.substitute_dialog,
        tip="Replace the selected hydrogens (or fluorines), or one on "
            "every aromatic ring, with a group -- NH2, OH, OMe, NO2, an "
            "acetyl, a phenyl, or one you draw -- bonded to the atom "
            "the hydrogen was on and to nothing else")
    add("fill_pores", "&Fill pores with molecules...",
        window.fill_pores_dialog,
        tip="Put copies of a molecule -- from another tab or a file "
            "-- into the empty space of this structure, each where it "
            "touches nothing -- or one beside each selected atom, for "
            "a charged framework's counter-ions, or one at a fractional "
            "point.  A host with symmetry is reduced to P1 first unless "
            "a point keeps it, and bonds are not recalculated")
    add("interpenetrate", "Interpe&netrate...",
        window.interpenetrate_dialog,
        tip="Thread copies of this framework through its own pores: "
            "every placement the lattice allows is measured, and one "
            "where atoms of two copies would meet cannot be chosen.  "
            "The copies keep their bonds, and the result is in P1")
    add("prepare_simulation", "&Prepare for simulation...",
        window.prepare_dialog,
        tip="Make a deposited structure one a calculation can use: "
            "order the disorder into whole atoms, remove solvent, "
            "complete M3O trimers, add the missing hydrogens and take "
            "the primitive cell -- each step saying what it chose "
            "before anything is done, and one undo step for the lot")
    add("insert_molecule", "&Insert molecule...",
        window.insert_molecule_dialog, tip=INSERT_MOLECULE_TIP)
    add("save_building_block", "Save as a &building block...",
        window.save_building_block,
        tip="Write this molecule into the folder the MOF builder "
            "reads, so it appears in the block picker beside the 867 "
            "PORMAKE ships.  It needs connection points on it -- the "
            "dialog says what is missing.")
    add("save_monomer", "Save as a mo&nomer...", window.save_monomer,
        tip=SAVE_MONOMER_TIP)
    add("mark_connection_points", "&Mark connection points",
        window.mark_connection_points,
        tip="Turn each selected atom that has exactly one bond into "
            "a connection point: a dummy 0.75 A along that bond, "
            "which is what a PORMAKE building block is joined by.  "
            "There is no unmark -- an X does not remember what it "
            "was, so the way back is Ctrl+Z.")
    add("mark_one_connection_point", "Mark as &one connection point",
        window.mark_one_connection_point,
        tip="Collapse the selected atoms into a single connection "
            "point, 0.75 A from the middle of everything they were "
            "bonded to and carrying those bonds.  For a chelate: two "
            "atoms that meet the next block together are one joint, "
            "and marking them separately gives a block with twice "
            "the coordination number it has.")
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
    add("assign_eqeq_charges", "Assign &EQeq charges",
        window.assign_eqeq_charges,
        tip="Equilibrate charges over the cell (Wilmer, Kim and Snurr "
            "2012) and write them onto the sites, where a CIF's "
            "_atom_site_charge and a LAMMPS file's q carry them.  An "
            "estimate to look over, as the status bar says")
    add("keep_shown_charges", "&Keep the charges shown",
        window.keep_shown_charges,
        tip="Write the charges drawn over the atoms -- a DFTB+ "
            "Mulliken run's -- onto the sites, so a save or an export "
            "carries them")
    add("clear_site_charges", "&Clear the sites' charges",
        window.clear_site_charges,
        tip="Take every charge off the sites, oxidation states read "
            "from the file included")
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

    # Ctrl+1 to Ctrl+7, in the toolbar's order: the modes are pressed
    # more than anything but the camera, and the bare digits already
    # look along a, b and c.  Ctrl+0, beside them, resets the view.
    for number, mode_name in enumerate(modes.names(), start=1):
        mode = modes.get(mode_name)
        add(f"mode_{mode_name}", mode.label,
            lambda checked=False, m=mode_name: window.set_mode(m),
            f"Ctrl+{number}" if number < 10 else None,
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

    add("select_all", "Select &all", window.select_all, "Ctrl+A")
    # No key of its own: Escape is one action, and clearing the
    # selection is its last rung -- see MainWindow.cancel_gesture.
    # Two actions on the same key is an "ambiguous shortcut overload",
    # which is Qt for neither of them firing.
    add("select_none", "Select &none", window.select_none,
        tip="Escape, when there is no gesture or mode to leave first")
    add("invert_selection", "&Invert selection",
        window.invert_selection, "Ctrl+I")
    add("select_same", "Select same &element",
        window.select_same_element)
    add("select_bonds", "&Bonds between elements...",
        window.select_bonds_between,
        tip="Select every bond joining two elements, and no atoms -- "
            "so Delete and Bond type act on those bonds alone")
    add("select_dialog", "&Advanced selection...",
        window.open_select_dialog,
        tip="Select by label, coordination, what an atom is bonded "
            "to, a box, a point, or bonds by length and order -- and "
            "add, remove or intersect with what is held")
    add("expand_bonded", "Grow to &bonded neighbours",
        lambda: window.expand_selection("shell"))
    add("expand_neighbours", "Grow to &neighbours only",
        lambda: window.expand_selection("neighbours"),
        tip="The atoms one bond from the selection, and the "
            "selection let go")
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
    add("invert", "&Mirror the structure (change hand)",
        window.invert_structure,
        tip="The same crystal in the other hand: the coordinates "
            "and the space group together")
    add("merge_duplicates", "Merge &duplicate sites...",
        window.merge_duplicates,
        tip="Merge sites of the same element that are the same "
            "atom, symmetry images included")

    add("supercell", "&Supercell...", window.supercell_dialog,
        tip="na x nb x nc, or a general integer transformation")
    add("slab", "S&lab...", window.slab_dialog,
        tip="Cut a slab along a lattice plane (hkl), with vacuum "
            "above it")
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
    add("move_origin", "Move &origin...", window.move_origin_dialog,
        tip=MOVE_ORIGIN_TIP)
    add("display_range", "Display &range...",
        window.display_range_dialog, "Ctrl+R",
        tip="How much of the crystal to draw")

    add("single_point", "&Single point energy",
        window.single_point_energy, "Ctrl+E",
        tip="Energy and per-term breakdown at this geometry")
    add("optimize", "&Optimise geometry", window.optimize_geometry,
        "Ctrl+Shift+E",
        tip="Relax the structure within its space group")
    add("show_ff", "&Setup and atom types...", window.show_force_field,
        tip="Atom types, electrostatics, and how the run is going")

    # DFTB+'s own three, the same shape as UFF's above and kept
    # deliberately unshortcut'd: Ctrl+E and Ctrl+Shift+E already
    # mean "run UFF", and a DFTB+ run is launched from its own
    # panel or the Modules menu rather than a reflex keystroke.
    add("dftb_single_point", "&Single point energy",
        window.dftb_single_point,
        tip="Energy and per-term breakdown at this geometry, "
            "through DFTB+")
    add("dftb_optimize", "&Optimise geometry",
        window.dftb_optimize,
        tip="Relax the structure within its space group, "
            "through DFTB+")
    add("show_dftb", "DFTB&+ panel", window.show_dftb_panel,
        tip="Hamiltonian, parameter set, dispersion, and how the "
            "run is going")
    add("refine_workbench", "Refine against a measured pattern...",
        window.open_refine_workbench,
        tip="Fit peaks and refine against a measured .xy pattern, in "
            "a window of its own; the runs go under the structure in "
            "front, or under the pattern's name if none is open")

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
    add("workspace_open", "&Open", window.open_selected_artifact,
        tip="Open what is selected in the Workspace panel -- the same "
            "as double-clicking it.")
    add("workspace_reveal", REVEAL_LABEL, window.reveal_selected_artifact,
        tip="Show the selected file or run folder in the desktop's own "
            "file browser.")
    add("workspace_copy_path", "&Copy path",
        window.copy_selected_artifact_path,
        tip="Put the full path of what is selected on the clipboard, "
            "for a script or a terminal.")
    add("workspace_rename", "Re&name...", window.rename_selected_artifact,
        tip="Give the selected file a new name in the same folder.  A "
            "tab open on it follows, and a name already taken is "
            "refused rather than written over.")
    add("workspace_trash", "Move to &Trash", window.trash_selected_run,
        tip="Put a run's folder in the desktop's wastebasket.  Only a "
            "run: the structure it was run on stays, and nothing here "
            "is ever deleted outright.")
    add("show_log", "Show &log file", window.show_log,
        tip="Reveal the file this application writes its warnings "
            "and its crashes to")
    add("install_ai_skill", "Set up an &AI assistant",
        window.install_ai_skill,
        tip="Put the crystal-builder skill where Claude Code reads it "
            "(~/.claude/skills), so an assistant can open, prepare, "
            "build, inspect and relax structures in your workspace "
            "through the same commands as this window.  A copy you "
            "have edited is replaced only if you say so.")
    add("connect_ai_assistant", "&Connect an AI assistant...",
        window.connect_ai_assistant,
        tip="Let an assistant such as Claude Code work in this window: "
            "the tabs open here are its documents, each thing it does "
            "is one step Ctrl+Z takes back, and the status bar says "
            "what it did.  Opens Preferences on the switch and the "
            "line to paste into the assistant.")
    add("help_contents", f"{APP_NAME} &Help", window.show_help,
        QKeySequence.StandardKey.HelpContents,
        tip="Every command and every module setting, generated from "
            "the application itself")
    add("user_manual", "User &Manual", window.show_manual,
        tip="The user manual in your browser: a quickstart, the tasks "
            "chapter by chapter, and each method's theory and "
            "references.  It is the copy that came with this "
            "application; only its equations need a connection, to "
            "fetch MathJax.")

def build_menus(window):
    bar = window.menuBar()

    file_menu = submenu(bar, "&File")
    window.actions_.fill_menu(file_menu, ["new", "open"])
    # The three ways to open something, together.  Recent was below
    # Close, at the far end of a menu whose top is where somebody
    # opening a file is looking.
    window.recent_menu = submenu(file_menu, "Open &Recent")
    window._rebuild_recent_menu()
    window.sample_menu = submenu(file_menu, "Open Sa&mple")
    build_sample_menu(window)
    window.actions_.fill_menu(file_menu, [
        None, "save", "save_as",
        None, "export", "export_net", "export_image", "export_stl",
        "render_blender",
        None, "new_workspace", "open_workspace",
        None, "close_tab", "close_all_tabs"])
    file_menu.addSeparator()
    # Both of these are drawn here on Windows and Linux and are moved
    # into the application menu on macOS, by the roles they carry.
    window.actions_.fill_menu(file_menu, ["preferences", None, "quit"])

    edit_menu = submenu(bar, "&Edit")
    window.actions_.fill_menu(edit_menu, [
        "undo", "redo", None, "cut", "copy", "paste", "duplicate",
        None, "delete_selection", "delete_bond"])

    select_menu = submenu(bar, "&Select")
    # Same element and By element are one intent and sit together;
    # Grow, which starts from a selection rather than making one, last.
    window.actions_.fill_menu(select_menu, [
        "select_all", "select_none", "invert_selection", None,
        "select_same"])
    window.element_menu = submenu(select_menu, "By &element")
    window.actions_.fill_menu(select_menu, [
        "select_bonds", "select_dialog", None])
    grow_menu = submenu(select_menu, "&Grow")
    window.actions_.fill_menu(grow_menu, ["expand_bonded",
                                        "expand_neighbours",
                                        "expand_fragment",
                                        "expand_orbit"])

    # What is added, then what it is joined by, then what it is for:
    # atoms, groups, whole molecules; the bond commands in one place;
    # the framework builder's markers; Prepare last, because it is a
    # rebuild of everything above.  Change element was in Edit, beside
    # Delete, and Save as a building block in File, beside the
    # exports; each is where the others of its kind are now.
    structure_menu = submenu(bar, "S&tructure")
    window.actions_.fill_menu(structure_menu, [
        "add_atom_dialog", "add_centroid", "merge_atoms",
        "change_element",
        None, "add_hydrogens", "substitute_rings",
        None, "insert_molecule", "fill_pores", "interpenetrate",
        None])
    # Six bond entries and a submenu made the middle of Structure a
    # list to read through; as one submenu they are one entry to find.
    # The same actions, so Recalculate bonds keeps its toolbar button
    # and Reset bonds its Ctrl+B.
    bonds_menu = submenu(structure_menu, "&Bonds")
    window.actions_.fill_menu(bonds_menu, ["recompute_bonds",
                                           "reset_bonds"])
    window.bond_type_menu = add_bond_type_menu(window, bonds_menu)
    window.actions_.fill_menu(bonds_menu, [None, "bond_rules",
                                           "bonds_follow"])
    charges_menu = submenu(structure_menu, "C&harges")
    window.actions_.fill_menu(charges_menu, [
        "assign_eqeq_charges", "keep_shown_charges", None,
        "clear_site_charges"])
    blocks_menu = submenu(structure_menu, "Building b&locks")
    window.actions_.fill_menu(blocks_menu, [
        "mark_connection_points", "mark_one_connection_point",
        "save_building_block", "save_monomer"])
    window.actions_.fill_menu(structure_menu, [
        None, "prepare_simulation", None])
    # A submenu and not six flat entries: these are what the *mouse*
    # does, and under the bond commands they made the bottom of
    # Structure read as though a mode were an edit.
    window.mode_menu = submenu(structure_menu, "Mouse &mode")
    window.actions_.fill_menu(window.mode_menu,
                            [f"mode_{n}" for n in modes.names()])

    symmetry_menu = submenu(bar, "S&ymmetry")
    window.actions_.fill_menu(symmetry_menu, [
        "find_symmetry", "set_space_group", "subgroup", None,
        "standardize", "primitive", None,
        "wyckoff", "merge_duplicates",
        None, "invert", "reduce_p1"])

    cell_menu = submenu(bar, "&Cell")
    window.actions_.fill_menu(cell_menu, [
        "edit_cell", "supercell", "slab", None,
        "niggli", "delaunay", None, "wrap_cell", "move_origin"])

    measure_menu = submenu(bar, "&Measure")
    window.actions_.fill_menu(measure_menu, [
        "measure_selection", None,
        "define_plane", "plane_angle", None,
        "clear_planes", "clear_measurements"])

    view_menu = submenu(bar, "&View")
    style_menu = submenu(view_menu, "&Style")
    window.actions_.fill_menu(
        style_menu, [f"style_{n}" for n in styles.names()])
    show_menu = submenu(view_menu, "&Show")
    window.actions_.fill_menu(
        show_menu, ["show_atoms", "show_bonds", "show_bond_orders",
                    "show_topology", "show_cell", "show_axes",
                    "show_planes",
                    "show_pores", "labels", "show_legend",
                    "show_scale_bar", None, "clear_overlays"])
    window.actions_.fill_menu(view_menu, [
        "show_only_selected", "show_all", None, "group_selected",
        "color_selected", "hide_selected"])
    view_menu.addSeparator()
    background_menu = submenu(view_menu, "&Background")
    background_menu.addAction(
        "Follow the system",
        lambda checked=False: window.set_background(FOLLOW_THE_SYSTEM))
    background_menu.addSeparator()
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

    window.modules_menu = submenu(bar, "&Modules")
    build_modules_menu(window)

    # Created here and filled by :func:`xtalapp.layout.build_docks`,
    # which is where the docks it lists come from.  It used to add a
    # menu of its own, and because that runs after this function the
    # Window menu landed after Help -- the menu bar's order was a
    # property of two files' call order rather than of either file's
    # contents, which is how it could be wrong with no line looking
    # wrong.  The whole order is here now, and it reads as it reads.
    window.window_menu = submenu(bar, "&Window")

    help_menu = submenu(bar, "&Help")
    window.actions_.fill_menu(help_menu, ["help_contents", "user_manual",
                                          None, "install_ai_skill",
                                          "connect_ai_assistant",
                                          "show_log",
                                          None, "about"])

def build_sample_menu(window) -> None:
    """The structures that ship with the application, as one submenu.

    Built once and never refreshed, unlike the Modules menu: a
    module's binary can be installed while the window is open, and
    these files cannot -- they are part of the installation itself.

    A copy that has not got them is a real state rather than a broken
    one: ``resources/`` is not package data, so a wheel install has no
    samples exactly as it has no bundled Zeo++.  That gets a disabled
    menu carrying the reason, which is the same answer a module with
    no binary gives, and not thirteen entries that each raise a dialog.

    The COD's are a submenu of their own and not a titled section:
    a section title is not drawn in a native macOS menu, which would
    leave two entries called MOF-5 a separator apart and nothing to
    say which was which.
    """
    menu = window.sample_menu
    menu.clear()
    present = samples.installed()
    menu.setEnabled(bool(present))
    menu.setToolTip("" if present else samples.MISSING)
    for group, title in samples.GROUPS:
        if group == samples.SHIPPED:
            into = menu
        else:
            menu.addSeparator()
            into = _sample_group_menu(window, group, title)
            into.clear()
            menu.addMenu(into)
        for sample in samples.in_group(group):
            action = window.actions_[f"sample_{sample.name}"]
            action.setEnabled(sample.path is not None)
            into.addAction(action)


def _sample_group_menu(window, group: str, title: str) -> QMenu:
    """The submenu one group of samples goes in, made once per window.

    Kept on the window because :func:`build_sample_menu` runs again
    over a menu it has already filled, and a fresh ``QMenu`` each time
    would leave the last one parented to the menu, unseen.
    """
    menus = getattr(window, "sample_group_menus", None)
    if menus is None:
        menus = window.sample_group_menus = {}
    if group not in menus:
        menus[group] = QMenu(title, window.sample_menu)
    return menus[group]

def build_modules_menu(window) -> None:
    """The Modules menu, built from the registry and nothing else.

    ``Calculate`` held a single point, an optimisation and a panel
    toggle -- three entries that were all UFF, in a menu whose name
    promised everything that computes.  This one has a submenu per
    module and knows the name of none of them, so a module
    installed as a plugin appears here without this file changing.
    A separator falls wherever :attr:`Module.group` changes, which is
    all the grouping there is: a submenu per group would put every
    entry three levels down.

    The structure is built once; whether each module *can* run is
    asked again every time the menu opens
    (:meth:`_refresh_module_availability`), because an engine whose
    binary was installed while the window was open should stop
    being greyed out, and a menu that cached the answer would go on
    saying it is missing.
    """
    menu = window.modules_menu
    menu.clear()
    # A greyed module's tooltip is its reason, and QMenu shows none
    # unless asked to.
    menu.setToolTipsVisible(True)
    window._module_actions = []
    window._module_submenus = {}
    previous = None
    for module in MODULES:
        if not module.listed:
            continue                    # Blender: File is its way in
        if previous is not None and module.group != previous:
            menu.addSeparator()
        previous = module.group
        entry = submenu(menu, module.label)
        window._module_submenus[module.name] = entry
        for action in module.actions:
            if action.listed:
                entry.addAction(module_action(window, module,
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
    window._module_actions.append((name, action.needs_structure,
                                   action))
    if name not in window.actions_:
        window.actions_.add(
            name, action.label,
            lambda checked=False, m=module.name, a=action.name:
                window.run_module_action(m, a),
            shortcut=action.shortcut, tip=action.tip)
    return window.actions_[name]

class _OverflowStaysOpen(QToolBar):
    """A toolbar whose folded-away end stays out until its double arrow
    is pressed again.

    Qt closes it the moment the pointer leaves the bar -- so on a
    narrow window the cell counts and axis views in it closed under
    anybody whose path to them crossed the edge.  The Leave is what
    collapses it, and it is swallowed only while the bar is expanded:
    hover and the drag state see every other one.
    """

    def event(self, event) -> bool:
        if event.type() == QEvent.Leave and self._expanded():
            return True
        return super().event(event)

    def _expanded(self) -> bool:
        button = self.findChild(QToolButton, "qt_toolbar_ext_button")
        return button is not None and button.isChecked()


def _toolbar_label(text: str) -> QLabel:
    """A word on the toolbar, in the toolbar buttons' font.

    macOS draws a toolbar button in the small system font and a plain
    label in the application's, so "cells" and "along" stood 13 pt
    among buttons of 10.
    """
    label = QLabel(text)
    label.setFont(QApplication.font("QToolButton"))
    return label


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
    bar = _OverflowStaysOpen("Main")
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
    window.element_table = PeriodicTableToolButton(
        current=window.element_combo.currentText)
    window.element_table.chosen.connect(window.choose_element_to_place)
    for name in modes.names():
        bar.addAction(window.actions_[f"mode_{name}"])
        if name == ELEMENT_MODE:
            bar.addWidget(window.element_combo)
            bar.addWidget(window.element_table)
    bar.addSeparator()
    bar.addAction(window.actions_["recompute_bonds"])
    bar.addSeparator()
    bar.addWidget(_toolbar_label("  cells "))
    window.cell_spins = []
    for axis in "abc":
        # Fractional when typed, because half a cell more of a
        # framework is a picture people ask for and a whole cell more
        # is eight times the atoms.  The Display range dialog could
        # always say 1.5; this is the same range from the box beside
        # the view.  The arrows step whole cells: stepping by halves
        # made reaching 3 x 3 x 3 twelve clicks, and a fraction is a
        # deliberate choice that is typed rather than clicked past.
        spin = QDoubleSpinBox()
        spin.setRange(0.1, 20.0)
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        spin.setValue(1.0)
        # Typing "1.5" passes through 1 and 15 on the way, and every
        # one of those would rebuild the scene and reframe the camera.
        spin.setKeyboardTracking(False)
        spin.setToolTip(f"Unit cells shown along {axis} -- "
                        f"fractions allowed, such as 1.5")
        spin.valueChanged.connect(window._on_cells_changed)
        # The axis letter is a label beside the box, not the
        # spinbox's prefix.  A prefix is drawn *inside* the field, so
        # the box read "a 1" -- the letter sitting where the number
        # is, in the space the user clicks into to type one.
        bar.addWidget(_toolbar_label(f" {axis} "))
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
    bar.addWidget(_toolbar_label("  along "))
    for axis, name in zip("abc", ["view_a", "view_b", "view_c"],
                          strict=True):
        action = window.actions_[name]
        action.setIconText(axis)
        bar.addAction(action)
    # A box the toolbar holds is not where a keystroke is aimed unless
    # it was clicked: an editable field keeps its own Ctrl+Z, and the
    # element combo held the focus from startup and again after every
    # dialog closed -- so Ctrl+Z undid the letter C and never the
    # slab.  Clicked into, it still hands Undo and Redo to the window.
    window._undo_goes_to_the_window = _UndoGoesToTheWindow(window)
    window.element_table.setFocusPolicy(Qt.ClickFocus)
    for box in (window.element_combo, *window.cell_spins):
        box.setFocusPolicy(Qt.ClickFocus)
        field = box.lineEdit()
        field.setFocusPolicy(Qt.ClickFocus)
        # Both: a combo answers the override for its field itself.
        for widget in (box, field):
            widget.installEventFilter(window._undo_goes_to_the_window)
    window.addToolBar(bar)
    window.toolbar = bar


class _UndoGoesToTheWindow(QObject):
    """Refuse a text field's claim on Undo and Redo, so the window's
    actions get them.

    A line edit accepts the *ShortcutOverride* for the undo keys, which
    is Qt for "this key is mine, do not fire the shortcut".  Swallowing
    that one event leaves it unaccepted, and the window's Undo fires.
    For a field that holds an element symbol or a cell count, undoing
    the typing is worth nothing next to undoing the structure.
    """

    KEYS = (QKeySequence.Undo, QKeySequence.Redo)

    def eventFilter(self, watched, event):              # noqa: N802
        if (event.type() == QEvent.ShortcutOverride
                and any(event.matches(k) for k in self.KEYS)):
            return True
        return super().eventFilter(watched, event)

def popup(menu, position) -> None:
    """Raise a context menu and wait on it, in one place.

    A seam, because ``QMenu.exec`` cannot be replaced from Python --
    PySide resolves it in C++ and an override on the class is ignored,
    unlike ``QDialog.exec``, which the suite's modal guard does
    replace.  So a test that reached a context menu could not be
    stopped by that guard and hung instead: 27 minutes of a CI job at
    98 %, for a menu nobody could click.  ``tests/conftest.py``
    patches this function; a test that means to open one patches it
    itself.
    """
    menu.exec(position)


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
        elif name == window.GROUP_MENU:
            add_group_menu(window, menu)
        elif name == window.MEASURE_ENTRY:
            add_measure(window, menu, count, kind)
        elif name in window.COUNTED_ACTIONS and count > 1:
            add_counted(window, menu, name, count, noun)
        else:
            menu.addAction(window.actions_[name])
    if kind == "view":
        style = submenu(menu, "&Style")
        window.actions_.fill_menu(
            style, [f"style_{n}" for n in styles.names()])
    return menu

def add_group_menu(window, menu):
    """Replace with group: one entry per group in the library.

    Enabled only when every selected atom is a hydrogen (or a halogen:
    :data:`~xtal.build.substitute.TERMINAL`) and RDKit is
    there to embed the group -- a submenu that opened on a carbon
    would offer an edit that could only refuse.  Fresh actions rather
    than registry ones, because the list is the library's and grows
    with it; what they call is the registry's own
    ``substitute_rings`` rule for everything else.
    """
    from xtal.build import installed as rdkit_installed
    from xtal.build import substitute

    entry = submenu(menu, "Replace with &group")
    document = window.current_document()
    atoms = sorted(document.selection.atoms) if document else []
    hydrogens = bool(atoms) and all(
        document.cell.elements[a] in substitute.TERMINAL for a in atoms)
    entry.setEnabled(hydrogens and rdkit_installed()
                     and window.actions_["substitute_rings"].isEnabled())
    for name in substitute.names():
        action = entry.addAction(name)
        action.triggered.connect(
            lambda _checked=False, n=name: window.replace_with_group(n))
    return entry


def add_boundary_menu(window, menu):
    """The three boundary answers, wherever they are wanted."""
    entry = submenu(menu, "Bonds at the &boundary")
    window.actions_.fill_menu(
        entry, [f"boundary_{n}" for n, _l, _t in BOUNDARY_ACTIONS])


def add_bond_type_menu(window, menu):
    """The Set Bond Type submenu, wherever it is wanted.

    The same five actions in both places, so the context menu and
    the menu bar are enabled by the same rule and show the same
    tick -- which is the whole reason the actions live in the
    registry rather than being built where they are shown.
    """
    entry = submenu(menu, "Set Bond &Type")
    entry.setEnabled(window.actions_["bond_type_single"].isEnabled())
    window.actions_.fill_menu(
        entry, [f"bond_type_{n.lower()}" for n, _ in BOND_TYPES])
    return entry

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
