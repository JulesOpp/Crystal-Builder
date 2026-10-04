(tutorial-prepare-relax)=
# Tutorial: prepare and relax a deposited MOF

A structure from a database is a record of an experiment, not an
input for a calculation.  In this tutorial you take the neutron
structure of MIL-53(Cr) from the COD, make it ready for simulation,
relax it with UFF4MOF, press *Recalculate bonds* to confirm the
relaxation did not change the chemistry, measure what moved, and
compare the result with the prepared copy the application ships.  It
takes a few minutes, and every run is seconds.

```{index} single: tutorial; prepare and relax
```

The structure is {ref}`MIL-53(Cr) <cmd-sample_cod_mil53>` (COD 1502688
{cite}`mulder2010mil53`), Cr(OH)(bdc): chains of corner-sharing
CrO{sub}`6` octahedra joined by terephthalate.  What is wrong with it
as deposited is what {doc}`/structure/prepare` calls the usual three:
it is a neutron structure, so the hydrogens are *deuterium*; the
bridging hydroxide's deuterium was never located; and the cell is
I-centred, twice the size of the primitive one.

## Prepare it

1. Choose *File ▸ Open Sample ▸ From the COD ▸*
   {ref}`MIL-53(Cr) <cmd-sample_cod_mil53>`.  The *Structure* panel
   reads **Imcm (#74)**, 72 atoms, *a* = 16.772, *b* = 13.145,
   *c* = 6.847 Å.
2. Choose *Structure ▸* {ref}`Prepare for simulation…
   <cmd-prepare_simulation>`.  The top of the dialog is the diagnosis:
   the deuterium site, the four hydrogens missing from the bridging
   hydroxides, and the I-centring.  Leave every step ticked except
   the chemistry one, which is unticked by default, and press
   **Prepare**.  The command line says the same thing, one sentence a
   step:

```console
$ xtal prepare resources/samples/cod/MIL-53.cif MIL-53_prep.cif
- 1 deuterium site(s), from a neutron experiment
- 4 hydrogen(s) missing where the structure's chemistry says they must be -- rings, M6 cores, bridging hydroxides, bound methanol
- the cell is I-centred, 2 times the primitive one (72 atoms against 36)

duplicates no site written twice
deuterium  1 deuterium site(s) written as hydrogen
primitive  primitive cell of the I-centred lattice: 36 atoms, from 72
disorder   nothing is disordered
solvent    no solvent molecules
hydrogens  2 on mu2-OH bridging trivalent metals

wrote MIL-53_prep.cif: C8H5CrO5, 38 atoms, P1
```

The cell is now the primitive one, *a* = *b* = *c* = 11.191 Å with
angles 82.93, 108.07 and 144.37°, in P1, with 38 atoms: 36 from the
primitive cell and the two hydroxide hydrogens.  The formula,
C{sub}`8`H{sub}`5`CrO{sub}`5`, is Cr(OH)(bdc) for one chromium.  The
whole operation is one undo step, so {kbd}`Ctrl+Z` gives back the
file as deposited.

:::{note}
The primitive cell is a rebuild, so it is P1: the group was spent
making the cell.  For a calculation that is what is wanted -- fewer
atoms, the same crystal.  To get the group back,
{ref}`Find symmetry… <cmd-find_symmetry>` and adopt it.
:::

## Compare it with the prepared sample

*File ▸ Open Sample ▸ Prepared for simulation ▸*
{ref}`MIL-53(Cr) <cmd-sample_prep_mil53>` is the same preparation of
the same file, and then relaxed with ORB-v3 and D3(BJ)
({doc}`/structure/prepare`).  Its cell and formula are the ones you
just made:

```console
$ xtal info resources/samples/prepared/MIL-53.cif
formula        C8H5CrO5  (Z = 2)
space group    P1 (#1, triclinic)
cell           a=11.1912  b=11.1912  c=11.1912
               alpha=82.934  beta=108.070  gamma=144.374
volume         754.772 A^3
sites / atoms  38 / 38
```

It differs from your copy only in where the atoms are.  That is the
point of the next section.

## Relax it with UFF4MOF

1. Open the panel with *Modules ▸ Force Field ▸*
   {ref}`Setup and atom types… <cmd-show_ff>`.  Leave *Force field* at
   **UFF** and *Parameters* at **UFF4MOF**, and read the table of atom
   types: each chromium is `Cr6f3` and each bridging oxygen `O_3`,
   both marked *likely* where the carboxylate carbons (`C_2`) and the
   ring (`C_R`) are *certain* -- a node is an environment the typer
   can only recognise, and the table says so.  `xtal types
   MIL-53_prep.cif` prints the same table.  ({doc}`/energy/uff` says
   how the typer decides.)
2. Leave *Optimiser* at **Smart** and **Relax the cell as well**
   *unticked*: this first run moves atoms only, at the experimental
   cell.
3. Choose *Modules ▸ Force Field ▸* {ref}`Optimise geometry
   <cmd-optimize>` ({kbd}`Ctrl+Shift+E`).

```console
$ xtal optimize MIL-53_prep.cif --method smart -q -o MIL-53_pos.cif
38 atoms, 46 bonds, 92 angles, 80 torsions, 48 inversions

converged after 54 steps: -340.4680 kcal/mol to 399.6830, |F|max 0.0336 kcal/mol/A
wrote MIL-53_pos.cif
```

The run is two seconds.  The same relaxation through the Python
`Session` that the assistant uses reports the largest displacement,
which the panel puts in the status bar:

```python
from xtal.agent import Session
s = Session.open("MIL-53_prep.cif")
print(s.optimize("uff", method="smart").message)
```

```text
converged after 54 steps: energy 740.1510 -> 399.6830 kcal/mol, |F|max 0.0336 kcal/mol/A; the furthest atom moved 0.354 A
```

The command's first energy is the *change* (-340.47 kcal/mol) and
the second the final energy; the session states the start,
740.15 kcal/mol, as well.  The energy is UFF's and is the whole cell's:
it is only ever read as a difference, between two geometries of one
structure.

## Recalculate bonds

A force field never changes the bonding.  The bonds you see are the
ones perceived when the structure was prepared, and they are
recalculated only when you ask: *Structure ▸ Bonds ▸*
{ref}`Recalculate bonds <cmd-recompute_bonds>`.  Asking is how you
check the relaxation: if an atom had moved into or out of bonding
distance, the count would change.

```python
print(s.recalculate_bonds().message)
```

```text
bonds recalculated, unchanged: 46 bonds
```

The same 46 bonds, 38 atoms: the chromium has six oxygens, each
bridging hydroxide two chromiums and a hydrogen.  `xtal bonds
MIL-53_pos.cif` lists them with their lengths.

## Measure what changed

Choose *Mouse mode ▸* {ref}`Measure <cmd-mode_measure>`
({kbd}`Ctrl+7`) and click a chromium and a bridging oxygen (the one
bonded to a hydrogen) for a bond length; {doc}`/essentials/measure`
has the rest.  The four Cr–O(H) bonds of the cell, and the carboxylate
Cr–O bonds, as they came out:

| Cr–O length (Å) | prepared, unrelaxed | UFF4MOF, atoms only | shipped sample (ORB-v3 + D3) |
|---|---|---|---|
| bridging hydroxide | 1.834 | 1.898 | 1.951 |
| carboxylate | 1.990 | 1.915 | 1.991 |

The first column is the neutron structure's own geometry.  UFF4MOF
lengthens the hydroxide bond by 0.06 Å and shortens the carboxylate
ones by 0.07 Å, so the two kinds end up within 0.02 Å of each other;
the machine-learned potential leaves the carboxylates where the
experiment had them and lengthens the hydroxide by 0.12 Å.  Neither is
the answer; the table is what two engines say about one structure, and
it is why a relaxed sample says which engine relaxed it.

## Let the cell relax too, and read the warning

Now tick **Relax the cell as well** and optimise again from the
prepared structure.  This is the run to be careful with:

```console
$ xtal optimize MIL-53_prep.cif --method smart --relax-cell -q -o MIL-53_uff.cif
converged after 334 steps: -575.5148 kcal/mol to 164.6362, |F|max 0.0479 kcal/mol/A, cell -51.55% by volume
cell           10.8761 9.7897 10.8698  50.315 147.044 144.139   (365.69 A^3)
```

The cell has lost half its volume: from 754.8 to 365.7 Å{sup}`3`.
MIL-53 *breathes*, and this is its narrow-pore form; a large-pore
structure is a minimum of the real material's free energy only with
guests in it or at high temperature, and UFF knows nothing of either.
**A cell relaxed under UFF is a UFF cell**, as the panel's hint says;
for a flexible framework it can be a different phase.  The scan in
{doc}`flexible-scan` is how you see both.  For a preparation you
mean to keep at the experimental cell, relax the atoms only, as the
shipped samples were.

:::{warning}
Compare cells only after asking what the engine is for.  A relaxation
that changes a framework's volume by a half has not found "the"
structure; it has found where this force field puts it.
:::

## What to check

- The preparation said what it did and the formula is the one you
  expect, C{sub}`8`H{sub}`5`CrO{sub}`5` for Cr(OH)(bdc).
- The run converged (*|F|max* below 0.05 kcal/mol/Å) and
  *Recalculate bonds* says *unchanged*.
- Bond lengths moved by hundredths of an ångström in an atoms-only
  relaxation, not tenths; a tenth is a sign the typer was unsure (the
  panel's table says which sites).
- A cell relaxation is compared with the experimental cell and the
  difference is explained, not adopted.

## Where this is explained

{doc}`/structure/prepare` has every step, the shipped prepared
samples and what each needed; {doc}`/structure/optimisation` the
optimisers and the convergence numbers; {doc}`/energy/uff` the force
field {cite}`rappe1992uff,addicoat2014uff4mof`; and
{doc}`/structure/cell` what relaxing the cell means.
