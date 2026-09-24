# review/ — a deep review of Crystal Builder, and what to do about it

> **This directory is dated material.** Each document carries a
> provenance line under its title saying when it was written and which
> commit it was written against. Nothing here is maintained alongside the
> code: if a file it cites has changed, the citation is stale, and the
> document is a record of what was true then — not a description of the
> repository now.

**Written:** 2026-09-18 (reports) and 2026-09-19 (priorities, designs).
**Against:** `3cd15e2` — v0.2.1, the base of `features/deep-review`.
**`origin/main` has since moved** to `fb38d25`.

## Read in this order

| File | What it is |
|---|---|
| [HITLIST.md](HITLIST.md) | **Written 2026-09-24, after PRs #2–#9 shipped.** What is left, what is wrong in what shipped, and what those PRs made cheaper. Start here if the four tracks have already been merged. |
| [REVIEW.md](REVIEW.md) | The synthesis. §4 is what is good, §5 an ordered work plan, §7 the feature ideas. Start here. |
| [PLAN.md](PLAN.md) | **The ordered work, with measured sizes.** What to act on. |
| [PRIORITIES.md](PRIORITIES.md) | Superseded by PLAN.md — the ordering from Julius's PR verdicts, before the design reading. |
| [design/](design/) | The reading behind PLAN.md: PORMAKE/MFU-4l, tier-1 specs, registry sizing, licensing. |
| `design/` | High-level design for the items that needed it before they could be sized. |
| `reports/` | The nine reviews the synthesis rests on, each with its evidence. |
| `probes/` | Reproductions. Scripts, not tests — they are how the findings were proved. |
| `shots/` | 23 screenshots from the UI/UX review. |

## How to tell if a finding has gone stale

Each report cites `path:line`. The cheapest check is whether the file has
changed since `3cd15e2`:

```bash
git log --oneline 3cd15e2..HEAD -- xtal/core/structure.py
```

Most findings also have a probe under `probes/` that either still
reproduces or does not. A probe that no longer reproduces is the clearest
possible signal that the finding is fixed.

## What this is not

It is not a patch. No file under `xtal/` or `xtalapp/` was modified to
produce any of it. The one piece of prototype code —
`probes/workers_fixed.py` — is a proposal, measured against the shipped
module, and is not wired into anything.
