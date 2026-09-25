# Energy Models

Every way Crystal Builder computes an energy, forces and a stress, from a classical force field to machine-learned potentials.  Each section outlines the model and its references, says what it is good and bad at for crystalline frameworks, works an example, and lists its settings.

:::{note}
This chapter is being written.  Until it is, the generated reference
in {ref}`the appendix <reference-appendix>` describes every command,
module and setting the application offers.
:::

## What this chapter will cover

- The Universal Force Field and UFF4MOF ({ref}`settings <engine-uff>`)
- Point charges: QEq and EQeq
- Tight binding: GFN1-xTB, GFN2-xTB and GFN-FF ({ref}`settings <engine-xtb>`)
- DFTB+ ({ref}`settings <engine-dftb>`, {ref}`runs <mod-dftb>`)
- Machine-learned potentials: MACE ({ref}`settings <engine-mace>`), ORB-v3 ({ref}`settings <engine-orb>`) and MatterSim ({ref}`settings <engine-mattersim>`)
- Dispersion corrections
- Choosing a model
