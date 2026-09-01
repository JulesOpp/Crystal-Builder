"""Shared fixtures: four real structures, chosen to cover the cases
that break crystallography code.

* rutile   -- tetragonal, two Wyckoff sites, a framework
* quartz   -- trigonal, non-orthogonal cell, an atom on a special
              position (Si is 3a, so its multiplicity is half the
              general one)
* halite   -- face-centred cubic, so centring translations matter
* dry ice  -- cubic but molecular: four discrete CO2 molecules
"""

import os

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
