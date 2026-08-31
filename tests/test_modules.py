"""The module registry: declaration, parameters, jobs and run folders.

Headless throughout.  A module that can only be exercised by clicking
it is one whose parameters, run folder and log cannot be tested, which
is the reason the registry lives in ``xtal`` and not in ``xtalapp``.
"""

import pytest

from xtal.modules import record as module_record
from xtal.modules import stub
from xtal.modules.job import Cancellation, Cancelled, Job, JobResult
from xtal.modules.registry import (
    Action,
    Availability,
    Module,
    ModuleError,
    ModuleRegistry,
    Param,
)
from xtal.workspace import Workspace


@pytest.fixture
def registry() -> ModuleRegistry:
    """A registry of this test's own -- the global one is shared, and
    a test that registered into it would leak into the next."""
    return ModuleRegistry()


@pytest.fixture
def stubbed(registry) -> ModuleRegistry:
    stub.register(registry)
    return registry


@pytest.fixture
def entry(tmp_path, rutile):
    from xtal.io import write_cif
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    return Workspace.create(tmp_path / "ws").add_structure(source)


# ----------------------------------------------------- the registry

def test_a_module_is_found_by_its_dotted_path(stubbed):
    module, action = stubbed.find("stub.count")
    assert module.name == "stub"
    assert action.name == "count"


def test_an_unknown_module_says_what_there_is(stubbed):
    with pytest.raises(ModuleError, match="stub"):
        stubbed.find("dftb.optimise")


def test_an_unknown_action_says_what_the_module_has(stubbed):
    with pytest.raises(ModuleError, match="count"):
        stubbed.find("stub.nonsense")


def test_a_module_without_an_action_is_not_an_action(stubbed):
    with pytest.raises(ModuleError, match="names a module"):
        stubbed.find("stub")


def test_the_tree_order_is_the_declared_one(registry):
    for order, name in ((30, "third"), (10, "first"), (20, "second")):
        registry.register(Module(
            name=name, label=name, order=order,
            actions=(Action(name="go", label="Go", run=lambda job: None),
                     )))
    assert registry.names() == ["first", "second", "third"]


def test_an_action_needs_something_to_do():
    with pytest.raises(ModuleError, match="run callable"):
        Action(name="nothing", label="Nothing")


def test_a_broken_availability_check_does_not_take_the_menu_with_it():
    def explode():
        raise RuntimeError("the parameter directory is unreadable")

    module = Module(name="x", label="X", check=explode,
                    actions=(Action(name="go", label="Go",
                                    run=lambda job: None),))
    available = module.availability()
    assert not available
    assert "unreadable" in available.reason


def test_the_forcefield_is_registered_with_its_three_entries():
    from xtal.modules import MODULES

    module = MODULES.get("forcefield")
    assert [a.name for a in module.actions] == [
        "setup", "single-point", "optimise"]
    # All three are performed by the panel that predates the registry.
    assert all(a.shell for a in module.actions)


def test_the_stub_is_not_registered_unless_it_is_asked_for():
    """An entry called Stub in a shipped menu is a confusing thing to
    find, so it takes an environment variable to appear."""
    import os
    import subprocess
    import sys

    environment = dict(os.environ)
    environment.pop("XTAL_STUB_MODULE", None)
    out = subprocess.run(
        [sys.executable, "-c",
         "from xtal.modules import MODULES; print(MODULES.names())"],
        capture_output=True, text=True, check=True, env=environment)
    assert "stub" not in out.stdout


# ------------------------------------------------------- parameters

def test_a_parameter_knows_what_it_is_when_nobody_says():
    assert Param("a", kind="bool").default_value() is False
    assert Param("b", kind="int", minimum=2).default_value() == 2
    assert Param("c", kind="text").default_value() == ""
    assert Param("d", kind="choice",
                 choices=("x", "y")).default_value() == "x"


def test_strings_are_typed_by_the_parameter_that_wanted_them():
    """The command line and a saved session both hand back strings,
    and a module must not have to know which it was given."""
    assert Param("n", kind="int").coerce("7") == 7
    assert Param("f", kind="float").coerce("0.5") == 0.5
    assert Param("b", kind="bool").coerce("true") is True
    assert Param("b", kind="bool").coerce("0") is False


def test_a_number_out_of_range_is_clamped_not_refused():
    """A spinbox cannot produce one, so one that arrives came from a
    script -- and stopping a run over it helps nobody."""
    param = Param("n", kind="int", minimum=1, maximum=10)
    assert param.coerce(99) == 10
    assert param.coerce(-5) == 1


def test_a_choice_outside_the_choices_is_refused():
    param = Param("m", kind="choice", choices=("lbfgs", "fire"))
    with pytest.raises(ModuleError, match="lbfgs, fire"):
        param.coerce("newton")


def test_a_labelled_choice_gives_back_the_value_not_the_label():
    param = Param("m", kind="choice",
                  choices=(("lbfgs", "L-BFGS"), ("fire", "FIRE")))
    assert param.values_and_labels()[0] == ("lbfgs", "L-BFGS")
    assert param.coerce("fire") == "fire"


def test_unknown_keys_are_dropped_rather_than_passed_through(stubbed):
    """Almost always a stale saved value or a typo in a script, and a
    module that received one would have to guess what to do with it."""
    _module, action = stubbed.find("stub.count")
    values = action.coerce({"steps": 3, "colour": "blue"})
    assert values["steps"] == 3
    assert "colour" not in values


def test_an_unknown_kind_is_refused_where_it_is_declared():
    with pytest.raises(ModuleError, match="unknown parameter kind"):
        Param("x", kind="molecule")


# ----------------------------------------------------- cancellation

def test_cancelling_wakes_a_sleeping_job():
    """A job resting for ten seconds still has to stop in
    milliseconds."""
    import threading
    import time

    cancel = Cancellation()
    threading.Timer(0.05, cancel.cancel).start()
    started = time.monotonic()
    assert cancel.wait(10.0) is True
    assert time.monotonic() - started < 2.0


def test_a_callback_registered_after_the_fact_still_fires():
    """The race between Stop and a process that has just started has
    to be harmless in both orders."""
    cancel = Cancellation()
    cancel.cancel()
    fired = []
    cancel.when_cancelled(lambda: fired.append(True))
    assert fired == [True]


def test_one_callback_raising_does_not_stop_the_others():
    cancel = Cancellation()
    fired = []

    def explode():
        raise RuntimeError("no")

    cancel.when_cancelled(explode)
    cancel.when_cancelled(lambda: fired.append(True))
    cancel.cancel()
    assert fired == [True]


def test_check_raises_only_once_it_is_cancelled():
    cancel = Cancellation()
    cancel.check()
    cancel.cancel()
    with pytest.raises(Cancelled):
        cancel.check()


# ------------------------------------------------------------ a job

def test_a_job_with_no_workspace_runs_and_says_nothing_to_disk(rutile):
    """A structure with no workspace still runs; it just leaves
    nothing behind, which is what this application did before there
    was anywhere to leave anything."""
    said = []
    job = Job(structure=rutile, params={"steps": 2, "interval": 0.0},
              on_progress=said.append)
    assert job.log is None
    result = stub.count(job)
    assert result.ok
    assert said == ["step 1 of 2", "step 2 of 2"]


def test_naming_a_file_with_no_workspace_says_so(rutile):
    job = Job(structure=rutile)
    with pytest.raises(RuntimeError, match="nowhere"):
        job.file("out.txt")


def test_a_stopped_job_is_not_a_failure(rutile):
    job = Job(structure=rutile, params={"steps": 50, "interval": 0.01})
    job.cancel.cancel()
    result = stub.count(job)
    assert result.cancelled
    assert result.ok
    assert "stopped" in result.message


# ---------------------------------------------------- the run folder

def test_a_run_leaves_a_folder_named_by_what_made_it(entry, stubbed,
                                                     rutile):
    module, action = stubbed.find("stub.count")
    folder = module_record.open_run(entry, module, action,
                                    {"steps": 2, "interval": 0.0},
                                    rutile)
    result = stub.count(Job(structure=rutile,
                            params={"steps": 2, "interval": 0.0},
                            folder=folder))
    module_record.close_run(folder, result)

    assert folder.path.name == "stub-count-001"
    assert (folder.path / "counted.txt").read_text() == "1\n2\n"
    log = (folder.path / "run.log").read_text()
    assert "Stub: Count here" in log
    assert "module         stub.count" in log
    assert "counted to 2" in log
    assert "finished" in log


def test_every_parameter_the_run_was_given_is_in_its_log(entry,
                                                         stubbed,
                                                         rutile):
    """The question somebody asks of a log three months later is what
    it was run with."""
    module, action = stubbed.find("stub.count")
    params = action.coerce({"steps": 1, "interval": 0.0,
                            "note": "third attempt", "fail": False})
    folder = module_record.open_run(entry, module, action, params,
                                    rutile)
    module_record.close_run(folder, JobResult(message="done"))
    log = (folder.path / "run.log").read_text()
    assert "steps        1" in log
    assert "note         third attempt" in log
    assert "fail         off" in log


def test_a_failed_run_still_leaves_the_log_that_says_so(entry,
                                                        stubbed,
                                                        rutile):
    module, action = stubbed.find("stub.count")
    folder = module_record.open_run(entry, module, action, {}, rutile)
    module_record.close_run(folder, error="the binary went away")
    log = (folder.path / "run.log").read_text()
    assert "the run failed: the binary went away" in log
    assert "finished" in log


def test_a_stopped_run_says_it_is_where_it_got_to(entry, stubbed,
                                                  rutile):
    module, action = stubbed.find("stub.count")
    folder = module_record.open_run(entry, module, action, {}, rutile)
    module_record.close_run(folder, JobResult.stopped("stopped at 3"))
    log = (folder.path / "run.log").read_text()
    assert "where it got to" in log


def test_runs_are_numbered_across_the_whole_entry(entry, stubbed,
                                                  rutile):
    module, count = stubbed.find("stub.count")
    _module, subprocess_action = stubbed.find("stub.subprocess")
    first = module_record.open_run(entry, module, count, {}, rutile)
    second = module_record.open_run(entry, module, subprocess_action,
                                    {}, rutile)
    first.close()
    second.close()
    assert first.path.name == "stub-count-001"
    assert second.path.name == "stub-subprocess-002"


def test_no_entry_means_no_folder_and_no_exception(stubbed, rutile):
    module, action = stubbed.find("stub.count")
    assert module_record.open_run(None, module, action, {},
                                  rutile) is None
    module_record.close_run(None, JobResult())     # must not raise


def test_a_run_folder_reads_back_whatever_the_module_was_called(
        tmp_path, rutile):
    """A module called ``dftb+`` has to make a folder the tree can
    still parse -- which is the reason the module half of the name has
    no hyphen in it."""
    from xtal.io import write_cif
    from xtal.workspace import Run

    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    folder = entry.next_run("dftb+", "geometry-optimisation")
    run = Run.at(folder.path)
    assert run is not None
    assert (run.module, run.kind, run.index) == (
        "dftb+", "geometry-optimisation", 1)


def test_availability_is_a_reason_and_not_a_bare_false():
    assert bool(Availability(True))
    assert not Availability(False, "no binary")
    assert Availability(False, "no binary").reason == "no binary"


# ------------------------------------------------------------ plugins
#
# The claim in docs/PLAN.md § 14 is that adding an engine changes *no
# existing file*.  In-tree modules register themselves on import; these
# are the other half -- a package installed beside this one, whose
# entry point is called once at start-up.

class FakeEntryPoint:
    def __init__(self, name, register):
        self.name = name
        self._register = register

    def load(self):
        return self._register


@pytest.fixture
def plugin_group(monkeypatch):
    """Stand in for the installed entry points, and forget the load
    that any earlier test did."""
    from xtal import plugins

    entries = []
    monkeypatch.setattr(plugins, "_report", None)
    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda group=None: list(entries) if group == plugins.GROUP
        else [])
    return entries


def test_a_plugin_registers_without_any_file_changing(plugin_group,
                                                      registry):
    from xtal import plugins

    def register():
        registry.register(Module(
            name="zeopp", label="Zeo++",
            actions=(Action(name="pore-diameter", label="Pore...",
                            run=lambda job: None),)))

    plugin_group.append(FakeEntryPoint("zeopp", register))
    report = plugins.load()
    assert report.ok
    assert report.loaded == ["zeopp"]
    assert registry.find("zeopp.pore-diameter")[1].name == \
        "pore-diameter"


def test_a_broken_plugin_does_not_take_the_application_with_it(
        plugin_group):
    from xtal import plugins

    def register():
        raise ImportError("no module named 'zeopp_internals'")

    plugin_group.append(FakeEntryPoint("broken", register))
    report = plugins.load()
    assert not report.ok
    assert report.loaded == []
    assert "zeopp_internals" in report.summary()


def test_one_broken_plugin_does_not_stop_the_others(plugin_group,
                                                    registry):
    from xtal import plugins

    def explode():
        raise RuntimeError("no")

    def works():
        registry.register(Module(
            name="fine", label="Fine",
            actions=(Action(name="go", label="Go",
                            run=lambda job: None),)))

    plugin_group.append(FakeEntryPoint("broken", explode))
    plugin_group.append(FakeEntryPoint("fine", works))
    report = plugins.load()
    assert report.loaded == ["fine"]
    assert [name for name, _ in report.failures] == ["broken"]
    assert "fine" in registry


def test_loading_twice_is_free(plugin_group):
    from xtal import plugins

    calls = []
    plugin_group.append(
        FakeEntryPoint("counted", lambda: calls.append(True)))
    plugins.load()
    plugins.load()
    assert calls == [True]
    assert plugins.report().loaded == ["counted"]


def test_no_plugins_is_not_an_error(plugin_group):
    from xtal import plugins

    report = plugins.load()
    assert report.ok
    assert report.summary() == "no plugins installed"
