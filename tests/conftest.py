"""Shared fixtures: four real structures, chosen to cover the cases
that break crystallography code.

* rutile   -- tetragonal, two Wyckoff sites, a framework
* quartz   -- trigonal, non-orthogonal cell, an atom on a special
              position (Si is 3a, so its multiplicity is half the
              general one)
* halite   -- face-centred cubic, so centring translations matter
* dry ice  -- cubic but molecular: four discrete CO2 molecules
"""

import atexit
import functools
import os
import re
import shutil
import tempfile

import pytest

from xtal import Lattice, Structure

# Nothing in a test run can answer a modal.  A widget test whose
# document still has unsaved edits hits the quit prompt when qtbot
# tears the window down, and the suite then waits on a human -- which
# looks like a hang under -q and like an invisible hang under
# QT_QPA_PLATFORM=offscreen, where the dialog is never even drawn.
# Set before any window is built, and for the whole session, so no
# test has to remember to.
os.environ.setdefault("XTAL_NO_CONFIRM_CLOSE", "1")

# And the same for the log.  ``xtalapp.applog`` writes to the
# platform's application-data folder -- ~/Library/Application Support
# on this machine -- and honours this variable ahead of everything
# else.  No test calls ``applog.start()``, but "no test does that
# today" is exactly the guarantee that expired the last time
# something in this suite reached the real preferences system and
# left 278 plists behind.  Set before any import can look.
_LOGS = tempfile.mkdtemp(prefix="xtal-test-logs-")
atexit.register(shutil.rmtree, _LOGS, ignore_errors=True)
os.environ.setdefault("XTAL_LOG_DIR", _LOGS)

# And the folder ``xtalapp.extras`` puts on sys.path, which lives
# beside the log for the same reason and must not be a real one
# either: revealing it creates it, and a test that reached that would
# make a directory in somebody's Application Support.
_PACKAGES = tempfile.mkdtemp(prefix="xtal-test-packages-")
atexit.register(shutil.rmtree, _PACKAGES, ignore_errors=True)
os.environ.setdefault("XTAL_PACKAGES_DIR", _PACKAGES)

# And the same for the workspace.  The application now *makes* the
# default workspace on a first run rather than only suggesting it --
# it does not let anybody work without one -- so a suite that let it
# answer with the real default would put a folder of runs in the
# developer's home directory on every run, which is the plists
# again with bigger files in it.
_WORKSPACE = tempfile.mkdtemp(prefix="xtal-test-workspace-")
atexit.register(shutil.rmtree, _WORKSPACE, ignore_errors=True)
os.environ.setdefault("XTAL_WORKSPACE_ROOT", _WORKSPACE)

# One BLAS thread per process.  OpenBLAS starts a thread per core in
# every worker, and its threads spin while they wait, so three xdist
# workers each fitting a powder pattern put 24 threads on 8 cores:
# a Pawley fit's SVD that takes 11 s alone took over 120 s beside
# another, and the workbench's auto tests timed out at random.  The
# fits gain nothing from the threads even alone (11.5 s on one, 12.4
# on eight).  Before ``xtal`` is imported, because OpenBLAS reads it
# when numpy loads; ``setdefault``, so a run can still ask for more.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

# RietX splits its compiled kernels over min(8, cores) threads unless
# told otherwise, and under xdist that is eight threads in each of
# three workers on an eight-core machine.  The parallelism is already
# one rank up, which is the case its own setting exists for.
os.environ.setdefault("RIETX_COMPILED_THREADS", "1")



def _settings_into_a_scratch_directory() -> None:
    """Keep QSettings out of the real preferences system.

    On macOS ``QSettings`` *is* CFPreferences, so every window a test
    builds talks to ``cfprefsd`` -- one system daemon, shared by every
    xdist worker -- and leaves a plist behind in
    ~/Library/Preferences that nothing ever removes.  Each window
    fixture names its domain after ``tmp_path``, so that is one new
    permanent preference domain per test: this suite had left 278 of
    them on the machine it was written on.

    Two things go wrong with that, and the second is the expensive
    one.  It is somebody's real preferences folder and the suite has
    no business writing there.  And eight workers hammering one
    daemon with new domains is a contention the suite cannot see
    inside: a full run would wedge about one time in six, blocked in
    Qt with no Python frame to blame, which reads as a hung suite.

    Pointing the INI backend at a directory of this process's own
    takes the same code path through a file instead, touching no
    daemon and nobody's preferences.  Done at import, because a
    fixture runs too late for a module-level ``AppSettings``.

    **``setDefaultFormat`` is not enough and looked like it was.**  On
    macOS the organisation/application constructors ignore it and hand
    back a NativeFormat object anyway, so this guard silently did
    nothing for as long as it has existed: 374 plists were sitting in
    ~/Library/Preferences when a test finally read one back from a
    previous run and failed on it.  The format has to be passed to the
    constructor, which is what ``XTAL_SETTINGS_DIR`` makes
    ``AppSettings`` do.
    """
    scratch = tempfile.mkdtemp(prefix="xtal-test-settings-")
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    # Spelled out rather than imported: this file is read before
    # anything else and the headless half of the suite has no Qt to
    # import xtalapp.settings through.
    os.environ.setdefault("XTAL_SETTINGS_DIR", scratch)
    try:
        from PySide6.QtCore import QSettings
    except ImportError:               # the headless half of the suite
        return
    QSettings.setDefaultFormat(QSettings.IniFormat)
    for scope in (QSettings.UserScope, QSettings.SystemScope):
        QSettings.setPath(QSettings.IniFormat, scope, scratch)


_settings_into_a_scratch_directory()


def _menus_out_of_the_system_menu_bar() -> None:
    """Keep a test window's menus off the machine's menu bar.

    On macOS a ``QMenuBar`` *is* the system menu bar, and Qt installs
    the one belonging to a window that was never shown just the same.
    So for the three minutes a full run takes, every shortcut this
    application has is live on the desktop -- and Qt spells ``Ctrl``
    as Command there, so a stray Cmd+R typed while the run holds the
    foreground opens *Display range* on whichever document a widget
    test is holding.  It arrives as ``DisplayRangeDialog.exec() would
    wait for a click`` against a test that never went near a dialog,
    and it lands on a different test each time.  A release build, run
    while somebody carries on using the machine, is exactly when that
    happens.

    Set at import because the attribute has to precede the
    ``QApplication``, which pytest-qt builds from a fixture.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError:               # the headless half of the suite
        return
    QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
    # The one the application sets too, so widget tests run with the
    # docks as the shipped window has them: not native windows.  See
    # xtalapp.application.keep_siblings_non_native.
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)


_menus_out_of_the_system_menu_bar()


#: The probe that decides whether this machine can render offscreen,
#: run in a process of its own.  A string because the whole point is
#: that it executes somewhere a crash cannot reach us.
_GL_PROBE = """
from xtalapp.viewport import vtk_scene
from xtalapp.viewport.scene import SceneModel

image = vtk_scene.render_to_array(SceneModel(), (8, 8))
raise SystemExit(0 if image.shape == (8, 8, 3) else 1)
"""


@functools.lru_cache(maxsize=1)
def offscreen_gl_works() -> bool:
    """Whether a real GL context can be had here, asked once.

    **Every test that calls ``window.Render()`` has to be behind
    this**, and a ``try/except`` around the render is not a
    substitute.  A machine with no GL driver does not raise: VTK
    reaches an access violation in C++ and the interpreter dies, so
    the ``except`` never runs and pytest goes down mid-run with a
    faulthandler dump and no results for anything, passed or failed.

    That is what the Windows runner did the first two times it ever
    got far enough to execute the suite -- it has no GPU -- and it
    was a different unguarded file each time.  Hence one shared
    answer here rather than a copy per module.

    The subprocess cannot take us with it: it crashes, we read a
    non-zero return code, and the caller skips.  Cached, so the cost
    is one interpreter start and one VTK import per session.
    """
    import subprocess
    import sys

    try:
        finished = subprocess.run(
            [sys.executable, "-c", _GL_PROBE],
            capture_output=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):    # pragma: no cover
        return False
    return finished.returncode == 0


#: What such a module puts in its ``pytestmark``.
needs_offscreen_gl = pytest.mark.skipif(
    not offscreen_gl_works(),
    reason="offscreen OpenGL is not available here")


_GUI_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:xtalapp|PySide6)\b",
                         re.MULTILINE)


def pytest_collection_modifyitems(config, items):
    """Mark every test in a module that brings in Qt as ``gui``.

    So a change to the headless core can be checked with
    ``-m "not gui"``: the other half of the suite, without the
    thousand-odd windows that are a quarter of its time.  Judged by
    what the *module* imports and not by fixture, because a test of a
    ``Document`` asks for no ``qtbot`` and is still a Qt test.
    """
    gui = pytest.mark.gui
    verdict: dict = {}
    for item in items:
        path = str(item.path)
        if path not in verdict:
            try:
                verdict[path] = bool(_GUI_IMPORT.search(
                    item.path.read_text(encoding="utf-8")))
            except OSError:                     # pragma: no cover
                verdict[path] = False
        if verdict[path]:
            item.add_marker(gui)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item):
    """Actually delete the windows a test built, before the next one.

    pytest-qt closes every widget a test registered and calls
    ``deleteLater`` on it, then ``processEvents`` -- and a deferred
    delete posted outside a running event loop is not delivered by
    ``processEvents``.  So no window was ever deleted.  They piled up
    until some later test happened to spin a real loop: 74 live
    ``MainWindow`` objects, 68 000 widgets, 86 threads (a file
    browser's ``QFileInfoGatherer`` per window) and 1.2 GB after a
    third of the suite.  The whole run got slower as every
    ``processEvents`` walked the heap of dead windows, and twice it
    aborted: dyld asserted while loading h5py for MACE, with the kernel
    reporting "pmap_enter retried due to resource shortage".

    This wraps pytest-qt's own teardown, so it runs after that has
    closed the widgets and the fixtures are finalised.
    """
    result = yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
    except ImportError:               # the headless half of the suite
        return result
    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None,
                                          QEvent.Type.DeferredDelete)
    return result


@pytest.fixture(scope="session")
def qapp_cls():
    """Run the suite under the application class ``main()`` builds.

    pytest-qt gives every widget test a plain ``QApplication``
    otherwise -- and the one thing this application overrides on it,
    the ``QFileOpenEvent`` that is how macOS hands a file to an
    already-running program, would then be untestable as well as
    untested.  It is a path no developer exercises by hand and the
    only one Finder uses.
    """
    from xtalapp.application import Application

    class OffScreen(Application):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            _keep_windows_off_screen(self)

    return OffScreen


def _keep_windows_off_screen(app) -> None:
    """Every window the suite shows is shown but never drawn.

    A window drawn on the developer's screen is a window that can take
    the keyboard from them -- 42 tests did, from the tests' own
    ``show()`` calls, a dialog's rows made as windows, and a progress
    dialog that raised itself.  Qt sends a window its Show event before
    it makes the native window, so marking it ``WA_DontShowOnScreen``
    there keeps it off the screen whoever showed it.  ``isVisible()``
    is still true and layouts still run; ``isExposed()`` never is, so
    ``with qtbot.waitExposed(...)`` would time out.  Installed once.

    An application-wide filter because nothing narrower holds:
    replacing ``setVisible`` in Python misses every Python subclass, a
    ``QMainWindow`` and a combo box's popup.  It is called for every
    event, which costs about 25 ms a GUI test.
    ``XTAL_SHOW_TEST_WINDOWS=1`` leaves it out, to watch a test's
    windows while debugging one.
    """
    from PySide6.QtCore import QEvent, QObject, Qt

    if getattr(app, "_off_screen", None) is not None \
            or os.environ.get("XTAL_SHOW_TEST_WINDOWS"):
        return

    class Filter(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Show \
                    and watched.isWidgetType() and watched.isWindow():
                watched.setAttribute(
                    Qt.WidgetAttribute.WA_DontShowOnScreen)
                watched.setAttribute(
                    Qt.WidgetAttribute.WA_ShowWithoutActivating)
            return False

    app._off_screen = Filter()
    app.installEventFilter(app._off_screen)


@pytest.fixture(autouse=True)
def _no_blocking_modal(monkeypatch):
    """Turn a modal dialog into a failure instead of a hung suite.

    ``QDialog.exec`` blocks until somebody clicks, and nobody will.
    Under -q that looks like a slow test; under
    QT_QPA_PLATFORM=offscreen the dialog is not even drawn, so the run
    hangs with nothing on screen to explain why.  Either way the
    person who finds it is a person who waited.

    A test that means to exercise a dialog patches ``exec`` (or the
    ``ask`` classmethod above it) itself, and that patch is applied
    after this one and wins.  Reaching this is always a bug in the
    test.
    """
    try:
        from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    except ImportError:               # the headless half of the suite
        return
    if QApplication.instance() is not None:
        # Made by something other than the qapp fixture.
        _keep_windows_off_screen(QApplication.instance())

    def refuse(self, *args, **kwargs):
        raise AssertionError(
            f"{type(self).__name__}.exec() would wait for a click. "
            "Patch it, or the classmethod that opens it.")

    monkeypatch.setattr(QDialog, "exec", refuse, raising=False)

    # A context menu waits the same way and is reached from a signal
    # rather than from a call the test can see.  ``QMenu.exec`` is
    # **not** patchable -- PySide resolves it in C++ and an override
    # on the class is ignored, which a test proved by hanging CI for
    # 27 minutes at 98 % -- so the application raises every context
    # menu through one function and that is what is replaced here.
    try:
        from xtalapp import menus
    except ImportError:                           # pragma: no cover
        return

    def refuse_popup(menu, position):
        raise AssertionError(
            "a context menu would wait for a click. Patch "
            "xtalapp.menus.popup if the test means to open one.")

    monkeypatch.setattr(menus, "popup", refuse_popup)

    # A window brought forward takes the keyboard from whatever the
    # developer is doing -- the workbench's tests did it 63 times a
    # run.  It is still shown, so ``isVisible`` means what it says;
    # the off-screen filter keeps it from being drawn, and this keeps
    # it from being activated.
    from xtalapp import windows

    def present_quietly(window, *, activate=True):
        window.show()

    monkeypatch.setattr(windows, "present", present_quietly)

    # QMessageBox's conveniences are static and do not go through
    # QDialog.exec, so they need blocking separately -- and they are
    # the ones reached from an error path nobody expected to reach.
    for name in ("question", "warning", "information", "critical",
                 "about"):
        def refuse_static(*args, _name=name, **kwargs):
            raise AssertionError(
                f"QMessageBox.{_name}() would wait for a click. "
                "Patch it if the test means to reach it.")

        monkeypatch.setattr(QMessageBox, name, refuse_static,
                            raising=False)


@pytest.fixture(autouse=True)
def _a_default_workspace_of_this_test_own(monkeypatch, tmp_path):
    """One default workspace per test, and never the real one.

    The window makes the default workspace when there is none to
    reopen -- it does not let anybody work without one -- so every
    window fixture in this suite now creates a workspace on the way
    up.  Two things go wrong without this.  It would be the
    developer's own ``~/Crystal Builder``, filled with entries by a
    test run.  And one directory shared by 2000 tests is a test that
    counts entries depending on what ran before it, which is the
    worst kind of failure to read.

    The process-wide ``XTAL_WORKSPACE_ROOT`` set at the top of this
    file is the safety net under this; this is the isolation.
    """
    monkeypatch.setenv("XTAL_WORKSPACE_ROOT",
                       str(tmp_path / "Crystal Builder"))


@pytest.fixture(autouse=True)
def _no_leftover_tool_hints():
    """Forget where a test said Zeo++ or DFTB+ is.

    ``xtal.modules.process`` holds the paths the GUI's preferences
    name in a module-level table, which is process-wide and outlives a
    test the way an environment variable would.  One test pointing at
    a fake binary in its own tmp_path would otherwise decide what
    every later test finds, and the later test would be the one that
    failed.
    """
    from xtal.modules import process
    process.clear_hints()
    yield
    process.clear_hints()

# Reference values from the literature, for tests that check we get
# real numbers out and not just self-consistent ones.
RUTILE_DENSITY = 4.25       # g/cm^3
QUARTZ_DENSITY = 2.65
QUARTZ_SI_O = 1.61          # Angstrom


@pytest.fixture
def rutile() -> Structure:
    """TiO2, P4_2/mnm (#136).  Ti on 2a, O on 4f."""
    return _rutile()


def _rutile() -> Structure:
    return Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        ["Ti", "O"],
        [[0.0, 0.0, 0.0], [0.30530, 0.30530, 0.0]],
        space_group="P4_2/mnm")


@pytest.fixture
def quartz() -> Structure:
    """alpha-SiO2, P3_221 (#154).  Si sits on the 3a special position
    (x, 0, 2/3) -- the multiplicity is 3, not 6."""
    return Structure.from_arrays(
        Lattice.from_parameters(4.9134, 4.9134, 5.4052, 90, 90, 120),
        ["Si", "O"],
        [[0.4697, 0.0, 2 / 3], [0.4135, 0.2669, 0.7857]],
        space_group="P3221")


@pytest.fixture
def halite() -> Structure:
    """NaCl, Fm-3m (#225).  192 operations, F centring."""
    return Structure.from_arrays(
        Lattice.cubic(5.6402), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="Fm-3m")


@pytest.fixture
def dry_ice() -> Structure:
    """CO2, Pa-3 (#205): four discrete molecules in the cell."""
    return Structure.from_arrays(
        Lattice.cubic(5.624), ["C", "O"],
        [[0.0, 0.0, 0.0], [0.118, 0.118, 0.118]], space_group="Pa-3")


@pytest.fixture
def rutile_xy(tmp_path, rutile):
    """A "measured" rutile pattern: Cu Kα doublet, 20-80°, Poisson
    noise on a flat background, calculated by RietX from the fixture.

    Synthetic so that the answer is known exactly -- the cell and the
    positions the pattern was made from -- and small, so a refinement
    test runs in a second.  Needs the ``refine`` extra.
    """
    return _rutile_xy(tmp_path, rutile)


@pytest.fixture(scope="module")
def rutile_xy_shared(tmp_path_factory):
    """:func:`rutile_xy`, made once for a module whose tests share one
    slow run over it -- an indexing search is seconds, not one."""
    return _rutile_xy(tmp_path_factory.mktemp("pattern"), _rutile())


def _rutile_xy(folder, structure):
    pytest.importorskip("rietx")
    import numpy as np

    from xtal.io.xy import write_xy
    from xtal.powder import bridge
    from xtal.powder.data import Radiation

    two_theta = np.arange(20.0, 80.0, 0.02)
    y = bridge.predict(structure, Radiation("cu"), two_theta)
    counts = np.random.default_rng(0).poisson(y / y.max() * 5000 + 100)
    return write_xy(two_theta, counts, folder / "rutile.xy",
                    header="synthetic rutile, Cu Ka1+Ka2")


@pytest.fixture
def rutile_cif(tmp_path, rutile) -> str:
    from xtal.io import write_cif
    path = tmp_path / "rutile.cif"
    write_cif(rutile, path)
    return str(path)


@pytest.fixture
def quartz_cif(tmp_path, quartz) -> str:
    from xtal.io import write_cif
    path = tmp_path / "quartz.cif"
    write_cif(quartz, path)
    return str(path)


@pytest.fixture
def rcsr_path():
    """The RCSR net file, on a checkout that has it.

    It is the input the shipped index is built from and is not needed
    to *use* the index, so a checkout without it skips these rather
    than failing: the tests that matter to a user run against the
    index, which is package data and is always there.
    """
    from xtal.analysis.rcsr import source_file
    path = source_file()
    if path is None:
        pytest.skip("resources/topo/RCSRnets-*.cgd is not in this tree")
    return path


@pytest.fixture(scope="session")
def rcsr_catalogue():
    """The shipped catalogue, read once for the whole session."""
    from xtal.analysis.rcsr import RcsrError, catalogue
    try:
        return catalogue()
    except RcsrError as exc:
        pytest.skip(str(exc))


#: 2-phenyl-BDC, ``[*:1]c1ccc([*:2])c(c2ccccc2)c1``: the phenyl ring
#: landed on a neighbouring linker on pcu/N16 built as found -- 0.37 A
#: where the fit's rounding happened to put it, with five hydrogens
#: once perceived bonded to two atoms each.  Drawn as written it is
#: 1.34 A with no search, and 1.77 with one.
PHENYL_BDC = "[*:1]c1ccc([*:2])c(c2ccccc2)c1"

#: 2,5-dimethoxy-BDC, ``[*:1]c1cc(OC)c([*:2])cc1OC``: 1.34 A under
#: consistent and 1.27 A as found, before a linker was turned for room.
DIMETHOXY_BDC = "[*:1]c1cc(OC)c([*:2])cc1OC"

#: 2,3,5,6-tetraphenyl-BDC: no angle about its axis clears the
#: neighbouring linkers on pcu/N16, so it overlaps whatever the fit's
#: rounding does -- the build ``test_mof_builder.py`` needs one of.
TETRAPHENYL_BDC = ("[*:1]c1c(c2ccccc2)c(c2ccccc2)c([*:2])"
                   "c(c2ccccc2)c1c1ccccc1")

#: The blocks as RDKit 2026.03 embedded them, recorded so that a test
#: of the builder needs no RDKit and builds one geometry everywhere.
#: ``from_smiles(SMILES, name=name)`` through ``write_building_block``
#: rewrites them.
RECORDED_BLOCKS = os.path.join(os.path.dirname(__file__), "data", "blocks")


@pytest.fixture
def phenyl_catalog(tmp_path):
    """A catalogue with three substituted BDCs beside PORMAKE's own,
    ``UPh``, ``UOMe`` and ``U4Ph``: the linkers that build, or used to
    build, on top of their neighbours on pcu/N16
    (``test_mof_builder.py``, ``test_mof_orientation.py``)."""
    from xtal.mof import Catalog, database_root

    if database_root() is None:
        pytest.skip("the vendored PORMAKE database is missing")
    folder = tmp_path / "blocks"
    folder.mkdir()
    for name in ("UPh", "UOMe", "U4Ph"):
        shutil.copyfile(os.path.join(RECORDED_BLOCKS, f"{name}.xyz"),
                        folder / f"{name}.xyz")
    return Catalog.default(also_blocks=(str(folder),))
