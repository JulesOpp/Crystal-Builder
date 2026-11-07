# Generative and inverse-design models for crystals and porous frameworks: candidates for Crystal Builder 1.2

Research date: 2026-11-06. Scope: generative and inverse-design models only. MLIPs were covered in the 2026-10-09 survey (`reports/Crystal Builder feature landscape.md`), which already notes Mofasa's MOFChecker validity (59.9% vs 15.7%), the "Hunting Structural Demons" paper on invalid generated MOFs (arXiv 2603.26295), PXRD-conditioned generators (deCIFer, PXRDGen, CrystaLLM-π weights on HF), and the lack of any open COF diffusion generator (CONFFUSION thesis embargoed to 2027). These notes do not repeat that material.

Licences were checked against the GitHub API (`license.spdx_id`) and LICENSE files on 2026-11-06. "Last push" is the GitHub `pushed_at` date on that day.

## 1. State of the art in inorganic crystal generation: what is open, permissive, installable and CPU-feasible?

### Takeaway
MatterGen (Microsoft, MIT code and weights) is the strongest and best-documented open generator with released property-conditioned checkpoints. It is GPU-oriented (CUDA, with experimental Apple MPS), slow (about 9 s per structure even on an A100), and trained only on cells of 20 atoms or fewer. CrystaLLM (MIT) and its property-conditioned successor CrystaLLM-π are the most CPU-friendly options: small GPT-2-style models with `cpu` and `mps` devices supported out of the box. They are less stable and less reliable at producing parseable output. Several headline models are open code but non-commercial (ADiT is CC-BY-NC 4.0), or have no stated licence (FlowMM).

### Cited Findings

**Model-by-model status (licence, weights, install, hardware)**

- **MatterGen** (Microsoft Research AI for Science). The repo is MIT. The Hugging Face card `microsoft/mattergen` is MIT and was last modified 2026-08-27. GitHub last push was 2026-08-27, with about 1.86k stars. — [GitHub API / repo](https://github.com/microsoft/mattergen); [HF card](https://huggingface.co/microsoft/mattergen)
  - Released checkpoints: `mattergen_base` (unconditional, trained on Alex-MP-20), `mp_20_base`, `chemical_system`, `space_group`, `dft_mag_density`, `dft_band_gap`, `ml_bulk_modulus`, `dft_mag_density_hhi_score`, and `chemical_system_energy_above_hull`. — [repo README](https://github.com/microsoft/mattergen)
  - Install: Python 3.10+ with `uv pip install -e .`, or the PyPI package `mattergen` with torch 2.2.0 and cu121 PyG wheels. Linux with CUDA is assumed. Apple Silicon is "experimental" and needs `PYTORCH_ENABLE_MPS_FALLBACK=1`. No CPU requirements are stated. — [repo README](https://github.com/microsoft/mattergen)
  - The `mattergen_base/checkpoints/last.ckpt` file is **461,370,350 bytes (~461 MB)**. I measured this via the HF API. It may include non-inference state, which I did not verify. — [HF tree API](https://huggingface.co/microsoft/mattergen)
  - Trained and evaluated only on unit cells with **≤20 atoms**; "more atoms are currently not supported". — [HF model card](https://huggingface.co/microsoft/mattergen)
  - The 4.4k ordered and 117.7k disordered ICSD structures used in the paper are not shared "for license reasons". — [repo README](https://github.com/microsoft/mattergen)
  - The Orb paper notes that MatterGen and MatterSim used ICSD training data, which has commercial-licensing implications. This is from the prior survey's notes. — [Orb paper arXiv 2410.22570](https://arxiv.org/html/2410.22570v1)
  - Speed: one baseline study ran MatterGen on a single A100 at **~9.22 s per generated material**. It notes the model was "much too slow (several minutes per material) to run in high throughput" in its other setting. The same study lists CrystaLLM at 38.27 s, CDVAE 14.32 s, random generation 0.14 s and FTCP 0.03 s per structure on its own setup, which is not a clean head-to-head. — [Szymanski & Bartel, arXiv 2501.02144](https://arxiv.org/pdf/2501.02144)
  - LeMat-GenBench puts MatterGen at the slow end of the inference-time Pareto front, with the highest M.S.U.N.%. WyFormer is at the low-latency extreme. — [LeMat-GenBench arXiv 2512.04562](https://arxiv.org/pdf/2512.04562)
- **CrystaLLM** (Antunes et al., Nat. Commun. 2024). Code is MIT and dataset files are CC-BY 4.0 (Zenodo 10642388). Last push 2026-03-16. — [repo](https://github.com/lantunes/CrystaLLM)
  - Default architecture: 12 layers, 12 heads, 768-dim embeddings. A pre-trained `crystallm_v1_small` is downloadable via `bin/download.py`.
  - Install: `pip install -r requirements.txt` plus `torch==2.0.1` plus `pip install -e .`. Device defaults to `cuda`, with `cpu` and `mps` documented as alternatives. bfloat16 is the default dtype.
  - Prompting requires a cell composition (elements sorted by electronegativity). Space group is optional. Decoding is random sampling or MCTS. No release packages are published. — [repo](https://github.com/lantunes/CrystaLLM)
- **CrystaLLM-π** (property injection; arXiv 2511.21299, 26 Nov 2025). It injects continuous property vectors into attention through "Property-Key-Value Prefix" and "PKV Residual" attention. It was fine-tuned on a photovoltaic dataset, and candidates were validated by DFT. — [arXiv 2511.21299](https://arxiv.org/html/2511.21299)
  - Released HF checkpoints under `c-bone/` include `CrystaLLM-pi_base`, `_bandgap`, `_density`, `_SLME`, `_mp_20_base`, `_alex_mp_20_base`, `_ft_alex_mp_20-text` (text-conditioned), and XRD-conditioned variants. — [HF model search](https://huggingface.co/c-bone/CrystaLLM-2.0_base)
  - The base card lists the licence as **MIT**, with a GPT-2-style architecture. — [HF card](https://huggingface.co/c-bone/CrystaLLM-2.0_base)
  - PSDI describes it as open source with a container and web app. — [PSDI resource](https://resources.psdi.ac.uk/resource-theme/37242589-7d89-462a-afad-29386bcfcda4)
  - An unverified secondary summary says band-gap match improves from 0.637 to 0.745 on MP-20. — [Emergent Mind](https://www.emergentmind.com/papers/2511.21299)
- **Chemeleon** (text-guided diffusion): MIT, last push 2025-05-30. **Chemeleon2** (RL/GRPO-tuned latent diffusion transformer): MIT, last push 2026-05-14. — [chemeleon](https://github.com/hspark1212/chemeleon); [chemeleon2](https://github.com/hspark1212/chemeleon2)
  - Chemeleon2 installs with `uv sync` from a clone, with no PyPI package. Its only example is CUDA 12.8 / torch 2.7. The README states no weight download location or model size.
  - Its RL rewards include an energy-above-hull reward, a predictor reward (e.g. band gap or density), and diversity and creativity rewards. Training extras pull in mace-torch and smact. — [chemeleon2 repo](https://github.com/hspark1212/chemeleon2)
  - The paper version appeared in Nature Machine Intelligence (2026). — [Nat. Mach. Intell.](https://www.nature.com/articles/s42256-026-01262-4); [arXiv 2511.07158](https://arxiv.org/pdf/2511.07158)
- **DiffCSP** (NeurIPS 2023): MIT, last push 2025-04-14. **DiffCSP++** (ICLR 2024, space-group-constrained): MIT, last push 2026-02-05. — [DiffCSP](https://github.com/jiaor17/DiffCSP); [DiffCSP-PP](https://github.com/jiaor17/DiffCSP-PP)
- **OMatG** (Open Materials Generation; CSP and de novo generation): MIT, last push 2026-06-30. — [FERMat-ML/OMatG](https://github.com/FERMat-ML/OMatG)
- **CrystalFormer** (deepmodeling; space-group-aware autoregressive "foundation model"): **Apache-2.0**, last push 2026-03-31. — [repo](https://github.com/deepmodeling/CrystalFormer)
- **ADiT** (All-atom Diffusion Transformer, Meta FAIR, ICML 2025; one model for molecules and crystals, scaled to ~0.5B parameters). LICENSE is **CC-BY-NC 4.0 (non-commercial)**. Last push 2026-04-13. — [repo LICENSE](https://github.com/facebookresearch/all-atom-diffusion-transformer); [arXiv 2503.03965](https://arxiv.org/abs/2503.03965)
- **FlowMM / FlowLLM** (Meta FAIR). GitHub reports licence "NOASSERTION", and no `LICENSE` file was found on the `main` branch. Last push 2024-10-29. — [repo](https://github.com/facebookresearch/flowmm)
- **LeMat-GenBench** (Dec 2025, v2 14 Jan 2026) evaluated 12 models: ADiT, Crystal-GFN, CrystalFormer, DiffCSP, DiffCSP++, LLaMat2-CIF, LLaMat3-CIF, MatterGen, PLaID++, SymmCD, WyFormer and WyFormer-DFT. Its benchmark code is Apache-2.0 and was last pushed 2026-09-15. — [arXiv 2512.04562](https://arxiv.org/html/2512.04562v1); [repo](https://github.com/LeMaterial/lemat-genbench)
- Other 2025–26 entrants seen but not examined:
  - DiffCrysGen (arXiv 2510.12329) claims S.U.N. generation rates 2–3 orders of magnitude above MatterGen and DiffCSP, by its own account. — [arXiv 2510.12329](https://arxiv.org/pdf/2510.12329)
  - NextCrystal (symmetry-driven CSP, arXiv 2602.17176). — [arXiv](https://arxiv.org/pdf/2602.17176)
  - A fine-tuning-free adaptive-constraint-guidance diffusion model (arXiv 2604.13354). — [alphaXiv](https://www.alphaxiv.org/abs/2604.13354)
  - CrystalReasoner (reasoning + RL, arXiv 2605.14344). — [alphaXiv](https://www.alphaxiv.org/abs/2605.14344.md)
  - InvDesFlow-AL and CrystalFlow, both scored in PhononBench. — [PhononBench](https://arxiv.org/html/2512.21227v1)

**Quality comparisons**

- **LeMat-GenBench results** (2,500 samples per model, LeMat-Bulk reference of ~5M structures; stable means E_hull ≤ 0, metastable means ≤ 0.1 eV/atom; energies are the mean of a MACE-MP, UMA and Orb-v3 ensemble, each with its own hull):
  - **MatterGen**: novel 70.5%, stable 2.0%, S.U.N. 0.2%, **M.S.U.N. 15.0% (highest)**.
  - **PLaID++**: **S.U.N. 1.0% (highest)**, stable 12.4%, but only 24.2% novel.
  - **WyFormer-DFT**: M.S.U.N. 7.8%.
  - **DiffCSP**: M.S.U.N. 8.5%.
  - **Crystal-GFN**: 0% stable.
  - Overall, "S.U.N. rates … never exceeding 1%". Stability trades off against novelty and diversity, and no model wins everywhere. Validity is generally >90%. — [arXiv 2512.04562](https://arxiv.org/html/2512.04562v1)
- **Relaxation matters for comparisons**. Models that relax internally (MatterGen, PLaID++, WyFormer) change little after relaxation. ADiT's stability rises from **0.1% to 17.7%**, and DiffCSP's M.S.U.N. from **8.2% to 19.4%**, after UMA relaxation. — [arXiv 2512.04562](https://arxiv.org/html/2512.04562v1)
- **Chemeleon2 paper** (authors' own numbers):
  - mSUN on MP-20: MatterGen 24.5, DiffCSP 17.2, Chemeleon1 20.7, **Chemeleon2 26.0**.
  - On Alex-MP-20: MatterGen 41.0, Chemeleon1 32.3, **Chemeleon2 61.3**.
  - Chemeleon2's uniqueness drops to 79.5 / 88.7. — [arXiv 2511.07158](https://arxiv.org/pdf/2511.07158)
  - Note that these mSUN figures are on a different protocol from LeMat-GenBench and are not comparable to it.
- **PhononBench** (dynamical stability, −0.1 THz threshold):
  - MP-20: MatterGen 45.05%, DiffCSP 43.94%, CrystalFlow 40.00%.
  - Alex-20: MatterGen 57.89%, InvDesFlow-AL 56.59%.
  - Throughput: DiffCSP is fastest and MatterGen slowest.
  - **CrystaLLM-small has CIF parsing failures "up to 90%" in severe cases.** — [arXiv 2512.21227](https://arxiv.org/html/2512.21227v1)
- In the baseline study, MatterGen had a higher stability rate than CrystaLLM and CDVAE. The authors also found that simple baselines such as ion exchange from known compounds are competitive for finding stable materials. — [arXiv 2501.02144](https://arxiv.org/pdf/2501.02144)

### Inferences
- The only open models that ship **ready-made property-conditioned weights** under a permissive licence are **MatterGen** (MIT) and **CrystaLLM-π** (MIT per its HF card). They are the realistic candidates for a "generate a structure with property X" button.
- Everything else either needs retraining for conditioning or is licence-restricted: ADiT (NC), FlowMM (unclear), Chemeleon2 (RL fine-tuning per target).
- **CPU feasibility, estimated rather than measured**:
  - MatterGen at ~9 s per structure on an A100 suggests minutes per structure on a laptop CPU. A batch of 16–64 candidates would then take tens of minutes to hours. That is acceptable only as a background job.
  - Apple MPS is "experimental", so a Mac build cannot promise it.
  - CrystaLLM-small explicitly supports `cpu` and `mps`. It is a GPT-2-sized model (12×768), so CPU sampling is plausible. The 38 s per structure figure was on unspecified hardware, and high parse-failure rates mean many samples are wasted.
  - No source gave measured laptop-CPU timings for any generator. Crystal Builder would need to benchmark this itself.
- **Packaging**:
  - MatterGen pins torch 2.2 + cu121 PyG wheels and its checkpoint is ~461 MB. Crystal Builder's MLIP extras already pull a torch stack.
  - Version conflicts between MatterGen's pins and MACE/ORB/MatterSim are likely. That argues for running generation in an isolated subprocess or venv, consistent with the app's existing "heavy ML in subprocesses" pattern.
  - Weights should be downloaded on demand, not bundled in the ~300 MB installer.
- **Cell-size limit**: MatterGen's ≤20-atom limit means it cannot generate MOFs or most porous frameworks. It is for small inorganic cells only.

### Gaps
- No measured CPU or Apple-silicon timings were found for MatterGen, CrystaLLM, Chemeleon2, DiffCSP or OMatG.
- MatterGen parameter count was not confirmed. The 461 MB checkpoint may include EMA or optimizer state.
- Not checked: the weight-release location for Chemeleon2, OMatG and DiffCSP++, and the WyFormer and PLaID++ licences and weights.
- The FlowMM licence could not be determined: no LICENSE file was found on `main`, and other branches were not checked.
- The licence for the MP-20 / Alex-MP-20 / LeMat-Bulk data was not checked.
- The current LeMat-GenBench HF leaderboard standings (post-paper submissions) were not read.

## 2. MOF/COF-specific generative work and links to topology-based building (PORMAKE)

### Takeaway
MOF generation has moved from coarse-grained building-block diffusion (MOFDiff) to flow matching (MOFFlow-2) and all-atom latent diffusion (Orbital's Mofasa). Only MOFDiff and MOFFlow-2 have MIT-licensed code. I could not find Mofasa's weights in public, though its 202k-structure MofasaDB is CC-BY 4.0. The approach closest to Crystal Builder's PORMAKE path is "generate the linker, assemble on a fixed topology" (GHP-MOFassemble). Mofasa's inpainting (generate linkers inside a fixed node scaffold) is the all-atom analogue.

### Cited Findings
- **MOFDiff** (Microsoft; coarse-grained diffusion over building blocks): MIT, last push **2024-06-18**, so it looks dormant. — [repo](https://github.com/microsoft/MOFDiff)
- **MOFFlow** (ICLR 2025) is a structure-prediction model (it predicts the assembled MOF from given building blocks), not a de novo generator. — [arXiv 2410.17270](https://arxiv.org/abs/2410.17270); [OpenReview](https://openreview.net/forum?id=dNT3abOsLo)
  - A secondary write-up says the checkpoints are on Zenodo under MIT. I could not resolve the repo at `kaist-silab/MOFFlow`. — [write-up](https://hunterheidenreich.com/notes/computational-chemistry/molecular-modeling/mofflow/)
- **MOFFlow-2** (NeurIPS 2025, torsion-aware flow matching, two-stage design plus structure prediction) beats MOFDiff on validity, novelty, uniqueness and sampling time. MIT, last push 2026-02-13. — [NeurIPS paper](https://proceedings.neurips.cc/paper_files/paper/2025/file/146b5b0feb14fe8e630669ad1faba25e-Paper-Conference.pdf); [repo](https://github.com/nayoung10/MOFFlow-2)
- **Mofasa** (Orbital Materials, arXiv 2512.01756, Dec 2025). All figures in this item are from [arXiv 2512.01756](https://arxiv.org/html/2512.01756v1) unless noted.
  - **What it generates**: all-atom latent diffusion that jointly samples atoms, types and lattice for **up to 500 atoms**. Nodes, linkers and topology emerge from sampling, with no assembly algorithm.
  - **Conditioning**: per-node chemical formula, per-fragment molecular graphs, and **inpainting** (e.g. linkers within a fixed node scaffold).
  - **Validity (MOFChecker)**: QMOF-trained Mofasa scores 52.9%, and 59.9% after MLIP relaxation, against 15.7% for ADiT. Trained on Boyd-Woo, it scores 44.8% against **MOFFlow-2 38.8%** and **MOF-BFN 32.3%**.
  - **Validation pipeline**: Orb-v3 + D3 relaxation (FIRE, 0.05 eV/Å, ≤500 steps). About 84% of MofasaDB converges, against 98% of QMOF. This is followed by a 50 ps NPT MD check with orb-v3-con-inf-omat + D3 on ~1,000 samples, MOFid decomposition, pymatgen space groups, and Zeo++ with a 1.86 Å N₂ probe.
  - **MofasaDB**: 201,926 generated structures on Hugging Face under **CC-BY 4.0**, searchable at mofux.ai.
  - **Not released, as far as I found**: model weights and code. The paper text does not say they are released, and a GitHub search for "mofasa" found only unrelated repos. Sampling uses 4k diffusion steps, and no hardware timing is reported.
  - **Limits**: memory is quadratic in atom count, the atom count must be fixed in advance, and the model covers MOFs only.
- **GHP-MOFassemble** generates linkers with DiffLinker and combines them with pre-selected metal nodes in a fixed topology. Mofasa's authors describe it this way and contrast it with their assembly-free approach. They ran no head-to-head benchmark. — [arXiv 2512.01756](https://arxiv.org/html/2512.01756v1)
  - A GitHub search found no public repo under the name GHP-MOFassemble.
- **ChatMOF** (LLM agent for MOF prediction and inverse design): MIT, `pip install chatmof`. It requires an **OpenAI API key** (GPT-4 / GPT-3.5-turbo), and generation needs `chatmof install-griday`. Linux is recommended, and torch must be below 2.0.0 for some dependencies. Last push 2025-05-15. — [repo](https://github.com/Yeonghun1675/ChatMOF)
  - The README does not say whether generation uses PORMAKE or a genetic algorithm.
- **MOFTransformer** (property predictor often used to score generated MOFs): MIT, last push 2026-05-23. — [repo](https://github.com/hspark1212/MOFTransformer)
- The prior survey found many invalid generated MOFs are traced to bad building-block inputs and weak topology/symmetry constraints during assembly. — [arXiv 2603.26295](https://arxiv.org/pdf/2603.26295)
- The prior survey found no open, peer-reviewed COF diffusion generator. — [TU Delft thesis record](https://repository.tudelft.nl/record/uuid:8184659a-547e-4dd9-aa2d-0e832465ef40)

### Inferences
- A MOF "generate" feature in Crystal Builder is more realistic as **"generative linker + PORMAKE assembly"** than as a full all-atom MOF diffusion model. The steps would be:
  1. Propose linkers with a small molecule generator, or sample from a curated set.
  2. Assemble on the user's chosen topology with the existing PORMAKE-style builder.
  3. Relax with UFF4MOF and then ORB/MACE.
  4. Validate with the MOF validation battery the prior survey recommends.
  5. Score pore size and geometry with Zeo++ (already shipped).

  This mirrors GHP-MOFassemble, keeps topology under the user's control, and runs on CPU because the costly step is the MLIP relaxation, which the app already does.
- Mofasa is the quality leader but cannot be integrated: no public weights were found. Orbital might be approachable, given that ORB is Apache-2.0, but that is speculation. MofasaDB (CC-BY 4.0) could be offered as a searchable "generated MOF library" through the planned fetch feature. This is a cheap, honest alternative to on-device generation.
- MOFFlow-2 (MIT) is the best open de novo MOF generator found, but it is a research codebase with no documented CPU support.
- Mofasa's own validation pipeline (Orb-v3 + D3 relax, then NPT MD, MOFid, Zeo++) is nearly identical to tools Crystal Builder already ships. That shows the app's validation stack is the community standard.

### Gaps
- Not determined: MOFDiff weight availability, MOFFlow-2 checkpoint location, and CPU feasibility for either.
- GHP-MOFassemble's code location and licence were not found.
- MOFGPT and other LLM-based MOF generators (e.g. MOF-BFN, MOFGen) were not examined: the tool-call budget ran out.
- Whether ChatMOF's generator uses PORMAKE was not confirmed. The README mentions only GRIDAY and MOFTransformer, and `structure.md` was not read.
- No reticular generative model found combines with PORMAKE topologies directly, though the search was not exhaustive.

## 3. Property-conditioned generation: what conditioning exists in released weights?

### Takeaway
Released, permissively licensed conditioning is narrow:
- **MatterGen**: chemical system, space group, DFT band gap, DFT magnetic density, ML bulk modulus, joint magnetic density + HHI (supply-risk score), and joint chemical system + energy-above-hull.
- **CrystaLLM-π**: band gap, density, SLME (photovoltaic efficiency), text, and XRD.
- **CrystaLLM**: composition and optional space group.
- **Mofasa** (not released): formula, fragment graphs and inpainting only, with no property targets.

No released open model was found that conditions directly on pore size or adsorption.

### Cited Findings
- MatterGen's conditioned checkpoints are `chemical_system`, `space_group`, `dft_mag_density`, `dft_band_gap`, `ml_bulk_modulus`, `dft_mag_density_hhi_score` and `chemical_system_energy_above_hull`. — [repo README](https://github.com/microsoft/mattergen)
- CrystaLLM-π HF checkpoints come in `_bandgap`, `_density`, `_SLME`, text and XRD variants. — [HF c-bone models](https://huggingface.co/c-bone/CrystaLLM-2.0_base); [arXiv 2511.21299](https://arxiv.org/html/2511.21299)
- CrystaLLM conditions on composition (required) and space group (optional). — [repo](https://github.com/lantunes/CrystaLLM)
- Chemeleon2 steers toward properties through RL rewards: hull energy, predictor reward and diversity. That means fine-tuning per target rather than a conditioning input at sampling time. — [repo](https://github.com/hspark1212/chemeleon2)
- Chemeleon v1 is "text-guided" (composition and crystal-system text). — [repo](https://github.com/hspark1212/chemeleon)
- Mofasa conditions on per-node formula, fragment molecular graphs and inpainting. Its paper reports no property or pore-size conditioning. — [arXiv 2512.01756](https://arxiv.org/html/2512.01756v1)
- The 2026 adaptive-constraint-guidance paper targets constraints without fine-tuning (title only, not read). — [arXiv 2604.13354](https://arxiv.org/html/2604.13354v1)
- TaCr2O6 was MatterGen's bulk-modulus-conditioned showcase. Its measured bulk modulus was within 20% of the predicted value. — [Szymanski & Bartel via search summary, escholarship](https://escholarship.org/content/qt9qx9t3kz/qt9qx9t3kz.pdf?t=sd23fh)

### Inferences
- For Crystal Builder's MOF and porous users, "generate with pore size X" or "with CO₂ uptake Y" is **not available from any released model found**. The honest version is **generate-then-filter**: produce candidates (PORMAKE enumeration or a generator), compute the property with tools already in the app (Zeo++ for pore size, later RASPA/Widom), and rank. This is screening, not conditioning, and should be labelled that way.
- For dense inorganic users, MatterGen's band-gap, bulk-modulus, space-group and chemical-system checkpoints map cleanly onto a dialog: "chemical system = Li-Fe-P-O, space group = 62, band gap ≈ 3 eV". Its labels are DFT (PBE) band gaps and an ML-predicted bulk modulus, which the UI must state.
- Space-group conditioning (MatterGen `space_group`, CrystaLLM prompt, DiffCSP++, CrystalFormer) fits well with Crystal Builder's symmetry tooling.

### Gaps
- Not quantified: how accurately MatterGen hits targets. The paper's target-hit statistics were not read in this pass.
- Not checked: whether CrystaLLM-π property checkpoints are trained on MP-20 cells only (≤20 atoms), or how well they hit targets on CPU.

## 4. Validation pipelines: what would a credible in-app "generate → relax → check → rank" loop look like?

### Takeaway
The field's de facto pipeline has five stages:
1. Validity filters: parseable CIF, minimum distance >0.7 Å, density bounds, charge neutrality, space-group consistency.
2. MLIP relaxation: MatterSim in MatterGen's own pipeline, or Orb, MACE or UMA.
3. Energy above the convex hull of a large reference set, with an MLIP-consistent hull.
4. Uniqueness and novelty by structure matching against the training or reference set.
5. Increasingly, dynamical stability: phonons or short NPT MD.

Every component except a large reference hull is already in or near Crystal Builder.

### Cited Findings
- **MatterGen's own evaluation** relaxes with MatterSim (default `MatterSim-v1-1M`, 5M optional). It computes novelty, uniqueness and stability against MP2020 by default, or the 845,997-structure Alex-MP reference. It recommends TRI2024 corrections for real work and warns MLFF results may differ from DFT. — [repo README](https://github.com/microsoft/mattergen)
- **LeMat-GenBench protocol** (Apache-2.0 code):
  - Validity checks: CIF readable, min distance >0.7 Å, density and lattice bounds, space-group consistency and charge neutrality.
  - Energies from an ensemble of MACE-MP, UMA and Orb-v3, each with its own hull; the mean ± SD is reported.
  - Novelty and uniqueness by fingerprint matching against LeMat-Bulk (~5M structures).
  - Also reports distribution metrics (JS, MMD, FID), diversity (element, space group, size, site), and HHI.
  - S.U.N. and M.S.U.N. are computed as a sequential funnel.
  - — [arXiv 2512.04562](https://arxiv.org/html/2512.04562v1); [repo](https://github.com/LeMaterial/lemat-genbench)
- **Dynamical stability** is now benchmarked. In PhononBench, even the best models are only ~45% (MP-20) and ~58% (Alex-20) phonon-stable. — [arXiv 2512.21227](https://arxiv.org/html/2512.21227v1)
- **MOF-specific pipeline (Mofasa)**:
  - MOFChecker validity.
  - Orb-v3 + D3 relaxation, which converged for ~84% of generated structures against 98% of QMOF.
  - 50 ps NPT MD, MOFid, pymatgen symmetry, and Zeo++ porosity.
  - — [arXiv 2512.01756](https://arxiv.org/html/2512.01756v1)
- Simple baselines (ion exchange of known compounds, random enumeration) are competitive for finding stable materials, so a credible loop should compare generators against such baselines. — [arXiv 2501.02144](https://arxiv.org/pdf/2501.02144)

### Inferences
A credible Crystal Builder loop, built mostly from shipped components:
1. **Generate** N candidates (MatterGen or CrystaLLM-π for small inorganic cells; PORMAKE enumeration plus a linker source for MOFs) in a subprocess job with a progress bar and cancel.
2. **Validity screen** with LeMat-GenBench-style checks: distances, density, charge neutrality via oxidation-state guessing, and the planned MOF validation battery and MOFChecker-style checks for frameworks.
3. **Relax**, cheap first: UFF/UFF4MOF pre-relax for frameworks, then ORB-v3-conservative / MatterSim / MACE-MPA-0. The prior survey's warning against direct-force models for cell relaxation applies.
4. **Symmetry and dedup**: spglib symmetrisation, plus a pymatgen StructureMatcher-style uniqueness check within the batch.
5. **Stability**: E_hull against a local hull built from MP/Alexandria/LeMat-Bulk entries for the chemical system, using the same MLIP. A per-system OPTIMADE fetch avoids shipping a 5M-structure database. Show engine disagreement across MACE/ORB/MatterSim as an uncertainty band, as LeMat-GenBench does with its 3-MLIP ensemble.
6. **Novelty**: match against the fetched reference set and flag "known compound" prominently. See the TaCr2O6 lesson in section 5.
7. **Optional dynamical check**: phonopy Γ-point or small supercell, or short NPT MD.
8. **Rank** on a Pareto view (target property vs E_hull vs novelty), with every number labelled with engine, dispersion setting and reference set.
9. **Present the output as "hypotheses for DFT/experiment"**, never as "new materials".

The heavy steps (3 and 5) are already CPU-feasible in the app. Generation itself is the CPU bottleneck.

### Gaps
- No CPU timing for a full loop was found.
- LeMat-Bulk licence and size-on-disk were not checked.
- Not determined: whether the OPTIMADE fetch can supply enough hull competitors per chemical system for reliable E_hull.

## 5. Experimental validations and critiques: honest limitations a chemist would raise

### Takeaway
MatterGen's flagship experimental validation (TaCr2O6, bulk modulus within ~20% of target) has been challenged in a 2026 *Materials Horizons* paper. The paper argues the synthesised phase is a disordered version of a compound reported in 1972, and one already present in MatterGen's training data. Combined with low S.U.N. rates (<1% in LeMat-GenBench), the stability–novelty trade-off, and ≤20-atom training cells, the honest framing for an app is "candidate generator", not "materials discovery".

### Cited Findings
- **Juelsholt critique.** "Continued challenges in high-throughput materials predictions: MatterGen predicts compounds from the training dataset", *Materials Horizons* 2026, Issue 11. Its claims:
  - Crystallographic analysis shows the synthesised material is "identical to the already known compound Ta1/2Cr1/2O2", reported in 1972 and present in MatterGen's training data.
  - The MatterGen team synthesised a **disordered** phase with overall stoichiometry Ta1/3Cr2/3O2 rather than the predicted ordered TaCr2O6.
  - — [RSC landing](https://pubs.rsc.org/en/content/articlelanding/2026/mh/d6mh00268d); [ChemRxiv/Cambridge Engage](https://www.cambridge.org/engage/coe/article-details/694d24f36e8e74030e9067de)
  - The full text returned 403 for me, so details are from search snippets.
- A secondary blog attributes the critique to Robert Palgrave (UCL). The primary RSC record names Juelsholt, so treat the Palgrave attribution as unreliable. — [nextwavesinsight](https://nextwavesinsight.com/?p=363); contradicted by [RSC](https://pubs.rsc.org/en/content/articlelanding/2026/mh/d6mh00268d)
- **Cheetham & Seshadri** (Chem. Mater. 2024) critiqued GNoME, not MatterGen. They argued that most breakthroughs come from exploring the large set of already-known compounds. I found no evidence that they wrote about TaCr2O6 specifically. — [search summary; Horizons 2025 related paper](https://pubs.rsc.org/en/content/articlepdf/2025/mh/d5mh00010f)
- Szymanski & Bartel present TaCr2O6 as a positive benchmark (measured bulk modulus within 20% of predicted). — [escholarship PDF](https://escholarship.org/content/qt9qx9t3kz/qt9qx9t3kz.pdf?t=sd23fh)
- **S.U.N. rates never exceed 1%** for any of 12 models on LeMat-GenBench. Higher stability comes with lower novelty and diversity. — [arXiv 2512.04562](https://arxiv.org/html/2512.04562v1)
- **Dynamical instability** is common: 42–60% of generated structures fail phonon stability, depending on dataset and model. — [PhononBench](https://arxiv.org/html/2512.21227v1)
- **Licence and data provenance**: MatterGen's paper training used ICSD structures that cannot be redistributed, so released results may differ. — [repo README](https://github.com/microsoft/mattergen)
- **MOF validity remains low** even for the best model: ~60% MOFChecker-valid after relaxation, with ~16% of generated MOFs failing to converge under Orb relaxation. MOFChecker itself is "brittle", per Mofasa's authors. — [arXiv 2512.01756](https://arxiv.org/html/2512.01756v1)
- The prior survey adds that the A-Lab review blamed unreliable automated Rietveld refinement for false discoveries. — [Chemistry World](https://chemistryworld.com/news/new-analysis-raises-doubts-over-autonomous-labs-materials-discoveries/4018791.article)

### Inferences
Limitations a chemist (Julius) would raise:
1. **Novelty is measured by structure matching against ordered entries.** A generated ordered phase can be a known disordered phase in disguise, as with TaCr2O6. The app should check generated structures against disorder-aware references, or at least warn that a novelty flag is not proof of novelty.
2. **E_hull from an MLIP is not thermodynamic stability.** It ignores entropy, temperature and kinetics, and depends on which hull competitors were fetched.
3. **Synthesisability is not modelled at all.**
4. **Property labels are PBE-level**: band gaps underestimated, bulk modulus from an ML predictor.
5. **Small-cell bias**: ≤20 atoms for MatterGen and MP-20-trained models.
6. **For MOFs**: many outputs are chemically invalid (oxidation states, missing H, impossible coordination), and there are no released property-conditioned MOF generators.

These map onto the prior survey's thesis that Crystal Builder's identity is "the place a structure becomes trustworthy". A generator is the input; the validation loop is the product.

Which E_hull cut-off counts as "promising", whether novelty against MP/Alexandria is enough, and whether to show generated structures at all without a disorder warning are **chemistry decisions for Julius**, per the project rule that he owns chemistry defaults.

### Gaps
- I could not read the Juelsholt full text (403), so its specific recommendations are unknown.
- No MatterGen team rebuttal was found, and none was searched for.
- No experimental validation of any MOF-generator output, or of CrystaLLM / Chemeleon outputs, was found in this pass.
- 2026 critiques beyond Juelsholt (e.g. Palgrave's broader GNoME and A-Lab critiques) were not systematically collected.
