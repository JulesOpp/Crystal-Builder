# General recommendations

These are the habits that keep a session out of trouble.  Each
follows from something the application does deliberately, and each
points at the place in the manual that explains it.

```{index} single: recommendations
```

**Work in a workspace, and let it file things.**  Every structure
gets a folder and every run lands under the structure it was run
against, with `run.log` saying what happened, in order: the version,
the engine and every option, the full typing table with the reason for
each assignment, a line per step, the energy breakdown at both ends.
That log is what makes a result defensible months later.  Do not move
runs about by hand; the tree shows the folders as they are.

**Save early with {kbd}`Ctrl+S`, and know what it does.**  A CIF you
opened becomes a `.xtalproj` beside it on the first save -- the CIF is
left alone -- and after that saving is silent.  *Preferences ▸ General*
can make it confirm before overwriting.  Use {ref}`Export… <cmd-export>`
for a file somebody else will read: it strips dummy atoms, net edges
and suppressed bonds, and says which of the format's limitations it
is about to hit.

**Bonds change only when you press Recalculate bonds.**  Not on load,
not when you edit the cell, not when an atom is placed, and not after
a relaxation.  After a build or a long optimisation, look at the bonds
before you trust anything that depends on them, and press
{ref}`Recalculate bonds <cmd-recompute_bonds>` if the geometry has
moved far enough to change them ({kbd}`Ctrl+B` is
{ref}`Reset bonds to automatic <cmd-reset_bonds>`, which also drops
the bonds you drew).  *Structure ▸* {ref}`Bond rules… <cmd-bond_rules>`
previews what a change to the criteria would add and remove before it
does it, and a bond type you set by hand always wins over the
distance rule.

**Read the atom-type table before you read the energy.**  The Force
Field panel names every site's type, what it means and how sure the
typer was, and the note under a run lists the sites it was not sure
of.  A wrong type gives a plausible number, not an obvious error; a
type can be overridden from the drop-down in that row, and the
override travels with the structure.

**Treat a relaxed UFF cell as a starting geometry.**  The panel says
so after every cell relaxation: for a framework it is routinely a few
percent out, and it is not a measured lattice constant.  UFF4MOF is
the default parameter set; switching to plain UFF is how to see what
the framework-fitted rows changed.

**The relaxation keeps the space group.**  The variables are the sites
of the asymmetric unit, so an atom on a special position stays on it.
To relax every atom independently, {ref}`Reduce to P1 <cmd-reduce_p1>`
first -- and then {ref}`Find symmetry… <cmd-find_symmetry>`
afterwards to see what the atoms
settled into, as the {doc}`first build <first-build>` does.

**Watch the tolerance when you find symmetry.**  The same coordinates
are P1 at 10{sup}`-5` Å and tetragonal at 10{sup}`-2`; the dialog
re-detects as you change the number, and the Wyckoff table under the
answer says whether it is the one you expected.  A structure solved in the wrong hand
looks perfectly good, which is why the *Structure* panel says which
hand you are in at all times.

**A dummy atom is a marker, not chemistry.**  Centroids and connection
points are `X` atoms: perception never bonds them, the force field
and *Add hydrogens* set them aside, and net edges and measurements
take them.  There is no *Unmark* for a connection point -- an `X` does
not remember what it was -- so the way back is {kbd}`Ctrl+Z`.

**Large structures: turn the picture down, not the run.**  The
*Redraw* rate in the Force Field panel is how often the 3D view
repaints while a run goes; every step is the smoothest and the
slowest, and a long run on a large cell is often best watched as the
plot alone.  Every step is still announced in the plot and the status
line whatever the rate.

**Cite what you ran.**  {doc}`/front/cite` lists, method by method,
the papers behind the force fields, engines, programs and databases
the application used on your behalf, and the Force Field panel links
them under whichever engine is selected.
