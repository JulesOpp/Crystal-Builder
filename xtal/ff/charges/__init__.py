"""
xtal.ff.charges
===============
Charge schemes that are not one force field's own.

QEq lives in :mod:`xtal.ff.uff.qeq` because its parameters are UFF's
table.  EQeq's are ionisation energies, which belong to no force field,
so it lives here -- and anything that reads charges off the geometry
rather than a parameter set would too.
"""
