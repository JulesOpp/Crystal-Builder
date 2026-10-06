"""Atom groups on the Document and in the picture.

What breaks if these regress: a colour or a hidden group that lands on
the wrong atoms after an edit, a hidden atom left out of a save or a
calculation, a colour written into a CIF, or Ctrl+Z missing a
group made, coloured or deleted.  The model is in
``test_atom_groups.py``.
"""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QColorDialog,
    QInputDialog,
    QWidget,
)

from xtal.core import p1  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402

RED = (255, 0, 0)
UIO67 = Path(__file__).resolve().parents[1] \
    / "resources/samples/cod/UiO-67.cif"


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


def test_making_colouring_and_deleting_a_group_are_undo_steps(rutile):
    """Ctrl+Z takes back a group made, a colour put on one and a group
    deleted, and Ctrl+Shift+Z puts each back -- a misclick on Delete
    Group would otherwise lose the group for good."""
    document = Document(rutile)
    seen = []
    document.atomGroupsChanged.connect(lambda: seen.append(1))
    document.make_atom_group([0], color=RED)
    document.set_atom_group_color(0, (0, 255, 0))
    document.remove_atom_group(0)
    assert document.atom_groups == [] and document.modified
    assert len(seen) == 3

    assert document.undo() == "Delete atom group"
    assert document.atom_groups[0].color == (0, 255, 0)
    assert document.undo() == "Colour atom group"
    assert document.atom_groups[0].color == RED
    assert document.undo() == "Colour selected atoms"
    assert document.atom_groups == [] and not document.modified
    assert len(seen) == 6

    document.redo()
    document.redo()
    assert document.atom_groups[0].color == (0, 255, 0)
    document.redo()
    assert document.atom_groups == []


def test_hiding_and_renaming_a_group_are_not_undo_steps(rutile):
    """A tick is how a hidden group is looked at, so Ctrl+Z after one
    takes back the last edit, not the look; a rename carries through
    an undo and redo of the group's making."""
    document = Document(rutile)
    document.make_atom_group([0])
    document.set_atom_group_shown(0, False)
    document.rename_atom_group(0, "the Ti")
    assert document.undo_label == "Group selected atoms"
    document.undo()
    document.redo()
    group, = document.atom_groups
    assert group.name == "the Ti" and not group.shown


def test_a_group_step_refreshes_no_crystal_panel(rutile):
    """A colour is not a change to the crystal: announcing one as
    ``structureChanged`` rebuilt the site table and the scene."""
    document = Document(rutile)
    changed = []
    document.structureChanged.connect(changed.append)
    document.make_atom_group([0], color=RED)
    document.undo()
    document.redo()
    assert changed == []


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


# ---------------------------------------------------- the window's half

class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def opened(qtbot, tmp_path, rutile_cif):
    settings = AppSettings("CrystalBuilderTest", f"Groups{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(window)
    return window, window.open_path(rutile_cif)


GROUP_ACTIONS = ("group_selected", "color_selected", "hide_selected")


def test_the_group_actions_need_a_selection(opened):
    """Greyed with nothing selected, live with an atom held -- and
    live during playback too, since none of them edits the crystal."""
    window, document = opened
    document.select([])
    assert not any(window.actions_[k].isEnabled() for k in GROUP_ACTIONS)
    document.select([0])
    assert all(window.actions_[k].isEnabled() for k in GROUP_ACTIONS)


def test_hide_selected_makes_a_hidden_group_that_its_tick_shows_again(
        opened, qtbot):
    """The selected atoms leave the picture as a hidden group listed,
    unticked, in the Style panel; ticking it draws them again."""
    window, document = opened
    ti = _titanium(document)
    document.select(ti)
    window.actions_["hide_selected"].trigger()

    assert len(document.atom_groups) == 1
    assert document.hidden_mask()[ti].all()
    panel = window.style_dock.atom_groups
    assert panel.count() == 1
    item = panel.item(0)
    assert item.text() == "Hidden 1"
    assert item.checkState() == Qt.Unchecked

    item.setCheckState(Qt.Checked)
    qtbot.waitUntil(lambda: document.hidden_mask() is None)
    assert document.atom_groups[0].shown
    assert window.style_dock.atom_groups.item(0).checkState() == Qt.Checked


def test_colour_selected_makes_a_group_in_the_chosen_colour(
        opened, monkeypatch):
    window, document = opened
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor(*RED)))
    ti = _titanium(document)
    document.select(ti)
    window.actions_["color_selected"].trigger()

    [group] = document.atom_groups
    assert group.color == RED and group.atoms == frozenset(ti)


def test_group_selected_takes_the_name_it_is_given(opened, monkeypatch):
    window, document = opened
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Titanium", True)))
    document.select(_titanium(document))
    window.actions_["group_selected"].trigger()
    assert [g.name for g in document.atom_groups] == ["Titanium"]


def test_the_atom_context_menu_offers_hide_and_colour(opened):
    window, document = opened
    document.select([0])
    texts = [a.text() for a in window.build_context_menu("atom").actions()]
    assert window.actions_["hide_selected"].text() in texts
    assert window.actions_["color_selected"].text() in texts


def test_the_style_panel_lists_each_group_with_its_tick_and_swatch(
        opened):
    """One row a group, ticked by whether it is drawn, with a swatch;
    the hint shows only while there is none, and Element colours is
    live only for a coloured group."""
    window, document = opened
    dock = window.style_dock
    assert not dock.atom_groups_hint.isHidden()
    assert dock.atom_groups.isHidden()

    document.make_atom_group([0], color=RED)
    document.make_atom_group([1], shown=False)
    panel = dock.atom_groups
    assert [panel.item(r).text() for r in range(panel.count())] \
        == ["Group 1", "Hidden 1"]
    assert [panel.item(r).checkState() for r in range(2)] \
        == [Qt.Checked, Qt.Unchecked]
    assert not panel.item(0).icon().isNull()
    assert dock.atom_groups_hint.isHidden()

    panel.setCurrentRow(0)
    assert dock.atom_group_buttons["elements"].isEnabled()
    dock.atom_group_buttons["elements"].click()
    assert document.atom_groups[0].color is None
    assert not dock.atom_group_buttons["elements"].isEnabled()

    panel.setCurrentRow(1)
    dock.atom_group_buttons["select"].click()
    assert document.selection.atoms == {1}
    dock.atom_group_buttons["delete"].click()
    assert [g.name for g in document.atom_groups] == ["Group 1"]


def test_renaming_a_group_in_the_list_renames_it(opened, qtbot):
    window, document = opened
    document.make_atom_group([0])
    window.style_dock.atom_groups.item(0).setText("Apex")
    qtbot.waitUntil(lambda: document.atom_groups[0].name == "Apex")


def test_ctrl_g_groups_the_selection(opened):
    """Ctrl+G is Group selected atoms; Grow to bonded neighbours has
    no key of its own any more."""
    window, _document = opened
    assert window.actions_["group_selected"].shortcut().toString() \
        == "Ctrl+G"
    assert window.actions_["expand_bonded"].shortcut().isEmpty()


def test_group_selected_atoms_in_the_panel_follows_the_menu(
        opened, monkeypatch):
    """The panel's button is the View menu's command: greyed with
    nothing selected, and a group made when pressed."""
    window, document = opened
    button = window.style_dock.group_selected_button
    document.select([])
    assert not button.isEnabled()
    document.select([0])
    assert button.isEnabled()
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Apex", True)))
    button.click()
    assert [g.name for g in document.atom_groups] == ["Apex"]


def test_a_cif_with_shelx_parts_opens_with_a_group_for_each_part():
    """UiO-67's embedded ``.res`` puts its disordered oxygens and
    linker in PART 1, 2 and -1: each is a group named after its PART,
    holding every P1 copy of its sites and nothing else."""
    document = Document.load(UIO67)
    names = [g.name for g in document.atom_groups]
    assert names == ["PART 1", "PART 2", "PART -1"]
    cell = document.cell
    for group in document.atom_groups:
        part = group.name.split()[1]
        expected = {a for a in range(cell.n_atoms)
                    if str(document.structure.sites[
                        int(cell.site_idx[a])].props.get(
                            "disorder_group")) == part}
        assert group.atoms == frozenset(expected) and expected
        assert group.color is None and group.shown
    assert "shelx_parts" not in document.structure.meta


def test_a_saved_project_does_not_make_its_part_groups_again(tmp_path):
    """A group deleted before the save stays deleted on reopening."""
    document = Document.load(UIO67)
    document.remove_atom_group(0)
    saved = document.save(tmp_path / "uio.xtalproj")
    again = Document.load(saved)
    assert [g.name for g in again.atom_groups] == ["PART 2", "PART -1"]

