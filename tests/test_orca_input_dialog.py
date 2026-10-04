"""The ORCA input dialog: the pickers, the preview, and a refusal
greying Write."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QDialogButtonBox, QWidget

from xtal.core.selection import Selection
from xtal.modules import MODULES
from xtalapp.dialogs import module_dialog
from xtalapp.dialogs.orca_input import OrcaInputDialog


class _Window(QWidget):
    def __init__(self, document):
        super().__init__()
        self._document = document

    def current_document(self):
        return self._document


@pytest.fixture
def make(qtbot, dry_ice):
    # Held here: qtbot keeps only a weak reference, and a window
    # collected mid-test deletes the dialog it parents.
    windows = []

    def build(selected=(), initial=None, structure=None):
        document = SimpleNamespace(
            structure=structure or dry_ice,
            selection=Selection(atoms=set(selected)),
            path=Path("/ws/dry ice/dry ice.cif"))
        window = _Window(document)
        qtbot.addWidget(window)
        windows.append(window)
        module, action = MODULES.find("orca.input")
        return OrcaInputDialog(module, action, window, initial)
    return build


def _write(dialog):
    return dialog.buttons.button(QDialogButtonBox.Ok)


def test_the_entry_names_this_dialog():
    _module, action = MODULES.find("orca.input")
    assert module_dialog(action.dialog) is OrcaInputDialog


def test_the_dialog_says_it_writes_input_and_never_runs_orca(make):
    """It looks like a front end; without this, somebody with no ORCA
    installed comes away thinking a calculation ran."""
    text = make().not_run.text()
    assert "does not run ORCA" in text
    assert "cited" in text


def test_the_dialog_links_the_orca_papers(make):
    """The two references ORCA's 6.1 manual asks for, followed in the
    browser rather than by the dialog."""
    sources = make().sources
    assert "https://doi.org/10.1002/wcms.81" in sources.urls()
    assert "https://doi.org/10.1002/wcms.70019" in sources.urls()
    assert sources.openExternalLinks()


def test_the_dialog_opens_on_bp86_def2_svp(make):
    dialog = make()
    assert dialog.functional.key() == "BP86"
    assert dialog.basis.key() == "def2-SVP"
    assert dialog.preview.toPlainText().splitlines()[1] == \
        "! BP86 def2-SVP"
    assert "88 electrons, singlet" in dialog.electrons.text()
    assert _write(dialog).isEnabled()


def test_searching_b3lyp_selects_the_hybrid_family(make):
    dialog = make()
    picker = dialog.functional
    line = next(line for line in picker._by_line
                if "\N{BLACK RIGHT-POINTING SMALL TRIANGLE} B3LYP " in line)
    picker._picked(line)
    assert picker.family.currentText() == "Global hybrid"
    assert picker.key() == "B3LYP"
    assert "! B3LYP def2-SVP" in dialog.preview.toPlainText()


def test_the_search_offers_matches_as_it_is_typed(make):
    """The completer's model was made inline with no owner, collected,
    and the search offered nothing -- the popup never opened.  A
    collection first, so a model held by nobody is gone by now."""
    import gc

    dialog = make()
    gc.collect()
    for picker, typed, expected in (
            (dialog.functional, "b3ly", "B3LYP"),
            (dialog.basis, "tzvpp", "def2-TZVPP")):
        picker.completer.setCompletionPrefix(typed)
        offered = [picker.completer.completionModel().index(row, 0).data()
                   for row in range(picker.completer.completionCount())]
        assert any(f" {expected} " in line or line.endswith(expected)
                   for line in offered), offered


def test_return_in_the_search_takes_an_exact_key(make):
    dialog = make()
    dialog.basis.search.setText("def2-tzvp")
    dialog.basis._entered()
    assert dialog.basis.key() == "def2-TZVP"
    assert dialog.basis.family.currentText() == "Karlsruhe def2"


def test_an_impossible_multiplicity_disables_write_and_says_why(make):
    dialog = make()
    dialog.multiplicity.setValue(2)
    assert not _write(dialog).isEnabled()
    assert "88 electrons need an odd multiplicity" in \
        dialog.problems.text()
    dialog.charge.setValue(1)
    assert _write(dialog).isEnabled()
    assert "87 electrons, doublet" in dialog.electrons.text()


def test_selected_only_is_disabled_with_nothing_selected(make):
    assert not make().selected_only.isEnabled()


def test_selected_only_writes_the_selection(make):
    dialog = make(selected=(0, 4, 5))
    assert dialog.selected_only.isEnabled()
    dialog.selected_only.setChecked(True)
    assert dialog.values()["atoms"] == "0 4 5"
    assert dialog.electrons.text().startswith("3 atoms")


def test_the_preview_follows_every_change(make):
    dialog = make()
    dialog.run.setCurrentIndex(dialog.run.findData("opt"))
    dialog.max_iter.setValue(200)
    dialog.freq.setChecked(True)
    dialog.scf_max_iter.setValue(300)
    text = dialog.preview.toPlainText()
    assert "! BP86 def2-SVP Opt Freq" in text
    assert "%geom\n  MaxIter 200\nend" in text
    assert "%scf\n  MaxIter 300\nend" in text
    assert text.rstrip().endswith(
        "*xyzfile 0 1 dry_ice_from_crystal_builder.xyz")
    dialog.tddft.setChecked(True)
    dialog.nroots.setValue(12)
    dialog.triplets.setChecked(True)
    text = dialog.preview.toPlainText()
    assert "%compound" in text
    assert "  %tddft\n    nroots 12\n    triplets true\n  end" in text


def test_the_route_is_asked_only_when_the_geometry_moves(make):
    """A single point has one TD-DFT; Opt or Freq has two, and IRoot
    belongs to the excited one alone."""
    dialog = make()
    dialog.tddft.setChecked(True)
    assert not dialog.tddft_state.isEnabled()
    dialog.run.setCurrentIndex(dialog.run.findData("opt"))
    assert dialog.tddft_state.isEnabled()
    assert dialog.tddft_state.currentData() == "ground"
    assert dialog.iroot.isHidden()
    dialog.functional.set_key("PBE0")
    dialog.tddft_state.setCurrentIndex(
        dialog.tddft_state.findData("excited"))
    assert not dialog.iroot.isHidden()
    dialog.iroot.setValue(2)
    text = dialog.preview.toPlainText()
    assert "%compound" not in text
    assert "  iroot 2\n" in text


def test_an_excited_state_bp86_cannot_follow_greys_write(make):
    dialog = make()
    dialog.tddft.setChecked(True)
    dialog.run.setCurrentIndex(dialog.run.findData("opt"))
    dialog.tddft_state.setCurrentIndex(
        dialog.tddft_state.findData("excited"))
    assert not _write(dialog).isEnabled()
    assert "cannot follow an excited state with BP86" in \
        dialog.problems.text()


def test_dispersion_greys_for_a_functional_that_has_its_own(make):
    dialog = make()
    assert dialog.dispersion.isEnabled()
    dialog.functional.set_key("WB97X-D3BJ")
    assert not dialog.dispersion.isEnabled()


def test_the_basis_greys_for_a_composite(make):
    dialog = make()
    dialog.functional.set_key("R2SCAN-3C")
    assert not dialog.basis.isEnabled()
    assert "! R2SCAN-3C\n" in dialog.preview.toPlainText()


def test_optimisation_settings_grey_for_a_single_point(make):
    dialog = make()
    assert not dialog.max_iter.isEnabled()
    dialog.run.setCurrentIndex(dialog.run.findData("optts"))
    assert dialog.max_iter.isEnabled() and dialog.calc_hess.isEnabled()
    assert not dialog.opt_level.isEnabled()


def test_a_solvent_is_found_by_an_alias(make):
    dialog = make()
    dialog.solvation.setCurrentIndex(dialog.solvation.findData("SMD"))
    dialog.solvent.setEditText("dmf")
    assert dialog.values()["solvent"] == "n,n-dimethylformamide"
    assert "SMD(n,n-dimethylformamide)" in dialog.preview.toPlainText()


def test_the_last_choices_come_back_but_not_the_atoms(make):
    first = make(selected=(0, 4, 5))
    first.functional.set_key("PBE0")
    first.selected_only.setChecked(True)
    first.tddft.setChecked(True)
    again = make(initial=first.values())
    assert again.functional.key() == "PBE0"
    assert again.tddft.isChecked()
    assert again.values()["atoms"] == ""


def test_the_values_are_the_modules_own(make):
    """The dialog substitutes the form and nothing else: every name it
    hands back is a parameter the run reads."""
    _module, action = MODULES.find("orca.input")
    assert set(make().values()) == {p.name for p in action.params}


def test_the_dialog_fits_a_laptop_screen(make):
    """A 1280x800 laptop less its menu bar: the form scrolls, the
    dialog does not run off the bottom."""
    dialog = make()
    assert dialog.sizeHint().height() <= 775
    assert dialog.minimumSizeHint().height() <= 775
    assert dialog.height() <= 775 and dialog.width() <= 1280
