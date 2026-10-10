"""``--selftest``'s frozen-Linux checks: the Extras ▸ Test probe and
the window icon, each run in the AppImage the way the window runs it.

Neither can be run for real off a frozen Linux build, so the probe
and the drawing are handed in, and what is tested is which builds
ask, what they ask, and what an answer that failed is called.
"""

import sys

import pytest

pytest.importorskip("PySide6")

from xtal.modules import probe  # noqa: E402
from xtalapp import selftest  # noqa: E402


@pytest.mark.parametrize("frozen, platform", [
    (False, "linux"), (True, "darwin"), (True, "win32")])
def test_the_test_button_check_is_skipped_off_a_frozen_linux_build(
        frozen, platform):
    """Only the Linux build hands its children the user's library path
    back; anywhere else the check has nothing to prove, and failing
    there would fail a macOS or Windows bundle that is fine."""
    said = []

    def ask(_probe):
        raise AssertionError("asked off a frozen Linux build")

    selftest.check_frozen_probe(said.append, frozen=frozen,
                                platform=platform, ask=ask)

    assert said and "skipped" in said[0]


def test_the_test_button_check_asks_numpy_as_the_button_would():
    """The application started again with the import flag, as a
    program of its own -- the same probe Extras ▸ Test starts -- and
    the version it answers is reported."""
    asked = []

    def ask(given):
        asked.append(given)
        return True, "numpy 2.1.3"

    said = []
    selftest.check_frozen_probe(said.append, frozen=True,
                                platform="linux", ask=ask)

    (given,) = asked
    assert given.argv == (sys.executable, probe.IMPORT_FLAG, "numpy")
    assert dict(given.env) == {"PYINSTALLER_RESET_ENVIRONMENT": "1"}
    assert said == ["Test button: numpy 2.1.3"]


def test_a_test_button_that_cannot_import_numpy_fails_the_selftest():
    """A child that lost the bundle's libraries says so as an import
    error, and the selftest must fail on it rather than report it."""
    def ask(_probe):
        return False, "ImportError: libscipy_openblas64_.so: cannot open"

    with pytest.raises(AssertionError, match="libscipy_openblas64_"):
        selftest.check_frozen_probe(lambda _line: None, frozen=True,
                                    platform="linux", ask=ask)


@pytest.mark.parametrize("frozen, platform", [
    (False, "linux"), (True, "darwin"), (True, "win32")])
def test_the_window_icon_check_is_skipped_off_a_frozen_linux_build(
        frozen, platform):
    """macOS and Windows take the icon from the bundle and the
    ``.exe``, and a checkout's Qt is pip's whole wheel."""
    said = []

    def draws(_path):
        raise AssertionError("drawn off a frozen Linux build")

    selftest.check_window_icon(said.append, frozen=frozen,
                               platform=platform, draws=draws)

    assert said and "skipped" in said[0]


def test_a_window_icon_that_draws_nothing_names_the_svg_plugin():
    """Qt draws the SVG through a plugin, and a build that lost it
    gives every Linux window a blank icon and says nothing; the
    selftest says which plugin to look for."""
    with pytest.raises(AssertionError, match="SVG"):
        selftest.check_window_icon(lambda _line: None, frozen=True,
                                   platform="linux",
                                   draws=lambda _path: False)


def test_a_window_icon_that_draws_is_reported_with_its_file():
    from xtalapp.application import icon_path

    drawn = []
    said = []

    selftest.check_window_icon(said.append, frozen=True,
                               platform="linux",
                               draws=lambda path: drawn.append(path)
                               or True)

    assert drawn == [icon_path()]
    assert said == [f"window icon: {icon_path().name} draws at 64 px"]


def test_the_window_icon_draws_from_the_checkout(qapp):
    """The real drawing, here: the file is there and this Qt has its
    SVG plugins, so the check's own question is a fair one."""
    from xtalapp.application import icon_path

    assert selftest._icon_draws(icon_path())


def test_both_checks_are_in_the_selftest():
    """A check that is written and never run proves nothing."""
    import inspect

    source = inspect.getsource(selftest.run)

    assert "check_frozen_probe" in source
    assert "check_window_icon" in source
