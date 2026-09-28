# Point charges: QEq and EQeq

When a structure carries no charges and you want UFF's Coulomb term,
the application can equilibrate a set from the geometry.  After this
section you know what charge equilibration solves, how EQeq changes
what QEq does, what a *charge centre* is and why it decides the
answer, and how to read the note the run leaves beside its charges.

```{index} single: charge equilibration
```
```{index} single: QEq
```
```{index} single: EQeq
```
```{index} single: charge centre
```

## What charge equilibration solves

QEq {cite}`rappe1991qeq` says that charge flows between atoms until
every atom has the same electronegativity, subject to the whole
system staying neutral.  Write the energy of a set of atomic charges
$Q_i$ as

$$
E(Q) = \sum_i \left(\chi_i Q_i + \tfrac{1}{2} J_{ii} Q_i^2\right)
     + \sum_{i<j} J_{ij}(r_{ij})\, Q_i Q_j
$$ (qeq-energy)

with $\chi_i$ an atom's electronegativity and $J_{ii}$ its hardness
(the second derivative of its energy with respect to charge), and the
condition is that every $\partial E/\partial Q_i$ is equal.  That is
a linear system, and its solution is the charges.  The parameters
come from the same table as the force field: UFF's Table 1 carries
$\chi$ and a hardness column for every type.

:::{note}
UFF's table stores *half* the QEq idempotential -- 6.9452 for
hydrogen where the QEq paper's $J$ is 13.8904 -- because it is
written for an energy of the form $\chi Q + \mathrm{Hard}\,Q^2$.  The
application doubles the column.  Used directly, the diagonal is
halved, the matrix is nearly singular against its own off-diagonals,
and the charges come back as several electrons per atom.
:::

**What the application's QEq is not.**  The paper computes
$J_{ij}(r)$ as the Coulomb integral between two Slater orbitals, with
a further charge-dependent correction for hydrogen.  Here $J_{ij}$ is
the Ohno--Klopman shielded form, which has the same two limits that
matter -- it tends to the combined hardness as the atoms merge and to
a bare $1/r$ as they separate -- but is not the same function in
between.  The charges are close to QEq's and are meant as a starting
point to look at and edit, not as a published result, and the run
says so in the note it leaves.  The dense $N \times N$ system is
refused above 2000 atoms rather than appearing to hang.

## EQeq: the same idea with measured atoms

EQeq {cite}`wilmer2012eqeq` keeps the energy {eq}`qeq-energy` and
changes where $\chi$ and $J$ come from.  QEq's are fitted parameters
about the *neutral* atom, and a zinc in a framework is nowhere near
neutral: expanded about $Q = 0$, its energy curve is the wrong curve
by the time it reaches $+1.2$, and QEq's metal charges are where it
fails worst.  EQeq expands each element about a **charge centre** $c$
instead -- the charge it usually carries -- and reads the curve there
off the atom's own ionisation energies:

$$
\chi = \frac{\mathrm{IE}_{c+1} + \mathrm{IE}_c}{2} - c\,J, \qquad
J = \mathrm{IE}_{c+1} - \mathrm{IE}_c,
$$ (eqeq-parameters)

with $\mathrm{IE}_0$ the electron affinity.  The $-cJ$ moves the
expansion back to $Q = 0$, so the solver is QEq's own and the charges
it returns are the atoms' charges, not offsets from $c$.

Between atoms the interaction is Coulomb's law screened by a
dielectric constant $\lambda = 1.2$, plus a Gaussian overlap term
that takes $1/r$ to the finite $\lambda\sqrt{J_i J_j}$ as two atoms
merge.  Hydrogen's electron affinity is set to $-2$ eV, the value the
authors fitted in place of the measured 0.754 eV, which would make
hydrogen far too ready to take an electron; it is a parameter of the
method, not a property of the atom.

Two things differ from the published program.  The Coulomb half is
summed by Ewald and converged, where the authors' program truncates it
at two cells either way; and the ionisation energies are NIST's
Atomic Spectra Database's, with electron affinities from PubChem,
written into the application's own table rather than copied from the
GPL-licensed table the published implementations carry.  On a
framework's cell the differences are small: run on the same MOF-5
atoms, the authors' program and the application agree to 0.0002 e;
and against the numbers the paper publishes for IRMOF-1, which are
for a different geometry, the application's zinc is +1.210 to their
+1.211.  On a cell under about ten ångströms they are not, because
two cells either way is not a converged sum there.

## The charge centres

**The centre decides the answer.**  EQeq's parabola is a finite
difference between the energies at $c$ and $c + 1$, so it is only an
approximation near $c$; a metal expanded about the neutral atom has a
soft curve there and runs away -- Al-soc-MOF-1's aluminium came out
$+6.33$ and its oxygens $-3.57$ when only the paper's seven metals had
centres.  Ongari et al. {cite}`ongari2019eqeq`, comparing EQeq with
DDEC charges over 2338 frameworks, found it heavily affected by the
centre, with the common oxidation state necessary for the alkali
metals and for aluminium.

So the application expands **every metal about its common oxidation
state** and non-metals and metalloids about 0, as the paper does.
The paper's own seven (Mg, V, Co, Ni, Cu, Zn, Zr) are kept as it gave
them, which leaves vanadium at +4.  The values agree with Open
Babel's EQeq table, which is where the authors' repository now sends
its users.

A common state is not every framework's: MIL-88B is chromium(III)
and the table's chromium is +2, which gives Cr +1.24 where +3 gives
+1.59.  The core's `equilibrate(centres=...)` takes a framework's own
centres; **that override has no place in the Force Field panel yet**,
and whether a CIF's `_atom_site_oxidation_number` should win over the
table is an open question (`docs/TODO.md`).

## What the application does with them

- The charges are solved once, at the starting geometry, and held for
  the whole relaxation (see {ref}`uff-electrostatics`).
- A **note** is left beside them, shown as a warning in the panel and
  on the command line.  For EQeq it names the method, the source of
  the table, and the charge centres the metals were expanded about;
  and it names any atom whose charge came out beyond what that
  element could carry -- the sign that a cation was expanded about the
  wrong centre -- with the remedy.
- QEq's note says that its integrals are not the paper's and that
  hydrogen has no charge-dependent hardness here, which is what keeps
  QEq's O--H and C--H charges smaller than these.

## Worked example: MOF-5 under EQeq and QEq

On the prepared primitive cell of MOF-5 (106 atoms), electrostatics
on:

```console
$ xtal energy resources/samples/prepared/MOF-5.cif --engine uff -p coulomb=true -p charges=eqeq
warning: EQeq charges (Wilmer, Kim and Snurr 2012) from NIST ionisation energies; an estimate to look over, not a published result; metals expanded about Zn +2
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

electrostatic    -3109.1033
torsion            646.7626
angle              330.0816
bond               259.6529
van der Waals      118.6581
inversion            0.0000
total            -1753.9481

max force      114.91861 kcal/mol/A
rms force      85.23653 kcal/mol/A

$ xtal energy resources/samples/prepared/MOF-5.cif --engine uff -p coulomb=true -p charges=qeq
warning: equilibrated charges use a shielded Coulomb integral in place of QEq's Slater integrals; treat them as an estimate to look over, not a published result. Hydrogen has no charge-dependent hardness here, which is what keeps QEq's O-H and C-H charges smaller than these
106 atoms, 128 bonds, 228 angles, 240 torsions, 144 inversions

torsion            646.7626
angle              330.0816
bond               259.6529
electrostatic      189.7134
van der Waals      118.6581
inversion            0.0000
total             1544.8686

max force      111.04152 kcal/mol/A
rms force      81.01627 kcal/mol/A
```

The charges the two runs assigned, read from the calculator and
summarised by element (the command line does not print them):

| Element | EQeq | QEq |
|---|---|---|
| Zn (8) | +1.214 | −0.617 |
| O (26) | −0.512 to −0.955 | −0.003 to +1.246 |
| C (48) | −0.093 to +0.398 | −0.383 to +0.095 |
| H (24) | +0.048 | +0.221 |

Both sets sum to zero.  EQeq's zinc is within a few thousandths of
the +1.211 the authors published; QEq about the neutral atom puts a
*negative* charge on the zinc and a positive one on the oxide, which
is the failure the charge centres exist to fix.  The electrostatic energies differ accordingly,
in size and in sign.

## Settings

The charge source is the *Charges from* option of the
{ref}`UFF engine <engine-uff>`, read only when *Include
electrostatics* is on; on the command line, `-p coulomb=true -p
charges=eqeq` (or `qeq`, `site`, `zero`).

## Limitations

- Both schemes give estimates to look over.  Neither reproduces the
  published method exactly (QEq's integrals; EQeq's converged Ewald
  sum and newer table), and the note says which.
- The charge centre is a per-element table, not a per-structure
  choice, and cannot yet be changed in the window.
- The dense solve is refused above 2000 atoms.  Set charges on the
  sites for a larger cell, or turn electrostatics off.
