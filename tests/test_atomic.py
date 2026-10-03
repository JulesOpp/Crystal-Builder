"""``xtal.io.atomic``: a write that fails leaves the file that was
there, on every platform the application ships to."""

import os

from xtal.io import atomic


def _windows_fsync(fd) -> None:
    """``os.fsync`` as Windows has it: ``_commit``, which refuses a
    handle not open for writing.  A zero-byte write is refused on a
    read-only descriptor here too, so the rule holds on macOS."""
    os.write(fd, b"")


def test_the_flush_is_made_through_a_handle_windows_accepts(
        tmp_path, monkeypatch):
    """The partial file was fsynced through a read-only handle: macOS
    took it, and on Windows every save failed with EBADF."""
    monkeypatch.setattr(os, "fsync", _windows_fsync)
    target = tmp_path / "rutile.cif"
    target.write_text("old", encoding="utf-8")

    atomic.write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert not atomic.partial_path(target).exists()


def test_a_write_that_raises_leaves_the_old_file(tmp_path):
    target = tmp_path / "rutile.cif"
    target.write_text("old", encoding="utf-8")
    try:
        with atomic.replacing(target) as partial:
            partial.write_text("half", encoding="utf-8")
            raise RuntimeError("disk full")
    except RuntimeError:
        pass
    assert target.read_text(encoding="utf-8") == "old"
    assert not atomic.partial_path(target).exists()
