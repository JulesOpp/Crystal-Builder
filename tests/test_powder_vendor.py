"""A diffractometer's own file, read without exporting it first.

RietX reads them; these hold the seam -- :meth:`PowderData.from_file`
to :func:`xtal.powder.bridge.read_measurement` -- to the same numbers
the instrument wrote, and to saying what it chose for the person.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest_patterns import (
    COUNTS,
    TWO_THETA,
    write_bruker_raw,
    write_rasx,
    write_uxd,
)
from xtal import powder
from xtal.powder.data import (
    PowderData,
    PowderError,
    Radiation,
    anode_note,
    readable_extensions,
)
from xtal.workspace import classify

needs_rietx = pytest.mark.skipif(not powder.available(),
                                 reason="needs the refine extra")


@needs_rietx
@pytest.mark.parametrize("write, name", [
    (write_rasx, "scan.rasx"),
    (write_uxd, "scan.uxd"),
    (write_bruker_raw, "scan.raw"),
])
def test_a_vendor_file_reads_as_the_numbers_the_instrument_wrote(
        tmp_path, write, name):
    """A reader that put the profile on the wrong axis, or a header
    read at the wrong offset, refines a pattern that is not the
    measurement -- and it would still plot."""
    data = PowderData.from_file(write(tmp_path / name))
    np.testing.assert_allclose(data.two_theta, TWO_THETA, atol=1e-9)
    np.testing.assert_allclose(data.intensity, COUNTS)
    assert data.name == "scan"
    assert data.meta["anode"] == "Cu"
    assert data.notes == ()


@needs_rietx
def test_a_multi_scan_file_reads_its_first_scan_and_says_so(tmp_path):
    """Reading scan 0 of three is a choice made for the person; a
    pattern that does not say so looks like the whole file."""
    data = PowderData.from_file(write_rasx(tmp_path / "three.rasx",
                                           scans=3))
    np.testing.assert_allclose(data.intensity, COUNTS)
    assert data.meta["scan_count"] == "3"
    assert any("scan 0 of 3" in note for note in data.notes)


@needs_rietx
def test_a_raw_file_nobody_can_read_is_a_powder_error(tmp_path):
    """Six vendors write ``.raw``; one RietX does not read has to come
    back as a refusal the workbench shows, not a traceback."""
    path = tmp_path / "other.raw"
    path.write_bytes(b"\x00\x01SOMETHING ELSE" + bytes(200))
    with pytest.raises(PowderError):
        PowderData.from_file(path)


def test_without_rietx_a_vendor_file_names_the_extra(tmp_path,
                                                     monkeypatch):
    monkeypatch.setattr(powder, "available", lambda: False)
    with pytest.raises(PowderError, match="refine extra"):
        PowderData.from_file(tmp_path / "scan.rasx")
    assert ".rasx" not in readable_extensions()


def test_without_rietx_an_xy_is_read_as_it_always_was(tmp_path,
                                                      monkeypatch):
    monkeypatch.setattr(powder, "available", lambda: False)
    path = tmp_path / "p.xy"
    path.write_text("\n".join(f"{a} {b}" for a, b in zip(
        TWO_THETA, COUNTS, strict=True)), encoding="utf-8")
    data = PowderData.from_file(path)
    np.testing.assert_allclose(data.intensity, COUNTS)
    assert data.meta == {}


def test_a_window_keeps_what_the_file_said(tmp_path):
    data = PowderData(TWO_THETA, COUNTS, notes=("scan 0 of 3",),
                      meta={"anode": "Mo"})
    part = data.window(12, 18)
    assert part.notes == ("scan 0 of 3",)
    assert part.meta["anode"] == "Mo"


def test_a_file_measured_with_another_tube_is_said_not_switched():
    """The radiation box is the person's statement; the file's anode
    is a header field.  Disagreeing is worth saying, never acting
    on."""
    data = PowderData(TWO_THETA, COUNTS, meta={"anode": "Mo"})
    assert "Mo" in anode_note(data, Radiation("cu"))
    assert anode_note(data, Radiation("mo-ka1")) == ""
    assert anode_note(data, Radiation("synchrotron", 0.7)) == ""
    assert anode_note(PowderData(TWO_THETA, COUNTS),
                      Radiation("cu")) == ""


@pytest.mark.parametrize("name", ["a.rasx", "a.raw", "a.uxd", "a.xrdml",
                                  "a.brml"])
def test_a_vendor_file_in_the_workspace_is_a_pattern(tmp_path, name):
    """A pattern opens the workbench; a structure would be an error."""
    assert classify(tmp_path / name) == "pattern"
