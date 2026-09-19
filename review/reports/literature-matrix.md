# Literature triage matrix — the papers the feature ideas rest on

Ten papers (eleven rows; EQeq is two). Every year, venue, volume and DOI
below was re-verified against Crossref or the publisher, not copied from
`reports/research.md`. **Four citations in the research report are wrong or
mis-attributed and two headline numbers are mis-stated** — the details are
in the per-paper blocks and the corrections are collected at the end.

The short version: the *validation* case (REVIEW §7 idea 1) is solid but
rests on fewer independent sources than the report implies and its biggest
error class is not geometric; the *MLIP* case (ideas 4 and 5) is close to
inverted — MOFSimBench does not say what the report says it says, and
MACE-MP-MOF0's "10× more accurate" is a misreading of a sentence that runs
the other way; the *LAMMPS export* case (idea 8) is the best-supported
idea in §7 and its paper even supplies the accuracy envelope to quote.

---

## The matrix

Columns are the skill's nine defaults, with two customised as asked:
**Relevance** = to a *Crystal Builder* decision; **Use as** = the numbered
idea in [REVIEW.md §7](../REVIEW.md) it informs.

| Citation | Question | Method | Data / study area | Main claim | Evidence | Limitation | Relevance (to a CB decision) | Use as (REVIEW §7) |
|---|---|---|---|---|---|---|---|---|
| **Kraß, Huang & Moosavi 2026** — MOFSimBench, *npj Comput. Mater.* **12**, 4 (online 11 Dec 2025; issue 2026), [10.1038/s41524-025-01872-3](https://doi.org/10.1038/s41524-025-01872-3), arXiv:2507.11806 | Are universal MLIPs usable for nanoporous-material modelling? | Benchmark of 21 uMLIPs on 4 tasks: relaxation, NpT MD stability, bulk modulus + heat capacity, host–guest forces | 100 structures (83 MOF, 7 COF, 10 zeolite) + 231 for C_p + 26 GoldDAC MOFs / 312 host–guest configs | Top uMLIPs beat classical force fields **and** fine-tuned MLIPs on every task; they are "ready for deployment" | Simulation benchmark vs DFT references | Ranking is model-generation-specific and already shifting; **no evaluation of charge-dependent properties or of breathing/flexibility**; all models need D3 | **High** — it is the evidence for/against ideas 4 and 5, and it contradicts the report's reading | **4** (more `ENGINES`), **5** (MOF checkpoint) |
| **Elena, Kamath, Jaffrelot Inizan, Rosen, Zanca & Persson 2025** — MACE-MP-MOF0, *npj Comput. Mater.* **11**, 125, [10.1038/s41524-025-01611-8](https://doi.org/10.1038/s41524-025-01611-8), arXiv:2412.02877 | Can a small MOF fine-tune make MACE usable for phonons in MOFs? | Multi-head fine-tune of MACE-MP-0b (medium) on PBE+D3(BJ); QHA phonon workflow | 127 curated MOFs, 4 764 DFT points; validated on MOF-5, UiO-66, MOF-74, MIL-53 + 70 unseen MOFs | Fine-tuning fixes MACE-MP-0's imaginary phonon modes and gives DFT-level bulk moduli and thermal expansion | Simulation vs DFT and experiment | Out-of-sample RMSDs are ~10× in-sample; Cu and Ti under-represented; QHA misses anharmonicity; covers ~60 % of QMOF chemistry | **High** — and it is *the* citation for idea 26 (QHA) too, which the report never connects | **5** (checkpoint), **26** (quasi-harmonic F(V,T)) |
| **Jin, Jablonka, Moubarak, Li & Smit 2025** — MOFChecker, *Digital Discovery* **4**(6), 1560–1569, [10.1039/d5dd00109a](https://doi.org/10.1039/d5dd00109a), PMC12091091 | Can MOF CIFs be validated *and repaired* automatically? | Rule-based geometry checks + OxiMACHINE ML oxidation states + Monte-Carlo counter-ion insertion | CoRE2014, CSD MOF subset, QMOF, an in-silico set (~1 300) | 38.0 % of CoRE2014 fails at least one criterion (11.8 % geometric, **32.5 % charge**); 35.3 % of the CSD MOF collection | Empirical audit of published databases + tool validation (97.5 % TPR) | The dominant failure mode is charge/oxidation state, not geometry; OxiMACHINE slips on variable-valence metals (Co, Mn); carbon anions not considered | **High** — it both motivates idea 1 and bounds what a geometry-only panel can deliver | **1** (validate on open) |
| **White, Gibaldi, Burner, Mayo & Woo 2025** — MOSAEC, *JACS* **147**(21), 17579–17583, [10.1021/jacs.5c04914](https://doi.org/10.1021/jacs.5c04914) | How many "computation-ready" MOF structures are chemically invalid? | MOSAEC: metal-oxidation-state validity algorithm, manually validated | 14 databases, >1.9 M structures; 14 796 hand-checked CoRE structures; 8 published HTS campaigns | Error rates >40 % in most databases; **52 % of top HTS candidates are chemically invalid** | Empirical audit + algorithm validation (96 % flagging accuracy) | Oxidation-state rules only — it detects chemical invalidity, not geometric damage; a 4-page communication, method detail is in the SI | **High** — the strongest single number behind idea 1 | **1** |
| **Chung & Lah 2026** — "Hunting Structural Demons…", *Israel J. Chem.* **66**(4), e70028, [10.1002/ijch.70028](https://doi.org/10.1002/ijch.70028), arXiv:2603.26295 | Where do invalid MOF structures come from, how are they found, how are they prevented? | **Mini-review** — no new data | The existing literature (incl. MOSAEC and MOFChecker) | Structural "demons" enter at conversion and at generation; a three-part prevention strategy (keep diffraction+synthesis data together, curate consistently on entry, filter topologies before generation) | Review | Reports **no primary results**; its >half figure is White 2025's 52 %, restated | **Low** — cite it as a framing reference; it is not independent corroboration | **1** (citation only) |
| **Martin-Noble, Reilley, Rivas, Smith & Schrier 2015** — EQeq+C, *JCTC* **11**(7), 3364–3374, [10.1021/acs.jctc.5b00037](https://doi.org/10.1021/acs.jctc.5b00037) | Can EQeq's bad metal charges be fixed without iteration? | Non-iterative empirical pairwise correction from the Pauling bond-order/distance relation, on top of Wilmer's EQeq | Molecular + periodic test sets (full set not reached — abstract only) | The correction "fixes the metal charge problem" and materially improves partial charges vs EQeq | Empirical/comparative against reference charges | Empirical correction, not a physical model; **not a Wilmer-group paper** (Haverford — Schrier) | **Medium** — it says the cheap method is fixable, not that it is trustworthy | **6** (EQeq/EQeq+C beside QEq) |
| **Ongari, Boyd, Kadioglu, Mace, Keskin & Smit 2019** — "Evaluating Charge Equilibration Methods…", *JCTC* **15**(1), 382–401, [10.1021/acs.jctc.8b00669](https://doi.org/10.1021/acs.jctc.8b00669) | Are Qeq-family charges good enough to screen with? | Henry's-law constants for CO₂, H₂O, N₂ with EQeq vs DDEC charges; Spearman rank correlation | CoRE MOF database | EQeq reproduces screening *trends* but reorders the leaders: only **8 of the top 15** MOFs are the same under EQeq and DDEC for CO₂/H₂O selectivity | Simulation comparison against DFT-derived (DDEC) reference | Rank disagreement ≠ validated false positives; one property family (polar-guest electrostatics), one database | **High** — it is the warning text that should ship *with* idea 6 | **6** |
| **Boyd, Moosavi, Witman & Smit 2017** — *J. Phys. Chem. Lett.* **8**(2), 357–363, [10.1021/acs.jpclett.6b02532](https://doi.org/10.1021/acs.jpclett.6b02532) | How well do generic and MOF-specific force fields predict MOF bulk properties? | MD/lattice-dynamics comparison of UFF, DREIDING, UFF4MOF, BTW-FF, DWES | IRMOF-1 (MOF-5), IRMOF-10, HKUST-1, UiO-66 | UFF and DREIDING give "surprisingly" good bulk moduli and linear thermal expansion; UFF4MOF/BTW-FF/DWES also accurate | Simulation vs DFT/experiment | "Noticeable deviations" for properties sensitive to **framework vibrational modes**, "more pronounced upon the introduction of framework charges" | **High** — this is the citation `lammps-interface` asks users to give, and it is CB's own accuracy envelope for UFF4MOF | **8** (LAMMPS export), **9** (more FFs), **26** |
| **Li & Ahlquist 2026** — MOFBuilder, *npj Comput. Mater.* **12**, 156 (online 17 Apr 2026), [10.1038/s41524-026-02086-x](https://doi.org/10.1038/s41524-026-02086-x) | Can MD-ready MOF models be built end to end without manual preparation? | Modular pipeline: molecular-identity assignment → topology/bonding → residues → FF params → periodic/**defective**/cluster/slab models | Functionalised UiO-66 variants; bio-hybrid interfaces | Static porosity analysis is misleading — several UiO-66 variants scored non-porous take up CO₂ by gate-opening, visible only in MD ("Porosity Paradox") | Simulation (pipeline demonstration + MD case study) | Full text not reached (abstract-level only); targets **GROMACS/OpenMM**, not LAMMPS; the report's "missing-linker defects within seconds" phrasing is **unverified** (`?`) | **Medium** — its headline result argues for MD, not for a defect generator | **15** (defects); indirectly **8** |
| **Park, Li & Lee 2025** — PSYMOF, *npj Comput. Mater.* **12**, 17 (online 5 Dec 2025), [10.1038/s41524-025-01888-9](https://doi.org/10.1038/s41524-025-01888-9) | Can post-synthetic modification be treated as a tunable design variable? | Cheminformatics + sterically aware random-walk functional-group growth + PACMOF charges + LAMMPS MD relaxation | Case study: UiO-66-NH₂ partially functionalised, CO₂/N₂ separation | Adsorption performance is **non-monotonic** in functionalisation level — an optimum trades CO₂ affinity against pore accessibility | Simulation, single framework family | Full text not reached (abstract-level only); one case study; no experimental validation; a library, not an interactive tool | **Medium** — it names exactly the pipeline an idea-17 feature would need (grow → charge → retype → relax) | **17** (post-synthetic functionalisation) |
| **Ran, Sharma, Balestra, Li, Calero, Vlugt, Snurr & Dubbeldam 2024** — RASPA3, *J. Chem. Phys.* **161**(11), 114106, [10.1063/5.0226249](https://doi.org/10.1063/5.0226249) | What changed in the ground-up C++23 rewrite of RASPA? | Software paper + methodological comparison of four MC insertion/deletion schemes (Metropolis, CBMC, CFCMC, CB/CFCMC) | Grand-canonical and Gibbs-ensemble isotherms over a range of loadings and systems | RASPA3 adds transition-matrix MC, quaternion rigid-body MC, and analytic dU/dλ for fractional molecules; MIT-licensed | Simulation / software | Says **nothing** about input preparation, GUIs, or CIF-to-input friction — the case for idea 18 rests on issue trackers and glue scripts, not on this paper; JSON input, pybind11 Python interface | **Low** — it establishes the target exists and is alive; it does not argue the feature | **18** (GCMC input generation) |

Depth reached: full text for **MOFSimBench**, **MACE-MP-MOF0** (arXiv HTML)
and **MOFChecker** (PMC); publisher PDF front matter + abstract for
**RASPA3**; author-posted abstract for **Boyd 2017**; arXiv abstract for
**Hunting Structural Demons**. **Abstract/metadata only** for PSYMOF,
MOFBuilder, the JACS communication, EQeq+C and Ongari 2019 — ACS, Wiley,
Research Square and nature.com all refused the fetch. Rows are marked
accordingly and nothing in them is extrapolated past what was read.

---

## Per-paper blocks

### 1. MOFSimBench — Kraß, Huang & Moosavi, *npj Comput. Mater.* 12, 4 (2026)

**Key Findings**
- 21 uMLIPs evaluated (9 in the main text, the rest in SI), not five.
  **CHGNet and M3GNet do not appear** in the evaluated set; the models are
  MACE-MP-0a/0b3/MPA-0, MACE-OMAT-0, eSEN-OAM, orb-v3-omat, orb-d3-v2,
  MatterSim-v1, SevenNet-ompa, eqV2-OMsA, GRACE-2L-OMAT and relatives,
  with MACE-MP-MOF0 as a fine-tuned baseline.
- Structural optimisation: eSEN-OAM and orb-v3-omat land within ±10 % of
  the DFT volume for **89 %** of structures; **UFF4MOF manages 62 %**;
  orb-d3-v2 only 39 %, and eqV2-OMsA fails to converge on 96 %.
- Bulk modulus (100 structures): eSEN-OAM MAE **2.64 GPa** (MAPE 22.1 %);
  MACE-MP-MOF0 3.14 GPa; orb-d3-v2 72.29 GPa. Heat capacity (231
  structures): orb-v3-omat MAE **0.018 J/K/g** (2.3 %), MACE-MP-0a
  0.082, orb-d3-v2 0.175. Every model over-estimates C_p.
- Host–guest (GoldDAC, 312 configs): MatterSim and eSEN-OAM beat both the
  *fine-tuned* MACE-DAC-1 and classical UFF+DDEC-with-DFT-charges.
- MACE-MP-MOF0 ran on only **72 of the 100** benchmark structures (28
  unsupported elements) and "does not outperform the top-performing
  universal models" on coordination stability.

**Methodology** A four-task benchmark (relaxation, 50 ps NpT MD stability,
bulk modulus + heat capacity, host–guest forces) over a 100-structure set
stratified by largest pore diameter, scored against DFT references.

**Relevance to Crystal Builder** It is the only evidence in §7 for which
`ENGINES` entries are worth adding, and it names them: eSEN-OAM,
orb-v3-omat and MatterSim-v1 are the three that are good at everything.
It equally names two that would embarrass the app if offered as defaults.

**What the research report claimed vs what the paper says**
- *Claimed* (research.md §2; REVIEW §7 idea 4): "benchmarks MACE-MP,
  CHGNet, M3GNet, ORB and SevenNet on MOFs and finds all of them struggle
  with charge-dependent properties and breathing/flexibility — none is
  uniformly reliable, which argues for offering several rather than
  picking a winner."
- *Paper*: the abstract's conclusion is the opposite in tone — "top-performing
  uMLIPs consistently outperform classical force fields and fine-tuned
  machine learning potentials across all tasks, demonstrating their
  readiness for deployment." Two models are consistently top across all
  four tasks. The paper **does not evaluate charge-dependent properties**
  (it notes classical models need DDEC or Qeq charges, and leaves it
  there) and **does not isolate breathing/flexible frameworks** at all;
  MD stability is a global measure. CHGNet and M3GNet were not tested.
- *Net*: the "offer several because none wins" argument is not in this
  paper. A defensible argument survives — the spread between best and
  worst is enormous (89 % vs 39 %), the ranking turns over between model
  generations, and the paper's own stated gap is that uMLIPs need to be
  *integrated into simulation packages* — which is precisely what an
  `ENGINES` entry is. That argument is about **choosing well and making
  swapping cheap**, not about shipping everything.

### 2. MACE-MP-MOF0 — Elena et al., *npj Comput. Mater.* 11, 125 (2025)

**Key Findings**
- Fine-tuned from **MACE-MP-0b (medium)** on 127 MOFs / **4 764** PBE+D3(BJ)
  data points (19 prototypical + 108 from QMOF).
- In-sample test errors: **1.4 meV/atom** energy, **0.014 eV/Å** forces,
  0.2 meV/Å³ stress.
- Out-of-sample (70 unseen MOFs): energy error **0.773 eV vs 3.543 eV**
  for MACE-MP-0b (≈4.6×), forces ≈**30 %** better, and the paper states
  plainly that out-of-sample RMSDs are "10 times the RMSDs" seen on the
  curated set — i.e. **10× *worse*, not 10× better**.
- Lattice parameters within **1.02 %** of DFT (MACE-MP-0b: ~10 %). Element-wise
  energy MAE down 80 % vs MACE-MP-0b; 50 % for Zn/Al/Mg frameworks.
- Fixes MACE-MP-0's spurious imaginary phonon modes; reproduces negative
  thermal expansion (MOF-5 −6.65×10⁻⁶ K⁻¹ vs −3.5×10⁻⁶ K⁻¹ DFT).

**Methodology** Multi-head fine-tune of a foundation MACE model on a
curated DFT dataset, then a quasi-harmonic phonon workflow validated on
MOF-5, UiO-66, MOF-74 and MIL-53.

**Relevance to Crystal Builder** Two things at once: it is idea 5's paper,
and it is a worked implementation of idea 26 (quasi-harmonic F(V,T)) on
exactly the framework class the app targets — including MIL-53, the app's
own scan example. If Jules ever wants idea 26, this is the reference
workflow and this checkpoint is the engine it was demonstrated with.

**What the research report claimed vs what the paper says**
- *Claimed* (research.md §2; research-parts/mof-workflows.md; REVIEW §7
  idea 5): "MOF fine-tune of MACE-MP-0b over 127 curated MOFs, **10× more
  accurate on geometry/forces/stress** than the general-purpose
  checkpoint."
- *Paper*: no such claim. Forces improve ~30 %; energies ~4.6× on unseen
  MOFs; lattice constants ~10× closer (1.02 % vs ~10 %) — so "10×" is
  true of *lattice parameters* alone. The literal phrase "10 times the
  RMSDs" in the paper describes its **transferability penalty**.
- Neither document carries a citation for it. It is Elena et al., *npj
  Comput. Mater.* **11**, 125 (2025), 10.1038/s41524-025-01611-8
  (arXiv:2412.02877, Dec 2024) — and it is a **phonon** paper, not a
  general-purpose-accuracy paper.
- Ideas 4 and 5 are in tension and neither document says so: MOFSimBench
  finds MACE-MP-MOF0 covers only 72/100 of its set and is now matched or
  beaten by current general models.

### 3. MOFChecker — Jin, Jablonka, Moubarak, Li & Smit, *Digital Discovery* 4(6), 1560 (2025)

**Key Findings**
- CoRE2014: **11.8 %** fail geometric checks, **32.5 %** fail charge
  checks, **38.0 %** fail at least one. CSD MOF collection: 11.5 % /
  31.5 % / **35.3 %**. QMOF mostly passes. An in-silico set of ~1 300: 38 %.
- Geometric checks: atomic overlaps, porosity, 3-D connectivity, element
  presence, over-/under-coordinated C/N/H, isolated free molecules,
  suspicious terminal oxygens.
- Charge checks: metal oxidation state via **OxiMACHINE**, counter-cation
  and anion identification, net-charge neutrality.
- It **corrects** as well as flags: deletes duplicates, adds missing H,
  inserts missing counter-ions by Monte Carlo, adds missing charged linkers.
- Validation: 97.5 % true-positive rate, 8 % false negatives.

**Methodology** A rule-based geometric checker combined with a pre-trained
ML oxidation-state model, run over four public MOF databases.

**Relevance to Crystal Builder** It is the specification for idea 1 — and
the proportion split is the decision-relevant fact: a panel that checks
only geometry addresses roughly a third of what MOFChecker catches.

**What the research report claimed vs what the paper says**
- *Venue wrong*: research.md says "RSC Digital Discovery **2023/2025**".
  There is one paper: *Digital Discovery* **2025**, 4(6), 1560–1569,
  10.1039/d5dd00109a.
- *Double counting*: research.md cites "38 % of CoRE MOF 2014 structures
  carry significant errors" and "mofchecker … is the one maintained
  validation tool" as if they were two findings. **The 38 % is
  MOFChecker's own number.** REVIEW §7 idea 1 inherits the impression of
  two independent sources.
- *Under-stated*: the report says MOFChecker validates; it also repairs,
  which is the harder and more interesting half for a desktop app.
- The report's framing of the problem as a CIF/geometry problem is at odds
  with the paper's own numbers — charge failures outnumber geometric ones
  roughly 3:1.

### 4. MOSAEC — White, Gibaldi, Burner, Mayo & Woo, *JACS* 147(21), 17579 (2025)

**Key Findings**
- 14 experimental and hypothetical MOF databases, **>1.9 million**
  structures; structural error rates **exceeding 40 % in most**.
- Across 8 recent high-throughput-screening studies, **52 %** of the
  highlighted top-performing candidates are chemically invalid.
- MOSAEC flags erroneous structures with **96 %** accuracy, validated by
  hand against **14 796** CoRE structures.
- The detection signal is metal oxidation state — chemically implausible
  oxidation states betray structures that look geometrically fine.

**Methodology** An oxidation-state-based validity algorithm applied across
14 databases, manually validated on a large CoRE subset.

**Relevance to Crystal Builder** It is the headline number for idea 1, and
it is a communication with an algorithm behind it — the check is
implementable, not just an indictment.

**What the research report claimed vs what the paper says**
- The ">40 % across 14 databases and 1.9 M structures" figure is
  **accurate**.
- *Mis-attributed*: research.md and REVIEW §7 idea 1 both credit "over
  half of top screening candidates are structurally wrong" to the Israel
  J. Chem. 2026 paper. **It originates here** (52 %, from 8 HTS studies);
  the 2026 mini-review restates it. As written, one finding is presented
  as two sources agreeing.
- The DOI was absent from the report. It is **10.1021/jacs.5c04914**;
  authors are the Woo group at Ottawa, not a group named anywhere in the
  report.

### 5. "Hunting Structural Demons" — Chung & Lah, *Israel J. Chem.* 66(4), e70028 (2026)

**Key Findings**
- A **mini-review**. It contributes no new measurements.
- Coins "structural demons" for chemically invalid models, and separates
  their two origins: bad conversion of disordered/incomplete experimental
  models, and implausible oxidation states/coordination/charge in
  hypothetical structures.
- Its >50 % figure is White 2025's 52 %.
- Prevention is three steps: keep diffraction data with synthesis details
  from the start, curate consistently at database entry, filter topology
  choices *before* structure generation.
- arXiv:2603.26295 (27 Mar 2026) is the same work; the brief's ID checks out.

**Methodology** Literature mini-review of error sources, detection methods
(rule-based through ML classifiers) and prevention.

**Relevance to Crystal Builder** Low as evidence, useful as framing: its
third prevention step — filter topologies before generation — lands on the
MOF builder rather than on the importer, which is a place none of §7's
ideas currently point.

**What the research report claimed vs what the paper says**
- *Claimed*: "a 2026 *Israel Journal of Chemistry* paper titled 'Hunting
  Structural Demons' **reports** over half of top-performing
  high-throughput screening candidates contain structural errors."
- *Paper*: it **cites** that, it does not report it. Using it alongside
  the JACS paper inflates the apparent weight of evidence behind idea 1.
  The evidence is still strong — it is just one audit, not two.
- Venue detail: vol. 66, issue 4, article e70028, online 21 May 2026.

### 6. EQeq+C — Martin-Noble, Reilley, Rivas, Smith & Schrier, *JCTC* 11(7), 3364 (2015)

**Key Findings**  *(abstract and metadata only — ACS refused the fetch)*
- A **non-iterative empirical pairwise correction** built on the Pauling
  bond-order/distance relationship, layered on EQeq.
- It "fixes the metal charge problem" and significantly improves partial
  atomic charges relative to EQeq.
- Being non-iterative, it keeps EQeq's cost profile — the reason the
  method is attractive beside a QEq that must be solved.
- `?` — the size of the validation set, the reference charges used and the
  error reduction achieved were not reachable.

**Methodology** An empirical bond-order correction term added to extended
charge equilibration, benchmarked against reference partial charges.

**Relevance to Crystal Builder** Idea 6 is "EQeq / EQeq+C beside QEq". This
paper establishes that plain EQeq's metal charges are known-bad and that
the fix is arithmetic, not a new solver — which is what makes the idea an
**S**.

**What the research report claimed vs what the paper says**
- *Mis-attributed*: the brief (and the report's framing) call this "the
  Wilmer group". It is **Schrier's group at Haverford College**. Wilmer's
  paper is the *original* EQeq — Wilmer, Kim & Snurr, *J. Phys. Chem.
  Lett.* **3**(17), 2506–2511 (2012), 10.1021/jz3008485 — which the report
  names but never cites. If Jules implements idea 6, both belong in the
  about box.
- *Slightly off mechanism*: research.md says EQeq+C "corrects
  high-oxidation-state transition-metal charges". The correction is
  **bond-order-based**, not oxidation-state-based; the *symptom* it treats
  is implausible metal charges. Worth keeping straight, because idea 1's
  oxidation-state checks and idea 6's charge correction are not the same
  machinery and the report's wording invites conflating them.

### 7. Ongari, Boyd, Kadioglu, Mace, Keskin & Smit, *JCTC* 15(1), 382 (2019)

**Key Findings**  *(abstract-level; full text behind ACS)*
- Compares **EQeq** against **DDEC** (DFT-derived) charges by computing
  Henry's-law constants for CO₂, H₂O and N₂ over the CoRE MOF database.
- On CO₂/H₂O selectivity ranking, **8 of the top 15** MOFs are the same
  under both charge schemes.
- Qeq-family charges cost a small fraction of DDEC, which is what makes
  screening thousands of frameworks feasible at all.
- `?` — the Spearman coefficients themselves, and the per-gas breakdown,
  were not reachable.

**Methodology** Large-scale GCMC/Henry-coefficient screening run twice,
once with each charge scheme, compared by rank correlation.

**Relevance to Crystal Builder** This is the sentence that should appear in
the app if idea 6 ships: fast charges move the leaderboard. It is the
difference between offering EQeq as a convenience and offering it as an
answer.

**What the research report claimed vs what the paper says**
- *Claimed* (research.md §2 and research-parts/mof-workflows.md): "a 2019
  *JCTC* comparison found EQeq screening produces **7/15 false positives**
  against DDEC reference charges."
- *Paper*: the reported statistic is that **8 of the top 15 are identical**
  — i.e. 7 of 15 *differ in membership of a top-15 ranking*. Rank
  disagreement against a proxy reference is not a false-positive rate, and
  DDEC is itself an approximation rather than ground truth. Directionally
  the report's point stands; the number as phrased would not survive Jules
  reading the paper.
- Citation detail the report omits: *JCTC* **15**(1), 382–401 (2019),
  Ongari *et al.* — the same Boyd and Smit as the UFF4MOF paper below.

### 8. Boyd, Moosavi, Witman & Smit, *J. Phys. Chem. Lett.* 8(2), 357 (2017)

**Key Findings**
- UFF and DREIDING give, "surprisingly", good bulk moduli and linear
  thermal expansion coefficients for IRMOF-1 (MOF-5), IRMOF-10, HKUST-1
  and UiO-66 — excluding species they are not parameterised for.
- MOF-specific force fields — **UFF4MOF**, BTW-FF, DWES — are also accurate
  for these properties.
- Each force field gives "a moderately good picture" of bulk properties,
  but **noticeable deviations appear for properties sensitive to framework
  vibrational modes**.
- Those deviations become **more pronounced once framework charges are
  introduced** — the direct caveat on any charge-assignment feature (idea 6)
  feeding an FF calculation.
- `lammps-interface` (Boyd's own code) asks users to cite this paper; it
  takes CIFs in **P1 only**, ships UFF typing, and its README states it is
  "currently unmaintained".

**Methodology** Force-field molecular simulation of bulk mechanical and
thermal properties across five force fields and four well-studied MOFs,
compared against DFT and experiment.

**Relevance to Crystal Builder** The app already has the bond graph and the
UFF4MOF typer that `lammps-interface` exists to reconstruct. This paper is
both the citation a LAMMPS export would carry and the statement of what
that export is good for: bulk moduli and thermal expansion yes; anything
vibrational, and especially anything vibrational with charges on, with
care.

**What the research report claimed vs what the paper says**
- The report never cites this paper at all — it cites the *tool*
  (`lammps-interface`, its issue #61 and #70) and infers the opportunity
  from maintenance status. Both true, but idea 8 currently has a
  maintenance argument and no accuracy argument; this paper supplies the
  accuracy argument, and its caveat.
- The report's claim that `lammps-interface` "requires a P1 cell" is
  **confirmed** by the README.
- research-parts/standards-expectations-distribution.md calls
  lammps-interface "the MOF standard (UFF4MOF!)". The README as fetched
  mentions UFF parameters only; UFF4MOF support is claimed in the paper's
  orbit rather than in the README text reached here — mark `?` until
  someone checks the source.

### 9. MOFBuilder — Li & Ahlquist, *npj Comput. Mater.* 12, 156 (2026)

**Key Findings**  *(abstract-level; Research Square and nature.com both refused the fetch)*
- A modular pipeline that turns a CIF, which "lack[s] explicit molecular
  topology, residue definitions, and chemically consistent bonding", into
  an MD-ready model — supporting **periodic, defective, cluster and slab**
  representations.
- The headline scientific result is a **"Porosity Paradox"**: several
  functionalised UiO-66 variants classified as non-porous by static
  analysis show significant CO₂ uptake by **gate-opening**, visible only
  in MD.
- Targets **GROMACS and OpenMM** (GRO output, an OpenMM setup class);
  LAMMPS is not among the documented outputs.
- Also emits XYZ, CIF and PDB; templates come from a bundled topology
  library.
- `?` — defect *fraction* control, the "within seconds" timing, and any
  limitations section could not be verified.

**Methodology** Software pipeline paper with an MD case study on
functionalised UiO-66 variants.

**Relevance to Crystal Builder** Idea 15 (missing-linker/-node defects)
cites it, and the defect capability is real. But the paper's actual
argument — static porosity screening misleads, you need dynamics — points
somewhere else in the app entirely: at the Zeo++ module's numbers and at
the relaxed-scan machinery, not at the builder.

**What the research report claimed vs what the paper says**
- *Claimed*: "generates MD-ready models with **systematic missing-linker
  defects 'within seconds'**, aimed at high-throughput screening."
  The quoted phrase "within seconds" and the specific "missing-linker"
  framing could not be found in anything reachable; the abstract says
  "periodic, defective, cluster, and slab". Treat the quote as
  **unverified** until someone opens the PDF.
- *Citation*: the report gives no year beyond "2026"; it is vol. 12,
  article 156, online 17 April 2026, Chenxi Li & Mårten S. G. Ahlquist.
- *Omitted*: the gate-opening/"Porosity Paradox" result — the most
  Crystal-Builder-relevant thing in the paper — appears in neither
  research.md nor REVIEW §7.

### 10. PSYMOF — Park, Li & Lee, *npj Comput. Mater.* 12, 17 (2025/2026)

**Key Findings**  *(abstract-level; nature.com and ChemRxiv both refused the fetch)*
- Treats post-synthetic modification as a **tunable design variable**:
  attach functional groups at user-defined substitution levels across
  predefined bonding sites.
- Pipeline: cheminformatics site selection → **sterically aware
  random-walk** group growth → bonding analysis → **PACMOF** partial
  charges → **LAMMPS** MD relaxation.
- Case study: partially functionalised **UiO-66-NH₂** for CO₂/N₂
  separation.
- Result: adsorption performance is **non-monotonic** in functionalisation
  level — an optimum where CO₂ affinity and pore accessibility trade off.
- Stated motivation is the manual process: "manual structure editing,
  chemical intuition, and expertise in force field parameterization".
- `?` — the selectivity and uptake numbers, the number of groups screened,
  and the limitations section were not reachable.

**Methodology** A modular Python workflow (growth + charges + MD)
demonstrated on one framework family.

**Relevance to Crystal Builder** Idea 17's shape comes straight from here,
and the four stages map onto machinery the app has or half-has: site
marking (connection points), growth (Add hydrogens / SMILES builder),
charges (QEq, or idea 6), relaxation (UFF/MACE). The gap is the growth
algorithm and the substitution-level bookkeeping.

**What the research report claimed vs what the paper says**
- The description in research.md ("bonding-site selection, functional-group
  growth at reactive sites, force-field assignment, partial charges and MD
  relaxation") **matches** the published description well. No correction.
- Two things to add: the charges are **PACMOF** (an ML charge predictor,
  not a Qeq variant — a third option beside ideas 6 and 1), and the
  evidence base is **one case study on one framework family**, which is
  thin ground for an **L**-sized feature.
- Dating: online 5 Dec 2025, but it carries vol. 12, art. 17 with a 2026
  print issue. Calling it "npj Comp. Mater. 2025" is defensible; the
  citation should carry both.

---

## What this changes about the feature ideas

One line per §7 idea that rests on one of these papers.

- **Idea 1 — validate on open.** *Supported, with a caveat.* The error
  rates are real and verified (MOFChecker 38 %/35.3 %; MOSAEC >40 % over
  1.9 M structures; 52 % of top HTS candidates). But it rests on **two**
  audits, not four — the Israel J. Chem. review and the "38 % of CoRE2014"
  line are restatements of the other two — and **roughly three-quarters of
  what MOFChecker catches is charge/oxidation-state, not geometry**. The
  **S** first step (coincident atoms on open) is still worth doing and
  fixes a bug this review found; it should not be sold as addressing the
  38 %.
- **Idea 4 — more ML potentials as `ENGINES` entries.** *Supported, but
  not by the stated reason.* MOFSimBench does not say "none is uniformly
  reliable"; it says the top models beat classical force fields and
  fine-tuned MLIPs on every task and are ready to deploy. Rewrite the
  pitch: add **eSEN-OAM, orb-v3-omat and MatterSim-v1** because they are
  measurably the best on MOFs (89 % volume accuracy vs UFF4MOF's 62 %),
  and make the seam cheap because the ranking turns over every model
  generation — not because the field is undecided.
- **Idea 5 — MACE-MP-MOF0 checkpoint.** *Supported with a significant
  caveat.* The "10× more accurate on geometry/forces/stress" number is
  wrong (forces ~30 %, energies ~4.6×, lattice constants ~10×), and
  MOFSimBench — the same benchmark idea 4 leans on — finds MACE-MP-MOF0
  now matched or beaten by general models and unable to run on 28 % of a
  representative MOF set. Ship it as a **phonon/QHA-oriented option**,
  which is what its paper is actually about, not as the accurate default.
- **Idea 6 — EQeq/EQeq+C beside QEq.** *Supported with a caveat, and the
  attribution needs fixing.* EQeq+C is Schrier's, not Wilmer's; Wilmer's
  is the 2012 original. Ongari 2019's number is "8 of the top 15 agree",
  not "7/15 false positives". Ship it with that sentence visible: fast
  charges reproduce trends and reorder leaders.
- **Idea 8 — LAMMPS data export.** *Supported, and the paper strengthens
  it.* Boyd 2017 is the citation `lammps-interface` itself asks for, and
  it says UFF/UFF4MOF are good for bulk moduli and thermal expansion but
  deviate for vibrational-mode-sensitive properties, more so with charges
  on. That is a shippable scope statement for the export, and it is
  currently missing from the idea.
- **Idea 9 — framework-class force fields (Dreiding, BTW-FF, …).**
  *Supported.* Boyd 2017 benchmarks exactly DREIDING, UFF4MOF, BTW-FF and
  DWES on MOFs and finds all of them adequate for bulk properties — so the
  idea has a real accuracy precedent, not just a "more is better" one.
- **Idea 15 — missing-linker / missing-node defects.** *Supported with a
  caveat.* MOFBuilder does defective models, but its documented outputs
  are GROMACS/OpenMM (not LAMMPS, so it does not double as idea 8's
  precedent) and the "within seconds" quote could not be verified. Its
  headline result argues for **MD over static porosity**, which is a
  different and arguably stronger message for this app.
- **Idea 17 — post-synthetic functionalisation.** *Supported as stated,
  thinly.* PSYMOF's pipeline is described accurately in the report, and it
  maps cleanly onto the app's existing machinery. The evidence is one case
  study on one framework family — reasonable motivation for an **L**, not
  a validated demand signal. Note its charges come from **PACMOF**, an ML
  predictor neither idea 1 nor idea 6 currently contemplates.
- **Idea 18 — GCMC input generation for RASPA3.** *Does not support it —
  the paper is silent.* RASPA3's paper is a rewrite announcement plus a
  comparison of four MC insertion schemes; it says nothing about input
  preparation, CIF conversion or GUIs, and it does document a pybind11
  Python interface. The case for idea 18 rests entirely on GitHub issues
  and the existence of hand-glue scripts, which is weaker evidence than
  the report's phrasing implies for an **L**-sized commitment.
- **Idea 26 — quasi-harmonic F(V,T).** *Newly supported, by a paper nobody
  connected to it.* MACE-MP-MOF0's paper **is** a QHA phonon workflow for
  MOFs, validated on MIL-53 — the app's own scan example. If idea 26 is
  ever revived, this is its reference implementation and the caveat comes
  with it: QHA "does not provide sufficient description of anharmonic
  effects in MOFs".

---

## What I did not get to

- **Five of the eleven rows are abstract-level.** ACS (JACS, both JCTC
  papers), Wiley (Israel J. Chem.), Research Square and nature.com's
  IdP redirect all refused fetches, so PSYMOF, MOFBuilder, MOSAEC, EQeq+C
  and Ongari 2019 were reconstructed from Crossref, PubMed/search-surfaced
  abstracts and author-posted copies. Every `?` in the matrix marks
  something that would have come from the full text.
- **MOFBuilder's "within seconds" quote is unresolved** and is the one
  place a research-report claim could not be either confirmed or refuted.
- The RASPA3 publisher PDF downloaded but its body streams did not extract
  cleanly; only the front matter and abstract were machine-readable, so
  claims about its input handling come from the online manual instead.
- `lammps-interface`'s **UFF4MOF** support is asserted in the
  research-parts but was not visible in the README text reached; unchecked.
- Papers cited in research.md but outside this brief's ten — MOFun, MOFid,
  the Chem. Sci. 2020 CSD curation, arXiv 2505.17914, PMC10388356, MOFA,
  SimMOF — were not triaged.
- No tracked file was touched; this report is the only file written.

---

```
[literature-triage-matrix]
  Wrote: review/reports/literature-matrix.md
  Papers in matrix: 11 (11 new this run; 10 requested, EQeq split into 2 rows)
  Skipped (already in matrix, unchanged): 0
  Read full text for: 3 (MOFSimBench, MACE-MP-MOF0 — arXiv HTML; MOFChecker — PMC)
  Abstract/metadata only: 5 (PSYMOF, MOFBuilder, MOSAEC/JACS, EQeq+C, Ongari 2019)
  Citation corrections found: 6 (MOFChecker venue; MOSAEC DOI + 52% attribution;
    MACE-MP-MOF0 "10x"; MOFSimBench model set + conclusion; EQeq+C authorship;
    Ongari "7/15 false positives")
  Suggested next: reread REVIEW.md §7 ideas 4 and 5 before sending them to Jules
```
