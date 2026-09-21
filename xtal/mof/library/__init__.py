"""The blocks this application ships of its own, beside PORMAKE's 867.

A package and not a folder under ``resources/`` because a block that
is only in the checkout is a block the ``.dmg`` does not have, which
is exactly how ``MIL53.cif`` became unreachable: ``packaging/
bundle.py`` collects package data, and a sample folder outside a
package has to be remembered separately every time.

``blocks/`` holds the four cut out of ``MFU4l.cif`` and ``NiHITP.cif``
by the gesture *Mark as one connection point* -- every connection
point of every one of them stands for **two** atoms, which is what
none of PORMAKE's own do and what the whole of Phases 3 to 6 is
about.  There is no code here; :func:`xtal.mof.catalog.library_root`
finds the folder the way :func:`~xtal.mof.catalog.database_root`
finds PORMAKE's, with ``find_spec`` and never an import.
"""
