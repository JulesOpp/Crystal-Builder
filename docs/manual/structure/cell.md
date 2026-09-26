# Relaxing the Cell

With the cell as a variable, a relaxation finds the lattice an engine
prefers as well as the positions, under the same space group and with
an external pressure if you ask for one.  After this section you know
how the cell enters the optimisation, what the stress tolerance and
the pressure mean, why a held cell quantity is a subspace of strains
and not a check on the answer, and how much to trust a relaxed cell.

```{index} single: cell relaxation
```
```{index} single: strain; symmetry-adapted
```
```{index} single: stress; residual
```
```{index} single: pressure; P V term
```
```{index} single: cell; holding a quantity
```

## The cell as a variable

**Six more variables.**  The cell is deformed by $F = I + e$ for a
symmetric strain $e$: the lattice matrix $M$ becomes

$$
M' = M\,(I + e),
$$ (cell-strain)

and every atom is carried with it, $r' = r\,(I + e)$.  The site
variables stay in the *undeformed* frame, which is what makes the two
sets of variables independent and leaves the fractional coordinates --
what a structure actually stores -- unchanged by a strain.  The six
strain components sit beside the site coordinates in one flat vector,
so every optimiser of {doc}`optimisation` relaxes a lattice constant
without knowing that is what it is doing.

**The strain is symmetry-adapted**, by the same argument that keeps an
atom on its special position, one rank up.  A displacement transforms
as $u\,W$ and a strain, being a rank-2 tensor, as $W^\mathsf{T} e\, W$;
the average of that over the point group is the projector onto the
strains every operation preserves.  It needs no table of crystal
systems: a cubic group leaves one free strain (the isotropic one), a
hexagonal group two, a triclinic group all six, and the cell cannot
leave its crystal system because there is no variable that would take
it there.  A cubic cell relaxed here stays cubic -- not because
anything checks that it did.

Two scalings make the six new variables behave like the old ones, so
that the step cap and the line search need no special case: the
variable stored is the strain times a cell length, so a step in it is
a distance; and its gradient is divided by the number of atoms, so it
is a force per atom rather than a quantity that grows with the cell.

**An external pressure enters as a $P V$ term.**  The energy the
optimiser descends is

$$
E_\mathrm{total} = E + P\,V,
$$ (cell-pv)

with $P$ in GPa and $V$ the current cell volume in Å³, converted with
$1\ \mathrm{GPa} = 0.143933\ \mathrm{kcal\,mol^{-1}\,Å^{-3}}$ (or
$1\ \mathrm{kcal\,mol^{-1}\,Å^{-3}} = 6.9477\ \mathrm{GPa}$, a number
worth recognising).  The pressure has an effect only when the cell is
free to respond to it.

## The stress, and when the cell is converged

```{index} single: stress; analytic or numeric
```

The cell's gradient is the stress.  An engine that computes its own
is asked for it; one that does not gets it by central differences,
which is twelve more energy evaluations a step.  UFF returns its
virial, which is nine times faster a step on MFU-4l than the
differences; UFF with electrostatics on (an Ewald sum), xTB and DFTB+
pay the twelve ({doc}`/energy/choosing` has the table).

% TODO(Sam): the Force Field panel's tooltip on "Relax the cell as
% well" says the run "costs twelve extra energy evaluations a step,
% because UFF has no analytic stress"; xtal/ff/optimize.py says UFF
% returns its virial and pays the twelve only with an Ewald sum.  One
% of the two is stale -- reported.

A run with the cell free is converged when **both halves** are: the
largest force on any atom is below the force tolerance *and* the
**residual stress** is below the stress tolerance, 0.05 GPa by
default.  The residual stress is the largest component of the stress
the cell can still relax, in GPa: the external pressure is added first
-- a cell at 5 GPa is relaxed when its own stress balances it, not when
it is zero -- and the part the space group forbids is projected away,
because no allowed strain could remove it and a criterion on it could
never be met.  It has its own number and its own units because the
per-atom strain gradient that was once the only criterion let MOF-5
call itself converged under about 0.2 GPa, which is a per cent of its
volume.  A cell still under a stress is not a relaxed structure,
however still its atoms are, and the panel's *stopped before
converging* message names which half is short: *the forces (…)*, *the
cell (… GPa)*, or both.

## Holding a cell quantity

```{index} single: constant volume
```

A relaxed scan ({doc}`scans`) asks the cell to relax with something
held: a lattice parameter, or the volume.  The application does not
relax freely and then check what it held; **a held cell quantity is a
strain subspace**.  A strain is six numbers, and the space group
already forbids most of them; holding a quantity forbids more, and
both restrictions are linear subspaces of the same six-dimensional
space.  `CellFreedom` intersects the space group's allowed strains
with the null space of $\partial(\text{held quantity})/\partial e$,
one row per held quantity, and the projector onto that intersection
replaces the group's own.  The intersection is taken in a
metric-normalised coordinate -- the shears scaled by $\sqrt{2}$ --
because only there is the tensor inner product the ordinary dot
product, only there is the group's average an orthogonal projector,
and intersecting subspaces in a skew metric silently gives the wrong
subspace.

:::{note}
Holding the **volume** with the shape free is the scan the literature
on flexible frameworks actually runs, and it is the reason this is not
simply a list of lattice parameters to fix: a profile taken at a
frozen cell *shape* depends on which shape was frozen, which makes it
a measurement of the constraint rather than of the material.
:::

What can be held, and what happens when nothing is left, is decided
before the first step:

- Any of `a`, `b`, `c`, `alpha`, `beta`, `gamma`, or `volume`.
- A quantity the space group already ties is not a thing to hold.  A
  scan of `b` in a trigonal group is refused with the ties spelled out
  (the example in {doc}`scans` prints *b is not free in P3221: b = a,
  alpha = 90, beta = 90, gamma = 120.  Scan one of a, c*).
- If holding leaves no allowed strain at all, the run is refused
  rather than started: *holding … leaves the cell nothing to relax in
  this space group -- every strain it allows would change something
  being held.  Relax the atoms alone instead.*
- Scanning *every* parameter the group leaves free fixes the cell
  completely, and the point is then relaxed with no cell variables at
  all -- exact, and one evaluation a step instead of thirteen on an
  engine with no analytic stress.

The command line and the Force Field panel relax the cell freely or
not at all; a held quantity is reached through a scan axis.

## Practical notes

- A relaxed cell is the number people most want out of this and the
  one a generic force field is least entitled to be believed about.
  The panel says so whenever the cell is a variable, before and after:
  *A cell relaxed under UFF is a UFF cell: for a framework it is
  routinely a few percent out. Use it as a starting geometry, not as a
  measured lattice constant.*  On the framework benchmark that ranks
  universal potentials, UFF4MOF reaches 62 % volume accuracy where the
  best of them reach 89 % ({doc}`/energy/choosing`).
- The step column `|sigma|` and the summary's *cell … % by volume* are
  how far the cell moved; the {ref}`Structure panel <panel-info_dock>`
  gives the relaxed parameters.
- With electrostatics on, or with xTB or DFTB+, budget thirteen
  evaluations a step.  For DFTB+ its own driver's cell relaxation
  ({ref}`Optimise with DFTB+'s driver… <mod-dftb-relax>`) sidesteps
  that ({doc}`/energy/dftb`).
- A negative pressure is allowed (the panel's box goes to −100 GPa)
  and pulls the cell open; a positive one closes it.

## Worked example: the MOF-5 cell under UFF4MOF

The same prepared primitive cell as in {doc}`optimisation` (the
rhombohedral primitive setting of the cubic cell: *a* = 18.2608 Å,
all angles 60°, 4305.72 Å³), now with the cell free.  The file is in
P1, so every strain is allowed and nothing holds the three lengths
equal but the forces themselves:

```console
$ xtal optimize resources/samples/prepared/MOF-5.cif --relax-cell -o MOF-5_cell.cif
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

step          energy            max force
    0  E =     1355.15520  |F|max =  110.00889  |sigma| =   2.5638 GPa
    1  E =     1185.27391  |F|max =   80.80603  |sigma| =   1.3482 GPa
    2  E =     1122.78658  |F|max =   37.60178  |sigma| =   0.6850 GPa
    3  E =     1073.31076  |F|max =   26.77922  |sigma| =   0.3394 GPa
    4  E =     1046.44371  |F|max =   17.27975  |sigma| =   0.9316 GPa
[...]
   16  E =     1026.19893  |F|max =    0.08060  |sigma| =   0.0003 GPa
   17  E =     1026.19889  |F|max =    0.04798  |sigma| =   0.0004 GPa

converged after 17 steps: -328.9563 kcal/mol to 1026.1989, |F|max 0.0480 kcal/mol/A, cell -2.85% by volume
cell           18.0854 18.0854 18.0854  60.000 60.000 60.000   (4182.84 A^3)
wrote MOF-5_cell.cif
```

The stress column starts at 2.56 GPa and ends below a thousandth; the
three lengths and three angles come out equal to the last figure, the
cell closes by 2.85 % in volume, and the minimum is 5 kcal/mol below
the fixed-cell one of the previous section.  Whether 18.09 Å against
the deposited cell's 18.26 Å is good or bad for UFF4MOF is exactly
the question the panel's warning is about.

The same run at 1 GPa, quietly:

```console
$ xtal optimize resources/samples/prepared/MOF-5.cif --relax-cell --pressure 1 -q
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

converged after 19 steps: -361.3017 kcal/mol to 1613.5871, |F|max 0.0159 kcal/mol/A, cell -7.49% by volume
cell           17.7929 17.7929 17.7929  60.000 60.000 60.000   (3983.15 A^3)
```

The energy reported now includes the $P V$ term (1 GPa on 3983 Å³ is
573 kcal/mol), which is why it is higher than the zero-pressure
minimum while the cell is smaller.

### Holding the volume

The cheapest illustration of a held quantity is a three-point volume
scan on the nine-atom quartz cell used by the test suite (α-SiO{sub}`2`,
P3{sub}`2`21, *a* and *c* its free parameters).  With the volume held
the shape is free, so *c/a* changes from point to point:

```console
$ xtal run scan.run quartz.cif -p axis1=volume -p axis1_start=105 -p axis1_stop=120 -p axis1_steps=3 -p direction=forward --workspace ws
3 points on UFF (uff4mof)
[1/3] volume 105: -23.7861 kcal/mol (not converged)
[2/3] volume 112.5: -25.9038 kcal/mol
[3/3] volume 120: -20.5473 kcal/mol
3 of 3 points relaxed; 1 did not reach the force tolerance and are marked apart

Relaxed scan

Every point
volume (A^3)  branch   E (kcal/mol)  dE       steps  |F|max  a       c       converged
    104.9923  forward      -23.7861  +2.1176    500  0.0000  4.8181  5.2224  no
    112.4996  forward      -25.9038  +0.0000     16  0.0483  4.9247  5.3563  yes
    119.9996  forward      -20.5473  +5.3564     19  0.0360  5.0264  5.4844  yes
[...]
```

The first point ran to the step limit with the forces on the atoms at
zero, so it is the cell's half of the criterion that was not met, and
the table marks it apart rather than plotting it as a number
({doc}`scans`).

% TODO(Sam): why the 105 A^3 point does not converge -- 500 steps,
% |F|max 0.0000, stress not shown in the table -- is a question for
% Julius; the scan table has no residual-stress column to say.

## Settings

`--relax-cell`, `--stress-tolerance` (GPa) and `--pressure` (GPa) on
`xtal optimize`; **Relax the cell as well**, **Stress below** and
**Pressure** in the Force Field panel ({ref}`panel-ff_dock`), the
latter two live only when the first is ticked; the entry is
{ref}`Optimise geometry <mod-forcefield-optimise>`.  A held quantity is
an axis of {ref}`Relaxed scan… <mod-scan-run>`.

## Limitations

- The stress is analytic only for the engines that provide one; the
  rest pay twelve extra evaluations a step, and xTB's and DFTB+'s own
  stress blocks are deliberately not read until their normalisation is
  understood (`docs/TODO.md`, and {doc}`/energy/xtb`).
- A cell relaxed under UFF or UFF4MOF is a starting geometry, not a
  lattice constant; the panel says so every time.
- The cell can be held only through a scan; there is no *hold the
  volume* box in the panel or flag on `xtal optimize`.
- The relaxation is at zero kelvin: an energy, not a free energy.
