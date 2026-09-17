"""Preferences: applied as they are changed, and read back later.

The settings this window edits all existed; several could be reached
from nowhere.  So most of what is worth asserting is the round trip --
a control moved here writes the preference, and the thing that reads
that preference does what it now says.

The dialog is built directly rather than through ``show_preferences``:
``QDialog.exec`` is patched to raise in this suite, and a modal loop is
not what any of this is about.  ``MainWindow.preferences_dialog``
exists so the wiring can be had without the loop.
"""

import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.core import bonding  # noqa: E402
from xtalapp import external, extras, menus  # noqa: E402
from xtalapp.dialogs.preferences import PreferencesDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import (  # noqa: E402
    AppSettings,
    built_in_workspace_root,
)


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.preview_interval_ms = 50


@pytest.fixture
def settings(tmp_path):
    return AppSettings("CrystalBuilderTest", f"Prefs{tmp_path.name}")


@pytest.fixture
def window(qtbot, tmp_path, settings):
    settings.clear_window()
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def dialog(qtbot, settings):
    d = PreferencesDialog(settings)
    qtbot.addWidget(d)
    return d


# -- the entry ---------------------------------------------------------

def test_preferences_is_reachable_and_says_where_it_belongs(window):
    """macOS moves this entry into the application menu, by its role.
    Asserting the role and not the menu is the point: the other test
    passes on Linux CI and fails on macOS."""
    action = window.actions_["preferences"]

    assert action.menuRole() == QAction.MenuRole.PreferencesRole
    assert action.shortcut().toString() in ("Ctrl+,", "Meta+,")


# -- the shell ---------------------------------------------------------

def test_the_pages_are_a_list_and_a_stack(dialog):
    """Not a tab bar: the pages this grows to would elide their own
    labels in one."""
    titles = [dialog.list.item(i).text()
              for i in range(dialog.list.count())]

    assert titles == ["General", "View defaults", "Bonding", "Engines"]
    assert dialog.stack.count() == len(titles)


def test_choosing_a_page_shows_it(dialog):
    dialog.show_page("View defaults")

    assert dialog.current_page() is dialog.page("View defaults")


# -- Saving ------------------------------------------------------------

def test_overwriting_without_asking_is_the_default(settings):
    """A box on every Ctrl+S trains the reflex it was added to
    interrupt."""
    assert settings.confirm_overwrite is False


def test_the_confirm_checkbox_is_stored_as_it_is_ticked(dialog,
                                                        settings):
    page = dialog.page("General")

    page.confirm_overwrite.setChecked(True)

    assert settings.confirm_overwrite is True


# -- General -----------------------------------------------------------

def test_the_default_workspace_folder_is_no_longer_hard_coded(
        dialog, settings, tmp_path):
    page = dialog.page("General")

    page.workspace_root.setText(str(tmp_path / "Runs"))

    assert settings.default_workspace_root == tmp_path / "Runs"


def test_emptying_the_workspace_folder_goes_back_to_the_built_in(
        dialog, settings):
    page = dialog.page("General")
    page.workspace_root.setText("/somewhere/else")

    page.workspace_root.setText("")

    assert (settings.default_workspace_root
            == built_in_workspace_root())


def test_clearing_the_recent_files_empties_them_and_says_so(
        dialog, settings, tmp_path, rutile):
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    settings.add_recent_file(path)
    page = dialog.page("General")
    page._show_recent_count()
    assert "1 recent file" in page.recent_label.text()

    page._clear_recent()

    assert settings.recent_files() == []
    assert "No recent files" in page.recent_label.text()


# -- View defaults -----------------------------------------------------

def test_the_style_a_new_structure_opens_as_is_stored(dialog, settings):
    page = dialog.page("View defaults")

    page.style.setCurrentIndex(page.style.findData("spacefill"))

    assert settings.default_view()["style"] == "spacefill"


def test_the_background_a_new_structure_opens_on_is_stored(
        dialog, settings):
    page = dialog.page("View defaults")

    page.background.setCurrentIndex(page.background.findData("black"))

    assert settings.default_view()["background"] == (0, 0, 0)


def test_a_custom_background_already_stored_is_kept_as_an_entry(
        qtbot, settings):
    """The View menu used to write this default, so a colour picked
    there can be in the preferences already.  Replacing it with white
    because it is not one of the four named ones would be a setting
    changed by opening a window."""
    settings.set_default_view(background=(12, 34, 56))
    dialog = PreferencesDialog(settings)
    qtbot.addWidget(dialog)
    page = dialog.page("View defaults")

    assert page._chosen_background() == (12, 34, 56)
    assert page.background.currentText() == "Custom"


def test_the_new_structure_default_is_actually_applied(window, rutile,
                                                       tmp_path):
    """It was written and never read, so choosing a default did
    nothing at all to the next structure opened."""
    from xtal.io import write_cif
    window.settings.set_default_view(style="spacefill",
                                     background=(0, 0, 0))
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)

    document = window.open_path(path)

    assert document.view.style == "spacefill"
    assert tuple(document.view.background) == (0, 0, 0)


def test_a_project_keeps_the_view_it_was_saved_with(window, rutile,
                                                    tmp_path):
    """A default is what a *new* document starts as.  A project brings
    its own view and the preference must not overwrite it."""
    document = window.new_document()
    document.structure = rutile
    document.update_view(style="wireframe")
    path = document.save(tmp_path / "session.xtalproj")
    window.close_document(0)
    window.settings.set_default_view(style="spacefill")

    reopened = window.open_path(path)

    assert reopened.view.style == "wireframe"


def test_the_view_menu_no_longer_decides_the_default(window, rutile,
                                                     tmp_path):
    """Choosing a style acted on this document and silently recorded a
    default for the next one, saying nothing about the second half."""
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    window.open_path(path)
    before = window.settings.default_view()

    window.set_style("spacefill")
    window.set_background("black")

    assert window.current_document().view.style == "spacefill"
    assert window.settings.default_view() == before


# -- Bonding -----------------------------------------------------------

def test_the_bonding_page_says_what_the_defaults_are(dialog,
                                                     settings):
    """Editing them is a dialog; saying what they are now is what a
    page owes, and it must not need one opened to answer."""
    settings.set_default_bond_rules(None)
    page = dialog.page("Bonding")
    page._show_defaults()

    assert "built-in" in page.summary.text()
    assert not page.reset.isEnabled()


def test_a_stored_default_is_described_rather_than_named(qtbot,
                                                         settings):
    settings.set_default_bond_rules(
        {"scale": 1.4, "allow_metal_metal": True,
         "forbidden": ["O-O"]})
    dialog = PreferencesDialog(settings)
    qtbot.addWidget(dialog)
    page = dialog.page("Bonding")

    assert "1.4" in page.summary.text()
    assert "metal-metal bonds allowed" in page.summary.text()
    assert "1 element pair(s) named" in page.summary.text()
    assert page.reset.isEnabled()
    settings.set_default_bond_rules(None)


def test_the_defaults_can_be_put_back_to_the_built_in_ones(qtbot,
                                                           settings):
    settings.set_default_bond_rules({"scale": 1.4})
    dialog = PreferencesDialog(settings)
    qtbot.addWidget(dialog)

    dialog.page("Bonding")._reset_defaults()

    assert settings.default_bond_rules() == {}


def test_editing_the_defaults_needs_no_structure(dialog, settings,
                                                 monkeypatch):
    """The whole point of the page: this was previously reachable only
    from the Bond Rules dialog opened on a document."""
    from PySide6.QtWidgets import QDialog

    from xtalapp.dialogs.bond_rules import BondRulesDialog
    settings.set_default_bond_rules(None)
    monkeypatch.setattr(BondRulesDialog, "exec",
                        lambda self: QDialog.Accepted)
    page = dialog.page("Bonding")

    page._edit_defaults()

    assert settings.default_bond_rules()["scale"] == pytest.approx(
        bonding.DEFAULT_SCALE)
    settings.set_default_bond_rules(None)


def test_bonds_following_the_geometry_is_the_menu_s_own_setting(
        window, rutile, tmp_path):
    """One setting in two places: the page must tick the menu entry
    and reach the documents that are already open, which is what the
    action's own slot does."""
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    document = window.open_path(path)
    dialog = window.preferences_dialog()

    dialog.page("Bonding").follow.setChecked(True)

    assert window.settings.bonds_follow_geometry is True
    assert window.actions_["bonds_follow"].isChecked()
    assert document.bonds_follow_geometry is True


# -- Engines -----------------------------------------------------------

def _fake_binary(directory, name="network"):
    """Something shutil.which will say yes to."""
    import stat
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP
               | stat.S_IXOTH)
    return path


def test_a_path_typed_here_is_stored_and_reported(dialog, settings,
                                                  tmp_path):
    binary = _fake_binary(tmp_path)
    page = dialog.page("Engines")

    page.fields["tools/zeopp"].setText(str(binary))

    assert settings.path_setting("tools/zeopp") == str(binary)
    assert "Found at" in page.status["tools/zeopp"].text()


def test_naming_a_binary_lights_up_its_module_without_a_restart(
        window, tmp_path, monkeypatch):
    """SHELL.md's own test for this step, and the reason the hints are
    pushed again every time the Modules menu opens."""
    from xtal.modules import zeopp
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.delenv(zeopp.PROGRAM.env_var, raising=False)
    menus.refresh_module_availability(window)
    assert not window._module_submenus["zeopp"].isEnabled()
    dialog = window.preferences_dialog()

    dialog.page("Engines").fields["tools/zeopp"].setText(
        str(_fake_binary(tmp_path)))

    assert window._module_submenus["zeopp"].isEnabled()


def test_a_path_that_is_wrong_is_named_rather_than_reddened(
        dialog, settings, tmp_path, monkeypatch):
    from xtal.modules import zeopp
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.delenv(zeopp.PROGRAM.env_var, raising=False)
    page = dialog.page("Engines")

    page.fields["tools/zeopp"].setText(str(tmp_path / "typo"))

    assert "typo" in page.status["tools/zeopp"].text()
    assert "Not found" in page.status["tools/zeopp"].text()


def test_the_parameter_folder_becomes_the_run_form_s_default(
        window, tmp_path):
    """Set once here instead of typed on every run.  Into an empty
    field only: what somebody typed for this run is this run's."""
    dialog = window.preferences_dialog()

    dialog.page("Engines").fields[
        external.SLATER_KOSTER].setText(str(tmp_path))

    form = window.dftb_dock.engine_forms["dftb"]
    assert form.values()["parameter_directory"] == str(tmp_path)


def test_a_directory_typed_for_this_run_is_not_overwritten(window,
                                                           tmp_path):
    form = window.dftb_dock.engine_forms["dftb"]
    form.set_values({"parameter_directory": "/typed/for/this/run"})
    dialog = window.preferences_dialog()

    dialog.page("Engines").fields[
        external.SLATER_KOSTER].setText(str(tmp_path))

    assert form.values()["parameter_directory"] == "/typed/for/this/run"


def test_every_tool_and_extra_has_a_row_on_the_engines_page(dialog):
    """One page for "why is this greyed out", so nothing that can grey
    an entry out may be missing from it -- and every program on it can
    be run from it."""
    page = dialog.page("Engines")

    assert set(page.fields) == {tool.key for tool in external.TOOLS}
    assert set(page.rows) == {extra.package for extra in extras.EXTRAS}
    assert set(page.tests) == (
        {p.setting for p in external.PROGRAMS}
        | {extra.package for extra in extras.EXTRAS})


#: A program that takes longer to answer than the test waits.  This
#: interpreter rather than /bin/sleep, which Windows does not have.
SLEEPS = [sys.executable, "-c", "import time; time.sleep(5)"]


def _answering(page, monkeypatch, argv, **kwargs):
    from xtal.modules import probe
    asked = probe.Probe(tuple(argv), **kwargs)
    monkeypatch.setattr(page, "_probe", lambda _key: asked)
    return asked


def test_a_test_button_reports_what_the_program_printed(
        qtbot, dialog, monkeypatch):
    page = dialog.page("Engines")
    _answering(page, monkeypatch,
               [sys.executable, "-c", "print('DFTB+ release 24.1')"])

    page.tests["tools/dftb"].click()

    result = page.results["tools/dftb"]
    qtbot.waitUntil(lambda: not page.is_testing("tools/dftb"),
                    timeout=5000)
    assert result.text() == "DFTB+ release 24.1"
    assert not result.isHidden()
    assert page.tests["tools/dftb"].isEnabled()


def test_a_test_button_is_disabled_while_its_probe_runs(
        qtbot, dialog, monkeypatch):
    """Blender takes three seconds to say its version, and a second
    press in that time would start a second Blender."""
    page = dialog.page("Engines")
    _answering(page, monkeypatch, SLEEPS)

    page.test("tools/blender")

    assert page.is_testing("tools/blender")
    assert not page.tests["tools/blender"].isEnabled()
    assert page.tests["tools/zeopp"].isEnabled()
    dialog.done(0)
    assert not page.is_testing("tools/blender")
    assert page.tests["tools/blender"].isEnabled()


def test_a_probe_that_does_not_answer_is_stopped_and_says_so(
        qtbot, dialog, monkeypatch):
    page = dialog.page("Engines")
    _answering(page, monkeypatch, SLEEPS, timeout=0.2)

    page.test("tools/xtb")

    qtbot.waitUntil(lambda: not page.is_testing("tools/xtb"),
                    timeout=5000)
    assert "did not answer within 0.2 s" in page.results[
        "tools/xtb"].text()


def test_a_program_that_is_not_there_is_not_run(dialog, settings,
                                                tmp_path, monkeypatch):
    from xtal.ff.xtb import calculator as xtb
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv(xtb.XTB.env_var, raising=False)
    page = dialog.page("Engines")

    page.test("tools/xtb")

    assert not page.is_testing("tools/xtb")
    assert "nothing to run" in page.results["tools/xtb"].text()


# -- what has to reach further than the next session --------------------

def test_a_new_redraw_rate_reaches_the_documents_already_open(
        window, rutile, tmp_path):
    """From the run panel, which is now the only control: the rate
    has to reach every open viewport and the other panel's combo."""
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    window.open_path(path)
    combo = window.ff_dock.redraw

    combo.setCurrentIndex(combo.findData(200))

    assert window.settings.preview_interval == 200
    assert window.current_viewport().preview_interval_ms == 200
    assert window.dftb_dock.redraw.currentData() == 200


def test_preferences_has_no_second_redraw_control(dialog):
    """Two controls for one setting, one of them in a window nobody
    has open while a run is going."""
    from PySide6.QtWidgets import QComboBox

    from xtalapp.docks.ff_panel import REDRAW_RATES
    labels = {label for label, _value in REDRAW_RATES}
    for page in dialog.pages:
        assert not hasattr(page, "redraw")
        for combo in page.findChildren(QComboBox):
            entries = {combo.itemText(i) for i in range(combo.count())}
            assert not entries & labels, page.TITLE
    assert not hasattr(dialog, "previewIntervalChanged")


def test_clearing_the_recent_files_rebuilds_the_menu(window, tmp_path,
                                                     rutile):
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    window.open_path(path)
    assert any(path.name in a.text()
               for a in window.recent_menu.actions())
    dialog = window.preferences_dialog()

    dialog.page("General")._clear_recent()

    assert not any(path.name in a.text()
                   for a in window.recent_menu.actions())


def test_resetting_the_layout_is_the_window_s_own_reset(window,
                                                        monkeypatch):
    """The same operation as Window > Reset layout, and that method --
    not a second copy of it that will drift."""
    done = []
    monkeypatch.setattr(window, "reset_layout",
                        lambda: done.append(True))
    dialog = window.preferences_dialog()

    dialog.page("General").layoutReset.emit()

    assert done == [True]
