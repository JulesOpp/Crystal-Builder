# Preparing a Deposited Structure

A crystal structure as refined is a statement about the *average* over
every cell of a sample, and several things that are true of an average
are not true of any one cell.  After this section you know what stands
between a deposited CIF and a calculation, what each of the seven
preparation steps decides and why, what the dialog shows before
anything is done, and where the prepared copies of the sample
structures came from.

```{index} single: Prepare for simulation
```
```{index} single: disorder; ordering
```
```{index} single: solvent; removal
```
```{index} single: hydrogens; adding
```
```{index} single: primitive cell
```

## What is wrong with a deposited cell

- **Disorder.**  A site with an occupancy of 0.5 is an atom that is
  there in half the cells.  An engine given it computes a whole atom
  -- and where two half-atoms are alternatives 0.4 Å apart, a pair
  nobody has ever seen.
- **Solvent.**  The pores of an as-made framework hold whatever it was
  crystallised from, often with no hydrogens found.
- **Deuterium**, from a neutron experiment.
- **Missing hydrogens**, never located by X-rays.
- **Open metal sites** a refinement left bare -- the terminal ligand of
  an M{sub}`3`O trimer, disordered over F, OH and water and often not
  modelled.
- **The conventional cell**, four times the primitive one when the
  group is F-centred: MIL-101 is 16 000 atoms, and 4 000 in primitive.
- **Sites written twice.**  A ConQuest export writes symmetry copies
  as sites (Ni{sub}`2`Cl{sub}`2`BTDD: 40 sites, 13 of them independent),
  which stack 1152 atoms on 378 places.

*Structure ▸* {ref}`Prepare for simulation… <cmd-prepare_simulation>`
and `xtal prepare` run the same seven steps, always in the same order,
each returning the structure and one sentence saying what it chose.
None of them is a guess dressed up as a fact: every message says what
was chosen, and the dialog shows all of them before anything is done.

:::{note}
Preparing is a rebuild and **one undo step**.  A step can change the
cell (the primitive cell), the group (ordering is in P1 unless whole
orbits went) and the atoms, and undoing half of the steps would leave
a cell nobody chose -- ordered but in the centred cell, or capped but
with the solvent put back.  The bonds of the result are perceived
afresh when they are next asked for, as after any change of group.
:::

## The steps, in order

```{index} single: prepare; steps
```

Merge sites written twice (`duplicates`)
: Every site that is a symmetry copy of another is dropped.  It goes
  first because a file with copies stacks atoms on places, and made
  the centring step's count refuse.

Write deuterium as hydrogen (`deuterium`)
: For a file anything can read.

Reduce to the primitive cell (`primitive`)
: The primitive cell of the group the file declares, every site keeping
  its label.  The result is in {term}`P1`, so each atom is tagged with
  the deposited site it came from for the ordering step's benefit, and
  the tag is removed before anything is returned.

Order the disorder (`disorder`)
: Every partially occupied site resolved into whole atoms.  Partial
  atoms are grouped into *units* -- the atoms that move together, by
  the bonds among them and by the CIF's own `_atom_site_disorder_group`
  where it names an alternative; a hydrogen goes with the atom it
  rides on, and no oxygen is shared by two oxyanion centres.  Two units
  that would put atoms too close to coexist are *alternatives*.  Per
  cluster of alternatives, as many units are kept as the occupancies
  add up to (rounded), the most occupied first and, among equals, as
  far apart as they will go; a unit with no alternative is kept as
  many times as its occupancy says it is present.  So each place gets
  its most probable occupant -- including nothing -- and the cell keeps
  the composition the refinement found: a counter-ion spread over six
  positions at 1/6 is one ion, not none.  Two orientations written at
  full occupancy (a three-membered ring of bonds no linker has) are
  disorder too, and so is an atom at full occupancy too close to an
  image of its own site -- unless it is at a bond's length and bonded
  to something else, which is a peroxide or a bound O{sub}`2`.  The
  sentence compares the ordered cell's composition per metal against
  the formula the CIF declares, and says when they differ.

Remove solvent from the pores (`solvent`)
: Every molecule in the pores whose heavy-atom formula is a known
  solvent -- water, methanol, ethanol, DMF, DEF, DMSO, acetone, THF,
  acetonitrile, dioxane, dichloromethane, chloroform, pyridine,
  benzene, toluene, NMP -- is removed.  Heavy atoms only, because an
  X-ray structure seldom has the solvent's hydrogens.

Complete M{sub}`3`O trimers' terminal ligands (`cap`)
: Each M(III){sub}`3`O(RCO{sub}`2`){sub}`6` trimer (Al, Sc, Ti, V, Cr,
  Mn, Fe, Ga, In) is given the terminal ligands its charge asks for.
  Three M(III) are +9, the µ{sub}`3`-oxide −2 and six carboxylates −6,
  which leaves +1 and one anion per trimer.  A halide in the pores is
  that anion for one trimer, which then keeps three waters; every other
  trimer carries it itself -- an F already there, else one terminal
  oxygen made hydroxide, or fluoride on an empty site -- with two
  waters.  A new ligand goes on the line from the µ{sub}`3`-O through
  the metal, where the octahedron's sixth corner is, and the hydrogens
  of the waters and the hydroxide are placed here, because only the
  trimer knows which is which.  **This step changes the chemistry of
  the material**: what it adds was not in the file, and is chosen by
  charge balance.  It is the one step in `CHEMISTRY`, and it is never a
  default.

Add missing hydrogens (`hydrogens`)
: Hydrogens **by rule first**, then the valence planner for everything
  else.  The rules, in order: on arene rings (by ring membership, 1.08 Å
  along the outward bisector); on M{sub}`6`O{sub}`8` cores (the four
  µ{sub}`3`-OH of a Zr{sub}`6`O{sub}`4`(OH){sub}`4`-like cluster; Zr, Hf, Ce,
  Th, U); on those cores' terminal OH and water, by charge; on µ{sub}`2`-OH
  bridging trivalent metals; completing bound methanol; and as
  **water** on a bare oxygen bonded to one metal that no cluster rule
  covers.  The sentence says how many went where.

:::{note}
**Chemistry is decided by connectivity and charge, never by a
refinement's bond lengths.**  A powder model's ring bonds of 1.51 Å are
still a benzene ring -- a planner reading them would give a ring CH two
hydrogens, which is why arene hydrogens are placed by ring membership.
A metal bond is dative, not covalent, and the valence planner reads it
as covalent, which is why an M{sub}`6`O{sub}`8` core's terminal ligands, a
µ{sub}`2`-OH and a bound methanol are placed by rule.  A bare oxygen on
one metal that no cluster rule covers is a water: hydroxide takes a
proton away, a charge claim only the M{sub}`6` and trimer rules know
enough to make, and the planner made Ni{sub}`2`Cl{sub}`2`BTDD's "diaqua"
oxygens hydroxide.
:::

:::{warning}
A step that adds what the file never located is a warning **either
way**.  Run, `cap` says it *changes the chemistry of the material --
what it adds was not in the file, and is chosen by charge balance*.
Not run, the result says the trimers *are left as the file has them,
without the terminal ligands their charge asks for, so the cell is not
neutral*, and their terminal oxygens get **no hydrogens at all**,
because water or hydroxide there is a choice of charge and the planner
would make all three hydroxide.
:::

## The dialog

```{index} single: Prepare for simulation; dialog
```

1. Open *Structure ▸* {ref}`Prepare for simulation…
   <cmd-prepare_simulation>`.  The top of the dialog
   ({numref}`fig-prepare-mil88b`) is the **diagnosis**: what the file
   as deposited has that a calculation cannot use, one line each.
2. Every step has a box, and every box but *Complete M3O trimers'
   terminal ligands* starts ticked, because a step with nothing to do
   says so rather than doing something -- *no solvent molecules* is an
   answer worth seeing.
3. The **preview runs the whole chain, live**, as you tick and untick
   -- what cannot be seen from the file as deposited (the trimers are
   not complete, the solvent is not a molecule) until the disorder is
   ordered is why it does not ask each step on its own.  MIL-101, the
   largest shipped structure, previews in under a second.  Under the
   boxes are the headline (*prepared for simulation: 138 -> 110 atoms,
   P1*), the cautions in a warning box, and each chosen step's
   sentence.
4. **Prepare** is enabled only when there is something to do and
   nothing refuses.  Press it; the status bar repeats the headline,
   and {kbd}`Ctrl+Z` gives back the structure as deposited.

:::{figure} /figures/structure/prepare-mil88b.png
:name: fig-prepare-mil88b
:width: 80%

*Prepare for simulation* on the COD structure of MIL-88B: the
diagnosis, the boxes with the chemistry step unticked, the headline,
the caution that the trimers are left as the file has them, and each
step's sentence.
:::

**Bonds drawn by hand are refused rather than lost.**  A structure with
bonds stated in its file, drawn or removed by hand is refused with
*this structure has N bond(s) stated in its file or drawn or removed by
hand, which ordering the disorder cannot carry through; prepare the
file as deposited, or Reset bonds to automatic first*
({ref}`Reset bonds <cmd-reset_bonds>`); one with a {term}`net` drawn
over it is told to prepare the file as deposited and draw the net on
the result.

## The prepared samples

```{index} single: samples; prepared for simulation
```

*File ▸ Open Sample ▸ Prepared for simulation* holds a prepared copy of
each COD sample -- for example {ref}`MOF-5 <cmd-sample_prep_mof5>` --
made from the COD file by every step above with `scripts/
prepare_samples.py`, and checked against the textbook formula of the
framework rather than only for clashes.  The COD files themselves are
left exactly as deposited.  Each entry's tooltip says what it needed;
`resources/samples/PROVENANCE.md` records the full table.  A few
examples: MOF-5 needed only the primitive cell; UiO-66 is the ideal
Zr{sub}`6`O{sub}`4`(OH){sub}`4`(bdc){sub}`6`, because the refinement's
~27 % missing linkers are an average the ordering does not keep;
MIL-53 is Cr(OH)(bdc), the µ{sub}`2`-OH the neutron structure never
located; MIL-88B had pyridine and water taken out of the pores and one
OH and two waters put on each trimer.

Six of them are also **relaxed**: positions only, at the experimental
cell, with ORB-v3 and D3(BJ) ({doc}`/energy/ml`), and only where the
refined linker geometry was out of line -- UFF was tried first and made
MIL-88B's linker geometry worse, and the bonding was checked unchanged
by every relaxation.  Being made from CC0 data they carry no licence;
they are this project's models, and citing one means citing the
structure it was made from.

## Worked example: MIL-88B from the COD

The COD structure of MIL-88B (*File ▸ Open Sample ▸ From the COD ▸*
{ref}`MIL-88B <cmd-sample_cod_mil88b>`, COD 7100637), with the default
steps -- everything but `cap`:

```console
$ xtal prepare resources/samples/cod/MIL-88B.cif MIL-88B_prep.cif
- 4 of 15 sites are partially occupied (0.333): an engine would count each as a whole atom
- no hydrogen at all: the X-ray structure never located them

duplicates no site written twice
deuterium  no deuterium
primitive  the cell is already primitive
disorder   ordered 36 partial atoms: kept 12, removed 24 (20 C, 4 N); the result is in P1
solvent    removed 18 solvent molecule(s) (2 pyridine, 16 water)
hydrogens  24 on arene rings; 6 the valence rules asked for on M3O trimers' terminal oxygens were not added: water or hydroxide there is a choice of charge

warning: 2 M3O trimer(s) are left as the file has them, without the terminal ligands their charge asks for, so the cell is not neutral; their terminal oxygens get no hydrogens, because water or hydroxide is a choice of charge.  Complete M3O trimers' terminal ligands makes that choice, and changes the chemistry.

wrote MIL-88B_prep.cif: C24H12Cr3O16, 110 atoms, P1
```

The partial sites are the carbons and nitrogens of pyridine in the
pores, at occupancy 1/3; ordering keeps a third of those atoms, and
the solvent step then removes the two pyridines, and the water, as
molecules.  The same file with `cap` named:

```console
$ xtal prepare resources/samples/cod/MIL-88B.cif MIL-88B_cap.cif --steps duplicates,deuterium,primitive,disorder,solvent,cap,hydrogens
[...]
cap        completed 2 M3O trimer(s): 0 F added, 2 OH and 4 water
hydrogens  24 on arene rings

warning: Complete M3O trimers' terminal ligands changes the chemistry of the material -- what it adds was not in the file, and is chosen by charge balance: completed 2 M3O trimer(s): 0 F added, 2 OH and 4 water

wrote MIL-88B_cap.cif: C24H17Cr3O16, 120 atoms, P1
```

UiO-66 (COD 4512072) shows the primitive cell and the formula check:

```console
$ xtal prepare resources/samples/cod/UiO-66.cif UiO-66_prep.cif
- 10 of 13 sites are partially occupied (0.273, 0.46, 0.54, 0.56, 0.727, ...): an engine would count each as a whole atom
- the cell is F-centred, 4 times the primitive one (688 atoms against 172)

duplicates no site written twice
deuterium  no deuterium
primitive  primitive cell of the F-centred lattice: 172 atoms, from 688
disorder   ordered 152 partial atoms: kept 115, removed 37 (37 O); per metal atom this cell differs from the CIF's formula: C 8.00 (CIF 5.82), H 4.00 (CIF 2.91), O 9.50 (CIF 10.29) -- missing hydrogens, defects the refinement averaged over, or a formula that was never complete
solvent    removed 25 solvent molecule(s) (25 water)
hydrogens  4 on M6 cores (mu3-OH)

wrote UiO-66_prep.cif: C24H14O16Zr3, 114 atoms, P1
```

And a file with nothing to prepare says so, and writes it unchanged:

```console
$ xtal prepare resources/samples/prepared/MOF-5.cif out.cif
nothing to prepare: no disorder, solvent, deuterium or missing hydrogens were found
[...]
```

## Settings

The command is {ref}`Prepare for simulation… <cmd-prepare_simulation>`
under *Structure*.  `xtal prepare INPUT OUTPUT` takes `--steps`, a
comma-separated list from `duplicates`, `deuterium`, `primitive`,
`disorder`, `solvent`, `cap`, `hydrogens`, run in that order; the
default is all but `cap`.

## Limitations

- Everything on this page is chemistry, and the page states only what
  the code does.  Whether a particular framework's trimer wants one
  anion and two waters, whether a bare oxygen on a given metal is a
  water, and whether the ordering's most-probable occupant is the
  right model of a given defect are the author's calls; the sentences
  the steps print are there so that you can make them too.
- Ordering keeps the composition the occupancies add up to.  A
  refinement's average over defects (UiO-66's missing linkers) is not
  a thing one cell can hold, and the sentence says how far the cell
  is from the declared formula.
- A cell that cannot hold half an ion is not made neutral: the
  prepared Mn-BTT has one extra-framework Mn where the charge wants
  1.5, and the prepared cubic-EuHOTP's charge is not settled
  (`PROVENANCE.md`).
- Only the solvents in the table above are recognised, by heavy-atom
  formula.
- The trimer rule covers the trivalent metals listed; the hexanuclear
  rule Zr, Hf, Ce, Th and U.  A cluster outside them gets the planner,
  and a bare oxygen a water.
