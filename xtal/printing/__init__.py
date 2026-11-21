"""
xtal.printing
=============
A structure as a model a 3D printer can take, in two colours.

One cell is cut (:func:`xtal.core.cellcut.cut_cell`), turned into balls
and sticks (:mod:`.primitives`), sampled as a distance field on one
grid (:mod:`.field`) and marched into two closed bodies that share
their interface exactly (:mod:`.mesh`); :mod:`.check` is what says a
body is a solid a slicer will take.
"""
