"""Select > Advanced Selection...: one rule, combined with what is held.

The rules themselves are tested headless in ``test_selection.py``;
this is the form, the count beside Apply, the combine chooser and the
menu entries.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.dialogs.select import SelectDialog  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Select{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _choose(dialog, rule, how="replace"):
    dialog.rule.setCurrentIndex(dialog.rule.findData(rule))
    dialog.how.setCurrentIndex(dialog.how.findData(how))


def test_combine_intersect_keeps_only_the_common_atoms(qtbot, rutile):
    """Six-coordinate atoms intersected with the lower layer is the one
    Ti at z = 0 -- neither rule alone says that."""
    document = Document(rutile)
    dialog = SelectDialog(document)
    qtbot.addWidget(dialog)
    _choose(dialog, "coordination")
    element, op, n = dialog.coordination
    n.setValue(6)
    dialog.apply()
    assert document.selection.atoms == {0, 1}

    _choose(dialog, "box", "intersect")
    lower, upper = dialog.box
    upper[2].setValue(0.25)
    dialog.apply()
    assert document.selection.atoms == {0}


def test_the_preview_count_matches_what_apply_selects(qtbot, rutile):
    """The number beside Apply is the number Apply selects -- for an
    atom rule, a region with its bonds, and bonds alone."""
    document = Document(rutile)
    dialog = SelectDialog(document)
    qtbot.addWidget(dialog)

    _choose(dialog, "element")
    assert dialog.found.text() == "4 atoms"         # O, checked first
    dialog.apply()
    assert len(document.selection.atoms) == 4

    _choose(dialog, "radius")
    preview = dialog.preview()
    text = dialog.found.text()
    dialog.apply()
    assert document.selection.atoms == preview.atoms
    assert document.selection.bonds == preview.bonds
    assert text == (f"{len(preview.atoms)} atoms, "
                    f"{len(preview.bonds)} bonds")

    _choose(dialog, "bonds")
    shortest, longest = dialog.bond_lengths
    longest.setValue(1.96)
    assert dialog.found.text() == "8 bonds"
    dialog.apply()
    assert len(document.selection.bonds) == 8
    assert not document.selection.atoms


def test_the_count_follows_the_selection_it_combines_with(qtbot,
                                                          rutile):
    """Add to the selection counts what would be held after, and
    changes when the selection changes under the open dialog."""
    document = Document(rutile)
    dialog = SelectDialog(document)
    qtbot.addWidget(dialog)
    _choose(dialog, "element", "add")
    assert dialog.found.text() == "4 atoms"
    document.select([0], "set")                 # a Ti
    assert dialog.found.text() == "5 atoms"


def test_an_empty_rule_says_so_rather_than_counting_zero(qtbot, rutile):
    document = Document(rutile)
    dialog = SelectDialog(document)
    qtbot.addWidget(dialog)
    _choose(dialog, "label")
    dialog.label_pattern.setText("Zn*")
    assert dialog.found.text() == "Nothing would be selected"


def test_select_opens_from_the_select_menu_over_the_tab(window, rutile):
    window.add_document(Document(rutile))
    action = window.actions_["select_dialog"]
    assert action.isEnabled()
    action.trigger()
    dialog = window._select_dialog
    assert dialog.isVisible()
    assert dialog.document is window.current_document()
    action.trigger()                            # brought forward, not two
    assert window._select_dialog is dialog
    dialog.close()


def test_grow_to_neighbours_only_lets_the_selection_go(window, rutile):
    window.add_document(Document(rutile))
    document = window.current_document()
    document.select([0], "set")
    window.actions_["expand_neighbours"].trigger()
    held = document.selection.atoms
    assert held == set(document.graph.neighbors(0))
    assert 0 not in held
    assert all(document.cell.elements[a] == "O" for a in held)


def _methanol_and_acid():
    """Methanol and acetic acid, apart in one box: one hydroxyl, and
    one acid whose OH is not a hydroxyl."""
    import numpy as np

    from xtal import Lattice, Structure
    from xtal.core.site import Site

    atoms = [("C", 0.0, 0.0, 0.0), ("O", 1.43, 0.0, 0.0),
             ("H", 1.75, 0.9, 0.0), ("H", -0.37, 1.03, 0.0),
             ("H", -0.37, -0.51, 0.89), ("H", -0.37, -0.51, -0.89),
             ("C", 0.0, 0.0, 6.0), ("C", 1.5, 0.0, 6.0),
             ("O", 2.105, 1.048, 6.0), ("O", 2.15, -1.126, 6.0),
             ("H", 3.11, -1.126, 6.0), ("H", -0.37, 1.03, 6.0),
             ("H", -0.37, -0.51, 6.89), ("H", -0.37, -0.51, 5.11)]
    lattice = Lattice.cubic(14.0)
    return Structure(lattice=lattice, sites=[
        Site(e, (np.array(xyz) + 3.0) / 14.0) for e, *xyz in atoms])


def test_selecting_hydroxyl_handles_selects_only_their_hydrogens(qtbot):
    """The handle of a hydroxyl is its hydrogen, and the acid's OH is
    the acid's: substituting the selection then esterifies the
    alcohol and leaves the acid alone.  Each row says its count."""
    document = Document(_methanol_and_acid())
    dialog = SelectDialog(document)
    qtbot.addWidget(dialog)
    _choose(dialog, "group")
    kind, part = dialog.group_kind, dialog.group_part
    kind.setCurrentIndex(kind.findData("alcohol"))
    assert kind.currentText() == "Hydroxyl (alcohol) — 1"
    assert part.itemText(1) == "Only the hydrogen"
    part.setCurrentIndex(part.findData("handle"))
    dialog.apply()
    assert document.selection.atoms == {2}

    part.setCurrentIndex(part.findData("whole"))
    kind.setCurrentIndex(kind.findData("carboxylic_acid"))
    dialog.apply()
    assert document.selection.atoms == {7, 8, 9, 10}
