> **Written 2026-09-24** against `origin/main` at `fc38248`, cross-referencing `review/reports/` (written 2026-09-18/19 against `3cd15e2`) with PRs #2-#9. Scratchpad paths named below were the checking scripts; they are not in the repository.

# Crystal Builder: review plan vs what shipped (engines, EQeq, COD), with a science audit

Repo `/Users/sam/Projects/Jules/Crystal-Builder` at `main` = `fc38248` (merge of PR #9). Review docs were read from `origin/features/deep-review`. Nothing tracked was edited, and `git status` is clean. Every script and every downloaded reference source is in the scratchpad `jules/` folder (listed at the end).

Note: `gh pr view 9` reports **19 commits**, not 105.

---

## 0. Scientific findings, ranked by severity

| # | Severity | Finding | Evidence |
|--:|---|---|---|
| S1 | **High** | **EQeq returns physically impossible charges for any cation outside a 7-element charge-centre list, and says nothing.** `CHARGE_CENTRES` is exactly the authors' 2012 `chargecenters.dat` (Mg, V, Co, Ni, Cu, Zn, Zr). Every other metal (Al, Cr, Fe, Mn, Ti, Na, Eu, In, Cd, ...) and Si is expanded about the neutral atom. That gives a soft J (5–7 eV) and a charge runaway. Measured with the shipped code: **Al-soc-MOF-1 (a shipped COD sample): Al +6.33, O down to −3.58**. Corundum: Al **+10.5**. Quartz: Si **+5.69**. Halite: Na **+1.78**, and the suite's own halite test only asserts > 0.5. Each of these exceeds the atom's valence-electron count. The users cannot set a charge centre (the authors' program read an editable file). Open Babel's EQeq, which the authors' own README now points users to, ships centres for about 65 elements (Al 3, Ti 3, Cr 2, Fe 3, Mn 2, Eu 3, In 3, Cd 2, Na 1, ...). With those centres, Al-soc-MOF-1 gives Al +2.40, PCN-222 gives Fe +1.84 (not +0.87), and Mn-BTT gives Mn +1.14–1.23 (not +0.57–0.79). About half the COD library (Al, Cr, Fe, Mn, Eu frameworks) is affected. The only caveat shown is the generic "an estimate to look over". | `scratchpad/jules/centres.py`, `centres2.py`, `simple.py`; OB `data/eqeqIonizations.txt` |
| S2 | **High** | **ORB-v3 and MatterSim ship without the D3 dispersion correction, yet cite MOFSimBench's volume accuracy.** The ORB docstring and the engine description rely on the "89 % volume accuracy vs UFF4MOF 62 %" figure. MOFSimBench (arXiv 2507.11806) states that all its models "either predict D3-corrected outputs … or the D3 correction is computed at inference time using the torch-dftd package … damping=bj". The review raised exactly this as an open decision ("does an `ENGINES` entry own its dispersion correction?", registry-and-interpenetration.md lines 1461–1468 and decision 4). No answer is recorded, and the shipped engines (and MACE) are bare PBE(+U) models. Expect a systematic over-estimate of cell volume on MOF relaxations, and a benchmark claim the shipped configuration cannot reproduce. | `grep -i 'd3\|dispersion' xtal/ff/{orb,mattersim,mace}` → nothing |
| S3 | **Medium (unverified risk)** | **ORB's "double precision" may be mixed precision.** `_build_model` puts torch's default dtype back after loading. But orb-models 0.7.0's `ForcefieldAdapter.from_ase_atoms` builds the graph (positions, edge vectors, the strain displacement) in `torch.get_default_dtype()` *at call time*, and `ORBCalculator.calculate` passes no dtype. So once the default is back to float32, the float64 model is given float32 geometry. It also depends on engine order: MACE's loader sets the global default to float64 and nobody restores it, so ORB's precision depends on whether MACE was loaded first in the process. The commit only checked "the model still evaluates after it is". The 4e-7 eV float64 figure may not hold in the shipped path. A one-line check on a machine with orb installed would settle it: compare the finite-difference energy error with the default restored and not restored. | orb-models v0.7.0 `forcefield_adapter.py:104-108`, `inference/calculator.py`; `xtal/ff/orb/calculator.py:_build_model`; `xtal/ff/mace/calculator.py:_build_model` |
| S4 | **Medium** | **The shipped EQeq differs sharply from the authors' program on small cells, and the docstring misstates the size of the difference.** The authors' "Ewald" uses η = 50 Å with ±2 cells and ±2 k-vectors. On a cell under ~10 Å that is a damped, truncated direct sum with essentially no reciprocal part. Crystal Builder's sum is properly converged: I checked it against the authors' own formula with a real split (η = 2–4 Å), and the Si/Al values agree to within the NIST-vs-authors table difference. So the port is the *correct* lattice sum. But on dense solids it disagrees with the program by factors: quartz Si 5.69 vs 1.50, corundum Al 10.5 vs 4.8. The docstring presents convergence as a small refinement ("+1.210 against +1.211"). That holds only for large MOF cells. | `simple.py` |
| S5 | **Medium** | **The MOF-5 validation compares different geometries, and the test is too loose to catch real errors.** The reference numbers (Zn +1.211, O −0.968/−0.483) are hard-coded external constants. They match the authors' algorithm on the authors' own `IRMOF-1.cif`: my re-implementation gives Zn 1.2115, O −0.9673/−0.482. The test, however, runs on `resources/samples/MOF-5.cif`, a PBEsol VESTA model, with a ±0.05 e window. On *the same geometry* the port matches the authors' algorithm to **1.5e-4 e** (both IRMOF-1 and MOF-5.cif). The "no atom off by >0.05 e (the carboxylate carbon)" is **entirely geometry** (C 0.368 vs 0.321). It is not "the converged Ewald sum and a newer NIST table", as `eqeq.py` claims. The implementation is better than advertised, but the test would pass a 0.04 e error. | `compare.py`, `digits.py` |
| S6 | **Low–Medium** | **Stress checks for ORB, MatterSim and MACE cannot detect a sign or factor-2 error.** Each compares analytic and numeric stress with `abs=2e-3` kcal/mol/Å³ on one water molecule in a 30 Å box. On that system UFF's whole stress is at most 1.4e-3 (and zz = 0, because the molecule is planar), so the signal is below the tolerance. Only a gross unit slip (GPa vs eV/Å³) would fail. Upstream code, read directly, does use the ASE convention (+1/V dE/dε, in eV/Å³; MatterSim goes via `/GPa` then `×GPa`), so no bug is shown. The guard is still nearly vacuous. Use a dense, strained crystal instead. | UFF numeric stress on `water()` |
| S7 | **Low** | **Deuterium and disorder break the COD samples for computation.** `cod/MIL-53.cif` (neutron, `D` atoms) is refused by every engine: UFF says "no parameters for D… covers hydrogen to lawrencium", which is misleading; EQeq says "no ionisation energies for 'D'"; ASE `Atoms('D')` raises a raw KeyError that is not wrapped into a `CalculatorError`. 11 of 16 COD files have partial-occupancy sites (UiO-66 has 10 of 13). `xtal/ff` has no occupancy awareness, so EQeq and UFF treat every split site as a full atom. UiO-66 EQeq then gives an oxygen at **+0.66 e**. MIL-88B and MIL-100/101 have no H. These are faithful experimental CIFs, not simulation-ready models, and nothing tells a user that before they press Relax or Equilibrate. | `occ.py`, `centres.py` |
| S8 | **Low** | `resources/samples/MIL53.cif` is, by its own provenance, a PORMAKE build on **`acs`**, which is the MIL-88/MIL-100 net. MIL-53 is a rod MOF (`sra`-type). The name is wrong. It is unreachable from the UI (still not in `SAMPLES`), so impact is low. | `PROVENANCE.md` |
| S9 | Trivial | `COULOMB_EV = 14.399645` vs the paper's 14.4 (0.0025 %). The authors' N electron affinity is −0.07; the shipped value is 0 (blank → 0). Both are negligible. The "every other byte as downloaded" claim is not literally true: `fetch()` normalises CRLF. | |

---

## 1. Status of Phase-2 items, §7 ideas and the gating decisions

### 1a. Julius's answers to "Decisions that gate work" (inline comment on PR #1, `review/PLAN.md`)

| # | Question | His answer (verbatim) | What happened |
|--:|---|---|---|
| 1 | MFU-4l: structure or topology? | "N457 is an extended Kuratowski block, but not through the multi connected note" | The structure was built: ROADMAP §2, phases 3–7 (attachments, joints, orientation, MFU-4l end to end, shipped 2026-09-20/21). |
| 2 | MACE-MP-MOF0: still want it? | "Yes we want them" | **Not shipped.** It is not in `MACE MODEL_CHOICES`, not in the ROADMAP and not in the TODO. **OPEN.** |
| 3 | Which uMLIPs, given the licences? | "Include whatever you recommend" | ROADMAP §7: "all three licence-clean uMLIPs (UMA and eSEN are out -- gated or research-only weights)". ORB-v3 and MatterSim shipped. SevenNet was dropped (e3nn conflict, "Julius's decision"). |
| 4 | EQeq+C: pay, or EQeq alone? | "Ship EQeq alone" | EQeq shipped. EQeq+C DECIDED-AGAINST (paywalled table). |
| 5 | Curated library: replace the CCDC-headed samples, or add beside them? Fix MIL53/UIO66? | "Add beside them for now, we can prune later." | 16 COD files added *beside* the old ones. The CCDC files are kept "knowingly" (PROVENANCE.md). MIL53.cif, UIO66.cif and NiHITP.cif are still shipped but not in Open Sample. |
| 6 | Shared `ASECalculatorEngine` first? | "Do it first" | Done first: factoring phase 4 (`1ad7080`), then ORB and MatterSim as subclasses. |

Not answered anywhere: the design doc's own "Decision needed" on **D3 dispersion** (see S2).

### 1b. PLAN.md Phase 2

| # | Item | Status | Where / reason |
|--:|---|---|---|
| 2.1 | mmCIF/PDBx read | **SHIPPED** | `0e7ea4d` |
| 2.2 | Interpenetration detection | **SHIPPED**, and generation too | `3e6b5c3`; ROADMAP §2 phase 9 (`xtal/analysis/interpenetrate.py`) |
| 2.3 | POSCAR/CONTCAR | **SHIPPED** | `c678168`, `93b9daf` |
| 2.4 | pymatgen JSON / ASE `.traj` | **SHIPPED** | `1ad6766`, `0338db5` |
| 2.5 | Shared ASE engine, then uMLIPs | **PARTIAL** | Base shipped (`1ad7080`). ORB-v3 (`69ab6a9`) and MatterSim (`8119594`) shipped. SevenNet DECIDED-AGAINST (sevenn needs e3nn ≥ 0.5; mace-torch pins 0.4.4; running it out of process was not pursued). UMA and eSEN-OAM DECIDED-AGAINST (gated / research-only weights). D3 was not addressed (S2). |
| 2.6 | EQeq | **SHIPPED** | `758f9eb`: NIST/PubChem table plus `scripts/eqeq_table.py`, one row in `CHARGE_SOURCES` (the three-copy list collapsed in factoring phase 4). See §2. |
| 2.7 | EQeq+C | **DECIDED-AGAINST** | "Ship EQeq alone" (the table is paywalled) |
| 2.8 | Curated library + `DATA_LICENSES` | **PARTIAL** | 16 COD CIFs plus `PROVENANCE.md` (a test enforces an entry per file). There is no `DATA_LICENSES` mechanism. The review's advice to ship primitive cells for MIL-100/101 was not followed (MIL-101 is 16 000 atoms in P1 and too big for EQeq's 2000-atom limit). |
| 2.9 | MOFkey-style identifier | **OPEN** | He said "Yes" (idea 13). Nothing in the code. |
| 2.10 | Energy units pref; vector 3-D export; publication renders; LAMMPS export; conda-forge/Zenodo/JOSS | **Mostly OPEN** | Energy units, renders, LAMMPS, conda-forge, CITATION.cff, Zenodo and JOSS: none present. **Vector 3-D export already existed before the review** (`xtalapp/viewport/svg_export.py`, 2026-09-04, older than the review base `3cd15e2`, and deliberately not gl2ps). That review gap was stale. |

### 1c. REVIEW.md §7 ideas

| # | Idea | His reply | Status |
|--:|---|---|---|
| 1 | Check a structure on open | "Sure it could" | **PARTIAL**: coincident-atom warning on open (`5121b44`). The charge-balance / oxidation-state checks (the larger 32.5-point share of MOFChecker's 38 %) are OPEN. |
| 2 | Autosave | "could be useful" | **SHIPPED** (shell phase 3) |
| 3 | Worker fix | "Yes" | **SHIPPED** (`937f614`, `32db6a5`) |
| 4 | More uMLIPs | "Yes we should add" | **PARTIAL**: ORB-v3 and MatterSim. SevenNet, UMA and eSEN are out (see 2.5). |
| 5 | MACE-MP-MOF0 | "Sure" / decision 2 "Yes we want them" | **OPEN** |
| 6 | EQeq / EQeq+C | "Yes we should add" | EQeq **SHIPPED**. EQeq+C **DECIDED-AGAINST** (paywall). |
| 7 | mmCIF, POSCAR, pymatgen JSON, .traj | "Yes we should add" | **SHIPPED** |
| 8 | LAMMPS data export | "Yes we should add" | **OPEN** |
| 9 | Dreiding / MZHB / ZIFFF | "lower priority" | **OPEN** (deprioritised) |
| 10 | More Zeo++ features | "We could add" | **PARTIAL, mostly already there**: `-ha`, `-chan`, `-volpo`, `-psd` predate the review. Blocking spheres and AV/NAV pocket separation are OPEN (TODO "Pockets are drawn with the channels"). |
| 11 | OPTIMADE dialog | "Yes" | **OPEN** |
| 12 | CoRE/QMOF/CSD catalogues | "Depends on licensing… A small database of curated MOFs could also be useful" | The curated set **SHIPPED** (COD, 16). Large catalogues are OPEN or deferred on licensing. |
| 13 | MOFid/MOFkey | "Yes" | **OPEN** |
| 14 | Interpenetration | "interested, need more information" | **SHIPPED** (detection and generation) |
| 15 | Defects | "…would require a definition of what the linker/nodes are" | **OPEN** (deferred behind the PORMAKE work) |
| 16 | Multi-linker / combinatorial | "Yes… MFU-4l… takes precedence" | The MFU-4l part **SHIPPED** (ROADMAP §2 phases 1–9). Multi-linker combinatorial generation itself is **OPEN**. |
| 17 | Post-synthetic functionalisation | "Crystal Builder itself enables this easily" | **DECIDED-AGAINST** |
| 18 | RASPA3 GCMC input | "lower priority" | **OPEN** |
| 19 | Publication renders | "Yes we should add" | **OPEN** |
| 20 | glTF / 3Dmol web 3D | "Low priority" | **OPEN** |
| 21 | Vector export of the 3-D view | "Yes we should add" | **Already built before the review** (svg_export.py) |
| 22 | Energy units preference | "Yes we should add" | **OPEN** |
| 23 | Code signing | "Paying $99 is low priority" | **DECIDED-AGAINST for now** (cost) |
| 24 | conda-forge, CITATION.cff, Zenodo, JOSS | "Yes we should add" | **OPEN** (no CITATION.cff) |
| — | Three non-feature questions | — | Invariant tests: **PARTIAL** (engines phase 0 pinned the QSettings guard, the √2 strain metric and others). CLI files a build: **SHIPPED** (factoring phase 1). `--selftest` on PRs: **OPEN** (the bundle and selftest job still run on pushes to main and tags only). |
| — | "Already on his lists" (scan `--resume`, dark mode, disorder, Rietveld, QHA) | — | Not audited here. Dark mode / "follow the system" shipped in shell phase 4. |

---

## 2. EQeq science audit (vs Wilmer, Kim & Snurr, JPCL 2012, 3, 2506, and the authors' `main.cpp`)

Reference implementations were read directly: numat/EQeq `main.cpp`, `chargecenters.dat` and `ionizationdata.dat`, and Open Babel `src/charges/eqeq.{cpp,h}` with `data/eqeqIonizations.txt`. The paper itself is paywalled. Its Correction (jz301439a) added the charge centres, the source code, the ionisation data and a NaCl CIF as supporting information, so the program's files are the paper's parameters.

| Check | Paper / program | Shipped | Verdict |
|---|---|---|---|
| χ, J from the charge centre c | `X = ½(IP[c+1]+IP[c]) − c·J`, `J = IP[c+1]−IP[c]`, with IP[0] = EA (program and OB) | `energies[centre]`, `energies[centre+1]`, the tuple = (EA, IE1, IE2, …), `chi = ½(above+below) − centre·J` | **Correct.** For Zn c = 2 it uses IE2 and IE3 (17.96, 39.72) |
| Ionisation indexing | NIST "Ion Charge" is the charge before ionisation, so it maps to IE(charge+1) | `table[z][charge+1]` in `scripts/eqeq_table.py` | **Correct** |
| Hydrogen EA | `hI0 = -2.0` in the EA slot, used whatever the centre (program and OB) | `HYDROGEN_AFFINITY = -2.0`, replacing `below` for H | **Correct.** Ongari 2019 describes it as "EA_eff = +2 eV"; that is a sign convention, and the program value is −2. |
| λ | 1.2 | `DIELECTRIC = 1.2` | **Correct** |
| Pair prefactor | `lambda * (k/2) * (...)` in both the authors' program and OB. Ongari calls it ε_eff = 1.67 | `dielectric * COULOMB_EV/2 * coulomb` | **Correct** (and the halving is documented) |
| Overlap term | `a = sqrt(Ji Jj)/k`; `exp(-a²r²)(2a − a²r − 1/r)`, summed over images; J_ij(r→0) → λ√(JiJj) | Identical form, summed over images out to 1e-12, with the self term at r = 0 dropped (the diagonal is J_i) | **Correct.** Self-image overlap is included, as in the program's i==j branch. |
| Diagonal | `J_i + λk/2 (self-image real + recip − 2/(η√π) + self-image overlap)` | `J_i + λk/2 (pair_matrix_ii + overlap_ii)`; pair_matrix_ii includes self images, −2α/√π and background | **Correct**, and converged |
| Ewald / k-space | Program: η = 50 Å, ±2 cells, ±2 k-vectors, `exp(-(hη/2)²)`, no background | Standard Ewald with α from an accuracy target and cutoffs, `exp(-k²/4α²)/k²`, uniform-background term in every entry | Physically **more correct**. It is the same as the program for ~26 Å MOF cells (1.5e-4 e) and very different for small cells (S4). |
| Split independence | — | Claimed | **Verified**: entry-wise max difference 3.8e-14 between real cutoffs 6/10/16 Å on a random triclinic 7-atom cell. Charges are split-independent to 9e-14 for Q = 0, +1 and −2. Supercell 2×1×1 charges are identical to 2e-14. The simple-cubic jellium diagonal gives M·a = −2.837299 (textbook −2.837297), and BCC gives −1.81962/a per particle (textbook −1.81962). |
| Charge neutrality | Row 0 = Σq = Q | `qeq._solve`, last row Σq = Q | **Holds** (sums to 1e-14 on every structure tried, charged cases included) |
| Units | eV, Å, e, k = 14.4 | eV, Å, e, 14.399645 | OK (S9) |
| Charge centres | 2012 file: Mg 2, V 4, Co 2, Ni 2, Cu 2, Zn 2, Zr 4. OB (successor): ~65 metals, e.g. Al 3, Ti 3, V 3, Cr 2, Mn 2, Fe 3, Na 1 … | The 2012 seven, hard-coded, with no override | **Faithful to the paper's defaults, and scientifically inadequate** (S1) |
| Table | The program ships its own table (GPL) | Regenerated from NIST ASD + PubChem, with both raw downloads in `tests/data/eqeq` and a regeneration test | Clean, and only negligibly different for MOF elements |

**The "+1.210 vs +1.211" claim.** The reference is an independent constant: the authors' program run on their `IRMOF-1.cif`. It is not produced by Crystal Builder itself. My Python re-implementation of `main.cpp` reproduces it (Zn 1.2115). The shipped code gives 1.2115 on the same geometry and 1.2102 on `MOF-5.cif`. So the number is honest, but it comes from comparing two geometries, and the test tolerance (±0.05) reflects that. Recommendation: pin IRMOF-1's (or COD 1516287's) geometry and compare at ±2e-3 against the program values.

---

## 3. ORB-v3 and MatterSim

Neither package is installed in `.venv`, so the upstream code was read at the tags (orb-models v0.7.0, mattersim v1.2.5).

- **Default dtype float64.** Yes for both (`double_precision=True`). MatterSim passes `dtype="float64"`, and upstream calls `model.double()` and upcasts inputs, so it is fine. For ORB see S3.
- **Units.** `ASECalculator.compute` multiplies energy, forces and stress by 23.0605 (eV to kcal/mol). ASE's `get_stress(voigt=False)` is +(1/V)dE/dε in eV/Å³, the same sign and normalisation as `Calculator.numeric_stress` (a central difference of symmetric strains divided by V). MatterSim's stress is `1/V·dE/dε / GPa` times `stress_weight = GPa`, which gives eV/Å³ in the ASE sign. ORB's conservative models report `grad_stress` from autograd. MACE, ORB and MatterSim all go through the same base class, so the handling is identical by construction. The tests guarding this are weak (S6).
- **Conservative-only ORB.** Yes: four `orb-v3-conservative-*` models, a test asserts it, and "direct" models are refused by `available`.
- **Device.** `torch_device(..., allow_mps=False)` for both. MatterSim also refuses an explicit "mps" with a sentence. ORB would fail at load with a `CalculatorError`.
- **Stress for cell relaxation.** Both declare `stress` and `implements_stress()` confirms it. ORB conservative models append "stress" when `has_stress`.
- **Licences.** The code docstrings say ORB is "Apache-2.0 code and weights" and MatterSim "MIT code and weights". Upstream confirms: the orb-models LICENSE is Apache-2.0 and its README says "Orb models are licensed under the Apache License, Version 2.0". The MatterSim repo is MIT and `MODEL_CARD.md` says `license: mit`. pyproject declares only the extras (`orb-models>=0.7`, `mattersim>=1.2.5`), with no licence metadata. Worth adding to the engine description: MatterSim's model card says it "has relatively low accuracy for organic polymeric systems", which is relevant to MOF linkers.
- **Other observations.** ORB puts torch's global dtype back after loading, but MACE does not, so precision depends on load order (S3). A `D` atom reaches ASE as an unwrapped `KeyError` (S7).

---

## 4. COD library

- **CC0.** Confirmed from crystallography.net/cod: "All data in the COD and the database itself are dedicated to the public domain and licensed under the CC0 License", with a request to acknowledge the original authors.
- **PROVENANCE.md** lists all 16 COD ids with the paper and DOI, and each DOI matches the file's `_journal_paper_doi`. `_cod_database_code` matches `ENTRIES` for all 16. It also names every legacy file.
- **Stripping.** The script drops only whole items or loops whose *every* tag starts with `_refln`, `_diffrn`, `_shelx_`, `_platon_squeeze`, `_pd_meas/proc/calc_intensity`, `_pd_proc_ls_weight` or `_gsas_i100`. It raises an error on a loop that mixes kept and dropped tags, and it re-parses with gemmi to assert that the set of non-stripped tags is unchanged. All other lines are copied verbatim, so the atom-site loops cannot change. Verified without network:
  - `strip()` is idempotent on all 16 shipped files.
  - No stripped-tag remnants remain.
  - A synthetic trap (a `_shelx_res_file` text field containing lines that start with `_atom_site…` and `loop_`, followed by `_refln` and `_atom_site` loops) strips correctly and leaves the atom-site loop byte-identical.

  I did not byte-diff against fresh COD downloads (no network download was done). The only non-verbatim change is CRLF→LF.
- **Residual CCDC markers.** ZIF-8, NU-1000 and cubic-EuHOTP from the COD carry `_audit_update_record … downloaded from the CCDC`, the same audit line the review cited for MFU4l. COD's CC0 covers them, but it shows the header alone does not decide the licence.
- **The three CCDC-headed samples.** `MFU4l.cif`, `Ni2Cl2BTDD.cif` and `CFA1.cif` were **not replaced**. PROVENANCE.md records the decision in so many words: *"That is a risk this folder carries knowingly: Julius chose on 2026-09-23 to keep them as they are and to add the COD set beside them"* (MFU-4l is the suite's stress case). CFA1's header explicitly forbids redistribution ("may not be copied or further disseminated"), and it ships in every bundle.

---

## Artefacts (scratchpad `/private/tmp/claude-502/-Users-sam-Projects-Jules/01fc0638-89bf-4229-8a0a-7713083cc256/scratchpad/jules/`)

- `authors_eqeq.py`: an independent Python re-implementation of the authors' `main.cpp` Ewald-mode EQeq
- `compare.py`, `digits.py`: port vs authors on IRMOF-1 and MOF-5 (agreement to 1.5e-4 e)
- `split.py`: pair_matrix Madelung checks and split / total-charge independence
- `simple.py`: quartz, halite and corundum; the program vs a converged split
- `centres.py`, `centres2.py`: EQeq over the COD library, and the effect of charge centres
- `occ.py`, `codcheck.py`: COD occupancy/H census and strip idempotence plus the trap test
- Reference sources used, all read-only: `eqeq_main.cpp.txt`, `eqeq_ion.dat`, `IRMOF-1.cif`, `ob_eqeq.cpp.txt`, `mattersim_potential.py.txt`, `orb_*.txt`
