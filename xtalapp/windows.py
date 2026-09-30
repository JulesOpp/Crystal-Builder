"""Bringing a window forward, in one place.

``activateWindow`` takes the keyboard from whatever the person is
doing, and on macOS brings the whole application in front of their
other work.  That is what a person asking for a window wants, and
what a test building one must never do: the refinement workbench's
tests took focus 63 times a run while everything else in the suite
stayed out of the way.  So every window the application brings
forward comes through :func:`present`, and ``tests/conftest.py``
replaces it with a show that is neither drawn nor activated -- the
same bargain :func:`xtalapp.menus.popup` strikes for context menus.
"""

from __future__ import annotations


def present(window, *, activate: bool = True) -> None:
    """Show ``window``, raise it, and give it the keyboard.

    ``activate=False`` raises without taking the keyboard: a window
    that comes up on its own, like a run's progress, must not steal
    typing from whatever the person is doing while they wait.
    """
    window.show()
    window.raise_()
    if activate:
        window.activateWindow()
