"""
xtal.ff.dftb.params
===================
The two tables a DFTB+ input cannot be written without.

**The maximum angular momentum of every element**, which DFTB+
requires and does not derive.  It is a property of the Slater-Koster
set rather than of the element -- 3ob gives chlorine a d shell and mio
does not -- so a table can only be a good default, and the one here
follows 3ob-3-1 and mio-1-1 where they agree and 3ob where they do
not.  It is overridable per element, because the day a set disagrees
with this table is the day the run is wrong in a way nothing reports:
DFTB+ takes what it is given and returns a number.

**The Hubbard derivatives** DFTB3 needs, from the 3ob parameterisation
(Gaus, Goyal and Elstner, *J. Chem. Theory Comput.* 2011).  Only for
the elements 3ob covers, because they are fitted to it and using them
with another set is not a smaller approximation, it is a different
model.

And a catalogue of the sets themselves, so the panel can name them --
which of them exists on this machine is decided by looking, in
:mod:`xtal.ff.dftb.hsd`.
"""

from __future__ import annotations

#: Element -> the highest shell to include.  Anything not here falls
#: back on :func:`angular_momentum`, which is a rule and not a
#: measurement, and says so.
ANGULAR_MOMENTUM = {
    "H": "s", "He": "s",
    "Li": "p", "Be": "p", "B": "p", "C": "p", "N": "p", "O": "p",
    "F": "p", "Ne": "p",
    "Na": "p", "Mg": "p", "Al": "p", "Si": "d", "P": "d", "S": "d",
    "Cl": "d", "Ar": "d",
    "K": "p", "Ca": "p",
    "Sc": "d", "Ti": "d", "V": "d", "Cr": "d", "Mn": "d", "Fe": "d",
    "Co": "d", "Ni": "d", "Cu": "d", "Zn": "d",
    "Ga": "d", "Ge": "d", "As": "d", "Se": "d", "Br": "d", "Kr": "d",
    "Rb": "p", "Sr": "p", "Y": "d", "Zr": "d", "Nb": "d", "Mo": "d",
    "Tc": "d", "Ru": "d", "Rh": "d", "Pd": "d", "Ag": "d", "Cd": "d",
    "In": "d", "Sn": "d", "Sb": "d", "Te": "d", "I": "d", "Xe": "d",
    "Cs": "p", "Ba": "p", "La": "d", "Hf": "d", "Ta": "d", "W": "d",
    "Re": "d", "Os": "d", "Ir": "d", "Pt": "d", "Au": "d", "Hg": "d",
    "Tl": "d", "Pb": "d", "Bi": "d", "Po": "d", "At": "d", "Rn": "d",
}

#: Hubbard derivatives (atomic units) for DFTB3 with 3ob.  Fitted to
#: that set and to no other.
HUBBARD_DERIVS = {
    "H": -0.1857, "C": -0.1492, "N": -0.1535, "O": -0.1575,
    "F": -0.1623, "Na": -0.0454, "Mg": -0.02, "P": -0.14,
    "S": -0.11, "Cl": -0.0697, "K": -0.0339, "Ca": -0.0340,
    "Zn": -0.03, "Br": -0.0573, "I": -0.0433,
}

#: The sets a user is likely to have, with what each is for.  Names,
#: not paths: where they are is a preference, and whether they are
#: there is answered by looking.
PARAMETER_SETS = (
    ("3ob", "3ob -- organic and biological molecules, DFTB3"),
    ("mio", "mio -- the original organic set, SCC-DFTB"),
    ("matsci", "matsci -- inorganic solids and surfaces"),
    ("pbc", "pbc -- periodic solids, silicon and oxides"),
    ("znorg", "znorg -- zinc with organic ligands"),
    ("trans3d", "trans3d -- first-row transition metals"),
)

#: Which Hamiltonians there are, in the order they came about.  This
#: is the field a user coming from DFT looks for the functional in,
#: and it is the nearest thing DFTB has to one.
METHODS = (
    ("dftb3", "DFTB3 (third order, needs 3ob)"),
    ("scc", "SCC-DFTB (self-consistent charges)"),
    ("non-scc", "Non-SCC DFTB (fastest, no charge transfer)"),
)

#: Dispersion corrections DFTB+ can add.  DFTB has none of its own,
#: and a framework's pore size is a dispersion-bound number, so this
#: is not an optional refinement for the structures this application
#: is for.
DISPERSIONS = (
    ("none", "None"),
    ("d3", "DFT-D3 with Becke-Johnson damping"),
    ("lj", "Lennard-Jones (universal force field radii)"),
)


def angular_momentum(symbol: str) -> tuple[str, bool]:
    """``(shell, was_known)`` for an element.

    The flag is what the caller warns about.  A guessed angular
    momentum does not make DFTB+ fail -- it makes it answer a
    different question -- so the guess has to be visible.
    """
    if symbol in ANGULAR_MOMENTUM:
        return ANGULAR_MOMENTUM[symbol], True
    from xtal.core import elements
    # The rule the table itself follows: p below sodium, d above.
    return ("p" if elements.atomic_number(symbol) < 11 else "d"), False


def parse_overrides(text: str) -> dict:
    """``"Cl=d, Zn=d"`` -> ``{"Cl": "d", "Zn": "d"}``.

    A free-text field rather than a table because it is the escape
    hatch for a disagreement between a parameter set and the built-in
    defaults, which is rare, per-set, and impossible to enumerate.
    """
    out = {}
    for piece in str(text or "").replace(";", ",").split(","):
        name, sep, shell = piece.partition("=")
        if not sep:
            continue
        name, shell = name.strip().capitalize(), shell.strip().lower()
        if shell not in ("s", "p", "d", "f"):
            raise ValueError(
                f"{shell!r} is not a shell; write s, p, d or f, as in "
                f"'Cl=d'")
        out[name] = shell
    return out
