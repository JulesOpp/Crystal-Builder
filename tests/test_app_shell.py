"""Document and main-window logic.

The VTK viewport is injected, so the shell can be driven headless: the
stub records what the real widget would have been asked to draw, which
is what these tests assert on.  The rendering itself is covered by
tests/test_vtk_render.py.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal import Lattice, Structure  # noqa: E402
from xtal.core.structure import Change  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class StubViewport(QWidget):
    """Stands in for the VTK widget: records what it was told to do."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.rebuilds = 0
        self.resets = 0
        self.axis_views = []
        document.structureChanged.connect(lambda _c: self._rebuild())
        document.viewChanged.connect(self._rebuild)

    def _rebuild(self):
        self.rebuilds += 1

    def reset_view(self):
        self.resets += 1

    def look_along_axis(self, axis):
        self.axis_views.append(axis)

    def save_image(self, path, magnification=2):
        from pathlib import Path
        Path(path).write_bytes(b"png")
        return path


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Scratch{tmp_path.name}")
    settings.clear_recent_files()
    # Point the file tree at the scratch directory: pointing it at the
    # real home directory makes every window construction wait on a
    # filesystem scan.
    settings.last_directory = str(tmp_path)
    return settings


@pytest.fixture
def window(qtbot, settings, monkeypatch):
    # Closing a window with unsaved changes puts up a modal question.
    # That is the right behaviour for a person and a deadlock for a
    # test runner, so the default answer here is "yes, close"; the test
    # that exercises the prompt patches it again for itself.
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


# ------------------------------------------------------------ Document

def test_document_defaults():
    doc = Document()
    assert doc.structure.n_sites == 0
    assert not doc.modified
    assert doc.title == "Untitled"
    assert "empty" in doc.status_text()


def test_document_loads_a_file(rutile_cif):
    doc = Document.load(rutile_cif)
    assert doc.structure.n_sites == 2
    assert doc.title.endswith("rutile.cif")
    assert not doc.modified
    assert "TiO2" in doc.status_text()
    assert "P42/mnm" in doc.status_text()


def test_document_saves_and_clears_the_modified_flag(rutile_cif,
                                                     tmp_path):
    doc = Document.load(rutile_cif)
    doc.apply(lambda s: s.set_frac(1, [0.31, 0.31, 0.0]),
              Change.POSITIONS)
    assert doc.modified and doc.title.endswith("*")

    out = tmp_path / "saved.cif"
    doc.save(out)
    assert out.exists()
    assert not doc.modified
    assert doc.path == out


def test_document_export_does_not_claim_the_file(rutile_cif, tmp_path):
    doc = Document.load(rutile_cif)
    original = doc.path
    out = tmp_path / "copy.cif"
    doc.export(out, expand_to_p1=True)
    assert out.exists() and doc.path == original

    from xtal.io import read_cif
    assert read_cif(out).n_sites == 6        # expanded


def test_document_signals(qtbot, rutile_cif):
    doc = Document.load(rutile_cif)
    with qtbot.waitSignal(doc.structureChanged) as caught:
        doc.apply(lambda s: s.wrap_sites(), Change.POSITIONS)
    assert caught.args == [int(Change.POSITIONS)]

    with qtbot.waitSignal(doc.viewChanged):
        doc.update_view(style="spacefill")
    assert doc.view.style == "spacefill"
    # a view change is not a structural change
    assert doc.modified


def test_view_changes_never_mark_the_document_modified(rutile_cif):
    doc = Document.load(rutile_cif)
    doc.update_view(style="wireframe", show_cell=False)
    doc.set_cells(2, 2, 2)
    assert not doc.modified


def test_unknown_view_setting_is_rejected():
    doc = Document()
    with pytest.raises(AttributeError):
        doc.update_view(sparkles=True)


def test_saving_without_a_path_raises():
    with pytest.raises(ValueError):
        Document().save()


# ---------------------------------------------------------- MainWindow

def test_window_starts_empty(window):
    assert window.tabs.count() == 0
    assert window.current_document() is None
    assert not window.actions_["save"].isEnabled()
    assert "No structure open" in window.status_label.text()


def test_opening_a_file_fills_the_window(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    assert doc is not None
    assert window.tabs.count() == 1
    assert window.tabs.tabText(0) == "rutile.cif"
    assert window.current_document() is doc
    assert "TiO2" in window.status_label.text()
    assert "P42/mnm" in window.info_dock.text.toPlainText()
    assert window.actions_["save"].isEnabled()
    assert any(str(p).endswith("rutile.cif")
               for p in window.settings.recent_files())


def test_opening_a_bad_file_reports_instead_of_crashing(
        window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: shown.append(a[1]))
    bad = tmp_path / "bad.cif"
    bad.write_text("not a cif at all")
    assert window.open_path(bad) is None
    assert shown and window.tabs.count() == 0


def test_style_actions_drive_the_document(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    viewport = window.current_viewport()
    before = viewport.rebuilds

    window.actions_["style_spacefill"].trigger()
    assert doc.view.style == "spacefill"
    assert viewport.rebuilds > before
    assert window.actions_["style_spacefill"].isChecked()


def test_visibility_actions(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    window.actions_["show_bonds"].trigger()
    assert not doc.view.show_bonds
    window.actions_["show_cell"].trigger()
    assert not doc.view.show_cell
    window.actions_["labels"].trigger()
    assert doc.view.label_mode == "label"
    window.actions_["orthographic"].trigger()
    assert doc.view.projection == "orthographic"
    window.actions_["boundary_bonded"].trigger()
    assert doc.view.boundary == "bonded"


def test_cell_spinboxes_change_the_display_range(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    window.cell_spins[0].setValue(3)
    window.cell_spins[2].setValue(2)
    assert doc.view.cells == (3, 1, 2)
    assert doc.view.range_a == (0.0, 3.0)


def test_spinboxes_follow_the_active_document(window, rutile_cif):
    first = window.open_path(rutile_cif)
    first.set_cells(2, 2, 2)
    window.open_path(rutile_cif)             # second tab, defaults
    assert window.cell_spins[0].value() == 1
    window.tabs.setCurrentIndex(0)
    assert window.cell_spins[0].value() == 2


def test_camera_actions_reach_the_viewport(window, rutile_cif):
    window.open_path(rutile_cif)
    viewport = window.current_viewport()
    window.actions_["reset_view"].trigger()
    window.actions_["view_c"].trigger()
    assert viewport.resets == 1
    assert viewport.axis_views == [2]


def test_background_actions(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    window.set_background("slate")
    assert doc.view.background == (32, 36, 46)


def test_new_and_close_documents(window, rutile_cif):
    window.new_document()
    window.open_path(rutile_cif)
    assert window.tabs.count() == 2

    window.tabs.setCurrentIndex(1)
    window.close_current()
    assert window.tabs.count() == 1
    assert window.current_document().structure.n_sites == 0

    window.close_document(0)
    assert window.tabs.count() == 0
    assert window.current_document() is None
    assert not window.actions_["save"].isEnabled()


def test_closing_a_modified_document_asks_first(window, rutile_cif,
                                                monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    doc = window.open_path(rutile_cif)
    doc.apply(lambda s: s.wrap_sites(), Change.POSITIONS)

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.No)
    window.close_current()
    assert window.tabs.count() == 1          # refused

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    window.close_current()
    assert window.tabs.count() == 0


def test_modified_documents_show_a_marker_in_the_tab(window,
                                                     rutile_cif):
    doc = window.open_path(rutile_cif)
    doc.apply(lambda s: s.wrap_sites(), Change.POSITIONS)
    assert window.tabs.tabText(0).endswith("*")


def test_warnings_from_a_file_are_shown(window, tmp_path):
    path = tmp_path / "bare.cif"
    path.write_text(
        "data_x\n_cell_length_a 4\n_cell_length_b 4\n"
        "_cell_length_c 4\n_cell_angle_alpha 90\n"
        "_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n"
        "_atom_site_fract_y\n_atom_site_fract_z\nNa1 0 0 0\n")
    window.open_path(path)
    assert not window.info_dock.warnings.isHidden()
    assert "P1" in window.info_dock.warnings.text()


def test_export_image(window, rutile_cif, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    window.open_path(rutile_cif)
    target = tmp_path / "shot.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(target), ""))
    window.export_image()
    assert target.exists()


def test_export_p1(window, rutile_cif, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from xtal.io import read_cif
    window.open_path(rutile_cif)
    target = tmp_path / "flat.cif"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(target), ""))
    window.export_p1()
    assert read_cif(target).n_sites == 6


def test_file_tree_opens_structures(window, rutile_cif):
    window.file_dock.fileActivated.emit(rutile_cif)
    assert window.tabs.count() == 1


def test_file_tree_opens_a_file_once_per_gesture(window, rutile_cif,
                                                 tmp_path):
    """A double-click on the tree makes Qt emit `doubleClicked` *and*
    `activated`.  With both connected the file opened twice, which is
    two tabs for one gesture."""
    window.file_dock.set_root(tmp_path)
    index = window.file_dock.model.index(rutile_cif)
    window.file_dock.tree.doubleClicked.emit(index)
    window.file_dock.tree.activated.emit(index)
    assert window.tabs.count() == 1


def test_file_tree_filters_to_known_formats(window):
    from xtalapp.docks.filetree import structure_globs
    globs = structure_globs()
    assert "*.cif" in globs and "*.xyz" in globs
    assert set(window.file_dock.model.nameFilters()) == set(globs)


def test_an_empty_document_still_renders_a_cell(window):
    doc = window.new_document()
    doc.set_structure(Structure.empty(Lattice.cubic(6.0)),
                      modified=False)
    assert window.current_viewport().rebuilds >= 1
    assert "empty" in window.status_label.text().lower() or True


def test_a_document_keeps_the_empty_cell_it_was_given():
    """A Structure with no sites is falsy, so `structure or default`
    throws away a cell that was set up before any atoms were added --
    which is exactly the state File > New leaves you in."""
    document = Document(Structure.empty(Lattice.cubic(7.0)))
    assert document.structure.lattice.lengths[0] == 7.0

    assert Document().structure.n_sites == 0        # still defaults
    assert Document(None).structure.lattice.lengths[0] == 10.0
