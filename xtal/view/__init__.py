"""How a structure is drawn: a record and its choices, no Qt or VTK.

:mod:`~xtal.view.settings` is the record (``ViewSettings``) and what each
setting may be; :mod:`~xtal.view.styles` the named styles it chooses
among; :mod:`~xtal.view.colormaps` the scales *Colour by* draws with.
Moved from ``xtalapp/viewport/`` on 2026-10-23 so the agent's headless
``view`` and ``set_view`` can read and check it without importing the
window, which Principle 1 forbids (``tests/test_core_is_headless.py``).
The old module names are kept as aliases of these.
"""
