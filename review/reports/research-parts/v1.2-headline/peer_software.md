# Peer crystallography and materials-modelling software: recent headline features and open white space (Nov 2025 – Nov 2026)

Scope note: this builds on the 2026-10-09 survey (`reports/Crystal Builder feature landscape.md` and `research_notes/Crystal Builder feature landscape/desktop_software.md`). That survey already covered CrystalMaker through 11.7.2, OVITO 3.16.0's AI Agent, Avogadro 2.0.0, Materials Studio 2026's MACE, Schrödinger Maestro Assistant and Bunsen, and VESTA being frozen at 3.5.8. These notes record only what is new since then, or what that survey missed. About 18 search, fetch and `gh` calls were made. Several vendor pages blocked fetching or returned only navigation: GlobeNewswire and VMblog (403), the CCDC What's New page (navigation only), and the Materials Studio 2026 "What's New" PDF (binary that could not be read). Facts taken from search-engine summaries rather than primary pages are marked "(search summary)".

## Q1. What did peers' latest major releases lead with? (versions and dates)

### Takeaway
The dominant headline of 2026 is **agent and scripting control of a live GUI**. OVITO 3.16 (Aug 2026), Matlantis (May 2026), Schrödinger (2025-3 and 2026-3) and now **Avogadro 2.1.0 (23 Oct 2026, with `avogadro-mcp` and a JSON-RPC command interface)** all shipped or announced it. Crystal Builder's MCP server is therefore no longer a unique headline; it is becoming table stakes. The second theme is ML potentials made routine: Materials Studio's MACE models and Avogadro's batch energies for ML potentials. A third, smaller theme is general tools moving onto crystal-viewer turf. OVITO 3.17 added a "VESTA-like bond mode" and periodic images, and Avogadro 2.1 added CIF space-group perception and fractional supercells.

### Cited Findings

**Avogadro 2.1.0 — released 2026-10-23 (new since the prior survey)**
- The release leads with a Z-matrix editor and faster geometry optimisation (ABC-FIRE2, with a hybrid default for Optimize and AutoOpt). Gaussian-basis orbital and surface rendering is up to 20–25× faster — [GitHub release 2.1.0](https://github.com/OpenChemistry/avogadroapp/releases/tag/2.1.0)
- **Agent and scripting features:** "Many tools can now be controlled through a JSON-RPC interface, including selection, measurement, force fields, constraints, symmetry, spectra, colors, and hydrogens." The `avogadro.connect` Python module lists the available commands for driving Avogadro "from Jupyter, scripts, or AI agents". There is also "a new `avogadro-mcp` project for connecting local LLM models and agents to Avogadro" — [GitHub release 2.1.0](https://github.com/OpenChemistry/avogadroapp/releases/tag/2.1.0)
- **Building and materials features:** an initial polymer builder ("feedback welcome"), fractional supercells, and "better support for CIF files, including space group perception from transforms". Distances, angles and dihedrals can be edited in the Measure tool, and PDB biological assemblies load at up to ~1 M atoms — [GitHub release 2.1.0](https://github.com/OpenChemistry/avogadroapp/releases/tag/2.1.0)
- **ML-potential workflow:** "Batch energies and forces: recalculate energies and forces for every conformer or frame at once, in batches suited to ML potentials" — [GitHub release 2.1.0](https://github.com/OpenChemistry/avogadroapp/releases/tag/2.1.0)
- **Platform and robustness:** the release marks 30 plugins, and continuous fuzz testing of the file readers found "a large number of bugs and potential crashes" — [GitHub release 2.1.0](https://github.com/OpenChemistry/avogadroapp/releases/tag/2.1.0)
- **Cadence:** Avogadro plans releases on 06 Feb, 02 June and 23 Oct ("Mole Day"). A May 2026 update had planned 2.1 for 2 June, so it slipped to October (search summary) — [Avogadro May 2026 update](https://discuss.avogadro.cc/t/may-2026-development-updates/7449); [2026 roadmap](https://discuss.avogadro.cc/t/avogadro-2026-roadmap/7268)
- `gh search repos avogadro-mcp` returned no public repository on 2026-11-06, so the MCP project may live inside the OpenChemistry organisation under another name, or it may not be public yet — (`gh` search run by researcher)

**OVITO 3.17.0 — 21 Oct 2026; 3.17.1 — 26 Oct; 3.17.2 — 2 Nov 2026 (new since the prior survey)**
- **3.17.0 visualisation:** "VESTA-like bond mode", virtual periodic images, and protein cartoons with DSSP. It also adds a Measure tool for distances, angles and areas, Steinhardt order parameters (Pro), diffusion coefficients (Pro), SSAO, cast shadows and depth of field in the standard renderer, and macOS 14.4 as the new minimum — [OVITO new features](https://ovito.org/manual/new_features.html)
- **3.17.1** fixes CJK input in the AI Agent terminal. **3.17.2** code-signs the Windows executables to fix Smart App Control blocking startup, and splits the conda packages into `ovito`, `ovito-pro` and `ovito-basic` — [OVITO new features](https://ovito.org/manual/new_features.html)
- **Earlier 2026 releases the prior survey did not itemise:**
  - **3.15.0 (3 Mar 2026):** molecular structure support (covalent-radius bonds, a Pro bond-order modifier), "Edit simulation cell" and "Edit types" modifiers.
  - **3.15.5 (20 Jun 2026):** MOL2, MedeA SCI and MedeA SLI readers.
  - **3.16.1 (14 Sep 2026):** an XYZ reader option to generate bonds.

  — [OVITO new features](https://ovito.org/manual/new_features.html)
- The homepage now markets the AI agent integration (Claude Code, Copilot CLI, Codex) for building pipelines "from plain-language descriptions" as a Pro feature. It is running a 50% off academic OVITO Pro sale until 30 Nov 2026 — [ovito.org](https://ovito.org/)

**CrystalMaker / CrystalDiffract**
- The newest release is still **11.7.2 (8 Sep 2026)**: enhanced CIF export with creation date, notes, formula and density fields; ring measurements with standard deviations; a crash fix for relaxing complex MOFs. No release after September 2026 was found (the release-notes page is listed newest first) — [CrystalMaker Mac release notes](https://crystalmaker.com/crystalmaker/release-notes/mac/11/index.html)
- The 11.7.0 headline (16 Apr 2026) is confirmed: "MOF Automation" (Transform > Automate > Filled Rings / Filled Rings & Cavities), automatic Measure > Rings, space-filling spheres in polyhedral plots, "orders-of-magnitude faster" relaxation, and Extended XYZ crystal files — [CrystalMaker Mac release notes](https://crystalmaker.com/crystalmaker/release-notes/mac/11/index.html)
- **Window-relevant releases from Nov 2025 to Feb 2026:**
  - **11.6.1 (17 Nov 2025):** Gallery redesign.
  - **11.6.2 (7 Jan 2026):** Coaching Tips on first launch, faster Find Cavities.
  - **11.6.3 (27 Jan 2026):** smarter framework detection.
  - **11.6.4 (25 Feb 2026):** better MOF relaxation and more detailed phonon output.

  The 11.6.0 headline (2 Oct 2025) was Create Surface/Slab, experimental crystal-shape prediction, and enhanced MOF/ZIF energy modelling — [CrystalMaker Mac release notes](https://crystalmaker.com/crystalmaker/release-notes/mac/11/index.html)

**Matlantis (PFN / ENEOS) — the prior survey missed this**
- **27 May 2026:** Matlantis "Brings Claude Code Into Atomistic Simulation Platform" and released a public Skills library on GitHub. An installer to run Claude Code inside the Matlantis terminal was described as coming "in a forthcoming update" (search summary; the press release returned 403) — [GlobeNewswire](https://www.globenewswire.com/news-release/2026/05/27/3301998/0/en/Matlantis-Brings-Claude-Code-Into-Atomistic-Simulation-Platform-Releases-Public-Skills-Library-on-GitHub.html); [VMblog](https://vmblog.com/news/matlantis-brings-claude-code-into-atomistic-simulation-platform-releases-public-skills-library-on-github/)
- The skills repository is `matlantis/matlantis-agent-skills` ("Skill files for the Matlantis coding agent to generate simulation code"), last updated 2026-08-04. A third-party `Nu424/matlantis-job-skill` (Japanese, for having an AI run Matlantis jobs) was updated 2026-08-17 — (`gh search repos` run by researcher)
- **14 Apr 2026:** Matlantis announced it had integrated the NVIDIA ALCHEMI Toolkit for industrial-throughput simulation (search summary) — [xpr.media](https://xpr.media/?p=739018)

**BIOVIA Materials Studio 2026 (mid-2026)**
- The headline items are native Python as a Materials Studio scripting language, a new MACE-MATPES-r2SCAN-0 model, better IR spectrum prediction, and non-local exchange functionals in CASTEP (search summary of 3DS documents) — [T61-2025 Materials Studio 2026](https://www.3ds.com/support/documentation/resource-library/t61-2025-materials-studio-2026.md); [What's New 2026 PDF](https://www.3ds.com/assets/invest/2026-06/biovia-materials-studio-whats-new-2026.pdf)
- No Materials Studio 2027 announcement was found as of 2026-11-06 — (search returned none)

**Schrödinger Materials Science Suite**
- **Release 2026-2** led with "Generative AI for molecular materials", Nanoreactor with reaction-barrier predictions, an advanced analysis report for battery materials, MLFF-based reaction kinetics in periodic DFT, "Improved crystal structure prediction", and OPLS5 for metals (open beta) (search summary) — [Schrödinger release notes 2026-2](https://www.schrodinger.com/life-science/download/release-notes/release-2026-2/)
- **14 Oct 2026:** Schrödinger announced a Nature paper on multi-lithium-ion clustering in battery electrolytes, which is research rather than a software release — [Schrödinger press release PDF](https://s203.q4cdn.com/609444515/files/doc_news/2026/10/14/Schrdinger-Research-Published-in-Nature-Reveals-New-Insights-into-Lithium-Ion-Battery-Chemistry.pdf)
- No 2026-4 notes were indexed. 2026-3 (Bunsen agent, composite matrix design) was covered in the prior survey.

**CCDC Mercury / CSD**
- **2026.1 CSD Software Update (Apr 2026):** CSD-CrossMiner enhancements. **2026.1.1 (May 2026):** better BFDH morphology and VisualHabit performance in Mercury, and Mac parity with the April Windows/Linux features. **May 2026 data update:** 14,029 structures. All from a search summary of CCDC's What's New page, which did not render when fetched — [CCDC What's New](https://ccdc.cam.ac.uk/solutions/whats-new/)
- The **November 2025 CSD release** and CSD 6.00 added new data fields (wavelength, resolution, Flack parameter, data availability) and disorder handling and visualisation in Mercury and the Python API — [IUCr newsletter Nov 2025](https://www.iucr.org/news/newsletter/volume-33/number-6/latest-csd-data-and-software-release-november-2025); [CCDC disorder blog](https://ccdc.cam.ac.uk/discover/blog/how-to-visualize-handle-disorder-in-mercury-csd); [CSD 6.00 blog](https://www.ccdc.cam.ac.uk/discover/blog/introducing-cambridge-structural-database-6-00/)
- CCDC lists a "Strategic AI Technology Partnership with Sapio Sciences" blog post; only the title rendered — [CCDC What's New](https://ccdc.cam.ac.uk/solutions/whats-new/)

**VESTA:** no new evidence. It is still 3.5.8 (Aug 2022) per the prior survey, and none of this session's searches surfaced a VESTA 4 release.

### Inferences
- Within 2026, at least four peers (OVITO, Avogadro, Matlantis, Schrödinger) shipped or announced agent control of their environment, and Materials Studio made Python native. "Your AI assistant can drive the app" is now a common feature. For 1.2 it can be a supporting point, not the headline.
- Avogadro 2.1 is the most direct open-source threat. It now has an MCP bridge, CIF space-group perception, a polymer builder and ML-potential batch evaluation. Unlike Crystal Builder's MCP, its JSON-RPC surface does not obviously make every edit an undo step, and it has no MOF, topology, phonon or PXRD tooling. Avogadro is molecule-first.
- OVITO keeps adding crystal-viewer conveniences (VESTA-like bonds, periodic images, cell editing, MOL2 and MedeA readers). Its gravity remains MD trajectory analysis.
- CrystalMaker's eight-month silence since April 2026 suggests its next headline (11.8 or 12) is unannounced. Its trajectory (MOF automation, cavities, relaxation, shapes) points squarely at porous-framework users.

### Gaps
- **Not checked this session:** QuantumATK (latest Y-2026.03 notes are behind SolvNet per the prior survey), MedeA (searches returned only unrelated "3.12" software), ToposPro, iRASPA, Jmol/JSmol, ASE GUI and Crystal Toolkit / Materials Project web apps. No 2025-11 to 2026-11 release headline is sourced for any of them.
- The contents of the Materials Studio 2026 "What's New" PDF could not be extracted, so its feature list rests on search summaries.
- I could not determine whether Matlantis's in-terminal Claude Code installer actually shipped after May 2026.
- I could not confirm whether `avogadro-mcp` exposes undo-safe edits, or which tools it offers.

## Q2. New entrants in 2025–2026 (open-source or commercial): crystal/MOF building, web editors, AI-native materials GUIs

### Takeaway
No new open-source GUI for building crystals or MOFs (desktop or web) surfaced for 2025–2026. The new activity is **headless MCP servers for materials databases** (Materials Project, COD, OPTIMADE/GNoME) with no GUI of their own, plus vendor agent layers. A search for browser MOF builders returned only 2018–2020 tools (3DStructGen, OpenMX Viewer) and Crystal Builder itself.

### Cited Findings
- **Materials Project MCP servers:**
  - `forum-ai/mp-mcp` is generated from the MP API's OpenAPI spec. It is read-only and served through a hosted proxy at mp.forum-ai.org — [GitHub forum-ai/mp-mcp](https://github.com/forum-ai/mp-mcp)
  - A search summary says an official MP MCP server ships in `mp_api` v0.46+ with ~23 tools. This was not verified against a primary source — [mcpmarket listing](https://mcpmarket.com/server/materials-project-1); [Building an MCP server for MP](https://xiangyu-yin.com/content/post_mp_mcp.html)
- **Other materials MCP servers:** MIT-licensed "MCP Materials Server" (HeshamFS) fetches MP structures as CIF/POSCAR — [glama](https://glama.ai/mcp/servers/HeshamFS/mcp-materials-server). A COD MCP gateway (Pipeworx) is hosted, with an unconfirmed licence — [PulseMCP](https://www.pulsemcp.com/servers/crystallography). "Materials MCP" (GNoME via OPTIMADE) appears stale — [glama MatMCP](https://glama.ai/mcp/servers/ZuchGuillotine/MatMCP)
- **Web builders:** the only web structure builders found were 3DStructGen (2020, MIT; supercells, surface cleaving, vacuum layers; no net-based MOF assembly) — [J. Cheminform.](https://link.springer.com/article/10.1186/s13321-020-0411-2) — and OpenMX Viewer (a viewer, not a builder) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1093326318309598)
- **A fork of Crystal Builder** exists at `jigonzalez930209/Crystal-Builder` with the same description. Its activity and divergence were not checked — [GitHub](https://github.com/jigonzalez930209/Crystal-Builder)
- **Commercial MOF building:** SCM AMS still ships its Autografs-based Framework Builder (Edit → Framework → Builder, custom linker export, topology choice such as pcu) — [SCM tutorial](https://scm.com/doc/Tutorials/BuildingStructures/BuildingFrameworksAndReticularCompounds.html)

### Inferences
- The database-MCP servers complement Crystal Builder rather than compete with it. Each fetches a structure, but none builds, edits, validates or computes inside a window. A 1.2 feature that composes them would be cheap and on-theme: an agent pulls from MP or COD, then builds, relaxes and checks in Crystal Builder.
- The absence of new open MOF GUIs means Crystal Builder's reticular builder stays uncontested in open source. Its rivals for that user are CrystalMaker (commercial, Mac/Win) and AMS (commercial).

### Gaps
- I could not search GitHub topics systematically for new 2026 PySide or Qt crystal editors, or for MatterViz/Chemiscope updates, within the budget.
- I did not check journal software papers (J. Appl. Cryst., JCIM, Digital Discovery) from 2026 for new GUIs.

## Q3. What users repeatedly ask for, and white space no peer does well

### Takeaway
Forum evidence was thin in this session. Neither Reddit nor Matter Modeling SE threads surfaced in search, and old "VESTA alternative" lists dominate the results. The white-space conclusions therefore rest on **absence across release notes**. Across every 2026 release checked, no peer leads with the following: open GUI adsorption isotherms; MLIP-driven phase-stability or breathing workflows with free energies; correlated MOF defects; magnetic or modulated structures; structure-graded agent verification. These match the five gaps in the prior survey, and nothing in Nov 2025 – Nov 2026 closed them.

### Cited Findings
- **Generic "VESTA alternative" answers** still list Avogadro, CrystalMaker, Mercury, Olex2, iRASPA, XCrySDen and Jmol. No 2026-dated community discussion was found — [AlternativeTo](https://alternativeto.net/software/vesta-visualization-for-electronic-and-structural-analysis); [ResearchGate thread](https://www.researchgate.net/post/What-software-can-I-use-to-draw-unit-cell-structure); [crystalsymmetry blog](https://crystalsymmetry.wordpress.com/software-webpages/)
- **What vendors chose to headline is indirect evidence of demand:**
  - CrystalMaker moved toward MOF cavities and rings, faster relaxation, and shape prediction — [CrystalMaker notes](https://crystalmaker.com/crystalmaker/release-notes/mac/11/index.html)
  - Avogadro shipped batch ML-potential evaluation and a polymer builder — [Avogadro 2.1.0](https://github.com/OpenChemistry/avogadroapp/releases/tag/2.1.0)
  - Schrödinger shipped CSP improvements and generative AI — [Schrödinger 2026-2](https://www.schrodinger.com/life-science/download/release-notes/release-2026-2/)
  - Mercury shipped disorder handling and morphology speed — [CCDC disorder blog](https://ccdc.cam.ac.uk/discover/blog/how-to-visualize-handle-disorder-in-mercury-csd); [CCDC What's New](https://ccdc.cam.ac.uk/solutions/whats-new/)
- **Capabilities in several commercial tools without a strong open desktop equivalent:**
  - Crystal structure prediction in a GUI (Schrödinger 2026-2) — [Schrödinger 2026-2](https://www.schrodinger.com/life-science/download/release-notes/release-2026-2/)
  - Crystal shape and morphology prediction: CrystalMaker 11.5/11.6 and Mercury BFDH/VisualHabit — [CrystalMaker notes](https://crystalmaker.com/crystalmaker/release-notes/mac/11/index.html); [CCDC What's New](https://ccdc.cam.ac.uk/solutions/whats-new/)
  - MLFF fine-tuning from a GUI (Materials Studio 2026) — [T61-2025](https://www.3ds.com/support/documentation/resource-library/t61-2025-materials-studio-2026.md)
  - Automated cavity and ring filling (CrystalMaker 11.7) — [CrystalMaker notes](https://crystalmaker.com/crystalmaker/release-notes/mac/11/index.html)
  - Disorder modelling and visualisation (Mercury / CSD 6.00) — [CCDC disorder blog](https://ccdc.cam.ac.uk/discover/blog/how-to-visualize-handle-disorder-in-mercury-csd)

### Inferences
- **White space a small open app could own, ranked by fit with Crystal Builder's existing stack:**
  1. **End-to-end adsorption** in an open GUI: build, validate, relax, then compute an isotherm, all agent-drivable. No 2026 peer release touches it. CrystalMaker's "Filled Cavities" is geometric only.
  2. **"Which phase is stable at T?"**: MLIP plus quasi-harmonic free-energy ranking of polymorphs or breathing phases from a menu. Crystal Builder already holds MACE/ORB/MatterSim, phonopy and F(V,T). Schrödinger's CSP and Materials Studio's MACE are commercial and not presented this way.
  3. **Experiment-closed loop**: generate candidates, refine against measured PXRD (rietx), and report the best match. Mercury's PXRD Optimize (2025.3) is licence-gated and molecular-crystal oriented.
  4. **Disorder and partial occupancy** handled through to a computation-ready ordered model (supercell enumeration of occupancies). Mercury visualises disorder but does not enumerate it for simulation. This is plausible white space but unverified.
  5. **Morphology/BFDH**, a parity item that VESTA, CrystalMaker and Mercury users expect.
- **Agent integration alone is no longer differentiating.** What remains distinctive is *verifiable* agent edits (undo per step, typed verbs, diagnostics), which the vendor announcements do not emphasise. This is a supporting message for 1.2, not the headline.

### Gaps
- **No direct forum evidence was gathered.** I have no sourced Matter Modeling SE, Reddit or GitHub-issue threads with repeated user requests. A follow-up should query site-restricted searches (site:mattermodeling.stackexchange.com "MOF" / "CIF disorder" / "adsorption GUI") or the issue trackers of Avogadro, ASE and pymatgen directly.
- "No peer does X" claims are absence-of-evidence from release notes and searches, not exhaustive verification.
