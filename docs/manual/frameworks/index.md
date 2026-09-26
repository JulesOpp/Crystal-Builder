# Frameworks and Nets

Building a framework from a net and building blocks, and reading the
net back out of a crystal.  After this chapter you can build a
metal--organic framework on any of the RCSR's nets with PORMAKE's
blocks or your own, understand what the builder measured and what it
did not, stack a layered framework at the spacing you want, draw a net
over a crystal and have it named, and build a molecule from a SMILES
string to use as a linker or a guest.

:::{note}
This chapter is a draft awaiting the author's review.  Every statement
about the science in it is taken from the cited papers, from the
application's own code and help text, or from measurements recorded
in the repository; where those sources stop, the chapter stops, and
the open questions have been listed for the author.
:::

The {doc}`first-build tutorial </quickstart/first-build>` walks one
build from start to finish -- **acs** on **N134** with a drawn benzene
linker -- and ends by naming its net twice.  This chapter does not
repeat that walk; it explains the rules underneath it: what a
connection point is and why it sits where it does, how a symmetric
node is turned, what happens to a layer net after it is built, and
how a drawn net is identified against the RCSR {cite}`okeeffe2008rcsr`.

Two ideas run through every page.  A **building block** is a molecule
with connection points, and a block fits a slot of the net when it has
as many connection points as the slot is coordinated -- that is the
only rule.  And a **net** is a choice of vertices and edges made over
a crystal, not a property the crystal has on its own; the builder
records the choice it built on, and you can make a different one.

```{toctree}
:maxdepth: 1

mof-builder
blocks
orientation
layers
nets
molecule-builder
```
