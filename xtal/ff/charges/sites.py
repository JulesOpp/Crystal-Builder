"""
xtal.ff.charges.sites
=====================
Charges per atom of the P1 cell, made charges per *site*, so they can
be written onto the structure (:class:`xtal.commands.ff.SetCharges`)
and leave it in a CIF's ``_atom_site_charge`` or a LAMMPS file.

A site's images are one atom as far as the crystal is concerned, so a
site takes the mean of its images' charges.  An equilibration over a
symmetric cell gives them all the same charge to rounding; where they
differ by more than :data:`SPREAD` the mean is still written and the
spread is said, because it means the cell was not as symmetric as the
group claims -- a structure to look at, not a number to trust.
"""

from __future__ import annotations

import numpy as np

from xtal.core import elements as el
from xtal.core import p1

#: The difference between two images' charges, in e, past which the
#: per-site mean is reported as hiding something.
SPREAD = 1e-3


def per_site(structure, values) -> tuple[list, float]:
    """``(charges, spread)``: the mean of each site's images in
    ``values`` (one per P1 atom; NaN for an atom that has none), and
    the widest disagreement between two images of one site.  A site
    with no value -- a marker -- gets ``None``."""
    cell = p1.expand(structure)
    values = np.asarray(values, float)
    if len(values) != cell.n_atoms:
        raise ValueError(f"got {len(values)} charges for "
                         f"{cell.n_atoms} atoms")
    charges: list = []
    spread = 0.0
    for site in range(structure.n_sites):
        mine = values[cell.site_idx == site]
        mine = mine[np.isfinite(mine)]
        if not len(mine):
            charges.append(None)
            continue
        charges.append(float(mine.mean()))
        spread = max(spread, float(mine.max() - mine.min()))
    return charges, spread


def eqeq_values(structure) -> tuple[np.ndarray, str]:
    """EQeq over ``structure``'s P1 cell, one value per atom of it and
    NaN on a marker -- held back at the door, as an engine holds it."""
    from xtal.ff.charges import eqeq

    cell = p1.expand(structure)
    real = np.array([not el.is_dummy(e) for e in cell.elements])
    values = np.full(cell.n_atoms, np.nan)
    if not real.any():
        raise ValueError("there are no atoms to put charges on")
    clean = structure.copy()
    clean.remove_sites([k for k, s in enumerate(structure.sites)
                        if el.is_dummy(s.element)])
    charges, note = eqeq.equilibrate(p1.expand(clean))
    # Removing marker sites removes exactly the marker atoms and keeps
    # the order of the rest -- see xtal.ff.markers.hold_back.
    values[real] = charges
    return values, note
