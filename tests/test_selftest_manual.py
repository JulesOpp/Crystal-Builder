"""``--selftest``'s manual check: a build carries the manual Help >
User Manual opens, or it fails."""

import pytest

pytest.importorskip("PySide6")


def test_a_bundle_without_its_manual_fails_and_a_checkout_says_so(
        tmp_path, monkeypatch):
    from xtalapp import extras, manual, selftest

    monkeypatch.setattr(manual, "root", lambda: tmp_path)
    said = []
    monkeypatch.setattr(extras, "frozen", lambda: False)
    selftest.check_manual(said.append)
    assert "not built" in said[0]

    monkeypatch.setattr(extras, "frozen", lambda: True)
    with pytest.raises(AssertionError, match="manual"):
        selftest.check_manual(said.append)


def test_a_bundle_with_its_manual_passes(tmp_path, monkeypatch):
    from xtalapp import extras, manual, selftest

    page = tmp_path.joinpath(*manual.BUNDLED, "index.html")
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(manual, "root", lambda: tmp_path)
    monkeypatch.setattr(extras, "frozen", lambda: True)
    said = []
    selftest.check_manual(said.append)
    assert str(page) in said[0]


def test_a_bundle_without_its_notices_fails_the_selftest(monkeypatch):
    """A build that skipped writing them ships everybody else's code
    without the notices their licences ask a binary to carry; a
    checkout only says it skipped."""
    from xtalapp import extras, manual, selftest

    monkeypatch.setattr(manual, "notices", lambda: None)
    said = []
    monkeypatch.setattr(extras, "frozen", lambda: False)
    selftest.check_notices(said.append)
    assert "skipped" in said[0]
    monkeypatch.setattr(extras, "frozen", lambda: True)
    with pytest.raises(AssertionError, match="notices"):
        selftest.check_notices(said.append)
