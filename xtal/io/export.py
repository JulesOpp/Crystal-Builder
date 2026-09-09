"""
xtal.io.export
==============
What a file leaving this application should contain.

A CIF written *into the workspace* is the document -- it carries the
markers the user placed and the net drawn over a framework, because
that is what they built and a file that loses half of it is not a copy
of anything (see :mod:`xtal.io.cif_writer`).  A CIF written *for
somebody else* is a crystal, and neither of those belongs in it:

* a **dummy atom** is a marker and not chemistry, so a program that
  reads one gets an element it has never heard of sitting in the cell
  -- the same reason `markers.hold_back` exists for a force field and
  `job.without_dummies` for a module run.  This is that rule at the
  one remaining door.
* a **net edge** is not a bond.  It joins the centres of two building
  blocks through empty space, and anything that reads it as chemistry
  reads a framework held together by bonds four times too long.
* a **suppressed** bond is the record of one deliberately deleted.  It
  is the absence of a bond, so writing it as a row in a bond loop
  says the opposite of what it means.

What survives is the chemistry: the atoms, and the bonds that are
bonds.
"""

from __future__ import annotations

from xtal.core import elements as el
from xtal.core.structure import TOPOLOGY, Structure

#: The bond kinds that are not a bond somebody else should be told
#: about.  ``explicit`` is the only one that is.
NOT_CHEMISTRY = frozenset({TOPOLOGY, "suppressed"})


def for_export(structure: Structure) -> Structure:
    """``structure`` as a file for another program should hold it.

    A copy, and only when there is something to take out -- a crystal
    with no markers and no net is every crystal anybody has opened,
    and it comes back untouched rather than duplicated.
    """
    markers = [i for i, site in enumerate(structure.sites)
               if el.is_dummy(site.element)]
    markup = [b for b in structure.bonds if b.kind in NOT_CHEMISTRY]
    if not markers and not markup:
        return structure
    clean = structure.copy()
    clean.bonds = [b for b in clean.bonds
                   if b.kind not in NOT_CHEMISTRY]
    if markers:
        # After the bonds, not before: removing the sites renumbers
        # what is left, and the net edges are exactly the ones hanging
        # off the markers.
        clean.remove_sites(markers)
    return clean


def what_is_dropped(structure: Structure) -> str:
    """One sentence naming what :func:`for_export` would take out, or
    ``""`` when the answer is nothing.

    For the export dialog, which says what a format drops before it
    writes -- and this is a thing *this application* drops, which is
    worth saying in the same place and the same voice.
    """
    markers = sum(1 for site in structure.sites
                  if el.is_dummy(site.element))
    edges = sum(1 for b in structure.bonds if b.kind == TOPOLOGY)
    said = []
    if markers:
        said.append(f"{markers} dummy atom"
                    f"{'s' if markers != 1 else ''}")
    if edges:
        said.append(f"{edges} net edge{'s' if edges != 1 else ''}")
    if not said:
        return ""
    return (f"{' and '.join(said)} will not be written -- a marker is "
            f"not chemistry and a net edge is not a bond")
