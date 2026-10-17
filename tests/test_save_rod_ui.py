"""Structure > Building blocks > Save the rod as a block: a rod and
its linker cut from the crystal in front into the workspace's blocks,
and the rod builder's form offering it from then on."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from xtalapp.dialogs.save_rod import SaveRodDialog
from xtalapp.mainwindow import MainWindow
from xtalapp.settings import AppSettings

PREPARED = Path(__file__).resolve().parents[1] / "resources" / \
    "samples" / "prepared"


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Rod{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_a_saved_rod_is_offered_by_the_rod_builder(window, monkeypatch):
    """The whole of the path: the selected metal is the seed, the rod
    and its linker land in the workspace's blocks, the tab is
    untouched, and the rod builder's form lists the rod."""
    from xtal.modules import MODULES

    document = window.open_path(PREPARED / "MIL-53.cif")
    before = document.structure.n_sites
    symbols = document.cell.elements
    metal = max(i for i, s in enumerate(symbols) if s == "Cr")
    document.select([metal])
    asked = {}

    def answer(cls, structure, folder, seed=None, parent=None):
        asked["seed"], asked["folder"] = seed, folder
        return {"name": "mine", "shape": "rng", "prepared": False,
                "seed": seed}

    monkeypatch.setattr(SaveRodDialog, "ask", classmethod(answer))
    action = window.actions_["save_rod"]
    assert action.isEnabled()
    action.trigger()

    blocks = window.workspace.blocks
    assert asked == {"seed": metal, "folder": blocks}
    assert (blocks / "rods" / "mine.xyz").is_file()
    assert (blocks / "rods" / "linkers" / "mine.xyz").is_file()
    assert document.structure.n_sites == before
    assert not document.modified

    _module, entry = MODULES.find("mof.rod")
    rod_param = next(p for p in entry.params if p.name == "rod")
    labels = dict(rod_param.values_and_labels())
    assert labels["mine"] == "mine (this workspace)"
    assert rod_param.coerce("mine") == "mine"


def test_the_dialog_says_what_the_rod_came_to_and_refuses_a_shipped_name(
        qtbot, tmp_path):
    """The footer is a cut made the way Save makes it, so what it
    accepts the builder reads; a shipped rod's name is refused."""
    from xtal.io import read_cif

    structure = read_cif(PREPARED / "MIL-53.cif")
    dialog = SaveRodDialog(structure, tmp_path / "blocks")
    qtbot.addWidget(dialog)
    dialog.name.setText("cr")
    assert dialog.ok_button.isEnabled()
    assert "achiral" in dialog.summary.text()
    assert "6 edge(s)" in dialog.summary.text()

    dialog.name.setText("MIL-53_Cr")
    assert not dialog.ok_button.isEnabled()
    assert "shipped rod" in dialog.summary.text()

    dialog.name.setText("cr")
    dialog.shape.setCurrentIndex(1)
    assert dialog.shells.isVisibleTo(dialog)
    assert dialog.values()["shape"] == 5


def test_save_rod_is_greyed_with_nothing_open(window):
    assert not window.actions_["save_rod"].isEnabled()


def test_the_rod_dialogs_cite_the_rod_review(qtbot, tmp_path, window):
    """Saving a rod and building on one both cite how a rod net is
    read: Schoedel et al.'s review."""
    from xtal.io import read_cif
    from xtal.modules import MODULES
    from xtalapp.dialogs.rod_build import RodBuildDialog

    review = "https://doi.org/10.1021/acs.chemrev.6b00346"
    saving = SaveRodDialog(read_cif(PREPARED / "MIL-53.cif"),
                           tmp_path / "blocks")
    qtbot.addWidget(saving)
    assert review in saving.sources.urls()
    module, action = MODULES.find("mof.rod")
    building = RodBuildDialog(module, action, window)
    qtbot.addWidget(building)
    assert review in building.sources.urls()
