"""What a view change costs compared with a structure change."""
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Cost{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _ms(fn, n=20):
    fn()
    t = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t) / n * 1000


def test_cost_of_each_refresh(window):
    doc = window.open_path("resources/samples/MFU4l.cif")
    assert doc is not None
    print(f"\nMFU4l: {len(doc.structure.sites)} sites, "
          f"{doc.cell.n_atoms} atoms in the cell")
    for name in ("_refresh_shell", "_refresh_module_actions",
                 "_on_view_changed", "_update_ui"):
        fn = getattr(window, name)
        call = (lambda f=fn, n=name:
                f(True) if n == "_refresh_module_actions" else f())
        print(f"  {name:<26} {_ms(call):8.2f} ms")
    print(f"  {'_on_structure_changed(ALL)':<26} "
          f"{_ms(lambda: window._on_structure_changed(0)):8.2f} ms")
