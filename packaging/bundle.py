"""
What goes in the bundle, for both platforms.

``macos.spec`` and ``windows.spec`` differ in real ways -- an
``Info.plist`` and a ``BUNDLE`` step against a version resource and a
different icon format -- but the *contents* are identical, so they are
here.  This exists so that "we forgot to collect the fragment library"
is one fix and not two.

It is not a build script.  ``pyinstaller packaging/macos.spec`` stays
the command.

**Half of this module imports PyInstaller and half of it must not.**
:func:`project_datas`, :data:`OMITTED` and :data:`EXCLUDES` are plain
data over :mod:`pathlib`, because ``tests/test_packaging.py`` runs in
the ordinary suite -- which installs ``[gui,build,test]`` and not
PyInstaller -- and asserting there that this file names every data
file the application looks for is the highest-value test in the whole
of packaging.  Everything that needs ``PyInstaller.utils.hooks`` is
behind a function the specs call and the test does not.

The layout the datas produce is not arbitrary.  Four places compute

    Path(<a module>.__file__).resolve().parent.parent / "resources" / ...

to find a file on a source checkout: :func:`xtal.analysis.rcsr.source_file`,
:func:`xtal.modules.zeopp.bundled`, :func:`xtal.ff.dftb.hsd.bundled` and
:func:`xtalapp.samples.folder`.  In a PyInstaller onedir bundle
``xtal.__file__`` is ``<bundle>/_internal/xtal/__init__.pyc``, so
``parent.parent`` is ``_internal``, which is ``sys._MEIPASS``.  **All
four keep working unchanged provided what they look for is placed at
``_internal/resources/...``**, which is what the destinations below
do.  Do not add a ``sys.frozen`` branch to any of the four and do not
flatten ``resources/`` into the package; put the tree where they
already look.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ICONS = HERE / "icons"

#: Subtrees of ``resources/`` that travel with the application, as
#: (relative path, why).  Both are load-bearing: File > Open Sample
#: builds its seven entries from :func:`xtalapp.samples.installed`, so
#: without the samples the menu greys out with a sentence about source
#: checkouts and ``--selftest`` has nothing to open; and the workspace
#: chooser, the first thing a launch shows, draws its side panel from
#: ``resources/chooser``.
RESOURCES = {
    "resources/samples":
        "File > Open Sample, and what --selftest opens.  164 KB.",
    "resources/chooser":
        "The workspace chooser's icon and framework picture, made by "
        "packaging/render_chooser_art.py.  150 KB.",
}

#: Subtrees of ``resources/`` that deliberately do **not** travel, and
#: the reason each is refused.  The test asserts these are absent, so
#: that a future "just collect resources/" edit fails a test rather
#: than quietly adding a gigabyte and a half to the download.
OMITTED = {
    "resources/topo":
        "The uncompressed .cgd, which only `python -m "
        "xtal.analysis.rcsr build` reads.  A gzipped copy of the same "
        "file ships as package data, and `xtal.analysis.rcsr.nets` "
        "prefers it, so the shipped app draws every net without this.",
    "resources/PTBP":
        "Somebody else's Slater-Koster parameters, with their own "
        "licence and citation terms.  Gitignored, so CI could not "
        "bundle them anyway.  Preferences > Engines is how a "
        "user points at their own.",
    "resources/zeo++-0.3":
        "78 MB of somebody else's source and a binary built from it, "
        "under its own licence.  Same answer: the shipped app finds "
        "Zeo++, it does not carry it.",
    "resources/test":
        "Test fixtures, including a 14 MB structure.  Nothing the "
        "application does reads them.",
}

#: Package data, mirroring ``[tool.setuptools.package-data]`` in
#: ``pyproject.toml``.  Both are non-optional by the argument recorded
#: there: a net panel that cannot name anything and a fragment picker
#: with nothing in it are broken features, not smaller ones.  The test
#: reads pyproject and asserts this list still matches it.
#:
#: A package may have more than one pattern, which is why the values
#: are lists: ``pyproject.toml`` writes the vendored PORMAKE's four in
#: one entry, and the test that compares the two files compares them
#: literally.
PACKAGE_DATA = {
    # The RCSR index, and the nets it indexes.  The second is not a
    # duplicate of the first: the index carries invariants and a key
    # and no coordinates, so it names a net and cannot draw one, and
    # drawing one is what `xtal.build.topology` does.  331 KB.
    "xtal/analysis": ["data/*.json.gz", "data/*.cgd.gz"],
    "xtal/build/data": ["*.json"],          # the fragment library
    # The script Blender runs for Export as STL, by path.
    "xtal/modules": ["data/*.py"],
    # PORMAKE's nets and building blocks, vendored with it: 3271
    # files, 2.8 MB of bytes and about 13 MB once installed, because
    # a file that small is a 4 KB block.  The builder is broken
    # without them --
    # `xtal.mof.catalog.database_root` is what looks, and
    # `xtal.modules.mof.available` greys the entry out when it finds
    # nothing -- so this is the entry that turns "the download is
    # missing the database" into a failing test rather than a bug
    # report.  The licence has to travel with the code, and the record
    # of what was changed in it is no use if it does not.
    "xtal/mof/pormake": ["database/topologies/*.cgd",
                         "database/bbs/*.xyz",
                         "LICENSE.md", "PROVENANCE.md"],
}

#: Imported for their side effect and not for a name, or reached only
#: at run time.  VTK's rendering back end registers factory overrides
#: when it is imported and is then never referred to again, which is
#: exactly the shape static analysis misses.
#:
#: :func:`dialog_imports` adds the other shape of the same problem and
#: is kept separate because it is *derived* rather than listed.
HIDDEN_IMPORTS = [
    "vtkmodules.vtkRenderingOpenGL2",
    "vtkmodules.vtkRenderingFreeType",
    "vtkmodules.vtkRenderingUI",
    "vtkmodules.vtkInteractionStyle",
    "vtkmodules.qt.QVTKRenderWindowInteractor",
    "vtkmodules.util.numpy_support",
    # matplotlib's Qt back end, named for the same reason the four
    # VTK entries above are: `xtalapp/dialogs/pattern.py` imports it
    # inside a function, so that the module can be imported -- and
    # `installed()` asked -- on a machine with no matplotlib.
    # `collect_all` below should find it as a submodule; this is the
    # belt to that brace, and it costs a line.
    "matplotlib.backends.backend_qtagg",
]

#: Collected whole, data files and all.  These are the extras SHELL.md
#: 3 decided to bundle: RDKit buys two entire features (build from
#: SMILES, and the sketcher) and rdeditor is a megabyte on top of a
#: PySide6 that ships anyway.  They are reached through ``find_spec``
#: and then imported inside a function, so the *feature gate* is
#: invisible to static analysis even though the import itself is not,
#: and RDKit carries data directories that no amount of import
#: scanning would find.
#:
#: ``matplotlib`` is the fourth, and it is the newest: PXRD's overlay
#: window wants axes that pan, zoom and pick and a vector export whose
#: text is still text, which is the case `docs/PLAN.md` section 2 had
#: named in advance as the one that would reverse "no plotting
#: library".  It is collected whole rather than traced because the Qt
#: back end is chosen at run time and ``mpl-data`` -- the fonts and
#: the style sheets -- is found by path, so a traced build imports and
#: then fails to draw.
#:
#: ``ase`` was a fourth entry here and is not one any more, which is
#: PACKAGING.md 4's "build the exclude list empirically" doing its
#: job.  It went on conservatively -- the vendored PORMAKE imports it
#: statically, so most of it would be traced anyway, but ``ase.io``'s
#: format registry imports its readers through ``importlib`` at call
#: time, and the MOF builder was the one feature that could not be
#: exercised until a bundle existed.  A bundle exists now, and three
#: measurements agree that the caution bought nothing:
#:
#: * ``ase.io`` is imported by the vendored ``utils.py`` and never
#:   called.  Nothing here reads or writes through ase --
#:   ``framework.py`` formats its own CIF -- so there is no format
#:   lookup to fail.
#: * Static tracing finds 200 of ase's 1218 modules, and every one of
#:   the 65 the MOF tests actually import is among them.
#: * ase's 106 non-Python files are all ``ase.gui`` translations,
#:   ``ase.db`` templates, ``spacegroup.dat`` and the molecule
#:   collections.  With every one of them renamed away, the MOF tests
#:   still pass; ``ase.spacegroup`` is imported but never constructs a
#:   ``Spacegroup``, which is the only thing that reads the ``.dat``.
#:
#: Off the list, ``--selftest`` still builds pcu inside the bundle,
#: and the ``.app`` is 16 MB smaller.
COLLECT = ["rdkit", "rdeditor", "qdarktheme", "matplotlib"]

#: Not bundled, and each line is a decision rather than an oversight.
EXCLUDES = [
    # `pormake` is NOT excluded any more, and its absence from this
    # list is the point.  It used to be: 44 packages and ~889 MB,
    # jax and pymatgen for one dialog, which made the MOF builder the
    # single feature a packaged user could not have.  It is now
    # vendored inside `xtal.mof.pormake`, trimmed of all three, and it
    # ships -- see `xtal/mof/pormake/PROVENANCE.md`.  Excluding the
    # name here would now exclude part of `xtal` itself.
    #
    # `ase` is not excluded any more either, for the same reason:
    # the vendored PORMAKE uses `ase.Atoms`, `ase.neighborlist` and
    # `ase.io` throughout, so the 26 MB now buys the MOF builder
    # rather than nothing.  Replacing it with
    # `xtal.core.structure.Structure` is a much larger piece of work
    # and is not a packaging decision.
    #
    # The three that came with them are still excluded, because
    # nothing imports them now:
    "jax",
    "jaxlib",
    "pymatgen",
    "networkx",
    # `matplotlib` is NOT excluded any more, and its absence from
    # this list is the point.  It used to be, because the plots this
    # application drew were a hundred lines of QPainter each and the
    # only matplotlib in the environment arrived as a dependency of
    # rdkit's drawing code, which is not used.  PXRD changed that: an
    # overlay of a measured pattern on a calculated one wants axes
    # that pan, zoom and pick, and a vector export whose text is
    # still text -- see `xtalapp/dialogs/pattern.py`.  It is in
    # COLLECT above, because the backend and `mpl-data` are found at
    # run time and are invisible to the import analysis.
    #
    # The panels are still QPainter, and that is what makes this a
    # bounded decision rather than a slide: `xtalapp/plot.py`,
    # `xtalapp/histogram.py` and `xtalapp/curve.py` draw with nothing
    # installed, so a build that failed to collect matplotlib loses
    # one window and no answers.
    "tkinter",
    # `import vtkmodules.all` would pull in every one of the ~180
    # modules in a 592 MB package.  xtalapp/viewport imports thirteen
    # by name, which is the form a frozen build can prune; this makes
    # sure nothing quietly undoes that.
    "vtkmodules.all",
    "vtk",
    # The application uses exactly four Qt modules: QtCore, QtGui,
    # QtWidgets and QtSvgWidgets.  Everything below is the rest of a
    # very large framework.
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    # Test and build machinery, which a shipped application has no
    # use for and which drags in more than it looks.
    "pytest",
    "pytest_qt",
    "setuptools",
    "pip",
    "IPython",
]


def dialog_imports() -> list[str]:
    """The dialogs an action can only *name*.

    ``xtalapp.dialogs.module_dialog`` turns a module's declared dialog
    name into a class with ``importlib.import_module``, because a
    module declares its parameters as data and imports no Qt.  Nothing
    static can see through that, so the first bundle to carry the MOF
    builder shipped without ``xtalapp.dialogs.mof_build`` **or**
    ``xtalapp.dialogs.build_molecule`` in it, and all three actions
    that use them died on ``ModuleNotFoundError`` at the click:

        File "xtalapp/dialogs/__init__.py", line 55, in module_dialog
        ModuleNotFoundError: No module named 'xtalapp.dialogs.mof_build'

    A source checkout imports these perfectly, so no test in the suite
    could have caught it and ``--selftest`` did not either -- it built
    a framework through ``xtal.mof.build`` and never went near the
    dialog a person actually clicks.  It checks the resolution now.

    Pure, and asked of ``xtalapp.dialogs`` rather than repeated here:
    that module holds nothing and imports no Qt, and a list copied
    into this file is a list that goes stale the next time somebody
    adds a dialog.
    """
    from xtalapp.dialogs import dialog_modules

    return dialog_modules()


def project_datas() -> list[tuple[str, str]]:
    """Every file this project owns that the bundle needs, as
    PyInstaller ``(source, destination directory)`` pairs.

    Pure: paths and globs, no PyInstaller.  This is the half
    ``tests/test_packaging.py`` checks.
    """
    datas: list[tuple[str, str]] = []

    for relative in sorted(RESOURCES):
        folder = ROOT / relative
        for path in sorted(folder.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                datas.append((str(path), relative))

    for package, patterns in sorted(PACKAGE_DATA.items()):
        folder = ROOT / package
        for pattern in patterns:
            for path in sorted(folder.glob(pattern)):
                # From the file's own parent, so a pattern that
                # reaches down a subdirectory -- as the vendored
                # database's two do -- lands where it was found.
                # `as_posix`, because a destination is a path *inside*
                # the bundle and not one on the machine building it:
                # `str()` here spells it `xtal\build\data` on
                # Windows, which is not what the entries above, or
                # PyInstaller, or the bundle's own layout use.
                destination = path.parent.relative_to(ROOT)
                datas.append((str(path), destination.as_posix()))

    return datas


def datas() -> list[tuple[str, str]]:
    """:func:`project_datas`, plus what PyInstaller has to be asked
    for.  Needs PyInstaller; called from the specs only.

    ``copy_metadata`` is the one that is invisible until it is
    missing.  ``pip`` writes ``crystal_builder-<version>.dist-info/``
    beside the code, holding the version and the entry points, and
    PyInstaller copies code and not that.  Without this,
    :func:`xtal.__init__.version` raises ``PackageNotFoundError``, its
    ``except`` catches it, and **Help > About reports 0.0.dev0 on
    every release** -- which is worse than showing nothing, because it
    looks like a real number and a bug report quoting it is useless.

    The other half of that metadata is ``xtal.plugins.load``, which
    calls ``entry_points(group=...)``.  That works again with this
    line, but honestly: a frozen app has no pip and therefore nowhere
    to install a plugin *to*.  The shipped build supports in-tree
    modules only, plus whatever a user has put in the folder
    :mod:`xtalapp.extras` prepends to ``sys.path``.
    """
    from PyInstaller.utils.hooks import collect_all, copy_metadata

    collected = list(project_datas())
    collected += copy_metadata("crystal-builder")
    for package in COLLECT:
        package_datas, _binaries, _hidden = collect_all(package)
        collected += package_datas
    return collected


def hiddenimports() -> list[str]:
    """:data:`HIDDEN_IMPORTS`, plus :func:`dialog_imports` and the
    modules ``collect_all`` finds inside the bundled extras."""
    from PyInstaller.utils.hooks import collect_all

    found = list(HIDDEN_IMPORTS) + dialog_imports()
    for package in COLLECT:
        _datas, _binaries, hidden = collect_all(package)
        found += hidden
    return found


def binaries() -> list[tuple[str, str]]:
    """Shared libraries the extras carry.

    No third-party *programs*: Zeo++'s ``network`` and DFTB+ are never
    bundled.  They carry their own licences and citation obligations,
    they are gitignored so CI could not bundle them anyway, and
    ``Program.locate`` plus the preference, the environment variable
    and PATH already give three ways to point at a local copy, with a
    greyed-out module entry naming which.  The shipped app finds
    these; it does not carry them.
    """
    from PyInstaller.utils.hooks import collect_all

    found: list[tuple[str, str]] = []
    for package in COLLECT:
        _datas, package_binaries, _hidden = collect_all(package)
        found += package_binaries
    return found


def version() -> str:
    """The number the build carries, from the installed metadata and
    therefore from the git tag ``setuptools-scm`` read.

    With no tag anywhere in the repository this is a ``0.1.devN``
    string rather than a release number, which is correct and is
    visible: a build made off an untagged tree should not claim to be
    one that was tagged.
    """
    from importlib.metadata import version as installed

    return installed("crystal-builder")


def windows_version() -> tuple[int, int, int, int]:
    """The version as Windows' four-part integer tuple.

    A version resource cannot hold ``0.1.dev70+gaebc1f5cf``, so the
    dev and local parts are dropped and the fourth field is zero.  The
    string fields in the resource keep the full version, so the
    properties dialog still shows what was actually built.
    """
    head = version().split("+")[0]
    parts: list[int] = []
    for piece in head.split(".")[:3]:
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2], 0)
