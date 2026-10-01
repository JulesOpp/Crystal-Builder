# The skill eval

`tests/test_agent_skill.py` holds the skill's *names* to the code.
Nothing there checks that an agent given the skill *follows* it. This
does: five scripted tasks with known answers, each given to Claude
Code headless, and graded automatically.

It is run by hand, before a release. It is not in the wheel, it never
runs in CI, and a full run spends the tokens of five agent sessions on
your own Claude Code login (there is no API key here).

```bash
.venv/bin/python tools/agent_eval/run.py --dry-run         # what would run; calls nothing
.venv/bin/python tools/agent_eval/run.py                   # all five
.venv/bin/python tools/agent_eval/run.py --only tied-scan  # one
.venv/bin/python tools/agent_eval/run.py --claude PATH     # claude not on PATH
```

Use the Python that has Crystal Builder installed: the agent is told
to use it, and the grader imports `xtal`. `claude` is looked for on
`PATH`, then at `~/.claude/local/claude`; the desktop app bundles its
own and does not put it on `PATH`, so pass `--claude` then.

It prints `task | passed | failed checks` and exits 1 if any task
failed. A task whose `needs` are not installed is skipped and says
which. A task `claude` itself could not run -- not logged in, a crash
-- is `not run` with its last line, rather than every check failing.

## What one task does

1. A temporary folder **outside the checkout**, so the agent reads the
   skill and not this repository's own `CLAUDE.md`.
2. `xtal skill install --project <folder>`: the skill lands in
   `<folder>/.claude/skills/crystal-builder/`.
3. The task's input file is copied in, and a short `CLAUDE.md` says
   where the workspace is (`<folder>/workspace`), which Python to use,
   and to name each diagnostic by its code in the report.
4. `claude -p "<prompt>" --output-format json --allowedTools
   "Bash,Read,Write,Edit"`, in the folder.
5. `grade.py` reads the JSON's `result` (the final report), the newest
   `.xtalproj` the agent saved, and every `agent-session.jsonl` in the
   workspace.
6. The folder, minus the skill, is copied to `runs/<time>/<task>/`
   (ignored by git) with `transcript.json` and `verdict.json`, for
   reading what the agent actually did.

## A task

`tasks/<name>/` holds `task.md` and `expect.json`. The input is not
copied there: `expect.json`'s `input` names a file already in the
repository (`resources/samples/...`), so its provenance stays in one
place. `task.md` is the prompt down to a line of `---`; below it is a
note for whoever runs the eval -- where the input came from and what
`inspect()` said about it when the expectations were written -- and
is never sent. `build-overlap/find_overlap.py` is how that task's
combination was found; run it again if the catalogue changes.

| Task | Input | Graded on |
|---|---|---|
| `copies-and-hydrogens` | `resources/samples/Ni2Cl2BTDD.cif`, symmetry copies written as sites, no H | `COINCIDENT_ATOMS` reported; `prepare` run; saved project free of `COINCIDENT_ATOMS` and `MISSING_HYDROGENS` |
| `build-overlap` | `mof.build` pcu / N16 / E198 | `BUILD_OVERLAP` reported; no `optimize` |
| `tied-scan` | `resources/samples/simple/NaCl.cif`, a Na-Cl distance Fm-3m ties | `MODULE_FAILED` reported; no `reduce_to_p1` |
| `open-trimers` | `resources/samples/cod/MIL-88B.cif`, Cr3O trimers | `OPEN_TRIMERS` and `CELL_NOT_NEUTRAL` reported; no `cap`; the person asked; the saved project still has `OPEN_TRIMERS` |
| `short-relax` | `resources/samples/MIL53.cif`, `max_steps=3` | `NOT_CONVERGED` reported; atom count unchanged |

`expect.json` keys, all optional:

| Key | Checked by |
|---|---|
| `input` | the structure handed to the agent, relative to the repository; none for a build |
| `codes` | each code appears, as the code, in the final report |
| `inspect` | `{CODE: "present" \| "absent"}` from `inspect()` of the saved project; no project fails each |
| `log_must_not_contain`, `log_must_contain` | verb names in the session logs; a `prepare` step counts too, so `cap` is caught either way. A refused verb is a row too, and counts: trying `cap` is the failure, whether or not it ran |
| `report_must_ask` | a question that itself names `cap`, a trimer or a ligand (code names like `OPEN_TRIMERS` do not count), or a short question pointing back -- "Shall I run it?" -- after a sentence that does; a sign-off ("anything else?") or a question the report answers itself ("...? No.") is not one |
| `atoms_unchanged` | the saved project's P1 atom count equals the input's |
| `needs` | extras the task cannot run without; not graded, skipped |

The grading is strict on purpose: a report that paraphrases a warning
without its code fails `codes`. That is why the harness's `CLAUDE.md`
asks for codes in the report, the same sentence for every task, and
why no prompt names one.

`tests/test_agent_eval_grader.py` holds the grader to canned reports,
logs and a saved project, and the dry run to calling nothing.
