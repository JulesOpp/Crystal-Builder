"""A dialog is deleted on the GUI thread once it has answered.

``QDialog.exec`` leaves the dialog owned by Python, parent or no
parent, so the wrapper alone decides when the widgets go.  A dialog
whose callbacks hold it in a reference cycle -- a lambda over
``self``, a row that keeps its dialog -- is then freed by whichever
thread next runs the cyclic collector, and the next thread to
allocate is often a module run's worker (:mod:`xtalapp.workers`).
Widgets destroyed there segfault: the polymer builder's Build did,
three runs in three, with the collector on the worker's stack.

So every ``ask`` opens its dialog through :func:`answered`, which
asks Qt to delete it on the GUI thread's next turn whatever the
answer was.  Nothing is lost by it: the answer is read before
``ask`` returns, and a dialog nobody holds would have gone anyway.
"""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def answered(dialog):
    """``dialog``, deleted on the GUI thread once the block is done
    with it, however the block leaves."""
    try:
        yield dialog
    finally:
        dialog.deleteLater()


__all__ = ["answered"]
