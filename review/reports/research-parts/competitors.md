# Sub-research: competitors and neighbours (condensed by coordinator)

> **Written 2026-09-18** against `Crystal-Builder` at commit `3cd15e2` (v0.2.1), the base of branch `features/deep-review`. `origin/main` has since moved to `fb38d25`. Line numbers, measurements and code references below were true at `3cd15e2` — re-verify before acting on one if the file has changed since.


| Tool | Has that CB lacks | Recurring complaints |
|---|---|---|
| VESTA | 30 in / 13 out structure formats, 17 volumetric formats, isosurfaces of charge density/ELF, thermal ellipsoids, crystal morphology, 25y polish, cited everywhere | macOS crashes on open / standardize / .xsf; "opens but no structure appears"; lock-file corruption; cannot cut along arbitrary plane; not scriptable |
| Materials Studio | Unified env: CASTEP, DMol3, Forcite, Adsorption Locator, polymer builder; HPC job submission from GUI; vendor support | $5k–$54k/yr; U-Michigan dropped licence 2025 for low use; Forcite gives inconsistent energies; DMol3/CASTEP crash "without any message" |
| CrystalMaker / CrystalDiffract / SingleCrystal | Multi-phase **Rietveld refinement** against measured patterns; live-linked single-crystal diffraction + Brillouin zone / stereographic projection; teaching content | Commercial ($99 student+); few public complaints |
| Mercury (CCDC) | CSD access (1.25M structures); packing / H-bond propensity / void surfaces / Miller planes; 3D-print export | Disorder display poor (two CCDC blog posts of workarounds); atom labelling cumbersome; free tier crippled (750 structures, no editing, no voids) |
| Diamond | Polyhedral rendering for inorganics; DiamDoc metadata; 30 years | Windows-only; vendor's own known-bugs page lists crashes on table click, toolbar move, registry, measurement |
| Olex2 | Full solution+refinement (SHELX), CIF→publication docs, ESDs, voids | SHELX path/setup friction; crashes on shutdown; silent refinement failures |
| Avogadro 2 | Plugin ecosystem, input generators for many QM codes, modern GL renderer (AO/reflections) | Many crash issues on GitHub (layers, measure >2 atoms, drag-bond); >10k atoms unstable; crystal support lags 1.x |
| ASE GUI | Thin front-end over dozens of calculators; trajectory animation | Tkinter: dated, no antialiasing, freezes on long ops |
| OVITO | 100M-atom rendering, analysis-modifier pipeline (CNA, DXA), ray-traced renders (Pro), Python modifiers in GUI | Pro pricing; trial programme discontinued; docs overwhelming |
| Jmol/JSmol | Zero-install browser viewer; COD embeds it | Crystal sub-project "lacking manpower"; forks fragmented; 3D-print export wrong for co-crystals |
| pymatgen + Crystal Toolkit | Materials Project DB + API; io for VASP/ABINIT/LAMMPS/QE…; Dash web viewer | CIF parsing bugs (P1 default, unlooped symops → overlapping atoms, #4230 Dec 2024); 502s on web app |
| CrystalExplorer | Hirshfeld surfaces + fingerprint plots; Gaussian/NWChem; now LGPL, xTB backend | EPS export grey pixels; wavefunction import |
| Materials Cloud / AiiDAlab | Hosted workflow apps, band-structure/phonon viewers | Steep onboarding; devs admit research software is hard to install |
| COD | 500k open structures, bulk download, JSmol preview | Quality: wrong non-H, wrong/missing H even in Q1 journals (CrystalX arXiv 2410.13713); 159 fraud cases |

## Things every neighbour has that CB does not (candidate gaps)
1. A structure **database door**: COD / Materials Project / OPTIMADE search-and-open from inside the app.
2. **Volumetric data** (cube/CHGCAR/xsf) isosurfaces — VESTA's raison d'être; CB already marches tetrahedra for pore surfaces, so the machinery exists (PLAN §12 defers it).
3. **Thermal ellipsoids / ADPs** and **disorder** display (Mercury's weakness, an opening).
4. **Arbitrary-plane cut / slab builder** (VESTA cannot; SE question).
5. **Rietveld / pattern fitting** against a measured PXRD (CrystalDiffract) — CB has overlay only.
6. **Publication renders**: ray tracing / AO / POV-Ray export (OVITO, Avogadro, Diamond).
7. **3D-print export** (Mercury, Jmol) — CB has STL via Blender already.
8. **Web/JSmol-style share** of a structure or a scan landscape.
9. **Trajectory viewer** as first-class (ASE, OVITO) — CB has a transport bar.
10. **CIF quality checks** on open (pymatgen bugs, COD errors, MOFChecker) — nobody desktop does this well.
