# The Universal Force Field and UFF4MOF

The Universal Force Field (UFF) is the engine that is always there: it
is native NumPy, runs in this process, and answers for every element.
After this section you can read the atom-type table the application
builds for a structure, decide between the UFF and UFF4MOF parameter
sets, know why electrostatics are off by default and what turning them
on costs, and compute a first energy from the command line.

```{index} single: UFF
```
```{index} single: force field; UFF
```

## What it is, and what it is for

UFF {cite}`rappe1992uff` is a molecular-mechanics force field whose
parameters are generated for every atom type from a short table of
per-element constants -- the 1992 paper's Table 1, which Crystal
Builder carries in full -- rather than fitted bond by bond.  That is
what lets it cover the whole periodic table, and it is what the
application relies on: a structure with any element in it can be given
an energy without a parameter file being found first.

The price is that UFF knows nothing about a particular compound.  Its
answer depends entirely on the **atom type** each atom is given, and
the typing is where wrong answers come from: the energy expressions
are arithmetic and either match the paper or do not, but a carbon
called `C_3` when it should have been `C_R` gives a plausible-looking
number that is simply wrong.  Section {ref}`uff-typing` explains how
the application decides, and how it tells you when it is not sure.

The environments UFF was never given, and gets visibly wrong, are the
metal nodes of a framework.  UFF4MOF {cite}`addicoat2014uff4mof` and
UFF4MOF-II {cite}`coupry2016uff4mof2` refit the metals, and two of the
oxygens, for exactly those nodes; Crystal Builder ships both
extensions and uses them by default (see {ref}`uff-uff4mof`).

## The energy expression

UFF writes the energy as a sum of valence terms over the bond graph
and non-bonded terms over pairs:

$$
E = E_\mathrm{bond} + E_\mathrm{angle} + E_\mathrm{torsion}
  + E_\mathrm{inversion} + E_\mathrm{vdW} + E_\mathrm{el}
$$ (uff-total)

The forms below are the ones the application implements
(`xtal/ff/uff/terms.py`), with the equation numbers of the 1992
paper.  Every term is written as a polynomial in a cosine, so a
linear angle or a planar torsion is an ordinary point and not a
division by zero; the only place a term is dropped is where the
geometry is genuinely degenerate (three collinear atoms have no
dihedral).  Periodic images are carried with every term, so a bond
across a cell boundary is just a bond.

**Bond stretch** (eq. 1a of {cite}`rappe1992uff`), harmonic about the
natural bond length:

$$
E_\mathrm{bond} = \tfrac{1}{2} k_{ij} (r - r_{ij})^2
$$ (uff-bond)

where the natural length (eq. 2--4) is the sum of the two atoms'
bond radii, shortened for bond order and for electronegativity
difference,

$$
r_{ij} = r_i + r_j + r_\mathrm{BO} - r_\mathrm{EN}, \qquad
r_\mathrm{BO} = -\lambda\,(r_i + r_j)\ln n, \qquad
r_\mathrm{EN} = \frac{r_i r_j (\sqrt{\chi_i} - \sqrt{\chi_j})^2}
                     {\chi_i r_i + \chi_j r_j}
$$ (uff-r0)

with $\lambda = 0.1332$ and $n$ the bond order, and the force
constant (eq. 6) follows from the two effective charges $Z^*$:

$$
k_{ij} = 664.12\,\frac{Z^*_i Z^*_j}{r_{ij}^3}
\quad\text{kcal mol}^{-1}\,\text{Å}^{-2}.
$$ (uff-kbond)

:::{note}
The paper prints the electronegativity term with a plus sign, which is
a known slip: with it, C--H comes out at 1.113 Å instead of the 1.109 Å
the paper itself quotes.  The application subtracts it, which is what
brings the paper's own worked examples back.
:::

**Angle bend** (eq. 11--13), a cosine expansion about the equilibrium
angle $\theta_0$ of the central atom's type:

$$
E_\mathrm{angle} = K_{ijk}\,(C_0 + C_1 \cos\theta + C_2 \cos 2\theta),
\qquad
C_2 = \frac{1}{4\sin^2\theta_0},\;
C_1 = -4 C_2 \cos\theta_0,\;
C_0 = C_2 (2\cos^2\theta_0 + 1),
$$ (uff-angle)

with the special periodic forms of eq. 12 for a linear
($K(1 + \cos\theta)$), trigonal-planar ($\tfrac{K}{9}(1 - \cos
3\theta)$) and square-planar ($\tfrac{K}{16}(1 - \cos 4\theta)$)
centre.  The force constant is built from the two bond lengths and
the 1--3 distance they imply, so a wide angle between long bonds comes
out soft without anyone having fitted it:

$$
K_{ijk} = 664.12\,\frac{Z^*_i Z^*_k}{r_{ik}^5}
\left[\,3 r_{ij} r_{jk} (1 - \cos^2\theta_0) - r_{ik}^2 \cos\theta_0\right].
$$ (uff-kangle)

**Torsion** (eq. 15--18), decided by the hybridisation of the two
atoms in the middle of the bond, with the barrier shared between every
dihedral about that bond:

$$
E_\mathrm{torsion} = \tfrac{1}{2} V_\phi \left[1 - \cos(n\phi_0)\cos(n\phi)\right]
$$ (uff-torsion)

For two sp³ centres $V = \sqrt{V_j V_k}$ with $n = 3$ and $\phi_0 =
180^\circ$, except that two group-16 sp³ atoms take a two-fold barrier
with its minimum at $90^\circ$ (2.0 kcal/mol for oxygen, 6.8 for the
heavier ones), which is what makes a peroxide come out skewed.  For
two sp² centres $V = 5\sqrt{U_j U_k}\,(1 + 4.18 \ln n)$ with $n = 2$
and $\phi_0 = 180^\circ$; an sp²--sp³ bond takes $V = 1$, $n = 6$,
$\phi_0 = 0$, or the sp² form with $\phi_0 = 90^\circ$ when the sp³
atom is group 16.  No torsion is placed about a bond to a metal, to an
sp centre or to a terminal atom.

**Inversion** (eq. 19), the out-of-plane bend at a three-coordinate
centre, with $\omega$ the angle between one bond and the plane of the
other two:

$$
E_\mathrm{inversion} = K_\omega\,(C_0 + C_1 \cos\omega + C_2 \cos 2\omega).
$$ (uff-inversion)

For an sp² carbon, nitrogen or oxygen $C_0 = 1$, $C_1 = -1$, $C_2 =
0$ with a barrier of 6 kcal/mol, or 50 kcal/mol when one neighbour is
a carbonyl-type `O_2`; a pyramidal P, As, Sb or Bi has its own
equilibrium angle and a 22 kcal/mol barrier.  Each of the three
neighbours takes a turn as the out-of-plane atom, so $K_\omega$ is a
third of the barrier.

**van der Waals** (eq. 20, 22), Lennard-Jones 12-6 with the
well position $x_{ij}$ and depth $D_{ij}$ as geometric means of the
two atoms' values:

$$
E_\mathrm{vdW} = D_{ij}\left[\left(\frac{x_{ij}}{r}\right)^{12}
                 - 2\left(\frac{x_{ij}}{r}\right)^{6}\right],
\qquad x_{ij} = \sqrt{x_i x_j},\; D_{ij} = \sqrt{D_i D_j}.
$$ (uff-vdw)

**Electrostatics** (eq. 21), point charges screened by a dielectric
constant $\varepsilon$:

$$
E_\mathrm{el} = 332.0637\,\frac{q_i q_j}{\varepsilon\, r_{ij}}
\quad\text{kcal mol}^{-1}.
$$ (uff-coulomb)

Under periodic boundary conditions this sum is only conditionally
convergent, so the application evaluates it by Ewald summation rather
than over a cutoff (see {ref}`uff-electrostatics`).  Bonded (1--2) and
geminal (1--3) pairs are excluded from both non-bonded terms, because
the bond and angle terms already describe them.

(uff-typing)=
## Atom typing

```{index} single: atom types
```
```{index} single: UFF; atom types
```

A UFF type name is data, not a label: five characters, the element
padded with `_` to two, one character of geometry, then the formal
oxidation state.  `Fe6+2` is octahedral iron(II); `C_R` is a resonant
(aromatic) carbon; `O_3` is an sp³ oxygen.  The geometry character is
what the application keys on when it meets an element it has no
hand-written rule for, which is how the parameter table doubles as a
table of expected coordination numbers.

Three things decide a type:

- **coordination**, from the bond graph -- so the types are only as
  good as the bonds, and *Recalculate Bonds* is the first thing to
  check when a type looks wrong;
- **geometry**, from the coordinates -- the angle at a two-coordinate
  atom is what tells a nitrile from an ether, and the sum of the
  angles at a three-coordinate one is what tells planar from
  pyramidal;
- **aromaticity**, from planar rings of the right size, detected
  through the periodic bond graph so that a ring which closes through
  a cell boundary is still a ring.

Hydrogen, boron, carbon, nitrogen, oxygen, phosphorus and sulfur have
hand-written rules.  Every other element, and every metal, falls
through to the type table: the type whose geometry character matches
the atom's coordination is chosen, and where nothing matches the atom
is reported *uncertain*, because a metal in an unusual coordination is
exactly the case UFF is worst at.

Missing hydrogens are the other running theme.  An X-ray structure
usually has none, so a benzene carbon has two neighbours rather than
three and a methyl carbon has one.  The rules are written to survive
that and to say so in the reason when it is what they assumed
("hydrogens are probably missing").  *Structure ▸ Prepare for
simulation…* places the hydrogens the file never located.

### The confidence column

Every assignment carries the reason it was made and one of three
confidences, and the Force Field panel's atom-type table shows both:

certain
: The rule had everything it needed: four neighbours, a flat aromatic
  ring, a linear angle.

likely
: The assignment carries its reasoning and is usually right -- a
  six-coordinate titanium is UFF's octahedral titanium -- but rests
  on an assumption: a coordination number alone, a bond length just
  either side of a threshold, a pyramidal carbon that is probably
  missing a hydrogen.

uncertain
: Nothing fitted: a coordination the element has no type for, or an
  atom with no neighbours to judge by.  These are the atoms to look at
  before believing the energy, and only these are counted in the
  panel's summary; warning about every *likely* row as well would put
  a warning on almost every crystal and leave nothing to notice.

You can override any type.  An override is one undoable edit, stored
on the site (`uff_type`) and saved with the structure.  The same table
appears in the relaxed-scan dialog for any engine that provides
types, and an override made in either is the same edit.

### Framework nodes

UFF4MOF's fitted rows were made for one situation and are wrong
outside it: a metal in the node of a framework, coordinated by the
oxygens of a carboxylate or the nitrogens of an azolate.  Nothing in
a five-character name says so -- `Zn3+2` and `Zn3f2` are both a
tetrahedral Zn(II) -- so the application decides from the chemistry
around the atom.  A metal is a **framework node** when every
neighbour is a non-metal, at least one of them is an O or N that is
itself bonded to a carbon, and there are at least two of them.  Each
condition rules out a real case that would otherwise take framework
parameters: rutile's titanium is octahedral and bridged by oxygen but
is an oxide, not a framework; an aquo ligand or a plain hydroxide is
not a linker; one neighbour is a terminal ligand and no node at all.

Two oxygens are treated specially on the same test.  An oxygen with
three or more neighbours, all of them metals and at least one a
framework node, is the oxide at the centre of a node and gets
UFF4MOF's `O_3_f`; rutile's oxygen bridges three titaniums and keeps
`O_3`, because the shortened framework radius would pull an oxide cell
in on itself.  A two-coordinate oxygen bridging two zeolite formers
(Si, Al, P, Ge, B) at 130° or wider gets UFF's zeolitic `O_3_z`.

:::{note}
UFF4MOF's `O_2_z` -- the type whose obvious reading is the carboxylate
oxygen on a framework metal -- is **not** assigned by the rules, and is
reachable only through the override.  It was tried and measured:
relaxing MOF-5 with it puts Zn--O(carboxylate) at 1.834 Å against an
experimental 1.941 Å, where leaving those oxygens as `O_3` gives
1.891 Å.  It makes the one number it is supposed to fix worse, so
which environment the 2014 paper fitted it for is an open question
(`docs/TODO.md`), and the carboxylate oxygen is typed `O_3`.
:::

### Worked example: the types of MOF-5

`xtal types` prints every atom's type, confidence and reason, and is
worth running before any energy.  On the COD structure of MOF-5
(*File ▸ Open Sample ▸ From the COD ▸ MOF-5*):

```console
$ xtal types resources/samples/cod/MOF-5.cif
atom       type    confidence  why
Zn0        Zn3f2   likely      4 neighbours, tetrahedral, in a framework node
Zn1        Zn3f2   likely      4 neighbours, tetrahedral, in a framework node
[...]
O32        O_3_f   certain     bridges 4 framework metals -- the oxide at the centre of a node
[...]
O40        O_3     certain     two neighbours at 132
[...]
C148       C_2     certain     planar, angles sum to 360
[...]
C298       C_R     certain     in a flat aromatic ring
[...]
H418       H_      certain
[...]

424 atoms typed: C_2x48, C_Rx144, H_x96, O_3x96, O_3_fx8, Zn3f2x32
```

The zinc is *likely* rather than *certain* because a metal is typed by
coordination alone; the carboxylate carbon is `C_2` (planar, not in a
ring), the ring carbons `C_R`, the carboxylate oxygens `O_3` and the
central oxide `O_3_f`.  No atom is uncertain.

(uff-uff4mof)=
## What UFF4MOF adds

```{index} single: UFF4MOF
```
```{index} single: parameter set; UFF or UFF4MOF
```

The parameter table has 218 rows.  The first 127 are the 1992 paper's,
covering the periodic table to lawrencium; the rest are UFF4MOF
{cite}`addicoat2014uff4mof` and UFF4MOF-II {cite}`coupry2016uff4mof2`
-- the same eleven columns, fitted to the metal nodes UFF was never
given, plus two oxygens (`O_3_f`, `O_2_z`).  A fitted row may spell an
`f` where UFF writes the sign of the oxidation state (`Zn3f2`,
`Cr6f3`), and that is the only mark a name carries to say it was
fitted rather than taken from Rappe's periodic trends; the type table
describes such a row as *framework-fitted* so that the override list
does not offer the same sentence twice.

The extension is second in the table and stays second: an element UFF
already covered keeps its own type first, and a fitted row is reached
only where the framework-node test above asks for it.  Every other
atom is typed exactly as UFF types it, which is why **UFF4MOF is the
default**: it is a superset, and plain UFF is there to compare
against -- the question somebody asks the day a UFF4MOF number looks
wrong.

:::{note}
UFF4MOF-II's table carries a second `Pt4+2` row with a different
radius from Rappe's under the same name.  It is a replacement rather
than an addition, and the application keeps the 1992 value
(`docs/TODO.md`).
:::

### Worked example: what the fitted rows change

The same structure under both parameter sets.  Only the terms that
involve the zinc and the oxide change; the torsions and the van der
Waals sum do not, because those rows carry the same non-bonded
parameters:

```console
$ xtal energy resources/samples/cod/MOF-5.cif --engine uff
424 atoms, 512 bonds, 912 angles, 960 torsions, 576 inversions

torsion           2587.0504
angle             1320.3265
bond              1038.6114
van der Waals      474.6320
inversion            0.0000
total             5420.6203

max force      110.00887 kcal/mol/A
rms force      80.79334 kcal/mol/A

$ xtal energy resources/samples/cod/MOF-5.cif --engine uff -p parameter_set=uff
424 atoms, 512 bonds, 912 angles, 960 torsions, 576 inversions

torsion           2587.0504
angle             1398.7926
bond             1212.4688
van der Waals      474.6320
inversion            0.0000
total             5672.9438

max force      110.00887 kcal/mol/A
rms force      83.74321 kcal/mol/A
```

The large forces are the deposited geometry's, not a fault: a
refinement's bond lengths are not a force field's.  Relaxing the
prepared primitive cell (106 atoms, positions only, at the
experimental cell) with each set and reading the node's bonds back
with `xtal bonds` gives, for the Zn--O(carboxylate) and Zn--O(oxide)
distances:

| | Zn--O(carboxylate) | Zn--O(oxide) |
|---|---|---|
| as deposited (COD 1516287) | 1.935 Å | 1.947 Å |
| relaxed, UFF4MOF | 1.887 Å | 1.829 Å |
| relaxed, UFF | 1.859 Å | 1.827 Å |

```console
$ xtal optimize resources/samples/prepared/MOF-5.cif --engine uff -q -o MOF-5_uff4mof.cif
[...]
converged after 12 steps: -323.9785 kcal/mol to 1031.1767, |F|max 0.0408 kcal/mol/A
$ xtal optimize resources/samples/prepared/MOF-5.cif --engine uff -p parameter_set=uff -q -o MOF-5_uff.cif
[...]
converged after 15 steps: -356.5942 kcal/mol to 1061.6418, |F|max 0.0168 kcal/mol/A
```

Both sets shorten the node's bonds from the deposited values; the
fitted `Zn3f2` row keeps the carboxylate bond closer to the
experiment than Rappe's `Zn3+2` does.

(uff-electrostatics)=
## Electrostatics

```{index} single: electrostatics
```
```{index} single: Ewald summation
```
```{index} single: charges; for the force field
```

**Electrostatics are off by default, as in UFF itself: the published
parameters were fitted without a Coulomb term.**  Turn them on with
*Include electrostatics* in the Force Field panel, or `-p coulomb=true`
on the command line, and choose where the charges come from:

- **The sites** -- the charges written on the sites, from the CIF or
  set by hand.  If every site's charge is zero the term contributes
  nothing and the run says so.  A cell whose charges do not sum to
  zero is given a uniform neutralising background, and the run says
  that too.
- **Equilibrate (QEq)** and **Equilibrate (EQeq)** -- charges from the
  geometry, by charge equilibration; see {doc}`charges`.
- **All zero**.

Under a cell the Coulomb sum is evaluated by Ewald summation: a
screened real-space part inside a cutoff, a reciprocal-space part, the
self energy and the background, converged to a relative accuracy of
$10^{-6}$ rather than truncated at a distance.  Two things follow:

- Equilibrated charges are solved **once, at the starting geometry,
  and held** for the rest of a relaxation.  Re-solving them at every
  step would make the energy non-conservative, and the forces would no
  longer be the gradient of anything.
- With charges on, the **stress is taken by finite differences**
  (twelve energy evaluations a step) rather than from the virial,
  because the reciprocal half of an Ewald sum depends on the cell
  directly and is not a sum over vectors between atoms.  Without
  charges UFF's stress is analytic.

## Cutoffs and the pair list

The van der Waals sum reaches to a **cutoff** of 12 Å by default.  The
pair count goes as the cube of it -- 10 Å is 42 % fewer pairs than
12 Å, for an LJ tail worth about a thousandth of a kcal/mol per pair --
and the potential is shifted to zero at the cutoff so that rebuilding
the pair list never moves the energy by a step, which an optimiser
would read as progress.

The list is built with a **skin** (2 Å by default) and rebuilt only
when some atom has moved half of it, or when a strain has moved the
periodic images a pair was listed with.  A larger skin trades memory
for fewer rebuilds.

## Practical notes

- Run `xtal types`, or open the Force Field panel's atom-type table,
  before believing an energy.  An *uncertain* row is an atom UFF has
  no type for in that coordination; a *likely* row is an assumption
  the reason names.
- Types follow the bonds.  If a type is wrong, the bond graph is the
  first suspect: *Recalculate Bonds*, or set the bond by hand -- a
  manually set bond type takes precedence over any distance-based one,
  and the typer reads stated bond orders (an amide C--N is 1.41 in
  UFF, not 1).
- Missing hydrogens change the types.  Prepare the structure first.
- Use plain UFF only to see what the fitted rows changed.
- An `X` dummy atom (a centroid, a connection point) is held back at
  the door: the force field is built over a structure without it, and
  it is shown with zero force.

## Settings

The engine's options -- parameter set, electrostatics, charge source,
cutoff and skin -- are listed in the reference under
{ref}`UFF <engine-uff>`; the Force Field panel is
{ref}`described <panel-ff_dock>` with the other panels, and its three
entries under {ref}`Forcefield <mod-forcefield>`.  On the command
line, `xtal energy` and `xtal optimize` take `--engine uff` (the
default) and `-p name=value` for each option; `xtal engines` lists
them.

## Limitations

- UFF is a generic force field.  It has no parameters fitted to any
  particular framework, and a node the framework-node test does not
  recognise, or a metal in a coordination its type table has no row
  for, is typed by coordination and marked as such.
- No torsion is placed about a bond to a metal (the code's decision:
  UFF names one type per metal after its commonest geometry, and a
  dihedral about a bond to a six-coordinate centre says nothing).
- Electrostatics are not part of the published parametrisation, and
  the charges the application can equilibrate are estimates to look
  over ({doc}`charges`).
- On the benchmark that ranks universal machine-learned potentials on
  frameworks, MOFSimBench {cite}`krass2025mofsimbench`, UFF4MOF
  reaches 62 % volume accuracy where the best of those potentials
  reach 89 % -- the figure the ORB-v3 engine's own notes record.  See
  {doc}`choosing`.
