"""
Run the skill eval: seven scripted tasks, each given to Claude Code
headless (``claude -p``) in a project of its own with the skill
installed, and graded by ``grade.py``.

``--via mcp`` gives the agent a chat client's view instead: no skill,
no ``CLAUDE.md``, no built-in tool, only ``xtal mcp --headless``'s
tools; ``--via both`` runs each task both ways and prints them side by
side.

    python tools/agent_eval/run.py --dry-run     # what would run
    python tools/agent_eval/run.py               # all seven; tokens
    python tools/agent_eval/run.py --only tied-scan

Run it with the Python that has Crystal Builder installed: the agent
is told to use this interpreter, and the grader imports ``xtal``.  It
uses the person's own Claude Code login; there is no key here.

Each task runs in a temporary folder **outside** the checkout, so the
agent reads the skill and nothing of this repository's own
``CLAUDE.md``; what it left is copied to ``runs/<time>/<via>/<task>/``
afterwards (ignored by git).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import grade

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
RUNS = HERE / "runs"

#: The tools the agent may use without asking; ``-p`` has nobody to
#: ask.
ALLOWED_TOOLS = "Bash,Read,Write,Edit"

#: Seconds one task may take.  A relaxation of 104 atoms is a second;
#: what takes the time is the agent.
TIMEOUT = 1800

#: Above this line of ``task.md`` is the prompt; below it, notes for
#: the person running the eval.
RULE = "---"

#: What ``--via`` chooses between: Claude Code with the skill and a
#: shell, or a chat client's view -- this server's tools and nothing
#: else.
VIAS = ("raw", "mcp")

#: The server's name in the agent's MCP config, which its tools are
#: listed under (``mcp__crystal-builder__open``).
SERVER = "crystal-builder"


class ClaudeFailed(RuntimeError):
    """``claude`` itself did not run the task -- not logged in, a bad
    flag, a crash -- which is not the agent failing a check."""


def task_dirs(only: str | None = None) -> list[Path]:
    found = sorted(p for p in TASKS.iterdir()
                   if (p / "task.md").is_file())
    if only is not None:
        found = [p for p in found if p.name == only]
        if not found:
            names = ", ".join(p.name for p in task_dirs())
            raise SystemExit(f"no task called {only!r}; the tasks are "
                             f"{names}")
    return found


def prompt_of(task: Path) -> str:
    text = (task / "task.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    if RULE in (line.strip() for line in lines):
        lines = lines[:[line.strip() for line in lines].index(RULE)]
    return "\n".join(lines).strip()


def missing_needs(task: Path) -> list[str]:
    needs = grade.expectations(task).get("needs", [])
    return [n for n in needs if importlib.util.find_spec(n) is None]


def find_claude(given: str | None) -> Path | None:
    """``--claude``, else ``claude`` on PATH, else Claude Code's own
    local install."""
    if given:
        return Path(given).expanduser()
    on_path = shutil.which("claude")
    if on_path:
        return Path(on_path)
    local = Path.home() / ".claude" / "local" / "claude"
    return local if local.is_file() else None


def claude_command(claude, prompt: str, via: str,
                   config=None) -> list[str]:
    """The ``claude -p`` line for one task.  Raw: the shell and file
    tools, as before.  MCP: no built-in tool at all (``--tools ""``),
    this server alone (``--strict-mcp-config`` leaves out the
    person's own), and its tools allowed without asking."""
    line = [str(claude), "-p", prompt, "--output-format", "json"]
    if via == "raw":
        return [*line, "--allowedTools", ALLOWED_TOOLS]
    return [*line, "--tools", "", "--mcp-config", str(config),
            "--strict-mcp-config", "--allowedTools", f"mcp__{SERVER}"]


def server_entry(folder: Path) -> dict:
    """``xtal mcp --headless`` under this Python, with application
    data of its own, so it never finds the person's window."""
    return {"command": sys.executable,
            "args": ["-m", "xtal.cli", "mcp", "--headless"],
            "env": {"XTAL_APP_DATA": str(folder / "appdata")}}


def preamble(folder: Path, inputs: list[Path]) -> str:
    """What the raw harness's ``CLAUDE.md`` tells the agent, said in
    the prompt instead: a chat client has no ``CLAUDE.md``."""
    lines = []
    if inputs:
        named = ", ".join(f"`{folder / p.name}`" for p in inputs)
        lines.append(f"The input: {named}.")
    lines.append(f"The Crystal Builder workspace is "
                 f"`{folder / 'workspace'}`: pass it as `workspace` "
                 f"when you open or build a structure, and save there.")
    lines.append("In your final report, name every diagnostic you met "
                 "by its code, as the tools give it.")
    return "\n".join(lines)


# ----------------------------------------------------------------------

def dry_run(tasks: list[Path], claude: Path | None,
            vias=("raw",)) -> int:
    print(f"claude: {claude or 'not found (pass --claude PATH)'}")
    print(f"python: {sys.executable}")
    print(f"{len(tasks)} task(s) via {', '.join(vias)}; nothing is "
          f"run\n")
    for task in tasks:
        expect = grade.expectations(task)
        print(f"== {task.name}")
        # As expect.json names it: a Path would print backslashes on
        # Windows.
        given = expect.get("input") or "(none)"
        shown = ", ".join(given) if isinstance(given, list) else given
        print(f"   input:  {shown}")
        prompt = " ".join(prompt_of(task).split())
        for line in textwrap.wrap(prompt, 66):
            print(f"   | {line}")
        for label, value in _expectation_lines(expect):
            print(f"   {label:<22}{value}")
        for via in vias:
            line = claude_command(claude or "claude", "<prompt>", via,
                                  "<folder>/mcp.json")
            print(f"   via {via}: {shlex.join(line)}")
            if via == "mcp":
                entry = server_entry(Path("<folder>"))
                print(f"   server:  "
                      f"{shlex.join([entry['command'], *entry['args']])}")
        missing = missing_needs(task)
        if missing:
            print(f"   would be skipped: needs {', '.join(missing)}")
        print()
    return 0


def _expectation_lines(expect: dict):
    if expect.get("codes"):
        yield "report names", ", ".join(expect["codes"])
    for code, state in expect.get("inspect", {}).items():
        yield "saved project", f"{code} {state}"
    if expect.get("log_must_contain"):
        yield "log has", ", ".join(expect["log_must_contain"])
    if expect.get("log_must_not_contain"):
        yield "log has no", ", ".join(expect["log_must_not_contain"])
    if expect.get("report_must_ask"):
        yield "report", "asks the person"
    if expect.get("atoms_unchanged"):
        yield "atoms", "unchanged from the input"
    for number in expect.get("numbers", []):
        yield "report gives", (f"{number['label']}: {number['value']:g}"
                               f" +/- {number['tol']:g}")
    if expect.get("report_names"):
        yield "report says", ", ".join(expect["report_names"])
    if expect.get("needs"):
        yield "needs", ", ".join(expect["needs"])


# ----------------------------------------------------------------------

def run_task(task: Path, claude: Path, out: Path, via: str = "raw"):
    """``(verdict, turns, cost)`` of one task run one way."""
    folder = Path(tempfile.mkdtemp(
        prefix=f"xtal-eval-{via}-{task.name}-"))
    try:
        prompt, config = prompt_of(task), None
        if via == "raw":
            _set_up(task, folder)
        else:
            inputs = _copy_inputs(task, folder)
            config = folder / "mcp.json"
            config.write_text(json.dumps(
                {"mcpServers": {SERVER: server_entry(folder)}},
                indent=1), encoding="utf-8")
            prompt = f"{preamble(folder, inputs)}\n\n{prompt}"
        done = subprocess.run(
            claude_command(claude, prompt, via, config),
            cwd=folder, capture_output=True, text=True,
            timeout=TIMEOUT, env=_environment())
        (folder / "transcript.json").write_text(done.stdout,
                                                encoding="utf-8")
        if done.stderr:
            (folder / "stderr.txt").write_text(done.stderr,
                                               encoding="utf-8")
        if done.returncode != 0:
            said = (done.stderr or done.stdout).strip().splitlines()
            raise ClaudeFailed(f"claude exited {done.returncode}"
                               f"{': ' + said[-1] if said else ''}")
        report = final_text(done.stdout)
        projects = sorted(folder.rglob("*.xtalproj"),
                          key=lambda p: p.stat().st_mtime)
        verdict = grade.grade(task, report,
                              projects[-1] if projects else None,
                              workspace=folder / "workspace")
        turns, cost = usage(done.stdout)
        (folder / "verdict.json").write_text(json.dumps(
            {"passed": verdict.passed, "checks": verdict.checks,
             "turns": turns, "cost": cost}, indent=1), encoding="utf-8")
        return verdict, turns, cost
    finally:
        shutil.copytree(folder, out / via / task.name,
                        ignore=shutil.ignore_patterns(".claude",
                                                      "appdata"))
        shutil.rmtree(folder, ignore_errors=True)


def _copy_inputs(task: Path, folder: Path) -> list[Path]:
    copied = []
    for source in grade.input_files(task):
        shutil.copy2(source, folder / source.name)
        copied.append(folder / source.name)
    return copied


def _set_up(task: Path, folder: Path) -> None:
    subprocess.run([sys.executable, "-m", "xtal.cli", "skill",
                    "install", "--project", str(folder)],
                   check=True, capture_output=True, text=True)
    _copy_inputs(task, folder)
    workspace = folder / "workspace"
    (folder / "CLAUDE.md").write_text(textwrap.dedent(f"""\
        # Crystal Builder

        - The Crystal Builder workspace for this project is
          `{workspace}`: pass it as `workspace=` when you open or
          build a structure, and save there.
        - The Python with Crystal Builder installed is
          `{sys.executable}`; the `xtal` command is beside it.
        - The crystal-builder skill is in
          `.claude/skills/crystal-builder/`.
        - In your final report, name every diagnostic you met by its
          code, as `inspect()` and the verbs print it.
        """), encoding="utf-8")


def _environment() -> dict:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), env.get("PATH", "")])
    return env


def _result_of(stdout: str) -> dict:
    """The result object of ``claude -p --output-format json``: one
    object, or (with ``--verbose``) the last ``result`` of a list."""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, list):
        results = [m for m in parsed if isinstance(m, dict)
                   and m.get("type") == "result"]
        parsed = results[-1] if results else {}
    return parsed if isinstance(parsed, dict) else {}


def final_text(stdout: str) -> str:
    """The agent's final report; the raw output when it is not
    JSON."""
    parsed = _result_of(stdout)
    if not parsed and stdout.strip()[:1] not in ("{", "["):
        return stdout
    return str(parsed.get("result", ""))


def usage(stdout: str) -> tuple[int | None, float | None]:
    """``num_turns`` and ``total_cost_usd``: fewer turns for the same
    answer is what easier context looks like as a number."""
    parsed = _result_of(stdout)
    return parsed.get("num_turns"), parsed.get("total_cost_usd")


def _run_folder(stamp: str) -> Path:
    """``runs/<stamp>``, or ``<stamp>-2`` ... for a second run started
    within the same second."""
    RUNS.mkdir(parents=True, exist_ok=True)
    for n in range(1, 100):
        folder = RUNS / (stamp if n == 1 else f"{stamp}-{n}")
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            continue
    raise SystemExit(f"{RUNS} has 99 runs stamped {stamp}")


def table(names: list[str], vias, results: dict) -> str:
    """One row a task, a status, turns and cost for each way it ran,
    then the failed checks, and a parity line: passed of those run."""
    head = ["task"]
    for via in vias:
        head += [via, "turns", "$"]
    head.append("failed checks")
    rows = []
    for name in names:
        row, said = [name], []
        for via in vias:
            status, turns, cost, detail = results[(name, via)]
            row += [status, "" if turns is None else str(turns),
                    "" if cost is None else f"{cost:.2f}"]
            if detail:
                said.append(f"{via}: {detail}" if len(vias) > 1
                            else detail)
        rows.append([*row, "; ".join(said)])
    parity = ["passed"]
    for via in vias:
        ran = [results[(n, via)][0] for n in names
               if results[(n, via)][0] != "skipped"]
        parity += [f"{ran.count('yes')}/{len(ran)}", "", ""]
    parity.append("")
    widths = [max(len(r[i]) for r in [head, *rows, parity])
              for i in range(len(head) - 1)]

    def line(cells):
        # The last cell is not padded, so zip stops short of it.
        return " | ".join(c.ljust(w) for c, w in
                          zip(cells, widths, strict=False)) + \
            " | " + cells[-1]

    rule = "-+-".join("-" * w for w in widths) + "-+-" + \
        "-" * len(head[-1])
    return "\n".join([line(head), rule, *map(line, rows), rule,
                      line(parity)])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--claude", metavar="PATH",
                        help="the claude executable, when it is not "
                             "on PATH or at ~/.claude/local/claude")
    parser.add_argument("--only", metavar="NAME",
                        help="run one task, by its folder's name")
    parser.add_argument("--dry-run", action="store_true",
                        help="list the tasks and what each is graded "
                             "on; run nothing")
    parser.add_argument("--via", choices=(*VIAS, "both"),
                        default="raw",
                        help="raw: the skill and a shell (default); "
                             "mcp: xtal mcp's tools alone, as a chat "
                             "client has them; both: side by side")
    args = parser.parse_args(argv)
    vias = VIAS if args.via == "both" else (args.via,)
    tasks = task_dirs(args.only)
    claude = find_claude(args.claude)
    if args.dry_run:
        return dry_run(tasks, claude, vias)
    if args.claude and not claude.is_file():
        raise SystemExit(f"--claude {args.claude}: no such file")
    if claude is None:
        raise SystemExit("claude was not found on PATH or at "
                         "~/.claude/local/claude; pass --claude PATH")
    if importlib.util.find_spec("xtal") is None:
        raise SystemExit(f"{sys.executable} has no Crystal Builder; "
                         f"run this with the Python that does")

    out = _run_folder(time.strftime("%Y-%m-%d-%H%M%S"))
    results = {}
    for task in tasks:
        missing = missing_needs(task)
        for via in vias:
            if missing:
                results[(task.name, via)] = (
                    "skipped", None, None,
                    f"needs {', '.join(missing)}")
                continue
            print(f"running {task.name} via {via} ...", flush=True)
            results[(task.name, via)] = _attempt(task, claude, out, via)
    print()
    print(table([t.name for t in tasks], vias, results))
    print(f"\nwhat each agent left: {out}")
    return 1 if any(r[0] not in ("yes", "skipped")
                    for r in results.values()) else 0


def _attempt(task: Path, claude: Path, out: Path, via: str):
    """``(status, turns, cost, detail)``: what the table shows."""
    try:
        verdict, turns, cost = run_task(task, claude, out, via)
    except subprocess.TimeoutExpired:
        return "no", None, None, f"timed out at {TIMEOUT} s"
    except ClaudeFailed as exc:
        return "not run", None, None, str(exc)
    except subprocess.CalledProcessError as exc:
        said = (exc.stderr or "").strip().splitlines()
        return ("not run", None, None,
                f"{' '.join(exc.cmd[2:5])} failed"
                f"{': ' + said[-1] if said else ''}")
    except OSError as exc:
        return "not run", None, None, str(exc)
    failed = [name for name, ok, _detail in verdict.checks if not ok]
    return ("yes" if verdict.passed else "no", turns, cost,
            "; ".join(failed))


if __name__ == "__main__":
    raise SystemExit(main())
