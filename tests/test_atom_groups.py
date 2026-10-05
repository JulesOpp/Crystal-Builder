"""Atom groups: named sets of atoms drawn in a colour, or hidden.

Headless: ``xtal.core.atom_groups`` is the model the window's Style
panel lists.  A group is view state; what breaks here is a picture
that colours or hides atoms nobody put in the group.
"""

import numpy as np

from xtal.commands import CommandStack, Host
from xtal.commands.atoms import DeleteSites
from xtal.commands.cell import Supercell
from xtal.core import atom_groups, p1, symmetry


def _p1(structure):
    flat = symmetry.reduce_to_p1(structure)
    return flat, p1.expand(flat)


def _of(cell, element):
    return [a for a in range(cell.n_atoms) if cell.elements[a] == element]


def test_a_later_group_colours_over_an_earlier_one(rutile):
    """Two groups over one atom: the later one's colour is drawn, as a
    later stroke of paint is, and an atom in neither is not touched."""
    flat, cell = _p1(rutile)
    ti, oxygen = _of(cell, "Ti"), _of(cell, "O")
    everything = atom_groups.make(cell, flat.lattice, ti + oxygen,
                                  "all", color=(255, 0, 0))
    titanium = atom_groups.make(cell, flat.lattice, ti[:1], "one Ti",
                                color=(0, 0, 255))
    plain = atom_groups.make(cell, flat.lattice, ti, "no colour")
    rgb, mask = atom_groups.colors([everything, titanium, plain],
                                   cell.n_atoms)
    assert mask.all()
    assert tuple(rgb[ti[0]]) == (0, 0, 255)
    assert tuple(rgb[ti[1]]) == (255, 0, 0)
    assert all(tuple(rgb[o]) == (255, 0, 0) for o in oxygen)

    rgb, mask = atom_groups.colors([titanium], cell.n_atoms)
    assert mask.tolist() == [a == ti[0] for a in range(cell.n_atoms)]


def test_a_hidden_group_is_in_the_hidden_mask_and_a_shown_one_is_not(
        rutile):
    """Hiding is per group: a shown group hides nothing, so ticking one
    group off leaves the others' atoms drawn."""
    flat, cell = _p1(rutile)
    ti, oxygen = _of(cell, "Ti"), _of(cell, "O")
    groups = [atom_groups.make(cell, flat.lattice, ti, "Ti",
                               shown=False),
              atom_groups.make(cell, flat.lattice, oxygen, "O")]
    mask = atom_groups.hidden(groups, cell.n_atoms)
    assert set(np.flatnonzero(mask)) == set(ti)


def test_a_group_follows_its_atoms_when_an_edit_renumbers_the_cell(
        rutile):
    """Deleting the first Ti moves every later atom down one; the
    oxygen group is the same oxygens afterwards, not their neighbours,
    and a group holding only the deleted atom is left empty in the
    list rather than vanishing."""
    flat, cell = _p1(rutile)
    host, stack = Host(flat), CommandStack()
    first_ti, oxygen = _of(cell, "Ti")[0], _of(cell, "O")
    assert first_ti < min(oxygen)
    groups = [atom_groups.make(cell, flat.lattice, oxygen, "O",
                               color=(1, 2, 3)),
              atom_groups.make(cell, flat.lattice, [first_ti], "gone")]

    stack.push(DeleteSites([first_ti]), host)
    after = p1.expand(host.structure)
    kept, gone = atom_groups.follow(groups, after,
                                    host.structure.lattice)
    assert kept.atoms == {a - 1 for a in oxygen}
    assert all(after.elements[a] == "O" for a in kept.atoms)
    assert (kept.name, kept.color) == ("O", (1, 2, 3))
    assert gone.empty and gone.name == "gone"


def test_a_group_keeps_its_indices_through_an_edit_that_keeps_them(
        rutile):
    """A move keeps the numbering, so the group is the same indices,
    re-recorded where the atoms now are so a later renumbering edit
    still finds them."""
    flat, cell = _p1(rutile)
    group = atom_groups.make(cell, flat.lattice, [0, 1], "pair")
    same, = atom_groups.follow([group], cell, flat.lattice,
                               renumbered=False)
    assert same is group
    moved, = atom_groups.follow([group], cell, flat.lattice,
                                renumbered=False, moved=True)
    assert moved.atoms == group.atoms


def test_a_group_holds_every_copy_through_a_supercell(rutile):
    """Through a symmetry or cell change the command's map is
    followed: one Ti grouped in the cell is both its copies in a
    2x1x1."""
    cell = p1.expand(rutile)
    ti = _of(cell, "Ti")[0]
    group = atom_groups.make(cell, rutile.lattice, [ti], "Ti",
                             color=(9, 9, 9))
    host, stack = Host(rutile), CommandStack()
    command = Supercell(2, 1, 1)
    stack.push(command, host)
    after = p1.expand(host.structure)
    grown, = atom_groups.follow([group], after, host.structure.lattice,
                                via=command.atom_map())
    assert len(grown.atoms) == 2
    assert all(after.elements[a] == "Ti" for a in grown.atoms)

    back, = atom_groups.follow([grown], cell, rutile.lattice,
                               via=command.atom_map().inverse())
    assert back.atoms == {ti}


def test_a_group_round_trips_through_its_dict(rutile):
    """Saved and restored onto the same cell, a group is what it was:
    name, atoms, colour and tick."""
    flat, cell = _p1(rutile)
    group = atom_groups.make(cell, flat.lattice, _of(cell, "O"),
                             "oxygens", color=(10, 20, 30), shown=False)
    plain = atom_groups.make(cell, flat.lattice, [0], "plain")
    for saved in (group, plain):
        restored = atom_groups.from_dict(saved.to_dict(cell), cell,
                                         flat.lattice)
        assert restored == saved
    assert "color" not in plain.to_dict(cell)


def test_a_saved_group_that_no_longer_fits_is_dropped_not_misapplied(
        rutile, quartz):
    """A group saved over one structure and restored onto another --
    an index past the end, or an atom of another element at that
    number -- is dropped rather than colouring whichever atoms now
    have those numbers."""
    flat, cell = _p1(rutile)
    saved = atom_groups.make(cell, flat.lattice, _of(cell, "O"),
                             "oxygens").to_dict(cell)

    other = p1.expand(quartz)
    assert other.n_atoms > cell.n_atoms
    assert atom_groups.from_dict(saved, other, quartz.lattice) is None

    past_the_end = dict(saved, atoms=[cell.n_atoms])
    assert atom_groups.from_dict(past_the_end, cell, flat.lattice) is None
    assert atom_groups.from_dict({"atoms": "nonsense"}, cell,
                                 flat.lattice) is None


def test_a_new_group_is_named_after_the_first_free_number():
    """``Group 1``, ``Group 2``, ... and a gap is filled first."""
    taken = [atom_groups.AtomGroup("Group 1"),
             atom_groups.AtomGroup("Group 3")]
    assert atom_groups.next_name([]) == "Group 1"
    assert atom_groups.next_name(taken) == "Group 2"
    assert atom_groups.next_name(taken, "Hidden") == "Hidden 1"
