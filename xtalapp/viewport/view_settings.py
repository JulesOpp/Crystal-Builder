"""Moved to :mod:`xtal.view.settings`; this name is kept for its importers."""
import sys

from xtal.view import settings as _moved

# The module itself and not a copy of its names, so a test that
# patches through this name patches what the core reads.
sys.modules[__name__] = _moved
