# Agentic materials and crystal modelling: evidence for an "agent-native" 1.2 headline feature

Scope note: research done 2026-11-06. The prior survey (`reports/Crystal Builder feature landscape.md`, 2026-10-09, and `research_notes/Crystal Builder feature landscape/agentic_science.md`) already covers El Agente Gráfico (arXiv 2602.17902), El Agente Sólido, OVITO 3.16's AI Agent panel, MCP spec 2025-11-25 Tasks/annotations, fairchem-mcp, DREAMS/MDCrow, MatTools, ChemCrow grading, ChimeraX `mcp`, agentic-pymol, Blender MCP CVE-2026-10688, Schrödinger Maestro Assistant and Bunsen, and the Materials Project MCP. This file does not repeat them except where new evidence changes the picture. Very little genuinely post-9-October material turned up. Most of the "new" items below are August–October 2026 work the prior survey did not cite. About 30 searches and fetches were run, so coverage is broad but not exhaustive.

## 1. What is new since October 2026 (and what was missed before): agent papers, products, MCP servers, desktop AI panels

### Takeaway
The clearest new development is **high-throughput agentic campaigns run as typed, provenance-tracked workflow graphs**: El Agente Potente (Sept 2026) and AtomisticSkills (May 2026). The field's own head-to-head numbers show these beat a free-form coding agent on both correctness and cost. No surveyed desktop app has an agent-run campaign view. OVITO shipped 3.17 and ovito-mcp 2026.3 in late October with no new agent capability found. Materials MCP servers are multiplying, but they are community wrappers of databases and engines, not structure editors.

### Cited Findings
**Campaign-scale agent systems (the most relevant new prior art)**
- **El Agente Potente** (Ko, Bai, …, Bernales, Aspuru-Guzik; arXiv 2609.14840, submitted 13 Sept 2026) is "High-Throughput Agentic Atomistic Simulations." It combines **typed execution graphs** for standard workflows, where LLMs only plan and route while deterministic Python handles computation and validation, with a coding agent for custom workflows that calls existing Potente functions. It claims "structured and provenance-aware execution." — [arXiv abstract](https://arxiv.org/abs/2609.14840)
- Potente campaign scales: a reproducibility study on **500 Materials Project structures × 5 runs** (elasticity, phonon C_V), checked against a manually scripted reference. An MLIP benchmark covered **1,000 bulk crystals × 3 models (MatterSim, Orb-OMAT, MACE-OMAT)**, and "All 3,000 model–structure calculations completed successfully." Perovskite and Li-conductor discovery used 5 compositions × 10 generated candidates each. MOF Widom insertion ran on 5 CoREMOF structures with 20,000 insertions per MOF–adsorbate pair. Fe(100) adsorption reduced 49 sites to 4 symmetry-distinct environments. — [arXiv HTML](https://arxiv.org/html/2609.14840)
- **Potente vs Claude Code with skills, on the same HKUST-1 GCMC task (5 runs each):**

  | Run by | CO₂ uptake (mmol/g) | Heat of adsorption (kJ/mol) | Token cost per run |
  |---|---|---|---|
  | Claude Code with skills | 1.25 ± 0.57 | 13.81 ± 0.77 | $0.638 ± 0.139 |
  | Potente | 1.88 ± 0.12 | 22.79 ± 0.53 | $0.152 ± 0.003 |

  **Only 2 of 5 Claude Code runs considered pre-relaxing the framework.** — [arXiv HTML](https://arxiv.org/html/2609.14840)
- Potente outputs CSV/JSON summaries, peak tables, spectra, plots, the generated Python scripts and full trajectories. Typed records track each candidate's outcome, and **failures are returned as typed records instead of halting the campaign**: YbZn2P2 (mp-9582) occasionally failed in Niggli reduction. **No explicit human approval gates are described**. "Uncertainty-triggered escalation" to DFT is recommended as future work, not implemented. — [arXiv HTML](https://arxiv.org/html/2609.14840)
- Potente documents physically wrong but "successful" outputs. H₂ dissociated spontaneously during relaxation, so the reported states were dissociative rather than molecular adsorption. MACE-OMAT gave −2.28 eV for an Fe(110) reaction that DFT puts at +0.85 eV (endothermic). Conductivities are likely inflated by short MD and small supercells. — [arXiv HTML](https://arxiv.org/html/2609.14840)
- **AtomisticSkills** (Deng, Li, Cox, … Gómez-Bombarelli; arXiv 2605.24002, 18 May 2026) is an open-source harness of **100+ human-curated agent skills** for general coding agents. The skills cover databases, thermodynamics and kinetics, and MLIP and DFT engines. Demonstrations include **high-throughput screening of MOFs for CO₂ capture**, solid-electrolyte generative design, autonomous MLIP benchmarking and fine-tuning, and multimodal XRD analysis. The abstract gives no with-versus-without-skills numbers and no structure-validation step. — [arXiv](https://arxiv.org/abs/2605.24002)

**MOF and crystal design agents (2026)**
- **SimMOF** (Lee, Bae, Kim, KAIST; arXiv 2603.29152, 31 Mar 2026) is a multi-agent framework (query, working and response agents) that runs end-to-end MOF simulation from natural language. It integrates four simulation programs (a review lists Zeo++, RASPA, VASP and LAMMPS), uses "self-debugging" to reduce human intervention, and suggests follow-up simulations. Evaluation is by case studies only, and no code release was found. — [arXiv](https://arxiv.org/abs/2603.29152); [AI Agent review](https://www.oaepublish.com/articles/aiagent.2026.33)
- **LEMO Agent** (Hu et al.; arXiv 2607.10559, 12 Jul 2026) does closed-loop inverse design of gas-separation MOFs in MOFid space. Its loop is generate, **MOFid standardisation, explicit validity checking**, Transformer property prediction, structured design memory, then multi-island exploration. Selected candidates are rebuilt, checked by GCMC, down-selected by chemists for feasibility and ligand purchasability, then synthesised and characterised by SEM. The abstract gives no invalid-fraction numbers. — [arXiv](https://arxiv.org/abs/2607.10559)
- **LitMOF** (arXiv 2512.01693, revised 26 Jun 2026) is a supervisor plus five agents that read the original paper and **edit the CIF until it matches the literature**, correcting CSD/CoRE records into LitMOF-DB. — [arXiv](https://arxiv.org/abs/2512.01693); [AI Agent review](https://www.oaepublish.com/articles/aiagent.2026.33)
- **MatEvolve** (Le, Ha, … Dam; arXiv 2608.15900, v2 21 Oct 2026) edits a crystal's "motif profile" with a stated rationale, builds a crystal from it, and validates the best candidates by first principles. It uses an un-fine-tuned general LLM (the paper names "Claude Fable 5") on rare-earth-lean magnets. Under an equal validation budget it claims success "an order of magnitude more often than generative models." The abstract gives no counts. — [arXiv](https://arxiv.org/abs/2608.15900)
- The mini-review "AI agents for MOFs and COFs discovery" (Yu, Jiang, He; *AI Agent* 2026, 2, 18, 17 Aug 2026) catalogues about 20 MOF/COF agents in three stages. These run from human-mediated LLM work, through database-grounded tool use (ChatMOF, SimMOF, LitMOF, L2M3, Eunomia, and multi-agent screening of 12,703 MOFs for CO₂ by Bai et al.), to experiment-integrated loops. It finds **only one MOF/COF closed loop (LFAST)**, and notes that ChatMOF's accuracy figures rest on 100 and 10 sample questions. — [OAE](https://www.oaepublish.com/articles/aiagent.2026.33)
- **AutoXRD / XRDBench** (Wu, Sun; arXiv 2609.00070, Sept 2026) has 100 diagnostic QA tasks plus 34 end-to-end executable refinement workflows, with 10 LLMs over 1,340 runs. The mean score was **57.8/100, dropping from 61.9 on QA to 53.7 end-to-end**. Models were best at assessing refinement history and accepting results, and weakest at action selection, phase quantification, indexing and Rietveld. The top overall score was 81.1 (GPT-5.6 Sol). This is from the abstract only. — [arXiv PDF](https://arxiv.org/pdf/2609.00070)
- A 2025 hackathon agent, "guillemot," takes a diffraction pattern, queries open structure databases and drives TOPAS Rietveld refinement. — [arXiv 2605.03205](https://arxiv.org/pdf/2605.03205)

**Generalist "AI scientist" products**
- **Kosmos** (Edison Scientific; arXiv 2511.02824) runs up to 12 h and 200+ rollouts, averaging about 42,000 lines of code and 1,500 papers per run. Independent experts judged **79.4% of 102 statements accurate: 85.5% for data analysis, 82.1% for literature, and only 57.9% for synthesis or interpretation**. Every statement cites a Jupyter notebook or a paper. One of its seven showcased discoveries is in materials: perovskite-film humidity and DMF partial-pressure effects. — [arXiv HTML](https://arxiv.org/html/2511.02824v2); [Edison announcement](https://edisonscientific.com/news/announcing-kosmos)
- Kosmos costs $200 per run after six free academic runs, per Alzforum. It is being deployed at Pfizer per R&D World. — [Alzforum](https://www.alzforum.org/news/research-news/introducing-kosmos-ai-scientist-makes-discoveries-overnight); [R&D World](https://www.rdworldonline.com/edisons-kosmos-ai-scientist-moves-into-pfizer-r-edison-details-the-math-behind-its-99-million-per-program-estimate/)
- **Schrödinger Bunsen** entered early access in late July 2026, with a BMS deployment. It orchestrates validated tools (FEP+, Glide, Jaguar, Desmond, AutoDesigner), lets researchers set up, run and troubleshoot multi-stage workflows, and **hands long simulations off to run in the background**. No explicit approval gate was found in public material. — [Schrödinger IR](https://ir.schrodinger.com/press-releases/news-details/2026/Schrdinger-Introduces-Bunsen-an-AI-Co-Scientist-for-Molecular-Discovery/default.aspx); [webinar page](https://www.schrodinger.com/life-science/resources/webinar/bunsen-where-validated-scientific-workflows-meet-agentic-ai/)
- **Periodic Labs, Lila Sciences and Radical AI**: no product or agent announcement relevant to desktop modelling was found. Coverage is about funding ($300M seed for Periodic, reported) and autonomous labs, and much is unverified or secondary. — [Implicator](https://www.implicator.ai/periodic-labs-raises-300-million-to-automate-science/); [MIT Tech Review, Dec 2025](https://www.technologyreview.com/2025/12/15/1129210/ai-materials-science-discovery-startups-investment/)
- **Microsoft Discovery and Google co-scientist in materials**: no 2026 materials-specific evidence was found. The Kosmos paper notes that Google's co-scientist "does not perform or analyze experiments." — [arXiv 2511.02824](https://arxiv.org/html/2511.02824v2)

**MCP servers for materials**
- Community MCP servers now cover Materials Project with pymatgen analysis, OPTIMADE across several providers (MP, Materials Cloud, COD, GNoME), LAMMPS (experimental), and "SciMCP" (45 tools: LAMMPS, CIF analysis, VASP/QE input generation, MP and phonons). "matmcp" combines ASE, pymatgen, GPAW and QE, with VASP and Slurm planned. **None found is a structure editor with undo or a GUI.** These are listings and READMEs on glama.ai, not official releases. — [glama: OPTIMADE MCP](https://glama.ai/mcp/servers/@dianfengxiaobo/optimade-mcp-server/blob/fc654cfe0f76482209505b30ec9924731d327165/README.md); [glama: SciMCP](https://glama.ai/mcp/servers/Nour-elhaq/scimcp); [glama: MCP_LAMMPS](https://glama.ai/mcp/servers/@Chenghao-Wu/MCP_LAMMPS/blob/a7c2af604b0dbd53ebc50a27b603ee36bd4cf3b2/README.md); [glama: MatMCP](https://glama.ai/mcp/servers/@ZuchGuillotine/MatMCP/tree/f89f6df89d388620755e5c2fff42f9cb47a0393c); [glama: Materials Project MCP](https://glama.ai/mcp/servers/@benedictdebrah/materials-project-mcp/blob/5d952499600527162ed8240f549924cd245b8051/README.md)
- **VASPilot** is an MCP-based multi-agent system for VASP. It needs a cluster and a VASP licence. — [arXiv 2508.07035](https://arxiv.org/html/2508.07035v1)
- **MCP Apps** is the official extension (`io.modelcontextprotocol/ui`) that lets a tool return a `ui://` HTML resource, which the host renders in a sandboxed iframe in the chat. Named hosts are Claude, ChatGPT, VS Code and Goose. Sources conflict on the stable spec date: several say 2026-01-26, and one blog says it shipped with a 2026-07-28 spec. Verify against modelcontextprotocol.io. — [MCP Apps API docs](https://apps.extensions.modelcontextprotocol.io/api/); [mcp.directory blog](https://mcp.directory/blog/mcp-apps-spec-2026-when-should-your-server-render-ui); [morphllm](https://www.morphllm.com/mcp-apps)
- nanoHUB's MCP documentation already has an MCP Apps (`ui://`) reference, so a science platform is using this pattern. — [nanohub-mcp docs](https://nanohub-mcp.readthedocs.io/en/latest/skill/references/mcp-apps.html)

**Desktop apps with AI panels**
- **OVITO 3.17.0 (21 Oct 2026)** added cartoon flags, a residues page, a "Hide selected" modifier, a memory-saver mode and GPU selection. **No new agent features were found.** The AI coding-agent panel remains as introduced in 3.16 (14 Aug 2026): it runs Python, checks pipelines, steps trajectories and takes viewport screenshots. **ovito-mcp 2026.3** was released 22 Oct 2026. — [OVITO changelog](https://www.ovito.org/manual/new_features.html); [PyPI ovito-mcp](https://pypi.org/project/ovito-mcp/2026.3/)
- **Avogadro**: v2.1 was planned for 23 Oct 2026, with feature freeze on 1 Oct. A 23 Oct 2026 "Avogadro Updated" post gives no changelog and **mentions no AI, MCP or agent features**. — [Avogadro forum](https://discuss.avogadro.cc/t/september-2026-updates/7517); [macinchem](https://macinchem.org/2026/10/23/avogadro-updated/)
- **ChatMol MCP** connects assistants to PyMOL and ChimeraX for command execution and image capture. — [PulseMCP](https://www.pulsemcp.com/servers/chatmol-molecule-visualization)
- No October 2026 ChimeraX, PyMOL or Jupyter AI agent release notes were found.

### Inferences
- Momentum has shifted from "chat with a tool" to **"agent runs a campaign of N structures through a typed graph, with failures as records."** El Agente Potente is the strongest academic prior art for the "campaigns" idea, but it is a headless HPC framework with no GUI review surface and no approval gates. Crystal Builder could be the first to bring that pattern into a desktop window.
- The Potente vs Claude Code numbers suggest a typed `campaign` verb would make a general assistant both cheaper and more correct than leaving it to script loops. The verb would carry fixed protocol steps such as "relax framework before GCMC", while Claude still plans. The figures are about 4× cheaper, with roughly 5× lower variance in uptake. This is a cross-system inference from one task with n=5.
- MCP Apps creates a second possible home for the results table, inside the chat as well as in the Crystal Builder window. This matters for users who drive the app from Claude Desktop.
- OVITO's panel is still a Python escape hatch with screenshots. Nothing in its 3.17 release suggests it is moving toward batch campaigns or reviewable results.

### Gaps
- No primary sources were found on LLaMP, MatAgent or AtomAgents evaluations in 2026. AtomAgents appears only as a citation.
- No Microsoft Discovery materials evidence was found, nor any agent product from Periodic, Lila or Radical AI usable by outside modellers.
- The El Agente Potente HTML was only partly read (first 100k of 209k characters). Appendix A (job scheduling, fan-out details) and any extra failure statistics were not read.
- AtomisticSkills' with-versus-without-skills numbers and its MOF HTS scale were not extracted.
- No genuinely post-2026-10-09 materials-agent paper of note was found beyond MatEvolve v2 (21 Oct) and arXiv 2610.25775, a GNN+LLM magnetic-ordering classifier (19 Oct) that is not an agent. — [arXiv 2610.25775](https://arxiv.org/abs/2610.25775)

## 2. Where agents fail on crystal tasks: evidence from benchmarks

### Takeaway
LLMs are unreliable at the spatial operations a crystal builder performs. In AtomWorld, rotation succeeds **under 12%** of the time and supercells range from 4% to 98% by model, and failures are "largely random" partial edits. Even when an agent finishes, the result is often physically wrong without saying so. Agents also ignore contrary evidence: in one chemistry study, 68% of tasks had at least one evidence-ignoring step. This argues for typed geometric verbs plus automatic structural checks, not LLM-authored coordinates or CIFs.

### Cited Findings
- **AtomWorld** (Lv et al.; arXiv 2510.04704, v4 28 May 2026) is the closest thing to an "agents on structure editing" eval. It tests 10 actions in 4 categories: point defect and doping (change, remove, add, insert_between, swap), surface (delete_below), perturbation (move, move_towards, rotate_around) and supercell (super_cell). **Rotation success is "below 12%"**. Supercell success ranges from **4% (Llama-3 70B) to 98% (GPT-o3)**. Claude Opus 4.6 "generally performs the best." Tasks fall into tiers: easy (change, remove, swap, add), moderate (move, move_towards, insert_between) and hard (delete_below, rotate_around). — [arXiv abstract](https://arxiv.org/abs/2510.04704); [HTML v4](https://arxiv.org/html/2510.04704v4)
- AtomWorld failure modes:
  - Failures are "largely random," from an unmodified input to partial edits or slightly perturbed positions.
  - Models compute rotation matrices but apply them inconsistently.
  - Qwen3-32B placed an `insert_between` atom at the midpoint instead of at the specified distance.
  - CIF generation looks memorised, with NaCl-type prototypes more reliable than MgSe.

  — [HTML v4](https://arxiv.org/html/2510.04704v4)
- AtomWorld on tools: giving DeepSeek a simple pymatgen-coding tool gave "noticeable gains," raising rotate_around from 6.8% to 18%. However, tools "do not fundamentally resolve the underlying challenges." The authors conclude that LLMs are "better suited as copilots for materials structure modelling rather than fully unsupervised autonomous scientific agents." They suggest text-only CIF is a suboptimal interface and multimodal input is promising, but did not test images. — [HTML v4](https://arxiv.org/html/2510.04704v4)
- AtomWorld CIF-Repair scores: Gemini 2.5 Pro 100%, GPT-o3 95.5%, Qwen3-4B 22.7%. CIF-Gen scores: GPT-o3 100%, Llama-3 70B 0%. Most LLMs scored ≤50% on band-gap and elastic property questions. — [HTML v4](https://arxiv.org/html/2510.04704v4)
- **Render ceiling for crystal structures** (Polat, Kurban, Serpedin, Kurban; arXiv 2609.00663, 1 Sept 2026) evaluated 14 VLMs on 2,160 rendered crystal structures. Supplying exact geometry as text improves every model but **closes under half the gap for 13 of 14**. A supervised vision model with no language component (0.8952) beats every VLM. The method exposes "extraction-stage fabrication," where the model invents what it reads from the image. — [arXiv](https://arxiv.org/abs/2609.00663)
- **SCALAR** (Polat et al.; arXiv 2601.22312, Jan 2026) tests CIF-to-nanoparticle property prediction over about 100k structures. Hallucination and cross-scale inconsistency **rise sharply out of distribution even when accuracy degrades only modestly**. Parse-error (invalid JSON) rates reached 96.34% for Grok 4.1 Fast (3-shot) and 89.01% for Nemotron 3 Nano (0-shot). Chain-of-thought reduced error but often destabilised consistency. — [arXiv HTML](https://arxiv.org/html/2601.22312v1)
- **"AI scientists produce results without reasoning scientifically"** (Rios-Garcia, Krishnan, Jablonka et al.; arXiv, 20 Apr 2026) annotated 619 chemistry lab-reasoning tasks. Agents **ignored evidence at least once in 68% of tasks** and made unsupported claims in 53%. They used contradictory evidence to update in only 26%. Jablonka: a result is only trustworthy if the process is. — [Science News](https://www.sciencenews.org/article/ai-ignore-evidence-trust-science)
- **AutoXRD/XRDBench**: end-to-end refinement averaged 53.7/100 across 10 LLMs. Models were weakest at indexing, phase quantification and Rietveld action selection, but good at judging whether to accept a result. — [arXiv](https://arxiv.org/pdf/2609.00070)
- **Silent physical errors in a "successful" campaign** (El Agente Potente): H₂ dissociated during adsorption relaxations, MLIP reaction energies had the wrong sign versus DFT, and Claude Code skipped framework pre-relaxation in 3 of 5 runs. — [arXiv HTML](https://arxiv.org/html/2609.14840)
- **Computational materials agents review** (Hu, Wang; *AI Agent* 2026, 2, 21, 4 Sept 2026):
  - Inputs "can look valid but fail" because of a missing pseudopotential, a misnamed potential file or version-dependent keywords.
  - Repair loops show a computation can proceed, but they "do not validate the physical model."
  - In AutoMat, one agent reported accuracy 0.8894 against a target of about 0.89 while using the wrong temperature feature and data subset.
  - Benchmarks include DFTBENCH (68 crystals, 4 task types) and GENIUS (295 prompts).

  — [OAE](https://www.oaepublish.com/articles/aiagent.2026.38)
- The MOF/COF review asks that agent outputs be checked with **charge balance, connectivity, stoichiometry and thermodynamic plausibility** checks, "not accepted on fluent reasoning alone." — [OAE](https://www.oaepublish.com/articles/aiagent.2026.33)
- From the prior survey, for continuity: MDCrow completed only 23% of 26 DFT steps correctly, with CO on the wrong site ([DREAMS arXiv 2507.14267](https://arxiv.org/pdf/2507.14267)). GPT-4 could not grade ChemCrow outputs ([arXiv 2304.05376](https://arxiv.org/pdf/2304.05376)).

### Inferences
- The AtomWorld failure list maps almost one-to-one onto Crystal Builder's typed verbs: substitute, delete, insert, supercell and slab. That is quantitative evidence for the existing design choice of no raw-coordinate verb, and for typed verbs rather than CIF text as the agent's interface. It belongs in 1.2 messaging: "the agent never writes coordinates; the app does."
- Taken together, rendered images are useful **for the human** but weak as the **agent's** primary perception channel: VLMs fabricate at extraction, and text geometry closes under half the gap. Crystal Builder's `render` PNG should therefore be paired with machine-readable diagnostics, not relied on alone. This inference combines AtomWorld and the render-ceiling paper.
- "Silent success" is the dominant failure in campaigns. The app's closed diagnostic codes are the natural tripwire, but they must run on every candidate in a batch, automatically, not only when the agent asks.
- AtomWorld (rotation, insert-at-distance) and the MOF review's checklist (charge balance, connectivity) together define a ready-made acceptance test for an agent-native release.

### Gaps
- No 2026 benchmark found reports **charge-balance failure rates** for LLM-generated CIFs. There is still no public benchmark that grades an agent's output crystal against a reference by StructureMatcher (consistent with the prior survey).
- LLM4Mat and MatSciBench were covered previously. No new 2026 results for them were found.
- AtomWorld's per-action numbers for Claude Opus 4.6 are in Figure 2a and were not extracted as text.

## 3. Patterns that work: visual feedback, closed-loop validation, human approval, provenance, background jobs

### Takeaway
The patterns with evidence behind them are: **(a) typed graphs or verbs with deterministic validation and LLM judgement confined to planning**, which El Agente Gráfico and Potente show is cheaper, faster and more reproducible; **(b) failures as typed records**, not crashes; **(c) per-claim provenance** linking every result to code or data (Kosmos, Potente); **(d) background execution of long jobs** (Bunsen, fairchem-mcp); and **(e) human approval for consequential actions**. Visual feedback helps humans more than models.

### Cited Findings
- **Typed graph beats coding agent:** Potente gets lower variance and about 4× lower token cost than Claude Code with skills on HKUST-1 GCMC, as tabulated in section 1. Coding agents skip protocol steps such as pre-relaxation. — [arXiv HTML](https://arxiv.org/html/2609.14840)
- **El Agente Gráfico** (prior survey) reports about 80% lower cost and more than 4× faster wall-clock than its multi-agent predecessor, through typed graphs with LLM decisions only at explicit points. — [arXiv 2602.17902](https://arxiv.org/abs/2602.17902)
- **Failures as records:** Potente returns failed candidates as typed records and keeps the campaign going. — [arXiv HTML](https://arxiv.org/html/2609.14840)
- **Validity checks inside the loop:** LEMO standardises every candidate to MOFid and runs explicit validity checks before property prediction, and keeps a "structured design memory" of both successes and failures. — [arXiv](https://arxiv.org/abs/2607.10559)
- **Per-claim provenance:** Kosmos cites every report statement to a notebook or paper, and Edison markets this as "trace any finding back to the specific code or literature passage." Interpretation statements were still only 57.9% accurate. — [arXiv HTML](https://arxiv.org/html/2511.02824v2); [Edison docs](https://docs.edisonscientific.com/)
- The computational-agents review asks agents to record software versions, file locations, auxiliary models, calculation route, assumptions, checks, recovery history and uncertainty, and to release run records. — [OAE](https://www.oaepublish.com/articles/aiagent.2026.38)
- **Background jobs:** Bunsen hands long simulations off to run in the background. — [Schrödinger webinar](https://www.schrodinger.com/life-science/resources/webinar/bunsen-where-validated-scientific-workflows-meet-agentic-ai/). MCP Tasks were in the 2025-11-25 spec (prior survey).
- **Oversight quality:** a 2026 survey of AI-scientist systems argues that an oversight step which only records accept or reject gives little evidence that the human actually checked anything. — [arXiv 2608.05179](https://arxiv.org/html/2608.05179v1). This is from a search snippet. The paper was not fetched.
- **Visual analytics for oversight:** AI Scientist Mission Control (AIMC; Pal and Mueller, arXiv 2608.28637, Aug 2026) proposes semantic embeddings, automated weakness extraction, temporal analysis and interactive visualisation for overseeing autonomous discovery output. It is tested on AI-generated papers (FARS), not materials, and **has no user study**. — [arXiv](https://arxiv.org/abs/2608.28637)
- **Visual feedback:** OVITO's agent takes viewport screenshots ([OVITO changelog](https://www.ovito.org/manual/new_features.html)), and ChatMol captures PyMOL/ChimeraX images ([PulseMCP](https://www.pulsemcp.com/servers/chatmol-molecule-visualization)). Neither reports evidence that this improves agent accuracy. VLM perception of crystal renders is limited ([arXiv 2609.00663](https://arxiv.org/abs/2609.00663)).
- **Skills documents:** MatTools found LLM-written documentation plus self-reflection beat RAG (prior survey). AtomisticSkills scales this to 100+ curated skills. — [arXiv 2605.24002](https://arxiv.org/abs/2605.24002)

### Inferences
- Crystal Builder already has pattern (a) in its typed verbs, codes and undo. 1.2 could add a **campaign layer** to cover patterns (b) to (d): a typed batch that fans out, applies checks to every candidate, logs failures as rows and runs in the background with MCP Tasks or progress. That turns the app into a "Potente with a window."
- Pattern (e) needs care. A bare "approve" button is weak oversight, per the survey above. A review table that **puts diagnostic codes, energies and a thumbnail on each row** gives the human something to check rather than a click to make.
- The best use of renders is human review, as thumbnails in a results table and a click to open in the 3D view, not the agent's eyes.

### Gaps
- No controlled study was found showing that screenshot feedback improves agent accuracy on structure tasks.
- No study was found that measures whether human approval gates improve outcomes in materials agents.

## 4. Could "campaigns" be the headline? Prior art for GUI-reviewable agent campaigns

### Takeaway
Agent-run campaigns are clearly established in headless research code: El Agente Potente (500–3,000 calculations), AtomisticSkills (MOF HTS), SimMOF, LEMO and Bai et al.'s 12,703-MOF screen. **No desktop GUI was found where an agent plans a batch and a human reviews a ranked, per-candidate results table that links back to editable structures.** The idea is open ground, and the evidence argues for typed protocols rather than free-form scripting.

### Cited Findings
- Headless campaign prior art:
  - Potente: 500 structures × 5 runs; 1,000 crystals × 3 MLIPs; generated perovskite and Li-conductor candidates; MOF Widom. Outputs are CSV/JSON plus scripts, and **no GUI is described**. — [arXiv HTML](https://arxiv.org/html/2609.14840)
  - AtomisticSkills runs high-throughput CO₂ MOF screening through a coding agent. — [arXiv](https://arxiv.org/abs/2605.24002)
  - Bai et al. ran a multi-agent screen of 12,703 MOFs for CO₂ capture and conversion, and Li et al. ran multi-agent Pareto screening of CO₂ MOFs with process and compliance roles. — [OAE review](https://www.oaepublish.com/articles/aiagent.2026.33)
  - LEMO runs generate, validate, predict and GCMC loops, with **human chemist down-selection** before synthesis. — [arXiv](https://arxiv.org/abs/2607.10559)
- Commercial orchestration: Bunsen runs multi-stage workflows in the background inside Schrödinger's suite. Public material shows no per-candidate review table. — [Schrödinger IR](https://ir.schrodinger.com/press-releases/news-details/2026/Schrdinger-Introduces-Bunsen-an-AI-Co-Scientist-for-Molecular-Discovery/default.aspx)
- Oversight UI research exists only for generic AI-scientist output (AIMC), not for materials campaigns. — [arXiv 2608.28637](https://arxiv.org/abs/2608.28637)
- Kosmos produces a cited report rather than a table of reviewable artefacts, and its weakest category is interpretation (57.9%). — [arXiv HTML](https://arxiv.org/html/2511.02824v2)
- MCP Apps lets a server render an interactive table inside the chat host. — [MCP Apps API](https://apps.extensions.modelcontextprotocol.io/api/)
- Potente's results warn what a campaign must check: protocol omissions (no pre-relax), dissociation during relaxation, MLIP sign errors and small-cell artefacts. — [arXiv HTML](https://arxiv.org/html/2609.14840)

### Inferences
- **A credible 1.2 headline is "Reviewable agent campaigns."** The assistant proposes a campaign plan, for example 50 MOF variants from a net and node/linker set, relax with MLIP X, compute pore size, rank by energy and pore. The user approves the plan, not each click. The app then runs a **typed** pipeline in the background and fills a results table in the window. Each row would hold a thumbnail, composition and space group, diagnostic codes, energy with MLIP and dispersion provenance, pore metrics, and failure records as rows. A row opens the structure as an undoable document. The table and its run record export as provenance.
- Why this beats OVITO and the headless frameworks:
  1. Typed protocols prevent the omissions Potente measured.
  2. The app's closed diagnostic codes become per-row tripwires for silent errors.
  3. Undo and per-row documents keep the human as editor-in-chief, matching AtomWorld's "copilot, not autonomous agent" conclusion.
  4. MCP Tasks solve the long-run health-probe problem noted in the prior survey.
- Ranking criteria and thresholds, such as what energy cut or pore metric counts as good, are chemistry choices. They should be presented as editable campaign parameters with Julius-chosen defaults, consistent with the "Julius owns the chemistry" rule.
- An optional MCP Apps view of the same table would serve Claude Desktop users who never look at the window. This is secondary to the in-window table.
- Risk: campaign scale multiplies MLIP model-dependence errors, such as Potente's Fe(110) sign error. Rows should show which engine produced each number, and campaigns should support an "escalate top-k to xTB/DFTB+" step.

### Gaps
- No user evidence was found on what review-table columns chemists actually want.
- No prior art was found for agent-run MOF variant builds (topology-based assembly) followed by GUI review. That may reflect search budget rather than absence.
- Potente's Appendix A (parallel fan-out and streaming) was not read and could inform the job design.

## 5. User studies: how scientists want to use AI assistants in modelling software

### Takeaway
Direct user studies of chemists using AI inside modelling GUIs remain essentially absent. The adjacent evidence agrees: **trust is the primary barrier**, scientists rely on agents when they cite sources, explain actions and allow intervention, approval is expected for actions that touch real compute, and current use concentrates on coding, literature and writing rather than core modelling.

### Cited Findings
- **Anthropic Interviewer** (researchers in chemistry, physics, biology and computational fields): trust and reliability were the primary barrier in **79% of interviews**. Scientists mostly used AI for literature review, coding and writing rather than core research. Computational fields appear further along in adopting AI for core work. — [Anthropic](https://www.anthropic.com/research/anthropic-interviewer). Figures are from a search-result summary. The page was not fetched.
- **European XFEL design-science study** (Fuchs, Gelisio, Hauf, Maalej; arXiv 2607.16845, Jul 2026; accepted at ICSME). It evaluated 16 AI tools and ran interviews, a focus group and a user study with facility scientists, then built two prototypes for knowledge retrieval and code generation in an HPC environment. A search summary states that participants relied on the agent when it **cited sources, explained what it was doing and left room for intervention**, and that human approval was required for HPC actions. The abstract fetched does not confirm those specifics, so treat them as unverified. — [arXiv](https://arxiv.org/abs/2607.16845)
- **Aitomia** (MLatom chatbot; ChemRxiv v4, Mar 2026) aims to lower barriers for experimental chemists and students without HPC experience. No user study was found. — [ChemRxiv](https://chemrxiv.org/doi/pdf/10.26434/chemrxiv-2025-gnf13/v4)
- The *Digital Discovery* 2026 commentary "Scientists might be reaffirming the relevance of human oversight as AI lands in labs" was cited in the prior survey. — [RSC](https://pubs.rsc.org/en/content/articlehtml/2026/dd/d6dd00030d)
- The position paper "AI Agents in Scientific Teams Should Be Studied as Human-Agent Systems" (arXiv 2608.14667, Aug 2026) argues for studying human-agent teams. Its content was not fetched. — [arXiv PDF](https://arxiv.org/pdf/2608.14667)
- A study of developers overseeing software agents (arXiv 2606.05391) documents oversight work and heuristics. It is an adjacent domain and was not fetched. — [arXiv PDF](https://arxiv.org/pdf/2606.05391)
- The MOF/COF review recommends that humans set goals and constraints, handle exceptions and validate chemical conclusions, and "should not have to manually transfer every result between rounds." — [OAE](https://www.oaepublish.com/articles/aiagent.2026.33)

### Inferences
- Users' stated preferences — citations, explanations, intervention and approval for compute — line up with a campaign design. A visible plan to approve, per-row provenance and an abortable background job deliver all of them.
- Because computational scientists already use AI mainly for coding, a headline that removes the *scripting* of batch screening, which today means hand-written pymatgen and ASE loops, meets an existing behaviour rather than inventing one.
- Crystal Builder could generate its own user evidence cheaply. A short study with Julius's group, observing tasks such as "build and rank 20 substituted variants" with and without campaigns, would fill a gap the literature leaves.

### Gaps
- **No 2025–2026 user study was found that specifically studies chemists or materials scientists using an AI assistant inside desktop modelling or visualisation software** (Avogadro, OVITO, VESTA, CrystalMaker, ChimeraX, PyMOL). That is a real gap in the literature, not just in this search.
- No usage data from OVITO's AI Agent panel, such as adoption or user feedback, was found.
