"""A drag repaints what moved, and draws its bonds in one batch.

A drag runs a command per mouse event, and every one of them rebuilt
the scene and reset the Sites table.  On MFU-4l that was 100 ms a step
-- ten frames a second, and visibly sticky.  These tests hold the two
cheaper paths to the answers the expensive ones gave.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.commands.atoms import MoveSites  # noqa: E402
from xtal.core import bonding, p1, transforms  # noqa: E402
from xtal.io import FORMATS  # noqa: E402
from xtalapp.docks.sites import SiteTableModel  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402
from xtalapp.viewport import scene as scene_model  # noqa: E402
from xtalapp.viewport.builder import _bond_frames  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


# ----------------------------------------------------- the bond frames

def one_plane_at_a_time(graph, cell, orders):
    """The frames as they were: a neighbour walk and an SVD per bond."""
    out = np.zeros((len(graph.bonds), 3))
    matrix, cart = cell.lattice.matrix, cell.cart
    for k, bond in enumerate(graph.bonds):
        if orders[k] <= scene_model.SINGLE_MAX:
            continue
        image = np.asarray(bond.image, dtype=int)
        far = cart[bond.j] + image @ matrix - cart[bond.i]
        others = [cart[n] + t @ matrix - cart[bond.i]
                  for n, t in graph.neighbors_with_images(bond.i)
                  if not (n == bond.j and np.array_equal(t, image))]
        others += [far + cart[n] + t @ matrix - cart[bond.j]
                   for n, t in graph.neighbors_with_images(bond.j)
                   if not (n == bond.i and np.array_equal(t, -image))]
        if not others:
            continue
        others = np.array(others)
        _c, normal = transforms.best_fit_plane(
            np.vstack([np.zeros(3), far, others]))
        direction = np.cross(normal, far / np.linalg.norm(far))
        direction /= np.linalg.norm(direction)
        if direction @ (others.mean(axis=0) - far / 2.0) < 0:
            direction = -direction
        out[k] = direction
    return out


@pytest.mark.parametrize("name", ["MFU4l", "MOF-5", "HKUST1"])
def test_bond_frames_from_batched_planes_match_one_svd_per_bond(name):
    """Every double and aromatic bond's second tube lies where it did,
    on the same side: pointed into the ring, not out of it."""
    structure = FORMATS.read(f"resources/samples/{name}.cif")
    graph, cell = bonding.graph(structure), p1.expand(structure)
    orders = bonding.orders(structure)
    batched = _bond_frames(graph, cell, orders)
    expected = one_plane_at_a_time(graph, cell, orders)
    framed = np.linalg.norm(expected, axis=1) > 0
    assert framed.sum() > 30
    assert np.allclose(batched[framed], expected[framed], atol=1e-9)


# ----------------------------------------------------- the Sites table

def watched(model):
    resets, changed = [], []
    model.modelReset.connect(lambda: resets.append(True))
    model.dataChanged.connect(
        lambda a, b, *_r: changed.append((a.row(), b.row(),
                                          a.column(), b.column())))
    return resets, changed


def test_a_move_repaints_the_moved_row_without_resetting_the_table(
        qapp, quartz):
    """A reset re-lays-out the table and drops its selection, once per
    mouse event of a drag.  A move is news only to the rows it moved."""
    document = Document(quartz)
    model = SiteTableModel(document)
    resets, changed = watched(model)
    document.run(MoveSites({1: np.array([0.01, 0.0, 0.0])}))
    model.moved()
    assert not resets
    assert changed == [(1, 1, 2, 8)]
    assert model.data(model.index(1, 2)) == \
        f"{document.structure.sites[1].frac[0]:.5f}"


def test_a_move_that_moved_nothing_repaints_nothing(qapp, quartz):
    model = SiteTableModel(Document(quartz))
    resets, changed = watched(model)
    model.moved()
    assert not resets and not changed


def test_a_drag_in_the_window_leaves_the_sites_table_its_shape(
        qtbot, tmp_path, quartz):
    """The window tells the dock a drag is positions only; the dock
    must then not reset, or the selection the drag is of goes."""
    settings = AppSettings("CrystalBuilderTest", f"Drag{tmp_path.name}")
    settings.clear_window()
    window = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(window)
    document = Document(quartz)
    window.add_document(document)
    document.select([0])
    resets, changed = watched(window.sites_dock.model)
    document.drag_selection(np.array([0.05, 0.0, 0.0]))
    assert not resets
    assert changed
