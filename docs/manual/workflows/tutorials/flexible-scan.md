(tutorial-flexible-scan)=
# Tutorial: scan a flexible framework

MIL-53(Cr) breathes: its wine-rack channels open and close with the
cell volume, and the energy as a function of volume is the question
people ask of it.  In this tutorial you prepare the COD structure
with its symmetry kept, watch UFF relax the cell to a different
volume than the experiment's, take a bulk modulus around that
minimum, and then scan a wide volume range in both directions and
read what a rough landscape looks like.  Everything is a few seconds
of UFF; the point is the reading, and where to be careful.

```{index} single: tutorial; flexible framework scan
```

## Keep the symmetry

A scan holds the space group.  Prepared as in {doc}`prepare-relax`,
MIL-53 would be a 38-atom P1 cell whose six cell parameters all move;
the conventional cell with its symmetry has three, and a scan of the
volume then breathes the way the framework does.

1. Open *File ▸ Open Sample ▸ From the COD ▸*
   {ref}`MIL-53(Cr) <cmd-sample_cod_mil53>`.
2. Choose *Structure ▸* {ref}`Prepare for simulation…
   <cmd-prepare_simulation>` and **untick the primitive-cell step**,
   leaving the others, then **Prepare**.  The hydrogens come back and
   the deuterium becomes hydrogen, but the cell stays the I-centred
   one.
3. {ref}`Find symmetry… <cmd-find_symmetry>` and **Adopt this group**.

```console
$ xtal prepare resources/samples/cod/MIL-53.cif MIL-53_conv.cif --steps duplicates,deuterium,disorder,solvent,hydrogens
[...]
wrote MIL-53_conv.cif: C8H5CrO5, 76 atoms, P1
$ xtal symmetry MIL-53_conv.cif --symprec 0.1 -o MIL-53_sym.cif
warning: standardised to the conventional cell: 76 atoms, V = 1509.54 A^3
Imma (#74): 76 atoms -> 8 independent sites
$ xtal info MIL-53_sym.cif | sed -n 2,5p
space group    Imma (#74, orthorhombic)
cell           a=6.8470  b=16.7720  c=13.1450
```

The group is **Imma**, in the standard setting, 8 independent sites,
76 atoms, V = 1509.54 Å{sup}`3`.  The short axis is now *a*; in the scans below it barely moves
(5.8 to 7.0 Å) while *c* runs from 5.7 to 13.8 Å, which is the cell
breathing: it closes along *c* and opens along *b*.

## Relax the cell

Open *Modules ▸ Force Field ▸* {ref}`Setup and atom types…
<cmd-show_ff>`, tick **Relax the cell as well**, and {ref}`Optimise
geometry <cmd-optimize>`.  The report line of the bulk-modulus run
below is the same relaxation:

```text
relaxed: converged after 168 steps: -1105.1582 kcal/mol to 375.1426, |F|max 0.0361 kcal/mol/A, cell -50.05% by volume
```

The cell has lost half its volume.  UFF's minimum is the narrow-pore
form, at about 754 Å{sup}`3`, not the large-pore 1509.5 Å{sup}`3` of
the experiment.  Every number that follows is *UFF's* breathing, and
the engine's own help says UFF4MOF was never fitted to reproduce a
double well ({doc}`/energy/uff`).

## The bulk modulus

*Modules ▸ Energy scan ▸* {ref}`Bulk modulus…
<mod-scan-bulk_modulus>` is a volume scan with the defaults a
modulus wants: **Relax the cell first** ticked (that relaxation is of
a copy and goes nowhere, but it decides where the volumes are), nine
points, ±6 % either side of the relaxed volume, one direction.  Press
**Run**.

```console
$ xtal run scan.bulk_modulus MIL-53_sym.cif --workspace ws
[...]
Every point
volume (A^3)  branch   E (kcal/mol)  dE       steps  |F|max  a       c       converged
    708.1493  forward      381.3953  +6.2532     54  0.0455  6.5456  5.7087  yes
    720.1117  forward      378.2524  +3.1103     50  0.0374  6.5574  5.7900  yes
    731.4192  forward      376.3971  +1.2550     50  0.0358  6.5649  5.8721  yes
    742.7269  forward      375.4141  +0.2720     60  0.0299  6.5711  5.9566  yes
    754.0356  forward      375.1421  +0.0000     62  0.0495  6.5762  6.0428  yes
    765.3478  forward      375.4556  +0.3134     43  0.0435  6.5817  6.1290  yes
    776.6508  forward      376.2544  +1.1123     49  0.0317  6.5844  6.2200  yes
    787.9641  forward      377.4690  +2.3269     52  0.0495  6.5878  6.3105  yes
    799.2743  forward      379.0412  +3.8991     52  0.0412  6.5908  6.4019  yes

Bulk modulus
branch   equation         B0 (GPa)  B0'    V0 (A^3)  RMS (kcal/mol)  points
forward  Birch-Murnaghan     25.03  11.75    753.22          0.0173       9
forward  Vinet               24.78  11.78    753.22          0.0125       9
```

(The table prints *a* and *c*; `scan.csv` has all six cell
parameters.)  This is a good scan, and what makes
it one is what the table says:

- every point **converged**, with a force below 0.05 kcal/mol/Å;
- the energy is a **smooth parabola** with its minimum in the middle,
  at 754 Å{sup}`3`, 375.14 kcal/mol, and the *dE* column is
  symmetric about it to a few tenths;
- the **two equations agree**: 25.03 and 24.78 GPa, V0 = 753.2 Å{sup}`3`
  from both, and a fit residual of 0.02 kcal/mol over nine points;
- the minimum is not at an end of the scan, which would be refused.

B0 of about 25 GPa is the *stiffness of UFF's narrow-pore phase*.
B0′ near 12 is large: read B0 as the curvature at the minimum and
B0′ with caution, and narrow the span if you need B0′ itself.  The whole
run, relaxation and nine points, took about six seconds.

## A wide scan, in both directions

Now ask the question the framework is famous for.  Open *Modules ▸
Energy scan ▸* {ref}`Relaxed scan… <mod-scan-run>`, leave the axis at
`volume`, set **From** to 700 and **To** to 1600, **Points** to 7, and
leave **Direction** at *both*.  Read the line the dialog prints under
the form -- the number of points, how long, and what is held at each
-- and press **Run**.

```console
$ xtal run scan.run MIL-53_sym.cif -p axis1=volume -p axis1_start=700 -p axis1_stop=1600 -p axis1_steps=7 --workspace ws
[...]
Every point
volume (A^3)  branch   E (kcal/mol)  dE         steps  |F|max  a       c        converged
    699.4943  forward      752.3953  +438.6772    241  0.0423  5.9281   8.0685  yes
    849.8804  forward      341.0744   +27.3563     62  0.0221  6.4110   8.5727  yes
    999.9978  forward      313.7181    +0.0000    131  0.0439  6.6247   9.4056  yes
   1149.7042  forward      406.6721   +92.9540    151  0.0246  6.7244  10.5217  yes
   1298.8357  forward      542.1719  +228.4538    153  0.0227  6.8068  11.5581  yes
   1449.5410  forward      658.7081  +344.9901    147  0.0351  6.8470  12.4335  yes
   1599.3102  forward      839.5788  +525.8607    246  0.0069  6.9464  13.6193  yes
   1599.7823  reverse      839.9838  +526.2657     47  0.0458  6.9602  13.4515  yes
   1449.1617  reverse      658.4205  +344.7024    180  0.0250  6.8291  12.6067  yes
   1298.8793  reverse      515.2586  +201.5406    190  0.0223  6.7326  11.3971  yes
   1149.9071  reverse      409.2502   +95.5321    135  0.0288  6.6569  10.1514  yes
    999.9991  reverse      352.9335   +39.2154    117  0.0426  6.5689   9.2363  yes
    849.5226  reverse      408.7160   +94.9979     70  0.0379  6.3628   8.5335  yes
    699.7795  reverse      762.4849  +448.7668     65  0.0259  5.9332   8.1590  yes
```

Fourteen relaxations, about fifteen seconds.  This is the opposite of
the bulk modulus's table, and it is the one to learn to read:

- **The achieved volume is the target.**  The first column is the
  volume each point *came out at*; the targets were 700, 850, 1000,
  1150, 1300, 1450 and 1600 Å{sup}`3` (`scan.csv` has both), and
  every point is within 0.1 % of its own.  A held volume is only
  held to first order by one relaxation, so a point whose shape moves
  far is relaxed again from its target volume until it is there
  ({doc}`/structure/scans`); one that never gets there is not counted
  converged.
- **The two branches disagree.**  At about 1000 Å{sup}`3` the forward
  walk gives 313.7 kcal/mol and the reverse 352.9; at 850, 341.1
  and 408.7; at 1300, 542.2 and 515.3.  The two walks meet only at the
  top of the range, 839.6 and 840.0.  They are **different basins**:
  a point starts from its relaxed neighbour, so each branch stays in
  the one it arrived in, and the gap is the {term}`hysteresis` the
  application reports side by side instead of averaging.
- **The ends are not the physics.**  The lowest-volume forward point
  is 752 kcal/mol, a cell squeezed to 700 Å{sup}`3` from a start at
  1500, and the reverse branch's last point is 762; the ends of a
  scan are where a start is furthest from the answer.

So what do you take from a landscape like this?  Not a double
well: the lowest energy anywhere in it is the 314 kcal/mol near
1000 Å{sup}`3` on the forward branch, in the middle of the range and
not at either of the two phases' volumes, and the narrow-pore
minimum of the previous section, 375 kcal/mol at 754 Å{sup}`3`, is
higher than that: the relaxation stopped in the first basin it fell
into.  Both are relaxations of one force field that the
manual says is not fitted for this.  What you take is a procedure:

1. scan **both directions** and compare the branches;
2. read the **achieved** volume beside the target, and the
   *converged* column that says whether it was reached;
3. do not fit a modulus to a curve with a branch gap, and accept the
   modulus table's refusal when it gives one;
4. repeat the scan with a machine-learned engine from the Force Field
   panel, **pre-relaxed** by UFF4MOF to keep it affordable
   ({doc}`/structure/scans`), which is the engine the method's own
   advice names for a flexible framework ({doc}`/energy/ml`).

:::{warning}
The wide scan above is a *demonstration of how to read a scan*, not a
result about MIL-53.  Its landscape is UFF's, walked from one
starting geometry, and a modulus or a barrier taken from it would be
an artefact of the engine and the path.
:::

## What a scan leaves behind

Each run's folder, under the structure's entry in the workspace,
holds `scan.csv` (one row per point: target, achieved, branch, energy,
convergence, steps, force, the six cell parameters and the file),
`forward-NN.cif` and `reverse-NN.cif` (the relaxed structure at every
point), `report.json` and `run.log`.  Double-click `report.json` in
the *Workspace* panel to put the landscape back in the Results panel,
and a click on a point opens the structure at that point.  A scan
returns no structure of its own: the tab it ran on is the crystal the
landscape is *of*.

## What to check

- Every point converged and the force is below the tolerance.
- The achieved value is the target, or close enough that you can say
  why not.
- The branches agree where you want to read one curve; where they do
  not, that is the result.
- The minimum lies inside the range, with the energy rising on both
  sides, before a modulus is believed.
- The engine is one you trust for this material.

## Where this is explained

{doc}`/structure/scans` for axes, seeds, directions and holes and the
bulk modulus fit, {doc}`/structure/cell` for what is held when the cell
moves, {doc}`/energy/uff` and {doc}`/energy/ml` for the engines.
