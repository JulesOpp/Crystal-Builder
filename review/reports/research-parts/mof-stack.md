# Sub-research: MOF-specific software stack (condensed by coordinator)

## Strongest signals
- **Structural validation is a field-wide crisis**: CoRE2014 38% error; >40% across 14 databases / 1.9M structures (JACS 2025, oxidation-state check); "over half of top-performing screening candidates contain structural errors" (Israel J Chem 2026 "Hunting Structural Demons"). **mofchecker** (lamalab-org, RSC DD 2023/2025) is validation-only: duplicates, overlaps, missing H/counter-ions/linkers, oxidation states via OxiMACHINE, porosity via zeopp PLD 2.4 Å. Nothing desktop does this at import time.
- **LAMMPS export is unowned**: lammps-interface has "New maintainer wanted!" (#61), Zr in UiO-66 gets 0 neighbours (#70), requires P1; cif2lammps archived Apr 2024. CB already has the graph + UFF/UFF4MOF typer — the hard part of both tools.
- **GCMC hand-off has no GUI**: RASPA3 (2024 C++23 rewrite, no Python packaging #32, no warning when cell < cutoff #65); gRASPA GPU; Zeo++ can emit **blocking spheres** and per-channel dimensionality that CB does not expose. coudertlab/simple-adsorption-workflow, MatKit, CoRE-MOF-Tools are all hand-glue scripts for CoRE→Zeo++→RASPA.
- **Workflow glue is a research topic**: MOFA (2025, Colmena/Parsl), SimMOF (2026 KAIST LLM agents), SciToolAgent — built because "manual workflow construction requires expert decisions for tool interoperability and preparation of computation-ready structures".
- **Defects / find-and-replace**: MOFun (WilmerLab) periodic substructure find-and-replace (functional groups, solvent, vacancies) — lightly maintained; MOFBuilder (2026) missing-linker/-node + multivariate + OpenMM/GROMACS topologies.
- **PORMAKE upstream gaps** (all open issues): multi-linker (#33), random/combinatorial generation (#32), 2D topologies (#29), MOFDecomposer reverse op (#25), random linker rotation about the 2-point axis, Python 3.12 dep conflicts (#36). Forks add single-metal nodes and coplanarity for π-d MOFs. No interpenetration control anywhere.
- **ToBaCCo**: 424 curated topologies; MOF-5 derivatives have "excessively long bonds" (#19); ToBaCCo structures have poor synthesizability until relaxed (MOFSynth) — argues for CB's build→relax loop.
- **MOFid/MOFkey**: canonical identifier (SMILES + RCSR + catenation); silent UNKNOWN/ERROR; no 3D. Useful for dedup and naming.
- **Databases**: CoRE MOF 2025 (Matter) 40k+; QMOF 20k DFT (band gaps, charges, bond orders — no trajectories); CSD MOF collection 12.5k free CC-BY-NC-SA (no redistribution). All are import sources CB lacks.
- **MOFsimplify**: ANN stability/decomposition-T with uncertainty; returns ground truth if in training set.
- **Zeo++ features unused**: `-block` blocking spheres, channel segmentation/dimensionality per channel, probe-occupiable volume, `-ha` high accuracy, stochastic ray tracing.
- **Force fields beyond UFF**: cif2lammps had MZHB (zeolites), ZIFFF (ZIFs), Dreiding — framework-class FFs CB lacks.
