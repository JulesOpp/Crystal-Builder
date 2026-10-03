"""The disordered-carbon builder as a module: xtal.modules.carbon."""

import pytest

from xtal.core import bonding
from xtal.modules import MODULES, Job
from xtal.modules import carbon as carbon_module

#: One dia cell, unrelaxed: a build in about a second.
SMALL = {"repeat": "1", "relax": "none"}


def _run(**changes):
    _module, action = MODULES.find("carbon.build")
    params = dict(SMALL)
    params.update(changes)
    return action.run(Job(params=action.coerce(params)))


def test_the_carbon_builder_needs_no_structure():
    """A builder: listed with the others, asking for no open structure,
    and returning one -- with its bonds stated, so nothing perceives
    them when the tab opens."""
    _module, action = MODULES.find("carbon.build")
    assert action.needs_structure is False
    assert action.kind == "build"
    result = _run()
    assert result.ok, result.message
    structure = result.structure
    assert structure.perceived is not None
    assert len(bonding.graph(structure).bonds) == len(
        structure.perceived.bonds)
    titles = [t.title for t in result.report.tables]
    assert titles == ["What was built", "Topology"]
    assert result.report.histograms[0].title == "Rings"


def test_a_net_that_cannot_be_followed_is_a_failed_run_naming_it():
    result = _run(net="nonesuch")
    assert not result.ok
    assert "nonesuch" in result.message


def test_a_repeat_that_is_not_three_counts_is_a_failed_run():
    result = _run(repeat="2x2")
    assert not result.ok
    assert "2x2" in result.message


@pytest.mark.parametrize("text, expected", [("2x2x2", (2, 2, 2)),
                                            ("2", (2, 2, 2)),
                                            ("1 2 3", (1, 2, 3)),
                                            ("1,1,2", (1, 1, 2))])
def test_a_repeat_is_read_the_ways_people_write_it(text, expected):
    assert carbon_module.parse_repeat(text) == expected


def test_xtal_run_carbon_build_writes_a_structure_and_a_report(
        tmp_path, capsys):
    """``xtal run carbon.build`` files the carbon as an entry of its
    own, exactly as the window does, and prints the report."""
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "carbon.build", "-p", "repeat=1", "-p",
                 "relax=none", "--workspace", str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "What was built" in out
    assert "Carbon density" in out
    cifs = [p for p in workspace.rglob("*.cif")
            if ".autosave" not in p.parts]
    assert len(cifs) == 1
    from xtal.io.cif_reader import read_cif
    again = read_cif(cifs[0])
    assert {s.element for s in again.sites} >= {"C", "F"}
