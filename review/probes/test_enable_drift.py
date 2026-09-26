"""Does the shell decide the same thing twice, and differently?

mainwindow._on_selection_changed and mainwindow._refresh_shell both
set the enabled state of the same dozen actions.  Only one of them
consults ``document.is_playing``.
"""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

SHARED = ["delete_selection", "change_element", "cut", "duplicate",
          "mark_connection_points", "add_centroid", "merge_atoms",
          "select_same", "expand_bonded", "expand_fragment",
          "expand_orbit", "copy"]


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Drift{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_the_two_places_disagree_while_a_trajectory_plays(
        window, quartz, monkeypatch):
    document = window.add_document.__self__ and None
    from xtalapp.document import Document
    doc = Document(quartz)
    window.add_document(doc)
    doc.select([0, 1], "set")

    # Pretend a trajectory is open, which is what is_playing means.
    monkeypatch.setattr(type(doc), "is_playing",
                        property(lambda self: True))

    window._refresh_shell()
    after_shell = {n: window.actions_[n].isEnabled() for n in SHARED}

    window._on_selection_changed()
    after_selection = {n: window.actions_[n].isEnabled() for n in SHARED}

    differ = {n: (after_shell[n], after_selection[n])
              for n in SHARED if after_shell[n] != after_selection[n]}
    print("\n_refresh_shell vs _on_selection_changed, "
          "while playing:")
    for name, (a, b) in sorted(differ.items()):
        print(f"  {name:<24} shell={a}  selection={b}")
    assert not differ, differ
