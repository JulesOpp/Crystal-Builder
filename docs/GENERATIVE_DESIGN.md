# Generative design: ideas, not yet a plan

> **Written 2026-11-09** on `feature/generative-design`, after v1.1.0.
> A list of things we could do with MatterGen and CrystaLLM, to argue
> over before anything is designed. Nothing here is decided and nothing
> is built. Install facts were read off the two projects' own
> repositories on the day; no timing below was measured by us.

## What Julius asked for

A way to *generate* structures from inside Crystal Builder with the two
open generators, **MatterGen** (Microsoft, diffusion) and **CrystaLLM**
(now CrystaLLM-π, a GPT-2 that writes CIFs), rather than only building
them from a recipe.

## The facts everything else hangs on

| | MatterGen | CrystaLLM-π |
|---|---|---|
| Licence | MIT, code and weights | MIT, code and weights |
| Asks for | chemical system, space group, band gap, magnetic density, bulk modulus, energy above hull | formula, Z, space group; band gap, density, solar efficiency (SLME); **XRD peaks** |
| Cell size | 20 atoms or fewer | about 20 atoms (1024-token window) |
| Python | 3.10 only (its pinned wheels are cp310) | 3.12, `uv sync` |
| Platforms | Linux with CUDA; Apple silicon "experimental"; no Windows wheels | says generation runs on CPU; 1-2 GB of memory |
| Weights | about 460 MB, fetched from Hugging Face | about 250 MB each, fetched from Hugging Face |
| How it is run | `mattergen-generate DIR --pretrained-name=...` | `python _load_and_generate.py --hf_model_path ...` |
| What it leaves | `generated_crystals.extxyz` and a zip of CIFs | a folder of CIFs, or a parquet |
| Speed | about 9 s a structure on an A100; unknown on a laptop | unknown on a laptop |

Three things follow before any idea is weighed.

- **Neither can live inside our Python.** We need 3.11 or later with
  our own torch for MACE, ORB and MatterSim; MatterGen is 3.10 with
  pinned torch and PyG wheels. So a generator is *somebody else's
  program in its own environment*, which is what DFTB+ and Zeo++
  already are: found by Preferences ▸ Engines, run by
  `xtal/modules/process.py`, with a live log and a Stop that reaches it.
- **Neither goes in the installer.** The environments are gigabytes and
  the weights hundreds of megabytes; they are fetched once, by the
  user, when asked.
- **Both make small inorganic cells.** No MOFs, no frameworks, nothing
  over about 20 atoms. This is a feature for dense inorganic work, and
  the form should say so.

## Ideas

### A. Getting a generator to run

1. **Open somebody's results.** Read a MatterGen results folder
   (`generated_crystals.extxyz`) or a folder of CrystaLLM CIFs as one
   set of candidates. No generator on this machine at all: the run
   happened on a GPU box or a cluster. The cheapest first step, and it
   forces idea B before anything else.
2. **MatterGen as an engine.** A row in Preferences ▸ Engines that
   finds `mattergen-generate`, a module `generate.mattergen` whose form
   is the table above (chemical system, space group, a target and its
   value, guidance, how many), and the run folder read back as a set.
3. **CrystaLLM-π as an engine.** The same, for the generator most
   likely to run on a laptop: formula, Z and space group, optional
   target, how many valid CIFs to keep.
4. **One Generate form over both.** Pick the generator, and the form
   shows only what that one can be asked. Because a module is a
   registry entry, the menu, `xtal run generate.*` and the assistant's
   verb come with it.
5. **Set it up for the user.** Preferences already offers install
   commands. A generator's would be "make an environment and install
   into it" with `uv`, which is more than one line and can fail in more
   ways; worth it only once 2 or 3 is known to be wanted.
6. **Run it elsewhere.** A generator on a remote machine over SSH, the
   results copied back. Probably idea 1 with a script, not a feature.

### B. What a batch of candidates *is*

A build returns one structure and files one entry. A generation returns
sixteen, or two hundred, and most are thrown away.

7. **A candidate set**: one workspace entry holding N structures and a
   table of them, not N tabs. Any row opens as an ordinary document.
8. **What the table shows**, cheap first: formula, atoms, space group
   (ours, from Find symmetry, not the generator's claim), density,
   shortest contact; then whatever section C computes.
9. **Keep, discard, compare.** Tick rows to keep, overlay two, export
   the kept ones. The set remembers which generator, which weights,
   which seed and which request made it.

### C. Checking candidates, which is most of the value

Published numbers: under 1% of generated structures are stable, unique
and new at once; about half fail a phonon check; and MatterGen's own
showcase compound was argued in 2026 to be a known disordered phase.
A generator proposes. The app's job is to say which proposals survive.

10. **A sanity screen**: atoms too close, impossible density, charges
    that cannot balance. Instant, no engine.
11. **Relax each one** with the engine in the Force Field panel.
    MatterGen's own evaluation uses MatterSim, which we ship.
12. **Symmetrise and remove duplicates** within the set.
13. **Energy above the hull.** Needs the known phases of that chemical
    system, relaxed with the *same* engine. That is the "Fetch a
    structure" item in TODO.md (Materials Project or Alexandria through
    OPTIMADE) with a use on day one.
14. **"Is this already known?"** Match against the fetched phases,
    including a disorder-tolerant match, and say so on the row before
    anything else.
15. **Phonons for the survivors**, with the phonopy we already bundle.
16. **Calculated PXRD for every row**, and a fit against a measured
    pattern where there is one, through the existing workbench.

### D. Where a generator meets what the app already does

17. **A starting model from a formula.** "TiO2, P4_2/mnm, Z = 2" and a
    plausible structure comes back in seconds. Not discovery: a faster
    way to a first model for a refinement or a calculation. Possibly
    the thing used most often.
18. **Pattern in, candidates out.** CrystaLLM-π has checkpoints
    conditioned on XRD peaks. Peaks from the workbench go in,
    candidates come out, and Rietveld judges them. The same shape as
    the Solve idea in the 1.2 report, with a generator where that had
    net enumeration, and for small inorganic cells only.
19. **An honest baseline beside the model.** Swapping ions in known
    compounds is competitive with the generators at finding stable
    structures, by one 2025 study. Offering it as a third "generator"
    costs little and keeps the comparison fair.
20. **The assistant asks for a batch.** One verb that starts a
    generation and returns the table, with every row's checks.
21. **Fine-tune on your own data.** Both projects support it. Later, if
    ever: it wants a GPU and a dataset.

### E. Deliberately out

- MOFs and other frameworks: no open generator with usable weights
  handles them.
- Anything shipped inside the installer.
- MatterGen on Windows, until its authors publish wheels.
- The words "new material". A row is a hypothesis for DFT or the lab.

## What we do not know yet

- **How long a batch takes on a laptop.** Nobody has published it for
  either generator. An afternoon's measurement on Apple silicon decides
  whether ideas 2 and 3 are a button or only idea 1 is.
- **How often CrystaLLM-π's output is usable.** The older CrystaLLM
  failed to produce a readable CIF up to 90% of the time in one
  benchmark; the new one keeps sampling until it has the number of
  valid CIFs asked for, at a cost we have not measured.
- **Whether MatterGen's Apple silicon path works at all** on a current
  macOS.
- **Whether OPTIMADE returns enough competing phases** for a hull worth
  the name.

## Julius's calls

- Who this is for, and the first three things they would ask it.
- Which targets matter: band gap, bulk modulus, density, a pattern?
- What energy above the hull counts as worth a second look, and whether
  a hull from an ML potential is shown at all.
- Whether a row is shown before the known-compound check has run.
- Whether the starting-model use (17) or the discovery use (2, 3, 13)
  is the point.

## A first slice, as a proposal

Measure both generators on one Mac first. Then: **open a results
folder as a candidate set (1, 7, 8), with the sanity screen and a relax
(10, 11)**. It needs no generator installed, it settles what a
candidate set is, and every later idea is a column or a source added to
it.
