"""The Net panel: where the name appears, and when it is recomputed.

Two things are being tested and only one of them is about text.  The
panel has to say **pcu** where a person can see it -- which is the
whole feature, and which nothing did before -- and it has to stay
silent while the rest of the application works, because identification
walks ten shells of an infinite graph and running it on every drag of
an atom is how a large structure loses interactivity.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal import Lattice, Structure  # noqa: E402
from xtal.core.structure import TOPOLOGY, Bond, Change  # noqa: E402
from xtalapp.docks.net import NetDock  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Net{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def pcu_document() -> Document:
    structure = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                      [[0.0, 0.0, 0.0]],
                                      space_group="P1")
    for image in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        structure.bonds.append(Bond(0, 0, image, kind=TOPOLOGY))
    structure.touch()
    return Document(structure)


@pytest.fixture
def dock(qtbot):
    """Shown, because a hidden panel deliberately computes nothing."""
    panel = NetDock()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    return panel


# ============================================================ what it says

def test_the_panel_names_the_net(dock, rcsr_catalogue):
    dock.set_document(pcu_document())
    assert dock.name.text() == "pcu"
    assert "4^12.6^3" in dock.text.toPlainText()
    assert "6, 18, 38, 66" in dock.text.toPlainText()


def test_the_panel_says_how_much_was_drawn(dock, rcsr_catalogue):
    """A pcu found on one vertex and three edges is the same net as
    one found on eight and twenty-four, and seeing the numbers is what
    makes that believable rather than surprising."""
    dock.set_document(pcu_document())
    assert "1 vertices and 3 edges" in dock.text.toPlainText()


def test_a_structure_with_no_net_is_told_how_to_draw_one(dock):
    """"Nothing here" is a dead end; the name of the mode is not."""
    plain = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                  [[0.0, 0.0, 0.0]], space_group="P1")
    dock.set_document(Document(plain))
    assert dock.name.text() == ""
    assert "Draw net" in dock.text.toPlainText()
    assert not dock.copy.isEnabled()


def test_no_document_is_not_no_net(dock):
    dock.set_document(None)
    assert "No structure open" in dock.text.toPlainText()


def test_the_identification_can_be_copied(dock, qtbot, rcsr_catalogue):
    from PySide6.QtWidgets import QApplication

    dock.set_document(pcu_document())
    with qtbot.waitSignal(dock.statusMessage):
        dock.copy.click()
    assert "pcu" in QApplication.clipboard().text()


# ================================================== when it is recomputed

def test_moving_an_atom_does_not_re_identify_the_net(dock, monkeypatch,
                                                     rcsr_catalogue):
    """The net is the one thing a geometry change cannot alter -- that
    is what makes it worth naming -- so a move must not pay for it."""
    document = pcu_document()
    dock.set_document(document)

    calls = []
    monkeypatch.setattr(document, "net_identification",
                        lambda: calls.append(1))
    dock.on_structure_changed(int(Change.POSITIONS))
    assert calls == []


def test_a_change_to_the_bonds_does_re_identify_it(dock, monkeypatch,
                                                   rcsr_catalogue):
    document = pcu_document()
    dock.set_document(document)

    calls = []
    real = document.net_identification
    monkeypatch.setattr(document, "net_identification",
                        lambda: (calls.append(1), real())[1])
    dock.on_structure_changed(int(Change.TOPOLOGY))
    assert calls == [1]


def test_the_answer_is_cached_against_the_structure(rcsr_catalogue):
    """Asked twice with nothing changed in between, the walk runs
    once: the panel, the status bar and anything else that asks are
    reading one answer."""
    document = pcu_document()
    first = document.net_identification()
    assert document.net_identification() is first

    document.structure.touch()
    assert document.net_identification() is not first


# ========================================================== in the window

def test_a_panel_nobody_has_opened_computes_nothing(qtbot,
                                                    monkeypatch):
    """It is not in the default layout, so for most users this is
    always the case -- and identification is the one refresh in the
    window that costs real time."""
    panel = NetDock()
    qtbot.addWidget(panel)
    document = pcu_document()
    monkeypatch.setattr(
        document, "net_identification",
        lambda: pytest.fail("a hidden panel identified the net"))
    panel.set_document(document)
    assert panel._stale


def test_it_catches_up_when_it_is_shown(qtbot, rcsr_catalogue):
    panel = NetDock()
    qtbot.addWidget(panel)
    panel.set_document(pcu_document())
    assert panel.name.text() == ""
    panel.show()
    qtbot.waitExposed(panel)
    assert panel.name.text() == "pcu"


def test_the_window_has_a_net_panel(window):
    assert window.net_dock in window.right_docks
    assert window.net_dock.windowTitle() == "Net"


def test_the_panel_follows_the_current_document(window, qtbot,
                                                rcsr_catalogue):
    """Raised from behind the tabs it starts in, it identifies the net
    in whatever document is current.  The window has to be on screen
    for that: a dock inside a hidden window is not visible, which is
    the same gate that stops a tabbed-away panel computing."""
    window.show()
    qtbot.waitExposed(window)
    window.net_dock.show()
    window.net_dock.raise_()
    window.add_document(pcu_document())
    assert window.net_dock.name.text() == "pcu"


def test_the_report_reaches_the_document_as_a_sentence(rcsr_catalogue):
    """``Document.net_report`` is what the status bar and the tests
    from the drawing half read, and it now leads with the name."""
    report = pcu_document().net_report()
    assert report.startswith("pcu")
    assert "6-coordinated" in report
    assert "6, 18, 38, 66" in report
    assert "4^12.6^3" in report


# ==================================================== asking Systre

def test_the_export_button_is_only_offered_for_a_net(dock,
                                                      rcsr_catalogue):
    plain = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                  [[0.0, 0.0, 0.0]], space_group="P1")
    dock.set_document(Document(plain))
    assert not dock.export.isEnabled()
    dock.set_document(pcu_document())
    assert dock.export.isEnabled()


def test_the_export_action_follows_the_net_being_drawn(window):
    """Greyed out until there is a net, and live the moment one edge
    is drawn -- not only when the tab changes."""
    plain = Structure.from_arrays(Lattice.cubic(5.0), ["Zn"],
                                  [[0.0, 0.0, 0.0]], space_group="P1")
    document = Document(plain)
    window.add_document(document)
    assert not window.actions_["export_net"].isEnabled()
    document.add_topology_bond_between(0, 0, image_b=(1, 0, 0))
    assert window.actions_["export_net"].isEnabled()


def test_exporting_writes_a_net_systre_can_read(window, tmp_path,
                                                monkeypatch):
    """What reaches the file is the net the panel named, under the
    name the user gave the file -- the one word Systre prints back."""
    from PySide6.QtWidgets import QFileDialog

    from xtal.analysis import rcsr
    from xtal.io.cgd import read_cgd

    document = pcu_document()
    window.add_document(document)
    asked = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kw: (asked.append(args[2]),
                             (str(tmp_path / "mine"), ""))[1])
    window.actions_["export_net"].trigger()

    assert asked and asked[0].endswith(".cgd")
    written = tmp_path / "mine.cgd"
    entry = read_cgd(written)["mine"]
    assert rcsr.expand(entry).key() == document.net().key()
    assert not document.modified


def test_the_panel_button_is_the_same_export(window, tmp_path,
                                             monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window.add_document(pcu_document())
    window.net_dock.set_document(window.current_document())
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kw: (str(tmp_path / "net.cgd"), ""))
    window.net_dock.export.setEnabled(True)
    window.net_dock.export.click()
    assert (tmp_path / "net.cgd").exists()


def test_a_net_that_cannot_be_written_says_why(window, tmp_path,
                                               monkeypatch):
    """Two vertices in one place would make the file a guess, and the
    refusal has to reach the person rather than a log."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    structure = Structure.from_arrays(
        Lattice.cubic(5.0), ["Zn", "X"],
        [[0.0, 0.0, 0.0], [0.9985, 0.0, 0.0]], space_group="P1")
    structure.bonds.append(Bond(0, 0, (1, 0, 0), kind=TOPOLOGY))
    structure.bonds.append(Bond(1, 1, (0, 1, 0), kind=TOPOLOGY))
    structure.touch()
    window.add_document(Document(structure))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kw: (str(tmp_path / "net.cgd"), ""))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda parent, title, text: warned.append(text))
    window.export_net()
    assert warned and "same place" in warned[0]
    assert not (tmp_path / "net.cgd").exists()
