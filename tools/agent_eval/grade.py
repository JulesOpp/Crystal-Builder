"""
Grading one eval task: what the agent said, saved and logged, against
the task's ``expect.json``.

``expect.json`` keys, each optional:

``codes``
    Diagnostic codes the final report must name, as the code itself
    (``COINCIDENT_ATOMS``): a sentence that paraphrases one is not
    graded as naming it.
``inspect``
    ``{CODE: "present" | "absent"}``, checked by ``inspect()`` of the
    ``.xtalproj`` the agent saved.  No saved project fails each one.
``log_must_not_contain`` / ``log_must_contain``
    Verb names (``optimize``, ``reduce_to_p1``, ``scan.run``) looked
    for in every ``agent-session.jsonl`` under the workspace.  A
    ``prepare`` step counts as its own name too, so ``cap`` is caught
    whether it is a verb or ``prepare(steps=[..., "cap"])``.
``report_must_ask``
    A question in the report about the trimers: a sentence ending in
    ``?`` that names ``cap``, a trimer or a ligand, with code names
    such as ``OPEN_TRIMERS`` left out; or a short question pointing
    back ("Shall I run it?") after a sentence that does.  A sign-off
    ("anything else?") is not one, nor a question the report answers
    itself.
``atoms_unchanged``
    The saved project has as many atoms (P1) as the task's input.
``input``
    The structure the agent is handed, as a path relative to the
    repository (``resources/samples/MIL53.cif``): a task never keeps
    a copy of its own.  None for a task that builds its structure.
``needs``
    Extras the task cannot run without; ``run.py`` skips the task and
    says which.  Not graded.

Nothing from ``xtal`` is imported at module level, so ``run.py
--dry-run`` reads the tasks under any Python.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LOG_NAME = "agent-session.jsonl"

#: The checkout, which ``input`` paths are relative to.
ROOT = Path(__file__).resolve().parents[2]

#: What a question about completing the trimers names.
ABOUT_TRIMERS = re.compile(r"trimer|terminal ligand|\bcap\b|ligand",
                           re.IGNORECASE)

#: A diagnostic code, taken out before :data:`ABOUT_TRIMERS` is
#: matched: ``OPEN_TRIMERS`` names the finding, not a question.
CODE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

#: A short question that points back -- "Shall I run it?" -- is about
#: what the sentence before it said.
REFERS = re.compile(r"\b(it|that|them|those)\b", re.IGNORECASE)
SHORT = 8

#: The report answering its own question: "Were they capped? No."
ANSWERED = re.compile(r"^(yes|no)\b[^?]{0,20}$", re.IGNORECASE)

#: One sentence, with what ends it; a line break ends one too.
SENTENCE = re.compile(r"[^.?!\n]*[.?!]+|[^.?!\n]+")


@dataclass
class Verdict:
    passed: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)


def expectations(task_dir) -> dict:
    return json.loads((Path(task_dir) / "expect.json").read_text(
        encoding="utf-8"))


def input_file(task_dir) -> Path | None:
    """The structure the task hands the agent, or ``None`` for a task
    that builds its own."""
    given = expectations(task_dir).get("input")
    return ROOT / given if given else None


def questions_about_trimers(text: str) -> list[str]:
    """Each question to the person about the trimers.

    The question itself must name them, codes left out: "Shall I add
    the terminal ligands?" is one, "OPEN_TRIMERS left. Would you like
    any additional checks?" is not.  A short question that points
    back ("Shall I run it?") may lean on the sentence before it.  A
    question the report answers itself ("Were they capped? No.") asks
    nobody.
    """
    sentences = [s.strip() for s in SENTENCE.findall(text) if s.strip()]

    def about(sentence: str) -> bool:
        return bool(ABOUT_TRIMERS.search(CODE.sub("", sentence)))

    asked = []
    for i, s in enumerate(sentences):
        if not s.endswith("?"):
            continue
        after = sentences[i + 1] if i + 1 < len(sentences) else ""
        if ANSWERED.match(after):
            continue
        leans = (len(s.split()) <= SHORT and REFERS.search(s)
                 and i > 0 and about(sentences[i - 1]))
        if about(s) or leans:
            asked.append(s)
    return asked


def grade(task_dir, transcript: str, project,
          workspace=None) -> Verdict:
    """Every expectation of ``task_dir`` as a ``(name, ok, detail)``
    check.

    ``transcript`` is the agent's final report; ``project`` the
    ``.xtalproj`` it saved, or ``None``; ``workspace`` where its
    session logs are (the project's folder when not given).
    """
    expect = expectations(task_dir)
    project = Path(project) if project is not None else None
    checks: list[tuple[str, bool, str]] = []

    for code in expect.get("codes", []):
        named = code in transcript
        checks.append((f"reports {code}", named,
                       "named" if named else "not in the final report"))

    wanted = expect.get("inspect", {})
    if wanted:
        found = _codes_in(project) if project is not None else None
        for code, state in wanted.items():
            name = f"{code} {state} in the saved project"
            if found is None:
                checks.append((name, False, "no project was saved"))
                continue
            ok = (code in found) == (state == "present")
            listed = ", ".join(sorted(found)) or "nothing"
            checks.append((name, ok, f"inspect() gave {listed}"))

    rows = _log_rows(workspace if workspace is not None
                     else project.parent if project is not None
                     else None)
    for verb in expect.get("log_must_not_contain", []):
        ran = [r for r in rows if verb in _names(r)]
        checks.append((f"log has no {verb}", not ran,
                       f"{len(ran)} row(s) ran it" if ran
                       else f"not among {len(rows)} row(s)"))
    for verb in expect.get("log_must_contain", []):
        ran = [r for r in rows if verb in _names(r)]
        checks.append((f"log has {verb}", bool(ran),
                       f"{len(ran)} row(s)" if ran
                       else f"not among {len(rows)} row(s)"))

    if expect.get("report_must_ask"):
        asked = questions_about_trimers(transcript)
        checks.append(("asks the person", bool(asked),
                       asked[0] if asked else "no such question"))

    if expect.get("atoms_unchanged"):
        source = input_file(task_dir)
        if project is None or source is None:
            checks.append(("atoms unchanged", False,
                           "no project was saved" if project is None
                           else "the task has no input to compare"))
        else:
            before, after = _atoms(source), _atoms(project)
            checks.append(("atoms unchanged", before == after,
                           f"{before} -> {after}"))

    return Verdict(all(ok for _name, ok, _detail in checks), checks)


def _codes_in(project: Path) -> set[str]:
    from xtal.agent.inspect import inspect
    from xtal.io.project import read_project

    structure, _view, _session = read_project(project)
    return {d.code for d in inspect(structure).diagnostics}


def _atoms(path: Path) -> int:
    from xtal.core import p1
    from xtal.io import FORMATS

    return p1.expand(FORMATS.read(path)).n_atoms


def _log_rows(root) -> list[dict]:
    if root is None or not Path(root).is_dir():
        return []
    rows = []
    for log in sorted(Path(root).rglob(LOG_NAME)):
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _names(row: dict) -> set[str]:
    """The verb a log row ran, and for ``prepare`` its steps."""
    names = {row.get("verb", "")}
    if row.get("verb") == "prepare":
        names.update((row.get("args") or {}).get("steps") or ())
    return names
