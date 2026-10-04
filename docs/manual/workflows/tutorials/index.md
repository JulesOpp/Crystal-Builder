(workflows-tutorials)=
# Worked Tutorials

Six exercises, each from a sample that ships with the application to
a number you can check.  The first build in the {doc}`Quickstart
</quickstart/first-build>` shows the shape of the window; these show
what to do with it.  Each tutorial gives the steps in the window and
the `xtal` command or the few lines of Python that do the same thing
beside them, so a result found by clicking can be reproduced from a
script, and the numbers printed are what the steps produced when
they were run.

```{index} single: tutorial; index
```

| Tutorial | You start from | You finish with |
|---|---|---|
| {doc}`prepare-relax` | the COD structure of MIL-53(Cr) | a model prepared for simulation, relaxed with UFF4MOF, and compared with the shipped prepared copy |
| {doc}`porosity-hkust1` | HKUST-1 | a surface area, a pore volume and the largest cavity, and the pore surface drawn |
| {doc}`draw-and-build` | a SMILES string | your own linker saved as a block, a MOF built from it, and a substituted linker |
| {doc}`pxrd` | HKUST-1 | a calculated pattern, the files it leaves, and what to do with a measured one |
| {doc}`flexible-scan` | MIL-53(Cr) | a relaxed cell, a bulk modulus, and a landscape with two branches to read |
| {doc}`export` | MOF-5 | a LAMMPS data file of a slab, a CIF with charges for RASPA, and a PDB for a viewer |

## Before you start

- **Run the commands from the repository root**, so that the sample
  paths `resources/samples/...` resolve, and with the environment the
  application was installed into active ({doc}`/quickstart/installation`).
  The window's *File ▸ Open Sample* copies the same files into your
  workspace.
- **Every command here writes into a folder you name.**  `--workspace
  ws` files a run in the layout the window reads, so a run made from
  the command line can be opened from the window afterwards
  ({doc}`/workflows/workspaces`).
- **Times are those of the machine the page was written on**, a
  laptop with no GPU, and are given to say whether a step is a second
  or an overnight job, not to compare machines.
- **A tutorial says what it could not check.**  Where a step needs
  something this page could not run -- a measured pattern, RASPA, a
  viewer -- the page says so and keeps the claim to what the
  manual already states.

```{toctree}
:maxdepth: 1

prepare-relax
porosity-hkust1
draw-and-build
pxrd
flexible-scan
export
```
