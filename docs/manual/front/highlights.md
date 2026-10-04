# Highlights

What is new in Crystal Builder {{ release }}.  The full list, release
by release, is the {doc}`change log </back/changelog>`.

## In 1.0

- **Disordered carbon** (*Modules ▸ Disordered carbon builder*): a
  zeolite-templated carbon or a schwarzite as one connected, terminated
  sheet that follows a net, at the density you ask for, with the rings
  Gauss--Bonnet fixes said up front --
  {doc}`the carbon builder </frameworks/carbon>`.
- **Amorphous polymers** (*Modules ▸ Polymer builder*): chains of a
  monomer packed into a box or a membrane at a target density,
  copolymers, any tacticity, ladder polymers such as PIM-1; packed, not
  equilibrated -- {doc}`the polymer builder </frameworks/polymer>`.
- **A 2D sketcher** that draws molecules and monomers, with metals built
  to their coordination shape --
  {doc}`the molecule builder </frameworks/molecule-builder>`.
- **The refinement workbench** (*Modules ▸ PXRD ▸ Refine against a
  measured pattern*): peaks, indexing, Pawley and Rietveld against a
  measured pattern or a diffractometer's own file, a parameter table,
  and Rietveld with a force field's energy --
  {doc}`refinement </porosity/refinement>`.
- **ORCA input files** (*Modules ▸ ORCA ▸ Input file*), written for any
  structure or selection, with the spin checked before anything is
  written -- {doc}`ORCA </energy/orca>`.
- **An AI assistant can work in the window**, each change one undo step,
  or on files of its own through `xtal mcp` --
  {doc}`the assistant </workflows/assistant>`.
- **Slabs** (*Cell ▸ Slab…*) that carry their bonds, and an *Open a
  Fresh Copy* when a file is already open --
  {doc}`Cell </essentials/cell>` and {doc}`File </essentials/file>`.
- **Large structures** are counted before they are built, and a size
  limit asks or refuses by a profile you choose in Preferences.

## Since 0.3.0

- **Prepare for simulation** (*Structure ▸ Prepare for simulation…*
  and `xtal prepare`): a deposited CIF made into a cell a calculation
  can use -- sites written twice merged, disorder ordered into whole
  atoms, solvent removed, the primitive cell, and missing hydrogens
  placed.  Each step says what it chose before anything is done, and
  a step that changes the chemistry is never a default.
- **Prepared copies of the sixteen COD frameworks**, under *Open
  Sample ▸ Prepared for simulation*, beside the originals as
  deposited.
- **MACE-MP-MOF0** as a model for the MACE engine
  {cite}`elena2025macemof0`.
- **Porosity from a grid** without the Zeo++ binary, beside the Zeo++
  entries, and the pore surface drawn over channels only.
- **Net transitivity from the RCSR** {cite}`okeeffe2008rcsr`, and the
  exported `.cgd` net checked by Systre
  {cite}`delgadofriedrichs2003systre`.
- *Select ▸ Bonds between elements…*

## In 0.3.0

- ORB-v3 {cite}`rhodes2025orbv3` and MatterSim
  {cite}`yang2024mattersim` beside MACE {cite}`batatia2022mace`, and
  EQeq charges {cite}`wilmer2012eqeq` for the force field.
- Sixteen metal-organic frameworks from the Crystallography Open
  Database {cite}`grazulis2012cod`.
- A MOF builder that builds chelating blocks, turns symmetric nodes so
  that the faces across every edge agree, and builds and stacks the
  RCSR's layer nets.
- *Structure ▸ Interpenetrate…*
- More file formats, autosave, and a start pane for the first minute.
