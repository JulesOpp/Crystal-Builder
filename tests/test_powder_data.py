"""A measured pattern, a radiation, and whether RietX is there.

None of this needs RietX installed, and that is part of what it
tests: the refinement entries have to be able to say *why* they are
greyed out on a machine without the ``refine`` extra.
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from xtal import powder
from xtal.io.xy import read_columns, read_xy
from xtal.powder.data import PowderData, PowderError, Radiation


def _write(tmp_path, text, name="p.xy"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_an_xy_file_reads_as_ascending_two_theta_with_optional_sigma(
        tmp_path):
    """A refinement weights by the third column when every row has
    one; an overlay never looked at it and still does not."""
    rows = "\n".join(f"{10 + 0.1 * i:.2f} {100 + i} {3 + 0.01 * i}"
                     for i in reversed(range(20)))
    path = _write(tmp_path, "# 2theta I esd\n" + rows + "\n")
    data = PowderData.from_xy(path)
    assert np.all(np.diff(data.two_theta) > 0)
    assert data.sigma is not None
    assert data.sigma[0] == pytest.approx(3.0)
    assert data.intensity[0] == pytest.approx(100)
    assert data.name == "p"
    x, y = read_xy(path)
    assert len(x) == len(y) == 20


def test_a_third_column_with_a_zero_is_not_taken_as_weights(tmp_path):
    """A zero error is an infinite weight: one row would own the fit."""
    rows = "\n".join(f"{10 + i} {100 + i} {0 if i == 5 else 2}"
                     for i in range(20))
    _x, _y, sigma = read_columns(_write(tmp_path, rows))
    assert sigma is None


def test_a_pattern_with_a_repeated_angle_is_refused(tmp_path):
    """Two scans pasted into one file refine as neither of them."""
    rows = "\n".join(f"{10 + i % 12} {100 + i}" for i in range(24))
    with pytest.raises(PowderError, match="repeats"):
        PowderData.from_xy(_write(tmp_path, rows))


def test_a_window_keeps_the_points_between_its_ends():
    data = PowderData(np.arange(5.0, 50.0, 0.5), np.ones(90))
    part = data.window(10.0, 20.0)
    assert part.range == (10.0, 20.0)
    with pytest.raises(PowderError, match="points"):
        data.window(60.0, 70.0)


def test_synchrotron_radiation_refuses_a_missing_wavelength():
    """A guessed wavelength refines to a cell wrong by the guess."""
    with pytest.raises(PowderError, match="wavelength"):
        Radiation("synchrotron")
    assert Radiation("synchrotron", 0.4139).label.endswith("0.41390 Å")


def test_every_laboratory_radiation_names_a_rietx_preset():
    for key in ("cu", "cu-ka1", "mo", "mo-ka1", "co", "co-ka1"):
        assert Radiation(key).preset.endswith(("Ka", "Ka1"))
    with pytest.raises(PowderError, match="not a radiation"):
        Radiation("tungsten")


def test_the_refine_extra_is_detected_without_importing_rietx():
    """Loading numba to grey out a menu entry would cost every window
    two seconds, refinement or not."""
    code = ("import sys, xtal.powder as p; p.available(); p.missing(); "
            "print('rietx' in sys.modules, 'numba' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], check=True,
                         capture_output=True, text=True).stdout
    assert out.split() == ["False", "False"]


def test_the_missing_reason_names_the_extra(monkeypatch):
    monkeypatch.setattr(powder, "available", lambda: False)
    assert "crystal-builder[refine]" in powder.missing()
