"""What is optional, what a build says about it, and the folder.

Two features are gated on a package this application does not install,
and each greys its menu entry out naming the extra to install -- which
is right on a source checkout and is advice about nothing in a
packaged build, where there is no environment to install into.

So the interesting behaviour is that the wording *changes*: these
tests drive both builds by faking ``sys.frozen``, because on this
machine only one of the two is ever the real one.

**There used to be a third, and it was the MOF builder.**  PORMAKE is
vendored now -- :mod:`xtal.mof.pormake` -- so the feature ships, it is
not on this page, and the box that offered two ways of having it
anyway is a general one about adding a package to a build with no pip.
"""

import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal import build as build_extra  # noqa: E402
from xtalapp import extras  # noqa: E402
from xtalapp.dialogs.preferences import PreferencesDialog  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return AppSettings("CrystalBuilderTest", f"Extras{tmp_path.name}")


@pytest.fixture
def dialog(qtbot, settings):
    widget = PreferencesDialog(settings)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def page(dialog):
    """The dialog is a fixture of its own so that it outlives this
    one: a page whose dialog has been collected is a deleted C++
    object, and the test that finds out says so in a traceback with no
    Python in it."""
    return dialog.page("Engines")


def extra(package):
    return next(e for e in extras.EXTRAS if e.package == package)


def frozen_build(monkeypatch, on=True):
    """A packaged build, as PyInstaller leaves it."""
    monkeypatch.setattr(sys, "frozen", on, raising=False)


# -- what each build says ----------------------------------------------

def test_a_checkout_says_what_to_install(monkeypatch):
    monkeypatch.setattr(build_extra, "installed", lambda: False)

    ok, sentence = extras.status(extra("rdkit"))

    assert not ok
    assert "pip install 'crystal-builder[build]'" in sentence


def test_a_bundle_never_says_pip_install(monkeypatch):
    """There is no environment to install into: the bundled
    interpreter is not on the user's PATH and has no pip.  Saying it
    anyway would be a polished way of saying something untrue."""
    frozen_build(monkeypatch)
    monkeypatch.setattr(build_extra, "installed", lambda: False)

    ok, sentence = extras.status(extra("rdkit"))

    assert not ok
    assert "pip" not in sentence


def test_a_bundled_feature_that_is_missing_is_a_fault_not_a_choice(
        monkeypatch):
    """RDKit is bundled deliberately.  If it is not importable in a
    build that carries it, the honest answer is not "install it"."""
    frozen_build(monkeypatch)
    monkeypatch.setattr(build_extra, "installed", lambda: False)

    ok, sentence = extras.status(extra("rdkit"))

    assert not ok
    assert "fault in the build" in sentence
    assert "pip" not in sentence


def test_a_bundle_says_a_working_feature_came_with_it(monkeypatch):
    frozen_build(monkeypatch)
    monkeypatch.setattr(build_extra, "installed", lambda: True)

    ok, sentence = extras.status(extra("rdkit"))

    assert ok
    assert "included in this build" in sentence


def test_nothing_on_the_page_is_left_out_of_a_build_any_more():
    """The product decision in SHELL.md 3 was: bundle the small ones,
    and be honest about the one that is larger than the application.

    That one was PORMAKE, and vendoring it settled the question --
    every feature this page lists now ships.  The ``bundled`` field
    stays because :func:`extras.status` still needs to tell "missing
    from a build meant to carry it", which is a fault, apart from
    "deliberately left out"; this is what fails if a row is added and
    the page starts making promises a build does not keep.
    """
    assert extras.EXTRAS
    assert [e.package for e in extras.EXTRAS if not e.bundled] == []
    assert "pormake" not in {e.package for e in extras.EXTRAS}


def test_the_check_is_each_feature_s_own():
    """One answer to "is RDKit here" in the application, not a second
    one that can drift from the first."""
    from xtal.build import installed as rdkit_installed

    assert extra("rdkit").installed() == rdkit_installed()


# -- the folder that goes on sys.path -----------------------------------

def test_the_folder_is_not_created_by_asking_where_it_is(tmp_path,
                                                         monkeypatch):
    """An empty folder appearing in somebody's Application Support
    without them doing anything is the same discourtesy as a workspace
    made behind their back."""
    monkeypatch.setenv(extras.DIR_VAR, str(tmp_path / "packages"))

    where = extras.folder()

    assert not where.exists()
    assert extras.folder(create=True).is_dir()


def test_a_folder_that_is_there_goes_first_on_the_path(tmp_path,
                                                       monkeypatch):
    """First, so a package installed into it wins over one of the same
    name inside the bundle -- which is the whole of what "add it to
    this copy" can mean."""
    where = tmp_path / "packages"
    where.mkdir()
    monkeypatch.setenv(extras.DIR_VAR, str(where))
    monkeypatch.setattr(sys, "path", list(sys.path))

    assert extras.add_to_path() == where
    assert sys.path[0] == str(where)


def test_a_folder_that_is_not_there_changes_nothing(tmp_path,
                                                    monkeypatch):
    monkeypatch.setenv(extras.DIR_VAR, str(tmp_path / "nothing"))
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = list(sys.path)

    assert extras.add_to_path() is None
    assert sys.path == before


def test_adding_it_twice_does_not_shadow_it_twice(tmp_path,
                                                  monkeypatch):
    where = tmp_path / "packages"
    where.mkdir()
    monkeypatch.setenv(extras.DIR_VAR, str(where))
    monkeypatch.setattr(sys, "path", list(sys.path))

    extras.add_to_path()
    extras.add_to_path()

    assert sys.path.count(str(where)) == 1


def test_the_command_names_the_folder_it_installs_into(tmp_path,
                                                       monkeypatch):
    monkeypatch.setenv(extras.DIR_VAR, str(tmp_path / "packages"))

    command = extras.target_command()

    assert str(tmp_path / "packages") in command
    assert command.startswith("pip install --target")


# -- the page ----------------------------------------------------------

def test_the_page_has_a_row_for_every_optional_feature(page):
    assert set(page.rows) == {e.package for e in extras.EXTRAS}


def test_the_folder_command_is_offered_with_its_warning(page):
    """The box used to offer two routes to a PORMAKE that was not in
    the bundle.  PORMAKE is vendored, so what is left is the one thing
    it always really was: how to add a package to a build with no pip,
    warned about in the same breath."""
    assert "pip install --target" in page.target_command.text()
    assert str(extras.folder()) in page.target_command.text()


def test_the_warning_about_route_two_is_on_the_page(page):
    """Not in a document nobody opens: --target works for pure Python
    and a compiled dependency has to match this build's ABI."""
    labels = [w.text() for w in page.findChildren(QWidget)
              if hasattr(w, "text") and isinstance(w.text(), str)]

    assert any(extras.TARGET_WARNING == text for text in labels)


def test_copying_a_command_puts_it_on_the_clipboard(page, qtbot):
    from PySide6.QtWidgets import QApplication

    page.target_command._copy()

    assert QApplication.clipboard().text() == extras.target_command()
