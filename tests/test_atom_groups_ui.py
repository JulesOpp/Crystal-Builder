"""Atom groups on the Document and in the picture.

What breaks if these regress: a colour or a hidden group that lands on
the wrong atoms after an edit, a hidden atom left out of a save or a
calculation, a colour written into a CIF, or Ctrl+Z taking back a
colour instead of the last edit.  The model is in
``test_atom_groups.py``.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")

from xtal.core import p1  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402

RED = (255, 0, 0)


def _scene(document):
    return build_scene(document.structure, document.view,
                       selection=document.selection,
                       hidden=document.hidden_mask(),
                       charges=document.charges,
                       atom_colors=document.atom_group_colors())


def _titanium(document):
    cell = document.cell
    return [a for a in range(cell.n_atoms) if cell.elements[a] == "Ti"]


def _half_owners(model):
    """The drawn atom each bond half starts at."""
    d = np.linalg.norm(model.bond_starts[:, None, :]
                       - model.positions[None, :, :], axis=2)
    return model.atom_index[d.argmin(axis=1)]


def test_a_coloured_group_draws_its_atoms_and_their_bond_halves_in_that_colour(
        rutile):
    """Every drawn copy of a grouped Ti is red, and so is each bond
    half that starts at one; the oxygens and their halves keep their
    element's colour."""
    document = Document(rutile)
    ti = set(_titanium(document))
    document.make_atom_group(ti, color=RED)
    model = _scene(document)
    red = np.all(model.colors == RED, axis=1)
    assert red.tolist() == [a in ti for a in model.atom_index.tolist()]

    assert len(model.bond_colors)
    owners = _half_owners(model)
    red_halves = np.all(model.bond_colors == RED, axis=1)
    assert red_halves.tolist() == [a in ti for a in owners.tolist()]


def test_a_hidden_group_is_out_of_the_picture_but_in_the_structure(
        rutile):
    """A hidden group is not drawn and no bond reaches it, but the
    cell still holds all six atoms."""
    document = Document(rutile)
    ti = _titanium(document)
    message = document.make_atom_group(ti, shown=False)
    assert message == "Hidden 1: hid 2 atoms"
    model = _scene(document)
    assert not set(model.atom_index.tolist()) & set(ti)
    assert len(model.bond_keys) == 0
    assert document.cell.n_atoms == 6
    assert document.shown_summary() == "4 of 6 atoms shown"


def test_showing_a_hidden_group_again_draws_it(rutile):
    document = Document(rutile)
    ti = _titanium(document)
    document.make_atom_group(ti, shown=False)
    document.make_atom_group([a for a in range(6) if a not in ti],
                             shown=False)
    assert _scene(document).atom_index.size == 0
    document.set_atom_group_shown(0, True)
    assert set(_scene(document).atom_index.tolist()) == set(ti)


def test_making_or_hiding_a_group_is_not_an_undo_step(rutile):
    """A colour is how the crystal is drawn, not a change to it."""
    document = Document(rutile)
    seen = []
    document.atomGroupsChanged.connect(lambda: seen.append(1))
    document.make_atom_group([0], color=RED)
    document.set_atom_group_shown(0, False)
    document.set_atom_group_color(0, (0, 255, 0))
    document.rename_atom_group(0, "the Ti")
    assert len(seen) == 4
    assert not document.can_undo
    assert not document.modified
    assert document.atom_groups[0].name == "the Ti"


def test_an_empty_selection_makes_no_group(rutile):
    document = Document(rutile)
    assert document.make_atom_group() == "nothing selected to group"
    assert document.atom_groups == []


def test_colour_by_draws_over_a_group_colour_and_element_brings_it_back(
        rutile):
    """*Colour by* draws a number; a group colour under it would make
    the number unreadable, and *Element* has to bring it back because
    nothing was stored."""
    document = Document(rutile)
    ti = _titanium(document)
    document.make_atom_group(ti, color=RED)
    document.update_view(color_by="coordination")
    model = _scene(document)
    assert not np.all(model.colors == RED, axis=1).any()
    document.update_view(color_by="")
    model = _scene(document)
    assert np.all(model.colors == RED, axis=1).sum() \
        == np.isin(model.atom_index, ti).sum() > 0


def test_a_coloured_group_colours_its_label_under_colour_labels(rutile):
    """Skeletal style writes each atom as ink, or its element's colour
    with *colour labels* on; a grouped atom's label takes the group's
    colour there instead."""
    document = Document(rutile)
    ti = _titanium(document)
    document.make_atom_group(ti, color=RED)
    document.update_view(style="skeletal", sketch_color_labels=True)
    model = _scene(document)
    red = np.all(model.colors == RED, axis=1)
    assert red.tolist() == [a in ti for a in model.atom_index.tolist()]
    document.update_view(sketch_color_labels=False)
    assert not np.all(_scene(document).colors == RED, axis=1).any()


def test_groups_are_saved_in_the_project_and_restored(tmp_path, rutile):
    document = Document(rutile)
    ti = _titanium(document)
    document.make_atom_group(ti, name="titanium", color=RED)
    document.make_atom_group([a for a in range(6) if a not in ti],
                             shown=False)
    path = document.save(tmp_path / "rutile")
    again = Document.load(path)
    assert [(g.name, set(g.atoms), g.color, g.shown)
            for g in again.atom_groups] == [
        ("titanium", set(ti), RED, True),
        ("Hidden 1", set(range(6)) - set(ti), None, False)]


def test_a_cif_export_carries_no_group(tmp_path, rutile):
    """Export cleans: a group is view state and never leaves in a
    file another program reads."""
    document = Document(rutile)
    document.make_atom_group(_titanium(document), name="titanium",
                             color=RED, shown=False)
    target = document.export(tmp_path / "out.cif")
    text = target.read_text()
    assert "titanium" not in text
    assert "Ti" in text


def test_show_all_shows_every_hidden_group(rutile):
    """Show All lets go of every hidden atom; the groups and their
    colours stay, ticked."""
    document = Document(rutile)
    document.make_atom_group([0], color=RED, shown=False)
    document.make_atom_group([1], shown=False)
    document.select([2])
    document.show_only_selected()
    document.show_all()
    assert document.hidden_mask() is None
    assert [g.shown for g in document.atom_groups] == [True, True]
    assert document.atom_groups[0].color == RED


def test_a_group_keeps_its_atoms_through_reduce_to_p1_and_find_symmetry(
        rutile):
    document = Document(rutile)
    ti = _titanium(document)
    document.make_atom_group(ti, color=RED)
    for step in (document.reduce_to_p1, document.find_symmetry):
        step()
        cell = document.cell
        group = document.atom_groups[0].atoms
        assert {cell.elements[a] for a in group} == {"Ti"}
        assert len(group) == len(_titanium(document))


def test_a_coloured_group_survives_a_supercell_on_every_copy(rutile):
    document = Document(rutile)
    document.make_atom_group(_titanium(document), color=RED)
    document.make_supercell(2, 2, 1)
    cell = document.cell
    assert cell.n_atoms == 24
    assert document.atom_groups[0].atoms == set(_titanium(document))
    rgb, mask = document.atom_group_colors()
    assert mask.sum() == 8


def test_undoing_a_symmetry_change_restores_the_group(rutile):
    """Ctrl+Z on a supercell takes the group back to the atoms it had,
    by the operation's own map run backwards."""
    document = Document(rutile)
    ti = _titanium(document)
    document.make_atom_group(ti, color=RED)
    document.make_supercell(2, 1, 1)
    document.undo()
    assert document.atom_groups[0].atoms == set(ti)
    assert p1.expand(document.structure).n_atoms == 6


def test_a_group_whose_atoms_are_deleted_stays_in_the_list_empty(rutile):
    document = Document(rutile)
    document.reduce_to_p1()
    document.make_atom_group([0], name="lone Ti")
    document.select([0])
    document.delete_selection()
    group, = document.atom_groups
    assert group.empty and group.name == "lone Ti"
    assert document.select_atom_group(0) == "lone Ti has no atoms left"
