# -*- mode: python ; coding: utf-8 -*-
"""
Crystal Builder for macOS.

    pyinstaller --noconfirm packaging/macos.spec

Onedir, wrapped in a ``.app`` by ``BUNDLE``.  Not onefile: a onefile
build unpacks the whole bundle to a temporary directory on every
launch, which is seconds of delay before a splash screen this
application does not have, and it moves ``sys._MEIPASS`` somewhere the
four ``parent.parent / resources`` lookups do not expect.  Onedir is
what goes inside a ``.app`` and inside a DMG anyway.

What goes in is :mod:`bundle`, shared with ``windows.spec``.  What is
here is only what the two platforms genuinely disagree about: the
``Info.plist``, the document types, and an ``.icns`` where Windows
wants an ``.ico``.

**Two architectures, never universal2.**  VTK publishes no universal2
wheel, so ``--target-arch universal2`` cannot work without building
VTK from source, which this project is not going to do.  CI builds on
``macos-14`` for arm64 and ``macos-15-intel`` for x86_64 and ships
two DMGs.  Do not ship arm64 only and tell Intel users about
Rosetta: Rosetta translates x86_64 for Apple silicon, not the other
way round, so there would simply be nothing for them to run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH).resolve()))

import bundle  # noqa: E402

VERSION = bundle.version()

# The document icons, at the top of the bundle.  `CFBundleTypeIconFile`
# below names a file and Finder looks for it in `Contents/Resources`
# and nowhere else, so these have to be collected as data with `.` as
# their destination; the app icon is the only one BUNDLE places by
# itself.  Without this the two file types get the generic blank page.
DOCUMENT_ICONS = [
    (str(bundle.ICONS / "cif.icns"), "."),
    (str(bundle.ICONS / "xtalproj.icns"), "."),
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
    upx=False,                  # UPX and macOS code signing do not mix
    console=False,              # a console flashing up behind a GUI
    disable_windowed_traceback=False,
    argv_emulation=False,       # see the note on QFileOpenEvent below
    target_arch=None,           # whatever this runner is; never universal2
    codesign_identity=None,     # signed after the build; see below
    entitlements_file=None,
    icon=str(bundle.ICONS / "app.icns"),
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

app = BUNDLE(
    collection,
    name="Crystal Builder.app",
    icon=str(bundle.ICONS / "app.icns"),
    bundle_identifier="org.crystalbuilder.CrystalBuilder",
    version=VERSION,
    info_plist={
        "CFBundleName": "Crystal Builder",
        "CFBundleDisplayName": "Crystal Builder",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        # The application already follows the system theme.  Without
        # this, macOS forces it into light appearance and the dark
        # theme it draws is never seen.
        "NSRequiresAquaSystemAppearance": False,
        # scipy's oldest arm64 wheel is tagged 12.0 and its extension
        # modules say 12.3, which is the one that counts;
        # packaging/postbuild.py refuses any binary newer than this.
        "LSMinimumSystemVersion": "12.3",
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHumanReadableCopyright": "MIT licence",
        # Double-clicking a file is delivered two different ways and
        # the application handles both: as argv on a cold launch, and
        # as a QFileOpenEvent when the window is already up.  That is
        # why argv_emulation is off above -- PyInstaller's emulation
        # intercepts the event to fake an argv, which would take the
        # warm case away from xtalapp/application.py, the only code
        # that can put the file in the running window.
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Crystallographic Information File",
                "CFBundleTypeExtensions": ["cif"],
                "CFBundleTypeIconFile": "cif.icns",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.chemical-file"],
            },
            {
                "CFBundleTypeName": "Crystal Builder Project",
                "CFBundleTypeExtensions": ["xtalproj"],
                "CFBundleTypeIconFile": "xtalproj.icns",
                "CFBundleTypeRole": "Editor",
                # Owner, because this application writes the format
                # and nothing else reads it.
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": [
                    "org.crystalbuilder.xtalproj"],
            },
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": "org.crystalbuilder.xtalproj",
                "UTTypeDescription": "Crystal Builder Project",
                "UTTypeConformsTo": ["public.data", "public.archive"],
                "UTTypeIconFile": "xtalproj.icns",
                "UTTypeTagSpecification": {
                    "public.filename-extension": ["xtalproj"],
                },
            },
        ],
    },
)

# `LSHandlerRank: Alternate` on the CIF entry is deliberate and is the
# same decision the Windows installer makes with an unticked checkbox.
# A .cif on a working machine is usually already VESTA's or Mercury's,
# and an application that silently takes the association on install is
# the fastest thing there is to be uninstalled.
