---
name: crystal-builder
description: >-
  Build, edit, prepare and inspect crystal structures with Crystal Builder
  (the xtal Python package): open a CIF, prepare a deposited structure for a
  calculation, build a MOF on a net, add or move atoms, recalculate bonds,
  relax with a force field or ML potential, measure porosity or a PXRD
  pattern, and judge whether the result is chemically right. Read it before
  the first edit whenever a task involves a crystal structure, a CIF, a MOF,
  a framework, a unit cell, a space group, a workspace of structures, or a
  structure a person will open in the Crystal Builder window.
license: MIT
compatibility: Requires the crystal-builder package (pip install crystal-builder) and Python 3.11+. Rendering needs the gui extra; MOF building needs ase; ML engines need their own extras. capabilities() says what this install has.
---

# Driving Crystal Builder

**Audience: an agent building or changing a crystal structure for a
person.** Not a tutorial and not an API reference. A *protocol*: what to
do, in what order, what to check before you believe a structure, and
where the program will tell you your answer is wrong even though it
looks right.

A structure that loads, relaxes and returns an energy can still be the
wrong crystal: three copies of every atom stacked in one place, a linker
with half its hydrogens, a cluster with the wrong charge. Nothing
crashes; the numbers are finite and wrong. Every rule below exists
because one of those happened. The person will open what you made in
the Crystal Builder window, so leave them something they can check.

## Load these when the task calls for them

| When | Load |
|---|---|
| you are about to call a verb: every verb, its arguments, what it returns | [`references/api.md`](references/api.md) |
| a diagnostic fired and you need its row: every code and its remedy | [`references/diagnostics.md`](references/diagnostics.md) |
| the structure came from a database or a paper (a deposited CIF) | [`references/prepare.md`](references/prepare.md) |
| the task is to build a framework on a net | [`references/mof.md`](references/mof.md) |
| an energy, a relaxation or a scan: which engine, and what it means | [`references/calculations.md`](references/calculations.md) |
| pore volume, surface area, pore size, or a PXRD pattern | [`references/porosity.md`](references/porosity.md) |
| where files land, and how the person opens what you made | [`references/workspace.md`](references/workspace.md) |

**Do not quote a signature from memory.** `capabilities()` says what this
install can run (engines, modules, whether it can render), and
`help_for(name)` gives a verb's signature or a module's parameters. From
a shell: `xtal capabilities` and `xtal capabilities NAME`.

---

## 1. The one surface, and why it is a session

```python
from xtal.agent import Session, capabilities, help_for

s = Session.open("MOF-5.cif", workspace="~/Crystal Builder")
print(s.inspect())            # numbers first, diagnostics last
answer = s.prepare()          # a VerbResult
print(answer)                 # ok / REFUSED, message, diagnostics
s.save()                      # a project the person opens in the window
```

A `Session` is a structure, its undo stack and its place in a
workspace. **Every verb is one undo step**, pushed as the same command
the window pushes when a person does the same thing. So your edit is
exactly theirs, `s.undo()` takes it back, and the product rules the
commands carry come with it. Do not edit `s.structure` directly: that
bypasses the stack, the log and every rule in §3.

Every verb returns a `VerbResult`: `ok`, `message`, `atoms_before` /
`atoms_after`, `data` (the numbers), and `diagnostics`. Print it, or
call `.to_json()`. **`ok=False` means nothing was changed and nothing
was pushed.** A warning rides on a change that *was* made. An agent that
reads `ok` and stops has missed half the answer, so read the diagnostics
every time.

**Site verbs take site indices** (the asymmetric unit, as `inspect()`
lists them). **Bond verbs take atom indices** of the P1 cell, because a
bond joins two drawn atoms, not two orbits. `inspect()` gives both: each
site row carries `first_atom`.

**A session lives as long as its Python process.** Do a multi-step
job in one script where you can. Where you cannot (one shell call per
step), end each script with `save()` and start the next with
`Session.open` of the **`.xtalproj`** it returned, never the original
CIF: reopening the CIF starts again from the deposited structure and
repeats every step (`PROJECT_EXISTS` on `session.opened` says so). The
undo stack does not survive between processes; the project and the log
do.

A refusal is an answer, not an exception: a bad space group, a
placement that collides, an engine missing an extra all come back as
`ok=False` with a coded diagnostic. A wrong argument *type* still
raises, because that is a bug in your call.

## 2. The order of work

1. **Ask what the deliverable is** (§6) if the person has not said. It
   decides which checks stop you.
2. **Open into a workspace**: `Session.open(path, workspace=...)`, or
   `Session.build(...)` for a framework. A structure with nowhere to be
   has nowhere to file its runs.
3. **`inspect()` before anything else.** Read the diagnostics. A
   `COINCIDENT_ATOMS` error means every later number is for a crystal
   with extra copies in it, so fix that first.
4. **Prepare a deposited structure** (`prepare()`) before any
   calculation. See `references/prepare.md`.
5. **Edit**, one verb at a time, checking each answer.
6. **Recalculate bonds deliberately** (`recalculate_bonds()`), and only
   when the geometry is where you want it (§3).
7. **`inspect()` again.** Compare against step 3: atom count, formula,
   coordination, detected group.
8. **Calculate** (`energy`, `optimize`, `run`) only on a structure that
   passed step 7.
9. **`inspect()` after a relaxation too.** A relaxation that moved an
   atom 2 Å has told you something about your structure.
10. **Look at it** when the task is geometric: `s.render("x.png",
    view="a")`, then read the image. Numbers first, pixels second.
11. **`save()`**, and tell the person what you did (§7).

## 3. The rules the program keeps, and you must not work around

These are product decisions, not implementation details. The verbs
already keep them; the failure is reaching around a verb to "help".

1. **Bonds change only in `recalculate_bonds()`.** Not when you add an
   atom, not after a relaxation, not after a cell edit. `add_atom(...)`
   arrives with no bonds, or with exactly one if you pass `bonded_to=`
   (a P1 atom). `BONDS_NOT_RECALCULATED` says so. That is by design: a
   person's own bond edits must survive, and recalculating is how they
   choose to replace perception. Bonds drawn or removed by hand survive
   a recalculation too (`BOND_OVERRIDES_KEPT`).
   **The one exception is an operation that rebuilds the cell into a
   different set of atoms**: `supercell`, `find_symmetry`,
   `standardize`, `set_space_group`, `prepare`. The stored graph cannot
   describe the new cell, so its bonds are perceived afresh (hand-drawn
   bonds are carried). `reduce_to_p1`, `set_cell` and every move carry
   the graph as it was. `inspect()` after any rebuild: an atom you left
   unbonded on purpose may not be any more.
2. **A force field never changes the atoms or the bonds.** `optimize()`
   moves positions and, with `relax_cell=True`, the cell. If a
   relaxation "needs" a bond broken or an atom added, that is your
   structural edit to make and report, never the optimiser's.
3. **Dummy atoms (`X`) are markers, not chemistry.** They are held back
   from every calculation, bond to nothing by perception, and stay where
   they were put. They are the person's; leave them unless asked.
4. **Chemistry is decided by connectivity and charge, never by a
   refinement's bond lengths.** A powder model's 1.51 Å ring bonds are
   still a benzene ring, and a long metal-oxygen bond is still a bond.
   `BOND_LENGTH_UNUSUAL` skips metals on purpose.
5. **A step that adds what the file never located is never a default.**
   `prepare()` leaves out `cap` (the terminal ligands of M3O trimers)
   unless you name it, and says in warning tone either way: that it
   changed the chemistry (`CHEMISTRY_CHANGED`), or that the cell is not
   neutral (`CELL_NOT_NEUTRAL`). **Ask the person before naming `cap`.**
6. **A site is on a special position when its coordinates say so to the
   precision they were written at** (0.05 Å). Do not "fix" a site that
   is 0.01 Å off a mirror by nudging it; the program already treats it
   as on the mirror. Snapping to the ideal position is `standardize()`.
7. **Operations over a whole structure are one step.**
   `add_hydrogens()` adds every hydrogen as one undo step. Never loop
   atom by atom when a verb takes the set.

## 4. Judging a structure, in this order

`inspect()` puts the numbers first and the diagnostics last. Read them
in this order anyway:

1. **Errors outrank everything.** `COINCIDENT_ATOMS` or a
   `CALCULATION_REFUSED` means stop and fix.
2. **Atom count and formula** against what the person expects, or what
   the paper says. A MOF-5 cell is `C24H12O13Zn4` × Z. A count four
   times too big is a centred cell (`CENTRED_CELL`). A count with no H
   is an X-ray structure that never located them (`MISSING_HYDROGENS`).
3. **Coordination, site by site.** Every metal should have the
   coordination its chemistry demands. Every C at most 4, every H
   exactly 1 (`OVERCOORDINATED`, `UNBONDED_ATOM`). `neighbours` gives
   element and distance.
4. **Contacts.** `CLOSE_CONTACT` means two unbonded atoms closer than
   0.8 × the sum of their covalent radii: a missing bond, or a
   misplaced atom. Render it with `highlight=[i, j]` and look.
5. **Symmetry.** `detected_space_group` against `space_group`. A P1 file
   whose coordinates have Fm-3m is fine. A high declared group whose
   coordinates detect lower means the coordinates have moved.
6. **Fragments.** One framework plus the molecules you expect. A
   framework that is suddenly three molecules has lost bonds.
7. **Only then an energy.** A converged UFF energy is not evidence the
   structure is right; it is evidence the optimiser stopped.

## 5. Abstention is a result. Do not convert it into a number

1. **A refusal before the first step is the answer.** A scan refused
   because the space group ties the coordinate (`MODULE_FAILED`, "the
   space group ties it") means the coordinate cannot move in this
   group. `reduce_to_p1()` first *only* if the person wants the
   symmetry broken. Never retry unchanged.
2. **`NOT_CONVERGED` is not a minimum.** Its geometry is applied (the
   window applies it too), but its energy is where the optimiser
   stopped. Do not report it as a relaxed energy, and do not compare it
   with a converged one.
3. **An unconverged scan point is a hole, not a zero.** A NaN plotted as
   0 is the deepest point of every landscape it appears in.
4. **A window flagged borderline** in a porosity table (within half a
   grid step of the probe) is unresolved. Report it as that, or rerun
   with a finer `spacing`; never round it to open or closed.
5. **`RENDER_UNAVAILABLE`** means no picture on this machine. Work from
   `inspect()`, which is what the judgement rests on anyway.
6. **`ENGINE_UNAVAILABLE` / `MODULE_UNAVAILABLE`** name what to install.
   Tell the person; do not silently substitute another engine for a
   number they asked a specific engine for.

## 6. Declare the deliverable

| Deliverable | What decides it | Stop when |
|---|---|---|
| **A structure to look at** (a person will open it) | `inspect()` clean of errors; formula and coordination right; a render that looks like the material | the person can open the project and see what you described |
| **Ready for a calculation** (DFT, MD, a force field) | `prepare()` run and reported; no `DISORDER`, `SOLVENT` (unless kept on purpose), `MISSING_HYDROGENS`, `COINCIDENT_ATOMS`; neutrality stated | every prepare step's sentence is in your report, and any `CELL_NOT_NEUTRAL` is said |
| **A built framework** | the build's own table: RMSD near 0, closest contact above ~1.5 Å, the net that came out equals the one asked for; then `inspect()` | the "net that came out" row says what was asked, and the joints are bonded |
| **A relaxed structure** | `converged` true; `inspect()` after shows the same atoms, bonds and fragments as before | converged, and nothing in `inspect()` changed but positions |
| **A property** (pore volume, area, PXRD, energy) | the module's report table, quoted with its probe, radii, source and engine | the number is quoted with the conditions it was measured under |

## 7. What to tell the person

- What you did, **verb by verb**, in the words the answers used. The log
  in the entry (`agent-session.jsonl`) has every step; your summary
  should not need it.
- Every **warning** diagnostic, by its message. Every
  `CHEMISTRY_CHANGED` in so many words.
- The numbers with their conditions: engine and parameter set for an
  energy, probe and radii for a pore volume, radiation for a pattern.
- Where the result is: the project path from `save()`. It opens in the
  window by double-clicking, or from File ▸ Open.
- What you could not do, and why (the refusal's message).

## 8. A worked default

A person hands you a deposited CIF and asks for it relaxed.

```python
from xtal.agent import Session, capabilities

print(capabilities())                         # what can run here
s = Session.open("Ni2Cl2BTDD.cif", workspace="~/Crystal Builder")
before = s.inspect()
print(before)                                 # COINCIDENT_ATOMS: copies as sites

answer = s.prepare()                          # duplicates .. hydrogens, not cap
print(answer)                                 # read every PREPARE_STEP line
if not answer.ok:
    raise SystemExit(answer.message)

after = s.inspect()
print(after)                                  # atoms, formula, coordination
# the cell is P1 now; bonds were perceived afresh by prepare

relaxed = s.optimize(engine="uff", max_steps=500)
print(relaxed)                                # NOT_CONVERGED?  say so
print(s.inspect())                            # same atoms and bonds as `after`
s.render("relaxed.png", view="c")             # then look at it
path = s.save()
```

The report to the person names the prepare steps (27 sites were copies,
the R cell made primitive, 42 waters removed, 24 hydrogens placed),
the engine and whether it converged, and `path`.

---

## The shell, for a quick look

Everything above is also a command, and every inspection command takes
`--json`:

```bash
xtal inspect file.cif --json        # the same Inspection
xtal render file.cif out.png --view c
xtal prepare in.cif out.cif         # prepare, file to file
xtal optimize file.cif --json -o relaxed.cif
xtal run zeopp.volume-grid file.cif --json
xtal capabilities                   # what can run here
xtal skill install                  # this file, where Claude Code reads it
```

Use the shell for a look; use a `Session` for anything with more than
one step, because only a session has undo and a log.
