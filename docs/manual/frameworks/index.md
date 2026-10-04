# Frameworks and Nets

Building a framework from a net and building blocks, and reading the
net back out of a crystal.  After this chapter you can build a
metal--organic framework on any of the RCSR's nets with PORMAKE's
blocks or your own, understand what the builder measured and what it
did not, stack a layered framework at the spacing you want, draw a net
over a crystal and have it named, build a molecule from a SMILES
string or a drawing to use as a linker or a guest, and make the two
kinds of disordered material the application builds without a
framework: a connected carbon that follows a net, and an amorphous
polymer packed from chains of a monomer.

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
only rule.  And a **net** is an arbitrary choice of vertices and
edges made over a crystal, not a property the crystal has on its
own; the builder records the choice it built on, and you can make a
different one.

```{toctree}
:maxdepth: 1

mof-builder
blocks
orientation
layers
nets
molecule-builder
carbon
polymer
```
