# Porous-framework computational workflows: from built structure to a property a chemist cares about (for Crystal Builder 1.2)

Research date: 2026-11-06. Builds on the prior survey (`reports/Crystal Builder feature landscape.md`, 2026-10-09), whose adsorption section already established: RASPA3 is MIT, has PyPI wheels for Apple silicon, Intel macOS and Linux as of v3.0.30 (31 May 2026); gRASPA needs CUDA/SYCL (no Mac); MLIP-MC (arXiv 2602.13725) does Python GCMC/Widom on any MLIP; AdsorpQC v1.0.0 (Sept 2026) and pyMSER handle equilibration detection and isotherm fitting; iRASPA is a visualiser; nanoHUB RASPA tools are browser teaching apps; no surveyed agent system or MCP server runs adsorption. This pass did not re-verify those facts except RASPA3 releases. About 19 tool calls were used, so several questions remain partially open (see Gaps).

## 1. What do typical 2025–2026 MOF/COF computational papers compute, and with which tools?

### Takeaway
The dominant pipeline in 2025–2026 is still: curated or built CIF → validity check → (UFF/DFT or now u-MLIP) relaxation → Zeo++ geometry → charges (DDEC6/REPEAT for accuracy, Qeq/EQeq or ML charges for speed) → RASPA Widom/GCMC → isotherm fitting/IAST/process metric, with ML stability filters bolted on. The newest change is u-MLIPs entering the adsorption step itself (Widom energetics, flexibility), not only the relaxation step. I found no quantitative frequency survey of which steps papers use.

### Cited Findings
- CoRE MOF 2024/2025 (Zhao et al., Matter 2025) curates >40,000 experimentally reported MOFs, adds ML-predicted stability, heat capacity, ML-assigned DDEC6 charges, GEMC-based hydrophobicity classes and MOFid, then runs temperature-swing adsorption simulations and identifies candidates predicted to outperform CALF-20. This is the canonical "full pipeline" paper of 2025 — [Matter PDF, DOI 10.1016/j.matt.2025.102140](https://www.coudert.name/papers/10.1016_j.matt.2025.102140.pdf); details summarised in prior survey notes (reticular_literature.md).
- Bonakala, Wahiduzzaman, Watanabe, Hamzaoui and Maurin (Chem. Sci. 2026, 17, 12084, published 5 May 2026) screen a large MOF database for ethylene capture with Widom insertion MC using UFF, then re-evaluate 88 UFF-selected candidates with the PFP universal MLIP and benchmark against DFT. Full unit-cell relaxation (flexibility) shifted ethylene affinity by up to 20 kJ/mol; they conclude u-MLIP treatment of host–guest energetics and flexibility is essential for reliable rankings — [Chem. Sci. landing page](https://pubs.rsc.org/en/Content/ArticleLanding/2026/SC/D6SC00831C) (via search summary; full text returned HTTP 403). Note: PFP is the commercial Matlantis potential, not open.
- MLIP-MC preprint (arXiv 2602.13725, Feb 2026) reports that all universal models tested exhibit systematic biases, consistently over- or under-estimating adsorption energetics, implying zero-shot u-MLIPs may need fine-tuning for quantitative CO2 work — [arXiv 2602.13725](https://arxiv.org/abs/2602.13725) (claim taken from search summary, not re-read in full this pass).
- End-to-end discovery loop (JACS, DOI 10.1021/jacs.6c07479, 2026): data mining → ML adsorption prediction → structure generation → synthesis of two new Zn MOFs for ambient CH4 adsorption, framed as an extensible platform — [CiteDrive record](https://www.citedrive.com/en/discovery/end-to-end-discovery-of-mofs-for-ambient-ch4-adsorption/) (abstract-level only).
- Open DAC 2025 (arXiv Aug 2025) is a dataset plus MLIPs evaluated on adsorption energies and Henry coefficients — i.e. MLIPs are now benchmarked on Henry coefficients, not only on structure — [arXiv 2508.03162](https://arxiv.org/pdf/2508.03162) (search summary).
- 2026 Materials Horizons review (Gómez-Gualdrón, Pak et al.) on data efficiency in ML for MOFs explicitly aims to make ML-aided MOF design "accessible to both theorists and experimentalists" — [Mater. Horiz. 2026, d5mh01467k](https://pubs.rsc.org/en/content/articlehtml/2026/mh/d5mh01467k).
- Flexibility via fine-tuned MACE is now a Chem. Sci. topic: MIL-120 work fine-tunes a pretrained MACE and finds CO2 induces local configurational rearrangements that reshape the pore — [Chem. Sci. 2026, d5sc09058j](https://pubs.rsc.org/en/content/articlelanding/2026/sc/d5sc09058j); [EPFL LSMO summary](https://www.epfl.ch/labs/lsmo/machine-learning-potential-for-modelling-dynamic-hydrogen-bond-networks-in-mof-mil-120/).

### Inferences
- Crystal Builder already covers the left half of this pipeline (build, net ID, relax with MACE/ORB/MatterSim, Zeo++). The first step it is missing in every paper above is the adsorption calculation (Widom → Henry/Qst, then GCMC isotherm). Charges are the hidden prerequisite.
- The Maurin 2026 paper's "classical screen, then MLIP re-score" structure maps unusually well onto an app that already has both UFF4MOF and three MLIPs: Widom with UFF + charges, then optionally re-score top candidates' insertion energies with the MLIP in a relaxed cell.

### Gaps
- No systematic survey with frequencies of which computations 2025–2026 MOF/COF papers report (e.g., "x% run GCMC, y% DFT"). I did not find one; the report should not quote a percentage.
- COF-specific and zeolite/ZTC-specific workflow papers from 2025–2026 were not searched this pass (time budget).

## 2. Adsorption tooling: RASPA3, gRASPA, MLIP-GCMC, ML surrogate isotherms, charges

### Takeaway
RASPA3 is pip-installable on macOS arm64 and is the obvious engine; charges are the gating input and there are now two fast, open ML charge models (PACMOF2, MIT; MEPO-ML, ~2 s/MOF on one CPU core, licence unstated). ML isotherm surrogates exist but are gas- and temperature-specific and not a substitute for running GCMC on a novel built structure.

### Cited Findings
**RASPA3**
- Releases page: v3.0.30 (31 May 2026) is the latest; earlier 2026 releases v3.0.20 (17 Jan) through v3.0.29 (7 May) — roughly monthly cadence, but nothing new since 31 May 2026 as of 6 Nov 2026 — [GitHub releases](https://github.com/iRASPA/raspa3/releases).
- Platforms: Linux Arch packages (aarch64, x86_64 AVX2/AVX-512) and RPMs (EL6/7/10); changelog lists PyPI packages for Apple silicon and Intel macOS; changelog mentions `raspalib` win-arm64 support; no Windows x86_64 installer visible on the page — [GitHub releases](https://github.com/iRASPA/raspa3/releases).
- Python bindings (`raspalib`) are built as an abi3 stable-ABI package for Python ≥3.12; binding layer changed (v3.0.26 "only use native pybind11"; v3.0.30 fixes "nanobind" bindings) — [GitHub releases](https://github.com/iRASPA/raspa3/releases). Licence MIT per [JCP 2024](https://pubs.aip.org/aip/jcp/article/161/11/114106/3312873/RASPA3-A-Monte-Carlo-code-for-computing-adsorption) (prior survey).

**Partial charges**
- PACMOF2 (Snurr group): MIT licence (sidebar + LICENSE file); separate `PACMOF2_neutral` and `PACMOF2_ionic` models (ionic needs a net charge argument); tested with Python 3.9, pinned pymatgen 2023.10.4, ASE 3.22.1, scikit-learn 1.3.2; models and DDEC6 training data on Zenodo 12747095 and fetched via huggingface-hub; install from source (`pip install -e .`), no PyPI release noted; runtime per structure not stated — [GitHub snurr-group/pacmof2](https://github.com/snurr-group/pacmof2).
- MEPO-ML (Woo lab, npj Comput. Mater. 2024): graph attention network trained on ARC-MOF (279,632 MOFs, >40 M charges), reference = REPEAT (periodic-DFT ESP-fitted) charges, MAE 0.025 e on >27k test MOFs; "less than two seconds on average" on a single CPU core, GAT inference <0.4 s; 27,996 MOFs in 3 h on 12 cores — [PMC11412901](https://pmc.ncbi.nlm.nih.gov/articles/PMC11412901/).
- MEPO-ML adsorption errors vs REPEAT (MAD): CO2 uptake (15:85 CO2/N2, 1 bar, 298 K) 0.059 mmol/g vs 0.206 for empirical SQE-MEPO; CO2/N2 selectivity 3.06 vs 7.52; H2S at 1 bar 0.25 vs 1.23 mmol/g — [PMC11412901](https://pmc.ncbi.nlm.nih.gov/articles/PMC11412901/).
- MEPO-ML code is at github.com/uowoolab/MEPO-ML with the pretrained model; the paper states no software licence (CC BY 4.0 covers only the article) — [PMC11412901](https://pmc.ncbi.nlm.nih.gov/articles/PMC11412901/). Licence on the repo itself not verified.
- PACMAN (2024, crystal-graph CNN trained on QMOF) reports test MAE 0.0055 e — [AIChE 2024 abstract](https://proceedings.aiche.org/conferences/aiche-annual-meeting/2024/proceeding/paper/612i-pacman-robust-partial-atomic-charge-predicter-nanoporous-materials-based-on-crystal-graph) (search summary; licence not checked).
- Charge equilibration quality depends strongly on algorithm and parameters: Qeq vs DDEC compared over 2,338 MOFs — [Materials Cloud record](https://archive.materialscloud.org/records/65/export/json).
- Liu & Luan (Nanoscale 2022) benchmarked CM5, Mulliken, Qeq, EQeq and PACMOF (v1) against DDEC on a MOF subset — [Nanoscale 2022, d2nr00354f](https://pubs.rsc.org/en/content/articlehtml/2022/nr/d2nr00354f).
- Older experimental comparison: Wilmer et al. compared CO2 isotherms of 12 MOFs with Qeq, EQeq, ChelpG and REPEAT charges; ChelpG best, EQeq comparable; separately, selectivities can differ significantly between EQeq and DDEC charges — summarised in [PMC6328974 review](https://pmc.ncbi.nlm.nih.gov/articles/PMC6328974) (secondary source).

**ML isotherm surrogates**
- 2025 ML isotherm work is gas- and condition-specific: a GNN for CO2/CH4 isotherms with fitted isotherm models (SKKU, 2025, [LAPSE 2025.0450](https://psecommunity.org/LAPSE:2025.0450)); IsothermNet (npj Comput. Mater., July 2025) predicts CO2 heat of adsorption and links it to isotherm type; a 2023 multi-adsorbate model used Henry constants at 300 K only — [Georgia Tech repository](https://repository.gatech.edu/entities/publication/1d2ef6e2-4bda-48d5-adb0-dc8e4c00f498); [PMC10544990](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10544990/). No temperature- and pressure-general universal isotherm predictor was found.

### Inferences
- Charges are the step most likely to silently ruin a GUI isotherm for polar guests (CO2, H2O, H2S). MEPO-ML's 3.5× smaller CO2 uptake error than an empirical scheme, at ~2 s per structure on CPU, makes an ML charge model the right default candidate to propose to Julius alongside the existing EQeq. Which one is a chemistry call (REPEAT-trained MEPO-ML vs DDEC6-trained PACMOF2).
- PACMOF2's Python 3.9 / pymatgen 2023 pins vs raspalib's Python ≥3.12 requirement is a likely packaging conflict; it would need testing or vendoring the model.
- ML isotherm surrogates do not fit a builder app: they are trained on database MOFs and fixed conditions, while Crystal Builder's users build new structures. Running Widom/GCMC directly is the more honest feature.

### Gaps
- Whether RASPA3 runs on Windows x86_64 via pip was not confirmed (only win-arm64 mention). CPU runtimes for a typical RASPA3 Widom (Henry coefficient) or a 10-point isotherm on Apple silicon were not found; the report should say "unmeasured" or have someone time one.
- MEPO-ML repo licence; EQeq reference-code licence; PACMOF2 runtime per structure; whether PACMOF2/MEPO-ML handle COFs, zeolites or ZTCs (both are trained on MOFs; zeolites/carbons usually use force-field charges or none).
- gRASPA current status and any Metal backend was not re-checked.

## 3. GUI tools that take an experimentalist from structure to isotherm without scripting — and what they lack

### Takeaway
The only GUI found that does structure → GCMC isotherm end to end is commercial (SCM AMS; Materials Studio Sorption/MAPS are commercial as well but were not re-checked), and its own tutorial uses ReaxFF, freezes the host manually, needs hand-computed chemical potentials and warns of multi-day runs. Free GUIs cover only the ends of the pipeline: visualisation (iRASPA), BET analysis of an isotherm (BETSI, SESAMI) and isotherm fitting/IAST (AIM). Nobody open joins them.

### Cited Findings
- SCM AMS GCMC tutorial (IRMOF-1 + CO2): workflow is build/optimise CO2 with ReaxFF → import and optimise host → compute chemical potential μ(T,P) by hand from NIST JANAF/Shomate data (table given for 5–30 bar) → choose GCMC task, freeze framework via a region constraint, set 100,000 iterations → monitor with an analysis script and stop manually — [SCM tutorial](https://www.scm.com/doc/Tutorials/MolecularDynamicsAndMonteCarlo/GCMCMOFIsotherm.html).
- Same tutorial: "The calculation of the full isotherm on IRMOF-1 can take several days to converge"; suggests a fragment with 8× fewer atoms; admits "the GCMC is not fully converged" at the reported point (~17 mol/kg vs ~19 experimental); warns that changing units after typing μ silently converts the value — [SCM tutorial](https://www.scm.com/doc/Tutorials/MolecularDynamicsAndMonteCarlo/GCMCMOFIsotherm.html). AMS is commercial (pricing/free trial links); licence terms not stated on the page.
- AIM (arXiv 2504.20713, 2025): MATLAB-based GUI for isotherm fitting, mixture prediction (IAST, extended Langmuir), isosteric heat estimation and breakthrough simulation, no coding — operates on isotherm data, not on structures — [arXiv 2504.20713](https://arxiv.org/abs/2504.20713).
- SESAMI is a web tool for BET surface area from an isotherm — [JOSS 05429 PDF](https://www.theoj.org/joss-papers/joss.05429/10.21105.joss.05429.pdf) (search summary).
- MOFSimplify (Kulik group, Sci. Data 2022) web interface predicts solvent-removal stability (accuracy 0.76, AUC 0.79) and thermal decomposition temperature (MAE 47 °C) from RAC fingerprints of a CIF; water stability deliberately excluded — [PMC8917177](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8917177/).
- Sholl-group (2019/2020) paper explicitly asked what would happen if screening workflow infrastructure were made available to experimental groups — [PMC7706098](https://pmc.ncbi.nlm.nih.gov/articles/PMC7706098).
- (Prior survey) iRASPA describes itself as a visualiser; nanoHUB RASPA tools are browser teaching apps — [iraspa.org](https://iraspa.org/); [ACS Omega](https://pubs.acs.org/doi/full/10.1021/acsomega.2c06978).

### Inferences
- What the commercial GUI path lacks, and an open desktop app could supply: (a) automatic chemical potential / fugacity (Peng–Robinson, as RASPA does internally) instead of hand-computed μ; (b) generic force field + charges defaulting sensibly for MOFs (UFF/DREIDING LJ + TraPPE guests + ML charges) rather than ReaxFF; (c) automatic equilibration detection instead of eyeballing; (d) cell replication to satisfy the cutoff automatically; (e) Widom/Henry first, so the user gets a number in minutes before committing to an isotherm.
- An open, local, Mac-native "built structure → Henry coefficient/Qst → short isotherm → fit → BET" chain does not appear to exist anywhere. That is the clearest whitespace found.

### Gaps
- Materials Studio Sorption, Scienomics MAPS, AiiDAlab isotherm app and current iRASPA state were not re-checked in this pass (a search for iRASPA returned only unrelated results). Their current pricing, platforms and features should not be asserted without checking.
- No user survey of experimental reticular chemists' software use was found.

## 4. Comparing a simulated isotherm with a measured one (BET from simulated N2/Ar)

### Takeaway
There is a long-standing, well-cited method: compute N2 (77 K) or Ar (87 K) isotherms by GCMC, apply the BET consistency (Rouquerol) criteria to the simulated isotherm, and compare simulated BET area with experimental BET area rather than with geometric surface area. BETSI (MIT, PyQt GUI) is the reproducible implementation, but it only takes a CSV, so nothing connects a simulator to it.

### Cited Findings
- Bae, Yazaydın & Snurr (Langmuir 2010): BET areas from simulated N2/Ar isotherms track geometric accessible surface areas only when the BET range satisfies consistency criteria; the textbook range underestimated every material tested — [peeref record](https://peeref.com/works/13119329); [GCMC study PDF](https://fomms.cache.org/sites/fomms.cache.org/files/2009/I-39.pdf).
- Gómez-Gualdrón et al. (JACS 2016): applying four consistency criteria to simulated N2 isotherms for 25 MOFs, BET can still significantly overestimate monolayer loading in MOFs mixing mesopores and large micropores; they recommend comparing experimental BET with simulated BET, not geometric ASA — [peeref record](https://peeref.com/works/949185).
- Osterrieth et al. (BETSI, 2021/2022): a round-robin of about 60 labs analysing the same isotherms produced widely varying BET areas; BETSI enforces extended Rouquerol criteria for an unambiguous assignment — [ChemRxiv DOI 10.26434/chemrxiv.14291644](https://www.doi.org/10.26434/CHEMRXIV.14291644.V1).
- BETSI: MIT licence; GUI (PyQt5) with drag-in two-column CSV (relative pressure, loading; adsorption branch only); Windows and Linux executables; tested on Windows 10, macOS 10.14, Ubuntu 16.04; pip install only from test.pypi; pinned old dependencies (Python 3.7 suggested); no RASPA/simulated-isotherm input mentioned — [GitHub fairen-group/betsi-gui](https://github.com/fairen-group/betsi-gui).
- Ultra-microporous MOFs/zeolites: a dedicated evaluation of BET for ultra-micropores exists — [catalogue record](https://katalog.dhi-paris.fr/vufind/Record/NLM196545269/Details) (abstract not read).

### Inferences
- "Simulated BET area for my built structure, computed the same way as my instrument" is a property an experimentalist already measures for every new framework, so it is the most direct bridge between a built model and the lab. It also serves as structure validation: a large BET mismatch flags collapse, interpenetration, residual solvent or wrong model — which complements Crystal Builder's existing PXRD/Rietveld comparison.
- Technically it is cheap given RASPA3: N2 at 77 K is a standard GCMC with TraPPE N2 and no strong charge sensitivity (N2 quadrupole is small; Ar has no charge at all), so the charge-model decision is less consequential than for CO2. Then a BETSI-style Rouquerol fit (MIT, can be reimplemented or imported) yields the number. Measured isotherm import + overlay would complete it.

### Gaps
- No 2025–2026 paper quantifying demand for simulated-vs-experimental BET; demand is inferred from the round-robin and standard practice.
- CPU cost of a 77 K N2 isotherm (which converges slowly near pore filling) on a laptop was not found.

## 5. Flexibility, breathing, gate opening: MLIP + GCMC (osmotic ensemble)?

### Takeaway
MLIP-based flexibility in adsorption is active in 2025–2026 (fine-tuned MACE for MIL-120, MLIPs for NbOFFIVE-1-Ni water uptake, MLP + transition-matrix MC for MOF-303, u-MLIP cell relaxation in screening), but I found no MLIP-driven osmotic-ensemble workflow for breathing/gate-opening. It is research-grade and not a GUI candidate for 1.2.

### Cited Findings
- NbOFFIVE-1-Ni (JPCC 2026, Shi group): MLIPs model flexibility and water uptake; rigid-framework GCMC markedly underpredicted water uptake vs experiment — [JPCC 2026 PDF](https://shiresearchgroup.github.io/assets/pdf/JPCC2026.pdf) (search summary).
- MOF-303 water harvesting: MLPs combined with transition-matrix Monte Carlo to account for flexibility (ChemRxiv, Nov 2024 preprint) — [ChemRxiv](https://chemrxiv.org/engage/chemrxiv/article-details/673babd15a82cea2fa945927).
- FFLAME (Digital Discovery 2025): fragment-based training for MLPs transferable across MOFs — [Digital Discovery d5dd00321k](https://pubs.rsc.org/en/content/articlepdf/2025/dd/d5dd00321k).
- Classical osmotic-ensemble treatment of MIL-53(Al) breathing (free energy as function of volume and guest loading) — [core.ac.uk PDF](https://core.ac.uk/download/55716328.pdf) (date unclear; no MLIP).
- Maurin 2026: full cell relaxation with u-MLIP changes ethylene affinity by up to 20 kJ/mol — [Chem. Sci. 2026](https://pubs.rsc.org/en/Content/ArticleLanding/2026/SC/D6SC00831C).

### Inferences
- The tractable flexibility feature for a GUI is the Maurin-style one: relax the cell with an MLIP (already in Crystal Builder), optionally with a guest loading, then rerun Widom/GCMC in the relaxed cell. Crystal Builder's existing quasi-harmonic F(V,T) machinery could in principle feed an osmotic-ensemble free energy F(V) + adsorption term, but that is a research project and a chemistry decision for Julius.

### Gaps
- No MLIP + osmotic-ensemble paper found (search may have missed Coudert/Boutin group output). No GUI tool for breathing/gate-opening found.

## 6. Which single step would an experimental reticular chemist most value in a desktop app?

### Takeaway
The evidence points to "built structure → adsorption numbers" as the headline, scoped to what converges on a laptop: Widom Henry coefficient + isosteric heat for CO2/CH4/N2/H2O, a short GCMC isotherm, and a simulated N2-77 K BET area overlaid against the user's measured isotherm. Charges (an ML charge model) are the necessary sub-feature; defects, stability prediction and osmotic flexibility are secondary.

### Cited Findings
- Adsorption is the property most screening and discovery papers end on (CoRE MOF 2025 TSA screening; Maurin 2026 ethylene capture; JACS 2026 CH4 discovery loop) — [Matter 2025](https://www.coudert.name/papers/10.1016_j.matt.2025.102140.pdf); [Chem. Sci. 2026](https://pubs.rsc.org/en/Content/ArticleLanding/2026/SC/D6SC00831C); [JACS 10.1021/jacs.6c07479](https://www.citedrive.com/en/discovery/end-to-end-discovery-of-mofs-for-ambient-ch4-adsorption/).
- The only GUI end-to-end path found is commercial and takes "several days" for one MOF isotherm with manual μ and convergence checks — [SCM tutorial](https://www.scm.com/doc/Tutorials/MolecularDynamicsAndMonteCarlo/GCMCMOFIsotherm.html).
- Experimental BET areas vary widely between labs for the same data; the field recommends comparing experimental with simulated BET — [BETSI ChemRxiv](https://www.doi.org/10.26434/CHEMRXIV.14291644.V1); [Gómez-Gualdrón JACS 2016](https://peeref.com/works/949185).
- Reviews in 2026 explicitly target accessibility for experimentalists — [Mater. Horiz. 2026](https://pubs.rsc.org/en/content/articlehtml/2026/mh/d5mh01467k).
- ML stability models exist as a web tool already (MOFSimplify, MAE 47 °C thermal; solvent-removal AUC 0.79), so stability prediction is less of a gap — [PMC8917177](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8917177/).

### Inferences
- Ranking of candidate 1.2 headline steps, by (unmet need for experimentalists) × (feasibility on macOS arm64 with existing deps):
  1. **Adsorption panel on RASPA3 (`raspalib` wheel)**: Widom → Henry coefficient/Qst at infinite dilution (minutes), then GCMC isotherm with auto-fugacity, auto-replication and equilibration detection (AdsorpQC/pyMSER), Langmuir/Toth fit, CSV export. Unique among open desktop tools; directly consumes Crystal Builder's built/relaxed structures.
  2. **Simulated N2/Ar BET + overlay with measured isotherm** (Rouquerol fit à la BETSI, MIT): the most "experimentalist-native" output and a structure-validation check; naturally a sub-feature of (1).
  3. **ML partial charges** (MEPO-ML ~2 s/MOF CPU, or PACMOF2 MIT): prerequisite for polar guests; small on its own.
  4. MLIP re-scoring of Widom energies / relaxed-cell GCMC (Maurin 2026 pattern): differentiator once (1) exists; u-MLIP bias caveat (MLIP-MC) means it should be labelled as such.
  5. Defect builder, stability prediction, osmotic breathing: valuable but either covered elsewhere (MOFSimplify) or research-grade.
- Choice of guest models, LJ parameters (UFF vs UFF4MOF vs DREIDING), charge scheme defaults and cutoff are chemistry decisions for Julius (per project memory); the app should expose them with presets, not hard-code them.

### Gaps
- No direct survey or interview data on what experimental reticular chemists want from software was found; the ranking is inferred from paper content, tool gaps and the BET reproducibility literature.
- Laptop CPU runtimes for RASPA3 Widom/GCMC on typical MOFs were not found and should be measured before scoping the feature.
