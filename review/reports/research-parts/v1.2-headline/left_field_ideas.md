# Left-field extension ideas for Crystal Builder (oblique directions, not new engines)

Researched 2026-11-06. Scope: unconventional extensions only. Peer software, generative models, structure-from-diffraction, LLM agents and MOF adsorption are covered by other researchers and are left out on purpose. There are 18 ideas in 7 clusters. Each idea lists prior art, audience, feasibility in a Python/PySide6 app, and why it matters. Ideas marked **[WHITE SPACE]** are ones where I found no usable existing tool. "Feasibility" ratings are my own inferences, not sourced claims.

Crystal Builder capabilities these ideas build on: nets and topologies, twisted bilayer graphene, phonons, PXRD, xTB, ML potentials, Blender export, and the MCP server.

---

## Q0. Which left-field ideas are the strongest headline candidates?

### Takeaway
Three ideas stand out. Each pairs strong recent prior art with a clear gap that Crystal Builder's existing machinery already half-fills:
1. **"Nets to engineering lattices"**: export any RCSR net as a printable strut, shell or chainmail architected material (Ideas 5 and 6).
2. **"Hold it / hear it"**: printability-aware physical output (STL/3MF, magnet kits, glass engraving), plus phonon and PXRD sonification (Ideas 1–3 and 11).
3. **Aperiodic and hat-tile mode**, extending the twisted-bilayer machinery (Idea 7).

Accessibility for blind and low-vision chemists (Idea 12) is the clearest genuine white space for crystal software specifically.

### Cited Findings
- Recent work treats crystallographic space groups and nets as a design space for mechanical metamaterials. One preprint dataset covers all 36 cubic space groups, with about 1.95 million voxelized unit cells — [arXiv 2603.10934](https://arxiv.org/html/2603.10934v1)
- A 2025 *Science* paper turned crystalline network geometries into 3D-printed interlocked "chainmail" materials — [Caltech news](https://mce.caltech.edu/news/reimagining-chain-mail); [Illinois Experts record](https://experts.illinois.edu/en/publications/3d-polycatenated-architected-materials/)
- Phonon sonification software for materials data (SingingMaterials, built on STRAUSS) was released in 2026 and accepted to ICAD 2026 — [arXiv 2603.29037](https://arxiv.org/abs/2603.29037)

### Inferences
- Crystal Builder already generates nets (RCSR-style topologies) and has a Blender/mesh export path. That makes "net to printable architected lattice" a short step technically but a big jump in audience, reaching mechanical and additive-manufacturing engineers. No chemistry-side tool I found targets that crossover.
- Physical and sensory outputs (printing, engraving, sound) are cheap to build, demo well in talks and on social media, and set the app apart from VESTA and Mercury, which stop at the screen and a basic STL.

### Gaps
- I did not survey whether any commercial lattice-design tool (nTop, Carbon Lattice Engine, etc.) imports crystallographic nets or CIF. Checking that would firm up the "white space" claim for Idea 5.

---

## Q1. Physical output: printing, kits, glass

### Takeaway
3D-printing crystal structures is well established in teaching (Mercury, Jmol scripts, J. Chem. Educ./J. Appl. Cryst. papers). Every tool I found stops at "export a mesh", though. Nothing found handles printability, supports, cutting planes, magnet joints or glass-engraving point clouds for frameworks, nets or nanotubes.

### Cited Findings
**Idea 1: Printability-aware 3D-print export (STL/3MF/VRML, cell-cut models, printable unit cells)**
- Mercury can export a unit cell as monochrome STL or colour VRML for 3D printing. A mineralogy teaching activity recommends a packing view with spacefill style and cell axes shown — [SERC Carleton activity](https://serc.carleton.edu/teachearth/activities/312015.html)
- Mercury 4.0 (Macrae et al., *J. Appl. Cryst.* 2020, 53, 226–235) is cited as a modelling tool that generates 3D-printable models directly — [Casas 2020, J. Appl. Cryst. teaching article](https://journals.iucr.org/j/issues/2020/06/00/gj5252/index.html)
- "Programmatic conversion of crystal structures into 3D printable files using Jmol" (*J. Cheminform.* 2016) scripted CIF-to-printable conversion at scale (over 30,000 CIFs). It notes that a single asymmetric unit shows only a fragment, so complete unit cells must be generated — [PMC5122160](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5122160/); [J Cheminform PDF](https://jcheminf.biomedcentral.com/track/pdf/10.1186/s13321-016-0181-z)
- "3D-Printing Crystallographic Unit Cells for Learning Materials Science and Engineering" (J. Chem. Educ., ISSN 0021-9584) converts crystallography files into 3D unit-cell teaching aids — [library record](https://bvbvf1.bib-bvb.de/vufind/PrimoRecord/cdi_proquest_journals_1735732315). A reference list cites it as vol. 92, pp. 1960–1962 (2015) — [arXiv 2001.04267 review](https://arxiv.org/pdf/2001.04267)
- Casas (2020), "Teaching periodicity and aperiodicity using 3D-printed tiles and polyhedra", *J. Appl. Cryst.* 53, 1583–1592 — [IUCr](https://journals.iucr.org/j/issues/2020/06/00/gj5252/index.html)
- Hobbyist and educator ecosystem: printable STL models of the six crystal classes (SERC, 2015) — [SERC](https://serc.carleton.edu/details/files/64834.html); a BCC unit cell on Thingiverse — [STLFinder](https://stlfinder.com/model/body-centered-cubic-unit-cell-full-atoms-d3y4gQx4/1340952); a blogger's own CIF-to-STL script — [blog, 2017](https://jiangrundong.blogspot.com/2017/12/3d-printed-models-of-crystal-structures.html)
- Chemistry World coverage of crystal printing: "print it out and hold it in your hand" — [Chemistry World](https://chemistryworld.com/news/how-to-print-a-crystal-in-3d/7274.article)

**Idea 2: Auto-generated magnet-joint and snap-fit model kits**
- Commercial magnetic lattice kits exist for fixed structures only. NaCl 3×3×3 and 4×4×4 kits have magnets embedded in each ion — [W.F. Education 3×3×3](https://wf-education.com/mo110120.html), [4×4×4](https://wf-education.com/mo110125.html). Flinn's version uses six magnets per ion for 6:6 coordination — [Flinn catalog](https://www.flinnsci.com/catalogs/HEC%20Curriculum%20Catalog%20V2/files/basic-html/page63.html). A magnetic ice kit is also sold — [Indigo Instruments](https://www.indigoinstruments.com/molecular_models/atomag/atomag-ice-magnetic-model-63009.html)
- Printables hosts a community "Molecular magnetic building kit" — [Printables](https://www.printables.com/education/263023-molecular-magnetic-building-kit)
- 3D-printed puzzle pieces with pockets for commercial neodymium magnets were used for DNA base pairing (Sophia University) — [3DPrinting.com](https://3dprinting.com/news/researchers-release-new-magnetic-3d-printable-dna-model/)

**Idea 3: Subsurface-laser-engraving ("bubblegram") point-cloud export**
- Subsurface laser engraving builds a 3D point cloud of micro-fractures inside K9 optical glass from X, Y, Z coordinates — [FacFox explainer](https://facfox.com/docs/kb/sub-surface-3d-laser-engraving-a-brief-explanation); [xTool how-to](https://www.xtool.eu/blogs/how-to/how-to-3d-laser-engrave-crystal-bubblegram)
- Molecules are already a known subject. xTool describes engraving a "metalla-radialene" molecule from Prof. Xia inside glass — [xTool blog](https://www.xtool.com/blogs/xtool-academy/engraving-crystal-as-memory-gift). A caffeine-molecule glass sculpture is shown in the Bubblegram article — [Wikiwand: Bubblegram](https://www.wikiwand.com/en/articles/Bubblegram)
- Thin filigree and hairline features can vanish at low point density — [UV-laser explainer](https://themakerschest.com/blogs/laser-engravers/what-is-3d-crystal-engraving-how-uv-lasers-create-internal-glass-engravings). An MIT fab-class student engraved K9 cubes — [MIT fab class 2025](https://fab.cba.mit.edu/classes/863.25/people/EghosaOhenhen/week14.html). Most SSLE sources are vendor pages, so treat their claims as marketing-leaning.

**Idea 4: "Real crystal" habit/morphology view, printable habit, phone-photo comparison**
- BFDH predicts crystal habit from lattice geometry and symmetry. Kaminsky's free WinXMorph (Windows, educational) implements it. He reports that symmetry-guided distortions often get closer to observed habits, and argues that virtual crystal visualisation sparks student interest — [WinXMorph page](https://chem.washington.edu/research/publications/winxmorph); [J. Appl. Cryst. 2007 CIF applications](https://journals.iucr.org/j/issues/2007/02/00/cg5057/index.html)
- BFDH morphology is also offered in commercial tools: Mercury CSD-Particle — [CCDC PDF](https://www.ccdc.cam.ac.uk/media/Particle-shape-calculation-using-CSD-particle.pdf); BIOVIA Materials Studio Morphology — [3DS PDF](https://www.3ds.com/fileadmin/PRODUCTS-SERVICES/BIOVIA/PDF/BIOVIA-material-studio-morphology.pdf)

### Inferences
- **Idea 1.** *Audience:* teachers, outreach, makers, and MOF/net researchers who want a desk model. *Feasibility:* high. Meshing spheres and cylinders is easy with trimesh or manifold3d. The differentiator is printability logic: minimum bond diameter for a given scale, slicing a cell along (hkl) planes into two printable halves, flat-bottom cuts, and 3MF per-element colour for multi-material printers. *Why it matters:* existing exports (Mercury, Jmol) are generic meshes. A "print this MOF on a Bambu or Prusa" button is a demo-friendly hook.
- **Idea 2 [WHITE SPACE].** All the magnetic kits I found are fixed SKUs (NaCl, ice). Nothing generates kit parts from an arbitrary structure. A generator could output one part per symmetry-unique site, with magnet pockets along bond vectors at the correct angles. That fits Crystal Builder's Wyckoff/symmetry machinery directly. *Feasibility:* medium, mostly CSG geometry. *Audience:* teachers, museum outreach, the maker community.
- **Idea 3 [WHITE SPACE for crystal tools].** Atoms are already a point cloud, so an export with configurable point density per atom (surface-sampled spheres plus sparse bond lines) is a few hundred lines of code. *Audience:* conference and award gifts, department outreach, thesis-defence keepsakes. Cheap, playful, and unusual for a science app.
- **Idea 4.** Crystal Builder could add BFDH (and later attachment-energy, using UFF/xTB/MLIP energies) to show the macroscopic crystal, then print it. A phone-photo matching step ("does my crystal look like the prediction?") would be **[WHITE SPACE]**; I found nothing.

### Gaps
- I did not find a J. Chem. Educ. paper on magnet-joint printed crystal lattice kits specifically. Searches turned up only DNA-model and commercial examples.
- I could not access the full Casas 2020 or Jmol papers (403 / not fetched), so I don't have their design rules (minimum strut diameter, supports).
- I found no tool that does printability checks for crystal models. The claim that this is absent is based on a limited search.
- Phone-camera habit capture and matching has no prior art in my searches.

---

## Q2. Crystal machinery as engineering design: architected lattices, chainmail, metasurfaces

### Takeaway
This is the most substantive crossover. Engineers are now explicitly using crystallographic space groups and crystal nets to design mechanical and electromagnetic metamaterials. A 2025 *Science* paper turned crystal networks into printable chainmail-like materials. A chemistry-native net builder that exports engineering-grade lattices would serve an audience Crystal Builder doesn't currently reach.

### Cited Findings
**Idea 5: "Net to architected lattice" export (strut, TPMS-like shell, voxel) for additive manufacturing**
- Symmetry-guided framework over all 36 cubic space groups (195–230): about 1.95M voxelized unit cells at relative densities 0.05–0.50. The authors report rare pentamode designs and isotropic-auxetic architectures, and train a 3D CNN for stiffness. This is a 2026 preprint, not yet peer-reviewed — [arXiv 2603.10934](https://arxiv.org/html/2603.10934v1)
- "Designing Mechanical Meta-Materials by Learning Equivariant Flows" (ICLR 2025) covers cellular solids under all 17 2D crystallographic (wallpaper) groups — [arXiv 2410.02385](https://arxiv.org/pdf/2410.02385)
- Crystallographic symmetry choice affects how close topology-optimized designs get to theoretical stiffness limits — [AMCA proceedings](https://amcaonline.org.ar/ojs/index.php/mc/article/view/5968)
- Lipidic cubic phases (gyroid-like) used as bio-inspired templates for mechanical metamaterials (Utah) — [Utah PDF](https://w.mech.utah.edu/wp-content/uploads/sites/116/2023/11/Computational-Design-of-Bio-inspired-Mechanical-Metamaterials-Based-on-Lipidic-Cubic-Phases.pdf)
- A 2026 IUCr Acta A commentary describes MOF "molecular truss lattices" (Wang et al., 2025), whose topology suits a mechanical-metamaterial reading. It also says the graph topology of supersymmetric nets dictates how a material stiffens, yields and recovers — [Acta Cryst. A 2026 commentary](https://journals.iucr.org/a/issues/2026/01/00/me6359/index.html) (abstract/snippet only; full text returned 403)
- RCSR is the standard reference for classifying framework topologies — [Wikipedia: RCSR](https://en.wikipedia.org/wiki/Reticular_Chemistry_Structure_Resource); IUCr newsletter on the "royal family" of periodic nets — [IUCr Newsletter](https://www.iucr.org/news/newsletter/volume-34/number-1/periodic-platonic-solids-royal-family-of-periodic-nets)

**Idea 6: "Chainmail mode": polycatenated architected materials from crystal nets**
- Zhou, Daraio et al., "3D polycatenated architected materials", *Science* 387(6731):269–277, 17 Jan 2025, DOI 10.1126/science.adr9713. The authors translated crystalline network geometries into interlocked rings and cages. The materials behave like non-Newtonian fluids at small loads and like lattices or foams at larger strains. They were printed in acrylic polymers, nylon and metals, and microscale versions change shape under electrostatic charge — [Caltech MCE news](https://mce.caltech.edu/news/reimagining-chain-mail); [ScienceDaily](https://sciencedaily.com/releases/2025/01/250121162100.htm); [Princeton record](https://collaborate.princeton.edu/en/publications/3d-polycatenated-architected-materials/)

**Idea 18: 2D nets as metasurface and photonic templates**
- Researchers built 72 electromagnetic metasurfaces using atom positions and lattice vectors of 2D crystal nets as templates, with a metallic cross as the meta-atom — [PMC10160015](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10160015/)
- Deployable kirigami patterns can be built from any of the 17 wallpaper groups. This came from a search summary over metamaterial results (possibly [arXiv 2411.17142](https://arxiv.org/pdf/2411.17142) or [NSF PAR 10296202](https://par.nsf.gov/servlets/purl/10296202)); I did not pin down the exact primary source, so verify before citing.

### Inferences
- **Idea 5.** *Audience:* mechanical engineers, AM designers, architects, metamaterials groups. They know gyroids but not RCSR, and Crystal Builder knows RCSR. *Feasibility:* medium. Nets map to struts, struts become a watertight mesh at a chosen relative density (manifold3d or SDF voxelization), with tiling to a part envelope. A Wyckoff-aware generator ("pick a cubic space group, place a node, get a lattice") would mirror the 2026 preprint's design space interactively. *Why it matters:* the same net abstraction serves MOFs and machine parts, so the app could be "the RCSR for engineers".
- **Idea 6.** Swapping each node for an interlocked cage or ring is a geometric transform on the net. A "catenate this net" button that outputs printable chainmail would be a very visual demo, with direct lineage to a 2025 *Science* paper. *Feasibility:* medium. Ring and cage geometry with collision-free interlocking needs care.
- **Idea 18.** Exporting 2D nets, wallpaper groups and twisted-bilayer moiré patterns as DXF/GDSII-style layouts would reach photonics and metasurface people. It would also feed laser-cutters (kirigami sheets, acrylic layered lattice models). *Feasibility:* high for DXF via ezdxf (a library choice, not sourced). Lower for GDSII.

### Gaps
- I could not verify the primary Wang et al. 2025 "molecular truss lattices" paper. It is known only via the 2026 commentary snippet.
- I didn't check whether nTop, Carbon or similar lattice tools import nets or CIFs. If they do, Idea 5 is less novel.
- I found no specific prior art on laser-cut layered crystal models. That part of Idea 18 rests on inference only.

---

## Q3. Aperiodic order and tilings

### Takeaway
The 2023 "hat" aperiodic monotile has a graphene-like electronic structure in tight-binding models and has been lithographically fabricated. Quasicrystal and aperiodic tiling teaching with 3D prints has also been published. Crystal Builder's twisted-bilayer and carbon tooling makes an "aperiodic carbon / hat lattice" mode a distinctive niche.

### Cited Findings
**Idea 7: Aperiodic / hat-tile / quasicrystal-approximant builder**
- Smith, Myers, Kaplan and Goodman-Strauss, "An aperiodic monotile", *Combinatorial Theory* 4(1), 2024 (discovered 2023) — [arXiv 2303.10798 via arxivlens](https://arxivlens.com/PaperView/Details/an-aperiodic-monotile-2318-1547544); chiral "spectre" follow-up — [UNAM ComDig 2023](https://comdig.unam.mx/2023/06/07/a-chiral-aperiodic-monotile)
- Schirmann, Franca, Flicker and Grushin (2024): in a tight-binding model on the hat tiling, the spectral function looks strikingly like graphene's, with six-fold symmetry and Dirac-like features. The authors suggest experimental realizations — [Bristol research portal](https://research-information.bris.ac.uk/en/publications/physical-properties-of-an-aperiodic-monotile-with-graphene-like-f/); [arXiv 2307.11054](https://pdf.arxiv.org/pdf/2307.11054)
- A monotile lattice was fabricated on SiN films (2025 preprint) — [arXiv 2506.07561](https://arxiv.org/pdf/2506.07561v1)
- Casas (2020) teaches periodicity and aperiodicity with 3D-printed tiles and polyhedra — [J. Appl. Cryst.](https://journals.iucr.org/j/issues/2020/06/00/gj5252/index.html)
- In 2014, BBC Radio 4 turned a quasicrystal diffraction photo into sound — [IYCr2014 audio](https://www.iycr2014.org/resources/audio-clips)

### Inferences
- *Audience:* condensed-matter theorists, math and art crossover (Bridges community), teachers. *Feasibility:* medium. Generate hat or Penrose patches by substitution rules, decorate vertices with atoms (a "hat-graphene" patch), then run xTB/MLIP relaxations and simulated diffraction on finite patches or periodic approximants. *Why it matters:* it is a beautiful, timely and very shareable feature, and it uses machinery the app already has (carbon builders, relaxations, PXRD).

### Gaps
- I could not confirm a molecular self-assembly of a hat or aperiodic tiling. A title, "An aperiodic chiral tiling by topological molecular self-assembly", appeared on arxivlens, but I could not verify its authors or details.
- I found no existing desktop chemistry tool with a hat or monotile builder. This is likely **[WHITE SPACE]**, but the search was limited.

---

## Q4. Immersive, AR and haptics

### Takeaway
Multi-user interactive MD in VR (Narupa) has a published materials-science track record, including DL_POLY and 15 materials and catalysis applications. AR for crystal structures in teaching is an active small field (2024–2026). The cheapest high-impact path for Crystal Builder is USDZ/glTF export for phone and Vision Pro Quick Look AR. A bigger option is a bridge to an iMD-VR server. Haptic crystal tools are white space but need special hardware.

### Cited Findings
**Idea 8: Multi-user interactive MD in VR (Narupa-style bridge)**
- Narupa is an open-source multi-person VR framework for real-time interactive MD. Users can pass a simulated C60 between them — O'Connor et al., *J. Chem. Phys.* 2019 — [arXiv 1902.01827](https://arxiv.org/abs/1902.01827v3)
- Crossley-Lewis et al. (*J. Mol. Graph. Model.* 2023) pair Narupa with DL_POLY for 15 materials and catalysis applications, including Li fast-ion conduction (vacancy vs. interstitialcy transport) and molecule diffusion in H-ZSM-5 zeolite pores. Files are on Zenodo — [LAMMPS abstract page](https://lammps.org/abstracts/abstract.32224.html)
- Nanome on Apple Vision Pro: a "lite" demo, NanoSpin, launched March 2024. As of a May 2024 roadmap post, the full port was not yet available — [NanoSpin App Store](https://apps.apple.com/app/nanospin/id6478713911); [Nanome roadmap](https://nanome.ai/blog/nanome-on-apple-vision-pro-roadmap)

**Idea 9: One-click AR (USDZ/glTF) for phones, Vision Pro and classrooms**
- Protein viewers on Vision Pro already exist: Vision ProTein (immersive viewer) — [App Store](https://apps.apple.com/us/app/vision-protein/id6499503487). A search summary also described a "FoldVision" app that exports molecules as USDZ, but I did not capture its URL (see Gaps).
- "Crystal View" (UiTM, 2024) is a smartphone AR app for exploring unit cells (Al, carbon steel) for engineering students — [UiTM repository](https://ir.uitm.edu.my/id/eprint/142997/)
- Saatzer, Syskowski, Unterlass and Huwer ran a head-mounted AR study in solid-state chemistry. Students valued exploring 3D crystal structures together in AR — [Unterlass lab](https://unterlasslab.com/?p=5715); [Konstanz repository](https://kops.uni-konstanz.de/server/api/core/bitstreams/683c14a8-4041-4af2-841b-c07edd8a612e/content)
- MoleculAR (J. Chem. Educ. 2024, free) and ARChem (RMIT, June 2024, free) are molecular AR apps — [MoleculAR GitHub](https://github.com/chagunda/moleculAR); [RMIT news](https://www.rmit.edu.au/news/all-news/2024/june/archem-app). A 2025 systematic review screened 81 Scopus studies (2020–2025) on AR in chemistry education — [INCOBEST proceedings](https://proceedings.ums.ac.id/incobest/article/view/6371)

**Idea 10: Haptic "feel the lattice" mode**
- Bivall, Ainsworth and Tibell (*Science Education* 2011): 20 postgraduates did protein–ligand docking. The haptic group gained more understanding and reasoned more in terms of forces — [Nottingham repository](https://nottingham-repository.worktribe.com/output/23577496/do-haptic-representations-help-complex-molecular-learning); [InformalScience](https://www.informalscience.org/do-haptic-representations-help-complex-molecular-learning)
- Earlier GROPE work found haptics cut the time to find low-energy molecular positions. A 2007 high-school study (HaptiChem, 43 students) reported increased curiosity — same source as above.

### Inferences
- **Idea 9** is the quick win. Crystal Builder already exports to Blender, so emitting USDZ/glTF from the same scene graph gives AR Quick Look on any iPhone or iPad and Vision Pro, with no app needed. That pairs with a QR code on a slide or poster. *Feasibility:* high.
- **Idea 8.** Crystal Builder already wraps ASE-style calculators (UFF, xTB, MLIPs). Streaming frames to a Narupa-compatible server, and taking user forces back, would let groups "pull" a Li ion through a lattice together, driven by MACE or ORB. *Feasibility:* medium–low (networking, frame rate). *Audience:* teaching labs, outreach, catalysis groups.
- **Idea 10 [WHITE SPACE for crystals].** All the haptic evidence is protein or ligand work. A crystal analogue (feeling the potential energy surface while dragging an interstitial) is unbuilt. Commodity haptic hardware is niche, though, so priority is low. Phone vibration on AR is a possible cheap proxy (speculative).

### Gaps
- I could not confirm the current name or status of the Narupa successor project (I believe it may have been rebranded, but this is unverified) or whether its Python server API is stable.
- I found no crystal-specific features in Nanome's visionOS apps.
- I couldn't verify the "FoldVision" USDZ-export claim against a primary App Store URL.
- The "Mirage Crystallography" AR app appeared only on an auto-generated listing page and could not be verified.

---

## Q5. Sonification and accessibility

### Takeaway
Sonification of materials data is a live 2026 research topic (SingingMaterials for phonon DOS) with a long artistic history (diffraction to sine synthesis, BNL scattering sonification). Accessibility work in chemistry is concentrated in the Shaw lab (Baylor). I found nothing that makes crystal-structure software accessible to blind users. Crystal Builder computes phonons and PXRD, so it could ship "listen to your material" and a tactile/screen-reader mode cheaply.

### Cited Findings
**Idea 11: Sonify phonon DOS, PXRD patterns and MD trajectories**
- Whalley, Shepherd, Boehringer, Knotts, Vickers et al., "Singing Materials: Initial experiments in applying sonification to phonon spectra" (arXiv 2603.29037, v1 March 2026, v2 July 2026, accepted to ICAD 2026). It sonifies phonon DOS from the Materials Project with spectral, synthesised and sample-based approaches. The software, SingingMaterials, is a modular Python package built on the STRAUSS toolkit. It includes a user study on whether listeners can distinguish materials by sound — [arXiv 2603.29037](https://arxiv.org/abs/2603.29037)
- "X-Rays" is a musical piece that maps simulated NaCl diffraction peaks to sine frequencies, with intensity as amplitude — [GitHub dsshen/x-rays](https://github.com/dsshen/x-rays)
- Brookhaven's Kevin Yager and Margaret Schedel treat x-ray scattering data as additive synthesis. Tightly packed metals sound higher-pitched — [BNL newsroom](https://www.bnl.gov/newsroom/news.php?a=214479); [Newswise](https://www.newswise.com/articles/view/716513/?sc=c57)
- Georgia Tech's Asegun Henry sonified atomic vibrations in crystalline silicon. Data that looked like white noise revealed a pattern when heard — [insideHPC sonification tag](https://insidehpc.com/tag/sonification/)
- IYCr 2014: BBC Radio 4 sound designer Sam Conran turned diffraction photos (including a quasicrystal) into sound — [IYCr2014 audio clips](https://www.iycr2014.org/resources/audio-clips)

**Idea 12: Accessibility mode (screen-reader structure narration, tactile exports, colour-blind palettes)**
- Bryan Shaw's Baylor group (*Science Advances* 2021): students identified 3D protein models by mouth with 85.59% accuracy, comparable to visual recognition. The team says the approach could apply to models of anything — [Baylor news](https://news.web.baylor.edu/news/story/2021/baylor-study-uses-candy-models-make-stem-imagery-accessible-students-visual); [News-Medical](https://www.news-medical.net/news/20210529/Candy-like-models-could-make-science-more-accessible-to-visually-impaired-students.aspx)
- The same group 3D-prints lithophanes of scientific images (e.g., gels, spectra) that blind researchers can interpret — [EurekAlert](https://www.eurekalert.org/news-releases/475548); NIH SEPA program with the Texas School for the Blind — [Texas Standard](https://texasstandard.org/stories/chemistry-program-blind-low-vision-texas-students-nih-grant-baylor-university/); [NIGMS](https://www.nigms.nih.gov/node/145041)
- "Applied computational chemistry for the blind and visually impaired" (J. Chem. Educ. 2012) combined tactile drawings, model kits, existing software, Bash and Perl scripts, and 3D printing — [Missouri State BearWorks](https://bearworks.missouristate.edu/articles-cnas/2954)
- Broader context: [Chemistry World on accessible labs](https://chemistryworld.com/careers/visionary-chemistry-is-making-labs-accessible-to-blind-students-and-researchers/4018758.article); [Science Friday](https://www.sciencefriday.com/segments/chemistry-for-blind-and-low-vision-people/)

### Inferences
- **Idea 11.** *Feasibility:* high. Crystal Builder already computes phonon DOS and PXRD, so a "Play" button (numpy plus sounddevice or a WAV export) is a weekend feature. SingingMaterials and STRAUSS may be reusable directly as Python dependencies (licence to be checked). *Audience:* outreach, BLV users, people making social-media clips, ICAD/sonification researchers. Sound also suits real analysis such as hearing soft modes or imaginary frequencies, though that is speculative and unvalidated.
- **Idea 12 [WHITE SPACE for crystal software].** No crystal tool I found offers screen-reader-first operation. Crystal Builder could build a deterministic text description of a structure (formula, space group, coordination environments, net topology, pore sizes from Zeo++) and expose it through Qt accessibility and the MCP server. It could add one-click tactile outputs: a printed model (Idea 1) and a lithophane of the PXRD pattern or a 2D slice. Colour-blind-safe element palettes are trivial to add. *Audience:* BLV students and researchers, accessibility-mandated courses. *Why it matters:* it is distinctive, it signals mission, and it has very little competition.

### Gaps
- I did not find a published study of sonification for crystallographers' quantitative analysis. Current uses are artistic, educational or early research.
- I found no source on screen-reader support in VESTA, Mercury, Avogadro and similar tools, so the "no competition" claim rests on absence of evidence.
- SingingMaterials' code repository and licence were not linked from the arXiv page.

---

## Q6. Games, puzzles and citizen science

### Takeaway
Crystallographic symmetry games exist only for 2D wallpaper groups (Escher Web Sketch, XtereO) and diffraction (vDiffraction). I found no 3D space-group, Wyckoff or "build this net" game. Citizen science has real crystallographic precedent: Foldit players built top-quality crystal structures (Nature Communications 2016). Cornell's UDiscoverIt applied volunteers to materials phase mapping.

### Cited Findings
**Idea 13: Symmetry and Wyckoff puzzles, "build this net" challenges for courses**
- EPFL's Escher Web Sketch was built for periodic decorations and became a crystallography teaching tool covering the 17 plane groups — [EPFL](https://www.epfl.ch/schools/sb/research/iphys/teaching/crystallography/escher-web-sketch/)
- XtereO is a game for university crystallography students, supervised by Dr. M.J. Mayayo (Zaragoza) — [skich.app](https://skich.app/games/xtereo)
- vDiffraction is an ILL serious game on diffraction and crystals — [ILL](https://www2017.ill.eu/for-ill-users/support-infrastructures/software-scientific-tools/vdiffraction)
- Wolfram Demonstrations "Design a Tile for the p3 Wallpaper Group"; iSymmetry app (iOS) — [Wolfram](https://demonstrations.wolfram.com/DesignATileForTheP3WallpaperGroup/); [App Store](https://apps.apple.com/es/app/isymmetry/id565956977?l=en)
- 2025 Bridges math-art paper on wallpaper-group interlocking assemblies — [Bridges 2025 archive](https://archive.bridgesmathart.org/2025/bridges2025-5.pdf); [Substack](https://apieceofthepi.substack.com/p/wallpaper-groups-and-interlocking)

**Idea 14: Citizen-science / crowdsourced "design a stable framework" challenges**
- Foldit (Baker lab, about 735,000 registered users). In a 2016 Nature Communications study, Foldit players produced the most accurate crystal structure models in a competition — [PubMed 27633552](https://pubmed.ncbi.nlm.nih.gov/27633552/); [Chemistry World](https://www.chemistryworld.com/opinion/bringing-video-games-into-the-protein-fold/3010769.article)
- Cornell Materials Discovery used volunteers on the UDiscoverIt platform to spot crystal-structure patterns for fuel-cell and solar materials — [Cornell CS](https://webedit.cs.cornell.edu/node/8171)
- In a human-computation game for materials microstructure design, teams beat solo players on complex problems — [NSF PAR](https://par.nsf.gov/servlets/purl/10410877)

### Inferences
- **Idea 13 [WHITE SPACE in 3D].** Crystal Builder has the spglib/Wyckoff and net machinery to auto-generate puzzles. Examples: "place one atom; the app applies the space group; reach this target structure", "identify the space group of this rotating cell", "build the **dia** net from these SBUs". *Audience:* undergraduate crystallography and inorganic courses, MOOCs. *Feasibility:* high. It is mostly UI plus scoring against a target (structure matcher). A "classroom mode" exporting results is a plus.
- **Idea 14.** The scoring engine already exists (xTB/MLIP energies, Zeo++ pore metrics). A weekly "design the lowest-energy porous framework with X" leaderboard is plausible. Real citizen science needs a server and a community, so *feasibility* is low–medium as a desktop feature. A lighter version is a competition mode for classes and hackathons.

### Gaps
- I didn't find usage numbers or current availability for XtereO or vDiffraction.
- I found no materials-design citizen-science game at Foldit scale. This may be **[WHITE SPACE]** or I may have missed it.

---

## Q7. Cross-domain reuse, sharing, and figure-to-structure

### Takeaway
Crystal net machinery maps directly onto DNA-origami-framed nanoparticle lattices, where frame geometry sets lattice topology. Web sharing and notebook embedding have partial prior art (Crystal Toolkit, anywidget viewers). Extracting a crystal structure from a published figure into a CIF appears to be genuine white space. The nearest work only classifies XRD plots in papers.

### Cited Findings
**Idea 15: DNA-origami and colloidal-crystal lattice design mode**
- Tian et al. (*Nature Materials* 2016): DNA-encoded nanoparticles sit at vertices of polyhedral origami frames. The frame shape sets the lattice topology, so the same nanoparticle can form different lattices — [PMC5282967](https://pmc.ncbi.nlm.nih.gov/articles/PMC5282967); [ScienceDaily](https://www.sciencedaily.com/releases/2016/06/160613122343.htm)
- In 2022 (*Chem. Sci.*), origami frames were used as assembly units with programmable bridging strands. The authors note that periodic arrangement of internal DNA modules remains a challenge — [RSC](https://pubs.rsc.org/en/content/articlepdf/2022/sc/d1sc05060e)
- caDNAno is the most reliable lattice-based origami design tool, and such tools are mostly used by experts — [arXiv 2104.15016 review](https://arxiv.org/pdf/2104.15016). Triangulated truss origami tool (Matthies et al., *Nano Lett.* 2016) — [ChemistryViews](https://www.chemistryviews.org/?p=32194). Review of DNA-based crystal engineering — [NSF PAR](https://par.nsf.gov/servlets/purl/10475738)

**Idea 16: Figure-to-structure (old paper or figure image to CIF)**
- The closest found: "ERAF4XRD" (Mostafa et al., reported as arXiv 2609.18583, 2026) mined 3,150 candidate figures from 273 papers. 282 were genuine XRD plots, and the best classifier reached 98.7% accuracy. Known only from a **secondary blog summary**; verify before use — [Pebblous blog](https://blog.pebblous.ai/blog/paper-figures-to-xrd-database/en/)
- CIF is now an ML text target (CrystaLLM), which shows CIFs are machine-generatable from text-like inputs — [CrystaLLM, PMC11624194](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11624194/)

**Idea 17: Shareable web links, notebook embeds, and AR QR codes**
- Crystal Toolkit is an interactive web app and component library on Plotly Dash for viewing and transforming crystal structures. It has been deployed as a Hugging Face Space (LeMaterial) — [GitHub fork](https://github.com/sweitzner/crystaltoolkit); [HF Space app.py](https://huggingface.co/spaces/LeMaterial/materials_explorer/blob/main/app.py)
- A Materials Virtual Lab notebook shows an "Interactive Crystal Toolkit Structure Viewer" — [nbviewer matgenb](https://nbviewer.jupyter.org/github/materialsvirtuallab/matgenb/tree/master/notebooks)
- tricor offers an anywidget-based Three.js structure viewer for Jupyter — [tricor docs](https://tricor.readthedocs.io/en/latest/visualization/structure_viewer.html)

### Inferences
- **Idea 15.** Crystal Builder's nets-with-SBUs abstraction maps closely onto "polyhedral DNA frame plus nanoparticle at vertices". A mode that picks a net, proposes the frame polyhedron and outputs inter-particle distances and frame edge lengths (in DNA helix units) would serve DNA nanotech and colloid groups. They currently move from caDNAno to lattice design by hand. *Feasibility:* medium for geometry. Export to caDNAno or oxDNA formats would need format work (not researched).
- **Idea 16 [WHITE SPACE].** I found no tool that reads a ball-and-stick or polyhedral figure, or a printed table of fractional coordinates, and outputs a CIF. A practical version is "table of coordinates from a scanned paper (OCR) plus a cell and space group typed in, giving a validated CIF with a symmetry check". That is feasible with OCR, and a vision LLM is optional. Image-only reconstruction is a research problem. *Audience:* anyone working with pre-CIF-era literature (1950s–1990s mineral and inorganic structures).
- **Idea 17.** A self-contained HTML export (structure plus a JS viewer inline) and a Jupyter anywidget would make Crystal Builder structures shareable in papers' SI, Slack and notebooks. Adding a QR code that opens the USDZ (Idea 9) on a phone adds the AR bridge. *Feasibility:* high. A git-friendly canonical text format for "structure diffs" and provenance badges is plausible, but I didn't research prior art for it.

### Gaps
- I didn't verify ERAF4XRD in the primary source.
- I didn't research DECIMER-style 2D molecule image recognition, or whether any vision model has been tested on crystal-structure figures.
- I didn't research git-friendly structure diffs, provenance badges, live co-editing, voice control, lab-hardware integrations (diffractometer drop folders, ELNs), moiré materials beyond graphene, or protein crystal packing. These were out of tool budget and remain open leads.
- I didn't confirm the official Crystal Toolkit repository's current Jupyter and embed status. The GitHub link above is a fork.
