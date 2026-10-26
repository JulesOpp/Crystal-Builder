"""The nanotube builder as a module: xtal.modules.nanotube."""

import re

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
    """(10,10)'s diameter, its 40 atoms a period and its metallic
    character, as the report's rows.  A row renamed, misformatted or
    filled from the wrong field reads here as a wrong tube."""
    rows = {row.label: row for row in _run().report.tables[0].rows}
    assert rows["Diameter"].value == "13.56"
    assert rows["Atoms per period"].value == "40"
    assert rows["Electronic character"].value == "metallic (armchair)"


def test_an_unknown_element_is_a_failed_run_naming_it():
    """A typo in an element box is a failed run whose one sentence
    names what was typed.  Regressing, it is a traceback, or a
    refusal that does not say which box was wrong."""
    result = _run(element_a="Xx")
    assert not result.ok
    assert "'Xx' is not an element" in result.message


def test_a_tube_too_thin_is_a_failed_run():
    """(2,0) brings atoms across the tube within bonding distance;
    the build's refusal must come back as a failed run, not an
    exception that takes the run down."""
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


def _longest(message):
    """The length a refusal names as the longest that fits."""
    found = re.search(r"(\d+) A,? is the longest that fits", message)
    assert found, message
    return float(found.group(1))


def test_a_periodic_refusal_names_a_length_that_is_not_refused():
    """(120,5) at 2000 A is over the hard limit, and the length the
    sentence names must build when asked for.  A periodic tube is
    whole periods, rounded: naming the continuous length that fits
    gave 1738 A, which rounds up to 17 periods and is refused
    again."""
    recipe = Recipe(120, 5, length=2000.0)
    verdict = limits.check_nanotube(recipe, limits.STANDARD)
    assert verdict.refused
    longest = _longest(verdict.sentence)
    retry = Recipe(120, 5, length=longest)
    assert not limits.check_nanotube(retry, limits.STANDARD).refused


def test_a_finite_refusal_names_a_length_not_a_period():
    """A finite tube needs no whole period, so a chiral tube whose
    period alone is over the limit still fits at some length.
    (200,199)'s period is about 477,000 atoms; the sentence said
    "one period alone", as though nothing of that chirality could be
    built, when about 600 A of it can."""
    recipe = Recipe(200, 199, ends="capped", length=2000.0)
    verdict = limits.check_nanotube(recipe, limits.STANDARD)
    assert verdict.refused
    assert "one period alone" not in verdict.sentence
    longest = _longest(verdict.sentence)
    retry = Recipe(200, 199, ends="capped", length=longest)
    assert not limits.check_nanotube(retry, limits.STANDARD).refused


def test_a_build_over_the_soft_limit_still_builds_and_says_so(
        tmp_path):
    """(100,100) periodic at 400 A is about 65,000 atoms: over the
    50,000 that is comfortable, under the 200,000 refused.  It must
    build, and the warning must reach the status bar and the run's
    log -- a warning only the status bar saw is gone in four
    seconds, and one that stopped the build is a refusal."""
    from xtal.modules import record
    from xtal.workspace import Workspace

    module, action = MODULES.find("nanotube.build")
    params = action.coerce({"n": 100, "m": 100, "length": 400.0})
    entry = Workspace.create(tmp_path / "ws").add_document(module.label)
    folder = record.open_run(entry, module, action, params)
    said = []
    result = action.run(Job(params=params, folder=folder,
                            on_progress=said.append))
    record.close_run(folder, result)
    assert result.ok, result.message
    assert len(result.structure.sites) > 50_000
    warning = [line for line in said if "comfortable" in line]
    assert warning, said
    assert warning[0] in (folder.path / "run.log").read_text()


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
    """A periodic tube's count is atoms a period times periods, with
    nothing to guess.  If it drifts from the build, the size check
    warns or refuses tubes on a number that is not theirs."""
    from xtal.nanotube import build
    recipe = Recipe(n, m, length=50.0)
    assert limits.nanotube_atoms(recipe) == len(
        build.build(recipe).structure.sites)


@pytest.mark.parametrize("n, m, ends, length", [
    (10, 10, "capped", 20.0), (10, 0, "bare", 57.3),
    (6, 5, "capped", 20.0), (15, 15, "bare", 10.0),
    (3, 7, "capped", 120.0), (40, 39, "capped", 5.0)])
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
