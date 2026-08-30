"""The undoable edits the force field produces.

The point of every one of these is that a calculation is not a change
until the user accepts it, and that when they do it is *one* change.
An optimisation that took two hundred steps has to leave one entry on
the undo stack, and Ctrl+Z after it has to give back the structure the
run started from -- not the second-to-last iteration, which is what a
command that read its own undo data at the wrong moment would do.
"""

import numpy as np
import pytest

from tests.conftest_ff import water
from xtal.commands import CommandStack, Host
from xtal.commands import ff as ff_commands
from xtal.ff import ENGINES, optimize


@pytest.fixture
def host(rutile):
    return Host(rutile)


def push(host, command):
    stack = getattr(host, "stack", None) or CommandStack()
    host.stack = stack
    stack.push(command, host)
    return stack


# ------------------------------------------------ optimised geometry

def test_an_optimisation_lands_as_one_undoable_step():
    structure = water(oh=1.15, angle=95.0)
    before = structure.frac.copy()
    calculator = ENGINES.build("uff", structure)
    result = optimize.run(calculator, structure, max_steps=200,
                          force_tolerance=1e-4)
    assert result.steps > 1

    host = Host(structure)
    stack = push(host, ff_commands.ApplyOptimizedGeometry.from_result(
        result))
    assert stack.depth == 1
    assert not np.allclose(host.structure.frac, before)

    stack.undo(host)
    assert np.allclose(host.structure.frac, before)
    stack.redo(host)
    assert np.allclose(host.structure.frac, result.frac)


def test_the_undo_data_can_be_supplied_by_a_caller_that_previewed():
    """The GUI draws every step, so by the time it commits, the
    structure already holds the final geometry.  A command that read
    its undo data from the structure then would undo to the answer."""
    structure = water(oh=1.15)
    origin = structure.frac.copy()
    target = origin + 0.01

    # Pretend the panel previewed its way to the answer already.
    for site, frac in zip(structure.sites, target, strict=True):
        site.frac = frac

    host = Host(structure)
    stack = push(host, ff_commands.ApplyOptimizedGeometry(
        target, before=origin))
    stack.undo(host)
    assert np.allclose(host.structure.frac, origin)


def test_two_optimisations_do_not_merge_into_one():
    """A move merges with the next move of the same atoms, which is
    right for dragging and wrong here: two relaxations are two things
    that happened, and collapsing them makes the first unreachable."""
    structure = water(oh=1.15)
    host = Host(structure)
    stack = push(host, ff_commands.ApplyOptimizedGeometry(
        structure.frac + 0.01))
    stack.push(ff_commands.ApplyOptimizedGeometry(
        structure.frac + 0.02), host)
    assert stack.depth == 2


def test_it_reports_how_far_the_furthest_atom_went():
    """The difference between a relaxation that tidied the geometry
    and one that rearranged the crystal, both of which report
    'converged'."""
    structure = water()
    shifted = structure.frac.copy()
    shifted[1] += np.array([0.1, 0.0, 0.0])     # 3 A in a 30 A box
    command = ff_commands.ApplyOptimizedGeometry(shifted)
    assert command.displacement(structure) == pytest.approx(3.0,
                                                            abs=1e-6)


def test_applying_a_stale_result_is_refused_rather_than_misapplied():
    """The structure can be edited while a run is in flight."""
    structure = water()
    command = ff_commands.ApplyOptimizedGeometry(np.zeros((9, 3)))
    with pytest.raises(ValueError, match="edited while"):
        command.do(Host(structure))


# ------------------------------------------------------ type overrides

def test_setting_a_type_is_undoable(host):
    stack = push(host, ff_commands.SetAtomTypes([0], "Ti3+4"))
    assert host.structure.sites[0].props["uff_type"] == "Ti3+4"
    stack.undo(host)
    assert "uff_type" not in host.structure.sites[0].props


def test_clearing_a_type_restores_what_was_there(host):
    host.structure.sites[0].props["uff_type"] = "Ti3+4"
    stack = push(host, ff_commands.SetAtomTypes([0], None))
    assert "uff_type" not in host.structure.sites[0].props
    stack.undo(host)
    assert host.structure.sites[0].props["uff_type"] == "Ti3+4"


def test_an_override_changes_what_the_calculator_uses(rutile):
    before = ENGINES.build("uff", rutile).types[0]
    rutile.sites[0].props["uff_type"] = "Ti3+4"
    rutile.touch()
    after = ENGINES.build("uff", rutile).types[0]
    assert before == "Ti6+4" and after == "Ti3+4"


# ------------------------------------------------------------ charges

def test_setting_charges_is_undoable(host):
    stack = push(host, ff_commands.SetCharges([0.8, -0.4]))
    assert [s.charge for s in host.structure.sites] == [0.8, -0.4]
    stack.undo(host)
    assert [s.charge for s in host.structure.sites] == [None, None]


def test_the_wrong_number_of_charges_is_refused(host):
    with pytest.raises(ValueError, match="for 2 sites"):
        ff_commands.SetCharges([0.1]).do(host)


# -------------------------------------------------- saving and loading

def test_an_override_survives_a_project_round_trip(rutile, tmp_path):
    """The plan asks for this explicitly, and a CIF has nowhere to put
    it: the project carries the site's props beside the crystal."""
    from xtal.io import read_project, write_project

    rutile.sites[0].props["uff_type"] = "Ti3+4"
    path = write_project(rutile, tmp_path / "r.xtalproj")
    restored, _view, _session = read_project(path)
    assert restored.sites[0].props["uff_type"] == "Ti3+4"
    assert ENGINES.build("uff", restored).types[0] == "Ti3+4"


def test_a_structure_with_no_overrides_writes_no_extra_part(
        rutile, tmp_path):
    import zipfile

    from xtal.io import write_project
    path = write_project(rutile, tmp_path / "plain.xtalproj")
    assert "sites.json" not in zipfile.ZipFile(path).namelist()


def test_a_props_entry_for_a_site_that_is_gone_is_dropped(rutile,
                                                          tmp_path):
    """The CIF part is the authority on what the sites are."""
    import json
    import zipfile

    from xtal.io import read_project, write_project

    path = write_project(rutile, tmp_path / "odd.xtalproj")
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("sites.json", json.dumps(
            {"props": {"0": {"uff_type": "Ti3+4"}, "99": {"x": 1}}}))
    restored, _view, _session = read_project(path)
    assert restored.sites[0].props["uff_type"] == "Ti3+4"
    assert restored.n_sites == 2
