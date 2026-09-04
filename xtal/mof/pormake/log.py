"""Configure PORMAKE's single shared logger.

PORMAKE routes all of its diagnostics through one module-level
``logger`` named ``"unique_logger"``. Centralizing on a single logger
keeps the assembly pipeline's output consistent and lets callers toggle
verbosity from one place. The logger sets ``propagate = False`` so its
records do not bubble up to the root logger and collide with logging
configured by other libraries.

Two handlers are attached. A :class:`logging.NullHandler` stands where
upstream wrote ``runtime.log`` -- see the note beside it -- while a
:class:`logging.StreamHandler` prints a simplified ``>>>``-prefixed
message to the console at ``INFO`` and above. The helper functions in
this module raise or lower each handler's threshold so users can quiet
or restore console and file output independently at runtime.
"""

import logging

# Make a logger. Pormake uses a single logger.
logger = logging.getLogger("unique_logger")
# To prevent colloisions with loggers in other libraries.
logger.propagate = False
# Log all levels.
logger.setLevel(logging.DEBUG)

# Setting for the file logs.
#
# Upstream opened ``runtime.log`` in the *current directory*, mode
# "w", right here -- at import.  That is somebody's home folder, or
# wherever they launched the application from, and a file of theirs
# with that name was truncated by an import they never asked for.
# ``xtal.mof.build`` used to contain that by swapping
# ``logging.FileHandler`` out for the length of the import; vendoring
# lets it be fixed where it happens instead.
#
# Nothing is lost.  ``xtal.mof.build`` takes these handlers off and
# forwards the logger into the run's own log, which is where this
# trace belonged: beside everything else that happened in the run,
# rather than in a file next to the executable.  The handler stays a
# handler so the four helpers below still mean something.
file_log_handler = logging.NullHandler()
file_log_handler.setLevel(logging.DEBUG)

_format = (
    "[%(asctime)s (%(levelname)s) " "%(filename)s:%(lineno)s] " "%(message)s"
)

formatter = logging.Formatter(
    fmt=_format,
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_log_handler.setFormatter(formatter)

# Setting for the console logs.
console_log_handler = logging.StreamHandler()
console_log_handler.setLevel(logging.INFO)
# Simple formatter.
formatter = logging.Formatter(fmt=">>> %(message)s")
console_log_handler.setFormatter(formatter)

# Add the handlers to the logger.
logger.addHandler(file_log_handler)
logger.addHandler(console_log_handler)


def disable_print():
    """Silence console messages below the ``WARNING`` level.

    Raises the console handler's threshold to ``WARNING`` so routine
    ``INFO``/``DEBUG`` progress messages no longer print to the screen.
    """
    console_log_handler.setLevel(logging.WARNING)
    logger.warning("Console logs (under WARNING level) are disabled.")


def enable_print():
    """Restore console messages at the ``INFO`` level and above.

    Lowers the console handler's threshold back to ``INFO``, undoing a
    previous :func:`disable_print` call.
    """
    console_log_handler.setLevel(logging.INFO)
    logger.warning("Console logs (under WARNING level) are enabled.")


def disable_file_print():
    """Silence file-log messages below the ``WARNING`` level.

    Raises the file handler's threshold to ``WARNING`` so the file
    log records only warnings and errors.
    """
    file_log_handler.setLevel(logging.WARNING)
    logging.warning("File logs (under WARNING level) are disabled.")


def enable_file_print():
    """Restore full ``DEBUG``-level logging to the file.

    Lowers the file handler's threshold back to ``DEBUG`` so every
    level is written again, undoing :func:`disable_file_print`.
    """
    file_log_handler.setLevel(logging.DEBUG)
    logging.warning("File logs (all levels) are enabled.")
