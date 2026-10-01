"""The ``xtal`` launcher a packaged build carries beside the window.

An AI assistant's client is configured with ``"<launcher> mcp"``
(Preferences > AI assistant shows the line), and in a packaged build
there is no ``pip`` to have put an ``xtal`` on anybody's PATH: the
command has to be inside the build, next to the application, and it
has to carry the ``mcp`` package.  The specs are read as they are, not
fixtures; a real build is CI's bundle job.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

from xtal.agent.discovery import LAUNCHER_NAME

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import bundle  # noqa: E402


def _executables(spec: Path) -> tuple[dict[str, dict], list[str]]:
    """Each ``EXE`` the spec makes, by the variable that holds it, with
    its literal keywords; and the names ``COLLECT`` is handed, in
    order."""
    tree = ast.parse(spec.read_text(encoding="utf-8"))
    exes: dict[str, dict] = {}
    collected: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)):
            continue
        call = node.value
        if call.func.id == "EXE":
            (target,) = node.targets
            exes[target.id] = {
                k.arg: k.value.value for k in call.keywords
                if isinstance(k.value, ast.Constant)}
        elif call.func.id == "COLLECT":
            collected = [a.id for a in call.args
                         if isinstance(a, ast.Name)]
    return exes, collected


@pytest.mark.parametrize("spec", ["macos.spec", "windows.spec"])
def test_both_specs_build_an_xtal_launcher_beside_the_app(
        spec, tmp_path, monkeypatch):
    """Two programs in one folder: the window, and ``xtal`` with a
    console, so that ``xtal mcp`` can speak over stdin and stdout.
    The window comes first in ``COLLECT`` because on macOS the first
    executable is the one ``BUNDLE`` makes the ``.app``'s own."""
    exes, collected = _executables(bundle.HERE / spec)
    by_name = {kw["name"]: var for var, kw in exes.items()}

    assert set(by_name) == {"Crystal Builder", LAUNCHER_NAME}
    assert exes[by_name[LAUNCHER_NAME]]["console"] is True
    assert exes[by_name["Crystal Builder"]]["console"] is False
    assert collected[:2] == [by_name["Crystal Builder"],
                             by_name[LAUNCHER_NAME]]

    # Where it lands is where the Preferences page says it is.
    from xtal.agent import discovery

    app = tmp_path / ("Crystal Builder.exe" if sys.platform == "win32"
                      else "Crystal Builder")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app))
    assert bundle.launcher_path(app) == discovery.launcher()
    assert bundle.launcher_path(app).parent == tmp_path
    assert bundle.launcher_path(app).stem == LAUNCHER_NAME


def test_the_bundle_collects_the_mcp_package():
    """``mcp`` reads its own version from its metadata on import, and
    uvicorn picks its protocol modules by name, so both are collected
    whole; and the build jobs install the extra, without which
    ``collect_all`` finds nothing and says so only in a warning."""
    assert "mcp" in bundle.COLLECT
    assert "uvicorn" in bundle.COLLECT

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    installs = [line for line in workflow.splitlines()
                if "pip install -e" in line and "pyinstaller" in line]
    assert installs
    for line in installs:
        (extras,) = re.findall(r'"\.\[([^\]]*)\]"', line)
        assert "mcp" in extras.split(","), line


def test_the_app_keeps_its_dock_icon_beside_a_console_launcher():
    """COLLECT takes ``console`` from the last EXE it is handed -- the
    launcher's True -- BUNDLE inherits it, and PyInstaller writes a
    console bundle ``LSBackgroundOnly = True``: a window with no Dock
    icon and no menu bar, which no selftest would notice.  The spec's
    own Info.plist says False, after PyInstaller's defaults."""
    tree = ast.parse((bundle.HERE / "macos.spec").read_text(
        encoding="utf-8"))
    (call,) = [node for node in ast.walk(tree)
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Name)
               and node.func.id == "BUNDLE"]
    (plist,) = [k.value for k in call.keywords if k.arg == "info_plist"]
    said = {key.value: value for key, value in zip(plist.keys,
                                                   plist.values,
                                                   strict=True)
            if isinstance(key, ast.Constant)}

    assert isinstance(said["LSBackgroundOnly"], ast.Constant)
    assert said["LSBackgroundOnly"].value is False


def _fake_launcher(folder: Path, monkeypatch, mcp_status=0) -> Path:
    """An ``xtal`` that answers ``capabilities --json`` and
    ``mcp --headless``, and only when started as a top-level frozen
    program would be -- with PyInstaller's reset variable set."""
    if sys.platform == "win32":
        from xtal.agent import discovery

        monkeypatch.setattr(discovery, "launcher_file_name",
                            lambda: "xtal.cmd")
        fake = folder / "xtal.cmd"
        fake.write_text(
            '@echo off\r\n'
            'if not "%PYINSTALLER_RESET_ENVIRONMENT%"=="1" exit /b 3\r\n'
            'if "%1 %2"=="capabilities --json" goto capabilities\r\n'
            f'if "%1 %2"=="mcp --headless" exit /b {mcp_status}\r\n'
            'exit /b 2\r\n'
            ':capabilities\r\n'
            'echo {"version": "x"}\r\n', encoding="utf-8")
    else:
        fake = folder / "xtal"
        fake.write_text(
            '#!/bin/sh\n'
            '[ "$PYINSTALLER_RESET_ENVIRONMENT" = 1 ] || exit 3\n'
            'if [ "$1 $2" = "capabilities --json" ]; then\n'
            '    echo \'{"version": "x"}\'; exit 0\n'
            'fi\n'
            f'[ "$1 $2" = "mcp --headless" ] && exit {mcp_status}\n'
            'exit 2\n', encoding="utf-8")
        fake.chmod(0o755)
    return fake


def test_the_selftest_launcher_check_runs_the_launcher(tmp_path,
                                                       monkeypatch):
    from xtalapp import selftest

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("PYINSTALLER_RESET_ENVIRONMENT", raising=False)
    app = tmp_path / "Crystal Builder"

    with pytest.raises(AssertionError, match="no xtal launcher"):
        selftest.check_launcher(app)

    fake = _fake_launcher(tmp_path, monkeypatch)
    said = selftest.check_launcher(app)
    assert str(fake) in said
    assert "version x" in said
    assert "mcp answers" in said

    _fake_launcher(tmp_path, monkeypatch, mcp_status=1)
    with pytest.raises(AssertionError, match="mcp --headless exited 1"):
        selftest.check_launcher(app)

    fake.write_text(fake.read_text(encoding="utf-8").replace(
        "version", "verse"), encoding="utf-8")
    with pytest.raises(AssertionError, match="version"):
        selftest.check_launcher(app)


def test_the_selftest_looks_for_the_launcher_where_the_spec_puts_it(
        tmp_path, monkeypatch):
    """One rule for where ``xtal`` is: the build's
    (:func:`bundle.launcher_path`) and the one the shipped selftest
    and Preferences page use (:mod:`xtal.agent.discovery`)."""
    from xtalapp import selftest

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    app = tmp_path / ("Crystal Builder.exe" if sys.platform == "win32"
                      else "Crystal Builder")
    expected = re.escape(str(bundle.launcher_path(app)))
    with pytest.raises(AssertionError, match=f"at {expected}:"):
        selftest.check_launcher(app)


def test_the_launcher_check_is_skipped_when_not_frozen(tmp_path,
                                                       monkeypatch):
    """A checkout's ``xtal`` is pip's, wherever pip put it; the check
    is about what a build carries."""
    from xtalapp import selftest

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    said = selftest.check_launcher(tmp_path / "Crystal Builder")
    assert said.startswith("xtal launcher: skipped")
    assert "not a frozen build" in said
