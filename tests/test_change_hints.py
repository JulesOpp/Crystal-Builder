"""Derived data survives the changes that did not touch it.

The application used to re-derive everything after every mutation:
moving one atom re-perceived every bond, re-typed every atom for the
force field, rebuilt the scene and repainted every panel.  On a large
asymmetric unit that cost more per optimiser step than the step.

These tests count calls rather than measure time.  A stopwatch in CI is
a flaky test; "the typer ran once during a twenty-step run" is the same
assertion and is not.
"""

import numpy as np
import pytest

from xtal.core import bonding, p1
from xtal.core.structure import CHANGE_FLAGS, CHEMISTRY, Change
from xtal.ff.uff import typer


class Counter:
    """Counts calls to a function, and passes them through."""

    def __init__(self, monkeypatch, module, name):
        self.calls = 0
        original = getattr(module, name)

        def wrapper(*args, **kwargs):
            self.calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(module, name, wrapper)


# ------------------------------------------------------------- the mask

def test_a_move_keeps_the_chemistry_and_drops_the_geometry(rutile):
    p1.expand(rutile)
    bonding.graph(rutile)
    typer.assign(rutile)
    keys = set(rutile._cache)

    rutile.touch(Change.POSITIONS)

    survived = set(rutile._cache)
    assert not any(k.startswith("p1:") for k in survived)
    assert {k for k in keys
            if k.startswith(("bonds:", "uff-typing"))} <= survived


@pytest.mark.parametrize("flag", CHANGE_FLAGS)
def test_every_flag_invalidates_exactly_what_it_should(rutile, flag):
    """The mask, enumerated.  A stale bond graph is not a rendering
    glitch, it is a wrong energy, so this is written out rather than
    trusted."""
    p1.expand(rutile)
    bonding.graph(rutile)
    typer.assign(rutile)

    rutile.touch(flag)
    survived = set(rutile._cache)

    def kept(prefix):
        return any(k.startswith(prefix) for k in survived)

    assert kept("p1:") is (flag is Change.NONE)
    assert kept("bonds:") is not bool(flag & CHEMISTRY)
    assert kept("uff-typing") is not bool(
        flag & (CHEMISTRY | Change.METADATA))


def test_setting_an_atom_type_reaches_the_typing(rutile):
    """The override lives in Site.props, which is metadata -- so the
    typing memo has to notice a metadata change even though the bond
    graph does not."""
    assert typer.assign(rutile).names[0] == "Ti6+4"
    rutile.sites[0].props["uff_type"] = "Ti3+4"
    rutile.touch(Change.METADATA)
    assert typer.assign(rutile).names[0] == "Ti3+4"


# --------------------------------------------------------------- bonds

def test_moving_an_atom_does_not_change_the_bonds(rutile, monkeypatch):
    """The complaint this exists for: bonds appearing and disappearing
    under a hand that is dragging one atom."""
    before = {b.key() for b in bonding.perceive(rutile)}
    perceive = Counter(monkeypatch, bonding, "_assemble")

    # Far enough to break every Ti-O bond, if perception were re-run.
    rutile.set_frac(1, [0.45, 0.45, 0.0])

    assert {b.key() for b in bonding.perceive(rutile)} == before
    assert perceive.calls == 0


# ----------------------------------------------------------- a full run

def test_a_relaxation_types_the_atoms_once(rutile, monkeypatch):
    """Twenty previewed steps, and the typing is derived once.

    Each step is replayed the way the panel replays it -- the atoms
    move, the structure is touched with POSITIONS -- and then the two
    things the window used to re-derive per step are asked for again.
    Both come back from the memo.
    """
    from xtal.ff import optimize
    from xtal.ff.uff.calculator import UFFCalculator

    calculator = UFFCalculator(rutile)
    assign = Counter(monkeypatch, typer, "_assign")
    perceive = Counter(monkeypatch, bonding, "_assemble")

    steps = 0
    for step in optimize.steps(calculator, rutile, "fire", max_steps=20):
        steps += 1
        for site, frac in zip(rutile.sites, step.frac, strict=True):
            site.frac = np.array(frac, dtype=float)
        rutile.touch(Change.POSITIONS)
        typer.assign(rutile)        # what the panel did on every step
        bonding.graph(rutile)       # what the viewport did

    assert steps > 1
    assert assign.calls == 0
    assert perceive.calls == 0
