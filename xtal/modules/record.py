"""
xtal.modules.record
===================
The run folder a module leaves behind.

Phase C's rule was that **the module that runs writes the folder**, not
the tree that displays it -- which is what makes a run started from a
script produce the identical layout and open in the window.  This is
that rule for the module registry: two functions, used by the window's
worker and by the CLI, so a module author writes neither.

The header and the footer are fixed and the middle is the module's.
That is the shape a log has to have to be worth keeping: the version,
the structure, the action and every parameter it was given at the top;
whatever the module said in the order it said it; and at the bottom
what came of it and when it stopped.  A module that only prints numbers
still produces a log somebody can date, attribute and reproduce.
"""

from __future__ import annotations

from xtal.workspace import RunFolder, timestamp, write_header


def open_run(entry, module, action, params=None,
             structure=None) -> RunFolder | None:
    """Make the run folder for one action and start its log.

    ``None`` when there is no entry -- a document opened with no
    workspace still runs and simply leaves nothing behind, which is
    what this application did before there was anywhere to leave
    anything.  Callers get ``None`` rather than an exception because
    that case is normal, not exceptional.
    """
    if entry is None:
        return None
    folder = entry.next_run(module.name, action.run_kind)
    write_header(
        folder.log(), folder, structure,
        title=f"{module.label}: {action.label.rstrip('.')}",
        fields=[("module", f"{module.name}.{action.name}")],
        options=params)
    folder.log().blank()
    return folder


def close_run(folder: RunFolder | None, result=None,
              error: str = "") -> None:
    """Finish the log, and say how it ended.

    Safe on a run that failed, was cancelled or never started: the
    whole point of writing as the run goes is that what did happen is
    on disk even when the run did not finish.
    """
    if folder is None:
        return
    log = folder.log()
    log.blank()
    if error:
        log.write(f"the run failed: {error}")
    elif result is None:                            # pragma: no cover
        log.write("the run ended without a result")
    else:
        log.heading("Result")
        log.write(result.summary())
        if getattr(result, "detail", ""):
            log.write(result.detail)
        if result.cancelled:
            log.write("note: this run was stopped, so what is here is "
                      "where it got to")
        elif not result.ok:
            log.write("note: the run reported a failure")
        for path in getattr(result, "artifacts", ()) or ():
            if path is not None:
                log.write(f"wrote {path.name}")
    log.write(f"finished       {timestamp()}")
    folder.close()
