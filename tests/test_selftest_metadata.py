"""``--selftest``'s metadata check: a build that was installed over an
older one without clearing it says so, rather than reporting the old
version on the start window."""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")


def _dist(name, version):
    return SimpleNamespace(metadata={"Name": name}, version=version)


def _two_releases(monkeypatch):
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "distributions", lambda: [
        _dist("crystal_builder", "0.4.0"),
        _dist("crystal-builder", "0.2.0"),
        _dist("numpy", "2.1.0"),
    ])


def test_a_bundle_holding_two_releases_metadata_fails(monkeypatch):
    """Without it the Windows installer's stale ``_internal`` goes
    unnoticed and the start window goes on naming the old release."""
    from xtalapp import extras, selftest

    _two_releases(monkeypatch)
    monkeypatch.setattr(extras, "frozen", lambda: True)

    with pytest.raises(AssertionError, match="0.2.0, 0.4.0"):
        selftest.check_one_metadata(lambda line: None)


def test_a_checkout_with_a_stale_egg_info_only_reports_it(monkeypatch):
    """A source tree's root ``egg-info`` beside the installed copy is
    ordinary; failing on it would fail every developer's selftest."""
    from xtalapp import extras, selftest

    _two_releases(monkeypatch)
    monkeypatch.setattr(extras, "frozen", lambda: False)
    said = []

    selftest.check_one_metadata(said.append)

    assert said == ["crystal-builder metadata: 0.2.0, 0.4.0"]
