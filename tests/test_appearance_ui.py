"""Appearance and analysis, through the application.

The rule running through all of it: none of this is a change to the
crystal.  Choosing a colour, taking a measurement or turning on the
legend must never mark the document modified and must never land on the
undo stack -- so most of these tests end by checking that it did not.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QColorDialog, QInputDialog  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal import Lattice, Structure  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.viewport import modes, picking  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402
from xtalapp.viewport.view_settings import BACKGROUNDS  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Look{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def document(rutile):
    return Document(rutile)


# ------------------------------------------------------- the style dock

def test_the_style_dock_shows_the_view(window, rutile_cif):
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    assert dock.style.currentData() == "ball_stick_occupancy"
    assert [dock.elements.item(r, 0).text()
            for r in range(dock.elements.rowCount())] == ["O", "Ti"]

    document.update_view(style="polyhedra", show_legend=True)
    assert dock.style.currentData() == "polyhedra"
    assert dock.legend.isChecked()


def test_the_style_dock_drives_the_view(window, rutile_cif):
    document = window.open_path(rutile_cif)
    dock = window.style_dock

    dock.style.setCurrentIndex(dock.style.findData("spacefill"))
    assert document.view.style == "spacefill"

    dock.bond_radius.setValue(0.3)
    assert document.view.bond_radius == pytest.approx(0.3)

    dock.legend.setChecked(True)
    assert document.view.show_legend

    dock.labels.setCurrentIndex(dock.labels.findData("element"))
    assert document.view.label_mode == "element"

    assert not document.modified and not document.can_undo


def test_element_colours_and_radii_can_be_overridden(window,
                                                     rutile_cif,
                                                     monkeypatch):
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    row = [dock.elements.item(r, 0).text()
           for r in range(dock.elements.rowCount())].index("Ti")

    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor(10, 20, 30))
    dock._on_element_cell(row, 1)
    assert document.view.element_colors["Ti"] == (10, 20, 30)
    assert document.view.color_for("Ti") == (10, 20, 30)

    monkeypatch.setattr(QInputDialog, "getDouble",
                        lambda *a, **k: (1.75, True))
    dock._on_element_cell(row, 2)
    assert document.view.element_radii["Ti"] == pytest.approx(1.75)

    scene = build_scene(document.structure, document.view)
    assert (10, 20, 30) in {tuple(c) for c in scene.colors}

    dock.reset_elements()
    assert document.view.element_colors == {}
    assert document.view.element_radii == {}
    assert not document.modified


def test_the_net_and_plane_colours_are_chosen_from_the_style_dock(
        window, rutile_cif, monkeypatch):
    """Both were module constants, which meant a net drawn over a
    purple framework and no way to move either of them."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor(10, 200, 90))

    dock.flat["topology_color"].click()
    assert document.view.topology_color == (10, 200, 90)
    dock.flat["plane_color"].click()
    assert document.view.plane_color == (10, 200, 90)
    assert not document.modified


def test_the_octant_switch_only_applies_where_there_are_ellipsoids(
        window, rutile_cif):
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    assert not dock.octants.isEnabled()

    document.update_view(style="ortep")
    assert dock.octants.isEnabled() and dock.octants.isChecked()
    dock.octants.setChecked(False)
    assert not document.view.ellipsoid_octants
    assert not document.modified


def _laid_out_at(qtbot, dock, width):
    """The dock floated at ``width`` and shown, so its layouts have
    placed everything: a hidden widget has no geometry to assert on."""
    dock.setFloating(True)
    dock.resize(width, 900)
    dock.show()
    qtbot.waitExposed(dock)
    qtbot.wait(20)
    return dock.columns


def test_the_style_panel_is_headed_groups_in_the_agreed_order(window):
    """Breaks when a control drifts out of its group, or a group moves:
    the order is what one column reads, and the manual photographs it."""
    dock = window.style_dock
    assert [group.title() for group in dock.groups] == [
        "Drawing", "Transparency", "Scene", "Show", "Colours",
        "Depth cue"]
    homes = {"Drawing": (dock.style, dock.atom_scale, dock.bond_radius,
                         dock.ellipsoid_probability, dock.octants),
             "Transparency": (dock.opacity, dock.pore_opacity),
             "Scene": (dock.background, dock.labels, dock.legend),
             "Show": (dock.cell_box, dock.cell_axes, dock.topology,
                      dock.pore_nodes),
             "Colours": tuple(dock.flat.values()),
             "Depth cue": (dock.depth_cue, dock.depth_cue_start,
                           dock.depth_cue_end, dock.depth_cue_strength,
                           dock.depth_cue_preview)}
    for group in dock.groups:
        for control in homes[group.title()]:
            assert group.isAncestorOf(control), (group.title(), control)
    # The element table is below the groups, not in either column.
    body = dock.widget().widget().layout()
    assert body.indexOf(dock.columns) < body.indexOf(
        dock.elements.parentWidget())


def _frame(dock) -> int:
    """What the dock takes off the width before its groups get any."""
    return dock.width() - dock.columns.width()


def test_a_wide_style_panel_puts_its_groups_side_by_side(qtbot, window,
                                                         rutile_cif):
    """520 px on macOS.  Where the font is larger -- Windows -- the
    groups are too, and wide means what the panel says two columns
    need rather than a number measured in another typeface."""
    window.open_path(rutile_cif)
    dock = window.style_dock
    columns = _laid_out_at(qtbot, dock, 520)
    needed = columns.layout().two_column_width() + _frame(dock)
    if needed > 520:
        columns = _laid_out_at(qtbot, dock, needed)
    drawing, show = dock.groups[0], dock.groups[3]
    assert columns.two_columns()
    assert drawing.y() == show.y()
    assert show.x() > drawing.x() + drawing.width()


def test_a_narrow_style_panel_stacks_its_groups_instead_of_scrolling_sideways(
        qtbot, window, rutile_cif):
    """A panel read by scrolling sideways is one whose right-hand half
    nobody finds, and 220 px is the column dragged nearly shut -- on
    macOS.  In a larger font one stacked column is itself wider than
    that, so there the test takes the narrowest the panel says it can
    be, which is the claim: stacked, it needs no more."""
    window.open_path(rutile_cif)
    dock = window.style_dock
    columns = _laid_out_at(qtbot, dock, 220)
    scroll = dock.widget()
    needed = (scroll.widget().minimumSizeHint().width()
              + dock.width() - scroll.viewport().width())
    if needed > 220:
        columns = _laid_out_at(qtbot, dock, needed)
    assert not columns.two_columns()
    xs = {group.x() for group in dock.groups}
    assert len(xs) == 1
    assert [g.y() for g in dock.groups] == sorted(
        g.y() for g in dock.groups)
    assert not dock.widget().horizontalScrollBar().isVisible()


def test_depth_cue_opens_itself_for_a_document_that_has_it_on(
        window, rutile_cif, quartz_cif):
    first = window.open_path(rutile_cif)
    first.update_view(depth_cue=True)
    window.open_path(quartz_cif)
    fold = window.style_dock.depth_cue_fold
    assert not fold.is_open()

    window.tabs.setCurrentIndex(window.documents.index(first))
    assert fold.is_open()


def test_depth_cue_stays_closed_for_one_that_does_not(window,
                                                       rutile_cif):
    window.open_path(rutile_cif)
    fold = window.style_dock.depth_cue_fold
    assert not fold.is_open()
    assert fold.body.isHidden()


def test_a_fold_opened_by_hand_stays_open_while_the_document_does(
        window, rutile_cif):
    """A refresh follows every view change; if it re-decided the fold,
    dragging a slider inside it would fold it shut under the cursor."""
    document = window.open_path(rutile_cif)
    fold = window.style_dock.depth_cue_fold
    fold.arrow.click()
    document.update_view(style="spacefill")
    window._update_ui()
    assert fold.is_open()


def test_the_element_table_keeps_its_height_when_the_panel_grows(
        qtbot, window, rutile_cif):
    """Stretched, it was four rows of MOF-5 and 400 px of white."""
    window.open_path(rutile_cif)
    dock = window.style_dock
    _laid_out_at(qtbot, dock, 520)
    before = dock.elements.height()
    dock.resize(520, 1600)
    qtbot.wait(20)
    assert dock.elements.height() == before


def test_the_fade_sliders_are_dead_until_the_fade_is_on(window,
                                                       rutile_cif):
    """The panel's own rule, extended to the two new ones: a control
    that does nothing is indistinguishable from a broken one, and all
    three of these do nothing until the checkbox is ticked."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    sliders = (dock.depth_cue_strength, dock.depth_cue_start,
               dock.depth_cue_end)
    assert not any(s.isEnabled() for s in sliders)

    dock.depth_cue.setChecked(True)
    assert document.view.depth_cue
    assert all(s.isEnabled() for s in sliders)


def test_where_the_fade_starts_and_ends_reach_the_view(window,
                                                        rutile_cif):
    """Each control shows its number, and the number is the setting:
    typing 40 in the box is the same as dragging to 40."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    dock.depth_cue.setChecked(True)

    dock.depth_cue_start.spin.setValue(40)
    assert document.view.depth_cue_start == pytest.approx(0.40)
    assert dock.depth_cue_start.slider.value() == 40
    dock.depth_cue_end.setValue(80)
    assert document.view.depth_cue_end == pytest.approx(0.80)
    dock.depth_cue_strength.setValue(55)
    assert document.view.depth_cue_strength == pytest.approx(0.55)
    assert not document.modified


def test_dragging_the_start_past_the_end_pushes_the_end_along(
        window, rutile_cif):
    """A slider that refuses to move reads as broken; one that lets
    the start overtake the end draws a fade of no length."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    dock.depth_cue.setChecked(True)
    dock.depth_cue_end.setValue(50)

    dock.depth_cue_start.setValue(70)
    view = document.view
    assert view.depth_cue_start < view.depth_cue_end
    assert view.depth_cue_end == pytest.approx(0.75)
    assert dock.depth_cue_end.value() == 75

    dock.depth_cue_end.setValue(10)
    assert view.depth_cue_start < view.depth_cue_end
    assert view.depth_cue_start == pytest.approx(0.05)


def test_the_preview_strip_is_the_fade_the_viewport_draws(window,
                                                          rutile_cif):
    """Clear in front of the start, fully faded behind the end, and
    nothing at all with the switch off."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    preview = dock.depth_cue_preview
    assert not preview.fractions(100).any()

    dock.depth_cue.setChecked(True)
    document.update_view(depth_cue_start=0.2, depth_cue_end=0.6,
                         depth_cue_strength=0.8)
    strip = preview.fractions(100)
    assert not strip[:19].any()
    assert strip[61:] == pytest.approx(0.8)


def test_a_cancelled_colour_dialog_changes_nothing(window, rutile_cif,
                                                   monkeypatch):
    document = window.open_path(rutile_cif)
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor())      # invalid
    window.style_dock._on_element_cell(0, 1)
    assert document.view.element_colors == {}


def test_the_style_dock_says_which_background_is_showing(window,
                                                        rutile_cif):
    """It said White for all four of them.

    ``QComboBox.findData`` compares through QVariant, which never
    matches a Python tuple against an equal one -- so a combo whose
    entries carried colours answered -1 for every background there is,
    and the panel fell back to its first entry every time it
    refreshed.  Paper is how it was noticed; black and slate were just
    as wrong.
    """
    document = window.open_path(rutile_cif)
    dock = window.style_dock

    for name, color in BACKGROUNDS.items():
        document.update_view(background=color)
        assert dock.background.currentData() == name
        assert dock.background.currentText() == name.capitalize()


def test_a_background_chosen_in_the_dock_reaches_the_view(window,
                                                          rutile_cif):
    document = window.open_path(rutile_cif)
    dock = window.style_dock

    dock.background.setCurrentIndex(dock.background.findData("paper"))

    assert tuple(document.view.background) == BACKGROUNDS["paper"]
    assert not document.modified


def test_a_custom_background_keeps_saying_it_is_custom(
        window, rutile_cif, monkeypatch):
    """And can be picked again.

    A colour that is none of the four used to read as White, which is
    the same bug from the other side.  Now it reads Custom -- and
    because a combo does not report the entry that is already current
    being chosen again, choosing it a second time has to go through
    ``activated`` or there is no way back to the colour dialog.
    """
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor(12, 34, 56))
    custom = dock.background.findData("custom")

    dock.background.activated.emit(custom)
    assert tuple(document.view.background) == (12, 34, 56)
    assert dock.background.currentData() == "custom"

    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor(65, 43, 21))
    dock.background.activated.emit(custom)
    assert tuple(document.view.background) == (65, 43, 21)
    assert not document.modified


def test_a_cancelled_background_dialog_leaves_the_view_alone(
        window, rutile_cif, monkeypatch):
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    document.update_view(background=BACKGROUNDS["slate"])
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor())          # invalid

    dock.background.activated.emit(dock.background.findData("custom"))

    assert tuple(document.view.background) == BACKGROUNDS["slate"]
    assert dock.background.currentData() == "slate"


def test_the_view_menu_and_the_style_dock_agree(window, rutile_cif):
    document = window.open_path(rutile_cif)
    window.actions_["show_legend"].trigger()
    assert document.view.show_legend
    assert window.style_dock.legend.isChecked()

    window.style_dock.cell_box.setChecked(False)
    assert not document.view.show_cell
    assert not window.actions_["show_cell"].isChecked()


def test_the_cell_axes_are_one_switch_in_the_dock_and_the_menu(
        window, rutile_cif):
    """``show_axes`` was saved and loaded for years and read by
    nothing; the triad it now switches is only worth having if the
    dock and View > Show agree about it."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    assert dock.cell_axes.isChecked()

    dock.cell_axes.setChecked(False)
    assert not document.view.show_axes
    assert not window.actions_["show_axes"].isChecked()

    window.actions_["show_axes"].trigger()
    assert document.view.show_axes and dock.cell_axes.isChecked()
    assert not document.modified


def test_the_net_can_be_hidden_from_the_style_dock(window, rutile_cif):
    """The checkbox and View > Show > Net are one switch; if they
    drift, the dock says the net is hidden while it is drawn."""
    document = window.open_path(rutile_cif)
    dock = window.style_dock
    assert dock.topology.isChecked()

    dock.topology.setChecked(False)
    assert not document.view.show_topology
    assert not window.actions_["show_topology"].isChecked()

    window.actions_["show_topology"].trigger()
    assert document.view.show_topology
    assert dock.topology.isChecked()
    assert not document.modified


# ------------------------------------------------------- measurements

def test_measuring_two_atoms_gives_a_distance(document):
    text = document.add_measurement([0, 2])
    assert "A" in text
    assert len(document.measurements) == 1
    assert document.measurements[0].kind == "distance"
    assert not document.modified and not document.can_undo


def test_the_measure_mode_counts_the_clicks_down(document):
    model = build_scene(document.structure, document.view)
    mode = modes.get("measure")
    mode.target, mode.picked = 3, []

    messages = [_click(mode, document, model, atom)
                for atom in (2, 0, 3)]
    assert messages[0] == "2 more atoms"
    assert messages[1] == "1 more atom"
    assert "deg" in messages[2]
    assert len(document.measurements) == 1
    assert document.measurements[0].kind == "angle"
    assert mode.picked == []


def test_the_measure_mode_refuses_the_same_atom_twice(document):
    model = build_scene(document.structure, document.view)
    mode = modes.get("measure")
    mode.target, mode.picked = 2, []
    _click(mode, document, model, 0)
    assert "already" in _click(mode, document, model, 0)
    assert document.measurements == []


def test_clicking_empty_space_abandons_a_measurement(document):
    model = build_scene(document.structure, document.view)
    mode = modes.get("measure")
    mode.target, mode.picked = 4, []
    _click(mode, document, model, 0)
    assert mode.picked
    away = mode.on_click(document, model, modes.ClickEvent(
        (500.0, 500.0, -500.0), (0.0, 0.0, 1.0)))
    assert away == "cancelled"
    assert mode.picked == []
    assert document.measurements == []


def test_measurements_follow_the_atoms_they_name(document):
    document.add_measurement([0, 2])
    before = document.measurements[0].value

    document.select([2])
    document.move_selection([0.05, 0.0, 0.0])
    assert document.measurements[0].value != pytest.approx(before)

    document.undo()
    assert document.measurements[0].value == pytest.approx(before)


def test_deleting_an_atom_takes_its_measurements_with_it(document):
    document.add_measurement([0, 2])
    document.select([2])
    document.delete_selection()
    assert document.measurements == []


def test_the_measure_dock_lists_and_removes(window, rutile_cif):
    document = window.open_path(rutile_cif)
    dock = window.measure_dock
    document.add_measurement([0, 2])
    document.add_measurement([2, 0, 3])
    assert dock.table.rowCount() == 2
    assert dock.table.item(0, 1).text() == "distance"
    assert dock.table.item(1, 1).text() == "angle"

    dock.table.selectRow(0)
    dock.remove_selected()
    assert dock.table.rowCount() == 1
    dock.clear()
    assert dock.table.rowCount() == 0
    assert not document.modified


def test_the_measure_dock_chooses_how_many_atoms(window, rutile_cif):
    window.open_path(rutile_cif)
    dock = window.measure_dock
    dock.target.setCurrentIndex(2)                  # torsion
    assert dock.atom_count() == 4
    assert modes.get("measure").target == 4
    dock.target.setCurrentIndex(0)
    assert modes.get("measure").target == 2


def test_choosing_a_measurement_selects_its_atoms(window, rutile_cif):
    document = window.open_path(rutile_cif)
    document.add_measurement([0, 2])
    window.measure_dock.table.selectRow(0)
    assert document.selection.atoms == {0, 2}


# ------------------------------------------------- measuring a bond
#
# "How long is that bond?" is the question the measuring tool is most
# often opened for, and it was the one thing it would not answer: a
# selected bond holds no atoms, so Measure was greyed out over the
# very thing being asked about.


def test_a_selected_bond_reports_its_length(window, rutile_cif):
    """Both directions of the gesture end here -- select a bond then
    press Measure, or press Measure then click the bond."""
    document = window.open_path(rutile_cif)
    bond = document.graph.bonds[0]
    document.select_bond(bond.key())

    assert window.actions_["measure_selection"].isEnabled()
    window.measure_selection()

    [taken] = document.measurements
    assert taken.kind == "distance"
    assert taken.atoms == tuple(sorted((bond.i, bond.j)))
    assert taken.value == pytest.approx(bond.distance, abs=1e-9)
    assert not document.modified and not document.can_undo


def test_measuring_a_bond_is_measuring_its_two_ends(window,
                                                    rutile_cif):
    """Stored as the pair of atoms and not as the bond, so it survives
    -- and follows the crystal -- the way every other measurement
    does."""
    document = window.open_path(rutile_cif)
    bond = document.graph.bonds[0]
    document.select_bond(bond.key())
    window.measure_selection()
    document.add_measurement([bond.i, bond.j])

    first, second = document.measurements
    assert first.value == pytest.approx(second.value)
    assert first.atoms == tuple(sorted(second.atoms))


def test_several_selected_bonds_are_measured_in_one_batch(
        window, rutile_cif):
    """A box round a linker selects eleven bonds, and eleven separate
    announcements is what makes a large structure stop responding."""
    document = window.open_path(rutile_cif)
    for bond in document.graph.bonds:
        document.select_bond(bond.key(), "toggle")
    pairs = {key[:2] for key in document.selection.bonds}
    assert len(pairs) > 1

    fired = []
    document.measurementsChanged.connect(lambda: fired.append(1))
    message = document.add_bond_measurements(document.selection.bonds)

    assert fired == [1]
    assert len(document.measurements) == len(pairs)
    assert f"{len(pairs)} bonds" in message


def test_one_bond_measured_twice_over_is_one_number(document):
    """Two images of the same pair recompute to the same distance, so
    a second row could never disagree with the first."""
    bonds = [b for b in document.graph.bonds]
    pair = bonds[0].i, bonds[0].j
    document.add_bond_measurements([(pair[0], pair[1], (0, 0, 0)),
                                    (pair[0], pair[1], (1, 0, 0))])
    assert len(document.measurements) == 1


def test_a_bond_to_an_atoms_own_image_says_why_it_cannot(document):
    """A real state and not an oversight: the two ends are one atom,
    and the minimum image between an atom and itself is zero."""
    with pytest.raises(ValueError, match="one atom"):
        document.add_bond_measurements([(0, 0, (1, 0, 0))])


def test_measure_is_not_offered_when_an_atom_is_also_in_hand(
        window, rutile_cif):
    """An atom in hand means the atoms are the question -- otherwise
    picking up a bond on the way would quietly change what Measure
    means."""
    document = window.open_path(rutile_cif)
    document.select_bond(document.graph.bonds[0].key())
    document.select([0], "toggle")
    assert not window.actions_["measure_selection"].isEnabled()


def test_the_measure_mode_takes_a_bond_in_one_click(document):
    """The bond already names its two atoms; asking for each end is
    asking the user to say it twice -- and it happens whatever the
    mode was counting down to."""
    model = build_scene(document.structure, document.view)
    mode = modes.get("measure")
    mode.target, mode.picked = 4, []

    message = _click_bond(mode, document, model)
    assert " A" in message
    [taken] = document.measurements
    assert taken.kind == "distance"
    assert len(document.selection.bonds) == 1
    assert taken.atoms == tuple(
        sorted(next(iter(document.selection.bonds))[:2]))
    assert mode.picked == []


def test_a_bond_click_drops_a_half_finished_measurement(document):
    """The click named a different measurement from the one being
    assembled, and folding the atoms into it would answer a question
    nobody asked."""
    model = build_scene(document.structure, document.view)
    mode = modes.get("measure")
    mode.target, mode.picked = 3, []
    _click(mode, document, model, 0)
    assert mode.picked == [0]

    _click_bond(mode, document, model)
    assert mode.picked == []
    assert not document.selection.atoms
    assert [m.kind for m in document.measurements] == ["distance"]


# ------------------------------------------------------- projects

def test_a_project_keeps_a_whole_session(window, rutile_cif, tmp_path):
    document = window.open_path(rutile_cif)
    document.update_view(style="polyhedra", show_legend=True,
                         element_colors={"Ti": (9, 9, 9)})
    document.select([0, 2])
    document.add_measurement([0, 2])

    path = document.save_project(tmp_path / "session.xtalproj")
    assert path.exists()
    assert not document.modified            # saving a project is not
    assert document.path.name == "rutile.cif"   # ... a "save as"

    reopened = Document.load(path)
    assert reopened.view.style == "polyhedra"
    assert reopened.view.show_legend
    assert reopened.view.element_colors["Ti"] == (9, 9, 9)
    assert reopened.selection.atoms == {0, 2}
    assert len(reopened.measurements) == 1
    assert reopened.measurements[0].value == pytest.approx(
        document.measurements[0].value)


def test_a_project_opens_through_the_window(window, rutile_cif,
                                            tmp_path):
    document = window.open_path(rutile_cif)
    document.update_view(style="stick")
    path = document.save_project(tmp_path / "session.xtalproj")

    reopened = window.open_path(path)
    assert reopened is not None
    assert reopened.view.style == "stick"
    assert window.style_dock.style.currentData() == "stick"


def test_a_project_of_an_empty_document_still_opens(tmp_path):
    document = Document(Structure.empty(Lattice.cubic(7.0)))
    path = document.save_project(tmp_path / "blank.xtalproj")
    reopened = Document.load(path)
    assert reopened.structure.n_sites == 0
    assert reopened.structure.lattice.lengths[0] == pytest.approx(7.0)


def test_a_session_pointing_at_atoms_that_are_gone_is_dropped(
        tmp_path, rutile):
    """A project is a convenience; a measurement naming an atom that is
    not there would be a lie about the crystal."""
    from xtal.io import write_project

    document = Document(rutile)
    document.add_measurement([0, 2])
    session = document.session()
    session["measurements"][0]["atoms"] = [0, 99]
    session["selection"] = [0, 500]

    path = write_project(rutile, tmp_path / "stale.xtalproj",
                         view=document.view.to_dict(), session=session)
    reopened = Document.load(path)
    assert reopened.measurements == []
    assert reopened.selection.atoms == {0}


def _click_bond(mode, document, model, half: int = 1):
    """Fire a click down z through a bond half, from the point along
    it where the ray reaches the bond first.

    Not simply the middle: an atom wins the depth test -- which is
    what makes a click on the join between an atom and the bond
    leaving it mean the atom -- so the point has to be far enough
    along the half to be clear of both ends.
    """
    start, end = model.bond_starts[half], model.bond_ends[half]
    for fraction in (0.5, 0.7, 0.85, 0.95):
        x, y, z = start + fraction * (end - start)
        origin = (float(x), float(y), float(z) - 500.0)
        if picking.pick(model, origin, (0.0, 0.0, 1.0))[0] == "bond":
            return mode.on_click(document, model,
                                 modes.ClickEvent(origin,
                                                  (0.0, 0.0, 1.0)))
    raise AssertionError("every ray through that bond met an atom")


def _click(mode, document, model, atom):
    """Fire a click straight down z through a drawn atom."""
    drawn = next(i for i in range(model.n_atoms)
                 if model.instance(i) == (atom, (0, 0, 0)))
    x, y, z = model.positions[drawn]
    return mode.on_click(document, model, modes.ClickEvent(
        (float(x), float(y), float(z) - 500.0), (0.0, 0.0, 1.0)))


