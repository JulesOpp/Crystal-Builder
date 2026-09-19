# Do the product invariants have functional tests?

Of the ~33 bolded invariants in `CLAUDE.md`, **26 are pinned by tests that
would fail if the invariant regressed the way CLAUDE.md describes**, and
most of those are functional (a real structure through a real door), not
`assert CONSTANT == 0.05`. This is an unusually well-tested codebase and
the sentence-named tests make the mapping easy to audit.

Five things are not pinned. Ranked by the damage CLAUDE.md records:
the **QSettings scratch-directory guard** (278 then 374 plists escaped
because it silently did nothing, and nothing tests it now either); the
**metric-normalised strain subspace** (I removed the √2 and 51 tests still
passed); the **PySide6 <6.10 cap and `--selftest`**, the pair that is
explicitly the only defence against an application that cannot draw;
the **unsaved question on a workspace switch**; and
`test_the_transcribed_radii_still_match_the_vendored_source`, which
**skips in every clean checkout and in CI**.

All 1000-odd tests I identified and ran pass. One skips.

---

## Method

Grepped `tests/` for every identifier CLAUDE.md names and for the behaviour
in test names, read each candidate, then — where the judgement was not
obvious from reading — **reintroduced the regression** as a pytest plugin
and recorded which tests noticed. Probes are in `review/probes/`
(`old_tol.py`, `tight_proj.py`, `flat_metric.py`); none touches a tracked
file and `git status` is clean.

Runs: `.venv/bin/python -m pytest -q -o faulthandler_timeout=90 <files>`,
serial, in batches. Totals: 60 + 139 + 145 + 137 + 111 + 189 + 119 + 211 +
148 passed, **1 skipped**, no failures, no hangs.
`sysctl vm.swapusage` was 9470M/10240M used throughout, so timings below
are indicative only.

---

## The table

kind = what the test is: **functional** (user-visible behaviour, usually a
real file), **unit** (the mechanism), **none**.

| # | Invariant | Test(s) `file::name` | Kind | Verdict | Note |
|---|---|---|---|---|---|
| 1 | Bonds recalculated only on Recalculate | `test_commands.py::test_deleting_an_atom_does_not_reperceive_the_rest_of_the_cell`; `test_add_atom.py::test_a_placed_atom_arrives_bonded_to_nothing`, `::test_the_bond_comes_with_the_atom`, `::test_a_centroid_does_not_perceive_either`, `::test_undoing_an_add_does_not_perceive_again`, `::test_add_hydrogens_still_bonds_what_it_adds`; `test_move_mode.py::test_a_drag_changes_no_bonding_at_all`; `test_stored_bonds.py::test_a_new_lattice_keeps_the_graph`; `test_clipboard.py::test_a_paste_lands_with_its_own_bonds_and_no_perceived_ones`; `test_symmetry.py::test_reduce_to_p1_does_not_perceive_again`; `test_reset_bonds.py::test_recalculating_keeps_a_suppression` | functional | **pinned** | Every door CLAUDE.md names except one — see #5. `hold_perception` appears **nowhere** in `tests/` (grep: 0 hits); the behaviour is pinned, the seam is not named. |
| 2 | `SPECIAL_POSITION_TOL = 0.05 Å` | `test_p1.py::test_a_site_nudged_off_a_special_position_keeps_its_multiplicity`, `::test_reduce_to_p1_adds_no_atoms_that_were_not_in_the_cell`; `test_merge_duplicates.py::test_the_cell_is_three_copies_of_itself`, `::test_merging_is_what_makes_the_formula_right`, `::test_the_count_steps_and_then_goes_flat`, `::test_the_preview_and_the_merge_agree` | functional | **pinned** | Proved, not assumed: with the tolerance put back to 1e-3 these six fail and nothing else does. `Ni2Cl2BTDD.cif` is the deposited file, and the test asserts the published formula. **`CFA1.cif` is not a test** — see Finding 6. |
| 3 | `SymmetryDOF._projectors` at the same tolerance | `test_optimize.py::test_a_site_written_a_rounding_place_off_its_axis_keeps_the_axis` (unit, MFU-4l Cl1); `test_scan.py::test_a_held_chloride_distance_keeps_mfu4l_in_its_group` (functional) | both | **pinned** | Probe at 1e-6: exactly these two fail, the functional one with the real message ("648 atoms to 712"). Model of how to pin a numeric decision. |
| 4 | A dummy atom is held back at the door, in three places | `test_centroid.py::test_the_marker_feels_no_force_and_exerts_none`, `::test_a_module_is_never_handed_a_dummy_atom`, `::test_the_markers_come_back_with_their_bonds`, `::test_the_runner_holds_the_dummies_back`, `::test_an_optimisation_leaves_the_marker_where_it_was`; `test_hydrogens.py::test_a_dummy_atom_does_not_stop_the_hydrogens_going_back`, `::test_the_marker_is_still_there_afterwards`; `test_mace.py::test_the_registry_builds_it_with_markers_held_back` | functional | **pinned** | All three doors (`markers.hold_back`, `hydrogens.plan`, `job.without_dummies`) plus "held back, not refused" and "not deleted". `hold_back` itself is never named in tests. |
| 5 | A force field or optimiser never changes the bonding or the atoms | atoms: `test_optimize.py::test_the_cell_keeps_the_same_number_of_atoms`, `::test_rutile_keeps_its_space_group`. Bonding: only indirectly, via `test_change_hints.py::test_a_move_keeps_the_chemistry_and_drops_the_geometry` | unit | **weak** | No test asserts that `structure.bonds` is unchanged across a relaxation. `ApplyRelaxation` reaches the structure through `MoveSites`, so it is one refactor away from the promise. |
| 6 | Manually set bond types take precedence | `test_bond_orders.py::test_a_stated_order_beats_the_inference`, `::test_a_bond_stated_single_stays_single`, `::test_a_stated_order_survives_a_round_trip` | functional | **pinned** | |
| 7 | A drag moves the copy the cursor has hold of | `test_move_mode.py::test_the_copy_under_the_cursor_is_the_one_that_follows_it` (rutile, P4₂/mnm, asserts the drawn atom moved by exactly the cursor travel **and** `op_idx != 0`); `::test_the_copies_under_the_cursor_turn_with_it_too`; `test_p1.py::test_parent_coordinates_inverts_the_image` | functional | **pinned** | The one test that matters here does pick a non-P1 group. `by_image_delta` is never named in tests; `by_image_rotation` once. See Finding 9 for the half that is only a docstring. |
| 8 | Alt claims a Move drag; shift is read inside it | `test_move_mode.py::test_what_the_modifiers_mean_to_a_drag` (the full truth table incl. `Alt|Shift → depth`), `::test_alt_drag_turns_the_selection_like_a_trackball` (one radius = one radian, asserted numerically), `::test_shift_alt_drag_moves_along_the_view_axis`, `::test_shift_drag_adds_the_atom_to_what_is_already_held` | functional | **pinned** | |
| 9 | A click inside a net edge is the net edge | `test_picking.py::test_a_click_down_the_axis_of_an_edge_means_the_edge`, `::test_a_click_out_at_the_rim_of_an_edge_takes_what_is_under_it`, `::test_an_atom_with_a_net_edge_on_it_is_still_an_atom`; `test_topology.py::test_selecting_a_net_edge_lights_that_one_up`, `::test_the_bond_under_an_edge_is_still_reachable` | functional | **pinned** | Both halves of the rule and the atom exception. The named case — *96 chemical bonds deleted on MOF-5* — is not a test; the fixtures are a diatomic and a synthetic framework. |
| 10 | Connection point is 0.75 Å | `test_block_writer.py::test_a_connection_point_is_written_at_0_75_angstrom`; `test_build_molecule.py::test_a_connection_point_lands_at_the_distance_pormake_uses`, `::test_pulling_a_connection_point_in_keeps_its_direction`; `test_connection_points.py::test_a_hydrogen_becomes_a_dummy_at_the_connection_distance` | functional | **pinned** | The "over the 867 blocks PORMAKE ships" derivation is not itself checked against the shipped blocks; 867 is asserted only as a count (`test_mof_builder.py`, `test_packaging.py`). |
| 11 | The workspace is asked for before anything opens | `test_workspace_chooser.py` (23 tests) incl. `::test_the_workspace_from_last_time_is_the_one_selected`, `::test_return_continues_rather_than_quitting`, `::test_a_file_inside_a_workspace_is_not_asked_about` (`Workspace.find`), `::test_main_opens_the_sample_the_chooser_returned`, `::test_quitting_from_the_chooser_opens_no_window` | functional | **pinned** | "Must not move into the constructor" is enforced structurally rather than by a test: `conftest.py`'s `_no_blocking_modal` patches `QDialog.exec` to raise, so the move would fail every widget test at once. |
| 12 | Every document has an entry, through all four doors | `test_open_once.py::test_the_workspaces_copy_is_the_document_that_made_it`, `::test_reopening_the_file_it_was_copied_from_finds_the_same_tab`, `::test_reopening_a_file_does_not_name_a_tab_spelled_the_same`; `test_samples.py::test_a_sample_is_copied_into_the_workspace`; `test_workspace_ui.py::test_a_new_document_gets_a_folder_of_its_own`; `test_mof_ui.py::test_a_build_lands_in_the_workspace_without_being_asked` (asserts the single CIF **and** `not list(entry.path.glob("*maker*"))` — the run's poorer copy dropped) | functional | **pinned** | `_paths_naming` and `place_in_workspace` are never named in tests; the behaviour above is what pins them. |
| 13 | `add_structure` de-duplicates by content, never by name | `test_workspace.py::test_two_different_files_of_the_same_name_get_two_entries` (reads both back and checks they are different crystals), `::test_the_same_bytes_under_a_taken_name_still_find_their_entry`, `::test_opening_the_same_file_twice_is_one_entry` | functional | **pinned** | `filecmp` never named in tests; content-vs-name is asserted by reading the files back. |
| 14 | Changing workspace closes every tab, after **one** question, new workspace opened first | `test_workspace_ui.py::test_switching_workspace_closes_the_tabs_of_the_old_one`, `::test_a_run_after_switching_is_filed_in_the_new_workspace`, `::test_a_workspace_that_will_not_open_costs_nobody_their_tabs` | functional | **weak** | The closing, the run-filing bug and the open-first ordering are all pinned. **The question is not.** `conftest.py:29` sets `XTAL_NO_CONFIRM_CLOSE=1` for the session, so `has_unsaved_work()` is always False and `may_discard_unsaved` returns True in every test. No test switches workspace with a modified document. See Finding 4. |
| 15 | A workspace remembers its own tabs; `_holding` | `test_workspace.py::test_a_workspace_remembers_what_was_open`, `::test_a_session_survives_the_workspace_being_moved`, `::test_a_path_outside_the_workspace_is_not_remembered`, `::test_a_marker_edited_into_nonsense_opens_empty`; `test_workspace_ui.py::test_reopening_a_workspace_reopens_its_tabs`, `::test_switching_back_brings_the_first_workspace_tabs_back`, `::test_a_remembered_tab_whose_file_has_gone_is_skipped` | functional | **pinned** | `_holding` is exercised by the switch-and-switch-back test: without it the closing half would record an empty session. |
| 16 | Save File converts and never asks; named after the **file** | `test_workspace_ui.py::test_save_file_converts_a_structure_to_the_project_beside_it`, `::test_saving_again_writes_the_same_file_without_asking`, `::test_a_numbered_entry_saves_beside_its_own_file` (the MFU4l/MFU4l-2 case exactly), `::test_the_confirm_preference_asks_before_writing_over`, `::test_answering_no_leaves_the_file_as_it_was` | functional | **pinned** | "Never asks" is enforced by the autouse modal guard raising — a regression that reached a dialog fails rather than hangs. |
| 17 | The degraded window survives | `test_workspace_ui.py::test_a_workspace_that_cannot_be_made_still_opens_a_window`, `::test_a_structure_opened_with_no_workspace_says_so_and_makes_none`, `::test_a_document_with_no_workspace_still_runs`; `test_modules.py::test_a_job_with_no_workspace_runs_and_says_nothing_to_disk`; `test_mof_ui.py::test_a_build_with_no_workspace_still_opens_its_tab`; `test_mof_builder.py::test_a_run_outside_a_workspace_still_has_a_catalogue`; `test_dftb_bands.py::test_without_a_workspace_it_still_answers`; `test_pxrd.py::test_a_run_with_no_workspace_still_answers`; `test_workspace_chooser.py::test_a_folder_that_cannot_be_made_leaves_the_dialog_open` | functional | **pinned** | Nine tests across seven files, one per `workspace is None` branch. A strength. |
| 18 | Porosity draws where the pores are; the overlay is not an edit | `test_run_progress_ui.py::test_it_is_not_drawn_over_whichever_tab_is_in_front`, `::test_the_drawing_is_not_an_edit`, `::test_a_pore_network_survives_a_save_and_reopen`, `::test_replacing_the_crystal_drops_the_pores`, `::test_editing_the_crystal_drops_the_pores`; `test_porosity.py::test_the_widest_node_is_where_the_largest_sphere_sits` (2r = D_i = 18.742 against the real captured MFU-4l Voronoi file), `::test_the_channel_diameters_match_the_res_file` | functional | **pinned** | Every clause of a long invariant has its own test, including the hardest one (the run's own document, not the tab in front). `JobResult.overlay` never named in tests; the behaviour is. |
| 18b | …"and the report says so" about D_f | `test_porosity.py::test_every_diameter_carries_what_it_means` | unit | **weak** | Asserts only that label/symbol/meaning are non-empty. The sentence that carries the invariant (`xtal/modules/zeopp.py:604`, "the width of a bottleneck along a channel, and no …") is asserted nowhere. |
| 19 | The pore surface is ours; tetrahedra not cubes; not written into the project | `test_isosurface.py::test_the_mesh_is_watertight` ("a marching-cubes table with an ambiguous case wrong fails this and nothing else"), `::test_the_triangles_all_face_the_same_way`, `::test_a_surface_across_a_cell_face_is_whole`, `::test_a_finer_grid_converges_rather_than_wandering`, `::test_the_accessible_fraction_agrees_with_what_zeo_measures`; `test_run_progress_ui.py::test_the_surface_is_not_written_into_the_project` | functional | **pinned** | |
| 19b | `ZEO_RADII` transcribed from Zeo++'s `networkinfo.cc` | `test_porosity.py::test_the_transcribed_radii_still_match_the_vendored_source` | unit | **untested in practice** | **The one skip in my whole run.** It needs `resources/zeo++-0.3/networkinfo.cc`; `.gitignore:25` excludes that directory and `.github/workflows/ci.yml` has no mention of Zeo++ (`grep -in zeo` → nothing). It skips in every clean checkout and in CI. See Finding 5. |
| 20 | The CIF carries the bonds; Export cleans; a foreign `_geom_bond` is not bonding | `test_io.py::test_a_foreign_geom_bond_loop_is_not_read_as_the_bonding`, `::test_an_export_keeps_the_chemistry_and_drops_the_markup`, `::test_a_structure_with_nothing_to_clean_is_not_copied`; `test_mof_ui.py::test_the_net_drawn_over_a_build_survives_into_the_workspace`, `::test_what_a_build_leaves_is_a_marker_and_a_net_until_it_is_exported`; `test_pdb_writer.py::test_markers_and_net_edges_are_not_cut` | functional | **pinned** | |
| 20b | A scan point's CIF carries the perceived graph | `test_io.py::test_a_stored_perception_can_be_written_and_read_back`, `::test_a_perception_is_not_written_unless_asked_for`, `::test_a_read_perception_is_still_replaced_by_recalculating`, `::test_a_perception_that_does_not_fit_the_atoms_is_ignored`; `test_scan_module.py::test_a_stretched_point_opens_with_the_bonds_the_scan_held` | functional | **pinned** | All four clauses incl. the "only if every bond is still the length it was written at" reader rule. **Drift:** CLAUDE.md names *MFU-4l at +15% opening with 560 of its 848 bonds*; the test uses MIL-53 (126 bonds, 24 lost). Same behaviour, cheaper structure — CLAUDE.md's number is now folklore. |
| 21 | A drawn block goes to `<workspace>/blocks/` | `test_draw_block.py::test_a_block_is_drawn_into_the_workspace_and_read_back_from_it`, `::test_drawing_needs_no_folder_named_first`; `test_mof_builder.py::test_a_block_in_the_workspace_is_what_the_run_builds_with`; `test_build_ui.py::test_saving_a_block_writes_it_where_the_picker_will_find_it` | functional | **pinned** | Including the "no longer demands a folder be named" half. |
| 22 | Structure edits go through `Document.apply(...)` | — | none | **untested** | A convention, not a checkable property: `document.apply(...)` is *used* throughout `test_change_hints_ui.py`, but nothing fails if new code mutates a structure behind the Document's back. Enforceable only by review or a lint. Low severity — the surrounding change-hint tests catch most of the consequences. |
| 23 | A panel never holds its column open | `test_window_layout.py::test_no_panel_insists_on_more_room_than_a_column_can_spare` (sweeps **every** dock against `MAXIMUM_MINIMUM`), `::test_opening_every_panel_leaves_the_column_free_to_narrow`, `::test_tabbed_panels_scroll_their_tabs_rather_than_widen`, `::test_the_viewport_does_not_make_the_panels_native_windows`, `::test_many_open_tabs_do_not_widen_the_tab_bar_past_the_screen`; `test_scan_ui.py::test_a_panel_holding_a_landscape_leaves_the_column_free`; reflow: `test_appearance_ui.py::test_a_wide_style_panel_puts_its_groups_side_by_side`, `::test_a_narrow_style_panel_stacks_its_groups_instead_of_scrolling_sideways` | functional | **pinned** | The sweep is the right shape: a new dock with a `setMinimumWidth` fails without anybody remembering to add a test. |
| 24 | A long operation over a selection is one batch | `test_bond_orders.py::test_setting_every_bond_is_one_command_and_one_change` (MFU-4l, 848 bonds, asserts **one** `structureChanged`, one revision, one undo step), `::test_deleting_every_bond_is_one_command_too`, `::test_a_bulk_edit_is_one_record_per_pair_not_per_drawn_bond`, `::test_a_bulk_edit_undoes_in_one_step` | functional | **pinned** | The exact named case (Select All → Set Bond Type on MFU-4l), asserted on the mechanism that caused the stall rather than on a timing. Best test in the repo. |
| 25 | A scan holds a coordinate; it does not freeze the atoms | `test_scan_constraints.py::test_holding_a_distance_leaves_more_atoms_free_than_freezing_them`, `::test_a_held_coordinate_does_not_drift_over_the_whole_run`, `::test_the_residual_force_ignores_the_direction_being_held`, `::test_a_site_on_a_special_position_stays_on_it_while_held`, `::test_a_frozen_site_stays_frozen_while_a_coordinate_is_held`, `::test_a_coordinate_the_space_group_forbids_is_refused` | functional | **pinned** | The projector-ordering clause ("a constraint can only ever take freedom away") has its own two tests. |
| 26 | A held cell quantity is a strain subspace, in a **metric-normalised** coordinate | `test_cell_freedom.py` (13 tests) — `::test_a_mask_is_a_projector`, `::test_a_tied_parameter_is_held_with_the_one_it_follows`, `::test_the_angles_of_a_trigonal_cell_are_left_alone`, `::test_a_cubic_cell_may_still_be_held_at_constant_volume`, `::test_the_residual_stress_ignores_a_strain_the_mask_forbids` | functional | **weak** | The *subspace* behaviour is pinned. The **metric normalisation is not**: with the √2 shear scaling removed (`review/probes/flat_metric.py`) all 51 tests in `test_cell_freedom.py` + `test_scan.py` still pass. See Finding 2. |
| 27 | A scan point is written the moment it finishes | `test_scan_module.py::test_a_point_is_on_disk_before_the_next_one_starts`, `::test_a_stopped_scan_leaves_the_points_it_finished`, `::test_a_scan_writes_one_cif_for_every_finished_point`; `test_scan.py::test_stopping_a_scan_keeps_the_points_already_finished` | functional | **pinned** | |
| 27b | …in **one** job on **one** thread, never one per point | — | none | **untested** | Nothing asserts the scan does not spawn a worker per point. Given it is justified by the unfixed `workers.py` teardown race, a refactor that parallelised the grid would pass the whole suite and make an overnight scan a coin toss. |
| 28 | An unconverged scan point is not a number | `test_scan.py::test_a_point_that_did_not_finish_is_not_a_number`, `::test_a_failed_point_does_not_seed_the_next_one`, `::test_both_directions_give_two_branches`, `::test_the_way_back_starts_where_the_way_out_finished`; `test_scan_ui.py::test_the_colour_scale_ignores_the_points_that_did_not_finish`; `test_report_surface.py::test_an_unfinished_point_is_not_a_number`, `::test_the_text_shows_a_hole_as_a_hole`, `::test_the_text_marks_a_point_that_did_not_converge`; `test_scan_module.py::test_unconverged_points_are_counted_in_the_message`; `test_scan_module.py::test_the_first_sheet_is_no_higher_than_either_branch` (drawn apart, not averaged) | functional | **pinned** | Every rendering layer CLAUDE.md lists (heat map, scale, contour, log) has its own test. |
| 29 | A scan refuses what it cannot hold, before the first point | `test_scan_module.py::test_a_distance_the_group_holds_is_refused_before_any_point`; `test_scan.py::test_a_coordinate_the_group_holds_is_refused_by_the_plan`, `::test_a_parameter_the_group_does_not_leave_free_is_refused`, `::test_a_point_that_leaves_the_group_is_a_hole_with_a_reason`, `::test_a_held_chloride_distance_keeps_mfu4l_in_its_group` | functional | **pinned** | "A different atom count is a hole with the reason beside it, never a number for another crystal" is asserted with the message text. |
| 30 | Axis syntax `distance 32, 33`, `+` in a centroid, old grammar still parses | `test_scan_module.py::test_a_comma_separates_two_atoms`, `::test_a_group_of_atoms_is_written_with_pluses`, `::test_an_axis_written_in_the_first_grammar_still_reads`, `::test_the_spelling_of_anchors_reads_back_as_them`, `::test_the_grammar_is_the_same_everywhere`, `::test_a_coordinate_nobody_can_read_is_refused_by_name` | unit | **pinned** | |
| 31 | A scan leaves `report.json` and double-clicking re-opens the landscape | `test_scan_module.py::test_a_scan_leaves_a_report_that_opens_again`; `test_report_surface.py::test_a_report_finds_its_surfaces`, `::test_the_export_carries_the_file_behind_each_cell` | functional | **pinned** | |
| 32 | The atom types table is one widget; an override is one `Document.set_atom_type` | `test_scan_dialog.py::test_a_type_overridden_in_the_dialog_is_the_documents` (overrides in the dialog, asserts `window.ff_dock.table` shows it, then `document.undo()` and asserts both revert), `::test_the_dialog_shows_the_atom_types_the_scan_will_run`, `::test_an_engine_without_atom_types_shows_no_table`, `::test_the_types_follow_the_parameter_set_chosen_here` | functional | **pinned** | Both directions and the undo. |
| 33 | A scan reads the engine; it does not configure one; it returns no structure | `test_scan_dialog.py::test_the_engine_comes_from_the_force_field_panel`; `test_scan_module.py::test_a_scan_does_not_replace_the_structure_it_ran_on`, `::test_the_engine_is_built_with_the_options_it_was_given` | functional | **pinned** | |
| P1 | `pyproject.toml`: PySide6 capped `<6.10`, and the cap is load-bearing | — | none | **untested** | No test reads the `gui` extra. `grep -rn "6.10\|PySide6<" tests/` → 0 hits. See Finding 3. |
| P2 | `--selftest` is the only thing that catches a PySide6 that hangs the window | `test_probe.py::test_a_frozen_build_imports_one_package_and_names_its_version` covers `selftest.import_one` only | none | **untested** | `selftest.run` — the function that opens a sample and writes a PNG of the 3D view, i.e. the whole point of the flag — has **no test**. `grep -rn "selftest.run" tests/` → 0 hits. See Finding 3. |
| G1 | Guard: `XTAL_NO_CONFIRM_CLOSE=1` for the session | `test_no_confirm_close.py` (6 tests) tests the *variable's* effect; `test_quit.py`, `test_app_shell.py:510` opt out correctly | functional | **partly pinned** | The variable's semantics are pinned. That `conftest.py:29` sets it is not — but removing the line makes the suite hang, which is self-announcing. |
| G2 | Guard: `QDialog.exec` / `QMessageBox` statics raise | — (used by ~everything; `test_workspace_ui.py::test_saving_again_writes_the_same_file_without_asking` relies on it explicitly) | none | **untested** | Nothing asserts the guard is installed. Removing it turns "reached a modal" from a failure into a hang — the exact failure mode CLAUDE.md is trying to prevent. Low-ish: it would show up quickly. |
| G3 | Guard: settings go to a scratch directory, never the real ones | — | none | **untested** | **The worst gap in the file.** See Finding 1. |
| G4 | Guard: a test's windows are deleted when it ends | — | none | **untested** | Nothing asserts `DeferredDelete` is delivered. Removing `pytest_runtest_teardown` reproduces 74 live `MainWindow`s silently — a slow suite and eventual `Fatal Python error: Aborted`, neither of which names the cause. See Finding 7. |

---

## Findings, worst first

### 1. `[critical]` The QSettings scratch-directory guard has no test, and CLAUDE.md records it silently failing for its entire life

**What.** `tests/conftest.py:62–107` points QSettings at a temp directory so a
window test does not leave a plist in `~/Library/Preferences`. Its own
docstring says the guard *had already silently done nothing for as long as
it has existed* — `setDefaultFormat` is ignored by the macOS
organisation/application constructors — and that **374 plists were sitting
in `~/Library/Preferences` when a test finally read one back from a
previous run and failed on it**, after an earlier count of 278.

**Where.** `tests/conftest.py:62`; `xtalapp/settings.py:27,138–150`.

**Evidence.**
```
$ grep -rn "XTAL_SETTINGS_DIR\|IniFormat\|NativeFormat\|fileName()" tests/*.py
tests/conftest.py:87:    back a NativeFormat object anyway, so this guard silently did
tests/conftest.py:99:    os.environ.setdefault("XTAL_SETTINGS_DIR", scratch)
tests/conftest.py:104:    QSettings.setDefaultFormat(QSettings.IniFormat)
```
Nothing outside `conftest.py` mentions any of it. `test_preferences.py`
(33 tests) exercises what preferences *do*, never where they land.

**Why it matters.** This is the only invariant in the repo with a recorded
history of failing open. The failure is invisible by construction: the
suite passes, and the damage is in somebody's home directory. The same
class of regression — a second `AppSettings` constructed without the
format, a Qt version that changes the default — would land the same way
again today.

**A fix.** One test, in `test_preferences.py`:
`test_a_windows_settings_never_reach_the_real_preferences` — build an
`AppSettings` the way a window fixture does and assert
`settings._q.format() == QSettings.IniFormat` **and** that
`Path(settings._q.fileName())` is under `os.environ["XTAL_SETTINGS_DIR"]`.
The second half is the one that matters: the format alone is what looked
right for years.

---

### 2. `[important]` The metric normalisation of `CellFreedom` is untested — I removed it and 51 tests passed

**What.** `xtal/ff/optimize.py:170–189` scales the shears by √2 so that the
space group's average is an *orthogonal* projector, because "intersecting
subspaces with a skew metric silently gives the wrong subspace". That
sentence is the whole justification for the invariant, and nothing tests it.

**Where.** `xtal/ff/optimize.py:177–189` (`_w_of` / `_tensor_of`);
`tests/test_cell_freedom.py`.

**Evidence.** `review/probes/flat_metric.py` replaces `_w_of`/`_tensor_of`
with unscaled versions at `pytest_configure`:
```
$ PYTHONPATH=…/scratchpad .venv/bin/python -m pytest -q -p flat_metric \
      tests/test_cell_freedom.py tests/test_scan.py
51 passed in 15.45s
```
Compare the SPECIAL_POSITION_TOL probe, which fails six tests, and the
projector probe, which fails two.

**Why it matters.** The reason is structural: every fixture here is quartz
(trigonal) or halite (cubic), and neither group's allowed-strain subspace
has an independent shear component, so the normalisation never bites. The
invariant is about *monoclinic and triclinic* cells, and no test holds a
cell quantity on one.

**A fix.** `test_holding_the_volume_of_a_monoclinic_cell_leaves_its_shear_free`
— take a real P2₁/c structure, build
`SymmetryDOF(s, relax_cell=True, freedom=CellFreedom.constant_volume())`,
and assert `project_strain` is idempotent *and* that the projected strain
of an arbitrary symmetric tensor still has the β-shear component the group
allows. Without the √2 that component leaks or is wrongly zeroed.

---

### 3. `[important]` The PySide6 `<6.10` cap and `--selftest` — the invariant and its only enforcement — are both untested

**What.** `pyproject.toml:45–66` records, at length, that PySide6 ≥6.10
makes VTK's `QVTKRenderWindowInteractor.paintEvent` repaint forever, that
**the suite cannot catch it** (widget tests inject a stub viewport), and
that `crystal-builder --selftest` is what catches it instead. Neither half
has a test.

**Where.** `pyproject.toml:66` (`gui = ["PySide6>=6.6,<6.10", …]`);
`xtalapp/selftest.py`; `xtalapp/main.py:46`.

**Evidence.**
```
$ grep -rn "6.10\|PySide6<\|pyside6" tests/*.py     # → nothing
$ grep -rn "selftest.run\|SELFTEST\b" tests/        # → nothing
```
The only selftest coverage is `test_probe.py:177–183`, which calls
`selftest.import_one("json", …)` — the one-package cousin, not the flag
that opens a window.

**Why it matters.** `test_packaging.py` is otherwise meticulous about the
build (it checks icons, globs, reserved Windows names, the macOS floor).
The cap is the one packaging decision in the file whose removal ships an
application that cannot draw, and it is the one nothing guards. A
dependency bump — Dependabot, a `pip install -U`, a contributor widening
the range "because 6.10 is out" — is silent.

**A fix.** Two tests in `test_packaging.py`:
`test_the_pyside_cap_is_still_in_place` — parse `pyproject.toml` and assert
the `gui` extra's PySide6 specifier still excludes `6.10.0` (one assertion:
`Specifier` contains `<6.10`), with the reason in the docstring; and
`test_the_selftest_flag_draws_the_viewport_it_promises_to` — run
`crystal-builder --selftest --selftest-image OUT.png` in a subprocess
(as `test_mace.py` does for its heavy stack) and assert exit 0 and that
`OUT.png` is a non-blank image. The second is what actually defends the
cap; without it, raising the bound in CI still goes green.

---

### 4. `[important]` The unsaved question on a workspace switch is never asked in any test

**What.** `switch_workspace` calls
`may_discard_unsaved("… Leave this workspace anyway?")` and returns `None`
if the answer is no. Neither the question nor the cancellation is tested.

**Where.** `xtalapp/workspace_shell.py:150–154`;
`xtalapp/mainwindow.py:1757`; `tests/test_workspace_ui.py:269–320`.

**Evidence.** `conftest.py:29` sets `XTAL_NO_CONFIRM_CLOSE=1` for the whole
session, and `has_unsaved_work()` returns
`not no_confirm_close() and any(...)` — always `False` in the suite. Of
the ten `switch_workspace` call sites in tests, none deletes the variable
and none has a modified document:
```
$ grep -rn "switch_workspace" tests/*.py | wc -l
10
$ grep -rn "delenv..XTAL_NO_CONFIRM_CLOSE" tests/*.py
tests/test_app_shell.py:510
```
— and that one is about closing a tab, not switching workspace. Contrast
`test_quit.py`, which does the opt-out properly for the quit path and has
ten tests including `test_the_same_question_is_not_asked_twice`.

**Why it matters.** The quit path got the full treatment because losing
unsaved work there had been reported. The switch path throws away exactly
the same work through a second door, with a different wording, and the
"answering no cancels the switch" branch has never executed in a test.

**A fix.** `test_leaving_a_workspace_with_unsaved_work_asks_before_it_closes`
— `monkeypatch.delenv("XTAL_NO_CONFIRM_CLOSE")`, patch
`QMessageBox.question` to return `No`, modify a document, call
`switch_workspace`. One assertion: `window.tabs.count() == 1` and
`window.workspace.root` is unchanged — the tabs survive a refusal.

---

### 5. `[important]` The `ZEO_RADII` transcription test can never fail

**What.** CLAUDE.md says "a test checks the transcription against the
vendored source". It does, and it skips everywhere.

**Where.** `tests/test_porosity.py:336–358`; `.gitignore:25`;
`.github/workflows/ci.yml`.

**Evidence.**
```
$ .venv/bin/python -m pytest -q -rs tests/test_porosity.py tests/test_isosurface.py
SKIPPED [1] tests/test_porosity.py:349: the vendored Zeo++ source is not in this checkout
51 passed, 1 skipped in 1.56s

$ sed -n '22,26p' .gitignore
resources/zeo++-0.3/
$ grep -in zeo .github/workflows/ci.yml     # → nothing
```
It is the only skip in the ~1250 tests I ran.

**Why it matters.** The table is 100-odd hand-typed numbers, and the
invariant is that the *picture* of a run is drawn with the radii its
*numbers* were computed with. The test is well written; it is simply
unreachable, and CLAUDE.md reads as though it runs.

**A fix.** Cheapest: commit the extracted `{symbol: radius}` dict as a
small JSON fixture under `tests/data/` (the same pattern as
`pormake_upstream.json`, and the same argument — a recording instead of
the upstream tree) and compare against that always, keeping the live
source comparison as the extra check when the tree is present. One
assertion unchanged: `porosity.ZEO_RADII == theirs`.

---

### 6. `[minor]` `CFA1.cif` — the first structure CLAUDE.md names — is not a test

**What.** The tolerance invariant names three concrete casualties.
`Ni2Cl2BTDD.cif` has a whole test file. MFU-4l's Cl1 has two tests.
`CFA1.cif` — "three Zn 0.0018 Å apart on the 3-fold axis" — has none.

**Evidence.** `grep -rn CFA1 tests/` finds one hit, in
`test_vtk_render.py:526`, about an unrelated PLATON rendering line. The
regression is live and reproducible:
```
CFA1 atoms at 1e-3: 258
CFA1 atoms at 0.05: 242
```
(16 extra atoms, i.e. the Zn orbit generated against itself.)

**Why it matters.** Mild — the tolerance is already pinned six ways over,
and the BTDD file is the better test because it checks the *published
formula*. But CFA1 is the cheapest possible regression test (read the
file, count) and it is the case the documentation leads with.

**A fix.** `test_reduce_to_p1_does_not_grow_the_atom_count_on_cfa1` in
`test_p1.py` — one assertion: `p1.expand(read_cif(CFA1)).n_atoms == 242`.

Related and equally cheap: CLAUDE.md claims "the count is flat from 0.01 Å
to 0.2 Å on **every** structure in `resources/samples`". Nothing sweeps
the samples; `test_the_count_steps_and_then_goes_flat` does the sweep for
one file only. A `@pytest.mark.parametrize` over `resources/samples/*.cif`
asserting `expand(s, 0.01).n_atoms == expand(s, 0.2).n_atoms` would turn a
claim into a test in six lines.

---

### 7. `[minor]` Neither of the two remaining conftest guards is self-checking

**What.** `pytest_runtest_teardown` (`conftest.py:195`) and
`_no_blocking_modal` (`conftest.py:241`) both carry "must stay" / "do not
remove it" in CLAUDE.md and neither has a test.

**Why it matters.** Asymmetric. Removing `_no_blocking_modal` turns a
failure into a hang — bad, but loud. Removing the teardown guard is
*silent*: the suite still passes, gets gradually slower, and eventually
aborts in `dlopen` with a stack that names nothing. CLAUDE.md's own
"Aborted runs" section is the write-up of the last time that happened.

**A fix.** `test_a_window_a_test_built_is_gone_before_the_next_one` in
`test_window_layout.py` — build a `MainWindow` in one test, keep a
`weakref` to it at module scope, and in a second test assert the weakref
is dead. One assertion, and it fails the moment the teardown hook is
dropped.

---

### 8. `[minor]` Two named regressions are pinned by a stand-in rather than the structure CLAUDE.md names

- **"MFU-4l at +15% on *a* opens with 560 of its 848 bonds."**
  `test_io.py::test_a_stored_perception_can_be_written_and_read_back`
  pins the behaviour with **MIL-53** (126 bonds, 24 lost). The test is
  correct and cheaper; CLAUDE.md's number no longer corresponds to
  anything that runs. Worth updating one or the other so a reader does not
  go looking for the MFU-4l test.
- **"96 chemical bonds on MOF-5 with the net still on screen."** The
  net-edge picking rule is pinned (invariant #9), but on a two-atom
  fixture and a synthetic framework. The deletion half — a click aimed at
  the net suppressing the bond *and its whole orbit* — is pinned
  separately by `test_context_menu.py::test_deleting_a_bond_reports_the_whole_orbit`,
  not together with the picking.

---

### 9. `[minor]` Docstrings that promise more than the assertion checks

Three, all in otherwise good tests:

1. **`test_move_mode.py:258 test_the_copies_under_the_cursor_turn_with_it_too`.**
   Docstring: *"One image per site, which is all a rotation of the
   asymmetric unit can promise — two images of the same site cannot both
   be granted the same turn, and the first of them is the one that gets
   it."* The test builds `atoms` from `first.setdefault(...)`, i.e. it
   deliberately passes **one** image per site, so the two-image case is
   never exercised and "the first wins" is never asserted. This is the
   half of invariant #7 that CLAUDE.md flags as a limitation.
   *Fix:* pass both images of one site and assert the command's target for
   that site equals the one the first image asks for.
2. **`test_porosity.py:52 test_every_diameter_carries_what_it_means`.**
   Docstring implies the meanings are right; the assertion is
   `assert label and symbol and meaning` — three truthiness checks. The
   D_f wording that carries invariant #18b (`xtal/modules/zeopp.py:604`)
   would survive being replaced with `"x"`.
   *Fix:* assert `"bottleneck"` is in the D_f row's meaning.
3. **`tests/conftest.py:62 _settings_into_a_scratch_directory`.** Not a
   test, but the same failure: a 40-line docstring explaining exactly how
   this guard can silently do nothing, followed by code that has no
   assertion anywhere. See Finding 1.

---

## Strengths worth telling the author

- **`test_bond_orders.py::test_setting_every_bond_is_one_command_and_one_change`** —
  a performance invariant expressed as a *mechanism* assertion (one
  `structureChanged`, one revision, one undo step) on the real structure
  that stalled, rather than as a timing. Nothing flaky, nothing to tune.
- **The degraded-window sweep** — nine `workspace is None` tests across
  seven files, one per branch. Exactly what CLAUDE.md's "every branch
  downstream is still reachable" asks for.
- **`test_window_layout.py::test_no_panel_insists_on_more_room_than_a_column_can_spare`** —
  a sweep over all docks, so a new panel is caught without anybody
  remembering to add a test. The only invariant in the file that defends
  itself against future code.
- **The tolerance probes pass the real test of a test.** Reintroducing
  either regression CLAUDE.md describes produces a small, precise set of
  failures with the right messages — including the scan point reporting
  *"the cell went from 648 atoms to 712"*, which is the sentence from the
  documentation, generated by the application.

---

## What I did not get to

- I did not probe the invariants I read as pinned. Findings 1–4 are
  probe-backed; the rest of the "pinned" column is reading, not mutation
  testing. A fuller pass would inject one regression per invariant.
- **`xtal/mof/pormake` and the MOF/RCSR invariants** were only spot-checked
  (`test_block_writer.py`, `test_mof_builder.py`, `test_packaging.py` ran
  green); I did not judge the vendored-tree tests against
  `PROVENANCE.md`.
- **Coverage was not measured.** "Has a test" is not "is covered"; a
  `pytest --cov` over `xtal/core/p1.py`, `xtal/ff/optimize.py` and
  `xtalapp/workspace_shell.py` would find branches neither grep nor
  reading reaches.
- I did not run the full suite (memory pressure: swap at 9470/10240 MB
  throughout), so I cannot speak to the `workers.py` deadlock, to
  `--durations`, or to whether any invariant test is slow. Everything I
  ran was targeted and serial.
- **`resources/test/` is nearly absent on this machine** — it holds only
  `MOF-5/MOF-5.cif` and `workspace.json`. Nothing I ran skipped because of
  it; the one skip was Zeo++ (Finding 5). Tests that need more of
  `resources/test/` may exist and may have been silently satisfied by
  `resources/samples/` instead.
