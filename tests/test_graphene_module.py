"""The graphene builder as a module: xtal.modules.graphene."""

from xtal.core import bonding
from xtal.modules import MODULES, Job


def _run(**changes):
    _module, action = MODULES.find("graphene.build")
    return action.run(Job(params=action.coerce(changes)))


def _rows(result):
    return {row.label: row for row in result.report.tables[0].rows}


def test_the_graphene_builder_needs_no_structure():
    """A builder in the Carbon builder submenu: asking for no open
    structure, returning one with its bonds stated."""
    module, action = MODULES.find("graphene.build")
    assert module.group == "build" and module.menu == "Carbon builder"
    assert action.needs_structure is False
    result = _run()
    assert result.ok, result.message
    structure = result.structure
    assert len(bonding.graph(structure).bonds) == len(
        structure.perceived.bonds) == 3
    assert result.message == "graphene, one layer: 2 atoms"


def test_the_report_says_the_cell_the_stacking_and_whence_the_spacing():
    rows = _rows(_run(element_a="B", element_b="N", layers=2,
                      stacking="AA'", stack="bulk"))
    assert rows["Composition"].value == "B2 N2"
    assert rows["Stacking"].value.startswith("AA'")
    assert rows["Layer spacing"].note == "h-BN's"
    assert rows["c"].value == "6.660"


def test_a_two_atom_cell_does_not_report_an_infinite_contact():
    assert _rows(_run())["Closest contact"].value == "--"
    assert _rows(_run(cells_a=3, cells_b=3))["Closest contact"].value \
        == "2.84"


def test_a_refusal_is_a_failed_run_naming_why():
    for changes, why in [({"layers": 3, "stack": "bulk"},
                          "multiple of 2"),
                         ({"element_a": "Qq"}, "'Qq' is not an element"),
                         ({"cells_a": 300, "cells_b": 300, "layers": 2},
                          "largest repeat that fits")]:
        result = _run(**changes)
        assert not result.ok
        assert why in result.message


def test_xtal_run_graphene_build_writes_a_structure_and_a_report(
        tmp_path, capsys):
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "graphene.build", "-p", "layers=2", "-p",
                 "stack=bulk", "--workspace", str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "What was built" in out and "AB graphene, bulk" in out
    cifs = [p for p in workspace.rglob("*.cif")
            if ".autosave" not in p.parts]
    assert len(cifs) == 1


def test_an_assistant_builds_a_sheet_through_session_build(tmp_path):
    from xtal.agent.session import Session

    session = Session.build("graphene.build", tmp_path / "ws",
                            cells_a=4, cells_b=4, layers=2)
    assert session.built.ok
    assert session.n_atoms == 64
