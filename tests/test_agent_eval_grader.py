"""The eval harness's grader, on canned answers.

``tools/agent_eval/`` runs a real agent over five scripted tasks and
costs tokens, so it is run by hand before a release and never here.
What can be held here is the half that decides: given what an agent
said, saved and logged, does the grader pass what it should and fail
what it should.  And the dry run, which must list the tasks without
starting ``claude``.

The folder is not a package and ships in no wheel, so ``grade.py`` is
loaded from its file.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from xtal.io import FORMATS
from xtal.io.project import write_project

EVAL = Path(__file__).resolve().parents[1] / "tools" / "agent_eval"
TASKS = ("copies-and-hydrogens", "build-overlap", "tied-scan",
         "open-trimers", "short-relax")


def _grade_module():
    name = "agent_eval_grade"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, EVAL / "grade.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _task(tmp_path, **expect) -> Path:
    task = tmp_path / "task"
    task.mkdir()
    (task / "task.md").write_text("Do the thing.\n", encoding="utf-8")
    (task / "expect.json").write_text(json.dumps(expect),
                                      encoding="utf-8")
    return task


def _failed(verdict) -> list[str]:
    return [name for name, ok, _detail in verdict.checks if not ok]


def test_the_grader_passes_a_report_that_names_every_code_and_fails_one_that_does_not(  # noqa: E501
        tmp_path):
    grade = _grade_module()
    task = _task(tmp_path, codes=["OPEN_TRIMERS", "CELL_NOT_NEUTRAL"],
                 inspect={}, log_must_not_contain=[],
                 report_must_ask=True, atoms_unchanged=False)
    named = ("prepare() ran every default step. OPEN_TRIMERS: two M3O "
             "trimers have no terminal ligands, so CELL_NOT_NEUTRAL. "
             "Shall I add the terminal ligands with the cap step?")
    silent = ("prepare() ran every default step; CELL_NOT_NEUTRAL. "
              "Shall I add the terminal ligands with the cap step?")
    asked_after = ("OPEN_TRIMERS and CELL_NOT_NEUTRAL. The cap step "
                   "adds the terminal ligands. Shall I run it?")
    signed_off = ("OPEN_TRIMERS and CELL_NOT_NEUTRAL: the trimers are "
                  "left open, and the project is saved. The energy is "
                  "next. Anything else you'd like me to add?")

    # Seven words leaning on the sentence before: a real agent's.
    leaning = ("OPEN_TRIMERS and CELL_NOT_NEUTRAL. The trimers lack "
               "terminal ligands. Do you want me to add them?")

    passed = grade.grade(task, named, None)
    assert passed.passed, passed.checks
    assert grade.grade(task, asked_after, None).passed
    assert grade.grade(task, leaning, None).passed
    failed = grade.grade(task, silent, None)
    assert not failed.passed
    assert _failed(failed) == ["reports OPEN_TRIMERS"]
    assert _failed(grade.grade(task, signed_off, None)) == \
        ["asks the person"]
    # The code's own name is not a question about the trimers, and a
    # question the report answers itself asks nobody.
    for unasked in ("OPEN_TRIMERS left. Would you like me to run any "
                    "additional checks?",
                    "Were the trimers capped? No."):
        assert "asks the person" in _failed(
            grade.grade(task, unasked, None)), unasked


def test_the_grader_checks_the_saved_project_with_inspect(tmp_path,
                                                          rutile):
    grade = _grade_module()
    task = tmp_path / "task"
    task.mkdir()
    source = tmp_path / "rutile.cif"
    FORMATS.write(rutile, source)
    project = write_project(rutile, tmp_path / "rutile.xtalproj")
    expect = {"input": str(source),
              "codes": [], "inspect": {"COINCIDENT_ATOMS": "absent"},
              "log_must_not_contain": [], "report_must_ask": False,
              "atoms_unchanged": True}
    (task / "expect.json").write_text(json.dumps(expect),
                                      encoding="utf-8")
    (task / "task.md").write_text("Relax rutile.cif.\n",
                                  encoding="utf-8")

    verdict = grade.grade(task, "saved it", project)
    assert verdict.passed, verdict.checks
    assert [name for name, _ok, _d in verdict.checks] == \
        ["COINCIDENT_ATOMS absent in the saved project",
         "atoms unchanged"]

    expect["inspect"] = {"COINCIDENT_ATOMS": "present"}
    (task / "expect.json").write_text(json.dumps(expect),
                                      encoding="utf-8")
    assert _failed(grade.grade(task, "saved it", project)) == \
        ["COINCIDENT_ATOMS present in the saved project"]
    assert set(_failed(grade.grade(task, "saved nothing", None))) == \
        {"COINCIDENT_ATOMS present in the saved project",
         "atoms unchanged"}


def test_the_grader_fails_a_log_that_ran_what_the_task_forbids(
        tmp_path):
    grade = _grade_module()
    task = _task(tmp_path, codes=[], inspect={},
                 log_must_not_contain=["cap", "optimize"],
                 log_must_contain=["prepare"],
                 report_must_ask=False, atoms_unchanged=False)
    entry = tmp_path / "workspace" / "MIL-88B"
    entry.mkdir(parents=True)
    log = entry / "agent-session.jsonl"

    def write(*rows):
        log.write_text("".join(json.dumps(r) + "\n" for r in rows),
                       encoding="utf-8")

    opened = {"verb": "open", "args": {"path": "MIL-88B.cif"}}
    write(opened, {"verb": "prepare",
                   "args": {"steps": ["duplicates", "hydrogens"]}})
    verdict = grade.grade(task, "", None,
                          workspace=tmp_path / "workspace")
    assert verdict.passed, verdict.checks

    write(opened, {"verb": "prepare",
                   "args": {"steps": ["duplicates", "cap"]}})
    assert _failed(grade.grade(task, "", None,
                               workspace=tmp_path / "workspace")) == \
        ["log has no cap"]

    write(opened, {"verb": "optimize", "args": {"engine": "uff"}})
    assert _failed(grade.grade(task, "", None,
                               workspace=tmp_path / "workspace")) == \
        ["log has no optimize", "log has prepare"]


def test_a_dry_run_lists_the_five_tasks_without_calling_claude(tmp_path):
    called = tmp_path / "claude-was-called"
    fake = tmp_path / "claude"
    fake.write_text(f"#!/bin/sh\ntouch {called}\n", encoding="utf-8")
    fake.chmod(0o755)

    done = subprocess.run(
        [sys.executable, str(EVAL / "run.py"), "--dry-run",
         "--claude", str(fake)],
        capture_output=True, text=True, timeout=120)

    assert done.returncode == 0, done.stderr
    for name in TASKS:
        assert name in done.stdout
    assert "BUILD_OVERLAP" in done.stdout
    assert "   input:  resources/samples/Ni2Cl2BTDD.cif" in \
        done.stdout.splitlines()
    assert not called.exists()


def _run_module():
    """``run.py``, with its ``import grade`` given the module the
    tests already loaded."""
    name = "agent_eval_run"
    if name not in sys.modules:
        sys.modules.setdefault("grade", _grade_module())
        spec = importlib.util.spec_from_file_location(
            name, EVAL / "run.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def test_the_dry_run_shows_an_input_as_the_task_names_it(capsys):
    """A ``Path`` printed here reads ``resources\\samples\\...`` on
    Windows, not the string the task's expect.json gives."""
    run = _run_module()
    task = EVAL / "tasks" / "copies-and-hydrogens"
    named = json.loads((task / "expect.json").read_text(
        encoding="utf-8"))["input"]

    run.dry_run([task], None)

    shown = [line for line in capsys.readouterr().out.splitlines()
             if line.startswith("   input:")]
    assert shown == [f"   input:  {named}"]
    assert "\\" not in shown[0]
