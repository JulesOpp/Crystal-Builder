"""Sizes estimated before they are built, and the profile that decides.

Each estimate is arithmetic so that it can be made before the thing
it estimates; if it drifts from what is built, a limit protects
nothing, so the estimates are held to the real counts here.
"""

from pathlib import Path

import numpy as np
import pytest

from xtal.analysis import grid
from xtal.commands import cell as cell_commands
from xtal.core import limits, p1, supercell
from xtal.io.cif_reader import read_cif

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


@pytest.fixture(scope="module")
def mfu4l():
    return read_cif(SAMPLES / "MFU4l.cif")


@pytest.mark.parametrize("name", ["rutile", "mfu4l"])
def test_each_estimate_is_arithmetic_and_matches_what_is_built(
        name, request):
    """A supercell's count is exact, a grid's is its shape, and a
    picture's is the atoms times the volume of its range."""
    structure = request.getfixturevalue(name)
    n = p1.expand(structure).n_atoms
    built = supercell.supercell(structure, 2, 1, 1)
    assert limits.supercell_atoms(n, (2, 1, 1)) == p1.expand(built).n_atoms
    p = [[1, 1, 0], [-1, 1, 0], [0, 0, 1]]
    assert limits.supercell_atoms(n, p) == \
        p1.expand(supercell.transform_cell(
            structure, np.array(p, float))).n_atoms
    assert limits.grid_points(structure.lattice, 0.5) == \
        grid.distance_grid(structure, lambda _e: 1.0, 0.5).size
    assert limits.drawn_atoms(n, [(0, 2), (0, 1), (-0.5, 0.5)]) == 2 * n


def test_the_sentence_names_the_largest_size_that_fits(mfu4l):
    """A refusal is worth something only if it says what to ask for
    instead -- and what it names must itself pass."""
    n = p1.expand(mfu4l).n_atoms                       # 648
    verdict = limits.check_supercell(n, (8, 8, 8))
    assert verdict.refused
    assert "6 x 6 x 6 is the largest that fits" in verdict.sentence
    assert not limits.check_supercell(n, (6, 6, 6)).refused

    verdict = limits.check_grid(mfu4l.lattice, 0.15)
    assert verdict.refused
    spacing = float(verdict.sentence.split("at ")[1].split(" A")[0])
    assert not limits.check_grid(mfu4l.lattice, spacing).refused
    assert limits.check_grid(mfu4l.lattice, spacing - 0.05).refused


def test_between_the_limits_it_asks_and_below_it_says_nothing(mfu4l):
    n = p1.expand(mfu4l).n_atoms
    assert limits.check_supercell(n, (2, 2, 2)).level == limits.OK
    assert limits.check_supercell(n, (2, 2, 2)).sentence == ""
    verdict = limits.check_supercell(n, (5, 5, 5))      # 81 000
    assert verdict.warned and not verdict.refused
    assert "4 x 4 x 4" in verdict.sentence


def test_warn_only_never_refuses(mfu4l):
    n = p1.expand(mfu4l).n_atoms
    verdict = limits.check_supercell(n, (20, 20, 20), limits.WARN_ONLY)
    assert verdict.warned and not verdict.refused
    assert not limits.check_drawn(n, [(0, 20)] * 3,
                                  limits.WARN_ONLY).refused
    assert not limits.check_grid(mfu4l.lattice, 0.05,
                                 limits.WARN_ONLY).refused


def test_generous_doubles_every_limit():
    for budget, (soft, hard) in limits.BUDGETS.items():
        assert limits.bounds(budget, limits.GENEROUS) == \
            (2 * soft, 2 * hard)


def test_the_profile_set_is_the_one_applied_and_nonsense_is_standard(
        mfu4l):
    n = p1.expand(mfu4l).n_atoms
    limits.use(limits.WARN_ONLY)
    assert not limits.check_supercell(n, (8, 8, 8)).refused
    limits.use("enormous")
    assert limits.current() == limits.STANDARD
    assert limits.check_supercell(n, (8, 8, 8)).refused


def test_a_supercell_over_the_hard_limit_is_refused_by_the_command(
        mfu4l, monkeypatch):
    """In the command, so an agent and the CLI meet it too -- and
    refused before anything is built, which is the whole point."""
    def built(*_args):
        pytest.fail("built before it was counted")

    monkeypatch.setattr(supercell, "supercell", built)
    monkeypatch.setattr(supercell, "transform_cell", built)
    for command in (cell_commands.Supercell(8, 8, 8),
                    cell_commands.TransformCell(np.diag([8, 8, 8]))):
        new, report = command.preview(mfu4l)
        assert new is mfu4l
        assert not report.ok
        assert report.code == "SIZE_LIMIT"
        assert "6 x 6 x 6" in report.message


def test_an_agent_is_told_size_limit_and_nothing_is_pushed(mfu4l):
    from xtal.agent import Session
    session = Session(mfu4l)
    answer = session.supercell(8, 8, 8)
    assert not answer.ok
    assert answer.diagnostics[0].code == "SIZE_LIMIT"
    assert not session.undo().ok
