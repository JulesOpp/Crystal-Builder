# Structure and Optimisation

Finding the structure an energy model prefers, and preparing a
deposited one so that a model can be asked at all.  After this chapter
you can relax a structure's atoms and its cell under its own space
group, hold a coordinate or a cell quantity while the rest relaxes,
map an energy landscape over one or two coordinates, turn a deposited
CIF into whole atoms a calculation can use, and thread copies of a
framework through its own pores.

:::{note}
This chapter is a draft awaiting the author's review.  Every statement
about the science in it is taken from the cited papers, from the
application's own code and help text, or from measurements recorded
in the repository; where those sources stop, the chapter stops, and
the open questions have been listed for the author.
:::

Each section has the same shape: what the operation is and what it is
for, the theory the code implements with its references, practical
notes, a worked example on a sample structure with the output it
actually printed, its settings (a link to the {ref}`generated
reference <reference-appendix>`, which is written by the application
itself), and its limitations.

Two decisions run through the whole chapter.  **The variables of every
relaxation are the {term}`asymmetric unit`, not the cell**: the
{term}`space group` is kept exactly, an atom on a {term}`special
position` stays on it, and a cubic cell stays cubic, because there is
no variable that could take any of them elsewhere.  And **nothing here
changes the chemistry on its own**: a force field or optimiser never
changes the bonding or the atoms, a scan holds a coordinate rather
than freezing atoms, and the one preparation step that adds what a
file never located is never a default.

```{toctree}
:maxdepth: 1

optimisation
cell
scans
prepare
interpenetration
```
