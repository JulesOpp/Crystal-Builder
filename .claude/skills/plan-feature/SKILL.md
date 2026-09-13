---
name: plan-feature
description: Write an implementation plan for Crystal Builder in the shape this project uses - context, measurements before decisions, invariants checked, phases with files and tests, run-app verification, docs to update. Use whenever asked to make, write or describe a plan, to "describe the changes" in a ROADMAP phase or TODO entry, to plan items from docs/TODO.md, or before implementing anything non-trivial. Planning only; no source edits.
---

# Planning a change

Work here is planned before it is built, and the plans that went well
share a shape: they **measured before deciding**, they **named the
invariant a change could break**, and every phase ended runnable with
a green suite. This skill is that shape. It produces a plan, not code:
**do not edit source files while planning.**

## 1. Gather, cheaply

- The request's source: the TODO entry, the ROADMAP phase, or the
  user's list. Quote it back in the plan's Context in one or two lines.
- `CLAUDE.md` **Invariants**. For each one the change comes near, say
  in the plan how it is kept. These are product decisions: bonds only
  on Recalculate, a force field never changes bonding, dummy atoms held
  back at the door, one batch per selection, edits through
  `Document.apply`, and the rest. A plan that breaks one has to say so
  and ask.
- The code, **by outline, not by reading**: see `code-map`. Read only
  the methods the change touches.
- The tests that already pin the behaviour:
  `ls tests | grep -i <topic>`, then outline the file `--no-docs`.
- If the answer depends on what a program or file actually does
  (a binary's output, a timing, a count on `MFU4l.cif`), **measure it
  now** with a throwaway script in the scratchpad and put the number in
  the plan. "Measured against the vendored 0.3 binary" is what made the
  Zeo++ plan right the first time.
- Questions only the user can answer (a product choice, a default,
  a name): ask them **before** writing the plan, with AskUserQuestion,
  and record the answers in the plan.

## 2. The plan's sections

```markdown
# <Feature, as the user would say it>

## Context
What was asked (quoted or pointed at), why it matters, and what is
already true that makes it smaller than it sounds.

## What is actually there — measured
Tables of what the code, the binary or the file does today, with the
numbers. Decisions that follow from them, numbered, each with its
reason. (Omit for a change with nothing to measure.)

## Answers
For question-type items: the answer, and whether any work follows.

## Phase N — <deliverable> (`the/main/file.py`)
- What changes, by file and function name (`Document.merge_atoms`,
  `menus.build_actions`), not by line number alone.
- The invariant(s) it keeps, and how.
- Tests: file, and the test names as sentences
  (`test_a_merge_is_one_undo_step`), each with what breaks if it
  regresses.
- Size: S / M / L.

## Verification (end to end)
The run-app command that shows it working when a person clicks it,
and what the screenshot or printed output must show. Plus
`python -m pytest -q tests/<files>` for the phase, and the full suite
once at the end.

## Docs
Which TODO entries are deleted when this ships, whether ROADMAP
changes, whether CLAUDE.md gains or changes an invariant, and whether
docs/MENUS.md or a skill is now out of date.

## Suggested order
Wrong before missing, small before large. One commit per phase.
```

## 3. Rules the plan must follow

- **Every phase ends runnable and green.** No phase that leaves the
  app half-migrated.
- **`xtal/` imports no Qt.** Anything crystallographic goes in `xtal`
  and gets a headless test; `xtalapp` only presents it.
- **New capability through a registry** (actions, modules, engines,
  formats, dialogs) rather than a special case in the shell. For a
  menu command see `add-action`; for a calculation see `add-module`.
- **A move is not a change.** If the plan needs code moved first,
  make that its own phase under `pure-move`.
- **Tests that take seconds get `@pytest.mark.slow`**, and no test
  should approach a minute. If the feature is slow on `MFU4l.cif`, the
  plan says how it will be made fast, not how the test will be skipped.
- **Renaming a visible label** costs a test edit wherever the text is
  asserted (docs/MENUS.md § 4). Keep registry keys when labels change.
- **Packaging**: a new module imported only through `importlib`
  (a dialog named in `xtalapp/dialogs/__init__.py`) is invisible to
  PyInstaller. Say that the plan adds it to the mapping, which the
  bundle reads.

## 4. Where it goes

In plan mode the plan is written to the plan file the harness names;
otherwise to `~/.claude/plans/<short-name>.md`. Tell the user the
path. When the user approves a multi-phase plan that will span
sessions, also schedule it in `docs/ROADMAP.md` (a phase table and one
section per phase) so the next session can find it. Delete the
section when the phase ships, as the ROADMAP's own header says.
