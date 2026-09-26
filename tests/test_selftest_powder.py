"""``--selftest``'s powder check: the refinement workbench refines in
the build it is run in, or the build says why."""

import pytest

pytest.importorskip("PySide6")


def test_the_selftest_refines_rutile_or_says_why_it_cannot(monkeypatch):
    """A bundle that promised the workbench and lost RietX fails; a
    checkout without the extra only says it skipped."""
    from xtal import powder
    from xtalapp import extras, selftest

    monkeypatch.setattr(powder, "available", lambda: False)
    said = []
    monkeypatch.setattr(extras, "frozen", lambda: False)
    selftest.check_powder(said.append)
    assert "skipped" in said[0]
    monkeypatch.setattr(extras, "frozen", lambda: True)
    with pytest.raises(AssertionError, match="bundled"):
        selftest.check_powder(said.append)


@pytest.mark.slow
def test_the_selftest_fits_rutiles_cell_and_oxygen(tmp_path, monkeypatch):
    """What a bundle job runs, run from the checkout: the scattering
    tables, the kernels and a fit's run folder, never the cwd."""
    pytest.importorskip("rietx")
    from xtalapp import selftest

    monkeypatch.chdir(tmp_path)
    said = []
    selftest.check_powder(said.append)
    assert any(line.startswith("Pawley: a 4.594") for line in said)
    assert any("-> 0.305" in line for line in said)
    assert not (tmp_path / ".rietx").exists()
