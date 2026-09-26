# GFN1-xTB, GFN2-xTB and GFN-FF

The GFN family sits between UFF and DFTB+ in every dimension that
matters: it needs no parameter set to download and no atom typing to
get right, it costs seconds rather than milliseconds or minutes, and
it answers for a metal node that UFF has to be extended to describe at
all.  After this section you know what each of the three methods is
for, which program runs it, and why a cell relaxation with them costs
twelve extra evaluations a step.

```{index} single: xTB
```
```{index} single: GFN2-xTB
```
```{index} single: GFN1-xTB
```
```{index} single: GFN-FF
```
```{index} single: tblite
```
```{index} single: tight binding; xTB
```

## What the methods are

GFN1-xTB {cite}`grimme2017gfn1` and GFN2-xTB {cite}`bannwarth2019gfn2`
are semiempirical tight-binding methods; GFN-FF {cite}`spicher2020gfnff`
is a generic force field fitted over the same reference data.  The
family is reviewed in {cite}`bannwarth2021xtb`.  In their authors'
words:

- **GFN1-xTB** is "a novel, special purpose semiempirical tight
  binding method for the calculation of structures, vibrational
  frequencies, and noncovalent interactions of large molecular
  systems with 1000 or more atoms", parametrised for all spd-block
  elements and the lanthanides up to $Z = 86$, with the D3 dispersion
  correction built in.
- **GFN2-xTB** adds anisotropic electrostatics through cumulative
  atomic multipole moments, incorporates the charge-dependent D4
  dispersion model self-consistently, needs no classical halogen- or
  hydrogen-bond corrections, and is parametrised up to radon.
- **GFN-FF** is "a generic force field ... completely newly developed
  to enable fast structure optimizations and molecular-dynamics
  simulations for basically any chemical structure consisting of
  elements up to radon", which "requires only starting coordinates and
  elemental composition as input from which, fully automatically, all
  potential-energy terms are constructed".  Its authors name
  metal-organic frameworks among the systems it was made for.

The application's own summary of the choice: GFN2-xTB is the default
and the most accurate of the three; GFN1-xTB is older and more robust
for metals; GFN-FF is a force field and is orders of magnitude faster,
which for a framework of a few thousand atoms is the difference
between a relaxation and an afternoon.

## One engine, two programs

The three methods are one engine whose *method* is the choice, and
the method decides which binary runs: **tblite** for the two
tight-binding methods and **xtb** for GFN-FF.  There is deliberately
no control for picking the program, because under periodic boundary
conditions -- and everything this application computes has a cell --
measurement left nothing to choose:

| | tblite 0.3.0 | tblite 0.6.0 | xtb 6.7.1 |
|---|---|---|---|
| GFN2, periodic | works | crashes (SIGSEGV) | refuses: "Multipoles not available with PBC" |
| GFN1, periodic | works | works | crashes (SIGSEGV) |
| GFN-FF, periodic | -- | -- | works |

Both crashes are the programs' and not the application's: tblite
0.6.0 segfaults on a two-atom silicon cell as readily as on MOF-5,
right after printing its repulsion energy; xtb's periodic GFN1 fails
to diagonalise the silicon cell and segfaults on MOF-5 after
reporting its own SCC converged.  So GFN2 needs a tblite that works,
and availability is answered per method: on a machine with only
tblite, GFN2 runs and GFN-FF greys out naming xtb.

Each evaluation is one subprocess: the geometry is written, the
program runs, the energy and gradient are read back (tblite's JSON
dump; xtb's `.engrad`).  The scratch directory persists for the
calculator's life, which matters most for GFN-FF: it spends its first
call working out a topology and writes it to `gfnff_topo`, and every
later call reads it back -- the topology is most of what a GFN-FF
step costs.

## Practical notes

- **Accuracy** is the SCF convergence criterion as a multiplier;
  smaller is tighter and slower.  GFN-FF has no SCF and ignores it.
- **Electronic temperature** is the Fermi filling, 300 K by default
  and not zero, for the same reason DFTB+'s is not: a metallic
  framework at exactly zero has no gap to fill and the cycle
  oscillates rather than failing.
- **Total charge** is the cell's.
- Point the application at the programs in *Preferences ▸ Engines*,
  or with the `XTAL_TBLITE` and `XTAL_XTB` environment variables; the
  engine's availability message names which is missing and where to
  get it (`conda install tblite -c conda-forge`, `conda install xtb -c
  conda-forge`).

## The stress limitation

**No analytic stress is claimed, and that was measured rather than
assumed.**  tblite writes a virial and xtb a lattice derivative, and
both are tempting: a claimed stress makes a variable-cell relaxation
twelve times cheaper.  The obvious conversion of tblite's virial --
divide by the cell volume -- was checked against the application's
finite-difference stress on quartz under GFN1-xTB and disagrees:
0.874 against 0.972 kcal/mol/Å³ on the two equal diagonal components,
with the numeric stress stable to four decimals from a $10^{-3}$
strain down to $10^{-5}$.  Ten per cent is not noise and not a sign
convention; it is a normalisation the application does not
understand.  A stress that is quietly wrong relaxes a cell to the
wrong volume while reporting that it converged, so the numeric stress
is used and its twelve extra evaluations a step are paid -- exactly as for
DFTB+, for exactly the same reason.  Finding the normalisation is an
open item in `docs/TODO.md`; until then, *Relax the cell as well* with
this engine costs thirteen evaluations a step.

## Worked example

The command is the same as for UFF, with the engine and method named:

```console
$ xtal energy resources/samples/prepared/MIL-53.cif --engine xtb -p method=gfn2
$ xtal optimize resources/samples/prepared/MIL-53.cif --engine xtb -p method=gfnff -o MIL-53_gfnff.cif
```

Neither tblite nor xtb is installed on the machine this draft was
written on, and the application says so before anything runs:

```console
$ xtal energy resources/samples/prepared/MIL-53.cif --engine xtb
error: tblite is not installed, or not on PATH (XTAL_TBLITE is not set).  It is at https://github.com/tblite/tblite  (conda install tblite -c conda-forge)
```

% TODO(Sam): run the two commands above with tblite and xtb installed
% and paste the output they print.

## Settings

The options -- method, total charge, accuracy, electronic temperature
and the SCF iteration limit -- are listed under {ref}`xTB (GFN)
<engine-xtb>`.  The engine is chosen in the Force Field panel
({ref}`panel-ff_dock`) or with `--engine xtb`.

## Limitations

- No stress of its own; a cell relaxation is by finite differences.
- Which program runs is fixed by the method, and a tblite release
  that crashes under a cell cannot be detected short of running it.
- The engine provides forces and periodicity only: no atom types, no
  charges for the force field.
