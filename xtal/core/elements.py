"""
xtal.core.elements
==================
Per-element reference data: atomic number, name, mass, radii, colour,
and the symbol parsing that turns whatever a file calls an atom
("Fe", "FE", "Fe2+", "Fe1", "O_1") into a clean element symbol.

Masses and radii come from gemmi's built-in element table (covalent
radii are Cordero 2008; van der Waals radii are Bondi where Bondi
defines them).  Only data gemmi does NOT carry lives here:

* ``COLORS``  -- the Jmol/CPK palette, used as the default draw colour.
* ``VALENCE`` -- typical valences, used later by the UFF atom typer.

Every radius here is a *default*.  The Style dock lets the user
override radii and colours per element, and those overrides live in the
document, never in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import gemmi

# ======================================================================
#  COLOURS  (Jmol / CPK palette, hex RGB)
# ======================================================================
# Z = 110-118 have no established convention; Jmol falls back to a deep
# pink, which is what we do too -- it reads as "exotic" on screen.

_COLOR_HEX = {
    "H": "FFFFFF", "He": "D9FFFF", "Li": "CC80FF", "Be": "C2FF00",
    "B": "FFB5B5", "C": "909090", "N": "3050F8", "O": "FF0D0D",
    "F": "90E050", "Ne": "B3E3F5", "Na": "AB5CF2", "Mg": "8AFF00",
    "Al": "BFA6A6", "Si": "F0C8A0", "P": "FF8000", "S": "FFFF30",
    "Cl": "1FF01F", "Ar": "80D1E3", "K": "8F40D4", "Ca": "3DFF00",
    "Sc": "E6E6E6", "Ti": "BFC2C7", "V": "A6A6AB", "Cr": "8A99C7",
    "Mn": "9C7AC7", "Fe": "E06633", "Co": "F090A0", "Ni": "50D050",
    "Cu": "C88033", "Zn": "7D80B0", "Ga": "C28F8F", "Ge": "668F8F",
    "As": "BD80E3", "Se": "FFA100", "Br": "A62929", "Kr": "5CB8D1",
    "Rb": "702EB0", "Sr": "00FF00", "Y": "94FFFF", "Zr": "94E0E0",
    "Nb": "73C2C9", "Mo": "54B5B5", "Tc": "3B9E9E", "Ru": "248F8F",
    "Rh": "0A7D8C", "Pd": "006985", "Ag": "C0C0C0", "Cd": "FFD98F",
    "In": "A67573", "Sn": "668080", "Sb": "9E63B5", "Te": "D47A00",
    "I": "940094", "Xe": "429EB0", "Cs": "57178F", "Ba": "00C900",
    "La": "70D4FF", "Ce": "FFFFC7", "Pr": "D9FFC7", "Nd": "C7FFC7",
    "Pm": "A3FFC7", "Sm": "8FFFC7", "Eu": "61FFC7", "Gd": "45FFC7",
    "Tb": "30FFC7", "Dy": "1FFFC7", "Ho": "00FF9C", "Er": "00E675",
    "Tm": "00D452", "Yb": "00BF38", "Lu": "00AB24", "Hf": "4DC2FF",
    "Ta": "4DA6FF", "W": "2194D6", "Re": "267DAB", "Os": "266696",
    "Ir": "175487", "Pt": "D0D0E0", "Au": "FFD123", "Hg": "B8B8D0",
    "Tl": "A6544D", "Pb": "575961", "Bi": "9E4FB5", "Po": "AB5C00",
    "At": "754F45", "Rn": "428296", "Fr": "420066", "Ra": "007D00",
    "Ac": "70ABFA", "Th": "00BAFF", "Pa": "00A1FF", "U": "008FFF",
    "Np": "0080FF", "Pu": "006BFF", "Am": "545CF2", "Cm": "785CE3",
    "Bk": "8A4FE3", "Cf": "A136D4", "Es": "B31FD4", "Fm": "B31FBA",
    "Md": "B30DA6", "No": "BD0D87", "Lr": "C70066", "Rf": "CC0059",
    "Db": "D1004F", "Sg": "D90045", "Bh": "E00038", "Hs": "E6002E",
    "Mt": "EB0026", "Ds": "EB0026", "Rg": "FF1493", "Cn": "FF1493",
    "Nh": "FF1493", "Fl": "FF1493", "Mc": "FF1493", "Lv": "FF1493",
    "Ts": "FF1493", "Og": "FF1493",
    "D": "FFFFC0",          # deuterium, drawn slightly warm
    "X": "FF1493",          # dummy / unknown
}

DEFAULT_COLOR = (255, 20, 147)          # deep pink: "I don't know this"

# Typical valences, keyed by symbol.  Incomplete on purpose: the UFF
# typer treats a missing entry as "decide from the bond graph".
VALENCE = {
    "H": 1, "D": 1, "Li": 1, "Be": 2, "B": 3, "C": 4, "N": 3, "O": 2,
    "F": 1, "Na": 1, "Mg": 2, "Al": 3, "Si": 4, "P": 3, "S": 2,
    "Cl": 1, "K": 1, "Ca": 2, "Br": 1, "Rb": 1, "Sr": 2, "I": 1,
    "Cs": 1, "Ba": 2,
}

# Pauling electronegativity.  Used to order formulas (the
# electropositive element first, as crystallographers write them) and,
# later, by the force field's charge heuristics.  Noble gases and a few
# synthetic elements have no accepted value and are absent.
ELECTRONEGATIVITY = {
    "H": 2.20, "Li": 0.98, "Be": 1.57, "B": 2.04, "C": 2.55,
    "N": 3.04, "O": 3.44, "F": 3.98, "Na": 0.93, "Mg": 1.31,
    "Al": 1.61, "Si": 1.90, "P": 2.19, "S": 2.58, "Cl": 3.16,
    "K": 0.82, "Ca": 1.00, "Sc": 1.36, "Ti": 1.54, "V": 1.63,
    "Cr": 1.66, "Mn": 1.55, "Fe": 1.83, "Co": 1.88, "Ni": 1.91,
    "Cu": 1.90, "Zn": 1.65, "Ga": 1.81, "Ge": 2.01, "As": 2.18,
    "Se": 2.55, "Br": 2.96, "Rb": 0.82, "Sr": 0.95, "Y": 1.22,
    "Zr": 1.33, "Nb": 1.60, "Mo": 2.16, "Tc": 1.90, "Ru": 2.20,
    "Rh": 2.28, "Pd": 2.20, "Ag": 1.93, "Cd": 1.69, "In": 1.78,
    "Sn": 1.96, "Sb": 2.05, "Te": 2.10, "I": 2.66, "Xe": 2.60,
    "Cs": 0.79, "Ba": 0.89, "La": 1.10, "Ce": 1.12, "Pr": 1.13,
    "Nd": 1.14, "Pm": 1.13, "Sm": 1.17, "Eu": 1.20, "Gd": 1.20,
    "Tb": 1.10, "Dy": 1.22, "Ho": 1.23, "Er": 1.24, "Tm": 1.25,
    "Yb": 1.10, "Lu": 1.27, "Hf": 1.30, "Ta": 1.50, "W": 2.36,
    "Re": 1.90, "Os": 2.20, "Ir": 2.20, "Pt": 2.28, "Au": 2.54,
    "Hg": 2.00, "Tl": 1.62, "Pb": 2.33, "Bi": 2.02, "Po": 2.00,
    "At": 2.20, "Rn": 2.20, "Fr": 0.79, "Ra": 0.90, "Ac": 1.10,
    "Th": 1.30, "Pa": 1.50, "U": 1.38, "Np": 1.36, "Pu": 1.28,
    "Am": 1.13, "Cm": 1.28, "Bk": 1.30, "Cf": 1.30, "Es": 1.30,
    "Fm": 1.30, "Md": 1.30, "No": 1.30, "Lr": 1.30, "D": 2.20,
}

# vdW radii gemmi leaves at a metallic/ionic value that looks wrong in
# a space-filling drawing.  Alvarez (2013) values for the elements we
# most often draw as spheres.
_VDW_OVERRIDE = {
    "Fe": 2.44, "Co": 2.40, "Ni": 2.40, "Cu": 2.38, "Zn": 2.39,
    "Mn": 2.45, "Cr": 2.45, "V": 2.53, "Ti": 2.57, "Sc": 2.58,
    "Mo": 2.45, "Ru": 2.46, "Rh": 2.44, "Pd": 2.15, "Ag": 2.53,
    "W": 2.46, "Re": 2.46, "Os": 2.46, "Ir": 2.46, "Pt": 2.44,
    "Au": 2.41, "Hg": 2.32, "U": 2.42, "Th": 2.43, "Zr": 2.52,
    "Nb": 2.56, "Hf": 2.52, "Ta": 2.51,
}

# Full names, for the Inspector and tooltips (gemmi's Element.name is
# the symbol, not the name).
_NAMES = {
    "H": "Hydrogen", "He": "Helium", "Li": "Lithium",
    "Be": "Beryllium", "B": "Boron", "C": "Carbon", "N": "Nitrogen",
    "O": "Oxygen", "F": "Fluorine", "Ne": "Neon", "Na": "Sodium",
    "Mg": "Magnesium", "Al": "Aluminium", "Si": "Silicon",
    "P": "Phosphorus", "S": "Sulfur", "Cl": "Chlorine", "Ar": "Argon",
    "K": "Potassium", "Ca": "Calcium", "Sc": "Scandium",
    "Ti": "Titanium", "V": "Vanadium", "Cr": "Chromium",
    "Mn": "Manganese", "Fe": "Iron", "Co": "Cobalt", "Ni": "Nickel",
    "Cu": "Copper", "Zn": "Zinc", "Ga": "Gallium", "Ge": "Germanium",
    "As": "Arsenic", "Se": "Selenium", "Br": "Bromine",
    "Kr": "Krypton", "Rb": "Rubidium", "Sr": "Strontium",
    "Y": "Yttrium", "Zr": "Zirconium", "Nb": "Niobium",
    "Mo": "Molybdenum", "Tc": "Technetium", "Ru": "Ruthenium",
    "Rh": "Rhodium", "Pd": "Palladium", "Ag": "Silver",
    "Cd": "Cadmium", "In": "Indium", "Sn": "Tin", "Sb": "Antimony",
    "Te": "Tellurium", "I": "Iodine", "Xe": "Xenon", "Cs": "Caesium",
    "Ba": "Barium", "La": "Lanthanum", "Ce": "Cerium",
    "Pr": "Praseodymium", "Nd": "Neodymium", "Pm": "Promethium",
    "Sm": "Samarium", "Eu": "Europium", "Gd": "Gadolinium",
    "Tb": "Terbium", "Dy": "Dysprosium", "Ho": "Holmium",
    "Er": "Erbium", "Tm": "Thulium", "Yb": "Ytterbium",
    "Lu": "Lutetium", "Hf": "Hafnium", "Ta": "Tantalum",
    "W": "Tungsten", "Re": "Rhenium", "Os": "Osmium", "Ir": "Iridium",
    "Pt": "Platinum", "Au": "Gold", "Hg": "Mercury", "Tl": "Thallium",
    "Pb": "Lead", "Bi": "Bismuth", "Po": "Polonium", "At": "Astatine",
    "Rn": "Radon", "Fr": "Francium", "Ra": "Radium",
    "Ac": "Actinium", "Th": "Thorium", "Pa": "Protactinium",
    "U": "Uranium", "Np": "Neptunium", "Pu": "Plutonium",
    "Am": "Americium", "Cm": "Curium", "Bk": "Berkelium",
    "Cf": "Californium", "Es": "Einsteinium", "Fm": "Fermium",
    "Md": "Mendelevium", "No": "Nobelium", "Lr": "Lawrencium",
    "Rf": "Rutherfordium", "Db": "Dubnium", "Sg": "Seaborgium",
    "Bh": "Bohrium", "Hs": "Hassium", "Mt": "Meitnerium",
    "Ds": "Darmstadtium", "Rg": "Roentgenium", "Cn": "Copernicium",
    "Nh": "Nihonium", "Fl": "Flerovium", "Mc": "Moscovium",
    "Lv": "Livermorium", "Ts": "Tennessine", "Og": "Oganesson",
    "D": "Deuterium", "X": "Dummy",
}

_SYMBOL_RE = re.compile(r"^([A-Za-z]{1,2})")


# ======================================================================
#  ELEMENT RECORD
# ======================================================================

@dataclass(frozen=True)
class Element:
    """Immutable reference data for one element."""

    symbol: str
    z: int
    name: str            # "Iron", not "Fe"
    mass: float
    covalent_radius: float      # Angstrom, Cordero 2008
    vdw_radius: float           # Angstrom
    color: tuple[int, int, int]
    is_metal: bool

    @property
    def valence(self) -> int | None:
        return VALENCE.get(self.symbol)


#: Symbols that name a *position* rather than an element: the centre
#: of a ring, the vertex of a net, somewhere a chemist wanted marked.
#: They carry a covalent radius in the tables only because every
#: symbol does, and everything that reasons about chemistry has to
#: leave them out -- perception (:data:`xtal.core.bonding.BondRules`),
#: the force field, and every external binary that would be handed a
#: structure containing one.
#:
#: ``D`` is not here: deuterium is hydrogen with a neutron.
DUMMY_ELEMENTS = frozenset({"X"})


def is_dummy(symbol: str) -> bool:
    return symbol in DUMMY_ELEMENTS


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


@lru_cache(maxsize=256)
def element(symbol: str) -> Element:
    """Look up an element by (possibly messy) symbol.

    Raises ValueError if the symbol cannot be resolved -- callers that
    want a tolerant fallback should use ``parse_symbol`` first.
    """
    sym = parse_symbol(symbol)
    ge = gemmi.Element(sym)
    if ge.atomic_number == 0 and sym not in ("X", "D"):
        raise ValueError(f"unknown element symbol: {symbol!r}")
    vdw = _VDW_OVERRIDE.get(sym, ge.vdw_r)
    return Element(
        symbol=sym,
        z=ge.atomic_number,
        name=_NAMES.get(sym, sym),
        mass=ge.weight,
        covalent_radius=ge.covalent_r,
        vdw_radius=vdw,
        color=_hex_to_rgb(_COLOR_HEX.get(sym, "FF1493")),
        is_metal=ge.is_metal,
    )


@lru_cache(maxsize=256)
def parse_symbol(text: str) -> str:
    """Normalise anything file-shaped into an element symbol.

        "fe"      -> "Fe"      (case is fixed)
        "FE"      -> "Fe"
        "Fe2+"    -> "Fe"      (oxidation state stripped)
        "Fe1"     -> "Fe"      (CIF label)
        "O_23"    -> "O"
        "Ow"      -> "O"       (2-letter guess fails, 1-letter wins)

    The two-letter reading is tried first, then the one-letter reading;
    this is the same order CIF readers use, and it is why "Co" is
    cobalt but "C1" is carbon.
    """
    if not text:
        raise ValueError("empty element symbol")
    m = _SYMBOL_RE.match(text.strip())
    if not m:
        raise ValueError(f"no element symbol in {text!r}")
    raw = m.group(1)
    if len(raw) == 2:
        two = raw[0].upper() + raw[1].lower()
        if two in _COLOR_HEX:
            return two
    one = raw[0].upper()
    if one in _COLOR_HEX:
        return one
    raise ValueError(f"unknown element symbol: {text!r}")


def canonical_symbol(text: str) -> str | None:
    """Strict reading of an element symbol: the whole string must be
    one, case aside.  ``"fe"`` and ``"FE"`` give ``"Fe"``; ``"Fe2+"``,
    ``"C1"`` and ``"Kryptonite"`` give ``None``.

    This is what UI input uses.  :func:`parse_symbol` is the forgiving
    reading for file contents, where "Ow" really does mean oxygen and
    refusing it would fail to open the file -- but where a person types
    into a box, a prefix match silently turning "Kryptonite" into
    krypton is a bug, not a convenience.
    """
    if not text:
        return None
    cleaned = text.strip()
    if len(cleaned) > 2:
        return None
    candidate = cleaned[0].upper() + cleaned[1:].lower()
    return candidate if candidate in _COLOR_HEX else None


def is_symbol(text: str) -> bool:
    return canonical_symbol(text) is not None


def symbol_from_z(z: int) -> str:
    """Element symbol for an atomic number (1-118)."""
    if not 1 <= z <= 118:
        raise ValueError(f"atomic number out of range: {z}")
    return gemmi.Element(z).name


def atomic_number(symbol: str) -> int:
    return element(symbol).z


def mass(symbol: str) -> float:
    return element(symbol).mass


def covalent_radius(symbol: str) -> float:
    return element(symbol).covalent_radius


def vdw_radius(symbol: str) -> float:
    return element(symbol).vdw_radius


def electronegativity(symbol: str) -> float | None:
    """Pauling electronegativity, or None where none is defined."""
    return ELECTRONEGATIVITY.get(parse_symbol(symbol))


def color(symbol: str) -> tuple[int, int, int]:
    """Default draw colour, as 0-255 RGB."""
    try:
        return element(symbol).color
    except ValueError:
        return DEFAULT_COLOR


def all_symbols() -> list[str]:
    """Every symbol we have colour data for, in atomic-number order."""
    syms = [s for s in _COLOR_HEX if s not in ("X", "D")]
    return sorted(syms, key=lambda s: gemmi.Element(s).atomic_number)
