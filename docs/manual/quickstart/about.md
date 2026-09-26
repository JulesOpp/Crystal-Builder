# About Crystal Builder

Crystal Builder is a desktop application for building, manipulating,
analysing and exporting crystal structures.  It reads and writes CIF,
edits symmetry and bonding, and runs a force field, a tight-binding
code or a porosity analysis on the result, in one window.

```{index} single: Crystal Builder; what it is
```

## What it is for

The visual and interaction model take some inspiration from VESTA
{cite}`momma2011vesta`; the symmetry and force-field capability take
inspiration from Materials Studio.  The application is Python
throughout and is shipped as a packaged application for macOS and
Windows.

The document you work on is an {term}`asymmetric unit` and a
{term}`space group`, not a bag of atoms.  That is the decision most of
the behaviour follows from: an edit to one atom is an edit to its
whole symmetry orbit, a relaxation keeps the group, and *Reduce to P1*
is the way to edit atoms one at a time.

With it you can:

- **Open and save structures.**  CIF, with POSCAR/CONTCAR, mmCIF,
  pymatgen's JSON, extended XYZ and ASE trajectories beside it, and
  the application's own `.xtalproj` project, which also holds the
  view, the selection, the measurements and the runs.  Sixteen
  metal-organic frameworks from the Crystallography Open Database
  {cite}`grazulis2012cod` ship as samples, as deposited and prepared
  for simulation.
- **Edit atoms, bonds and the cell.**  Place, move, delete and retype
  atoms; draw, delete and type bonds; add hydrogens; build supercells
  and reduce cells; put solvent into a framework.
- **Work with symmetry.**  Find the space group at a tolerance you can
  change while watching the answer, set any of the 230 groups in any
  setting, descend to a subgroup, label Wyckoff positions, standardise
  the cell, invert the hand.
- **Compute energies and relax geometries.**  UFF with the UFF4MOF
  parameters {cite}`rappe1992uff,addicoat2014uff4mof,coupry2016uff4mof2`
  in process; xTB and DFTB+ as external programs; MACE, ORB-v3 and
  MatterSim as machine-learned potentials.  Every optimiser moves only
  the variables the space group allows, and the cell can relax under
  a symmetry-adapted strain.
- **Measure porosity.**  Pore diameters, surface area, accessible
  volume and the pore size distribution with Zeo++
  {cite}`willems2012zeopp`, and the same numbers from a distance grid
  without it; the pore surface is drawn over the channels.
- **Build frameworks.**  A framework from an RCSR net
  {cite}`okeeffe2008rcsr`, a metal node and a linker, with PORMAKE
  {cite}`lee2021pormake` vendored into the application; a molecule
  from a SMILES string; a net drawn on its own.  The net a framework
  reduces to is identified against the RCSR, and can be exported for
  Systre {cite}`delgadofriedrichs2003systre` to check.
- **Simulate a powder pattern**, and export a printable STL through
  Blender.

The chapter {doc}`/essentials/index` goes through the menus one by
one; the chapters after it are organised by task.

## Two halves

The application has a headless core, `xtal`, which imports no GUI
toolkit and is what every calculation runs in, and a window, the
PySide6 and VTK shell, which holds no crystallography of its own.  The
core has a command line, `xtal`, so that anything the window does --
symmetry, bonds, an optimisation, a module run -- can be done from a
script and files the same run folder the window would.  Chapter
{doc}`/workflows/index` covers it.

## Licence, source and citing

Crystal Builder is MIT licensed.  The source is at
<https://github.com/JulesOpp/Crystal-Builder>, with the packaged
builds under *Releases*.  It has no publication of its own yet; how to
cite the release you used, and the methods and programs it ran for
you, is in {doc}`/front/cite`.  What is new in this release is in
{doc}`/front/highlights`, and the whole history in the
{doc}`change log </back/changelog>`.
