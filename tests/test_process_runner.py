"""The external-process runner, which DFTB+ and Zeo++ both go through.

Every test here launches this interpreter rather than a binary, so the
runner is under test on a machine with nothing installed -- which is
also the state a user's machine is in before they install DFTB+.
"""

import sys
import threading
import time

import pytest

from xtal.modules.job import Cancellation, Job
from xtal.modules.process import (
    ExternalProcess,
    MissingProgram,
    Program,
)
from xtal.workspace import RunLog, Workspace


def python(*script) -> list:
    return [sys.executable, "-u", "-c", *script]


COUNTER = (
    "import sys, time\n"
    "for i in range(int(sys.argv[1])):\n"
    "    print('line', i, flush=True)\n"
    "    time.sleep(float(sys.argv[2]))\n"
)


@pytest.fixture
def folder(tmp_path, rutile):
    from xtal.io import write_cif
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    return entry.next_run("test", "process")


# --------------------------------------------------- finding it first

def test_a_missing_binary_is_found_before_anything_is_launched():
    """`FileNotFoundError: [Errno 2] ... 'dftb+'` is a stack trace, not
    a sentence, and it arrives after the run folder has been made."""
    program = Program("definitely-not-installed", label="Nonesuch",
                      env_var="XTAL_NONESUCH",
                      url="https://example.invalid")
    with pytest.raises(MissingProgram) as raised:
        program.resolve()
    message = str(raised.value)
    assert "Nonesuch was not found" in message
    assert "example.invalid" in message


def test_availability_says_the_same_thing_without_raising():
    """The tree greys the module out before anybody clicks it, and the
    reason is the tooltip."""
    available = Program("definitely-not-installed",
                        label="Nonesuch").availability()
    assert not available
    assert "not installed" in available.reason


def test_an_explicit_path_beats_the_path(tmp_path):
    program = Program("definitely-not-installed")
    assert program.locate(sys.executable) == \
        __import__("pathlib").Path(sys.executable)
    assert program.found(sys.executable)


def test_an_environment_variable_is_looked_at(monkeypatch):
    monkeypatch.setenv("XTAL_TEST_BINARY", sys.executable)
    program = Program("definitely-not-installed",
                      env_var="XTAL_TEST_BINARY")
    assert program.found()


def test_a_directory_is_not_a_program(tmp_path):
    assert Program("definitely-not-installed").locate(tmp_path) is None


# ------------------------------------------------------- the run

def test_the_output_goes_into_the_log_as_it_arrives(folder):
    log = folder.log()
    process = ExternalProcess(python(COUNTER, "3", "0"),
                              cwd=folder.path, log=log)
    result = process.run()
    assert result.ok
    text = folder.run.log_path.read_text()
    assert "line 0" in text and "line 2" in text


def test_the_log_holds_the_command_that_was_run(folder):
    """A run folder with the exact command in it is a run somebody can
    reproduce by hand."""
    ExternalProcess(python(COUNTER, "1", "0"), cwd=folder.path,
                    log=folder.log()).run()
    assert "$ " in folder.run.log_path.read_text()


def test_the_log_is_live_rather_than_written_at_the_end(folder):
    """The log of a run that hung is the only evidence of where it
    hung, so the file has to fill up while the process is still
    going."""
    log = folder.log()
    seen = []
    process = ExternalProcess(python(COUNTER, "20", "0.05"),
                              cwd=folder.path, log=log)
    cancel = Cancellation()

    def peek():
        # Half a second in, some of it must already be on disk.
        time.sleep(0.5)
        seen.append(folder.run.log_path.read_text())
        cancel.cancel()

    threading.Thread(target=peek).start()
    process.run(cancel=cancel)
    assert seen and "line 0" in seen[0]
    assert "line 19" not in seen[0]


def test_stderr_and_stdout_land_in_one_stream(folder):
    script = ("import sys\n"
              "print('out', flush=True)\n"
              "print('err', file=sys.stderr, flush=True)\n")
    ExternalProcess(python(script), cwd=folder.path,
                    log=folder.log()).run()
    text = folder.run.log_path.read_text()
    assert "out" in text and "err" in text


def test_a_run_in_a_folder_writes_into_that_folder(folder):
    script = "open('made-here.txt', 'w').write('yes')\n"
    ExternalProcess(python(script), cwd=folder.path).run()
    assert (folder.path / "made-here.txt").read_text() == "yes"


# ---------------------------------------------------------- failure

def test_a_nonzero_exit_becomes_something_a_user_can_act_on(folder):
    script = ("import sys\n"
              "print('the parameter set has no Zn-O pair')\n"
              "sys.exit(2)\n")
    result = ExternalProcess(python(script), cwd=folder.path,
                             log=folder.log()).run()
    assert not result.ok
    assert result.returncode == 2
    assert "exited with status 2" in result.message()
    # The exit status says nothing; the last thing it printed says
    # everything.
    assert "Zn-O pair" in result.detail()
    assert "run.log" in result.detail()


def test_only_the_tail_is_kept_in_memory(folder):
    result = ExternalProcess(python(COUNTER, "500", "0"),
                             cwd=folder.path, tail=5).run()
    assert len(result.lines) == 5
    assert result.lines[-1] == "line 499"


def test_a_program_that_is_not_there_never_reaches_popen(folder):
    with pytest.raises(MissingProgram):
        ExternalProcess(["definitely-not-installed"],
                        cwd=folder.path).run()


def test_a_process_needs_a_program(folder):
    with pytest.raises(ValueError, match="needs a program"):
        ExternalProcess([], cwd=folder.path)


# ------------------------------------------------------- cancelling

def test_cancelling_terminates_the_process_rather_than_the_thread(
        folder):
    """Abandoning the reading thread leaves the binary running: still
    on the CPU, still writing into the run folder, and still there
    when the next run starts."""
    process = ExternalProcess(python(COUNTER, "1000", "0.05"),
                              cwd=folder.path, log=folder.log())
    cancel = Cancellation()
    threading.Timer(0.3, cancel.cancel).start()
    started = time.monotonic()
    result = process.run(cancel=cancel)
    assert time.monotonic() - started < 5.0
    assert result.cancelled
    assert not result.ok
    assert "was stopped" in result.message()
    assert not process.running


def test_a_process_that_ignores_the_signal_is_killed(folder):
    """Terminate, wait a moment for it to put itself away, kill what
    is left."""
    script = ("import signal, time\n"
              "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
              "print('ready', flush=True)\n"
              "time.sleep(60)\n")
    process = ExternalProcess(python(script), cwd=folder.path,
                              grace=0.5)
    cancel = Cancellation()
    threading.Timer(0.5, cancel.cancel).start()
    started = time.monotonic()
    result = process.run(cancel=cancel)
    assert result.cancelled
    assert time.monotonic() - started < 10.0


def test_cancelling_a_run_that_has_already_finished_is_harmless(folder):
    process = ExternalProcess(python(COUNTER, "1", "0"),
                              cwd=folder.path)
    result = process.run()
    assert result.ok
    process.cancel()                # must not raise


def test_cancelling_before_it_starts_stops_it_at_once(folder):
    """Stop pressed between opening the run folder and launching has
    to be honoured, not lost."""
    cancel = Cancellation()
    cancel.cancel()
    process = ExternalProcess(python(COUNTER, "1000", "0.05"),
                              cwd=folder.path)
    started = time.monotonic()
    result = process.run(cancel=cancel)
    assert result.cancelled
    assert time.monotonic() - started < 5.0


# ------------------------------------------- the stub, end to end

def test_the_stub_proves_the_whole_external_path(folder, rutile):
    """The registry, the job, the run folder, the log and the process
    runner, with no binary installed anywhere."""
    from xtal.modules import stub

    job = Job(structure=rutile,
              params={"steps": 2, "interval": 0.0, "note": "",
                      "fail": False},
              folder=folder)
    result = stub.count_in_a_subprocess(job)
    assert result.ok
    text = folder.run.log_path.read_text()
    assert "step 1 of 2" in text and "counted to 2" in text
    assert (folder.path / "counted.txt").exists()


def test_the_stub_can_be_stopped_mid_subprocess(folder, rutile):
    from xtal.modules import stub

    job = Job(structure=rutile,
              params={"steps": 1000, "interval": 0.05, "note": "",
                      "fail": False},
              folder=folder)
    threading.Timer(0.3, job.cancel.cancel).start()
    result = stub.count_in_a_subprocess(job)
    assert result.cancelled
    assert result.ok                    # stopping is not failing
    assert not (folder.path / "counted.txt").exists()


def test_the_stub_reports_a_failing_subprocess(folder, rutile):
    from xtal.modules import stub

    job = Job(structure=rutile,
              params={"steps": 1, "interval": 0.0, "note": "",
                      "fail": True},
              folder=folder)
    result = stub.count_in_a_subprocess(job)
    assert not result.ok
    assert "status 3" in result.message


def test_a_run_log_is_flushed_line_by_line(tmp_path):
    """The property the live log rests on, checked directly."""
    path = tmp_path / "run.log"
    log = RunLog(path)
    log.write("first")
    assert path.read_text() == "first\n"
    log.close()
