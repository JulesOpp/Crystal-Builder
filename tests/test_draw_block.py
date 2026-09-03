"""xtalapp.dialogs.draw_block on screen, and the button that opens it
from a slot row.

The dialog itself needs only RDKit -- a :class:`~xtal.mof.catalog.Slot`
is a plain dataclass and reading it costs no catalogue at all -- so
those tests are gated on ``needs_rdkit`` alone.  Wiring it into a
running :class:`~xtalapp.dialogs.mof_build.MofBuildDialog` needs
PORMAKE's own database for the topology the row comes from, hence the
second marker below.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.build import installed as rdkit_installed  # noqa: E402
from xtal.modules import MODULES  # noqa: E402
from xtal.mof import database_root  # noqa: E402
from xtal.mof.catalog import Slot, read_building_block  # noqa: E402
from xtalapp.dialogs.draw_block import DrawBlockDialog  # noqa: E402
from xtalapp.dialogs.mof_build import MofBuildDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

needs_rdkit = pytest.mark.skipif(
    not rdkit_installed(),
    reason="RDKit is not installed; pip install "
           "'crystal-builder[build]'")

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="PORMAKE is not installed; pip install "
           "'crystal-builder[mof]'")


def typed(dialog, qtbot, text):
    """Type a string and wait for the build the keystrokes start."""
    dialog.form.widgets["smiles"].setText(text)
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)


# ------------------------------------------------- the dialog alone

@needs_rdkit
def test_a_molecule_that_fits_the_slot_enables_save(qtbot, tmp_path):
    slot = Slot("edge", (0, 0), 2)
    dialog = DrawBlockDialog(slot, str(tmp_path))
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]CC[*:2]")

    assert "fits" in dialog.footer.text()
    assert dialog.save_button.isEnabled()


@needs_rdkit
def test_the_wrong_number_of_connection_points_refuses_the_save(
        qtbot, tmp_path):
    """A six-connected node slot wants six connection points and
    nothing else fits it -- the same rule the catalogue's own
    ``fitting`` enforces after the fact, checked here before a file
    is ever written."""
    slot = Slot("node", 0, 6)
    dialog = DrawBlockDialog(slot, str(tmp_path))
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]c1ccc([*:2])cc1")

    assert "needs 6, not 2" in dialog.footer.text()
    assert not dialog.save_button.isEnabled()


@needs_rdkit
def test_saving_writes_a_block_the_catalog_can_read_back(qtbot,
                                                         tmp_path):
    slot = Slot("edge", (0, 0), 2)
    dialog = DrawBlockDialog(slot, str(tmp_path))
    qtbot.addWidget(dialog)
    dialog.form.set_values({"name": "my-linker"})
    typed(dialog, qtbot, "[*:1]CC[*:2]")
    dialog.accept()

    written = tmp_path / "my-linker.xyz"
    assert dialog.path == written
    assert read_building_block(written).n_connections == 2


@needs_rdkit
def test_with_no_folder_saving_is_refused_and_says_why(qtbot):
    """Nowhere of the user's own to write into -- the MOF builder's
    own "Extra building blocks" folder is where a drawn block has to
    land to be found again."""
    slot = Slot("edge", (0, 0), 2)
    dialog = DrawBlockDialog(slot, "")
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]CC[*:2]")

    assert "Extra building blocks" in dialog.where.text()
    assert not dialog.save_button.isEnabled()


# ---------------------------------------------- wired into a row

@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest",
                           f"DrawBlock{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    return settings


@pytest.fixture
def window(qtbot, settings):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def built(qtbot, window, tmp_path):
    _module, action = MODULES.find("mof.build")
    dialog = MofBuildDialog(MODULES.get("mof"), action, window,
                            {"topology": "pcu", "bb_dir": str(tmp_path)})
    qtbot.addWidget(dialog)
    return dialog


@needs_database
@needs_rdkit
def test_a_row_asks_the_sketcher_for_its_own_slot(built, tmp_path,
                                                   monkeypatch):
    """The button opens already knowing the coordination number to
    check against -- the dialog is asked for it, not told afterwards."""
    seen = {}

    def fake_ask(cls, slot, folder, parent=None):
        seen["slot"] = slot
        seen["folder"] = folder
        return None

    monkeypatch.setattr(DrawBlockDialog, "ask", classmethod(fake_ask))
    edge = built._rows[-1]
    edge.draw_button.click()

    assert seen["slot"] is edge.slot
    assert seen["folder"] == str(tmp_path)


@needs_database
@needs_rdkit
def test_drawing_a_block_selects_it_with_nothing_further_clicked(
        built, tmp_path, monkeypatch):
    edge = built._rows[-1]
    assert edge.slot.is_edge and edge.slot.coordination == 2
    written = tmp_path / "U-drawn.xyz"

    def fake_ask(cls, slot, folder, parent=None):
        written.write_text("4\n\nX 2 0 0\nC 0.7 0 0\n"
                           "C -0.7 0 0\nX -2 0 0\n")
        return written

    monkeypatch.setattr(DrawBlockDialog, "ask", classmethod(fake_ask))
    edge.draw_button.click()

    assert edge.block() == "U-drawn"
    assert built.values()["edges"] == "0-0=U-drawn"


@needs_database
@needs_rdkit
def test_drawing_a_block_rereads_every_rows_catalogue(built,
                                                       tmp_path,
                                                       monkeypatch):
    """A block fits every slot of its own coordination, so the
    catalogue every row reads from is refreshed and not only the row
    that asked -- see ``MofBuildDialog._on_block_drawn``."""
    node, edge = built._rows
    written = tmp_path / "U-drawn.xyz"
    old_catalog = built.catalog

    def fake_ask(cls, slot, folder, parent=None):
        written.write_text("4\n\nX 2 0 0\nC 0.7 0 0\n"
                           "C -0.7 0 0\nX -2 0 0\n")
        return written

    monkeypatch.setattr(DrawBlockDialog, "ask", classmethod(fake_ask))
    edge.draw_button.click()

    assert built.catalog is not old_catalog
    assert node._catalog is built.catalog
    assert edge._catalog is built.catalog
    assert "U-drawn" in {b.name for b in built.catalog.fitting(2)}


@needs_database
@needs_rdkit
def test_a_cancelled_draw_changes_nothing(built, monkeypatch):
    edge = built._rows[-1]
    before = edge.block()

    monkeypatch.setattr(
        DrawBlockDialog, "ask",
        classmethod(lambda cls, slot, folder, parent=None: None))
    edge.draw_button.click()

    assert edge.block() == before
