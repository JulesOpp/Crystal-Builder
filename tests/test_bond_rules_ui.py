"""The bond rules dialog, and the preference beside it.

The dialog is the only way to reach criteria that ``BondRules`` has
carried since phase 1, so these tests are mostly about the two things
that make it usable rather than merely present: the preview says what
*changes*, and metal-metal is a control of its own rather than a
finer tolerance.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from xtal.core import bonding  # noqa: E402
from xtalapp.dialogs.bond_rules import BondRulesDialog  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def dialog(qtbot, rutile):
    widget = BondRulesDialog(Document(rutile))
    qtbot.addWidget(widget)
    return widget


def row_for(widget, pair) -> int:
    return widget.pairs.index(pair)


# ------------------------------------------------------------ the form

def test_it_opens_on_the_structures_own_rules(qtbot, rutile):
    rutile.bond_rules = {"scale": 1.4, "allow_metal_metal": True}
    widget = BondRulesDialog(Document(rutile))
    qtbot.addWidget(widget)
    assert widget.scale.value() == pytest.approx(1.4)
    assert widget.metal_metal.isChecked()


def test_the_table_is_keyed_on_the_elements_that_are_here(dialog):
    """Not the periodic table: rutile has two elements and therefore
    three rows."""
    assert dialog.pairs == [("O", "O"), ("O", "Ti"), ("Ti", "Ti")]


def test_the_slider_and_the_number_stay_together(dialog):
    dialog.slider.setValue(dialog._to_slider(1.60))
    assert dialog.scale.value() == pytest.approx(1.60, abs=0.02)
    dialog.scale.setValue(1.20)
    assert dialog.slider.value() == dialog._to_slider(1.20)


# --------------------------------------------------------- the preview

def test_the_preview_says_what_changes_not_what_there_is(dialog):
    """A count alone hides the setting that swaps one bond for
    another."""
    assert dialog.difference() == (0, 0, 12)
    assert "no change" in dialog.summary.text()

    dialog.scale.setValue(1.60)              # the second shell arrives
    added, removed, total = dialog.difference()
    assert added and not removed
    assert total == 28
    assert "added" in dialog.summary.text()


def test_the_plateau_is_visible_as_a_number(dialog):
    """Rutile keeps exactly its 12 Ti-O bonds from 1.05 to 1.45 and
    then jumps.  The figure beside the slider is the only thing that
    shows that, which is why there is one."""
    counts = []
    for scale in (1.05, 1.15, 1.25, 1.35, 1.45, 1.60):
        dialog.scale.setValue(scale)
        counts.append(dialog.difference()[2])
    assert counts[:5] == [12] * 5
    assert counts[5] > 12


def test_metal_metal_is_not_a_finer_tolerance(dialog):
    """No amount of loosening the radius factor gives rutile a Ti-Ti
    bond while the flag is off."""
    dialog.scale.setValue(1.45)
    assert dialog.difference()[2] == 12

    dialog.scale.setValue(bonding.DEFAULT_SCALE)
    dialog.metal_metal.setChecked(True)
    assert dialog.difference()[2] == 22


def test_forbidding_a_pair_removes_its_bonds(dialog):
    dialog.table.item(row_for(dialog, ("O", "Ti")), 1).setCheckState(
        Qt.Unchecked)
    assert dialog.rules().forbidden == {("O", "Ti")}
    assert dialog.difference() == (0, 12, 0)


def test_an_explicit_range_overrides_the_radii(dialog):
    row = row_for(dialog, ("O", "Ti"))
    dialog.table.item(row, 2).setText("0.5")
    dialog.table.item(row, 3).setText("1.0")     # shorter than any bond
    assert dialog.rules().pair_ranges == {("O", "Ti"): (0.5, 1.0)}
    assert dialog.difference()[2] == 0


def test_a_minimum_with_no_maximum_is_left_alone(dialog):
    """Half a range would bound nothing, and silently doing nothing is
    worse than ignoring it."""
    row = row_for(dialog, ("O", "Ti"))
    dialog.table.item(row, 2).setText("0.9")
    assert dialog.rules().pair_ranges == {}


def test_unparseable_text_reads_as_automatic(dialog):
    row = row_for(dialog, ("O", "Ti"))
    dialog.table.item(row, 3).setText("1.6q")
    assert dialog.rules().pair_ranges == {}
    assert dialog.difference() == (0, 0, 12)


def test_restore_defaults_puts_everything_back(dialog):
    dialog.scale.setValue(1.9)
    dialog.metal_metal.setChecked(True)
    dialog.table.item(0, 1).setCheckState(Qt.Unchecked)

    dialog.restore_defaults()
    assert dialog.scale.value() == pytest.approx(bonding.DEFAULT_SCALE)
    assert not dialog.metal_metal.isChecked()
    assert dialog.rules().forbidden == set()
    assert dialog.difference() == (0, 0, 12)


# ------------------------------------------------------- previewing is
#                                                          not applying

def test_a_preview_does_not_touch_the_stored_graph(dialog):
    """Rules handed to ``perceive`` are a question.  Answering it must
    not replace the graph the document is carrying."""
    structure = dialog.structure
    bonding.perceive(structure)
    stored = structure.perceived

    dialog.scale.setValue(1.9)
    dialog.difference()
    assert structure.perceived is stored
    assert len(bonding.perceive(structure)) == 12


def test_accepting_applies_it_as_one_undoable_command(qtbot, rutile,
                                                      monkeypatch):
    from PySide6.QtWidgets import QDialog

    document = Document(rutile)
    monkeypatch.setattr(BondRulesDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(BondRulesDialog, "__init__",
                        _accepting(BondRulesDialog.__init__, 1.60))

    message = BondRulesDialog.ask(document)
    assert "added" in message
    assert document.stack.depth == 1
    assert len(document.graph.bonds) == 28

    document.undo()
    assert len(document.graph.bonds) == 12


def test_accepting_an_unchanged_form_pushes_nothing(qtbot, rutile,
                                                    monkeypatch):
    from PySide6.QtWidgets import QDialog

    document = Document(rutile)
    monkeypatch.setattr(BondRulesDialog, "exec",
                        lambda self: QDialog.Accepted)
    assert "unchanged" in BondRulesDialog.ask(document)
    assert document.stack.depth == 0


def test_remembering_the_rules_is_asked_for_not_assumed(qtbot, rutile,
                                                        tmp_path,
                                                        monkeypatch):
    from PySide6.QtWidgets import QDialog

    settings = AppSettings("CrystalBuilderTest", f"Rules{tmp_path.name}")
    settings.set_default_bond_rules(None)
    monkeypatch.setattr(BondRulesDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(BondRulesDialog, "__init__",
                        _accepting(BondRulesDialog.__init__, 1.60))

    BondRulesDialog.ask(Document(rutile.copy()), settings=settings)
    assert settings.default_bond_rules() == {}

    monkeypatch.setattr(
        BondRulesDialog, "__init__",
        _accepting(BondRulesDialog.__init__, 1.60, remember=True))
    BondRulesDialog.ask(Document(rutile.copy()), settings=settings)
    assert settings.default_bond_rules()["scale"] == pytest.approx(1.60)
    settings.set_default_bond_rules(None)


# ------------------------------------------- the same form, no crystal
#
# Preferences > Bonding opens this dialog with no document, over the
# criteria a newly opened structure starts from.  Those could
# previously be set only by opening this dialog *on a structure* and
# ticking a box, so somebody with no file open -- which is the moment
# they might want to say what their files should open as -- could not
# reach them at all.

def test_it_opens_with_no_structure_at_all(qtbot):
    widget = BondRulesDialog(None, rules={"scale": 1.4,
                                          "allow_metal_metal": True})
    qtbot.addWidget(widget)

    assert widget.defaults_mode
    assert widget.scale.value() == pytest.approx(1.4)
    assert widget.metal_metal.isChecked()


def test_with_no_crystal_there_is_no_count_of_what_changed(qtbot):
    """The preview says what a rule *changes*, which is a fact about a
    structure.  With none, it says what the rules are for instead."""
    widget = BondRulesDialog(None)
    qtbot.addWidget(widget)

    assert "opened from now on" in widget.summary.text()


def test_with_no_crystal_the_pair_table_has_nothing_to_key_on(qtbot):
    """The rows are the elements in a structure.  Without one the
    alternative is the whole periodic table, which is 8000 rows."""
    widget = BondRulesDialog(None)
    qtbot.addWidget(widget)

    assert widget.pairs == []
    assert widget.table.isHidden()


def test_a_pair_the_defaults_already_name_still_gets_a_row(qtbot):
    """Otherwise opening this dialog would silently drop a rule that
    was set from a structure."""
    widget = BondRulesDialog(None, rules={
        "pair_ranges": {"O-Ti": [0.0, 2.4]}, "forbidden": ["O-O"]})
    qtbot.addWidget(widget)

    assert widget.pairs == [("O", "O"), ("O", "Ti")]
    assert not widget.table.isHidden()
    assert widget.rules().pair_ranges[("O", "Ti")] == (0.0, 2.4)


def test_there_is_nothing_to_remember_them_for(qtbot):
    """The checkbox makes a structure's rules the default.  In this
    mode they are the default."""
    widget = BondRulesDialog(None)
    qtbot.addWidget(widget)

    assert widget.remember.isHidden()


def test_accepting_the_defaults_writes_them_to_the_preference(
        qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    settings = AppSettings("CrystalBuilderTest", f"Defs{tmp_path.name}")
    settings.set_default_bond_rules(None)
    monkeypatch.setattr(BondRulesDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(BondRulesDialog, "__init__",
                        _accepting_defaults(BondRulesDialog.__init__,
                                            1.35))

    assert BondRulesDialog.edit_defaults(settings) is True
    assert settings.default_bond_rules()["scale"] == pytest.approx(1.35)


def test_cancelling_leaves_the_defaults_as_they_were(qtbot, tmp_path,
                                                     monkeypatch):
    from PySide6.QtWidgets import QDialog

    settings = AppSettings("CrystalBuilderTest", f"Keep{tmp_path.name}")
    settings.set_default_bond_rules({"scale": 1.25})
    monkeypatch.setattr(BondRulesDialog, "exec",
                        lambda self: QDialog.Rejected)

    assert BondRulesDialog.edit_defaults(settings) is False
    assert settings.default_bond_rules()["scale"] == pytest.approx(1.25)
    settings.set_default_bond_rules(None)


def _accepting(original, scale, remember=False):
    """A dialog that comes up already set the way the test wants."""
    def patched(self, document, parent=None):
        original(self, document, parent)
        self.scale.setValue(scale)
        self.remember.setChecked(remember)
    return patched


def _accepting_defaults(original, scale):
    """The same, for the form opened with no document."""
    def patched(self, document=None, parent=None, rules=None):
        original(self, document, parent, rules)
        self.scale.setValue(scale)
    return patched
