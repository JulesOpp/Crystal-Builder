(tutorial-export)=
# Tutorial: export for other codes

The point of a structure builder is usually a file somebody else's
program reads.  In this tutorial you take MOF-5 out three ways: a slab
as a LAMMPS data file for a molecular-dynamics run, a CIF carrying
EQeq charges for RASPA, and a periodic PDB for a viewer.  Each is a
different question about what the file must contain, and the
{doc}`/utilities/formats` page's list of what each format keeps is
what the checks below are against.

```{index} single: tutorial; export for other codes
```

## What export does to a structure

*File ▸* {ref}`Export… <cmd-export>` cleans on the way out: **no dummy
atoms, no net edges and no suppressed bonds** are written, whatever
the format ({doc}`/utilities/export`), because a marker is not
chemistry and a net edge is not a bond.  The dialog says what the
chosen format keeps and drops in one line under the picker; read it.
`xtal convert` writes any readable file as any writable one but does
**not** clean ({doc}`/utilities/formats`), so a structure with markers
or a net goes through the window's export, not the command, if it has
either.  Nothing here has either.

## A slab as a LAMMPS data file

Open *File ▸ Open Sample ▸* {ref}`MOF-5 <cmd-sample_mof5>`: the cubic
cell, 424 atoms, 25.866 Å on an edge.

1. Choose *Cell ▸* {ref}`Slab… <cmd-slab>`.  Leave **Plane (hkl)** at
   (1 0 0) and set **Layers** to 1 and **Vacuum above** to 15 Å.  The
   line under the form says what will come out before it does:
   *(1 0 0) slab, 1 layer, 25.87 A thick under 15 A of vacuum: 424
   sites, 424 atoms, V = 27340.95 A^3; 16 bonds cut at the surfaces,
   left unsaturated*.
2. Press **OK**.  The result is in P1, with the cell *c* turned to the
   plane normal, and the whole operation is one undo step.  The
   bonds the two surfaces cut are gone and counted, not perceived
   again; the cut atoms are left as they are, because capping them
   is chemistry ({doc}`/essentials/cell`).
3. Choose *File ▸ Export…*, **LAMMPS-DATA** as the format, name the
   file and press **Export**.

The same through the Python the assistant drives (the command-line
`xtal convert` has no slab):

```python
from xtal.agent import Session

s = Session.open("resources/samples/MOF-5.cif")
s.slab((1, 0, 0), layers=1, vacuum=15.0)
s.export("slab.data")
s.export("slab.pdb")
```

The file starts

```text
LAMMPS data file written by Crystal Builder: VESTA_phase_1

# No charges were set; every atom is written with q = 0
# bond type 1: O-Zn
# bond type 2: C-O
# bond type 3: C-C
# bond type 4: H-C

424 atoms
504 bonds

4 atom types
4 bond types

0.0 25.8658400000 xlo xhi
0.0 25.8658400000 ylo yhi
0.0 40.8658400000 zlo zhi
```

and continues with the masses and an `atom_style full` *Atoms* section.
What to check against {doc}`/utilities/formats`:

- **The box is the slab's**: 25.866 × 25.866 × 40.866 Å, the 25.87 Å
  of framework plus 15 Å of vacuum.  A slab's box is orthogonal here,
  so there are no tilt factors; a skewed cell gets LAMMPS's restricted
  triclinic one by a change of basis that moves no atom.
- **Types are elements and bonds are element pairs**: four atom
  types (Zn, O, C, H) and four bond types (O-Zn, C-O, C-C, H-C),
  named in comments.  The file holds **no coefficients**: choosing a
  force field is the input script's job.
- **The bonds are the ones on screen**: 504.  A bond you removed stays
  out and nothing is perceived.
- **Charges are zero and the file says so.**  Set them first and
  they are written (next section).
- **One molecule ID**: the framework is a single connected piece of
  the graph.

The file reads back: opening `slab.data` gives 424 atoms, 504 bonds
and the same box, so a LAMMPS result written the same way can be opened
in the window ({doc}`/utilities/formats`).

:::{note}
A cell too thin for LAMMPS's closest-image rule is refused by name, with
a request for a supercell; MOF-5's cell is not one, and rutile's 2.96 Å
*c* is.
:::

## A CIF with EQeq charges for RASPA

A grand-canonical Monte Carlo code wants partial charges in the CIF.
Charge equilibration gives them from the structure alone; the Force
Field panel computes them for an energy, and this section is where
they leave.  Use the prepared MOF-5, 106 atoms in its primitive cell.

1. Open *File ▸ Open Sample ▸ Prepared for simulation ▸*
   {ref}`MOF-5 <cmd-sample_prep_mof5>`.
2. In the Force Field panel, tick **Include electrostatics** and choose
   **Equilibrate (EQeq)** under *Charges from*, then press {ref}`Single point energy
   <cmd-single_point>`.  The panel shows the method's note as a
   warning -- *an estimate to look over, not a published result;
   metals expanded about Zn +2* -- and the charges are used for that
   energy ({doc}`/energy/charges`).
3. Equilibrated charges are a property of the sites, and putting
   them there is a step of its own.  The window computes them for an
   energy but, in the version this page was written against, has no menu
   command that writes them to the sites; the inspector's *Charge* box sets one site at a time.
   For the whole cell, the route is a script:

```python
import numpy as np
from xtal.agent import Session
from xtal.io.cif_writer import cif_string

s = Session.open("resources/samples/prepared/MOF-5.cif")
calc, _ = s._calculator("uff", {"coulomb": True, "charges": "eqeq"})
for site, q in zip(s.structure.sites, np.asarray(calc.charges)):
    site.charge = float(q)          # P1: one charge per site
open("MOF-5_eqeq.cif", "w").write(cif_string(s.structure))
```

(`_calculator` is the engine the window builds; the structure is P1, so
a site is an atom and the charges line up.  Charges per site, not per
atom, is what a CIF holds: a cell with symmetry needs the same value
on each atom of an orbit, which EQeq gives.)

What the charges are, by element:

| Element | sites | charge range (e) |
|---|---|---|
| Zn | 8 | +1.214 |
| O | 26 | −0.955 to −0.512 |
| C | 48 | −0.093 to +0.398 |
| H | 24 | +0.048 |

and they sum to zero (to 1e-4 once rounded to the five places the
file gives).  The zinc is within a few thousandths of the +1.211 the
EQeq authors published {cite}`wilmer2012eqeq`; a QEq about the neutral
atom would give it a negative charge ({doc}`/energy/charges`).  In the
file the column is added to the atom-site loop:

```text
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
_atom_site_U_iso_or_equiv
_atom_site_charge
[...]
Zn1      Zn     0.293526  0.119422  0.293526   1.0000  0.02528  1.21373
```

`_atom_site_charge` is the column RASPA and Zeo++ read, a computed
charge is never put in the type symbol (a whole oxidation state is,
`Zn2+`), and **File ▸ Open** reads the column back: 106 sites, the same
range, the same sum.  Check the charges rather than trusting the
method: sum them, look at the extremes, and confirm that a metal is
not given a charge beyond what that element can carry -- the
method's note names any that is.  The same CIF through `xtal
convert` to a LAMMPS data file writes the charges in the `q` column
and drops the *no charges* line, so one set serves both programs:

```console
$ xtal convert MOF-5_eqeq.cif MOF-5_q.data
wrote MOF-5_q.data: C24H12O13Zn4, 106 sites, 106 atoms, P1
```

RASPA was not run for this tutorial: that it accepts the file rests
on the format's description (the column is the one it reads), not on
a test.

## A periodic PDB for a viewer

PyMOL, VMD and Mercury read a PDB with a `CRYST1` record.  Choose
*File ▸ Export…* with **PDB** (or `s.export("slab.pdb")` above):

```text
CRYST1   25.866   25.866   40.866  90.00  90.00  90.00 P 1           1
HETATM    1 ZN   UNL A   1       7.588   5.345   8.088  1.00  0.00          ZN
```

The slab gives the cell's 424 atoms as `HETATM` records and 424
`CONECT` records, the bonds on screen.  The file keeps bonds and
nothing else of the structure -- no symmetry, occupancy,
displacement parameters, charges or view -- and **a bond through a
cell face is left out**, because `CONECT` has no way to say which copy
of its partner is meant and a viewer would draw it across the cell
({doc}`/utilities/formats`).  A viewer that understands `CRYST1` draws the cell and can replicate
it.  The file was checked for its records, not opened in VMD or PyMOL
for this tutorial.

## What to check

- The dialog's line about what the format drops is the one you
  expected, and a structure with markers or a net went through the
  window's export, not `xtal convert`.
- The LAMMPS file's atom, bond and type counts and its box are those
  of the structure, and its charges are not silently zero (the comment
  line says so when they are).
- Charges sum to the structure's net charge, and no element carries
  more than it can.
- The PDB's `CRYST1` cell is the cell; bonds across faces are absent
  by design.

## Where this is explained

{doc}`/utilities/export` and {doc}`/utilities/formats` for the door
and the formats, {doc}`/essentials/cell` for the slab,
{doc}`/energy/charges` for EQeq, QEq and what their notes say.
