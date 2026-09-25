"""
xtal.ff.isotopes
================
An isotope is its element, to an energy.

Every engine in this application returns a Born-Oppenheimer energy:
the electrons are solved for with the nuclei held still, so the surface
the atoms move on depends on the nuclear *charge* and not the nuclear
mass.  Deuterium's surface is hydrogen's.  A neutron structure -- the
COD's MIL-53(Cr) is one, and every engine refused it -- therefore has
exactly the energy, forces, stress and equilibrated charges of the same
structure written with ``H``, and handing the engine ``H`` is not an
approximation.

Mass does matter to vibration, and to nothing else computed here.  The
DFTB+ modes run writes its own input rather than coming through the
engine door, so it still meets ``D`` as ``D`` and refuses; renaming
there would give hydrogen's frequencies for a deuterated crystal
without a word.

Like :mod:`xtal.ff.markers`, this is applied once, at
:meth:`xtal.ff.registry.Engine.__call__`, so an engine written next
year gets it without remembering to.
"""

from __future__ import annotations

#: Isotope symbol -> the element whose energy surface it shares.
#: ``T`` is not here because nothing reads it: ``elements.parse_symbol``
#: has no tritium, so a file written with one does not open.
ISOTOPES = {"D": "H"}

#: What the run says when it did this, once per calculator.
NOTE = ("deuterium was computed as hydrogen: the energy surface is the "
        "same for both, and nothing in a relaxation uses the mass")


def has_isotopes(structure) -> bool:
    return any(site.element in ISOTOPES for site in structure.sites)


def as_elements(structure):
    """``structure``, or a copy with every isotope written as its
    element.

    The copy keeps the sites in their order, so its P1 cell is the
    original's atom for atom and nothing downstream needs a mapping --
    unlike holding a marker back, which removes atoms.  The structure
    itself is never touched: it is the user's, and still says ``D``.
    """
    if not has_isotopes(structure):
        return structure
    copy = structure.copy()
    for site in copy.sites:
        site.element = ISOTOPES.get(site.element, site.element)
    copy.touch()
    return copy
