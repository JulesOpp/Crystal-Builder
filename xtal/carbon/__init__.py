"""
xtal.carbon
===========
Disordered carbon frameworks -- zeolite-templated carbons and
schwarzites -- built as one connected sheet that follows a net.

The route is the one fullerenes and schwarzites have always been made
by: a smooth periodic surface around the net (:mod:`.surface`),
triangulated evenly and given its defects (:mod:`.mesh`), and then
**dualised** (:mod:`.lattice`): every triangle a carbon, every edge two
triangles share a bond.  A dual is three-coordinate by construction and
a vertex of valence *n* becomes an *n*-membered ring, so the rings are
decided on the mesh and the carbon only reads them off.

**Connected by construction.**  One percolating surface is one carbon
graph; a model of separate fragments, each plausible, is a model of a
material nobody can make, and that is the gap this fills.  The surface
is cut into ribbons by keeping part of its area, and only the largest
piece is kept and checked to percolate in all three directions.

:mod:`.build` puts the steps together, solves the cell from the carbon
density asked for, terminates the edges and relaxes the result.
"""
