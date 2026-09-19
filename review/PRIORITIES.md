# What to build, in order

Jules reviewed the deep review on PR #1 (2026-09-19, five inline comments)
and gave a verdict on all 24 feature ideas plus the bug findings. This file
turns that into an ordered plan. His words are quoted; the ordering is the
proposal.

**His blanket verdicts:** *"Good catch, these should be fixed"*
([edge-cases](reports/edge-cases.md)), *"Good suggestions"*
([performance](reports/performance.md), [ui-ux](reports/ui-ux.md)). So the
correctness and NFR findings are accepted as a block; what needed deciding
was the features, and he decided all of them.

---

## The thing the review missed, and he put first

> **16.** "Yes. Pormake is also incapable of generating MFU-4l because
> (1) it is pcu, but every other node is flipped and (2) the SBU doesn't
> connect the linker at a single point. **Fixing this takes precedence**"

This was not in the review at all, and it is the only item he marked as
taking precedence. It matters more than its position in the list suggests:
**MFU-4l is the application's own stress case** — `resources/samples/MFU4l.cif`
is what CLAUDE.md benchmarks with throughout (648 atoms, the 0.05 Å tolerance
story, the Select All → Set Bond Type batch, the 237-subgroup descent), and
the MOF builder cannot construct it. Two concrete defects named:

1. **Flipped nodes on a `pcu` net** — the builder assumes one node
   orientation per vertex; MFU-4l alternates.
2. **An SBU that does not meet its linker at a single point** — the
   connection-point model (`CONNECTION_DISTANCE`, one `X` per attachment)
   assumes a single contact.

Both are in the vendored PORMAKE (`xtal/mof/pormake/`) or the layer over it,
and upstream has neither fixed (its own issues #33, #29, #25 circle the same
area). This is the one item where the app could go past the library it
vendors.

**Proposed first.** Size unknown until the builder is read against those two
statements — that reading is itself the first task.

---

## Tier 1 — correctness, and the cheap wins he said yes to

Everything here is small, and everything has a verdict.

| # | Work | Jules | Size | From |
|--:|---|---|:-:|---|
| 1 | **PORMAKE: flipped nodes + multi-point SBU** so MFU-4l builds | *"takes precedence"* | ? | his §16 |
| 2 | **Quote CIF labels** — a space or `#` corrupts the saved file | *"should be fixed"* | S | [edge §2](reports/edge-cases.md) |
| 3 | **Guard `symprec <= 0`** in the core — `--symprec -1` segfaults | *"should be fixed"* | S | [edge §1](reports/edge-cases.md) |
| 4 | **Coincident-atom warning on open** — `CFA1`/`Ni2Cl2BTDD` are wrong today, and it is also the performance cliff | *"Sure it could"* (1) | S | [edge §3](reports/edge-cases.md), [perf](reports/performance.md) |
| 5 | **`add_bond` O(n²) → set** — 2.10 s off every MFU-4l project open | *"Good suggestions"* | S | [perf](reports/performance.md) |
| 6 | **Worker-thread fix** — 31 segfaults in 45 stress runs; prototype on this branch | *"Yes"* (3) | S | [threads §6](reports/threads.md) |
| 7 | **Stop on a UFF/MACE scan** — `optimize.steps` ignores `cancel=` | *"should be fixed"* | S | [threads §7](reports/threads.md) |
| 8 | **Subgroup warning in `asymmetrize`** — MFU-4l silently becomes Pmmm | *"should be fixed"* | S | [edge §5](reports/edge-cases.md) |

Items 2–8 are all a day or less each and mostly a few lines. Item 6 must
rebase over `fb38d25`, which touched `ff_panel.py`.

## Tier 2 — "Yes we should add", in ascending cost

| # | Work | Jules | Size |
|--:|---|---|:-:|
| 9 | **Formats via `FORMATS`**: mmCIF/PDBx (gemmi is already a dependency), POSCAR/CONTCAR, pymatgen JSON, ASE `.traj` | *"Yes we should add"* (7) | S each |
| 10 | **EQeq / EQeq+C** beside QEq — the Ewald sum is already there | *"Yes we should add"* (6) | S |
| 11 | **More ML potentials as `ENGINES`** — ORB-v3, SevenNet, UMA, eSEN-OAM, MatterSim. MOFSimBench: top uMLIPs hit **89 % volume accuracy against UFF4MOF's 62 %** | *"Yes we should add"* (4) | S each |
| 12 | **Energy units as a preference** (kcal/mol · kJ/mol · eV) | *"Yes we should add"* (22) | M |
| 13 | **Vector export of the 3-D view** (gl2ps) to match PXRD and bands | *"Yes we should add"* (21) | S–M |
| 14 | **MOFid / MOFkey** for naming and dedup | *"Yes"* (13) | S |
| 15 | **OPTIMADE search dialog** | *"Yes"* (11) | M |
| 16 | **Publication renders** — ray-traced / ambient occlusion | *"Yes we should add"* (19) | M |
| 17 | **LAMMPS data export** — reuses the bond graph and UFF typer the app has | *"Yes we should add"* (8) | M |
| 18 | **conda-forge + `CITATION.cff` + Zenodo DOI + JOSS** | *"Yes we should add"* (24) | S–M |
| 19 | **MACE-MP-MOF0 checkpoint** — but it is a phonon/QHA model in tension with #11; it feeds quasi-harmonic F(V,T) better than it feeds relaxation | *"Sure"* (5) | S |
| 20 | **Autosave + crash recovery** | *"could be useful"* (2) | M |

## Tier 3 — yes, but he marked them lower

| Work | Jules |
|---|---|
| Framework force fields (Dreiding, MZHB, ZIFFF) | *"We could add, but lower priority"* (9) |
| Zeo++ channel segmentation, blocking spheres | *"We could add"* (10) |
| Web-shareable 3D / glTF | *"Low priority"* (20) |
| GCMC input generation | *"Any adsorption simulator could be useful, but lower priority"* (18) |
| Code signing | *"Paying $99 is low priority at the moment"* (23) |

## Tier 4 — needs a decision before it can be sized

- **Interpenetration** (14) — *"I am interested, but need more information on
  the implementation"*. The review found no maintained open-source tool
  anywhere; the only published method is a 2016 atom-by-atom collision check.
  **Owed to him: a design note, not code.**
- **Defect generation** (15) — *"could be implemented into the pormake
  feature. But on its own, it would require a definition of what the
  linker/nodes are"*. That definition is exactly what item 1 has to pin down,
  so **this follows the PORMAKE work rather than preceding it**.
- **Structure databases** (12) — *"Depends on licensing and the size of
  databases. A small database of curated MOFs could also be useful. MOF-#,
  NU-#, HKUST-#, etc."* — a bundled curated set is a different, much smaller
  job than a database client, and he would take it. Note this sits against
  his *"tough to implement because of licensing and database sizes"* on the
  competitors list; OPTIMADE (15 above) is the query-only half he said yes to.

## Dropped

- **Post-synthetic functionalisation** (17) — *"Theoretically could be
  useful. But Crystal Builder itself enables this easily"*. He is right; the
  sketcher plus Add hydrogens plus connection points already covers it.

---

## Corrections to the review

Jules named two things the review listed as gaps that are already built:

- **Thermal ellipsoids / disorder display** — *"Does exist in the code under
  Styles"*. The competitors comparison was wrong; it was drawn from
  Mercury's weakness without checking the Style panel.
- **3-D print export** — *"Does exist in the code"* (STL via Blender, which
  the README does document — the condensed competitor note listed it as a
  gap anyway).

And one thing the review proposed that he has deliberately not built:

- **Rietveld / pattern fitting** — *"I haven't implemented 5 yet because I
  need to make sure I get the physics right, I was looking for a published
  package to make a wrapper for."* Not a gap in his awareness; a correctness
  standard he is holding to. If this is ever picked up, the useful
  contribution is **finding him the package to wrap**, not writing the
  refinement.

---

## Suggested first session

1. Read the MOF builder against his two statements about MFU-4l and write
   down what each would take. Produce a plan, not a patch.
2. While that is in hand, land items 2–5 and 7–8 — six small correctness
   fixes, each with a test named in the reports.
3. Item 6 (workers) on its own branch, rebased over `fb38d25`, verified with
   `probes/matrix.sh` before and after, then ten full suite runs.

Items 2–8 together are a day's work and close every `[critical]` and most
`[important]` findings in the review.
