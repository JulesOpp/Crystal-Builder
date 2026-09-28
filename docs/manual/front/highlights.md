# Highlights

What is new in Crystal Builder {{ release }}.  The full list, release
by release, is the {doc}`change log </back/changelog>`.

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
