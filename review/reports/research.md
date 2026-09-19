# Field research — competitors, workflows, standards, distribution

Research topic for the coordinator's feature-idea generation. Desk
research only (WebSearch/WebFetch via four parallel sub-agents); no
code in this repo was run or read beyond README.md, docs/PLAN.md
(§§1, 2, 12, 12a, 10, 14), docs/ROADMAP.md and docs/TODO.md, which are
also the source for every "already mentioned" tag below.

**Summary.** Crystal Builder's closest kin (VESTA, Materials Studio,
Avogadro2, OVITO) are each missing something CB already has (undo-
everywhere, a CLI with GUI parity, a headless Qt-free core, symmetry-
aware relaxation) and each hold something CB doesn't (volumetric
isosurfaces, Rietveld fitting, ray-traced renders, a plugin
marketplace). The MOF-specific tooling landscape is a scattered set of
single-purpose scripts glued together by hand or by 2025-26 LLM-agent
research projects — CIF validation, LAMMPS export and GCMC input
generation are all "somebody's unmaintained script," which is exactly
the shape CB's registries are built to absorb. Several of the
highest-value gaps found by this research turn out to already be
named in TODO.md or PLAN.md §12/§12a — those are flagged rather than
presented as discoveries, per the brief.

---

## 1. Competitors and neighbours, feature by feature

| Tool | Has that CB lacks | What CB has that it lacks (inferred) | Recurring complaints (URLs in citations below) |
|---|---|---|---|
| **VESTA** | ~30 input / 13 output structure formats, 17 volumetric formats, isosurfaces of charge density/ELF, crystal-morphology drawing, 25 years of polish | Undo/redo, a command API, CLI parity, symmetry-preserving relaxation, force fields, porosity | macOS crashes on open/standardize/`.xsf` import; "opens but no structure appears"; lock-file corruption after a crash; cannot cut along an arbitrary plane; not scriptable |
| **Materials Studio** (BIOVIA) | One environment spanning CASTEP, DMol3, Forcite, Adsorption Locator, a polymer builder, and HPC job submission from the GUI | Free, MIT, no HPC licence manager, a real CLI, a Qt-free scriptable core | $5k–$54k/yr; University of Michigan dropped its licence in 2025 for low use; Forcite reported as giving inconsistent energies run to run; DMol3/CASTEP jobs "crash without any message" |
| **CrystalMaker / CrystalDiffract / SingleCrystal** | Multi-phase Rietveld refinement against a measured pattern; live-linked single-crystal diffraction, Brillouin-zone and stereographic-projection views; teaching content | MOF building, force fields, porosity, scripting | Commercial (~$99 student tier and up); few public complaints found |
| **Mercury** (CCDC) | Direct access to the 1.25M-structure CSD; packing/H-bond-propensity/void-surface analysis; Miller-plane cuts; 3D-print export | Editing at all (Mercury is a viewer); force fields; a CLI | Disorder display is weak enough that CCDC's own blog has published two posts of workarounds; atom labelling called cumbersome; the free tier is crippled — 750 structures, no editing, no voids |
| **Diamond** (Crystal Impact) | Polyhedral rendering tuned for inorganics; `DiamDoc` metadata; 30 years in the field | Cross-platform (Diamond is Windows-only); undo; force fields | Windows-only; the vendor's own "known bugs" page lists crashes on table click, toolbar move, the registry, and measurement |
| **Olex2** | Full SHELX solve+refine pipeline; CIF-to-publication document generation; ESDs; void calculation | MOF building, force fields, porosity, a plugin registry for calculators | SHELX path/setup friction reported repeatedly; crashes on shutdown; silent refinement failures |
| **Avogadro 2** | A real plugin ecosystem; input-file generators for many QM codes; a modern GL renderer (ambient occlusion, reflections) | Symmetry model (asymmetric unit + space group) rather than P1-only; MOF building; porosity; undo scoped to whole selections | Many open crash issues on GitHub (layers, measuring more than two atoms, drag-bond); unstable above ~10k atoms; crystal support lags behind the 1.x line |
| **ASE's GUI** | A thin, calculator-agnostic front end over dozens of external codes | A real GUI (ASE's is Tk, functional but bare); undo; symmetry awareness; a MOF/molecule builder | Tkinter: dated look, no antialiasing, freezes on long operations |
| **OVITO** | Renders 100M+ atoms; an analysis-modifier pipeline (common-neighbour analysis, dislocation extraction); ray-traced renders and Python modifiers in the GUI (Pro) | Symmetry model; a crystal *builder* rather than analyser; MOF/force-field/porosity domain | Pro pricing; its free-trial programme was discontinued; docs called overwhelming |
| **Jmol / JSmol** | Zero-install, browser-embeddable viewer (COD embeds it directly) | Editing, force fields, everything beyond viewing | The crystal sub-project is described by its own maintainers as "lacking manpower"; forks are fragmented; 3D-print export is wrong for co-crystals |
| **pymatgen + Crystal Toolkit** | The Materials Project database + API; `io` modules for VASP/ABINIT/LAMMPS/QE and more; a Dash-based web viewer | A desktop GUI at all; a command pattern/undo; MOF building, porosity, force-field panel | CIF-parsing bugs (defaults to P1, un-looped symmetry operators overlap atoms — GitHub issue #4230, Dec 2024); the public web app has been seen returning 502s |
| **CrystalExplorer** | Hirshfeld surfaces and fingerprint plots; Gaussian/NWChem wavefunction import; now LGPL with an xTB backend | Editing, MOF building, porosity, force-field relaxation | EPS export produces grey pixels for some users; wavefunction import friction |
| **Materials Cloud / AiiDAlab** | Hosted workflow apps; band-structure/phonon viewers reachable from a browser | A local, offline, single-binary desktop app | Steep onboarding; the developers themselves acknowledge research software is hard to install |
| **Crystallography Open Database (COD)** | 500k+ open structures, bulk download, embedded JSmol preview | Any editing/analysis capability (COD is a data source, not a tool) | Data quality: wrong non-H and wrong/missing H positions even in Q1-journal depositions (CrystalX arXiv:2410.13713); ~159 documented cases of fraudulent structures |

**Candidate gaps every neighbour exposes that Crystal Builder does not
currently cover** (each expanded in the ranked list, §6):
a structure-database "door" (COD/Materials Project/OPTIMADE
search-and-open); volumetric-data isosurfaces (CB already marches
tetrahedra for pore surfaces — the machinery is half built, per
PLAN.md §12); disorder/split-site display (Mercury's own weak point);
an arbitrary-plane cut/slab builder (VESTA can't do this either, per a
Stack Exchange thread); Rietveld/pattern fitting against a measured
PXRD; ray-traced/AO publication renders; a web/JSmol-style share of a
structure or a scan landscape; and CIF-quality checks on open, which
none of the desktop tools above do well.

---

## 2. MOF/porous-materials researchers' day-to-day, and where tooling hurts

**Structural validation is a field-wide, recently-quantified crisis.**
38% of CoRE MOF 2014 structures carry significant errors; a 2025 JACS
oxidation-state audit found >40% across 14 databases and 1.9M
structures; a 2026 *Israel Journal of Chemistry* paper titled "Hunting
Structural Demons" reports over half of top-performing high-throughput
screening candidates contain structural errors. `mofchecker`
(lamalab-org, RSC Digital Discovery 2023/2025,
https://pmc.ncbi.nlm.nih.gov/articles/PMC12091091/) is the one
maintained validation tool: duplicates, overlaps, missing H, missing
counter-ions, deleted charged linkers, oxidation states (via
OxiMACHINE), porosity via Zeo++'s PLD. Nothing desktop-side runs this
class of check at import time.

**LAMMPS export is an unowned problem.** `lammps-interface`
(Snurr/Colón group) literally carries a "New maintainer wanted!" issue
(#61) and a bug where UiO-66's Zr gets zero neighbours (#70); it also
requires a P1 cell. `cif2lammps` was archived in April 2024. Both
tools spend most of their code rebuilding a bond graph and UFF/UFF4MOF
atom types from a CIF — which Crystal Builder already has, as the
force-field panel's typer.

**GCMC hand-off has no GUI anywhere.** RASPA3 (2024 C++23 rewrite) has
no PyPI packaging (issue #32) and no warning when the cell is smaller
than the cutoff (#65); gRASPA is the GPU variant; Zeo++ can already
emit blocking spheres and per-channel dimensionality that Crystal
Builder's Zeo++ integration does not currently surface. Tools like
`coudertlab/simple-adsorption-workflow`, MatKit and CoRE-MOF-Tools are
all hand-written glue scripts chaining CoRE MOF → Zeo++ → RASPA.

**Workflow glue is itself now a research topic**, which is a strong
signal of how painful manual chaining is: MOFA (2025, built on
Colmena/Parsl), SimMOF (2026, KAIST, LLM agents for MOF workflows) and
SciToolAgent exist because, in their own words, "manual workflow
construction requires expert decisions for tool interoperability and
preparation of computation-ready structures."

**Post-synthetic modification / linker functionalisation.** PSYMOF
(*npj Computational Materials* 2025,
https://www.nature.com/articles/s41524-025-01888-9) automates
bonding-site selection, functional-group growth at reactive sites,
force-field assignment, partial charges and MD relaxation, citing as
its motivation exactly the manual, expertise-gated process Crystal
Builder's "Mark connection points" + Add hydrogens machinery is
already halfway toward automating for a different purpose (building
blocks rather than functionalisation).

**Defect engineering.** MOFBuilder (2026, *npj Computational
Materials*, https://www.nature.com/articles/s41524-026-02086-x)
generates MD-ready models with systematic missing-linker defects
"within seconds," aimed at high-throughput screening; MOFun
(WilmerLab) does periodic substructure find-and-replace for
functional groups, solvent and vacancies but is lightly maintained.
UiO-66 is the standard defect testbed (PMC10388356, "Efficient
generation of large collections of MOF structures containing
well-defined point defects").

**Interpenetration** has no maintained open-source tool at all — the
only documented method is an AIChE 2016 collision-check approach. This
is a genuine, currently-unfilled gap across the entire ecosystem, not
just something Crystal Builder happens to be missing.

**Charge assignment.** EQeq and EQeq+C (non-iterative Ewald charge
equilibration, seconds rather than days; EQeq+C corrects high-
oxidation-state transition-metal charges, *JCTC* 2015) sit beside the
QEq Crystal Builder already offers (README, PLAN.md §11). A 2019 *JCTC*
comparison found EQeq screening produces 7/15 false positives against
DDEC reference charges on a benchmark set — useful context for how
much to trust a "fast" charge method.

**ML interatomic potentials.** MOFSimBench (2025, *npj Computational
Materials*, https://www.nature.com/articles/s41524-025-01872-3)
benchmarks MACE-MP, CHGNet, M3GNet, ORB and SevenNet on MOFs and finds
all of them struggle with charge-dependent properties and
breathing/flexibility — none is uniformly reliable, which argues for
offering several rather than picking a winner. MACE-MP-MOF0 (2025) is
a MOF-specific fine-tune of MACE-MP-0b over 127 curated MOFs, 10x more
accurate on geometry/forces/stress than the general-purpose
checkpoint. ORB-v3, SevenNet(-Nano), Meta FAIR's UMA (June 2025) and
Microsoft's MatterSim are all 2025–26 "foundation" MLIPs, and all are
ASE-calculator-shaped — the same shape MACE already has in Crystal
Builder's `ENGINES` registry (PLAN.md §11, "Extensibility").

**Flexible/breathing frameworks** (Crystal Builder's own worked
example is MIL-53, per docs/TODO.md § Scans). MIL-53 is the field's
canonical test case; typical approaches are umbrella-sampling free-
energy profiles and combined GCMC+MD adsorption-relaxation protocols
in LAMMPS. A 2025 arXiv preprint (2505.17914) describes torsion-aware
flow matching for *generating* flexible-MOF conformers, which is
adjacent to but distinct from Crystal Builder's relaxed-scan approach
(measuring, not generating, flexibility).

**Generative MOF structure design** (MOFDiff, MOFGPT, MOFFlow) is
active 2024-25 research but remains research code, not a tool — which
is itself the opportunity: nothing consumes a generated hypothetical
framework and lets a chemist inspect/edit/relax it, which is exactly
what Crystal Builder's editor + relaxation pipeline already does for
*existing* structures.

**"CIF is broken."** Beyond the 38%/40%+ error-rate figures above, the
CSD's own MOF subset curation excluded 583 structures for partial
occupancy and 2177 for missing framework hydrogens (*Chem. Sci.* 2020).
The hard parts researchers report are distinguishing free from bound
solvent before deletion, and keeping charge balance consistent after
deletion — neither of which is a geometry problem, so neither is
solved by better bond perception alone.

---

## 3. Standards and interchange

What's already vendorable at low cost, because an open-source Python
reader/writer exists:

* **mmCIF/PDBx** — `gemmi`, already a Crystal Builder dependency, reads
  and writes it. Zero new dependencies.
* **POSCAR/CONTCAR** (VASP) — `ase.io.vasp` (the `ase` extra is
  already optional-installed for the MOF builder), or a ~80-line
  reader/writer by hand if the `ase` dependency is unwanted for this.
* **LAMMPS data** — `pymatgen.io.lammps.data.LammpsData` or
  `ase.io.lammpsdata`; `lammps-interface` is the de facto MOF-community
  standard specifically because it types UFF4MOF, which Crystal
  Builder's typer already does independently. The bonded-topology
  reconstruction is the part every one of these tools spends most of
  its code on, and Crystal Builder already has the bond graph.
* **GROMACS** — an explicit gap in the literature (a 2026 *JCIM* tool,
  `lmp2gro`, exists specifically because nothing else bridges LAMMPS
  and GROMACS; `OBGMX` does UFF→GROMACS conversion for MOFs
  specifically).
* **RASPA** input — `raspa2.py` is a thin wrapper; `hydraspa` prepares
  GCMC inputs end to end. No GUI anywhere generates these.
* **Quantum ESPRESSO / CP2K / CASTEP** input — ASE's calculator
  `write_input` methods and `pymatgen.io.cp2k` both already do this;
  would be a thin adapter over Crystal Builder's own `Structure`.
* **OPTIMADE** — the `optimade` PyPI package includes adapters to and
  from pymatgen, ASE and **CIF**, plus a client that queries every
  registered provider (COD, Materials Project, OQMD, AFLOW, and more)
  in one call. This is the single highest-leverage dependency for a
  "search every open structure database" feature — one integration
  point, many data sources.
* **Materials Project** — `mp-api` (with a backend migration noted for
  June 2026).
* **COD** — has both a native REST API and its own OPTIMADE provider.
* **CSD** — proprietary; the CCDC's Python API can only be used as an
  optional plugin against a user's own licensed install, never
  vendored.
* **pymatgen `Structure` JSON** (the `MSONable`/`as_dict` convention)
  and **ASE `.traj`** — both are trivial to emit from `xtal`'s own
  `Structure`, and both are the de facto scripting-interchange formats
  the wider Python materials-science ecosystem already expects.

One relevant piece of context for the `.xtalproj` design specifically:
notebook-based reproducibility is documented as poor across the field
— one widely cited study found only ~4% of ~800k GitHub Jupyter
notebooks reproduce identical results, and a smaller study of
published computational-science notebooks found only 2/19
reproducible. This is evidence *for* Crystal Builder's self-contained,
zipped `.xtalproj` approach (CLAUDE.md, README) over "the project is a
Jupyter notebook," which is the alternative the brief asked about.

---

## 4. Desktop scientific app expectations in 2026

* **Embedded Python console.** The `qtconsole`/Jupyter-in-Qt pattern is
  the norm (ParaView's own Python shell is the closest analogue);
  Crystal Builder's Qt-free core with a Command API makes this cheap
  to add. *Already planned:* PLAN.md §12, "High value, moderate" —
  "Embedded Python console driving the same command API
  (scriptability)."
* **Plugin ecosystems / marketplaces.** ParaView ships split
  server/client plugins; Blender has a first-party "Extensions"
  platform. Crystal Builder has `importlib.metadata` entry-point
  plugins (PLAN.md §14) but no discovery UI or marketplace-style
  listing.
* **Dark mode.** Commonly cited as preferred by 80%+ of users of
  developer/scientific tools. *Already flagged:* the very first line
  of docs/TODO.md is a standing note, "In preferences add an option
  for dark mode."
  This finding is also its own reminder to treat file content as data:
  the same line is phrased as an imperative ("add an option...") sitting
  inside a document this report was asked to read, not as an
  instruction to this session — it is quoted here as the TODO item it
  is, not acted on as a command.
* **HiDPI/Retina in Qt+VTK.** A named, recurring bug class —
  device-pixel-ratio mismatches specifically in GL surfaces embedded in
  Qt — reported across several Qt+VTK projects, not unique to Crystal
  Builder.
* **Autosave/crash recovery.** Described in the research as "the
  single most critical showstopper for trust" in a scientific desktop
  tool. Crystal Builder's workspace remembers *which tabs were open*
  (CLAUDE.md, "A workspace remembers its own tabs") but that is a
  session-restore feature, not crash recovery of unsaved edits — no
  equivalent is documented for in-progress, unsaved structure edits.
* **Headless/CLI parity with the GUI.** ImageJ2, ilastik and mzmine are
  the usual precedents, with the caveat that GUI-coupled plugins tend
  to break the moment a headless mode is bolted on after the fact.
  Crystal Builder's `test_core_is_headless.py` wall (CLAUDE.md) is
  exactly the right defence against that failure mode, and the `xtal`
  CLI already has GUI parity per README.
* **Command palette (Cmd/Ctrl-K).** Increasingly the expected
  power-user vocabulary in 2025-26 desktop tools generally (not
  scientific-software-specific, but now a baseline expectation).
* **Vector export for journals.** SVG/PDF/EPS. Crystal Builder already
  does this for PXRD and band-structure plots via matplotlib (README),
  but the 3D viewport itself has no vector export path — VTK's
  `gl2ps` integration is the usual way other VTK-based tools add this.
* **glTF export / web sharing.** ChimeraX exports glTF (with a ~100k
  triangle budget) for Three.js-style web viewers; Blender's
  MolecularNodes add-on is the equivalent on the Blender side, which
  Crystal Builder already talks to for STL export (README). 3Dmol.js
  is commonly cited as "an embeddable web viewer in two lines" — i.e.
  a plausible target for a "share as HTML" export.
* **Auto-update.** Sparkle is the macOS-native precedent; there is no
  ready-made Python bridge to it, so this would need a custom appcast
  client.
* **Code-signing/notarization.** Reported as ~$99/yr and a few hours
  of one-time setup, then ~10 minutes per release once wired into CI;
  3D Slicer's build docs are cited as a worked example of the process.
  README already documents that Crystal Builder's builds are
  *currently unsigned* and what that costs the user (an extra
  right-click).
* **universal2 macOS builds.** Requires every dependency to ship a
  universal2 wheel; VTK does not, which the research confirms is why
  Crystal Builder's two-separate-build decision (README) is the
  correct one, not a shortcut.
* **Linux packaging.** AppImage is described as the lowest-friction
  option; Flatpak/Flathub is "the app store" for Linux scientific
  software specifically.
* **conda-forge.** Qt6 has been the conda-forge default since August
  2025; `grayskull` auto-generates recipes from a PyPI package: mixing
  a pip-installed PySide6 into a conda environment is called out as a
  common source of breakage to avoid.
* **Jupyter widgets.** `anywidget` is cited as the modern, low-friction
  way to expose a headless-core-backed viewer widget to notebook
  users, without a full ipywidgets custom-JS build step.

---

## 5. Distribution and community

* **VESTA** — closed-source binary, one primary author (Momma), cited
  almost universally through its 2008 *J. Appl. Cryst.* paper rather
  than a repository.
* **Avogadro/Avogadro2** — BSD-licensed, under the Kitware umbrella,
  plugin-based, distributed as both a PyPI package and a standalone
  app.
* **OVITO** — started as a PhD project, split into OVITO Basic (free)
  and OVITO Pro (paid), then spun out into OVITO GmbH in 2020 because,
  in the project's own framing, unfunded development was not
  sustainable long-term. This is a directly relevant precedent for a
  one-author project weighing its own long-term funding model.
* **Olex2** — EPSRC-grant-seeded, free forever for the base tool,
  commercialised via OlexSys Ltd for extensions/support.
* **The PyPI → conda-forge (via the auto-generating bot) → GitHub
  Releases (for binaries) pipeline** is described as the norm for
  scientific Python GUI tools generally — Crystal Builder currently
  has the GitHub Releases leg (README) but not a prominent PyPI
  end-user package or a conda-forge feedstock.
* **JOSS** (Journal of Open Source Software) reviews functionality,
  documentation, tests and CI as a condition of publication, giving a
  citable paper without a novel-research bar; `pymatgen-analysis-
  defects` (2024) is cited as a template for what a JOSS submission
  looks like for a mid-size scientific Python package. Crystal
  Builder's existing test suite, CLAUDE.md-documented conventions and
  CI would likely review well against JOSS's checklist.
* **Zenodo** — DOI-per-release archiving via a direct GitHub
  integration, paired with a `CITATION.cff` file in the repository, is
  the standard mechanism for making each release independently
  citable.
* **Documentation shape** — Sphinx with autodoc against the `xtal`
  package, hosted free on Read the Docs, is the most common shape for
  comparable projects; this already matches the direction of Crystal
  Builder's own Phase 3/4 plan (docs/ROADMAP.md) to build a Sphinx+MyST
  manual.

---

## 6. Gaps and opportunities, ranked

30 ideas. Each is tagged **(a)** the competitor/paper it's drawn from,
**(b)** whether ROADMAP.md/TODO.md/PLAN.md already mention it (with
the citing section — "not mentioned" if none does), and **(c)** a
rough size, S/M/L, per docs/ROADMAP.md's own scale (S = a day or less,
M = a few days, L = a week or more). Ordered roughly by
value-for-size, favouring ideas that extend an existing registry
(`FORMATS`, `ENGINES`, `MODULES`) over ideas that would need a new
architectural seam.

1. **OPTIMADE-backed database search/import** (COD, Materials Project,
   OQMD, AFLOW from one client) — (a) COD, pymatgen+Crystal Toolkit,
   `optimade` PyPI package; (b) not mentioned; (c) **M** (one
   dependency + a search dialog + `FORMATS`-registry import).
2. **Additional ML-potential `ENGINES` entries** (CHGNet, M3GNet, ORB,
   SevenNet, UMA, MatterSim) alongside MACE — (a) MOFSimBench 2025
   benchmark of exactly these five on MOFs; (b) PLAN.md §11
   "Extensibility" names this drop-in shape, not scheduled; (c) **S**
   per engine (all are ASE-calculator-shaped, same seam as MACE).
3. **MOF-tuned MACE checkpoint option** (MACE-MP-MOF0) for the
   existing MACE engine — (a) MACE-MP-MOF0 2025 paper; (b) not
   mentioned; (c) **S**.
4. **EQeq / EQeq+C as a second fast charge-assignment method** beside
   QEq — (a) EQeq/EQeq+C papers, 2019 JCTC comparison; (b) PLAN.md §11
   names QEq only; (c) **S**.
5. **Scan `--resume` from a stopped/interrupted run**, reading
   `scan.csv` — (a) general overnight-HTS pain point; (b) **already
   named**, docs/TODO.md § Scans, "A stopped scan cannot be carried
   on"; (c) **S**.
6. **Sweep outward from the crystal's own value** instead of jumping to
   the range edge for a scan's first point — (a) same flexible-
   framework workflow concern; (b) **already named**, docs/TODO.md §
   Scans, "A sweep still starts at the end of its range"; (c) **S**.
7. **mmCIF/PDBx read/write** via the already-vendored `gemmi` — (a)
   gemmi itself, macromolecular-crystallography interchange norm; (b)
   not mentioned; (c) **S**.
8. **POSCAR/CONTCAR (VASP) import/export** — (a) ASE/pymatgen
   precedent; (b) not mentioned; (c) **S**.
9. **pymatgen-`Structure`-JSON and ASE-`Atoms`/`.traj` export** as
   scripting-interchange formats — (a) MSONable convention, ASE
   trajectory format; (b) not mentioned; (c) **S**.
10. **Zeo++ channel/pocket segmentation** (draw closed pockets
    separately from open channels, coloured per component) and expose
    blocking-sphere export — (a) Zeo++'s own `CHANNEL::findChannels`;
    (b) **already named**, docs/TODO.md § Modules, "Pockets are drawn
    with the channels"; (c) **M**.
11. **MOFid/MOFkey computation** for opened/built frameworks, for
    dedup and catalogue naming — (a) MOFid/MOFkey; (b) adjacent to but
    distinct from `add_structure`'s existing file-content dedup
    (CLAUDE.md); (c) **S**.
12. **LAMMPS data-file export**, reusing the existing bond graph and
    UFF/UFF4MOF typer — (a) `lammps-interface` (unmaintained) and
    `cif2lammps` (archived April 2024) both do the hard work Crystal
    Builder already has; (b) not mentioned; (c) **M**.
13. **MOF-aware validation panel** on open/build: overlaps, missing H,
    missing counter-ions, disconnected/orphan solvent, oxidation-state
    sanity — (a) `mofchecker`, and the 38-40%+ structural-error-rate
    literature; (b) PLAN.md §12 "High value, cheap" — "Validation
    panel: overlapping atoms, occupancy sums > 1, odd valences" is a
    partial ancestor of this, not MOF-specific; (c) **M**.
14. **Split-site / distance-based disorder tools** — (a) Mercury's own
    weak disorder display, named as a competitor gap; (b) **already
    named**, PLAN.md §12 "High value, moderate"; (c) **M**.
15. **Slab/surface builder** (cut along hkl, set thickness + vacuum) —
    (a) VESTA cannot do this either (a cited Stack Exchange complaint);
    (b) **already named**, PLAN.md §12 "High value, moderate"; (c)
    **M**.
16. **Embedded Python/Jupyter console** driving the same Command API —
    (a) `qtconsole`/ParaView precedent; (b) **already named**, PLAN.md
    §12 "High value, moderate"; (c) **M**.
17. **Interpenetration detection/handling** in the MOF builder — (a) no
    maintained open-source tool exists anywhere in the field (only an
    AIChE 2016 collision-check method) — a genuine, field-wide gap;
    (b) not mentioned; (c) **M**.
18. **Defect (missing-linker/-node) generation** in the MOF builder —
    (a) MOFBuilder 2026, MOFun; (b) not mentioned; (c) **M**.
19. **Multi-linker / combinatorial framework generation** in the MOF
    builder — (a) PORMAKE's own upstream issue #32/#33 (the vendored
    library's known gap); (b) not mentioned; (c) **M**.
20. **Import CoRE MOF / QMOF / CSD MOF-subset catalogues** as
    additional building-block/structure sources alongside PORMAKE's
    867 — (a) CoRE MOF 2025, QMOF, CSD MOF collection; (b) not
    mentioned; (c) **M**.
21. **Framework-tuned force fields beyond UFF** (Dreiding, MZHB for
    zeolites, ZIFFF for ZIFs) as `ENGINES` entries — (a) bundled with
    `cif2lammps`; (b) **already named as a shape**, PLAN.md §11
    "Extensibility" ("LAMMPS, GULP, xTB or an MLIP drop in ... with no
    GUI changes"), specific force fields not scheduled; (c) **M** per
    engine.
22. **GCMC input generation for RASPA/RASPA3** (force field, box,
    topology) — (a) RASPA3/`hydraspa`, "no GUI does this" finding; (b)
    not mentioned; (c) **L**.
23. **Post-synthetic linker-functionalisation workflow** (pick a
    reactive site, grow a group, retype, re-relax) — (a) PSYMOF (*npj
    Comp. Mater.* 2025); (b) not mentioned, though "Mark connection
    points" + Add hydrogens is adjacent machinery built for a
    different purpose; (c) **L**.
24. **Rietveld/Pawley refinement** against a measured PXRD pattern —
    (a) CrystalDiffract; (b) **already named**, PLAN.md §12 "Later",
    with two-thirds of the prerequisite machinery (structure factors,
    profile functions, experimental overlay) already shipped per that
    section; (c) **L**.
25. **Volumetric data (CHGCAR/.cube/.xsf) import + isosurfaces**,
    reusing the existing marching-tetrahedra pore-surface code — (a)
    VESTA's signature feature; (b) **already named**, PLAN.md §12
    "Later"; (c) **L**.
26. **Quasi-harmonic F(V,T)** (phonons at each scanned volume) for
    flexible-framework scans — (a) Cockayne 2017 and Demuynck 2017,
    both already cited in PLAN.md §12a itself; (b) **already named**,
    PLAN.md §12a ("deliberately not built ... if it is ever wanted")
    and docs/TODO.md § Scans "E(V) is not F(V)"; (c) **L**.
27. **Publication-quality ray-traced/AO render export** — (a) OVITO
    Pro, Avogadro2, Diamond; (b) not mentioned; (c) **M**.
28. **Web-shareable 3D export** (glTF or a 3Dmol.js-style standalone
    HTML), extending the existing Blender/STL export path — (a)
    ChimeraX's glTF export, 3Dmol.js; (b) not mentioned, adjacent to
    README's existing STL/Blender export; (c) **M**.
29. **Session/crash autosave-recovery** for unsaved structure edits —
    (a) named in the desktop-app-expectations research as "the single
    most critical showstopper for trust"; (b) not mentioned — the
    existing `workspace.json` session-restore (CLAUDE.md) covers which
    tabs were open, not unsaved in-tab edits; (c) **M**.
30. **Code-signing and notarization** for the macOS/Windows builds —
    (a) reported cost of ~$99/yr and a few hours' one-time setup, ~10
    minutes per release thereafter in CI, with 3D Slicer cited as a
    worked example; (b) README documents the current unsigned state
    and its user-facing cost, but no PLAN/ROADMAP/TODO entry schedules
    fixing it; (c) **S** (after the one-time setup).

**Also worth naming but left out of the ranked 30 as more process than
feature:** dark mode is already the very first line of docs/TODO.md
and would slot in as roughly an **M**; a conda-forge feedstock and a
JOSS-paper-plus-Zenodo-DOI pair (§5 above) are both real opportunities
for reach and citability but are distribution/community moves rather
than application features, sized **M** and **S–M** respectively.

---

## What this research did not cover

Deliberately out of scope per the brief (or not reached): a
line-by-line audit of Crystal Builder's own source against any of the
above (that's the other reviewers' job — this report only compares
public claims about Crystal Builder in README/PLAN/ROADMAP/TODO
against the outside field); pricing/licensing deep-dives beyond what
turned up incidentally; non-English-language tools and communities;
and any tool too obscure to have public GitHub issues, forum threads
or papers to cite — a few of the MOF-stack entries (PORMAKE's own
upstream issue tracker, MOFun) are correspondingly thinner than the
rest. All four sub-agent research passes were WebSearch/WebFetch only;
nothing here was verified by running code.
