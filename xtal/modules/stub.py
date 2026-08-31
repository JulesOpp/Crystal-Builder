"""
xtal.modules.stub
=================
A module that does nothing, so everything around modules can be tested.

The registry, the generated parameter form, the worker thread, the run
folder, the live log and the Stop button are one piece of machinery,
and none of it can be exercised by the Force Field panel -- which
predates all of it and does its own. The alternative is finding the
bugs in it while also writing DFTB+, which is the wrong place to
discover that cancelling leaves a process behind.

So: a module that counts.  It sleeps, it writes a line per tick, it
leaves a file, and it can be told to fail.  Two actions, because there
are two things worth proving:

* **Count here** runs in the worker thread and is stopped by being
  asked to look -- the in-process cancellation path.
* **Count in a subprocess** runs the same count through
  :class:`~xtal.modules.process.ExternalProcess` and is stopped by
  being killed -- the external path, which is the one DFTB+ and Zeo++
  will use.  It launches this interpreter rather than a binary, so it
  proves the runner on a machine with nothing installed.

It is **not registered by default**: a menu entry called *Stub* in a
shipped application is a confusing thing to find.  Set
``XTAL_STUB_MODULE=1`` to have it appear, which is also what its tests
do.
"""

from __future__ import annotations

import sys

from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param

OUTPUT_NAME = "counted.txt"

#: The subprocess half, as a program.  Deliberately unbuffered and
#: line by line, because what is being proved is that the log fills up
#: *while* it runs rather than at the end of it.
COUNTER = """
import sys, time
steps = int(sys.argv[1])
interval = float(sys.argv[2])
fail = sys.argv[3] == "1"
for i in range(1, steps + 1):
    print("step %d of %d" % (i, steps), flush=True)
    time.sleep(interval)
if fail:
    print("asked to fail", file=sys.stderr, flush=True)
    sys.exit(3)
print("counted to %d" % steps, flush=True)
"""

PARAMS = (
    Param("steps", "Steps", kind="int", default=5, minimum=1,
          maximum=1000, help="How many times round the loop"),
    Param("interval", "Wait between steps", kind="float", default=0.2,
          minimum=0.0, maximum=60.0, step=0.1, decimals=2,
          suffix=" s"),
    Param("note", "Note", kind="text", default="",
          help="Written at the top of the log, to prove that what "
               "the form collected is what the run received"),
    Param("fail", "Fail at the end", kind="bool", default=False,
          help="Finish by failing, to see what a failed run leaves "
               "behind"),
)


def count(job) -> JobResult:
    """Count, in this thread, stopping when asked."""
    steps = int(job.param("steps", 5))
    interval = float(job.param("interval", 0.2))
    note = str(job.param("note", ""))
    if note:
        job.note(f"note           {note}")
    job.note(f"counting to {steps}, {interval:g} s apart")
    done = 0
    for step in range(1, steps + 1):
        # Sleeping through the cancellation is what makes Stop feel
        # immediate: a job resting for ten seconds still stops in
        # milliseconds.
        if job.sleep(interval):
            return JobResult.stopped(
                f"stopped after {done} of {steps} steps")
        done = step
        job.say(f"step {step} of {steps}")
    written = _write_output(job, done)
    if job.param("fail"):
        return JobResult.failure(
            "the stub was asked to fail, and did",
            detail="Nothing went wrong; this action exists so that a "
                   "failed run can be looked at.")
    return JobResult(
        message=f"counted to {done}",
        artifacts=(written,) if written else ())


def count_in_a_subprocess(job) -> JobResult:
    """The same count, in a child process, stopped by killing it."""
    from xtal.modules.process import ExternalProcess

    if job.folder is None:
        return JobResult.failure(
            "this action writes its output into a run folder, and "
            "there is no workspace open to make one in")
    steps = int(job.param("steps", 5))
    interval = float(job.param("interval", 0.2))
    note = str(job.param("note", ""))
    if note:
        job.note(f"note           {note}")
    process = ExternalProcess(
        [sys.executable, "-u", "-c", COUNTER, str(steps),
         str(interval), "1" if job.param("fail") else "0"],
        cwd=job.folder.path, log=job.log,
        on_line=job.on_progress)
    result = process.run(cancel=job.cancel)
    if result.cancelled:
        return JobResult.stopped(result.message())
    if not result.ok:
        return JobResult.failure(result.message(),
                                 detail=result.detail())
    written = _write_output(job, steps)
    return JobResult(message=result.message(),
                     artifacts=(written,) if written else ())


def _write_output(job, steps: int):
    """Leave a file behind, which is the other half of what a module
    does."""
    if job.folder is None:
        return None
    path = job.file(OUTPUT_NAME)
    path.write_text("\n".join(f"{n}" for n in range(1, steps + 1))
                    + "\n")
    job.note(f"wrote {path.name}")
    return path


STUB = Module(
    name="stub",
    label="Stub",
    description="Counts, logs and writes a file.  It exists so that "
                "the registry, the form, the worker and the Stop "
                "button can be checked without a binary installed.",
    order=900,
    actions=(
        Action(name="count", label="Count here...",
               tip="Count in a worker thread, stopping when asked",
               params=PARAMS, run=count),
        Action(name="subprocess", label="Count in a subprocess...",
               tip="The same count in a child process, stopped by "
                   "terminating it",
               params=PARAMS, run=count_in_a_subprocess),
    ),
)


def register(registry=MODULES) -> Module:
    """Put the stub in a registry.  Called by ``xtal.modules`` when
    ``XTAL_STUB_MODULE`` is set, and by its own tests directly."""
    return registry.register(STUB)
