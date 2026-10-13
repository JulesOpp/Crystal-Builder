(thermochemistry)=
# Frequencies, thermochemistry and IR

An energy from an engine is a 0 K number for atoms held still.  After
this section you can take the vibrational modes of a structure under
any engine, turn them into an enthalpy, entropy and free energy at a
temperature, draw an IR spectrum from the same modes, and read which
of those numbers to trust.

```{index} single: thermochemistry
```
```{index} single: vibrational modes; Hessian
```
```{index} single: IR spectrum
```

Both runs are entries of the Force Field module --
{ref}`Frequencies and thermochemistry... <mod-forcefield-thermo>` and
{ref}`IR spectrum... <mod-forcefield-infrared>` -- and the Force Field
panel's **Thermochemistry...** button opens the first.  Each uses the
engine and options the panel has set up.

## What is computed

**The Hessian.**  Every {term}`engine` gives forces, so the second
derivatives are taken from them by central differences: each free
atom is moved 0.01 Å either way along each axis, which is six
evaluations per atom and one more at the start.  The matrix is
symmetrised, divided by the masses, and diagonalised; its eigenvalues
are the squared frequencies, and a negative one is an *imaginary*
mode.

```{index} single: phonopy
```

*Hessian* says how many displacements that takes.  With the `phonons`
extra installed, **phonopy** {cite}`togo2023phonopy` displaces only
the atoms and directions the space group does not already relate and
fills in every other column by symmetry: MOF-5 needs 19 displacements
where displacing every atom takes 637.  A cell narrower than 10 Å is
repeated into a supercell at least that wide, and the thermochemistry
is summed over a Γ-centred q-mesh of the whole zone; the mode table
and the IR spectrum are Γ's either way.  **Gamma only** displaces
every free atom, needs nothing installed, and is what a molecule in a
box and a run with frozen sites always take.  *Automatic* is phonopy
where it is installed and can be used.  Whichever it was, the
summary's **Hessian** row names it.

The rigid motions are projected out rather than left to the
differences: a crystal's three translations, and a molecule's three
translations and three rotations, come out at exactly zero.

**The thermochemistry.**  Each mode of wavenumber $\tilde\nu$ is a
harmonic oscillator.  With $x = hc\tilde\nu / k_\mathrm{B}T$ it holds
a zero-point energy $\tfrac12 hc\tilde\nu$, a thermal energy
$RT\,x/(e^x-1)$ and an entropy

$$
S = R\left[\frac{x}{e^x - 1} - \ln\left(1 - e^{-x}\right)\right].
$$ (harmonic-entropy)

For a **crystal**, $H = E + \mathrm{ZPE} + U_\mathrm{vib}$ and
$G = H - TS$; that $G$ is the Helmholtz energy $F$, because $PV$ of a
solid at one bar is thousandths of a kcal/mol per cell, and the
summary says so.  For a **molecule** alone in a box the ideal gas is
added: translation at the chosen pressure, rigid rotation with the
rotational symmetry number (water 2, methane 12, counted from the
geometry unless you give it), and $R\ln(2S+1)$ for the spin.

**Soft modes.**  A mode of a few tens of wavenumbers holds an entropy
that grows without bound as it softens, and in a framework those are
the modes that decide $S$.  *Quasi-RRHO entropy* replaces each mode's
entropy below the cutoff (100 cm⁻¹) by a blend going over to a free
rotor's, as Grimme proposed {cite}`grimme2012qrrho`.  Only the entropy
changes; the soft modes are counted either way.

**IR intensities.**  An intensity is how much a mode moves the
dipole, which needs the Born effective charges.  No engine here gives
a charge or a dipole, so the charges come from EQeq
{cite}`wilmer2012eqeq` (or UFF's own, when its electrostatics are
on), either **fixed** or **re-solved at each displacement**, which
follows the charge a polar bond moves as it stretches.  They are made
to sum to zero over the cell, so translations carry no intensity.
The frequencies are the engine's and the intensities the charge
model's; the spectrum's note says which.

## Practical notes

- Leave **Relax first** on.  Away from a minimum some modes are the
  gradient's rather than the curvature's and come out imaginary.  The
  relaxation is of a copy, at a tighter force tolerance than an
  ordinary optimisation, and is written beside the report as
  `relaxed.cif`; the tab is left as it was.
- Read the **Imaginary modes** row first.  Imaginary modes are left
  out of $G$ and counted, and a non-zero count means $G$ is not a
  minimum's $G$.
- Without phonopy a small cell is a Γ-only estimate, and the run log
  says so when the cell is narrower than 10 Å.  The acoustic and low
  optic branches across the zone are what a solid's entropy is made
  of, and Γ alone misses them.  With phonopy the supercell is chosen
  for you; *Supercell* takes three counts (`2 2 1`) or `gamma` to
  choose otherwise, and one too large for **Large structures** in
  Preferences is refused with the largest that fits.
- With a q-mesh, the **Modes summed**, **Soft modes** and
  **Imaginary modes** rows count entries over the mesh's points, not
  modes of the cell; the row's note says how many points.
- The cost is said before **Run**: the dialog times one evaluation of
  the structure in front and multiplies by the count, and by the
  supercell's size for phonopy.

## Worked example

Quartz from the simple samples, under UFF, with the IR spectrum:

```console
$ xtal run forcefield.thermo resources/samples/simple/quartz.cif -p engine=uff -p ir=true
relaxing a copy on UFF (uff4mof), cell included
relaxed: converged after 16 steps: -2.8185 kcal/mol to -26.1465, |F|max 0.0003 kcal/mol/A, cell -2.05% by volume
crystal: phonopy, supercell 3x3x2 (162 atoms), 18 displacements by 0.01 A on UFF (uff4mof)
q-mesh 24x24x19
IR intensities from fixed charges
G(298.15 K) = -0.171 kcal/mol per formula unit, 1% of the modes below 100 cm-1

Summary
Quantity           Per cell                                   Per formula unit  Unit
E (electronic)                                      -26.1465           -8.7155  kcal/mol
Zero-point energy                                    27.9428            9.3143  kcal/mol
H(298.15 K)                                           5.2127            1.7376  kcal/mol
T S(298.15 K)                                         5.7255            1.9085  kcal/mol
G(298.15 K)                                          -0.5127           -0.1709  kcal/mol
S                                                    19.2034            6.4011  cal/(mol K)
Imaginary modes                                            0
Hessian            phonopy, supercell 3x3x2, q-mesh 24x24x19                    19 evaluations
```

Nineteen evaluations of a 162-atom supercell, under two seconds.  The
same run with *Hessian* set to **Gamma only** takes 55 evaluations of
the cell and gives 3.72 cal/(mol K) per SiO₂: a three-formula-unit
cell 4.2 Å across samples its branches at one point, and the q-mesh
is what brings the entropy towards the 9.9 cal/(mol K) a calorimeter
measures for quartz.  What is left of the gap is UFF's.

The run folder holds `relaxed.cif`, `forces.npz` (each displacement's
forces, written as they finish), `phonopy_params.yaml` when phonopy
was used -- phonopy's own record of the cell, the displacements and
the force constants, for its band structure or DOS --
`modes.dat`, `thermo.dat` (every
temperature of the curves, in kcal and kJ), `ir.dat`,
`ir_broadened.xy` and `report.json`, which reopens the tables and
curves in the Results panel.  The Results panel's mode table plays a
mode with **Animate mode**; a click on the IR band chooses the mode
under it, and the width box redraws the band without a second run.

## Settings

Every setting, its range and its default are in the generated
reference: {ref}`mod-forcefield-thermo` and
{ref}`mod-forcefield-infrared`.

## Limitations

- By finite differences either way: no engine's analytic Hessian is
  used.
- Frozen sites need **Gamma only**: phonopy's symmetry moves every
  atom.
- Harmonic about one minimum: no anharmonicity, and no thermal
  expansion -- the cell is the relaxed 0 K one.
- Stop keeps the forces reached and gives no thermochemistry: a
  Hessian with some of its columns is not one.
- The IR spectrum is Γ's, with no LO-TO splitting: the long-range
  field of a polar crystal is not included.
- No Raman: it needs derivatives of the polarisability, which no
  engine provides.
