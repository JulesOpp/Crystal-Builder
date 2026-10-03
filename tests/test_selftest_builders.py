"""``--selftest``'s builder checks: the disordered-carbon and polymer
builders build in the build they are run in, or the build says why."""

import pytest

pytest.importorskip("PySide6")


def test_the_selftest_builds_a_carbon_and_says_what_came_out():
    """What every bundle job runs, run from the checkout."""
    from xtalapp import selftest

    said = []
    selftest.check_carbon_builder(said.append)
    assert said and said[0].startswith("dia 1x1x1:")


def test_the_selftest_packs_polyethylene_or_says_why_it_cannot(
        monkeypatch):
    """A bundle that promised the polymer builder and lost RDKit
    fails; a checkout without the extra only says it skipped."""
    from xtal import build
    from xtalapp import extras, selftest

    said = []
    if build.installed():
        selftest.check_polymer_builder(said.append)
        assert "64 atoms, 62 bonds" in said[0]

    monkeypatch.setattr(build, "installed", lambda: False)
    monkeypatch.setattr(extras, "frozen", lambda: False)
    said.clear()
    selftest.check_polymer_builder(said.append)
    assert "skipped" in said[0]
    monkeypatch.setattr(extras, "frozen", lambda: True)
    with pytest.raises(AssertionError, match="bundled"):
        selftest.check_polymer_builder(said.append)
