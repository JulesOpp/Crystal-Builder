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
mode.  Only the Γ point is taken, every atom of the cell displaced.

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
- A small cell is a Γ-only estimate: the run log says so when the
  cell is narrower than 10 Å.  The acoustic and low optic branches
  across the zone are what a solid's entropy is made of, and Γ alone
  misses them.
- The cost is said before **Run**: the dialog times one evaluation of
  the structure in front and multiplies by the count.

## Worked example

Quartz from the simple samples, under UFF, with the IR spectrum:

```console
$ xtal run forcefield.thermo resources/samples/simple/quartz.cif -p engine=uff -p ir=true
relaxing a copy on UFF (uff4mof), cell included
relaxed: converged after 16 steps: -2.8185 kcal/mol to -26.1465, |F|max 0.0003 kcal/mol/A, cell -2.05% by volume
crystal: 55 evaluations on UFF (uff4mof) (Gamma only, every free atom displaced by 0.01 A)
the cell is 4.2 A across at its narrowest: S and G are a Gamma-only estimate, missing the branches across the zone
IR intensities from fixed charges
G(298.15 K) = 0.031 kcal/mol per formula unit

Summary
Quantity           Per cell                        Per formula unit  Unit
E (electronic)                           -26.1465           -8.7155  kcal/mol
Zero-point energy                         27.3505            9.1168  kcal/mol
H(298.15 K)                                3.4205            1.1402  kcal/mol
T S(298.15 K)                              3.3275            1.1092  kcal/mol
G(298.15 K)                                0.0930            0.0310  kcal/mol
S                                         11.1604            3.7201  cal/(mol K)
Imaginary modes                                 0
Zero modes                                      3
```

The entropy per SiO₂ is well below what a calorimeter measures for
quartz, which is the Γ-only warning two lines above it made concrete:
a three-formula-unit cell 4.2 Å across has nine atoms' worth of
branches and samples them at one point.

The run folder holds `relaxed.cif`, `forces.npz` (each displacement's
forces, written as they finish), `modes.dat`, `thermo.dat` (every
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

- Γ only, by finite differences.  Symmetry-reduced displacements and a
  q-mesh for small cells are planned.
- Harmonic about one minimum: no anharmonicity, and no thermal
  expansion -- the cell is the relaxed 0 K one.
- Stop keeps the forces reached and gives no thermochemistry: a
  Hessian with some of its columns is not one.
- No Raman: it needs derivatives of the polarisability, which no
  engine provides.
