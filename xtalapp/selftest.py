"""
``crystal-builder --selftest``: does this build actually work?

The ordinary suite tests a source checkout and can say nothing about a
frozen one.  This runs *inside* whatever it was built into, so CI can
launch the packaged executable and get a non-zero exit rather than a
screenshot nobody looks at.

It checks the five things that break in a bundle and nowhere else:

1. **The version.**  ``pip`` writes the version into a ``dist-info``
   folder beside the code, and PyInstaller copies code and not that,
   so without ``copy_metadata`` in the spec ``version()`` raises,
   ``xtal.__init__`` catches it, and Help > About reports ``0.0.dev0``
   on every release.  Nothing else notices; About just quietly lies.
2. **The resource lookups.**  Four places compute
   ``parent.parent / "resources" / ...``, which lands on ``_internal``
   in a onedir bundle.  Opening a sample is that path being right.  On
   macOS it is also ``.resolve()`` surviving PyInstaller's
   ``Contents/Frameworks`` to ``Contents/Resources`` symlinks, which
   is the part that could break on a point release.
3. **The package data.**  The RCSR index and the fragment library are
   read two different ways -- a filesystem join and
   ``importlib.resources`` -- and a bundle can get one right and the
   other wrong.
4. **The bundled extras.**  RDKit and rdeditor are collected whole
   and RDKit carries data directories, so an import can succeed
   against a build whose parameter files did not come along.
   *Preferences > Engines* promises both work; in a bundle
   the user cannot check that, so this does.
5. **The VTK OpenGL context.**  Rendering is the single largest thing
   in the bundle and the most likely to have been pruned too hard.
   Writing a PNG of the 3D view is the only honest way to ask.

**It never opens a dialog.**  A modal in a windowed build with nobody
at the keyboard is a hung CI job, not a failure, so the same bargain
as ``tests/conftest.py`` applies: reaching one is an error.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

#: What ``xtal.__init__`` falls back to when the metadata is missing,
#: plus what a stale ``egg-info`` in a source tree reports.  Either
#: means the build does not know what it is.
UNKNOWN_VERSIONS = ("0.0.dev0", "0.0.0")

#: The sample opened, by its registry name.  MOF-5 rather than the
#: smallest file: it is written in P1 with 424 sites, so it exercises
#: the reader and gives the renderer something to be slow about.
SAMPLE = "mof5"


def _refuse_dialogs() -> None:
    """Turn a modal into a failure instead of a hung run.

    Not caution.  A ``--windowed`` build has no console to print to
    and no stdin to interrupt, so a message box here would block the
    CI job until the runner's own timeout killed it, twenty minutes
    later, with no output saying why.
    """
    from PySide6.QtWidgets import QDialog, QMessageBox

    def refuse(self, *args, **kwargs):
        raise AssertionError(
            f"{type(self).__name__}.exec() would wait for a click")

    QDialog.exec = refuse
    for name in ("question", "warning", "information", "critical",
                 "about"):
        def refuse_static(*args, _name=name, **kwargs):
            raise AssertionError(
                f"QMessageBox.{_name}() would wait for a click")
        setattr(QMessageBox, name, staticmethod(refuse_static))


def _settle(app, ms: int = 400) -> None:
    """Let Qt and VTK catch up.

    Not politeness: on macOS the render window has to be realised and
    its events processed before VTK initialises it, and an image
    grabbed before that is of a window that has not drawn.
    """
    from PySide6.QtCore import QDeadlineTimer, QEventLoop

    deadline = QDeadlineTimer(ms)
    while not deadline.hasExpired():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def check_version(report) -> None:
    """The build knows its own version number."""
    from xtal import __version__

    report(f"version {__version__}")
    if __version__ in UNKNOWN_VERSIONS:
        raise AssertionError(
            f"version is {__version__}, which is the fallback for "
            "missing metadata.  The spec needs "
            "copy_metadata('crystal-builder'), and the tree needs a "
            "tag for setuptools-scm to read.")


def check_rcsr_index(report) -> None:
    """The net panel can name a topology."""
    from xtal.analysis import rcsr

    catalogue = rcsr.catalogue()
    report(f"RCSR index: {len(catalogue.entries)} nets")
    if not catalogue.entries:
        raise AssertionError(
            f"the RCSR index at {rcsr.INDEX} loaded no nets")


def check_fragment_library(report) -> None:
    """The fragment picker has something in it."""
    from xtal.build import library

    fragments = library.entries()
    report(f"fragment library: {len(fragments)} fragments")
    if not fragments:
        raise AssertionError("the fragment library loaded nothing")


def check_samples(report) -> None:
    """The seven structures File > Open Sample offers are present.

    This is the resource lookup of point 2, asked before a window
    exists so that a failure names the real cause rather than
    presenting as an empty tab.
    """
    from xtalapp import samples

    found = samples.installed()
    report(f"samples: {len(found)} of {len(samples.SAMPLES)} present")
    if len(found) != len(samples.SAMPLES):
        missing = [s.file for s in samples.SAMPLES if s.path is None]
        raise AssertionError(
            f"looked in {samples.folder()} and did not find: "
            f"{', '.join(missing)}")


def check_extras(report) -> None:
    """The optional packages a packaged build promises are there.

    *Preferences > Engines* tells the user that RDKit and
    rdeditor are included and working.  In a bundle the user cannot
    check that, so this does.  The MOF builder used to be the third
    row and the one that said "not included"; it is vendored now and
    has a check of its own below.

    RDKit is the one worth exercising rather than importing: it is
    collected wholesale with ``collect_all`` and it carries data
    directories, so an import can succeed against a build whose
    parameter files did not come along.  Embedding a SMILES actually
    uses them.
    """
    from xtal import build as build_extra
    from xtalapp.dialogs import sketch

    if not build_extra.installed():
        raise AssertionError(
            "RDKit is missing, but the extras page says it is "
            "bundled.  The page is now lying to somebody who cannot "
            "check.")

    from xtal.build import chem

    # (symbols, cart, bonds, connections) -- benzene, so six carbons
    # and six hydrogens once RDKit has added them, with real
    # coordinates from a conformer rather than a parsed graph.
    symbols, cart, bonds, _connections = chem.embed("c1ccccc1")
    report(f"RDKit: benzene embedded, {len(symbols)} atoms, "
           f"{len(bonds)} bonds")
    if len(symbols) != 12 or len(cart) != 12:
        raise AssertionError(
            f"benzene embedded as {len(symbols)} atoms rather than "
            "12, which usually means RDKit's data files did not come "
            "along")

    if not sketch.installed():
        raise AssertionError(
            "rdeditor is missing, but the extras page says the "
            "sketcher is bundled")
    report("rdeditor: present")


def check_module_dialogs(report) -> None:
    """Every dialog an action names resolves, in this build.

    **The check that was missing, and it cost a bundle.**  A module
    declares its parameters as data and imports no Qt, so an action
    wanting a dialog of its own can only *name* one;
    ``xtalapp.dialogs.module_dialog`` turns that name into a class
    with ``importlib.import_module``.  PyInstaller's analysis cannot
    see through that, so the first build carrying the MOF builder had
    neither ``mof_build`` nor ``build_molecule`` in it, and *Build
    MOF*, *Build molecule* and *Insert molecule* all died on
    ``ModuleNotFoundError`` the moment they were clicked.

    The MOF check below went past it because it builds through
    ``xtal.mof.build`` and never touches the dialog -- the feature
    worked and the button did not.  Resolving is enough here: the
    failure is an import, and constructing a modal dialog in a
    selftest is a different and worse idea.
    """
    from xtalapp.dialogs import dialog_actions, dialog_modules, module_dialog

    actions = dialog_actions()
    for name in actions:
        if module_dialog(name) is None:
            raise AssertionError(
                f"the action {name!r} names a dialog and nothing "
                "answered to it")
    report(f"module dialogs: {len(actions)} actions resolve to "
           f"{len(dialog_modules())} modules")


def check_mof_builder(report) -> None:
    """The MOF builder builds a framework, in this build.

    **The check the bundle exists for.**  PORMAKE was excluded from
    packaged builds for being 889 MB, which made the MOF builder the
    single feature a packaged user could not have; it is vendored and
    trimmed now (``xtal/mof/pormake``) and the whole point is that it
    ships.  ``tests/test_packaging.py`` asserts that
    ``packaging/bundle.py`` *names* the 3271 nets and blocks.  Only
    this can say they survived PyInstaller.

    Exercised rather than imported, for the same reason RDKit is
    above and a stronger one: a build with the code and no database
    imports perfectly and then greys the entry out, which is
    indistinguishable to a user from the feature having been dropped
    again.  So it builds **pcu** and asks what came out -- which
    covers the database, the vendored code, ``ase``, the SciPy
    relaxation that replaced jax's gradient, and the net
    identification, in about a second.

    Then it builds **MFU-4l** on the same net, out of two of the four
    blocks this application ships of its own, which the first build
    cannot cover: those are package data of ``xtal.mof.library`` rather than
    of the vendored package, they are four files against 3271, and
    they are the only polydentate blocks there are -- so a bundle
    that dropped them would pass every check above and still be one
    that cannot build the material the feature was written for.
    """
    from xtal.mof import Catalog, database_root, has_ase, library_root

    root = database_root()
    if root is None:
        raise AssertionError(
            "the PORMAKE database did not come along.  The MOF "
            "builder is in this build and has nothing to build with; "
            "see PACKAGE_DATA in packaging/bundle.py.")
    if not has_ase():
        raise AssertionError(
            "ase is missing, so the MOF builder greys out in a build "
            "that was made to carry it.  The build job installs the "
            "`ase` extra; see .github/workflows/ci.yml.")

    catalogue = Catalog.default()
    nets = catalogue.topologies()
    blocks = catalogue.building_blocks()
    report(f"MOF catalogue: {len(nets)} nets, {len(blocks)} blocks")
    if len(nets) < 2000 or len(blocks) < 800:
        raise AssertionError(
            f"the catalogue is short: {len(nets)} nets and "
            f"{len(blocks)} blocks, against 2403 and 871")

    from xtal.mof.build import BuildRequest, build

    with tempfile.TemporaryDirectory(prefix="selftest-mof-") as folder:
        outcome = build(BuildRequest.parse("pcu", "N59", "E32"),
                        folder, catalogue)
    report(f"MOF builder: pcu-N59-E32, {outcome.n_atoms} atoms, "
           f"net identified as {outcome.net_name}")
    if not outcome.net_agrees:
        raise AssertionError(
            f"built pcu and got {outcome.net_name}.  The framework is "
            "wrong, which in a bundle means the vendored PORMAKE or "
            "its database is not what the tests ran against.")

    if library_root() is None:
        raise AssertionError(
            "the four polydentate blocks did not come along.  The "
            "builder has PORMAKE's 867 and cannot build MFU-4l; see "
            "PACKAGE_DATA in packaging/bundle.py.")
    with tempfile.TemporaryDirectory(prefix="selftest-mfu4l-") as folder:
        mfu4l = build(BuildRequest.parse("pcu", "MFU4l_Kuratowski",
                                         "MFU4l_BTDD"),
                      folder, catalogue)
    report(f"MOF builder: MFU-4l, {mfu4l.n_atoms} atoms, "
           f"{mfu4l.joints} joint(s) bonded")
    if mfu4l.n_atoms != 81 or mfu4l.joints != 12:
        raise AssertionError(
            f"MFU-4l on pcu came out {mfu4l.n_atoms} atoms and "
            f"{mfu4l.joints} joints, against 81 and 12.  Twelve is "
            "the bidentate count: six at six would mean the blocks "
            "arrived with their attachments read as single atoms.")


def check_window(report, shot: Path | None) -> None:
    """Build the real window, open a sample, and draw it.

    The one check that needs a display.  Everything above could run
    headless; this is the half that says the bundle's Qt plugins and
    VTK's OpenGL back end both survived being pruned.
    """
    from PySide6.QtWidgets import QApplication

    from xtalapp import samples
    from xtalapp.mainwindow import APP_NAME, MainWindow

    sample = samples.get(SAMPLE)
    if sample.path is None:
        raise AssertionError(f"{sample.file} is not in this build")

    from xtalapp.application import keep_siblings_non_native

    keep_siblings_non_native()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("CrystalBuilder")

    window = MainWindow()
    try:
        window.show()
        _settle(app, 600)          # realise the window before VTK

        window.open_path(sample.path)
        _settle(app, 600)

        document = window.current_document()
        if document is None:
            raise AssertionError(f"{sample.file} opened no document")
        sites = len(document.structure.sites)
        report(f"opened {sample.file}: {sites} sites")
        if not sites:
            raise AssertionError(f"{sample.file} opened with no atoms")

        viewport = window.current_viewport()
        if viewport is None or not hasattr(viewport, "save_image"):
            raise AssertionError("the tab has no 3D viewport")

        if shot is not None:
            shot.parent.mkdir(parents=True, exist_ok=True)
            _settle(app, 400)
            viewport.save_image(str(shot))
            if not shot.is_file() or shot.stat().st_size == 0:
                raise AssertionError(
                    f"the viewport wrote nothing to {shot}, so VTK has "
                    "no usable OpenGL context in this build")
            report(f"viewport image: {shot} "
                   f"({shot.stat().st_size} bytes)")
    finally:
        window.close()


def import_one(package: str, out=None) -> int:
    """Import one package and print its name and version; 0 if it
    imported.

    The Test button on Preferences > Engines asks a source checkout
    with ``python -c "import rdkit"``.  A frozen build has no
    ``python`` to ask -- ``sys.executable`` is the application -- so
    it is asked through this, in a process of its own, for the same
    reason: a package whose compiled half is broken can abort whatever
    imports it, and that must not be the window somebody is using.
    """
    import importlib

    out = sys.stdout if out is None else out
    try:
        module = importlib.import_module(package)
    except Exception as exc:                        # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=out, flush=True)
        return 1
    print(package, getattr(module, "__version__", ""), file=out,
          flush=True)
    return 0


def run(shot: Path | None = None, out=None) -> int:
    """Every check, in order, cheapest first.  0 if all of them pass.

    Cheapest first so that a bundle missing its metadata says so in
    milliseconds rather than after building a window; and the window
    check last so that everything which could have explained a blank
    tab has already been ruled out by the time one appears.
    """
    out = sys.stdout if out is None else out

    def report(line: str) -> None:
        print(f"  {line}", file=out, flush=True)

    # Otherwise tearing down a window with unsaved edits raises the
    # quit prompt, and nothing here can answer it.
    os.environ.setdefault("XTAL_NO_CONFIRM_CLOSE", "1")
    _refuse_dialogs()

    checks = [
        ("version", check_version),
        ("RCSR index", check_rcsr_index),
        ("fragment library", check_fragment_library),
        ("samples", check_samples),
        ("bundled extras", check_extras),
        ("module dialogs", check_module_dialogs),
        ("MOF builder", check_mof_builder),
        ("window and 3D view", lambda r: check_window(r, shot)),
    ]

    failures = 0
    for name, check in checks:
        print(f"{name}...", file=out, flush=True)
        try:
            check(report)
        except Exception:
            failures += 1
            traceback.print_exc(file=out)
            print(f"  FAILED: {name}", file=out, flush=True)

    if failures:
        print(f"\nselftest FAILED ({failures} of {len(checks)})",
              file=out, flush=True)
        return 1
    print("\nselftest passed", file=out, flush=True)
    return 0
