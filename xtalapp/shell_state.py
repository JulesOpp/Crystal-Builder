"""What the shell's actions are allowed to do, decided in one place.

The enabled state of the selection's actions used to be written down
twice -- once in ``MainWindow._refresh_shell`` and again in
``_on_selection_changed`` -- and only the first remembered that a
trajectory being played makes the crystal read-only.  Whichever ran
last won, so clicking an atom during playback put Cut, Duplicate,
Delete and Change element back on, and pressing one reached
``Document.run``'s ``PlaybackActive`` backstop as an exception in the
log instead of a greyed entry.  Both handlers now apply the map this
module returns, so a new condition is added once or not at all.
"""

from __future__ import annotations

from xtal.build import MISSING as NO_RDKIT
from xtal.build import installed as rdkit_installed
from xtal.commands.bonds import BOND_TYPES
from xtal.core.structure import Change

# ``shell_state`` is this module, by the name the moved methods call it
# by: they were written in mainwindow.py as ``shell_state.apply(...)``
# and moved without a character of their bodies changing.
from xtalapp import menus, shell_state
from xtalapp.viewport.view_settings import BOUNDARIES

# Reading the selection: allowed during playback, because none of
# these changes the crystal.
READING = ("select_same", "expand_bonded", "expand_fragment",
           "expand_orbit", "copy")
# Editing with at least one atom held.
EDITING_ATOMS = ("change_element", "cut", "duplicate",
                 "mark_connection_points")
# A centroid needs a middle, and one atom has none.
EDITING_SEVERAL = ("add_centroid", "merge_atoms",
                   "mark_one_connection_point")

SELECTION_ACTIONS = (READING + EDITING_ATOMS + EDITING_SEVERAL
                     + ("delete_selection", "delete_bond"))


def selection_states(document) -> dict[str, bool]:
    """Every selection action's enabled state for ``document``.

    Complete by construction: each name in :data:`SELECTION_ACTIONS`
    has an answer, ``False`` when there is no document, so applying
    the map leaves nothing enabled from whatever ran before it.
    """
    if document is None:
        return dict.fromkeys(SELECTION_ACTIONS, False)
    editable = not document.is_playing
    selection = document.selection
    atoms = len(selection.atoms)
    states = dict.fromkeys(READING, atoms > 0)
    states.update(dict.fromkeys(EDITING_ATOMS, atoms > 0 and editable))
    states.update(dict.fromkeys(EDITING_SEVERAL, atoms > 1 and editable))
    # Delete acts on whichever of the three is held -- net edges,
    # then bonds, then sites -- so it is enabled by any of them.
    # With a bond selected and no atom it was once greyed out, and
    # the key did nothing.
    states["delete_selection"] = bool(selection) and editable
    states["delete_bond"] = bool(selection.bonds) and editable
    return states


def apply(actions, states: dict[str, bool]) -> None:
    """Set each action in ``states`` to its answer."""
    for value in (True, False):
        names = [name for name, on in states.items() if on is value]
        if names:
            actions.set_enabled(names, value)


class ShellRefresh:
    """The window's refresh and enabling methods, moved out of
    :mod:`xtalapp.mainwindow` unchanged.

    A mixin of :class:`~xtalapp.mainwindow.MainWindow` and nothing
    else: every method here reads the window's own attributes through
    ``self``, which is what let them move without a line of their
    bodies changing.  Refreshing is still split three ways and the
    split is the point -- ``_update_ui`` rebinds panels when the
    current document changes, ``_on_structure_changed`` refreshes what
    they show, ``_on_view_changed`` touches only the shell's own
    widgets.
    """

    def _refresh_module_availability(self) -> None:
        """Grey out what cannot run, with the reason as the tooltip.

        Connected to the Modules menu's ``aboutToShow``, so it stays a
        bound method of this window: that is what makes it a queued
        connection to the right thread and what keeps the menu from
        holding the slot alive by itself.
        """
        menus.refresh_module_availability(self)

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
        # A document playing a trajectory back is showing somebody
        # else's geometry, so undoing into it would be undoing under a
        # picture that is about to be replaced by the next frame.
        editable = not document.is_playing
        undo.setEnabled(document.can_undo and editable)
        redo.setEnabled(document.can_redo and editable)
        undo.setText(f"&Undo {document.undo_label}".rstrip())
        redo.setText(f"&Redo {document.redo_label}".rstrip())

    def _on_selection_changed(self) -> None:
        document = self.current_document()
        if document is None:
            return
        self.inspector_dock.refresh()
        self.sites_dock.sync_selection()
        self.move_dock.refresh()
        self.selection_label.setText(document.selection_summary())
        shell_state.apply(self.actions_,
                          shell_state.selection_states(document))
        self._sync_bond_type_actions(document)
        self._refresh_plane_actions()
        self.measure_dock.refresh_planes()

    def _sync_bond_type_actions(self, document) -> None:
        """Enable the bond types, and tick what the selection already
        is -- "" when the selected bonds are not all the same type, in
        which case none of them is ticked."""
        names = [f"bond_type_{n.lower()}" for n, _ in BOND_TYPES]
        selected = bool(document is not None
                        and not document.is_playing
                        and document.selection.bonds)
        self.actions_.set_enabled(names, selected)
        if hasattr(self, "bond_type_menu"):
            self.bond_type_menu.setEnabled(selected)
        current = document.selected_bond_type() if selected else ""
        for type_name, _order in BOND_TYPES:
            action = self.actions_[f"bond_type_{type_name.lower()}"]
            # Without this the group refuses to leave every entry
            # unticked, and a mixed selection would claim to be
            # whichever type happened to be ticked last.
            action.setChecked(type_name == current)

    def _refresh_plane_actions(self) -> None:
        """A plane needs three atoms, an angle needs two planes and a
        measurement needs two to four atoms -- or a bond -- so none of
        these entries is offered before there is anything to do."""
        document = self.current_document()
        self.actions_.set_enabled(
            ["define_plane"],
            document is not None and len(document.selection.atoms) >= 3)
        self.actions_.set_enabled(
            ["measure_selection"],
            document is not None
            and self._measurable(document.selection))
        self.actions_.set_enabled(
            ["plane_angle"],
            document is not None and len(document.planes) >= 2)
        self.actions_.set_enabled(
            ["clear_planes"],
            document is not None and bool(document.planes))
        self.actions_.set_enabled(
            ["clear_measurements"],
            document is not None and bool(document.measurements))

    @staticmethod
    def _measurable(selection) -> bool:
        """Whether this selection admits a measurement.

        The same rule :meth:`measure_selection` acts on, asked here so
        the entry is enabled exactly when pressing it would do
        something -- two to four atoms, or bonds with no atom in hand.
        """
        if selection.bonds and not selection.atoms:
            return True
        return len(selection.atoms) in menus.MEASURE_LABELS

    def _rebuild_element_menu(self, document) -> None:
        self.element_menu.clear()
        if document is None:
            return
        for symbol in sorted(document.structure.elements):
            self.element_menu.addAction(
                symbol,
                lambda checked=False, s=symbol: self.select_element(s))

    def _on_cells_changed(self, _value=None) -> None:
        """More cells, and then a camera that frames them.

        Growing 1x1x1 into 3x3x3 puts eight ninths of the picture
        outside the frame, and the frame is where it is because it
        was set for one cell -- so the user's next action was always
        Reset view.  :meth:`descend_to_subgroup` resets for the same
        reason and its docstring carries the argument.

        **The rule lives here rather than on ``Document.set_cells``**,
        deliberately.  A camera belongs to a viewport and a document
        does not have one; ``set_cells`` is also called with no user
        present -- restoring a workspace, and by the tests -- where a
        reset would fight a view that has just been restored.  The
        second route to the same ranges, ``DisplayRangeDialog``, does
        not travel through ``set_cells`` either (it goes through
        ``update_view``), so putting it there would not have covered
        it; and it should not be covered.  That dialog composes a
        picture -- a half cell to look inside a framework, a slab
        one cell thick -- with the camera already placed on the
        thing being looked at, and resetting would throw that away.
        """
        document = self.current_document()
        if document is None:
            return
        document.set_cells(*[s.value() for s in self.cell_spins])
        self.reset_view()

    def _on_tab_changed(self, _index: int) -> None:
        # Fired for the first tab arriving and the last one going, so
        # it is also where the start pane comes and goes.
        self.central.setCurrentWidget(
            self.tabs if self.tabs.count() else self.start_pane)
        self._update_ui()
        self.workspace_shell.save_session()
        self.workspace_shell.show_open_document()

    def _on_title_changed(self, document, title: str) -> None:
        if document in self.documents:
            self.tabs.setTabText(self.documents.index(document), title)
        # A title changes with the file -- a first save, an adoption
        # -- and the tree marks the file.
        if document is self.current_document():
            self.workspace_shell.show_open_document()

    def _on_structure_changed(self, change: int = 0) -> None:
        """The crystal changed: the panels that show it must catch up.

        Only the ones the change actually reached.  The formula, the
        density, the space group, the elements present and the force
        field's typing are all decided by *what* the atoms are, not by
        where they are -- so a geometry change refreshes the panels
        that show coordinates and leaves the rest alone.  Refreshing
        all of them on every drag of one atom is where a large
        structure loses its responsiveness.

        Previews do not arrive here at all; they travel on the
        document's ``previewChanged`` and reach the viewport only.
        """
        document = self.current_document()
        if document is None:
            return
        positions_only = bool(change) and not (
            change & ~int(Change.POSITIONS))

        # These show coordinates, so a move is news to them.
        self.inspector_dock.refresh()
        self.sites_dock.refresh(positions_only)
        self.move_dock.refresh()

        # The net panel is the one expensive refresh here, so it is
        # given the flag and left to decide: identification walks ten
        # shells of an infinite graph, and a change that did not touch
        # a bond cannot have changed the answer.
        self.net_dock.on_structure_changed(change)

        if not positions_only:
            self.info_dock.show_document(document)
            self.style_dock.refresh()
            self.ff_dock.refresh()
            self.dftb_dock.refresh()
            self._rebuild_element_menu(document)
        # The shell, not _update_ui: that one *rebinds* every panel to
        # the document, which is for when the current document changes
        # and which would undo every skip above.
        self._refresh_shell()

    def _on_view_changed(self) -> None:
        """How it is drawn changed: the shell's own widgets and the
        style panel, which is the thing that shows view state."""
        self.style_dock.refresh()
        self._refresh_shell()

    def _on_measurements_changed(self) -> None:
        self.measure_dock.refresh()
        self._refresh_plane_actions()

    def _on_planes_changed(self) -> None:
        self.measure_dock.refresh_planes()
        self._refresh_plane_actions()

    def _update_ui(self, *_args) -> None:
        document = self.current_document()
        self.info_dock.show_document(document)
        self.net_dock.set_document(document)
        self.inspector_dock.set_document(document)
        self.sites_dock.set_document(document)
        self.move_dock.set_document(document)
        self.style_dock.set_document(document)
        self.measure_dock.set_document(document)
        self.ff_dock.set_document(document)
        self.dftb_dock.set_document(document)
        self.trajectory_dock.set_document(document)
        self._rebuild_element_menu(document)
        self._refresh_shell()

    def _refresh_insert_molecule(self, editable: bool) -> None:
        """Insert molecule, and the reason when it is off.

        Greyed with the sentence rather than absent.  RDKit is an
        optional extra, and an entry that is simply not there leaves
        somebody looking for a feature they have read about with
        nothing to find; one that is greyed and says ``pip install
        'crystal-builder[build]'`` in its tooltip tells them what to
        do.  The Modules tree greys its own entry from
        :func:`xtal.modules.build.available` and says the same thing.

        ``installed`` is ``find_spec``, which is why this can be
        called from every shell refresh.
        """
        action = self.actions_.get("insert_molecule")
        if action is None:                          # pragma: no cover
            return
        has_rdkit = rdkit_installed()
        action.setEnabled(editable and has_rdkit)
        tip = NO_RDKIT if not has_rdkit else menus.INSERT_MOLECULE_TIP
        action.setToolTip(tip)
        action.setStatusTip(tip)

    def _refresh_shell(self) -> None:
        """Menus, toolbar and status bar for the current document."""
        document = self.current_document()
        has_document = document is not None
        self.actions_.set_enabled(
            ["save", "save_as", "export", "export_image",
             "clear_overlays",
             "close_tab", "close_all_tabs", "reset_view", "view_a",
             "view_b", "view_c"],
            has_document)
        self._update_history_actions()
        self.actions_.set_enabled(
            ["select_all", "select_none", "invert_selection",
             "display_range", "bond_rules"],
            has_document)
        # Everything that changes the crystal is off while a
        # trajectory is being played: the atoms are showing a frame,
        # and an edit made against them would be wiped by the next one
        # without ever saying so.  ``Document.run`` refuses as well --
        # this is what stops the user reaching it.
        editable = has_document and not document.is_playing
        self.actions_.set_enabled(
            ["reduce_p1", "paste", "add_atom_dialog", "add_hydrogens",
             "fill_pores", "interpenetrate", "prepare_simulation",
             "find_symmetry", "set_space_group", "standardize",
             "primitive", "wyckoff", "merge_duplicates", "subgroup",
             "invert", "supercell",
             "edit_cell", "niggli", "delaunay", "wrap_cell",
             "save_building_block",
             "single_point", "optimize", "dftb_single_point",
             "dftb_optimize", "recompute_bonds", "reset_bonds"],
            editable)
        # Reading a net is not editing one, so a trajectory playing
        # does not take this away.
        self.actions_.set_enabled(
            ["export_net"], has_document and document.has_net())
        shell_state.apply(self.actions_,
                          shell_state.selection_states(document))
        if document is None:
            self._refresh_module_actions(False)
            self._refresh_insert_molecule(False)
            self._sync_bond_type_actions(None)
            self._refresh_plane_actions()
            self.status_label.setText("No structure open")
            self.selection_label.setText("")
            self.refresh_title()
            return
        self.selection_label.setText(document.selection_summary())
        self._refresh_module_actions(editable)
        self._refresh_insert_molecule(editable)
        self._sync_bond_type_actions(document)
        self._refresh_plane_actions()
        self.status_label.setText(document.status_text())
        self.refresh_title()
        name = f"style_{document.view.style}"
        if name in self.actions_:
            self.actions_[name].setChecked(True)
        for action, value in (("show_atoms", document.view.show_atoms),
                              ("show_bonds", document.view.show_bonds),
                              ("show_bond_orders",
                               document.view.show_bond_orders),
                              ("show_cell", document.view.show_cell),
                              ("show_axes", document.view.show_axes),
                              ("show_legend",
                               document.view.show_legend),
                              ("show_topology",
                               document.view.show_topology),
                              ("show_planes",
                               document.view.show_planes),
                              ("show_pores",
                               document.view.show_pores),
                              ("show_scale_bar",
                               document.view.show_scale_bar),
                              ("depth_cue", document.view.depth_cue)):
            widget = self.actions_[action]
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        # Set on each of the three and not just on the current one,
        # and without blocking signals: an exclusive QActionGroup
        # unticks the others *through* the signal it was blocked from
        # seeing, so blocking here left all three ticked at once.  The
        # slots hang off ``triggered``, which ``setChecked`` does not
        # emit -- see ``_sync_bond_type_actions``, which is the same
        # move for the same reason.
        for name in BOUNDARIES:
            action = self.actions_.get(f"boundary_{name}")
            if action is not None:
                action.setChecked(name == document.view.boundary)
        viewport = self.current_viewport()
        mode = getattr(viewport, "mode", None)
        if mode is not None and f"mode_{mode.name}" in self.actions_:
            self.actions_[f"mode_{mode.name}"].setChecked(True)
        for spin, value in zip(self.cell_spins, document.view.cells,
                               strict=True):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _refresh_module_actions(self, editable: bool) -> None:
        """Which module entries can be picked right now.

        Two reasons one cannot: there is nothing for it to run against
        -- no structure, or a trajectory being played, whose atoms are
        showing a frame -- or a module run is already going, because
        two at once would want two run folders and a Stop button that
        asks which.
        """
        idle = self.module_worker is None
        for name, needs_structure, action in self._module_actions:
            available = action.availability()
            self.actions_.set_enabled(
                [name], idle and bool(available)
                and (editable or not needs_structure))
            if not available:
                self.actions_[name].setToolTip(available.reason)
            elif action.tip:
                self.actions_[name].setToolTip(action.tip)
        self.actions_.set_enabled(["export_stl"], idle and editable)
