"""What shiboken holds, for the tests that must leave nothing behind.

A wrapper for an object Qt made and Qt later frees is not told: it
stays in shiboken's map under the freed address, and whatever Qt
allocates there next is handed to Python as the old wrapper.  These
count the kind that has done it, so a test can say it made none.
"""

from __future__ import annotations

import gc

import shiboken6
from PySide6.QtGui import QStandardItem


def item_wrappers() -> int:
    """How many QStandardItem wrappers shiboken holds, stranded or
    not: greying and reading a combo's entries should add none."""
    gc.collect()
    return sum(type(w) is QStandardItem
               for w in shiboken6.getAllValidWrappers())
