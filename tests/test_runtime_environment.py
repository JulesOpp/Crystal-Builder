"""What a packaged build hands the programs it starts.

PyInstaller's bootloader puts the bundle's own library folder first on
``LD_LIBRARY_PATH``, and every child inherits it: DFTB+, xTB, Zeo++,
Blender and the ``xdg-open`` behind every opened URL then load the
bundle's libstdc++, libssl or Qt instead of their own, and fail.
"""

import pytest

from xtal import runtime

BUNDLE = "/tmp/.mount_Crysta/usr/lib/crystal-builder/_internal"


def test_a_frozen_linux_build_gives_children_the_users_library_path():
    """Regressing this hands DFTB+ the bundle's libstdc++ again."""
    environ = {"LD_LIBRARY_PATH": f"{BUNDLE}:/opt/dftb/lib",
               "LD_LIBRARY_PATH_ORIG": "/opt/dftb/lib"}
    runtime.restore_system_library_path(environ, platform="linux",
                                        frozen=True)
    assert environ == {"LD_LIBRARY_PATH": "/opt/dftb/lib"}


def test_a_frozen_linux_build_with_no_library_path_of_its_own_gives_children_none():  # noqa: E501
    """The user launched with none, so the bundle's folder must not be
    the only thing a child searches; the variable goes entirely."""
    environ = {"LD_LIBRARY_PATH": BUNDLE, "HOME": "/home/jules"}
    runtime.restore_system_library_path(environ, platform="linux",
                                        frozen=True)
    assert environ == {"HOME": "/home/jules"}


def test_a_source_install_leaves_the_library_path_alone():
    """A checkout's library path is the user's own and nobody else's."""
    environ = {"LD_LIBRARY_PATH": "/opt/dftb/lib",
               "LD_LIBRARY_PATH_ORIG": "/somewhere"}
    before = dict(environ)
    runtime.restore_system_library_path(environ, platform="linux",
                                        frozen=False)
    assert environ == before


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_macos_and_windows_are_left_alone(platform):
    """Those builds are not handed the bundle's path, so a variable
    set there is the user's own and must reach their programs."""
    environ = {"LD_LIBRARY_PATH": BUNDLE,
               "LD_LIBRARY_PATH_ORIG": "/opt/dftb/lib"}
    before = dict(environ)
    runtime.restore_system_library_path(environ, platform=platform,
                                        frozen=True)
    assert environ == before


def _first_call_probe(monkeypatch, calls):
    def restore(*args, **kwargs):
        calls.append("restore")
        raise SystemExit(0)

    monkeypatch.setattr(runtime, "restore_system_library_path", restore)


def test_the_window_restores_the_library_path_before_anything_else(
        monkeypatch):
    """Later than the ``QApplication`` and Qt's own ``QProcess`` and
    ``xdg-open`` start with the bundle's path; later than the login
    shell ``shellenv.adopt`` asks, and that shell does too."""
    from xtalapp import applog
    from xtalapp import main as app_main

    calls = []
    _first_call_probe(monkeypatch, calls)
    monkeypatch.setattr(applog, "start", lambda: calls.append("applog"))
    with pytest.raises(SystemExit):
        app_main.main(["crystal-builder"])
    assert calls == ["restore"]


def test_the_command_line_restores_the_library_path_before_anything_else(
        monkeypatch):
    """``xtal`` starts DFTB+ and xTB itself, and serves ``xtal mcp``,
    without a window ever being built."""
    from xtal import cli

    calls = []
    _first_call_probe(monkeypatch, calls)
    monkeypatch.setattr(cli, "build_parser",
                        lambda: calls.append("parser"))
    with pytest.raises(SystemExit):
        cli.main(["modules"])
    assert calls == ["restore"]
