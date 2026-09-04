"""
``crystal-builder --selftest``: does this build actually work?

The ordinary suite tests a source checkout and can say nothing about a
frozen one.  This runs *inside* whatever it was built into, so CI can
launch the packaged executable and get a non-zero exit rather than a
screenshot nobody looks at.

It checks the four things that break in a bundle and nowhere else:

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
4. **The VTK OpenGL context.**  Rendering is the single largest thing
   in the bundle and the most likely to have been pruned too hard.
   Writing a PNG of the 3D view is the only honest way to ask.

**It never opens a dialog.**  A modal in a windowed build with nobody
at the keyboard is a hung CI job, not a failure, so the same bargain
as ``tests/conftest.py`` applies: reaching one is an error.
"""

from __future__ import annotations

import os
import sys
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
