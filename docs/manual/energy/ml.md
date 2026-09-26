# Machine-learned potentials: MACE, ORB-v3 and MatterSim

A universal machine-learned interatomic potential answers for a
framework with no parameters to assign and no atom typing to get
right, at a cost between a force field's and tight binding's.  Crystal
Builder offers three: MACE, ORB-v3 and MatterSim.  After this section
you know what such a model is, which models each engine offers and
what each was trained on, why the engines run in double precision by
default, and how to install the extra each one needs.

```{index} single: machine-learned potential
```
```{index} single: foundation model
```
```{index} single: MACE
```
```{index} single: MACE-MP-0
```
```{index} single: MACE-MP-MOF0
```
```{index} single: ORB-v3
```
```{index} single: MatterSim
```
```{index} single: ASE
```

## What a machine-learned potential is

A machine-learned interatomic potential is a model fitted to the
energies and forces of first-principles calculations, which then
evaluates an energy and its gradient at a cost far below the
calculations it was fitted to.  Early models had to be fitted per
system; the ones offered here are **{term}`foundation models <foundation
model>`**, fitted once over a public dataset of many materials -- in
the words of the
MACE-MP-0 paper {cite}`batatia2025macemp0`, "a general-purpose
atomistic ML model, trained on a public dataset of moderate size,
that is capable of running stable molecular dynamics for a wide range
of molecules and materials", which "can be applied out of the box as
a starting or 'foundation' model for any atomistic system of
interest".  That is the gap between UFF, which has to be extended to
describe a metal node at all, and DFTB+, which needs a Slater-Koster
set downloading per element pair.

All three engines run **in this process** on the same code, through
the Atomic Simulation Environment {cite}`larsen2017ase`: the structure
is handed to the model once and the geometry moves under it, so the
per-step cost is the model's own.  A model is loaded once and cached,
and a foundation model's weights are **downloaded on first use** to
the package's own cache -- a download the application did not start
and cannot make silently, so the engine's availability line says so
before anything runs.  Energies and forces come back from ASE in eV
and are converted to kcal/mol by one factor.

Each engine needs its own optional extra, and none is installed by
default; see {ref}`ml-installing`.

## MACE

MACE {cite}`batatia2022mace` is an equivariant message-passing model
in the atomic cluster expansion family.  The **MACE-MP** foundation
models {cite}`batatia2025macemp0` are fitted over the Materials
Project, and the engine offers those whose training set, level of
theory or licence makes them a different answer to "which model for
this framework" -- every description is the upstream table's own,
deliberately not a characterisation of the application's:

| Model | Training set, level of theory | Licence |
|---|---|---|
| MACE-MPA-0 (default, recommended) | MPtrj + sAlex, PBE+U | MIT |
| MACE-MP-0b3 | MPtrj, PBE+U; steadier under pressure | MIT |
| MACE-OMAT-0 | OMat, PBE+U | ASL |
| MACE-MATPES-r2SCAN-0 | r2SCAN, no +U | ASL |
| MACE-MH-1 | crystals, molecules and surfaces | ASL |
| MACE-MP-MOF0 | 127 MOFs, PBE-D3(BJ), for phonons; 26 elements | CC BY 4.0, cite |
| MACE-MP-0a small / medium / large | the models before mace 0.3.10 | MIT |
| A model file of my own | a `.model` file you have fitted | -- |

The default is `mace_mp`'s own: from mace-torch 0.3.10 the package
stopped defaulting to `medium` and started defaulting to MACE-MPA-0,
and asking for `medium` explicitly now gets the older generation.
The models under the Academic Software License say so in the chooser
before the choice is made, because MACE prints "you accept the terms
of the license" only as it downloads, and the application is the
thing doing the downloading.

**MACE-MP-MOF0** {cite}`elena2025macemof0` is MACE-MP-0b fine-tuned
on a curated set of 127 metal-organic frameworks, made for phonons:
its authors report that it "improves the accuracy of phonon density
of states and corrects the imaginary phonon modes of MACE-MP-0", and
predicts thermal expansion and bulk moduli in agreement with DFT and
experiment for several well-known MOFs.  Three things about it are
the application's to enforce:

- **Dispersion is already in it.**  Its reference data were
  PBE-D3(BJ), so D3 must never be added on top; see {doc}`dispersion`.
- **It knows 26 elements**: H, C, N, O, F, Mg, Al, Si, P, S, Cl, Ti,
  Fe, Cu, Zn, Ga, Br, Sr, Zr, Cd, In, Sn, I, Ce, Ho and Hf -- no Cr,
  Mn, Co or Ni.  A structure with any other element is refused by
  name before a run, with the MACE-MP models suggested instead.
- **CC BY 4.0 makes the citation a condition.**  The engine's source
  links name the paper whenever this model is chosen.

It is not one of `mace_mp`'s models, so the application fetches it
from the authors' repository at a fixed commit (a 31 MB download) and
loads it only if it is byte for byte that file, because a model file
is a pickle and loading one runs it.

*Run on* asks torch what the machine has; a GPU is worth an order of
magnitude on a framework of a few thousand atoms, and on a Mac the
Apple GPU (mps) is offered for MACE.

## ORB-v3

ORB-v3 {cite}`rhodes2025orbv3` is Orbital Materials' universal
potential, Apache-2.0 code and weights, described by its authors as
offering "near SoTA performance across a range of evaluations with a
>10x reduction in latency".  The reason it sits beside MACE is the
benchmark the engine's notes record: on MOFSimBench
{cite}`krass2025mofsimbench`, which evaluates over twenty universal
potentials on nanoporous materials and finds that "top-performing
uMLIPs consistently outperform classical force fields and fine-tuned
machine learning potentials across all tasks", the best models reach
89 % volume accuracy on frameworks where UFF4MOF reaches 62 %.

**That figure is for ORB-v3 with a dispersion correction, and the
engine has none** -- see {doc}`dispersion` for the measured
difference.

Only the **conservative** models are offered: ORB's "direct" models
predict forces from a head of their own rather than by
differentiating the energy, so the force is not the gradient of the
energy the optimiser's line search compares, which is the one thing a
relaxation needs.  The four choices are the upstream loaders' own
descriptions -- trained on OMat24 (recommended) or on MPtrj +
Alexandria, each with every neighbour inside 6 Å or with 20
neighbours (faster).  Weights are about 100 MB.  orb-models cannot run
on an Apple GPU, so on a Mac *auto* means the CPU.

## MatterSim

MatterSim {cite}`yang2024mattersim` is Microsoft Research's universal
potential, an M3GNet "actively learned from large-scale
first-principles computations ... spanning temperatures from 0 to
5000 K and pressures up to 1000 GPa"; MIT code and weights.  Two
checkpoints are offered, the 1M model (recommended, 18 MB) and the 5M
model with five times the parameters (91 MB), downloaded to
`~/.local/mattersim`.

**Its limits, in its authors' words** (the model card): "relatively
low accuracy for organic polymeric systems", and trained on PBE with
PBE's limits.  A framework's linkers are organic, so a relaxation here
wants checking against another engine.  It is the fastest of the
three (see below), and like ORB-v3 runs with no dispersion
correction.  It cannot load onto an Apple GPU -- on macOS 13 it does
so without asking and the process dies in `torch.load` -- so *auto*
is CUDA or the CPU.

(ml-precision)=
## Precision

**All three engines run in double precision by default, and not for
the accuracy of the energy -- for the consistency of it.**  An
optimiser reads differences between energies a few thousandths of a
kcal/mol apart, and in single precision the model's own noise is of
that size, so a line search stops converging and starts wandering.
Measured on MOF-5 (424 atoms), along the force, for a step of
$10^{-4}$ Å:

| Engine | Energy change, float64 | Error of float32 | Cost of float64 |
|---|---|---|---|
| ORB-v3 | $5.8 \times 10^{-4}$ eV | $2.1 \times 10^{-4}$ eV (a third) | 2.7× (0.94 → 2.58 s an evaluation) |
| MatterSim 1M | $9.2 \times 10^{-3}$ eV | $6.6 \times 10^{-4}$ eV (7 %) | 1.5× (0.33 → 0.51 s) |
| MACE-MPA-0 | -- | noise larger than the differences read | (3.32 s an evaluation in float64) |

Turn *Double precision* off for a single point or a molecular
dynamics run where the speed matters more than the last digit; leave
it on for a geometry optimisation.  Double precision needs memory:
relaxing MIL-100 in float64 needed 4.4 GB on an 8 GB laptop, which is
why the prepared samples above 2000 atoms were relaxed in float32
(`resources/samples/PROVENANCE.md`).

## Stress

The stress is ASE's, claimed only because it was checked: the
conversion is one factor with no normalisation guessed at (ASE
reports $(1/V)\,\partial E/\partial\varepsilon$ in eV/Å³, which is
what the application's numeric stress computes in kcal/mol/Å³), and a
test compares what the model reports against the finite-difference
stress.  It is claimed **per model**, not per engine: every
foundation model here reports a stress, and a model file of your own
that reports none (a dipole-only MACE, say) falls back to the numeric
stress with a warning rather than failing the evaluation.

(ml-installing)=
## Installing the extras

Each engine is an optional extra of the package, and the engine's
availability line prints the command for this interpreter and this
checkout when it is missing.  From a source checkout:

```console
$ python -m pip install -e ".[mace]"
$ python -m pip install -e ".[orb]"
$ python -m pip install -e ".[mattersim]"
```

*Preferences ▸ Engines* shows the same commands.  One conflict is
known: mattersim declares e3nn 0.5 or newer and mace-torch pins
0.4.4, so pip will not resolve both extras into one environment.
What MatterSim's inference imports from e3nn is in 0.4.4, so **where
MACE is already installed** the command offered is mattersim with
`--no-deps` and the three packages it imports that MACE did not bring
(`torch_runstats`, `loguru`, `deprecated`); following the plain extra
beside MACE moves e3nn to a version MACE refuses to load with.

## Worked example

Any of the three is asked for like UFF, with the model as a
parameter:

```console
$ xtal energy resources/samples/prepared/MOF-5.cif --engine mace -p model=medium-mpa-0
$ xtal optimize resources/samples/prepared/MOF-5.cif --engine orb -o MOF-5_orb.cif
$ xtal energy resources/samples/prepared/MOF-5.cif --engine mattersim -p model=MatterSim-v1.0.0-1M
```

None of the three extras is installed on the machine this draft was
written on, and each engine says what to do:

```console
$ xtal energy resources/samples/prepared/MOF-5.cif --engine mace
error: MACE is not installed -- "/Users/sam/Projects/Jules/Crystal-Builder/.venv/bin/python" -m pip install -e "/Users/sam/Projects/Jules/Crystal-Builder[mace]"
```

% TODO(Sam): with the extras installed, run the three commands above
% on the prepared MOF-5 (106 atoms) and paste the output, including
% the first-use download line and the time per step the log reports.

## Settings

Each engine's options -- model, device, precision, and for MACE a
model file -- are listed under {ref}`MACE <engine-mace>`,
{ref}`ORB-v3 <engine-orb>` and {ref}`MatterSim <engine-mattersim>`.

## Limitations

- **No {term}`dispersion correction` on the foundation models** other than
  MACE-MP-MOF0, which has it inside.  A relaxed framework's volume
  from ORB-v3 or MatterSim is the bare model's, not the benchmark's;
  see {doc}`dispersion`.
- MACE-MP-MOF0 knows 26 elements and refuses the rest.
- MatterSim's authors note low accuracy for organic polymeric
  systems, which is the linker half of a framework.
- The engines provide forces, stress and periodicity; no atom types
  and no charges for the force field.
- On a Mac, only MACE can use the GPU.
- A first use downloads weights; nothing runs offline until it has.
