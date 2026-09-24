"""The molecule builder as a registry entry, and what it will not do.

The build itself is :mod:`tests.test_build_molecule`; what is here is
the module declaration -- that the tree can grey it out cheaply, that
a bad string is a failed run rather than a crash, and that inserting
into the open cell is deliberately not an action.
"""

from __future__ import annotations

import pytest

from xtal import install
from xtal.build import MISSING, installed
from xtal.modules import MODULES, Job
from xtal.modules import build as build_module

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


def test_the_entry_is_registered_under_its_own_name():
    module, action = MODULES.find("build.molecule")
    assert module is build_module.BUILD
    assert action.needs_structure is False
    assert action.dialog == "build-molecule"


def test_without_rdkit_the_entry_greys_out_naming_the_extra(
        monkeypatch):
    monkeypatch.setattr(build_module, "installed", lambda: False)
    available = build_module.BUILD.availability()

    assert not available
    assert install.command("build") in available.reason


def test_inserting_into_the_open_cell_is_not_a_module_action():
    """It cannot be one.  A returned structure either replaces the
    open document or opens a new tab, and a paste into the framework
    that is already there is neither of those things."""
    assert [a.name for a in build_module.BUILD.actions] == ["molecule"]
    assert "insert" not in build_module.BUILD
    assert build_module.INSERT.shell == "insert_molecule"
    assert build_module.INSERT.params is build_module.PARAMS


def test_the_two_dialog_names_differ_so_one_class_can_tell_them_apart(
):
    """The dialog reads connection points off the action's name, so
    the two entries have to arrive as two different actions."""
    molecule = build_module.BUILD.action("molecule")
    assert molecule.dialog != build_module.INSERT.dialog
    assert molecule.name != build_module.INSERT.name


@needs_rdkit
def test_a_built_molecule_comes_back_as_a_structure_to_open():
    result = build_module.build_molecule(
        Job(params=build_module.BUILD.action("molecule").coerce(
            {"smiles": "c1ccccc1", "name": "benzene"})))

    assert result.ok
    assert "C6H6" in result.message
    assert result.structure is not None
    assert result.structure.space_group.is_p1
    assert result.structure.meta["title"] == "benzene"


@needs_rdkit
def test_a_molecule_built_here_may_carry_connection_points():
    """A tab of its own is where a building block is looked at before
    it is written, so ``*`` is allowed in this box and refused in the
    one that pastes into a cell."""
    result = build_module.build_molecule(
        Job(params={"smiles": "[*:1]c1ccccc1[*:2]"}))

    assert result.ok
    assert "2 connection point(s)" in result.message
    assert [s.element for s in result.structure.sites].count("X") == 2


@needs_rdkit
def test_a_string_that_is_not_a_molecule_fails_the_run_by_name():
    """A failed run says why in the log; a raised exception says it in
    a traceback nobody reads."""
    result = build_module.build_molecule(
        Job(params={"smiles": "not a molecule"}))

    assert not result.ok
    assert "not a molecule" in result.message


@needs_rdkit
def test_the_same_parameters_build_the_same_molecule_twice():
    """The seed is a parameter and has a default, so a saved
    parameter set rebuilds what it built before."""
    values = build_module.BUILD.action("molecule").defaults()
    values["smiles"] = "CCO"
    first = build_module.molecule_for(values, connection_points=False)
    second = build_module.molecule_for(values, connection_points=False)

    assert first.cart == pytest.approx(second.cart)
