# Review brief — read this first

You are one of several reviewers looking at **Crystal Builder**, a desktop
crystallography application written by Julius Oppenheim (GitHub JulesOpp).
The reviewer coordinating you is preparing a non-functional-requirements
(NFR) review and a list of feature ideas for the author. You are reviewing
someone else's project: **nothing you do may modify a tracked file**.

## Ground rules

- Repo: `/Users/sam/Projects/Jules/Crystal-Builder` (main, clean, v0.2.1).
- Python: **`/Users/sam/Projects/Jules/Crystal-Builder/.venv/bin/python`**
  (3.12, arm64, everything in `[dev]` installed). Always use this path.
  `.venv/bin/xtal` and `.venv/bin/crystal-builder` are the entry points.
- **Do not edit, create or delete any tracked file.** `git status` must stay
  clean when you finish. Write everything you produce under
  `review/` (git-excluded locally). Your report goes to
  `review/reports/<your-topic>.md`; scratch scripts under `review/probes/`;
  screenshots under `review/shots/`.
- **Read `CLAUDE.md` in full before anything else.** It is 517 lines of
  product invariants, each with the bug that motivated it, plus the rules
  for running tests and the GUI. It is the spec you are reviewing against.
- Before opening any large file use the outline tool:
  `.venv/bin/python .claude/skills/code-map/outline.py <file>` or
  `... --find <name>`. `xtalapp/mainwindow.py` is ~1800 lines.
- Test-running rules from CLAUDE.md, restated because they bite:
  - Never set `QT_QPA_PLATFORM=offscreen` locally.
  - Never run `ruff format`. `ruff check .` is fine.
  - Never use `-n auto`. Run serially.
  - A full run wedges ~1 in 4 on a known `workers.py` deadlock. Use
    `-o faulthandler_timeout=90` so a hang names itself. If you must kill:
    `pkill -f pytest; pkill -9 -f "stdin.readline"`.
  - Set `XTAL_NO_CONFIRM_CLOSE=1` when launching the real app.
  - **The machine is under memory pressure (swap ~97% used).** Prefer
    targeted test files over the full suite; check `sysctl vm.swapusage`
    before trusting timings. If a process dies with `Fatal Python error:
    Aborted` and a `dlopen` stack, it is the memory, not the code.
  - `resources/test/` is gitignored and mostly absent on this machine;
    tests that need it may skip. Say so if you see it.
- `.claude/skills/run-app/drive.py` drives the real window headed:
  `--scratch DIR --open FILE --action NAME --viewport-shot OUT.png`,
  `--list-actions`, `--list-docks`, `--grab`. Read its SKILL.md.
- Existing planning docs: `docs/PLAN.md` (architecture + roadmap that
  built it), `docs/ROADMAP.md` (what is scheduled), `docs/TODO.md` (known
  problems, unscheduled). Do not repeat what TODO.md already says as if it
  were a discovery — cite it and go further.

## Report format

Markdown. Lead with a 5-line summary. Then findings, most important first,
each with: **what**, **where** (`path:line`), **evidence** (the command you
ran and what it printed, or the code you read), **why it matters**, and
**what a fix would look like** (a sentence, not a patch). Severity tags:
`[critical]` `[important]` `[minor]` `[strength]`. Be concrete and
verifiable; a finding without evidence is an opinion. End with a short
"what I did not get to" section so the coordinator knows the edges.
