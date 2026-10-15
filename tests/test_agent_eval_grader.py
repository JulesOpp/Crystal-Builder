"""The eval harness's grader, on canned answers.

``tools/agent_eval/`` runs a real agent over seven scripted tasks and
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
         "open-trimers", "short-relax", "strain-sweep", "compare-two")


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


def test_a_dry_run_lists_every_task_without_calling_claude(tmp_path):
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
    assert "report says" in done.stdout
    assert ("   input:  resources/samples/HKUST1.cif, "
            "resources/samples/MOF-5.cif") in done.stdout.splitlines()
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


def test_the_grader_finds_each_number_within_its_tolerance(tmp_path):
    """A sweep is graded on its numbers.  A report that rounds to one
    place must pass, and one that is off by more than the tolerance
    must fail, naming the closest number it did give."""
    grade = _grade_module()
    task = _task(tmp_path, numbers=[
        {"label": "energy at 0.98 a", "value": 1977.58, "tol": 0.5},
        {"label": "energy at 1.02 a", "value": 2053.48, "tol": 0.5}])
    good = ("UFF single points: at 0.98 a, 1,977.6 kcal/mol; "
            "at 1.02 a, 2053.5 kcal/mol.")
    off = "UFF single points: 1977.6 and 2060.0 kcal/mol."

    assert grade.grade(task, good, None).passed
    failed = grade.grade(task, off, None)
    assert _failed(failed) == ["reports energy at 1.02 a"]
    detail = {name: d for name, _ok, d in failed.checks}
    assert "closest 2060" in detail["reports energy at 1.02 a"]
    assert _failed(grade.grade(task, "no numbers here", None)) == [
        "reports energy at 0.98 a", "reports energy at 1.02 a"]


def test_the_grader_reads_a_typeset_minus_and_a_thousands_separator():
    grade = _grade_module()
    assert grade.numbers_in("E = −1,234.5 then 2,002.33 and 7") \
        == [-1234.5, 2002.33, 7.0]


def test_a_hyphen_between_numbers_is_a_range_not_a_minus():
    """A report writes a range as "2.60-2.65" and a name as "MOF-5";
    reading either hyphen as a minus fails a report that gave the
    upper end of a range."""
    grade = _grade_module()
    assert grade.numbers_in("Cu-Cu 2.60-2.65 A in MOF-5; E = -12.5") \
        == [2.6, 2.65, 5.0, -12.5]


def test_a_report_must_name_each_word_case_aside(tmp_path):
    grade = _grade_module()
    task = _task(tmp_path, report_names=["HKUST"])
    assert grade.grade(task, "hkust-1 has the shorter Cu-Cu", None).passed
    assert _failed(grade.grade(task, "MOF-5 does", None)) == [
        "names HKUST"]


def test_a_task_may_hand_the_agent_several_inputs(tmp_path):
    """Comparing two structures needs both copied in; an atom count
    has nothing single to compare against then, and says so rather
    than comparing with the first."""
    grade = _grade_module()
    task = _task(tmp_path, atoms_unchanged=True, input=[
        "resources/samples/HKUST1.cif", "resources/samples/MOF-5.cif"])

    files = grade.input_files(task)
    assert [p.name for p in files] == ["HKUST1.cif", "MOF-5.cif"]
    assert all(p.is_file() for p in files)
    verdict = grade.grade(task, "", tmp_path / "unused.xtalproj")
    detail = {name: d for name, _ok, d in verdict.checks}
    assert detail["atoms unchanged"] == "the task has more than one input"


def test_the_dry_run_lists_every_input_of_a_task(tmp_path, capsys):
    run = _run_module()
    task = _task(tmp_path, input=[
        "resources/samples/HKUST1.cif", "resources/samples/MOF-5.cif"],
        numbers=[{"label": "d", "value": 2.63, "tol": 0.01}])

    run.dry_run([task], None)

    out = capsys.readouterr().out.splitlines()
    assert ("   input:  resources/samples/HKUST1.cif, "
            "resources/samples/MOF-5.cif") in out
    assert any("d: 2.63 +/- 0.01" in line for line in out)


def test_the_mcp_line_has_no_builtin_tool_and_this_server_alone():
    """A chat client has no shell and no file tools.  If the MCP run
    kept Bash, the agent would read the skill off disk and the eval
    would measure raw access twice."""
    run = _run_module()
    line = run.claude_command("claude", "Do it.", "mcp",
                              Path("cfg.json"))
    assert line[line.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in line
    assert line[line.index("--mcp-config") + 1] == "cfg.json"
    assert line[line.index("--allowedTools") + 1] == \
        "mcp__crystal-builder"
    raw = run.claude_command("claude", "Do it.", "raw")
    assert raw[raw.index("--allowedTools") + 1] == "Bash,Read,Write,Edit"
    assert "--mcp-config" not in raw


def test_both_ways_load_the_project_settings_alone():
    """Without ``--setting-sources project`` the agent loads the
    person's own settings: their plugins' hooks and skills reach it
    either way, which no chat client has, and the eval measures their
    setup instead of Crystal Builder's."""
    run = _run_module()
    for line in (run.claude_command("claude", "Do it.", "raw"),
                 run.claude_command("claude", "Do it.", "mcp",
                                    Path("cfg.json"))):
        assert line[line.index("--setting-sources") + 1] == "project"


def test_the_agent_inherits_no_host_claude_session(monkeypatch):
    """Started from inside a Claude Code session, the agent would
    otherwise take that session's variables -- its id, its SDK, its
    endpoint, its effort -- and run as a part of it, with turns and
    cost skewed by the host's effort, and the MCP way started before
    the server has listed its tools.  A key the person set is theirs,
    and stays, as does a name that merely contains CLAUDE."""
    run = _run_module()
    for name, value in (("CLAUDECODE", "1"),
                        ("CLAUDE_CODE_SESSION_ID", "x"),
                        ("CLAUDE_AGENT_SDK_VERSION", "y"),
                        ("CLAUDE_EFFORT", "high"),
                        ("CLAUDE_PID", "1"),
                        ("ANTHROPIC_BASE_URL", "z"),
                        ("MCP_CONNECTION_NONBLOCKING", "true"),
                        ("MCP_SERVER_CONNECTION_BATCH_SIZE", "4"),
                        ("DISABLE_MICROCOMPACT", "1"),
                        ("ANTHROPIC_API_KEY", "k"),
                        ("MY_CLAUDE_X", "1"),
                        ("HOME", "h")):
        monkeypatch.setenv(name, value)

    env = run._environment()

    for gone in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID",
                 "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_EFFORT",
                 "CLAUDE_PID", "ANTHROPIC_BASE_URL",
                 "MCP_CONNECTION_NONBLOCKING",
                 "MCP_SERVER_CONNECTION_BATCH_SIZE",
                 "DISABLE_MICROCOMPACT"):
        assert gone not in env
    assert env["ANTHROPIC_API_KEY"] == "k"
    assert env["MY_CLAUDE_X"] == "1"
    assert env["HOME"] == "h"
    assert env["PATH"].startswith(str(Path(sys.executable).parent))


def test_the_eval_server_is_headless_with_app_data_of_its_own(tmp_path):
    """Pointed at the person's own application data, ``xtal mcp``
    would find their window and the eval would edit their tabs."""
    run = _run_module()
    entry = run.server_entry(tmp_path)
    assert entry["args"] == ["-m", "xtal.cli", "mcp", "--headless"]
    assert entry["env"]["XTAL_APP_DATA"] == str(tmp_path / "appdata")


def test_the_mcp_preamble_says_what_the_raw_claude_md_says(tmp_path):
    run = _run_module()
    text = run.preamble(tmp_path, [Path("anywhere/MIL53.cif")])
    assert str(tmp_path / "MIL53.cif") in text
    assert str(tmp_path / "workspace") in text
    assert "by its code" in text


def test_turns_and_cost_are_read_from_the_json_answer():
    run = _run_module()
    out = json.dumps({"type": "result", "result": "done",
                      "num_turns": 7, "total_cost_usd": 0.31})
    assert run.usage(out) == (7, 0.31)
    assert run.final_text(out) == "done"
    assert run.usage("not json") == (None, None)


def test_the_table_puts_the_two_ways_side_by_side_with_a_parity_line():
    run = _run_module()
    results = {
        ("a", "raw"): ("yes", 9, 0.2, ""),
        ("a", "mcp"): ("no", 20, 0.5, "reports X"),
        ("b", "raw"): ("yes", 5, 0.1, ""),
        ("b", "mcp"): ("skipped", None, None, "needs mace")}
    lines = run.table(["a", "b"], ("raw", "mcp"), results).splitlines()
    # Padded to the widest cell: "passed" widens the task column.
    assert [c.strip() for c in lines[0].split(" | ")[:4]] == \
        ["task", "raw", "turns", "$"]
    assert "mcp: reports X" in lines[2]
    assert "0.50" in lines[2]
    parity = lines[-1]
    assert "2/2" in parity and "0/1" in parity


def test_a_dry_run_via_mcp_shows_the_line_and_the_server_and_calls_nothing(
        tmp_path):
    called = tmp_path / "claude-was-called"
    fake = tmp_path / "claude"
    fake.write_text(f"#!/bin/sh\ntouch {called}\n", encoding="utf-8")
    fake.chmod(0o755)

    done = subprocess.run(
        [sys.executable, str(EVAL / "run.py"), "--dry-run",
         "--via", "mcp", "--only", "short-relax", "--claude", str(fake)],
        capture_output=True, text=True, timeout=120)

    assert done.returncode == 0, done.stderr
    assert "--strict-mcp-config" in done.stdout
    assert "xtal.cli mcp --headless" in done.stdout
    assert not called.exists()
