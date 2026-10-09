# -*- mode: python ; coding: utf-8 -*-
"""
Crystal Builder for Linux.

    pyinstaller --noconfirm packaging/linux.spec
    python packaging/makedeb.py dist/crystal-builder

Onedir, for the reasons ``macos.spec`` gives: a onefile build unpacks
the whole bundle to a temporary directory on every launch, and it
moves ``sys._MEIPASS`` somewhere the four ``parent.parent /
resources`` lookups do not expect.  What goes in is :mod:`bundle`,
shared with the other two specs; what is here is only what Linux
genuinely disagrees about.

Three disagreements, and each is deliberate:

* **The executable is ``crystal-builder``**, not ``Crystal Builder``:
  a space in a path is a shell quoting problem on every platform that
  does not have Finder, and the .desktop file is where the display
  name lives.
* **There is no ``BUNDLE`` step.**  There is no bundle format here:
  the onedir folder *is* the artifact, ``packaging/makedeb.py`` puts
  it under ``/opt/crystal-builder`` and writes the .deb around it.
* **The icon is not passed.**  PyInstaller uses ``icon=`` on Windows
  and macOS only; on Linux the icon is a file in the hicolor theme
  and a line in the .desktop entry, both written by makedeb.py from
  the same SVGs.

What is *not* in here is as important: the C library and the handful
of system libraries Qt and VTK link against -- ``libGL``, ``libEGL``,
``libxkbcommon-x11``, the xcb family -- which PyInstaller leaves to
the machine and which are therefore the .deb's ``Depends:``.  They
are the same list the CI Linux job installs before it can import
``QtGui`` at all; see the ``Depends`` comment in makedeb.py.

``strip=False`` on the COLLECT below, for a Linux reason rather than
the macOS one: the stripping that is worth having is
``strip --strip-unneeded`` over the staged copy, which makedeb.py
does, and doing it twice costs minutes for nothing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH).resolve()))

import bundle  # noqa: E402

# Asked once: each walks every package in `bundle.COLLECT`, and both
# programs below are made from the same answer.
BINARIES = bundle.binaries()
DATAS = bundle.datas()
HIDDEN = bundle.hiddenimports()

analysis = Analysis(
    [str(bundle.ROOT / "xtalapp" / "main.py")],
    pathex=[str(bundle.ROOT)],
    binaries=BINARIES,
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=bundle.EXCLUDES,
    noarchive=False,
    optimize=0,
    module_collection_mode=bundle.MODULE_COLLECTION_MODE,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="crystal-builder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# The second program: `xtal`, the headless CLI, so that an AI
# assistant's client can run `xtal mcp` from a packaged install --
# there is no pip here to have put one on PATH, and the .deb's wrapper
# is what puts this one there.  Its own Analysis over the same
# contents, because a program's scripts and archive are its own; the
# two land in the one COLLECT below, which keeps one copy of every
# shared library and data file.  With a console, because stdio *is*
# the MCP transport, and beside the window's executable, which is
# where `xtal.agent.discovery.launcher` and `bundle.launcher_path`
# look.
cli_analysis = Analysis(
    [str(bundle.ROOT / "xtal" / "cli.py")],
    pathex=[str(bundle.ROOT)],
    binaries=BINARIES,
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=bundle.EXCLUDES,
    noarchive=False,
    optimize=0,
    module_collection_mode=bundle.MODULE_COLLECTION_MODE,
)

cli_pyz = PYZ(cli_analysis.pure)

launcher = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="xtal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    executable,
    launcher,
    analysis.binaries,
    analysis.datas,
    cli_analysis.binaries,
    cli_analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="crystal-builder",
)
