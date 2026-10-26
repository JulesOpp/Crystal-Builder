"""The nanotube builder as a module: xtal.modules.nanotube."""

import pytest

from xtal.core import bonding, limits
from xtal.modules import MODULES, Job
from xtal.nanotube.build import Recipe


def _run(**changes):
    _module, action = MODULES.find("nanotube.build")
    return action.run(Job(params=action.coerce(changes)))


def test_the_nanotube_builder_needs_no_structure():
    """A builder: in the Build group, asking for no open structure,
    returning one with its bonds stated, and a report of what was
    built."""
    module, action = MODULES.find("nanotube.build")
    assert module.group == "build"
    assert action.needs_structure is False
    assert action.kind == "build"
    result = _run()
    assert result.ok, result.message
    structure = result.structure
    assert structure.perceived is not None
    assert len(bonding.graph(structure).bonds) == len(
        structure.perceived.bonds)
    assert [t.title for t in result.report.tables] == ["What was built"]
    assert "(10,10) nanotube" in result.message


def test_the_defaults_are_julius_s():
    """C on both sites at 1.42 A: Julius's own defaults.  Changing one
    is his decision, so a change here should be deliberate."""
    _module, action = MODULES.find("nanotube.build")
    values = action.coerce({})
    assert (values["element_a"], values["element_b"],
            values["bond"]) == ("C", "C", 1.42)


def test_the_report_says_size_period_and_character():
    rows = {row.label: row for row in _run().report.tables[0].rows}
    assert rows["Diameter"].value == "13.56"
    assert rows["Atoms per period"].value == "40"
    assert rows["Electronic character"].value == "metallic (armchair)"


def test_an_unknown_element_is_a_failed_run_naming_it():
    result = _run(element_a="Xx")
    assert not result.ok
    assert "'Xx' is not an element" in result.message


def test_a_tube_too_thin_is_a_failed_run():
    result = _run(n=2, m=0)
    assert not result.ok
    assert "within bonding distance" in result.message


def test_xtal_run_nanotube_build_writes_a_structure_and_a_report(
        tmp_path, capsys):
    """``xtal run nanotube.build`` files the tube as an entry of its
    own, as the window does, and prints the report."""
    from xtal.cli import main

    workspace = tmp_path / "ws"
    assert main(["run", "nanotube.build", "-p", "n=6", "-p", "m=5",
                 "-p", "ends=capped", "--workspace",
                 str(workspace)]) == 0
    out = capsys.readouterr().out
    assert "What was built" in out
    assert "Diameter" in out
    cifs = [p for p in workspace.rglob("*.cif")
            if ".autosave" not in p.parts]
    assert len(cifs) == 1


def test_a_tube_over_the_hard_limit_is_refused_before_it_is_built(
        monkeypatch):
    """(200,200) at 2000 A is about 650,000 atoms: refused before
    anything is rolled, naming the longest tube that fits."""
    from xtal.nanotube import build
    monkeypatch.setattr(build, "build", pytest.fail)
    result = _run(n=200, m=200, length=2000.0)
    assert not result.ok
    assert "longest that fits" in result.message


def test_an_assistant_builds_a_tube_through_session_build(tmp_path):
    """The MCP's way in to a builder, with nothing added to its API:
    Session.build files the tube in the workspace and hands back a
    session on it.  (6,5)'s period is 40.6 A, so 20 A rounds to one
    period of 364 atoms."""
    from xtal.agent.session import Session

    session = Session.build("nanotube.build", tmp_path / "ws", n=6, m=5)
    assert session.built.ok
    assert session.n_atoms == 364


@pytest.mark.parametrize("n, m", [(10, 10), (6, 5), (12, 3)])
def test_a_periodic_estimate_is_exact(n, m):
    from xtal.nanotube import build
    recipe = Recipe(n, m, length=50.0)
    assert limits.nanotube_atoms(recipe) == len(
        build.build(recipe).structure.sites)


@pytest.mark.parametrize("n, m, ends, length", [
    (10, 10, "capped", 20.0), (10, 0, "bare", 57.3),
    (6, 5, "capped", 20.0), (15, 15, "bare", 10.0),
    (3, 7, "capped", 120.0)])
def test_a_finite_estimate_is_an_upper_bound_within_the_edges(
        n, m, ends, length):
    """A refusal rests on this count, so it must not undercount.  It
    may overcount by the edges' worth, 6(n+m) at most: measured from
    (5,0) to (15,15) at 3 to 120 A."""
    from xtal.nanotube import build
    recipe = Recipe(n, m, ends=ends, length=length)
    built = len(build.build(recipe).structure.sites)
    estimate = limits.nanotube_atoms(recipe)
    assert built <= estimate <= built + 6 * (n + m)
