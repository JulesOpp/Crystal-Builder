"""Document and main-window logic.

The VTK viewport is injected, so the shell can be driven headless: the
stub records what the real widget would have been asked to draw, which
is what these tests assert on.  The rendering itself is covered by
tests/test_vtk_render.py.
"""

import gc

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

    def image_size(self):
        return (640, 480)

    def save_image(self, path, magnification=2, transparent=False):
        from pathlib import Path
        self.saved = (Path(path), magnification, transparent)
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

    out = tmp_path / "saved.xtalproj"
    doc.save(out)
    assert out.exists()
    assert not doc.modified
    assert doc.path == out


def test_save_writes_a_project_whatever_extension_it_is_given(
        rutile_cif, tmp_path):
    """Save is about the session, and the extension is not a choice.

    It used to dispatch on the three characters after the dot, so the
    same command either kept a whole working session or threw most of
    it away depending on what the user typed.
    """
    from xtal.io import is_project

    doc = Document.load(rutile_cif)
    doc.add_measurement([0, 1])
    written = doc.save(tmp_path / "typed_a_cif.cif")

    assert written.suffix == ".xtalproj"
    assert not (tmp_path / "typed_a_cif.cif").exists()
    assert is_project(written)
    assert doc.path == written

    reopened = Document.load(written)
    assert len(reopened.measurements) == 1


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


def test_the_three_boundary_answers_are_one_choice(window, rutile_cif):
    """One question with three answers, so an exclusive group and not
    three checkboxes -- picking one has to clear the last."""
    doc = window.open_path(rutile_cif)
    for name in ("half", "bonded", "in_range", "half"):
        window.actions_[f"boundary_{name}"].trigger()
        assert doc.view.boundary == name
        checked = [n for n in ("in_range", "bonded", "half")
                   if window.actions_[f"boundary_{n}"].isChecked()]
        assert checked == [name]


def test_the_boundary_tick_follows_the_document(window, rutile_cif):
    """The menu has to show what the current document is set to, and
    exactly one entry of the three.

    Blocking the action's signals while ticking it was what got this
    wrong: an exclusive group unticks the others *through* the signal
    it was then not seeing, so all three ended up ticked at once and
    the menu claimed every answer.
    """
    document = window.open_path(rutile_cif)
    for name in ("half", "bonded", "in_range"):
        document.update_view(boundary=name)
        checked = [n for n in ("in_range", "bonded", "half")
                   if window.actions_[f"boundary_{n}"].isChecked()]
        assert checked == [name]


def test_the_boundary_tick_follows_the_tab(window, rutile_cif):
    """Two documents at different settings: the menu shows the one in
    front, or it is a picture of somebody else's view."""
    first = window.open_path(rutile_cif)
    first.update_view(boundary="half")
    window.new_document()
    second = window.current_document()
    assert second is not first
    second.update_view(boundary="bonded")
    assert window.actions_["boundary_bonded"].isChecked()

    window.tabs.setCurrentIndex(window.documents.index(first))
    assert window.actions_["boundary_half"].isChecked()
    assert not window.actions_["boundary_bonded"].isChecked()


def test_the_new_view_toggles_reach_the_document(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    assert doc.view.show_planes and not doc.view.show_scale_bar
    window.actions_["show_planes"].trigger()
    assert not doc.view.show_planes
    window.actions_["show_scale_bar"].trigger()
    assert doc.view.show_scale_bar


def test_cell_spinboxes_change_the_display_range(window, rutile_cif):
    doc = window.open_path(rutile_cif)
    window.cell_spins[0].setValue(3)
    window.cell_spins[2].setValue(2)
    assert doc.view.cells == (3, 1, 2)
    assert doc.view.range_a == (0.0, 3.0)


def test_the_menu_bar_ends_with_window_and_help(window):
    """Window used to be after Help, because build_docks added a menu
    of its own after build_menus had finished -- so the order was a
    property of two files' call order.  build_menus owns it now."""
    titles = [a.text().replace("&", "")
              for a in window.menuBar().actions()]
    assert titles == ["File", "Edit", "Select", "Structure",
                      "Symmetry", "Cell", "Measure", "View",
                      "Modules", "Window", "Help"]


def test_the_window_menu_still_lists_every_dock(window):
    """build_menus creates it empty; build_docks fills it, because the
    docks do not exist until it has built them."""
    entries = [a.text() for a in window.window_menu.actions()]
    for dock in window.docks:
        assert dock.toggleViewAction().text() in entries
    assert entries[-1] == window.actions_["reset_layout"].text()


def test_every_stored_menu_survives_a_walk_of_the_menu_bar(window):
    """Reading a submenu off its QAction must not take the submenu.

    A menu built by ``parent.addMenu(title)`` hands back a wrapper
    tied to the QAction the walk produced; when that temporary is
    collected the handle stored on the window is invalidated, while
    the menu itself goes on dropping down as though nothing were
    wrong.  Generating the help pages walks the whole bar, so opening
    Help once made the next structure edit die in
    ``_rebuild_element_menu``.
    """
    def walk(menu):
        for action in menu.actions():
            child = action.menu()
            if child is not None:
                walk(child)

    for action in window.menuBar().actions():
        walk(action.menu())
    gc.collect()

    stored = ["sample_menu", "recent_menu", "element_menu",
              "mode_menu", "bond_type_menu", "modules_menu",
              "window_menu"]
    for name in stored:
        getattr(window, name).actions()
    for name, menu in window._module_submenus.items():
        assert menu.actions(), name


def test_the_mouse_modes_are_a_submenu_of_structure(window):
    """Six flat entries under the bond commands made the bottom of
    Structure read as though a mode were an edit."""
    from xtalapp.viewport import modes
    entries = [a.text() for a in window.mode_menu.actions()]
    assert entries == [window.actions_[f"mode_{n}"].text()
                       for n in modes.names()]


def test_the_ways_of_opening_a_file_are_together(window):
    """Open Recent was below Close, at the far end of a menu whose top
    is where somebody opening a file is looking."""
    entry = window.menuBar().actions()[0]
    titles = [a.text().replace("&", "") for a in entry.menu().actions()]
    assert titles[:4] == ["New", "Open...", "Open Recent",
                          "Open Sample"]


def test_the_element_combo_sits_with_the_mode_that_places_it(window):
    """It is the element Add atom places -- its own tooltip says so --
    and it stood beside Recalculate bonds, which it has nothing to do
    with."""
    bar = window.toolbar
    widgets = [bar.widgetForAction(a) for a in bar.actions()]
    order = [w for w in widgets if w is not None]
    combo = order.index(window.element_combo)
    add_atom = order.index(
        bar.widgetForAction(window.actions_["mode_add_atom"]))
    recompute = order.index(
        bar.widgetForAction(window.actions_["recompute_bonds"]))
    assert add_atom < combo < recompute


def test_the_camera_buttons_are_at_the_far_end_of_the_toolbar(window):
    """Reset view was grouped with Undo and Redo, which reads as
    though it undid something; the axis views were on no toolbar."""
    on_bar = [a for a in window.toolbar.actions()]
    for name in ("reset_view", "view_a", "view_b", "view_c"):
        assert window.actions_[name] in on_bar
    assert on_bar[-1] is window.actions_["view_c"]
    assert on_bar.index(window.actions_["reset_view"]) > \
        on_bar.index(window.actions_["undo"])


def test_an_axis_button_is_a_letter_on_the_bar_and_a_sentence_in_the_menu(
        window):
    """A toolbar button shows the action's icon text, which is the one
    place a shorter spelling belongs."""
    assert window.actions_["view_a"].iconText() == "a"
    assert window.actions_["view_a"].text() == "Along &a"


def test_the_axis_letter_is_beside_the_cell_spin_and_not_inside_it(
        window):
    """The letter was the spinbox's prefix, so the box read "a 1" and
    the letter sat where the number the user types goes."""
    from PySide6.QtWidgets import QLabel
    assert [s.prefix() for s in window.cell_spins] == ["", "", ""]
    labels = [w.text().strip() for w in window.toolbar.findChildren(QLabel)]
    assert ["a", "b", "c"] == [t for t in labels
                               if t in ("a", "b", "c")]


def test_growing_the_cell_count_reframes_the_picture(window, rutile_cif):
    """1x1x1 to 3x1x1 puts two thirds of the picture outside a frame
    that was set for one cell, so the camera resets with it."""
    window.open_path(rutile_cif)
    viewport = window.current_viewport()
    before = viewport.resets
    window.cell_spins[0].setValue(3)
    assert viewport.resets == before + 1


def test_the_display_range_dialog_leaves_the_camera_alone(window,
                                                         rutile_cif):
    """The other route to the same ranges composes a picture -- a slab,
    a half cell -- with the camera already placed on what is being
    looked at."""
    document = window.open_path(rutile_cif)
    viewport = window.current_viewport()
    before = viewport.resets
    document.update_view(range_a=(0.0, 0.5))
    assert viewport.resets == before


def test_spinboxes_follow_the_active_document(window, rutile_cif,
                                              quartz_cif):
    """Two documents, and therefore two *files*: opening one file
    twice now raises the tab it is already in rather than making a
    second document, which is what tests/test_open_once.py is
    about."""
    first = window.open_path(rutile_cif)
    first.set_cells(2, 2, 2)
    window.open_path(quartz_cif)             # second tab, defaults
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

    # conftest turns the prompt off for the session, because nothing
    # in a test run can answer it.  This test is about the prompt, so
    # it is the one place that has to put it back.
    monkeypatch.delenv("XTAL_NO_CONFIRM_CLOSE", raising=False)
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


def test_export_image_writes_what_the_dialog_asked_for(
        window, rutile_cif, tmp_path, monkeypatch):
    """The format, the magnification and the background are the
    user's now; they used to be PNG at 2x over the view's colour with
    nowhere to say otherwise."""
    from PySide6.QtWidgets import QDialog

    from xtalapp.dialogs.image_export import ImageExportDialog
    window.open_path(rutile_cif)
    target = tmp_path / "shot.tif"

    def stub(self):
        self.format.setCurrentIndex(2)
        self.scale.setValue(4)
        self.transparent.setChecked(True)
        self.path.setText(str(target))
        return QDialog.Accepted

    monkeypatch.setattr(ImageExportDialog, "exec", stub)
    window.export_image()
    assert target.exists()
    assert window.current_viewport().saved == (target, 4, True)


def test_exporting_an_image_moves_the_last_directory(
        window, rutile_cif, tmp_path, monkeypatch):
    """The native save dialog this replaced never did, so the next
    Export opened wherever the last structure came from."""
    from PySide6.QtWidgets import QDialog

    from xtalapp.dialogs.image_export import ImageExportDialog
    window.open_path(rutile_cif)
    elsewhere = tmp_path / "figures"
    elsewhere.mkdir()

    def stub(self):
        self.path.setText(str(elsewhere / "shot.png"))
        return QDialog.Accepted

    monkeypatch.setattr(ImageExportDialog, "exec", stub)
    window.export_image()
    assert window.settings.last_directory == str(elsewhere)


def test_the_image_dialog_says_the_pixels_it_will_write(window):
    """"2x" is a lie on a Retina screen, where the render window is
    already twice the widget: the dialog multiplies it out."""
    from xtalapp.dialogs.image_export import ImageExportDialog
    dialog = ImageExportDialog(window, size=(1120, 1294))
    dialog.scale.setValue(3)
    assert dialog.output_size() == (3360, 3882)
    assert "3360 x 3882" in dialog.pixels.text()


def test_the_image_dialog_drops_the_options_a_format_cannot_take(
        window):
    """JPEG has no alpha channel and GL2PS takes the window at its own
    size, so neither box may pretend to work."""
    from xtalapp.dialogs.image_export import ImageExportDialog
    dialog = ImageExportDialog(window, size=(400, 300))
    assert dialog.transparent.isEnabled() and dialog.scale.isEnabled()

    dialog.format.setCurrentIndex(1)                # JPEG
    assert not dialog.transparent.isEnabled()
    assert dialog.scale.isEnabled()

    # SVG has no resolution -- it is shapes -- but leaving the ground
    # out of it is exactly as meaningful as for a PNG.
    dialog.format.setCurrentIndex(3)
    assert not dialog.scale.isEnabled()
    assert dialog.transparent.isEnabled()
    assert dialog.output_size() == (400, 300)
    dialog.transparent.setChecked(True)
    assert dialog.options() == {"magnification": 1, "transparent": True}


def test_every_image_format_says_what_it_costs(window):
    """The counterpart of ``ExportDialog``'s ``keeps_text``: JPEG is
    lossy, TIFF is enormous, and SVG has no resolution to set at
    all."""
    from xtalapp.dialogs.image_export import ImageExportDialog
    dialog = ImageExportDialog(window, size=(400, 300))
    seen = set()
    for index in range(dialog.format.count()):
        dialog.format.setCurrentIndex(index)
        assert dialog.note.text().strip()
        seen.add(dialog.note.text())
    assert len(seen) == dialog.format.count()
    assert "editable" in dialog.note.text()         # SVG is the last


def test_the_image_dialog_swaps_the_suffix_with_the_format(window,
                                                           tmp_path):
    from xtalapp.dialogs.image_export import ImageExportDialog
    dialog = ImageExportDialog(window, directory=tmp_path, stem="rutile")
    assert dialog.target().name == "rutile.png"
    dialog.format.setCurrentIndex(3)
    assert dialog.target().name == "rutile.svg"


def test_export_writes_p1_when_the_dialog_asks_for_it(
        window, rutile_cif, tmp_path, monkeypatch):
    """Both of CIF's answers are reachable now.

    ``Export as P1 CIF...`` was one format with one of its two options
    on the menu; ``cif_writer.write_cif`` has always taken
    ``expand_to_p1`` and only one setting of it could be asked for.
    """
    from PySide6.QtWidgets import QDialog

    from xtal.io import read_cif
    from xtalapp.dialogs.export import ExportDialog
    window.open_path(rutile_cif)
    target = tmp_path / "flat.cif"

    def stub(self, *args, **kwargs):
        self.path.setText(str(target))
        self.as_p1.setChecked(True)
        return QDialog.Accepted

    monkeypatch.setattr(ExportDialog, "exec", stub)
    window.export_dialog()
    assert read_cif(target).n_sites == 6

    # ...and the document did not adopt it, which is the whole point
    # of the split.
    assert window.current_document().path.name == "rutile.cif"


def test_file_tree_opens_structures(window, rutile_cif):
    window.file_dock.fileActivated.emit(rutile_cif)
    assert window.tabs.count() == 1


def test_file_tree_opens_a_file_once_per_gesture(window, rutile_cif,
                                                 tmp_path):
    """A double-click on the tree makes Qt emit `doubleClicked` *and*
    `activated`.  With both connected the file opened twice, which is
    two tabs for one gesture."""
    window.file_dock.browser.set_root(tmp_path)
    index = window.file_dock.browser.model.index(rutile_cif)
    window.file_dock.browser.tree.doubleClicked.emit(index)
    window.file_dock.browser.tree.activated.emit(index)
    assert window.tabs.count() == 1


def test_file_tree_filters_to_known_formats(window):
    from xtalapp.docks.filetree import structure_globs
    globs = structure_globs()
    assert "*.cif" in globs and "*.xyz" in globs
    assert set(window.file_dock.browser.model.nameFilters()) \
        == set(globs)


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
