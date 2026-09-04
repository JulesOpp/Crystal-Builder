"""Where other people's programs are, when there is no shell to say.

Zeo++, DFTB+ and the Slater-Koster sets are found through
``XTAL_ZEOPP``, ``XTAL_DFTB`` and ``DFTB_PREFIX``.  That is right in a
terminal and useless in a double-clicked application, which has no
shell to export one in -- so the paths are preferences, and
``xtalapp.external`` is the seam between a preference and a package
that must never read one.

The half with teeth is the status line.  A path field that goes red
says nothing anybody can act on; what was *tried* is the difference
between a five-minute fix and concluding the feature is broken.
"""

import os
import stat

import pytest

from xtal.ff.dftb import hsd
from xtal.modules import MODULES, process, zeopp
from xtalapp import external
from xtalapp.settings import AppSettings


@pytest.fixture
def settings(tmp_path):
    return AppSettings("CrystalBuilderTest", f"Tools{tmp_path.name}")


def fake_program(directory, name="network"):
    """Something ``shutil.which`` will say yes to."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP
               | stat.S_IXOTH)
    return path


def tool(key):
    return next(t for t in external.TOOLS if t.key == key)


# -- the hint, which is how a preference reaches xtal -------------------

def test_a_program_is_looked_for_where_the_preference_says(tmp_path):
    """``Program.setting`` has been declared since the module
    machinery was built and nothing ever filled it in."""
    binary = fake_program(tmp_path)
    process.set_hint(zeopp.PROGRAM.setting, binary)

    assert zeopp.PROGRAM.locate() == binary


def test_the_preference_beats_the_environment_variable(tmp_path,
                                                       monkeypatch):
    """The decision recorded in SHELL.md 1.5: a variable is what a
    shell set and a preference is what a person set on purpose -- and
    a packaged build has no shell to set the first one in."""
    from_shell = fake_program(tmp_path / "shell", "network")
    from_person = fake_program(tmp_path / "person", "network")
    monkeypatch.setenv(zeopp.PROGRAM.env_var, str(from_shell))
    process.set_hint(zeopp.PROGRAM.setting, from_person)

    assert zeopp.PROGRAM.locate() == from_person


def test_clearing_it_leaves_the_environment_variable_alone(tmp_path,
                                                           monkeypatch):
    from_shell = fake_program(tmp_path / "shell", "network")
    monkeypatch.setenv(zeopp.PROGRAM.env_var, str(from_shell))
    process.set_hint(zeopp.PROGRAM.setting, tmp_path / "gone")

    process.set_hint(zeopp.PROGRAM.setting, "")

    assert zeopp.PROGRAM.locate() == from_shell


def test_the_preferences_are_copied_in_one_call(tmp_path, settings):
    binary = fake_program(tmp_path)
    settings.set_path_setting(zeopp.PROGRAM.setting, binary)

    external.apply_hints(settings)

    assert process.hint_for(zeopp.PROGRAM.setting) == str(binary)
    assert zeopp.PROGRAM.locate() == binary


def test_a_named_binary_makes_the_module_available_again(
        tmp_path, settings, monkeypatch):
    """The whole point of the page: a path filled in makes a greyed
    out module run, without restarting anything."""
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.delenv(zeopp.PROGRAM.env_var, raising=False)
    assert not MODULES.get("zeopp").availability()

    settings.set_path_setting(zeopp.PROGRAM.setting,
                             fake_program(tmp_path))
    external.apply_hints(settings)

    assert MODULES.get("zeopp").availability()


# -- what the status line says -----------------------------------------

def test_it_says_where_it_found_it_and_which_answer_won(tmp_path,
                                                        settings):
    binary = fake_program(tmp_path)
    settings.set_path_setting(zeopp.PROGRAM.setting, binary)
    external.apply_hints(settings)

    ok, sentence = external.status(settings, tool("tools/zeopp"))

    assert ok
    assert str(binary) in sentence
    assert "set here" in sentence


def test_it_names_a_path_that_was_set_and_is_wrong(tmp_path, settings,
                                                   monkeypatch):
    """A path that is a typo looks exactly like one never set, and
    only one of the two is five seconds from working."""
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.delenv(zeopp.PROGRAM.env_var, raising=False)
    settings.set_path_setting(zeopp.PROGRAM.setting,
                              tmp_path / "not-here")
    external.apply_hints(settings)

    ok, sentence = external.status(settings, tool("tools/zeopp"))

    assert not ok
    assert "not-here" in sentence
    assert "on PATH" in sentence


def test_it_says_the_environment_variable_is_not_set(settings,
                                                     monkeypatch):
    """The sentence that saves the afternoon."""
    monkeypatch.setattr(zeopp, "bundled", lambda: None)
    monkeypatch.delenv(zeopp.PROGRAM.env_var, raising=False)

    ok, sentence = external.status(settings, tool("tools/zeopp"))

    assert not ok
    assert f"{zeopp.PROGRAM.env_var}, which is not set" in sentence
    assert zeopp.PROGRAM.url in sentence


def test_the_copy_that_ships_with_a_checkout_is_named_as_such(
        settings, monkeypatch):
    """It is real and it is found last, so saying "on PATH" about it
    would be wrong twice."""
    monkeypatch.setattr(zeopp, "bundled",
                        lambda: "/somewhere/resources/network")

    ok, sentence = external.status(settings, tool("tools/zeopp"))

    assert ok
    assert "ships with this source checkout" in sentence


# -- the two kinds of folder -------------------------------------------

def test_the_parameter_folder_is_read_before_the_variable(tmp_path,
                                                          settings):
    settings.set_path_setting(external.SLATER_KOSTER, tmp_path)

    ok, sentence = external.status(settings, tool(external.SLATER_KOSTER))

    assert ok
    assert str(tmp_path) in sentence


def test_a_parameter_folder_that_is_not_there_says_so(tmp_path,
                                                      settings):
    settings.set_path_setting(external.SLATER_KOSTER,
                              tmp_path / "nothing")

    ok, sentence = external.status(settings, tool(external.SLATER_KOSTER))

    assert not ok
    assert "is not a folder" in sentence


def test_with_nothing_set_it_names_the_variable_and_the_downloads(
        settings, monkeypatch):
    monkeypatch.setattr(hsd, "bundled", lambda: None)
    monkeypatch.delenv(hsd.ENV_VAR, raising=False)

    ok, sentence = external.status(settings, tool(external.SLATER_KOSTER))

    assert not ok
    assert hsd.ENV_VAR in sentence
    assert "dftb.org" in sentence


def test_a_block_folder_is_counted_rather_than_validated(tmp_path,
                                                         settings):
    (tmp_path / "one.xyz").write_text("1\n\nC 0 0 0\n")
    (tmp_path / "two.xyz").write_text("1\n\nC 0 0 0\n")
    settings.set_path_setting("mof/bb_dir", tmp_path)

    ok, sentence = external.status(settings, tool("mof/bb_dir"))

    assert ok
    assert "2 *.xyz file(s)" in sentence


def test_an_unset_block_folder_is_not_a_failure(settings):
    """PORMAKE ships 867 of them; this row is for a user's own."""
    ok, sentence = external.status(settings, tool("mof/bb_dir"))

    assert ok
    assert "PORMAKE's own database" in sentence


def test_the_environment_is_left_exactly_as_it_was(settings):
    """These are preferences, not exports: nothing here writes to the
    environment, which a subprocess would then inherit."""
    before = dict(os.environ)
    settings.set_path_setting(zeopp.PROGRAM.setting, "/tmp/network")
    external.apply_hints(settings)

    assert dict(os.environ) == before
