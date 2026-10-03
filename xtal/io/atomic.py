"""Writing a file so that a failure leaves the one that was there.

Every writer used to open its target for writing and fill it, which
truncates first: a project whose CIF part raised was left a 22-byte
empty zip, and a crash, a kill or a full disk half way through left
half a file -- in each case over the user's last good copy, which Save
writes over silently by design.  So the bytes go to a sibling first,
are flushed to the disk, and only then take the target's name, which
``os.replace`` does in one step on both platforms.  The sibling is in
the same folder because a rename across file systems is a copy.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


def partial_path(path) -> Path:
    """Where ``path`` is written before it is renamed into place.

    ``.partial`` goes before the extension rather than after it, so a
    writer that puts its own suffix on whatever it is handed -- the
    project writer does -- still writes exactly here.
    """
    path = Path(path)
    return path.with_name(f"{path.stem}.partial{path.suffix}")


@contextmanager
def replacing(path):
    """Yield the path to write instead of ``path``; on a clean exit it
    replaces ``path``, and on an exception it is removed and ``path``
    is untouched."""
    path = Path(path)
    partial = partial_path(path)
    try:
        yield partial
        with open(partial, "rb") as written:
            os.fsync(written.fileno())
        os.replace(partial, path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def write_text(path, text: str, encoding: str = "utf-8") -> Path:
    """``Path.write_text``, through :func:`replacing`."""
    path = Path(path)
    with replacing(path) as partial:
        partial.write_text(text, encoding=encoding)
    return path


__all__ = ["partial_path", "replacing", "write_text"]
