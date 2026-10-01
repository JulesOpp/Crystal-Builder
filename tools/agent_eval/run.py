"""
Run the skill eval: five scripted tasks, each given to Claude Code
headless (``claude -p``) in a project of its own with the skill
installed, and graded by ``grade.py``.

    python tools/agent_eval/run.py --dry-run     # what would run
    python tools/agent_eval/run.py               # all five; tokens
    python tools/agent_eval/run.py --only tied-scan

Run it with the Python that has Crystal Builder installed: the agent
is told to use this interpreter, and the grader imports ``xtal``.  It
uses the person's own Claude Code login; there is no key here.

Each task runs in a temporary folder **outside** the checkout, so the
agent reads the skill and nothing of this repository's own
``CLAUDE.md``; what it left is copied to ``runs/<time>/<task>/``
afterwards (ignored by git).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
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


# ----------------------------------------------------------------------

def dry_run(tasks: list[Path], claude: Path | None) -> int:
    print(f"claude: {claude or 'not found (pass --claude PATH)'}")
    print(f"python: {sys.executable}")
    print(f"{len(tasks)} task(s); nothing is run\n")
    for task in tasks:
        expect = grade.expectations(task)
        print(f"== {task.name}")
        # As expect.json names it: a Path would print backslashes on
        # Windows.
        print(f"   input:  {expect.get('input') or '(none)'}")
        prompt = " ".join(prompt_of(task).split())
        for line in textwrap.wrap(prompt, 66):
            print(f"   | {line}")
        for label, value in _expectation_lines(expect):
            print(f"   {label:<22}{value}")
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
    if expect.get("needs"):
        yield "needs", ", ".join(expect["needs"])


# ----------------------------------------------------------------------

def run_task(task: Path, claude: Path, out: Path) -> grade.Verdict:
    folder = Path(tempfile.mkdtemp(prefix=f"xtal-eval-{task.name}-"))
    try:
        _set_up(task, folder)
        done = subprocess.run(
            [str(claude), "-p", prompt_of(task),
             "--output-format", "json",
             "--allowedTools", ALLOWED_TOOLS],
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
        (folder / "verdict.json").write_text(json.dumps(
            {"passed": verdict.passed, "checks": verdict.checks},
            indent=1), encoding="utf-8")
        return verdict
    finally:
        shutil.copytree(folder, out / task.name,
                        ignore=shutil.ignore_patterns(".claude"))
        shutil.rmtree(folder, ignore_errors=True)


def _set_up(task: Path, folder: Path) -> None:
    subprocess.run([sys.executable, "-m", "xtal.cli", "skill",
                    "install", "--project", str(folder)],
                   check=True, capture_output=True, text=True)
    source = grade.input_file(task)
    if source is not None:
        shutil.copy2(source, folder / source.name)
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


def final_text(stdout: str) -> str:
    """The ``result`` of ``claude -p --output-format json``: one
    object, or (with ``--verbose``) a list whose last ``result`` entry
    is it."""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout
    if isinstance(parsed, list):
        results = [m for m in parsed if isinstance(m, dict)
                   and m.get("type") == "result"]
        parsed = results[-1] if results else {}
    return str(parsed.get("result", "")) if isinstance(parsed, dict) \
        else ""


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


def table(rows: list[tuple[str, str, str]]) -> str:
    head = ("task", "passed", "failed checks")
    width = [max(len(r[i]) for r in [head, *rows]) for i in range(2)]
    lines = [f"{head[0]:<{width[0]}} | {head[1]:<{width[1]}} | "
             f"{head[2]}"]
    lines.append(f"{'-' * width[0]}-+-{'-' * width[1]}-+-"
                 f"{'-' * len(head[2])}")
    for name, passed, failed in rows:
        lines.append(f"{name:<{width[0]}} | {passed:<{width[1]}} | "
                     f"{failed}")
    return "\n".join(lines)


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
    args = parser.parse_args(argv)
    tasks = task_dirs(args.only)
    claude = find_claude(args.claude)
    if args.dry_run:
        return dry_run(tasks, claude)
    if args.claude and not claude.is_file():
        raise SystemExit(f"--claude {args.claude}: no such file")
    if claude is None:
        raise SystemExit("claude was not found on PATH or at "
                         "~/.claude/local/claude; pass --claude PATH")
    if importlib.util.find_spec("xtal") is None:
        raise SystemExit(f"{sys.executable} has no Crystal Builder; "
                         f"run this with the Python that does")

    out = _run_folder(time.strftime("%Y-%m-%d-%H%M%S"))
    rows, failed_any = [], False
    for task in tasks:
        missing = missing_needs(task)
        if missing:
            rows.append((task.name, "skipped",
                         f"needs {', '.join(missing)}"))
            continue
        print(f"running {task.name} ...", flush=True)
        try:
            verdict = run_task(task, claude, out)
        except subprocess.TimeoutExpired:
            rows.append((task.name, "no", f"timed out at {TIMEOUT} s"))
            failed_any = True
            continue
        except ClaudeFailed as exc:
            rows.append((task.name, "not run", str(exc)))
            failed_any = True
            continue
        except subprocess.CalledProcessError as exc:
            said = (exc.stderr or "").strip().splitlines()
            rows.append((task.name, "not run",
                         f"{' '.join(exc.cmd[2:5])} failed"
                         f"{': ' + said[-1] if said else ''}"))
            failed_any = True
            continue
        except OSError as exc:
            rows.append((task.name, "not run", str(exc)))
            failed_any = True
            continue
        failed = [name for name, ok, _detail in verdict.checks
                  if not ok]
        rows.append((task.name, "yes" if verdict.passed else "no",
                     "; ".join(failed)))
        failed_any |= not verdict.passed
    print()
    print(table(rows))
    print(f"\nwhat each agent left: {out}")
    return 1 if failed_any else 0


if __name__ == "__main__":
    raise SystemExit(main())
