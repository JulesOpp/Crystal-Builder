# Structure from experiment: "pattern in, structure out" for Crystal Builder 1.2

Research date: 2026-11-06. Builds on the 2026-10-09 survey (`reports/Crystal Builder feature landscape.md`, features 12, 13 and 15), which already covered Dara, CrystalShift, deCIFer's real-data paper, Crystalyze's 42% and RMCProfile export. These notes go deeper on structure solution and on what can be chained in-app. Where a number comes only from simulated patterns, it is labelled **[SIM]**. Where it comes from measured patterns, it is labelled **[EXP]**.

## 1. Classical direct-space structure solution and charge flipping: what is usable from Python?

### Takeaway
The best open, Python-callable route for **molecular** crystals is GALLOP: it is GPU-accelerated and reads Pawley output. For **inorganic** crystals, the closest new analogue to what the app already does is the Ab-PXRD-Solver recipe from the PyXtal group (Zhu, May 2026): enumerate symmetry, sample Wyckoff positions, relax with MACE, then Rietveld-rank. Both methods are open, and both consume indexing and Pawley results that Crystal Builder already produces. FOX/ObjCryst is available as pyobjcryst (BSD-3). Superflip and EDMA (charge flipping) are free but cannot be redistributed, so they cannot be bundled.

### Cited Findings
- **GALLOP** (Spillman & Shankland, CrystEngComm 2021, DOI 10.1039/D1CE00978H) combines fast local optimisation with a particle swarm. On two challenging structures it found solutions about **10× more often than DASH**. It is open source, GPU-accelerated, and can be run from a browser GUI or as a Python library. Colab and Kaggle notebooks mean no local GPU is needed. — [CrystEngComm](https://pubs.rsc.org/en/content/articlehtml/2021/ce/d1ce00978h); [GitHub](https://github.com/mspillman/gallop)
- GALLOP **reads Pawley fit outputs from DASH, GSAS-II and TOPAS**, plus SHELX HKLF4 single-crystal data. The README warns it is "very much a work in progress". A 2022 follow-up added handling of ring conformations of unknown geometry. — [GitHub](https://github.com/mspillman/gallop); [Reading repository](https://reading-clone.eprints-hosting.org/105564/1/CEC_Article_Revised_ForCentaur.pdf)
- **Ab-PXRD-Solver** (Su, Ridwan, Xue, Zhu, UNC Charlotte; arXiv 2605.24594, 23 May 2026) is a physics-based, non-generative pipeline:
  - **Preprocessing:** background subtraction, SciPy peak detection and a CNN peak filter.
  - **Indexing:** cells indexed per Bravais lattice (CellSolver and SmartCellSolver), with PyXtal extinction rules; then Wyckoff combinations are enumerated.
  - **Candidates:** Sobol or Halton quasi-random sampling of free coordinates.
  - **Relaxation:** **MACE relaxation at fixed cell via ASE**. Candidates are rejected if forces exceed 0.5 eV/Å or stress exceeds 0.3 GPa.
  - **Ranking:** normalised cross-correlation screen, then **GSAS-II Rietveld**. A candidate is accepted at R² ≥ 0.95 and χ² ≤ 0.12, with energy used alongside the fit.
  — [arXiv](https://arxiv.org/html/2605.24594v1)
- Ab-PXRD-Solver results:
  - On **1,136 MP-20 cases that earlier generative models had failed**, success was 100% cubic, 99.2% hexagonal, 98.1% trigonal, 98.4% tetragonal, 94.0% orthorhombic and **60.1% monoclinic**. The paper does not say clearly whether these patterns were measured or simulated; treat them as likely **[SIM]**.
  - **Runtime:** minutes to hours on one CPU.
  - **Scope:** inorganic only. MOFs and organics are left as future work with MatterSim, MACE-OFF or UMA.
  - **Ranking failures:** in the Eu₃Al₂O₇ example with an unknown space group, it generated about 33,000 trial structures and the true answer ranked **9th**. The authors say it is "not a black-box optimization procedure."
  — [arXiv](https://arxiv.org/html/2605.24594v1)
- Ab-PXRD-Solver code is at github.com/MaterSim/Ab-PXRD-Solver. No licence was found in the text. — [arXiv](https://arxiv.org/html/2605.24594v1); [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **FOX / ObjCryst++** is free, open-source ab initio structure determination from powder data. It runs global optimisation in direct space and can fit several powder patterns at once (X-ray and neutron). Its documentation includes a PbSO₄ inorganic tutorial. — [FOX docs](https://objcryst-fox.readthedocs.io/en/latest/); [PbSO₄ tutorial](https://objcryst-fox.readthedocs.io/en/latest/tutorial-pbso4.html)
- **pyobjcryst** provides Python bindings to ObjCryst++. It is listed as **BSD-3-Clause**, supports Python 3.12–3.14 and ships in the diffpy.cmi conda collection. The project does not clearly document a turnkey solving API; its listing invites users to contact the maintainer for help with the global optimisation algorithms. — [libraries.io](https://libraries.io/pypi/pyobjcryst); [PyPI](https://pypi.org/project/pyobjcryst)
- **Superflip** (charge flipping, Fortran90) supports powder data by combining charge flipping with histogram matching. Its licence allows modification but **forbids redistributing the code, modified or not**. **EDMA** is free with acknowledgement; commercial use requires contacting the copyright holders. — [Superflip licence](https://superflip.fzu.cz/download/license_superflip.txt); [EDMA licence](https://superflip.fzu.cz/download/license_EDMA.txt); [Superflip site](https://superflip.fzu.cz/)

### Inferences
- Ab-PXRD-Solver is almost a blueprint of Crystal Builder's existing stack. The app has its own indexing, PyXtal-style symmetry and in-process MACE. It would swap RietX in for GSAS-II, and its Rwp-versus-energy Pareto view replaces Zhu's empirical thresholds. Of all the routes surveyed, this is the cheapest "solve" feature for small inorganic cells. It is also honest about failure: it ranks candidates rather than claiming one answer.
- GALLOP's Pawley-file input means a "solve molecular structure" step could sit directly after the app's Pawley fit. The dependency is heavy (PyTorch/GPU, alpha-quality code), so an optional extra or a "send to GALLOP" export is safer than vendoring.
- Charge flipping cannot ship inside an open-source distribution under Superflip's licence. At most the app could call a user-installed binary.

### Gaps
- No licence was found for GALLOP or Ab-PXRD-Solver; check the repos before vendoring.
- EXPO, DASH, TOPAS and PowCod-based search were not researched in this pass. EXPO and DASH are standalone programs and TOPAS is commercial. No source was retrieved on their current licensing or scripting APIs.
- No head-to-head of GALLOP, FOX and Ab-PXRD-Solver on the same experimental patterns was found.

## 2. ML structure solution from PXRD (late 2024–2026): success on real data, licences, weights

### Takeaway
Experimental benchmarks have improved sharply in 2026. RealPXRD-Solver reports about **78% top-1 on measured RRUFF/CNRS patterns, but only when lattice parameters are given**. That falls to **48–57% on structures not in training**, and only small cells (≤20 atoms) were tested. Without that help, top-1 on measured data stays around **42–44%** (Crystalyze, Bragglite). The papers with the best experimental numbers all treat Rietveld refinement as essential for choosing among candidates. Almost no repo states a licence for its weights.

### Cited Findings
- The curated list (last updated 2026-10-30) now has **17 core PXRD→structure solvers and 25 related modules**. It warns that "experimental results are scarce" and that most rates are not comparable. — [awesome_pxrd2xtal_generation](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **Crystalyze** (Riesel, Mackey et al., JACS 2024, 146, 30340): **42% on 134 RRUFF patterns [EXP]** vs 67% on Materials Project **[SIM]**. — [MIT News](https://news.mit.edu/2024/ai-model-can-reveal-crystalline-materials-structures-0919); [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **RealPXRD-Solver** (Li, Guo, Jiao … Ke, E, Jin, Yao; DP Technology and IOP-CAS; arXiv 2603.00965, 1 Mar 2026):
  - **Training:** about 6.25 M theoretical structures from AFLOW, Alexandria, MP and OQMD, with peak-shift, noise, intensity and broadening augmentation.
  - **Results with lattice given [EXP]:** CNRS (126) top-1 **77.9%**, top-20 91.9%; RRUFF (269) top-1 **78.8%**, top-20 92.9%.
  - **Non-overlapping subsets [EXP]:** CNRS (23) top-1 **47.8%**; RRUFF (14) top-1 **57.1%**.
  - **Match criterion:** StructureMatcher with stol 0.5, ltol 0.3, angle 10°.
  - **Refinement:** candidates are refined with scripted **GSAS-II**, and the authors call that step "essential". A structure counts as solved at Rwp < 15% and chemically sensible.
  - **Runtime:** under 1 min per sample on one GPU.
  - **Limits:** ≤20 atoms per primitive cell; organic and hybrid materials excluded; code on GitHub and weights on Google Drive, **no licence stated**.
  — [arXiv](https://arxiv.org/html/2603.00965v1)
- **XRDSol** (Nat. Commun. 2026): **81.6% on ICDD-20 [EXP]**, 82.3% on MP-20 **[SIM]**. Code at ai4mat-zhu/XRDSol; licence not stated. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **Bragglite** (arXiv 2026): **44.2% top-1 on 100 RRUFF patterns [EXP]** (±2.49 over five seeds), under strict unrefined matching. The code is MIT but some helpers are CC BY-NC 4.0, and pretrained weights are "TBA". — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **AGAPI-XRD** (arXiv 2026, RRUFF [EXP]): it offers a candidate for 93.8% of patterns and a valid lattice for 79.7%. A structure-match rate on RRUFF is not reported, and it needs an AGAPI key. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **deCIFer** (TMLR 2025, plus a Digital Discovery 2026 real-world study): on experimental tests it recovered Si and CeO₂, but **failed on Fe₂O₃ and on nanocrystalline CeO₂** [EXP, diagnostic only]. Its 94% figure is on synthetic validation [SIM]. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation); [deCIFer arXiv](https://arxiv.org/html/2502.02189); [Digital Discovery](https://pubs.rsc.org/dd/article/doi/10.1039/d6dd00088f/1290750/Tackling-real-world-crystal-structure-prediction) (403 on fetch; details from the list)
- Models reported **only on simulated patterns**:
  - PXRDGen (Nat. Commun. 2025): 82% with one sample, 96% with 20, on MP-20.
  - PXRDnet (Nat. Mater. 2025): simulated nanocrystals.
  - CrystalNet (npj 2024).
  - XtalNet (Adv. Sci.): hMOF-100/400 top-10 90.2%/79%.
  - DiffractGPT (JPCL 2025), Uni3DAR (75.08% MP-20) and CrystaLLM-π (62.73% MP-20; Hugging Face weights).
  - PXtal and JEPA-PXRD.
  None of these states a weights licence. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation); [PXRDGen](https://www.nature.com/articles/s41467-025-62708-8)
- PXRDGen pairs its generator with a Rietveld refinement module. — [Nat. Commun.](https://www.nature.com/articles/s41467-025-62708-8)
- **AlphaDiffract** (arXiv 2026), as a pre-step: 81.7% crystal system and 66.2% space group on RRUFF [EXP]. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)

### Inferences
- In 2026 the experimental numbers are only as good as the lattice that goes in. That favours Crystal Builder, which already indexes. Feed the indexed cell to a lattice-conditioned generator, take its top 20, refine each with RietX, and judge them with the MLIP. That is the RealPXRD-Solver recipe with the app's own components.
- The weights-licence gap reported on 2026-10-09 has not closed. RealPXRD-Solver, XRDSol, Crystalyze and deCIFer still state none. "Bring your own model" plugins remain the safe design. The only cleanly licensed pieces are code: Bragglite (MIT, weights pending) and GALAXI (MIT).
- The common cut-off for these benchmarks, about ≤20 atoms per primitive cell, excludes MOFs and most molecular crystals. ML generators therefore cover the app's inorganic users, not its MOF users.

### Gaps
- No independent, cross-paper benchmark on one shared experimental test set was found. The RRUFF subsets differ in size: 134, 100, 269 and 14 patterns.
- The deCIFer real-world paper returned 403, so its per-artefact findings come second-hand.
- No measured runtime for running RealPXRD-Solver on CPU, as in a desktop app, was found.

## 3. MOF/COF-specific: topology-built candidates + PXRD fitting + MLIP energy ranking

### Takeaway
**No published workflow was found that combines reticular building from topologies, Rietveld or Pawley ranking against measured PXRD, and universal-MLIP energy ranking.** The closest pieces are:
- **Xrd2Mof** (JACS 2025): diffusion over coarse-grained metal nodes and linker centroids, then assembly, force-field relaxation and pattern ranking. It scores >93% top-10 on simulated CSD patterns, with one experimental case.
- **XtalNet**: hMOF patterns, simulated only.
- **A ZIF crystal structure prediction study** (2026) using DFT plus MLIPs with PXRD similarity.

That leaves the gap open, and it is the one Crystal Builder is best placed to fill.

### Cited Findings
- **Xrd2Mof** (Feng et al., *JACS* 2025, 148, 869–78, per the citing article's reference list):
  - **Representation:** metal nodes kept as 3D coordinates and linkers reduced to centroids, built on a MOFdiff-style diffusion model. Linkers are matched against about **400,000 building blocks**, with connection points set by charge neutrality and linker SMILES.
  - **Downstream:** assembled structures are relaxed with a **force field** and ranked against the input pattern.
  - **Results:** on about 10,000 CSD-derived MOFs **[SIM]**, top-10 is **93.4% single-linker and 96.2% dual-linker**. One measured ALICEE pattern was tried; the authors call it "encouraging but not a systematic experimental benchmark".
  - **Limits:** simulated data omit broadening, preferred orientation, background, guests, defects and breathing. It assumes the linker survives synthesis intact.
  — [Zhang & Li, AI Agent 2026, 2, 15 (27 Jul 2026)](https://www.oaepublish.com/articles/aiagent.2026.25)
- Xrd2Mof source is **MIT** at PKUsam2023/Xrd2Mof; data must be requested from the authors. CrySTARNet, from the same group, has only a repo and Zenodo deposit with no paper, and claims >85% top-10 across six families. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- The same highlight article says it does **not** describe combining Xrd2Mof's assembly with Rietveld refinement or MLIP/DFT energy ranking. It proposes this only conceptually, as an agent orchestrating both tools. — [AI Agent 2026](https://www.oaepublish.com/articles/aiagent.2026.25)
- **XtalNet** (Adv. Sci. 2024/25) generates MOF candidates from PXRD and ranks them by pattern similarity: top-10 **90.2% (hMOF-100) and 79% (hMOF-400) [SIM]**. — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11848617/)
- **Hierarchical crystal structure prediction of ZIFs with DFT and MLIPs** (arXiv 2601.05097, 2026) matches predicted structures to PXRD with a variable-cell similarity index. It reports "considerable variations" in where the correct match ranks, and blames one poorly ranked structure on its lack of porosity. — [arXiv](https://arxiv.org/pdf/2601.05097)
- **PhiGen** (arXiv 2026) seeds zeolite phases from experimental data: ZSM-25 succeeded in 1 of 4 seeds and TNU-9 in 1 of 40. No public code. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- Ab-PXRD-Solver names MatterSim, MACE-OFF and UMA as needed to extend its approach to MOFs and organics. — [arXiv](https://arxiv.org/html/2605.24594v1)

### Inferences
- A "solve MOF from PXRD" mode would combine building blocks and reticular rules Crystal Builder already has:
  1. The user supplies the metal cluster and linker.
  2. The app enumerates candidate nets (RCSR, plus interpenetration).
  3. It builds each candidate, relaxes it with MACE, ORB or MatterSim, and checks it with MOFChecker-style diagnostics.
  4. It Pawley-checks each cell against the indexed cell, then Rietveld-ranks.
  5. Results appear on the existing Rwp-versus-energy Pareto view.

  The search found no published end-to-end version of this, so it would be both a differentiator and a publishable result. The ZIF study suggests energy-ranking will not be clean for porous frameworks: dense polymorphs win on energy. The MLIP should therefore act as a filter, rejecting high-energy or unphysical candidates, not as the judge.
- Xrd2Mof's MIT code could feed candidates into the same Rietveld+MLIP ranker as an optional generator, once its data licence is resolved.
- Thresholds such as an energy window for porous polymorphs, and how guests or solvent are treated in the fit, are chemistry decisions for Julius.

### Gaps
- No COF-specific structure-from-PXRD solver was found beyond the existing pyCOFBuilder stacking-plus-PXRD comparison noted in the earlier survey.
- No benchmark of topology enumeration against experimental MOF patterns was found. The search found no published experimental MOF benchmark set for any method.
- A dedicated search for "reticular" plus "Rietveld" plus "MLIP" papers in the last two months might still turn something up. One extended search did not.

## 4. Automated phase identification and quantification: accuracy and critiques

### Takeaway
Dara is now MIT-licensed, pip-installable, and has been run on more than 2,400 A-Lab patterns with a median of 89 s each. It uses **BGMN** as its refinement engine, which matters for licensing and for the app's Mac build constraints. The A-Lab critique (Leeman, …, Schoop, Palgrave; PRX Energy 2024) concluded that **automated Rietveld is not yet reliable** and that disorder is often neglected. Any automated phase-ID mode must therefore present alternatives and Rwp evidence, not a single verdict.

### Cited Findings
- **Dara** ("Data-driven Automated Rietveld Analysis") performs automated phase search **with BGMN**. It is **MIT licensed**, installs with `pip install dara-xrd`, and includes a browser server (`dara server`, localhost:8898). Paper: Chem. Mater. 2026, DOI 10.1021/acs.chemmater.5c02820. — [GitHub](https://github.com/CederGroupHub/dara)
- Dara accuracy on **commercial mixtures [EXP]**: **18/20 with 2-min scans, 20/20 with 8-min scans**. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- Dara at scale: deployed at A-Lab, it processed **more than 2,400 experimental patterns at a median 88.9 s**. It cannot reliably identify phases missing from databases, disordered materials or poorly represented metastable phases. — [AI Agent 2026](https://www.oaepublish.com/articles/aiagent.2026.25)
- **RADAR-PD** (APL Machine Learning 2026, 291 RRUFF patterns [EXP]) reportedly beat Dara on impurity recovery; no rate is given. It is built on GSAS-II. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **GALAXI** (Szymanski group, arXiv 2026, **MIT**): micro-F1 **0.935 after refinement on 61 pristine experimental patterns**. **MatDiffract**: 91.3% top-1 on 875 single-phase experimental patterns, 85.0%/70.0% on mixtures; it is a public service with no verified source. **AIF** (hackingmaterials): the top interpretation was chosen in 93% of 30 blinded experimental cases; no licence declared. **AutoXRD** (agentic): mean score **57.8/100** over 1,340 runs. **Gan Jiang**: 81.78% RRUFF but **40.83% opXRD** [EXP]. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)
- **A-Lab critique** (Leeman, Liu, Stiles, Lee, Bhatt, Schoop, Palgrave, PRX Energy 2024):
  - **Case study:** the A-Lab paper (Szymanski et al., Nature 2023), which reported 41 of 58 targets over 17 days.
  - **Conclusions:** **automated Rietveld analysis of PXRD is "not yet reliable"**; the authors call for a reliable AI Rietveld tool. Disorder is often neglected in predictions.
  - **Press summary:** Chemistry World reported the conclusion that "no new materials have been discovered".
  - **Response:** Ceder acknowledged gaps and said the team aimed to address the concerns.
  — [Princeton record](https://collaborate.princeton.edu/en/publications/challenges-in-high-throughput-inorganic-materials-prediction-and-/); [NSF PAR](https://par.nsf.gov/biblio/10532478); [Nature news](https://www.nature.com/articles/d41586-023-03956-w); [Chemistry World](https://www.chemistryworld.com/news/new-analysis-raises-doubts-over-autonomous-labs-materials-discoveries/4018791.article)
- **QualX** (GPL-3.0 vs LGPL-3.0 conflict) and **RAPID** (J. Appl. Cryst. 2026; GPL-3.0; Windows-only) are other open phase-ID tools. — [awesome list](https://github.com/xyin-anl/awesome_pxrd2xtal_generation)

### Inferences
- Dara's MIT code is reusable, but its BGMN dependency is a compiled binary. Given the Mac's no-developer-tools constraint and the app's RietX engine, the earlier plan still holds: **reimplement Dara's tree search over RietX** rather than ship BGMN.
- The A-Lab lesson maps onto features the app already has. Always show the runner-up hypotheses, their Rwp and their MLIP energies. Flag possible disorder or solid solutions. Never auto-label a phase "new".
- The opXRD vs RRUFF drop for Gan Jiang (82% to 41%) is a useful warning: RRUFF minerals are an easy test set.

### Gaps
- BGMN's licence and macOS build status were not checked.
- No head-to-head of Dara against commercial Match!, HighScore or CrystalDiffract Phase ID was found.
- Whether the A-Lab authors formally revised their claims was not settled by the sources retrieved.

## 5. 3D ED / microED and PDF total scattering: open tools and ML; relevance to nanocrystalline MOFs and amorphous carbons

### Takeaway
The 3D ED chain relies on Windows-only or non-redistributable programs (PETS, XDS, SHELXT), with Python tools such as AutoLEI and edtools only wrapping them. It belongs outside a desktop builder; at most the app should import CIF and hkl files from it. For PDF, ML structure solution is still limited to nanoparticles (DeepStruc, 2022) and motif extraction. The search found no ML PDF-to-structure method for MOFs or amorphous carbons. The realistic in-app feature is **forward G(r) simulation plus fitting** of the app's own models, with RMCProfile export as noted in the earlier survey.

### Cited Findings
- **AutoLEI** is an open-access Python 3D ED/microED pipeline, available on PyPI, GitLab and Zenodo. It needs **XDS** installed and runs on **Linux or WSL**. Its demos include the **MOF SU-100**. — [IUCrJ 2026](https://journals.iucr.org/m/issues/2026/01/00/jf5003/); [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12809502)
- **PETS 2.0** is **Windows-only**. On the MOF ICR-2, its frame-orientation refinement located **13 of 15 hydrogens**. **edtools** is pip-installable but documented for Windows 10+, and prepares SHELXT input. The typical chain is PETS for reduction, edtools, SHELXT for solution, SHELXL for refinement, with Olex2 as GUI. — [cRED guide](https://iverks.github.io/crysm/cred_guide.pdf); [edtools](https://edtools.readthedocs.io/)
- **DeepStruc** (Kjær, Anker, Jensen et al., Digital Discovery 2023; NeurIPS AI4Mat 2022) is a conditional VAE that takes a PDF and outputs atomic coordinates. It was trained on seven monometallic nanoparticle types and tested on **simulated and experimental PDFs**. Where the PDF does not fix a unique structure, it supplies a distribution of starting models. — [PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9923795/); [RSC](https://pubs.rsc.org/en/content/articlehtml/2022/dd/d2dd00086e)
- The Billinge group published explainable ML for extracting structural motifs from PDFs of disordered Mo oxides, trained on candidate motifs and their Rwp. The same group has an ML method for space-group determination from PDFs. — [OSTI](https://www.osti.gov/pages/servlets/purl/2423433)
- A multivariate analysis of PDFs fingerprinted crystalline, disordered and amorphous forms of compositionally identical MOFs. — [Nat. Commun.](https://www.nature.com/articles/s41467-022-29849-6)
- A 2025 npj Computational Materials **diffusion model for amorphous structures** was validated against partial PDFs on SiO₂ and Cu–Zr, not on MOFs or carbons. — [npj Comput. Mater.](https://www.nature.com/articles/s41524-025-01901-1)
- pyobjcryst ships in the **diffpy.cmi** collection, the diffpy PDF-modelling ecosystem. — [libraries.io](https://libraries.io/pypi/pyobjcryst)
- From the earlier survey: RMCProfile accepts LAMMPS ML potentials as a hybrid-RMC constraint. — [PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11611278/)

### Inferences
- For nanocrystalline MOFs and ZTCs, the defensible 1.2-era capability is "compute S(Q) and G(r) of my model and overlay the measured PDF, with a small-box refinement". That is diffpy-style fitting, not ML solution. ML PDF-to-structure has not been shown on frameworks or carbons.
- 3D ED would chain only at the CIF level. A solved ED structure goes into the app for MLIP checks and simulated PXRD. Building 3D ED into the app is not justified: the tools are Windows- or Linux-bound and depend on XDS and SHELX.

### Gaps
- diffpy-CMI and diffpy.srreal licences, and their install status on macOS arm64 with Python 3.10+, were not verified in this pass.
- eTOX could not be found in any search; its status is unknown.
- No 2025–2026 ML PDF-to-structure work specific to MOFs or amorphous carbons was found after two searches.

## 6. How "pattern in, structure out" would chain with the existing indexing → Pawley → Rietveld

### Takeaway
Every successful method in 2025–2026 follows the same pattern: generate candidates (symmetry enumeration, global optimisation, ML generator or topology builder), then refine each one with Rietveld, then filter by energy and chemistry. Crystal Builder already owns the outer stages: indexing, Pawley, RietX, MLIP energies and the Pareto view. The 1.2 feature is therefore mostly a candidate generator plus orchestration, not a new refinement engine.

### Cited Findings
- **RealPXRD-Solver:** lattice-conditioned generation, then GSAS-II Rietveld, which it calls essential; solved at Rwp < 15%. — [arXiv](https://arxiv.org/html/2603.00965v1)
- **Ab-PXRD-Solver:** indexing, Wyckoff enumeration, MACE relaxation, cross-correlation screen, then GSAS-II Rietveld, with energy as a secondary criterion. — [arXiv](https://arxiv.org/html/2605.24594v1)
- **GALLOP:** Pawley-extracted intensities from GSAS-II, TOPAS or DASH, then particle swarm with local optimisation. — [GitHub](https://github.com/mspillman/gallop)
- **PXRDGen:** generator plus Rietveld module. — [Nat. Commun.](https://www.nature.com/articles/s41467-025-62708-8)
- **Xrd2Mof:** diffusion over coarse-grained nodes and linkers, assembly, force-field relaxation, then pattern ranking. — [AI Agent 2026](https://www.oaepublish.com/articles/aiagent.2026.25)
- **Dara:** tree search over database phases, each validated by BGMN Rietveld. — [GitHub](https://github.com/CederGroupHub/dara)

### Inferences
- **Proposed 1.2 headline: a "Solve" panel with three tiered back-ends, all feeding one ranking stage.**
  - **Shared ranking stage:** RietX Rwp plus MLIP energy plus diagnostics, shown on the Pareto plot.
  - **(a) Known-phase search (Dara-style over RietX + fetch).** Most reliable; inorganic. **Ship first.**
  - **(b) Symmetry-enumeration solve (Ab-PXRD-Solver-style using the app's indexer, PyXtal and in-process MACE).** For small inorganic cells. CPU runtime is minutes to hours, so it needs a background job with progress. Monoclinic and large cells are weak (60% monoclinic).
  - **(c) Reticular solve (topology enumeration plus PORMAKE-style build, MLIP filter, Rietveld rank).** For MOFs. **Novel, and the search found no published equivalent.** Plays to the app's strengths and is a publishable result.
  - **Optional plugins:** ML generators (RealPXRD-Solver, XRDSol, Crystalyze, Xrd2Mof) and GALLOP for molecular crystals. Ship them as bring-your-own-weights because of licence gaps.
- **Reliability framing for UI copy:**
  - Measured-data success is about 40–80% top-1 even for the best small-cell inorganic methods, and lower for novel structures.
  - The app should present ranked hypotheses with evidence, never one answer. This follows the A-Lab lesson and RealPXRD-Solver's own reliance on refinement.
- **Material-class fit:**
  - Inorganic: strong for (a) and (b).
  - MOF: only (c) and Xrd2Mof exist, and neither has been benchmarked on experimental data.
  - Molecular: GALLOP or FOX. Out of the app's core scope; offer an export or plugin.
  - Amorphous or nanocrystalline (ZTCs, nano-MOFs): PDF forward-modelling, not solution.

### Gaps
- RietX's ability to batch-refine tens to hundreds of candidates in an acceptable desktop time was not measured; this needs a local benchmark.
- No experimental MOF PXRD benchmark set was found for validating route (c). One would need to be assembled, for example from CSD-matched measured patterns; Julius's judgement is needed on which.
