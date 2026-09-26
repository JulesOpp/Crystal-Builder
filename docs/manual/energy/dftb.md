# DFTB+

Density-functional tight binding is DFT-like and fast enough to relax
a framework UFF can only approximate.  Crystal Builder runs it through
the DFTB+ program, in two ways: as an energy engine that the
application's own optimiser drives one evaluation at a time, and as a
set of DFTB+'s native runs -- a band structure, a density of states,
charges, an orbital, its own relaxation driver, vibrational modes and
molecular dynamics.  After this section you can set up the
Hamiltonian, point the application at a parameter set, and know which
kind of run to reach for.

```{index} single: DFTB+; energy engine
```
```{index} single: DFTB3
```
```{index} single: SCC-DFTB
```
```{index} single: Slater-Koster parameters
```
```{index} single: DFTB_PREFIX
```
```{index} single: tight binding; DFTB+
```

## What it is

DFTB builds a tight-binding Hamiltonian from density-functional
theory {cite}`porezag1995dftb`; SCC-DFTB adds a self-consistent
treatment of the atomic charges {cite}`elstner1998scc`; DFTB3 extends
it to third order in the charge fluctuations {cite}`gaus2011dftb3`.
DFTB+ {cite}`hourahine2020dftbplus` is the program, "offering fast and
efficient methods for carrying out atomistic quantum mechanical
simulations" by "approximating density functional theory", and "being
considerably faster for typical simulations than the respective ab
initio methods".  Everything a DFTB calculation needs about a pair of
elements is in a **{term}`Slater-Koster <Slater-Koster file>`** file,
and those files are separate downloads from
[dftb.org](https://dftb.org), per parameter set.

## The Hamiltonian

The Hamiltonian is the nearest thing DFTB has to a functional, and it
is the field a user coming from DFT looks for the functional in:

- **DFTB3** (the default) is third order, and is what the 3ob set was
  fitted for.
- **SCC-DFTB** is second order and works with any set.
- **Non-SCC DFTB** has no charge transfer at all, and is for a first
  look.

DFTB3 needs a Hubbard derivative per element, and 3ob publishes them
only for the elements it covers (H, C, N, O, F, Na, Mg, P, S, Cl, K,
Ca, Zn, Br, I).  Any other element under DFTB3 is treated at second
order, which is a different model rather than a coarser one; the run
says so, and suggests SCC-DFTB if that is most of the structure.

## Parameter sets and where they are looked for

The sets a user is likely to have, with what each is for: **3ob**
(organic and biological molecules, DFTB3), **mio** (the original
organic set, SCC-DFTB), **matsci** (inorganic solids and surfaces),
**pbc** (periodic solids, silicon and oxides), **znorg** (zinc with
organic ligands) and **trans3d** (first-row transition metals).

The directory of `.skf` files is looked for in this order, and
nothing else is guessed from the filesystem:

1. the *Parameter directory* field of the DFTB+ panel;
2. the `DFTB_PREFIX` environment variable, which DFTB+ users
   conventionally set;
3. on a source checkout, a set dropped into `resources/PTBP`.

Every element pair in the structure is checked before anything is
launched -- both orders of each pair, because DFTB+ reads both -- and
the missing files are named.  That is the difference between
"download the 3ob set and point at it" and a run that fails several
seconds in with "could not open Zn-N.skf".

The **maximum angular momentum** of every element is a property of
the set rather than of the element (3ob gives chlorine a d shell; mio
does not).  The application's table follows 3ob-3-1 and mio-1-1 where
they agree and 3ob where they do not; an element not in the table
gets a rule (p below sodium, d above) and the run warns that it was
derived.  *Angular momentum overrides* (`Cl=d, Zn=d`) is the escape
hatch for a set that disagrees, because DFTB+ takes what it is given
and returns a number rather than an error.

## Dispersion

DFTB has no dispersion of its own, and a framework's pore size is a
dispersion-bound number -- so for a porous solid this is not an
optional refinement.  The choices are *None*, **DFT-D3 with
Becke-Johnson damping** {cite}`grimme2010d3` {cite}`grimme2011bj`, and
a **Lennard-Jones** term with UFF's radii {cite}`rappe1992uff`.  With
D3(BJ) the application writes DFTB+'s `DftD3` block with
$s_6 = 1.0$, $s_8 = 0.5883$, $a_1 = 0.5719$ and $a_2 = 3.6017$; see
{doc}`dispersion` for what the parameters mean.

## k-points and filling

The k-point mesh is worked out from the cell at a **spacing** of
0.25 Å⁻¹ by default: a cell twice as long gets half as many points
along it, counted from the reciprocal vectors' lengths rather than the
real ones' (they agree only for a rectangular cell).  It errs towards
more points on a small cell, where they are cheap, and reaches the
Γ point alone on a cell big enough that the zone is a point, which is
nearly every framework.  Zero asks for Γ alone.

The **electronic temperature** is 300 K and not zero, because a
metallic framework at exactly zero has no gap to fill and the SCC
cycle oscillates for ever rather than failing.  The **SCC tolerance**
and iteration limit are DFTB+'s own.

## Two kinds of run

**The energy engine.**  *Single point energy* and *Optimise geometry*
in the DFTB+ panel are the application's optimiser taking one DFTB+
evaluation a step: a directory, a geometry file, a run and a parse
per step, with the charges of the last step as the starting guess for
this one (`ReadInitialCharges`), which is most of the cost of an SCC
cycle.  That is what keeps the space group and every frozen site
exactly, and what gives DFTB+ the symmetry projection, the live plot,
the trajectory and the one undoable command at the end without any of
them learning what DFTB+ is.  **No analytic stress is claimed**: DFTB+
prints one, but the sign and volume conventions of that block have
not been checked against a numeric stress, and a stress read with the
wrong sign relaxes a cell in the wrong direction while reporting that
it converged.  So a cell relaxation pays twelve extra evaluations a
step, as xTB does (`docs/TODO.md`).

**DFTB+'s own runs.**  Each is one invocation in which DFTB+ does
what it does natively, in a run folder of the workspace, and nothing
DFTB+ can do itself is done again by the application.  The
Hamiltonian is the panel's -- parameter set, dispersion, temperature
and the rest are chosen once, and every run reads them from there,
because a band structure computed with a different Hamiltonian from
the relaxation beside it would be a figure of a different crystal.

{ref}`Band structure… <mod-dftb-band-structure>`
: Charges converged on a Monkhorst-Pack mesh first, then the
  eigenvalues along a path through the zone, in one SCC iteration so
  nothing is re-converged; the Fermi level is the mesh run's.  The
  path is given as ASE names them (`GXWKGLUWLK,UX`, a comma being a
  jump), or left empty for ASE's recommended path for the cell.  A
  projected density of states can be read off the mesh run beside it.
  `bands.dat` and `bands.csv` are written into the run folder.

{ref}`Density of states… <mod-dftb-dos>`
: One SCC run on a mesh denser than the charges need (0.1 Å⁻¹ by
  default), projected onto each element and, if asked, onto s, p and
  d.  DFTB+ does not broaden; the Gaussian width is the
  application's.  Counted per cell with both spins, so the curve
  integrates to the number of electrons up to the Fermi level.

{ref}`Mulliken charges <mod-dftb-charges>`
: One SCC run with `MullikenAnalysis`, read per atom.  They come back
  as a table per site -- with the spread shown beside it when the
  atoms of one orbit do not agree, which is a run whose SCC broke the
  symmetry -- and as an overlay colouring every atom by its charge.

{ref}`Orbital… <mod-dftb-orbital>`
: One state as its two lobes, through DFTB+'s `waveplot`, which needs
  the parameter set's `wfc.*.hsd` files -- the radial parts of the
  basis, which Slater-Koster files do not carry.  A set without them
  is refused by name before anything runs.

{ref}`Optimise with DFTB+'s driver… <mod-dftb-relax>`
: One DFTB+ run relaxes the atoms and, if asked, the cell
  (`LatticeOpt`, against DFTB+'s own analytic stress, which sidesteps
  the numeric-stress cost above), with charges carried between steps
  in memory.  What that gives up is symmetry -- DFTB+ moves a P1 cell
  -- so the answer is mapped back onto the sites and the largest
  distance between where DFTB+ put an atom and where the space group
  now puts it is reported beside the energy: a few thousandths of an
  ångström is a converged relaxation, a tenth is a structure that
  wanted to leave its group.  Frozen sites are left out of DFTB+'s
  `MovedAtoms`.

{ref}`Vibrational modes… <mod-dftb-modes>`
: DFTB+'s Hessian by finite differences -- six evaluations per free
  atom, which on a framework is an afternoon -- diagonalised by its
  `modes` program.  Relax first: a Hessian taken away from a minimum
  has imaginary modes that are the gradient and not the curvature,
  and they are flagged rather than hidden.  A mode plays back as a
  loop of frames in the transport bar.

{ref}`Molecular dynamics… <mod-dftb-md>`
: Velocity Verlet with a Berendsen or Nosé--Hoover thermostat, or none
  for constant energy; half a femtosecond or less with hydrogen in the
  structure.  The frames go to the transport bar.

## Worked example

The engine is asked for like any other, with its options as `-p`
parameters; a native run is `xtal run dftb.<entry>`:

```console
$ xtal energy resources/samples/prepared/ZIF-8.cif --engine dftb -p method=dftb3 -p dispersion=d3 -p parameter_directory=~/slakos/3ob-3-1
$ xtal run dftb.dos resources/samples/prepared/ZIF-8.cif -p spacing=0.1 --workspace ~/Crystal\ Builder
```

DFTB+ is not installed on the machine this draft was written on:

```console
$ xtal energy resources/samples/prepared/ZIF-8.cif --engine dftb
error: DFTB+ is not installed, or not on PATH (XTAL_DFTB is not set).  It is at https://dftbplus.org  (conda install 'dftbplus=*=nompi_*' -c conda-forge)
```

% TODO(Sam): with DFTB+ and the 3ob set installed, run the two
% commands above and paste what they print, and what the DFTB+ panel
% reports for the single point (the per-run warnings about angular
% momentum and Hubbard derivatives, if any).

## Settings

The engine's options are listed under {ref}`DFTB+ <engine-dftb>`;
the native runs and their settings under the {ref}`DFTB+ module
<mod-dftb>`; the panel under {ref}`panel-dftb_dock`.  `xtal engines`
and `xtal modules` print the same lists.

## Limitations

- A parameter set is per element pair, and a set that lacks one pair
  the structure has cannot run; the check names the files.
- DFTB3's Hubbard derivatives exist for 3ob's elements only.
- The engine claims no stress; the native driver relaxes a cell with
  DFTB+'s own.
- Angular momenta not in the built-in table are derived by rule and
  must be checked against the set.
- Atom types have no place in DFTB, so the engine provides none.
