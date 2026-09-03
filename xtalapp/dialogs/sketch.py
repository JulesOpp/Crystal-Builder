"""
xtalapp.dialogs.sketch
======================
Whether the molecule can be drawn, and the words to say when it
cannot.

`rdeditor <https://github.com/EBjerrum/rdeditor>`_ is the 2D editor
:class:`xtalapp.dialogs.build_molecule._Sketch` was written to make
room for: a PySide6 widget over the same RDKit, LGPL-3.0, and used as
a dependency rather than vendored because that licence is the whole
of what makes it usable here.

**Its own extra and not part of ``build``.**  RDKit is a library;
rdeditor is a library plus PySide6 plus a theme package.  ``xtal/``
imports no Qt at all, so somebody installing ``[build]`` on a cluster
node to turn SMILES into structures must not be handed a widget
toolkit to get it.  Two extras, and ``[build]`` alone still greys the
Build entries in exactly the way it always did.

**Two greying axes, not one.**  No RDKit is the coarse one and is
unchanged: the menu entry itself is off, naming ``[build]``.  RDKit
without rdeditor is the fine one, and it is not an error -- the
dialog opens, the picture is the read-only depiction that shipped
with the fragment library, and it names this extra underneath.  A
feature that is missing says so where somebody is looking for it.

:func:`installed` is ``find_spec`` and never an import, the same rule
:func:`xtal.build.installed` follows and for a sharper reason here:
``rdeditor/__init__.py`` does ``from .rdEditor import MainWindow``, so
importing anything from the package executes a thousand-line
application shell and pulls in ``qdarktheme``.  That is fine at the
moment a dialog is built and unaffordable on every menu rebuild.
"""

from __future__ import annotations

import importlib.util

MISSING = ("rdeditor is not installed, so the molecule is drawn "
           "rather than drawable -- pip install "
           "'crystal-builder[sketch]'")


def installed() -> bool:
    """Whether ``rdeditor`` is importable -- without importing it.

    See the module docstring: importing it to find out costs a
    ``MainWindow`` class and a theme package that are never used.
    """
    try:
        return importlib.util.find_spec("rdeditor") is not None
    except (ImportError, ValueError):           # pragma: no cover
        return False


__all__ = ["MISSING", "installed"]
