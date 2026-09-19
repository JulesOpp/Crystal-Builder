# The work, in order

> **Written 2026-09-19** against `Crystal-Builder` at `3cd15e2` (v0.2.1),
> the base of `features/deep-review`. `origin/main` is at `fb38d25`, which
> was checked and does **not** conflict with anything here. Sizes below are
> measured, not guessed — every number has a probe under `review/probes/`.
>
> **Supersedes [PRIORITIES.md](PRIORITIES.md)**, which ordered the work
> from Julius's PR verdicts alone, before the design reading was done. The
> reading moved several sizes and killed two items outright.

## How to read this

Julius answered all 24 feature ideas on PR #1 and accepted the correctness
findings as a block. Eight design agents then read the code against those
answers. This file is the result: **one ordered list, with what each item
actually costs.**

Nothing here is committed to. The next step is cutting it down.

---

## Three things the reading found that change the picture

### 1. Interpenetration detection is already built, and he does not know

He said of idea 14: *"I am interested, but need more information on the
implementation."* The implementation is **in his own tree**:

- `xtal/analysis/topology.py:243` — `Net.multiplicity()`, whose docstring
  calls it *"the interpenetration number of a net described in a doubled
  cell"*.
- `Net.components()` splits catenated nets.
- `xtal/analysis/rcsr.py:758` — `_shape()` already **prints**
  `"2-fold interpenetrated"`.
- `tests/test_net_identification.py:268` asserts exactly that string.

The gap is that it only runs on a net the **user draws by hand**. Running
it on the perceived chemistry is ~10 lines of glue, measured at **0.9–57 ms**
across the nine samples, and the periodicity rank separates Ni2Cl2BTDD's 126
solvent molecules from the framework for free.

The literature says the number is right: `multiplicity` = `|det S̃|` (Gao et
al., *npj Comput. Mater.* **6**, 143) = Blatov's PICVR, recovering *Z*ₜ
exactly. **MOFid's catenation count is literally `components − 1` with no
multiplicity term — this app's answer is already better than the field
standard.** Detection **S**. Generation stays **L** and waits behind PORMAKE.

### 2. Three shipped sample files carry CCDC download headers

`resources/samples/MFU4l.cif` says *"downloaded from the CCDC"*, and two
others do too. There is no `PROVENANCE.md` beside them — unlike the vendored
PORMAKE, which has one. CCDC's own published position is that its licence
*"does not allow external sharing of original data from the CSD"*, and these
files ship inside every `.dmg` and `.exe`.

This was not on anyone's list. It is cheap to fix — COD holds all six
headline MOFs under CC0 (verified by download), and regenerating the rest
RASPA2-style with a `_citation_*` block is the community norm. See
[mof-database-licensing.md](design/mof-database-licensing.md).

Also found: **`MIL53.cif` and `UIO66.cif` ship in every build and are
reachable from nowhere in the UI.**

### 3. Nobody has ever built MFU-4l automatically

Searched ToBaCCo, PORMAKE, AuToGraFS, Boyd–Woo, MOFBuilder, pyCOFBuilder and
the hypothetical-MOF literature. No instance; no paper naming it as a hard
case. ToBaCCo's node database has no Kuratowski node at all. If this lands,
it is a first — and it belongs in the release notes.

---

## Phase 0 — his precedence item

**PORMAKE cannot build MFU-4l.** Full diagnosis in
[pormake-mfu4l.md](design/pormake-mfu4l.md), upstream in
[pormake-upstream.md](design/pormake-upstream.md), literature in
[pormake-literature.md](design/pormake-literature.md).

Both his claims reproduce, and they are **one defect**. The two node
orientations score **bit-identically (0.164405 both ways, 24 of 720
permutations tied)** — the objective is *degenerate*, not weak, because the
off-axis nitrogens that make the attachment tridentate are exactly the atoms
that encode orientation. Collapse the end to one `X` and the evidence is
gone.

| # | Work | Size | Notes |
|--:|---|:-:|---|
| 0.1 | **Refuse to claim a topology it did not build.** The build completes and reports *"the framework is pcu, as asked"* while relaxing a cubic net to triclinic 81.0/99.4/100.2°. | **S** | Highest value per line in the whole plan. Independent of everything else. |
| 0.2 | **Per-slot orientation through the existing `permutations=` argument.** `Builder.build` already honours it; `xtal/mof/build.py:338` never passes it because it calls `build_by_type`. A prototype reproduces MFU-4l's checkerboard on `pcu`×2. **No vendored edit.** | **M** | ⚠ The automatic chiral fallback re-flips any slot whose RMSD exceeds the cached type minimum by 1 %. It will fight a pinned assignment unless disabled. |
| 0.3 | **Multi-point connections** (his claim 2, general form). | **L** | Changes the connection-point data model, `LocalStructure`, the Hungarian matching and the bonding step. Not a patch to `locate`. **Defer** — 0.2 gets MFU-4l's topology without it. |

**Open question for Julius, and it decides 0.3:** the catalogue has no
chloride-bearing Kuratowski block and no O₂ edge block. Even with orientation
fixed, MFU-4l's *chemistry* needs a custom block. **Does he want the
structure, or only its topology?** Those are different jobs.

---

## Phase 1 — correctness, all measured

Every item accepted by him already. Full specs in
[tier1-fixes.md](design/tier1-fixes.md).

| # | Work | Size | Measured |
|--:|---|:-:|---|
| 1.1 | **`add_bond` O(n²) → stamp-invalidated set** | **S** | MFU-4l project open **2161.8 → 22.7 ms (95×)**; HKUST-1 86×; MOF-5 53×. Bond lists byte-identical, same order. Invalidate via the existing `_stamp` — `structure.bonds` is replaced wholesale in seven places and only the stamp survives that. |
| 1.2 | **Coincident-atom warning on open, at 0.05 Å** | **S** | 0.6–7.8 ms marginal. Fires on exactly `CFA1` and `Ni2Cl2BTDD`, silent on the other seven. At that tolerance it sees a site duplicated by its **own orbit** — `duplicate_groups`' structural blind spot — so it **closes an open TODO entry** under § Symmetry. Home is `FORMATS.read`/`read_all` + `read_project`, *not* `Document.adopt` (which never sees a structure). |
| 1.3 | **Force field refuses below 1 µÅ** | **S** | Must *refuse* (`CalculatorError`), not warn: `scan.py:549` already turns a refusal into a proper hole, whereas a warning leaves `converged=True, |F|max=0` standing. |
| 1.4 | **Guard `symprec <= 0` in the core** | **S** | Four doors segfault; only **two** need guarding (two others call `detect`). `niggli_reduce`'s `eps` raises cleanly and is not a door. |
| 1.5 | **Quote CIF labels** | **S** | ⚠ **`_quote` is itself broken** — it replaces apostrophes with spaces (`Na'1` → `Na 1`, which round-trips *correctly* today) and misses `data_`/`loop_` prefixes. Fix `_quote` first or this is a regression. Writer-only; the reader already round-trips. CIF-only — CSSR/gen/XYZ/PDB never write labels. |
| 1.6 | **Stop on a UFF/MACE scan** | **S** | Today's dead Stop costs a whole grid point: **3.7 min** on Ni2Cl2BTDD. One step with the cell free is 14.2 evaluations / 106.9 ms, so poll per evaluation. `_one_point` must convert a stop into `_failed(..., "stopped")` or `optimize.run` returns a finite energy for a half-relaxed geometry. |
| 1.7 | **Worker-thread fix** | **S** | 31 failures in 45 stress runs → 0 in 50. `fb38d25` **does not conflict**; the call site moved 726 → 732. Plus the `aboutToQuit`/`atexit` reaper. Verify with `probes/matrix.sh`, then ten full suite runs. |
| 1.8 | **`asymmetrize` subgroup warning** | **S–M** | The prior group is **genuinely unrecoverable** after Reduce to P1 — proved, the `meta` keys are identical. So a tolerance ladder is the only method, not a fallback: `(1e-3, 1e-2, 5e-2)` costs **88.5 ms** on MFU-4l and stops at 0.05 Å because 0.1 Å makes ZIF-8 report Cc. |

**1.1 through 1.7 are a day's work together** and close every `[critical]`
finding in the review.

---

## Phase 2 — registry additions he said yes to

Full sizing in
[registry-and-interpenetration.md](design/registry-and-interpenetration.md).

| # | Work | Size | What the reading changed |
|--:|---|:-:|---|
| 2.1 | **mmCIF/PDBx read** | **S** | **Best value per hour in the plan.** Not a `FORMATS` entry — mmCIF files are `.cif` and dispatch is by suffix, so it is a branch in `read_cif_all`. gemmi is already a hard dependency: a measured **8-line** reader over the existing `_from_small_structure` gets cell, space group, occupancy and ADPs. |
| 2.2 | **Interpenetration detection** | **S** | ~10 lines of glue over code that already exists. See above. |
| 2.3 | **POSCAR/CONTCAR** | **S–M** | Forces a registry change: `Path('POSCAR').suffix` is `''`, and `FORMATS.by_extension('POSCAR')` raises. Needs a `Format.filenames` field. |
| 2.4 | **pymatgen JSON / ASE `.traj`** | **S–M** | `.traj` needs a `Format.available` field (`Format` has no `check`, unlike `Module` and `Engine`) plus a dispatch in `read_trajectory`, which is hard-wired to text. |
| 2.5 | **Shared `ASECalculatorEngine`, then uMLIPs** | **M** + **S** each | **141 of 219 lines in `xtal/ff/mace/calculator.py` are generic** (measured). Does not conflict with [factoring §6](reports/factoring.md) — that is the external-*binary* base; both belong in one `api.py` pass, three levels not two. Licence-first order: **ORB-v3 (Apache-2.0), MatterSim (MIT), SevenNet (MIT)**, then UMA (HuggingFace gate; its MOF task `odac` has **no trained stress head**) and eSEN-OAM (best on the benchmark, **research-use-only weights**). |
| 2.6 | **EQeq** | **M** | Not S. `qeq._solve` is reusable verbatim, but `ewald.py` has no pair-matrix interface — that is the only new numerics. The 484-number table is regenerable from **NIST**, which matters: every EQeq implementation is GPL-2.0 and this project is MIT. Adding entries exposes a **three-copy** charge-source list (engine `Param`, `ff_panel.py:89`, `cli.py:569`) that no test ties together. |
| 2.7 | **EQeq+C** | **S** | A post-hoc additive charge shift that never touches the linear system or the bond graph — ~40 lines. **Blocked**: the parameter table is paywalled. |
| 2.8 | **Curated MOF library + `DATA_LICENSES`** | **S–M** | Fixes finding 2 above. COD (CC0) holds all six headline MOFs, verified. 30 structures ≈ **50–150 KB gzipped**. Strip `_refln` loops (−99.7 % on UiO-66); ship primitive cells for MIL-100/101; ship asymmetric units, not P1 (28× saving). |
| 2.9 | **A MOFkey-shaped identifier of our own** | **S** | **`pip install mofid` does not exist.** It is a CMake build of a vendored Open Babel plus a Java Systre jar, GPL-2.0, with absolute paths baked in by `set_paths.py` — unshippable. Reuse `graph.fragments()` + `rcsr.describe()` + RDKit's InChIKey instead. Integrating MOFid is **L and not recommended**. |
| 2.10 | Energy units preference; vector 3-D export; publication renders; LAMMPS export; conda-forge + Zenodo + JOSS | **M** each | Unchanged from [PRIORITIES.md](PRIORITIES.md); no design work done. |

---

## Decisions that gate work

Nine items wait on six answers. These are the brainstorming agenda.

1. **MFU-4l: structure or topology?** Gates 0.3 (**L**). The catalogue has no
   Kuratowski block.
2. **MACE-MP-MOF0 — still want it?** It is *not* the MOF winner: **28 of 100
   structures unsupported**, and it is a phonon/QHA model. It feeds idea 26
   (quasi-harmonic F(V,T)) better than it feeds relaxation.
3. **Which uMLIPs, given the licences?** Two of the five best have
   research-use-only or gated weights.
4. **EQeq+C** — worth paying for the paywalled table, or ship EQeq alone?
5. **Curated library** — replace the CCDC-headed samples, or add beside them?
   And does `MIL53`/`UIO66` shipping-but-unreachable get fixed here?
6. **Is the shared `ASECalculatorEngine` a prerequisite or a follow-up?**
   Doing it first makes each uMLIP ~100 lines; doing it after means five
   copies to collapse.

---

## What I would cut

Offered as a starting position for the cut-down, not a recommendation he
has agreed to:

- **Cut 0.3** (multi-point connections, **L**) until question 1 is answered.
  0.2 gets the topology.
- **Cut 2.7** (EQeq+C) — blocked on a paywall for a ~40-line addition.
- **Cut 2.9** unless naming is wanted for its own sake.
- **Defer all of 2.10** — five **M** items with no design work behind them.
- **Keep 0.1, and all of Phase 1.** Together that is about two days, closes
  every critical finding, makes the builder stop lying about topology, and
  takes 2.1 seconds off every project open.

Phase 1 plus 0.1 plus 2.1 and 2.2 is the highest-value slice in the
document: **roughly three days, and every item is measured.**
