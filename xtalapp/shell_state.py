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
