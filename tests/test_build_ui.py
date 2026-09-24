"""The molecule builder on screen: one dialog, two entries.

The build itself is headless and tested in
:mod:`tests.test_build_molecule`.  What is here is the shell: that the
Structure entry is greyed with a reason rather than missing, that the
dialog says what the button will do before it is pressed, and that the
same class serves the entry that opens a tab and the entry that pastes.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal import install  # noqa: E402
from xtal.build import installed  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtal.modules.build import BUILD, INSERT  # noqa: E402
from xtalapp.dialogs import module_dialog, sketch  # noqa: E402
from xtalapp.dialogs.build_molecule import (  # noqa: E402
    BuildMoleculeDialog,
    _Sketch,
)
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

needs_rdkit = pytest.mark.skipif(
    not installed(),
    reason="RDKit is not installed; pip install "
           "'crystal-builder[build]'")

needs_rdeditor = pytest.mark.skipif(
    not (installed() and sketch.installed()),
    reason="rdeditor is not installed; pip install "
           "'crystal-builder[sketch]'")


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest",
                           f"Build{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    return settings


@pytest.fixture
def window(qtbot, settings):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


def opened(window, tmp_path, structure, name="crystal"):
    path = tmp_path / f"{name}.cif"
    write_cif(structure, path)
    return window.open_path(path)


def typed(dialog, qtbot, text):
    """Type a string and wait for the build the keystrokes start."""
    dialog.form.widgets["smiles"].setText(text)
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)


def drawn(dialog, qtbot, symbol):
    """Put one atom on the canvas, the way a click on it would.

    Through the editor's own API rather than a synthetic mouse event:
    what is under test is the cycle from the canvas to the box and
    back, and rdeditor's hit-testing is rdeditor's business.
    """
    from rdkit.Geometry.rdGeometry import Point2D

    dialog.sketch.view.setChemEntity(symbol)
    dialog.sketch.view.add_canvas_atom(Point2D(0.0, 0.0))
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)


# --------------------------------------------------- the shell entry

def test_the_insert_entry_needs_a_structure_to_insert_into(window):
    assert not window.actions_["insert_molecule"].isEnabled()


@needs_rdkit
def test_the_insert_entry_is_on_once_something_is_open(
        window, tmp_path, rutile):
    opened(window, tmp_path, rutile)
    assert window.actions_["insert_molecule"].isEnabled()


def test_without_rdkit_the_entry_is_greyed_and_says_what_to_install(
        window, tmp_path, rutile, monkeypatch):
    """Greyed with a sentence, not absent.  A menu entry that is
    simply not there leaves somebody looking for a feature they have
    read about with nothing to find."""
    import xtalapp.shell_state as shell
    monkeypatch.setattr(shell, "rdkit_installed", lambda: False)
    opened(window, tmp_path, rutile)

    action = window.actions_["insert_molecule"]
    assert not action.isEnabled()
    assert install.command("build") in action.toolTip()


def test_both_dialog_names_reach_the_one_class():
    """Two entries, one dialog: they differ in what the footer says
    and in whether connection points are on offer, and that is read
    off the action's name."""
    assert module_dialog("build-molecule") is BuildMoleculeDialog
    assert module_dialog("build-insert") is BuildMoleculeDialog


# ------------------------------------------------------- the dialog

@needs_rdkit
def test_the_footer_says_how_far_the_symmetry_will_multiply_it(
        window, qtbot, tmp_path, rutile):
    """Eleven atoms into Fm-3m is 2112 atoms and a window that stops
    responding.  PasteFragment.describe has always said so; the point
    of the footer is that it says so before the click."""
    opened(window, tmp_path, rutile)
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert "multiply" in dialog.footer.text()
    assert rutile.space_group.short_name in dialog.footer.text()
    assert dialog.ok_button.isEnabled()


@needs_rdkit
def test_the_footer_of_the_new_document_entry_talks_about_a_tab(
        window, qtbot, tmp_path, rutile):
    """The same dialog, the other action, and no paste in sight --
    what it builds is a document of its own whatever is in front."""
    opened(window, tmp_path, rutile)
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert "tab of its own" in dialog.footer.text()
    assert "multiply" not in dialog.footer.text()


@needs_rdkit
def test_a_connection_point_is_refused_by_the_entry_that_pastes(
        window, qtbot):
    """A star in the box that drops a molecule into a cell meant
    something, and a benzene with a silent extra hydrogen is a worse
    answer than being told this box does not do connection points."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]c1ccccc1")

    assert dialog.molecule is None
    assert not dialog.ok_button.isEnabled()
    assert "connection point" in dialog.footer.text()


@needs_rdkit
def test_a_connection_point_is_kept_by_the_entry_that_opens_a_tab(
        window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]c1ccccc1[*:2]")

    assert dialog.molecule is not None
    assert dialog.molecule.n_connections == 2
    assert "2 connection point(s)" in dialog.footer.text()


@needs_rdkit
def test_a_string_that_is_not_a_molecule_says_so_and_stops_the_button(
        window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc")

    assert dialog.molecule is None
    assert not dialog.ok_button.isEnabled()
    assert "RDKit" in dialog.footer.text()


@needs_rdkit
def test_one_build_for_a_burst_of_keystrokes(window, qtbot):
    """Typing a twenty-character SMILES must not be twenty embeds.
    The timer is restarted by each keystroke, so only the last one
    builds anything."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    builds = []
    dialog._quiet.timeout.connect(lambda: builds.append(1))
    for text in ("C", "CC", "CCO"):
        dialog.form.widgets["smiles"].setText(text)
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)

    assert len(builds) == 1
    assert dialog.molecule.formula == "C2H6O"


@needs_rdkit
def test_the_picture_follows_the_string(window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert dialog.sketch.smiles() == "c1ccccc1"
    assert dialog.sketch.view.renderer().isValid()
    assert dialog.sketch.view.isVisibleTo(dialog.sketch)


@needs_rdkit
def test_an_unfinished_string_leaves_the_last_picture_up(window,
                                                         qtbot):
    """Every ring is unreadable while it is being typed, and blanking
    the drawing on the way through one makes the panel flicker for
    every molecule that has a ring in it."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")
    drawn = dialog.sketch.view.renderer().defaultSize()

    typed(dialog, qtbot, "c1ccccc1(")
    assert dialog.sketch.view.renderer().defaultSize() == drawn
    assert dialog.sketch.view.renderer().isValid()
    assert dialog.sketch.view.isVisibleTo(dialog.sketch)


# -------------------------------------------------- the 2D editor

@needs_rdeditor
def test_the_editor_replaces_the_picture_when_rdeditor_is_installed(
        window, qtbot):
    """The same two members either way -- set_smiles in,
    smilesChanged out -- which is why the dialog around it did not
    have to change to gain an editor."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert isinstance(dialog.sketch, sketch.SketchEditor)
    assert dialog.sketch.smiles() == "c1ccccc1"
    assert dialog.sketch.view.mol.GetNumAtoms() == 6


@needs_rdkit
def test_without_rdeditor_the_picture_is_still_there_and_says_what_to_install(  # noqa: E501
        window, qtbot, monkeypatch):
    """The fine greying axis.  No RDKit turns the menu entry off; RDKit
    without rdeditor is not an error at all, so the dialog opens with
    the depiction that always worked and names the extra underneath
    it rather than leaving somebody to wonder why it cannot be drawn
    on."""
    monkeypatch.setattr(sketch, "installed", lambda: False)
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert isinstance(dialog.sketch, _Sketch)
    assert dialog.sketch.view.renderer().isValid()
    assert install.command("sketch") in dialog.sketch.hint.text()
    assert dialog.sketch.hint.isVisibleTo(dialog.sketch)


@needs_rdeditor
def test_closing_the_dialog_twice_does_not_take_the_editor_with_it(
        window, qtbot):
    """rdeditor sets WA_DeleteOnClose on the canvas, which is right
    for the standalone window it ships in and wrong for a dialog that
    is opened, closed and opened again -- the second open would be
    holding a freed C++ object."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.close()
    dialog.show()
    dialog.close()

    assert not dialog.sketch.view.testAttribute(Qt.WA_DeleteOnClose)
    typed(dialog, qtbot, "CCO")
    assert dialog.sketch.view.mol.GetNumAtoms() == 3


@needs_rdeditor
def test_drawing_an_atom_puts_the_smiles_in_the_box(window, qtbot):
    """The direction that did not exist while the picture was
    read-only: what is drawn is what the box says, so the button
    below builds what is on screen."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    drawn(dialog, qtbot, "O")

    assert dialog.form.widgets["smiles"].text() == "O"
    assert dialog.molecule.formula == "H2O"


@needs_rdeditor
def test_typing_in_the_box_redraws_the_editor(window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "CCO")

    assert dialog.sketch.view.mol.GetNumAtoms() == 3


@needs_rdeditor
def test_the_same_molecule_typed_back_does_not_relayout_the_drawing(
        window, qtbot):
    """The two ends of the cycle disagree about spelling constantly --
    a ring template comes back kekulized where the box says
    c1ccccc1 -- so the guard is on the canonical SMILES and not on
    the string.  Setting the mol again re-lays the depiction out
    under the cursor, which is the failure being avoided."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")
    before = dialog.sketch.view.mol

    typed(dialog, qtbot, "C1=CC=CC=C1")

    assert dialog.sketch.view.mol is before
    assert dialog.form.widgets["smiles"].text() == "C1=CC=CC=C1"


@needs_rdeditor
def test_the_toolbar_chooses_what_the_canvas_draws(window, qtbot):
    """Our own chrome and not theirs: MolEditWidget has none, and the
    toolbar rdEditor puts above it lives on a MainWindow that is not
    coming with the widget."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    tools = dialog.sketch.tools
    tools.check("O")
    drawn(dialog, qtbot, "O")
    tools.check("Benzene")
    dialog.sketch.view.add_ring_to_atom(
        dialog.sketch.view.mol.GetAtomWithIdx(0))
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)

    assert tools.button("Benzene").isChecked()
    assert not tools.button("O").isChecked()
    assert dialog.sketch.view.mol.GetNumAtoms() == 6


@needs_rdeditor
def test_undo_takes_the_last_thing_drawn_back_out_of_the_box(
        window, qtbot):
    """Undo is the way back from a connection point as well: an X does
    not remember what it was, so Ctrl+Z is the whole of unmarking."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "CCO")
    drawn(dialog, qtbot, "N")
    assert dialog.form.widgets["smiles"].text() != "CCO"

    dialog.sketch.tools.button("Undo").click()
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)

    assert dialog.form.widgets["smiles"].text() == "CCO"


@needs_rdeditor
def test_the_paste_entry_offers_no_connection_point_tool(window,
                                                         qtbot):
    """That box refuses a starred string, so a tool that draws one
    would be a button whose only outcome is the footer turning red."""
    pastes = BuildMoleculeDialog(BUILD, INSERT, window)
    builds = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(pastes)
    qtbot.addWidget(builds)

    assert pastes.sketch.tools.button("X") is None
    assert builds.sketch.tools.button("X") is not None


@needs_rdeditor
def test_a_connection_point_drawn_comes_back_as_a_star(window, qtbot):
    """No special case anywhere below the toolbar: an atom of atomic
    number zero is a * in the box, and from_smiles already turns that
    into the X the block writer and every marker guard know about."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")
    dialog.sketch.tools.check("X")
    dialog.sketch.view.add_atom_to_atom(
        dialog.sketch.view.mol.GetAtomWithIdx(0))
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)

    assert "*" in dialog.form.widgets["smiles"].text()
    assert dialog.molecule.n_connections == 1
    assert "1 connection point(s)" in dialog.footer.text()


@needs_rdeditor
def test_a_dark_window_gets_a_dark_canvas(window, qtbot,
                                          monkeypatch):
    """RDKit draws on white whatever the application looks like, and
    on a dark theme that is the brightest thing on screen."""
    monkeypatch.setattr(sketch, "is_dark", lambda _palette: True)
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)

    assert dialog.sketch.view.darkmode


@needs_rdeditor
def test_the_canvas_stays_square_in_a_wide_dialog(window, qtbot):
    """rdeditor asks RDKit for a 300x300 drawing whatever shape its
    canvas is, and QSvgWidget stretches what it is given -- so in a
    canvas twice as wide as it is tall a benzene is a flattened
    hexagon."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    dialog.resize(1200, 600)
    dialog.show()
    qtbot.waitExposed(dialog)

    view = dialog.sketch.view
    assert view.width() == view.height()
    assert view.width() > 200
    assert view.parent().width() > view.width()


@needs_rdkit
def test_the_picture_is_drawn_again_when_the_panel_changes_shape(
        window, qtbot, monkeypatch):
    """The depiction is made at the size of the widget, so one made
    before the layout had sized it is a picture stretched to fit."""
    monkeypatch.setattr(sketch, "installed", lambda: False)
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    typed(dialog, qtbot, "c1ccccc1")
    view = dialog.sketch.view
    qtbot.waitUntil(lambda: not dialog.sketch._redraw.isActive(),
                    timeout=5000)

    dialog.resize(1100, 700)
    qtbot.waitUntil(lambda: not dialog.sketch._redraw.isActive(),
                    timeout=5000)
    drawn = view.renderer().defaultSize()

    assert abs(drawn.width() - view.width()) <= 1
    assert abs(drawn.height() - view.height()) <= 1


@needs_rdkit
def test_what_the_dialog_hands_back_is_what_the_module_would_run(
        window, qtbot):
    """The values dict and nothing else, coerced by the action -- the
    same contract the generated form honours."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "CCO")
    values = dialog.values()

    assert values["smiles"] == "CCO"
    assert set(values) == {p.name for p in INSERT.params}
    assert isinstance(values["seed"], int)
    assert isinstance(values["optimise"], bool)


# ---------------------------------------------------- the whole path

@needs_rdkit
def test_inserting_puts_the_molecule_into_the_open_structure(
        window, qtbot, tmp_path, rutile, monkeypatch):
    document = opened(window, tmp_path, rutile)
    before = document.structure.n_sites
    monkeypatch.setattr(
        BuildMoleculeDialog, "ask",
        classmethod(lambda cls, *a, **k: {"smiles": "O", "name": "",
                                          "optimise": False,
                                          "seed": 1}))
    window.insert_molecule_dialog()

    assert document.structure.n_sites == before + 3
    assert document.can_undo


@needs_rdkit
def test_a_cancelled_insert_changes_nothing(window, tmp_path, rutile,
                                            monkeypatch):
    document = opened(window, tmp_path, rutile)
    monkeypatch.setattr(BuildMoleculeDialog, "ask",
                        classmethod(lambda cls, *a, **k: None))
    window.insert_molecule_dialog()

    assert not document.can_undo
    assert document.structure.n_sites == rutile.n_sites


# ------------------------------------------------- where it lands

class CameraViewport(StubViewport):
    """A stub with a camera, which the plain one deliberately has
    not: the shell has to work with both."""

    focal = (3.0, 4.0, 6.0)

    def focal_point(self):
        return np.array(self.focal, dtype=float)


@pytest.fixture
def camera_window(qtbot, settings):
    win = MainWindow(viewport_factory=CameraViewport,
                     settings=settings)
    qtbot.addWidget(win)
    return win


def test_a_viewport_with_no_camera_asks_for_the_middle_of_the_cell(
        window, tmp_path, rutile):
    """``None`` is not a failure: it is what Fragment.to_sites has
    always read as the centre of the cell, and the stub the widget
    tests inject has no camera to ask."""
    opened(window, tmp_path, rutile)
    assert window.paste_offset() is None


def test_the_focal_point_is_where_a_paste_is_offered(camera_window):
    camera_window.new_document()
    assert list(camera_window.paste_offset()) == [3.0, 4.0, 6.0]


@needs_rdkit
def test_a_molecule_lands_in_the_middle_of_the_picture(
        camera_window, monkeypatch):
    """A framework somebody has zoomed into puts the centre of the
    cell off screen, and a molecule that lands there has to be hunted
    for."""
    document = camera_window.new_document()
    monkeypatch.setattr(
        BuildMoleculeDialog, "ask",
        classmethod(lambda cls, *a, **k: {"smiles": "O", "name": "",
                                          "optimise": False,
                                          "seed": 1}))
    camera_window.insert_molecule_dialog()

    placed = document.structure.lattice.to_cart(
        [s.frac for s in document.structure.sites])
    assert placed.mean(axis=0) == pytest.approx(
        np.array(CameraViewport.focal), abs=1e-6)


@needs_rdkit
def test_with_no_camera_it_lands_in_the_middle_of_the_cell(
        window, monkeypatch):
    document = window.new_document()
    monkeypatch.setattr(
        BuildMoleculeDialog, "ask",
        classmethod(lambda cls, *a, **k: {"smiles": "O", "name": "",
                                          "optimise": False,
                                          "seed": 1}))
    window.insert_molecule_dialog()

    placed = np.array([s.frac for s in document.structure.sites])
    assert placed.mean(axis=0) == pytest.approx([0.5, 0.5, 0.5],
                                                abs=1e-6)


# --------------------------------------------- marking in the window

def test_marking_needs_something_selected(window, tmp_path, rutile):
    opened(window, tmp_path, rutile)
    assert not window.actions_["mark_connection_points"].isEnabled()


def test_marking_the_selection_is_one_undo_step(window, tmp_path,
                                                dry_ice):
    """One gesture, one press of Ctrl+Z -- and the element and the
    position come back together."""
    document = opened(window, tmp_path, dry_ice, "dry_ice")
    cell = document.cell
    oxygen = int(np.flatnonzero(np.array(cell.elements) == "O")[0])
    document.select({oxygen})

    assert window.actions_["mark_connection_points"].isEnabled()
    window.actions_["mark_connection_points"].trigger()
    assert document.cell.elements[oxygen] == "X"
    assert document.can_undo

    document.undo()
    assert document.cell.elements[oxygen] == "O"
    assert not document.can_undo


def test_marking_an_atom_that_has_no_single_bond_says_which(
        window, tmp_path, dry_ice):
    """Named rather than counted: the label of the one that cannot be
    marked is what tells somebody where to look."""
    document = opened(window, tmp_path, dry_ice, "dry_ice")
    cell = document.cell
    carbon = int(np.flatnonzero(np.array(cell.elements) == "C")[0])
    document.select({carbon})
    window.actions_["mark_connection_points"].trigger()

    assert document.cell.elements[carbon] == "C"
    assert not document.can_undo
    assert "bond" in window.status_label.text()


def benzene_ring():
    """Four carbons in a ring with two hydrogens on the far pair.

    Small enough to name every atom in a test and shaped so that a
    bidentate attachment has somewhere to point: the two carbons at
    the top are the group, the two below them the members.
    """
    from xtal.core.lattice import Lattice
    from xtal.core.structure import Bond, Structure

    lattice = Lattice.cubic(20.0)
    cart = np.array([[-0.70, -1.21, 0.0], [0.70, -1.21, 0.0],
                     [-0.70, 0.21, 0.0], [0.70, 0.21, 0.0],
                     [-1.40, -2.42, 0.0], [1.40, -2.42, 0.0]]) + 10.0
    ring = Structure.from_arrays(
        lattice, ["C", "C", "C", "C", "H", "H"],
        lattice.to_frac(cart), space_group="P1")
    for i, j in ((0, 1), (0, 2), (1, 3), (2, 3), (0, 4), (1, 5)):
        ring.add_bond(Bond(i, j, (0, 0, 0), 1.0))
    return ring


def test_marking_a_group_as_one_point_needs_two_atoms(window,
                                                      tmp_path):
    """One atom on the end of one bond is the other command's
    gesture, so this one is greyed out until there are two."""
    document = opened(window, tmp_path, benzene_ring())
    document.select({2})

    assert window.actions_["mark_connection_points"].isEnabled()
    assert not window.actions_[
        "mark_one_connection_point"].isEnabled()


def test_marking_a_group_as_one_point_is_one_undo_step(window,
                                                       tmp_path):
    """Three commands inside it -- the add, the bonds, the delete --
    and one press of Ctrl+Z gives back all six atoms."""
    document = opened(window, tmp_path, benzene_ring())
    document.select({2, 3})

    assert window.actions_["mark_one_connection_point"].isEnabled()
    window.actions_["mark_one_connection_point"].trigger()

    assert list(document.cell.elements).count("X") == 1
    assert document.structure.n_sites == 5
    assert document.can_undo

    document.undo()
    assert document.structure.n_sites == 6
    assert "X" not in list(document.cell.elements)
    assert not document.can_undo


def test_the_new_connection_point_is_left_selected(window, tmp_path):
    """Like Merge atoms and Add centroid: the atom that was just made
    is the one the next gesture is about."""
    document = opened(window, tmp_path, benzene_ring())
    document.select({2, 3})
    window.actions_["mark_one_connection_point"].trigger()

    selected = sorted(document.selection.atoms)
    assert len(selected) == 1
    assert document.cell.elements[selected[0]] == "X"


# ------------------------------------------------- saving a block

@needs_rdkit
def test_the_save_dialog_defaults_to_the_folder_the_picker_reads(
        window, qtbot, tmp_path):
    """The whole of "with nothing further clicked": it is the same
    box the MOF builder reads its extra blocks from."""
    from xtalapp.dialogs.save_block import SaveBlockDialog
    window.settings.mof_bb_dir = str(tmp_path / "mine")
    document = window.new_document()
    document.paste(linker_fragment())

    dialog = SaveBlockDialog(document.structure, window)
    qtbot.addWidget(dialog)
    assert dialog.folder.text() == str(tmp_path / "mine")


@needs_rdkit
def test_saving_remembers_the_folder_for_the_mof_picker(window,
                                                        qtbot,
                                                        tmp_path):
    """The other half of "with nothing further clicked": the MOF
    builder reads its extra blocks from this same setting."""
    from xtalapp.dialogs.save_block import SaveBlockDialog
    window.settings.mof_bb_dir = ""
    document = window.new_document()
    document.paste(linker_fragment())

    dialog = SaveBlockDialog(document.structure, window)
    qtbot.addWidget(dialog)
    dialog.folder.setText(str(tmp_path / "mine"))
    dialog.accept()

    assert window.settings.mof_bb_dir == str(tmp_path / "mine")


@needs_rdkit
def test_the_save_dialog_says_what_stops_it_being_a_block(window,
                                                          qtbot):
    """Told before the click, because every one of these is something
    to go back and change."""
    from xtalapp.dialogs.save_block import SaveBlockDialog
    document = window.new_document()
    document.paste(water_fragment())

    dialog = SaveBlockDialog(document.structure, window)
    qtbot.addWidget(dialog)
    assert not dialog.ok_button.isEnabled()
    assert "nothing marks where this joins" in dialog.summary.text()


@needs_rdkit
def test_saving_a_block_writes_it_where_the_picker_will_find_it(
        window, qtbot, tmp_path, monkeypatch):
    from xtal.mof.catalog import read_building_block
    from xtalapp.dialogs.save_block import SaveBlockDialog

    window.settings.mof_bb_dir = ""
    blocks = tmp_path / "bbs"
    document = window.new_document()
    document.paste(linker_fragment())
    monkeypatch.setattr(
        SaveBlockDialog, "ask",
        classmethod(lambda cls, *a, **k: blocks / "UPhen.xyz"))
    window.save_building_block()

    written = blocks / "UPhen.xyz"
    assert written.exists()
    assert read_building_block(written).n_connections == 2
    assert "picker" in window.status_label.text()


@needs_rdkit
def test_saving_something_that_is_not_a_block_is_reported(
        window, tmp_path, monkeypatch):
    from xtalapp.dialogs.save_block import SaveBlockDialog

    document = window.new_document()
    document.paste(water_fragment())
    monkeypatch.setattr(
        SaveBlockDialog, "ask",
        classmethod(lambda cls, *a, **k: tmp_path / "no.xyz"))
    window.save_building_block()

    assert not (tmp_path / "no.xyz").exists()


def linker_fragment():
    from xtal.build import from_smiles
    return from_smiles("[*:1]c1ccc([*:2])cc1").to_fragment()


def water_fragment():
    from xtal.build import from_smiles
    return from_smiles("O").to_fragment()


# ---------------------------------------------------- the library

def test_the_library_fills_the_picker(window, qtbot):
    """It is text, so the picker fills whether or not RDKit is
    there."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    from xtal.build import library

    assert dialog.library.count() == len(library.entries())


def test_the_picker_that_pastes_leaves_out_the_linkers(window, qtbot):
    """That box refuses a starred string, so a linker in it would be
    an entry that answers with a refusal."""
    from xtal.build import library

    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    offered = dialog.library.count()

    assert offered == len(library.matching(connection_points=False))
    assert offered < len(library.entries())


@needs_rdkit
def test_choosing_a_fragment_fills_the_boxes_and_draws_it(window,
                                                          qtbot):
    """Into the boxes rather than around them: the next thing anybody
    does with a phenylene is put a methyl on it."""
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    index = dialog.library.combo.findText("Phenylene", Qt.MatchStartsWith)
    dialog.library.combo.setCurrentIndex(index)
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)

    assert dialog.form.widgets["smiles"].text().startswith("[*:1]")
    assert dialog.values()["name"] == "Phenylene"
    assert dialog.molecule.n_connections == 2
    assert "2 connection point(s)" in dialog.footer.text()
