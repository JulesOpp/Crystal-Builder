# Tier 1 — seven accepted correctness fixes, as phases

> **Written 2026-09-19** against `Crystal-Builder` at commit `3cd15e2` (v0.2.1),
> which is the base of branch `features/deep-review`. Note `origin/main` has
> since moved to `fb38d25`. Every line number, measurement and code reference
> below was true at `3cd15e2` — re-verify before acting on it if the file has
> changed.

## Context

Jules gave a blanket verdict on the deep review's correctness findings on
PR #1 — *"Good catch, these should be fixed"* on
[edge-cases](../reports/edge-cases.md), *"Good suggestions"* on
[performance](../reports/performance.md), and *"Yes"* on the worker fix.
[review/PRIORITIES.md](../PRIORITIES.md) turns that into items 2–8 of Tier 1.
This document is the implementation plan for those seven: what changes, in
which function, which CLAUDE.md invariant it sits against, the tests, the
size, and the order.

Nothing here is argued — it is specified. Where a number decides a design
the number was measured today and is in the table it decides.

What makes this smaller than it sounds: every one of the seven has its
machinery already built. `_quote` exists. `Cancellation` exists.
`meta["warnings"]` is a channel with three consumers. `optimize.run` already
takes a `callback` that stops it. `scan._failed` already writes a hole with
a reason. `duplicate_groups` already finds the coincident atoms. The
worker-thread fix exists as a working prototype. Six of the seven are
*connecting what is there*, not building something new.

Probes for this document are under `review/probes/tier1/`; each carries a
dated one-line header. Nothing tracked was modified.

---

## What is actually there — measured

### 1. `add_bond`, before and after the set (`probes/tier1/addbond_fix.py`)

The probe monkeypatches the exact body Phase 5 specifies onto
`Structure.add_bond` and re-runs the real paths. Best of three each.

| path | sites | bonds | before | after | speed-up |
|---|---:|---:|---:|---:|---:|
| `read_project` MOF-5 | 424 | 512 | 785.1 ms | 14.7 ms | **53×** |
| `read_project` **MFU4l** | 648 | 848 | **2161.8 ms** | **22.7 ms** | **95×** |
| `read_project` HKUST1 | 624 | 768 | 1738.3 ms | 20.2 ms | 86× |
| `reduce_to_p1` MOF-5, 512 stored bonds | | 512 | 802.4 ms | 40.5 ms | 19.8× |

The bond lists come back **byte-identical — same bonds, same order** on all
three (`identical=True` in the probe's third section). The identity is
unchanged; only the lookup is.

### 2. Coincident atoms: what a check on open would cost (`probes/tier1/coincident2.py`)

Each column is the best of three on a structure **read fresh each time**, so
no cached P1 expansion is shared between detectors.

| sample | atoms | `p1.expand` | A: expand + query | A: query alone | pairs < 1 µÅ | B: `duplicate_groups(0.05)` |
|---|---:|---:|---:|---:|---:|---:|
| CFA1 | 242 | 0.53 | 2.03 | **1.48** | **18** | 1.05 |
| HKUST1 | 624 | 7.47 | 11.05 | 3.98 | 0 | 7.15 |
| MFU4l | 648 | 11.42 | 16.03 | **4.38** | 0 | 11.62 |
| MIL53 | 104 | 0.34 | 1.12 | 0.75 | 0 | 0.44 |
| MOF-5 | 424 | 0.19 | 3.08 | 2.88 | 0 | 6.03 |
| Ni2Cl2BTDD | 1152 | 2.33 | 10.05 | **7.75** | **360** | 2.99 |
| UIO66 | 432 | 0.22 | 2.96 | 2.75 | 0 | 6.04 |
| ZIF-8 | 102 | 0.07 | 0.67 | 0.60 | 0 | 1.06 |
| zn_oac | 210 | 0.10 | 1.27 | 1.16 | 0 | 2.30 |

All times in milliseconds. `FORMATS.read` itself is 0.6–4.9 ms on these
files. **Decision 1:** the detector is A — `neighbor_pairs` over the P1 cell
with `min_distance=0`. The expansion is needed to draw the structure anyway,
so its marginal cost is the query alone: **0.6–7.8 ms, worst case 7.75 ms on
the largest shipped sample.** `duplicate_groups` is the same order of
magnitude but answers a different question (which *sites* merge) and belongs
in the dialog where a tolerance can be chosen.

The count at a chemical floor rather than exactly zero:

| tolerance | CFA1 | Ni2Cl2BTDD | the other seven |
|---|---:|---:|---:|
| 1e-6 Å | 18 | 360 | 0 |
| **0.05 Å** | **18** | **2088** | **0** |
| 0.4 Å | 18 | 2088 | 0 |

**Decision 2:** run it at **0.05 Å**, which is `p1.SPECIAL_POSITION_TOL`, not
at 1e-6. It costs the same, it fires on exactly the two structures that are
wrong, and it is silent on the other seven — and, unlike `duplicate_groups`,
it *can* see a site duplicated by its **own** orbit, which is the open TODO
entry under § Symmetry (see Docs below).

### 3. `asymmetrize` and the subgroup (`probes/tier1/subgroup.py`)

**The group it should have found is not available where the warning would
go.** Measured directly:

```
before: space_group=Fm-3m sites=10   meta keys=[chemical_formula, format,
                                      source, systematic_name, title, warnings]
after : space_group=P1    sites=648  meta keys=[... identical ...]
-> the group the file said is GONE: nothing on the P1 structure remembers it
```

`asymmetrize(structure, ...)` *does* have `structure.space_group` — but after
Reduce to P1 that is P1, and P1 → Pmmm is a supergroup, correctly found.
Comparing against the input group catches only *Find Symmetry run directly on
a symmetric structure*, which is not the reported case.

The round trip on all nine samples, and what each end says today:

| sample | file | found | `ok` | order | sites | warnings |
|---|---|---|:-:|---|---|:-:|
| CFA1 | P321 | — | — | — | — | **raises** "too close distance" |
| HKUST1 | Fm-3m | Fm-3m | True | 192→192 | 6→6 | 0 |
| **MFU4l** | **Fm-3m** | **Pmmm** | **True** | **192→8** | **10→87** | **0** |
| MIL53 | P6₃/mmc | P1 | True | 24→1 | 7→104 | 0 |
| MOF-5 | P1 | Fm-3m | True | 1→192 | 424→7 | 0 |
| Ni2Cl2BTDD | H-3m | — | — | — | — | **raises** "too close distance" |
| UIO66 | P1 | P1 | True | 1→1 | 432→432 | 0 |
| ZIF-8 | P1 | P1 | False | 1→1 | 102→102 | 1 (setting) |
| zn_oac | P1 | P1 | True | 1→1 | 210→210 | 0 |

So the answer must come from a **tolerance ladder**, not from history. What
one costs, on the P1 form of each sample:

| sample | one `detect` at 1e-5 | full ladder (1e-5 … 1e-1) | ×  | what the ladder finds |
|---|---:|---:|---:|---|
| **MFU4l** | **8.4 ms** | **127.8 ms** | 15.2 | `#47 · #47 · #123 · #225 · #225` |
| MOF-5 | 15.7 | 76.8 | 4.9 | `#225` throughout |
| HKUST1 | 7.9 | 36.7 | 4.6 | `#225` throughout |
| UIO66 | 6.8 | 31.8 | 4.7 | `#1` throughout |
| MIL53 | 0.7 | 5.3 | 7.3 | `#1 · #194 · #194 · #194 · #194` |
| zn_oac | 1.0 | 4.0 | 4.2 | `#1` throughout |
| ZIF-8 | 0.4 | 2.2 | 5.0 | `#1 · #1 · #1 · #1 · #8` |
| CFA1 / Ni2Cl2BTDD | 0.3 / 0.9 | 0.7 / 1.9 | — | FAIL at every tolerance |

and the group's **order** along the ladder, which is what the test will be:

| sample | 1e-5 | 1e-3 | 1e-2 | 5e-2 | 1e-1 |
|---|---|---|---|---|---|
| MFU4l | #47/8 | #123/16 | **#225/192** | #225/192 | #225/192 |
| MIL53 | #1/1 | **#194/24** | #194/24 | #194/24 | #194/24 |
| ZIF-8 | #1/1 | #1/1 | #1/1 | **#8/4** | #8/4 |
| HKUST1, MOF-5 | #225/192 | … | … | … | … (flat) |
| UIO66, zn_oac | #1/1 | … | … | … | … (flat) |

**Decision 3:** the ladder is `(1e-3, 1e-2, 5e-2)`, filtered to values greater
than the requested `symprec`, **stopping at the first tolerance that finds a
group with more operations**. On MFU-4l it stops at 1e-2 having paid
**88.5 ms for three detects** (measured); the worst case, where nothing
improves and all three run, is **~128 ms**. That is inside a click and does
not need a background thread. ZIF-8 fires at 5e-2 with Cc (#8) — a true
statement about that cell, and the reason the ladder stops at 0.05 Å and not
at 0.1 Å.

### 4. How long Stop stays dead, per candidate polling point (`probes/tier1/cancel_grain.py`)

UFF, L-BFGS, 10 steps, the calculator's `compute` counted:

| structure | cell | steps | evaluations | eval/step | per step | per evaluation |
|---|---|---:|---:|---:|---:|---:|
| MFU4l (648 atoms) | fixed | 11 | 12 | 1.1 | 9.0 ms | 8.2 ms |
| **MFU4l** | **relaxing** | 11 | **156** | **14.2** | **106.9 ms** | **7.5 ms** |
| MIL53 (104 atoms) | fixed | 11 | 11 | 1.0 | 2.1 ms | 2.1 ms |
| MIL53 | relaxing | 11 | 143 | 13.0 | 28.9 ms | 2.2 ms |

The 14.2 is `numeric_stress`'s twelve extra evaluations a step
(performance.md § 5), so **with the cell relaxing — which is what a cell scan
always does — one "step" is fourteen evaluations.**

Against that, today's granularity on a scan is **one whole grid point**:
`max_steps` defaults to 500 (`xtal/modules/scan.py:195`), so the dead Stop is
up to 500 × 106.9 ms ≈ **53 s on MFU-4l**, and at CLAUDE.md's own
0.44 s/step on Ni2Cl2BTDD, 500 × 0.44 s ≈ **3.7 minutes** — doubled to ~7
with a pre-relax engine configured.

**Decision 4:** poll **per energy evaluation**, not per step. Per step would
be 106.9 ms, which is fine for a human, but per evaluation is the same amount
of code in one chokepoint (`_Problem.__call__`) and it makes `cancel=` mean
for UFF and MACE what it already means for xTB and DFTB+ — the asymmetry
`optimize.steps`' own docstring describes.

### 5. A label with a space or a `#` (`probes/tier1/labels.py`)

Twelve hostile labels through `write_cif` → `FORMATS.read`, and through
`write_project` → `read_project`:

| label | CIF re-read | project |
|---|---|---|
| `Na 1` | **raises** "Wrong number of values in loop `_atom_site_*`" | same |
| `#Na1` | **209 sites of 210 — the atom is gone, rc 0** | same |
| `_Na1`, `Na\tNa` | raises, wrong number of values | same |
| `;Na1`, `$Na1` | raises, parse error | same |
| `data_Na1`, `loop_` | raises, parse error | same |
| `Na'1`, `Na"1`, `[Na1]` | round-trips today | round-trips today |
| `'Na1'` | comes back as `Na1` (quotes eaten) | same |

Three things this settles that the review did not:

1. **The reader already round-trips a correctly quoted label.** Hand-quoting
   the row to `'Na 1'` and re-reading gives `label='Na 1'`, 210 sites. So the
   fix is writer-only; `cif_reader` needs no change.
2. **There is one `_quote`, not three copies.** It is
   `xtal/io/cif_writer.py:51` and is called on five fields (`_audit_creation_
   method`, `_chemical_formula_sum`, `_space_group_name_H-M_alt`, `_..._Hall`,
   and each symmetry triplet). The CSSR, gen, XYZ and PDB writers do not write
   site labels at all — verified by round-tripping the same hostile labels
   through each, all 210 sites back. **The hole is CIF-only**, and `.xtalproj`
   inherits it because it embeds the same text.
3. **`_quote` itself has two bugs that routing labels through it would
   expose.** `_quote("Na'1")` returns `'Na 1'` — it replaces the apostrophe
   with a *space*, so a label that round-trips correctly today would come back
   corrupted; and `data_Na1` / `loop_` are not quoted at all (the leading-
   character test is `text[0] in "_#$[];"`), which is a parse error. Both must
   be fixed in the same commit as the routing, or the fix is a regression.

### 6. Where a non-positive `symprec` reaches spglib (`probes/tier1/symprec.py`)

One subprocess per door, so a segfault names its own door:

```
symmetry.detect(-1)              rc=-11   (SIGSEGV)
symmetry.assign_wyckoff(-1)      rc=-11
symmetry.standardize(-1)         rc=-11
symmetry.asymmetrize(-1)         rc=-11
symmetry.detect(0)               rc=1     ValueError: ... spacegroup search failed
supercell.niggli_reduce(eps=-1)  rc=1     SpglibCppError: Niggli reduction failed
commands.FindSymmetry(-1)        rc=0     (constructs fine; segfaults on apply)
xtal symmetry --symprec -1       rc=-11
xtal symmetry --symprec -1 --wyckoff  rc=-11
```

**Decision 5:** two guarded call sites, not five. `assign_wyckoff` and
`asymmetrize` both begin by calling `detect`, so guarding `detect` covers
them; `standardize` calls `spglib.standardize_cell` itself at
`symmetry.py:409` and needs its own. `niggli_reduce`'s `eps` is **not** a door
— spglib raises there. `subgroups._name` uses a constant.

### 7. Does `fb38d25` conflict with the worker prototype? **No.**

`git show fb38d25` touches two files. In `xtalapp/docks/ff_panel.py` the hunk
is at lines **502–520** (`_engine_changed`'s `declared` → `generated`), about
two hundred lines above the prototype's one-word change. In
`tests/test_ff_ui.py` it adds a single visibility test,
`test_choosing_uff_shows_the_controls_that_are_uffs`, which drives combo boxes
and touches no thread.

The call site itself is textually unchanged and simply **moved down six
lines**:

| reference | at `3cd15e2` (this review) | at `fb38d25` (`origin/main`) |
|---|---|---|
| `start_in_thread(self.worker)` | `ff_panel.py:726` | **`ff_panel.py:732`** |
| `from xtalapp.workers import ...` | `ff_panel.py:87` | `ff_panel.py:87` (unchanged) |

`start_in_thread(worker, parent=None)` already takes the parent
(`xtalapp/workers.py:179`), so `start_in_thread(self.worker, self)` is valid
against both commits. A rebase applies cleanly; only the line number in the
recommendation is stale.

---

## Phase 1 — CIF labels are quoted, and `_quote` is correct (`xtal/io/cif_writer.py`)

**What changes.** `cif_string` writes the `_atom_site_label` and
`_atom_site_type_symbol` columns through `_quote`, and `_bond_loop` writes its
two `_geom_bond_atom_site_label_*` columns the same way — four call sites, all
inside `cif_string` (the site row at `:136`) and `_bond_loop` (the bond row at
`:191`). Because a quoted field is longer than eight characters, the
fixed-width `f"{...:<8s}"` padding is applied to the *quoted* text, not to the
raw label, so the columns still line up. `_quote` itself gains two
corrections measured above: a value containing a single quote is wrapped in
double quotes instead of having its apostrophes replaced by spaces, and the
reserved *word* prefixes `data_` and `loop_` join the reserved leading
characters. `_perception_loop` needs nothing — it writes atom indices, not
labels.

**Invariant.** *"The CIF carries the bonds; Export cleans."* The workspace
copy of a structure **is** the document, so the file the user's markers and
net live in must be one this application can read back. This phase is that
invariant's precondition, not a change to it: after it, every label the
Inspector accepts survives `Ctrl+S`. `xtal.io.export.for_export` is
untouched — quoting is not cleaning.

**Tests** (`tests/test_io.py`, beside the existing round-trip tests):

- `test_a_label_with_a_space_survives_being_saved` — writes a structure whose
  site 0 is `Na 1`, reads it back, asserts the label and the site count.
  Regression: the `.cif` and the `.xtalproj` both raise "Wrong number of
  values in loop `_atom_site_*`" and the document is unopenable.
- `test_a_label_starting_with_a_hash_does_not_delete_its_atom` — asserts
  `n_sites` is unchanged. Regression: the atom vanishes on save with rc 0,
  which is the worst failure mode in the report.
- `test_a_label_with_an_apostrophe_is_not_rewritten` — asserts `Na'1` comes
  back as `Na'1`. Regression: `_quote` turns it into `Na 1`, which is a
  *new* corruption introduced by this very fix.
- `test_a_label_that_reads_as_a_cif_keyword_is_quoted` — `data_Na1` and
  `loop_`. Regression: parse error on re-read.
- `test_a_bond_between_awkwardly_labelled_sites_round_trips` — the bond loop
  half; bond count preserved.
- `tests/test_project.py::test_a_project_keeps_an_awkward_label` — the
  `.xtalproj` path, because it embeds the CIF text and is the `Ctrl+S`
  target.

**Existing tests to change:** none expected. The CIF written for every
well-behaved label is byte-identical — `_quote` returns its input unchanged
unless the value contains whitespace, a quote, or a reserved prefix. Run
`tests/test_io.py tests/test_project.py tests/test_real_structure.py
tests/test_stored_bonds.py tests/test_cgd.py` to confirm; `test_real_structure.
py::test_cif_round_trip` is the one that would notice a stray quote.

**Size: S.** Four call sites and two lines inside `_quote`.

**Ordering:** none. Independent of everything else here.

### Phase 1b (optional) — the Inspector refuses what the writer would have to escape

**What changes.** `xtalapp/docks/inspector.py` gives `self.label` (`:89`) a
`QRegularExpressionValidator` refusing whitespace and the reserved leading
characters, and `_commit_label` (`:342`) keeps its `.strip()`.

**Say plainly: this is not needed for correctness once Phase 1 lands**, and it
costs the user the ability to type a label a foreign CIF legitimately
contains. It is listed because the review named the `QLineEdit` as the reach;
it should be **dropped unless Jules wants it**, and it must not be a
precondition for Phase 1.

**Invariant.** None touched. **Test:** `tests/test_inspection_ui.py::
test_a_label_with_a_space_is_refused_in_the_inspector`. **Size: S.**
**Ordering:** after Phase 1, never before.

---

## Phase 2 — `symprec <= 0` raises instead of segfaulting (`xtal/core/symmetry.py`)

**What changes.** A module-level `_checked_symprec(symprec)` beside
`DEFAULT_SYMPREC` (`:45`), called at the top of `detect` (`:139`) and of
`standardize` (`:400`) — the two functions that hand a caller's tolerance to
spglib. It raises `ValueError` and returns the float, so the call sites read
`symprec = _checked_symprec(symprec)`. `assign_wyckoff` and `asymmetrize`
inherit the guard through `detect`. `angle_tolerance` is **not** guarded: a
negative value is meaningful there (`DEFAULT_ANGLE_TOLERANCE = -1.0` means
"derive it from symprec").

The sentence, in the house style — it names the value and the reason lives in
the docstring:

```python
raise ValueError(
    f"symprec must be greater than zero, not {symprec:g}")
```

with the docstring saying *why* it is in the core and not the dialog: spglib
segfaults on a negative tolerance rather than raising, a segfault is not
catchable, and an overnight scan or a module run that reached one would take
the unsaved work with it.

`xtalapp/dialogs/find_symmetry.py:156`'s `if symprec <= 0:` **stays** — it is
an inline message in a live-updating dialog, not a guard, and it must keep
reporting before a detection is attempted. Its comment gains a line saying
the core now refuses too.

**Invariant.** *"`xtal/` imports no Qt. Anything crystallographic lives here
and is testable without a display."* Today the only validation of a
crystallographic input is in the one module that imports Qt; this phase moves
the rule to where the rule belongs and leaves the *presentation* of it in the
dialog.

**Tests** (`tests/test_symmetry.py`):

- `test_a_tolerance_of_zero_or_less_is_refused_before_spglib_sees_it` —
  parametrised over `detect`, `assign_wyckoff`, `standardize`, `asymmetrize`
  and `-1.0`/`0.0`/`-1e-9`; `pytest.raises(ValueError, match="greater than
  zero")`. Regression: SIGSEGV, rc 139, no traceback, unsaved work lost.
- `tests/test_cli.py::test_a_negative_symprec_is_an_error_not_a_crash` —
  `xtal symmetry <file> --symprec -1` exits 1 with `error:` on stderr, and
  with `--wyckoff` too. Regression: rc -11. Run it in a subprocess; an
  in-process assert would take the test runner with it if the guard is
  missing.

**Existing tests to change:** none. No test passes a non-positive symprec
today (`grep -rn 'symprec' tests/` finds only positive values).

**Size: S.** One helper, two call sites, two tests.

**Ordering:** must land **before Phase 7** — `asymmetrize`'s ladder calls
`detect` repeatedly with derived tolerances, and it should be impossible for
that loop to construct a bad one.

---

## Phase 3 — a structure that opens with atoms on top of each other says so (`xtal/io/registry.py`)

**What changes.** A new `xtal/core/overlaps.py` holding
`coincident_pairs(structure, tol=p1.SPECIAL_POSITION_TOL)` — expand to P1,
one `neighbors.neighbor_pairs(cell.frac, lattice, cutoff=tol,
min_distance=0.0)` call, return the pairs under `tol`. It also splits them,
using `cell.site_idx`, into pairs whose two atoms come from **different**
sites (Merge Duplicates collapses those) and pairs from the **same** site's
own orbit (Merge Duplicates cannot see those; Standardize is the answer) —
see the TODO entry this closes, below. A `describe(...)` beside it returns
the sentence.

`FormatRegistry.read` and `FormatRegistry.read_all`
(`xtal/io/registry.py:86` and `:93`) append the sentence to
`structure.meta.setdefault("warnings", [])`, and so does
`xtal/io/project.py::read_project`, which does not go through the registry.

**`Document.adopt` is the wrong place and must not be used**: it only
re-points `self._path` at the workspace copy (`xtalapp/document.py:181`) and
never sees a structure. Nothing in the GUI needs a change at all —
`Document.warnings` is refreshed from `meta["warnings"]` in `__init__`
(`:128`), `set_structure` (`:355`) and `_after_change` (`:526`), and it is
already shown by `xtalapp/docks/info.py:69` ("warning: …"), by the status bar
(`xtalapp/documents.py:249` and `:304`, "opened with N warning(s)"), and
printed by `xtal/cli.py:34`. Verified: this is the same channel the
space-group disagreements use (`cif_reader.py:153`) and the malformed Hall
symbol on MFU-4l (`tests/test_real_structure.py:45`).

The sentence, measured against the two files it fires on:

> `18 pairs of atoms are on top of each other (within 0.05 A); Merge
> Duplicates will collapse them — until then the symmetry, the bonding and
> every energy are for a different crystal`

and for the same-site case:

> `Zn1 is 0.06 A off its special position and the group is making 3 of it;
> Standardize is what puts it back`

**Invariant.** *"A site is on a special position when its coordinates say it
is, to the precision they were written at"* — this phase is the reporting half
of that paragraph, which ends "**Nothing reported it**". And it sits inside
*"Bonds are recalculated only when the user presses Recalculate Bonds"*: the
check **reports and changes nothing** — no merge, no site moved, no bond, and
it is not on the undo stack. `p1.expand` is memoised on the structure
(`Structure.cached`), so opening does not expand twice.

**Tests** (`tests/test_merge_duplicates.py`, which is already the
Ni2Cl2BTDD file's test):

- `test_a_sample_with_coincident_atoms_warns_when_it_is_opened` — reads
  `Ni2Cl2BTDD.cif` and `CFA1.cif` through `FORMATS.read`, asserts a warning
  mentioning "on top of each other" and the counts 360 / 18 at 1 µÅ. Failure:
  two of nine shipped samples open silently wrong, which is where the 6786
  bonds, the coordination of 28 and the 6.28e6 kcal/mol come from.
- `test_the_other_seven_samples_open_without_that_warning` — parametrised over
  the rest. Failure: a false positive on every open makes the channel useless.
- `test_the_warning_survives_the_project_round_trip` — through
  `read_project`, which is the second door.
- `test_a_site_duplicated_by_its_own_orbit_is_named_separately` — build the
  Zn-0.06 Å-off-the-3-fold case from CLAUDE.md's own paragraph; assert the
  sentence names Standardize and not Merge Duplicates. Failure: the user is
  sent to a menu item that says "no duplicates".
- `tests/test_cli.py::test_a_coincident_structure_warns_on_the_command_line` —
  `_load` prints it to stderr.

**Existing tests to change:** none found. `grep -rn 'CFA1\|Ni2Cl2BTDD' tests/`
gives `test_merge_duplicates.py` (reads the file, asserts merge counts),
`test_scan_dialog.py` (builds a dialog on it) and a `test_vtk_render.py`
docstring; none asserts an empty warning list.
`tests/test_real_structure.py:120`'s `assert not back.meta.get("warnings")` is
about MFU-4l, which has **zero** coincident pairs at every tolerance measured
— it is safe, and it is the test that proves the check does not fire on a
healthy framework.

**Size: S.** One small new module, three call sites, five tests.

**Ordering:** independent. Land it **before Phase 4**, which reuses
`overlaps.coincident_pairs`.

---

## Phase 4 — the force field refuses a geometry it has no number for (`xtal/core/neighbors.py`, `xtal/ff/uff/calculator.py`)

**What changes.** `neighbor_pairs` keeps its `min_distance` guard — dropping a
zero-separation pair is what keeps the van der Waals sum finite — but stops
swallowing the fact: `PairList` gains a `n_dropped: int` field set at
`neighbors.py:156` from `np.count_nonzero(~keep)`, and `neighbor_pairs`'
docstring finally mentions the parameter (it does not today). Then
`UFFCalculator._check_topology` (`xtal/ff/uff/calculator.py:336`) calls
`overlaps.coincident_pairs(self.structure)` — the same helper Phase 3 adds —
and **raises `CalculatorError`** when any pair is closer than 1 µÅ.

**Refuse, not warn, and here is the argument.** A warning would leave
`converged=True, |F|max=0` standing on an impossible geometry, and CLAUDE.md
is explicit that a hole is better than a number: *"An unconverged scan point
is not a number… a hole plotted as a zero is the deepest point of every
landscape it appears in."* A *converged* point over a geometry with atoms at
0 Å is worse, because nothing hatches it. Refusing also costs nothing to
recover from: `xtal/ff/scan.py:549` already catches `CalculatorError` and
returns `_failed(index, targets, branch, at, blank, str(error))` — a hole with
the reason beside it, exactly the shape the invariant asks for — and the Force
Field panel already shows a `CalculatorError` as a message. The floor is
**1 µÅ, not 0.05 Å**: a drag or an optimiser step can legitimately put two
atoms 0.04 Å apart mid-edit, and only symmetry images land at *exactly* zero.
Measured today for contrast: `Ni2Cl2BTDD` builds in 1560.7 ms and returns
`E=6.28e6, |F|max=2983`, with its only warning being about atom typing.

**Invariant.** *"A force field or optimiser never changes the bonding or the
atoms."* Refusing is the invariant kept, not broken: the alternative — a
calculator that quietly discards the pairs it cannot price — is the one that
reports about a structure other than the one it was given. And *"An
unconverged scan point is not a number"*, above.

**Tests:**

- `tests/test_neighbors.py::test_a_pair_dropped_as_an_overlap_is_counted` —
  two atoms at the same point, `n_dropped == 1`. Failure: the count is the
  only evidence the guard left behind.
- `tests/test_uff_calculator.py::test_two_atoms_in_the_same_place_are_refused_
  rather_than_priced` — the three-atom C/C/O cell from edge-cases §4;
  `pytest.raises(CalculatorError)`. Failure: `E=315.024` identical whether the
  overlap is exact or 1e-6 frac apart, forces zero, `converged=True` after one
  step.
- `tests/test_scan.py::test_a_point_whose_geometry_overlaps_is_a_hole_not_a_
  number` — one scan point over an overlapped structure; `energy` is NaN,
  `converged` is False and the message names the overlap. Failure: a landscape
  with a false minimum in it.
- `tests/test_uff_calculator.py::test_a_healthy_framework_is_not_refused` —
  MFU-4l builds. Mark `@pytest.mark.slow` if it approaches a second.

**Existing tests to change: yes, expect one or two.** Any test that builds a
UFF calculator over `Ni2Cl2BTDD.cif` without merging first would now raise.
`grep -rn 'Ni2Cl2BTDD' tests/` finds only `test_merge_duplicates.py` and
`test_scan_dialog.py`, and neither builds an engine — but run
`tests/test_uff_calculator.py tests/test_ff_ui.py tests/test_scan*.py
tests/test_mace.py tests/test_xtb.py` before believing that, because the
engine fixtures in `conftest_ff.py` are shared.

**Size: M.** Two packages, a public dataclass field, and the one judgement
call in this document that changes behaviour a user can see.

**Ordering:** **after Phase 3** (reuses `overlaps.coincident_pairs`) and
**before Phase 6** if both are wanted in the same release, because Phase 6's
tests assert what a stopped point looks like and this one changes what a
refused point looks like. They do not otherwise interact.

---

## Phase 5 — `add_bond` is a hash lookup (`xtal/core/structure.py`)

**What changes.** `Structure.add_bond` (`:534`) stops scanning
`self.bonds`. The duplicate test becomes membership in a set of
`_bond_identity` tuples, built lazily and invalidated by the structure's own
revision stamp — the mechanism `Structure.cached` (`:641`) already uses:

```python
_BOND_IDS = Change.TOPOLOGY | Change.SYMMETRY

def _bond_ids(self) -> set:
    stamp = self._stamp(_BOND_IDS)
    if self._ids_at != stamp:
        self._ids = {self._bond_identity(b) for b in self.bonds}
        self._ids_at = stamp
    return self._ids

def add_bond(self, bond: Bond) -> bool:
    self._check_bond(bond)
    identity = self._bond_identity(bond)
    ids = self._bond_ids()
    if identity in ids:
        return False
    self.bonds.append(bond)
    self.touch(Change.TOPOLOGY)
    ids.add(identity)                    # the append, kept in step
    self._ids_at = self._stamp(_BOND_IDS)
    return True
```

**The identity tuple does not change.** It is `_bond_identity` exactly as it
stands (`:518`): `(bond.kind == TOPOLOGY, bond.key(self.space_group))`, where
`key` is `(i, j, op, image)` of the **canonical** form — the lexicographically
smaller of the bond and `bond.reverse(space_group)`. That is already the
normalisation: site indices, the operation index, and the lattice translation,
with the direction resolved by the group. Nothing about *what makes two bonds
the same bond* is being redefined; only how many times the question is asked.

**`reverse` stays.** It is `canonical`'s only way to turn a bond round
(`structure.py:170`) and it is what the identity *means*; it is also asserted
directly by `tests/test_bonding.py:267`,
`tests/test_bond_orders.py:401` and `tests/test_topology.py:546`. The fix does
not remove the matmul — it stops doing it `n` times per insertion.

**Why the stamp and not an eagerly maintained set.** `structure.bonds` is a
public list and is replaced wholesale in seven places
(`symmetry.py:289` and `:620`, `structure.py:348` and `:495`,
`export.py:51`, `commands/atoms.py:214`, `io/cif_reader.py:206`). A set
maintained only by `add_bond`/`remove_bond`/`set_bonds` would go stale on
every one of them. The stamp catches all but one: `cif_reader.py:206` appends
to `structure.bonds` without calling `touch`, and that is safe only because
the reader never calls `add_bond` on the same structure afterwards — **say so
in the docstring**, because it is the one way this can be got wrong later. The
strongest evidence for the stamp is a test that already does the risky thing:
`tests/test_bonding.py::test_a_net_edge_is_removed_by_any_of_its_copies` does
`halite.bonds.append(...)` followed by `halite.touch()`, and the stamp handles
it correctly where an eager set would not.

**The six loop callers stay loops.** `symmetry.py:243` (Reduce to P1),
`project.py:191` (project open), `mof/build.py:517`, `build/molecule.py:105`,
`commands/clipboard.py:271` and `commands/connections.py:146` each need
per-bond de-duplication, which `set_bonds` deliberately does not do ("the
caller owns the deduplication"). With `add_bond` at O(1) they no longer need
converting — which is what keeps this phase S. `mof/build.py:561-583` already
keeps its own `seen` set of `bond.key(space_group)` and is the precedent for
the tuple.

**Invariant.** *"Structure edits go through `Document.apply` with a `Change`
flag"* — untouched; and *"a long operation over a whole selection is applied
in one batch"*, which is the same complaint this fixes from the other end.
`Change.TOPOLOGY` is still touched exactly once per added bond, so every panel
refreshes exactly as often as before.

**Tests:**

- The three that already pin duplicate rejection **must keep passing
  unchanged**, and they are the real test of this phase:
  `tests/test_structure.py::test_bonds_are_direction_independent` (a bond and
  its reverse; add True then False; remove either),
  `tests/test_bonding.py::test_a_bond_and_the_same_bond_backwards_are_one_bond`
  (through the group, on halite's Fm-3m),
  `tests/test_topology.py` line 111 (a chemical bond and a net edge on the
  same pair do **not** collide) and
  `tests/test_bonding.py::test_the_same_net_edge_is_not_stored_twice`.
- `tests/test_structure.py::test_a_bond_added_after_the_list_was_replaced_is_
  still_de_duplicated` — `set_bonds`, then `add_bond` of one of them, expect
  False; and `remove_bond` then re-`add_bond`, expect True. Failure: a stale
  set silently admits a duplicate bond, which is drawn twice and takes two
  deletes to remove.
- `tests/test_project.py::test_opening_a_project_with_a_thousand_bonds_is_not_
  quadratic` — build a P1 chain of 200 and of 800 bonds, assert the per-bond
  cost of the larger is within 2× of the smaller. `@pytest.mark.slow`.
  Failure: the 2.1 s re-appears and grows with the framework.

**Existing tests to change:** none. Answers are byte-identical (measured).

**Size: S.** One method, one helper, two fields.

**Ordering:** independent of all six others. It is the best first commit —
biggest measured win, zero behaviour change.

---

## Phase 6 — Stop lands on a UFF or MACE scan (`xtal/ff/optimize.py`, `xtal/ff/scan.py`)

Two commits; the first is the one users meet.

### 6a — `optimize.steps` honours the `cancel` it advertises

**What changes.** `steps` (`xtal/ff/optimize.py:1359`) already forwards
`cancel` to engines that can be stopped mid-evaluation
(`if cancel is not None and hasattr(calculator, "stop_with")`). It gains the
symmetric half for the ones that cannot: when `cancel` is given, the
calculator is wrapped in a small `_Stoppable` proxy whose `compute` and
`numeric_stress` check `cancel.requested` and raise `CalculatorStopped` before
delegating, with `__getattr__` forwarding everything else (`warnings`,
`summary`, `stop_with`, `provides_stress`, `n_atoms`). Every optimiser reaches
the calculator through `_Problem.__call__` (`:709`), so one proxy covers
`lbfgs`, `fire`, `smart`, `steepest_descent`, `conjugate_gradient`,
`quasi_newton` and `abnr` with no signature change anywhere — and it covers
the twelve `numeric_stress` evaluations a relaxing-cell step spends, which is
where the time is.

`xtal/ff/markers.py`'s `WithoutMarkers` is the precedent for wrapping a
calculator; put `_Stoppable` beside `_Problem`, not in `markers.py`.

**Granularity: per evaluation** — 7.5 ms on MFU-4l with the cell relaxing,
against 106.9 ms per step and 53 s per scan point (measured above). The cost
is one `Event.is_set()` per evaluation, ~14 per step.

**What a cancelled optimisation returns.** `CalculatorStopped`, which is
already the contract for the external engines and which **both** consumers
already handle correctly:

- `xtalapp/workers.py:129-135` catches it, keeps the last completed step and
  reports it — *"exactly as if Stop had landed between two"*.
- `xtal/ff/scan.py:546-548` catches it and returns
  `_failed(index, targets, branch, at, blank, "stopped")` — energy NaN,
  achieved NaN, `converged=False`: a **hole**, hatched on the heat map,
  outside the colour scale, `--` in the log.

So this commit needs no new error type and no new branch.

### 6b — a stopped scan point is a hole, not the energy of wherever it stopped

**What changes.** `xtal/ff/scan.py::_one_point` passes a callback into both
`optimize.run` calls — the real one (`:541`) and the pre-relaxation
(`_prerelaxed`, `:580`) — `callback=lambda step: not cancel.requested`, so the
step loop breaks the way `OptimizationWorker.run` breaks it even if 6a is not
in yet. **And immediately after the call it converts that into a hole:**

```python
if cancel is not None and cancel.requested:
    return _failed(index, targets, branch, at, blank, "stopped")
```

This is the part that matters and it is easy to miss. Without it,
`optimize.run` returns `converged=False` with a **finite energy** and a
message *"stopped by the caller at step N"* — a number for a geometry that is
not the relaxed point, which `scan` would write into `scan.csv` and plot,
hatched, as if it were a converged-short point. `_failed` already exists and
already produces the right thing.

**Invariant.** *"An unconverged scan point is not a number"* — and a stopped
one is not even unconverged; it is a hole. Also *"A scan point is written the
moment it finishes"*: the hole is written by the same `on_point` callback as
every other point, so Stop leaves a landscape with a gap rather than losing
one. Also *"A scan holds a coordinate; it does not freeze the atoms that
define it"* — untouched; the proxy sits above the constraint machinery and
changes no geometry.

**Tests** (`tests/test_scan.py`, `tests/test_optimize.py`):

- `tests/test_optimize.py::test_a_cancelled_in_process_optimisation_stops_
  inside_a_step` — a stub calculator that cancels on its third `compute`;
  assert `CalculatorStopped` and that fewer than one full step's worth of
  evaluations ran. Failure: `cancel=` is documented and ignored, which is
  today.
- `tests/test_optimize.py::test_a_cancelled_run_keeps_the_last_finished_step`
  — the `workers.py` contract, headless. Failure: Stop loses the work done.
- `tests/test_scan.py::test_stopping_a_scan_leaves_a_hole_and_not_a_number` —
  cancel during a point; assert `np.isnan(point.energy)`,
  `point.converged is False`, `"stopped" in point.message`. Failure: a
  plotted number for a half-relaxed geometry, which is the deepest point of
  any landscape it lands in.
- `tests/test_scan.py::test_a_stopped_point_is_still_written_to_the_csv` —
  the row is `--`. Failure: an overnight run that was stopped loses its
  landscape.
- `tests/test_scan_module.py::test_stop_is_answered_within_a_step_not_a_point`
  — a counting stub; assert the number of evaluations after Stop is bounded.
  Failure: the 3.7-minute dead Stop on Ni2Cl2BTDD.

**Existing tests to change:** possibly `tests/test_scan.py`'s existing cancel
test, which today asserts a cancelled scan returns early at a *grid index*
boundary (`scan.py:460`). That behaviour is unchanged; check whether it also
asserts something about the last point's energy.

### 6c — the two modules that never poll at all

**What changes.** `xtal/modules/build.py::build_molecule` and
`xtal/modules/net.py::draw_net` gain `job.check()` before the call and
`if job.cancelled: return JobResult.stopped(...)` after it, copying
`xtal/modules/mof.py:188-213` — **including its docstring's honesty**, which
says cancellation is checked either side and not during, and why.

**Do not put a poll inside the build.** Measured: `topology.by_name` is
**5.1–70.0 ms** across `pcu`, `sod`, `tbo`, `naz-x` and `nbo` (it was 4.0 s
before the KD-tree fix recorded in `pormake/PROVENANCE.md`), and
`from_smiles` is **15–284 ms** after RDKit is imported. There is nothing to
interrupt. Reaching into `analysis/rcsr.py` to add one would be a separate,
larger change for no measurable gain.

**Size: 6a M, 6b S, 6c S.**

**Ordering:** 6b can land before 6a and is worth doing first if only one is
taken — it is the fix for the bug users meet. 6a makes `cancel=` honest for
every caller. 6c is independent of both.

---

## Phase 7 — `asymmetrize` says when it has handed back a subgroup (`xtal/core/symmetry.py`)

**What changes.** After `asymmetrize` (`:434`) has a verified result, and
before it builds its `SymmetryReport`, it runs a short ladder of extra
`detect` calls and, if one of them finds a group with **more operations**,
adds a warning naming that group and the tolerance that found it.

- **The ladder** is `(1e-3, 1e-2, 5e-2)`, filtered to values strictly greater
  than the `symprec` in hand, **stopping at the first improvement**.
  Measured cost (§3 above): **88.5 ms on MFU-4l**, where it stops at 1e-2
  having found Fm-3m; **~128 ms** worst case if nothing improves and all three
  run. Nothing else on the nine samples exceeds 80 ms.
- **The test is the group's order**, not a subgroup-lattice computation:
  "a looser tolerance finds a group with more operations" is a true and
  checkable statement, and `SpaceGroup.order` is already there. No new
  group theory.
- **A candidate is only reported if it also regenerates the cell** — reuse
  `_regenerates(candidate, cell, max(MATCH_TOL, tol))`, the function
  `asymmetrize` already trusts, so a looser tolerance that "finds" a group it
  cannot reproduce is never offered.
- The ladder stops at **0.05 Å** deliberately. At 0.1 Å, ZIF-8 reports Cc
  (#8) where the file says P1 — true, but noise for a structure a user
  deliberately reduced. 0.05 Å is `p1.SPECIAL_POSITION_TOL`, which is the
  tolerance this codebase has already decided is the boundary between "a
  rounding place off" and "a different atom".

The sentence:

> `at symprec 0.01 A this cell is Fm-3m (#225, 192 operations) with 10
> independent sites, not Pmmm (#47, 8); the atom count is the same either way`

**Answering the brief's question directly: the structure's own
`space_group` cannot be used.** It *is* available inside `asymmetrize`, and a
cheap `found.order < structure.space_group.order` check should be added as
well — it is free and it catches Find Symmetry run directly on a symmetric
structure. But it does **not** catch the reported case: after Reduce to P1 the
input group is P1, and nothing on the P1 structure remembers Fm-3m — proved
in §3, the `meta` keys are identical before and after. The ladder is
therefore not an optimisation of a cheaper method; it is the only method.

**A rejected alternative, and why.** `reduce_to_p1` could record the group it
dropped in `meta["reduced_from"]`. That is cheaper, but it only helps the
Reduce-then-Find round trip, does nothing for MIL-53 or for any P1 file a user
opens from elsewhere, and it puts a breadcrumb in `meta` that
`write_cif`/`read_cif` would then have to agree about. The ladder covers every
case with one rule. Mention it to Jules; do not build it.

**Invariant.** *"A site is on a special position when its coordinates say it
is, to the precision they were written at"* — this is the same story at the
group level, and the warning is the reporting the SPECIAL_POSITION_TOL
paragraph says nothing does today. The phase **changes no behaviour**: the
group returned at the requested tolerance is still the group returned. It adds
a sentence to `SymmetryReport.warnings`, which `xtalapp/mainwindow.py:1244`
and `xtalapp/dialogs/spacegroup.py:160` already display.

**Tests** (`tests/test_symmetry.py`):

- `test_a_looser_tolerance_finding_a_larger_group_is_reported` — MFU-4l
  reduced to P1 then `asymmetrize`; assert the report is still `ok`, the group
  is still Pmmm, and a warning names `Fm-3m` and `0.01`. `@pytest.mark.slow`
  (measured 128 ms for the ladder plus the round trip). Failure: a user gets
  an orthorhombic MFU-4l that will scan, optimise and save, with `ok=True` and
  the right atom count — every automatic guard satisfied.
- `test_a_structure_whose_group_is_already_the_best_one_is_not_warned_about` —
  HKUST1, MOF-5, UIO66, zn_oac. Failure: a warning on every Find Symmetry
  makes the channel useless.
- `test_the_ladder_stops_at_the_first_tolerance_that_improves_the_group` —
  count `detect` calls with a spy; MFU-4l must stop at 1e-2, not run 5e-2.
  Failure: the phase costs 128 ms where 88 will do, on every Find Symmetry.
- `test_a_group_a_looser_tolerance_cannot_regenerate_is_not_offered` —
  Failure: the warning sends the user to a tolerance that produces a different
  crystal.

**Existing tests to change: check two.** `tests/test_symmetry.py:152` and
`:288` assert `not report.warnings`. Both are on fixtures
(`rutile`/`quartz`/`halite`) whose groups are flat along the ladder, so they
should pass — but run `tests/test_symmetry.py tests/test_symmetry_ui.py
tests/test_subgroups.py` and read the two assertions before assuming it.

**Size: M.** The change is small; the test matrix is not, and it is the one
phase whose cost is paid on a user-facing click.

**Ordering:** **after Phase 2** (the ladder must not be able to construct a
non-positive tolerance). Independent of the rest.

---

## Phase 8 — the worker-thread fix (`xtalapp/workers.py`, `ff_panel.py`, `mainwindow.py`)

The prototype is written and measured: `review/probes/workers_fixed.py`. The
recommendation is [threads.md §6](../reports/threads.md); this phase is its
mechanics, plus what `fb38d25` changes about it.

### 8a — `start_in_thread` owns the pair from Python

**What changes.** `xtalapp/workers.py:179`'s 27-line `start_in_thread` becomes
the `_Run` / `_LIVE` / `stop_all` version from the prototype — 110 lines, of
which about 45 are docstring in the house style. Four rules, in the order they
matter:

1. The worker has an owner outside the connections **before** the thread
   starts (`_LIVE.add(run)` precedes `thread.start()`).
2. **Nothing is deleted by Qt** — both
   `thread.finished.connect(worker.deleteLater)` and
   `thread.finished.connect(thread.deleteLater)` go.
3. Both objects are owned from Python, on the GUI thread, by `_Run`.
4. The drop happens **one clean event-loop turn after the thread has
   stopped**, via `QTimer.singleShot(0, self._release)`, so nothing is freed
   with Qt still delivering a signal underneath.

`_Run` is deliberately **unparented**: parenting it to the window hands its
lifetime back to C++, and closing the window would then destroy it while
`_LIVE` still held the wrapper — the same zombie the change exists to stop
making. `OptimizationWorker` and `ModuleWorker` are **byte-identical** in the
prototype; nothing else in the file changes.

**Invariant.** None of the product invariants are near this. CLAUDE.md's
§ Testing the GUI paragraph *"A full run wedges roughly one time in four, and
it is a real application bug rather than a test one… **Unfixed**"* is the
thing this phase edits, and `docs/TODO.md` § Testing and threads with it.

### 8b — the two call sites

- **`xtalapp/docks/ff_panel.py`** — `start_in_thread(self.worker, self)`.
  **This reference has moved**: it is **line 726 at `3cd15e2`** and
  **line 732 at `fb38d25`**, because `fb38d25` added nine net lines at
  `ff_panel.py:502-520`. The line of code itself is unchanged, the import at
  `:87` is unchanged, and `start_in_thread` has taken `parent` since before
  either commit — so **the prototype's change applies cleanly over
  `fb38d25`; only the line number in threads.md §6 is stale.** `fb38d25`'s new
  test, `test_choosing_uff_shows_the_controls_that_are_uffs`, drives combo
  boxes and touches nothing threaded.
- **`xtalapp/mainwindow.py::closeEvent`** (**line 1807 at `3cd15e2`**) — after
  `self.stop_module()`, add `self.ff_panel.stop()` and
  `workers.stop_all()`. Today the window can be destroyed with a live thread
  among its children (threads.md §3c), which is an abort rather than a hang,
  and the Force Field worker is not stopped at all. `FFPanel.closeEvent`
  cannot do this job — a docked widget gets no close event when its window
  closes, which is why that method is `# pragma: no cover`.

### 8c — the reaper (threads.md §8)

**What changes.** Two halves, on the right sides of the Qt line:

- `xtal/modules/process.py` gains a module-level `weakref.WeakSet` of live
  `ExternalProcess` objects, joined in `run()` and left in `_close()`, and an
  `atexit` handler that calls `cancel()` on each one still `running`. This is
  headless code and `atexit` is stdlib, so **`xtal/` still imports no Qt**.
- `xtalapp/application.py::Application.__init__` (`:82`) connects
  `self.aboutToQuit` to `workers.stop_all()`.

There is neither today — `grep -rn 'atexit\|aboutToQuit' xtal xtalapp` finds
nothing — and `start_new_session=True` (`process.py:488-498`) deliberately
detaches the child from our process group, so no POSIX signal follows the
parent's death. A crashed or `kill -9`'d application leaves xtb, DFTB+ or
Zeo++ running and writing into a run folder nobody is watching.

**Tests:**

- `tests/test_workers.py` (new file):
  `test_a_finished_worker_and_its_thread_are_dropped_one_turn_later` —
  run a trivial worker, `qtbot.waitUntil` on `_LIVE` emptying, assert both
  references are None. Failure: the leak that the `deleteLater` pair was
  there to prevent comes back.
  `test_stop_all_waits_for_every_thread_and_not_up_to_the_first` — two
  workers, one that will not stop promptly; assert both were waited on.
  Failure: `all()` short-circuits and a live thread survives `closeEvent`,
  which is an abort.
- `tests/test_quit.py::test_closing_the_window_stops_a_running_optimisation` —
  start an optimisation in the FF panel, close the window, assert no live
  thread. Failure: sequence (c) — the window destroyed with a thread among
  its children.
- `tests/test_process_runner.py::test_a_live_external_process_is_killed_at_
  exit` — subprocess test, since `atexit` needs a real interpreter exit.
  Failure: an orphaned solver writing into a run folder.
- **The two latches that broke the last attempt must keep passing**:
  `tests/test_modules_ui.py:91` and `tests/test_ff_ui.py:78`. They pass by
  construction in the prototype (threads.md §3 "Why 'hold the pair alive'
  broke `test_modules_ui`"), but they are the acceptance criterion.

**Existing tests to change:** none expected — no public signature changes, no
caller changes. `tests/test_ff_ui.py` and `tests/test_modules_ui.py` are the
ones to watch.

**Size: L.** Not because the diff is large — it is about 120 lines across
four files — but because the verification is: `review/probes/matrix.sh` before
and after, then **ten full suite runs** with
`-o faulthandler_timeout=90`, serially, on a machine under memory pressure.
Budget the day for the runs, not for the code.

**Ordering:** last, and **on its own branch**. It is the only phase whose
verification is statistical, and mixing it with anything else makes a failed
run ambiguous. Do **not** flip `-n auto` back on in the same commit:
`pyproject.toml:183-185`'s comment can be updated, but CLAUDE.md records a
*second* wedge cause (`conftest.py:62`, eight workers contending on
`cfprefsd`) that deserves its own measured run before the default changes.

---

## Verification (end to end)

Per phase, targeted first:

```bash
.venv/bin/python -m pytest -q tests/test_io.py tests/test_project.py        # 1
.venv/bin/python -m pytest -q tests/test_symmetry.py tests/test_cli.py      # 2, 7
.venv/bin/python -m pytest -q tests/test_merge_duplicates.py tests/test_cli.py  # 3
.venv/bin/python -m pytest -q tests/test_neighbors.py tests/test_uff_calculator.py tests/test_scan.py  # 4
.venv/bin/python -m pytest -q tests/test_structure.py tests/test_bonding.py tests/test_topology.py tests/test_project.py  # 5
.venv/bin/python -m pytest -q tests/test_optimize.py tests/test_scan.py tests/test_scan_module.py      # 6
.venv/bin/python -m pytest -q tests/test_ff_ui.py tests/test_modules_ui.py tests/test_quit.py tests/test_process_runner.py  # 8
```

Serial, never `-n auto`, `-o faulthandler_timeout=90` on anything that might
hang, and `ruff check .` before each commit (never `ruff format`).

In the real window, with `XTAL_NO_CONFIRM_CLOSE=1`:

```bash
# 1 — rename an atom to "Na 1" in the Inspector, Ctrl+S, reopen the tab.
.venv/bin/python .claude/skills/run-app/drive.py --scratch /tmp/t1 \
    --open resources/samples/zn_oac.cif --grab inspector \
    --viewport-shot review/shots/tier1-label.png
# 3 — the Info dock must carry the warning, the status bar "opened with
#      1 warning(s)", and Merge Duplicates must still say 27 sites.
.venv/bin/python .claude/skills/run-app/drive.py --scratch /tmp/t3 \
    --open resources/samples/Ni2Cl2BTDD.cif --grab info \
    --viewport-shot review/shots/tier1-coincident.png
# 5 — open an MFU-4l project and watch it appear; 2.1 s becomes ~20 ms.
# 6 — start a UFF scan on Ni2Cl2BTDD, press Stop, and time it: the log must
#      show "--" for the stopped point within a second, not minutes.
# 7 — Reduce to P1, then Find Symmetry on MFU-4l: the dialog must show
#      Pmmm *and* the sentence naming Fm-3m at 0.01 A.
.venv/bin/python .claude/skills/run-app/drive.py --scratch /tmp/t7 \
    --open resources/samples/MFU4l.cif --action reduce_to_p1 \
    --grab find-symmetry --viewport-shot review/shots/tier1-subgroup.png
# 8 — matrix.sh before and after, then ten full suite runs.
REPEATS=5 JOBS=200 review/probes/matrix.sh
```

Then the full suite once at the end of each commit, and ten times for
Phase 8. Check `sysctl vm.swapusage` before trusting any timing.

---

## Docs

**`docs/TODO.md` entries deleted when each ships** — honestly, only two of the
seven touch it, because TODO.md carries none of the CIF, symprec, `add_bond`
or `asymmetrize` findings:

| phase | TODO entry |
|---|---|
| 3 | **§ Symmetry → "Merge duplicates cannot see a site duplicated by its own group"** — **deleted**, but only if Phase 3 is built at 0.05 Å and splits same-site pairs from different-site ones as specified. That entry's own closing sentence is *"Wanted with whatever finally reports a site sitting just off a special position, which nothing does today"*, and the coincident-pair check over the P1 cell is exactly that: it sees a site duplicated by its **own** orbit, which is the blind spot `duplicate_groups` has by construction. Built at 1 µÅ instead, the entry survives and should be amended rather than deleted. |
| 8 | **§ Testing and threads → "A finished worker thread can deadlock the application"** — **deleted in full**, including the *"Seen in the shipped application, 2026-09-15"* paragraph, once ten clean suite runs are on record. Not before. |
| 1, 2, 4, 5, 6, 7 | **none.** TODO.md has no entry for any of them. Phase 6's neighbours — *"A stopped scan cannot be carried on"* (that is `--resume`, a different job) and *"A sweep still starts at the end of its range"* — are **not** closed by it. Say so rather than letting the count look better than it is. |

**`CLAUDE.md`:**

- **Phase 8 rewrites** § Testing the GUI's *"A full run wedges roughly one
  time in four… **Unfixed** — holding the pair alive from Python is the
  obvious remedy and it is not enough on its own"*. It becomes the fixed
  description, with the rule that survives it: *nothing in `workers.py` is
  deleted by Qt*. `pyproject.toml:183-185`'s "-n0" comment is updated in the
  same commit; the flag itself is not flipped.
- **Phase 4 changes an invariant's reach.** *"A force field or optimiser never
  changes the bonding or the atoms"* gains the sentence that a calculator
  handed a geometry with atoms at the same point **refuses** rather than
  pricing what it can reach, with the three-atom measurement as its reason —
  the same shape as every other invariant in that list.
- **Phase 3** is worth one line under the SPECIAL_POSITION_TOL paragraph: that
  paragraph ends "Nothing reported it", and after Phase 3 something does.
- **Phases 1, 2, 5, 6, 7** need no CLAUDE.md change.

**`docs/ROADMAP.md`:** these are unscheduled correctness fixes, not a phase of
the delivery plan (whose Phases 2–4 are the text pass, Help and the manual).
If Jules wants them tracked across sessions, add one short Tier-1 table; do
not fold them into the manual phases.

**Skills and `docs/MENUS.md`:** untouched. No visible label changes, no new
menu entry, no new module, no new dialog — so nothing in
`xtalapp/dialogs/__init__.py`'s `_BY_NAME` mapping and nothing for
PyInstaller to be told about.

---

## Suggested order

Wrong before missing, small before large, one commit per phase, each ending
green. The rule that sets the order: Phase 5 is pure speed with byte-identical
output and no behaviour change, so it is the safest first commit and the one
that makes every later test run faster to iterate on; Phase 8 is last and
alone because its verification is statistical.

1. **Phase 5 — `add_bond` is a hash lookup.** Biggest measured win (2.10 s →
   22.7 ms on MFU-4l), zero behaviour change, answers byte-identical, covered
   by tests that already exist.
2. **Phase 2 — `symprec <= 0` raises.** Closes a segfault. Must precede
   Phase 7.
3. **Phase 1 — CIF labels are quoted** (with the two `_quote` corrections).
   Closes the silent data loss.
4. **Phase 3 — the coincident-atom warning on open.** Makes two shipped
   samples honest.
5. **Phase 4 — the force field refuses an overlapped geometry.** Depends on
   Phase 3's helper.
6. **Phase 6b — a stopped scan point is a hole**, then **6a — `steps`
   honours `cancel`**, then **6c — `build` and `net` check either side.**
   6b first because it is the bug users meet.
7. **Phase 7 — the subgroup warning.** After Phase 2.
8. **Phase 8 — the worker fix**, on its own branch, rebased over `fb38d25`,
   `matrix.sh` before and after, then ten full suite runs.
9. *(optional, only if Jules asks)* **Phase 1b — the Inspector validator.**

### What can share a commit

- **Phases 1 and 2** — both are small, both are pure "refuse or escape bad
  input at the core", neither touches the other's files, and both close a
  `[critical]`. One commit, *"A label the user typed cannot corrupt the file
  it is saved into, and a tolerance spglib cannot survive is refused"*, is
  defensible if you prefer fewer commits. Keep them apart if you want each
  bisectable.
- **Phases 3 and 4** — same helper, same story, same two sample files, and
  Phase 4's tests read better beside Phase 3's. One commit is fine; two is
  cleaner because Phase 4 changes behaviour a user can see and Phase 3 does
  not.
- **Phases 6a, 6b, 6c** — three commits or one; they are three halves of one
  sentence ("Stop means stop"). If one commit, 6b's `_failed` conversion must
  still be its own paragraph in the message.
- **Nothing shares a commit with Phase 8.** A failed suite run must have one
  candidate cause.

### Every item, sized

| # | Item | File and function | Size | Depends on | Deletes a TODO entry |
|---:|---|---|:-:|---|---|
| 1 | CIF labels quoted; `_quote` handles apostrophes and `data_`/`loop_` | `xtal/io/cif_writer.py` — `cif_string`, `_bond_loop`, `_quote` | **S** | — | no |
| 1b | Inspector label validator *(optional; drop unless asked)* | `xtalapp/docks/inspector.py` — `__init__`, `_commit_label` | **S** | 1 | no |
| 2 | `symprec <= 0` raises `ValueError` in the core | `xtal/core/symmetry.py` — `_checked_symprec`, `detect`, `standardize` | **S** | — | no |
| 3 | Coincident atoms reported on open | new `xtal/core/overlaps.py`; `xtal/io/registry.py` — `read`, `read_all`; `xtal/io/project.py` — `read_project` | **S** | — | **yes** — § Symmetry, *"Merge duplicates cannot see a site duplicated by its own group"* (only if built at 0.05 Å) |
| 4 | The force field refuses an overlapped geometry | `xtal/core/neighbors.py` — `neighbor_pairs`, `PairList`; `xtal/ff/uff/calculator.py` — `_check_topology` | **M** | 3 | no |
| 5 | `add_bond` is a hash lookup | `xtal/core/structure.py` — `add_bond`, `_bond_ids` | **S** | — | no |
| 6a | `optimize.steps` honours `cancel` per evaluation | `xtal/ff/optimize.py` — `steps`, new `_Stoppable` | **M** | — | no |
| 6b | A stopped scan point is a hole | `xtal/ff/scan.py` — `_one_point`, `_prerelaxed` | **S** | — (better after 6a) | no |
| 6c | `build` and `net` check cancellation either side | `xtal/modules/build.py` — `build_molecule`; `xtal/modules/net.py` — `draw_net` | **S** | — | no |
| 7 | `asymmetrize` warns when a looser tolerance finds a larger group | `xtal/core/symmetry.py` — `asymmetrize` | **M** | 2 | no |
| 8a | `start_in_thread` owns the worker and thread from Python | `xtalapp/workers.py` — `start_in_thread`, new `_Run`, `stop_all` | **L** | — | **yes** — § Testing and threads, *"A finished worker thread can deadlock the application"* (with 8b, 8c, after ten clean runs) |
| 8b | The two call sites | `xtalapp/docks/ff_panel.py` (`:726` at `3cd15e2`, **`:732` at `fb38d25`**); `xtalapp/mainwindow.py` — `closeEvent` (`:1807`) | **S** | 8a | — |
| 8c | The `aboutToQuit` / `atexit` reaper | `xtal/modules/process.py` — `ExternalProcess.run`, `_close`, new `atexit`; `xtalapp/application.py` — `Application.__init__` | **S** | 8a | — |

**Totals:** eight S, three M, one L, plus one optional S. The eight S items
are a day between them; Phase 4 and Phase 7 are half a day each because of
their test matrices; Phase 8 is a day, most of it waiting on ten suite runs.
