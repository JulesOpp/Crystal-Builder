"""Planes: defined from the selection, measured against each other.

Three atoms determine a plane and a phenyl ring is six, so a plane is
made from the *selection* rather than from a counted run of clicks the
way a distance is.  These tests cover the chain from "select a ring,
press the button" to a number in the measurement table, and the two
things that make such a number trustworthy: it is re-fitted when the
atoms move, and it goes when they do.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal import Lattice, Structure  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

BOX = 30.0


def ring(radius: float = 1.39, tilt: float = 0.0,
         offset=(0.0, 0.0, 0.0)) -> np.ndarray:
    angles = np.radians(np.arange(0.0, 360.0, 60.0))
    points = np.stack([radius * np.cos(angles),
                       radius * np.sin(angles),
                       np.zeros(6)], axis=1)
    theta = np.radians(tilt)
    rotation = np.array([[1.0, 0.0, 0.0],
                         [0.0, np.cos(theta), -np.sin(theta)],
                         [0.0, np.sin(theta), np.cos(theta)]])
    return points @ rotation.T + np.asarray(offset)


def two_rings(tilt: float = 35.0) -> Structure:
    """Two flat six-rings, the second tilted by a known angle."""
    cart = np.vstack([ring(offset=(10.0, 10.0, 10.0)),
                      ring(tilt=tilt, offset=(18.0, 10.0, 10.0))])
    return Structure.from_arrays(Lattice.cubic(BOX), ["C"] * 12,
                                 cart / BOX, space_group="P1")


@pytest.fixture
def document() -> Document:
    return Document(two_rings())


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = AppSettings("CrystalBuilderTest", f"Plane{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


def define_both(document) -> None:
    document.select(range(6))
    document.define_plane()
    document.select(range(6, 12))
    document.define_plane()


# ------------------------------------------------------- the document

def test_a_plane_comes_from_the_selection(qtbot, document):
    document.select(range(6))
    with qtbot.waitSignal(document.planesChanged):
        message = document.define_plane()
    assert len(document.planes) == 1
    assert document.planes[0].atoms == tuple(range(6))
    assert "rms" in message


def test_fewer_than_three_atoms_is_not_a_plane(document):
    document.select([0, 1])
    assert "three" in document.define_plane()
    assert not document.planes


def test_planes_are_named_as_they_are_defined(document):
    define_both(document)
    assert [p.name for p in document.planes] == ["Plane 1", "Plane 2"]


def test_a_removed_name_is_not_reused(document):
    """A measurement already on the table names its planes, so handing
    Plane 1 to a different set of atoms would relabel history."""
    define_both(document)
    document.remove_plane(0)
    document.select([0, 1, 2])
    document.define_plane()
    assert [p.name for p in document.planes] == ["Plane 2", "Plane 1"]


def test_the_angle_between_two_planes(document):
    define_both(document)
    document.measure_plane_angles()
    assert len(document.measurements) == 1
    assert document.measurements[0].value == pytest.approx(35.0)
    assert document.measurements[0].kind == "plane angle"


def test_three_planes_give_every_pair(document):
    """There is no such thing as "the" angle between three planes, so
    all three are measured rather than one being chosen."""
    define_both(document)
    document.select([0, 2, 4])
    document.define_plane()
    assert "3" in document.measure_plane_angles()
    assert len(document.measurements) == 3


def test_measuring_needs_two_planes(document):
    document.select(range(6))
    document.define_plane()
    assert "two planes" in document.measure_plane_angles()
    assert not document.measurements


def test_only_the_chosen_planes_are_measured(document):
    define_both(document)
    document.select([0, 2, 4])
    document.define_plane()
    document.measure_plane_angles([0, 1])
    assert len(document.measurements) == 1


def test_a_plane_follows_the_atoms_that_define_it(document):
    """A plane stored as four numbers would go on reporting the angle
    the molecule used to have."""
    define_both(document)
    document.measure_plane_angles()
    before = document.measurements[0].value

    document.select(range(6, 12))
    document.rotate_selection([1.0, 0.0, 0.0], 20.0)

    assert document.measurements[0].value != pytest.approx(before)
    assert document.measurements[0].value == pytest.approx(55.0, abs=1e-6)


def test_deleting_an_atom_takes_its_plane_with_it(document):
    define_both(document)
    document.measure_plane_angles()
    document.select([0])
    document.delete_selection()

    assert len(document.planes) == 1
    assert not document.measurements


def test_planes_survive_a_save_and_reopen(document, tmp_path):
    define_both(document)
    document.measure_plane_angles()
    path = document.save(tmp_path / "rings.xtalproj")

    reopened = Document.load(path)
    assert [p.name for p in reopened.planes] == ["Plane 1", "Plane 2"]
    assert len(reopened.measurements) == 1
    assert reopened.measurements[0].value == pytest.approx(35.0)


# ----------------------------------------------------------- the window

def test_the_menu_defines_a_plane(window, document):
    window.add_document(document)
    assert not window.actions_["define_plane"].isEnabled()

    document.select(range(6))
    assert window.actions_["define_plane"].isEnabled()
    window.actions_["define_plane"].trigger()

    assert len(document.planes) == 1
    assert window.measure_dock.plane_list.count() == 1


def test_the_angle_entry_waits_for_two_planes(window, document):
    window.add_document(document)
    document.select(range(6))
    window.actions_["define_plane"].trigger()
    assert not window.actions_["plane_angle"].isEnabled()

    document.select(range(6, 12))
    window.actions_["define_plane"].trigger()
    assert window.actions_["plane_angle"].isEnabled()

    window.actions_["plane_angle"].trigger()
    assert window.measure_dock.table.rowCount() == 1
    assert "35" in window.measure_dock.table.item(0, 2).text()


def test_the_dock_defines_and_measures_too(window, document):
    window.add_document(document)
    document.select(range(6))
    window.measure_dock.define_plane()
    document.select(range(6, 12))
    window.measure_dock.define_plane()
    window.measure_dock.measure_plane_angle()

    assert len(document.measurements) == 1
    assert window.measure_dock.plane_list.count() == 2


def test_clearing_planes_leaves_the_measurements(window, document):
    """A measurement records two sets of atoms, not two rows of a
    list, so it outlives the planes it was taken between."""
    window.add_document(document)
    define_both(document)
    document.measure_plane_angles()
    window.actions_["clear_planes"].trigger()

    assert not document.planes
    assert len(document.measurements) == 1
    assert window.measure_dock.table.rowCount() == 1
