# -*- mode: python ; coding: utf-8 -*-
"""
Crystal Builder for Linux.

    pyinstaller --noconfirm packaging/linux.spec

Onedir, for the same reasons as ``macos.spec``, and because what comes
out is not the download: ``packaging/appimage.py`` lays this folder out
as ``usr/lib/crystal-builder/`` in an AppDir, and ``appimagetool`` packs
that.  A onefile build inside an AppImage would be an archive unpacked
to a temporary directory on every launch, inside an image already
mounted for the purpose.

What goes in is :mod:`bundle`, shared with the other two specs, and the
two programs are theirs too: the window, and ``xtal`` beside it for an
AI assistant's client to run as ``xtal mcp``.  What is not here is what
a Linux executable has nowhere to carry -- an ELF file holds no icon and
no version resource -- and the document icons.  The AppDir carries the
icon and the ``.desktop`` entry, and its MIME file the two file types.

Nothing is stripped here.  ``packaging/postbuild_linux.py`` does it
afterwards with ``--strip-unneeded``, the same split macOS has with
``postbuild.py``.
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

# `console` changes nothing in a Linux executable -- whether a terminal
# opens is the desktop's decision, and the .desktop entry says
# `Terminal=false` -- but it is said, as the other specs say it, so
# that the three agree on which program is the window.
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Crystal Builder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # The AppImage is a compressed squashfs already, so UPX would
    # compress these a second time and unpack them on every launch.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# The second program: `xtal`, the headless CLI, so that an AI
# assistant's client can run `xtal mcp` from the AppImage -- there is
# no pip here to have put one on PATH.  Its own Analysis over the same
# contents, because a program's scripts and archive are its own; the
# two land in the one COLLECT below, which keeps one copy of every
# shared library and data file.  With a console, because stdio *is*
# the MCP transport.
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
    # PyInstaller's strip on Linux is a bare `strip` over each library
    # as it is collected.  postbuild_linux.py strips once, with
    # --strip-unneeded, after the unused Qt modules are gone, and
    # prints the size before and after so the saving is measured.
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Crystal Builder",
)
