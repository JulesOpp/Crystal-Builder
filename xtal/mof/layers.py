"""
xtal.mof.layers
===============
A 2-periodic net built, and then stacked.

PORMAKE's 2403 nets are all 3-periodic, and a layered MOF --
Ni3(HITP)2, Cu-HHTP, every 2-D COF -- is a sheet repeated along the
one direction the net says nothing about.  So a layer net ships as a
``.cgd`` in a 3-D cell, the form Zeo++'s own ``hcb.cgd`` already uses,
and the stacking is **set after the build rather than asked of it**.

Asking the builder does not work, and that was measured rather than
assumed (probe P9).  PORMAKE's scaler applies one global factor to the
whole cell, so ``hcb`` written with *c* = 10 comes out of a
Ni3(HITP)2 build with *c* = 107.154 A: the stacking axis is scaled
with everything else, by a factor chosen for the in-plane edges.  The
layer, though, comes out flat to 0.0000 A, so nothing is lost by
throwing the built *c* away and writing the one the user asked for.

What :func:`restack` changes is **only the stacking**.  Each layer is
translated as a whole to where the new cell puts it and keeps its own
out-of-plane shape, so a block that is not flat -- a paddlewheel's
axial ligands, a hydrogen out of the ring -- is carried rather than
squashed by the thirty-fold change in *c*.  In-plane nothing moves at
all: every edge of a layer net lies in its plane, so every image the
net records, and every joint the builder made, means what it meant.
"""

from __future__ import annotations

import numpy as np

#: The spacing a layer net is stacked at when nobody says otherwise.
#: Graphite's 3.35 A, rounded: pi-stacked sheets sit between 3.2 and
#: 3.5 A -- Ni3(HITP)2 at 3.24, Cu-HHTP at 3.3 -- and a spacing
#: somebody has to type before a layered framework is anything but a
#: hundred Angstrom of vacuum is a default nobody would choose.
DEFAULT_SPACING = 3.4


def stacking_axis_is_free(net) -> bool:
    """Whether *net* is a layer lying in the cell's *ab* plane.

    Two things, both read off the graph and neither off the file's
    name: the net's own lattice has rank two, and no cycle of it
    closes along *c*.  The second is what makes *c* the axis a spacing
    may be written on; a layer in the *ac* plane is still a layer, and
    is refused rather than stacked along a direction it is periodic
    in.
    """
    if net.periodicity() != 2:
        return False
    voltages = np.asarray(net.voltages(), dtype=int)
    return bool(len(voltages)) and not voltages[:, 2].any()


def stacking_vector(cell, spacing: float, offset=(0.0, 0.0),
                    repeat=(1, 1, 1)) -> np.ndarray:
    """One layer to the next, as a Cartesian vector.

    *spacing* along the normal to the layer, and *offset* in fractions
    of the **net's own** *a* and *b* -- the cell before it was
    repeated, which is what makes ``(1/3, 2/3)`` mean the same slip on
    a 1x1x1 and on a 2x2x1.  ``(0, 0)`` is eclipsed stacking, the way
    Ni3(HITP)2 is stacked.
    """
    cell = np.asarray(cell, dtype=float)
    a, b = cell[0], cell[1]
    normal = np.cross(a, b)
    normal /= np.linalg.norm(normal)
    if np.dot(normal, cell[2]) < 0:
        # Keep the handedness the builder wrote: a cell whose c has
        # turned through the plane is a left-handed one, and a
        # left-handed cell is a mirror image in every reader that
        # does not check.
        normal = -normal
    return (float(offset[0]) * a / repeat[0]
            + float(offset[1]) * b / repeat[1]
            + float(spacing) * normal)


def restack(framework, spacing: float, offset=(0.0, 0.0),
            repeat=(1, 1, 1)) -> float:
    """Put the layers of a built framework *spacing* apart.

    ``repeat[2]`` layers to a cell when the net was repeated along
    *c*, each one step of :func:`stacking_vector` above the last.
    The framework, the net it was built on and every placed block are
    moved together, because each of the three is read afterwards --
    by ``write_cif``, by :func:`xtal.mof.build.draw_net` and by
    :func:`xtal.mof.build.bond_joints` respectively -- and a vertex
    looked for at a position its block no longer has would draw the
    net over the wrong atom.

    *spacing* is between the sheets' **mean planes**; inside itself
    each sheet is moved as a whole.

    Returns the layer's thickness, the out-of-plane spread of one
    sheet's atoms about its own middle: the number a spacing smaller
    than it would collide with, and one the caller says.
    """
    atoms = framework.atoms
    old = np.array(atoms.cell, dtype=float)
    layers = int(repeat[2])
    step = stacking_vector(old, spacing, offset, repeat)
    new = old.copy()
    new[2] = layers * step
    inverse = np.linalg.inv(old)

    def layer_of(positions):
        # Which layer each point belongs to, read off the *built*
        # cell and never the new one: there c is a hundred Angstrom
        # and a layer a few, so a point is never near half way
        # between two, where in a cell 3.4 A tall the far side of a
        # paddlewheel already is.  Unwrapped -- an atom a hair below
        # the plane is in layer 0, not the cell's last.
        return np.round((positions @ inverse)[:, 2] * layers)

    before = atoms.get_positions()
    normal = np.cross(old[0], old[1])
    normal /= np.linalg.norm(normal)
    rise = float(old[2] @ normal) / layers
    own = layer_of(before)
    height = before @ normal - own * rise
    # Where each sheet's mean plane sits off the one it was built
    # for.  PORMAKE does not put them all on it: on hcb x (1,1,2) one
    # sheet is 0.021 A above its plane and the other exactly on it, so
    # carrying each sheet's own offset across made "3.3 A apart"
    # 3.28.  Each sheet is lifted until its middle is one spacing
    # above the last one's, and its shape inside is left as it was.
    drift = {}
    for k in range(layers):
        mine = np.mod(own, layers) == k
        if mine.any():
            drift[k] = float(height[mine].mean())
    base = drift.get(0, 0.0)

    def lift(k):
        return np.array([base - drift.get(int(i) % layers, base)
                         for i in k])

    thickness = float(np.ptp(height + lift(own)))

    def moved(positions):
        positions = np.asarray(positions, dtype=float)
        k = layer_of(positions)
        return (positions + np.outer(k, step - old[2] / layers)
                + np.outer(lift(k), normal))

    atoms.set_positions(moved(before))
    atoms.set_cell(new, scale_atoms=False)
    topology = framework.info.get("topology")
    if topology is not None:
        topology.atoms.set_positions(
            moved(topology.atoms.get_positions()))
        topology.atoms.set_cell(new, scale_atoms=False)
    for block in framework.info.get("located_bbs") or ():
        if block is not None:
            block.atoms.set_positions(
                moved(block.atoms.get_positions()))
    return thickness
