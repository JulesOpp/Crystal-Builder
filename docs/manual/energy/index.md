# Energy Models

Every way Crystal Builder computes an energy, forces and a stress, from
a classical force field to machine-learned potentials.  After this
chapter you can choose a model for a framework, set it up in the Force
Field or DFTB+ panel or on the `xtal` command line, read what it
reports, and know which of its numbers to trust and which to check
against another model.

:::{note}
This chapter is a draft awaiting the author's review.  Every statement
about the science in it is taken from the cited papers, from the
application's own code and help text, or from measurements recorded
in the repository; where those sources stop, the chapter stops, and
the open questions have been listed for the author.
:::

Each section has the same shape: what the model is and what it is for,
its energy expression and references, practical notes, a worked
example on a sample structure with the output it actually printed,
its settings (a link to the {ref}`generated reference
<reference-appendix>`, which is written by the application itself),
and its limitations.

Every {term}`engine` answers the same three questions -- the energy, the force
on each atom and, where it can, the stress on the cell -- and the
optimiser, the relaxed scan and the Force Field panel ask them the same
way whichever engine is chosen.  What differs between engines is what
they need before they can run, what they cost, and what they are good
at, which is what this chapter is about.

:::{note}
An energy engine never changes the bonding or the atoms.  It reads the
bonds the structure has, and a relaxation moves atoms and, if asked,
the cell; every structural change is yours, made explicitly.
:::

```{toctree}
:maxdepth: 1

uff
charges
xtb
dftb
ml
dispersion
choosing
```
