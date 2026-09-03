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
import os
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
    """
    try:
        from PySide6.QtCore import QSettings
    except ImportError:               # the headless half of the suite
        return
    scratch = tempfile.mkdtemp(prefix="xtal-test-settings-")
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    for scope in (QSettings.UserScope, QSettings.SystemScope):
        QSettings.setPath(QSettings.IniFormat, scope, scratch)


_settings_into_a_scratch_directory()


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
    return Application


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
        from PySide6.QtWidgets import QDialog, QMessageBox
    except ImportError:               # the headless half of the suite
        return

    def refuse(self, *args, **kwargs):
        raise AssertionError(
            f"{type(self).__name__}.exec() would wait for a click. "
            "Patch it, or the classmethod that opens it.")

    monkeypatch.setattr(QDialog, "exec", refuse, raising=False)

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

# Reference values from the literature, for tests that check we get
# real numbers out and not just self-consistent ones.
RUTILE_DENSITY = 4.25       # g/cm^3
QUARTZ_DENSITY = 2.65
QUARTZ_SI_O = 1.61          # Angstrom


@pytest.fixture
def rutile() -> Structure:
    """TiO2, P4_2/mnm (#136).  Ti on 2a, O on 4f."""
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
