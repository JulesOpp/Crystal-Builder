# Modules

The *Modules* menu is every calculation the application can run, one
submenu per module.  After this page you know how the menu is built,
why an entry is greyed and what its tooltip tells you, and where in
this manual each calculation is described.

## How the menu is built

```{index} single: Modules menu
```

The menu is built from the module registry and nothing else, so a
module installed as a {term}`plug-in` appears in it without the
application changing.  Each submenu is a {term}`module` --
*Forcefield*, *DFTB+*,
*Porosity*, *MOF builder*, *Molecule builder*, *PXRD*, *Energy scan*,
*Net builder*, *Blender* -- and each entry inside it is one thing that
module does.  The same tree, with the *Stop* button for the run in
progress, is the {ref}`Modules panel <panel-modules_dock>`.

Whether a module *can* run is asked again every time the menu opens,
so a program installed while the window was open stops being greyed
out without a restart.  A greyed submenu's tooltip is its reason: for
the Zeo++ entries with no binary on this machine, *Zeo++ is not
installed, or not on PATH (XTAL_ZEOPP is not set).  It is at
https://www.zeoplusplus.org/*.  The path to an external program is
named in *Preferences ▸ Engines*, which also says whether each one was
found.  Entries that need no binary -- the *(faster)* porosity
entries, which read their numbers off the application's own grid --
stay enabled beside their greyed Zeo++ twins.

Two entries keep the keys they had when they were the whole of a
*Calculate* menu: *Forcefield ▸* {ref}`Single point energy
<cmd-single_point>` is {kbd}`Ctrl+E` and {ref}`Optimise geometry
<cmd-optimize>` is {kbd}`Ctrl+Shift+E`.  Their DFTB+ counterparts have
no key on purpose: a DFTB+ run is launched from its panel or this
menu, not by reflex.

## Where each module is described

- *Forcefield* (the {ref}`Force Field panel <cmd-show_ff>`, a single
  point, an optimisation) and *DFTB+* (its panel, single point,
  optimisation, band structure, density of states, Mulliken charges,
  orbital, DFTB+'s own driver, vibrational modes, molecular dynamics):
  {doc}`Energy Models </energy/index>` for the engines and what they
  are good at, and {doc}`Structure and Optimisation
  </structure/index>` for the optimisers and the *Energy scan*.
- *Porosity* (pore diameters and channels, surface area, accessible
  volume, pore size distribution, and the *(faster)* grid entries)
  and *PXRD*: {doc}`Porosity and Properties </porosity/index>`.
- *MOF builder*, *Molecule builder* and *Net builder*:
  {doc}`Frameworks and Nets </frameworks/index>`.
- *Blender ▸ Export as STL…* -- the same command as *File ▸ Export as
  STL…*: {doc}`Utilities and Export </utilities/index>`.

:::{note}
**A calculation never changes the bonding or the atoms.**  A force
field or an optimiser reads the bonds the structure has and moves the
atoms and, if asked, the cell; every structural change is yours, made
explicitly through the *Structure*, *Symmetry* and *Cell* menus.  A
{term}`dummy atom` is held back from every engine and module run and
put back afterwards, so a centroid or a connection point never stops
a calculation.
:::

While a run is going, quitting asks whether to stop it before it asks
about unsaved work, and the run continues if you answer no.
