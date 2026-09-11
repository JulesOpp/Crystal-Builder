"""The suite as a package, and it now has to be one.

Not import ceremony.  ``tests/`` was a *namespace* portion, and a
namespace portion loses to a regular ``tests`` package found anywhere
on ``sys.path`` -- whatever the order.  ``mace-torch`` ships its own
``tests/``, ``__init__.py`` and all, as a top-level package straight
into site-packages, so installing the ``mace`` extra made
``from tests.conftest_ff import water`` resolve to MACE's tests
instead of ours: 32 files failed to collect at once, and not one of
them had been touched.

An ``__init__.py`` here makes this directory a regular package as
well, and a regular package in the working directory is found before
one in site-packages.  Deleting the installed copy would work until
the next ``pip install``; this is ours to fix and cheap to keep.
"""
