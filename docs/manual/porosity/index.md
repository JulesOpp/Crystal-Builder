# Porosity and Properties

What a structure's pores measure and what its diffraction pattern
looks like.  After this chapter you can ask a framework for its
largest included and free spheres, its accessible surface area and
pore volume and its pore size distribution -- through Zeo++ where it
is installed and off the application's own distance grid where it is
not -- read the pore network and the pore surface drawn over the
crystal, and calculate a powder pattern to lay a measured one over.

:::{note}
This chapter is a draft awaiting the author's review.  Every statement
about the science in it is taken from the cited papers, from the
application's own code and help text, or from measurements recorded
in the repository; where those sources stop, the chapter stops, and
the open questions have been listed for the author.
:::

Each section has the same shape: what the calculation is and what it
is for, the theory the code implements with its references, practical
notes, a worked example on a sample structure with the output it
actually printed, its settings (a link to the {ref}`generated
reference <reference-appendix>`, which is written by the application
itself), and its limitations.

Two decisions run through the porosity half of the chapter.  **Every
number is a function of the probe and the atom radii it was measured
with**, so the probe is a named gas with its radius, the radii table
is a setting written into every log, and the picture drawn in the
view is always built from the same table as the number beside it.
And **nothing here guesses**: the largest free sphere is not drawn
where Zeo++ never said it was, a window the grid cannot resolve is
flagged rather than decided, and a pore network is dropped the moment
the atoms it was measured on move.

Everything in this chapter is a calculation on the structure as it
is.  What a number means for a material -- whether a surface area is
high, whether a calculated pattern matches a measured one -- is not
something the application says, and this chapter does not either.

```{toctree}
:maxdepth: 1

zeopp
grid
pore-surface
pxrd
```
