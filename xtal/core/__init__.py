"""Core crystallography: data model, symmetry, geometry.

Nothing in this package imports Qt or VTK.
"""

# spglib >= 2.5 keeps a deprecated global error flag; opting out makes
# it raise on failure instead of warning and returning None, which is
# the behaviour every caller in here is written against.  It is set
# once, for the package, because a module that forgets to set it does
# not fail loudly -- it gets a DeprecationWarning where it expected an
# answer, and under a suite that turns warnings into errors that
# surfaces as a symmetry operation quietly declining to name a group.
try:                                            # pragma: no cover
    import spglib.error as _spglib_error
    _spglib_error.OLD_ERROR_HANDLING = False
except (ImportError, AttributeError):           # pragma: no cover
    pass
