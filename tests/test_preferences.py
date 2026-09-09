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

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.core import bonding  # noqa: E402
from xtalapp import external, menus, samples  # noqa: E402
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

    assert titles == ["General", "View defaults", "Bonding",
                      "External tools", "Optional features"]
    assert dialog.stack.count() == len(titles)


def test_choosing_a_page_shows_it(dialog):
    dialog.show_page("View defaults")

    assert dialog.current_page() is dialog.page("View defaults")


# -- General -----------------------------------------------------------

def test_what_to_open_with_is_stored_as_it_is_chosen(dialog, settings):
    page = dialog.page("General")

    page.startup.setCurrentIndex(page.startup.findData("sample"))

    assert settings.startup_action == "sample"


def test_the_sample_row_only_matters_for_one_answer(dialog):
    page = dialog.page("General")

    page.startup.setCurrentIndex(page.startup.findData("empty"))
    assert not page.sample.isEnabled()

    page.startup.setCurrentIndex(page.startup.findData("sample"))
    assert page.sample.isEnabled()


def test_which_sample_to_open_with_is_stored(dialog, settings):
    page = dialog.page("General")

    page.sample.setCurrentIndex(page.sample.findData("zif8"))

    assert settings.startup_sample == "zif8"


def test_a_sample_that_no_longer_exists_reads_as_the_default(settings):
    """A name written by another version must not fail the launch."""
    settings.startup_sample = "a_sample_that_was_renamed"

    assert settings.startup_sample == "mof5"


def test_making_a_workspace_automatically_is_finally_reachable(
        dialog, settings):
    """It is read on every file that is opened and had no control at
    all."""
    page = dialog.page("General")

    page.auto_workspace.setChecked(True)

    assert settings.auto_workspace is True


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


# -- External tools ----------------------------------------------------

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
    page = dialog.page("External tools")

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

    dialog.page("External tools").fields["tools/zeopp"].setText(
        str(_fake_binary(tmp_path)))

    assert window._module_submenus["zeopp"].isEnabled()


def test_a_path_that_is_wrong_is_named_rather_than_reddened(
        dialog, settings, tmp_path, monkeypatch):
    from xtal.modules import zeopp
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.delenv(zeopp.PROGRAM.env_var, raising=False)
    page = dialog.page("External tools")

    page.fields["tools/zeopp"].setText(str(tmp_path / "typo"))

    assert "typo" in page.status["tools/zeopp"].text()
    assert "Not found" in page.status["tools/zeopp"].text()


def test_the_parameter_folder_becomes_the_run_form_s_default(
        window, tmp_path):
    """Set once here instead of typed on every run.  Into an empty
    field only: what somebody typed for this run is this run's."""
    dialog = window.preferences_dialog()

    dialog.page("External tools").fields[
        external.SLATER_KOSTER].setText(str(tmp_path))

    form = window.dftb_dock.engine_forms["dftb"]
    assert form.values()["parameter_directory"] == str(tmp_path)


def test_a_directory_typed_for_this_run_is_not_overwritten(window,
                                                           tmp_path):
    form = window.dftb_dock.engine_forms["dftb"]
    form.set_values({"parameter_directory": "/typed/for/this/run"})
    dialog = window.preferences_dialog()

    dialog.page("External tools").fields[
        external.SLATER_KOSTER].setText(str(tmp_path))

    assert form.values()["parameter_directory"] == "/typed/for/this/run"


# -- what has to reach further than the next session --------------------

def test_a_new_redraw_rate_reaches_the_documents_already_open(
        window, rutile, tmp_path):
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    window.open_path(path)
    dialog = window.preferences_dialog()
    page = dialog.page("View defaults")

    page.redraw.setCurrentIndex(page.redraw.findData(200))

    assert window.settings.preview_interval == 200
    assert window.current_viewport().preview_interval_ms == 200


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


# -- what the application opens with ------------------------------------

def test_by_default_it_still_opens_an_empty_window(window):
    assert window.settings.startup_action == "empty"
    assert window.open_at_startup() is None
    assert window.tabs.count() == 0


def test_it_can_open_the_file_from_last_time(window, rutile, tmp_path):
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    window.settings.add_recent_file(path)
    window.settings.startup_action = "recent"

    document = window.open_at_startup()

    assert document is not None
    assert document.path == path


def test_a_remembered_file_that_has_gone_opens_nothing(window,
                                                       tmp_path):
    """recent_files() filters what is no longer there, and a launch
    must not begin with a dialog about a file the user deleted."""
    window.settings.startup_action = "recent"

    assert window.open_at_startup() is None
    assert window.tabs.count() == 0


def test_it_can_open_a_sample_instead(window):
    """For somebody who has just installed this and owns no CIF."""
    window.settings.startup_action = "sample"
    window.settings.startup_sample = "zif8"

    document = window.open_at_startup()

    assert document is not None
    assert document.title == "ZIF-8"
    assert document.path is None


def test_the_startup_sample_is_one_of_the_ones_that_ship(window):
    known = [s.name for s in samples.SAMPLES]

    assert window.settings.startup_sample in known
