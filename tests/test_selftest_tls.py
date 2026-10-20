"""``--selftest``'s TLS check: a build can speak HTTPS to GitHub.

Help ▸ Check for Updates goes through Qt's network, and Qt finds its
TLS backend as a plugin it scans for, so a bundle without one is not
an import error -- it is a check that fails on the person's first
click, saying only that the connection could not be made.  The check
asks the backends and never the network: CI runners and an offline
machine must pass it.
"""

import pytest

pytest.importorskip("PySide6")

from xtalapp import selftest  # noqa: E402


@pytest.mark.parametrize("platform, backends", [
    ("darwin", ["securetransport", "cert-only"]),
    ("win32", ["schannel", "cert-only"]),
    ("linux", ["openssl", "cert-only"])])
def test_each_platform_s_own_backend_passes(platform, backends):
    said = []
    selftest.check_tls(said.append, platform=platform,
                       backends=backends, supports=True)
    assert backends[0] in said[0]


def test_a_build_with_only_the_certificate_backend_fails():
    """``cert-only`` reads certificates and cannot open a connection;
    it is what is left when the tls plugins were not collected."""
    with pytest.raises(AssertionError, match="tls"):
        selftest.check_tls(lambda _line: None, platform="darwin",
                           backends=["cert-only"], supports=False)


def test_a_backend_other_than_the_platform_s_still_passes():
    """OpenSSL on macOS connects too; what matters is that something
    can."""
    said = []
    selftest.check_tls(said.append, platform="darwin",
                       backends=["openssl", "cert-only"], supports=True)
    assert "openssl" in said[0]


def test_this_checkout_can_speak_tls():
    selftest.check_tls(lambda _line: None)


def test_the_selftest_runs_the_tls_check():
    import inspect
    assert "check_tls" in inspect.getsource(selftest.run)
