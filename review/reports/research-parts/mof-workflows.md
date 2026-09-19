# Sub-research: MOF researcher workflows and pain points
(captured by coordinator from sub-agent result, 2026-09-18)

## Key actionable findings
- **PSYMOF** (npj Comp Mater 2025) — automated post-synthetic modification platform: bonding-site selection, functional-group growth at reactive sites, FF assignment, partial charges, MD relaxation. Stated pain: "manual structure editing, chemical intuition, and expertise in force field parameterization." https://www.nature.com/articles/s41524-025-01888-9
- **MOFChecker** (2025) — CIF validation/repair: overlaps from partial occupancy, over/under-coordination, isolated solvent, missing H, missing counter-ions, deleted charged linkers; corrects them. https://pmc.ncbi.nlm.nih.gov/articles/PMC12091091/
- **MOFBuilder** (npj Comp Mater 2026) — end-to-end MD-ready models with systematic defect engineering (missing-linker) "within seconds", for HTS. https://www.nature.com/articles/s41524-026-02086-x
- **MOFSimBench** (npj Comp Mater 2025) — MACE-MP, CHGNet, M3GNet, ORB, SevenNet benchmarked on MOFs; all struggle with charge-dependent props and breathing/flexibility; none uniformly reliable. https://www.nature.com/articles/s41524-025-01872-3
- **MACE-MP-MOF0** (2025) — MOF fine-tune of MACE-MP-0b, 127 curated MOFs, 10x more accurate on geometry/forces/stress.
- **EQeq / EQeq+C** — non-iterative Ewald charge equilibration, seconds not days; EQeq+C fixes high-oxidation-state TM charges (JCTC 2015). EQeq screening vs DDEC: 7/15 false positives (JCTC 2019). Cheap addition beside existing QEq.
- **CIF is broken**: 38% of CoRE2014 structures have significant errors; CSD MOF subset excluded 583 for partial occupancy, 2177 for missing framework H (Chem Sci 2020). Free vs bound solvent removal and charge-balance tracking are the hard bits.
- **Defects**: UiO-66 is the testbed; "Efficient generation of large collections of MOF structures containing well-defined point defects" (PMC10388356).
- **Interpenetration**: no maintained open-source tool; AIChE 2016 collision-check method. Genuine gap.
- **GCMC/RASPA3** (2024): input generation manual (naming patterns, FF folders); FF "chosen off-the-shelf with little validation"; no desktop GUI does it.
- **Breathing MOFs**: MIL-53 canonical; umbrella sampling free-energy profiles; GCMC+MD adsorption-relaxation protocols in LAMMPS — matches the app's relaxed-scan direction. Torsion-aware flow matching for flexible MOF generation (arXiv 2505.17914).
- **Generative**: MOFDiff, MOFGPT, MOFFlow — research code, not tools; gap for a desktop tool that *consumes* generated structures.
- **Foundation MLIPs 2025–26**: ORB-v3, SevenNet(-Nano), UMA (Meta FAIR, June 2025), MatterSim — all ASE-calculator shaped, so they slot into the ENGINES registry the way MACE did.
