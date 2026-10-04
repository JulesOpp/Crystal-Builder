(energy-orca)=
# ORCA input files

Crystal Builder does not run ORCA.  It writes an ORCA input file for
the structure in front of you, and the coordinates that file reads,
into a run folder; you take the folder to wherever ORCA is installed.
After this section you can choose a functional, basis set, job and
solvent from ORCA's own lists, know what part of a crystal is handed
to a program that has no cell, see why an impossible spin state is
refused before anything is written, and get a UV-Vis spectrum of a
relaxed structure rather than of the wrong state.

```{index} single: ORCA
```
```{index} single: ORCA; input file
```
```{index} single: TD-DFT
```

ORCA {cite}`neese2022orca` is a separate quantum-chemistry program,
free for academic use from FACCTs, and its authors ask to be cited.
The dialog repeats that, because the entry is never greyed: writing an
input needs no ORCA.  The lists are those of the ORCA 6.1 manual.

## What it does

*Modules ▸ ORCA ▸* {ref}`Input file… <cmd-module.orca.input>` opens one
dialog of choices, with the input shown as it is chosen and anything
wrong with it said under it.  Pressing **Write** (greyed while the input is refused) writes two files in a
new run folder of the structure's entry:

`<name>.inp`
: The input.

`<name>_from_crystal_builder.xyz`
: The coordinates, plain XYZ in Å, four columns, with no cell.  The
  input reads it with `*xyzfile`.

The coordinates are not called `<name>.xyz` because that is the name
ORCA writes an optimised geometry to, over the file it started from;
the structure you handed it would then be gone and a second run would
start somewhere else.  The `*xyzfile` line takes the name unquoted and
has no closing `*`, either of which would be an ORCA input error, so
the name is made of characters that need no quotes.  *File name*
overrides it; empty, it is the tab's.

When ORCA's own `<name>_trj.xyz` is copied back into that folder, it
opens as a run like any other trajectory.

## The cluster: what a program with no cell is given

ORCA is molecular.  What it is handed is a **cluster**: every atom of
the cell, or only the atoms you selected, with the following care.

- **A molecule is made whole.**  Written as the cell wraps them, a CO₂
  lying across a face is a carbon with its oxygens four ångström away
  on the far side, and ORCA would optimise three atoms nobody meant.
  The stored bond graph is used to carry each molecule across the
  faces so it is written in one piece.
- **A framework is written as cut.**  A piece that never closes -- a
  framework, a chain, a sheet -- has no whole to make, and is written as
  it falls in the cell, with dangling bonds.  A caution says so, with
  the number of such pieces.  The sensible use of a periodic structure
  is therefore *select what you mean, then write the input*: a linker,
  a node and its first shell.  **Selected atoms only** in the dialog writes the
  selection, each molecule in it made whole; on the command line, *Atoms* takes the
  cell indices.
- **Markers are left out.**  Dummy atoms are markers and not chemistry
  ({term}`dummy atom`).  They are dropped by the cluster itself rather
  than by removing their sites first, because removing sites would
  renumber the cell under the selection.
- **Partly occupied atoms are all written.**  A caution counts them;
  *Structure ▸ Prepare for simulation* orders the disorder first
  ({doc}`/structure/prepare`).

## The spin is refused, not corrected

The electron count is the sum of the atomic numbers less the
**Charge**.  An even count needs an odd multiplicity and an odd count
an even one, and no multiplicity can exceed the count plus one.  ORCA
says the same thing, but only after your job has been through the
queue; here it is said before anything is written, and a refused
input writes **nothing**, because a folder holding an input with a
spin its electrons cannot have is one somebody will submit:

```console
$ xtal run orca.input DMF.cif -p multiplicity=2
40 electrons need an odd multiplicity (1, 3, ...); 2 was given
```

A pseudopotential removes an even number of electrons, so the parity
holds with one.  The other refusals are a functional or basis set that
is not in ORCA's list, a negative number of roots, TD-DFT with a VV10
functional (use its -D3BJ or -D4 variant), a solvent without
parameters for the chosen model, and an excited-state follow that
ORCA cannot do (below).

## The choices

**Functional** and **Basis set** are each a pair of boxes -- a family
and what is in it -- with a search line over everything: ORCA's
native functionals (95 of them, in the nine families of Tables 3.1 to
3.9) and 440 basis sets in 22 families (Tables 2.12 to 2.33).  Typing
`tzvp` offers every TZVP in every family, and picking one sets both
boxes.  The LibXC functionals are left out on purpose.  Composite
(3c) methods bring their own basis, so none is written.

Cautions, not refusals, say what to look at:

- a basis with no functions for an element in the structure (zinc and
  a basis that stops at krypton), said with the elements it does cover,
  before ORCA aborts;
- a basis contracted for a relativistic treatment, with the keyword to
  add under *More*;
- a **Dispersion** correction on a functional that already carries one,
  which would count it twice;
- OptTS without an exact Hessian, and double-hybrid or excited-state
  frequencies, which are numerical and slow.

**RI** is ORCA's own default -- RI-J for a pure functional, RIJCOSX
for a hybrid -- or a choice, which writes its auxiliary basis too.
**Job** is a single point, an optimisation (`Opt`, with a convergence
level and optionally Cartesian coordinates, an exact Hessian first,
and a MaxIter) or a transition-state search (`OptTS`); **Frequencies**
are taken after the optimisation if there is one.  The SCF
convergence, solver, MaxIter and guess go into `%scf`.  **Solvation**
is an implicit solvent, C-PCM or SMD, with any solvent of ORCA's
Table 2.56 (a solvent a model has no parameters for is refused).
**Processes** and **Memory per process** write `%pal` and `%maxcore`,
the whole job's.  **More keywords** are added to the `!` line as you
write them and **More blocks** go before the coordinates; both are
for what the dialog does not name.

## TD-DFT beside an optimisation is two different questions

ORCA answers only one of them by default.  With a `%tddft` block, `Opt`
and `Freq` follow the **excited state** `IRoot`.  A UV-Vis spectrum of
the *relaxed structure* is the other one: the ground state optimised,
then the excitations at that geometry.  *TD-DFT with Opt or Freq*
chooses:

Ground state, then the spectrum (two steps)
: The default, because it is what a spectrum usually means.  The input
  is a two-step `%compound` job, the second step taking the first's
  geometry.

Excited state IRoot (one step)
: ORCA's own behaviour: it optimises excited state *IRoot* (counting
  from 1; a triplet root needs the triplets computed).  It is offered
  only for the functionals ORCA 6.1 has a TD-DFT gradient for, and
  refused for the others, with the functionals that work named.

For the optimised dimethylformamide of the next section, the default
writes:

```text
# DMF, from Crystal Builder
*xyzfile 0 1 DMF_from_crystal_builder.xyz

%compound
  # Step 1: the ground state, optimised
  NewStep
  ! PBE0 def2-TZVP Opt
  StepEnd
  # Step 2: the excited states at that geometry
  NewStep
  ! PBE0 def2-TZVP
  %tddft
    nroots 10
    triplets false
  end
  StepEnd
End
```

and the excited route, with C-PCM in DMF, 4 processes and 2000 MB each:

```text
# DMF, from Crystal Builder
! PBE0 def2-SVP CPCM(n,n-dimethylformamide) Opt

%pal
  nprocs 4
end

%maxcore 2000

%tddft
  nroots 5
  triplets false
  iroot 1
end

*xyzfile 0 1 DMF_from_crystal_builder.xyz
```

## Worked example

A molecule built from SMILES ({doc}`/frameworks/molecule-builder`) is
the easy case, since it has no cell to cut:

```console
$ xtal run build.molecule -p smiles='CN(C)C=O' -p name=DMF -o DMF.cif
$ xtal run orca.input DMF.cif --workspace ws -p functional=PBE0 -p basis=def2-TZVP -p run=opt -p tddft_nroots=10
Wrote DMF.inp and DMF_from_crystal_builder.xyz: 12 atoms, 40 electrons, singlet
run folder: ws/DMF/orca-input-001
```

The run folder holds `DMF.inp`, `DMF_from_crystal_builder.xyz` and the
usual `run.log`, which records the choices.  On a framework the same
command reports the cluster's limit rather than refusing it:

```console
$ xtal run orca.input resources/samples/MOF-5.cif --workspace ws
1 piece is periodic (a framework, chain or sheet) and written as cut from the cell, with dangling bonds
Wrote VESTA_phase_1.inp and VESTA_phase_1_from_crystal_builder.xyz: 424 atoms, 3040 electrons, singlet; 1 caution
```

Whether a cut framework is a calculation worth running is yours to
judge: for a periodic structure the better inputs are a selection --
a linker with the carboxylates on it, capped as you decide -- than the
cell.

## Settings

The parameters, with the names `-p` takes, are listed under {ref}`Input
file… <mod-orca-input>` in the generated reference.  The command line
spells a solvation model `CPCM` or `SMD` and a job `sp`, `opt` or
`optts`.

## Limitations

- **Nothing is run, and no output is read** other than a trajectory
  copied back.  Charges, spin and the chemistry of a cut are as you
  choose them.
- The functional and basis lists are the 6.1 manual's, entered or read
  off by hand and by script; another ORCA version may differ.
- A periodic structure is a cluster of it, never a periodic
  calculation: ORCA has no cell.
- The excited-state route is limited to functionals with an excited-state
  gradient, measured against ORCA 6.1.
