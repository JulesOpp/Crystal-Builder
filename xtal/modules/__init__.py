"""
xtal.modules
============
Things that can be run, and the machinery to run them.

Importing this package registers every module that ships in-tree.
Third-party modules register themselves through the
``crystal_builder.plugins`` entry point -- see :mod:`xtal.plugins` --
which is what makes "adding an engine touches no existing file"
literally true rather than nearly true.

    from xtal.modules import MODULES
    module, action = MODULES.find("stub.count")
    result = action.run(Job(structure=s, params=action.defaults()))

Everything here is headless, like the rest of ``xtal``: the menu, the
tree, the generated form and the worker thread are in ``xtalapp`` and
are a thin shell over this.

The stub module is registered only when ``XTAL_STUB_MODULE`` is set.
It exists to exercise the machinery -- see :mod:`xtal.modules.stub` --
and an entry called *Stub* in a shipped menu would be a confusing
thing to find.
"""

from __future__ import annotations

import os

from xtal.modules import build, dftb, forcefield, mof, net, pxrd, zeopp
from xtal.modules.job import Cancellation, Cancelled, Job, JobResult
from xtal.modules.process import (
    ExternalProcess,
    MissingProgram,
    ProcessResult,
    Program,
)
from xtal.modules.registry import (
    MODULES,
    Action,
    Availability,
    Module,
    ModuleError,
    ModuleRegistry,
    Param,
)

forcefield.register()
dftb.register()
zeopp.register()
mof.register()
build.register()
net.register()
pxrd.register()

if os.environ.get("XTAL_STUB_MODULE", "").strip().lower() not in (
        "", "0", "false", "no", "off"):
    from xtal.modules import stub
    stub.register()

__all__ = ["MODULES", "Action", "Availability", "Module",
           "ModuleError", "ModuleRegistry", "Param", "Job",
           "JobResult", "Cancellation", "Cancelled", "ExternalProcess",
           "MissingProgram", "ProcessResult", "Program"]
