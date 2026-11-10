"""Build the likely frameworks, through the window.

The module is tested headless in :mod:`tests.test_synthesis`; what is
here is the one thing only the window does with it -- the best build
opens in a tab of its own, filed in the workspace, with the linker
block left where the MOF builder will find it again.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.build import MISSING, installed  # noqa: E402
from xtal.mof import database_root  # noqa: E402
from xtalapp.dialogs.module_form import ModuleDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

pytestmark = [
    pytest.mark.skipif(not installed(), reason=MISSING),
    pytest.mark.skipif(database_root() is None,
                       reason="the MOF builder's database is missing"),
]


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Syn{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.mark.slow
def test_the_best_build_opens_in_a_new_tab_with_its_linker_kept(
        window, qtbot, monkeypatch):
    """UiO-66 from its synthesis: the fcu build is the one that opens,
    and the BDC block it was made with is in the workspace's blocks/
    -- which is what makes the report's rebuild lines true."""
    monkeypatch.setattr(ModuleDialog, "ask", staticmethod(
        lambda *a, **k: {"metal": "ZrCl4", "linkers": "BDC",
                         "solvents": "DMF", "budget": 3.0}))

    window.run_module_action("synthesis", "build")
    qtbot.waitUntil(lambda: window.module_worker is None,
                    timeout=120000)

    assert len(window.documents) == 1
    built = window.documents[0].structure
    assert built.meta["title"].startswith("fcu-N419-SYN-")
    assert any("not a prediction" in w
               for w in built.meta.get("warnings", ()))
    blocks = window.workspace.blocks
    assert len(list(blocks.glob("SYN-*.xyz"))) == 1
