# -*- mode: python ; coding: utf-8 -*-
"""
Crystal Builder for Windows.

    pyinstaller --noconfirm packaging\\windows.spec

Onedir, for the same reasons as ``macos.spec``, and because Inno Setup
wants a directory to install rather than a self-extracting archive to
copy.  What goes in is :mod:`bundle`, shared with the macOS spec; what
is here is the version resource, the ``.ico``, and ``console=False``.

``console=False`` is what makes ``xtalapp/applog.py`` load-bearing
rather than nice: with no console there is no stderr, so an uncaught
exception would take the window down leaving nothing on disk to say
why, and the first bug report would be the word "crashed".  The log
file and the excepthook are the answer, and Help > Show log is how a
user finds them.

The version resource is generated here rather than committed.  It has
to carry the ``setuptools-scm`` version, which changes with every
commit, and a committed file would be stale on every build but the one
that regenerated it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH).resolve()))

import bundle  # noqa: E402

VERSION = bundle.version()
NUMBERS = bundle.windows_version()

# A version resource holds four 16-bit integers and a set of strings,
# and PyInstaller wants them in this Python-literal format.  The
# numbers cannot express `0.1.dev70+gaebc1f5cf`, so they carry the
# release part and the strings carry what was actually built.  Without
# any of this the .exe properties dialog shows no publisher and no
# name, and SmartScreen has nothing to report but the file name.
VERSION_RESOURCE = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={NUMBERS},
    prodvers={NUMBERS},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Crystal Builder'),
         StringStruct('FileDescription',
                      'Build, manipulate, analyse and export crystal '
                      'structures'),
         StringStruct('FileVersion', '{VERSION}'),
         StringStruct('InternalName', 'crystal-builder'),
         StringStruct('LegalCopyright', 'MIT licence'),
         StringStruct('OriginalFilename', 'Crystal Builder.exe'),
         StringStruct('ProductName', 'Crystal Builder'),
         StringStruct('ProductVersion', '{VERSION}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

# The root build/ directory, which is gitignored.  Not
# packaging/build/: .gitignore anchors the rule as `/build/`,
# deliberately, so that it cannot swallow xtal/build/, and a
# generated file under packaging/ would therefore show up as
# untracked after every Windows build.
VERSION_FILE = (Path(SPECPATH).parent / "build"
                / "version_info.txt")
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
VERSION_FILE.write_text(VERSION_RESOURCE, encoding="utf-8")

# The document icons travel with the build so the installer can point
# the file associations at them.  Windows takes an icon out of any
# file that has one, and a loose .ico beside the executable is the
# simplest thing for the .iss to name.
DOCUMENT_ICONS = [
    (str(bundle.ICONS / "cif.ico"), "."),
    (str(bundle.ICONS / "xtalproj.ico"), "."),
]

analysis = Analysis(
    [str(bundle.ROOT / "xtalapp" / "main.py")],
    pathex=[str(bundle.ROOT)],
    binaries=bundle.binaries(),
    datas=bundle.datas() + DOCUMENT_ICONS,
    hiddenimports=bundle.hiddenimports(),
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
    name="Crystal Builder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX would roughly halve the download and is off anyway: it
    # rewrites every DLL it touches, which is what antivirus
    # heuristics are looking for, and an unsigned installer already
    # has enough to explain to SmartScreen.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(bundle.ICONS / "app.ico"),
    version=str(VERSION_FILE),
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    # PyInstaller's strip is `strip -S` on macOS, which removes debug
    # symbols these libraries do not have, and costs minutes.  The
    # saving is in the *local* symbol table, which is `strip -x`, and
    # packaging/postbuild.py does that afterwards: 54.7 MB of
    # libvtkCommonCore's 98.4 MB is one __LINKEDIT segment.
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Crystal Builder",
)
