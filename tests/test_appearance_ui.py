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
from xtalapp.viewport import modes  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402


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
    assert dock.style.currentData() == "ball_stick"
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


def test_a_cancelled_colour_dialog_changes_nothing(window, rutile_cif,
                                                   monkeypatch):
    document = window.open_path(rutile_cif)
    monkeypatch.setattr(QColorDialog, "getColor",
                        lambda *a, **k: QColor())      # invalid
    window.style_dock._on_element_cell(0, 1)
    assert document.view.element_colors == {}


def test_the_view_menu_and_the_style_dock_agree(window, rutile_cif):
    document = window.open_path(rutile_cif)
    window.actions_["show_legend"].trigger()
    assert document.view.show_legend
    assert window.style_dock.legend.isChecked()

    window.style_dock.cell_box.setChecked(False)
    assert not document.view.show_cell
    assert not window.actions_["show_cell"].isChecked()


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


def _click(mode, document, model, atom):
    """Fire a click straight down z through a drawn atom."""
    drawn = next(i for i in range(model.n_atoms)
                 if model.instance(i) == (atom, (0, 0, 0)))
    x, y, z = model.positions[drawn]
    return mode.on_click(document, model, modes.ClickEvent(
        (float(x), float(y), float(z) - 500.0), (0.0, 0.0, 1.0)))


